"""SQL de los rellenos de las zonas de losa (migración 0144). RLS por organización; solo Control de obra escribe."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioRellenosDeZonaSQL"]

_SELECCION = """
    select r.id, r.zona_id, r.elemento_clave, r.trazo_id, r.espesor_m, r.pendiente_pct, r.recorrido_m, r.compensar_espesores,
           r.abundamiento_pct, r.mortero_m3_por_m2, r.espacio_id, r.created_at
      from relleno_zona r
"""


class RepositorioRellenosDeZonaSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def de_la_zona(self, zona_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(text(_SELECCION + " where r.zona_id = :z order by r.created_at, r.id"), {"z": str(zona_id)})
        ).mappings().all()
        return [dict(f) for f in filas]

    async def uno(self, relleno_id: UUID) -> dict[str, Any] | None:
        fila = (await self._sesion.execute(text(_SELECCION + " where r.id = :r"), {"r": str(relleno_id)})).mappings().first()
        return dict(fila) if fila else None

    async def agregar(self, *, zona_id: UUID, datos: dict[str, Any], autor_id: UUID) -> UUID:
        nuevo = (
            await self._sesion.execute(
                text(
                    """
                    insert into relleno_zona (org_id, zona_id, elemento_clave, trazo_id, espesor_m, pendiente_pct, recorrido_m, compensar_espesores,
                                              abundamiento_pct, mortero_m3_por_m2, espacio_id, autor_id)
                    select app.current_org_id(), :z, :clave, cast(:trazo as uuid), :espesor, :pendiente, :recorrido, :compensar, :abundamiento, :mortero,
                           cast(:espacio as uuid), :autor
                    returning id
                    """
                ),
                {**self._valores(datos), "z": str(zona_id), "autor": str(autor_id)},
            )
        ).scalar_one()
        return UUID(str(nuevo))

    async def actualizar(self, relleno_id: UUID, datos: dict[str, Any]) -> None:
        await self._sesion.execute(
            text(
                "update relleno_zona set elemento_clave = :clave, trazo_id = cast(:trazo as uuid), espesor_m = :espesor, pendiente_pct = :pendiente, "
                "recorrido_m = :recorrido, compensar_espesores = :compensar, abundamiento_pct = :abundamiento, mortero_m3_por_m2 = :mortero, "
                "espacio_id = cast(:espacio as uuid) where id = :r"
            ),
            {**self._valores(datos), "r": str(relleno_id)},
        )

    async def eliminar(self, relleno_id: UUID) -> None:
        await self._sesion.execute(text("delete from relleno_zona where id = :r"), {"r": str(relleno_id)})

    @staticmethod
    def _valores(d: dict[str, Any]) -> dict[str, Any]:
        return {
            "clave": d["elemento_clave"], "trazo": str(d["trazo_id"]) if d.get("trazo_id") else None, "espesor": d["espesor_m"],
            "pendiente": d["pendiente_pct"], "recorrido": d["recorrido_m"], "compensar": d["compensar_espesores"],
            "abundamiento": d["abundamiento_pct"], "mortero": d["mortero_m3_por_m2"],
            "espacio": str(d["espacio_id"]) if d.get("espacio_id") else None,
        }

    async def espacio_existe(self, obra_id: UUID, espacio_id: UUID) -> bool:
        fila = (
            await self._sesion.execute(
                text("select 1 from espacio where id = :e and obra_id = :o"), {"e": str(espacio_id), "o": str(obra_id)}
            )
        ).first()
        return fila is not None
