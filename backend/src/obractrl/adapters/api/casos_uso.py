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
from obractrl.adapters.repos.estimaciones_sql import RepositorioEstimacionesSQL
from obractrl.adapters.repos.evaluaciones_sql import RepositorioEvaluacionesSQL
from obractrl.adapters.repos.incidencias_sql import RepositorioIncidenciasSQL
from obractrl.adapters.repos.materiales_sql import RepositorioMaterialesSQL
from obractrl.adapters.repos.obras_sql import RepositorioObrasSQL
from obractrl.adapters.repos.prototipos_sql import RepositorioPrototiposSQL
from obractrl.adapters.repos.proyectos_sql import RepositorioProyectosSQL
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL
from obractrl.application.casos_uso.capturar_avance import CapturarAvance
from obractrl.application.casos_uso.generar_obra_desde_prototipo import (
    GenerarObraDesdePrototipo,
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
from obractrl.application.casos_uso.gestionar_proyecto import (
    CrearCluster,
    CrearPrototipo,
    CrearProyecto,
)
from obractrl.application.casos_uso.registrar_salida_almacen import RegistrarSalidaAlmacen

__all__ = [
    "AbrirIncidenciaDep",
    "ActualizarObraDep",
    "AgregarRespuestasDep",
    "AutorizarCierreDep",
    "CapturarAvanceDep",
    "CerrarIncidenciaDep",
    "CrearClusterDep",
    "CrearEvaluacionDep",
    "CrearObraDep",
    "CrearObrasEnLoteDep",
    "CrearPrototipoDep",
    "CrearProyectoDep",
    "EnviarEstimacionDep",
    "GenerarEstimacionDep",
    "GenerarObraDesdePrototipoDep",
    "ProgramarIncidenciaDep",
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
    return ValidarCierre(
        actividades=RepositorioActividadesSQL(sesion),
        cierres=RepositorioCierresSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


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


CrearObraDep = Annotated[CrearObra, Depends(obtener_crear_obra)]
CrearObrasEnLoteDep = Annotated[CrearObrasEnLote, Depends(obtener_crear_obras_en_lote)]
ActualizarObraDep = Annotated[ActualizarObra, Depends(obtener_actualizar_obra)]
GenerarObraDesdePrototipoDep = Annotated[
    GenerarObraDesdePrototipo, Depends(obtener_generar_obra)
]
