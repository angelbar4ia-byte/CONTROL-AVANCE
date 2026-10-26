"""Repositorio de los cierres por frente (migración 0071).

Un frente es un **nivel** (D-450): el de la actividad, con el de su etapa como
respaldo, igual que la Torre y la estimación. Su avance es el de sus actividades
ponderado por `cant_base × precio_unitario` —el mismo peso que el de la obra (0064)—;
sin importes, promedio simple.

Nada aquí filtra por organización u obra para decidir qué es visible: lo impone RLS
(§12.4). `org_id` en el INSERT sale de `current_setting('app.org_id')`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.application.puertos.repositorios import RegistroNoEncontrado

__all__ = ["CierreDeFrenteNoModificado", "RepositorioCierresDeFrenteSQL"]

# El avance ponderado de un conjunto de actividades. Sin importes, promedio simple.
_AVANCE_PONDERADO = """
    round(
      case when sum(a.cant_base * a.precio_unitario) > 0
           then sum(a.avance_pct * a.cant_base * a.precio_unitario)
                / sum(a.cant_base * a.precio_unitario)
           else avg(a.avance_pct)
      end, 2)
"""

_COLUMNAS = """
    id, obra_id, nivel_id, estatus, avance_pct, solicitado_por, solicitado_en,
    aprobado_por, aprobado_en, validado_por, validado_en, comentarios
"""


class CierreDeFrenteNoModificado(RegistroNoEncontrado):
    """El UPDATE no afectó ninguna fila: el cierre ya no existe o salió del alcance."""


class RepositorioCierresDeFrenteSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def frentes_de_obra(self, obra_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select niv.id as nivel_id, niv.clave, niv.descripcion, niv.orden,
                           count(a.id)               as n_actividades,
                           {_AVANCE_PONDERADO}       as avance_pct,
                           c.id                      as cierre_id,
                           c.estatus::text           as cierre_estatus,
                           c.avance_pct              as cierre_avance_pct,
                           c.solicitado_en           as solicitado_en,
                           c.aprobado_en             as aprobado_en,
                           c.validado_en             as validado_en,
                           c.comentarios             as cierre_comentarios
                      from actividad a
                      left join etapa_constructiva eta on eta.id = a.etapa_id
                      join nivel niv on niv.id = coalesce(a.nivel_id, eta.nivel_id)
                      left join lateral (
                            -- El cierre vivo del frente; si no hay, el rechazado más
                            -- reciente, para que el residente vea por qué.
                            select cf.*
                              from cierre_frente cf
                             where cf.obra_id = a.obra_id and cf.nivel_id = niv.id
                             order by (cf.estatus <> 'rechazado') desc, cf.created_at desc
                             limit 1
                      ) c on true
                     where a.obra_id = :obra_id
                     group by niv.id, niv.clave, niv.descripcion, niv.orden,
                              c.id, c.estatus, c.avance_pct, c.solicitado_en,
                              c.aprobado_en, c.validado_en, c.comentarios
                     order by niv.orden nulls last, niv.clave
                    """
                ),
                {"obra_id": str(obra_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def avance_del_frente(self, obra_id: UUID, nivel_id: UUID) -> Decimal | None:
        fila = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_AVANCE_PONDERADO} as avance_pct, count(a.id) as n
                      from actividad a
                      left join etapa_constructiva eta on eta.id = a.etapa_id
                     where a.obra_id = :obra_id
                       and coalesce(a.nivel_id, eta.nivel_id) = :nivel_id
                    """
                ),
                {"obra_id": str(obra_id), "nivel_id": str(nivel_id)},
            )
        ).mappings().one()
        return None if fila["n"] == 0 else Decimal(str(fila["avance_pct"] or 0))

    async def obtener(self, cierre_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} from cierre_frente where id = :id"),
                {"id": str(cierre_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def crear(
        self, *, obra_id: UUID, nivel_id: UUID, avance_pct: Decimal, solicitado_por: UUID
    ) -> UUID:
        id_ = uuid4()
        await self._sesion.execute(
            text(
                """
                insert into cierre_frente
                    (id, org_id, obra_id, nivel_id, avance_pct, solicitado_por)
                values
                    (:id, current_setting('app.org_id')::uuid, :obra_id, :nivel_id,
                     :avance_pct, :solicitado_por)
                """
            ),
            {
                "id": str(id_),
                "obra_id": str(obra_id),
                "nivel_id": str(nivel_id),
                "avance_pct": avance_pct,
                "solicitado_por": str(solicitado_por),
            },
        )
        return id_

    async def actualizar(
        self,
        cierre_id: UUID,
        *,
        estatus: str,
        aprobado_por: UUID | None = None,
        validado_por: UUID | None = None,
        comentarios: str | None = None,
    ) -> None:
        resultado = await self._sesion.execute(
            text(
                """
                update cierre_frente
                   set estatus      = cast(:estatus as estatus_cierre_frente),
                       aprobado_por = coalesce(cast(:aprobado_por as uuid), aprobado_por),
                       aprobado_en  = case when cast(:aprobado_por as uuid) is not null
                                           then now() else aprobado_en end,
                       validado_por = coalesce(cast(:validado_por as uuid), validado_por),
                       validado_en  = case when cast(:validado_por as uuid) is not null
                                           then now() else validado_en end,
                       comentarios  = coalesce(:comentarios, comentarios)
                 where id = :id
                """
            ),
            {
                "id": str(cierre_id),
                "estatus": estatus,
                "aprobado_por": str(aprobado_por) if aprobado_por else None,
                "validado_por": str(validado_por) if validado_por else None,
                "comentarios": comentarios,
            },
        )
        if resultado.rowcount == 0:
            raise CierreDeFrenteNoModificado(
                f"No se actualizó el cierre {cierre_id}: ya no existe o salió de tu alcance."
            )

    async def frente_de_actividad_cerrado(self, actividad_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select niv.clave, niv.descripcion
                      from actividad a
                      left join etapa_constructiva eta on eta.id = a.etapa_id
                      join nivel niv on niv.id = coalesce(a.nivel_id, eta.nivel_id)
                      join cierre_frente cf
                        on cf.obra_id = a.obra_id and cf.nivel_id = niv.id
                       and cf.estatus = 'validado'
                     where a.id = :id
                     limit 1
                    """
                ),
                {"id": str(actividad_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None
