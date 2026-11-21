"""SQL de los cimientos de las zonas de losa (migración 0146). RLS por organización; solo Control de obra escribe."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioCimientosDeZonaSQL"]

_SELECCION = """
    select c.id, c.zona_id, c.elemento_clave, c.trazo_id, c.cota_desplante_m, c.punto_nivel_id, c.cota_corona_m, c.caras, c.dentellon, c.espacio_id,
           c.created_at, ST_AsGeoJSON(app.geometria_efectiva(t.id, t.geometria), 9, 0) as geojson
      from cimiento_zona c
      join trazo t on t.id = c.trazo_id
"""


def _fila(f: Any) -> dict[str, Any]:
    d = dict(f)
    d["geojson"] = json.loads(d["geojson"]) if d.get("geojson") else None
    return d


class RepositorioCimientosDeZonaSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def de_la_zona(self, zona_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(text(_SELECCION + " where c.zona_id = :z order by c.created_at, c.id"), {"z": str(zona_id)})
        ).mappings().all()
        return [_fila(f) for f in filas]

    async def uno(self, cimiento_id: UUID) -> dict[str, Any] | None:
        fila = (await self._sesion.execute(text(_SELECCION + " where c.id = :c"), {"c": str(cimiento_id)})).mappings().first()
        return _fila(fila) if fila else None

    async def agregar(self, *, zona_id: UUID, datos: dict[str, Any], autor_id: UUID) -> UUID:
        nuevo = (
            await self._sesion.execute(
                text(
                    """
                    insert into cimiento_zona (org_id, zona_id, elemento_clave, trazo_id, cota_desplante_m, punto_nivel_id, cota_corona_m, caras, dentellon,
                                               espacio_id, autor_id)
                    select app.current_org_id(), :z, :clave, cast(:trazo as uuid), :desplante, cast(:punto as uuid), :corona, :caras, :dentellon,
                           cast(:espacio as uuid), :autor
                    returning id
                    """
                ),
                {**self._valores(datos), "z": str(zona_id), "autor": str(autor_id)},
            )
        ).scalar_one()
        return UUID(str(nuevo))

    async def actualizar(self, cimiento_id: UUID, datos: dict[str, Any]) -> None:
        await self._sesion.execute(
            text(
                "update cimiento_zona set elemento_clave = :clave, trazo_id = cast(:trazo as uuid), cota_desplante_m = :desplante, "
                "punto_nivel_id = cast(:punto as uuid), cota_corona_m = :corona, caras = :caras, dentellon = :dentellon, "
                "espacio_id = cast(:espacio as uuid) where id = :c"
            ),
            {**self._valores(datos), "c": str(cimiento_id)},
        )

    async def eliminar(self, cimiento_id: UUID) -> None:
        await self._sesion.execute(text("delete from cimiento_zona where id = :c"), {"c": str(cimiento_id)})

    async def con_la_linea(self, trazo_id: UUID) -> UUID | None:
        fila = (await self._sesion.execute(text("select id from cimiento_zona where trazo_id = :t"), {"t": str(trazo_id)})).first()
        return UUID(str(fila[0])) if fila else None

    @staticmethod
    def _valores(d: dict[str, Any]) -> dict[str, Any]:
        return {
            "clave": d["elemento_clave"], "trazo": str(d["trazo_id"]), "desplante": d.get("cota_desplante_m"),
            "punto": str(d["punto_nivel_id"]) if d.get("punto_nivel_id") else None, "corona": d.get("cota_corona_m"), "caras": d["caras"],
            "dentellon": d["dentellon"], "espacio": str(d["espacio_id"]) if d.get("espacio_id") else None,
        }

    async def espacio_existe(self, obra_id: UUID, espacio_id: UUID) -> bool:
        fila = (
            await self._sesion.execute(
                text("select 1 from espacio where id = :e and obra_id = :o"), {"e": str(espacio_id), "o": str(obra_id)}
            )
        ).first()
        return fila is not None
