"""Repositorio de insumos (y por tanto de materiales).

Spec §12.11 (adaptador de persistencia) · §7.3 · §10.1 (campos del catálogo
de materiales) · §10.5 (valuación: costo base vs costo de almacén) ·
§3.5 (IVA) · §12.4 (RLS).

**`Material` = `Insumo` con `tipo = 'material'` (§7.3).** No hay tabla ni
repositorio de materiales: `GET /materiales` (§11.2) es `listar(tipo=...)`
con el filtro puesto. Duplicarlo partiría la clave única del catálogo, que es
justo lo que el §3.3 no permite.

`insumo` está en el bloque A de `rls_policies`
(`database/migrations/20260814000012`): lectura para toda la organización,
escritura solo para `app.es_config()`. El `org_id` del INSERT sale de
`current_setting('app.org_id')`.

`iva_aplica` viaja tal cual, **incluido el `None`**: en esta tabla nulo no es
"sin dato" sino "hereda de la familia" (§3.5, `comment on column
insumo.iva_aplica`). Resolverlo es del dominio
(`domain.catalogos.reglas.resolver_iva`), no del SQL.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioInsumosSQL"]

_COLUMNAS = """
    id, tipo, clave, descripcion, unidad_id, familia_id,
    costo_base, costo_base_actualizado, costo_promedio_almacen, costo_ultimo,
    origen, iva_aplica, factor_conversion, estatus
"""


class RepositorioInsumosSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def crear(self, datos: dict[str, Any]) -> UUID:
        """Alta de insumo (§11.2 `POST /insumos` y `POST /materiales`, rol C).

        Claves esperadas: ``tipo``, ``clave`` y ``descripcion``, ya
        normalizados por `domain.catalogos.reglas.Insumo`. Opcionales:
        ``unidad_id``, ``familia_id``, ``costo_base``, ``iva_aplica``,
        ``factor_conversion``.
        """
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into insumo
                        (org_id, tipo, clave, descripcion, unidad_id, familia_id,
                         costo_base, iva_aplica, factor_conversion)
                    values (cast(current_setting('app.org_id') as uuid),
                            cast(:tipo as tipo_insumo), :clave, :descripcion,
                            cast(:unidad_id as uuid), cast(:familia_id as uuid),
                            -- El cast a numeric no es decorativo: sin él
                            -- asyncpg infiere el tipo del parámetro por el
                            -- literal entero del `coalesce` y un Decimal
                            -- perdería sus decimales en silencio.
                            coalesce(cast(:costo_base as numeric), 0),
                            cast(:iva_aplica as boolean),
                            coalesce(cast(:factor_conversion as numeric), 1))
                    returning id
                    """
                ),
                {
                    "tipo": datos["tipo"],
                    "clave": datos["clave"],
                    "descripcion": datos["descripcion"],
                    "unidad_id": (
                        str(datos["unidad_id"]) if datos.get("unidad_id") else None
                    ),
                    "familia_id": (
                        str(datos["familia_id"]) if datos.get("familia_id") else None
                    ),
                    "costo_base": datos.get("costo_base"),
                    "iva_aplica": datos.get("iva_aplica"),
                    "factor_conversion": datos.get("factor_conversion"),
                },
            )
        ).scalar_one()

    async def obtener(self, insumo_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} from insumo where id = :id"),
                {"id": str(insumo_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def listar(
        self,
        *,
        tipo: str | None = None,
        familia_id: UUID | None = None,
        solo_activos: bool = True,
    ) -> list[dict[str, Any]]:
        """Insumos del catálogo; ``tipo='material'`` da los materiales (§7.3)."""
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS}
                    from insumo
                    -- El cast del lado `is null` fija el tipo del parámetro;
                    -- sin él asyncpg levanta AmbiguousParameterError.
                    where (cast(:tipo as tipo_insumo) is null
                           or tipo = cast(:tipo as tipo_insumo))
                      and (cast(:familia_id as uuid) is null
                           or familia_id = cast(:familia_id as uuid))
                      and (not cast(:solo_activos as boolean) or estatus = 'activo')
                    order by clave
                    """
                ),
                {
                    "tipo": tipo,
                    "familia_id": str(familia_id) if familia_id else None,
                    "solo_activos": solo_activos,
                },
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]
