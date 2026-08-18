"""Punto de entrada del worker de jobs.

Spec §12.2 ("**Jobs** — Arq + Redis (asyncio)") · §11.2 (los reportes son
jobs) · §12.8 (entornos) · §12.11.

Se levanta aparte de la API, como un segundo proceso del mismo despliegue:

    arq obractrl.trabajador.WorkerSettings

Es el **composition root de los jobs**, el hermano de `main.py`: aquí se
declara qué funciones existen y con qué Redis se habla, y nada más. La lógica
está en `adapters/export/trabajos.py`, y las reglas, como siempre, en el
dominio (§12.11).

`WorkerSettings.redis_settings` se resuelve al importar el módulo, que es
cuando `arq` lo lee. Si `REDIS_URL` no es un DSN válido el worker no arranca
—falla cerrado y ruidoso, que es lo correcto en un proceso de fondo: un worker
que levanta y no consume dejaría los reportes encolados para siempre.
"""

from __future__ import annotations

from typing import Any, ClassVar

from arq.connections import RedisSettings

from obractrl.adapters.export.trabajos import FUNCIONES
from obractrl.infrastructure.config import obtener_config
from obractrl.infrastructure.db.sesion import cerrar_engine

__all__ = ["WorkerSettings"]


async def _apagar(_ctx: dict) -> None:
    """Cierra el pool de Postgres al apagar, como el `lifespan` de la API."""
    await cerrar_engine()


class WorkerSettings:
    """Configuración que `arq` lee por convención."""

    # `ClassVar` y no un atributo suelto: `arq` lee la lista de la clase,
    # nunca de una instancia, así que anotarla deja escrito que no es un
    # default mutable de dataclass a medio escribir.
    functions: ClassVar[list[Any]] = list(FUNCIONES)
    on_shutdown = _apagar
    redis_settings = RedisSettings.from_dsn(obtener_config().redis_url)

    max_jobs = 4
    """Un reporte es CPU (openpyxl/WeasyPrint) sobre un plan chico de Render
    (§12.8): más concurrencia solo alarga a todos por igual."""

    job_timeout = 120
    """Un expediente grande con su PDF no debería pasar de esto; si pasa, es
    un defecto que hay que ver, no algo que valga la pena esperar."""

    keep_result = 3600
    """El resultado —el archivo— vive una hora en Redis. Suficiente para que
    el cliente que lo pidió lo descargue (`GET /reportes/{id}/descargar`), y
    acotado para no usar Redis como almacén de archivos."""
