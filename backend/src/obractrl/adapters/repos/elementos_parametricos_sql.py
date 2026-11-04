"""SQL de los elementos paramétricos (migración 0104). RLS por organización."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioElementosParametricosSQL"]

_COLUMNAS = "id, clave, nombre, tipo, parametros"


class RepositorioElementosParametricosSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def listar(self) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(text(f"select {_COLUMNAS} from elemento_parametrico order by lower(clave)"))
        ).mappings().all()
        return [dict(f) for f in filas]

    async def obtener(self, elemento_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} from elemento_parametrico where id = :id"), {"id": str(elemento_id)}
            )
        ).mappings().first()
        return dict(fila) if fila else None

    async def clave_en_uso(self, clave: str, *, salvo: UUID | None = None) -> bool:
        return bool(
            (
                await self._sesion.execute(
                    text(
                        "select exists (select 1 from elemento_parametrico "
                        "where lower(btrim(clave)) = lower(btrim(:c)) and (cast(:salvo as uuid) is null or id <> cast(:salvo as uuid)))"
                    ),
                    {"c": clave, "salvo": str(salvo) if salvo else None},
                )
            ).scalar_one()
        )

    async def crear(
        self, *, clave: str, nombre: str, tipo: str, parametros: dict[str, Any], autor_id: UUID
    ) -> UUID:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    insert into elemento_parametrico (org_id, clave, nombre, tipo, parametros, autor_id)
                    values (app.current_org_id(), :clave, :nombre, :tipo, cast(:p as jsonb), :autor)
                    returning id
                    """
                ),
                {"clave": clave, "nombre": nombre, "tipo": tipo, "p": json.dumps(parametros), "autor": str(autor_id)},
            )
        ).scalar_one()
        return UUID(str(fila))

    async def actualizar(
        self, elemento_id: UUID, *, clave: str, nombre: str, parametros: dict[str, Any]
    ) -> None:
        await self._sesion.execute(
            text(
                "update elemento_parametrico set clave = :clave, nombre = :nombre, parametros = cast(:p as jsonb) "
                "where id = :id"
            ),
            {"id": str(elemento_id), "clave": clave, "nombre": nombre, "p": json.dumps(parametros)},
        )

    async def eliminar(self, elemento_id: UUID) -> None:
        await self._sesion.execute(
            text("delete from elemento_parametrico where id = :id"), {"id": str(elemento_id)}
        )

    async def tipo_de_geometria(self, trazo_id: UUID) -> str | None:
        """`punto`, `linea` o `area` según la geometría del trazo; `None` si no existe o es un hueco."""
        fila = (
            await self._sesion.execute(
                text("select ST_GeometryType(geometria) from trazo where id = :id and hueco_de is null"),
                {"id": str(trazo_id)},
            )
        ).scalar_one_or_none()
        if fila is None:
            return None
        return {"ST_Point": "punto", "ST_LineString": "linea", "ST_Polygon": "area"}.get(str(fila))

    async def poner_en_trazo(self, trazo_id: UUID, elemento_id: UUID | None, lados: int | None) -> None:
        await self._sesion.execute(
            text(
                "update trazo set elemento_parametrico_id = cast(:e as uuid), lados_cimbra = :l where id = :id"
            ),
            {"id": str(trazo_id), "e": str(elemento_id) if elemento_id else None, "l": lados},
        )

    async def trazo_de(self, trazo_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text("select id, elemento_parametrico_id, lados_cimbra from trazo where id = :id"),
                {"id": str(trazo_id)},
            )
        ).mappings().first()
        return dict(fila) if fila else None

    async def trazos_del_plano(self, plano_id: UUID) -> list[dict[str, Any]]:
        """Cada trazo del plano que es un elemento, con lo que aporta: 1 pieza, sus metros o sus m² (ya con la escala)."""
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select t.id, t.elemento_parametrico_id, t.lados_cimbra,
                           case ep.tipo
                             when 'lineal' then ST_Length(app.geometria_efectiva(t.id, t.geometria))
                                                * coalesce(p.escala_m_por_unidad, 1)
                                                * sqrt(1 + power(coalesce(t.pendiente_pct, 0) / 100.0, 2))
                             when 'losa'   then ST_Area(app.geometria_efectiva(t.id, t.geometria))
                                                * power(coalesce(p.escala_m_por_unidad, 1), 2)
                             else 1
                           end as cantidad
                      from trazo t
                      join plano p on p.id = t.plano_id
                      join elemento_parametrico ep on ep.id = t.elemento_parametrico_id
                     where t.plano_id = :plano and t.hueco_de is null and not t.propuesta
                    """
                ),
                {"plano": str(plano_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]
