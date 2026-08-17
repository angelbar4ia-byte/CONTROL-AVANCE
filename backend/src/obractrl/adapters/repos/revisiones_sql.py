"""Repositorio de revisiones físicas de campo.

Spec §12.11 (adaptador de persistencia) · §7.8 (`RevisionFisica`) · §11.2 ·
§12.4 (RLS).

`revision_fisica` entra al loop genérico `por_obra` de
`database/migrations/20260814000012_rls_policies.sql` (política
`revision_fisica_scope`, vía `obra_visible`): ningún método de aquí filtra por
`org_id` u `obra_id` de forma manual —eso lo impone la base—, igual que
`incidencias_sql.py`. `org_id` en el INSERT sale de
`current_setting('app.org_id')`.

`sync_status` no se escribe desde la API: la columna existe para la cola
offline del móvil (§12.2 "las fotos se suben en segundo plano"), y su default
`'sincronizado'` es justamente lo que corresponde a una revisión que llegó por
HTTP y ya está en Postgres.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioRevisionesSQL"]

_COLUMNAS = """
    id, obra_id, actividad_id, incidencia_id, usuario_id, fecha, fotos,
    comentario, calidad
"""


class RepositorioRevisionesSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def crear(
        self,
        *,
        obra_id: UUID,
        usuario_id: UUID,
        fecha: date,
        fotos: list[str],
        comentario: str | None = None,
        calidad: int | None = None,
        actividad_id: UUID | None = None,
        incidencia_id: UUID | None = None,
    ) -> UUID:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    insert into revision_fisica
                        (org_id, obra_id, actividad_id, incidencia_id,
                         usuario_id, fecha, fotos, comentario, calidad)
                    values
                        (cast(current_setting('app.org_id') as uuid),
                         :obra_id, :actividad_id, :incidencia_id, :usuario_id,
                         :fecha, cast(:fotos as jsonb), :comentario, :calidad)
                    returning id
                    """
                ),
                {
                    "obra_id": str(obra_id),
                    "actividad_id": str(actividad_id) if actividad_id else None,
                    "incidencia_id": str(incidencia_id) if incidencia_id else None,
                    "usuario_id": str(usuario_id),
                    "fecha": fecha,
                    "fotos": json.dumps(fotos),
                    "comentario": comentario,
                    "calidad": calidad,
                },
            )
        ).scalar_one()
        return fila

    async def listar(self, *, obra_id: UUID | None = None) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS}
                    from revision_fisica
                    -- El cast del lado `is null` fija el tipo del parámetro;
                    -- sin él asyncpg levanta AmbiguousParameterError.
                    where cast(:obra_id as uuid) is null
                       or obra_id = cast(:obra_id as uuid)
                    order by fecha desc, created_at desc
                    """
                ),
                {"obra_id": str(obra_id) if obra_id else None},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]
