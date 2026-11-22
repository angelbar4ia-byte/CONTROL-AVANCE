"""SQL de las escaleras de las zonas de losa, sus descansos propios y sus escalones de abanico (migraciones 0145 y 0148). RLS por organización; solo Control de obra escribe."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioEscalerasDeZonaSQL"]

_SELECCION = """
    select e.id, e.zona_id, e.elemento_clave, e.zona_llegada_id, e.cota_arranque_m, e.cota_llegada_m, e.peldanos, e.contrahuella_max_m, e.huella_m,
           e.ancho_m, e.espesor_m, e.rampas, e.largo_descanso_m, e.trazo_id, e.espacio_id, e.created_at,
           case when t.id is null then null else ST_AsGeoJSON(app.geometria_efectiva(t.id, t.geometria), 9, 0) end as geojson
      from escalera_zona e
      left join trazo t on t.id = e.trazo_id
"""


_SELECCION_DE_DESCANSOS = """
    select d.id, d.escalera_id, d.posicion, d.giro_grados, d.largo_m, d.ancho_m, d.espesor_m, d.trazo_id,
           case when t.id is null then null else ST_AsGeoJSON(app.geometria_efectiva(t.id, t.geometria), 9, 0) end as geojson
      from escalera_descanso d
      join escalera_zona e on e.id = d.escalera_id
      left join trazo t on t.id = d.trazo_id
