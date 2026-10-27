"""Punto de entrada de la API.

Spec §11.2 (convenciones) · §12.2 (stack) · §12.8 (CORS y entornos).

Monolito modular: cada módulo del §11.1 registra su router aquí, y toda
llamada entre módulos pasa por su fachada (§11.1). Este archivo solo ensambla;
no contiene lógica de negocio (§12.11).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as ExcepcionHTTP

from obractrl import __version__
from obractrl.adapters.api.idempotencia import (
    ClaveDeIdempotenciaInvalida,
    ClaveReusada,
    PeticionYaProcesada,
)
from obractrl.adapters.api.middleware import (
    MiddlewareDeErroresConCORS,
    MiddlewareDeIdDePeticion,
    MiddlewareDeVersionDeCliente,
)
from obractrl.adapters.api.problemas import problema_no_previsto
from obractrl.adapters.api.v1 import api_v1
from obractrl.adapters.excel.cargadores import TipoDeCargaSinCargador
from obractrl.adapters.excel.lector import ErrorDeArchivo
from obractrl.adapters.export.catalogo import TipoDeReporteDesconocido
from obractrl.adapters.export.pdf import MotorDePdfNoDisponible
from obractrl.adapters.repos.calendario_sql import CalendarioNoConfigurado
from obractrl.adapters.repos.cargas_sql import ReversaEnConflicto, TablaNoRevertible
from obractrl.adapters.repos.procesos_sql import ProcesoNoEncontrado
from obractrl.application.casos_uso.calcular_cpu import ConceptoNoEncontrado
from obractrl.application.casos_uso.capturar_avance import (
    ActividadBloqueada,
    ActividadNoEncontrada,
    FrenteCerrado,
)
from obractrl.application.casos_uso.comprobar_excedente import ActividadSinComprobacion
from obractrl.application.casos_uso.confirmar_avance import (
    ActividadSinConfirmacion,
    PeriodoBloqueadoParaConfirmar,
)
from obractrl.application.casos_uso.consultar_insumos_programados import (
    CalendarioSinGenerar,
    PrototipoSinPrograma,
)
from obractrl.application.casos_uso.crear_obra_desde_catalogo_base import (
    ErrorDeCatalogoBase,
)
from obractrl.application.casos_uso.cuantificar import (
    EnlaceNoEncontrado,
    GobiernoDeCuantificacionInvalido,
    PlanoNoEncontrado,
    TrazoNoEncontrado,
)
from obractrl.application.casos_uso.generar_obra_desde_prototipo import (
    ObraNoEncontrada,
    ObraYaEjecutada,
)
from obractrl.application.casos_uso.gestionar_carga import (
    CargaConDependientes,
    CargaNoEliminable,
    CargaNoEncontrada,
    CargaNoRevertible,
)
from obractrl.application.casos_uso.gestionar_cierre import SolicitudCierreNoEncontrada
from obractrl.application.casos_uso.gestionar_cierre_de_frente import (
    CierreDeFrenteNoEncontrado,
    FrenteNoEncontrado,
)
from obractrl.application.casos_uso.gestionar_cierre_de_obra import (
    CierreDeObraNoEncontrado,
)
from obractrl.application.casos_uso.gestionar_desviaciones import DesviacionNoEncontrada
from obractrl.application.casos_uso.gestionar_ensamble import (
    ClaveDeEnsambleEnUso,
    EnsambleNoCoincideConInstancia,
    EnsambleNoEncontrado,
    InstanciaNoEncontrada,
    SubEnsambleNoEncontrado,
)
from obractrl.application.casos_uso.gestionar_estimacion import EstimacionNoEncontrada
from obractrl.application.casos_uso.gestionar_evaluacion import EvaluacionNoEncontrada
from obractrl.application.casos_uso.gestionar_incidencia import IncidenciaNoEncontrada
from obractrl.application.casos_uso.gestionar_partes import (
    ErrorDeParte,
    ErrorDePlantas,
    ParteNoEncontrada,
    ParteNoPermitida,
    PrototipoNoEncontrado,
)
from obractrl.application.casos_uso.gestionar_programacion import (
    ActividadNoProgramable,
    ConflictoNoResuelto,
    NodoNoProgramable,
    ProgramaBaseNoEncontrado,
)
from obractrl.application.casos_uso.gestionar_reprogramacion import (
    ReprogramacionNoEncontrada,
)
from obractrl.application.casos_uso.gestionar_usuarios import (
    CorreoYaRegistrado,
    UsuarioNoEncontrado,
)
from obractrl.application.casos_uso.registrar_salida_almacen import (
    MotivoAlmacenNoEncontrado,
)
from obractrl.application.puertos.auth import ErrorDelProveedorDeAuth
from obractrl.application.puertos.repositorios import (
    RegistroNoEncontrado,
    VersionVigenteNoEliminable,
)
from obractrl.domain.avance.comprobacion import ErrorDeComprobacion, SinExcedente
from obractrl.domain.avance.confirmacion import ErrorDeConfirmacion
from obractrl.domain.avance.reglas import ErrorDeCaptura
from obractrl.domain.cargadores.cabeceras import ErrorDeCabecera
from obractrl.domain.catalogos.apu import CicloEnExplosion, ErrorDeAPU
from obractrl.domain.catalogos.reglas import ErrorDeCatalogo
from obractrl.domain.cierres.obra import ErrorDeCierreDeObra
from obractrl.domain.cierres.reglas import ErrorDeCierre
from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion
from obractrl.domain.desviacion.desviacion import ErrorDeDesviacion
from obractrl.domain.estimacion.reglas import ErrorDeEstimacion
from obractrl.domain.evaluaciones.reglas import ErrorDeEvaluacion
from obractrl.domain.expediente.reglas import ErrorDeExpediente
from obractrl.domain.identidad.reglas import ErrorDeIdentidad
from obractrl.domain.incidencias.reglas import ErrorDeIncidencia
from obractrl.domain.materiales.reglas import ErrorDeMaterial
from obractrl.domain.obras.generacion import ErrorDeGeneracion
from obractrl.domain.obras.precio_armado import ErrorDePrecioArmado
from obractrl.domain.obras.reglas import ErrorDeObra, TransicionDeObraInvalida
from obractrl.domain.partes.alertas import ErrorDeUmbrales
from obractrl.domain.partes.modificacion import ErrorDeModificacion
from obractrl.domain.programacion.cpm import CicloEnGrafoError
from obractrl.domain.programacion.reglas import (
    EdicionDeProgramaNoPermitida,
    ErrorDeProgramacion,
)
from obractrl.domain.programacion.reprogramacion import (
    ErrorDeReprogramacion,
    FechasDeLoAsignado,
)
from obractrl.domain.proyectos.reglas import ErrorDeProyecto
from obractrl.domain.revisiones.reglas import ErrorDeRevision
from obractrl.infrastructure.config import obtener_config
from obractrl.infrastructure.db.sesion import cerrar_engine, obtener_sessionmaker
from obractrl.infrastructure.jobs.cola import (
    ColaDeTrabajos,
    ColaNoDisponible,
    TrabajoNoEncontrado,
)
from obractrl.infrastructure.observabilidad import (
    configurar_logging,
    id_de_peticion,
    iniciar_sentry,
)
from obractrl.infrastructure.storage.r2 import AlmacenamientoNoConfigurado
from obractrl.infrastructure.tiempo_real.canal import canal_de_avisos

BASE_API = "/api/v1"

_log = logging.getLogger(__name__)

_TIMEOUT_SONDA = 3
"""Segundos por dependencia. Corto: la sonda se consulta cuando algo ya va
mal, y ahí una respuesta lenta es tan inútil como ninguna."""


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
    yield
    # El canal de avisos primero: su puente con Redis es una tarea de fondo, y
    # cerrarla antes de que el proceso muera hace que las conexiones SSE
    # abiertas terminen limpio y el navegador reconecte contra la instancia
    # nueva en vez de quedarse colgado del socket viejo (§12.12).
    await canal_de_avisos.cerrar()
    await cerrar_engine()


def crear_app() -> FastAPI:
    cfg = obtener_config()

    # Antes de construir nada: si algo del ensamblado falla, que salga con el
    # formato de la casa y no con el default de Python (§11.7).
    configurar_logging(cfg)
    iniciar_sentry(cfg)

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

    # Antes que CORS y por eso **más adentro**: `add_middleware` inserta al
    # principio y la pila se pliega de fuera hacia dentro. Un 500 atrapado aquí
    # sale como respuesta y sube por CORS, que le pone sus cabeceras; atrapado
    # por `ServerErrorMiddleware` —que va por fuera de todo— saldría sin ellas
    # y el navegador lo reportaría como un problema de CORS (§12.8).
    app.add_middleware(MiddlewareDeErroresConCORS)

    # El backend en Render permite el origen de Vercel por entorno (§12.8)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origenes,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # Sin esto el navegador **no deja leer** el id de una respuesta de
        # error, que es justo cuando el front lo necesita para reportarla.
        expose_headers=["X-Request-Id"],
    )

    # El orden de `add_middleware` es de adentro hacia afuera: el último que
    # se agrega es el primero que ve la petición. La versión de cliente va
    # antes que el id porque un 426 también debe salir con su `X-Request-Id`
    # —es justo el que se reporta cuando alguien dice "no me deja entrar"—
    # (§12.12, §11.7).
    app.add_middleware(MiddlewareDeVersionDeCliente)

    # Se agrega al final para que quede por fuera de CORS: así hasta una
    # respuesta rechazada por origen sale con su id (§11.7).
    app.add_middleware(MiddlewareDeIdDePeticion)

    _registrar_manejadores_de_error(app)
    app.include_router(api_v1, prefix=BASE_API)

    @app.get("/health", tags=["salud"], summary="Health check")
    async def health() -> dict[str, str]:
        """Sonda de Render. Debe responder sin tocar la BD.

        Incluye cómo quedó configurada la verificación del JWT. Sin esto, un
        despliegue mal configurado solo se manifiesta como 401 en todas las
        rutas y no hay forma de distinguir "la variable no llegó" de "el
        token es malo" —y la Shell de Render es de pago.

        No expone secretos: `jwks_url` es un endpoint público del proveedor,
        `auth_modo` solo dice qué camino se tomó y `cors_origenes` es la lista
        de sitios que ya pueden llamar a esta API — quien la lee desde fuera no
        gana nada que no supiera al abrir la web.
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
            # Los orígenes que el navegador tiene permitido usar (§12.8). No
            # es secreto —son URLs públicas— y es el dato que convierte un
            # "Disallowed CORS origin" en un vistazo: desde el navegador, un
            # origen no permitido se ve como *falta la cabecera*, sin decir
            # cuál es la lista contra la que se comparó. Mismo criterio que
            # `jwks_url`: sin esto, un despliegue mal configurado solo se
            # manifiesta como un error del lado del cliente.
            "cors_origenes": ", ".join(cfg.cors_origenes) or "(ninguno)",
        }

    @app.get(
        "/health/dependencias",
        tags=["salud"],
        summary="Estado de la base, la cola, los jobs, el disco y el respaldo",
    )
    async def health_dependencias() -> dict[str, str]:
        """Sonda **de readiness**: sí toca la base y sí toca Redis (§11.7).

        Va aparte de `/health` a propósito. `/health` es la sonda de liveness
        de Render y responde sin tocar nada: si la base se cae, Render no
        debe reiniciar un proceso que está perfectamente vivo —eso solo
        agrega un arranque en frío a un incidente que ya existe—. Esta otra
        es la que se mira cuando algo va mal, y para eso tiene que consultar.

        **Nunca responde 5xx.** Devuelve 200 con el estado de cada
        dependencia; una sonda que se cae junto con lo que vigila no
        diagnostica nada. El estado agregado dice `degradado` para que un
        monitor pueda alertar sobre un solo campo.

        No expone cadenas de conexión: solo `ok` o la clase del fallo (§12.4).

        **Los valores son frases, no estructuras.** Quien abre esta ruta es una
        persona en medio de un incidente; lo que necesita es leer "3 en cola,
        sin worker" de un vistazo. El monitor automático tiene `estatus`, que
        es el único campo con valores cerrados y el único sobre el que conviene
        alertar.
        """
        # En paralelo: son independientes, y en serie la sonda tardaría la
        # suma de los timeouts justo cuando todo está caído — que es cuando
        # alguien la está mirando.
        postgres, redis, jobs, respaldo, esquema = await asyncio.gather(
            _postgres_responde(),
            _redis_responde(),
            _jobs_responden(),
            _ultimo_respaldo(),
            _version_del_esquema(),
        )
        disco = _disco_disponible()

        # `estatus` agrega solo lo que significa "la API no puede trabajar".
        # El disco y el respaldo se reportan pero no degradan: un disco al 85 %
        # o un respaldo de anteayer son cosas que hay que atender, no
        # incidentes que justifiquen despertar a nadie — y una sonda que grita
        # por todo deja de leerse.
        sano = postgres == "ok" and redis == "ok"
        return {
            "estatus": "ok" if sano else "degradado",
            "postgres": postgres,
            "esquema": esquema,
            "cola": redis,
            "jobs": jobs,
            "disco": disco,
            "ultimo_respaldo": respaldo,
        }

    return app


