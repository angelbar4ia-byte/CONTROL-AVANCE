"""SQL del árbol propio de una obra (migración 0107, D-624): el prototipo de un solo uso, su presupuesto en borrador."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioArbolDeObraSQL"]

_FORMA_DISPONIBLE = False
"""Se vuelve `True` cuando la columna `obra.forma_de_arranque` (0109) ya existe y no se vuelve a preguntar."""

_COLUMNAS_NODO = (
    "parent_id, tipo, nombre, clave, concepto_id, nivel_id, etapa_id, orden, cantidad, ponderacion, "
    "modo_cantidad, ocurrencia, wbs, nivel_erp"
)


class RepositorioArbolDeObraSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def obra(self, obra_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select o.id, o.clave, o.prototipo_id, o.prototipo_origen_id, p.clave as prototipo_clave, p.nombre as prototipo_nombre,
                           p.de_una_obra
                      from obra o join prototipo p on p.id = o.prototipo_id where o.id = :id
                    """
                ),
                {"id": str(obra_id)},
            )
        ).mappings().first()
        return dict(fila) if fila else None

    # --- el clon ---------------------------------------------------------------------------------------------

    async def clonar(self, prototipo_id: UUID, clave: str) -> tuple[UUID, dict[UUID, UUID]]:
        """Un prototipo de un solo uso con el mismo árbol (cantidades incluidas) y el presupuesto vigente como versión 1."""
        s = self._sesion
        nuevo = UUID(
            str(
                (
                    await s.execute(
                        text(
                            """
                            insert into prototipo (org_id, proyecto_id, clave, nombre, m2, niveles, recamaras, plantas, de_una_obra)
                            select org_id, proyecto_id, :clave, nombre, m2, niveles, recamaras, plantas, true
                              from prototipo where id = :id returning id
                            """
                        ),
                        {"clave": clave, "id": str(prototipo_id)},
                    )
                ).scalar_one()
            )
        )
        origen = (
            await s.execute(
                text(f"select id, {_COLUMNAS_NODO} from prototipo_nodo where prototipo_id = :id"), {"id": str(prototipo_id)}
            )
        ).mappings().all()
        por_id = {f["id"]: dict(f) for f in origen}
        mapa: dict[Any, Any] = {}
        pendientes = set(por_id)
        while pendientes:
            listos = [n for n in pendientes if por_id[n]["parent_id"] is None or por_id[n]["parent_id"] in mapa]
            if not listos:
                raise ValueError("El árbol del prototipo tiene nodos sin su padre.")
            for n in listos:
                f = por_id[n]
                nid = (
                    await s.execute(
                        text(
                            f"""
                            insert into prototipo_nodo (org_id, prototipo_id, {_COLUMNAS_NODO})
                            values (app.current_org_id(), :p, cast(:parent as uuid), :tipo, :nombre, :clave, cast(:concepto as uuid),
                                    cast(:nivel as uuid), cast(:etapa as uuid), :orden, :cantidad, :ponderacion,
                                    :modo, :ocurrencia, :wbs, :nivel_erp)
                            returning id
                            """
                        ),
                        {
                            "p": str(nuevo), "parent": str(mapa[f["parent_id"]]) if f["parent_id"] else None, "tipo": f["tipo"],
                            "nombre": f["nombre"], "clave": f["clave"], "concepto": str(f["concepto_id"]) if f["concepto_id"] else None,
                            "nivel": str(f["nivel_id"]) if f["nivel_id"] else None, "etapa": str(f["etapa_id"]) if f["etapa_id"] else None,
                            "orden": f["orden"], "cantidad": f["cantidad"], "ponderacion": f["ponderacion"],
                            "modo": f["modo_cantidad"], "ocurrencia": f["ocurrencia"], "wbs": f["wbs"], "nivel_erp": f["nivel_erp"],
                        },
                    )
                ).scalar_one()
                mapa[n] = UUID(str(nid))
                pendientes.discard(n)
        # El presupuesto vigente pasa como la versión 1 del clon, ya confirmada y activa.
        vigente = (
            await s.execute(
                text("select id, monto_total from presupuesto where prototipo_id = :id and vigente"), {"id": str(prototipo_id)}
            )
        ).mappings().first()
        if vigente is not None:
            nuevo_p = (
                await s.execute(
                    text(
                        """
                        insert into presupuesto (org_id, prototipo_id, version, vigente, origen, monto_total, estado, nota)
                        values (app.current_org_id(), :p, 1, true, 'clon', :m, 'confirmada', 'Copia del prototipo base') returning id
                        """
                    ),
                    {"p": str(nuevo), "m": vigente["monto_total"]},
                )
            ).scalar_one()
            for viejo, nodo_nuevo in mapa.items():
                await s.execute(
                    text(
                        """
                        insert into partida_presupuesto (org_id, presupuesto_id, concepto_id, prototipo_nodo_id, cantidad,
                                                         precio_unitario, importe, orden)
                        select org_id, :np, concepto_id, :nn, cantidad, precio_unitario, importe, orden
                          from partida_presupuesto where presupuesto_id = :pv and prototipo_nodo_id = :nv
                        """
                    ),
                    {"np": str(nuevo_p), "nn": str(nodo_nuevo), "pv": str(vigente["id"]), "nv": str(viejo)},
                )
        return nuevo, {UUID(str(k)): v for k, v in mapa.items()}

    async def clave_libre(self, base: str) -> str:
        clave, n = base, 1
        while (await self._sesion.execute(text("select 1 from prototipo where clave = :c"), {"c": clave})).first() is not None:
            n += 1
            clave = f"{base}-{n}"
        return clave

    async def apuntar_obra(self, obra_id: UUID, prototipo_id: UUID, mapa: dict[UUID, UUID]) -> int:
        """La obra pasa al prototipo nuevo y sus partidas se re-ligan a los nodos copiados."""
        await self._sesion.execute(
            text("update obra set prototipo_origen_id = prototipo_id, prototipo_id = :p where id = :o"),
            {"p": str(prototipo_id), "o": str(obra_id)},
        )
        n = 0
        for viejo, nuevo in mapa.items():
            r = await self._sesion.execute(
                text("update actividad set prototipo_nodo_id = :n where obra_id = :o and prototipo_nodo_id = :v"),
                {"n": str(nuevo), "o": str(obra_id), "v": str(viejo)},
            )
            n += r.rowcount or 0
        return n

    # --- el borrador ------------------------------------------------------------------------------------------

    async def borrador(self, prototipo_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text("select id, version from presupuesto where prototipo_id = :p and estado = 'borrador'"), {"p": str(prototipo_id)}
            )
        ).mappings().first()
        return dict(fila) if fila else None

    async def asegurar_borrador(self, prototipo_id: UUID) -> UUID:
        """El borrador que junta los cambios: nace con las partidas de la versión vigente, en el primer cambio."""
        s = self._sesion
        existente = await self.borrador(prototipo_id)
        if existente:
            return UUID(str(existente["id"]))
        vigente = (
            await s.execute(
                text("select id, monto_total from presupuesto where prototipo_id = :p and vigente"), {"p": str(prototipo_id)}
            )
        ).mappings().first()
        siguiente = (
            await s.execute(text("select coalesce(max(version), 0) + 1 from presupuesto where prototipo_id = :p"), {"p": str(prototipo_id)})
        ).scalar_one()
        nuevo = UUID(
            str(
                (
                    await s.execute(
                        text(
                            """
                            insert into presupuesto (org_id, prototipo_id, version, vigente, origen, monto_total, estado)
                            values (app.current_org_id(), :p, :v, false, 'borrador', :m, 'borrador') returning id
                            """
                        ),
                        {"p": str(prototipo_id), "v": siguiente, "m": vigente["monto_total"] if vigente else 0},
                    )
                ).scalar_one()
            )
        )
        if vigente:
            await s.execute(
                text(
                    """
                    insert into partida_presupuesto (org_id, presupuesto_id, concepto_id, prototipo_nodo_id, cantidad,
                                                     precio_unitario, importe, orden)
                    select org_id, :n, concepto_id, prototipo_nodo_id, cantidad, precio_unitario, importe, orden
                      from partida_presupuesto where presupuesto_id = :v
                    """
                ),
                {"n": str(nuevo), "v": str(vigente["id"])},
            )
        return nuevo

    async def versiones(self, prototipo_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select p.id, p.version, p.estado, p.vigente, p.nota, p.monto_total, p.created_at,
                           (select count(*) from partida_presupuesto x where x.presupuesto_id = p.id) as partidas
                      from presupuesto p where p.prototipo_id = :p order by p.version desc
                    """
                ),
                {"p": str(prototipo_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def presupuesto(self, presupuesto_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text("select id, prototipo_id, estado, vigente from presupuesto where id = :id"), {"id": str(presupuesto_id)}
            )
        ).mappings().first()
        return dict(fila) if fila else None

    async def confirmar(self, presupuesto_id: UUID, nota: str | None) -> None:
        await self._sesion.execute(
            text(
                """
                update presupuesto set estado = 'confirmada', nota = :n,
                       monto_total = coalesce((select sum(importe) from partida_presupuesto where presupuesto_id = :id), 0)
                 where id = :id
                """
            ),
            {"id": str(presupuesto_id), "n": nota},
        )

    async def activar(self, presupuesto_id: UUID, prototipo_id: UUID) -> None:
        await self._sesion.execute(text("update presupuesto set vigente = false where prototipo_id = :p"), {"p": str(prototipo_id)})
        await self._sesion.execute(text("update presupuesto set vigente = true where id = :id"), {"id": str(presupuesto_id)})

    # --- los nodos --------------------------------------------------------------------------------------------

    async def nodos(self, prototipo_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select n.id, n.parent_id, n.tipo, n.nombre, n.clave, n.concepto_id, n.etapa_id, n.orden, n.cantidad,
                           c.clave as concepto_clave, c.descripcion as concepto_descripcion, u.clave as unidad
                      from prototipo_nodo n
                      left join concepto c on c.id = n.concepto_id
                      left join unidad u on u.id = c.unidad_id
                     where n.prototipo_id = :p order by n.orden, n.nombre
                    """
                ),
                {"p": str(prototipo_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def nodo(self, nodo_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text("select id, prototipo_id, parent_id, tipo, nombre, etapa_id, concepto_id from prototipo_nodo where id = :id"),
                {"id": str(nodo_id)},
            )
        ).mappings().first()
        return dict(fila) if fila else None

    async def crear_nodo(
        self, *, prototipo_id: UUID, parent_id: UUID | None, tipo: str, nombre: str, clave: str | None, concepto_id: UUID | None
    ) -> UUID:
        orden = (
            await self._sesion.execute(
                text(
                    "select coalesce(max(orden), 0) + 1 from prototipo_nodo where prototipo_id = :p "
                    "and parent_id is not distinct from cast(:parent as uuid)"
                ),
                {"p": str(prototipo_id), "parent": str(parent_id) if parent_id else None},
            )
        ).scalar_one()
        nuevo = (
            await self._sesion.execute(
                text(
                    """
                    insert into prototipo_nodo (org_id, prototipo_id, parent_id, tipo, nombre, clave, concepto_id, orden)
                    values (app.current_org_id(), :p, cast(:parent as uuid), cast(:tipo as tipo_prototipo_nodo), :nombre, :clave,
                            cast(:concepto as uuid), :orden) returning id
                    """
                ),
                {
                    "p": str(prototipo_id), "parent": str(parent_id) if parent_id else None, "tipo": tipo, "nombre": nombre,
                    "clave": clave, "concepto": str(concepto_id) if concepto_id else None, "orden": orden,
                },
            )
        ).scalar_one()
        return UUID(str(nuevo))

    async def partida_al_borrador(self, borrador_id: UUID, nodo_id: UUID, concepto_id: UUID) -> None:
        """Un concepto nuevo en el árbol entra al borrador sin cantidad y con el precio vigente del concepto."""
        await self._sesion.execute(
            text(
                """
                insert into partida_presupuesto (org_id, presupuesto_id, concepto_id, prototipo_nodo_id, cantidad, precio_unitario, importe, orden)
                values (app.current_org_id(), :b, :c, :n, 0,
                        coalesce((select precio_unitario from cpu where concepto_id = :c and vigente and variante is null limit 1), 0),
                        0, coalesce((select max(orden) + 1 from partida_presupuesto where presupuesto_id = :b), 1))
                """
            ),
            {"b": str(borrador_id), "c": str(concepto_id), "n": str(nodo_id)},
        )

    async def fijar_cantidad(self, prototipo_id: UUID, borrador_id: UUID, nodo_id: UUID, cantidad: Decimal) -> None:
        """La cantidad de una partida del árbol (cargada de una ingeniería) y la de su renglón en el borrador."""
        s = self._sesion
        await s.execute(
            text("update prototipo_nodo set cantidad = :c, modo_cantidad = 'cargada' where id = :n and prototipo_id = :p"),
            {"c": cantidad, "n": str(nodo_id), "p": str(prototipo_id)},
        )
        await s.execute(
            text(
                "update partida_presupuesto set cantidad = :c, importe = round(:c * precio_unitario, 2) "
                "where presupuesto_id = :b and prototipo_nodo_id = :n"
            ),
            {"c": cantidad, "b": str(borrador_id), "n": str(nodo_id)},
        )
        await s.execute(
            text(
                "update presupuesto set monto_total = coalesce((select sum(importe) from partida_presupuesto "
                "where presupuesto_id = :b), 0) where id = :b"
            ),
            {"b": str(borrador_id)},
        )

    async def concepto_por_clave(self, clave: str) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text("select id, clave, descripcion from concepto where clave = :c limit 1"), {"c": clave}
            )
        ).mappings().first()
        return dict(fila) if fila else None

    async def ajustar_nodo(self, nodo_id: UUID, nombre: str | None, orden: int | None) -> None:
        await self._sesion.execute(
            text("update prototipo_nodo set nombre = coalesce(:n, nombre), orden = coalesce(:o, orden) where id = :id"),
            {"id": str(nodo_id), "n": nombre, "o": orden},
        )

    async def subarbol(self, nodo_id: UUID) -> list[UUID]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    with recursive r as (select id from prototipo_nodo where id = :id
                                         union all select h.id from prototipo_nodo h join r on h.parent_id = r.id)
                    select id from r
                    """
                ),
                {"id": str(nodo_id)},
            )
        ).scalars().all()
        return [UUID(str(i)) for i in filas]

    async def partidas_de_obra_en(self, nodos: list[UUID]) -> int:
        n = (
            await self._sesion.execute(
                text("select count(*) from actividad where prototipo_nodo_id = any(cast(:n as uuid[]))"), {"n": [str(x) for x in nodos]}
            )
        ).scalar_one()
        return int(n)

    async def eliminar_nodo(self, nodo_id: UUID, borrador_id: UUID, subarbol: list[UUID]) -> None:
        await self._sesion.execute(
            text("delete from partida_presupuesto where presupuesto_id = :b and prototipo_nodo_id = any(cast(:n as uuid[]))"),
            {"b": str(borrador_id), "n": [str(x) for x in subarbol]},
        )
        await self._sesion.execute(text("delete from prototipo_nodo where id = :id"), {"id": str(nodo_id)})

    async def concepto(self, concepto_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text("select id, clave, descripcion from concepto where id = :id"), {"id": str(concepto_id)}
            )
        ).mappings().first()
        return dict(fila) if fila else None

    async def suma_del_borrador(self, borrador_id: UUID) -> Decimal:
        return Decimal(
            str(
                (
                    await self._sesion.execute(
                        text("select coalesce(sum(importe), 0) from partida_presupuesto where presupuesto_id = :id"), {"id": str(borrador_id)}
                    )
                ).scalar_one()
            )
        )

    async def partidas_de_la_obra(self, obra_id: UUID) -> int:
        """Cuántas partidas (actividades) tiene la obra: si ya se generaron, «Generar actividades» sobra."""
        return int(
            (await self._sesion.execute(text("select count(*) from actividad where obra_id = :o"), {"o": str(obra_id)})).scalar_one()
        )

    async def trabajo_real_de_la_obra(self, obra_id: UUID) -> str | None:
        """Lo que ya no es diseño: avance ejecutado, registros de avance o estimaciones; `None` si no hay nada de eso."""
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select exists (select 1 from actividad where obra_id = :o and cant_ejecutada > 0) as avance,
                           exists (select 1 from registro_avance where obra_id = :o) as registros,
                           exists (select 1 from estimacion where obra_id = :o) as estimaciones
                    """
                ),
                {"o": str(obra_id)},
            )
        ).mappings().one()
        if fila["avance"] or fila["registros"]:
            return "La obra ya tiene avance ejecutado."
        if fila["estimaciones"]:
            return "La obra ya tiene estimaciones."
        return None

    async def eliminar_obra(self, obra_id: UUID, prototipo_id: UUID, borrar_prototipo: bool) -> None:
        """Borra la obra (todo lo suyo cae en cascada) y, si era un prototipo de un solo uso, también ese prototipo."""
        await self._sesion.execute(text("delete from obra where id = :o"), {"o": str(obra_id)})
        if borrar_prototipo:
            await self._sesion.execute(
                text("delete from prototipo where id = :p and de_una_obra and not exists (select 1 from obra where prototipo_id = :p)"),
                {"p": str(prototipo_id)},
            )

    async def reiniciar_obra(self, obra_id: UUID, prototipo_id: UUID, origen_id: UUID | None) -> dict[str, int]:
        """Vuelve la obra al principio del diseño: se queda con su cluster y sus planos (los archivos), sin lo hecho encima.

        Borra partidas, programa, estados de las partes, y lo medido en los planos (trazos, mediciones, notas, enlaces).
        Si la obra tenía un árbol propio copiado de un prototipo base, regresa a ese prototipo y se borra la copia.
        """
        s = self._sesion
        o = {"o": str(obra_id)}

        async def borrar(sql: str) -> int:
            return int((await s.execute(text(sql), o)).rowcount or 0)

        trazos = await borrar("delete from trazo where plano_id in (select id from plano where obra_id = :o)")
        await borrar("delete from medicion where plano_id in (select id from plano where obra_id = :o)")
        await borrar("delete from nota_plano where plano_id in (select id from plano where obra_id = :o)")
        await borrar("delete from plano_enlace where plano_id in (select id from plano where obra_id = :o)")
        actividades = await borrar("delete from actividad where obra_id = :o")
        await borrar("delete from programa_obra where obra_id = :o")
        # `parte_transicion` es una bitácora de solo agregar: se conserva como historial de lo que se hizo.
        # Las partes vuelven a «cuantificando»: ese registro no se borra (el rol de la app solo lo agrega y lo cambia).
        await borrar("update parte_estado set estado = 'cuantificando' where obra_id = :o")
        await borrar("delete from desviacion where obra_id = :o")
        volvio = 0
        if origen_id is not None:
            await s.execute(
                text("update obra set prototipo_id = :origen, prototipo_origen_id = null where id = :o"),
                {"origen": str(origen_id), "o": str(obra_id)},
            )
            await s.execute(
                text("delete from prototipo where id = :p and de_una_obra and not exists (select 1 from obra where prototipo_id = :p)"),
                {"p": str(prototipo_id)},
            )
            volvio = 1
        return {"trazos": trazos, "actividades": actividades, "volvio_al_base": volvio}

    async def _hay_forma_de_arranque(self) -> bool:
        """La columna llega con la migración 0109; el código puede desplegarse antes y no debe tumbar nada (expand → contract)."""
        global _FORMA_DISPONIBLE
        if not _FORMA_DISPONIBLE:
            _FORMA_DISPONIBLE = bool(
                (
                    await self._sesion.execute(
                        text(
                            "select exists (select 1 from information_schema.columns "
                            "where table_name = 'obra' and column_name = 'forma_de_arranque')"
                        )
                    )
                ).scalar_one()
            )
        return _FORMA_DISPONIBLE

    async def fijar_forma_de_arranque(self, obra_id: UUID, forma: str) -> None:
        if not await self._hay_forma_de_arranque():
            return
        await self._sesion.execute(
            text("update obra set forma_de_arranque = :f where id = :o"), {"f": forma, "o": str(obra_id)}
        )

    async def forma_de_arranque(self, obra_id: UUID) -> str | None:
        if not await self._hay_forma_de_arranque():
            return None
        return (
            await self._sesion.execute(text("select forma_de_arranque from obra where id = :o"), {"o": str(obra_id)})
        ).scalar_one_or_none()

    async def prototipo(self, prototipo_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text("select id, clave, nombre, de_una_obra from prototipo where id = :p"), {"p": str(prototipo_id)}
            )
        ).mappings().first()
        return dict(fila) if fila else None
