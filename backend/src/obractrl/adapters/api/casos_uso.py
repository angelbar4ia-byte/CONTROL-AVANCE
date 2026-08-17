"""Construcción de casos de uso para los endpoints.

Spec §12.11 (el borde ensambla; la aplicación no sabe cómo).

Cada función es una dependencia de FastAPI que arma un caso de uso con
implementaciones concretas de sus puertos, a partir de la sesión con RLS ya
fijado (`SesionRLS`, `adapters/api/dependencias.py`). Los routers dependen de
estas funciones, nunca construyen un repositorio SQL directamente: así el
router solo conoce el caso de uso (aplicación), no `adapters.repos`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from obractrl.adapters.api.dependencias import SesionRLS
from obractrl.adapters.repos.actividades_sql import RepositorioActividadesSQL
from obractrl.adapters.repos.calendario_sql import RepositorioCalendarioSQL
from obractrl.adapters.repos.cierres_sql import RepositorioCierresSQL
from obractrl.adapters.repos.clusters_sql import RepositorioClustersSQL
from obractrl.adapters.repos.conceptos_sql import RepositorioConceptosSQL
from obractrl.adapters.repos.contratistas_sql import RepositorioContratistasSQL
from obractrl.adapters.repos.estimaciones_sql import RepositorioEstimacionesSQL
from obractrl.adapters.repos.evaluaciones_sql import RepositorioEvaluacionesSQL
from obractrl.adapters.repos.familias_sql import RepositorioFamiliasSQL
from obractrl.adapters.repos.incidencias_sql import RepositorioIncidenciasSQL
from obractrl.adapters.repos.insumos_sql import RepositorioInsumosSQL
from obractrl.adapters.repos.materiales_sql import RepositorioMaterialesSQL
from obractrl.adapters.repos.obras_sql import RepositorioObrasSQL
from obractrl.adapters.repos.programas_sql import RepositorioProgramasSQL
from obractrl.adapters.repos.prototipos_sql import RepositorioPrototiposSQL
from obractrl.adapters.repos.proyectos_sql import RepositorioProyectosSQL
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL
from obractrl.adapters.repos.unidades_sql import RepositorioUnidadesSQL
from obractrl.application.casos_uso.calcular_cpu import (
    ExplotarConcepto,
    ObtenerCPU,
    PublicarVersionCPU,
)
from obractrl.application.casos_uso.capturar_avance import CapturarAvance
from obractrl.application.casos_uso.generar_obra_desde_prototipo import (
    GenerarObraDesdePrototipo,
)
from obractrl.application.casos_uso.gestionar_catalogos import (
    CrearConcepto,
    CrearContratista,
    CrearFamilia,
    CrearInsumo,
    CrearUnidad,
)
from obractrl.application.casos_uso.gestionar_cierre import (
    AutorizarCierre,
    RechazarCierre,
    SolicitarCierre,
    ValidarCierre,
)
from obractrl.application.casos_uso.gestionar_estimacion import (
    EnviarEstimacion,
    GenerarEstimacion,
    ValidarEstimacion,
)
from obractrl.application.casos_uso.gestionar_evaluacion import (
    AgregarRespuestas,
    CrearEvaluacion,
)
from obractrl.application.casos_uso.gestionar_incidencia import (
    AbrirIncidencia,
    CerrarIncidencia,
    ProgramarIncidencia,
    RechazarIncidencia,
    RegistrarEventoIncidencia,
)
from obractrl.application.casos_uso.gestionar_obra import (
    ActualizarObra,
    CrearObra,
    CrearObrasEnLote,
)
from obractrl.application.casos_uso.gestionar_programacion import (
    ComandoRecalcularRutaCritica,
    ConsultarRutaCritica,
    CrearProgramaBase,
    EditarProgramacionActividad,
    InstanciarProgramaObra,
    RecalcularRutaCritica,
)
from obractrl.application.casos_uso.gestionar_proyecto import (
    CrearCluster,
    CrearPrototipo,
    CrearProyecto,
)
from obractrl.application.casos_uso.registrar_salida_almacen import RegistrarSalidaAlmacen
from obractrl.application.eventos import ActividadCerrada, BusEnProceso

__all__ = [
    "AbrirIncidenciaDep",
    "ActualizarObraDep",
    "AgregarRespuestasDep",
    "AutorizarCierreDep",
    "CapturarAvanceDep",
    "CerrarIncidenciaDep",
    "ConsultarRutaCriticaDep",
    "CrearClusterDep",
    "CrearConceptoDep",
    "CrearContratistaDep",
    "CrearEvaluacionDep",
    "CrearFamiliaDep",
    "CrearInsumoDep",
    "CrearObraDep",
    "CrearObrasEnLoteDep",
    "CrearProgramaBaseDep",
    "CrearPrototipoDep",
    "CrearProyectoDep",
    "CrearUnidadDep",
    "EditarProgramacionActividadDep",
    "EnviarEstimacionDep",
    "ExplotarConceptoDep",
    "GenerarEstimacionDep",
    "GenerarObraDesdePrototipoDep",
    "InstanciarProgramaObraDep",
    "ObtenerCPUDep",
    "ProgramarIncidenciaDep",
    "PublicarVersionCPUDep",
    "RecalcularRutaCriticaDep",
    "RechazarCierreDep",
    "RechazarIncidenciaDep",
    "RegistrarEventoIncidenciaDep",
    "RegistrarSalidaAlmacenDep",
    "SolicitarCierreDep",
    "ValidarCierreDep",
    "ValidarEstimacionDep",
]


def obtener_capturar_avance(sesion: SesionRLS) -> CapturarAvance:
    return CapturarAvance(
        actividades=RepositorioActividadesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


CapturarAvanceDep = Annotated[CapturarAvance, Depends(obtener_capturar_avance)]


def obtener_solicitar_cierre(sesion: SesionRLS) -> SolicitarCierre:
    return SolicitarCierre(
        actividades=RepositorioActividadesSQL(sesion),
        cierres=RepositorioCierresSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_autorizar_cierre(sesion: SesionRLS) -> AutorizarCierre:
    return AutorizarCierre(
        cierres=RepositorioCierresSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_validar_cierre(sesion: SesionRLS) -> ValidarCierre:
    """Validar un cierre publica `ActividadCerrada` (§11.3 C.4).

    El **borde** es quien decide que ese evento recalcula el CPM: el caso de
    uso de cierres no conoce el de programación, y viceversa (§11.1). Cambiar
    el transporte a Arq es sustituir el bus aquí, sin tocar ningún caso de uso.
    """
    return ValidarCierre(
        actividades=RepositorioActividadesSQL(sesion),
        cierres=RepositorioCierresSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
        eventos=_bus_de_cierre(sesion),
    )


def _bus_de_cierre(sesion: SesionRLS) -> BusEnProceso:
    """`ActividadCerrada` → recalcular la ruta crítica de su obra (§11.1)."""
    recalcular = obtener_recalcular_ruta_critica(sesion)

    async def _recalcular_cpm(evento: ActividadCerrada) -> None:
        await recalcular.ejecutar(
            ComandoRecalcularRutaCritica(obra_id=evento.obra_id)
        )

    bus = BusEnProceso()
    bus.suscribir(ActividadCerrada, _recalcular_cpm)
    return bus


def obtener_rechazar_cierre(sesion: SesionRLS) -> RechazarCierre:
    return RechazarCierre(
        actividades=RepositorioActividadesSQL(sesion),
        cierres=RepositorioCierresSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


SolicitarCierreDep = Annotated[SolicitarCierre, Depends(obtener_solicitar_cierre)]
AutorizarCierreDep = Annotated[AutorizarCierre, Depends(obtener_autorizar_cierre)]
ValidarCierreDep = Annotated[ValidarCierre, Depends(obtener_validar_cierre)]
RechazarCierreDep = Annotated[RechazarCierre, Depends(obtener_rechazar_cierre)]


def obtener_generar_estimacion(sesion: SesionRLS) -> GenerarEstimacion:
    return GenerarEstimacion(
        estimaciones=RepositorioEstimacionesSQL(sesion),
        calendario=RepositorioCalendarioSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_enviar_estimacion(sesion: SesionRLS) -> EnviarEstimacion:
    return EnviarEstimacion(
        estimaciones=RepositorioEstimacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_validar_estimacion(sesion: SesionRLS) -> ValidarEstimacion:
    return ValidarEstimacion(
        estimaciones=RepositorioEstimacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


GenerarEstimacionDep = Annotated[GenerarEstimacion, Depends(obtener_generar_estimacion)]
EnviarEstimacionDep = Annotated[EnviarEstimacion, Depends(obtener_enviar_estimacion)]
ValidarEstimacionDep = Annotated[ValidarEstimacion, Depends(obtener_validar_estimacion)]


def obtener_registrar_salida_almacen(sesion: SesionRLS) -> RegistrarSalidaAlmacen:
    return RegistrarSalidaAlmacen(
        materiales=RepositorioMaterialesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


RegistrarSalidaAlmacenDep = Annotated[
    RegistrarSalidaAlmacen, Depends(obtener_registrar_salida_almacen)
]


def obtener_abrir_incidencia(sesion: SesionRLS) -> AbrirIncidencia:
    return AbrirIncidencia(
        actividades=RepositorioActividadesSQL(sesion),
        incidencias=RepositorioIncidenciasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_programar_incidencia(sesion: SesionRLS) -> ProgramarIncidencia:
    return ProgramarIncidencia(
        incidencias=RepositorioIncidenciasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_registrar_evento_incidencia(sesion: SesionRLS) -> RegistrarEventoIncidencia:
    return RegistrarEventoIncidencia(
        incidencias=RepositorioIncidenciasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_cerrar_incidencia(sesion: SesionRLS) -> CerrarIncidencia:
    return CerrarIncidencia(
        actividades=RepositorioActividadesSQL(sesion),
        incidencias=RepositorioIncidenciasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_rechazar_incidencia(sesion: SesionRLS) -> RechazarIncidencia:
    return RechazarIncidencia(
        actividades=RepositorioActividadesSQL(sesion),
        incidencias=RepositorioIncidenciasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


AbrirIncidenciaDep = Annotated[AbrirIncidencia, Depends(obtener_abrir_incidencia)]
ProgramarIncidenciaDep = Annotated[
    ProgramarIncidencia, Depends(obtener_programar_incidencia)
]
RegistrarEventoIncidenciaDep = Annotated[
    RegistrarEventoIncidencia, Depends(obtener_registrar_evento_incidencia)
]
CerrarIncidenciaDep = Annotated[CerrarIncidencia, Depends(obtener_cerrar_incidencia)]
RechazarIncidenciaDep = Annotated[
    RechazarIncidencia, Depends(obtener_rechazar_incidencia)
]


def obtener_crear_evaluacion(sesion: SesionRLS) -> CrearEvaluacion:
    return CrearEvaluacion(
        evaluaciones=RepositorioEvaluacionesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_agregar_respuestas(sesion: SesionRLS) -> AgregarRespuestas:
    return AgregarRespuestas(
        evaluaciones=RepositorioEvaluacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


CrearEvaluacionDep = Annotated[CrearEvaluacion, Depends(obtener_crear_evaluacion)]
AgregarRespuestasDep = Annotated[AgregarRespuestas, Depends(obtener_agregar_respuestas)]


# --- Proyecto · Obra (§11.2) --------------------------------------------


def obtener_crear_proyecto(sesion: SesionRLS) -> CrearProyecto:
    return CrearProyecto(
        proyectos=RepositorioProyectosSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_crear_cluster(sesion: SesionRLS) -> CrearCluster:
    return CrearCluster(
        clusters=RepositorioClustersSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_crear_prototipo(sesion: SesionRLS) -> CrearPrototipo:
    return CrearPrototipo(
        prototipos=RepositorioPrototiposSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


CrearProyectoDep = Annotated[CrearProyecto, Depends(obtener_crear_proyecto)]
CrearClusterDep = Annotated[CrearCluster, Depends(obtener_crear_cluster)]
CrearPrototipoDep = Annotated[CrearPrototipo, Depends(obtener_crear_prototipo)]


def obtener_crear_obra(sesion: SesionRLS) -> CrearObra:
    return CrearObra(
        obras=RepositorioObrasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_crear_obras_en_lote(sesion: SesionRLS) -> CrearObrasEnLote:
    return CrearObrasEnLote(
        obras=RepositorioObrasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_actualizar_obra(sesion: SesionRLS) -> ActualizarObra:
    return ActualizarObra(
        obras=RepositorioObrasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_generar_obra(sesion: SesionRLS) -> GenerarObraDesdePrototipo:
    return GenerarObraDesdePrototipo(
        obras=RepositorioObrasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


# --- Catálogos · APU (§11.2) ---------------------------------------------


def obtener_crear_unidad(sesion: SesionRLS) -> CrearUnidad:
    return CrearUnidad(
        unidades=RepositorioUnidadesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_crear_familia(sesion: SesionRLS) -> CrearFamilia:
    return CrearFamilia(
        familias=RepositorioFamiliasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_crear_insumo(sesion: SesionRLS) -> CrearInsumo:
    """Sirve a `POST /insumos` y a `POST /materiales`: `Material` es un
    `Insumo` con `tipo='material'` (§7.3)."""
    return CrearInsumo(
        insumos=RepositorioInsumosSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_crear_concepto(sesion: SesionRLS) -> CrearConcepto:
    return CrearConcepto(
        conceptos=RepositorioConceptosSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_crear_contratista(sesion: SesionRLS) -> CrearContratista:
    return CrearContratista(
        contratistas=RepositorioContratistasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_explotar_concepto(sesion: SesionRLS) -> ExplotarConcepto:
    return ExplotarConcepto(conceptos=RepositorioConceptosSQL(sesion))


def obtener_cpu(sesion: SesionRLS) -> ObtenerCPU:
    return ObtenerCPU(conceptos=RepositorioConceptosSQL(sesion))


def obtener_publicar_version_cpu(sesion: SesionRLS) -> PublicarVersionCPU:
    return PublicarVersionCPU(
        conceptos=RepositorioConceptosSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


CrearUnidadDep = Annotated[CrearUnidad, Depends(obtener_crear_unidad)]
CrearFamiliaDep = Annotated[CrearFamilia, Depends(obtener_crear_familia)]
CrearInsumoDep = Annotated[CrearInsumo, Depends(obtener_crear_insumo)]
CrearConceptoDep = Annotated[CrearConcepto, Depends(obtener_crear_concepto)]
CrearContratistaDep = Annotated[CrearContratista, Depends(obtener_crear_contratista)]
ExplotarConceptoDep = Annotated[ExplotarConcepto, Depends(obtener_explotar_concepto)]
ObtenerCPUDep = Annotated[ObtenerCPU, Depends(obtener_cpu)]
PublicarVersionCPUDep = Annotated[
    PublicarVersionCPU, Depends(obtener_publicar_version_cpu)
]


# --- Programación · CPM (§11.2) ------------------------------------------


def obtener_crear_programa_base(sesion: SesionRLS) -> CrearProgramaBase:
    return CrearProgramaBase(
        programas=RepositorioProgramasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_consultar_ruta_critica(sesion: SesionRLS) -> ConsultarRutaCritica:
    return ConsultarRutaCritica(
        actividades=RepositorioActividadesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        programas=RepositorioProgramasSQL(sesion),
    )


def obtener_recalcular_ruta_critica(sesion: SesionRLS) -> RecalcularRutaCritica:
    return RecalcularRutaCritica(
        actividades=RepositorioActividadesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        programas=RepositorioProgramasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_instanciar_programa(sesion: SesionRLS) -> InstanciarProgramaObra:
    return InstanciarProgramaObra(
        actividades=RepositorioActividadesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        programas=RepositorioProgramasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_editar_programacion(sesion: SesionRLS) -> EditarProgramacionActividad:
    return EditarProgramacionActividad(
        actividades=RepositorioActividadesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


CrearProgramaBaseDep = Annotated[
    CrearProgramaBase, Depends(obtener_crear_programa_base)
]
ConsultarRutaCriticaDep = Annotated[
    ConsultarRutaCritica, Depends(obtener_consultar_ruta_critica)
]
RecalcularRutaCriticaDep = Annotated[
    RecalcularRutaCritica, Depends(obtener_recalcular_ruta_critica)
]
InstanciarProgramaObraDep = Annotated[
    InstanciarProgramaObra, Depends(obtener_instanciar_programa)
]
EditarProgramacionActividadDep = Annotated[
    EditarProgramacionActividad, Depends(obtener_editar_programacion)
]


CrearObraDep = Annotated[CrearObra, Depends(obtener_crear_obra)]
CrearObrasEnLoteDep = Annotated[CrearObrasEnLote, Depends(obtener_crear_obras_en_lote)]
ActualizarObraDep = Annotated[ActualizarObra, Depends(obtener_actualizar_obra)]
GenerarObraDesdePrototipoDep = Annotated[
    GenerarObraDesdePrototipo, Depends(obtener_generar_obra)
]
