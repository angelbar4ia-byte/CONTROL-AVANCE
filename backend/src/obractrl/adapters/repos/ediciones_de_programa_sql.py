"""Repositorio de la bitácora de ediciones del programa (migración 0067).

Nada aquí filtra por organización u obra para decidir qué es visible: lo impone
RLS (§12.4). `org_id` en el INSERT sale de `current_setting('app.org_id')`.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioEdicionesDeProgramaSQL"]


class RepositorioEdicionesDeProgramaSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def registrar(
        self,
        *,
        obra_id: UUID,
        actividad_id: UUID,
        usuario_id: UUID,
        rol: str,
        tipo: str,
        antes: dict[str, Any],
        despues: dict[str, Any],
    ) -> UUID:
        id_ = uuid4()
        await self._sesion.execute(
            text(
                """
                insert into programa_edicion
                    (id, org_id, obra_id, actividad_id, usuario_id, rol, tipo,
                     antes, despues)
                values
                    (:id, current_setting('app.org_id')::uuid, :obra_id,
                     :actividad_id, :usuario_id, :rol,
                     cast(:tipo as tipo_edicion_programa),
                     cast(:antes as jsonb), cast(:despues as jsonb))
                """
            ),
            {
                "id": str(id_),
                "obra_id": str(obra_id),
                "actividad_id": str(actividad_id),
                "usuario_id": str(usuario_id),
                "rol": rol,
                "tipo": tipo,
                "antes": json.dumps(antes),
                "despues": json.dumps(despues),
            },
        )
        return id_

    async def de_obra(self, obra_id: UUID, *, limite: int = 200) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select e.id, e.obra_id, e.actividad_id,
                           coalesce(act.descripcion, con.descripcion) as actividad,
                           con.clave as concepto_clave,
                           e.usuario_id, u.nombre as usuario_nombre, e.rol, e.tipo,
                           e.antes, e.despues, e.creada_en
                      from programa_edicion e
                      join actividad act on act.id = e.actividad_id
                      left join concepto con on con.id = act.concepto_id
                      left join usuario u on u.id = e.usuario_id
                     where e.obra_id = :obra_id
                     order by e.creada_en desc, e.id
                     limit :limite
                    """
                ),
                {"obra_id": str(obra_id), "limite": limite},
            )
        ).mappings().all()
        return [dict(f) for f in filas]
