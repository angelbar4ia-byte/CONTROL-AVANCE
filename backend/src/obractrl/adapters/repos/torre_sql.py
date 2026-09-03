"""Repositorio de la Torre de control: el estado de cada obra en una consulta.

Spec §5.1 (la Torre es la primera entrada de Supervisor, Control de obra y
Super intendente) · §5.3 (pantalla compartida) · §12.1 (60–80 obras activas) ·
§12.4 (RLS) · §12.11 (adaptador de persistencia).

## Por qué es un agregado y no cuatro llamadas del cliente

La Torre muestra, por obra: avance, cuántas actividades hay, cuántas están en
la ruta crítica, cuántas bloqueadas, cuántas incidencias abiertas y cuántos
cierres esperando. Resolverlo desde el navegador serían **cinco peticiones por
obra**; a la escala del §12.1 eso son cuatrocientas peticiones para pintar una
pantalla, y cada una con su ida y vuelta de RLS.

Aquí es una sola consulta con subconsultas escalares. No es la forma más
elegante de SQL, pero es la que hace que la pantalla que abren tres de los
cuatro roles cargue en un viaje.

## El alcance no se filtra aquí

`obra` trae su política (`obra_select`, migración 0012) y las tablas hijas la
suya. Un supervisor ve las obras de sus clusters y **los conteos se calculan
solo sobre lo que él ve**, porque las subconsultas pasan por las mismas
políticas. No hay un `where org_id` a mano en este archivo, y no debería
haberlo: sería una segunda frontera que puede desincronizarse de la primera.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioTorreSQL"]

# `count(*) filter (where ...)` en vez de cinco subconsultas correlacionadas:
# un solo recorrido de `actividad` por obra en lugar de tres.
_ESTADO_POR_OBRA = """
    select
        o.id                as obra_id,
        o.clave             as obra_clave,
        o.estatus           as obra_estatus,
        o.avance_pct        as avance_pct,
        o.fecha_inicio      as fecha_inicio,
        o.fecha_fin         as fecha_fin,
        c.id                as cluster_id,
        c.clave             as cluster_clave,
        p.id                as proyecto_id,
        p.clave             as proyecto_clave,
        u.nombre            as residente_nombre,
        coalesce(a.total, 0)      as actividades,
        coalesce(a.criticas, 0)   as criticas,
        coalesce(a.bloqueadas, 0) as bloqueadas,
        coalesce(a.concluidas, 0) as concluidas,
        coalesce(i.abiertas, 0)   as incidencias_abiertas,
        coalesce(i.detienen, 0)   as incidencias_detienen,
        coalesce(s.pendientes, 0) as cierres_pendientes
    from obra o
    join cluster c   on c.id = o.cluster_id
    join proyecto p  on p.id = c.proyecto_id
    left join usuario u on u.id = o.residente_id
    left join lateral (
        select count(*)                                        as total,
               count(*) filter (where act.es_critica)          as criticas,
               count(*) filter (where act.bloqueada)           as bloqueadas,
               -- `concluida`, no `cerrada`: el enum `estatus_actividad` del §8.2
               -- no tiene ese valor, y escribirlo mal daría un error de tipo
               -- en tiempo de consulta, no un cero silencioso.
               count(*) filter (where act.estatus = 'concluida') as concluidas
          from actividad act
         where act.obra_id = o.id
    ) a on true
    left join lateral (
        select count(*)                                                as abiertas,
               count(*) filter (where inc.impacto = 'detiene')         as detienen
          from incidencia inc
         where inc.obra_id = o.id
           -- Abiertas de verdad: `rechazada` y `cerrada` ya no le tocan a
           -- nadie, y un `<> 'cerrada'` habría contado las rechazadas como
           -- trabajo pendiente.
           and inc.estatus in ('abierta', 'programada', 'en_atencion',
                               'cierre_solicitado')
    ) i on true
    left join lateral (
        -- Cierres que esperan a alguien: el residente ya solicitó y falta que
        -- el supervisor autorice o que control valide (§11.3 C). Un cierre
        -- validado o rechazado ya no le toca a nadie.
        select count(*) as pendientes
          from solicitud_cierre sc
          join actividad act2 on act2.id = sc.actividad_id
         where act2.obra_id = o.id
           and sc.estatus in ('solicitada', 'autorizada')
    ) s on true
