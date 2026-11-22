"""SQL de los rellenos de las zonas de losa (migración 0144). RLS por organización; solo Control de obra escribe."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioRellenosDeZonaSQL"]

_SELECCION = """
    select r.id, r.zona_id, r.elemento_clave, r.trazo_id, r.espesor_m, r.pendiente_pct, r.recorrido_m, r.compensar_espesores,
           r.abundamiento_pct, r.mortero_m3_por_m2, r.espacio_id, r.pendiente_zona_pct, r.espesor_bajada_m, r.mortero_espesor_m, r.factor_abundamiento,
           r.created_at
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
                                              abundamiento_pct, mortero_m3_por_m2, espacio_id, pendiente_zona_pct, espesor_bajada_m, mortero_espesor_m,
                                              factor_abundamiento, autor_id)
                    select app.current_org_id(), :z, :clave, cast(:trazo as uuid), :espesor, :pendiente, :recorrido, :compensar, :abundamiento, :mortero,
                           cast(:espacio as uuid), :pendiente_zona, :espesor_bajada, :mortero_espesor, :factor, :autor
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
                "espacio_id = cast(:espacio as uuid), pendiente_zona_pct = :pendiente_zona, espesor_bajada_m = :espesor_bajada, "
                "mortero_espesor_m = :mortero_espesor, factor_abundamiento = :factor where id = :r"
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
            "pendiente_zona": d["pendiente_zona_pct"], "espesor_bajada": d["espesor_bajada_m"], "mortero_espesor": d["mortero_espesor_m"],
            "factor": d["factor_abundamiento"],
        }

    async def espacio_existe(self, obra_id: UUID, espacio_id: UUID) -> bool:
        fila = (
            await self._sesion.execute(
                text("select 1 from espacio where id = :e and obra_id = :o"), {"e": str(espacio_id), "o": str(obra_id)}
            )
        ).first()
        return fila is not None

    # ── Bajadas pluviales (0147) ────────────────────────────────────────────────────────────────────────

    _BAJADA = """
        select b.id, b.relleno_id, b.trazo_id, b.linea_trazo_id, b.rotulo,
               ST_AsGeoJSON(app.geometria_efectiva(p.id, p.geometria), 9, 0) as geojson,
               case when l.id is null then null else ST_AsGeoJSON(app.geometria_efectiva(l.id, l.geometria), 9, 0) end as geojson_linea
          from relleno_bajada b
          join trazo p on p.id = b.trazo_id
          left join trazo l on l.id = b.linea_trazo_id
    """

    @staticmethod
    def _bajada_fila(f: Any) -> dict[str, Any]:
        d = dict(f)
        d["geojson"] = json.loads(d["geojson"]) if d.get("geojson") else None
        d["geojson_linea"] = json.loads(d["geojson_linea"]) if d.get("geojson_linea") else None
        return d

    async def bajadas_de_la_zona(self, zona_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    self._BAJADA
                    + " join relleno_zona r on r.id = b.relleno_id where r.zona_id = :z order by b.created_at, b.id"
                ),
                {"z": str(zona_id)},
            )
        ).mappings().all()
        return [self._bajada_fila(f) for f in filas]

    async def bajada(self, bajada_id: UUID) -> dict[str, Any] | None:
        fila = (await self._sesion.execute(text(self._BAJADA + " where b.id = :b"), {"b": str(bajada_id)})).mappings().first()
        return self._bajada_fila(fila) if fila else None

    async def agregar_bajada(self, *, relleno_id: UUID, trazo_id: UUID, linea_trazo_id: UUID | None, rotulo: str | None, autor_id: UUID) -> UUID:
        nuevo = (
            await self._sesion.execute(
                text(
                    """
                    insert into relleno_bajada (org_id, relleno_id, trazo_id, linea_trazo_id, rotulo, autor_id)
                    select app.current_org_id(), :r, :t, cast(:l as uuid), :rotulo, :autor
                    returning id
                    """
                ),
                {"r": str(relleno_id), "t": str(trazo_id), "l": str(linea_trazo_id) if linea_trazo_id else None, "rotulo": rotulo, "autor": str(autor_id)},
            )
        ).scalar_one()
        return UUID(str(nuevo))

    async def actualizar_bajada(self, bajada_id: UUID, *, linea_trazo_id: UUID | None, rotulo: str | None) -> None:
        await self._sesion.execute(
            text("update relleno_bajada set linea_trazo_id = cast(:l as uuid), rotulo = :rotulo where id = :b"),
            {"l": str(linea_trazo_id) if linea_trazo_id else None, "rotulo": rotulo, "b": str(bajada_id)},
        )

    async def eliminar_bajada(self, bajada_id: UUID) -> None:
        await self._sesion.execute(text("delete from relleno_bajada where id = :b"), {"b": str(bajada_id)})

    async def bajada_del_punto(self, trazo_id: UUID) -> UUID | None:
        fila = (await self._sesion.execute(text("select id from relleno_bajada where trazo_id = :t"), {"t": str(trazo_id)})).first()
        return UUID(str(fila[0])) if fila else None

    async def bajada_de_la_linea(self, trazo_id: UUID) -> UUID | None:
        fila = (await self._sesion.execute(text("select id from relleno_bajada where linea_trazo_id = :t"), {"t": str(trazo_id)})).first()
        return UUID(str(fila[0])) if fila else None
