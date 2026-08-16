"""Repositorio de materiales: motivos, salidas de almacén y su cruce.

Spec §12.11 (adaptador de persistencia) · §7.7 · §10.5 · §12.4 (RLS).

`motivo_almacen` entra por el loop "catálogo" de
`database/migrations/20260814000012_rls_policies.sql`: alcance de
organización, visible a cualquier usuario de la org (§8.7, semilla editable).
`salida_almacen` entra por el loop `por_obra` (política `salida_almacen_scope`):
ningún método de aquí filtra por `org_id` u `obra_id` de forma manual para
esas dos tablas —eso lo impone la base—, igual que `cierres_sql.py`. `org_id`
en el INSERT sale de `current_setting('app.org_id')`.

`v_consumo_vs_presupuesto` es la excepción: no tiene política RLS propia
—hereda la de las tablas que consulta (invoker-rights por default en
Postgres)—, pero tampoco acota por una sola obra. Por eso
`consumo_vs_presupuesto` sí filtra explícitamente por `obra_id` (§10.5).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioMaterialesSQL"]

_COLUMNAS_SALIDA = """
    id, obra_id, insumo_id, motivo_id, concepto_id, contratista_id,
    usuario_id, fecha, semana, anio, cantidad, costo, costo_ultimo,
    almacen, referencia
"""


class RepositorioMaterialesSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def obtener_motivo(self, motivo_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select id, clave, descripcion, signo, bucket, estatus
                    from motivo_almacen
                    where id = :id
                    """
                ),
                {"id": str(motivo_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def crear_salida(self, datos: dict[str, Any]) -> UUID:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    insert into salida_almacen
                        (org_id, obra_id, insumo_id, motivo_id, concepto_id,
                         contratista_id, usuario_id, fecha, cantidad, costo)
                    values
                        (cast(current_setting('app.org_id') as uuid),
                         :obra_id, :insumo_id, :motivo_id, :concepto_id,
                         :contratista_id, :usuario_id, :fecha, :cantidad, :costo)
                    returning id
                    """
                ),
                {
                    "obra_id": str(datos["obra_id"]),
                    "insumo_id": str(datos["insumo_id"]),
                    "motivo_id": str(datos["motivo_id"]),
                    "concepto_id": str(datos["concepto_id"]) if datos.get("concepto_id") else None,
                    "contratista_id": (
                        str(datos["contratista_id"]) if datos.get("contratista_id") else None
                    ),
                    "usuario_id": str(datos["usuario_id"]) if datos.get("usuario_id") else None,
                    "fecha": datos["fecha"],
                    "cantidad": datos["cantidad"],
                    "costo": datos["costo"],
                },
            )
        ).scalar_one()
        return fila

    async def consumo_vs_presupuesto(self, obra_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select org_id, obra_id, insumo_id, cant_teorica, cant_real,
                           desviacion_cant, desviacion_pct, costo_valuacion
                    from v_consumo_vs_presupuesto
                    where obra_id = :obra_id
                    """
                ),
                {"obra_id": str(obra_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def listar_salidas(self, obra_id: UUID | None = None) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS_SALIDA}
                    from salida_almacen
                    -- El cast del lado `is null` fija el tipo del parámetro;
                    -- sin él asyncpg levanta AmbiguousParameterError.
                    where cast(:obra_id as uuid) is null
                       or obra_id = cast(:obra_id as uuid)
                    order by fecha desc
                    """
                ),
                {"obra_id": str(obra_id) if obra_id else None},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]
