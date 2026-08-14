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
from obractrl.adapters.repos.estimaciones_sql import RepositorioEstimacionesSQL
from obractrl.adapters.repos.evaluaciones_sql import RepositorioEvaluacionesSQL
from obractrl.adapters.repos.obras_sql import RepositorioObrasSQL
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL
from obractrl.application.casos_uso.capturar_avance import CapturarAvance
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

__all__ = [
    "AgregarRespuestasDep",
    "AutorizarCierreDep",
    "CapturarAvanceDep",
    "CrearEvaluacionDep",
    "EnviarEstimacionDep",
    "GenerarEstimacionDep",
    "RechazarCierreDep",
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
