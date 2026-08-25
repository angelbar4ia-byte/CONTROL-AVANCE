"""Repositorio del catálogo de cuadrillas.

Spec §12.11 (adaptador de persistencia) · §7.6 (cuadrilla) · §10.6 (cargador
de mano de obra da de alta la cuadrilla que trae el archivo) · §12.4 (RLS).

`cuadrilla` está en el mismo bloque de `rls_policies`
(`database/migrations/20260814000012`) que `unidad`/`familia`: lectura para
cualquier usuario de la organización, escritura solo para `app.es_config()`.
`org_id` en el INSERT sale de `current_setting('app.org_id')`, igual que en
`unidades_sql.py`/`familias_sql.py`.

Sin pantalla de alta propia todavía (§10.6, hallazgo del cargador de mano de
obra): el único escritor de esta tabla es `AplicadorManoObra`, que la da de
alta con lo mínimo (clave, nombre) — `contratista_id`/`frente_id`/`lider`/
`integrantes` quedan en su default/null hasta que exista esa pantalla.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioCuadrillasSQL"]

_COLUMNAS = """
    id, clave, nombre, rendimiento, estatus
"""


class RepositorioCuadrillasSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def crear(self, datos: dict[str, Any]) -> UUID:
        """Alta de cuadrilla (§10.6, dada de alta por el cargador de mano de
        obra). Claves esperadas: ``clave`` y ``nombre``."""
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into cuadrilla (org_id, clave, nombre)
                    values (cast(current_setting('app.org_id') as uuid),
                            :clave, :nombre)
                    returning id
                    """
                ),
                {"clave": datos["clave"], "nombre": datos["nombre"]},
            )
        ).scalar_one()

    async def listar(self, *, solo_activos: bool = True) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS}
                    from cuadrilla
                    where not cast(:solo_activos as boolean) or estatus = 'activo'
                    order by clave
                    """
                ),
                {"solo_activos": solo_activos},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def actualizar_rendimiento(
        self, cuadrilla_id: UUID, rendimiento: Decimal
    ) -> None:
        """La cuadrilla "asume" el rendimiento teórico del destajo que se le
        asigna (§10.6) — se llama solo cuando el archivo trae el dato."""
        await self._sesion.execute(
            text("update cuadrilla set rendimiento = :rendimiento where id = :id"),
            {"rendimiento": rendimiento, "id": str(cuadrilla_id)},
        )
