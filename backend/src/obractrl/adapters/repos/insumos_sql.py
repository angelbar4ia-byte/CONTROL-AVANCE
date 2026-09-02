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
    origen, iva_aplica, factor_conversion, estatus,
    cuadrilla_id, rendimiento_teorico, dias_entrega
"""

_CAMPOS_EDITABLES: dict[str, str] = {
    "descripcion": "descripcion = :descripcion",
    "unidad_id": "unidad_id = cast(:unidad_id as uuid)",
    "familia_id": "familia_id = cast(:familia_id as uuid)",
    "costo_base": "costo_base = cast(:costo_base as numeric)",
    "costo_base_actualizado": (
        "costo_base_actualizado = cast(:costo_base_actualizado as numeric)"
    ),
    "costo_promedio_almacen": (
        "costo_promedio_almacen = cast(:costo_promedio_almacen as numeric)"
    ),
    "costo_ultimo": "costo_ultimo = cast(:costo_ultimo as numeric)",
    "origen": "origen = :origen",
    "iva_aplica": "iva_aplica = cast(:iva_aplica as boolean)",
    "factor_conversion": "factor_conversion = cast(:factor_conversion as numeric)",
    "estatus": "estatus = cast(:estatus as estatus_registro)",
    "cuadrilla_id": "cuadrilla_id = cast(:cuadrilla_id as uuid)",
    "rendimiento_teorico": (
        "rendimiento_teorico = cast(:rendimiento_teorico as numeric)"
    ),
    "dias_entrega": "dias_entrega = cast(:dias_entrega as smallint)",
}
"""Campos que una edición puede tocar. La `clave` no está: es la identidad
del registro (§3.3). El diccionario es también la lista blanca que evita
armar SQL con nombres que vengan de un archivo."""


class RepositorioInsumosSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def crear(self, datos: dict[str, Any]) -> UUID:
        """Alta de insumo (§11.2 `POST /insumos` y `POST /materiales`, rol C).

        Claves esperadas: ``tipo``, ``clave`` y ``descripcion``, ya
        normalizados por `domain.catalogos.reglas.Insumo`. Opcionales:
        ``unidad_id``, ``familia_id``, ``costo_base``, ``iva_aplica``,
        ``factor_conversion``, ``cuadrilla_id``, ``rendimiento_teorico``
        (§10.6, mano de obra).
        """
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into insumo
                        (org_id, tipo, clave, descripcion, unidad_id, familia_id,
                         costo_base, iva_aplica, factor_conversion,
                         cuadrilla_id, rendimiento_teorico, dias_entrega)
                    values (cast(current_setting('app.org_id') as uuid),
                            cast(:tipo as tipo_insumo), :clave, :descripcion,
                            cast(:unidad_id as uuid), cast(:familia_id as uuid),
                            -- El cast a numeric no es decorativo: sin él
                            -- asyncpg infiere el tipo del parámetro por el
                            -- literal entero del `coalesce` y un Decimal
                            -- perdería sus decimales en silencio.
                            coalesce(cast(:costo_base as numeric), 0),
                            cast(:iva_aplica as boolean),
                            coalesce(cast(:factor_conversion as numeric), 1),
                            cast(:cuadrilla_id as uuid),
                            cast(:rendimiento_teorico as numeric),
                            cast(:dias_entrega as smallint))
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
                    "cuadrilla_id": (
                        str(datos["cuadrilla_id"]) if datos.get("cuadrilla_id") else None
                    ),
                    "rendimiento_teorico": datos.get("rendimiento_teorico"),
                    "dias_entrega": datos.get("dias_entrega"),
                },
            )
        ).scalar_one()

    async def crear_o_existente(self, datos: dict[str, Any]) -> UUID:
        """Como `crear`, pero idempotente por clave (§3.3, §8.7).

        Para el auto-alta de una carga (`_resolver_o_dar_de_alta` y los
        `_dar_de_alta_insumo` de CPU/Presupuesto, en
        `application.casos_uso.aplicar_carga`): dos cargas que auto-crean el
        mismo insumo nuevo casi al mismo tiempo no deben tronar con
        `UniqueViolationError` — la clave manda, así que la segunda solo
        obtiene el id del que la primera ya dio de alta, sin pisar sus
        datos. `POST /insumos`/`POST /materiales` (alta manual) siguen
        usando `crear`, que sí debe fallar si la clave ya existe.
        """
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into insumo
                        (org_id, tipo, clave, descripcion, unidad_id, familia_id,
                         costo_base, iva_aplica, factor_conversion,
                         cuadrilla_id, rendimiento_teorico, dias_entrega)
                    values (cast(current_setting('app.org_id') as uuid),
                            cast(:tipo as tipo_insumo), :clave, :descripcion,
                            cast(:unidad_id as uuid), cast(:familia_id as uuid),
                            coalesce(cast(:costo_base as numeric), 0),
                            cast(:iva_aplica as boolean),
                            coalesce(cast(:factor_conversion as numeric), 1),
                            cast(:cuadrilla_id as uuid),
                            cast(:rendimiento_teorico as numeric),
                            cast(:dias_entrega as smallint))
                    on conflict (org_id, clave) do update set clave = excluded.clave
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
                    "cuadrilla_id": (
                        str(datos["cuadrilla_id"]) if datos.get("cuadrilla_id") else None
                    ),
                    "rendimiento_teorico": datos.get("rendimiento_teorico"),
                    "dias_entrega": datos.get("dias_entrega"),
                },
            )
        ).scalar_one()

    async def actualizar(self, insumo_id: UUID, cambios: dict[str, Any]) -> None:
        """Edición parcial; solo las claves presentes en ``cambios`` se escriben.

        La usan los cargadores (§10.6): el de materiales para actualizar lo
        que ya existe en el modo Actualizar (§10.2), y el de almacén para
        bajar la valuación del §10.5 —`costo_ultimo` y
        `costo_base_actualizado` = el costo último más reciente—. La `clave`
        **no** es editable: es la identidad del registro (§3.3); cambiarla
        sería otro insumo, no una edición.
        """
        asignaciones = [
            _CAMPOS_EDITABLES[campo] for campo in cambios if campo in _CAMPOS_EDITABLES
        ]
        if not asignaciones:
            return

        parametros: dict[str, Any] = {"id": str(insumo_id)}
        for campo in cambios:
            if campo not in _CAMPOS_EDITABLES:
                continue
            valor = cambios[campo]
            parametros[campo] = (
                str(valor) if campo.endswith("_id") and valor is not None else valor
            )

        await self._sesion.execute(
            text(
                f"update insumo set {', '.join(asignaciones)} where id = :id"
            ),
            parametros,
        )

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
