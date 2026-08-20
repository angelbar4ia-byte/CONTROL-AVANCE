"""Repositorio del cierre de obra final (§11.3 D, §11.2).

Spec §12.11 (adaptador de persistencia) · §12.4 (RLS) · §11.1 (ningún módulo
lee las tablas de otro).

## El estado que el dominio necesita, en una consulta

`evaluar_pendientes` pregunta por cinco contextos —avance, actividades, cierres
de actividad, estimaciones, incidencias, expediente y evaluaciones— para decidir
si una obra se puede entregar. Pedirlos por separado serían siete viajes para
responder una sola pregunta, y además abriría una ventana entre el primero y el
último en la que el estado cambia: se contaría el avance de antes con las
incidencias de después.

Aquí es una consulta con `lateral`, igual que la Torre. **No filtra por `org_id`
a mano**: cada subconsulta pasa por la política de su tabla, así que el estado
que se evalúa es el que ve quien pregunta.

## Por qué el cierre no vive en `cierres_sql.py`

Ese es el cierre **de actividad** (§11.3 C): otro flujo, otros roles, otra
tabla. Comparten la palabra y nada más; juntarlos habría hecho un repositorio
que responde a dos preguntas distintas según el método.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.application.puertos.repositorios import RegistroNoEncontrado

__all__ = ["CierreDeObraNoModificado", "RepositorioCierresDeObraSQL"]


class CierreDeObraNoModificado(RegistroNoEncontrado):
    """El `UPDATE` acotado no afectó ninguna fila (§12.4).

    O el cierre ya no existe, o la obra salió del alcance de quien escribe.
    Las dos se ven igual y las dos son un 404.
    """


_COLUMNAS = """
    co.id, co.obra_id, co.estatus, co.fecha, co.acta, co.evidencias,
    co.abierto_por, co.created_at, o.clave as obra_clave, o.estatus as obra_estatus
