"""Middleware del borde HTTP.

Spec §11.7 (observabilidad) · §11.2 (convenciones de API) · §12.4.

Hoy solo el id de petición. Vive en `adapters/api/` y no en `infrastructure/`
porque lee y escribe una **cabecera HTTP**: es borde, no plomería. Lo que sí es
plomería —el `ContextVar`, el formato del log, Sentry— está en
`infrastructure/observabilidad.py`, que no conoce Starlette y por eso también
lo puede usar el worker de jobs.

**Middleware ASGI y no `BaseHTTPMiddleware`.** El de Starlette envuelve cada
respuesta en una tarea aparte, lo que rompe el streaming y —peor para lo que
aquí importa— corre el endpoint en otro contexto, así que el `ContextVar` que
se fija en el middleware podría no ser el que ve el endpoint. Un middleware
ASGI puro fija el contexto en el mismo `Task` que atiende la petición.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from obractrl.infrastructure.observabilidad import (
    nuevo_id_de_peticion,
    poner_id_de_peticion,
)

__all__ = ["CABECERA_ID_PETICION", "MiddlewareDeIdDePeticion"]

CABECERA_ID_PETICION = "x-request-id"

Alcance = dict[str, Any]
Recibir = Callable[[], Awaitable[dict[str, Any]]]
Enviar = Callable[[dict[str, Any]], Awaitable[None]]


class MiddlewareDeIdDePeticion:
    """Cose la petición, su log y su respuesta con un mismo id.

    Toma el `X-Request-Id` que venga del cliente o genera uno, lo deja en el
    contexto para que lo levante el log, y lo devuelve en la respuesta. Que
    salga en la respuesta es la mitad útil: es lo que permite que un usuario
    reporte "me falló, id abc123" y que eso se pueda buscar en Render.
    """

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self._app = app

    async def __call__(
        self, alcance: Alcance, recibir: Recibir, enviar: Enviar
    ) -> None:
        if alcance["type"] != "http":
            # WebSocket y lifespan pasan de largo: no tienen cabeceras de
            # respuesta donde devolver el id.
            await self._app(alcance, recibir, enviar)
            return

        identificador = nuevo_id_de_peticion(_cabecera(alcance, CABECERA_ID_PETICION))
        poner_id_de_peticion(identificador)

        async def _enviar_con_id(mensaje: dict[str, Any]) -> None:
            if mensaje["type"] == "http.response.start":
                # `setdefault` no aplica: la lista puede traer ya la cabecera
                # si algo la puso antes, y duplicarla confundiría a un proxy.
                cabeceras = [
                    (k, v)
                    for k, v in mensaje.get("headers", [])
                    if k.lower() != CABECERA_ID_PETICION.encode()
                ]
                cabeceras.append(
                    (CABECERA_ID_PETICION.encode(), identificador.encode())
                )
                mensaje = {**mensaje, "headers": cabeceras}
            await enviar(mensaje)

        await self._app(alcance, recibir, _enviar_con_id)


def _cabecera(alcance: Alcance, nombre: str) -> str | None:
    objetivo = nombre.lower().encode()
    for clave, valor in alcance.get("headers", []):
        if clave.lower() == objetivo:
            return valor.decode("latin-1")
    return None
