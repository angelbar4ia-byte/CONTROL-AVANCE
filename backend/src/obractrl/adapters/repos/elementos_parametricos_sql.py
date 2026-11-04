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
