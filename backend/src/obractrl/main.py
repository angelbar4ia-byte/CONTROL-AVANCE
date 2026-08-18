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
from obractrl.adapters.excel.cargadores import TipoDeCargaSinCargador
from obractrl.adapters.excel.lector import ErrorDeArchivo
from obractrl.adapters.export.pdf import MotorDePdfNoDisponible
from obractrl.adapters.repos.calendario_sql import CalendarioNoConfigurado
from obractrl.adapters.repos.cargas_sql import TablaNoRevertible
from obractrl.application.casos_uso.calcular_cpu import ConceptoNoEncontrado
from obractrl.application.casos_uso.capturar_avance import (
    ActividadBloqueada,
    ActividadNoEncontrada,
)
from obractrl.application.casos_uso.generar_obra_desde_prototipo import ObraNoEncontrada
from obractrl.application.casos_uso.gestionar_carga import (
    CargaNoEncontrada,
    CargaNoRevertible,
)
from obractrl.application.casos_uso.gestionar_cierre import SolicitudCierreNoEncontrada
from obractrl.application.casos_uso.gestionar_estimacion import EstimacionNoEncontrada
from obractrl.application.casos_uso.gestionar_evaluacion import EvaluacionNoEncontrada
from obractrl.application.casos_uso.gestionar_incidencia import IncidenciaNoEncontrada
from obractrl.application.casos_uso.gestionar_programacion import (
    ActividadNoProgramable,
    ProgramaBaseNoEncontrado,
)
from obractrl.application.casos_uso.registrar_salida_almacen import (
    MotivoAlmacenNoEncontrado,
)
from obractrl.domain.avance.reglas import ErrorDeCaptura
from obractrl.domain.cargadores.cabeceras import ErrorDeCabecera
from obractrl.domain.catalogos.apu import CicloEnExplosion, ErrorDeAPU
from obractrl.domain.catalogos.reglas import ErrorDeCatalogo
from obractrl.domain.cierres.reglas import ErrorDeCierre
from obractrl.domain.estimacion.reglas import ErrorDeEstimacion
from obractrl.domain.evaluaciones.reglas import ErrorDeEvaluacion
from obractrl.domain.expediente.reglas import ErrorDeExpediente
from obractrl.domain.incidencias.reglas import ErrorDeIncidencia
from obractrl.domain.materiales.reglas import ErrorDeMaterial
from obractrl.domain.obras.generacion import ErrorDeGeneracion
from obractrl.domain.obras.reglas import ErrorDeObra, TransicionDeObraInvalida
from obractrl.domain.programacion.cpm import CicloEnGrafoError
from obractrl.domain.programacion.reglas import ErrorDeProgramacion
from obractrl.domain.proyectos.reglas import ErrorDeProyecto
from obractrl.domain.revisiones.reglas import ErrorDeRevision
from obractrl.infrastructure.config import obtener_config
from obractrl.infrastructure.db.sesion import cerrar_engine
from obractrl.infrastructure.jobs.cola import ColaNoDisponible, TrabajoNoEncontrado
from obractrl.infrastructure.storage.r2 import AlmacenamientoNoConfigurado

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
        """Sonda de Render. Debe responder sin tocar la BD.

        Incluye cómo quedó configurada la verificación del JWT. Sin esto, un
        despliegue mal configurado solo se manifiesta como 401 en todas las
        rutas y no hay forma de distinguir "la variable no llegó" de "el
        token es malo" —y la Shell de Render es de pago.

        No expone secretos: `jwks_url` es un endpoint público del proveedor
        y `auth_modo` solo dice qué camino se tomó.
        """
        jwks = cfg.jwks_url_efectiva
        return {
            "estatus": "ok",
            "version": __version__,
            "entorno": cfg.entorno,
            "auth_modo": "jwks" if jwks else "secreto_compartido",
            "jwks_url": jwks or "(sin configurar: falta SUPABASE_URL)",
            # Verificar ES256 exige `cryptography`, que entra por el extra
            # `pyjwt[crypto]`. Si el build lo instaló sin el extra, PyJWT
            # rechaza el algoritmo y la respuesta es un 401 idéntico al de un
            # token realmente inválido. Sin esta sonda no se distinguen.
            "es256_disponible": _hay_es256(),
            "jwks_alcanzable": _jwks_alcanzable(jwks),
        }

    return app


def _hay_es256() -> str:
    """¿PyJWT puede verificar ES256 en este entorno? (§12.4)"""
    try:
        import jwt.algorithms as _alg

        return "si" if "ES256" in _alg.get_default_algorithms() else "no"
    except Exception as exc:  # noqa: BLE001 — es una sonda, no una ruta crítica
        return f"error: {type(exc).__name__}"


