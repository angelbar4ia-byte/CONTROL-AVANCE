"""SQL del catálogo de versiones de vano (migración 0117). RLS por organización."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["PREFIJO_DEL_TIPO", "VERSIONES_DE_PARTIDA", "RepositorioVanosVersionSQL"]

PREFIJO_DEL_TIPO = {"puerta": "P", "ventana": "V", "cancel": "C", "arco": "A", "paso": "PS", "castillo": "K"}

# Las versiones con que nace el catálogo de una organización (las del mockup).
VERSIONES_DE_PARTIDA: tuple[tuple[str, str, str, str, str], ...] = (
    ("puerta", "P-01", "0.9", "2.1", "0"),
    ("puerta", "P-02", "1", "2.1", "0"),
    ("puerta", "P-03", "0.7", "2.1", "0"),
    ("ventana", "V-01", "1.2", "1.2", "0.9"),
    ("ventana", "V-02", "1.5", "1.2", "1"),
    ("cancel", "C-01", "1.5", "2.1", "0"),
    ("arco", "A-01", "1", "2.1", "0"),
    ("paso", "PS-01", "0.9", "2.1", "0"),
    ("castillo", "K-01", "0.15", "2.6", "0"),
)

_COLUMNAS = "id, tipo, clave, ancho_m, alto_m, antepecho_m"


class RepositorioVanosVersionSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def listar(self, tipo: str | None = None) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"select {_COLUMNAS} from vano_version where cast(:t as text) is null or tipo = :t "
                    "order by tipo, lower(clave)"
                ),
                {"t": tipo},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def hay_alguna(self) -> bool:
        return bool((await self._sesion.execute(text("select exists (select 1 from vano_version)"))).scalar_one())

    async def sembrar(self, autor_id: UUID) -> None:
        for tipo, clave, ancho, alto, antepecho in VERSIONES_DE_PARTIDA:
            await self._sesion.execute(
                text(
                    "insert into vano_version (org_id, tipo, clave, ancho_m, alto_m, antepecho_m, autor_id) "
                    "values (cast(current_setting('app.org_id') as uuid), :tipo, :clave, :a, :h, :s, :autor) "
                    "on conflict do nothing"
                ),
                {"tipo": tipo, "clave": clave, "a": Decimal(ancho), "h": Decimal(alto), "s": Decimal(antepecho), "autor": str(autor_id)},
            )

    async def obtener(self, version_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(text(f"select {_COLUMNAS} from vano_version where id = :i"), {"i": str(version_id)})
        ).mappings().first()
        return dict(fila) if fila else None

    async def clave_en_uso(self, clave: str, *, salvo: UUID | None = None) -> bool:
        return bool(
            (
                await self._sesion.execute(
                    text(
                        "select exists (select 1 from vano_version where lower(btrim(clave)) = lower(btrim(:c)) "
                        "and (cast(:s as uuid) is null or id <> cast(:s as uuid)))"
                    ),
                    {"c": clave, "s": str(salvo) if salvo else None},
                )
            ).scalar_one()
        )

    async def crear(self, *, tipo: str, clave: str, ancho_m: Decimal, alto_m: Decimal, antepecho_m: Decimal, autor_id: UUID) -> UUID:
        return (
            await self._sesion.execute(
                text(
                    "insert into vano_version (org_id, tipo, clave, ancho_m, alto_m, antepecho_m, autor_id) "
                    "values (cast(current_setting('app.org_id') as uuid), :tipo, :clave, :a, :h, :s, :autor) returning id"
                ),
                {"tipo": tipo, "clave": clave, "a": ancho_m, "h": alto_m, "s": antepecho_m, "autor": str(autor_id)},
            )
        ).scalar_one()

    async def actualizar(self, version_id: UUID, cambios: dict[str, Any]) -> None:
        if not cambios:
            return
        asignaciones = ", ".join(f"{k} = :{k}" for k in cambios)
        await self._sesion.execute(
            text(f"update vano_version set {asignaciones} where id = :id"), {**cambios, "id": str(version_id)}
        )

    async def cuantas_del_tipo(self, tipo: str) -> int:
        return int((await self._sesion.execute(text("select count(*) from vano_version where tipo = :t"), {"t": tipo})).scalar_one())

    async def eliminar(self, version_id: UUID) -> None:
        await self._sesion.execute(text("delete from vano_version where id = :i"), {"i": str(version_id)})
