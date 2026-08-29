"""Repositorio del árbol de familias.

Spec §12.11 (adaptador de persistencia) · §7.3 · §3.5 (la familia define el
IVA) · §10.1 (familias de materiales / conceptos) · §12.4 (RLS).

`familia` está en el bloque A de `rls_policies`
(`database/migrations/20260814000012`): lectura para toda la organización,
escritura solo para `app.es_config()`. Ningún método filtra por `org_id` a
mano; `org_id` en el INSERT sale de `current_setting('app.org_id')`, igual
que en `unidades_sql.py`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioFamiliasSQL"]

_COLUMNAS = """
    id, parent_id, clave, nombre, aplica_a, iva_aplica, estatus
"""

_CAMPOS_EDITABLES: dict[str, str] = {
    "nombre": "nombre = :nombre",
    "parent_id": "parent_id = cast(:parent_id as uuid)",
    "aplica_a": "aplica_a = :aplica_a",
    "iva_aplica": "iva_aplica = :iva_aplica",
    "estatus": "estatus = cast(:estatus as estatus_registro)",
}
"""Lista blanca de campos editables por `actualizar`; también evita armar
SQL con nombres que vengan de un archivo externo. La `clave` no está: es
la identidad (§3.3)."""


class RepositorioFamiliasSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def crear(self, datos: dict[str, Any]) -> UUID:
        """Alta de familia (§11.2 `POST /familias`, rol C).

        Claves esperadas: ``clave`` y ``nombre``, ya normalizados por
        `domain.catalogos.reglas.Familia`. Opcionales: ``parent_id``,
        ``aplica_a``, ``iva_aplica``.
        """
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into familia
                        (org_id, parent_id, clave, nombre, aplica_a, iva_aplica)
                    values (cast(current_setting('app.org_id') as uuid),
                            cast(:parent_id as uuid), :clave, :nombre,
                            -- El cast fija el tipo del parámetro: sin él
                            -- asyncpg lo infiere del literal del `coalesce`.
                            coalesce(cast(:aplica_a as text), 'material'),
                            coalesce(cast(:iva_aplica as boolean), true))
                    returning id
                    """
                ),
                {
                    "parent_id": (
                        str(datos["parent_id"]) if datos.get("parent_id") else None
                    ),
                    "clave": datos["clave"],
                    "nombre": datos["nombre"],
                    "aplica_a": datos.get("aplica_a"),
                    "iva_aplica": datos.get("iva_aplica"),
                },
            )
        ).scalar_one()

    async def crear_o_existente(self, datos: dict[str, Any]) -> UUID:
        """Como `crear`, pero idempotente por clave (§3.3, §8.7).

        Para el auto-alta de una carga (`_resolver_o_dar_de_alta`,
        `application.casos_uso.aplicar_carga`): dos cargas que auto-crean la
        misma familia nueva casi al mismo tiempo no deben tronar con
        `UniqueViolationError` — la clave manda, así que la segunda solo
        obtiene el id de la que la primera ya dio de alta (sin tocar su
        `aplica_a`: el conflicto no reescribe nada, solo devuelve el id).
        `POST /familias` (alta manual) sigue usando `crear`, que sí debe
        fallar si la clave ya existe.
        """
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into familia
                        (org_id, parent_id, clave, nombre, aplica_a, iva_aplica)
                    values (cast(current_setting('app.org_id') as uuid),
                            cast(:parent_id as uuid), :clave, :nombre,
                            coalesce(cast(:aplica_a as text), 'material'),
                            coalesce(cast(:iva_aplica as boolean), true))
                    on conflict (org_id, clave) do update set clave = excluded.clave
                    returning id
                    """
                ),
                {
                    "parent_id": (
                        str(datos["parent_id"]) if datos.get("parent_id") else None
                    ),
                    "clave": datos["clave"],
                    "nombre": datos["nombre"],
                    "aplica_a": datos.get("aplica_a"),
                    "iva_aplica": datos.get("iva_aplica"),
                },
            )
        ).scalar_one()

    async def obtener(self, familia_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} from familia where id = :id"),
                {"id": str(familia_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def listar(
        self, *, aplica_a: str | None = None, solo_activos: bool = True
    ) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS}
                    from familia
                    -- El cast del lado `is null` fija el tipo del parámetro;
                    -- sin él asyncpg levanta AmbiguousParameterError.
                    where (cast(:aplica_a as text) is null
                           or aplica_a = cast(:aplica_a as text))
                      and (not cast(:solo_activos as boolean) or estatus = 'activo')
                    order by clave
                    """
                ),
                {"aplica_a": aplica_a, "solo_activos": solo_activos},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def actualizar(self, familia_id: UUID, cambios: dict[str, Any]) -> None:
        """Edición parcial; solo las claves presentes en ``cambios`` se
        escriben. La `clave` no es editable — es la identidad (§3.3).

        La usa el cargador dedicado (§10.6) cuando el archivo trae una
        familia que ya existe: en modo Actualizar se refresca `nombre` (y
        `estatus` para la baja lógica de modo Reemplazar) — a diferencia de
        `crear_o_existente`, que en conflicto es un no-op a propósito.
        """
        asignaciones = [
            _CAMPOS_EDITABLES[campo] for campo in cambios if campo in _CAMPOS_EDITABLES
        ]
        if not asignaciones:
            return

        parametros: dict[str, Any] = {"id": str(familia_id)}
        for campo in cambios:
            if campo in _CAMPOS_EDITABLES:
                parametros[campo] = cambios[campo]

        await self._sesion.execute(
            text(f"update familia set {', '.join(asignaciones)} where id = :id"),
            parametros,
        )
