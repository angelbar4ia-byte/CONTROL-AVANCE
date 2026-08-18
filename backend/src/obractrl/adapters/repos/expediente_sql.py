"""Repositorio del expediente técnico.

Spec §12.11 (adaptador de persistencia) · §7.9 (`ExpedienteDoc`) · §11.2 ·
§12.4 (RLS).

`expediente_doc` entra al loop genérico `por_obra` de
`database/migrations/20260814000012_rls_policies.sql` (política
`expediente_doc_scope`, vía `obra_visible`): ningún método de aquí filtra por
`org_id` u `obra_id` de forma manual —eso lo impone la base—, igual que
`revisiones_sql.py`. `org_id` en el INSERT sale de
`current_setting('app.org_id')`.

`url` guarda la **clave** del objeto en R2, no una URL firmada: la firma
caduca (`infrastructure/storage/r2.py`), la clave no.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioExpedienteSQL"]

_COLUMNAS = """
    id, obra_id, tipo, nombre, url, subido_por, fecha
"""


class RepositorioExpedienteSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def crear(
        self,
        *,
        obra_id: UUID,
        tipo: str,
        nombre: str,
        url: str,
        subido_por: UUID,
    ) -> UUID:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    insert into expediente_doc
                        (org_id, obra_id, tipo, nombre, url, subido_por)
                    values
                        (cast(current_setting('app.org_id') as uuid),
                         cast(:obra_id as uuid),
                         cast(:tipo as tipo_expediente_doc),
                         :nombre, :url, cast(:subido_por as uuid))
                    returning id
                    """
                ),
                {
                    "obra_id": str(obra_id),
                    "tipo": tipo,
                    "nombre": nombre,
                    "url": url,
                    "subido_por": str(subido_por),
                },
            )
        ).scalar_one()
        return fila

    async def listar(
        self, obra_id: UUID, *, tipo: str | None = None
    ) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS}
                    from expediente_doc
                    where obra_id = cast(:obra_id as uuid)
                      -- El cast del lado `is null` fija el tipo del parámetro;
                      -- sin él asyncpg levanta AmbiguousParameterError.
                      and (cast(:tipo as tipo_expediente_doc) is null
                           or tipo = cast(:tipo as tipo_expediente_doc))
                    order by fecha desc, created_at desc
                    """
                ),
                {"obra_id": str(obra_id), "tipo": tipo},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]
