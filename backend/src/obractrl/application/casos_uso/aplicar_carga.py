"""Aplicadores: bajar una lectura validada al catálogo (§9.2 paso "Commit").

Spec §9.2 (pipeline) · §10.2 (los tres modos) · §10.3 (bandeja) · §10.5
(valuación y motivos) · §10.6 (qué trae cada archivo) · §10.8 (versión y
snapshot) · §12.11 (la aplicación orquesta el dominio por puertos).

Un **aplicador** por archivo del §10.6. Todos hacen lo mismo en el mismo
orden y por eso comparten forma:

1. Traen el conjunto **vigente** por sus puertos (§10.8 compara contra la
   versión vigente, así que cargarlo entero no es un lujo: es el diff).
2. Homologan lo que el archivo trae contra los catálogos (§10.3). Lo que no
   cruza **no se inventa**: cae en la bandeja.
3. Calculan el diff con `domain.cargadores.versionado` según el modo (§10.2).
4. Escriben, dejando en el `snapshot` el antes/después de cada registro para
   que el lote se pueda revertir como unidad (§10.8).

En `dry_run` se hace todo menos el paso 4: el resumen y la bandeja salen
idénticos, que es lo que hace útil a la vista previa (§9.3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from obractrl.application.puertos.cargadores import RepositorioCargas
from obractrl.application.puertos.repositorios import (
    RepositorioConceptos,
    RepositorioContratistas,
    RepositorioFamilias,
    RepositorioInsumos,
    RepositorioMateriales,
    RepositorioNivelesEtapas,
    RepositorioObras,
    RepositorioPresupuestos,
    RepositorioPrototipoNodo,
    RepositorioPrototipos,
    RepositorioProyectos,
    RepositorioUnidades,
)
from obractrl.domain.cargadores.almacen import FilaMovimiento, importe_con_iva
from obractrl.domain.cargadores.cpu import ConceptoCargado
from obractrl.domain.cargadores.homologacion import Homologador
from obractrl.domain.cargadores.materiales import FilaMaterial
from obractrl.domain.cargadores.presupuesto import (
    ArbolPrototipoCargado,
    NodoLeido,
    TipoNodoPresupuesto,
    es_etapa_con_componentes_directos,
)
from obractrl.domain.cargadores.prototipos import FilaPrototipo
from obractrl.domain.cargadores.reporte import (
    ErrorDeFila,
    LecturaCarga,
    PendientePropuesto,
    TipoPendiente,
)
from obractrl.domain.cargadores.versionado import Cambio, Diff, diferenciar
from obractrl.domain.catalogos.apu import (
    Componente,
    ErrorDeAPU,
    VersionCPU,
    calcular_cpu,
    publicar_version,
)
from obractrl.domain.catalogos.reglas import resolver_iva
from obractrl.domain.materiales.reglas import ErrorDeMaterial, validar_signo_salida
from obractrl.domain.proyectos.reglas import ErrorDeProyecto, Prototipo
from obractrl.domain.shared.diccionario import (
    CategoriaExplosion,
    ModoCarga,
    TipoConcepto,
    TipoHijoExplosion,
    TipoInsumo,
)
from obractrl.domain.shared.valores import Dinero, PrecioUnitario

__all__ = [
    "Aplicacion",
    "AplicadorAlmacen",
    "AplicadorCPU",
    "AplicadorDeCarga",
    "AplicadorMateriales",
    "AplicadorPresupuesto",
    "AplicadorPrototipos",
]

_ESTATUS_BAJA = "inactivo"
"""Baja **lógica** para el modo Reemplazar (§10.2).

