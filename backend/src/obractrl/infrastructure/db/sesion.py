"""Sesión de base de datos con contexto RLS.

Spec §12.4 (multi-tenant) · §10.7 (RLS como frontera).

El flujo completo:

    cliente → JWT del proveedor administrado
           → FastAPI extrae `org_id` + `rol`
           → `SET LOCAL app.*` fija el contexto de la transacción
           → las políticas RLS filtran automáticamente

Por eso los endpoints **nunca** reciben ni pasan `org_id` como parámetro
(§11.2): el alcance es implícito y lo impone la base de datos.

Tres detalles que no se pueden relajar:

1. `SET LOCAL` (no `SET`) — el contexto muere con la transacción y no se
   filtra a la siguiente petición que reutilice la conexión del pool.
2. El rol de conexión **no** puede ser dueño de las tablas: el owner salta
   RLS. Se conecta con `obractrl_api` (ver `database/migrations/0014`).
3. Como el contexto es **de transacción**, un `commit()` a media sesión lo
   borra: todo lo que se leyera después quedaría sin `app.org_id` y RLS no
   devolvería **nada** —un caso de uso que reconsulta tras confirmar vería
   su propio registro como inexistente—. Por eso el contexto se re-aplica en
   cada `begin` (`_fijar_contexto`), no una sola vez al abrir la sesión.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from obractrl.infrastructure.config import obtener_config

__all__ = ["ContextoSesion", "crear_engine", "obtener_sessionmaker", "sesion_con_rls"]


@dataclass(frozen=True, slots=True)
class ContextoSesion:
    """Identidad que viaja del JWT a la sesión de Postgres (§12.4)."""

    org_id: UUID
    usuario_id: UUID
    rol: str


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def crear_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        cfg = obtener_config()
        _engine = create_async_engine(
            cfg.database_url,
            pool_size=cfg.db_pool_size,
            max_overflow=cfg.db_max_overflow,
            pool_pre_ping=True,
            echo=cfg.debug,
        )
    return _engine


def obtener_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            crear_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _sessionmaker


@asynccontextmanager
async def sesion_con_rls(ctx: ContextoSesion) -> AsyncIterator[AsyncSession]:
    """Abre una sesión con el contexto RLS ya fijado.

    Los valores van como parámetros de `set_config`, no interpolados en el
    SQL: `SET LOCAL` no admite parámetros vinculados, así que usar
    `set_config(..., true)` es lo que evita construir la sentencia por
    concatenación.
    """
    async with obtener_sessionmaker()() as sesion:
        # Se engancha a `after_begin` en vez de ejecutarlo una vez: así el
        # contexto vuelve a fijarse en la transacción que abre cada `commit()`
        # intermedio, y no solo en la primera (ver punto 3 del encabezado).
        @event.listens_for(sesion.sync_session, "after_begin")
        def _fijar_contexto(_sesion, _transaccion, conexion) -> None:  # noqa: ANN001
            conexion.execute(
                text(
                    "select set_config('app.org_id',     :org,  true),"
                    "       set_config('app.usuario_id', :usr,  true),"
                    "       set_config('app.rol',        :rol,  true)"
                ),
                {"org": str(ctx.org_id), "usr": str(ctx.usuario_id), "rol": ctx.rol},
            )

        try:
            # Fuerza el primer `begin` para que el contexto quede puesto antes
            # de la primera consulta del llamador.
            await sesion.connection()
            yield sesion
        except Exception:
            await sesion.rollback()
            raise
        finally:
            event.remove(sesion.sync_session, "after_begin", _fijar_contexto)


async def cerrar_engine() -> None:
    """Cierra el pool al apagar la app."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
