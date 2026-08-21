"""Middleware del borde HTTP.

Spec §11.7 (observabilidad) · §11.2 (convenciones de API) · §12.4 · §12.12
(versión del cliente).

Dos: el id de petición y la versión mínima del cliente móvil. Viven en
`adapters/api/` y no en `infrastructure/` porque leen y escriben **cabeceras
HTTP**: son borde, no plomería. Lo que sí es plomería —el `ContextVar`, el
formato del log, Sentry— está en `infrastructure/observabilidad.py`, que no
conoce Starlette y por eso también lo puede usar el worker de jobs.

**Middleware ASGI y no `BaseHTTPMiddleware`.** El de Starlette envuelve cada
respuesta en una tarea aparte, lo que rompe el streaming y —peor para lo que
aquí importa— corre el endpoint en otro contexto, así que el `ContextVar` que
se fija en el middleware podría no ser el que ve el endpoint. Un middleware
ASGI puro fija el contexto en el mismo `Task` que atiende la petición.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from obractrl.adapters.api.problemas import problema_no_previsto
from obractrl.infrastructure.observabilidad import (
    nuevo_id_de_peticion,
    poner_id_de_peticion,
)

__all__ = [
    "CABECERA_ID_PETICION",
    "CABECERA_VERSION_CLIENTE",
    "MiddlewareDeErroresConCORS",
    "MiddlewareDeIdDePeticion",
    "MiddlewareDeVersionDeCliente",
    "version_es_menor",
]

_log = logging.getLogger(__name__)

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


CABECERA_VERSION_CLIENTE = "x-cliente-version"
"""La manda el móvil en toda petición (`mobile/src/lib/version.ts`)."""

CABECERA_VERSION_MINIMA = "x-version-minima"
"""Va en la respuesta 426: le dice al cliente **cuál** necesita."""

RUTAS_EXENTAS = ("/health", "/api/v1/cliente/version")
"""
Rutas que un cliente obsoleto **tiene** que poder llamar.

