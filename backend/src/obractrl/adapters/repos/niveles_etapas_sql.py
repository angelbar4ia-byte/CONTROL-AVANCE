"""Repositorio de escritura del catálogo nivel/etapa constructiva (§10.1).

Spec §12.11 (adaptador de persistencia) · §12.4 (RLS).

Primer escritor de `nivel`/`etapa_constructiva` — hasta el cargador de
presupuesto jerárquico, ambas tablas solo se sembraban a mano. Son
catálogo compartido por organización (`uq_nivel_clave`/`uq_etapa_clave`,
`(org_id, clave)`, migración 0005), no por prototipo: la clave se repite
igual en cada prototipo del archivo, así que la primera carga que la trae
define su descripción y las siguientes solo la reutilizan.

El `on conflict ... do update set clave = excluded.clave` es un no-op a
propósito: no cambia ningún dato, solo hace que `returning id` dispare
también cuando la fila ya existía, sin una segunda consulta.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioNivelesEtapasSQL"]


class RepositorioNivelesEtapasSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def upsert_nivel(self, *, clave: str, descripcion: str, orden: int) -> UUID:
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into nivel (org_id, clave, descripcion, orden)
                    values (cast(current_setting('app.org_id') as uuid), :clave, :descripcion, :orden)
                    on conflict (org_id, clave) do update set clave = excluded.clave
                    returning id
                    """
                ),
                {"clave": clave, "descripcion": descripcion, "orden": orden},
            )
        ).scalar_one()

    async def upsert_etapa(
        self, *, clave: str, descripcion: str, nivel_id: UUID | None, orden: int
    ) -> UUID:
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into etapa_constructiva (org_id, nivel_id, clave, descripcion, orden)
                    values (cast(current_setting('app.org_id') as uuid), cast(:nivel_id as uuid),
                            :clave, :descripcion, :orden)
                    on conflict (org_id, clave) do update set clave = excluded.clave
                    returning id
                    """
                ),
                {
                    "nivel_id": str(nivel_id) if nivel_id else None,
                    "clave": clave,
                    "descripcion": descripcion,
                    "orden": orden,
                },
            )
        ).scalar_one()
