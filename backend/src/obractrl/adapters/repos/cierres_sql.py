"""Repositorio de solicitudes de cierre.

Spec §12.11 (adaptador de persistencia) · §7.8 (control y flujos) · §6 ·
§12.4 (RLS).

RLS ya filtra `solicitud_cierre` por alcance de rol (política
`solicitud_cierre_scope`, `database/migrations/0012`, vía el `obra_id` de la
actividad relacionada): ningún método de aquí filtra por `org_id` u `obra_id`
de forma manual — eso lo impone la base. `org_id` en el INSERT sale de
`current_setting('app.org_id')`, igual que en `actividades_sql.py`.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.application.puertos.repositorios import RegistroNoEncontrado

__all__ = ["RepositorioCierresSQL", "SolicitudCierreNoModificada"]

_COLUMNAS = """
    id, actividad_id, solicitada_por, autorizada_por, validada_por,
    cantidad, monto, checklist, adjuntos, comentarios, estatus
"""


class SolicitudCierreNoModificada(RegistroNoEncontrado):
    """El UPDATE no afectó ninguna fila: la solicitud ya no existe o salió
    del alcance del usuario (RLS) entre el `obtener()` y el `actualizar()`."""


class RepositorioCierresSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def obtener(self, cierre_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} from solicitud_cierre where id = :id"),
                {"id": str(cierre_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def crear(
        self,
        *,
        actividad_id: UUID,
        solicitada_por: UUID,
        cantidad: Decimal,
        monto: Decimal,
        checklist: list[dict],
        adjuntos: list[str],
    ) -> UUID:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    insert into solicitud_cierre
                        (org_id, actividad_id, solicitada_por, cantidad, monto,
                         checklist, adjuntos, estatus)
                    values
                        (cast(current_setting('app.org_id') as uuid),
                         :actividad_id, :solicitada_por, :cantidad, :monto,
                         cast(:checklist as jsonb), cast(:adjuntos as jsonb),
                         'solicitada')
                    returning id
                    """
                ),
                {
                    "actividad_id": str(actividad_id),
                    "solicitada_por": str(solicitada_por),
                    "cantidad": cantidad,
                    "monto": monto,
                    "checklist": json.dumps(checklist),
                    "adjuntos": json.dumps(adjuntos),
                },
            )
        ).scalar_one()
        return fila

    async def actualizar(
        self,
        cierre_id: UUID,
        *,
        estatus: str,
        autorizada_por: UUID | None = None,
        validada_por: UUID | None = None,
        comentarios: str | None = None,
    ) -> None:
        # `fecha_autoriza`/`fecha_valida` se fijan aquí mismo, no en el
        # dominio: son metadatos de persistencia (§7.8), no una regla de
        # negocio. `estimaciones_sql.actividades_estimables` depende de
        # `fecha_valida` para acotar la semana de estimación (§11.3 E.2).
        resultado = await self._sesion.execute(
            text(
                """
                update solicitud_cierre
                   set estatus        = cast(:estatus as estatus_solicitud_cierre),
                       autorizada_por = coalesce(cast(:autorizada_por as uuid), autorizada_por),
                       validada_por   = coalesce(cast(:validada_por as uuid), validada_por),
                       comentarios    = coalesce(:comentarios, comentarios),
                       fecha_autoriza = case when :estatus = 'autorizada' then now() else fecha_autoriza end,
                       fecha_valida   = case when :estatus = 'validada' then now() else fecha_valida end
                 where id = :id
                """
            ),
            {
                "id": str(cierre_id),
                "estatus": estatus,
                "autorizada_por": str(autorizada_por) if autorizada_por else None,
                "validada_por": str(validada_por) if validada_por else None,
                "comentarios": comentarios,
            },
        )
        if resultado.rowcount == 0:
            raise SolicitudCierreNoModificada(
                f"No se actualizó la solicitud {cierre_id}: ya no existe o "
                f"salió de tu alcance."
            )

    async def listar(self, *, estatus: str | None = None) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS}
                    from solicitud_cierre
                    where :estatus is null or estatus = cast(:estatus as estatus_solicitud_cierre)
                    order by fecha_solicitud desc
                    """
                ),
                {"estatus": estatus},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]