async def _postgres_responde() -> str:
    """`select 1` contra el pool real. Devuelve `ok` o la clase del fallo."""
    try:
        async with asyncio.timeout(_TIMEOUT_SONDA):
            sesion_maker = obtener_sessionmaker()
            async with sesion_maker() as sesion:
                await sesion.execute(text("select 1"))
        return "ok"
    except Exception as exc:  # noqa: BLE001 — es una sonda, no una ruta crítica
        # La clase basta para saber si es red, credenciales o esquema; el
        # mensaje de asyncpg puede traer el DSN con contraseña.
        return f"error: {type(exc).__name__}"


async def _version_del_esquema() -> str:
    """Hasta qué migración llegó **esta** base (§12.12).

    Existe por un incidente concreto: la web daba 500 en `/usuarios` porque la
    base de producción estaba en la 0023 y el código consultaba
    `debe_cambiar_password`, que agrega la 0025. Desde fuera, eso se veía como
    un error de CORS en el navegador —el 500 salía sin cabeceras— y desde la
    sonda como `ultimo_respaldo: error: ProgrammingError`, que es una pista de
    tercera mano.

    Aquí se responde de frente: la última versión aplicada y cuántas van. Quien
    opera lo compara con `ls database/migrations/*.sql | tail -1` y sabe en un
    vistazo si le falta migrar.

    No compara contra un número esperado en el código a propósito: ese número
    tendría que actualizarse a mano en cada migración y el día que alguien lo
    olvide, la sonda mentiría — que es peor que no tenerla.
    """
    try:
        async with asyncio.timeout(_TIMEOUT_SONDA):
            sesion_maker = obtener_sessionmaker()
            async with sesion_maker() as sesion:
                if not (
                    await sesion.execute(
                        text("select to_regclass('app.schema_migrations')")
                    )
                ).scalar():
                    # Base sin bitácora: o es de antes del runner, o nunca se
                    # migró. Las dos se arreglan desde `database/scripts/`.
                    return "sin bitácora de migraciones"

                fila = (
                    await sesion.execute(
                        text(
                            "select max(version) as ultima, count(*) as total "
                            "from app.schema_migrations"
                        )
                    )
                ).first()

        if fila is None or fila.ultima is None:
            return "sin migraciones aplicadas"
        return f"{fila.ultima} ({fila.total} aplicadas)"
    except Exception as exc:  # noqa: BLE001 — es una sonda, no una ruta crítica
        return f"error: {type(exc).__name__}"


