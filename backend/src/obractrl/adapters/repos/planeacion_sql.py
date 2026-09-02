"""Repositorio de la planeación por obra (§8.3, §11.3, §12.4).

`frente_obra` entra por el loop `por_obra` de
`database/migrations/20260814000012_rls_policies.sql` —el mismo predicado que
`actividad`—: ningún método de aquí filtra por `org_id` u `obra_id` para
decidir qué es visible, eso lo impone la base. `org_id` en el INSERT sale de
`current_setting('app.org_id')`.

Qué es cada cosa, porque son dos tablas que se parecen y no son lo mismo:

* `contratista_frente` (0005) — qué frentes **sabe hacer** un contratista. Es
  capacidad de catálogo y no cambia de obra en obra.
* `frente_obra` (0046) — quién lleva ese frente **en esta obra**. Es el trato,
  y puede ser otro en la obra de al lado.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioPlaneacionSQL"]


class RepositorioPlaneacionSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def frentes_de_obra(self, obra_id: UUID) -> list[dict[str, Any]]:
        """Lo asignado en esa obra, con el nombre del contratista resuelto.

        `left join` sobre `contratista`: un frente puede estar planeado —con sus
        cuadrillas ya decididas— antes de saber quién lo va a hacer, que es
        justo cuando se cotiza.
        """
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select fo.id, fo.frente_id, fo.contratista_id,
                           fo.cuadrillas_plan, fo.notas,
                           f.clave  as frente_clave,
                           f.nombre as frente_nombre,
                           c.razon_social as contratista_nombre
                      from frente_obra fo
                      join frente f on f.id = fo.frente_id
                      left join contratista c on c.id = fo.contratista_id
                     where fo.obra_id = :obra_id
                     order by f.orden, f.clave
                    """
                ),
                {"obra_id": str(obra_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def asignar_frente(
        self,
        *,
        obra_id: UUID,
        frente_id: UUID,
        contratista_id: UUID | None,
        cuadrillas_plan: int | None,
        notas: str | None,
    ) -> UUID:
        """Deja el trato de ese frente en esa obra. Idempotente por el par.

        `on conflict do update` y no un alta: asignar el frente dos veces es
        cambiar de contratista, no crear un segundo trato. La única de la 0046
        (`uq_frente_obra`) es lo que lo hace posible.

        Los tres campos se escriben aunque vengan nulos: vaciar el contratista
        —"ya no sé quién lo lleva"— es un cambio tan válido como ponerlo, y un
        `coalesce` lo haría imposible.
        """
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into frente_obra
                        (org_id, obra_id, frente_id, contratista_id,
                         cuadrillas_plan, notas)
                    values (cast(current_setting('app.org_id') as uuid),
                            cast(:obra_id as uuid), cast(:frente_id as uuid),
                            cast(:contratista_id as uuid),
                            cast(:cuadrillas_plan as smallint), :notas)
                    on conflict (obra_id, frente_id) do update set
                        contratista_id  = excluded.contratista_id,
                        cuadrillas_plan = excluded.cuadrillas_plan,
                        notas           = excluded.notas
                    returning id
                    """
                ),
                {
                    "obra_id": str(obra_id),
                    "frente_id": str(frente_id),
                    "contratista_id": str(contratista_id) if contratista_id else None,
                    "cuadrillas_plan": cuadrillas_plan,
                    "notas": notas,
                },
            )
        ).scalar_one()

    async def dias_habiles_de_obra(self, obra_id: UUID) -> list[int] | None:
        """Días hábiles del cronograma de la obra (§7.5, migración 0040).

        `None` si la obra todavía no tiene programa instanciado: el dominio cae
        a semana natural (`CalendarioLaboral.de(None)`), que es su decisión y no
        la de un `coalesce` en SQL.
        """
        return await self._sesion.scalar(
            text(
                "select dias_habiles from programa_obra "
                "where obra_id = :obra_id and vigente"
            ),
            {"obra_id": str(obra_id)},
        )
