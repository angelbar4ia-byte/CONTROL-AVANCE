"""Repositorio de proyectos.

Spec §12.11 (adaptador de persistencia) · §7.2 (estructura de proyecto) ·
§11.2 (Proyecto · Obra) · §12.4 (RLS).

RLS filtra `proyecto` por alcance de rol (política `proyecto_select`,
`database/migrations/20260814000012`, vía `app.proyecto_visible(id)`): ningún
método de aquí filtra por `org_id` a mano, eso lo impone la base. `org_id` en
los INSERT sale de `current_setting('app.org_id')`, igual que en
`incidencias_sql.py`.

**Por qué el `id` se genera aquí y no con `RETURNING`:** `proyecto_select`
evalúa `app.proyecto_visible(id)`, una función `STABLE` que consulta la tabla
`proyecto`. Postgres aplica las políticas de `SELECT` a la cláusula
`RETURNING` de un `INSERT`, y bajo el snapshot de esa misma sentencia la fila
recién insertada **todavía no es visible** para una función `STABLE` — el
`RETURNING` fallaría siempre, aunque el `INSERT` sea legítimo. Es el mismo
motivo por el que `obra_insert` valida contra el cluster y no contra la obra
(ver el comentario de la migración 0012). Con el uuid generado en Python el
`INSERT` no necesita devolver nada, y la lectura posterior —otra sentencia,
otro snapshot— ya ve la fila. `obras_sql.py` hace lo mismo por la misma razón.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioProyectosSQL"]

_COLUMNAS = """
    id, clave, nombre, ubicacion, inicio, fin_estimado, estatus
"""


class RepositorioProyectosSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def crear(self, datos: dict[str, Any]) -> UUID:
        """Alta de proyecto (§11.2, roles C y SI).

        Claves esperadas en ``datos``: ``clave`` y ``nombre`` (str, ya
        normalizados por `domain.proyectos.reglas.Proyecto`). Opcionales:
        ``ubicacion``, ``inicio``, ``fin_estimado``.
        """
        proyecto_id = uuid4()
        await self._sesion.execute(
            text(
                """
                insert into proyecto
                    (id, org_id, clave, nombre, ubicacion, inicio, fin_estimado)
                values
                    (:id, cast(current_setting('app.org_id') as uuid),
                     :clave, :nombre, :ubicacion, :inicio, :fin_estimado)
                """
            ),
            {
                "id": str(proyecto_id),
                "clave": datos["clave"],
                "nombre": datos["nombre"],
                "ubicacion": datos.get("ubicacion"),
                "inicio": datos.get("inicio"),
                "fin_estimado": datos.get("fin_estimado"),
            },
        )
        return proyecto_id

    async def obtener(self, proyecto_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} from proyecto where id = :id"),
                {"id": str(proyecto_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def listar(self) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} from proyecto order by clave")
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]
