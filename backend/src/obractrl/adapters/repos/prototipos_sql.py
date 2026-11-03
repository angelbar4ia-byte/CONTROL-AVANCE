"""Repositorio de prototipos (modelos de vivienda).

Spec §12.11 (adaptador de persistencia) · §7.2 · §7.4 (árbol WBS) · §12.4 (RLS).

`prototipo` entra por el loop de **catálogo** de
`database/migrations/20260814000012_rls_policies.sql`: alcance de
organización —lo lee cualquier usuario de la org— y escritura restringida a
`app.es_config()` (Control de obra y Super intendente, §5.1). Ningún método de
aquí filtra por `org_id` a mano; `org_id` en el INSERT sale de
`current_setting('app.org_id')`.

Como el predicado de `SELECT` es solo de organización, el `RETURNING` del alta
es seguro (no depende de ver la fila recién insertada, a diferencia de
`proyectos_sql.py`).

El árbol WBS del prototipo no se lee aquí sino en `obras_sql.py`
(`arbol_prototipo`), donde vive el workflow A que lo consume (§11.3 A).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioPrototiposSQL"]

_COLUMNAS = """
    id, proyecto_id, clave, nombre, m2, niveles, recamaras, plantas
"""


class RepositorioPrototiposSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def crear(self, datos: dict[str, Any]) -> UUID:
        """Alta de prototipo (§11.2, roles C y SI).

        Claves esperadas: ``proyecto_id``, ``clave`` y ``nombre``, ya
        normalizados por `domain.proyectos.reglas.Prototipo`. Opcionales:
        ``m2``, ``niveles``, ``recamaras``.
        """
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into prototipo
                        (org_id, proyecto_id, clave, nombre, m2, niveles, recamaras, plantas, de_una_obra)
                    values
                        (cast(current_setting('app.org_id') as uuid),
                         :proyecto_id, :clave, :nombre, :m2, :niveles, :recamaras,
                         :plantas, :de_una_obra)
                    returning id
                    """
                ),
                {
                    "proyecto_id": (
                        str(datos["proyecto_id"]) if datos.get("proyecto_id") else None
                    ),
                    "clave": datos["clave"],
                    "nombre": datos["nombre"],
                    "m2": datos.get("m2"),
                    "niveles": datos.get("niveles"),
                    "recamaras": datos.get("recamaras"),
                    "plantas": datos.get("plantas"),
                    "de_una_obra": bool(datos.get("de_una_obra", False)),
                },
            )
        ).scalar_one()

    async def obtener(self, prototipo_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} from prototipo where id = :id"),
                {"id": str(prototipo_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def actualizar(self, prototipo_id: UUID, campos: dict[str, Any]) -> None:
        """Solo la usa el cargador masivo (§7.2, extensión propia): un
        renglón cuya clave ya existía en el archivo actualiza `nombre`, `m2`,
        `niveles` y `recamaras` — nunca `proyecto_id` ni `clave`, que son la
        identidad de la fila y no algo que una carga reasigne.
        """
        await self._sesion.execute(
            text(
                """
                update prototipo
                   set nombre    = :nombre,
                       m2        = :m2,
                       niveles   = :niveles,
                       recamaras = :recamaras
                 where id = :id
                """
            ),
            {
                "id": str(prototipo_id),
                "nombre": campos["nombre"],
                "m2": campos.get("m2"),
                "niveles": campos.get("niveles"),
                "recamaras": campos.get("recamaras"),
            },
        )

    async def listar(self, proyecto_id: UUID | None = None) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS}
                    from prototipo
                    -- El cast del lado `is null` fija el tipo del parámetro;
                    -- sin él asyncpg levanta AmbiguousParameterError.
                    -- Los prototipos de todos los proyectos (proyecto_id nulo,
                    -- D-614) se ven desde cualquier proyecto.
                    where cast(:proyecto_id as uuid) is null
                       or proyecto_id is null
                       or proyecto_id = cast(:proyecto_id as uuid)
                    order by clave
                    """
                ),
                {"proyecto_id": str(proyecto_id) if proyecto_id else None},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]
