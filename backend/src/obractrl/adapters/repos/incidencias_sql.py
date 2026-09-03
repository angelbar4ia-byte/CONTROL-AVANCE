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
    i.id, i.obra_id, i.frente_id, i.tipo, i.impacto, i.titulo, i.descripcion,
    i.creada_por, i.asignada_a, i.estatus, i.fecha_creada, i.fecha_limite,
    i.bloquea_actividades, i.evidencias
"""
# `i.dias_retraso` no está aquí a propósito: la columna existe desde la 0009
# pero nada la escribe —ningún trigger, ningún caso de uso— así que siempre
# vale su default (0). Confiarla mentiría. Los días de atraso se calculan al
# vuelo contra `fecha_limite`, que sí se captura, y viven en el borde
# (`IncidenciaRespuesta`) porque son de presentación: "cuántos días lleva
# vencida hoy" cambia cada día sin que la fila cambie.

_COLUMNAS_RESUELTAS = f"""
    {_COLUMNAS},
    -- Dónde en la obra (§7.4, migración 0050): el nivel es el frente y la
    -- etapa el sub-frente, mismo eje que `actividad`. `i.frente_id` de arriba
    -- sigue siendo el tipo de contratación (0005), otro eje.
    niv.clave as nivel_clave, niv.descripcion as nivel_descripcion,
    eta.clave as etapa_clave, eta.descripcion as etapa_descripcion,
    obr.clave as obra_clave,
    -- Las actividades bloqueadas resueltas a la clave de su concepto, para
    -- poder decir "bloquea ALB-003" en vez de un UUID. `bloquea_actividades`
    -- es un jsonb con ids en texto porque nace de una lista libre (§6); esto
    -- la reconcilia contra el catálogo cada vez, así que una actividad que
    -- cambió de concepto o se borró no deja una clave fantasma.
    coalesce((
        select array_agg(coalesce(con.clave, act.descripcion) order by con.clave)
          from jsonb_array_elements_text(i.bloquea_actividades) as ref(actividad_id)
          join actividad act on act.id = ref.actividad_id::uuid
          left join concepto con on con.id = act.concepto_id
    ), array[]::text[]) as bloquea_claves
"""

_DESDE_RESUELTA = """
    from incidencia i
    left join nivel niv              on niv.id = i.nivel_id
    left join etapa_constructiva eta on eta.id = i.etapa_id
    left join obra obr               on obr.id = i.obra_id
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
                text(
                    f"select {_COLUMNAS_RESUELTAS} {_DESDE_RESUELTA} "
                    f"where i.id = :id"
                ),
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
        nivel_id: UUID | None = None,
        etapa_id: UUID | None = None,
        evidencias: list[str] | None = None,
        bloquea_actividades: list[str] | None = None,
        fecha_limite: date | None = None,
    ) -> UUID:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    insert into incidencia
                        (org_id, obra_id, frente_id, nivel_id, etapa_id, tipo,
                         impacto, titulo, descripcion, creada_por, evidencias,
                         bloquea_actividades, fecha_limite, estatus)
                    values
                        (cast(current_setting('app.org_id') as uuid),
                         :obra_id, :frente_id, cast(:nivel_id as uuid),
                         cast(:etapa_id as uuid), cast(:tipo as tipo_incidencia),
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
                    "nivel_id": str(nivel_id) if nivel_id else None,
                    "etapa_id": str(etapa_id) if etapa_id else None,
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

    async def listar(
        self, *, estatus: str | None = None, obra_id: UUID | None = None
    ) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS_RESUELTAS}
                    {_DESDE_RESUELTA}
                    -- El cast del lado `is null` fija el tipo del parámetro;
                    -- sin él asyncpg levanta AmbiguousParameterError.
                    where (cast(:estatus as estatus_incidencia) is null
                           or i.estatus = cast(:estatus as estatus_incidencia))
                      and (cast(:obra_id as uuid) is null
                           or i.obra_id = cast(:obra_id as uuid))
                    order by i.fecha_creada desc
                    """
                ),
                {"estatus": estatus, "obra_id": str(obra_id) if obra_id else None},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]
