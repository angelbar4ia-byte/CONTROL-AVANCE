"""Repositorio de clusters (manzanas).

Spec §12.11 (adaptador de persistencia) · §7.2 · §2.1 (cluster = manzana) ·
§12.4 (RLS).

RLS filtra `cluster` por el proyecto al que pertenece (política
`cluster_select`, `database/migrations/20260814000012`, vía
`app.proyecto_visible(proyecto_id)`): ningún método de aquí filtra por
`org_id` a mano. `org_id` en el INSERT sale de
`current_setting('app.org_id')`.

A diferencia de `proyectos_sql.py`, aquí el `RETURNING` sí es seguro: el
predicado de `SELECT` mira el **proyecto padre**, que ya existe y por tanto sí
es visible bajo el snapshot del `INSERT`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioClustersSQL"]

_COLUMNAS = """
    id, proyecto_id, clave, nombre
"""


class RepositorioClustersSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def crear(self, datos: dict[str, Any]) -> UUID:
        """Alta de cluster (§11.2, roles C y SI).

        Claves esperadas: ``proyecto_id``, ``clave`` y ``nombre``, ya
        normalizados por `domain.proyectos.reglas.Cluster`.
        """
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into cluster (org_id, proyecto_id, clave, nombre)
                    values (cast(current_setting('app.org_id') as uuid),
                            :proyecto_id, :clave, :nombre)
                    returning id
                    """
                ),
                {
                    "proyecto_id": str(datos["proyecto_id"]),
                    "clave": datos["clave"],
                    "nombre": datos["nombre"],
                },
            )
        ).scalar_one()

    async def obtener(self, cluster_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} from cluster where id = :id"),
                {"id": str(cluster_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def listar(self, proyecto_id: UUID | None = None) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS}
                    from cluster
                    where :proyecto_id is null
                       or proyecto_id = cast(:proyecto_id as uuid)
                    order by clave
                    """
                ),
                {"proyecto_id": str(proyecto_id) if proyecto_id else None},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]
