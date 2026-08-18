"""Repositorio de usuarios: la parte de Identidad que otros contextos piden.

Spec §12.11 (adaptador de persistencia) · §7.1 · §12.4 (RLS) · §11.1
(comunicación entre contextos solo por fachadas).

Existe para que Notificaciones sepa a qué correo escribirle sin consultar
`usuario` desde su propio repositorio (§11.1). La política `usuario_select`
(`database/migrations/20260814000012_rls_policies.sql`) da lectura a cualquier
usuario **de la organización del token**, así que el alcance no se filtra a
mano aquí: lo impone la base, y un usuario de otra organización simplemente no
aparece.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioUsuariosSQL"]


class RepositorioUsuariosSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def correos_de(self, usuario_ids: list[UUID]) -> list[dict[str, Any]]:
        """`{id, nombre, email}` de los usuarios visibles de la lista.

        Se resuelve en **una** consulta con `= any(...)` —como
        `obras_sql.precios_vigentes`— y no en un `obtener()` por usuario: los
        destinatarios de un aviso son tres o cuatro, pero un N+1 aquí sería
        N+1 en cada validación de estimación.
        """
        if not usuario_ids:
            return []

        filas = (
            await self._sesion.execute(
                text(
                    """
                    select id, nombre, email
                    from usuario
                    where id = any(cast(:ids as uuid[]))
                      and estatus = 'activo'
                    order by nombre
                    """
                ),
                {"ids": [str(uid) for uid in usuario_ids]},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]
