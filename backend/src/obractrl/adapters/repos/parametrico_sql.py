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

    # --- enlaces de ranura ----------------------------------------------------------------------------------------------

    async def enlaces(self, obra_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select e.id, e.ranura, e.nivel_id, e.etapa_id, e.ubicacion, e.concepto_id,
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
        """Los nodos de concepto del árbol de la obra, con el nivel y la etapa del ancestro más cercano que los fija."""
        filas = (
            await self._sesion.execute(
                text(
                    """
                    with recursive nodos as (
                      select n.id, n.parent_id, n.tipo, n.nombre, n.concepto_id, n.nivel_id, n.etapa_id, n.orden
                        from prototipo_nodo n join obra o on o.prototipo_id = n.prototipo_id
                       where o.id = :o
                    ), subida as (
                      select id as hoja, parent_id, nivel_id, etapa_id from nodos where tipo = 'concepto'
                      union all
                      select s.hoja, p.parent_id, coalesce(s.nivel_id, p.nivel_id), coalesce(s.etapa_id, p.etapa_id)
                        from subida s join nodos p on p.id = s.parent_id
                    )
                    select h.id, h.concepto_id, h.nombre, h.orden, s.nivel_id, s.etapa_id
                      from nodos h join subida s on s.hoja = h.id and s.parent_id is null
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
                    select distinct v.id, v.clave, v.descripcion, v.orden
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
        return {"niveles": [dict(f) for f in niveles], "etapas": [dict(f) for f in etapas]}

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
                    """
                ),
                {
                    "o": str(obra_id), "r": ranura, "z": _SIN_UUID, "u": ubicacion,
                    "n": str(nivel_id) if nivel_id else None, "e": str(etapa_id) if etapa_id else None,
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
                    insert into enlace_ranura (org_id, obra_id, ranura, nivel_id, etapa_id, ubicacion, concepto_id, actualizado_por)
                    values (app.current_org_id(), :o, :r, cast(:n as uuid), cast(:e as uuid), :u, :c, :a) returning id
                    """
                ),
                {
                    "o": str(obra_id), "r": ranura, "u": ubicacion, "c": str(concepto_id), "a": str(usuario_id),
                    "n": str(nivel_id) if nivel_id else None, "e": str(etapa_id) if etapa_id else None,
                },
            )
        ).scalar_one()
        return UUID(str(nuevo)), True

    async def quitar_enlace(self, obra_id: UUID, enlace_id: UUID) -> bool:
        r = await self._sesion.execute(
            text("delete from enlace_ranura where id = :i and obra_id = :o"), {"i": str(enlace_id), "o": str(obra_id)}
        )
        return bool(getattr(r, "rowcount", 0))
