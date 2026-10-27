"""Repositorio de las partes de una obra y de sus plantas (migración 0074).

Nada aquí filtra por organización u obra para decidir qué es visible: lo impone RLS (§12.4).
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.domain.partes.cotizacion import CotizacionYaRespondida

__all__ = ["RepositorioPartesSQL"]


class RepositorioPartesSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def actividades_de_obra(self, obra_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select a.id, coalesce(a.descripcion, c.descripcion, '') as descripcion,
                           a.avance_pct, a.cant_base * a.precio_unitario as importe,
                           a.parte_independiente as independiente, a.fecha_inicio,
                           a.etapa_id, e.descripcion as etapa_nombre,
                           n.clave as nivel_clave
                      from actividad a
                      left join concepto c on c.id = a.concepto_id
                      left join etapa_constructiva e on e.id = a.etapa_id
                      left join nivel n on n.id = coalesce(a.nivel_id, e.nivel_id)
                     where a.obra_id = :obra_id
                     order by n.orden nulls last, e.orden nulls last, e.clave nulls last,
                              c.clave nulls last, a.id
                    """
                ),
                {"obra_id": str(obra_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def carga_por_etapa(self, obra_id: UUID) -> dict[str, Any]:
        claves = {
            str(f["id"]): f["clave"]
            for f in (
                await self._sesion.execute(
                    text(
                        """
                        select distinct e.id, e.clave
                          from actividad a join etapa_constructiva e on e.id = a.etapa_id
                         where a.obra_id = :obra_id
                        """
                    ),
                    {"obra_id": str(obra_id)},
                )
            ).mappings()
        }
        # Solo cuenta la ingeniería aplicada y no revertida (join, nunca una bandera propia).
        cargado = {
            f["etapa"]: Decimal(str(f["importe"]))
            for f in (
                await self._sesion.execute(
                    text(
                        """
                        select ili.etapa,
                               sum(coalesce(ili.importe, ili.cantidad * coalesce(ili.precio, 0))) as importe
                          from ingenieria_lote_insumo ili
                          join carga_datos cd on cd.id = ili.carga_id
                         where ili.obra_id = :obra_id
                           and cd.tipo = 'ingenieria_lote'
                           and cd.estatus = 'aplicado'
                           and cd.revertida_en is null
                           and ili.etapa is not null
                         group by ili.etapa
                        """
                    ),
                    {"obra_id": str(obra_id)},
                )
            ).mappings()
        }
        return {"claves": claves, "cargado": cargado}

    async def actividad_a_modificar(self, actividad_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select a.obra_id, a.cant_base, a.cant_programada, a.cant_prototipo,
                           coalesce(a.descripcion, c.descripcion, '') as descripcion,
                           case when a.parte_independiente then 'concepto:' || a.id::text
                                when a.etapa_id is not null then 'etapa:' || a.etapa_id::text
                                else 'sin_etapa:-' end as clave
                      from actividad a left join concepto c on c.id = a.concepto_id
                     where a.id = :id
                       for update of a
                    """
                ),
                {"id": str(actividad_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def aplicar_modificacion(
        self,
        actividad_id: UUID,
        *,
        tipo: str,
        cantidad: Any,
        cant_prototipo: Any,
        modo: str = "capturada",
    ) -> None:
        await self._sesion.execute(
            text(
                """
                update actividad
                   set cant_base = :cantidad,
                       cant_programada = least(cant_programada, :cantidad),
                       modo_cantidad = cast(:modo as modo_cantidad),
                       modificacion = cast(:tipo as tipo_modificacion),
                       cant_prototipo = coalesce(cant_prototipo, :prototipo)
                 where id = :id
                """
            ),
            {
                "id": str(actividad_id),
                "cantidad": cantidad,
                "tipo": tipo,
                "prototipo": cant_prototipo,
                "modo": modo,
            },
        )

    async def crear_actividad_nueva(self, datos: dict[str, Any]) -> UUID:
        actividad_id = uuid4()
        await self._sesion.execute(
            text(
                """
                insert into actividad
                    (id, org_id, obra_id, concepto_id, nivel_id, etapa_id, descripcion,
                     cant_base, cant_programada, cant_ejecutada, precio_unitario,
                     duracion_dias, modificacion, cant_prototipo, modo_cantidad)
                values
                    (:id, cast(current_setting('app.org_id') as uuid), :obra_id,
                     cast(:concepto_id as uuid), cast(:nivel_id as uuid), cast(:etapa_id as uuid),
                     :descripcion, :cantidad, :cantidad, 0, :precio_unitario, 1,
                     cast(:tipo as tipo_modificacion), 0, 'capturada')
                """
            ),
            {
                "id": str(actividad_id),
                "obra_id": str(datos["obra_id"]),
                "concepto_id": str(datos["concepto_id"]) if datos.get("concepto_id") else None,
                "nivel_id": str(datos["nivel_id"]) if datos.get("nivel_id") else None,
                "etapa_id": str(datos["etapa_id"]) if datos.get("etapa_id") else None,
                "descripcion": datos["descripcion"],
                "cantidad": datos["cantidad"],
                "precio_unitario": datos["precio_unitario"],
                "tipo": datos["tipo"],
            },
        )
        return actividad_id

    async def registrar_modificacion(self, **datos: Any) -> None:
        await self._sesion.execute(
            text(
                """
                insert into actividad_modificacion
                    (org_id, obra_id, actividad_id, tipo, cantidad_antes, delta,
                     cantidad_despues, nace_nueva, nota, usuario_id, rol)
                values
                    (cast(current_setting('app.org_id') as uuid), :obra_id, :actividad_id,
                     cast(:tipo as tipo_modificacion), :cantidad_antes, :delta,
                     :cantidad_despues, :nace_nueva, :nota, :usuario_id, :rol)
                """
            ),
            {k: (str(v) if k.endswith("_id") else v) for k, v in datos.items()},
        )

    async def modificaciones_de_obra(self, obra_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select m.id, m.actividad_id,
                           coalesce(a.descripcion, c.descripcion, '') as descripcion,
                           c.clave as concepto_clave, m.tipo::text as tipo, m.cantidad_antes,
                           m.delta, m.cantidad_despues, m.nace_nueva, m.nota, m.usuario_id,
                           u.nombre as usuario_nombre, m.rol, m.creada_en
                      from actividad_modificacion m
                      join actividad a on a.id = m.actividad_id
                      left join concepto c on c.id = a.concepto_id
                      left join usuario u on u.id = m.usuario_id
                     where m.obra_id = :obra_id
                     order by m.creada_en desc, m.id
                    """
                ),
                {"obra_id": str(obra_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def lineas_de_valuacion(self, obra_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select a.id, a.cant_base, a.precio_unitario, a.cant_estimada,
                           a.modo_cantidad::text as modo_cantidad, c.clave as concepto_clave,
                           coalesce(a.descripcion, c.descripcion, '') as descripcion,
                           case when a.parte_independiente then 'concepto:' || a.id::text
                                when a.etapa_id is not null then 'etapa:' || a.etapa_id::text
                                else 'sin_etapa:-' end as clave
                      from actividad a left join concepto c on c.id = a.concepto_id
                     where a.obra_id = :obra_id
                    """
                ),
                {"obra_id": str(obra_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def crear_presupuesto_parametrico(self, prototipo_id: UUID) -> UUID:
        presupuesto_id = uuid4()
        await self._sesion.execute(
            text(
                """
                insert into presupuesto (id, org_id, prototipo_id, version, vigente, origen, monto_total)
                values (:id, cast(current_setting('app.org_id') as uuid), :prototipo, 1, true,
                        'parametrico', 0)
                """
            ),
            {"id": str(presupuesto_id), "prototipo": str(prototipo_id)},
        )
        return presupuesto_id

    async def modificados_netos(self, obra_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select a.id as actividad_id, coalesce(a.descripcion, c.descripcion, '') as descripcion,
                           c.clave as concepto_clave, sum(m.delta) as delta, a.precio_unitario
                      from actividad_modificacion m
                      join actividad a on a.id = m.actividad_id
                      left join concepto c on c.id = a.concepto_id
                     where m.obra_id = :obra_id
                     group by a.id, c.clave, c.descripcion
                    having sum(m.delta) <> 0
                    """
                ),
                {"obra_id": str(obra_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    _COLUMNAS_COTIZACION = """
        c.id, c.obra_id, c.folio, c.metodo_precio, c.estado, c.factor, c.costo_entra, c.costo_sale,
        c.m2_ampliacion, c.precio_m2, c.precio_por_diferencia, c.precio_por_m2, c.precio, c.lineas,
        c.nota, c.creada_por, uc.nombre as creada_por_nombre, c.creada_en, c.respondida_por,
        c.respondida_en
    """

    async def crear_cotizacion(self, **datos: Any) -> dict[str, Any]:
        n = (
            await self._sesion.execute(
                text("select count(*) from cotizacion_cliente where obra_id = :o"),
                {"o": str(datos["obra_id"])},
            )
        ).scalar_one()
        folio = f"CZ-{datos['obra_clave']}-{int(n) + 1:03d}"
        cid = uuid4()
        await self._sesion.execute(
            text(
                """
                insert into cotizacion_cliente
                    (id, org_id, obra_id, folio, metodo_precio, factor, costo_entra, costo_sale,
                     m2_ampliacion, precio_m2, precio_por_diferencia, precio_por_m2, precio,
                     lineas, nota, creada_por)
                values
                    (:id, cast(current_setting('app.org_id') as uuid), :obra_id, :folio, :metodo,
                     :factor, :entra, :sale, :m2, :precio_m2, :por_diferencia, :por_m2, :precio,
                     cast(:lineas as jsonb), :nota, :usuario)
                """
            ),
            {
                "id": str(cid),
                "obra_id": str(datos["obra_id"]),
                "folio": folio,
                "metodo": datos["metodo"],
                "factor": datos["factor"],
                "entra": datos["costo_entra"],
                "sale": datos["costo_sale"],
                "m2": datos.get("m2_ampliacion"),
                "precio_m2": datos.get("precio_m2"),
                "por_diferencia": datos["precio_por_diferencia"],
                "por_m2": datos.get("precio_por_m2"),
                "precio": datos["precio"],
                "lineas": json.dumps(datos["lineas"]),
                "nota": datos.get("nota"),
                "usuario": str(datos["usuario_id"]),
            },
        )
        return await self._una_cotizacion(cid)

    async def _una_cotizacion(self, cotizacion_id: UUID) -> dict[str, Any]:
        fila = (
            await self._sesion.execute(
                text(
                    f"select {self._COLUMNAS_COTIZACION} from cotizacion_cliente c "
                    "left join usuario uc on uc.id = c.creada_por where c.id = :id"
                ),
                {"id": str(cotizacion_id)},
            )
        ).mappings().one()
        return dict(fila)

    async def cotizaciones_de_obra(self, obra_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"select {self._COLUMNAS_COTIZACION} from cotizacion_cliente c "
                    "left join usuario uc on uc.id = c.creada_por "
                    "where c.obra_id = :o order by c.creada_en desc, c.folio desc"
                ),
                {"o": str(obra_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def responder_cotizacion(
        self, cotizacion_id: UUID, *, aceptada: bool, usuario_id: UUID, nota: str | None
    ) -> dict[str, Any] | None:
        hay = (
            await self._sesion.execute(
                text("select estado from cotizacion_cliente where id = :id for update"),
                {"id": str(cotizacion_id)},
            )
        ).first()
        if hay is None:
            return None
        if hay[0] != "enviada":
            raise CotizacionYaRespondida("El cliente ya respondió esta cotización.")
        await self._sesion.execute(
            text(
                """
                update cotizacion_cliente
                   set estado = :estado, respondida_por = :usuario, respondida_en = now(),
                       nota = coalesce(:nota, nota)
                 where id = :id
                """
            ),
            {
                "estado": "aceptada" if aceptada else "rechazada",
                "usuario": str(usuario_id),
                "nota": nota,
                "id": str(cotizacion_id),
            },
        )
        return await self._una_cotizacion(cotizacion_id)

    async def catalogos_base(self) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select distinct on (p.plantas)
                           p.plantas, p.id, p.proyecto_id, p.clave, p.nombre, p.m2, p.niveles,
                           p.recamaras, count(n.id) as n_nodos
                      from prototipo p
                      left join prototipo_nodo n on n.prototipo_id = p.id
                     where p.plantas in (1, 2) and not p.de_una_obra
                     group by p.id
                     order by p.plantas, count(n.id) desc, p.created_at, p.clave
                    """
                )
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def plantas_de_obra(self, obra_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select o.plantas, p.plantas as plantas_del_prototipo
                      from obra o left join prototipo p on p.id = o.prototipo_id
                     where o.id = :id
                    """
                ),
                {"id": str(obra_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def marcar_independiente(self, actividad_id: UUID, independiente: bool) -> bool:
        r = await self._sesion.execute(
            text("update actividad set parte_independiente = :v where id = :id"),
            {"v": independiente, "id": str(actividad_id)},
        )
        return r.rowcount > 0

    async def fijar_plantas_de_obra(self, obra_id: UUID, plantas: int | None) -> bool:
        r = await self._sesion.execute(
            text("update obra set plantas = :p where id = :id"),
            {"p": plantas, "id": str(obra_id)},
        )
        return r.rowcount > 0

    async def fijar_plantas_de_prototipo(self, prototipo_id: UUID, plantas: int | None) -> bool:
        r = await self._sesion.execute(
            text("update prototipo set plantas = :p where id = :id"),
            {"p": plantas, "id": str(prototipo_id)},
        )
        return r.rowcount > 0

    async def parte_de_actividad(self, actividad_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select obra_id,
                           case when parte_independiente then 'concepto:' || id::text
                                when etapa_id is not null then 'etapa:' || etapa_id::text
                                else 'sin_etapa:-' end as clave
                      from actividad where id = :id
                    """
                ),
                {"id": str(actividad_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def estados_de_obra(self, obra_id: UUID) -> dict[str, str]:
        filas = (
            await self._sesion.execute(
                text("select clave, estado::text as estado from parte_estado where obra_id = :id"),
                {"id": str(obra_id)},
            )
        ).mappings().all()
        return {f["clave"]: f["estado"] for f in filas}

    async def fijar_estado(
        self,
        obra_id: UUID,
        clave: str,
        estado: str,
        usuario_id: UUID | None,
        *,
        programa_por_revisar: bool | None = None,
    ) -> None:
        await self._sesion.execute(
            text(
                """
                insert into parte_estado
                    (org_id, obra_id, clave, estado, actualizada_por, programa_por_revisar)
                values (current_setting('app.org_id')::uuid, :obra_id, :clave,
                        cast(:estado as estado_parte), cast(:usuario as uuid),
                        coalesce(:revisar, false))
                on conflict (obra_id, clave) do update
                   set estado = excluded.estado, actualizada_por = excluded.actualizada_por,
                       actualizada_en = now(),
                       programa_por_revisar =
                           coalesce(:revisar, parte_estado.programa_por_revisar)
                """
            ),
            {
                "obra_id": str(obra_id),
                "clave": clave,
                "estado": estado,
                "usuario": str(usuario_id) if usuario_id else None,
                "revisar": programa_por_revisar,
            },
        )

    async def programas_por_revisar(self, obra_id: UUID) -> set[str]:
        filas = (
            await self._sesion.execute(
                text(
                    "select clave from parte_estado "
                    "where obra_id = :id and programa_por_revisar"
                ),
                {"id": str(obra_id)},
            )
        ).mappings().all()
        return {f["clave"] for f in filas}

    async def registrar_transicion(
        self,
        *,
        obra_id: UUID,
        clave: str,
        accion: str,
        de: str,
        a: str,
        usuario_id: UUID,
        rol: str,
        nota: str | None,
    ) -> None:
        await self._sesion.execute(
            text(
                """
                insert into parte_transicion
                    (org_id, obra_id, clave, accion, de, a, usuario_id, rol, nota)
                values (current_setting('app.org_id')::uuid, :obra_id, :clave, :accion,
                        cast(:de as estado_parte), cast(:a as estado_parte), :usuario, :rol, :nota)
                """
            ),
            {
                "obra_id": str(obra_id),
                "clave": clave,
                "accion": accion,
                "de": de,
                "a": a,
                "usuario": str(usuario_id),
                "rol": rol,
                "nota": nota,
            },
        )

    async def bitacora_de_obra(self, obra_id: UUID, *, limite: int = 200) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select t.id, t.clave, t.accion, t.de::text as de, t.a::text as a,
                           t.usuario_id, u.nombre as usuario_nombre, t.rol, t.nota, t.creada_en
                      from parte_transicion t left join usuario u on u.id = t.usuario_id
                     where t.obra_id = :obra_id
                     order by t.creada_en desc, t.id
                     limit :limite
                    """
                ),
                {"obra_id": str(obra_id), "limite": limite},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def candado_de_obra(self, obra_id: UUID) -> bool | None:
        fila = (
            await self._sesion.execute(
                text("select candado_asignar from obra where id = :id"), {"id": str(obra_id)}
            )
        ).first()
        return bool(fila[0]) if fila is not None else None

    async def fijar_candado(self, obra_id: UUID, activo: bool) -> bool:
        r = await self._sesion.execute(
            text("update obra set candado_asignar = :v where id = :id"),
            {"v": activo, "id": str(obra_id)},
        )
        return r.rowcount > 0

    async def validaciones_con_anotacion(self, obra_id: UUID) -> set[str]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select distinct on (clave) clave, nota
                      from parte_transicion
                     where obra_id = :id and accion = 'validar'
                     order by clave, creada_en desc, id
                    """
                ),
                {"id": str(obra_id)},
            )
        ).mappings().all()
        return {f["clave"] for f in filas if (f["nota"] or "").strip()}