Un `delete` real no es opción: `explosion` y `salida_almacen` referencian
`insumo`, y borrar el catálogo se llevaría por delante APUs y movimientos
históricos que la carga no está sustituyendo. "Sustituye todo el conjunto"
se cumple sacando de circulación lo que el archivo ya no trae.
"""


@dataclass(frozen=True, slots=True)
class Aplicacion:
    """Lo que un aplicador reporta al caso de uso."""

    diff: Diff
    operaciones: tuple[dict[str, Any], ...] = ()
    """Antes/después por registro tocado, en orden de ejecución (§10.8)."""

    pendientes: tuple[PendientePropuesto, ...] = ()
    errores: tuple[ErrorDeFila, ...] = ()
    insertados: int = 0
    actualizados: int = 0
    omitidos: int = 0
    detalle: dict[str, Any] = field(default_factory=dict)
    """Datos propios del cargador para el resumen (§9.4)."""


@runtime_checkable
class AplicadorDeCarga(Protocol):
    """Puerto de escritura de una carga. Uno por archivo del §10.6."""

    async def aplicar(
        self,
        lectura: LecturaCarga,
        *,
        modo: ModoCarga,
        dry_run: bool,
        carga_id: UUID,
    ) -> Aplicacion: ...


def _operacion(
    tabla: str,
    registro_id: UUID | str,
    operacion: str,
    *,
    antes: dict[str, Any] | None = None,
    despues: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "tabla": tabla,
        "registro_id": str(registro_id),
        "operacion": operacion,
        "antes": antes,
        "despues": despues,
    }


def _pendiente_de_mapeo(
    entidad: str, valor: str, fila: int, *, critico: bool
) -> PendientePropuesto:
    return PendientePropuesto(
        tipo=TipoPendiente.MAPEO_NO_RECONOCIDO,
        entidad=entidad,
        valor_origen=valor,
        propuesta={"accion": f"Homologar {entidad} o darlo de alta en el catálogo."},
        critico=critico,
        origen_ref=f"fila {fila}",
    )


# --- Materiales (§10.6 `CABECERAS_MATERIALES.xlsx`) -----------------------

_CAMPOS_MATERIAL = (
    "descripcion",
    "unidad_id",
    "familia_id",
    "costo_base",
    "costo_base_actualizado",
    "costo_promedio_almacen",
    "costo_ultimo",
    "iva_aplica",
)
"""Campos que este cargador gobierna. El diff solo mira estos: si el archivo
no habla de un campo, cambiarlo no sería carga sino invención."""

_CAMPOS_RESTAURABLES_INSUMO = (
    *_CAMPOS_MATERIAL,
    "origen",
    "factor_conversion",
    "estatus",
)
"""Lo que el snapshot guarda como ``antes``: debe coincidir con lo que la
reversa sabe restaurar (`adapters/repos/cargas_sql._RESTAURAR`)."""


class AplicadorMateriales:
    """Catálogo de materiales (§10.6, §10.1).

    Un material es un `Insumo` con ``tipo='material'`` (§7.3): esto alimenta
    el catálogo de insumos, no una tabla aparte.
    """

    def __init__(
        self,
        *,
        insumos: RepositorioInsumos,
        unidades: RepositorioUnidades,
        familias: RepositorioFamilias,
        cargas: RepositorioCargas,
    ) -> None:
        self._insumos = insumos
        self._unidades = unidades
        self._familias = familias
        self._cargas = cargas

    async def aplicar(
        self,
        lectura: LecturaCarga,
        *,
        modo: ModoCarga,
        dry_run: bool,
        carga_id: UUID,
    ) -> Aplicacion:
        vigentes_filas = await self._insumos.listar(
            tipo=str(TipoInsumo.MATERIAL), solo_activos=False
        )
        por_clave = {str(fila["clave"]): fila for fila in vigentes_filas}

        unidades_filas = await self._unidades.listar(solo_activos=False)
        unidades = Homologador.desde(
            unidades_filas, mapeos=await self._cargas.mapeos("unidad")
        )
        id_unidad = {str(f["clave"]): f["id"] for f in unidades_filas}

        familias_filas = await self._familias.listar(
            aplica_a="material", solo_activos=False
        )
        familias = Homologador.desde(
            familias_filas, mapeos=await self._cargas.mapeos("familia")
        )
        id_familia = {str(f["clave"]): f["id"] for f in familias_filas}

        pendientes: list[PendientePropuesto] = []
        entrantes: dict[str, dict[str, Any]] = {}

        for registro in lectura.registros:
            material: FilaMaterial = registro  # type: ignore[assignment]
            actual = por_clave.get(material.llave, {})

            unidad_id = actual.get("unidad_id")
            if material.unidad:
                clave_unidad = unidades.resolver(material.unidad)
                if clave_unidad is None:
                    pendientes.append(
                        PendientePropuesto(
                            tipo=TipoPendiente.UNIDAD,
                            entidad="unidad",
                            valor_origen=material.unidad,
                            propuesta={
                                "material": material.llave,
                                "accion": (
                                    "Dar de alta la unidad con su factor de "
                                    "conversión u homologarla a una existente."
                                ),
                            },
                            origen_ref=f"fila {material.fila}",
                        )
                    )
                else:
                    unidad_id = id_unidad.get(clave_unidad)

            familia_id = actual.get("familia_id")
            if material.familia:
                clave_familia = familias.resolver(material.familia)
                if clave_familia is None:
                    pendientes.append(
                        _pendiente_de_mapeo(
                            "familia", material.familia, material.fila, critico=False
                        )
                    )
                else:
                    familia_id = id_familia.get(clave_familia)

            # Regla del cargador: **lo que el archivo no trae, no se toca**.
            # Un archivo sin columna de costo o sin casilla de IVA actualiza
            # descripciones sin vaciar el resto del catálogo — que es lo que
            # el modo Actualizar promete (§10.2) y lo que el §3.4 exige del
            # catálogo como fuente de verdad.
            entrantes[material.llave] = {
                "descripcion": material.descripcion,
                "unidad_id": unidad_id,
                "familia_id": familia_id,
                "costo_base": _o_vigente(material.costo_base, actual, "costo_base"),
                # §10.5: "costo_base_actualizado = el costo último más
                # reciente (costo vigente)".
                "costo_base_actualizado": _o_vigente(
                    material.costo_ultimo, actual, "costo_base_actualizado"
                ),
                "costo_promedio_almacen": _o_vigente(
                    material.costo_promedio, actual, "costo_promedio_almacen"
                ),
                "costo_ultimo": _o_vigente(material.costo_ultimo, actual, "costo_ultimo"),
                "iva_aplica": _o_vigente(material.iva, actual, "iva_aplica"),
            }

        vigentes = {
            clave: {campo: fila.get(campo) for campo in _CAMPOS_MATERIAL}
            for clave, fila in por_clave.items()
        }
        diff = diferenciar(vigentes=vigentes, entrantes=entrantes, modo=modo)

        operaciones: list[dict[str, Any]] = []
        if not dry_run:
            for alta in diff.altas:
                nuevo_id = await self._insumos.crear(
                    {
                        "tipo": str(TipoInsumo.MATERIAL),
                        "clave": alta.clave,
                        "descripcion": alta.despues["descripcion"],
                        "unidad_id": alta.despues["unidad_id"],
                        "familia_id": alta.despues["familia_id"],
                        "costo_base": alta.despues["costo_base"],
                        "iva_aplica": alta.despues["iva_aplica"],
                    }
                )
                extras = {
                    campo: alta.despues[campo]
                    for campo in (
                        "costo_base_actualizado",
                        "costo_promedio_almacen",
                        "costo_ultimo",
                    )
                    if alta.despues.get(campo) is not None
                }
                if extras:
                    await self._insumos.actualizar(nuevo_id, extras)
                operaciones.append(
                    _operacion("insumo", nuevo_id, "insert", despues=dict(alta.despues))
                )

            for cambio in diff.cambios:
                fila = por_clave[cambio.clave]
                # Se escriben **todos** los campos gestionados, incluidos los
                # que quedaron en `None`: a estas alturas `None` ya no
                # significa "el archivo no lo trae" —eso se resolvió al armar
                # `entrantes`— sino "así queda".
                await self._insumos.actualizar(fila["id"], dict(cambio.despues))
                operaciones.append(
                    _operacion(
                        "insumo",
                        fila["id"],
                        "update",
                        antes=_recorte(fila, _CAMPOS_RESTAURABLES_INSUMO),
                        despues=dict(cambio.despues),
                    )
                )

            for baja in diff.bajas:
                fila = por_clave[baja.clave]
                await self._insumos.actualizar(fila["id"], {"estatus": _ESTATUS_BAJA})
                operaciones.append(
                    _operacion(
                        "insumo",
                        fila["id"],
                        "update",
                        antes=_recorte(fila, _CAMPOS_RESTAURABLES_INSUMO),
                        despues={"estatus": _ESTATUS_BAJA},
                    )
                )

        return Aplicacion(
            diff=diff,
            operaciones=tuple(operaciones),
            pendientes=tuple(pendientes),
            insertados=len(diff.altas),
            actualizados=len(diff.cambios) + len(diff.bajas),
            omitidos=diff.omitidos + lectura.omitidos,
        )


def _recorte(fila: dict[str, Any], campos: tuple[str, ...]) -> dict[str, Any]:
    return {campo: fila.get(campo) for campo in campos}


def _o_vigente(valor: Any, actual: dict[str, Any], campo: str) -> Any:
    """``valor`` si el archivo lo trajo; si no, lo que ya está en el catálogo.

    Es la regla que separa "el archivo dice que vale cero" de "el archivo no
    habla de esto". Sin ella, cargar un `.xlsx` sin la columna de costo
    pondría en cero todo el catálogo (§3.4: el catálogo es la fuente de
    verdad; una carga lo actualiza, no lo vacía).
    """
    return actual.get(campo) if valor is None else valor


# --- CPU / Conceptos (§10.6 `CABECERAS_CPU.xlsx`) -------------------------


class AplicadorCPU:
    """Catálogo de conceptos con su APU (§10.6, §7.3).

    Cada concepto del archivo se convierte en: el `concepto` (alta o
    actualización), su **composición** (`explosion`) sustituida completa, y una
    **versión nueva de CPU** cuyo precio sale de explotar esa composición
    (§7.3: el CPU se calcula, no se captura).

    Un componente cuyo insumo no está en el catálogo **detiene ese concepto**,
    no solo ese renglón: un APU con un hueco daría un precio menor al real y
    ese precio se propaga a presupuesto y estimación. El concepto se omite y
    el insumo va a la bandeja como pendiente **crítico** (§10.3).
    """

    def __init__(
        self,
        *,
        conceptos: RepositorioConceptos,
        insumos: RepositorioInsumos,
        unidades: RepositorioUnidades,
        familias: RepositorioFamilias,
        cargas: RepositorioCargas,
    ) -> None:
        self._conceptos = conceptos
        self._insumos = insumos
        self._unidades = unidades
        self._familias = familias
        self._cargas = cargas

    async def aplicar(  # noqa: C901 — el flujo del §9.2 es lineal, no ramificado
        self,
        lectura: LecturaCarga,
        *,
        modo: ModoCarga,
        dry_run: bool,
        carga_id: UUID,
    ) -> Aplicacion:
        conceptos_filas = await self._conceptos.listar(solo_activos=False)
        por_clave = {str(f["clave"]): f for f in conceptos_filas}

        insumos_filas = await self._insumos.listar(solo_activos=False)
        insumos_por_clave = {str(f["clave"]): f for f in insumos_filas}
        clave_de_insumo = {f["id"]: str(f["clave"]) for f in insumos_filas}
        insumos = Homologador.desde(
            insumos_filas, mapeos=await self._cargas.mapeos("insumo")
        )
        costos_insumo = {
            str(f["clave"]): Decimal(
                str(f.get("costo_base_actualizado") or f.get("costo_base") or 0)
            )
            for f in insumos_filas
        }

        unidades_filas = await self._unidades.listar(solo_activos=False)
        unidades = Homologador.desde(
            unidades_filas, mapeos=await self._cargas.mapeos("unidad")
        )
        id_unidad = {str(f["clave"]): f["id"] for f in unidades_filas}
        familias_filas = await self._familias.listar(
            aplica_a="concepto", solo_activos=False
        )
        familias = Homologador.desde(
            familias_filas, mapeos=await self._cargas.mapeos("familia")
        )
        id_familia = {str(f["clave"]): f["id"] for f in familias_filas}

        pendientes: list[PendientePropuesto] = []
        errores: list[ErrorDeFila] = []
        entrantes: dict[str, dict[str, Any]] = {}
        planes: dict[str, dict[str, Any]] = {}

        for registro in lectura.registros:
            bloque: ConceptoCargado = registro  # type: ignore[assignment]
            cabeza = bloque.encabezado

            componentes: list[Componente] = []
            filas_explosion: list[dict[str, Any]] = []
            incompleto = False

            for componente in bloque.componentes:
                clave_insumo = insumos.resolver(str(componente.clave_insumo))
                if clave_insumo is None:
                    pendientes.append(
                        _pendiente_de_mapeo(
                            "insumo",
                            str(componente.clave_insumo),
                            componente.fila,
                            critico=True,
                        )
                    )
                    incompleto = True
                    continue
                try:
                    del_dominio = Componente(
                        categoria=componente.categoria,
                        cantidad=componente.cantidad,
                        clave_insumo=clave_insumo,
                        costo_unitario=componente.precio_unitario or None,
                        orden=len(componentes),
                    )
                except ErrorDeAPU as exc:
                    errores.append(
                        ErrorDeFila(
                            fila=componente.fila,
                            columna="cantidad",
                            valor=str(componente.cantidad),
                            motivo=str(exc),
                        )
                    )
                    incompleto = True
                    continue

                componentes.append(del_dominio)
                costo = (
                    del_dominio.costo_unitario
                    if del_dominio.costo_unitario is not None
                    else costos_insumo.get(clave_insumo, Decimal(0))
                )
                filas_explosion.append(
                    {
                        "tipo_hijo": str(TipoHijoExplosion.INSUMO),
                        "insumo_id": insumos_por_clave[clave_insumo]["id"],
                        "categoria": str(componente.categoria),
                        # El §10.6 da una sola columna E ("rendimiento =
                        # CANTIDAD"), así que las dos del esquema (§7.3)
                        # reciben el mismo número.
                        "cantidad": del_dominio.cantidad,
                        "rendimiento": del_dominio.cantidad,
                        "costo_unitario": costo,
                        "importe": del_dominio.cantidad * costo,
                        "orden": len(filas_explosion),
                    }
                )

            if incompleto:
                # Cargar el concepto sin uno de sus insumos publicaría un CPU
                # más barato que el real (§7.3). Se omite entero.
                continue

            actual = por_clave.get(bloque.llave, {})

            unidad_id = actual.get("unidad_id")
            if cabeza.unidad:
                clave_unidad = unidades.resolver(cabeza.unidad)
                if clave_unidad is None:
                    pendientes.append(
                        PendientePropuesto(
                            tipo=TipoPendiente.UNIDAD,
                            entidad="unidad",
                            valor_origen=cabeza.unidad,
                            propuesta={"concepto": bloque.llave},
                            origen_ref=f"fila {cabeza.fila}",
                        )
                    )
                else:
                    unidad_id = id_unidad.get(clave_unidad)

            familia_id = actual.get("familia_id")
            if cabeza.familia:
                clave_familia = familias.resolver(cabeza.familia)
                if clave_familia is None:
                    pendientes.append(
                        _pendiente_de_mapeo(
                            "familia", cabeza.familia, cabeza.fila, critico=False
                        )
                    )
                else:
                    familia_id = id_familia.get(clave_familia)

            try:
                precio = calcular_cpu(
                    bloque.llave,
                    composiciones={bloque.llave: componentes},
                    costos_insumo=costos_insumo,
                )
            except ErrorDeAPU as exc:
                errores.append(
                    ErrorDeFila(fila=cabeza.fila, columna="clave", valor=bloque.llave, motivo=str(exc))
                )
                continue

            if bloque.llave not in por_clave:
                pendientes.append(
                    PendientePropuesto(
                        tipo=TipoPendiente.CPU_NUEVO,
                        entidad="concepto",
                        valor_origen=bloque.llave,
                        propuesta={
                            "descripcion": cabeza.descripcion,
                            "precio_unitario": str(precio.total.monto),
                            "componentes": len(componentes),
                        },
                        origen_ref=f"fila {cabeza.fila}",
                    )
                )

            entrantes[bloque.llave] = {
                "descripcion": cabeza.descripcion,
                "unidad_id": unidad_id,
                "familia_id": familia_id,
                "composicion": _firma_explosion(filas_explosion, clave_de_insumo),
            }
            planes[bloque.llave] = {
                "cabeza": cabeza,
                "filas_explosion": filas_explosion,
                "precio": precio,
            }

        vigentes: dict[str, dict[str, Any]] = {}
        for clave, fila in por_clave.items():
            # La composición solo se lee de los conceptos que el archivo toca:
            # para los demás el diff únicamente mira si están o no (bajas del
            # modo Reemplazar, §10.2), y explotar todo el catálogo para eso
            # sería una consulta por concepto sin necesidad.
            composicion = (
                _firma_explosion(
                    await self._conceptos.explosion_directa(fila["id"]), clave_de_insumo
                )
                if clave in entrantes
                else ""
            )
            vigentes[clave] = {
                "descripcion": fila.get("descripcion"),
                "unidad_id": fila.get("unidad_id"),
                "familia_id": fila.get("familia_id"),
                "composicion": composicion,
            }

        diff = diferenciar(vigentes=vigentes, entrantes=entrantes, modo=modo)

        operaciones: list[dict[str, Any]] = []
        if not dry_run:
            for cambio in (*diff.altas, *diff.cambios):
                plan = planes[cambio.clave]
                fila = por_clave.get(cambio.clave)

                if fila is None:
                    concepto_id = await self._conceptos.crear(
                        {
                            "tipo": str(TipoConcepto.CONCEPTO),
                            "clave": cambio.clave,
                            "descripcion": cambio.despues["descripcion"],
                            "unidad_id": cambio.despues["unidad_id"],
                            "familia_id": cambio.despues["familia_id"],
                        }
                    )
                    operaciones.append(
                        _operacion(
                            "concepto",
                            concepto_id,
                            "insert",
                            despues={"clave": cambio.clave},
                        )
                    )
                else:
                    concepto_id = fila["id"]
                    await self._conceptos.actualizar(
                        concepto_id,
                        {
                            "descripcion": cambio.despues["descripcion"],
                            "unidad_id": cambio.despues["unidad_id"],
                            "familia_id": cambio.despues["familia_id"],
                        },
                    )
                    operaciones.append(
                        _operacion(
                            "concepto",
                            concepto_id,
                            "update",
                            antes=_recorte(
                                fila,
                                ("tipo", "descripcion", "unidad_id", "familia_id", "estatus"),
                            ),
                            despues=dict(cambio.despues),
                        )
                    )

                operaciones.extend(
                    await _publicar_cpu_de_concepto(
                        self._conceptos, concepto_id, plan["filas_explosion"], plan["precio"]
                    )
                )

            for baja in diff.bajas:
                fila = por_clave[baja.clave]
                # Baja lógica, igual que en materiales: `explosion`,
                # `actividad` y `presupuesto` referencian `concepto` y un
                # borrado se llevaría obra ya ejecutada (§10.2).
                await self._conceptos.actualizar(fila["id"], {"estatus": _ESTATUS_BAJA})
                operaciones.append(
                    _operacion(
                        "concepto",
                        fila["id"],
                        "update",
                        antes=_recorte(
                            fila,
                            ("tipo", "descripcion", "unidad_id", "familia_id", "estatus"),
                        ),
                        despues={"estatus": _ESTATUS_BAJA},
                    )
                )

        return Aplicacion(
            diff=diff,
            operaciones=tuple(operaciones),
            pendientes=tuple(pendientes),
            errores=tuple(errores),
            insertados=len(diff.altas),
            actualizados=len(diff.cambios) + len(diff.bajas),
            omitidos=diff.omitidos + lectura.omitidos,
        )


async def _publicar_cpu_de_concepto(
    conceptos: RepositorioConceptos,
    concepto_id: UUID,
    filas_explosion: list[dict[str, Any]],
    precio: PrecioUnitario,
) -> list[dict[str, Any]]:
    """Sustituye la composición y publica la versión nueva de CPU (§10.8).

    Compartida por `AplicadorCPU` y `AplicadorPresupuesto`: la única
    diferencia entre publicar el CPU de un concepto por el archivo de CPU o
    por el árbol de un prototipo es de dónde salió `filas_explosion` — el
    resto (guardar antes, sustituir, versionar) es idéntico.

    El orden importa y es el que la reversa deshace al revés: primero se
    guarda lo que se va a borrar de `explosion`, luego se retira el CPU
    vigente y se inserta el nuevo, y al final entran las filas nuevas de
    `explosion` atadas a ese CPU.
    """
    operaciones: list[dict[str, Any]] = []

    anteriores = await conceptos.explosion_directa(concepto_id)
    await conceptos.eliminar_explosion(concepto_id)
    for anterior in anteriores:
        operaciones.append(
            _operacion("explosion", anterior["id"], "delete", antes=dict(anterior))
        )

    versiones = await conceptos.versiones_cpu(concepto_id)
    vigentes_antes = {
        fila["id"]: dict(fila) for fila in versiones if bool(fila["vigente"])
    }
    nueva, retiradas = publicar_version(
        [_version_de_dominio(fila) for fila in versiones],
        precio,
        variante=None,
    )
    for identificador, fila in vigentes_antes.items():
        if int(fila["version"]) in retiradas:
            operaciones.append(
                _operacion(
                    "cpu",
                    identificador,
                    "update",
                    antes={
                        "precio_unitario": fila["precio_unitario"],
                        "precio_destajo": fila["precio_destajo"],
                        "vigente": True,
                    },
                    despues={"vigente": False},
                )
            )

    cpu_id = await conceptos.publicar_version_cpu(
        concepto_id,
        version=nueva.version,
        precio_unitario=nueva.precio.total.monto,
        precio_destajo=nueva.precio.destajo.monto,
        variante=None,
        retirar=list(retiradas),
    )
    operaciones.append(
        _operacion("cpu", cpu_id, "insert", despues={"version": nueva.version})
    )

    insertadas = await conceptos.agregar_explosion(
        concepto_id, cpu_id=cpu_id, filas=filas_explosion
    )
    for fila in insertadas:
        operaciones.append(_operacion("explosion", fila["id"], "insert"))

    return operaciones


def _version_de_dominio(fila: dict[str, Any]) -> VersionCPU:
    return VersionCPU(
        version=int(fila["version"]),
        precio=PrecioUnitario(
            total=Dinero(Decimal(str(fila["precio_unitario"]))),
            destajo=Dinero(Decimal(str(fila["precio_destajo"]))),
        ),
        vigente=bool(fila["vigente"]),
        variante=fila.get("variante"),
    )


def _firma_explosion(
    filas: list[dict[str, Any]], clave_de_insumo: dict[Any, str]
) -> str:
    """Composición como texto comparable, para saber si el APU cambió (§10.8).

    Se firma por **clave** de insumo y no por su id (§3.3): es la identidad
    estable entre el archivo y la base.
    """
    partes = []
    for fila in sorted(filas, key=lambda f: int(f.get("orden") or 0)):
        clave = clave_de_insumo.get(fila.get("insumo_id"), "")
        cantidad = Decimal(str(fila.get("cantidad") or 0)).normalize() + Decimal(0)
        costo = Decimal(str(fila.get("costo_unitario") or 0)).normalize() + Decimal(0)
        partes.append(f"{clave}:{fila.get('categoria')}:{cantidad}:{costo}")
    return "|".join(partes)


# --- Movimientos de almacén (§10.6 `IMPORTAADOR_ALMACEN.xlsx`) ------------


class AplicadorAlmacen:
    """Movimientos de almacén (§10.6, §10.5, §7.7).

    Un archivo de almacén es un **libro de movimientos**, no un catálogo: sus
    renglones son altas y el §10.6 no le define clave de renglón. Por eso la
    idempotencia aquí es de **lote**: el mismo archivo no se aplica dos veces
    (hash, §10.8) y dentro del archivo se deduplica por la composición
    obra+material+fecha+motivo+cantidad+costo.

    Además baja la **valuación** del §10.5: `C/Último` de la fila más reciente
    de cada insumo pasa a `costo_ultimo` y a `costo_base_actualizado` —"el
    costo último más reciente (costo vigente)"—, con `origen = 'almacen'`.
    """

    def __init__(
        self,
        *,
        materiales: RepositorioMateriales,
        insumos: RepositorioInsumos,
        obras: RepositorioObras,
        contratistas: RepositorioContratistas,
        conceptos: RepositorioConceptos,
        familias: RepositorioFamilias,
        cargas: RepositorioCargas,
        tasa_iva: Decimal,
    ) -> None:
        self._materiales = materiales
        self._insumos = insumos
        self._obras = obras
        self._contratistas = contratistas
        self._conceptos = conceptos
        self._familias = familias
        self._cargas = cargas
        self._tasa_iva = tasa_iva

    async def aplicar(  # noqa: C901 — un cruce por catálogo, todos del §10.6
        self,
        lectura: LecturaCarga,
        *,
        modo: ModoCarga,
        dry_run: bool,
        carga_id: UUID,
    ) -> Aplicacion:
        insumos_filas = await self._insumos.listar(solo_activos=False)
        insumos_por_clave = {str(f["clave"]): f for f in insumos_filas}
        insumos = Homologador.desde(
            insumos_filas, mapeos=await self._cargas.mapeos("insumo")
        )

        obras_filas = await self._obras.listar()
        obras_por_clave = {str(f["clave"]): f for f in obras_filas}
        obras = Homologador.desde(obras_filas, mapeos=await self._cargas.mapeos("obra"))

        motivos_filas = await self._materiales.listar_motivos(solo_activos=False)
        motivos_por_clave = {str(f["clave"]): f for f in motivos_filas}
        motivos = Homologador.desde(
            motivos_filas, mapeos=await self._cargas.mapeos("motivo_almacen")
        )

        contratistas_filas = await self._contratistas.listar(solo_activos=False)
        contratistas_por_clave = {str(f["clave"]): f for f in contratistas_filas}
        contratistas = Homologador.desde(
            contratistas_filas, mapeos=await self._cargas.mapeos("contratista")
        )

        conceptos_filas = await self._conceptos.listar(solo_activos=False)
        conceptos_por_clave = {str(f["clave"]): f for f in conceptos_filas}

        familias_por_id = {
            f["id"]: f for f in await self._familias.listar(solo_activos=False)
        }

        pendientes: list[PendientePropuesto] = []
        errores: list[ErrorDeFila] = []
        movimientos: list[tuple[FilaMovimiento, dict[str, Any]]] = []
        omitidos = lectura.omitidos
        importe_con_iva_total = Decimal(0)

        for registro in lectura.registros:
            movimiento: FilaMovimiento = registro  # type: ignore[assignment]

            clave_insumo = insumos.resolver(str(movimiento.clave_insumo))
            if clave_insumo is None:
                pendientes.append(
                    _pendiente_de_mapeo(
                        "insumo", str(movimiento.clave_insumo), movimiento.fila, critico=True
                    )
                )
                omitidos += 1
                continue

            clave_obra = obras.resolver(str(movimiento.clave_obra))
            if clave_obra is None:
                pendientes.append(
                    _pendiente_de_mapeo(
                        "obra", str(movimiento.clave_obra), movimiento.fila, critico=True
                    )
                )
                omitidos += 1
                continue

            clave_motivo = motivos.resolver(movimiento.motivo)
            if clave_motivo is None:
                # §10.5: "Motivo no catalogado -> bandeja de pendientes". Es
                # semilla editable (§8.7): el usuario lo agrega con su
                # signo/bucket y la carga se puede repetir.
                pendientes.append(
                    PendientePropuesto(
                        tipo=TipoPendiente.MOTIVO_ALMACEN,
                        entidad="motivo_almacen",
                        valor_origen=movimiento.motivo,
                        propuesta={
                            "signo": 1 if movimiento.cantidad > 0 else -1,
                            "accion": (
                                "Dar de alta el motivo con su signo y bucket de "
                                "KPI (§10.5)."
                            ),
                        },
                        critico=True,
                        origen_ref=f"fila {movimiento.fila}",
                    )
                )
                omitidos += 1
                continue

            motivo = motivos_por_clave[clave_motivo]
            try:
                # El signo viene del archivo (§10.5); esto solo verifica que
                # no contradiga al motivo elegido — misma regla que la captura
                # manual de `POST /obras/{id}/salidas`.
                validar_signo_salida(movimiento.cantidad, int(motivo["signo"]))
            except ErrorDeMaterial as exc:
                errores.append(
                    ErrorDeFila(
                        fila=movimiento.fila,
                        columna="cantidad",
                        valor=str(movimiento.cantidad),
                        motivo=str(exc),
                    )
                )
                continue

            contratista_id = None
            if movimiento.contratista:
                clave_contratista = contratistas.resolver(movimiento.contratista)
                if clave_contratista is None:
                    pendientes.append(
                        _pendiente_de_mapeo(
                            "contratista",
                            movimiento.contratista,
                            movimiento.fila,
                            critico=False,
                        )
                    )
                else:
                    contratista_id = contratistas_por_clave[clave_contratista]["id"]

            concepto_id = None
            if movimiento.clave_concepto:
                fila_concepto = conceptos_por_clave.get(movimiento.clave_concepto)
                if fila_concepto is None:
                    pendientes.append(
                        _pendiente_de_mapeo(
                            "concepto",
                            movimiento.clave_concepto,
                            movimiento.fila,
                            critico=False,
                        )
                    )
                else:
                    concepto_id = fila_concepto["id"]

            insumo = insumos_por_clave[clave_insumo]
            familia = familias_por_id.get(insumo.get("familia_id"))
            aplica_iva = resolver_iva(
                iva_familia=bool(familia["iva_aplica"]) if familia else True,
                override_insumo=insumo.get("iva_aplica"),
            )
            importe_con_iva_total += importe_con_iva(
                movimiento.costo, aplica_iva=aplica_iva, tasa=self._tasa_iva
            )

            movimientos.append(
                (
                    movimiento,
                    {
                        "obra_id": obras_por_clave[clave_obra]["id"],
                        "insumo_id": insumo["id"],
                        "motivo_id": motivo["id"],
                        "concepto_id": concepto_id,
                        "contratista_id": contratista_id,
                        "carga_id": carga_id,
                        "fecha": movimiento.fecha,
                        "cantidad": movimiento.cantidad,
                        "costo": movimiento.costo,
                        "costo_ultimo": movimiento.costo_ultimo,
                        "almacen": movimiento.almacen,
                        "referencia": movimiento.clave_concepto,
                    },
                )
            )

        entrantes = {
            movimiento.llave: {"cantidad": movimiento.cantidad, "costo": movimiento.costo}
            for movimiento, _ in movimientos
        }
        # Contra `{}`: el §10.6 no da clave de renglón para este archivo, así
        # que no hay "vigente" con qué comparar fila a fila. La idempotencia
        # es de lote, por hash (§10.8).
        diff = diferenciar(vigentes={}, entrantes=entrantes, modo=modo)

        operaciones: list[dict[str, Any]] = []
        if not dry_run:
            for _, datos in movimientos:
                salida_id = await self._materiales.crear_salida(datos)
                operaciones.append(_operacion("salida_almacen", salida_id, "insert"))

            operaciones.extend(
                await self._valuar(movimientos, insumos_por_clave, insumos)
            )

        return Aplicacion(
            diff=diff,
            operaciones=tuple(operaciones),
            pendientes=tuple(pendientes),
            errores=tuple(errores),
            insertados=len(movimientos),
            actualizados=0,
            omitidos=omitidos,
            detalle={
                "importe_con_iva": str(importe_con_iva_total),
                "tasa_iva": str(self._tasa_iva),
            },
        )

    async def _valuar(
        self,
        movimientos: list[tuple[FilaMovimiento, dict[str, Any]]],
        insumos_por_clave: dict[str, dict[str, Any]],
        homologador: Homologador,
    ) -> list[dict[str, Any]]:
        """Baja `C/Último` al catálogo como costo vigente (§10.5).

        "El sistema calcula `costo_promedio_almacen` desde el costo último;
        `costo_base_actualizado` = el costo último **más reciente** (costo
        vigente)". Por eso gana la fila de **fecha mayor**, no la última del
        archivo: el orden del Excel no es cronológico.
        """
        ultimos: dict[str, tuple[object, Decimal]] = {}
        for movimiento, _ in movimientos:
            if movimiento.costo_ultimo is None:
                continue
            clave = homologador.resolver(str(movimiento.clave_insumo))
            if clave is None:
                continue
            previo = ultimos.get(clave)
            if previo is None or movimiento.fecha >= previo[0]:  # type: ignore[operator]
                ultimos[clave] = (movimiento.fecha, movimiento.costo_ultimo)

        operaciones: list[dict[str, Any]] = []
        for clave, (_, costo) in ultimos.items():
            insumo = insumos_por_clave[clave]
            if (
                insumo.get("costo_ultimo") == costo
                and insumo.get("costo_base_actualizado") == costo
                and insumo.get("origen") == "almacen"
            ):
                continue
            await self._insumos.actualizar(
                insumo["id"],
                {
                    "costo_ultimo": costo,
                    "costo_base_actualizado": costo,
                    "origen": "almacen",
                },
            )
            operaciones.append(
                _operacion(
                    "insumo",
                    insumo["id"],
                    "update",
                    antes=_recorte(insumo, _CAMPOS_RESTAURABLES_INSUMO),
                    despues={"costo_ultimo": costo, "origen": "almacen"},
                )
            )
        return operaciones


# --- Prototipos (extensión propia, no está en el §10.6) -------------------

_CAMPOS_PROTOTIPO = ("nombre", "m2", "niveles", "recamaras")
"""Campos que este cargador gobierna. `proyecto_id` y `clave` son la
identidad de la fila (§3.3): un renglón cuya clave ya existe **nunca**
reasigna su proyecto por carga, solo actualiza estos cuatro."""


class AplicadorPrototipos:
    """Prototipos — bulk-load de `POST /prototipos` (§7.2).

    Sin `Homologador`: el único cruce es el proyecto por su clave, y una
    clave que no existe exacto es un error de fila, no algo que adivinar
    (mismo criterio que "la clave manda" en materiales, §3.3).

    No soporta el modo Reemplazar: `prototipo` no tiene columna `estatus`,
    así que no hay baja lógica que ejecutar sobre lo que el archivo ya no
    trae.
    """

    def __init__(
        self,
        *,
        prototipos: RepositorioPrototipos,
        proyectos: RepositorioProyectos,
    ) -> None:
        self._prototipos = prototipos
        self._proyectos = proyectos

    async def aplicar(
        self,
        lectura: LecturaCarga,
        *,
        modo: ModoCarga,
        dry_run: bool,
        carga_id: UUID,
    ) -> Aplicacion:
        if modo is ModoCarga.REEMPLAZAR:
            raise ErrorDeProyecto(
                "Prototipos no soporta el modo Reemplazar: no tiene baja "
                "lógica (§10.2). Usa Actualizar o Acumular."
            )

        vigentes_filas = await self._prototipos.listar()
        por_clave = {str(f["clave"]): f for f in vigentes_filas}

        proyectos_filas = await self._proyectos.listar()
        proyecto_id_por_clave = {str(p["clave"]): p["id"] for p in proyectos_filas}

        errores: list[ErrorDeFila] = []
        entrantes: dict[str, dict[str, Any]] = {}
        proyecto_id_por_llave: dict[str, Any] = {}

        # La validación de dominio (`Prototipo.crear`) corre aquí, **antes**
        # del diff y sin importar `dry_run`: si se dejara para el commit, la
        # vista previa contaría una fila con `niveles=0` como alta válida y
        # el aplicar real la rechazaría — números distintos entre los dos,
        # que es justo lo que "el dry-run tiene que dar los mismos números
        # que el commit" (§9.3) prohíbe.
        for registro in lectura.registros:
            prototipo: FilaPrototipo = registro  # type: ignore[assignment]
            actual = por_clave.get(prototipo.llave, {})

            proyecto_id = proyecto_id_por_clave.get(prototipo.proyecto_clave)
            if proyecto_id is None and not actual:
                # Solo bloquea el alta: un renglón que ya existe se puede
                # actualizar aunque el archivo traiga un `proyecto_clave`
                # que ya no cruza (no se reasigna, ver `_CAMPOS_PROTOTIPO`).
                errores.append(
                    ErrorDeFila(
                        fila=prototipo.fila,
                        columna="proyecto_clave",
                        valor=prototipo.proyecto_clave,
                        motivo=(
                            f"proyecto_clave: no existe un proyecto con la "
                            f"clave {prototipo.proyecto_clave!r} (créalo primero "
                            f"en Creador de obra)."
                        ),
                    )
                )
                continue

            proyecto_id_efectivo = proyecto_id or actual.get("proyecto_id")
            try:
                dominio = Prototipo.crear(
                    proyecto_id=str(proyecto_id_efectivo),
                    clave=prototipo.llave,
                    nombre=prototipo.nombre,
                    m2=_o_vigente(prototipo.m2, actual, "m2"),
                    niveles=_o_vigente(prototipo.niveles, actual, "niveles"),
                    recamaras=_o_vigente(prototipo.recamaras, actual, "recamaras"),
                )
            except ErrorDeProyecto as exc:
                errores.append(ErrorDeFila(fila=prototipo.fila, motivo=str(exc)))
                continue

            proyecto_id_por_llave[prototipo.llave] = dominio.proyecto_id
            entrantes[prototipo.llave] = {
                "nombre": dominio.nombre,
                "m2": dominio.m2,
                "niveles": dominio.niveles,
                "recamaras": dominio.recamaras,
            }

        vigentes = {
            clave: {campo: fila.get(campo) for campo in _CAMPOS_PROTOTIPO}
            for clave, fila in por_clave.items()
        }
        diff = diferenciar(vigentes=vigentes, entrantes=entrantes, modo=modo)

        operaciones: list[dict[str, Any]] = []
        if not dry_run:
            for alta in diff.altas:
                nuevo_id = await self._prototipos.crear(
                    {
                        "proyecto_id": proyecto_id_por_llave[alta.clave],
                        "clave": alta.clave,
                        "nombre": alta.despues["nombre"],
                        "m2": alta.despues["m2"],
                        "niveles": alta.despues["niveles"],
                        "recamaras": alta.despues["recamaras"],
                    }
                )
                operaciones.append(
                    _operacion(
                        "prototipo", nuevo_id, "insert", despues=dict(alta.despues)
                    )
                )

            for cambio in diff.cambios:
                fila = por_clave[cambio.clave]
                await self._prototipos.actualizar(fila["id"], dict(cambio.despues))
                operaciones.append(
                    _operacion(
                        "prototipo",
                        fila["id"],
                        "update",
                        antes=_recorte(fila, _CAMPOS_PROTOTIPO),
                        despues=dict(cambio.despues),
                    )
                )

        return Aplicacion(
            diff=diff,
            operaciones=tuple(operaciones),
            errores=tuple(errores),
            insertados=len(diff.altas),
            actualizados=len(diff.cambios),
            omitidos=diff.omitidos + lectura.omitidos,
        )


# --- Presupuesto jerárquico (extensión propia, no está en el §10.6) -------

_CATEGORIA_POR_TIPO_NODO: dict[TipoNodoPresupuesto, CategoriaExplosion] = {
    TipoNodoPresupuesto.MATERIAL: CategoriaExplosion.MATERIAL,
    TipoNodoPresupuesto.DESTAJO: CategoriaExplosion.DESTAJO,
    TipoNodoPresupuesto.SUBCONTRATO: CategoriaExplosion.SUBCONTRATO,
}


class AplicadorPresupuesto:
    """Árbol de un prototipo (nivel → etapa → concepto) y su presupuesto
    (§7.4, §7.3, extensión propia — no está en el §10.6).

    Puebla tres cosas que hasta hoy nadie escribía: el árbol WBS
    (`prototipo_nodo`), el catálogo compartido de niveles/etapas, y el
    presupuesto versionado del prototipo. El catálogo de conceptos/APU es el
    mismo de siempre (`concepto`/`explosion`/`cpu`, `variante=null`) — este
    aplicador reutiliza `_publicar_cpu_de_concepto`, la misma función que usa
    `AplicadorCPU`.

    **Conflicto de catálogo, no sobrescritura silenciosa.** Un concepto
    (misma clave) puede repetirse en varios prototipos. Si la composición
    coincide con la vigente, se publica igual que siempre. Si difiere, el
    catálogo **se queda como estaba** —no se toca `concepto`/`explosion`/
    `cpu`— y se registra `TipoPendiente.CONCEPTO_EN_CONFLICTO` (no crítico)
    para que alguien lo resuelva a mano. La partida de presupuesto de este
    prototipo usa siempre el precio calculado de **su propia** composición,
    haya o no conflicto: nunca hereda en silencio el precio de otro
    prototipo por un conflicto no resuelto.

    **No hay `Homologador` de proyecto**: este cargador no da de alta
    prototipos (el archivo no trae proyecto, §7.2) — solo identifica por
    clave uno ya existente. Uno que no cruza es error de fila crítico; el
    resto del archivo sigue.
    """

    def __init__(
        self,
        *,
        conceptos: RepositorioConceptos,
        insumos: RepositorioInsumos,
        unidades: RepositorioUnidades,
        prototipos: RepositorioPrototipos,
        prototipo_nodos: RepositorioPrototipoNodo,
        niveles_etapas: RepositorioNivelesEtapas,
        presupuestos: RepositorioPresupuestos,
        cargas: RepositorioCargas,
    ) -> None:
        self._conceptos = conceptos
        self._insumos = insumos
        self._unidades = unidades
        self._prototipos = prototipos
        self._prototipo_nodos = prototipo_nodos
        self._niveles_etapas = niveles_etapas
        self._presupuestos = presupuestos
        self._cargas = cargas

    async def aplicar(
        self,
        lectura: LecturaCarga,
        *,
        modo: ModoCarga,
        dry_run: bool,
        carga_id: UUID,
    ) -> Aplicacion:
        if modo is ModoCarga.REEMPLAZAR:
            raise ErrorDeProyecto(
                "Presupuesto no soporta el modo Reemplazar: recargar ya "
                "sustituye el árbol del prototipo por una versión nueva "
                "(§10.2). Usa Actualizar."
            )

        prototipos_filas = await self._prototipos.listar()
        prototipo_por_clave = {str(f["clave"]): f for f in prototipos_filas}

        conceptos_filas = await self._conceptos.listar(solo_activos=False)
        catalogo_conceptos: dict[str, dict[str, Any]] = {
            str(f["clave"]): dict(f) for f in conceptos_filas
        }
        firma_cache: dict[str, str] = {}

        insumos_filas = await self._insumos.listar(solo_activos=False)
        insumos_por_clave = {str(f["clave"]): f for f in insumos_filas}
        clave_de_insumo = {f["id"]: str(f["clave"]) for f in insumos_filas}
        insumos = Homologador.desde(
            insumos_filas, mapeos=await self._cargas.mapeos("insumo")
        )
        costos_insumo = {
            str(f["clave"]): Decimal(
                str(f.get("costo_base_actualizado") or f.get("costo_base") or 0)
            )
            for f in insumos_filas
        }

        unidades_filas = await self._unidades.listar(solo_activos=False)
        unidades = Homologador.desde(
            unidades_filas, mapeos=await self._cargas.mapeos("unidad")
        )
        id_unidad = {str(f["clave"]): f["id"] for f in unidades_filas}

        errores: list[ErrorDeFila] = []
        pendientes: list[PendientePropuesto] = []
        operaciones: list[dict[str, Any]] = []
        claves_nuevas: set[str] = set()
        claves_actualizadas: set[str] = set()
        contadores = {
            "prototipos_tocados": 0,
            "nodos_creados": 0,
            "nodos_actualizados": 0,
            "conceptos_en_conflicto": 0,
            "conceptos_omitidos": 0,
            "conceptos_sin_cambio": 0,
            "partidas": 0,
        }

        for registro in lectura.registros:
            arbol: ArbolPrototipoCargado = registro  # type: ignore[assignment]
            prototipo = prototipo_por_clave.get(arbol.clave_prototipo)
            if prototipo is None:
                errores.append(
                    ErrorDeFila(
                        fila=arbol.raiz.fila,
                        columna="clave_hijo",
                        valor=arbol.clave_prototipo,
                        motivo=(
                            f"El prototipo {arbol.clave_prototipo!r} no existe. "
                            f"Carga primero este prototipo con Cargas → "
                            f"Prototipos (§7.2)."
                        ),
                    )
                )
                continue

            contadores["prototipos_tocados"] += 1
            partidas: list[dict[str, Any]] = []
            # Capturado una vez por prototipo, antes de tocar nada: es el
            # `antes` que la reversa necesita por nodo (§10.8) — el `id` que
            # conserva un upsert no basta, hace falta el valor previo.
            nodos_existentes = {
                str(f["clave"]): dict(f)
                for f in await self._prototipo_nodos.por_prototipo(prototipo["id"])
                if f["clave"]
            }

            for hijo in arbol.hijos.get(arbol.clave_prototipo, ()):
                await self._procesar_subarbol(
                    arbol=arbol,
                    nodo=hijo,
                    prototipo_id=prototipo["id"],
                    parent_id_db=None,
                    nivel_id_heredado=None,
                    dry_run=dry_run,
                    insumos=insumos,
                    insumos_por_clave=insumos_por_clave,
                    clave_de_insumo=clave_de_insumo,
                    costos_insumo=costos_insumo,
                    unidades=unidades,
                    id_unidad=id_unidad,
                    catalogo_conceptos=catalogo_conceptos,
                    firma_cache=firma_cache,
                    nodos_existentes=nodos_existentes,
                    operaciones=operaciones,
                    partidas=partidas,
                    errores=errores,
                    pendientes=pendientes,
                    contadores=contadores,
                    claves_nuevas=claves_nuevas,
                    claves_actualizadas=claves_actualizadas,
                )

            if not dry_run and partidas:
                version = await self._presupuestos.crear_version(
                    prototipo["id"], origen="excel", carga_id=carga_id
                )
                if version.get("anterior_id") is not None:
                    # La versión que este `crear_version` acaba de retirar
                    # (`vigente=false`): sin registrar esta operación, la
                    # reversa no sabría devolverla a vigente (§10.8).
                    operaciones.append(
                        _operacion(
                            "presupuesto",
                            version["anterior_id"],
                            "update",
                            antes={"vigente": True},
                            despues={"vigente": False},
                        )
                    )
                operaciones.append(
                    _operacion(
                        "presupuesto",
                        version["id"],
                        "insert",
                        despues={"version": version["version"]},
                    )
                )
                insertadas = await self._presupuestos.agregar_partidas(
                    version["id"], partidas
                )
                for fila in insertadas:
                    operaciones.append(
                        _operacion("partida_presupuesto", fila["id"], "insert")
                    )
                monto_total = sum(
                    (Decimal(str(p["importe"])) for p in partidas), Decimal(0)
                )
                await self._presupuestos.actualizar_monto_total(version["id"], monto_total)

        # Diff sintético: este cargador no tiene un conjunto plano por clave
        # que diferenciar (es un árbol, no una lista), pero `hay_cambios`
        # sigue decidiendo si la carga genera versión propia (§10.8) — y las
        # claves de concepto tocadas son justo lo que ese resumen necesita
        # decir.
        diff = Diff(
            altas=tuple(Cambio(clave=c, despues={}) for c in sorted(claves_nuevas)),
            cambios=tuple(
                Cambio(clave=c, despues={}) for c in sorted(claves_actualizadas)
            ),
        )

        return Aplicacion(
            diff=diff,
            operaciones=tuple(operaciones),
            pendientes=tuple(pendientes),
            errores=tuple(errores),
            insertados=len(diff.altas),
            actualizados=len(diff.cambios),
            omitidos=(
                contadores["conceptos_omitidos"]
                + contadores["conceptos_sin_cambio"]
                + lectura.omitidos
            ),
            detalle=dict(contadores),
        )

    async def _procesar_subarbol(
        self,
        *,
        arbol: ArbolPrototipoCargado,
        nodo: NodoLeido,
        prototipo_id: UUID,
        parent_id_db: UUID | None,
        nivel_id_heredado: UUID | None,
        dry_run: bool,
        insumos: Homologador,
        insumos_por_clave: dict[str, dict[str, Any]],
        clave_de_insumo: dict[Any, str],
        costos_insumo: dict[str, Decimal],
        unidades: Homologador,
        id_unidad: dict[str, Any],
        catalogo_conceptos: dict[str, dict[str, Any]],
        firma_cache: dict[str, str],
        nodos_existentes: dict[str, dict[str, Any]],
        operaciones: list[dict[str, Any]],
        partidas: list[dict[str, Any]],
        errores: list[ErrorDeFila],
        pendientes: list[PendientePropuesto],
        contadores: dict[str, int],
        claves_nuevas: set[str],
        claves_actualizadas: set[str],
    ) -> None:
        """Un nodo del árbol leído → `prototipo_nodo` (+ catálogo, si aplica).

        `NIVEL`/`ETAPA` (que no colapsan en concepto, ver
        `es_etapa_con_componentes_directos`) recursan hacia sus hijos.
        `CONCEPTO`/`CONCEPTO_AUXILIAR` (o una etapa que colapsa) son hojas
        del árbol: sus hijos `MATERIAL`/`DESTAJO`/`SUBCONTRATO` no se
        convierten en `prototipo_nodo` — se consumen como la explosión del
        concepto.

        El alta/actualización se decide contra `nodos_existentes` **antes**
        de escribir, sin importar `dry_run`: es lo que hace que la vista
        previa cuente igual que el commit (§9.3).
        """
        es_concepto_efectivo = nodo.tipo in (
            TipoNodoPresupuesto.CONCEPTO,
            TipoNodoPresupuesto.CONCEPTO_AUXILIAR,
        ) or (
            nodo.tipo is TipoNodoPresupuesto.ETAPA
            and es_etapa_con_componentes_directos(arbol, nodo)
        )

        if es_concepto_efectivo:
            await self._procesar_concepto(
                arbol=arbol,
                nodo=nodo,
                prototipo_id=prototipo_id,
                parent_id_db=parent_id_db,
                dry_run=dry_run,
                insumos=insumos,
                insumos_por_clave=insumos_por_clave,
                clave_de_insumo=clave_de_insumo,
                costos_insumo=costos_insumo,
                unidades=unidades,
                id_unidad=id_unidad,
                catalogo_conceptos=catalogo_conceptos,
                firma_cache=firma_cache,
                nodos_existentes=nodos_existentes,
                operaciones=operaciones,
                partidas=partidas,
                errores=errores,
                pendientes=pendientes,
                contadores=contadores,
                claves_nuevas=claves_nuevas,
                claves_actualizadas=claves_actualizadas,
            )
            return

        anterior = nodos_existentes.get(nodo.clave)
        es_alta = anterior is None
        contadores["nodos_creados" if es_alta else "nodos_actualizados"] += 1

        nivel_id_db = nivel_id_heredado
        etapa_id_db = None
        nodo_id: UUID | None = anterior["id"] if anterior else None

        if not dry_run:
            if nodo.tipo is TipoNodoPresupuesto.NIVEL:
                nivel_id_db = await self._niveles_etapas.upsert_nivel(
                    clave=nodo.clave, descripcion=nodo.descripcion, orden=nodo.indice or 0
                )
            elif nodo.tipo is TipoNodoPresupuesto.ETAPA:
                etapa_id_db = await self._niveles_etapas.upsert_etapa(
                    clave=nodo.clave,
                    descripcion=nodo.descripcion,
                    nivel_id=nivel_id_heredado,
                    orden=nodo.indice or 0,
                )

            nodo_id, _ = await self._prototipo_nodos.upsert(
                prototipo_id,
                clave=nodo.clave,
                datos={
                    "parent_id": parent_id_db,
                    "tipo": "nivel" if nodo.tipo is TipoNodoPresupuesto.NIVEL else "etapa",
                    "nombre": nodo.descripcion,
                    "nivel_id": nivel_id_db if nodo.tipo is TipoNodoPresupuesto.NIVEL else None,
                    "etapa_id": etapa_id_db,
                    "orden": nodo.indice or 0,
                    "cantidad": nodo.cantidad or 0,
                },
            )
            operaciones.append(
                _operacion(
                    "prototipo_nodo",
                    nodo_id,
                    "insert" if es_alta else "update",
                    antes=_recorte(
                        anterior,
                        ("parent_id", "tipo", "nombre", "concepto_id", "nivel_id", "etapa_id", "orden", "cantidad"),
                    )
                    if anterior
                    else None,
                    despues={"clave": nodo.clave, "nombre": nodo.descripcion},
                )
            )

        for hijo in arbol.hijos.get(nodo.clave, ()):
            await self._procesar_subarbol(
                arbol=arbol,
                nodo=hijo,
                prototipo_id=prototipo_id,
                parent_id_db=nodo_id,
                nivel_id_heredado=nivel_id_db,
                dry_run=dry_run,
                insumos=insumos,
                insumos_por_clave=insumos_por_clave,
                clave_de_insumo=clave_de_insumo,
                costos_insumo=costos_insumo,
                unidades=unidades,
                id_unidad=id_unidad,
                catalogo_conceptos=catalogo_conceptos,
                firma_cache=firma_cache,
                nodos_existentes=nodos_existentes,
                operaciones=operaciones,
                partidas=partidas,
                errores=errores,
                pendientes=pendientes,
                contadores=contadores,
                claves_nuevas=claves_nuevas,
                claves_actualizadas=claves_actualizadas,
            )

    async def _procesar_concepto(
        self,
        *,
        arbol: ArbolPrototipoCargado,
        nodo: NodoLeido,
        prototipo_id: UUID,
        parent_id_db: UUID | None,
        dry_run: bool,
        insumos: Homologador,
        insumos_por_clave: dict[str, dict[str, Any]],
        clave_de_insumo: dict[Any, str],
        costos_insumo: dict[str, Decimal],
        unidades: Homologador,
        id_unidad: dict[str, Any],
        catalogo_conceptos: dict[str, dict[str, Any]],
        firma_cache: dict[str, str],
        nodos_existentes: dict[str, dict[str, Any]],
        operaciones: list[dict[str, Any]],
        partidas: list[dict[str, Any]],
        errores: list[ErrorDeFila],
        pendientes: list[PendientePropuesto],
        contadores: dict[str, int],
        claves_nuevas: set[str],
        claves_actualizadas: set[str],
    ) -> None:
        """Un nodo CONCEPTO/CONCEPTO_AUXILIAR (o etapa-colapsada): arma su
        APU desde sus hijos, decide alta/actualiza/conflicto contra el
        catálogo, y registra su partida de presupuesto."""
        componentes: list[Componente] = []
        filas_explosion: list[dict[str, Any]] = []
        incompleto = False

        for hijo in arbol.hijos.get(nodo.clave, ()):
            categoria = _CATEGORIA_POR_TIPO_NODO.get(hijo.tipo)
            if categoria is None:
                # No debería pasar: `construir_arboles` solo cuelga hojas de
                # tipo MATERIAL/DESTAJO/SUBCONTRATO de un concepto.
                continue

            clave_insumo = insumos.resolver(hijo.clave)
            if clave_insumo is None:
                pendientes.append(
                    _pendiente_de_mapeo("insumo", hijo.clave, hijo.fila, critico=True)
                )
                incompleto = True
                continue

            cantidad = hijo.cantidad if hijo.cantidad is not None else Decimal(0)
            try:
                del_dominio = Componente(
                    categoria=categoria,
                    cantidad=cantidad,
                    clave_insumo=clave_insumo,
                    costo_unitario=hijo.precio_unitario or None,
                    orden=len(componentes),
                )
            except ErrorDeAPU as exc:
                errores.append(
                    ErrorDeFila(
                        fila=hijo.fila,
                        columna="cantidad",
                        valor=str(hijo.cantidad),
                        motivo=str(exc),
                    )
                )
                incompleto = True
                continue

            componentes.append(del_dominio)
            costo = (
                del_dominio.costo_unitario
                if del_dominio.costo_unitario is not None
                else costos_insumo.get(clave_insumo, Decimal(0))
            )
            filas_explosion.append(
                {
                    "tipo_hijo": str(TipoHijoExplosion.INSUMO),
                    "insumo_id": insumos_por_clave[clave_insumo]["id"],
                    "categoria": str(categoria),
                    "cantidad": del_dominio.cantidad,
                    "rendimiento": del_dominio.cantidad,
                    "costo_unitario": costo,
                    "importe": del_dominio.cantidad * costo,
                    "orden": len(filas_explosion),
                }
            )

        if incompleto:
            # Un APU con un hueco daría un precio menor al real (§7.3, mismo
            # criterio que `AplicadorCPU`): el concepto se omite entero, y
            # con él su partida — no hay precio confiable que registrar.
            contadores["conceptos_omitidos"] += 1
            return

        try:
            precio = calcular_cpu(
                nodo.clave, composiciones={nodo.clave: componentes}, costos_insumo=costos_insumo
            )
        except ErrorDeAPU as exc:
            errores.append(
                ErrorDeFila(fila=nodo.fila, columna="clave_hijo", valor=nodo.clave, motivo=str(exc))
            )
            contadores["conceptos_omitidos"] += 1
            return

        actual = catalogo_conceptos.get(nodo.clave)

        unidad_id = actual.get("unidad_id") if actual else None
        if nodo.unidad:
            clave_unidad = unidades.resolver(nodo.unidad)
            if clave_unidad is not None:
                unidad_id = id_unidad.get(clave_unidad)
            elif actual is None:
                pendientes.append(
                    PendientePropuesto(
                        tipo=TipoPendiente.UNIDAD,
                        entidad="unidad",
                        valor_origen=nodo.unidad,
                        propuesta={"concepto": nodo.clave},
                        origen_ref=f"fila {nodo.fila}",
                    )
                )

        firma_nueva = _firma_explosion(filas_explosion, clave_de_insumo)

        diferente = False
        concepto_id: UUID | None = actual["id"] if actual else None
        if actual is not None:
            firma_vigente = firma_cache.get(nodo.clave)
            if firma_vigente is None:
                # Sin firma en caché, `actual` solo puede venir del catálogo
                # real (no de una simulación en dry_run de este mismo
                # archivo — esa siempre deja firma en caché al procesar,
                # línea de abajo): `concepto_id` es un id real.
                assert concepto_id is not None  # noqa: S101
                filas_previas = await self._conceptos.explosion_directa(concepto_id)
                firma_vigente = _firma_explosion(filas_previas, clave_de_insumo)
                firma_cache[nodo.clave] = firma_vigente
            diferente = firma_vigente != firma_nueva

        conflicto = False
        if diferente:
            assert concepto_id is not None  # noqa: S101 — `diferente` implica `actual is not None`
            # Composición distinta a la vigente: ¿es un prototipo DISTINTO
            # el que ya depende de ella (conflicto real), o es este mismo
            # prototipo recargando una corrección (actualización legítima,
            # nadie más se queda con datos viejos)? La consulta es de solo
            # lectura — se hace igual en dry_run, para que la vista previa
            # cuente igual que el commit (§9.3).
            otros = await self._presupuestos.otros_prototipos_con_partida_vigente(
                concepto_id, excluir_prototipo_id=prototipo_id
            )
            conflicto = bool(otros)

        if conflicto:
            contadores["conceptos_en_conflicto"] += 1
            pendientes.append(
                PendientePropuesto(
                    tipo=TipoPendiente.CONCEPTO_EN_CONFLICTO,
                    entidad="concepto",
                    valor_origen=nodo.clave,
                    propuesta={
                        "prototipo": arbol.clave_prototipo,
                        "accion": (
                            "Composición distinta a la del catálogo; corrige a "
                            "mano o vuelve a cargar el prototipo correcto."
                        ),
                    },
                    critico=False,
                    origen_ref=f"fila {nodo.fila}",
                )
            )
        elif actual is None:
            # Alta: clave nueva en el catálogo.
            tipo_concepto = (
                TipoConcepto.AUXILIAR
                if nodo.tipo is TipoNodoPresupuesto.CONCEPTO_AUXILIAR
                else TipoConcepto.CONCEPTO
            )
            if not dry_run:
                concepto_id = await self._conceptos.crear(
                    {
                        "tipo": str(tipo_concepto),
                        "clave": nodo.clave,
                        "descripcion": nodo.descripcion,
                        "unidad_id": unidad_id,
                        "familia_id": None,
                    }
                )
                operaciones.append(
                    _operacion("concepto", concepto_id, "insert", despues={"clave": nodo.clave})
                )
                operaciones.extend(
                    await _publicar_cpu_de_concepto(
                        self._conceptos, concepto_id, filas_explosion, precio
                    )
                )

            claves_nuevas.add(nodo.clave)
            catalogo_conceptos[nodo.clave] = {
                "id": concepto_id,
                "tipo": str(tipo_concepto),
                "clave": nodo.clave,
                "descripcion": nodo.descripcion,
                "unidad_id": unidad_id,
                "familia_id": None,
                "estatus": "activo",
            }
            firma_cache[nodo.clave] = firma_nueva
        elif diferente:
            # Composición distinta pero nadie más vigente depende de ella:
            # actualización legítima (típicamente este mismo prototipo
            # recargando una corrección), no conflicto — se publica igual
            # que un cambio en `AplicadorCPU`.
            assert actual is not None  # noqa: S101 — `diferente` implica `actual is not None`
            assert concepto_id is not None  # noqa: S101
            if not dry_run:
                await self._conceptos.actualizar(
                    concepto_id,
                    {
                        "descripcion": nodo.descripcion,
                        "unidad_id": unidad_id,
                        "familia_id": actual.get("familia_id"),
                    },
                )
                operaciones.append(
                    _operacion(
                        "concepto",
                        concepto_id,
                        "update",
                        antes=_recorte(
                            actual, ("tipo", "descripcion", "unidad_id", "familia_id", "estatus")
                        ),
                        despues={"descripcion": nodo.descripcion, "unidad_id": unidad_id},
                    )
                )
                operaciones.extend(
                    await _publicar_cpu_de_concepto(
                        self._conceptos, concepto_id, filas_explosion, precio
                    )
                )

            claves_actualizadas.add(nodo.clave)
            catalogo_conceptos[nodo.clave] = {
                **actual,
                "descripcion": nodo.descripcion,
                "unidad_id": unidad_id,
            }
            firma_cache[nodo.clave] = firma_nueva
        else:
            # Sin conflicto, ya existía, misma composición: "si es idéntico,
            # no crea versión" (§10.8) — no se toca `concepto`/`explosion`/
            # `cpu`. `catalogo_conceptos`/`firma_cache` ya están correctos
            # (vienen del propio `actual`).
            contadores["conceptos_sin_cambio"] += 1

        contadores["partidas"] += 1
        cantidad_partida = nodo.cantidad if nodo.cantidad is not None else Decimal(1)
        precio_unitario = precio.total.monto

        anterior_nodo = nodos_existentes.get(nodo.clave)
        contadores["nodos_creados" if anterior_nodo is None else "nodos_actualizados"] += 1

        if not dry_run:
            nodo_id, _ = await self._prototipo_nodos.upsert(
                prototipo_id,
                clave=nodo.clave,
                datos={
                    "parent_id": parent_id_db,
                    "tipo": "concepto",
                    "nombre": nodo.descripcion,
                    "concepto_id": concepto_id,
                    "orden": nodo.indice or 0,
                    "cantidad": cantidad_partida,
                },
            )
            operaciones.append(
                _operacion(
                    "prototipo_nodo",
                    nodo_id,
                    "insert" if anterior_nodo is None else "update",
                    antes=_recorte(
                        anterior_nodo,
                        ("parent_id", "tipo", "nombre", "concepto_id", "nivel_id", "etapa_id", "orden", "cantidad"),
                    )
                    if anterior_nodo
                    else None,
                    despues={"clave": nodo.clave, "concepto_id": str(concepto_id)},
                )
            )
            partidas.append(
                {
                    "concepto_id": concepto_id,
                    "prototipo_nodo_id": nodo_id,
                    "cantidad": cantidad_partida,
                    "precio_unitario": precio_unitario,
                    "importe": cantidad_partida * precio_unitario,
                    "orden": nodo.indice or 0,
                }
            )
