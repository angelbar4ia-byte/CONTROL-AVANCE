"""Punto de entrada de la API.

Spec §11.2 (convenciones) · §12.2 (stack) · §12.8 (CORS y entornos).

Monolito modular: cada módulo del §11.1 registra su router aquí, y toda
llamada entre módulos pasa por su fachada (§11.1). Este archivo solo ensambla;
no contiene lógica de negocio (§12.11).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from obractrl import __version__
from obractrl.adapters.api.v1 import api_v1
from obractrl.adapters.repos.calendario_sql import CalendarioNoConfigurado
from obractrl.application.casos_uso.capturar_avance import (
    ActividadBloqueada,
    ActividadNoEncontrada,
)
from obractrl.application.casos_uso.gestionar_cierre import SolicitudCierreNoEncontrada
from obractrl.application.casos_uso.gestionar_estimacion import EstimacionNoEncontrada
from obractrl.application.casos_uso.gestionar_evaluacion import EvaluacionNoEncontrada
from obractrl.domain.avance.reglas import ErrorDeCaptura
from obractrl.domain.cierres.reglas import ErrorDeCierre
from obractrl.domain.estimacion.reglas import ErrorDeEstimacion
from obractrl.domain.evaluaciones.reglas import ErrorDeEvaluacion
from obractrl.domain.programacion.cpm import CicloEnGrafoError
from obractrl.infrastructure.config import obtener_config
from obractrl.infrastructure.db.sesion import cerrar_engine

BASE_API = "/api/v1"


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
    yield
    await cerrar_engine()


def crear_app() -> FastAPI:
    cfg = obtener_config()

    app = FastAPI(
        title="ObraCtrl API",
        description=(
            "Control de avance de obra para vivienda en serie. "
            "REST + OpenAPI; los hooks de TanStack Query se autogeneran con "
            "Orval desde este esquema (§12.2)."
        ),
        version=__version__,
        lifespan=ciclo_de_vida,
        docs_url="/docs" if not cfg.es_produccion else None,
        redoc_url=None,
        openapi_url=f"{BASE_API}/openapi.json",
    )

    # El backend en Render permite el origen de Vercel por entorno (§12.8)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origenes,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _registrar_manejadores_de_error(app)
    app.include_router(api_v1, prefix=BASE_API)

    @app.get("/health", tags=["salud"], summary="Health check")
    async def health() -> dict[str, str]:
        """Sonda de Render. Debe responder sin tocar la BD."""
        return {"estatus": "ok", "version": __version__, "entorno": cfg.entorno}

    return app


def _registrar_manejadores_de_error(app: FastAPI) -> None:
    """Errores de dominio → problem+json, RFC 7807 (§11.2).

    Traducir aquí es lo que mantiene el dominio libre de HTTP: las reglas
    lanzan excepciones de negocio y el borde decide el código de estado.
    """

    def _problema(
        request: Request, *, status: int, tipo: str, titulo: str, detalle: str, **extra
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            media_type="application/problem+json",
            content={
                "type": f"https://obractrl.mx/errores/{tipo}",
                "title": titulo,
                "status": status,
                "detail": detalle,
                "instance": str(request.url.path),
                **extra,
            },
        )

    @app.exception_handler(ErrorDeCaptura)
    async def _captura(request: Request, exc: ErrorDeCaptura) -> JSONResponse:
        return _problema(
            request,
            status=422,
            tipo="regla-de-captura",
            titulo="Captura de avance inválida",
            detalle=str(exc),
            campo=exc.campo,
        )

    @app.exception_handler(ErrorDeCierre)
    async def _cierre(request: Request, exc: ErrorDeCierre) -> JSONResponse:
        return _problema(
            request,
            status=409,
            tipo="flujo-de-cierre",
            titulo="Transición de cierre no permitida",
            detalle=str(exc),
        )

    @app.exception_handler(CicloEnGrafoError)
    async def _ciclo(request: Request, exc: CicloEnGrafoError) -> JSONResponse:
        return _problema(
            request,
            status=422,
            tipo="cronograma-ciclico",
            titulo="El cronograma tiene dependencias circulares",
            detalle=str(exc),
            actividades=exc.involucradas,
        )

    @app.exception_handler(ActividadNoEncontrada)
    async def _actividad_no_encontrada(
        request: Request, exc: ActividadNoEncontrada
    ) -> JSONResponse:
        # RLS hace indistinguible "no existe" de "no la puedes ver" a
        # propósito (§12.4): ambos casos dan 404, nunca un 403 que revele
        # que el recurso existe en otra organización o fuera de tu alcance.
        return _problema(
            request,
            status=404,
            tipo="actividad-no-encontrada",
            titulo="Actividad no encontrada",
            detalle=str(exc),
        )

    @app.exception_handler(ActividadBloqueada)
    async def _actividad_bloqueada(
        request: Request, exc: ActividadBloqueada
    ) -> JSONResponse:
        return _problema(
            request,
            status=409,
            tipo="actividad-bloqueada",
            titulo="Actividad bloqueada",
            detalle=str(exc),
        )

    @app.exception_handler(SolicitudCierreNoEncontrada)
    async def _cierre_no_encontrado(
        request: Request, exc: SolicitudCierreNoEncontrada
    ) -> JSONResponse:
        # Mismo tratamiento que ActividadNoEncontrada: RLS hace indistinguible
        # "no existe" de "no la puedes ver" a propósito (§12.4).
        return _problema(
            request,
            status=404,
            tipo="cierre-no-encontrado",
            titulo="Solicitud de cierre no encontrada",
            detalle=str(exc),
        )

    @app.exception_handler(ErrorDeEstimacion)
    async def _estimacion(request: Request, exc: ErrorDeEstimacion) -> JSONResponse:
        # Mismo código que ErrorDeCierre (409): cubre tanto "no hay nada que
        # estimar" (precondición de negocio) como la transición de flujo
        # inválida — igual que allá, un solo tipo de error de dominio (§6).
        return _problema(
            request,
            status=409,
            tipo="regla-de-estimacion",
            titulo="Estimación inválida",
            detalle=str(exc),
        )

    @app.exception_handler(EstimacionNoEncontrada)
    async def _estimacion_no_encontrada(
        request: Request, exc: EstimacionNoEncontrada
    ) -> JSONResponse:
        return _problema(
            request,
            status=404,
            tipo="estimacion-no-encontrada",
            titulo="Estimación no encontrada",
            detalle=str(exc),
        )

    @app.exception_handler(CalendarioNoConfigurado)
    async def _calendario_no_configurado(
        request: Request, exc: CalendarioNoConfigurado
    ) -> JSONResponse:
        return _problema(
            request,
            status=409,
            tipo="calendario-no-configurado",
            titulo="Ancla de semana no configurada",
            detalle=str(exc),
        )

    @app.exception_handler(ErrorDeEvaluacion)
    async def _evaluacion(request: Request, exc: ErrorDeEvaluacion) -> JSONResponse:
        return _problema(
            request,
            status=409,
            tipo="regla-de-evaluacion",
            titulo="Evaluación inválida",
            detalle=str(exc),
        )

    @app.exception_handler(EvaluacionNoEncontrada)
    async def _evaluacion_no_encontrada(
        request: Request, exc: EvaluacionNoEncontrada
    ) -> JSONResponse:
        # Mismo tratamiento que SolicitudCierreNoEncontrada: RLS hace
        # indistinguible "no existe" de "no la puedes ver" a propósito (§12.4).
        return _problema(
            request,
            status=404,
            tipo="evaluacion-no-encontrada",
            titulo="Evaluación no encontrada",
            detalle=str(exc),
        )


app = crear_app()
