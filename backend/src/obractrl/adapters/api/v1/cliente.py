"""Versión mínima soportada del cliente móvil.

Spec §12.12 ("El cliente manda su **versión** (header); el server puede pedir
**actualización mínima**" · "Force-update / soft-update: pantalla que exige
actualizar si la versión < mínima soportada").

## Por qué es un endpoint y no una constante en la app

Porque la decisión la toma el servidor **después** de que la app se publicó.
El día que un cambio de contrato deje de tolerar a los clientes de la 1.2, lo
que hay que mover es una variable de entorno en Render, no un build nuevo en
Play que tardaría días en llegar justo a quien ya no puede usar la app.

## Público a propósito

Sin `ContextoActual`: la pantalla de actualización tiene que poder mostrarse
**antes** del login. Un cliente obsoleto puede fallar al autenticarse —el
contrato de `/me` cambió, por ejemplo— y exigir sesión para decirle que
actualice lo dejaría en un callejón sin salida. Lo que devuelve no es
sensible: dos números de versión y la URL pública de la tienda.

## Qué NO hace

No decide por el cliente. Devuelve `minima` y `recomendada`; quién bloquea y
quién solo sugiere lo resuelve `mobile/src/lib/actualizacion.ts`. El servidor
sí bloquea por su cuenta en el borde HTTP —`MiddlewareDeVersionDeCliente`
responde 426— pero eso protege a la **API**; esto informa a la **app**, y son
dos preguntas distintas.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from obractrl.infrastructure.config import obtener_config

router = APIRouter(tags=["cliente"])

Plataforma = Annotated[
    Literal["android", "ios"],
    Query(description="Plataforma del cliente; cada tienda tiene su propio ritmo."),
]


class VersionSoportadaRespuesta(BaseModel):
    """Lo que la app necesita para decidir entre bloquear, sugerir o callarse."""

    minima: str = Field(
        description="Por debajo de esta versión la app debe bloquearse (§12.12)."
    )
    recomendada: str = Field(description="Última publicada; por debajo se sugiere actualizar.")
    url_tienda: str = Field(description="A dónde mandar al usuario para actualizar.")
    mensaje: str = Field(
        description="Texto que la app muestra tal cual; permite explicar el motivo sin publicar."
    )


@router.get(
    "/cliente/version",
    response_model=VersionSoportadaRespuesta,
    summary="Versión mínima y recomendada del cliente móvil",
)
async def version_soportada(plataforma: Plataforma = "android") -> VersionSoportadaRespuesta:
    """Devuelve la política de versiones vigente (§12.12).

    Hoy iOS y Android comparten valores porque solo se publica en Play
    (§12.13). El parámetro existe desde ahora para que el día que haya App
    Store —con su propio lag de revisión— no haya que romper el contrato:
    agregar valores por plataforma será cambiar la configuración, no el
    endpoint.
    """
    cfg = obtener_config()
    return VersionSoportadaRespuesta(
        minima=cfg.movil_version_minima,
        recomendada=cfg.movil_version_recomendada,
        url_tienda=cfg.movil_url_tienda,
        mensaje=cfg.movil_mensaje_actualizacion,
    )