def _jwks_alcanzable(url: str) -> str:
    """¿El proceso alcanza el JWKS del proveedor? (§12.4)

    Un despliegue sin salida a Internet, o con la URL mal derivada, da el
    mismo 401 que un token inválido. Devuelve la clase del fallo, nunca el
    contenido: el JWKS es público, pero el detalle del error no aporta al
    cliente y sí describe la infraestructura.
    """
    if not url:
        return "n/a"
    try:
        import urllib.request

        with urllib.request.urlopen(url, timeout=5) as r:  # noqa: S310 — URL propia
            return "si" if r.status == 200 else f"http {r.status}"
    except Exception as exc:  # noqa: BLE001 — es una sonda, no una ruta crítica
        return f"error: {type(exc).__name__}"


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

    @app.exception_handler(ErrorDeProgramacion)
    async def _programacion(
        request: Request, exc: ErrorDeProgramacion
    ) -> JSONResponse:
        # 422 como `ErrorDeCaptura`: es una invariante del cronograma
        # (duración no positiva, dependencia fuera de la obra, fechas
        # invertidas), no una transición de flujo (§7.5).
        return _problema(
            request,
            status=422,
            tipo="regla-de-programacion",
            titulo="Programación inválida",
            detalle=str(exc),
        )

    @app.exception_handler(ProgramaBaseNoEncontrado)
    async def _programa_base_no_encontrado(
        request: Request, exc: ProgramaBaseNoEncontrado
    ) -> JSONResponse:
        # RLS hace indistinguible "no existe" de "no lo puedes ver" (§12.4).
        return _problema(
            request,
            status=404,
            tipo="programa-base-no-encontrado",
            titulo="Programa base no encontrado",
            detalle=str(exc),
        )

    @app.exception_handler(ActividadNoProgramable)
    async def _actividad_no_programable(
        request: Request, exc: ActividadNoProgramable
    ) -> JSONResponse:
        # Mismo 404 que `ActividadNoEncontrada`: para el cliente son
        # indistinguibles a propósito, aunque sean de contextos distintos
        # (§11.1, §12.4).
        return _problema(
            request,
            status=404,
            tipo="actividad-no-encontrada",
            titulo="Actividad no encontrada",
            detalle=str(exc),
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

    @app.exception_handler(ErrorDeMaterial)
    async def _material(request: Request, exc: ErrorDeMaterial) -> JSONResponse:
        # Mismo tratamiento que ErrorDeCierre (409): el signo de la cantidad
        # no coincide con el del motivo (§10.5).
        return _problema(
            request,
            status=409,
            tipo="regla-de-material",
            titulo="Movimiento de almacén inválido",
            detalle=str(exc),
        )

    @app.exception_handler(MotivoAlmacenNoEncontrado)
    async def _motivo_no_encontrado(
        request: Request, exc: MotivoAlmacenNoEncontrado
    ) -> JSONResponse:
        # RLS hace indistinguible "no existe" de "no la puedes ver" a
        # propósito (§12.4), igual que ActividadNoEncontrada.
        return _problema(
            request,
            status=404,
            tipo="motivo-almacen-no-encontrado",
            titulo="Motivo de almacén no encontrado",
            detalle=str(exc),
        )

    @app.exception_handler(ErrorDeIncidencia)
    async def _incidencia(request: Request, exc: ErrorDeIncidencia) -> JSONResponse:
        return _problema(
            request,
            status=409,
            tipo="flujo-de-incidencia",
            titulo="Transición de incidencia no permitida",
            detalle=str(exc),
        )

    @app.exception_handler(IncidenciaNoEncontrada)
    async def _incidencia_no_encontrada(
        request: Request, exc: IncidenciaNoEncontrada
    ) -> JSONResponse:
        # Mismo tratamiento que ActividadNoEncontrada/SolicitudCierreNoEncontrada:
        # RLS hace indistinguible "no existe" de "no la puedes ver" (§12.4).
        return _problema(
            request,
            status=404,
            tipo="incidencia-no-encontrada",
            titulo="Incidencia no encontrada",
            detalle=str(exc),
        )

    @app.exception_handler(ErrorDeProyecto)
    async def _proyecto(request: Request, exc: ErrorDeProyecto) -> JSONResponse:
        # 422 como `ErrorDeCaptura`: es una invariante de datos de alta
        # (clave vacía, fechas invertidas…), no una transición de flujo.
        return _problema(
            request,
            status=422,
            tipo="regla-de-proyecto",
            titulo="Datos de proyecto inválidos",
            detalle=str(exc),
        )

    @app.exception_handler(ErrorDeObra)
    async def _obra(request: Request, exc: ErrorDeObra) -> JSONResponse:
        return _problema(
            request,
            status=422,
            tipo="regla-de-obra",
            titulo="Datos de obra inválidos",
            detalle=str(exc),
        )

    # Starlette resuelve el manejador recorriendo el MRO de la excepción, así
    # que estas dos subclases de `ErrorDeObra` ganan sobre el 422 de arriba:
    # no son datos malos del usuario sino una precondición de negocio (§11.3
    # A y D), y eso es un 409 —mismo criterio que `ErrorDeEstimacion`.
    @app.exception_handler(TransicionDeObraInvalida)
    async def _transicion_obra(
        request: Request, exc: TransicionDeObraInvalida
    ) -> JSONResponse:
        return _problema(
            request,
            status=409,
            tipo="flujo-de-obra",
            titulo="Operación no permitida sobre la obra",
            detalle=str(exc),
        )

    @app.exception_handler(ErrorDeGeneracion)
    async def _generacion_obra(
        request: Request, exc: ErrorDeGeneracion
    ) -> JSONResponse:
        return _problema(
            request,
            status=409,
            tipo="generacion-de-obra",
            titulo="La obra no se puede generar desde su prototipo",
            detalle=str(exc),
        )

    @app.exception_handler(ObraNoEncontrada)
    async def _obra_no_encontrada(
        request: Request, exc: ObraNoEncontrada
    ) -> JSONResponse:
        # Mismo tratamiento que ActividadNoEncontrada: RLS hace indistinguible
        # "no existe" de "no la puedes ver" a propósito (§12.4).
        return _problema(
            request,
            status=404,
            tipo="obra-no-encontrada",
            titulo="Obra no encontrada",
            detalle=str(exc),
        )

    @app.exception_handler(ErrorDeCatalogo)
    async def _catalogo(request: Request, exc: ErrorDeCatalogo) -> JSONResponse:
        # 422 como `ErrorDeProyecto`: es una invariante de datos de alta
        # (clave vacía, tipo fuera del §8.2, factor no positivo…), no una
        # transición de flujo.
        return _problema(
            request,
            status=422,
            tipo="regla-de-catalogo",
            titulo="Datos de catálogo inválidos",
            detalle=str(exc),
        )

    @app.exception_handler(ErrorDeAPU)
    async def _apu(request: Request, exc: ErrorDeAPU) -> JSONResponse:
        return _problema(
            request,
            status=422,
            tipo="regla-de-apu",
            titulo="Composición de APU inválida",
            detalle=str(exc),
        )

    # Starlette resuelve el manejador recorriendo el MRO, así que esta
    # subclase gana sobre el `ErrorDeAPU` de arriba: el ciclo se reporta con
    # el camino involucrado, igual que `CicloEnGrafoError` en el CPM.
    @app.exception_handler(CicloEnExplosion)
    async def _ciclo_explosion(
        request: Request, exc: CicloEnExplosion
    ) -> JSONResponse:
        return _problema(
            request,
            status=422,
            tipo="explosion-ciclica",
            titulo="La explosión del concepto tiene un ciclo",
            detalle=str(exc),
            conceptos=exc.camino,
        )

    @app.exception_handler(ConceptoNoEncontrado)
    async def _concepto_no_encontrado(
        request: Request, exc: ConceptoNoEncontrado
    ) -> JSONResponse:
        # Mismo tratamiento que ActividadNoEncontrada: RLS hace indistinguible
        # "no existe" de "no lo puedes ver" a propósito (§12.4).
        return _problema(
            request,
            status=404,
            tipo="concepto-no-encontrado",
            titulo="Concepto no encontrado",
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

    @app.exception_handler(ErrorDeRevision)
    async def _revision(request: Request, exc: ErrorDeRevision) -> JSONResponse:
        # 422 como `ErrorDeCaptura`: es una invariante de la captura (rol que
        # no registra, calidad fuera de escala), no una transición de flujo —
        # la revisión física no tiene ciclo de vida (§7.8).
        return _problema(
            request,
            status=422,
            tipo="regla-de-revision",
            titulo="Revisión física inválida",
            detalle=str(exc),
        )

    # --- Cargas de datos (§9.3, §10.6, §10.8) ---------------------------

    @app.exception_handler(ErrorDeArchivo)
    async def _archivo_de_carga(request: Request, exc: ErrorDeArchivo) -> JSONResponse:
        # 422 y no 400: la petición está bien formada, el **contenido** no
        # cumple el contrato del §10.6 —mismo criterio que `ErrorDeCaptura`.
        return _problema(
            request,
            status=422,
            tipo="archivo-de-carga-invalido",
            titulo="El archivo de carga no se puede leer",
            detalle=str(exc),
        )

    @app.exception_handler(ErrorDeCabecera)
    async def _cabecera_de_carga(
        request: Request, exc: ErrorDeCabecera
    ) -> JSONResponse:
        return _problema(
            request,
            status=422,
            tipo="cabeceras-de-carga-invalidas",
            titulo="El archivo no trae las cabeceras del contrato",
            detalle=str(exc),
        )

    @app.exception_handler(TipoDeCargaSinCargador)
    async def _tipo_sin_cargador(
        request: Request, exc: TipoDeCargaSinCargador
    ) -> JSONResponse:
        # 501 y no 404: el tipo existe en el §8.2, lo que falta es el
        # cargador de este lado. El cliente no tiene nada que corregir.
        return _problema(
            request,
            status=501,
            tipo="cargador-no-implementado",
            titulo="Ese tipo de carga todavía no tiene cargador",
            detalle=str(exc),
        )

    @app.exception_handler(CargaNoEncontrada)
    async def _carga_no_encontrada(
        request: Request, exc: CargaNoEncontrada
    ) -> JSONResponse:
        # Mismo tratamiento que ActividadNoEncontrada: RLS hace indistinguible
        # "no existe" de "no la puedes ver" a propósito (§12.4).
        return _problema(
            request,
            status=404,
            tipo="carga-no-encontrada",
            titulo="Carga no encontrada",
            detalle=str(exc),
        )

    @app.exception_handler(CargaNoRevertible)
    async def _carga_no_revertible(
        request: Request, exc: CargaNoRevertible
    ) -> JSONResponse:
        return _problema(
            request,
            status=409,
            tipo="carga-no-revertible",
            titulo="La carga no se puede revertir",
            detalle=str(exc),
        )

    @app.exception_handler(TablaNoRevertible)
    async def _tabla_no_revertible(
        request: Request, exc: TablaNoRevertible
    ) -> JSONResponse:
        # 500: el snapshot lo escribió este mismo backend, así que si menciona
        # una tabla que no sabe deshacer, el defecto es nuestro (§10.8).
        return _problema(
            request,
            status=500,
            tipo="snapshot-inconsistente",
            titulo="El lote no se puede deshacer completo",
            detalle=str(exc),
        )

    # --- Expediente y reportes (§7.9, §11.2) ----------------------------

    @app.exception_handler(ErrorDeExpediente)
    async def _expediente(request: Request, exc: ErrorDeExpediente) -> JSONResponse:
        # 422 como `ErrorDeRevision`: es una invariante del alta (rol que no
        # sube, nombre o clave vacíos), no una transición de flujo — el §7.9
        # no le da ciclo de vida al documento.
        return _problema(
            request,
            status=422,
            tipo="regla-de-expediente",
            titulo="Documento de expediente inválido",
            detalle=str(exc),
        )

    @app.exception_handler(TrabajoNoEncontrado)
    async def _trabajo_no_encontrado(
        request: Request, exc: TrabajoNoEncontrado
    ) -> JSONResponse:
        # 404: el resultado de un reporte vive un tiempo acotado en Redis
        # (`keep_result`, `obractrl/trabajador.py`). Pasado eso el reporte deja
        # de existir y hay que volver a pedirlo.
        return _problema(
            request,
            status=404,
            tipo="reporte-no-encontrado",
            titulo="Reporte no encontrado",
            detalle=str(exc),
        )

    @app.exception_handler(ColaNoDisponible)
    async def _cola_no_disponible(
        request: Request, exc: ColaNoDisponible
    ) -> JSONResponse:
        # 503 y no 500, mismo criterio que `AlmacenamientoNoConfigurado`: la
        # petición es válida y volverá a serlo en cuanto Redis responda
        # (§12.8). El detalle nombra la variable que falta, nunca su valor —el
        # DSN de Redis puede traer contraseña.
        return _problema(
            request,
            status=503,
            tipo="cola-no-disponible",
            titulo="Cola de trabajos no disponible",
            detalle=str(exc),
        )

    @app.exception_handler(MotorDePdfNoDisponible)
    async def _motor_pdf_no_disponible(
        request: Request, exc: MotorDePdfNoDisponible
    ) -> JSONResponse:
        # 503 igual: faltan las bibliotecas nativas de WeasyPrint en el
        # despliegue (§12.8). El resto de la API sigue sirviendo.
        return _problema(
            request,
            status=503,
            tipo="motor-de-pdf-no-disponible",
            titulo="Generación de PDF no disponible",
            detalle=str(exc),
        )

    @app.exception_handler(AlmacenamientoNoConfigurado)
    async def _almacenamiento_no_configurado(
        request: Request, exc: AlmacenamientoNoConfigurado
    ) -> JSONResponse:
        # 503 y no 500: la petición es válida y volverá a serlo en cuanto el
        # despliegue tenga sus variables de R2 (§12.8). El detalle nombra las
        # variables que faltan —nunca su valor—, igual que `/health` reporta
        # el modo de auth sin exponer secretos.
        return _problema(
            request,
            status=503,
            tipo="almacenamiento-no-configurado",
            titulo="Almacenamiento de evidencias no disponible",
            detalle=str(exc),
        )


app = crear_app()
