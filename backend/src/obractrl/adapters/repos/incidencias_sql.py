"""Repositorio de incidencias.

Spec §12.11 (adaptador de persistencia) · §7.8 (control y flujos) · §6 ·
§12.4 (RLS).

RLS ya filtra `incidencia` por alcance de rol: entra al loop genérico
`por_obra` (política `incidencia_scope`, `database/migrations/0012`, vía
`obra_id`) — ningún método de aquí filtra por `org_id` u `obra_id` de forma
manual, eso lo impone la base. `incidencia_evento` tiene su propia política
explícita (`incidencia_evento_scope`), que resuelve el alcance a través de
la incidencia padre. `org_id` en los INSERT sale de
`current_setting('app.org_id')`, igual que en `cierres_sql.py`.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.application.puertos.repositorios import RegistroNoEncontrado

__all__ = ["IncidenciaNoModificada", "RepositorioIncidenciasSQL"]

_COLUMNAS = """
    id, obra_id, frente_id, tipo, impacto, titulo, descripcion, creada_por,
    asignada_a, estatus, fecha_creada, fecha_limite, dias_retraso,
    bloquea_actividades, evidencias
"""


class IncidenciaNoModificada(RegistroNoEncontrado):
    """El UPDATE no afectó ninguna fila: la incidencia ya no existe o salió
    del alcance del usuario (RLS) entre el `obtener()` y el `actualizar()`."""


class RepositorioIncidenciasSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def obtener(self, incidencia_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} from incidencia where id = :id"),
                {"id": str(incidencia_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def crear(
        self,
        *,
        obra_id: UUID,
        creada_por: UUID,
        tipo: str,
        impacto: str,
        titulo: str,
        descripcion: str | None = None,
        frente_id: UUID | None = None,
        evidencias: list[str] | None = None,
        bloquea_actividades: list[str] | None = None,
        fecha_limite: date | None = None,
    ) -> UUID:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    insert into incidencia
                        (org_id, obra_id, frente_id, tipo, impacto, titulo,
                         descripcion, creada_por, evidencias,
                         bloquea_actividades, fecha_limite, estatus)
                    values
                        (cast(current_setting('app.org_id') as uuid),
                         :obra_id, :frente_id, cast(:tipo as tipo_incidencia),
                         cast(:impacto as impacto_incidencia), :titulo,
                         :descripcion, :creada_por, cast(:evidencias as jsonb),
                         cast(:bloquea_actividades as jsonb), :fecha_limite,
                         'abierta')
                    returning id
                    """
                ),
                {
                    "obra_id": str(obra_id),
                    "frente_id": str(frente_id) if frente_id else None,
                    "tipo": tipo,
                    "impacto": impacto,
                    "titulo": titulo,
                    "descripcion": descripcion,
                    "creada_por": str(creada_por),
                    "evidencias": json.dumps(evidencias or []),
                    "bloquea_actividades": json.dumps(bloquea_actividades or []),
                    "fecha_limite": fecha_limite,
                },
            )
        ).scalar_one()
        return fila

    async def actualizar(
        self,
        incidencia_id: UUID,
        *,
        estatus: str,
        asignada_a: UUID | None = None,
    ) -> None:
        resultado = await self._sesion.execute(
            text(
                """
                update incidencia
                   set estatus    = cast(:estatus as estatus_incidencia),
                       asignada_a = coalesce(cast(:asignada_a as uuid), asignada_a)
                 where id = :id
                """
            ),
            {
                "id": str(incidencia_id),
                "estatus": estatus,
                "asignada_a": str(asignada_a) if asignada_a else None,
            },
        )
        if resultado.rowcount == 0:
            raise IncidenciaNoModificada(
                f"No se actualizó la incidencia {incidencia_id}: ya no existe "
                f"o salió de tu alcance."
            )

    async def registrar_evento(
        self,
        incidencia_id: UUID,
        *,
        usuario_id: UUID,
        accion: str,
        estatus_previo: str,
        estatus_nuevo: str,
        comentario: str | None = None,
    ) -> UUID:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    insert into incidencia_evento
                        (org_id, incidencia_id, usuario_id, accion,
                         estatus_previo, estatus_nuevo, comentario)
                    values
                        (cast(current_setting('app.org_id') as uuid),
                         :incidencia_id, :usuario_id, :accion,
                         cast(:estatus_previo as estatus_incidencia),
                         cast(:estatus_nuevo as estatus_incidencia),
                         :comentario)
                    returning id
                    """
                ),
                {
                    "incidencia_id": str(incidencia_id),
                    "usuario_id": str(usuario_id),
                    "accion": accion,
                    "estatus_previo": estatus_previo,
                    "estatus_nuevo": estatus_nuevo,
                    "comentario": comentario,
                },
            )
        ).scalar_one()
        return fila

    async def listar(self, *, estatus: str | None = None) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS}
                    from incidencia
                    where :estatus is null or estatus = cast(:estatus as estatus_incidencia)
                    order by fecha_creada desc
                    """
                ),
                {"estatus": estatus},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]
