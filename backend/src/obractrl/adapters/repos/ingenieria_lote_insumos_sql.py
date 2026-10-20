"""Repositorio de insumos crudos de ingeniería del lote (migración 0058).

Spec: cerebro CONOCIMIENTO.md §11.11 (P-36, "no se consolida al cargar") ·
§12.4 (RLS). `ingenieria_lote_insumo` comparte el patrón "por_obra" de
`plano`/`expediente_doc`: `obra_id` directo, política `app.obra_visible`.

Este adaptador nunca agrega por `(etapa, clave)` — eso es dominio puro
(`domain.ingenieria.consolidacion.consolidar_lote`); aquí solo se lee y se
escribe la fila cruda, tal cual (§12.11).
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.domain.cargadores.ingenieria_lote import FilaInsumoIngenieria

__all__ = ["RepositorioIngenieriaLoteInsumosSQL"]


class RepositorioIngenieriaLoteInsumosSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def guardar(
        self,
        *,
        obra_id: UUID,
        carga_id: UUID,
        filas: Sequence[FilaInsumoIngenieria],
    ) -> None:
        """Inserta las filas crudas de ESTE archivo. Nunca se llama en
        `dry_run` (§9.3): el caso de uso solo invoca esto cuando sí va a
        escribir el catálogo."""
        for f in filas:
            await self._sesion.execute(
                text(
                    """
                    insert into ingenieria_lote_insumo
                        (org_id, obra_id, carga_id, clave, descripcion,
                         unidad, cantidad, precio, importe, etapa,
                         agrupador, fila)
                    values
                        (cast(current_setting('app.org_id') as uuid),
                         :obra_id, :carga_id, :clave, :descripcion,
                         :unidad, :cantidad, :precio, :importe, :etapa,
                         :agrupador, :fila)
                    """
                ),
                {
                    "obra_id": str(obra_id),
                    "carga_id": str(carga_id),
                    "clave": f.clave,
                    "descripcion": f.descripcion,
                    "unidad": f.unidad,
                    "cantidad": f.cantidad,
                    "precio": f.precio,
                    "importe": f.importe,
                    "etapa": f.etapa,
                    "agrupador": f.agrupador,
                    "fila": f.fila,
                },
            )

    async def acumulado_por_obra(self, obra_id: UUID) -> tuple[FilaInsumoIngenieria, ...]:
        """Filas de cualquier carga de `ingenieria_lote` ya **aplicada y no
        revertida** de esta obra (join contra `carga_datos`, nunca una
        bandera propia que se pueda desincronizar — ver el docstring de la
        migración 0058). Nunca incluye la carga que se está aplicando en
        este mismo momento: su `estatus` sigue en `pendiente` hasta que
        `EjecutarCarga.ejecutar` la cierra, después de que el aplicador ya
        leyó esto."""
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select ili.clave, ili.descripcion, ili.unidad, ili.cantidad,
                           ili.precio, ili.importe, ili.etapa, ili.agrupador,
                           ili.fila
                      from ingenieria_lote_insumo ili
                      join carga_datos cd on cd.id = ili.carga_id
                     where ili.obra_id = cast(:obra_id as uuid)
                       and cd.tipo = 'ingenieria_lote'
                       and cd.estatus = 'aplicado'
                       and cd.revertida_en is null
                     order by ili.carga_id, ili.fila
                    """
                ),
                {"obra_id": str(obra_id)},
            )
        ).mappings().all()
        return tuple(_a_fila_insumo(dict(fila)) for fila in filas)


def _a_fila_insumo(fila: dict[str, Any]) -> FilaInsumoIngenieria:
    return FilaInsumoIngenieria(
        clave=str(fila["clave"]),
        descripcion=str(fila["descripcion"]),
        unidad=fila.get("unidad"),
        cantidad=Decimal(str(fila["cantidad"])),
        precio=Decimal(str(fila["precio"])) if fila.get("precio") is not None else None,
        importe=Decimal(str(fila["importe"])) if fila.get("importe") is not None else None,
        etapa=fila.get("etapa"),
        agrupador=fila.get("agrupador"),
        fila=int(fila["fila"]),
    )
