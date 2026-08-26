"""Repositorio del catálogo de unidades.

Spec §12.11 (adaptador de persistencia) · §7.3 · §3.5 (unidades con sinónimos
y factor) · §8.7 (semilla editable) · §12.4 (RLS).

`unidad` está en el bloque A de `rls_policies`
(`database/migrations/20260814000012`): **lectura** para cualquier usuario de
la organización (`unidad_select`, `org_id = app.current_org_id()`),
**escritura** solo para `app.es_config()` —Control de obra y Super
intendente—. Ningún método filtra por `org_id` a mano: lo impone la base.
`org_id` en el INSERT sale de `current_setting('app.org_id')`, igual que en
`proyectos_sql.py`.

El `RETURNING` sí es seguro aquí: la política de `SELECT` de un catálogo solo
compara `org_id` —ninguna función `STABLE` que consulte la propia tabla—, así
que la fila recién insertada es visible bajo el snapshot del `INSERT`. Ese es
el problema que obligó a generar el uuid en Python en `proyectos_sql.py`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioUnidadesSQL"]

_COLUMNAS = """
    id, clave, nombre, sinonimos, factor, estatus
"""


class RepositorioUnidadesSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def crear(self, datos: dict[str, Any]) -> UUID:
        """Alta de unidad (§11.2 `POST /unidades`, rol C).

        Claves esperadas: ``clave`` y ``nombre``, ya normalizados por
        `domain.catalogos.reglas.Unidad`. Opcionales: ``sinonimos``, ``factor``.
        """
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into unidad (org_id, clave, nombre, sinonimos, factor)
                    values (cast(current_setting('app.org_id') as uuid),
                            :clave, :nombre,
                            coalesce(cast(:sinonimos as text[]), '{}'),
                            -- El cast no es decorativo: sin él asyncpg infiere
                            -- el tipo del parámetro por el literal del
                            -- `coalesce` y un Decimal viajaría como entero,
                            -- perdiendo los decimales en silencio.
                            coalesce(cast(:factor as numeric), 1))
                    returning id
                    """
                ),
                {
                    "clave": datos["clave"],
                    "nombre": datos["nombre"],
                    "sinonimos": list(datos.get("sinonimos") or []),
                    "factor": datos.get("factor"),
                },
            )
        ).scalar_one()

    async def crear_o_existente(self, datos: dict[str, Any]) -> UUID:
        """Como `crear`, pero idempotente por clave (§3.3, §8.7).

        Para el auto-alta de una carga (`_resolver_o_dar_de_alta`,
        `application.casos_uso.aplicar_carga`): dos cargas que auto-crean la
        misma unidad nueva casi al mismo tiempo no deben tronar con
        `UniqueViolationError` — la clave manda, así que la segunda solo
        obtiene el id de la que la primera ya dio de alta. `POST /unidades`
        (alta manual) sigue usando `crear`, que sí debe fallar si la clave
        ya existe.
        """
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into unidad (org_id, clave, nombre, sinonimos, factor)
                    values (cast(current_setting('app.org_id') as uuid),
                            :clave, :nombre,
                            coalesce(cast(:sinonimos as text[]), '{}'),
                            coalesce(cast(:factor as numeric), 1))
                    on conflict (org_id, clave) do update set clave = excluded.clave
                    returning id
                    """
                ),
                {
                    "clave": datos["clave"],
                    "nombre": datos["nombre"],
                    "sinonimos": list(datos.get("sinonimos") or []),
                    "factor": datos.get("factor"),
                },
            )
        ).scalar_one()

    async def obtener(self, unidad_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} from unidad where id = :id"),
                {"id": str(unidad_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def listar(self, *, solo_activos: bool = True) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS}
                    from unidad
                    where not cast(:solo_activos as boolean) or estatus = 'activo'
                    order by clave
                    """
                ),
                {"solo_activos": solo_activos},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]
