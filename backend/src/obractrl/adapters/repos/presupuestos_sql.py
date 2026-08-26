"""Presupuesto y rendimientos (§5.1, §11.2, §7.3).

Spec §12.11 (adaptador de persistencia) · §12.4 (RLS) · §11.1.

## El presupuesto es del prototipo, no de la obra

`presupuesto` cuelga de `prototipo` (migración 0006), y tiene sentido: el
presupuesto describe **el modelo de vivienda**, y todas las obras que lo
instancian comparten el mismo. Por eso `presupuesto_de_obra` resuelve
`obra → prototipo → presupuesto vigente` en vez de buscar un presupuesto que no
existiría.

Consecuencia práctica: una obra URBA —sin prototipo (§7.2)— **no tiene
presupuesto**, y eso no es un error sino su naturaleza. Los métodos devuelven
vacío y quien llama lo dice con esas palabras.

## Dos alcances distintos en el mismo archivo, a propósito

· `presupuesto` y `partida_presupuesto` son **catálogo**: alcance de
  organización (migración 0012, array de catálogos). Cualquier usuario de la org
  los lee; quién los ve en su pantalla lo decide el RBAC del borde, no RLS.
· Los rendimientos parten de **`obra`**, que sí trae alcance por rol. Un
  supervisor compara solo las obras de sus clusters porque la consulta arranca
  en una tabla que ya lo sabe.

Que sean distintos es correcto y conviene tenerlo escrito: si algún día alguien
se extraña de que un residente pueda leer el presupuesto de un prototipo, la
respuesta está aquí y no en una política olvidada.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioPresupuestosSQL"]

_COLUMNAS_VERSION = "id, prototipo_id, version, vigente, origen, carga_id, monto_total, created_at"


class RepositorioPresupuestosSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    # --- Escritura (cargador de presupuesto jerárquico, §10.8) ----------

    async def crear_version(
        self, prototipo_id: UUID, *, origen: str, carga_id: UUID | None
    ) -> dict[str, Any]:
        """Retira el vigente anterior e inserta la versión siguiente como
        vigente, en **dos sentencias separadas y secuenciales** — mismo
        patrón que `RepositorioConceptos.publicar_version_cpu`.

        No es una sola sentencia con CTEs: `uq_presupuesto_vigente` es un
        índice único parcial y no diferible, y dos CTEs independientes
        (`update ... returning` e `insert ... returning`) que no se
        referencian entre sí **no tienen orden de ejecución garantizado**
        entre ellas en Postgres — solo lo tienen frente a lo que sí las
        referencia. Un intento con una sola sentencia violó la restricción
        en CI: el `insert` alcanzó a correr antes de que el `update`
        aterrizara. Dos `execute()` awaited, uno tras otro, sí garantizan el
        orden porque son dos sentencias distintas en la misma transacción.
        """
        anterior = (
            await self._sesion.execute(
                text(
                    """
                    update presupuesto
                       set vigente = false
                     where org_id = cast(current_setting('app.org_id') as uuid)
                       and prototipo_id = :prototipo_id
                       and vigente
                    returning id
                    """
                ),
                {"prototipo_id": str(prototipo_id)},
            )
        ).first()

        fila = (
            await self._sesion.execute(
                text(
                    f"""
                    insert into presupuesto (org_id, prototipo_id, version, vigente, origen, carga_id)
                    select cast(current_setting('app.org_id') as uuid), :prototipo_id,
                           coalesce(max(version), 0) + 1, true, :origen, cast(:carga_id as uuid)
                      from presupuesto
                     where org_id = cast(current_setting('app.org_id') as uuid)
                       and prototipo_id = :prototipo_id
                    returning {_COLUMNAS_VERSION}
                    """
                ),
                {
                    "prototipo_id": str(prototipo_id),
                    "origen": origen,
                    "carga_id": str(carga_id) if carga_id else None,
                },
            )
        ).mappings().one()
        return {**fila, "anterior_id": anterior.id if anterior else None}

    async def agregar_partidas(
        self, presupuesto_id: UUID, partidas: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Inserta las partidas y devuelve las filas persistidas, completas,
        para el snapshot del lote (§10.8). Claves esperadas por partida:
        ``concepto_id``, ``prototipo_nodo_id``, ``cantidad``,
        ``precio_unitario``, ``importe``, ``orden``.
        """
        insertadas: list[dict[str, Any]] = []
        for partida in partidas:
            fila = (
                await self._sesion.execute(
                    text(
                        """
                        insert into partida_presupuesto
                            (org_id, presupuesto_id, concepto_id, prototipo_nodo_id,
                             cantidad, precio_unitario, importe, orden)
                        values
                            (cast(current_setting('app.org_id') as uuid), :presupuesto_id,
                             cast(:concepto_id as uuid), cast(:prototipo_nodo_id as uuid),
                             cast(:cantidad as numeric), cast(:precio_unitario as numeric),
                             cast(:importe as numeric), :orden)
                        returning id, concepto_id, prototipo_nodo_id, cantidad,
                                  precio_unitario, importe, orden
                        """
                    ),
                    {
                        "presupuesto_id": str(presupuesto_id),
                        "concepto_id": str(partida["concepto_id"]),
                        "prototipo_nodo_id": str(partida["prototipo_nodo_id"]),
                        "cantidad": partida["cantidad"],
                        "precio_unitario": partida["precio_unitario"],
                        "importe": partida["importe"],
                        "orden": partida.get("orden", 0),
                    },
                )
            ).mappings().one()
            insertadas.append(dict(fila))
        return insertadas

    async def actualizar_monto_total(self, presupuesto_id: UUID, monto_total: Decimal) -> None:
        await self._sesion.execute(
            text("update presupuesto set monto_total = :monto where id = :id"),
            {"id": str(presupuesto_id), "monto": monto_total},
        )

    async def otros_prototipos_con_partida_vigente(
        self, concepto_id: UUID, *, excluir_prototipo_id: UUID
    ) -> list[UUID]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select distinct p.prototipo_id
                      from partida_presupuesto pp
                      join presupuesto p on p.id = pp.presupuesto_id and p.vigente
                     where p.org_id = cast(current_setting('app.org_id') as uuid)
                       and pp.concepto_id = :concepto_id
                       and p.prototipo_id != :excluir_prototipo_id
                    """
                ),
                {
                    "concepto_id": str(concepto_id),
                    "excluir_prototipo_id": str(excluir_prototipo_id),
                },
            )
        ).all()
        return [fila.prototipo_id for fila in filas]

    async def tiene_partida_vigente(
        self, concepto_id: UUID, prototipo_id: UUID
    ) -> bool:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select 1
                      from partida_presupuesto pp
                      join presupuesto p on p.id = pp.presupuesto_id and p.vigente
                     where p.org_id = cast(current_setting('app.org_id') as uuid)
                       and pp.concepto_id = :concepto_id
                       and p.prototipo_id = :prototipo_id
                    """
                ),
                {"concepto_id": str(concepto_id), "prototipo_id": str(prototipo_id)},
            )
        ).first()
        return fila is not None

    # --- Presupuesto ----------------------------------------------------

    async def vigente_de_prototipo(self, prototipo_id: UUID) -> dict[str, Any] | None:
        """El presupuesto vigente de un prototipo (§7.3).

        `uq_presupuesto_vigente` garantiza que haya **uno**: el índice único
        parcial `where vigente` es lo que impide que dos versiones se declaren
        vigentes a la vez. Por eso aquí no hay `order by version desc limit 1`,
        que sería tratar como ambiguo algo que la base ya resolvió.
        """
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select p.id, p.prototipo_id, p.version, p.origen,
                           p.monto_total, p.created_at,
                           pr.clave as prototipo_clave, pr.nombre as prototipo_nombre
                      from presupuesto p
                      join prototipo pr on pr.id = p.prototipo_id
                     where p.prototipo_id = :prototipo_id and p.vigente
                    """
                ),
                {"prototipo_id": str(prototipo_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def presupuesto_de_obra(self, obra_id: UUID) -> dict[str, Any] | None:
        """`obra → prototipo → presupuesto vigente`.

        Devuelve `None` si la obra no es visible, si es URBA —sin prototipo, y
        por lo tanto sin presupuesto— o si su prototipo todavía no tiene uno
        cargado. Las tres son "no hay presupuesto que mostrar"; quien llama
        distingue el motivo consultando la obra, que ya tiene.
        """
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select p.id, p.prototipo_id, p.version, p.origen,
                           p.monto_total, p.created_at,
                           pr.clave as prototipo_clave, pr.nombre as prototipo_nombre,
                           o.clave as obra_clave, o.es_urba
                      from obra o
                      join prototipo pr on pr.id = o.prototipo_id
                      join presupuesto p on p.prototipo_id = pr.id and p.vigente
                     where o.id = :obra_id
                    """
                ),
                {"obra_id": str(obra_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def partidas(self, presupuesto_id: UUID) -> list[dict[str, Any]]:
        """Las partidas con la descripción de su concepto.

        `left join` sobre `concepto`: una partida puede apuntar a un concepto
        que ya no está —el catálogo se versiona (§10.8)— y perderla del listado
        haría que las partidas no sumaran el `monto_total` del presupuesto.
        """
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select pp.id, pp.concepto_id, pp.prototipo_nodo_id,
                           pp.cantidad, pp.precio_unitario, pp.importe, pp.orden,
                           c.clave as concepto_clave,
                           c.descripcion as concepto_descripcion,
                           u.clave as unidad_clave
                      from partida_presupuesto pp
                      left join concepto c on c.id = pp.concepto_id
                      left join unidad u   on u.id = c.unidad_id
                     where pp.presupuesto_id = :presupuesto_id
                     order by pp.orden, c.clave
                    """
                ),
                {"presupuesto_id": str(presupuesto_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def versiones_de_prototipo(self, prototipo_id: UUID) -> list[dict[str, Any]]:
        """El historial (§10.8): qué versión estuvo vigente y de qué carga vino."""
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select p.id, p.version, p.vigente, p.origen, p.carga_id,
                           p.monto_total, p.created_at
                      from presupuesto p
                     where p.prototipo_id = :prototipo_id
                     order by p.version desc
                    """
                ),
                {"prototipo_id": str(prototipo_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    # --- Rendimientos ---------------------------------------------------

    async def rendimiento_por_concepto(self, obra_id: UUID) -> list[dict[str, Any]]:
        """Presupuestado contra ejecutado, concepto por concepto (§5.1).

        ## Por qué se comparan las dos caras y no solo el presupuesto

        Las dos caras tienen filas que la otra no: un concepto presupuestado que
        nunca se ejecutó (se dejó de hacer) y una actividad ejecutada que no
        estaba presupuestada (un extra-catálogo, §11.2). Con un `left join`
        desde el presupuesto, los extras desaparecerían del comparativo — y son
        justamente los que explican por qué la obra costó más.

        ## El ejecutado se valúa con el precio de la actividad, no con el del
        presupuesto

        `actividad.precio_unitario` es el que se estima y se paga (§11.3 E). Usar
        el precio presupuestado daría una comparación de cantidades disfrazada
        de comparación de dinero, y escondería exactamente la desviación que se
        viene a buscar.
        """
        filas = (
            await self._sesion.execute(
                text(
                    """
                    with presupuestado as (
                        select pp.concepto_id,
                               sum(pp.cantidad) as cantidad,
                               sum(pp.importe)  as importe
                          from obra o
                          join presupuesto p
                            on p.prototipo_id = o.prototipo_id and p.vigente
                          join partida_presupuesto pp on pp.presupuesto_id = p.id
                         where o.id = :obra_id
                         group by pp.concepto_id
                    ),
                    ejecutado as (
                        select act.concepto_id,
                               sum(act.cant_ejecutada) as cantidad,
                               -- El modo de pago decide qué precio vale (§7.3):
                               -- un destajo no se valúa con el unitario.
                               sum(act.cant_ejecutada * case
                                     when act.modo_pago = 'destajo'
                                       then act.precio_destajo
                                     else act.precio_unitario
                                   end) as importe,
                               bool_or(act.extra) as hay_extra
                          from actividad act
                         where act.obra_id = :obra_id
                         group by act.concepto_id
                    ),
                    claves as (
                        -- El conjunto de conceptos que aparecen en cualquiera de
                        -- las dos caras. Es un `union` y no un `full outer
                        -- join` porque Postgres **no soporta** `FULL JOIN` con
                        -- `is not distinct from` —la condición tiene que ser
                        -- hash o merge joinable— y esa condición hace falta:
                        -- las actividades extra no tienen concepto, así que su
                        -- clave es `null` y un `=` no las junta.
                        select concepto_id from presupuestado
                        union
                        select concepto_id from ejecutado
                    )
                    select
                        k.concepto_id,
                        c.clave       as concepto_clave,
                        c.descripcion as concepto_descripcion,
                        u.clave       as unidad_clave,
                        coalesce(pre.cantidad, 0) as cantidad_presupuestada,
                        coalesce(pre.importe, 0)  as importe_presupuestado,
                        coalesce(eje.cantidad, 0) as cantidad_ejecutada,
                        coalesce(eje.importe, 0)  as importe_ejecutado,
                        coalesce(eje.hay_extra, false) as extra
                      from claves k
                      left join presupuestado pre
                        on pre.concepto_id is not distinct from k.concepto_id
                      left join ejecutado eje
                        on eje.concepto_id is not distinct from k.concepto_id
                      left join concepto c on c.id = k.concepto_id
                      left join unidad u on u.id = c.unidad_id
                     order by
                        -- Lo que más se desvía en dinero, primero: es lo que hay
                        -- que explicar.
                        abs(coalesce(eje.importe, 0) - coalesce(pre.importe, 0)) desc,
                        c.clave
                    """
                ),
                {"obra_id": str(obra_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def rendimiento_por_cuadrilla(self, obra_id: UUID) -> list[dict[str, Any]]:
        """Lo ejecutado por cada cuadrilla (§5.1).

        No hay contraparte presupuestada: el presupuesto es por concepto y no
        reparte el trabajo entre cuadrillas. Lo que sí se puede comparar es su
        `rendimiento` de catálogo —lo que se espera que produzca— contra lo que
        produjo, y eso es lo que devuelve.
        """
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select cu.id as cuadrilla_id,
                           cu.clave as cuadrilla_clave,
                           cu.nombre as cuadrilla_nombre,
                           cu.rendimiento as rendimiento_esperado,
                           ct.razon_social as contratista_nombre,
                           count(act.id) as actividades,
                           sum(act.cant_ejecutada) as cantidad_ejecutada,
                           sum(act.cant_ejecutada * case
                                 when act.modo_pago = 'destajo'
                                   then act.precio_destajo
                                 else act.precio_unitario
                               end) as importe_ejecutado,
                           count(*) filter (where act.estatus = 'concluida')
                               as concluidas
                      from actividad act
                      join cuadrilla cu on cu.id = act.cuadrilla_id
                      left join contratista ct on ct.id = cu.contratista_id
                     where act.obra_id = :obra_id
                     group by cu.id, cu.clave, cu.nombre, cu.rendimiento,
                              ct.razon_social
                     order by importe_ejecutado desc nulls last
                    """
                ),
                {"obra_id": str(obra_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def resumen_por_obra(
        self, *, proyecto_id: UUID | None = None
    ) -> list[dict[str, Any]]:
        """Una fila por obra visible: presupuestado contra ejecutado (§5.1).

        Es la pantalla de «Presupuesto de obras» del Super intendente. Arranca en
        `obra`, así que el alcance por rol lo impone RLS y no se filtra a mano.

        Las obras URBA aparecen con presupuesto en cero, no desaparecen: una
        obra que se está ejecutando tiene que verse aunque no tenga con qué
        compararse.
        """
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select
                        o.id as obra_id,
                        o.clave as obra_clave,
                        o.estatus as obra_estatus,
                        o.avance_pct,
                        o.es_urba,
                        pr.clave as prototipo_clave,
                        c.clave  as cluster_clave,
                        pj.clave as proyecto_clave,
                        pj.id    as proyecto_id,
                        coalesce(p.monto_total, 0) as monto_presupuestado,
                        coalesce(eje.importe, 0)   as monto_ejecutado,
                        coalesce(eje.actividades, 0) as actividades
                      from obra o
                      join cluster c   on c.id = o.cluster_id
                      join proyecto pj on pj.id = c.proyecto_id
                      left join prototipo pr on pr.id = o.prototipo_id
                      left join presupuesto p
                        on p.prototipo_id = o.prototipo_id and p.vigente
                      left join lateral (
                          select count(*) as actividades,
                                 sum(act.cant_ejecutada * case
                                       when act.modo_pago = 'destajo'
                                         then act.precio_destajo
                                       else act.precio_unitario
                                     end) as importe
                            from actividad act
                           where act.obra_id = o.id
                      ) eje on true
                     where (cast(:proyecto_id as uuid) is null
                            or pj.id = cast(:proyecto_id as uuid))
                     order by
                        -- La desviación más grande primero, igual que la Torre
                        -- pone delante lo que estorba.
                        abs(coalesce(eje.importe, 0) - coalesce(p.monto_total, 0)) desc,
                        o.clave
                    """
                ),
                {"proyecto_id": str(proyecto_id) if proyecto_id else None},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]
