"""Repositorio de escritura del árbol WBS del prototipo (§7.4).

Spec §12.11 (adaptador de persistencia) · §10.8 (idempotencia de la carga) ·
§12.4 (RLS).

Primer escritor de `prototipo_nodo` — hasta el cargador de presupuesto
jerárquico, la tabla solo se leía (`RepositorioObras.arbol_prototipo`,
otra fachada, §11.1). El `upsert` por `(org_id, prototipo_id, clave)`
(`uq_prototipo_nodo_clave`, migración 0030) es lo que conserva el `id` de un
nodo entre recargas: regenerarlo rompería en silencio
`programa_base_item.prototipo_nodo_id` y `actividad.prototipo_nodo_id`, que
lo referencian por igualdad literal.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioPrototipoNodoSQL"]


class RepositorioPrototipoNodoSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def por_prototipo(self, prototipo_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select id, parent_id, tipo, nombre, clave, concepto_id,
                           nivel_id, etapa_id, orden, cantidad, ponderacion
                      from prototipo_nodo
                     where org_id = cast(current_setting('app.org_id') as uuid)
                       and prototipo_id = :prototipo_id
                    """
                ),
                {"prototipo_id": str(prototipo_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def upsert(
        self, prototipo_id: UUID, *, clave: str | None, datos: dict[str, Any]
    ) -> tuple[UUID, bool]:
        """Inserta o actualiza por `(org_id, prototipo_id, clave)`.

        Claves esperadas en ``datos``: ``parent_id``, ``tipo``, ``nombre``,
        opcionales ``concepto_id``, ``nivel_id``, ``etapa_id``, ``orden``,
        ``cantidad``. Sin ``clave`` (nodo sin identidad natural) siempre
        inserta — no hay match posible.

        ``xmax = 0`` en el `RETURNING` distingue insert de update: es el
        idioma estándar de Postgres para un `INSERT ... ON CONFLICT ... DO
        UPDATE` de una sola sentencia.
        """
        parametros = {
            "prototipo_id": str(prototipo_id),
            "clave": clave,
            "parent_id": str(datos["parent_id"]) if datos.get("parent_id") else None,
            "tipo": datos["tipo"],
            "nombre": datos["nombre"],
            "concepto_id": str(datos["concepto_id"]) if datos.get("concepto_id") else None,
            "nivel_id": str(datos["nivel_id"]) if datos.get("nivel_id") else None,
            "etapa_id": str(datos["etapa_id"]) if datos.get("etapa_id") else None,
            "orden": datos.get("orden", 0),
            "cantidad": datos.get("cantidad", 0),
        }

        if clave is None:
            fila = (
                await self._sesion.execute(
                    text(
                        """
                        insert into prototipo_nodo
                            (org_id, prototipo_id, parent_id, tipo, nombre, clave,
                             concepto_id, nivel_id, etapa_id, orden, cantidad)
                        values
                            (cast(current_setting('app.org_id') as uuid), :prototipo_id,
                             cast(:parent_id as uuid), cast(:tipo as tipo_prototipo_nodo),
                             :nombre, null, cast(:concepto_id as uuid),
                             cast(:nivel_id as uuid), cast(:etapa_id as uuid),
                             :orden, :cantidad)
                        returning id
                        """
                    ),
                    parametros,
                )
            ).one()
            return fila.id, True

        fila = (
            await self._sesion.execute(
                text(
                    """
                    insert into prototipo_nodo
                        (org_id, prototipo_id, parent_id, tipo, nombre, clave,
                         concepto_id, nivel_id, etapa_id, orden, cantidad)
                    values
                        (cast(current_setting('app.org_id') as uuid), :prototipo_id,
                         cast(:parent_id as uuid), cast(:tipo as tipo_prototipo_nodo),
                         :nombre, :clave, cast(:concepto_id as uuid),
                         cast(:nivel_id as uuid), cast(:etapa_id as uuid),
                         :orden, :cantidad)
                    on conflict (org_id, prototipo_id, clave) where clave is not null
                    do update set
                        parent_id   = excluded.parent_id,
                        tipo        = excluded.tipo,
                        nombre      = excluded.nombre,
                        concepto_id = excluded.concepto_id,
                        nivel_id    = excluded.nivel_id,
                        etapa_id    = excluded.etapa_id,
                        orden       = excluded.orden,
                        cantidad    = excluded.cantidad
                    returning id, (xmax = 0) as es_alta
                    """
                ),
                parametros,
            )
        ).one()
        return fila.id, bool(fila.es_alta)
