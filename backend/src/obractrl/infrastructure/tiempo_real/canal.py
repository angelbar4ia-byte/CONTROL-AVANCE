"""El canal de avisos en vivo: memoria dentro del proceso, Redis entre procesos.

Spec §11.2 ("**Tiempo real** — `WS /ws` (o `GET /events` SSE)") · §12.2
(Redis ya está para Arq) · §12.8 (entornos) · §12.11.

Implementa `application.puertos.tiempo_real.PublicadorEnVivo`.

## Por qué hacen falta dos capas y no una

Un aviso nace en el proceso que atendió la petición —o en el **worker**, si
lo produjo un job— y tiene que llegar a los navegadores conectados, que pueden
estar hablando con otra instancia. Con un solo `set` en memoria, un usuario
recibiría solo los avisos que casualmente nacieron donde él está conectado, y
ese "casualmente" cambia con cada deploy y con cada réplica de Render.

Entonces:

- **En memoria** — una cola `asyncio` por suscriptor, para entregar dentro del
  proceso. Es lo único que se necesita si hay una sola instancia y ningún job
  publica.
- **Redis pub/sub** — un canal por organización (`obractrl:eventos:{org_id}`)
  que reparte entre procesos. Se activa solo si `REDIS_URL` está configurada,
  que es la misma que ya usa Arq (§12.2): no se suma infraestructura.

**Sin Redis se degrada, no se rompe**, igual que la cola de trabajos: los
avisos siguen llegando a quien esté conectado a ese proceso y el resto del
sistema no se entera. Un despliegue de una sola instancia —el del piloto—
funciona completo sin Redis.

## Por qué pub/sub y no una cola durable

Porque un aviso que llega tarde no sirve. El cliente que se reconecta no
quiere el aviso de hace diez minutos: quiere volver a consultar el estado
actual, y eso ya lo hace TanStack Query al remontar. Guardar los avisos
implicaría decidir por cuánto tiempo, y para qué —el estado autoritativo
siempre está en Postgres—.

## Contrapresión: se descarta, no se acumula

Cada suscriptor tiene una cola acotada. Si un navegador deja de leer —pestaña
suspendida, red lenta—, su cola se llena y **se descartan los avisos nuevos**
para ese suscriptor, no para los demás. La alternativa —crecer sin límite— es
una fuga de memoria que tumba el proceso por una sola pestaña dormida. Es
seguro descartar porque un aviso perdido cuesta a lo sumo una recarga tardía:
el dato de verdad se pide por HTTP.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any
from uuid import UUID

import redis.asyncio as redis
from redis.exceptions import RedisError

from obractrl.application.puertos.tiempo_real import Aviso
from obractrl.infrastructure.config import Config, obtener_config

__all__ = ["CanalDeAvisos", "canal_de_avisos", "prefijo_de_canal"]

_log = logging.getLogger(__name__)

TOPE_POR_SUSCRIPTOR = 64
"""Avisos en vuelo por conexión antes de empezar a descartar. Sesenta y cuatro
es holgado para el ritmo real —un cierre, una incidencia— y chico para que una
pestaña dormida no acumule megabytes."""

PREFIJO = "obractrl:eventos:"


def prefijo_de_canal(org_id: UUID) -> str:
    """Canal de Redis de una organización. El aislamiento empieza en el nombre."""
    return f"{PREFIJO}{org_id}"


class CanalDeAvisos:
    """Publica y reparte avisos. Una instancia por proceso.

    No se crea por petición: los suscriptores viven mientras dura una conexión
    SSE, o sea minutos u horas, y tienen que sobrevivir a la petición que los
    abrió.
    """

    def __init__(self, cfg: Config | None = None) -> None:
        self._cfg = cfg or obtener_config()
        self._suscriptores: dict[UUID, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._puente: asyncio.Task[None] | None = None
        self._cliente: redis.Redis | None = None
        self._descartados = 0

    # --- Publicación -------------------------------------------------------

    async def publicar(self, aviso: Aviso) -> None:
        """Reparte el aviso local y, si hay Redis, al resto de los procesos.

        **No levanta** (ver el puerto). Local primero: si Redis falla, quien
        está conectado a este proceso —que en un despliegue de una instancia
        son todos— ya lo recibió.
        """
        self._repartir_local(aviso.org_id, aviso.como_json())

        if not self._hay_redis():
            return

        try:
            cliente = await self._obtener_cliente()
            await cliente.publish(
                prefijo_de_canal(aviso.org_id), json.dumps(aviso.como_json())
            )
        except (RedisError, OSError) as exc:
            _log.warning(
                "No se pudo repartir el aviso %s por Redis (%s); "
                "solo lo recibieron los clientes de este proceso.",
                aviso.tipo,
                type(exc).__name__,
            )

    def _repartir_local(self, org_id: UUID, mensaje: dict[str, Any]) -> None:
        for cola in self._suscriptores.get(org_id, set()):
            try:
                cola.put_nowait(mensaje)
            except asyncio.QueueFull:
                # Ver "contrapresión" en el encabezado. Se cuenta para que el
                # log diga *cuánto* se está descartando, no solo que pasa.
                self._descartados += 1
                if self._descartados % 100 == 1:
                    _log.warning(
                        "Un suscriptor no lee sus avisos; se descartaron %d en "
                        "este proceso.",
                        self._descartados,
                    )

    # --- Suscripción -------------------------------------------------------

    @asynccontextmanager
    async def suscribir(self, org_id: UUID) -> AsyncIterator[asyncio.Queue[dict[str, Any]]]:
        """Cola de avisos de una organización, mientras dure el `async with`.

        Context manager y no un par `suscribir`/`cancelar`: una conexión SSE
        se cierra de muchas maneras —el usuario cambia de página, el proxy
        corta, el proceso recibe SIGTERM— y en todas hay que quitar la cola.
        Con `finally` eso pasa una sola vez y en un solo lugar; con dos
        métodos, cada llamador tiene su propia oportunidad de olvidarlo y
        dejar una cola creciendo para siempre.
        """
        cola: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=TOPE_POR_SUSCRIPTOR)
        self._suscriptores.setdefault(org_id, set()).add(cola)
        self._asegurar_puente()

        try:
            yield cola
        finally:
            colas = self._suscriptores.get(org_id)
            if colas is not None:
                colas.discard(cola)
                if not colas:
                    del self._suscriptores[org_id]

    @property
    def suscriptores(self) -> int:
        """Conexiones vivas en este proceso. Lo usa la sonda de `/health`."""
        return sum(len(colas) for colas in self._suscriptores.values())

    # --- Puente con Redis --------------------------------------------------

    def _hay_redis(self) -> bool:
        return bool(self._cfg.redis_url.strip())

    async def _obtener_cliente(self) -> redis.Redis:
        if self._cliente is None:
            self._cliente = redis.from_url(self._cfg.redis_url)
        return self._cliente

    def _asegurar_puente(self) -> None:
        """Arranca la escucha de Redis la primera vez que alguien se suscribe.

        Perezoso a propósito: un proceso sin nadie conectado —el worker, o la
        API entre despliegues— no tiene por qué mantener abierta una conexión
        de pub/sub.
        """
        if not self._hay_redis() or (self._puente is not None and not self._puente.done()):
            return
        self._puente = asyncio.create_task(self._escuchar())

    async def _escuchar(self) -> None:
        """Escucha `obractrl:eventos:*` y reparte a las colas locales.

        Un solo patrón para todas las organizaciones en vez de una suscripción
        por org: el proceso ya filtra por `org_id` al repartir, y así una
        organización nueva no necesita que nadie suscriba nada.
        """
        while True:
            try:
                cliente = await self._obtener_cliente()
                async with cliente.pubsub() as pubsub:
                    await pubsub.psubscribe(f"{PREFIJO}*")
                    async for mensaje in pubsub.listen():
                        if mensaje.get("type") != "pmessage":
                            continue
                        self._entregar_de_redis(mensaje)
            except asyncio.CancelledError:
                raise
            except (RedisError, OSError) as exc:
                # Redis se cayó o se reinició. Se reintenta con una espera
                # fija: sin ella este bucle giraría a toda velocidad contra un
                # socket cerrado y quemaría la CPU del plan chico (§12.8).
                _log.warning(
                    "Se perdió la escucha de avisos (%s); se reintenta en 5 s.",
                    type(exc).__name__,
                )
                self._cliente = None
                await asyncio.sleep(5)

    def _entregar_de_redis(self, mensaje: dict[str, Any]) -> None:
        canal = mensaje.get("channel")
        canal = canal.decode() if isinstance(canal, bytes) else str(canal or "")
        crudo = mensaje.get("data")
        crudo = crudo.decode() if isinstance(crudo, bytes) else str(crudo or "")

        try:
            org_id = UUID(canal.removeprefix(PREFIJO))
            datos = json.loads(crudo)
        except (ValueError, json.JSONDecodeError):
            # Basura en el canal —otra app usando el mismo Redis, un mensaje
            # de una versión anterior— no puede tumbar la escucha de todos.
            _log.warning("Aviso ilegible en el canal %r; se descarta.", canal)
            return

        self._repartir_local(org_id, datos)

    async def cerrar(self) -> None:
        """Cierra el puente y la conexión. Lo llama el `lifespan` de la app.

        **Tolera que el event loop del puente ya no exista.** Esta instancia
        es de módulo —tiene que sobrevivir a las peticiones (ver abajo)— y por
        eso puede quedar con una tarea nacida en un loop que ya se cerró:
        pasa en la suite, donde cada prueba abre el suyo, y pasaría en
        producción si alguien levantara la app dos veces en el mismo proceso.
        Cancelar contra un loop cerrado levanta `RuntimeError`, y que el
        apagado de la app tronara por eso convertiría un detalle en un fallo
        de despliegue.
        """
        puente, self._puente = self._puente, None
        if puente is not None:
            try:
                puente.cancel()
                with suppress(asyncio.CancelledError):
                    await puente
            except RuntimeError:
                _log.debug("El puente de avisos pertenecía a un loop ya cerrado.")

        cliente, self._cliente = self._cliente, None
        if cliente is not None:
            with suppress(RedisError, OSError, RuntimeError):
                await cliente.aclose()


canal_de_avisos = CanalDeAvisos()
"""Instancia del proceso.

Módulo-nivel y no una dependencia de FastAPI: los suscriptores tienen que
sobrevivir a la petición que los creó, y una dependencia con `Depends` se
construye y se descarta por petición. Es el mismo motivo por el que el engine
de SQLAlchemy vive en `infrastructure/db/sesion.py` como singleton.
"""