`/cliente/version` es la que le dice qué versión necesita: bloquearla dejaría
a la app sin forma de saber por qué la bloquearon. `/health` es la sonda de
Render, que no manda cabecera de cliente y no debe empezar a fallar porque
alguien suba la mínima.
"""


def version_es_menor(actual: str, minima: str) -> bool:
    """`True` si `actual < minima` comparando semver laxo.

    Espejo exacto de `comparar()` en `mobile/src/lib/version.ts`: se comparan
    solo los componentes numéricos `major.minor.patch` y se ignora el sufijo,
    de modo que `1.2.0-rc.1` cuenta como `1.2.0`. Que las dos
    implementaciones coincidan **importa**: si el servidor considerara
    obsoleto lo que la app considera al día, la app pediría datos, recibiría
    426 y no mostraría la pantalla de actualización —quedaría rota sin
    explicación—.

    Un componente no numérico vale 0 en vez de `NaN`, por la misma razón que
    en el móvil: con `NaN` toda comparación es falsa y el resultado sería
    "está al día" en silencio, el peor default para algo que decide si se
    bloquea el acceso.
    """
    partes_a = _componentes(actual)
    partes_b = _componentes(minima)

    for va, vb in zip(partes_a, partes_b, strict=False):
        if va != vb:
            return va < vb

    # Prefijo común idéntico: la más corta es menor solo si a la otra le
    # quedan componentes distintos de cero (`1.2` == `1.2.0`).
    return sum(partes_a[len(partes_b) :]) < sum(partes_b[len(partes_a) :])


def _componentes(version: str) -> list[int]:
    base = version.strip().split("-")[0].split("+")[0]
    salida = []
    for parte in base.split("."):
        try:
            salida.append(int(parte))
        except ValueError:
            salida.append(0)
    return salida


class MiddlewareDeVersionDeCliente:
    """Rechaza con **426** a los clientes móviles por debajo de la mínima (§12.12).

    ## Por qué el borde y no cada endpoint

    Porque la razón del rechazo no es de ningún endpoint en particular: es que
    ese binario ya no entiende el contrato. Repartirlo por rutas garantizaría
    que la siguiente se olvide.

    ## Por qué 426 y no 403

    `426 Upgrade Required` dice exactamente lo que pasa. Un 403 diría "no
    tienes permiso", que es falso y mandaría al usuario a pedirle accesos a
    Control de obra en vez de a la tienda. La respuesta lleva
    `X-Version-Minima` para que el cliente pueda decir el número sin volver a
    preguntar.

    ## Por qué solo aplica a quien manda la cabecera

    La web no la manda, ni curl, ni la sonda de Render. Sin cabecera, la
    petición pasa: exigirla convertiría este middleware en una barrera para
    todos los clientes que no son el móvil. La política es *quien se
    identifica como app vieja, se bloquea*, no *quien no se identifica, se
    bloquea*.

    ## Por qué la mínima se lee en cada petición

    `obtener_config()` está cacheada con `lru_cache`, así que leerla aquí no
    cuesta E/S — pero además deja el valor en un solo lugar. Cambiarla es
    reiniciar el servicio con otra variable, que es el flujo del §12.12.
    """

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self._app = app

    async def __call__(
        self, alcance: Alcance, recibir: Recibir, enviar: Enviar
    ) -> None:
        if alcance["type"] != "http":
            await self._app(alcance, recibir, enviar)
            return

        version = _cabecera(alcance, CABECERA_VERSION_CLIENTE)
        ruta = alcance.get("path", "")

        if version is None or ruta.startswith(RUTAS_EXENTAS):
            await self._app(alcance, recibir, enviar)
            return

        # Importación diferida: `middleware.py` lo importa `main.py` al
        # ensamblar, y traer la configuración arriba ataría este módulo al
        # arranque de la app en las pruebas que lo usan aislado.
        from obractrl.infrastructure.config import obtener_config

        minima = obtener_config().movil_version_minima
        if not version_es_menor(version, minima):
            await self._app(alcance, recibir, enviar)
            return

        await _responder_426(enviar, version=version, minima=minima)


async def _responder_426(enviar: Enviar, *, version: str, minima: str) -> None:
    """Respuesta con el mismo formato de error del resto de la API (§11.7)."""
    cuerpo = json.dumps(
        {
            "type": "about:blank",
            "title": "Actualización requerida",
            "status": 426,
            "detail": (
                f"Esta versión de la app ({version}) ya no es compatible; "
                f"se requiere {minima} o mayor (§12.12)."
            ),
        }
    ).encode()

    await enviar(
        {
            "type": "http.response.start",
            "status": 426,
            "headers": [
                (b"content-type", b"application/problem+json"),
                (CABECERA_VERSION_MINIMA.encode(), minima.encode()),
            ],
        }
    )
    await enviar({"type": "http.response.body", "body": cuerpo})


class MiddlewareDeErroresConCORS:
    """Convierte un fallo no previsto en respuesta **dentro** de la pila de CORS.

    ## El problema, que costó dos diagnósticos equivocados

    Un 500 sin manejar lo atrapa `ServerErrorMiddleware`, que Starlette pone
    **por fuera** de todo —incluido `CORSMiddleware`—. La respuesta sale sin
    `Access-Control-Allow-Origin`, así que el navegador no reporta el 500: dice

        blocked by CORS policy: No 'Access-Control-Allow-Origin' header

    Y ahí empieza la cacería equivocada. Pasó dos veces con el mismo
    despliegue: la primera era CORS de verdad; la segunda, un error de SQL por
    una base sin migrar que se disfrazó de lo mismo. El mensaje del navegador
    era idéntico y la causa no tenía nada que ver.

    ## La solución

    Este middleware se agrega **antes** que `CORSMiddleware`, y en Starlette
    eso significa más adentro: `add_middleware` inserta al principio de la
    lista y la lista se pliega de fuera hacia dentro. Así la excepción se
    convierte en respuesta aquí, y esa respuesta **sube por CORS**, que le pone
    sus cabeceras.

    El navegador entonces ve un 500 con su `problem+json` y su `request_id`:
    algo que se puede reportar y buscar en el log.

    ## Qué no decide

    El cuerpo. Lo arma `adapters/api/problemas.py`, el mismo que usa el
    manejador de `Exception` de `main.py`, que es el que sabe **no** filtrar el
    mensaje de la excepción (§12.4).
    """

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self._app = app

    async def __call__(
        self, alcance: Alcance, recibir: Recibir, enviar: Enviar
    ) -> None:
        if alcance["type"] != "http":
            await self._app(alcance, recibir, enviar)
            return

        empezo = False

        async def _marcar(mensaje: dict[str, Any]) -> None:
            nonlocal empezo
            if mensaje["type"] == "http.response.start":
                empezo = True
            await enviar(mensaje)

        try:
            await self._app(alcance, recibir, _marcar)
        except Exception as exc:
            if empezo:
                # La respuesta ya salió a medias —un streaming que truena a la
                # mitad, por ejemplo—: sustituirla rompería el protocolo. Se
                # deja subir para que `ServerErrorMiddleware` la registre.
                raise

            _log.exception(
                "Fallo no previsto en %s %s",
                alcance.get("method", "?"),
                alcance.get("path", "?"),
            )
            respuesta = problema_no_previsto(
                str(alcance.get("path", "")), clase=type(exc).__name__
            )
            await respuesta(alcance, _sin_cuerpo, enviar)


async def _sin_cuerpo() -> dict[str, Any]:
    """`receive` de la respuesta de error: ya no hay cuerpo que leer."""
    return {"type": "http.disconnect"}
