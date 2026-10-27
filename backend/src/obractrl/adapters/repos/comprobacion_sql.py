"""Repositorio del excedente de ejecución (migración 0066).

Nada aquí filtra por organización u obra para decidir qué es visible: lo impone
RLS (§12.4). `org_id` en los INSERT sale de `current_setting('app.org_id')`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioComprobacionesSQL"]


class RepositorioComprobacionesSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def pendientes(self) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select act.id as actividad_id, act.obra_id, o.clave as obra_clave,
                           con.clave as concepto_clave,
                           coalesce(act.descripcion, con.descripcion) as descripcion,
                           uni.clave as unidad,
                           act.cant_programada, act.cant_ejecutada, act.cant_perdida,
                           greatest(act.cant_ejecutada - act.cant_programada
                                    - act.cant_perdida, 0) as cant_excedente,
                           act.excedente_desde,
                           (current_date - act.excedente_desde) as dias
                      from actividad act
                      join obra o on o.id = act.obra_id
                      left join concepto con on con.id = act.concepto_id
                      left join unidad   uni on uni.id = con.unidad_id
                     where act.cant_ejecutada - act.cant_programada - act.cant_perdida > 0
                     order by act.excedente_desde nulls last, o.clave, act.created_at
                    """
                )
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def historial(self, actividad_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select c.id, c.actividad_id, c.decision, c.cantidad, c.nota,
                           c.orden_cambio, c.control_cambio_id, c.decidido_por,
                           u.nombre as decidido_por_nombre, c.decidido_en
                      from comprobacion_excedente c
                      left join usuario u on u.id = c.decidido_por
                     where c.actividad_id = :id
                     order by c.decidido_en, c.id
                    """
                ),
                {"id": str(actividad_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def obtener_para_decidir(self, actividad_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select id, obra_id, cant_programada, cant_ejecutada,
                           cant_perdida, cant_autorizada
                      from actividad
                     where id = :id
                       for update
                    """
                ),
                {"id": str(actividad_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def subir_techo(
        self,
        actividad_id: UUID,
        *,
        cant_programada: Decimal,
        cant_autorizada: Decimal,
        orden_cambio: str,
    ) -> None:
        await self._sesion.execute(
            text(
                """
                update actividad
                   set cant_autorizada = :autorizada,
                       cant_programada = :programada,
                       orden_cambio = :orden
                 where id = :id
                """
            ),
            {
                "id": str(actividad_id),
                "autorizada": cant_autorizada,
                "programada": cant_programada,
                "orden": orden_cambio,
            },
        )

    async def declarar_perdida(self, actividad_id: UUID, cantidad: Decimal) -> None:
        await self._sesion.execute(
            text(
                "update actividad set cant_perdida = cant_perdida + :cantidad where id = :id"
            ),
            {"id": str(actividad_id), "cantidad": cantidad},
        )

    async def abrir_control_de_cambio_autorizado(
        self,
        *,
        obra_id: UUID,
        actividad_id: UUID,
        cantidad_techo: Decimal,
        orden_cambio: str,
        motivo: str,
        usuario_id: UUID,
    ) -> UUID:
        """Deja el rastro como control de cambio **ya autorizado**: nadie lo pidió
        antes de ejecutarse, así que pedir y autorizar son el mismo acto de
        Control. Misma forma que `RepositorioControlCambioSQL`, para que aparezca
        en su bandeja."""
        control_id = uuid4()
        await self._sesion.execute(
            text(
                """
                insert into control_cambio
                    (id, org_id, obra_id, tipo, estatus, motivo, solicitado_por,
                     orden_cambio, autorizado_por, resuelto_en, nota_resolucion)
                values
                    (:id, cast(current_setting('app.org_id') as uuid),
                     cast(:obra_id as uuid), 'extra_catalogo', 'autorizado', :motivo,
                     cast(:usuario as uuid), :orden, cast(:usuario as uuid), now(),
                     'Excedente de ejecución comprobado y validado.')
                """
            ),
            {
                "id": str(control_id),
                "obra_id": str(obra_id),
                "motivo": motivo,
                "usuario": str(usuario_id),
                "orden": orden_cambio,
            },
        )
        await self._sesion.execute(
            text(
                """
                insert into control_cambio_linea
                    (org_id, control_cambio_id, actividad_id, cantidad)
                values
                    (cast(current_setting('app.org_id') as uuid), :control,
                     cast(:actividad as uuid), :cantidad)
                """
            ),
            {
                "control": str(control_id),
                "actividad": str(actividad_id),
                "cantidad": cantidad_techo,
            },
        )
        return control_id

    async def registrar_decision(
        self,
        *,
        actividad_id: UUID,
        decision: str,
        cantidad: Decimal,
        nota: str,
        orden_cambio: str | None,
        control_cambio_id: UUID | None,
        usuario_id: UUID,
    ) -> UUID:
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into comprobacion_excedente
                        (org_id, actividad_id, decision, cantidad, nota,
                         orden_cambio, control_cambio_id, decidido_por)
                    values
                        (cast(current_setting('app.org_id') as uuid),
                         cast(:actividad as uuid),
                         cast(:decision as decision_excedente), :cantidad, :nota,
                         :orden, cast(:control as uuid), cast(:usuario as uuid))
                    returning id
                    """
                ),
                {
                    "actividad": str(actividad_id),
                    "decision": decision,
                    "cantidad": cantidad,
                    "nota": nota,
                    "orden": orden_cambio,
                    "control": str(control_cambio_id) if control_cambio_id else None,
                    "usuario": str(usuario_id),
                },
            )
        ).scalar_one()