"""


def _fila(f: Any) -> dict[str, Any]:
    d = dict(f)
    d["geojson"] = json.loads(d["geojson"]) if d.get("geojson") else None
    return d


class RepositorioEscalerasDeZonaSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def de_la_zona(self, zona_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(text(_SELECCION + " where e.zona_id = :z order by e.created_at, e.id"), {"z": str(zona_id)})
        ).mappings().all()
        return [_fila(f) for f in filas]

    async def uno(self, escalera_id: UUID) -> dict[str, Any] | None:
        fila = (await self._sesion.execute(text(_SELECCION + " where e.id = :e"), {"e": str(escalera_id)})).mappings().first()
        return _fila(fila) if fila else None

    async def agregar(self, *, zona_id: UUID, datos: dict[str, Any], autor_id: UUID) -> UUID:
        nuevo = (
            await self._sesion.execute(
                text(
                    """
                    insert into escalera_zona (org_id, zona_id, elemento_clave, zona_llegada_id, cota_arranque_m, cota_llegada_m, peldanos, contrahuella_max_m,
                                               huella_m, ancho_m, espesor_m, rampas, largo_descanso_m, trazo_id, espacio_id, autor_id)
                    select app.current_org_id(), :z, :clave, cast(:llegada as uuid), :arranque, :cota_llegada, :peldanos, :contrahuella, :huella, :ancho,
                           :espesor, :rampas, :descanso, cast(:trazo as uuid), cast(:espacio as uuid), :autor
                    returning id
                    """
                ),
                {**self._valores(datos), "z": str(zona_id), "autor": str(autor_id)},
            )
        ).scalar_one()
        return UUID(str(nuevo))

    async def actualizar(self, escalera_id: UUID, datos: dict[str, Any]) -> None:
        await self._sesion.execute(
            text(
                "update escalera_zona set elemento_clave = :clave, zona_llegada_id = cast(:llegada as uuid), cota_arranque_m = :arranque, "
                "cota_llegada_m = :cota_llegada, peldanos = :peldanos, contrahuella_max_m = :contrahuella, huella_m = :huella, ancho_m = :ancho, "
                "espesor_m = :espesor, rampas = :rampas, largo_descanso_m = :descanso, trazo_id = cast(:trazo as uuid), "
                "espacio_id = cast(:espacio as uuid) where id = :e"
            ),
            {**self._valores(datos), "e": str(escalera_id)},
        )

    async def eliminar(self, escalera_id: UUID) -> None:
        await self._sesion.execute(text("delete from escalera_zona where id = :e"), {"e": str(escalera_id)})

    @staticmethod
    def _valores(d: dict[str, Any]) -> dict[str, Any]:
        return {
            "clave": d["elemento_clave"], "llegada": str(d["zona_llegada_id"]) if d.get("zona_llegada_id") else None,
            "arranque": d.get("cota_arranque_m"), "cota_llegada": d.get("cota_llegada_m"), "peldanos": d.get("peldanos"),
            "contrahuella": d["contrahuella_max_m"], "huella": d["huella_m"], "ancho": d["ancho_m"], "espesor": d["espesor_m"], "rampas": d["rampas"],
            "descanso": d.get("largo_descanso_m"), "trazo": str(d["trazo_id"]) if d.get("trazo_id") else None,
            "espacio": str(d["espacio_id"]) if d.get("espacio_id") else None,
        }

    async def con_la_linea(self, trazo_id: UUID) -> UUID | None:
        fila = (await self._sesion.execute(text("select id from escalera_zona where trazo_id = :t"), {"t": str(trazo_id)})).first()
        return UUID(str(fila[0])) if fila else None

    async def espacio_existe(self, obra_id: UUID, espacio_id: UUID) -> bool:
        fila = (
            await self._sesion.execute(
                text("select 1 from espacio where id = :e and obra_id = :o"), {"e": str(espacio_id), "o": str(obra_id)}
            )
        ).first()
        return fila is not None

    # ── Descansos propios y escalones de abanico (0148) ──────────────────────────────────────────────────

    async def descansos_de_la_zona(self, zona_id: UUID) -> dict[UUID, list[dict[str, Any]]]:
        filas = (
            await self._sesion.execute(text(_SELECCION_DE_DESCANSOS + " where e.zona_id = :z order by d.escalera_id, d.posicion"), {"z": str(zona_id)})
        ).mappings().all()
        salida: dict[UUID, list[dict[str, Any]]] = {}
        for f in filas:
            salida.setdefault(UUID(str(f["escalera_id"])), []).append(_fila(f))
        return salida

    async def abanicos_de_la_zona(self, zona_id: UUID) -> dict[UUID, list[dict[str, Any]]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select a.id, a.escalera_id, a.posicion, a.escalones, a.ancho_interior_m, a.ancho_exterior_m, a.radio_huella_m
                      from escalera_abanico a join escalera_zona e on e.id = a.escalera_id
                     where e.zona_id = :z order by a.escalera_id, a.posicion
                    """
                ),
                {"z": str(zona_id)},
            )
        ).mappings().all()
        salida: dict[UUID, list[dict[str, Any]]] = {}
        for f in filas:
            salida.setdefault(UUID(str(f["escalera_id"])), []).append(dict(f))
        return salida

    async def reemplazar_descansos(self, escalera_id: UUID, filas: list[dict[str, Any]], autor_id: UUID | None) -> None:
        await self._sesion.execute(text("delete from escalera_descanso where escalera_id = :e"), {"e": str(escalera_id)})
        for f in filas:
            await self._sesion.execute(
                text(
                    """
                    insert into escalera_descanso (org_id, escalera_id, posicion, giro_grados, largo_m, ancho_m, espesor_m, trazo_id, autor_id)
                    select app.current_org_id(), :e, :posicion, :giro, :largo, :ancho, :espesor, cast(:trazo as uuid), cast(:autor as uuid)
                    """
                ),
                {
                    "e": str(escalera_id), "posicion": f["posicion"], "giro": f["giro_grados"], "largo": f.get("largo_m"), "ancho": f.get("ancho_m"),
                    "espesor": f.get("espesor_m"), "trazo": str(f["trazo_id"]) if f.get("trazo_id") else None, "autor": str(autor_id) if autor_id else None,
                },
            )

    async def reemplazar_abanicos(self, escalera_id: UUID, filas: list[dict[str, Any]], autor_id: UUID | None) -> None:
        await self._sesion.execute(text("delete from escalera_abanico where escalera_id = :e"), {"e": str(escalera_id)})
        for f in filas:
            await self._sesion.execute(
                text(
                    """
                    insert into escalera_abanico (org_id, escalera_id, posicion, escalones, ancho_interior_m, ancho_exterior_m, radio_huella_m, autor_id)
                    select app.current_org_id(), :e, :posicion, :escalones, :interior, :exterior, :radio, cast(:autor as uuid)
                    """
                ),
                {
                    "e": str(escalera_id), "posicion": f["posicion"], "escalones": f["escalones"], "interior": f["ancho_interior_m"],
                    "exterior": f["ancho_exterior_m"], "radio": f["radio_huella_m"], "autor": str(autor_id) if autor_id else None,
                },
            )

    async def descanso_con_el_poligono(self, trazo_id: UUID) -> UUID | None:
        fila = (await self._sesion.execute(text("select escalera_id from escalera_descanso where trazo_id = :t"), {"t": str(trazo_id)})).first()
        return UUID(str(fila[0])) if fila else None

    async def trazo_es_de_losa(self, trazo_id: UUID) -> bool:
        fila = (await self._sesion.execute(text("select 1 from trazo where id = :t and losa_zona_id is not null"), {"t": str(trazo_id)})).first()
        return fila is not None
