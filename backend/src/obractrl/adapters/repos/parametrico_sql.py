"""SQL del Paramétrico: drivers por nivel y enlace de ranuras con el árbol de la obra (migración 0134). RLS por organización y obra."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioParametricoSQL"]

_SIN_UUID = "00000000-0000-0000-0000-000000000000"


class RepositorioParametricoSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    # --- la obra --------------------------------------------------------------------------------------------------------

    async def obra_visible(self, obra_id: UUID) -> bool:
        """La obra existe y está en el alcance de quien pregunta (RLS)."""
        fila = (await self._sesion.execute(text("select 1 from obra where id = :o"), {"o": str(obra_id)})).first()
        return fila is not None

    # --- drivers --------------------------------------------------------------------------------------------------------

    async def globales(self) -> dict[str, dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text("select clave, valor, modo, updated_at, actualizado_por from driver_valor where nivel = 'global'")
            )
        ).mappings().all()
        return {f["clave"]: dict(f) for f in filas}

    async def de_obra(self, obra_id: UUID) -> dict[str, dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text("select clave, valor, updated_at, actualizado_por from driver_valor where nivel = 'obra' and obra_id = :o"),
                {"o": str(obra_id)},
            )
        ).mappings().all()
        return {f["clave"]: dict(f) for f in filas}

    async def guardar_global(self, clave: str, valor: Decimal, modo: str, usuario_id: UUID) -> None:
        await self._sesion.execute(
            text(
                """
                insert into driver_valor (org_id, clave, nivel, valor, modo, actualizado_por)
                values (app.current_org_id(), :c, 'global', :v, :m, :u)
                on conflict (org_id, clave) where nivel = 'global'
                do update set valor = excluded.valor, modo = excluded.modo, actualizado_por = excluded.actualizado_por
                """
            ),
            {"c": clave, "v": valor, "m": modo, "u": str(usuario_id)},
        )

    async def guardar_de_obra(self, obra_id: UUID, clave: str, valor: Decimal, usuario_id: UUID) -> None:
        await self._sesion.execute(
            text(
                """
                insert into driver_valor (org_id, clave, nivel, obra_id, valor, actualizado_por)
                values (app.current_org_id(), :c, 'obra', :o, :v, :u)
                on conflict (org_id, obra_id, clave) where nivel = 'obra'
                do update set valor = excluded.valor, actualizado_por = excluded.actualizado_por
                """
            ),
            {"c": clave, "o": str(obra_id), "v": valor, "u": str(usuario_id)},
        )

    async def quitar_de_obra(self, obra_id: UUID, clave: str) -> bool:
        r = await self._sesion.execute(
            text("delete from driver_valor where nivel = 'obra' and obra_id = :o and clave = :c"), {"o": str(obra_id), "c": clave}
        )
        return bool(getattr(r, "rowcount", 0))

    # --- propuestas de cambio de driver (0141, F3) -------------------------------------------------------------------------

    _COLUMNAS_PROPUESTA = """
        p.id, p.clave, p.alcance, p.obra_id, p.accion, p.valor, p.modo, p.valor_anterior, p.modo_anterior, p.estado,
        p.propuso_id, u1.nombre as propuso_nombre, p.propuso_rol, p.propuesto_en,
        p.decidio_id, u2.nombre as decidio_nombre, p.decidio_rol, p.decidido_en, p.motivo
    """
    _DE_PROPUESTA = """
        from propuesta_de_driver p
        left join usuario u1 on u1.id = p.propuso_id
        left join usuario u2 on u2.id = p.decidio_id
    """

    async def propuestas_de_driver(
        self, *, estado: str | None = None, obra_id: UUID | None = None, clave: str | None = None, limite: int = 200
    ) -> list[dict[str, Any]]:
        """Las propuestas de cambio de driver, las más nuevas primero. Con `obra_id` entran las globales y las de esa obra."""
        filtros, params = [], {"limite": limite}
        if estado is not None:
            filtros.append("p.estado = :estado")
            params["estado"] = estado
        if obra_id is not None:
            filtros.append("(p.obra_id is null or p.obra_id = :obra)")
            params["obra"] = str(obra_id)
        if clave is not None:
            filtros.append("p.clave = :clave")
            params["clave"] = clave
        donde = f"where {' and '.join(filtros)}" if filtros else ""
        filas = (
            await self._sesion.execute(
                text(f"select {self._COLUMNAS_PROPUESTA} {self._DE_PROPUESTA} {donde} order by p.propuesto_en desc, p.id limit :limite"),
                params,
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def obtener_propuesta_de_driver(self, propuesta_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(f"select {self._COLUMNAS_PROPUESTA} {self._DE_PROPUESTA} where p.id = :i"), {"i": str(propuesta_id)}
            )
        ).mappings().first()
        return dict(fila) if fila else None

    async def registrar_propuesta_de_driver(
        self,
        *,
        clave: str,
        alcance: str,
        obra_id: UUID | None,
        accion: str,
        valor: Decimal | None,
        modo: str | None,
        valor_anterior: Decimal | None,
        modo_anterior: str | None,
        estado: str,
        propuso_id: UUID,
        propuso_rol: str,
        decidio_id: UUID | None,
        decidio_rol: str | None,
    ) -> UUID:
        decidida = estado != "pendiente"
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into propuesta_de_driver (org_id, clave, alcance, obra_id, accion, valor, modo, valor_anterior, modo_anterior,
                                                     estado, propuso_id, propuso_rol, decidio_id, decidio_rol, decidido_en)
                    values (app.current_org_id(), :c, :al, cast(:o as uuid), :ac, :v, :m, :va, :ma, :e, :pi, :pr,
                            cast(:di as uuid), :dr, case when :dec then now() end)
                    returning id
                    """
                ),
                {
                    "c": clave, "al": alcance, "o": str(obra_id) if obra_id else None, "ac": accion, "v": valor, "m": modo,
                    "va": valor_anterior, "ma": modo_anterior, "e": estado, "pi": str(propuso_id), "pr": propuso_rol,
                    "di": str(decidio_id) if decidio_id else None, "dr": decidio_rol, "dec": decidida,
                },
            )
        ).scalar_one()

    async def decidir_propuesta_de_driver(
        self, propuesta_id: UUID, *, estado: str, decidio_id: UUID, decidio_rol: str, motivo: str | None
    ) -> None:
        await self._sesion.execute(
            text(
                "update propuesta_de_driver set estado = :e, decidio_id = :d, decidio_rol = :r, decidido_en = now(), motivo = :m "
                "where id = :i and estado = 'pendiente'"
            ),
            {"e": estado, "d": str(decidio_id), "r": decidio_rol, "m": motivo, "i": str(propuesta_id)},
        )

    # --- enlaces de ranura ----------------------------------------------------------------------------------------------

    async def enlaces(self, obra_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select e.id, e.ranura, e.nivel_id, e.etapa_id, e.ubicacion, e.espacio_id, e.concepto_id,
                           c.clave as concepto_clave, c.descripcion as concepto_descripcion, u.clave as unidad
                      from enlace_ranura e
                      join concepto c on c.id = e.concepto_id
                      left join unidad u on u.id = c.unidad_id
                     where e.obra_id = :o
                     order by e.ranura, e.created_at, e.id
                    """
                ),
                {"o": str(obra_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def partidas(self, obra_id: UUID) -> list[dict[str, Any]]:
        """Los nodos de concepto del árbol de la obra, con el nivel, la etapa y el espacio del ancestro más cercano que los fija (el espacio sale de
        `espacio_nodo`, la rama del árbol que la obra asignó a un espacio; sin él, la partida es general)."""
        filas = (
            await self._sesion.execute(
                text(
                    """
                    with recursive nodos as (
                      select n.id, n.parent_id, n.tipo, n.nombre, n.concepto_id, n.nivel_id, n.etapa_id, n.orden, en.espacio_id
                        from prototipo_nodo n join obra o on o.prototipo_id = n.prototipo_id
                        left join espacio_nodo en on en.prototipo_nodo_id = n.id and en.obra_id = o.id
                       where o.id = :o
                    ), subida as (
                      select id as hoja, parent_id, nivel_id, etapa_id, espacio_id from nodos where tipo = 'concepto'
                      union all
                      select s.hoja, p.parent_id, coalesce(s.nivel_id, p.nivel_id), coalesce(s.etapa_id, p.etapa_id),
                             coalesce(s.espacio_id, p.espacio_id)
                        from subida s join nodos p on p.id = s.parent_id
                    )
                    select h.id, h.concepto_id, h.nombre, h.orden, s.nivel_id, s.etapa_id, s.espacio_id,
                           c.clave as concepto_clave, c.descripcion as concepto_descripcion
                      from nodos h join subida s on s.hoja = h.id and s.parent_id is null
                      join concepto c on c.id = h.concepto_id
                     where h.tipo = 'concepto'
                     order by h.orden, h.nombre, h.id
                    """
                ),
                {"o": str(obra_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def capas(self, obra_id: UUID) -> dict[str, list[dict[str, Any]]]:
        """Los niveles y las etapas que el árbol de la obra usa: de ahí se eligen las capas de un enlace."""
        niveles = (
            await self._sesion.execute(
                text(
                    """
                    select distinct v.id, v.clave, v.descripcion, v.orden, v.numero_de_nivel, app.numero_de_nivel(v.id) as numero_efectivo
                      from prototipo_nodo n join obra o on o.prototipo_id = n.prototipo_id join nivel v on v.id = n.nivel_id
                     where o.id = :o order by v.orden, v.clave
                    """
                ),
                {"o": str(obra_id)},
            )
        ).mappings().all()
        etapas = (
            await self._sesion.execute(
                text(
                    """
                    select distinct v.id, v.clave, v.descripcion, v.orden
                      from prototipo_nodo n join obra o on o.prototipo_id = n.prototipo_id join etapa_constructiva v on v.id = n.etapa_id
                     where o.id = :o order by v.orden, v.clave
                    """
                ),
                {"o": str(obra_id)},
            )
        ).mappings().all()
        espacios = (
            await self._sesion.execute(
                text("select id, nombre, tipo, nivel_id, area_m2, orden from espacio where obra_id = :o order by orden, lower(nombre), id"),
                {"o": str(obra_id)},
            )
        ).mappings().all()
        return {"niveles": [dict(f) for f in niveles], "etapas": [dict(f) for f in etapas], "espacios": [dict(f) for f in espacios]}

    async def fijar_numero_de_nivel(self, nivel_id: UUID, numero: int | None) -> dict[str, Any] | None:
        """El número de nivel explícito (F5, 0141); `None` lo quita. Devuelve el nivel con su número efectivo, o `None` si no existe."""
        r = await self._sesion.execute(text("update nivel set numero_de_nivel = :n where id = :i"), {"n": numero, "i": str(nivel_id)})
        if not getattr(r, "rowcount", 0):
            return None
        fila = (
            await self._sesion.execute(
                text(
                    "select id, clave, descripcion, orden, numero_de_nivel, app.numero_de_nivel(id) as numero_efectivo from nivel where id = :i"
                ),
                {"i": str(nivel_id)},
            )
        ).mappings().one()
        return dict(fila)

    async def concepto_por_clave(self, clave: str) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select c.id, c.clave, c.descripcion, u.clave as unidad
                      from concepto c left join unidad u on u.id = c.unidad_id
                     where upper(c.clave) = upper(:k)
                    """
                ),
                {"k": clave.strip()},
            )
        ).mappings().first()
        return dict(fila) if fila else None

    async def nivel_o_etapa_existe(self, tabla: str, ident: UUID) -> bool:
        if tabla not in ("nivel", "etapa_constructiva"):  # pragma: no cover - defensa: la tabla la fija el caso de uso
            raise ValueError(tabla)
        fila = (await self._sesion.execute(text(f"select 1 from {tabla} where id = :i"), {"i": str(ident)})).first()  # noqa: S608
        return fila is not None

    async def espacio_existe(self, obra_id: UUID, espacio_id: UUID) -> bool:
        """El espacio es de esa obra (y se ve con el alcance de quien pregunta)."""
        fila = (
            await self._sesion.execute(
                text("select 1 from espacio where id = :e and obra_id = :o"), {"e": str(espacio_id), "o": str(obra_id)}
            )
        ).first()
        return fila is not None

    async def guardar_enlace(
        self,
        *,
        obra_id: UUID,
        ranura: str,
        nivel_id: UUID | None,
        etapa_id: UUID | None,
        ubicacion: str | None,
        concepto_id: UUID,
        usuario_id: UUID,
        espacio_id: UUID | None = None,
    ) -> tuple[UUID, bool]:
        """Crea el enlace de esa capa o cambia su concepto si ya existe. Devuelve (id, creado)."""
        existente = (
            await self._sesion.execute(
                text(
                    """
                    select id from enlace_ranura
                     where obra_id = :o and ranura = :r
                       and coalesce(nivel_id, cast(:z as uuid)) = coalesce(cast(:n as uuid), cast(:z as uuid))
                       and coalesce(etapa_id, cast(:z as uuid)) = coalesce(cast(:e as uuid), cast(:z as uuid))
                       and coalesce(ubicacion, '') = coalesce(:u, '')
                       and coalesce(espacio_id, cast(:z as uuid)) = coalesce(cast(:s as uuid), cast(:z as uuid))
                    """
                ),
                {
                    "o": str(obra_id), "r": ranura, "z": _SIN_UUID, "u": ubicacion,
                    "n": str(nivel_id) if nivel_id else None, "e": str(etapa_id) if etapa_id else None,
                    "s": str(espacio_id) if espacio_id else None,
                },
            )
        ).scalar_one_or_none()
        if existente is not None:
            await self._sesion.execute(
                text("update enlace_ranura set concepto_id = :c, actualizado_por = :u where id = :i"),
                {"c": str(concepto_id), "u": str(usuario_id), "i": str(existente)},
            )
            return UUID(str(existente)), False
        nuevo = (
            await self._sesion.execute(
                text(
                    """
                    insert into enlace_ranura (org_id, obra_id, ranura, nivel_id, etapa_id, ubicacion, espacio_id, concepto_id, actualizado_por)
                    values (app.current_org_id(), :o, :r, cast(:n as uuid), cast(:e as uuid), :u, cast(:s as uuid), :c, :a) returning id
                    """
                ),
                {
                    "o": str(obra_id), "r": ranura, "u": ubicacion, "c": str(concepto_id), "a": str(usuario_id),
                    "n": str(nivel_id) if nivel_id else None, "e": str(etapa_id) if etapa_id else None,
                    "s": str(espacio_id) if espacio_id else None,
                },
            )
        ).scalar_one()
        return UUID(str(nuevo)), True

    async def quitar_enlace(self, obra_id: UUID, enlace_id: UUID) -> bool:
        r = await self._sesion.execute(
            text("delete from enlace_ranura where id = :i and obra_id = :o"), {"i": str(enlace_id), "o": str(obra_id)}
        )
        return bool(getattr(r, "rowcount", 0))
