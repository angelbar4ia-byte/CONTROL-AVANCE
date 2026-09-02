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

`listar_*`/`crear_*`/`actualizar_*` son para el cargador dedicado
(migración 0037, §10.6): a diferencia de `upsert_*`, sí actualizan la
descripción en cada carga — son el cargador dueño del catálogo, no una
referencia de otro cargador de pasada.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
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

    # --- CRUD para el cargador dedicado (§10.6) --------------------------

    async def listar_niveles(self) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text("select id, clave, descripcion, orden, importe from nivel order by clave")
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def crear_nivel(self, datos: dict[str, Any]) -> UUID:
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into nivel (org_id, clave, descripcion)
                    values (cast(current_setting('app.org_id') as uuid), :clave, :descripcion)
                    returning id
                    """
                ),
                {"clave": datos["clave"], "descripcion": datos["descripcion"]},
            )
        ).scalar_one()

    async def actualizar_nivel(self, nivel_id: UUID, cambios: dict[str, Any]) -> None:
        if "descripcion" not in cambios:
            return
        await self._sesion.execute(
            text("update nivel set descripcion = :descripcion where id = :id"),
            {"id": str(nivel_id), "descripcion": cambios["descripcion"]},
        )

    async def listar_etapas(self) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    "select id, nivel_id, frente_id, clave, descripcion, orden, "
                    "       ponderacion, importe "
                    "from etapa_constructiva order by clave"
                )
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def crear_etapa(self, datos: dict[str, Any]) -> UUID:
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into etapa_constructiva (org_id, clave, descripcion)
                    values (cast(current_setting('app.org_id') as uuid), :clave, :descripcion)
                    returning id
                    """
                ),
                {"clave": datos["clave"], "descripcion": datos["descripcion"]},
            )
        ).scalar_one()

    async def actualizar_etapa(self, etapa_id: UUID, cambios: dict[str, Any]) -> None:
        if "descripcion" not in cambios:
            return
        await self._sesion.execute(
            text("update etapa_constructiva set descripcion = :descripcion where id = :id"),
            {"id": str(etapa_id), "descripcion": cambios["descripcion"]},
        )

    async def asignar_frente(
        self, *, frente_id: UUID, etapa_ids: Sequence[UUID]
    ) -> None:
        """Deja ese frente con **exactamente** esas etapas (§8.3, 0045).

        Es un reemplazo y no un alta: primero suelta las que tenía y luego toma
        las que llegan. Así una etapa que se quitó de la lista queda sin frente
        en vez de arrastrarse, y la pantalla no necesita mandar dos llamadas
        para mover una etapa de un frente a otro.

        Una etapa pertenece a un frente y solo a uno, así que tomarla aquí la
        quita del frente en el que estuviera — sin eso, su trabajo se contaría
        dos veces al planear cuántas cuadrillas hacen falta.
        """
        await self._sesion.execute(
            text(
                "update etapa_constructiva set frente_id = null "
                "where frente_id = cast(:frente_id as uuid)"
            ),
            {"frente_id": str(frente_id)},
        )
        if not etapa_ids:
            return
        await self._sesion.execute(
            text(
                "update etapa_constructiva set frente_id = cast(:frente_id as uuid) "
                "where id = any(cast(:etapas as uuid[]))"
            ),
            {"frente_id": str(frente_id), "etapas": [str(e) for e in etapa_ids]},
        )
