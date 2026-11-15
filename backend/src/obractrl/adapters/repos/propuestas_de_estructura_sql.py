"""SQL de las propuestas de versión de concepto de los elementos de estructura (migración 0131). RLS por organización."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.domain.cuantificacion.elementos_parametricos import (
    ErrorDeElementoParametrico,
)

__all__ = ["RepositorioPropuestasDeEstructuraSQL"]

_COLUMNAS = """
    p.id, p.elemento_clave, p.concepto_clave, p.clase, p.estado, p.version, p.resumen, p.detalle,
    p.propuso_id, u1.nombre as propuso_nombre, p.propuso_rol, p.propuesto_en,
    p.decidio_id, u2.nombre as decidio_nombre, p.decidio_rol, p.decidido_en, p.motivo
"""
_DE = """
    from propuesta_de_estructura p
    left join usuario u1 on u1.id = p.propuso_id
    left join usuario u2 on u2.id = p.decidio_id
"""


class RepositorioPropuestasDeEstructuraSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def del_elemento(self, elemento_clave: str) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} {_DE} where p.elemento_clave = :e order by p.propuesto_en desc, p.concepto_clave"),
                {"e": elemento_clave},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def pendientes(self) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} {_DE} where p.estado = 'pendiente' order by p.propuesto_en, p.concepto_clave")
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def obtener(self, propuesta_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(text(f"select {_COLUMNAS} {_DE} where p.id = :i"), {"i": str(propuesta_id)})
        ).mappings().first()
        return dict(fila) if fila else None

    async def autorizadas(self, concepto_clave: str, clase: str) -> list[int]:
        filas = (
            await self._sesion.execute(
                text(
                    "select version from propuesta_de_estructura "
                    "where concepto_clave = :c and clase = :k and estado = 'autorizada'"
                ),
                {"c": concepto_clave, "k": clase},
            )
        ).scalars().all()
        return [int(v) for v in filas]

    async def vigentes_del_concepto(self, concepto_clave: str) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} {_DE} where p.concepto_clave = :c and p.estado in ('pendiente', 'autorizada')"),
                {"c": concepto_clave},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def registrar(
        self,
        *,
        elemento_clave: str,
        concepto_clave: str,
        clase: str,
        estado: str,
        version: int | None,
        resumen: str,
        detalle: dict[str, Any],
        propuso_id: UUID | None,
        propuso_rol: str | None,
        decidio_id: UUID | None = None,
        decidio_rol: str | None = None,
    ) -> UUID:
        """Una propuesta (`pendiente`) o una decisión directa (`autorizada`, cuando Control de obra propone lo suyo)."""
        decidida = estado != "pendiente"
        try:
            async with self._sesion.begin_nested():
                nuevo = (
                    await self._sesion.execute(
                        text(
                            """
                            insert into propuesta_de_estructura (org_id, elemento_clave, concepto_clave, clase, estado, version, resumen,
                                                                 detalle, propuso_id, propuso_rol, decidio_id, decidio_rol, decidido_en)
                            values (app.current_org_id(), :e, :c, :k, :s, :v, :res, cast(:d as jsonb), :pi, :pr, :di, :dr,
                                    case when :dec then now() end)
                            returning id
                            """
                        ),
                        {
                            "e": elemento_clave, "c": concepto_clave, "k": clase, "s": estado, "v": version, "res": resumen,
                            "d": json.dumps(detalle, default=str),
                            "pi": str(propuso_id) if propuso_id else None, "pr": propuso_rol,
                            "di": str(decidio_id) if decidio_id else None, "dr": decidio_rol, "dec": decidida,
                        },
                    )
                ).scalar_one()
        except IntegrityError as e:
            if "ux_propuesta_estructura_pendiente" in str(e):
                raise ErrorDeElementoParametrico(
                    f"Ya hay una propuesta pendiente de {concepto_clave}: espera a que Control de obra la decida."
                ) from e
            if "ux_propuesta_estructura_numero" in str(e):
                raise ErrorDeElementoParametrico("La versión ya existe: vuelve a intentarlo.") from e
            raise
        return UUID(str(nuevo))

    async def decidir(
        self, propuesta_id: UUID, *, estado: str, version: int | None, decidio_id: UUID, decidio_rol: str, motivo: str | None = None
    ) -> None:
        try:
            async with self._sesion.begin_nested():
                await self._sesion.execute(
                    text(
                        """
                        update propuesta_de_estructura
                           set estado = :s, version = :v, decidio_id = :di, decidio_rol = :dr, decidido_en = now(), motivo = :m
                         where id = :i and estado = 'pendiente'
                        """
                    ),
                    {"i": str(propuesta_id), "s": estado, "v": version, "di": str(decidio_id), "dr": decidio_rol, "m": motivo},
                )
        except IntegrityError as e:
            if "ux_propuesta_estructura_numero" in str(e):
                raise ErrorDeElementoParametrico("La versión ya existe: vuelve a intentarlo.") from e
            raise
