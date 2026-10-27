"""Repositorio de las reprogramaciones de lo asignado (migración 0072).

Nada aquí filtra por organización u obra para decidir qué es visible: lo impone
RLS (§12.4). `org_id` en el INSERT sale de `current_setting('app.org_id')`.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.application.puertos.repositorios import RegistroNoEncontrado

__all__ = ["RepositorioReprogramacionesSQL", "ReprogramacionNoModificada"]

_COLUMNAS = """
    r.id, r.obra_id, r.actividad_id, r.estatus::text as estatus,
    r.fecha_inicio, r.fecha_termino, r.fecha_inicio_anterior, r.fecha_termino_anterior,
    r.motivo, r.propuesta_por, r.propuesta_rol, r.propuesta_en,
    r.revisada_por, r.revisada_en, r.validada_por, r.validada_en,
    r.aplicada_por, r.aplicada_en, r.rechazada_por, r.rechazada_en, r.motivo_rechazo
"""


_OBSERVACION = """
    select o.id, o.reprogramacion_id, o.obra_id, o.usuario_id, u.nombre as usuario_nombre,
           o.rol, o.texto, o.creada_en
      from reprogramacion_observacion o
      left join usuario u on u.id = o.usuario_id
"""


class ReprogramacionNoModificada(RegistroNoEncontrado):
    """El UPDATE no afectó ninguna fila: la reprogramación ya no existe o salió del alcance."""


class RepositorioReprogramacionesSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def obtener(self, reprogramacion_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS},
                           coalesce(act.descripcion, con.descripcion) as actividad,
                           con.clave                                  as concepto_clave
                      from reprogramacion r
                      join actividad act on act.id = r.actividad_id
                      left join concepto con on con.id = act.concepto_id
                     where r.id = :id
                    """
                ),
                {"id": str(reprogramacion_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def viva_de(self, actividad_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS}
                      from reprogramacion r
                     where r.actividad_id = :actividad_id
                       and r.estatus in ('propuesta', 'revisada', 'validada')
                    """
                ),
                {"actividad_id": str(actividad_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def de_obra(self, obra_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS},
                           coalesce(act.descripcion, con.descripcion) as actividad,
                           con.clave                                  as concepto_clave,
                           ct.razon_social                            as contratista,
                           up.nombre                                  as propuesta_por_nombre,
                           ur.nombre                                  as revisada_por_nombre,
                           uv.nombre                                  as validada_por_nombre,
                           ua.nombre                                  as aplicada_por_nombre,
                           uz.nombre                                  as rechazada_por_nombre
                      from reprogramacion r
                      join actividad act on act.id = r.actividad_id
                      left join concepto con on con.id = act.concepto_id
                      left join frente_obra fo
                        on fo.obra_id = r.obra_id and fo.frente_id = act.frente_id
                      left join contratista ct
                        on ct.id = coalesce(act.contratista_id, fo.contratista_id)
                      left join usuario up on up.id = r.propuesta_por
                      left join usuario ur on ur.id = r.revisada_por
                      left join usuario uv on uv.id = r.validada_por
                      left join usuario ua on ua.id = r.aplicada_por
                      left join usuario uz on uz.id = r.rechazada_por
                     where r.obra_id = :obra_id
                     order by r.created_at desc, r.id
                    """
                ),
                {"obra_id": str(obra_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def crear(
        self,
        *,
        obra_id: UUID,
        actividad_id: UUID,
        estatus: str,
        fecha_inicio: date | None,
        fecha_termino: date | None,
        fecha_inicio_anterior: date | None,
        fecha_termino_anterior: date | None,
        motivo: str,
        propuesta_por: UUID,
        propuesta_rol: str,
    ) -> UUID:
        id_ = uuid4()
        await self._sesion.execute(
            text(
                """
                insert into reprogramacion
                    (id, org_id, obra_id, actividad_id, estatus, fecha_inicio,
                     fecha_termino, fecha_inicio_anterior, fecha_termino_anterior,
                     motivo, propuesta_por, propuesta_rol)
                values
                    (:id, current_setting('app.org_id')::uuid, :obra_id, :actividad_id,
                     cast(:estatus as estatus_reprogramacion), :fecha_inicio,
                     :fecha_termino, :fecha_inicio_anterior, :fecha_termino_anterior,
                     :motivo, :propuesta_por, :propuesta_rol)
                """
            ),
            {
                "id": str(id_),
                "obra_id": str(obra_id),
                "actividad_id": str(actividad_id),
                "estatus": estatus,
                "fecha_inicio": fecha_inicio,
                "fecha_termino": fecha_termino,
                "fecha_inicio_anterior": fecha_inicio_anterior,
                "fecha_termino_anterior": fecha_termino_anterior,
                "motivo": motivo,
                "propuesta_por": str(propuesta_por),
                "propuesta_rol": propuesta_rol,
            },
        )
        return id_

    async def actualizar(
        self,
        reprogramacion_id: UUID,
        *,
        estatus: str,
        revisada_por: UUID | None = None,
        validada_por: UUID | None = None,
        aplicada_por: UUID | None = None,
        rechazada_por: UUID | None = None,
        motivo_rechazo: str | None = None,
    ) -> None:
        resultado = await self._sesion.execute(
            text(
                """
                update reprogramacion
                   set estatus        = cast(:estatus as estatus_reprogramacion),
                       revisada_por   = coalesce(cast(:revisada_por as uuid), revisada_por),
                       revisada_en    = case when cast(:revisada_por as uuid) is not null
                                             then now() else revisada_en end,
                       validada_por   = coalesce(cast(:validada_por as uuid), validada_por),
                       validada_en    = case when cast(:validada_por as uuid) is not null
                                             then now() else validada_en end,
                       aplicada_por   = coalesce(cast(:aplicada_por as uuid), aplicada_por),
                       aplicada_en    = case when cast(:aplicada_por as uuid) is not null
                                             then now() else aplicada_en end,
                       rechazada_por  = coalesce(cast(:rechazada_por as uuid), rechazada_por),
                       rechazada_en   = case when cast(:rechazada_por as uuid) is not null
                                             then now() else rechazada_en end,
                       motivo_rechazo = coalesce(:motivo_rechazo, motivo_rechazo)
                 where id = :id
                """
            ),
            {
                "id": str(reprogramacion_id),
                "estatus": estatus,
                "revisada_por": str(revisada_por) if revisada_por else None,
                "validada_por": str(validada_por) if validada_por else None,
                "aplicada_por": str(aplicada_por) if aplicada_por else None,
                "rechazada_por": str(rechazada_por) if rechazada_por else None,
                "motivo_rechazo": motivo_rechazo,
            },
        )
        if resultado.rowcount == 0:
            raise ReprogramacionNoModificada(
                f"No se actualizó la reprogramación {reprogramacion_id}: ya no existe o "
                "salió de tu alcance."
            )

    async def agregar_observacion(
        self,
        *,
        reprogramacion_id: UUID,
        obra_id: UUID,
        usuario_id: UUID,
        rol: str,
        texto: str,
    ) -> UUID:
        id_ = uuid4()
        await self._sesion.execute(
            text(
                """
                insert into reprogramacion_observacion
                    (id, org_id, obra_id, reprogramacion_id, usuario_id, rol, texto)
                values
                    (:id, current_setting('app.org_id')::uuid, :obra_id,
                     :reprogramacion_id, :usuario_id, :rol, :texto)
                """
            ),
            {
                "id": str(id_),
                "obra_id": str(obra_id),
                "reprogramacion_id": str(reprogramacion_id),
                "usuario_id": str(usuario_id),
                "rol": rol,
                "texto": texto,
            },
        )
        return id_

    async def obtener_observacion(self, observacion_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(f"{_OBSERVACION} where o.id = :id"), {"id": str(observacion_id)}
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def observaciones_de_obra(self, obra_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(f"{_OBSERVACION} where o.obra_id = :obra_id order by o.creada_en, o.id"),
                {"obra_id": str(obra_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]
