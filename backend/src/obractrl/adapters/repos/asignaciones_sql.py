"""Repositorio de los puentes de alcance: quién ve qué (§4).

Spec §4 (alcance por rol) · §5.1 ("Equipo" · "Asignaciones") · §12.4 (RLS) ·
§12.11 (adaptador de persistencia).

CINCO TABLAS, Y SOLO TRES GOBIERNAN ALGO

Desde la migración 0042 el alcance es una cadena de personas:

    Control de obra → Super intendente → Supervisor → Residente → Obra

y cada eslabón tiene su puente:

· `superintendente_usuario` — la escribe **solo Control**. Decide qué ve un
  Super intendente, o sea el alcance de quien administra: si el SI pudiera
  editarla, se ampliaría solo.
· `supervisor_residente`    — Control, y el SI dentro de su propia gente.
· `residente_obra`          — los tres mandos, pero los intermedios solo
  pueden repartir obras que YA ven (`app.puede_repartir_obra`). Traer trabajo
  nuevo a la cadena es de Control, porque es el único que no puede ampliarse.

Las otras dos siguen aquí y ya no deciden nada:

· `supervisor_cluster` — dato territorial: qué manzanas recorre el supervisor.
  Hasta la 0041 era su alcance; ahora su alcance son sus residentes.
· `control_proyecto`   — inerte: Control ve toda la organización. Se conserva
  como registro de qué proyectos abrió o atiende, y porque tiene datos.

Se siguen escribiendo y leyendo a propósito: la pantalla de Asignaciones las
muestra, el trigger de la 0016 sigue llenando `control_proyecto` y quitarlas
haría irreversible el despliegue de la 0042.

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

        DATO TERRITORIAL desde la 0042: esto ya **no** le abre ninguna obra. El
        alcance del supervisor son sus residentes (`asignar_residente`); esto
        registra qué manzanas recorre, que es información útil en pantalla y
        para reportes, pero RLS dejó de leerla.

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

    # --- Super intendente ↔ su gente ------------------------------------

    async def asignar_persona_a_superintendente(
        self, *, superintendente_id: UUID, usuario_id: UUID
    ) -> None:
        """Cuelga a un supervisor o residente de un Super intendente (§4).

        Solo Control puede llegar aquí: la política `superintendente_usuario_*`
        de la 0042 rechaza a todos los demás. El caso de uso lo comprueba antes
        para dar un error legible, pero la garantía es la de la base.
        """
        await self._sesion.execute(
            text(
                """
                insert into superintendente_usuario
                       (org_id, superintendente_id, usuario_id)
                values (cast(current_setting('app.org_id') as uuid),
                        :superintendente_id, :usuario_id)
                on conflict (superintendente_id, usuario_id) do nothing
                """
            ),
            {
                "superintendente_id": str(superintendente_id),
                "usuario_id": str(usuario_id),
            },
        )

    async def retirar_persona_de_superintendente(
        self, *, superintendente_id: UUID, usuario_id: UUID
    ) -> None:
        resultado = await self._sesion.execute(
            text(
                """
                delete from superintendente_usuario
                 where superintendente_id = :superintendente_id
                   and usuario_id = :usuario_id
                """
            ),
            {
                "superintendente_id": str(superintendente_id),
                "usuario_id": str(usuario_id),
            },
        )
        if resultado.rowcount == 0:
            raise AsignacionNoRetirada(
                f"El super intendente {superintendente_id} no tiene asignado a "
                f"{usuario_id}, o está fuera de tu alcance."
            )

    async def gente_de_superintendente(
        self, superintendente_id: UUID
    ) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select u.id, u.nombre, u.email, u.rol
                      from superintendente_usuario su
                      join usuario u on u.id = su.usuario_id
                     where su.superintendente_id = :superintendente_id
                     order by u.rol, u.nombre
                    """
                ),
                {"superintendente_id": str(superintendente_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    # --- Supervisor ↔ sus residentes ------------------------------------

    async def asignar_residente(
        self, *, supervisor_id: UUID, residente_id: UUID
    ) -> None:
        """Le da un residente a un supervisor (§5.1 "Asignaciones").

        Esto **mueve la cartera del residente** al supervisor: sus obras entran
        al alcance del supervisor de inmediato, sin tocar `residente_obra`. Es
        lo que el usuario pidió con "al mover un residente, su cartera lo
        sigue", y es la razón de que el puente sea persona-a-persona y no
        persona-a-cluster.
        """
        await self._sesion.execute(
            text(
                """
                insert into supervisor_residente (org_id, supervisor_id, residente_id)
                values (cast(current_setting('app.org_id') as uuid),
                        :supervisor_id, :residente_id)
                on conflict (supervisor_id, residente_id) do nothing
                """
            ),
            {"supervisor_id": str(supervisor_id), "residente_id": str(residente_id)},
        )

    async def retirar_residente(
        self, *, supervisor_id: UUID, residente_id: UUID
    ) -> None:
        resultado = await self._sesion.execute(
            text(
                """
                delete from supervisor_residente
                 where supervisor_id = :supervisor_id
                   and residente_id = :residente_id
                """
            ),
            {"supervisor_id": str(supervisor_id), "residente_id": str(residente_id)},
        )
        if resultado.rowcount == 0:
            raise AsignacionNoRetirada(
                f"El supervisor {supervisor_id} no tiene asignado al residente "
                f"{residente_id}, o está fuera de tu alcance."
            )

    async def residentes_de(self, supervisor_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select u.id, u.nombre, u.email, u.rol
                      from supervisor_residente sr
                      join usuario u on u.id = sr.residente_id
                     where sr.supervisor_id = :supervisor_id
                     order by u.nombre
                    """
                ),
                {"supervisor_id": str(supervisor_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    # --- Residente ↔ sus obras ------------------------------------------

    async def asignar_obra(self, *, residente_id: UUID, obra_id: UUID) -> None:
        """Le da una obra a un residente (§4, `residente_obra`).

        No toca `obra.residente_id`: de eso se encarga el trigger
        `trg_residente_obra_sincronizar_principal` de la 0042, que le pone la
        etiqueta de principal si la obra no tenía y se la deja al que ya la
        tenía si sí. Duplicar esa decisión aquí sería la forma segura de que un
        día las dos discrepen.
        """
        await self._sesion.execute(
            text(
                """
                insert into residente_obra (org_id, residente_id, obra_id)
                values (cast(current_setting('app.org_id') as uuid),
                        :residente_id, :obra_id)
                on conflict (residente_id, obra_id) do nothing
                """
            ),
            {"residente_id": str(residente_id), "obra_id": str(obra_id)},
        )

    async def retirar_obra(self, *, residente_id: UUID, obra_id: UUID) -> None:
        resultado = await self._sesion.execute(
            text(
                """
                delete from residente_obra
                 where residente_id = :residente_id
                   and obra_id = :obra_id
                """
            ),
            {"residente_id": str(residente_id), "obra_id": str(obra_id)},
        )
        if resultado.rowcount == 0:
            raise AsignacionNoRetirada(
                f"El residente {residente_id} no tiene asignada la obra "
                f"{obra_id}, o está fuera de tu alcance."
            )

    async def obras_de(self, residente_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select o.id, o.clave, o.cluster_id, o.estatus, o.avance_pct,
                           (o.residente_id = ro.residente_id) as es_principal
                      from residente_obra ro
                      join obra o on o.id = ro.obra_id
                     where ro.residente_id = :residente_id
                     order by o.clave
                    """
                ),
                {"residente_id": str(residente_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    # --- Control de obra ↔ proyecto -------------------------------------

    async def asignar_proyecto(self, *, usuario_id: UUID, proyecto_id: UUID) -> None:
        """Le da un proyecto a un Control de obra (§5.1).

        INERTE PARA EL ALCANCE desde la 0042: Control ve toda la organización,
        así que esta fila ya no le abre ni le cierra nada. Se conserva porque
        el trigger de la 0016 la sigue escribiendo y porque es el registro de
        qué proyectos abrió o atiende cada Control.
        """
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
