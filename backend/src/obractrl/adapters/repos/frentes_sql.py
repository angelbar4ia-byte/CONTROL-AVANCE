"""Repositorio del catálogo de frentes.

Spec §12.11 (adaptador de persistencia) · §7.2 · §8.3 (frentes canónicos) ·
§8.7 (semilla editable) · §12.4 (RLS).

`frente` entra por el loop de **catálogo** de
`database/migrations/20260814000012_rls_policies.sql`: lectura para cualquier
usuario de la organización —por eso `GET /frentes` es de todos los roles
(§11.2)— y escritura solo para `app.es_config()` (§5.1). Ningún método filtra
por `org_id` a mano.

Solo hay lectura: el catálogo de frentes es semilla editable (§8.7), se siembra
con los ocho canónicos del §8.3 y se administra desde Configuración, no desde
este módulo.
"""

from __future__ import annotations

from typing import Any

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