async def _redis_responde() -> str:
    try:
        async with asyncio.timeout(_TIMEOUT_SONDA):
            return "ok" if await ColaDeTrabajos().disponible() else "no responde"
    except Exception as exc:  # noqa: BLE001 — es una sonda, no una ruta crítica
        return f"error: {type(exc).__name__}"


async def _jobs_responden() -> str:
    """Cuántos trabajos esperan y si el worker sigue vivo (§11.7).

    El §11.7 pide el estado de los jobs, no solo el de Redis, y son preguntas
    distintas: Redis puede responder perfectamente mientras el worker está
    caído y la cola crece sin que nadie la atienda. Ese es justo el fallo que
    no produce ningún error visible en la API.
    """
    try:
        async with asyncio.timeout(_TIMEOUT_SONDA):
            en_cola, latido = await ColaDeTrabajos().estado()
    except Exception as exc:  # noqa: BLE001 — es una sonda, no una ruta crítica
        return f"error: {type(exc).__name__}"
    worker = "worker latiendo" if latido else "SIN WORKER"
    return f"{en_cola} en cola · {worker}"


def _disco_disponible() -> str:
    """Espacio libre donde se arman los archivos temporales (§11.7).

    Los export de XLSX y los PDF del expediente se escriben en disco antes de
    subirse. Un disco lleno no rompe la API: rompe *un tipo de petición*, con
    un error que no se parece a "no queda espacio". Por eso la sonda lo dice
    antes.
    """
    try:
        import shutil
        import tempfile

        uso = shutil.disk_usage(tempfile.gettempdir())
    except Exception as exc:  # noqa: BLE001 — es una sonda, no una ruta crítica
        return f"error: {type(exc).__name__}"
    libre_gb = uso.free / 1024**3
    usado_pct = round(100 * uso.used / uso.total) if uso.total else 0
    return f"{libre_gb:.1f} GB libres · {usado_pct}% usado"


