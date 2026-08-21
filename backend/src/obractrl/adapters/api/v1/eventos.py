"""Tiempo real: avisos en vivo por SSE.

Spec §11.2 ("**Tiempo real** — `WS /ws` (o `GET /events` SSE) — Torre,
bandejas y notificaciones (todos, por alcance)") · §11.1 (eventos de dominio)
· §12.4 (RLS) · §12.8.

## SSE y no WebSocket, que el §11.2 deja elegir

El spec ofrece las dos y aquí se toma **SSE**, por lo que hace falta:

- El tráfico es **de una sola dirección**. La Torre y las bandejas necesitan
  enterarse de que algo cambió; no mandan nada por el canal. Un WebSocket da
  un canal bidireccional del que se usaría la mitad, y con él la obligación de
  inventar un protocolo de mensajes, un ping propio y una máquina de
  reconexión.
- **Es HTTP.** Pasa por el proxy de Render, por los balanceadores y por los
  corporativos sin negociar un `Upgrade`, que es donde los WebSockets fallan
  en obra —redes con proxy y VPN son exactamente el caso del cliente—.
- La **reconexión** es del protocolo, no del código: el cliente reintenta solo
  y el servidor le sugiere cada cuánto con `retry:`.

Lo que se pierde —mandar cosas del cliente al servidor— ya lo hace la API
REST, que es donde tiene que estar: con su validación, su idempotencia y su
auditoría. Un canal en vivo que aceptara escrituras sería una segunda API sin
ninguna de las tres.

Si algún día hace falta bidireccional —chat en obra, edición concurrente— el
`WS /ws` del §11.2 sigue disponible y este endpoint no estorba.

## El token va en la cabecera, no en la URL

`EventSource`, la API nativa del navegador, **no deja poner cabeceras**: el
único lugar para el JWT sería la query string, y ahí acaba en los logs de
acceso de Render, en el historial del navegador y en cualquier proxy del
camino (§12.4). Por eso el cliente web lo consume con `fetch` + streams
(`frontend/src/lib/tiempoReal.ts`), que sí manda `Authorization`, y esta ruta
usa la dependencia de autenticación de siempre.

## Qué viaja

Ids, nunca contenido: ver `application/puertos/tiempo_real.py`. Quien recibe
`{"tipo": "actividad_cerrada", "datos": {...}}` vuelve a consultar por HTTP lo
que le interese, con su propio token y su propio RLS. El canal no es una
puerta trasera a datos que el rol no podría pedir.

El aislamiento es por **organización**, no por rol: dos usuarios de la misma
organización con alcances distintos reciben los mismos avisos. Es correcto
porque un aviso es un id y un nombre de hecho —saber que *algo* se cerró no
revela nada que la lista de obras no revele—, y la alternativa (resolver el
alcance de cada suscriptor en cada aviso) sería una segunda implementación de
RLS en Python: exactamente lo que el §12.4 pide no hacer.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from obractrl.adapters.api.dependencias import ContextoActual
from obractrl.infrastructure.tiempo_real.canal import canal_de_avisos

router = APIRouter(tags=["tiempo real"])

_log = logging.getLogger(__name__)

LATIDO_SEGUNDOS = 20
"""Cada cuánto se manda un comentario SSE si no hubo avisos.

Existe por los intermediarios, no por el cliente: un proxy que no ve bytes
cierra la conexión —Render corta a los ~30 s de silencio—, y el usuario vería
una reconexión cada medio minuto. Un comentario (`: latido`) es un byte de
relleno que el navegador ignora."""

REINTENTO_MS = 5_000
"""Sugerencia de reconexión que se manda al abrir. Cinco segundos: suficiente
para no martillar el servidor cuando se cae, corto para que la Torre vuelva a
estar en vivo antes de que nadie recargue a mano."""


def _sse(datos: dict, *, evento: str | None = None) -> str:
    """Un mensaje en el formato de `text/event-stream`.

    El JSON va en una sola línea a propósito: el protocolo separa campos por
    salto de línea, así que un `json.dumps` con indentación partiría el
    mensaje en varios `data:` y el cliente recibiría fragmentos.
    """
    cabeza = f"event: {evento}\n" if evento else ""
    return f"{cabeza}data: {json.dumps(datos, separators=(',', ':'))}\n\n"


@router.get(
    "/events",
    summary="Avisos en vivo (SSE)",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Flujo `text/event-stream`. Ver el encabezado del módulo.",
            "content": {"text/event-stream": {}},
        }
    },
)
async def eventos_en_vivo(peticion: Request, ctx: ContextoActual) -> StreamingResponse:
    """Abre el flujo de avisos de la organización del token (§11.2).

    La conexión vive hasta que el cliente se va. Se comprueba
    `peticion.is_disconnected()` en cada vuelta porque un generador de
    streaming **no** se cancela solo cuando el navegador cierra la pestaña:
    sin esa comprobación, cada pestaña cerrada dejaría una tarea despertándose
    cada veinte segundos para escribir en un socket muerto.
    """
    org_id = ctx.org_id

    async def flujo() -> AsyncIterator[str]:
        async with canal_de_avisos.suscribir(org_id) as cola:
            # `retry` primero: si la conexión se cae en el primer segundo, el
            # navegador ya sabe cuánto esperar.
            yield f"retry: {REINTENTO_MS}\n\n"
            yield _sse({"tipo": "conectado", "datos": {}}, evento="conectado")

            while True:
                if await peticion.is_disconnected():
                    return
                try:
                    aviso = await asyncio.wait_for(cola.get(), timeout=LATIDO_SEGUNDOS)
                except TimeoutError:
                    yield ": latido\n\n"
                    continue
                except asyncio.CancelledError:
                    # El servidor se está apagando (deploy, §12.12). Cerrar
                    # limpio hace que el navegador reconecte contra la
                    # instancia nueva en `REINTENTO_MS` en vez de quedarse
                    # colgado del socket viejo.
                    return

                yield _sse(aviso, evento=str(aviso.get("tipo") or "aviso"))

    return StreamingResponse(
        flujo(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Nginx —el proxy de Render— almacena la respuesta por defecto y
            # con eso el flujo llegaría a golpes o no llegaría. Es la cabecera
            # que convierte "funciona en local" en "funciona desplegado".
            "X-Accel-Buffering": "no",
        },
    )
