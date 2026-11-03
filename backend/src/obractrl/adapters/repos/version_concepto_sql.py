"""Adaptador SQL de `version_concepto` (migración 0096, MODELO §4, D-227).

La tabla tiene RLS por organización: las consultas no filtran por `org_id` a
mano, lo hace la política con `app.current_org_id()`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class RepositorioVersionesConceptoSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def crear(self, datos: dict[str, Any]) -> UUID:
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into version_concepto
                        (org_id, concepto_id, version, vigente_desde, huella, pu)
                    values (cast(current_setting('app.org_id') as uuid),
                            cast(:concepto_id as uuid), :version,
                            coalesce(cast(:vigente_desde as date), current_date),
                            :huella, cast(:pu as numeric))
                    returning id
                    """
                ),
                {
                    "concepto_id": str(datos["concepto_id"]),
                    "version": int(datos["version"]),
                    "vigente_desde": datos.get("vigente_desde"),
                    "huella": datos.get("huella"),
                    "pu": str(datos["pu"]),
                },
            )
        ).scalar_one()

    async def listar(self, concepto_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select id, concepto_id, version, vigente_desde, huella, pu
                    from version_concepto
                    where concepto_id = cast(:concepto_id as uuid)
                    order by version
                    """
                ),
                {"concepto_id": str(concepto_id)},
            )
        ).mappings()
        return [dict(f) for f in filas]