async def _ultimo_respaldo() -> str:
    """Cuándo se respaldó y cuándo se probó restaurar (§11.7, §12.12).

    Las dos fechas, porque son dos garantías distintas y la segunda es la que
    vale: un respaldo que nunca se restauró es una carpeta que crece. Los
    renglones los escriben `database/scripts/respaldar.sh` y
    `probar_respaldo.sh` (migración 0024).

    "sin registro" es una respuesta verdadera y accionable: significa que nadie
    ha respaldado desde esta base, no que haga mucho tiempo.
    """
    try:
        async with asyncio.timeout(_TIMEOUT_SONDA):
            sesion_maker = obtener_sessionmaker()
            async with sesion_maker() as sesion:
                filas = (
                    await sesion.execute(
                        text(
                            "select tipo, max(terminado_en) as cuando "
                            "  from app.respaldo "
                            " where ok "
                            " group by tipo"
                        )
                    )
                ).all()
    except Exception as exc:  # noqa: BLE001 — es una sonda, no una ruta crítica
        return f"error: {type(exc).__name__}"

    cuando = {fila.tipo: fila.cuando for fila in filas}
    return (
        f"respaldo: {_hace_cuanto(cuando.get('respaldo'))}"
        f" · restauración probada: "
        f"{_hace_cuanto(cuando.get('restauracion_probada'))}"
    )


def _hace_cuanto(momento: datetime | None) -> str:
    if momento is None:
        return "sin registro"
    horas = (datetime.now(UTC) - momento).total_seconds() / 3600
    if horas < 1:
        return "hace menos de 1 h"
    if horas < 48:
        return f"hace {horas:.0f} h"
    return f"hace {horas / 24:.0f} d"


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


_TIPO_POR_ESTADO: dict[int, str] = {
    400: "peticion-invalida",
    401: "no-autenticado",
    403: "acceso-denegado",
    404: "no-encontrado",
    405: "metodo-no-permitido",
    409: "conflicto",
    413: "archivo-demasiado-grande",
    415: "medio-no-soportado",
    422: "peticion-invalida",
    429: "demasiadas-peticiones",
    503: "servicio-no-disponible",
}
"""Slug de `type` para los errores que **no** nacen de una regla de dominio.

Los del dominio traen su propio nombre (`regla-de-cierre`,
`estimacion-no-encontrada`…) porque el cliente puede ramificar sobre ellos.
Estos son de protocolo, así que el slug describe el estado y nada más — pero
existe, porque el front lee `type` en toda respuesta de error
(`frontend/src/api/cliente.ts`) y un `undefined` ahí es un caso especial de
más en el cliente.
"""


def _titulo_por_estado(status: int) -> str:
    return {
        400: "Petición inválida",
        401: "No autenticado",
        403: "Acceso denegado",
        404: "Recurso no encontrado",
        405: "Método no permitido",
        409: "Conflicto con el estado actual",
        413: "Archivo demasiado grande",
        415: "Tipo de contenido no soportado",
        422: "Petición inválida",
        429: "Demasiadas peticiones",
        503: "Servicio no disponible",
    }.get(status, "Error de la API")


