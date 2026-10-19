"""Lo que Generación escribe sobre `prototipo_nodo`/`partida_presupuesto`
(migración 0062, skill `erp-parametrico` §6, dirección ensamble →
presupuesto).

Spec §12.11 (adaptador de persistencia) · §12.4 (RLS).

Puerto propio (`RepositorioGeneracionDePresupuesto`) y no una extensión de
`RepositorioPrototipoNodo`/`RepositorioPresupuestos`: ver el docstring del
puerto para por qué.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioGeneracionDePresupuestoSQL"]

_PROFUNDIDAD_MAXIMA = 32
"""Mismo tope que `domain.catalogos.ensamble`: un cinturón de seguridad
para que el CTE termine, no una regla de negocio."""

_NODO = """
    id, prototipo_id, parent_id, tipo, nombre, clave, concepto_id,
    ensamble_id, ensamble_factor, orden
"""

_DESCENDIENTES = f"""
    with recursive descendientes as (
        select cast(:instancia_id as uuid) as id,
               array[cast(:instancia_id as uuid)] as camino
        union all
        select n.id, d.camino || n.id
        from prototipo_nodo n
        join descendientes d on n.parent_id = d.id
        where not (n.id = any(d.camino))
          and cardinality(d.camino) <= {_PROFUNDIDAD_MAXIMA}
    )
"""


class RepositorioGeneracionDePresupuestoSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def crear_instancia(
        self,
        *,
        prototipo_id: UUID,
        parent_id: UUID | None,
        nombre: str,
        ensamble_id: UUID,
        factor: Decimal,
        orden: int = 0,
    ) -> dict[str, Any]:
        fila = (
            await self._sesion.execute(
                text(
                    f"""
                    insert into prototipo_nodo
                        (org_id, prototipo_id, parent_id, tipo, nombre,
                         ensamble_id, ensamble_factor, orden)
                    values (cast(current_setting('app.org_id') as uuid),
                            cast(:prototipo_id as uuid), cast(:parent_id as uuid),
                            'nivel', :nombre, cast(:ensamble_id as uuid),
                            cast(:factor as numeric), :orden)
                    returning {_NODO}
                    """
                ),
                {
                    "prototipo_id": str(prototipo_id),
                    "parent_id": str(parent_id) if parent_id else None,
                    "nombre": nombre,
                    "ensamble_id": str(ensamble_id),
                    "factor": factor,
                    "orden": orden,
                },
            )
        ).mappings().one()
        return dict(fila)

    async def obtener_instancia(self, prototipo_nodo_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_NODO} from prototipo_nodo
                     where id = cast(:id as uuid) and ensamble_id is not null
                    """
                ),
                {"id": str(prototipo_nodo_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def actualizar_factor(self, prototipo_nodo_id: UUID, factor: Decimal) -> None:
        await self._sesion.execute(
            text(
                """
                update prototipo_nodo
                   set ensamble_factor = cast(:factor as numeric)
                 where id = cast(:id as uuid) and ensamble_id is not null
                """
            ),
            {"id": str(prototipo_nodo_id), "factor": factor},
        )

    async def partidas_de_instancia(
        self, *, presupuesto_id: UUID, instancia_id: UUID
    ) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    {_DESCENDIENTES}
                    select
                        n.id                        as prototipo_nodo_id,
                        n.concepto_id               as concepto_id,
                        c.clave                     as concepto_clave,
                        pp.id                       as partida_id,
                        pp.cantidad                 as cantidad,
                        pp.precio_unitario          as precio_unitario,
                        pp.cantidad_generada        as cantidad_generada,
                        pp.precio_unitario_generado as precio_unitario_generado
                      from prototipo_nodo n
                      join concepto c on c.id = n.concepto_id
                      left join partida_presupuesto pp
                        on pp.prototipo_nodo_id = n.id
                       and pp.presupuesto_id = cast(:presupuesto_id as uuid)
                     where n.tipo = 'concepto'
                       and n.id in (select id from descendientes)
                     order by c.clave
                    """
                ),
                {
                    "instancia_id": str(instancia_id),
                    "presupuesto_id": str(presupuesto_id),
                },
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def crear_partida_generada(
        self,
        *,
        presupuesto_id: UUID,
        prototipo_id: UUID,
        instancia_id: UUID,
        concepto_id: UUID,
        nombre: str,
        cantidad: Decimal,
        precio_unitario: Decimal,
        importe: Decimal,
        orden: int = 0,
    ) -> dict[str, Any]:
        nodo = (
            await self._sesion.execute(
                text(
                    """
                    insert into prototipo_nodo
                        (org_id, prototipo_id, parent_id, tipo, nombre,
                         concepto_id, orden)
                    values (cast(current_setting('app.org_id') as uuid),
                            cast(:prototipo_id as uuid), cast(:instancia_id as uuid),
                            'concepto', :nombre, cast(:concepto_id as uuid), :orden)
                    returning id
                    """
                ),
                {
                    "prototipo_id": str(prototipo_id),
                    "instancia_id": str(instancia_id),
                    "nombre": nombre,
                    "concepto_id": str(concepto_id),
                    "orden": orden,
                },
            )
        ).one()

        partida = (
            await self._sesion.execute(
                text(
                    """
                    insert into partida_presupuesto
                        (org_id, presupuesto_id, concepto_id, prototipo_nodo_id,
                         cantidad, precio_unitario, importe,
                         cantidad_generada, precio_unitario_generado, orden)
                    values (cast(current_setting('app.org_id') as uuid),
                            cast(:presupuesto_id as uuid), cast(:concepto_id as uuid),
                            cast(:prototipo_nodo_id as uuid), cast(:cantidad as numeric),
                            cast(:precio_unitario as numeric), cast(:importe as numeric),
                            cast(:cantidad as numeric), cast(:precio_unitario as numeric),
                            :orden)
                    returning id, concepto_id, prototipo_nodo_id, cantidad,
                              precio_unitario, importe, cantidad_generada,
                              precio_unitario_generado, orden
                    """
                ),
                {
                    "presupuesto_id": str(presupuesto_id),
                    "concepto_id": str(concepto_id),
                    "prototipo_nodo_id": str(nodo.id),
                    "cantidad": cantidad,
                    "precio_unitario": precio_unitario,
                    "importe": importe,
                    "orden": orden,
                },
            )
        ).mappings().one()
        return dict(partida)

    async def actualizar_partida_generada(
        self,
        partida_id: UUID,
        *,
        cantidad: Decimal,
        precio_unitario: Decimal,
        importe: Decimal,
    ) -> None:
        await self._sesion.execute(
            text(
                """
                update partida_presupuesto
                   set cantidad = cast(:cantidad as numeric),
                       precio_unitario = cast(:precio_unitario as numeric),
                       importe = cast(:importe as numeric),
                       cantidad_generada = cast(:cantidad as numeric),
                       precio_unitario_generado = cast(:precio_unitario as numeric)
                 where id = cast(:id as uuid)
                """
            ),
            {
                "id": str(partida_id),
                "cantidad": cantidad,
                "precio_unitario": precio_unitario,
                "importe": importe,
            },
        )
