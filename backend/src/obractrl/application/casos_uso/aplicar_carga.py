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
    RepositorioObras,
    RepositorioUnidades,
)
from obractrl.domain.cargadores.almacen import FilaMovimiento, importe_con_iva
from obractrl.domain.cargadores.cpu import ConceptoCargado
from obractrl.domain.cargadores.homologacion import Homologador
from obractrl.domain.cargadores.materiales import FilaMaterial
from obractrl.domain.cargadores.reporte import (
    ErrorDeFila,
    LecturaCarga,
    PendientePropuesto,
    TipoPendiente,
)
from obractrl.domain.cargadores.versionado import Diff, diferenciar
from obractrl.domain.catalogos.apu import (
    Componente,
    ErrorDeAPU,
    VersionCPU,
    calcular_cpu,
    publicar_version,
)
from obractrl.domain.catalogos.reglas import resolver_iva
from obractrl.domain.materiales.reglas import ErrorDeMaterial, validar_signo_salida
from obractrl.domain.shared.diccionario import (
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
                    await self._publicar_cpu(concepto_id, plan)
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

    async def _publicar_cpu(
        self, concepto_id: UUID, plan: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Sustituye la composición y publica la versión nueva de CPU (§10.8).

        El orden importa y es el que la reversa deshace al revés: primero se
        guarda lo que se va a borrar de `explosion`, luego se retira el CPU
        vigente y se inserta el nuevo, y al final entran las filas nuevas de
        `explosion` atadas a ese CPU.
        """
        operaciones: list[dict[str, Any]] = []

        anteriores = await self._conceptos.explosion_directa(concepto_id)
        await self._conceptos.eliminar_explosion(concepto_id)
        for anterior in anteriores:
            operaciones.append(
                _operacion("explosion", anterior["id"], "delete", antes=dict(anterior))
            )

        versiones = await self._conceptos.versiones_cpu(concepto_id)
        vigentes_antes = {
            fila["id"]: dict(fila) for fila in versiones if bool(fila["vigente"])
        }
        nueva, retiradas = publicar_version(
            [
                _version_de_dominio(fila)
                for fila in versiones
            ],
            plan["precio"],
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

        cpu_id = await self._conceptos.publicar_version_cpu(
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

        insertadas = await self._conceptos.agregar_explosion(
            concepto_id, cpu_id=cpu_id, filas=plan["filas_explosion"]
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
