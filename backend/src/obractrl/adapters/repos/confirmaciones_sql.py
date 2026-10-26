"""Repositorio de las confirmaciones de avance (migración 0070).

Nada aquí filtra por organización u obra para decidir qué es visible: lo impone
RLS (§12.4). `org_id` en el INSERT sale de `current_setting('app.org_id')`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioConfirmacionesSQL"]


class RepositorioConfirmacionesSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def registrar(
        self,
        *,
        obra_id: UUID,
        actividad_id: UUID,
        cantidad: Decimal,
        momento: str,
        nota: str | None,
        usuario_id: UUID,
    ) -> UUID:
        id_ = uuid4()
        await self._sesion.execute(
            text(
                """
                insert into confirmacion_avance
                    (id, org_id, obra_id, actividad_id, cantidad, momento, nota,
                     confirmado_por)
                values
                    (:id, current_setting('app.org_id')::uuid, :obra_id,
                     :actividad_id, :cantidad,
                     cast(:momento as momento_confirmacion), :nota, :usuario_id)
                """
            ),
            {
                "id": str(id_),
                "obra_id": str(obra_id),
                "actividad_id": str(actividad_id),
                "cantidad": cantidad,
                "momento": momento,
                "nota": nota,
                "usuario_id": str(usuario_id),
            },
        )
        return id_

    async def de_obra(self, obra_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select a.id as actividad_id,
                           con.clave as concepto_clave,
                           coalesce(a.descripcion, con.descripcion) as descripcion,
                           uni.clave as unidad,
                           a.cant_ejecutada,
                           ult.cantidad       as cant_confirmada,
                           ult.confirmado_en  as confirmado_en,
                           ult.momento::text  as momento,
                           u.nombre           as confirmado_por_nombre
                      from actividad a
                      left join concepto con on con.id = a.concepto_id
                      left join unidad   uni on uni.id = con.unidad_id
                      left join lateral (
                            select c.cantidad, c.confirmado_en, c.momento, c.confirmado_por
                              from confirmacion_avance c
                             where c.actividad_id = a.id
                             order by c.confirmado_en desc, c.id desc
                             limit 1
                      ) ult on true
                      left join usuario u on u.id = ult.confirmado_por
                     where a.obra_id = :obra_id
                     order by a.created_at, a.id
                    """
                ),
                {"obra_id": str(obra_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def periodo_activo_bloqueado(self, obra_id: UUID) -> bool:
        return bool(
            (
                await self._sesion.execute(
                    text(
                        """
                        select exists (
                          select 1
                            from periodo_bloqueado pb
                            join ancla_semana an
                              on an.tipo = pb.tipo_semana
                             and an.anio = pb.anio
                             and an.semana = pb.semana
                           where pb.obra_id = :obra_id
                             and pb.tipo_semana = 'obra'
                        )
                        """
                    ),
                    {"obra_id": str(obra_id)},
                )
            ).scalar_one()
        )
