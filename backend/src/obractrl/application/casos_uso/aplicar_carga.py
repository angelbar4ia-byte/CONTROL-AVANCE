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

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from obractrl.application.puertos.cargadores import RepositorioCargas
from obractrl.application.puertos.repositorios import (
    RepositorioConceptos,
    RepositorioContratistas,
    RepositorioCuadrillas,
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
from obractrl.domain.cargadores.cuadrillas import CuadrillaCargada
from obractrl.domain.cargadores.homologacion import Homologador
from obractrl.domain.cargadores.mano_de_obra import FilaManoObra
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
    "AplicadorCuadrillas",
    "AplicadorDeCarga",
    "AplicadorDePrototipos",
    "AplicadorManoObra",
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


async def _resolver_o_dar_de_alta(
    valor: str,
    *,
    homologador: Homologador,
    id_por_clave: dict[str, UUID],
    creadas: dict[str, UUID | None],
    crear: Callable[[dict[str, Any]], Awaitable[UUID]],
    dry_run: bool,
) -> UUID | None:
    """Unidad o familia: si el archivo trae una que no cruza contra el
    catálogo, se da de alta con ese mismo texto como clave y nombre, en vez
    de solo dejar un pendiente sin que nadie la cree (§8.7).

    Es la excepción a "lo que no cruza no se inventa" (§10.3) porque el
    riesgo es distinto al de un concepto o un precio: una unidad o familia
    de más se corrige después con un alta/homologación, sin que eso
    signifique que alguien perdió datos o que un precio salió mal. Bloquear
    la carga entera por una unidad nueva —el caso normal, no la excepción,
    en un catálogo que recién empieza a cargarse— es peor que crearla.

    Dentro de la misma carga la misma clave nueva se da de alta una sola
    vez (`creadas` la recuerda tal cual vino en el archivo); en `dry_run`
    no se escribe nada, pero cuenta igual para que la vista previa no
    prometa un alta que después no aplica igual (§9.3).
    """
    clave = homologador.resolver(valor)
    if clave is not None:
        return id_por_clave.get(clave)
    if valor not in creadas:
        creadas[valor] = None if dry_run else await crear({"clave": valor, "nombre": valor})
    return creadas[valor]


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
        nuevas_unidades: dict[str, UUID | None] = {}
        nuevas_familias: dict[str, UUID | None] = {}

        for registro in lectura.registros:
            material: FilaMaterial = registro  # type: ignore[assignment]
            actual = por_clave.get(material.llave, {})

            unidad_id = actual.get("unidad_id")
            if material.unidad:
                unidad_id = await _resolver_o_dar_de_alta(
                    material.unidad,
                    homologador=unidades,
                    id_por_clave=id_unidad,
                    creadas=nuevas_unidades,
                    crear=self._unidades.crear,
                    dry_run=dry_run,
                )

            familia_id = actual.get("familia_id")
            if material.familia:
                familia_id = await _resolver_o_dar_de_alta(
                    material.familia,
                    homologador=familias,
                    id_por_clave=id_familia,
                    creadas=nuevas_familias,
                    crear=self._familias.crear,
                    dry_run=dry_run,
                )

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
            detalle={
                "unidades_creadas": len(nuevas_unidades),
                "familias_creadas": len(nuevas_familias),
            },
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


# --- Mano de obra / Destajos (§10.6 `CABECERAS_MANO_DE_OBRA.xlsx`) --------

_CAMPOS_MANO_OBRA = (
    "descripcion",
    "unidad_id",
    "familia_id",
    "costo_base",
    "cuadrilla_id",
    "rendimiento_teorico",
)
"""Campos que este cargador gobierna. Sin el trío de valuación de almacén
(§10.5) ni `iva_aplica`: ese archivo no trae esas columnas — son de
materiales, no de mano de obra."""

_CAMPOS_RESTAURABLES_MANO_OBRA = (
    *_CAMPOS_MANO_OBRA,
    "estatus",
)
"""Lo que el snapshot guarda como ``antes`` (`adapters/repos/
cargas_sql._RESTAURAR`)."""


class AplicadorManoObra:
    """Mano de obra / destajos (§10.6).

    Copia estructural de `AplicadorMateriales`: un destajo es un `Insumo`
    con ``tipo='mano_obra'`` (§7.3), mismo catálogo, mismo diff/versionado.
    Además homologa —o da de alta, mismo criterio que unidad/familia
    (§8.7)— la `cuadrilla` que ejecuta el destajo, y si el archivo trae
    rendimiento teórico se lo asienta también a la cuadrilla ("la cuadrilla
    asume el rendimiento" del destajo que se le asigna): un efecto
    colateral fuera del diff de insumo, porque la cuadrilla no es lo que
    esta carga está versionando.
    """

    def __init__(
        self,
        *,
        insumos: RepositorioInsumos,
        unidades: RepositorioUnidades,
        familias: RepositorioFamilias,
        cuadrillas: RepositorioCuadrillas,
        cargas: RepositorioCargas,
    ) -> None:
        self._insumos = insumos
        self._unidades = unidades
        self._familias = familias
        self._cuadrillas = cuadrillas
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
            tipo=str(TipoInsumo.MANO_OBRA), solo_activos=False
        )
        por_clave = {str(fila["clave"]): fila for fila in vigentes_filas}

        unidades_filas = await self._unidades.listar(solo_activos=False)
        unidades = Homologador.desde(
            unidades_filas, mapeos=await self._cargas.mapeos("unidad")
        )
        id_unidad = {str(f["clave"]): f["id"] for f in unidades_filas}

        # Sin ámbito propio de "mano_obra" en `familia.aplica_a` (§10.1 solo
        # define material/concepto): un destajo es un insumo igual que un
        # material, así que comparte el mismo árbol de familias que ellos.
        familias_filas = await self._familias.listar(
            aplica_a="material", solo_activos=False
        )
        familias = Homologador.desde(
            familias_filas, mapeos=await self._cargas.mapeos("familia")
        )
        id_familia = {str(f["clave"]): f["id"] for f in familias_filas}

        cuadrillas_filas = await self._cuadrillas.listar(solo_activos=False)
        cuadrillas = Homologador.desde(
            cuadrillas_filas, mapeos=await self._cargas.mapeos("cuadrilla")
        )
        id_cuadrilla = {str(f["clave"]): f["id"] for f in cuadrillas_filas}

        pendientes: list[PendientePropuesto] = []
        entrantes: dict[str, dict[str, Any]] = {}
        nuevas_unidades: dict[str, UUID | None] = {}
        nuevas_familias: dict[str, UUID | None] = {}
        nuevas_cuadrillas: dict[str, UUID | None] = {}
        rendimientos_por_cuadrilla: dict[UUID, Decimal] = {}

        for registro in lectura.registros:
            destajo: FilaManoObra = registro  # type: ignore[assignment]
            actual = por_clave.get(destajo.llave, {})

            unidad_id = actual.get("unidad_id")
            if destajo.unidad:
                unidad_id = await _resolver_o_dar_de_alta(
                    destajo.unidad,
                    homologador=unidades,
                    id_por_clave=id_unidad,
                    creadas=nuevas_unidades,
                    crear=self._unidades.crear,
                    dry_run=dry_run,
                )

            familia_id = actual.get("familia_id")
            if destajo.familia:
                familia_id = await _resolver_o_dar_de_alta(
                    destajo.familia,
                    homologador=familias,
                    id_por_clave=id_familia,
                    creadas=nuevas_familias,
                    crear=self._familias.crear,
                    dry_run=dry_run,
                )

            cuadrilla_id = actual.get("cuadrilla_id")
            if destajo.cuadrilla:
                cuadrilla_id = await _resolver_o_dar_de_alta(
                    destajo.cuadrilla,
                    homologador=cuadrillas,
                    id_por_clave=id_cuadrilla,
                    creadas=nuevas_cuadrillas,
                    crear=self._cuadrillas.crear,
                    dry_run=dry_run,
                )
                if cuadrilla_id is not None and destajo.rendimiento_teorico is not None:
                    rendimientos_por_cuadrilla[cuadrilla_id] = destajo.rendimiento_teorico

            entrantes[destajo.llave] = {
                "descripcion": destajo.descripcion,
                "unidad_id": unidad_id,
                "familia_id": familia_id,
                "costo_base": _o_vigente(destajo.costo_base, actual, "costo_base"),
                "cuadrilla_id": cuadrilla_id,
                "rendimiento_teorico": _o_vigente(
                    destajo.rendimiento_teorico, actual, "rendimiento_teorico"
                ),
            }

        vigentes = {
            clave: {campo: fila.get(campo) for campo in _CAMPOS_MANO_OBRA}
            for clave, fila in por_clave.items()
        }
        diff = diferenciar(vigentes=vigentes, entrantes=entrantes, modo=modo)

        operaciones: list[dict[str, Any]] = []
        if not dry_run:
            for alta in diff.altas:
                nuevo_id = await self._insumos.crear(
                    {
                        "tipo": str(TipoInsumo.MANO_OBRA),
                        "clave": alta.clave,
                        "descripcion": alta.despues["descripcion"],
                        "unidad_id": alta.despues["unidad_id"],
                        "familia_id": alta.despues["familia_id"],
                        "costo_base": alta.despues["costo_base"],
                        "cuadrilla_id": alta.despues["cuadrilla_id"],
                        "rendimiento_teorico": alta.despues["rendimiento_teorico"],
                    }
                )
                operaciones.append(
                    _operacion("insumo", nuevo_id, "insert", despues=dict(alta.despues))
                )

            for cambio in diff.cambios:
                fila = por_clave[cambio.clave]
                await self._insumos.actualizar(fila["id"], dict(cambio.despues))
                operaciones.append(
                    _operacion(
                        "insumo",
                        fila["id"],
                        "update",
                        antes=_recorte(fila, _CAMPOS_RESTAURABLES_MANO_OBRA),
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
                        antes=_recorte(fila, _CAMPOS_RESTAURABLES_MANO_OBRA),
                        despues={"estatus": _ESTATUS_BAJA},
                    )
                )

            for cuadrilla_id, rendimiento in rendimientos_por_cuadrilla.items():
                await self._cuadrillas.actualizar_rendimiento(cuadrilla_id, rendimiento)

        return Aplicacion(
            diff=diff,
            operaciones=tuple(operaciones),
            pendientes=tuple(pendientes),
            insertados=len(diff.altas),
            actualizados=len(diff.cambios) + len(diff.bajas),
            omitidos=diff.omitidos + lectura.omitidos,
            detalle={
                "unidades_creadas": len(nuevas_unidades),
                "familias_creadas": len(nuevas_familias),
                "cuadrillas_creadas": len(nuevas_cuadrillas),
            },
        )


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
        nuevas_unidades: dict[str, UUID | None] = {}
        nuevas_familias: dict[str, UUID | None] = {}

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
                unidad_id = await _resolver_o_dar_de_alta(
                    cabeza.unidad,
                    homologador=unidades,
                    id_por_clave=id_unidad,
                    creadas=nuevas_unidades,
                    crear=self._unidades.crear,
                    dry_run=dry_run,
                )

            familia_id = actual.get("familia_id")
            if cabeza.familia:
                familia_id = await _resolver_o_dar_de_alta(
                    cabeza.familia,
                    homologador=familias,
                    id_por_clave=id_familia,
                    creadas=nuevas_familias,
                    crear=self._familias.crear,
                    dry_run=dry_run,
                )

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
            detalle={
                "unidades_creadas": len(nuevas_unidades),
                "familias_creadas": len(nuevas_familias),
            },
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


