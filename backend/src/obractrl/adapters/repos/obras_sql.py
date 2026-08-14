"""Repositorio de obras.

Spec §12.11 (adaptador de persistencia) · §7.2 (estructura de proyecto) ·
§7.4 (árbol WBS del prototipo) · §11.3 workflow A.

RLS filtra `obra` por alcance de rol (política `obra_select` /
`obra_insert` / `obra_update` / `obra_delete`, `database/migrations/0012`):
igual que en `actividades_sql.py`, ningún método filtra `org_id` a mano.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.application.puertos.repositorios import RegistroNoEncontrado

__all__ = ["ObraNoModificada", "RepositorioObrasSQL"]


class ObraNoModificada(RegistroNoEncontrado):
    """El UPDATE no afectó ninguna fila (carrera entre `obtener` y escribir,
    o la obra salió del alcance del usuario vía RLS)."""


class RepositorioObrasSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def obtener(self, obra_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select id, cluster_id, prototipo_id, clave, residente_id,
                           estatus, fecha_inicio, fecha_fin, avance_pct,
                           m2, es_urba
                    from obra
                    where id = :id
                    """
                ),
                {"id": str(obra_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def actualizar_avance(self, obra_id: UUID, avance_pct: Decimal) -> None:
        resultado = await self._sesion.execute(
            text("update obra set avance_pct = :avance_pct where id = :id"),
            {"avance_pct": avance_pct, "id": str(obra_id)},
        )
        if resultado.rowcount == 0:
            raise ObraNoModificada(
                f"No se actualizó la obra {obra_id}: ya no existe o salió de "
                f"tu alcance."
            )

    async def arbol_prototipo(self, prototipo_id: UUID) -> list[dict[str, Any]]:
        """Nodos WBS del prototipo en orden de recorrido (§7.4).

        `orden` solo es comparable **dentro** de un mismo padre (es una
        columna por nivel, no una posición global), así que un `ORDER BY
        orden` plano intercalaría ramas distintas. El CTE recursivo arma la
        ruta de "orden"s desde la raíz (`array[orden_raíz, orden_hijo, …]`) y
        ordena por esa ruta —lo que da el recorrido en profundidad,
        padre-antes-que-hijos, que necesita el workflow A (§11.3) para crear
        las `Actividad` en el orden correcto del árbol.
        """
        filas = (
            await self._sesion.execute(
                text(
                    """
                    with recursive arbol as (
                        select id, parent_id, tipo, nombre, clave,
                               concepto_id, nivel_id, etapa_id, orden,
                               cantidad, ponderacion,
                               array[orden] as ruta
                        from prototipo_nodo
                        where prototipo_id = :prototipo_id
                          and parent_id is null

                        union all

                        select h.id, h.parent_id, h.tipo, h.nombre, h.clave,
                               h.concepto_id, h.nivel_id, h.etapa_id, h.orden,
                               h.cantidad, h.ponderacion,
                               a.ruta || h.orden
                        from prototipo_nodo h
                        join arbol a on h.parent_id = a.id
                    )
                    select id, parent_id, tipo, nombre, clave, concepto_id,
                           nivel_id, etapa_id, orden, cantidad, ponderacion
                    from arbol
                    order by ruta
                    """
                ),
                {"prototipo_id": str(prototipo_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]
