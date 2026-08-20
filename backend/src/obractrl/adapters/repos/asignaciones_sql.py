"""Repositorio de los puentes de alcance: quién ve qué (§4).

Spec §4 (alcance por rol) · §5.1 ("Equipo" · "Asignaciones") · §12.4 (RLS) ·
§12.11 (adaptador de persistencia).

Dos tablas con **permisos distintos**, y la diferencia no es un descuido de la
migración 0012:

· `supervisor_cluster` — la escribe Control de obra y Super intendente
  (`app.es_config()`). Repartir clusters entre supervisores es operación
  diaria.
· `control_proyecto` — **solo** Super intendente. Ese puente decide qué
  proyectos ve un Control de obra, o sea el alcance de quien administra: si
  Control pudiera editarlo, se ampliaría su propio alcance. Es la misma razón
  por la que el trigger de la 0025 no lo deja promoverse.

El residente no tiene puente: llega a su obra por `obra.residente_id`, que se
asigna desde la obra (§4). Por eso aquí no hay un tercer método.

Ningún método filtra por `org_id` a mano: lo impone RLS, y `org_id` en los
INSERT sale de `current_setting('app.org_id')` como en el resto de los repos.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.application.puertos.repositorios import RegistroNoEncontrado

__all__ = ["AsignacionNoRetirada", "RepositorioAsignacionesSQL"]


class AsignacionNoRetirada(RegistroNoEncontrado):
    """El `DELETE` del puente no afectó ninguna fila (§12.4).

    O la asignación ya no existía, o está fuera del alcance de quien la quiso
    retirar. Las dos se ven igual desde aquí y las dos son un 404: decir cuál
    fue sería confirmar la existencia de algo que no se puede ver.
    """


class RepositorioAsignacionesSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    # --- Supervisor ↔ cluster -------------------------------------------

    async def asignar_cluster(self, *, supervisor_id: UUID, cluster_id: UUID) -> None:
        """Le da un cluster a un supervisor (§5.1 "Asignaciones").

        `on conflict do nothing` porque asignar dos veces el mismo cluster es
        la misma intención expresada dos veces, no un error: la pantalla puede
        reenviar y el resultado es el mismo. Sin esto, un doble clic daría un
        500 por violación de unicidad.
        """
        await self._sesion.execute(
            text(
                """
                insert into supervisor_cluster (org_id, supervisor_id, cluster_id)
                values (cast(current_setting('app.org_id') as uuid),
                        :supervisor_id, :cluster_id)
                on conflict (supervisor_id, cluster_id) do nothing
                """
            ),
            {"supervisor_id": str(supervisor_id), "cluster_id": str(cluster_id)},
        )

    async def retirar_cluster(self, *, supervisor_id: UUID, cluster_id: UUID) -> None:
        resultado = await self._sesion.execute(
            text(
                """
                delete from supervisor_cluster
                 where supervisor_id = :supervisor_id
                   and cluster_id = :cluster_id
                """
            ),
            {"supervisor_id": str(supervisor_id), "cluster_id": str(cluster_id)},
        )
        if resultado.rowcount == 0:
            raise AsignacionNoRetirada(
                f"El supervisor {supervisor_id} no tiene asignado el cluster "
                f"{cluster_id}, o está fuera de tu alcance."
            )

    async def clusters_de(self, supervisor_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select c.id, c.clave, c.nombre, c.proyecto_id
                      from supervisor_cluster sc
                      join cluster c on c.id = sc.cluster_id
                     where sc.supervisor_id = :supervisor_id
                     order by c.clave
                    """
                ),
                {"supervisor_id": str(supervisor_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    # --- Control de obra ↔ proyecto -------------------------------------

    async def asignar_proyecto(self, *, usuario_id: UUID, proyecto_id: UUID) -> None:
        """Le da un proyecto a un Control de obra (§5.1, **solo** SI)."""
        await self._sesion.execute(
            text(
                """
                insert into control_proyecto (org_id, usuario_id, proyecto_id)
                values (cast(current_setting('app.org_id') as uuid),
                        :usuario_id, :proyecto_id)
                on conflict (usuario_id, proyecto_id) do nothing
                """
            ),
            {"usuario_id": str(usuario_id), "proyecto_id": str(proyecto_id)},
        )

    async def retirar_proyecto(self, *, usuario_id: UUID, proyecto_id: UUID) -> None:
        resultado = await self._sesion.execute(
            text(
                """
                delete from control_proyecto
                 where usuario_id = :usuario_id
                   and proyecto_id = :proyecto_id
                """
            ),
            {"usuario_id": str(usuario_id), "proyecto_id": str(proyecto_id)},
        )
        if resultado.rowcount == 0:
            raise AsignacionNoRetirada(
                f"El usuario {usuario_id} no tiene asignado el proyecto "
                f"{proyecto_id}, o está fuera de tu alcance."
            )

    async def proyectos_de(self, usuario_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select p.id, p.clave, p.nombre
                      from control_proyecto cp
                      join proyecto p on p.id = cp.proyecto_id
                     where cp.usuario_id = :usuario_id
                     order by p.clave
                    """
                ),
                {"usuario_id": str(usuario_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]