"""


class RepositorioTorreSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def estado_de_obras(
        self,
        *,
        proyecto_id: UUID | None = None,
        cluster_id: UUID | None = None,
        solo_con_pendientes: bool = False,
    ) -> list[dict[str, Any]]:
        """Una fila por obra visible, con sus contadores (§5.1).

        `solo_con_pendientes` es el filtro que convierte la Torre en una lista
        de tareas: deja las obras que tienen algo esperando a alguien —una
        incidencia abierta, un cierre por resolver, una actividad bloqueada—.
        Se resuelve en SQL y no en el cliente porque filtrar después de traer
        ochenta filas es traer ochenta filas.
        """
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    with estado as (
                        {_ESTADO_POR_OBRA}
                    )
                    select *
                      from estado
                     -- El cast del lado `is null` fija el tipo del parámetro;
                     -- sin él asyncpg levanta AmbiguousParameterError. Mismo
                     -- patrón que `obras_sql.listar`.
                     where (cast(:proyecto_id as uuid) is null
                            or proyecto_id = cast(:proyecto_id as uuid))
                       and (cast(:cluster_id as uuid) is null
                            or cluster_id = cast(:cluster_id as uuid))
                       and (not cast(:solo_pendientes as boolean)
                            or incidencias_abiertas > 0
                            or cierres_pendientes > 0
                            or bloqueadas > 0)
                     order by
                        -- Lo que estorba primero: una obra con actividades
                        -- detenidas es la que hay que mirar hoy, no la que va
                        -- más adelantada.
                        (bloqueadas > 0 or incidencias_detienen > 0) desc,
                        cierres_pendientes desc,
                        obra_clave
                    """
                ),
                {
                    "proyecto_id": str(proyecto_id) if proyecto_id else None,
                    "cluster_id": str(cluster_id) if cluster_id else None,
                    "solo_pendientes": solo_con_pendientes,
                },
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def actividades_de_obra(
        self,
        obra_id: UUID,
        *,
        estatus: str | None = None,
        solo_criticas: bool = False,
    ) -> list[dict[str, Any]]:
        """Las actividades de una obra (§11.2 `GET /obras/{id}/actividades`).

        Trae la descripción del concepto además de la propia: una actividad
        generada desde el prototipo puede no tener `descripcion` y quedarse sin
        nada que mostrar en la tabla.

        Y trae la **jerarquía resuelta**, que es como el residente mira su obra
        (§7.4): el nivel es el *frente* —cimentación, planta baja, azotea— y la
        etapa el *sub-frente*. Sin ellos, la única agrupación disponible era
        `act.frente_id`, que está vacío en todas las actividades porque se
        llena desde el item del programa base y ése casi nunca lo trae; el
        frente de contratación —OBRA, INSTALACIONES…— sale de la etapa, igual
        que en `actividades_para_insumos`.
        """
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select act.id, act.obra_id, act.concepto_id, act.frente_id,
                           coalesce(act.descripcion, con.descripcion) as descripcion,
                           con.clave as concepto_clave,
                           uni.clave as unidad,
                           coalesce(act.nivel_id, eta.nivel_id) as nivel_id,
                           niv.clave       as nivel_clave,
                           niv.descripcion as nivel_descripcion,
                           act.etapa_id,
                           eta.clave       as etapa_clave,
                           eta.descripcion as etapa_descripcion,
                           coalesce(f.nombre, fre.nombre) as frente_nombre,
                           fre.clave as contratacion_clave,
                           esp.clave as especialidad_clave,
                           act.cant_base, act.cant_programada, act.cant_ejecutada,
                           act.avance_pct, act.estatus, act.bloqueada, act.extra,
                           act.orden_cambio,
                           act.es_critica, act.holgura, act.desfase,
                           act.fecha_inicio, act.fecha_termino, act.duracion_dias,
                           act.modo_pago, act.precio_unitario, act.precio_destajo,
                           act.contratista_id, ctr.razon_social as contratista_nombre,
                           act.cuadrilla_id,  cua.nombre        as cuadrilla_nombre
                      from actividad act
                      left join concepto con on con.id = act.concepto_id
                      left join unidad   uni on uni.id = con.unidad_id
                      left join frente f     on f.id = act.frente_id
                      left join etapa_constructiva eta on eta.id = act.etapa_id
                      left join nivel  niv on niv.id = coalesce(act.nivel_id, eta.nivel_id)
                      left join frente fre on fre.id = eta.frente_id
                      left join especialidad esp on esp.id = con.especialidad_id
                      left join contratista  ctr on ctr.id = act.contratista_id
                      left join cuadrilla    cua on cua.id = act.cuadrilla_id
                     where act.obra_id = :obra_id
                       and (cast(:estatus as estatus_actividad) is null
                            or act.estatus = cast(:estatus as estatus_actividad))
                       and (not cast(:solo_criticas as boolean) or act.es_critica)
                     order by act.es_critica desc, act.fecha_inicio nulls last,
                              act.created_at
                    """
                ),
                {
                    "obra_id": str(obra_id),
                    "estatus": estatus,
                    "solo_criticas": solo_criticas,
                },
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def actividad(self, actividad_id: UUID) -> dict[str, Any] | None:
        """Detalle de una actividad (§11.2 `GET /actividades/{id}`).

        Las mismas columnas que el listado, más las que solo interesan cuando
        se abre una: notas, dependencias y a quién está asignada.
        """
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select act.id, act.obra_id, act.concepto_id, act.frente_id,
                           coalesce(act.descripcion, con.descripcion) as descripcion,
                           f.nombre as frente_nombre,
                           o.clave as obra_clave,
                           act.cant_base, act.cant_programada, act.cant_ejecutada,
                           act.avance_pct, act.estatus, act.bloqueada, act.extra,
                           act.es_critica, act.holgura, act.desfase,
                           act.fecha_inicio, act.fecha_termino, act.duracion_dias,
                           act.modo_pago, act.precio_unitario, act.precio_destajo,
                           act.dependencias, act.notas, act.orden_cambio,
                           -- `razon_social`, no `nombre`: un contratista es
                           -- una empresa (§7.3) y esa es la columna que tiene.
                           ct.razon_social as contratista_nombre,
                           cu.nombre as cuadrilla_nombre
                      from actividad act
                      join obra o             on o.id = act.obra_id
                      left join concepto con  on con.id = act.concepto_id
                      left join frente f      on f.id = act.frente_id
                      left join contratista ct on ct.id = act.contratista_id
                      left join cuadrilla cu   on cu.id = act.cuadrilla_id
                     where act.id = :id
                    """
                ),
                {"id": str(actividad_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def costos_de_cuadrillas(
        self, cuadrilla_ids: Sequence[UUID]
    ) -> dict[str, dict[str, Any]]:
        """Nombre y costo por jornada de esas cuadrillas (§7.6, migración 0048).

        Se piden todas de una: son cuatro o cinco renglones en un formulario y
        una ida por cada uno sería una consulta por tecla.

        Una cuadrilla sin `costo_jornada` capturado vuelve con `None`, no con
        cero: el dominio lo reporta como "no se sabe cuánto vale" en vez de
        sumarlo como gratis.
        """
        if not cuadrilla_ids:
            return {}
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select id, nombre, costo_jornada
                      from cuadrilla
                     where id = any(cast(:ids as uuid[]))
                    """
                ),
                {"ids": [str(x) for x in cuadrilla_ids]},
            )
        ).mappings().all()
        return {str(fila["id"]): dict(fila) for fila in filas}

    async def costos_de_insumos(
        self, insumo_ids: Sequence[UUID]
    ) -> dict[str, dict[str, Any]]:
        """Descripción y costo de esos insumos (§7.3, §10.5).

        El costo es `coalesce(costo_base_actualizado, costo_base)`, la **misma**
        regla de valuación que usa la explosión del APU
        (`conceptos_sql.composicion_recursiva`). Elegir otra aquí haría que el
        mismo cemento valiera distinto en el precio de un extra que en el de un
        concepto de catálogo, sobre la misma obra y el mismo día.

        Mismo criterio que arriba: en bloque, y sin costo vuelve `None` —no
        cero— para que el dominio lo reporte en vez de sumarlo como gratis.
        """
        if not insumo_ids:
            return {}
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select id, descripcion,
                           coalesce(costo_base_actualizado, costo_base) as costo
                      from insumo
                     where id = any(cast(:ids as uuid[]))
                    """
                ),
                {"ids": [str(x) for x in insumo_ids]},
            )
        ).mappings().all()
        return {str(fila["id"]): dict(fila) for fila in filas}
