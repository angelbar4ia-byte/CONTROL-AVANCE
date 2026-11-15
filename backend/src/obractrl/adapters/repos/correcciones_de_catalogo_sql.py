"""SQL de las correcciones propuestas al catálogo (migración 0132). RLS por organización."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.domain.cuantificacion.elementos_parametricos import (
    ErrorDeElementoParametrico,
)

__all__ = ["RepositorioCorreccionesDeCatalogoSQL"]

_COLUMNAS = """
    c.id, c.concepto_clave, c.campo, c.valor_catalogo, c.valor_propuesto, c.motivo, c.fuente, c.estado, c.version,
    c.propuso_id, u1.nombre as propuso_nombre, c.propuso_rol, c.propuesto_en,
    c.decidio_id, u2.nombre as decidio_nombre, c.decidio_rol, c.decidido_en, c.motivo_rechazo
"""
_DE = """
    from correccion_de_catalogo c
    left join usuario u1 on u1.id = c.propuso_id
    left join usuario u2 on u2.id = c.decidio_id
"""


class RepositorioCorreccionesDeCatalogoSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def historial(self) -> list[dict[str, Any]]:
        """Todas las propuestas y versiones de la organización, de la más nueva a la más vieja."""
        filas = (
            await self._sesion.execute(text(f"select {_COLUMNAS} {_DE} order by c.propuesto_en desc, c.version desc nulls first, c.id"))
        ).mappings().all()
        return [dict(f) for f in filas]

    async def obtener(self, correccion_id: UUID) -> dict[str, Any] | None:
        fila = (await self._sesion.execute(text(f"select {_COLUMNAS} {_DE} where c.id = :i"), {"i": str(correccion_id)})).mappings().first()
        return dict(fila) if fila else None

    async def autorizadas(self, concepto_clave: str, campo: str) -> list[int]:
        filas = (
            await self._sesion.execute(
                text(
                    "select version from correccion_de_catalogo where upper(concepto_clave) = upper(:k) and campo = :c "
                    "and estado = 'autorizada'"
                ),
                {"k": concepto_clave, "c": campo},
            )
        ).scalars().all()
        return [int(v) for v in filas]

    async def registrar(
        self,
        *,
        concepto_clave: str,
        campo: str,
        valor_catalogo: str,
        valor_propuesto: str,
        motivo: str,
        fuente: str,
        estado: str,
        version: int | None,
        propuso_id: UUID,
        propuso_rol: str,
    ) -> UUID:
        """Una propuesta (`pendiente`) o, si la hace Control de obra, la versión ya autorizada."""
        decidida = estado != "pendiente"
        try:
            async with self._sesion.begin_nested():
                nuevo = (
                    await self._sesion.execute(
                        text(
                            """
                            insert into correccion_de_catalogo (org_id, concepto_clave, campo, valor_catalogo, valor_propuesto, motivo, fuente,
                                                                estado, version, propuso_id, propuso_rol, decidio_id, decidio_rol, decidido_en)
                            values (app.current_org_id(), :k, :c, :vc, :vp, :m, :f, :s, :v, :pi, :pr,
                                    case when :dec then cast(:pi as uuid) end, case when :dec then :pr end, case when :dec then now() end)
                            returning id
                            """
                        ),
                        {
                            "k": concepto_clave, "c": campo, "vc": valor_catalogo, "vp": valor_propuesto, "m": motivo, "f": fuente,
                            "s": estado, "v": version, "pi": str(propuso_id), "pr": propuso_rol, "dec": decidida,
                        },
                    )
                ).scalar_one()
        except IntegrityError as e:
            if "ux_correccion_de_catalogo_pendiente" in str(e):
                raise ErrorDeElementoParametrico(
                    "Ya hay una propuesta pendiente de esta corrección: espera a que Control de obra la decida."
                ) from e
            if "ux_correccion_de_catalogo_numero" in str(e):
                raise ErrorDeElementoParametrico("La versión ya existe: vuelve a intentarlo.") from e
            raise
        return UUID(str(nuevo))

    async def decidir(
        self, correccion_id: UUID, *, estado: str, version: int | None, decidio_id: UUID, decidio_rol: str, motivo: str | None = None
    ) -> None:
        try:
            async with self._sesion.begin_nested():
                await self._sesion.execute(
                    text(
                        """
                        update correccion_de_catalogo
                           set estado = :s, version = :v, decidio_id = :d, decidio_rol = :r, decidido_en = now(), motivo_rechazo = :m
                         where id = :i and estado = 'pendiente'
                        """
                    ),
                    {"i": str(correccion_id), "s": estado, "v": version, "d": str(decidio_id), "r": decidio_rol, "m": motivo},
                )
        except IntegrityError as e:
            if "ux_correccion_de_catalogo_numero" in str(e):
                raise ErrorDeElementoParametrico("La versión ya existe: vuelve a intentarlo.") from e
            raise
