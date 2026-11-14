"""SQL de los insumos de los elementos paramétricos (migración 0129): leer la base de insumos con su familia y subfamilia,
los insumos que se agregan a un elemento y el alta de insumos provisionales. RLS por organización."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.domain.cuantificacion.insumos_permitidos import Insumo, clase_de_insumo

__all__ = ["RepositorioInsumosDeElementoSQL"]

_BASE = """
    select i.id, i.clave, i.descripcion, i.tipo::text as tipo, u.clave as unidad, i.provisional,
           coalesce(i.costo_base_actualizado, i.costo_base) as precio,
           coalesce(p.nombre, f.nombre) as familia,
           case when p.id is not null then f.nombre end as subfamilia
      from insumo i
      left join unidad u on u.id = i.unidad_id
      left join familia f on f.id = i.familia_id
      left join familia p on p.id = f.parent_id
     where i.estatus = 'activo'
"""


def _insumo(f: dict[str, Any]) -> tuple[UUID, Insumo]:
    familia, sub = f["familia"], f["subfamilia"]
    insumo = Insumo(
        clave=f["clave"],
        descripcion=f["descripcion"],
        clase=clase_de_insumo(f["tipo"], familia),
        familia=familia,
        subfamilia=sub,
        unidad=f["unidad"],
        precio=float(f["precio"]) if f["precio"] is not None else None,
        provisional=bool(f["provisional"]),
    )
    return f["id"], insumo


class RepositorioInsumosDeElementoSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def por_claves(self, claves: Sequence[str]) -> dict[str, tuple[UUID, Insumo]]:
        if not claves:
            return {}
        filas = (
            await self._sesion.execute(
                text(_BASE + " and upper(i.clave) = any(cast(:c as text[]))"), {"c": [c.upper() for c in claves]}
            )
        ).mappings().all()
        return {str(f["clave"]).upper(): _insumo(dict(f)) for f in filas}

    async def por_id(self, insumo_id: UUID) -> tuple[UUID, Insumo] | None:
        fila = (await self._sesion.execute(text(_BASE + " and i.id = :i"), {"i": str(insumo_id)})).mappings().first()
        return _insumo(dict(fila)) if fila else None

    async def todos(self) -> list[tuple[UUID, Insumo]]:
        """Todos los insumos activos con su clase y su lugar en el árbol de familias."""
        filas = (await self._sesion.execute(text(_BASE + " order by i.clave"))).mappings().all()
        return [_insumo(dict(f)) for f in filas]

    async def unidad_id(self, unidad: str) -> UUID | None:
        """La unidad de la organización por clave o sinónimo (`jor` → `jornal`)."""
        fila = (
            await self._sesion.execute(
                text(
                    "select id from unidad where lower(clave) = lower(:u) "
                    "or lower(:u) = any(select lower(s) from unnest(sinonimos) s) order by (lower(clave) = lower(:u)) desc limit 1"
                ),
                {"u": unidad},
            )
        ).first()
        return UUID(str(fila[0])) if fila else None

    async def asegurar_familia(self, nombre: str, *, padre: str | None = None) -> UUID:
        """La familia (o subfamilia, si trae `padre`) de la organización; la crea si no existe. La clave de una familia es su
        nombre, como la dan de alta los cargadores del catálogo."""
        fila = (await self._sesion.execute(text("select id from familia where clave = :n"), {"n": nombre})).first()
        if fila:
            return UUID(str(fila[0]))
        id_padre = None
        if padre is not None:
            id_padre = str(await self.asegurar_familia(padre))
        nuevo = (
            await self._sesion.execute(
                text(
                    "insert into familia (org_id, parent_id, clave, nombre, aplica_a) "
                    "values (app.current_org_id(), cast(:p as uuid), :n, :n, 'material') returning id"
                ),
                {"p": id_padre, "n": nombre},
            )
        ).scalar_one()
        return UUID(str(nuevo))

    async def crear_provisional(
        self, *, tipo: str, clave: str, descripcion: str, unidad_id: UUID, familia_id: UUID
    ) -> UUID:
        """Un insumo nuevo sin precio (`costo_base` 0) y marcado provisional: Costos le pone el precio."""
        nuevo = (
            await self._sesion.execute(
                text(
                    "insert into insumo (org_id, tipo, clave, descripcion, unidad_id, familia_id, costo_base, provisional) "
                    "values (app.current_org_id(), cast(:t as tipo_insumo), :k, :d, :u, :f, 0, true) returning id"
                ),
                {"t": tipo, "k": clave, "d": descripcion, "u": str(unidad_id), "f": str(familia_id)},
            )
        ).scalar_one()
        return UUID(str(nuevo))

    async def del_elemento(self, elemento_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select ei.id, ei.insumo_id, ei.clase, ei.cantidad, ei.created_at
                      from elemento_insumo ei join insumo i on i.id = ei.insumo_id
                     where ei.elemento_id = :e order by ei.created_at, i.clave
                    """
                ),
                {"e": str(elemento_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def agregar(
        self, *, elemento_id: UUID, insumo_id: UUID, clase: str, cantidad: float, autor_id: UUID
    ) -> bool:
        """Agrega el insumo al elemento; `False` si ya lo tenía (no se repite)."""
        fila = (
            await self._sesion.execute(
                text(
                    "insert into elemento_insumo (org_id, elemento_id, insumo_id, clase, cantidad, autor_id) "
                    "select e.org_id, e.id, :i, :c, :q, :a from elemento_parametrico e where e.id = :e "
                    "on conflict (elemento_id, insumo_id) do nothing returning id"
                ),
                {"e": str(elemento_id), "i": str(insumo_id), "c": clase, "q": cantidad, "a": str(autor_id)},
            )
        ).first()
        return fila is not None

    async def cambiar_cantidad(self, elemento_id: UUID, insumo_id: UUID, cantidad: float) -> bool:
        fila = (
            await self._sesion.execute(
                text("update elemento_insumo set cantidad = :q where elemento_id = :e and insumo_id = :i returning id"),
                {"e": str(elemento_id), "i": str(insumo_id), "q": cantidad},
            )
        ).first()
        return fila is not None

    async def quitar(self, elemento_id: UUID, insumo_id: UUID) -> bool:
        fila = (
            await self._sesion.execute(
                text("delete from elemento_insumo where elemento_id = :e and insumo_id = :i returning id"),
                {"e": str(elemento_id), "i": str(insumo_id)},
            )
        ).first()
        return fila is not None
