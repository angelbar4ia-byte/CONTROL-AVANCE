"""Cola de trabajos: encolar y consultar (Arq + Redis).

Spec §12.2 ("**Jobs** — Arq + Redis (asyncio): CPM, estimaciones, importación
masiva de catálogos") · §11.2 (`GET /estimaciones/{id}/export` (xlsx, **job**),
`GET /obras/{id}/expediente/pdf` (job), `GET /reportes/{id}` estado/descarga) ·
§12.8 (entornos).

Este módulo es **plomería**: no sabe qué hace un trabajo, solo lo pone en la
cola y pregunta cómo va. Las funciones que corren viven en
`adapters/export/trabajos.py`, y el proceso worker las ensambla en
`obractrl/trabajador.py`. Por eso `infrastructure` no importa `adapters`: la
dependencia sigue apuntando hacia afuera-adentro y no al revés (§12.11).

**Un pool por operación.** Encolar abre el pool, encola y lo cierra. Es una
conexión de más por petición, cierto —a la escala del §12.1 (20-30 usuarios
concurrentes, un reporte no es una consulta de lista) eso no se nota—, y a
cambio no hay estado global atado a un event loop, que es exactamente el
problema que `infrastructure/db/sesion.py` tuvo que resolver con un fixture
(ver el encabezado de `tests/integracion/conftest.py`).

**Sin Redis se degrada, no se rompe.** Un despliegue sin Redis alcanzable
levanta `ColaNoDisponible`, que el borde traduce a 503: la petición es válida
y volverá a serlo cuando la infraestructura esté (§12.8). Sin esto, el
`ConnectionError` crudo de redis saldría como un 500 opaco.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Any, Final

from arq.connections import ArqRedis, RedisSettings, create_pool
from arq.jobs import Job, JobStatus
from redis.exceptions import RedisError

from obractrl.infrastructure.config import Config, obtener_config

__all__ = [
    "ColaDeTrabajos",
    "ColaNoDisponible",
    "EstadoTrabajo",
    "ResultadoTrabajo",
    "TrabajoEncolado",
    "TrabajoNoEncontrado",
]

_log = logging.getLogger(__name__)

CONN_TIMEOUT: Final = 3
"""Segundos para dar por perdida la conexión a Redis. Corto a propósito: esto
corre dentro de una petición HTTP y un Redis caído no puede colgarla."""


class ColaNoDisponible(RuntimeError):
    """Redis no está configurado o no responde (§12.8).

    Fallo **de despliegue**, no del cliente: la API está arriba pero no puede
    encolar. Se distingue de un error genérico para que el borde responda un
    503 legible, mismo criterio que `AlmacenamientoNoConfigurado` con R2.
    """


class TrabajoNoEncontrado(LookupError):
    """El identificador no corresponde a ningún trabajo vivo.

    Arq guarda el resultado un tiempo acotado (`keep_result`); pasado eso, el
    trabajo deja de existir. Para el cliente es un 404.
    """


class EstadoTrabajo:
    """Estados que el cliente ve. Nombres del dominio, en español (§8.1)."""

    EN_COLA = "en_cola"
    EN_PROCESO = "en_proceso"
    LISTO = "listo"
    FALLIDO = "fallido"


_ESTADOS: Final[dict[JobStatus, str]] = {
    JobStatus.deferred: EstadoTrabajo.EN_COLA,
    JobStatus.queued: EstadoTrabajo.EN_COLA,
    JobStatus.in_progress: EstadoTrabajo.EN_PROCESO,
    JobStatus.complete: EstadoTrabajo.LISTO,
}


@dataclass(frozen=True, slots=True)
class TrabajoEncolado:
    """Lo que el cliente necesita para volver a preguntar (§11.2)."""

    id: str
    estatus: str


@dataclass(frozen=True, slots=True)
class ResultadoTrabajo:
    """Estado del trabajo y, si terminó, lo que devolvió."""

    id: str
    estatus: str
    valor: Any = None
    error: str | None = None

    @property
    def listo(self) -> bool:
        return self.estatus == EstadoTrabajo.LISTO


def _ajustes(cfg: Config) -> RedisSettings:
    """`RedisSettings` del DSN configurado, sin reintentos largos.

    `conn_retries=0` porque el default de arq (5 intentos con 1 s de espera)
    dejaría la petición HTTP colgada cinco segundos antes de admitir que
    Redis no está.
    """
    if not cfg.redis_url.strip():
        raise ColaNoDisponible(
            "La cola de trabajos no está configurada en este entorno; falta "
            "REDIS_URL (§12.8)."
        )
    try:
        base = RedisSettings.from_dsn(cfg.redis_url)
    except Exception as exc:  # noqa: BLE001 — un DSN mal escrito no es un 500
        # No se ecoa el DSN: puede traer contraseña (`redis://:pass@host`).
        raise ColaNoDisponible(
            f"REDIS_URL no es un DSN válido de Redis ({type(exc).__name__}); "
            f"revisa la variable de entorno (§12.8)."
        ) from exc
    return replace(base, conn_retries=0, conn_timeout=CONN_TIMEOUT)


class ColaDeTrabajos:
    """Fachada de la cola (§12.2). La usan los routers de reportes."""

    def __init__(self, cfg: Config | None = None) -> None:
        self._cfg = cfg or obtener_config()

    async def encolar(self, funcion: str, **argumentos: Any) -> TrabajoEncolado:
        """Pone el trabajo en la cola y devuelve su identificador.

        Los argumentos van por nombre a propósito: el worker los recibe como
        `**kwargs` y así agregar un parámetro no reordena una tupla que ya
        está serializada en Redis de un despliegue anterior.
        """
        async with self._pool() as pool:
            trabajo = await pool.enqueue_job(funcion, **argumentos)
            if trabajo is None:  # pragma: no cover - solo con `_job_id` repetido
                raise ColaNoDisponible(
                    "Redis rechazó el encolado: ya existe un trabajo con ese "
                    "identificador."
                )
            return TrabajoEncolado(id=trabajo.job_id, estatus=EstadoTrabajo.EN_COLA)

    async def consultar(self, trabajo_id: str) -> ResultadoTrabajo:
        """Estado del trabajo; si terminó, su resultado o su error (§11.2)."""
        async with self._pool() as pool:
            trabajo = Job(trabajo_id, redis=pool)
            estado = await trabajo.status()
            if estado is JobStatus.not_found:
                raise TrabajoNoEncontrado(
                    f"El reporte {trabajo_id} no existe o su resultado ya "
                    f"expiró; vuelve a pedirlo."
                )
            if estado is not JobStatus.complete:
                return ResultadoTrabajo(id=trabajo_id, estatus=_ESTADOS[estado])

            info = await trabajo.result_info()
            if info is None:  # pragma: no cover - carrera con la expiración
                raise TrabajoNoEncontrado(
                    f"El resultado del reporte {trabajo_id} ya expiró; vuelve "
                    f"a pedirlo."
                )
            if not info.success:
                # `info.result` es la excepción del worker. Se registra
                # completa y al cliente solo le llega su clase: el mensaje
                # podría traer rutas o parámetros de la infraestructura.
                _log.error(
                    "El trabajo %s falló en el worker: %r", trabajo_id, info.result
                )
                return ResultadoTrabajo(
                    id=trabajo_id,
                    estatus=EstadoTrabajo.FALLIDO,
                    error=type(info.result).__name__,
                )
            return ResultadoTrabajo(
                id=trabajo_id, estatus=EstadoTrabajo.LISTO, valor=info.result
            )

    async def disponible(self) -> bool:
        """¿Responde Redis? Para la sonda de dependencias (§11.7).

        Abre el pool y lo cierra, que es lo que `arq` hace con un `ping`
        incluido. No levanta: la sonda reporta el estado, no falla por él —un
        `/health` que se cae cuando se cae una dependencia no sirve para
        diagnosticar nada—.
        """
        try:
            async with self._pool():
                return True
        except ColaNoDisponible:
            return False

    async def estado(self) -> tuple[int, bool]:
        """Cuántos trabajos esperan y si el worker sigue latiendo (§11.7).

        POR QUÉ LAS DOS COSAS Y NO SOLO LA PRIMERA

        Una cola con trabajos y sin worker se ve igual que una cola ocupada:
        crece. La diferencia —la que importa cuando alguien mira la sonda a
        media noche— está en el latido. `arq` escribe `health_check_key` con un
        vencimiento de `health_check_interval + 1`, así que **que la llave
        exista ya significa que el worker latió hace poco**: no hay que
        interpretar su contenido ni comparar relojes entre máquinas.
        """
        ajustes = _ajustes(self._cfg)
        async with self._pool() as pool:
            en_cola = len(await pool.queued_jobs())
            latido = await pool.exists(ajustes.health_check_key)
        return en_cola, bool(latido)

    def _pool(self) -> _PoolDeArq:
        return _PoolDeArq(_ajustes(self._cfg))


class _PoolDeArq:
    """Context manager que abre el pool y siempre lo cierra.

    Traduce cualquier fallo de conexión a `ColaNoDisponible` en un solo lugar,
    para que ni `encolar` ni `consultar` tengan que repetir el `except`.
    """

    def __init__(self, ajustes: RedisSettings) -> None:
        self._ajustes = ajustes
        self._pool: ArqRedis | None = None

    async def __aenter__(self) -> ArqRedis:
        try:
            self._pool = await create_pool(self._ajustes)
        except (TimeoutError, OSError, RedisError) as exc:
            # `RedisError` va explícito: `redis.exceptions.ConnectionError`
            # **no** hereda de `OSError` —cuelga de `RedisError`, que cuelga
            # de `Exception`—, así que "conexión rechazada" se escaparía de un
            # `except OSError` y saldría como un 500 opaco. `OSError` y
            # `TimeoutError` se quedan por los fallos que sí levanta la capa
            # de sockets antes de que redis-py los envuelva (DNS, por ejemplo).
            raise ColaNoDisponible(
                f"La cola de trabajos no responde en este entorno "
                f"({type(exc).__name__}); revisa Redis (§12.8)."
            ) from exc
        return self._pool

    async def __aexit__(self, *exc_info: object) -> None:
        if self._pool is None:  # pragma: no cover - defensivo
            return
        cerrar = getattr(self._pool, "aclose", None) or self._pool.close
        await cerrar()
