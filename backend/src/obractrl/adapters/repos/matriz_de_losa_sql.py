"""SQL de los elementos de las zonas de losa (migración 0142). RLS por organización; solo Control de obra escribe."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioElementosDeLosaSQL"]

_SELECCION = """
    select e.id, e.zona_id, e.elemento_clave, e.modo, e.cantidad, e.largo_m, e.pago, e.trazo_id, e.espacio_id, e.created_at,
           case when t.id is null then null else ST_AsGeoJSON(app.geometria_efectiva(t.id, t.geometria), 9, 0) end as geojson
      from losa_elemento e
      left join trazo t on t.id = e.trazo_id
"""


def _fila(f: Any) -> dict[str, Any]:
    d = dict(f)
    d["geojson"] = json.loads(d["geojson"]) if d.get("geojson") else None
    return d


class RepositorioElementosDeLosaSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def de_la_zona(self, zona_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(text(_SELECCION + " where e.zona_id = :z order by e.created_at, e.id"), {"z": str(zona_id)})
        ).mappings().all()
        return [_fila(f) for f in filas]

    async def uno(self, elemento_id: UUID) -> dict[str, Any] | None:
        fila = (await self._sesion.execute(text(_SELECCION + " where e.id = :e"), {"e": str(elemento_id)})).mappings().first()
        return _fila(fila) if fila else None

    async def agregar(self, *, zona_id: UUID, datos: dict[str, Any], autor_id: UUID) -> UUID:
        nuevo = (
            await self._sesion.execute(
                text(
                    """
                    insert into losa_elemento (org_id, zona_id, elemento_clave, modo, cantidad, largo_m, pago, trazo_id, espacio_id, autor_id)
                    select app.current_org_id(), :z, :clave, :modo, :cantidad, :largo, :pago, cast(:trazo as uuid), cast(:espacio as uuid), :autor
                    returning id
                    """
                ),
                {**self._valores(datos), "z": str(zona_id), "autor": str(autor_id)},
            )
        ).scalar_one()
        return UUID(str(nuevo))

    async def actualizar(self, elemento_id: UUID, datos: dict[str, Any]) -> None:
        await self._sesion.execute(
            text(
                "update losa_elemento set elemento_clave = :clave, modo = :modo, cantidad = :cantidad, largo_m = :largo, pago = :pago, "
                "trazo_id = cast(:trazo as uuid), espacio_id = cast(:espacio as uuid) where id = :e"
            ),
            {**self._valores(datos), "e": str(elemento_id)},
        )

    async def eliminar(self, elemento_id: UUID) -> None:
        await self._sesion.execute(text("delete from losa_elemento where id = :e"), {"e": str(elemento_id)})

    @staticmethod
    def _valores(d: dict[str, Any]) -> dict[str, Any]:
        return {
            "clave": d["elemento_clave"], "modo": d["modo"], "cantidad": d["cantidad"], "largo": d["largo_m"], "pago": d["pago"],
            "trazo": str(d["trazo_id"]) if d.get("trazo_id") else None,
            "espacio": str(d["espacio_id"]) if d.get("espacio_id") else None,
        }

    async def espacio_existe(self, obra_id: UUID, espacio_id: UUID) -> bool:
        fila = (
            await self._sesion.execute(
                text("select 1 from espacio where id = :e and obra_id = :o"), {"e": str(espacio_id), "o": str(obra_id)}
            )
        ).first()
        return fila is not None
