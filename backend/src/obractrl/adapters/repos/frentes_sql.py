"""Repositorio del catálogo de frentes.

Spec §12.11 (adaptador de persistencia) · §7.2 · §8.3 (frentes canónicos) ·
§8.7 (semilla editable) · §12.4 (RLS).

`frente` entra por el loop de **catálogo** de
`database/migrations/20260814000012_rls_policies.sql`: lectura para cualquier
usuario de la organización —por eso `GET /frentes` es de todos los roles
(§11.2)— y escritura solo para `app.es_config()` (§5.1). Ningún método filtra
por `org_id` a mano.

El catálogo se siembra con los ocho canónicos del §8.3 y **se edita** (§8.7):
una constructora agrupa sus frentes como los trabaja —`INSTALACIONES` cubriendo
hidráulica, sanitaria, eléctrica y gas— y ésa no es la lista de gremios del
spec. Qué etapas cuelgan de cada frente vive en `etapa_constructiva.frente_id`
(0045) y lo escribe `RepositorioNivelesEtapasSQL.asignar_frente`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioFrentesSQL"]

_COLUMNAS = """
    id, clave, nombre, etapa, orden, color, estatus
"""


class RepositorioFrentesSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def listar(self, *, solo_activos: bool = True) -> list[dict[str, Any]]:
        """Catálogo de frentes en su orden de obra (§8.3).

        Ordena por `orden` y desempata por `clave`: `orden` nace en 0 para
        toda la semilla, así que sin el desempate el listado saldría en un
        orden arbitrario entre frentes con el mismo peso.
        """
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS}
                    from frente
                    where not :solo_activos or estatus = 'activo'
                    order by orden, clave
                    """
                ),
                {"solo_activos": solo_activos},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def crear(self, datos: dict[str, Any]) -> UUID:
        """Alta de un frente propio de la organización (§8.7)."""
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into frente (org_id, clave, nombre, orden, color)
                    values (cast(current_setting('app.org_id') as uuid),
                            :clave, :nombre, coalesce(:orden, 0), :color)
                    returning id
                    """
                ),
                {
                    "clave": datos["clave"],
                    "nombre": datos["nombre"],
                    "orden": datos.get("orden"),
                    "color": datos.get("color"),
                },
            )
        ).scalar_one()

    async def actualizar(self, frente_id: UUID, cambios: dict[str, Any]) -> None:
        """Edición parcial; la `clave` no se toca — es la identidad (§3.3).

        Lista blanca como el resto de los catálogos: la clave del dict entra a
        la sentencia, así que solo pueden entrar éstas.
        """
        editables = {
            "nombre": "nombre = :nombre",
            "orden": "orden = cast(:orden as smallint)",
            "color": "color = :color",
            "estatus": "estatus = cast(:estatus as estatus_registro)",
        }
        asignaciones = [sql for campo, sql in editables.items() if campo in cambios]
        if not asignaciones:
            return
        await self._sesion.execute(
            text(f"update frente set {', '.join(asignaciones)} where id = cast(:id as uuid)"),
            {"id": str(frente_id), **{c: cambios[c] for c in editables if c in cambios}},
        )
