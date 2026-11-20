"""SQL de las zonas de losa (migración 0137): zonas, polígonos con rol de losa y puntos de nivel exterior. RLS por organización."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.domain.cuantificacion.zonas_de_losa import ErrorDeZonaDeLosa

__all__ = ["RepositorioZonasDeLosaSQL"]

_COLUMNAS_ZONA = "z.id, z.plano_id, z.nombre, z.nivel, z.cota_piso_m, z.altura_libre_m, z.espesor_m, z.tipo_de_losa, z.uso_de_losa, z.created_at, z.updated_at"


class RepositorioZonasDeLosaSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def plano(self, plano_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text("select id, obra_id, escala_m_por_unidad from plano where id = :p"), {"p": str(plano_id)}
            )
        ).mappings().one_or_none()
        return dict(fila) if fila else None

    async def muros(self, plano_id: UUID) -> list[dict[str, Any]]:
        """Los muros del plano: líneas con grosor (no huecos, no propuestas ni revestimientos), con su ubicación (0133) y su tipo."""
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select t.id, t.muro_ubicacion as ubicacion, t.muro_tipo as tipo
                      from trazo t
                     where t.plano_id = :p and geometrytype(t.geometria) = 'LINESTRING' and t.grosor_m is not null
                       and t.hueco_de is null and not t.propuesta and t.revestimiento_de is null
                     order by t.created_at, t.id
                    """
                ),
                {"p": str(plano_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def zonas(self, plano_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"select {_COLUMNAS_ZONA} from losa_zona z where z.plano_id = :p "
                    "order by z.cota_piso_m, z.altura_libre_m, lower(z.nombre), z.id"
                ),
                {"p": str(plano_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def zonas_de_la_obra(self, obra_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"select {_COLUMNAS_ZONA} from losa_zona z join plano p on p.id = z.plano_id where p.obra_id = :o "
                    "order by p.created_at, p.id, z.cota_piso_m, z.altura_libre_m, lower(z.nombre), z.id"
                ),
                {"o": str(obra_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def zona(self, zona_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(text(f"select {_COLUMNAS_ZONA} from losa_zona z where z.id = :z"), {"z": str(zona_id)})
        ).mappings().one_or_none()
        return dict(fila) if fila else None

    async def losas(self, plano_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select t.id, t.losa_zona_id as zona_id, t.losa_espesor_m as espesor_propio_m, t.espacio_id,
                           ST_AsGeoJSON(app.geometria_efectiva(t.id, t.geometria), 9, 0) as geojson
                      from trazo t
                     where t.plano_id = :p and t.losa_zona_id is not null and t.hueco_de is null
                     order by t.created_at, t.id
                    """
                ),
                {"p": str(plano_id)},
            )
        ).mappings().all()
        return [{**{k: v for k, v in f.items() if k != "geojson"}, "geojson": json.loads(f["geojson"])} for f in filas]

    async def puntos_de_nivel(self, plano_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select t.id, ST_X(t.geometria) as x, ST_Y(t.geometria) as y, t.nivel_exterior_m as cota_m, t.rotulo
                      from trazo t
                     where t.plano_id = :p and t.nivel_exterior_m is not null and t.hueco_de is null
                     order by t.created_at, t.id
                    """
                ),
                {"p": str(plano_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def crear(self, *, plano_id: UUID, datos: dict[str, Any], autor_id: UUID) -> UUID:
        try:
            async with self._sesion.begin_nested():
                nuevo = (
                    await self._sesion.execute(
                        text(
                            """
                            insert into losa_zona (org_id, plano_id, nombre, nivel, cota_piso_m, altura_libre_m, espesor_m, tipo_de_losa, uso_de_losa, autor_id)
                            select app.current_org_id(), :p, :nombre, :nivel, :cota, :altura, :espesor,
                                   coalesce(:tipo, 'maciza'), coalesce(:uso, 'entrepiso'), :autor
                            returning id
                            """
                        ),
                        self._valores(datos) | {"p": str(plano_id), "autor": str(autor_id)},
                    )
                ).scalar_one()
        except IntegrityError as e:
            raise self._conflicto(e, datos["nombre"]) from e
        return UUID(str(nuevo))

    async def actualizar(self, zona_id: UUID, datos: dict[str, Any]) -> None:
        try:
            async with self._sesion.begin_nested():
                await self._sesion.execute(
                    text(
                        "update losa_zona set nombre = :nombre, nivel = :nivel, cota_piso_m = :cota, altura_libre_m = :altura, "
                        "espesor_m = :espesor, tipo_de_losa = coalesce(:tipo, tipo_de_losa), uso_de_losa = coalesce(:uso, uso_de_losa) where id = :z"
                    ),
                    self._valores(datos) | {"z": str(zona_id)},
                )
        except IntegrityError as e:
            raise self._conflicto(e, datos["nombre"]) from e

    @staticmethod
    def _valores(datos: dict[str, Any]) -> dict[str, Any]:
        return {
            "nombre": datos["nombre"], "nivel": datos["nivel"], "cota": datos["cota_piso_m"],
            "altura": datos["altura_libre_m"], "espesor": datos["espesor_m"],
            "tipo": datos.get("tipo_de_losa"), "uso": datos.get("uso_de_losa"),
        }

    @staticmethod
    def _conflicto(error: IntegrityError, nombre: str) -> ErrorDeZonaDeLosa:
        if "ux_losa_zona_nombre" in str(error.orig):
            return ErrorDeZonaDeLosa(f"Ya hay una zona de losa llamada «{nombre}» en este plano.")
        return ErrorDeZonaDeLosa("Los datos de la zona de losa no valen.")

    async def eliminar(self, zona_id: UUID) -> None:
        # El espesor propio de una subzona no significa nada sin su zona: se suelta con ella.
        await self._sesion.execute(text("update trazo set losa_espesor_m = null where losa_zona_id = :z"), {"z": str(zona_id)})
        await self._sesion.execute(text("delete from losa_zona where id = :z"), {"z": str(zona_id)})

    async def trazo(self, trazo_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select t.id, t.plano_id, geometrytype(t.geometria) as tipo, t.hueco_de, t.grosor_m,
                           ST_AsGeoJSON(app.geometria_efectiva(t.id, t.geometria), 9, 0) as geojson
                      from trazo t where t.id = :t
                    """
                ),
                {"t": str(trazo_id)},
            )
        ).mappings().one_or_none()
        if fila is None:
            return None
        return {**{k: v for k, v in fila.items() if k != "geojson"}, "geojson": json.loads(fila["geojson"])}

    async def fijar_losa(self, trazo_id: UUID, zona_id: UUID | None, espesor_m: Decimal | None) -> None:
        await self._sesion.execute(
            text("update trazo set losa_zona_id = cast(:z as uuid), losa_espesor_m = :e where id = :t"),
            {"z": str(zona_id) if zona_id else None, "e": espesor_m if zona_id else None, "t": str(trazo_id)},
        )

    async def fijar_nivel_exterior(self, trazo_id: UUID, cota_m: Decimal | None, rotulo: str | None) -> None:
        await self._sesion.execute(
            text("update trazo set nivel_exterior_m = :c, rotulo = :r where id = :t"),
            {"c": cota_m, "r": rotulo if cota_m is not None else None, "t": str(trazo_id)},
        )