def _registrar_manejadores_de_error(app: FastAPI) -> None:
    """Errores de dominio → problem+json, RFC 7807 (§11.2).

    Traducir aquí es lo que mantiene el dominio libre de HTTP: las reglas
    lanzan excepciones de negocio y el borde decide el código de estado.

    Los manejadores **genéricos** van al final del archivo: cubren lo que no
    nace de una regla —un 403 de `exigir_rol`, un 422 de Pydantic, un fallo no
    previsto— para que el §11.2 se cumpla sin excepciones. El front lee
    `problem+json` en toda respuesta de error, así que una sola que salga con
    el formato por defecto de FastAPI es un caso especial que alguien tiene
    que manejar en el cliente.
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
                # Extensión propia del problem+json (RFC 7807 §3.2 las
                # permite). Es el mismo id que va en `X-Request-Id` y en cada
                # línea de log de esta petición: es lo que convierte "me
                # falló" en algo buscable.
                "request_id": id_de_peticion(),
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

    @app.exception_handler(EdicionDeProgramaNoPermitida)
    async def _edicion_de_programa(
        request: Request, exc: EdicionDeProgramaNoPermitida
    ) -> JSONResponse:
        # 403: el rol puede editar el programa, pero no ESTO. Depende de qué campos
        # trae la petición, no solo de quién la manda (`exigir_rol` no lo ve).
        return _problema(
            request,
            status=403,
            tipo="edicion-de-programa-no-permitida",
            titulo="Esa edición del programa no te corresponde",
            detalle=str(exc),
        )

    @app.exception_handler(ParteNoPermitida)
    async def _parte_no_permitida(request: Request, exc: ParteNoPermitida) -> JSONResponse:
        return _problema(
            request,
            status=403,
            tipo="parte-no-permitida",
            titulo="Ese paso de la parte no te corresponde",
            detalle=str(exc),
        )

    @app.exception_handler(ErrorDeParte)
    async def _error_de_parte(request: Request, exc: ErrorDeParte) -> JSONResponse:
        return _problema(
            request,
            status=409,
            tipo="regla-de-parte",
            titulo="La parte no está en ese paso",
            detalle=str(exc),
        )

    @app.exception_handler(ParteNoEncontrada)
    async def _parte_no_encontrada(request: Request, exc: ParteNoEncontrada) -> JSONResponse:
        return _problema(
            request,
            status=404,
            tipo="parte-no-encontrada",
            titulo="Parte no encontrada",
            detalle=str(exc),
        )

    @app.exception_handler(ErrorDeCatalogoBase)
    async def _catalogo_base(request: Request, exc: ErrorDeCatalogoBase) -> JSONResponse:
        return _problema(
            request,
            status=422,
            tipo="catalogo-base-no-disponible",
            titulo="No hay catálogo base para eso",
            detalle=str(exc),
        )

    @app.exception_handler(ErrorDeModificacion)
    async def _modificacion(request: Request, exc: ErrorDeModificacion) -> JSONResponse:
        return _problema(
            request,
            status=422,
            tipo="modificacion-invalida",
            titulo="Esa modificación no cabe",
            detalle=str(exc),
        )

    @app.exception_handler(ErrorDeUmbrales)
    async def _umbrales(request: Request, exc: ErrorDeUmbrales) -> JSONResponse:
        return _problema(
            request,
            status=422,
            tipo="umbrales-invalidos",
            titulo="Umbrales inválidos",
            detalle=str(exc),
        )

    @app.exception_handler(ErrorDePlantas)
    async def _plantas(request: Request, exc: ErrorDePlantas) -> JSONResponse:
        return _problema(
            request,
            status=422,
            tipo="plantas-invalidas",
            titulo="Plantas inválidas",
            detalle=str(exc),
        )

    @app.exception_handler(PrototipoNoEncontrado)
    async def _prototipo_no_encontrado(
        request: Request, exc: PrototipoNoEncontrado
    ) -> JSONResponse:
        return _problema(
            request,
            status=404,
            tipo="prototipo-no-encontrado",
            titulo="Prototipo no encontrado",
            detalle=str(exc),
        )

    @app.exception_handler(FechasDeLoAsignado)
    async def _fechas_de_lo_asignado(
        request: Request, exc: FechasDeLoAsignado
    ) -> JSONResponse:
        # 409: la petición es válida pero choca con el estado de la actividad
        # (asignada). El camino es proponer una reprogramación (P-4).
        return _problema(
            request,
            status=409,
            tipo="fechas-de-lo-asignado",
            titulo="Las fechas de lo asignado no se mueven solas",
            detalle=str(exc),
        )

    @app.exception_handler(ErrorDeReprogramacion)
    async def _reprogramacion(request: Request, exc: ErrorDeReprogramacion) -> JSONResponse:
        return _problema(
            request,
            status=409,
            tipo="regla-de-reprogramacion",
            titulo="Reprogramación no permitida",
            detalle=str(exc),
        )

    @app.exception_handler(ReprogramacionNoEncontrada)
    async def _reprogramacion_no_encontrada(
        request: Request, exc: ReprogramacionNoEncontrada
    ) -> JSONResponse:
        return _problema(
            request,
            status=404,
            tipo="reprogramacion-no-encontrada",
            titulo="Reprogramación no encontrada",
            detalle=str(exc),
        )

    @app.exception_handler(CierreDeFrenteNoEncontrado)
    async def _cierre_de_frente_no_encontrado(
        request: Request, exc: CierreDeFrenteNoEncontrado
    ) -> JSONResponse:
        return _problema(
            request,
            status=404,
            tipo="cierre-de-frente-no-encontrado",
            titulo="Cierre de frente no encontrado",
            detalle=str(exc),
        )

    @app.exception_handler(FrenteNoEncontrado)
    async def _frente_no_encontrado(request: Request, exc: FrenteNoEncontrado) -> JSONResponse:
        return _problema(
            request,
            status=404,
            tipo="frente-no-encontrado",
            titulo="Frente no encontrado",
            detalle=str(exc),
        )

    @app.exception_handler(ErrorDeConfirmacion)
    async def _confirmacion(request: Request, exc: ErrorDeConfirmacion) -> JSONResponse:
        return _problema(
            request,
            status=422,
            tipo="regla-de-confirmacion",
            titulo="Confirmación de avance inválida",
            detalle=str(exc),
        )

    @app.exception_handler(ActividadSinConfirmacion)
    async def _actividad_sin_confirmacion(
        request: Request, exc: ActividadSinConfirmacion
    ) -> JSONResponse:
        return _problema(
            request,
            status=404,
            tipo="actividad-no-encontrada",
            titulo="Actividad no encontrada",
            detalle=str(exc),
        )

    @app.exception_handler(PeriodoBloqueadoParaConfirmar)
    async def _periodo_bloqueado_confirmar(
        request: Request, exc: PeriodoBloqueadoParaConfirmar
    ) -> JSONResponse:
        return _problema(
            request,
            status=409,
            tipo="periodo-bloqueado",
            titulo="El periodo está bloqueado",
            detalle=str(exc),
        )

    @app.exception_handler(ErrorDeDesviacion)
    async def _desviacion(request: Request, exc: ErrorDeDesviacion) -> JSONResponse:
        return _problema(
            request,
            status=422,
            tipo="regla-de-desviacion",
            titulo="Desviación inválida",
            detalle=str(exc),
        )

    @app.exception_handler(DesviacionNoEncontrada)
    async def _desviacion_no_encontrada(
        request: Request, exc: DesviacionNoEncontrada
    ) -> JSONResponse:
        return _problema(
            request,
            status=404,
            tipo="desviacion-no-encontrada",
            titulo="Desviación no encontrada",
            detalle=str(exc),
        )

    @app.exception_handler(ErrorDeComprobacion)
    async def _comprobacion(request: Request, exc: ErrorDeComprobacion) -> JSONResponse:
        return _problema(
            request,
            status=422,
            tipo="regla-de-comprobacion",
            titulo="Comprobación de excedente inválida",
            detalle=str(exc),
            campo=exc.campo,
        )

    @app.exception_handler(SinExcedente)
    async def _sin_excedente(request: Request, exc: SinExcedente) -> JSONResponse:
        return _problema(
            request,
            status=409,
            tipo="sin-excedente",
            titulo="No hay excedente que decidir",
            detalle=str(exc),
        )

    @app.exception_handler(ActividadSinComprobacion)
    async def _actividad_sin_comprobacion(
        request: Request, exc: ActividadSinComprobacion
    ) -> JSONResponse:
        return _problema(
            request,
            status=404,
            tipo="actividad-no-encontrada",
            titulo="Actividad no encontrada",
            detalle=str(exc),
        )

    @app.exception_handler(ErrorDePrecioArmado)
    async def _precio_armado(
        request: Request, exc: ErrorDePrecioArmado
    ) -> JSONResponse:
        return _problema(
            request,
            status=422,
            tipo="precio-no-armable",
            titulo="El precio no se puede armar con eso",
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

    @app.exception_handler(ConflictoNoResuelto)
    async def _conflicto_jerarquia(
        request: Request, exc: ConflictoNoResuelto
    ) -> JSONResponse:
        # 409 y no 422: la ventana capturada es válida, y lo que trae cada hoja
        # también. Lo que no se puede es aplicar las dos, y quién gana lo decide
        # el usuario (§7.5). Se registra **antes** que el handler genérico de
        # `ErrorDeProgramacion`, del que hereda: Starlette resuelve por MRO y se
        # queda con el más específico.
        #
        # Las dos cifras viajan en el cuerpo porque la respuesta es la pregunta:
        # sin ellas, la pantalla tendría que ir a buscarlas para poder ofrecer
        # la elección.
        conflicto = exc.conflicto
        return _problema(
            request,
            status=409,
            tipo="conflicto-de-programacion-jerarquica",
            titulo="La programación del nodo choca con la de sus conceptos",
            detalle=str(exc),
            nodo_id=conflicto.nodo_id,
            nombre=conflicto.nombre,
            dias_capturados=float(conflicto.dias_capturados),
            dias_derivados=float(conflicto.dias_derivados),
            actividades=list(conflicto.actividades),
        )

    @app.exception_handler(NodoNoProgramable)
    async def _nodo_no_programable(
        request: Request, exc: NodoNoProgramable
    ) -> JSONResponse:
        # Mismo 404 que el resto: RLS hace indistinguible "no existe" de "no lo
        # puedes ver" (§12.4), y un nodo del árbol sin conceptos debajo tampoco
        # es programable, así que para el cliente es la misma nada.
        return _problema(
            request,
            status=404,
            tipo="nodo-no-programable",
            titulo="Nodo del árbol no encontrado o sin conceptos debajo",
            detalle=str(exc),
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

    @app.exception_handler(ObraYaEjecutada)
    async def _obra_ya_ejecutada(
        request: Request, exc: ObraYaEjecutada
    ) -> JSONResponse:
        # 409 y no 422: el cuerpo era correcto, es el estado de la obra el que
        # no admite la operación (§11.2).
        return _problema(
            request,
            status=409,
            tipo="obra-ya-ejecutada",
            titulo="La obra ya tiene ejecución capturada",
            detalle=str(exc),
        )

    @app.exception_handler(CalendarioSinGenerar)
    async def _calendario_sin_generar(
        request: Request, exc: CalendarioSinGenerar
    ) -> JSONResponse:
        # No es un 500: la organización todavía no corrió
        # `app.generar_calendario()` para esos años (§3.1), y el mensaje dice
        # exactamente eso para que se pueda arreglar sin abrir el log.
        return _problema(
            request,
            status=404,
            tipo="calendario-sin-generar",
            titulo="Calendario sin generar",
            detalle=str(exc),
        )

    @app.exception_handler(PrototipoSinPrograma)
    async def _prototipo_sin_programa(
        request: Request, exc: PrototipoSinPrograma
    ) -> JSONResponse:
        return _problema(
            request,
            status=404,
            tipo="prototipo-sin-programa",
            titulo="Prototipo sin programa o sin presupuesto",
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

    @app.exception_handler(FrenteCerrado)
    async def _frente_cerrado(request: Request, exc: FrenteCerrado) -> JSONResponse:
        return _problema(
            request,
            status=409,
            tipo="frente-cerrado",
            titulo="El frente está cerrado",
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

    @app.exception_handler(ProcesoNoEncontrado)
    async def _proceso_no_encontrado(
        request: Request, exc: ProcesoNoEncontrado
    ) -> JSONResponse:
        # Mismo tratamiento que las demás entidades: RLS hace indistinguible
        # "no existe" de "no lo puedes ver" (§12.4).
        return _problema(
            request,
            status=404,
            tipo="proceso-no-encontrado",
            titulo="Proceso no encontrado",
            detalle=str(exc),
        )

    @app.exception_handler(TipoDeReporteDesconocido)
    async def _tipo_de_reporte(
        request: Request, exc: TipoDeReporteDesconocido
    ) -> JSONResponse:
        # 404 y no 422: `{tipo}` es parte de la **ruta**, así que un tipo que
        # no existe es una ruta que no existe. El detalle enumera los válidos
        # (`adapters/export/catalogo.py`).
        return _problema(
            request,
            status=404,
            tipo="reporte-desconocido",
            titulo="Tipo de reporte desconocido",
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

    @app.exception_handler(RegistroNoEncontrado)
    async def _registro_no_encontrado(
        request: Request, exc: RegistroNoEncontrado
    ) -> JSONResponse:
        return _problema(
            request,
            status=404,
            tipo="registro-no-encontrado",
            titulo="El registro no existe",
            detalle=str(exc),
        )

    @app.exception_handler(VersionVigenteNoEliminable)
    async def _version_vigente_no_eliminable(
        request: Request, exc: VersionVigenteNoEliminable
    ) -> JSONResponse:
        return _problema(
            request,
            status=409,
            tipo="version-vigente-no-eliminable",
            titulo="No se puede eliminar la versión vigente",
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

    # Los tres "no encontrado" del ensamble comparten el criterio de
    # `ConceptoNoEncontrado`: RLS hace indistinguible "no existe" de "no lo
    # puedes ver" a propósito (§12.4).
    @app.exception_handler(EnsambleNoEncontrado)
    async def _ensamble_no_encontrado(
        request: Request, exc: EnsambleNoEncontrado
    ) -> JSONResponse:
        return _problema(
            request,
            status=404,
            tipo="ensamble-no-encontrado",
            titulo="Ensamble no encontrado",
            detalle=str(exc),
        )

    @app.exception_handler(SubEnsambleNoEncontrado)
    async def _sub_ensamble_no_encontrado(
        request: Request, exc: SubEnsambleNoEncontrado
    ) -> JSONResponse:
        return _problema(
            request,
            status=404,
            tipo="ensamble-no-encontrado",
            titulo="Sub-ensamble no encontrado",
            detalle=str(exc),
        )

    @app.exception_handler(InstanciaNoEncontrada)
    async def _instancia_no_encontrada(
        request: Request, exc: InstanciaNoEncontrada
    ) -> JSONResponse:
        return _problema(
            request,
            status=404,
            tipo="instancia-no-encontrada",
            titulo="Instancia de ensamble no encontrada",
            detalle=str(exc),
        )

    # Subclases de `ErrorDeAPU` que ganan sobre su 422 genérico: no son datos
    # inválidos sino un choque con el estado actual (ya existe esa clave; la
    # instancia ya pertenece a otra plantilla) — 409, igual que
    # `VersionVigenteNoEliminable`.
    @app.exception_handler(ClaveDeEnsambleEnUso)
    async def _clave_de_ensamble_en_uso(
        request: Request, exc: ClaveDeEnsambleEnUso
    ) -> JSONResponse:
        return _problema(
            request,
            status=409,
            tipo="clave-de-ensamble-en-uso",
            titulo="Ya existe un ensamble con esa clave",
            detalle=str(exc),
        )

    @app.exception_handler(EnsambleNoCoincideConInstancia)
    async def _ensamble_no_coincide(
        request: Request, exc: EnsambleNoCoincideConInstancia
    ) -> JSONResponse:
        return _problema(
            request,
            status=409,
            tipo="ensamble-no-coincide-con-instancia",
            titulo="La instancia pertenece a otro ensamble",
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

    @app.exception_handler(CargaConDependientes)
    async def _carga_con_dependientes(
        request: Request, exc: CargaConDependientes
    ) -> JSONResponse:
        # 409, no 500: revertir la cadena completa (`en_cadena=true`) es la
        # salida (§10.8) — no es un defecto, es un estado real de datos.
        return _problema(
            request,
            status=409,
            tipo="carga-con-dependientes",
            titulo="La carga no se puede revertir sola",
            detalle=str(exc),
        )

    @app.exception_handler(CargaNoEliminable)
    async def _carga_no_eliminable(
        request: Request, exc: CargaNoEliminable
    ) -> JSONResponse:
        return _problema(
            request,
            status=409,
            tipo="carga-no-eliminable",
            titulo="La carga no se puede eliminar",
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

    @app.exception_handler(ReversaEnConflicto)
    async def _reversa_en_conflicto(
        request: Request, exc: ReversaEnConflicto
    ) -> JSONResponse:
        # 409, no 500: a diferencia de `TablaNoRevertible` esto no es un
        # defecto del backend, es un conflicto real entre lotes (§10.8) —
        # revertir fuera de orden.
        return _problema(
            request,
            status=409,
            tipo="reversa-en-conflicto",
            titulo="La carga no se puede revertir",
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

    # --- Cuantificador (cerebro MODELO.md §1b, migración 0057) ----------

    @app.exception_handler(ErrorDeCuantificacion)
    async def _cuantificacion(
        request: Request, exc: ErrorDeCuantificacion
    ) -> JSONResponse:
        # 422: invariante del dato (factor no positivo, nodo ambiguo,
        # texto vacío de una nota), no una transición de flujo.
        return _problema(
            request,
            status=422,
            tipo="regla-de-cuantificacion",
            titulo="Dato de cuantificación inválido",
            detalle=str(exc),
        )

    @app.exception_handler(GobiernoDeCuantificacionInvalido)
    async def _gobierno_de_cuantificacion(
        request: Request, exc: GobiernoDeCuantificacionInvalido
    ) -> JSONResponse:
        # 403: el rol existe y está autenticado, solo no puede ESTA acción
        # (enlazar contra un prototipo_nodo) — mismo criterio que
        # `exigir_rol`, pero decidido en el dominio porque depende del
        # dato (a qué nodo apunta el enlace), no solo del rol.
        return _problema(
            request,
            status=403,
            tipo="gobierno-de-cuantificacion",
            titulo="Rol sin permiso para este enlace",
            detalle=str(exc),
        )

    @app.exception_handler(EnlaceNoEncontrado)
    async def _enlace_no_encontrado(
        request: Request, exc: EnlaceNoEncontrado
    ) -> JSONResponse:
        return _problema(
            request,
            status=404,
            tipo="enlace-no-encontrado",
            titulo="Enlace de cuantificación no encontrado",
            detalle=str(exc),
        )

    @app.exception_handler(TrazoNoEncontrado)
    async def _trazo_no_encontrado(
        request: Request, exc: TrazoNoEncontrado
    ) -> JSONResponse:
        return _problema(
            request,
            status=404,
            tipo="trazo-no-encontrado",
            titulo="Trazo no encontrado",
            detalle=str(exc),
        )

    @app.exception_handler(PlanoNoEncontrado)
    async def _plano_no_encontrado(
        request: Request, exc: PlanoNoEncontrado
    ) -> JSONResponse:
        return _problema(
            request,
            status=404,
            tipo="plano-no-encontrado",
            titulo="Plano no encontrado",
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

    @app.exception_handler(ErrorDeCierreDeObra)
    async def _cierre_de_obra(
        request: Request, exc: ErrorDeCierreDeObra
    ) -> JSONResponse:
        # 422 y no 409: no es un conflicto de concurrencia, es que la entrega
        # todavía no se puede firmar —falta gente por participar o falta
        # trabajo por resolver— y el detalle dice exactamente cuál de las dos.
        return _problema(
            request,
            status=422,
            tipo="regla-de-cierre-de-obra",
            titulo="La obra no se puede entregar todavía",
            detalle=str(exc),
        )

    @app.exception_handler(CierreDeObraNoEncontrado)
    async def _cierre_de_obra_no_encontrado(
        request: Request, exc: CierreDeObraNoEncontrado
    ) -> JSONResponse:
        return _problema(
            request,
            status=404,
            tipo="cierre-de-obra-no-encontrado",
            titulo="Cierre de obra no encontrado",
            detalle=str(exc),
        )

    @app.exception_handler(ErrorDeIdentidad)
    async def _identidad(request: Request, exc: ErrorDeIdentidad) -> JSONResponse:
        # 403 y no 422: no es un dato mal formado, es una acción que quien la
        # pide no puede hacer —otorgar un rol que no le corresponde, cambiar el
        # propio—. El cliente no lo arregla reenviando otro cuerpo.
        return _problema(
            request,
            status=403,
            tipo="regla-de-identidad",
            titulo="Acción no permitida sobre este usuario",
            detalle=str(exc),
        )

    @app.exception_handler(UsuarioNoEncontrado)
    async def _usuario_no_encontrado(
        request: Request, exc: UsuarioNoEncontrado
    ) -> JSONResponse:
        return _problema(
            request,
            status=404,
            tipo="usuario-no-encontrado",
            titulo="Usuario no encontrado",
            detalle=str(exc),
        )

    @app.exception_handler(CorreoYaRegistrado)
    async def _correo_ya_registrado(
        request: Request, exc: CorreoYaRegistrado
    ) -> JSONResponse:
        # 409 y no 503: es el único fallo del alta que quien la está haciendo
        # puede resolver solo —ese correo ya tiene cuenta—, y merece un mensaje
        # que lo diga en vez de un "algo pasó".
        return _problema(
            request,
            status=409,
            tipo="correo-ya-registrado",
            titulo="Ese correo ya tiene cuenta",
            detalle=str(exc),
        )

    @app.exception_handler(ErrorDelProveedorDeAuth)
    async def _proveedor_de_auth(
        request: Request, exc: ErrorDelProveedorDeAuth
    ) -> JSONResponse:
        # 503, mismo criterio que la cola y R2: la petición es válida y volverá
        # a serlo cuando el proveedor responda o cuando el despliegue tenga su
        # `SUPABASE_SERVICE_KEY` (§12.8). El detalle nombra la variable que
        # falta, jamás su valor.
        return _problema(
            request,
            status=503,
            tipo="proveedor-de-auth-no-disponible",
            titulo="Alta de usuarios no disponible",
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

    # --- Idempotencia (§11.2, §12.3) ------------------------------------

    @app.exception_handler(PeticionYaProcesada)
    async def _ya_procesada(
        request: Request, exc: PeticionYaProcesada
    ) -> JSONResponse:
        # 409 y no 200: la operación ocurrió **una** vez y esta petición no
        # hizo nada. Devolver 200 fingiría que este intento la ejecutó, y el
        # cliente no podría distinguir "se hizo ahora" de "ya estaba hecha"
        # —que es justo lo que quiere saber después de un doble clic—.
        return _problema(
            request,
            status=409,
            tipo="peticion-ya-procesada",
            titulo="La petición ya se procesó",
            detalle=str(exc),
            clave_idempotencia=exc.clave,
        )

    @app.exception_handler(ClaveReusada)
    async def _clave_reusada(request: Request, exc: ClaveReusada) -> JSONResponse:
        # 422: la clave es correcta como cabecera pero incorrecta como uso.
        # No es un conflicto de estado —no hay nada previo que estorbe—, es
        # que el cliente mandó mal la petición.
        return _problema(
            request,
            status=422,
            tipo="clave-de-idempotencia-reusada",
            titulo="Clave de idempotencia reusada",
            detalle=str(exc),
            clave_idempotencia=exc.clave,
        )

    @app.exception_handler(ClaveDeIdempotenciaInvalida)
    async def _clave_invalida(
        request: Request, exc: ClaveDeIdempotenciaInvalida
    ) -> JSONResponse:
        return _problema(
            request,
            status=400,
            tipo="clave-de-idempotencia-invalida",
            titulo="Clave de idempotencia inválida",
            detalle=str(exc),
        )

    # --- Genéricos: lo que no nace de una regla de dominio (§11.2) -------

    @app.exception_handler(ExcepcionHTTP)
    async def _http(request: Request, exc: ExcepcionHTTP) -> JSONResponse:
        """`HTTPException` de los routers y de Starlette → problem+json.

        Cubre el 403 de `exigir_rol`, el 401 de `dependencias`, el 409 de
        `/reportes/{id}/descargar` y los 404/405 que enruta Starlette sola.

        Se atrapa la excepción de **Starlette**, no la de FastAPI: la de
        FastAPI hereda de ella, así que este manejador cubre las dos, mientras
        que registrar la de FastAPI dejaría fuera las que levanta el router
        antes de entrar al endpoint.

        Las cabeceras se conservan. No es un detalle: el 401 lleva
        `WWW-Authenticate: Bearer` (`_no_autorizado`), y perderlo convertiría
        una respuesta correcta de autenticación en una a medias.
        """
        respuesta = _problema(
            request,
            status=exc.status_code,
            tipo=_TIPO_POR_ESTADO.get(exc.status_code, f"http-{exc.status_code}"),
            titulo=_titulo_por_estado(exc.status_code),
            detalle=str(exc.detail),
        )
        for nombre, valor in (exc.headers or {}).items():
            respuesta.headers[nombre] = valor
        return respuesta

    @app.exception_handler(RequestValidationError)
    async def _validacion(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """422 de Pydantic → problem+json con el detalle por campo.

        El formato de FastAPI (`{"detail": [{loc, msg, type}, …]}`) se
        conserva **traducido** en `errores`: el front necesita saber qué campo
        falló para marcarlo en el formulario, y perder esa lista para ganar
        uniformidad sería cambiar un problema por otro.

        `loc` se aplana a un nombre de campo con punto. Se descarta el primer
        segmento —`body`, `query`, `path`—, que le dice al cliente dónde
        buscar algo que él mismo mandó.
        """
        errores = [
            {
                "campo": ".".join(str(parte) for parte in error["loc"][1:])
                or str(error["loc"][0]),
                "motivo": error.get("msg", ""),
                "tipo": error.get("type", ""),
            }
            for error in exc.errors()
        ]
        return _problema(
            request,
            status=422,
            tipo="peticion-invalida",
            titulo="Petición inválida",
            detalle=(
                f"{len(errores)} campo(s) no cumplen el contrato: "
                + ", ".join(e["campo"] for e in errores)
            ),
            errores=errores,
        )

    @app.exception_handler(Exception)
    async def _no_previsto(request: Request, exc: Exception) -> JSONResponse:
        """Último recurso: cualquier fallo no previsto → 500 problem+json.

        **El detalle no lleva el mensaje de la excepción.** Un `str(exc)` de
        algo no previsto puede traer un fragmento de SQL, una ruta del
        servidor o un valor de la fila que se estaba procesando (§12.4). Lo
        que sí va es la clase y el `request_id` cuando exista, que es lo que
        permite cruzar el reporte del usuario con la traza del servidor.

        La traza completa se registra con `exception`, no se responde.
        """
        _log.exception(
            "Fallo no previsto en %s %s: %s",
            request.method,
            request.url.path,
            type(exc).__name__,
        )
        # El cuerpo lo arma `problemas.py`, no este manejador: el mismo 500
        # lo produce también `MiddlewareDeErroresConCORS`, y dos definiciones
        # del mismo error acaban diciendo cosas distintas.
        return problema_no_previsto(
            str(request.url.path), clase=type(exc).__name__
        )


app = crear_app()
