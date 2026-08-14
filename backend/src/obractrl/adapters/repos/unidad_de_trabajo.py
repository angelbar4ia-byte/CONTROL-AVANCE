"""Unidad de trabajo sobre una sesión de SQLAlchemy.

Spec §12.11 (puertos en el borde) · §9.2 (commit transaccional de cargas) ·
§12.4 (contexto RLS).

La transacción real ya la abre `infrastructure.db.sesion.sesion_con_rls` al
fijar el contexto con `SET LOCAL` (§12.4): ese `set_config` es la primera
sentencia que corre en la sesión, y con SQLAlchemy async una sesión
autoinicia su transacción en el primer `execute()`. Por eso esta clase
**no abre una transacción nueva** —hacerlo forzaría un `SAVEPOINT` anidado y,
peor, si algo commiteara la transacción externa a medio camino, el contexto
`app.org_id`/`app.rol` moriría con ella y las consultas siguientes de la
misma petición perderían RLS. `UnidadDeTrabajoSQL` solo envuelve el
commit/rollback de la transacción que ya está abierta, para que los casos de
uso escriban `async with self._uow:` sin conocer SQLAlchemy.
"""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["UnidadDeTrabajoSQL"]


class UnidadDeTrabajoSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def __aenter__(self) -> UnidadDeTrabajoSQL:
        return self

    async def __aexit__(
        self,
        tipo_exc: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        # `sesion_con_rls` ya hace rollback ante una excepción no manejada
        # (infrastructure/db/sesion.py); este rollback es una red adicional
        # por si el caso de uso captura la excepción de dominio (§11.2 la
        # convierte en problem+json antes de que llegue tan arriba) y dejó
        # la transacción a medias. `in_transaction()` evita un rollback
        # redundante cuando no hace falta.
        if exc is not None and self._sesion.in_transaction():
            await self._sesion.rollback()

    async def commit(self) -> None:
        await self._sesion.commit()

    async def rollback(self) -> None:
        await self._sesion.rollback()