"""


class RepositorioCierresDeObraSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    # --- El acta -------------------------------------------------------

    async def abrir(self, *, obra_id: UUID, abierto_por: UUID) -> UUID:
        """Abre el acta en `en_proceso` (§11.3 D.1).

        `on conflict do nothing` sobre `uq_cierre_obra`: una obra tiene **un**
        cierre. Abrirlo dos veces es la misma intención expresada dos veces, no
        un error — y sin esto, un doble clic daría un 500 por violación de
        unicidad. El `select` posterior devuelve el que quedó, sea el nuevo o el
        que ya estaba.
        """
        cierre_id = uuid4()
        await self._sesion.execute(
            text(
                """
                insert into cierre_obra (id, org_id, obra_id, abierto_por)
                values (:id, cast(current_setting('app.org_id') as uuid),
                        :obra_id, :abierto_por)
                on conflict on constraint uq_cierre_obra do nothing
                """
            ),
            {
                "id": str(cierre_id),
                "obra_id": str(obra_id),
                "abierto_por": str(abierto_por),
            },
        )
        fila = (
            await self._sesion.execute(
                text("select id from cierre_obra where obra_id = :obra_id"),
                {"obra_id": str(obra_id)},
            )
        ).first()
        if fila is None:
            # Defensa, no el camino normal: cuando la obra no es visible, la
            # política rechaza el `INSERT` con `insufficient_privilege` y la
            # excepción sube desde ahí (§12.4). Esto cubre el caso raro de que
            # el `on conflict do nothing` se trague una fila que después no se
            # puede leer.
            raise CierreDeObraNoModificado(
                f"La obra {obra_id} no existe o está fuera de tu alcance."
            )
        return UUID(str(fila.id))

    async def obtener(self, cierre_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS}
                      from cierre_obra co
                      join obra o on o.id = co.obra_id
                     where co.id = :id
                    """
                ),
                {"id": str(cierre_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def obtener_de_obra(self, obra_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS}
                      from cierre_obra co
                      join obra o on o.id = co.obra_id
                     where co.obra_id = :obra_id
                    """
                ),
                {"obra_id": str(obra_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def listar(self, *, estatus: str | None = None) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS}
                      from cierre_obra co
                      join obra o on o.id = co.obra_id
                     where (cast(:estatus as estatus_cierre_obra) is null
                            or co.estatus = cast(:estatus as estatus_cierre_obra))
                     order by co.estatus, o.clave
                    """
                ),
                {"estatus": estatus},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def cerrar(self, cierre_id: UUID, *, fecha: date, acta: str | None) -> None:
        resultado = await self._sesion.execute(
            text(
                """
                update cierre_obra
                   set estatus = 'cerrada', fecha = :fecha,
                       acta = coalesce(:acta, acta)
                 where id = :id and estatus = 'en_proceso'
                """
            ),
            {"id": str(cierre_id), "fecha": fecha, "acta": acta},
        )
        if resultado.rowcount == 0:
            # O no existe, o salió del alcance, o **ya estaba cerrada**. El
            # `and estatus = 'en_proceso'` es lo que impide que dos peticiones
            # simultáneas la cierren dos veces y publiquen el evento dos veces.
            raise CierreDeObraNoModificado(
                f"El cierre {cierre_id} no existe, ya está cerrado o está fuera "
                f"de tu alcance."
            )

    # --- Participación -------------------------------------------------

    async def participar(
        self,
        *,
        cierre_obra_id: UUID,
        usuario_id: UUID,
        rol: str,
        comentario: str | None,
        evidencias: list[str],
    ) -> UUID:
        """Registra la parte de un rol (§11.3 D.2).

        Sin `on conflict`: `uq_cierre_obra_participacion` es por `(cierre, rol)`
        y repetir **sí** es un error que hay que decir —el dominio lo detecta
        antes, y esto es la red de la base.
        """
        participacion_id = uuid4()
        await self._sesion.execute(
            text(
                """
                insert into cierre_obra_participacion
                    (id, org_id, cierre_obra_id, usuario_id, rol, comentario,
                     evidencias)
                values
                    (:id, cast(current_setting('app.org_id') as uuid),
                     :cierre_obra_id, :usuario_id, cast(:rol as rol_usuario),
                     :comentario, cast(:evidencias as jsonb))
                """
            ),
            {
                "id": str(participacion_id),
                "cierre_obra_id": str(cierre_obra_id),
                "usuario_id": str(usuario_id),
                "rol": rol,
                "comentario": comentario,
                "evidencias": _json(evidencias),
            },
        )
        return participacion_id

    async def participaciones(self, cierre_obra_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select p.id, p.rol, p.usuario_id, p.comentario, p.evidencias,
                           p.fecha, u.nombre as usuario_nombre
                      from cierre_obra_participacion p
                      left join usuario u on u.id = p.usuario_id
                     where p.cierre_obra_id = :id
                     order by p.fecha
                    """
                ),
                {"id": str(cierre_obra_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    # --- El estado que decide si se puede entregar ---------------------

    async def estado_de_obra(self, obra_id: UUID) -> dict[str, Any] | None:
        """Lo que `evaluar_pendientes` necesita, en una consulta.

        Siete preguntas de cinco contextos. En viajes separados, además de
        costar siete, dejarían una ventana en la que el estado cambia: se
        contaría el avance de antes con las incidencias de después.
        """
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select
                        o.id as obra_id,
                        o.clave as obra_clave,
                        o.estatus as obra_estatus,
                        o.avance_pct,
                        coalesce(a.sin_concluir, 0)   as actividades_sin_concluir,
                        coalesce(a.total, 0)          as actividades,
                        coalesce(sc.pendientes, 0)    as cierres_pendientes,
                        coalesce(e.sin_validar, 0)    as estimaciones_sin_validar,
                        coalesce(i.abiertas, 0)       as incidencias_abiertas,
                        coalesce(i.detienen, 0)       as incidencias_detienen,
                        coalesce(d.documentos, 0)     as documentos_expediente,
                        coalesce(ev.finales, 0)       as evaluaciones_finales
                      from obra o
                      left join lateral (
                          select count(*) as total,
                                 count(*) filter (
                                     where act.estatus <> 'concluida'
                                 ) as sin_concluir
                            from actividad act
                           where act.obra_id = o.id
                      ) a on true
                      left join lateral (
                          select count(*) as pendientes
                            from solicitud_cierre s
                            join actividad act2 on act2.id = s.actividad_id
                           where act2.obra_id = o.id
                             and s.estatus in ('solicitada', 'autorizada')
                      ) sc on true
                      left join lateral (
                          select count(*) as sin_validar
                            from estimacion est
                           where est.obra_id = o.id
                             and est.estatus <> 'validada'
                      ) e on true
                      left join lateral (
                          select count(*) as abiertas,
                                 count(*) filter (
                                     where inc.impacto = 'detiene'
                                 ) as detienen
                            from incidencia inc
                           where inc.obra_id = o.id
                             and inc.estatus in ('abierta', 'programada',
                                                 'en_atencion', 'cierre_solicitado')
                      ) i on true
                      left join lateral (
                          select count(*) as documentos
                            from expediente_doc doc
                           where doc.obra_id = o.id
                      ) d on true
                      left join lateral (
                          select count(*) as finales
                            from evaluacion evl
                           where evl.obra_id = o.id
                             and evl.nivel = 'final'
                      ) ev on true
                     where o.id = :obra_id
                    """
                ),
                {"obra_id": str(obra_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None


def _json(valor: list[str]) -> str:
    import json

    return json.dumps(valor)