# --- Cuadrillas (§10.6 `CABECERAS_CUADRILLAS.xlsx`) -----------------------


class AplicadorCuadrillas:
    """Composición y PU de cuadrillas (§10.6, §7.3, §7.6).

    Para efectos de costo, una cuadrilla es un concepto cuya composición es
    100% mano de obra: cada integrante se modela como un `Componente`
    (`domain.catalogos.apu`) con ``categoria=MANO_OBRA``, así que
    `calcular_cpu` devuelve un `PrecioUnitario` donde destajo == total
    siempre — "lo que cobra la cuadrilla es el 100% de su costo". Cero
    matemática nueva: se reutiliza tal cual lo que ya prueba `AplicadorCPU`.

    Un integrante cuyo insumo no está en el catálogo detiene la cuadrilla
    entera (mismo criterio que un componente de concepto sin insumo, §10.3):
    un PU con un hueco es peor que no cargarlo.
    """

    def __init__(
        self,
        *,
        cuadrillas: RepositorioCuadrillas,
        insumos: RepositorioInsumos,
        unidades: RepositorioUnidades,
        cargas: RepositorioCargas,
    ) -> None:
        self._cuadrillas = cuadrillas
        self._insumos = insumos
        self._unidades = unidades
        self._cargas = cargas

    async def aplicar(  # noqa: C901 — el flujo del §9.2 es lineal, no ramificado
        self,
        lectura: LecturaCarga,
        *,
        modo: ModoCarga,
        dry_run: bool,
        carga_id: UUID,
    ) -> Aplicacion:
        cuadrillas_filas = await self._cuadrillas.listar(solo_activos=False)
        por_clave = {str(f["clave"]): f for f in cuadrillas_filas}

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

        pendientes: list[PendientePropuesto] = []
        errores: list[ErrorDeFila] = []
        entrantes: dict[str, dict[str, Any]] = {}
        planes: dict[str, dict[str, Any]] = {}
        nuevas_unidades: dict[str, UUID | None] = {}
        nuevas_cuadrillas: dict[str, UUID | None] = {}

        for registro in lectura.registros:
            bloque: CuadrillaCargada = registro  # type: ignore[assignment]
            cabeza = bloque.encabezado

            componentes: list[Componente] = []
            filas_integrantes: list[dict[str, Any]] = []
            incompleto = False

            for integrante in bloque.componentes:
                clave_insumo = insumos.resolver(str(integrante.clave_insumo))
                if clave_insumo is None:
                    pendientes.append(
                        _pendiente_de_mapeo(
                            "insumo",
                            str(integrante.clave_insumo),
                            integrante.fila,
                            critico=True,
                        )
                    )
                    incompleto = True
                    continue
                try:
                    del_dominio = Componente(
                        categoria=CategoriaExplosion.MANO_OBRA,
                        cantidad=integrante.cantidad,
                        clave_insumo=clave_insumo,
                        costo_unitario=integrante.costo_unitario or None,
                        orden=len(componentes),
                    )
                except ErrorDeAPU as exc:
                    errores.append(
                        ErrorDeFila(
                            fila=integrante.fila,
                            columna="cantidad",
                            valor=str(integrante.cantidad),
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
                filas_integrantes.append(
                    {
                        "insumo_id": insumos_por_clave[clave_insumo]["id"],
                        "cantidad": del_dominio.cantidad,
                        "costo_unitario": costo,
                        "importe": del_dominio.cantidad * costo,
                        "orden": len(filas_integrantes),
                    }
                )

            if incompleto:
                # Mismo criterio que un concepto con un insumo faltante: un
                # PU de cuadrilla con un hueco sale más barato que el real
                # y ese precio se propagaría a cada destajo que la use.
                continue

            actual = por_clave.get(bloque.llave, {})

            unidad_id = actual.get("unidad_id")
            if cabeza.unidad:
                unidad_id = await _resolver_o_dar_de_alta(
                    cabeza.unidad,
                    homologador=unidades,
                    id_por_clave=id_unidad,
                    creadas=nuevas_unidades,
                    crear=self._unidades.crear,
                    dry_run=dry_run,
                )

            try:
                precio = calcular_cpu(
                    bloque.llave,
                    composiciones={bloque.llave: componentes},
                    costos_insumo=costos_insumo,
                )
            except ErrorDeAPU as exc:
                errores.append(
                    ErrorDeFila(
                        fila=cabeza.fila, columna="clave", valor=bloque.llave, motivo=str(exc)
                    )
                )
                continue

            entrantes[bloque.llave] = {
                "nombre": cabeza.descripcion,
                "unidad_id": unidad_id,
                "composicion": _firma_cuadrilla(filas_integrantes, clave_de_insumo),
            }
            planes[bloque.llave] = {"filas_integrantes": filas_integrantes, "precio": precio}

        vigentes: dict[str, dict[str, Any]] = {}
        for clave, fila in por_clave.items():
            # La composición vigente solo se lee de las cuadrillas que el
            # archivo toca: para las demás el diff únicamente mira si están
            # o no (bajas del modo Reemplazar, §10.2).
            composicion = ""
            if clave in entrantes:
                version_vigente = next(
                    (v for v in await self._cuadrillas.versiones(fila["id"]) if v["vigente"]),
                    None,
                )
                if version_vigente is not None:
                    composicion = _firma_cuadrilla(
                        await self._cuadrillas.integrantes_de(version_vigente["id"]),
                        clave_de_insumo,
                    )
            vigentes[clave] = {
                "nombre": fila.get("nombre"),
                "unidad_id": fila.get("unidad_id"),
                "composicion": composicion,
            }

        diff = diferenciar(vigentes=vigentes, entrantes=entrantes, modo=modo)

        operaciones: list[dict[str, Any]] = []
        if not dry_run:
            for cambio in (*diff.altas, *diff.cambios):
                plan = planes[cambio.clave]
                fila = por_clave.get(cambio.clave)

                if fila is None:
                    cuadrilla_id = await self._cuadrillas.crear(
                        {
                            "clave": cambio.clave,
                            "nombre": cambio.despues["nombre"],
                            "unidad_id": cambio.despues["unidad_id"],
                        }
                    )
                    nuevas_cuadrillas[cambio.clave] = cuadrilla_id
                    operaciones.append(
                        _operacion(
                            "cuadrilla", cuadrilla_id, "insert", despues={"clave": cambio.clave}
                        )
                    )
                else:
                    cuadrilla_id = fila["id"]
                    cambios_cuadrilla = {
                        "nombre": cambio.despues["nombre"],
                        "unidad_id": cambio.despues["unidad_id"],
                    }
                    await self._cuadrillas.actualizar(cuadrilla_id, cambios_cuadrilla)
                    operaciones.append(
                        _operacion(
                            "cuadrilla",
                            cuadrilla_id,
                            "update",
                            antes=_recorte(fila, ("nombre", "unidad_id", "estatus")),
                            despues=cambios_cuadrilla,
                        )
                    )

                operaciones.extend(
                    await _publicar_version_de_cuadrilla(
                        self._cuadrillas, cuadrilla_id, plan["filas_integrantes"], plan["precio"]
                    )
                )

            for baja in diff.bajas:
                fila = por_clave[baja.clave]
                # Baja lógica, igual que insumo/concepto: no se toca el
                # historial de versiones, solo el estatus del catálogo.
                await self._cuadrillas.actualizar(fila["id"], {"estatus": _ESTATUS_BAJA})
                operaciones.append(
                    _operacion(
                        "cuadrilla",
                        fila["id"],
                        "update",
                        antes=_recorte(fila, ("nombre", "unidad_id", "estatus")),
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
            detalle={
                "unidades_creadas": len(nuevas_unidades),
                "cuadrillas_creadas": len(nuevas_cuadrillas),
            },
        )


async def _publicar_version_de_cuadrilla(
    cuadrillas: RepositorioCuadrillas,
    cuadrilla_id: UUID,
    filas_integrantes: list[dict[str, Any]],
    precio: PrecioUnitario,
) -> list[dict[str, Any]]:
    """Publica la versión nueva de PU de una cuadrilla y su composición (§10.8).

    A diferencia de `_publicar_cpu_de_concepto`, no hay una fila "viva" de
    composición que sustituir: `cuadrilla_integrante.cuadrilla_version_id`
    no admite nulo, así que cada versión es dueña exclusiva de sus filas —
    basta con insertar las de la versión nueva; las de versiones anteriores
    quedan intactas, que es justo el historial que se pidió (§10.8).
    """
    operaciones: list[dict[str, Any]] = []

    versiones = await cuadrillas.versiones(cuadrilla_id)
    vigentes_antes = {f["id"]: dict(f) for f in versiones if bool(f["vigente"])}
    nueva, retiradas = publicar_version(
        [_version_de_cuadrilla(f) for f in versiones], precio, variante=None
    )
    for identificador, fila in vigentes_antes.items():
        if int(fila["version"]) in retiradas:
            operaciones.append(
                _operacion(
                    "cuadrilla_version",
                    identificador,
                    "update",
                    antes={"precio_unitario": fila["precio_unitario"], "vigente": True},
                    despues={"vigente": False},
                )
            )

    version_id = await cuadrillas.publicar_version(
        cuadrilla_id,
        version=nueva.version,
        precio_unitario=nueva.precio.total.monto,
        retirar=list(retiradas),
    )
    operaciones.append(
        _operacion("cuadrilla_version", version_id, "insert", despues={"version": nueva.version})
    )

    insertadas = await cuadrillas.agregar_integrantes(version_id, filas_integrantes)
    for fila in insertadas:
        operaciones.append(_operacion("cuadrilla_integrante", fila["id"], "insert"))

    return operaciones


def _version_de_cuadrilla(fila: dict[str, Any]) -> VersionCPU:
    # El destajo de una cuadrilla siempre es el 100% de su costo (§7.3): no
    # hay una columna `precio_destajo` propia que leer, a diferencia de `cpu`.
    return VersionCPU(
        version=int(fila["version"]),
        precio=PrecioUnitario(
            total=Dinero(Decimal(str(fila["precio_unitario"]))),
            destajo=Dinero(Decimal(str(fila["precio_unitario"]))),
        ),
        vigente=bool(fila["vigente"]),
        variante=None,
    )


def _firma_cuadrilla(filas: list[dict[str, Any]], clave_de_insumo: dict[Any, str]) -> str:
    """Composición de una cuadrilla como texto comparable (§10.8) — mismo
    criterio que `_firma_explosion`, sin `categoria`: todo integrante de una
    cuadrilla es mano de obra por definición."""
    partes = []
    for fila in sorted(filas, key=lambda f: int(f.get("orden") or 0)):
        clave = clave_de_insumo.get(fila.get("insumo_id"), "")
        cantidad = Decimal(str(fila.get("cantidad") or 0)).normalize() + Decimal(0)
        costo = Decimal(str(fila.get("costo_unitario") or 0)).normalize() + Decimal(0)
        partes.append(f"{clave}:{cantidad}:{costo}")
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


def _clave_catalogo_concepto(nodo: NodoLeido, arbol: ArbolPrototipoCargado) -> str:
    """La clave que identifica el concepto en el catálogo **compartido**.

    Para `CONCEPTO`/`CONCEPTO_AUXILIAR` es la propia clave del archivo
    (`EST-`, `SUB-`...): es catálogo real, la misma composición vale para
    cualquier prototipo que la use — por diseño (§7.3).

    Para una etapa que colapsa en concepto
    (`es_etapa_con_componentes_directos`) **no existe tal cosa**: dos
    prototipos comparten la misma clave de etapa (`ECO-...`) para un paso
    que no tiene por qué costar lo mismo en cada uno —es la estructura del
    archivo real, no una excepción—, así que no hay "la vigente" que
    compartir. Se aísla con la clave del prototipo para que cada uno tenga
    su propia fila de `concepto`/`explosion`/`cpu` y nunca compitan por
    cuál es la buena: ni conflicto que resolver, ni riesgo de que el
    catálogo compartido termine con la composición de un prototipo ajeno.
    """
    if nodo.tipo is TipoNodoPresupuesto.ETAPA:
        return f"{nodo.clave}~{arbol.clave_prototipo}"
    return nodo.clave


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
        nuevas_unidades: dict[str, UUID | None] = {}

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
                    nuevas_unidades=nuevas_unidades,
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
            detalle={**contadores, "unidades_creadas": len(nuevas_unidades)},
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
        nuevas_unidades: dict[str, UUID | None],
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
                nuevas_unidades=nuevas_unidades,
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
                nuevas_unidades=nuevas_unidades,
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
        nuevas_unidades: dict[str, UUID | None],
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

        clave_catalogo = _clave_catalogo_concepto(nodo, arbol)

        try:
            precio = calcular_cpu(
                clave_catalogo,
                composiciones={clave_catalogo: componentes},
                costos_insumo=costos_insumo,
            )
        except ErrorDeAPU as exc:
            errores.append(
                ErrorDeFila(fila=nodo.fila, columna="clave_hijo", valor=nodo.clave, motivo=str(exc))
            )
            contadores["conceptos_omitidos"] += 1
            return

        actual = catalogo_conceptos.get(clave_catalogo)

        unidad_id = actual.get("unidad_id") if actual else None
        if nodo.unidad:
            unidad_id = await _resolver_o_dar_de_alta(
                nodo.unidad,
                homologador=unidades,
                id_por_clave=id_unidad,
                creadas=nuevas_unidades,
                crear=self._unidades.crear,
                dry_run=dry_run,
            )

        firma_nueva = _firma_explosion(filas_explosion, clave_de_insumo)

        diferente = False
        concepto_id: UUID | None = actual["id"] if actual else None
        if actual is not None:
            firma_vigente = firma_cache.get(clave_catalogo)
            if firma_vigente is None:
                # Sin firma en caché, `actual` solo puede venir del catálogo
                # real (no de una simulación en dry_run de este mismo
                # archivo — esa siempre deja firma en caché al procesar,
                # línea de abajo): `concepto_id` es un id real.
                assert concepto_id is not None  # noqa: S101
                filas_previas = await self._conceptos.explosion_directa(concepto_id)
                firma_vigente = _firma_explosion(filas_previas, clave_de_insumo)
                firma_cache[clave_catalogo] = firma_vigente
            diferente = firma_vigente != firma_nueva

        conflicto = False
        if diferente and concepto_id is None:
            # `actual` es un alta de ESTE MISMO archivo que dry_run dejó sin
            # id real (no se llamó `crear()`, §9.3: la vista previa no
            # escribe). Sin fila en la base no hay `otros_prototipos_con_
            # partida_vigente` que consultar — pero dos prototipos del mismo
            # archivo proponiendo la primera composición de una clave nueva
            # y no coincidiendo entre sí es exactamente el mismo desacuerdo
            # que el conflicto real: ninguno de los dos es "el vigente"
            # todavía. Se resuelve igual, sin tocar nada.
            conflicto = True
        elif diferente:
            assert concepto_id is not None  # noqa: S101 — cubierto arriba
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
                    valor_origen=clave_catalogo,
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
                        "clave": clave_catalogo,
                        "descripcion": nodo.descripcion,
                        "unidad_id": unidad_id,
                        "familia_id": None,
                    }
                )
                operaciones.append(
                    _operacion(
                        "concepto", concepto_id, "insert", despues={"clave": clave_catalogo}
                    )
                )
                operaciones.extend(
                    await _publicar_cpu_de_concepto(
                        self._conceptos, concepto_id, filas_explosion, precio
                    )
                )

            claves_nuevas.add(clave_catalogo)
            catalogo_conceptos[clave_catalogo] = {
                "id": concepto_id,
                "tipo": str(tipo_concepto),
                "clave": clave_catalogo,
                "descripcion": nodo.descripcion,
                "unidad_id": unidad_id,
                "familia_id": None,
                "estatus": "activo",
            }
            firma_cache[clave_catalogo] = firma_nueva
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

            claves_actualizadas.add(clave_catalogo)
            catalogo_conceptos[clave_catalogo] = {
                **actual,
                "descripcion": nodo.descripcion,
                "unidad_id": unidad_id,
            }
            firma_cache[clave_catalogo] = firma_nueva
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


class AplicadorDePrototipos:
    """Despacha al aplicador que corresponde al **formato** del archivo.

    `TipoCarga.PROTOTIPOS` acepta dos archivos distintos —el alta plana y la
    ingeniería por prototipo (ver `CargadorPrototipos`)— porque para el
    usuario son la misma tarea: poblar prototipos. Cuál llegó lo dice lo que
    el lector entregó, no un segundo campo en la pantalla que hubiera que
    mantener en sincronía con el archivo.
    """

    def __init__(
        self, *, plano: AplicadorPrototipos, ingenieria: AplicadorPresupuesto
    ) -> None:
        self._plano = plano
        self._ingenieria = ingenieria

    async def aplicar(
        self,
        lectura: LecturaCarga,
        *,
        modo: ModoCarga,
        dry_run: bool,
        carga_id: UUID,
    ) -> Aplicacion:
        # Un archivo vacío o que no dejó ningún registro válido cae al plano:
        # da el mismo resultado (nada que aplicar) y evita una rama muerta.
        es_arbol = bool(lectura.registros) and isinstance(
            lectura.registros[0], ArbolPrototipoCargado
        )
        aplicador = self._ingenieria if es_arbol else self._plano
        return await aplicador.aplicar(
            lectura, modo=modo, dry_run=dry_run, carga_id=carga_id
        )
