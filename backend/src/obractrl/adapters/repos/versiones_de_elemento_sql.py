"""SQL de las propuestas y versiones de los elementos y sus conceptos (migración 0130). RLS por organización."""

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

__all__ = ["RepositorioVersionesDeElementoSQL"]

_NULO = "00000000-0000-0000-0000-000000000000"

_COLUMNAS = """
    v.id, v.elemento_id, v.raiz_id, v.fila_id, v.clase, v.estado, v.version, v.resumen, v.detalle,
    v.propuso_id, u1.nombre as propuso_nombre, v.propuso_rol, v.propuesto_en,
    v.decidio_id, u2.nombre as decidio_nombre, v.decidio_rol, v.decidido_en, v.motivo,
    coalesce(c.clave, ec.clave_propuesta) as concepto_clave
"""
_DE = """
    from elemento_version v
    left join usuario u1 on u1.id = v.propuso_id
    left join usuario u2 on u2.id = v.decidio_id
    left join elemento_concepto ec on ec.id = v.fila_id
    left join concepto c on c.id = ec.concepto_id
"""


class RepositorioVersionesDeElementoSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def raiz_de(self, elemento_id: UUID) -> UUID | None:
        fila = (
            await self._sesion.execute(
                text("select coalesce(raiz_id, id) from elemento_parametrico where id = :e"), {"e": str(elemento_id)}
            )
        ).first()
        return UUID(str(fila[0])) if fila else None

    async def vigente_de(self, raiz_id: UUID) -> UUID | None:
        """La versión vigente de la receta del elemento (la raíz la comparten todas, 0120)."""
        fila = (
            await self._sesion.execute(
                text(
                    "select id from elemento_parametrico where coalesce(raiz_id, id) = :r and vigente order by version desc limit 1"
                ),
                {"r": str(raiz_id)},
            )
        ).first()
        return UUID(str(fila[0])) if fila else None

    async def autorizadas(self, raiz_id: UUID, fila_id: UUID | None) -> list[int]:
        filas = (
            await self._sesion.execute(
                text(
                    "select version from elemento_version where raiz_id = :r and estado = 'autorizada' "
                    f"and coalesce(fila_id, cast('{_NULO}' as uuid)) = coalesce(cast(:f as uuid), cast('{_NULO}' as uuid))"
                ),
                {"r": str(raiz_id), "f": str(fila_id) if fila_id else None},
            )
        ).scalars().all()
        return [int(v) for v in filas]

    async def registrar(
        self,
        *,
        elemento_id: UUID,
        raiz_id: UUID,
        fila_id: UUID | None,
        clase: str,
        estado: str,
        version: int | None,
        resumen: str,
        detalle: dict[str, Any],
        propuso_id: UUID | None,
        propuso_rol: str | None,
        decidio_id: UUID | None = None,
        decidio_rol: str | None = None,
        motivo: str | None = None,
    ) -> UUID:
        """Una propuesta (`pendiente`) o una decisión directa (`autorizada`, cuando Control de obra cambia lo suyo)."""
        decidida = estado != "pendiente"
        try:
            async with self._sesion.begin_nested():
                nuevo = (
                    await self._sesion.execute(
                        text(
                            """
                            insert into elemento_version (org_id, elemento_id, raiz_id, fila_id, clase, estado, version, resumen, detalle,
                                                          propuso_id, propuso_rol, decidio_id, decidio_rol, decidido_en, motivo)
                            values (app.current_org_id(), :e, :r, :f, :c, :s, :v, :res, cast(:d as jsonb), :pi, :pr, :di, :dr,
                                    case when :dec then now() end, :m)
                            returning id
                            """
                        ),
                        {
                            "e": str(elemento_id), "r": str(raiz_id), "f": str(fila_id) if fila_id else None, "c": clase, "s": estado,
                            "v": version, "res": resumen, "d": json.dumps(detalle, default=str),
                            "pi": str(propuso_id) if propuso_id else None, "pr": propuso_rol,
                            "di": str(decidio_id) if decidio_id else None, "dr": decidio_rol, "dec": decidida, "m": motivo,
                        },
                    )
                ).scalar_one()
        except IntegrityError as e:
            if "ux_elemento_version_pendiente" in str(e):
                raise ErrorDeElementoParametrico(
                    "Ya hay una propuesta pendiente de este mismo cambio: espera a que Control de obra la decida."
                ) from e
            if "ux_elemento_version_numero" in str(e):
                raise ErrorDeElementoParametrico("La versión ya existe: vuelve a intentarlo.") from e
            raise
        return UUID(str(nuevo))

    async def obtener(self, revision_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(text(f"select {_COLUMNAS} {_DE} where v.id = :i"), {"i": str(revision_id)})
        ).mappings().first()
        return dict(fila) if fila else None

    async def decidir(
        self,
        revision_id: UUID,
        *,
        estado: str,
        version: int | None,
        decidio_id: UUID,
        decidio_rol: str,
        motivo: str | None = None,
        detalle: dict[str, Any] | None = None,
    ) -> None:
        await self._sesion.execute(
            text(
                """
                update elemento_version
                   set estado = :s, version = :v, decidio_id = :d, decidio_rol = :r, decidido_en = now(), motivo = :m,
                       detalle = coalesce(cast(:det as jsonb), detalle)
                 where id = :i and estado = 'pendiente'
                """
            ),
            {
                "i": str(revision_id), "s": estado, "v": version, "d": str(decidio_id), "r": decidio_rol, "m": motivo,
                "det": json.dumps(detalle, default=str) if detalle is not None else None,
            },
        )

    async def historial(self, raiz_id: UUID) -> list[dict[str, Any]]:
        """Todas las propuestas y versiones del elemento y de sus conceptos, de la más nueva a la más vieja."""
        filas = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} {_DE} where v.raiz_id = :r order by v.propuesto_en desc, v.version desc nulls first, v.id"),
                {"r": str(raiz_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def pendientes(self) -> list[dict[str, Any]]:
        """Todo lo que espera la autorización de Control de obra en la organización: propuestas, elementos nuevos y conceptos nuevos."""
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select 'revision' as tipo, v.id as ref, v.elemento_id, e.clave as elemento_clave, e.nombre as elemento_nombre,
                           v.fila_id, coalesce(c.clave, ec.clave_propuesta) as concepto_clave, v.clase, v.resumen,
                           v.propuso_id, u1.nombre as propuso_nombre, v.propuesto_en as desde
                      from elemento_version v
                      join elemento_parametrico e on e.id = v.elemento_id
                      left join elemento_concepto ec on ec.id = v.fila_id
                      left join concepto c on c.id = ec.concepto_id
                      left join usuario u1 on u1.id = v.propuso_id
                     where v.estado = 'pendiente' and e.vigente
                    union all
                    select 'elemento_nuevo', e.id, e.id, e.clave, e.nombre, null, null, 'elemento',
                           'Elemento nuevo propuesto: se usa como provisional hasta que Control de obra lo autorice',
                           e.autor_id, u.nombre, e.created_at
                      from elemento_parametrico e left join usuario u on u.id = e.autor_id
                     where e.estado_autorizacion = 'pendiente' and e.vigente
                    union all
                    select 'concepto_nuevo', ec.id, ec.elemento_id, e.clave, e.nombre, ec.id, ec.clave_propuesta, 'concepto',
                           'Concepto nuevo propuesto, sin precio: no cuenta en el presupuesto hasta que Control de obra lo autorice',
                           ec.autor_id, u.nombre, ec.created_at
                      from elemento_concepto ec join elemento_parametrico e on e.id = ec.elemento_id
                      left join usuario u on u.id = ec.autor_id
                     where ec.estado = 'propuesto' and e.vigente
                    order by desde, elemento_clave
                    """
                )
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def pendiente_de(self, raiz_id: UUID, fila_id: UUID | None, clase: str) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(
                    f"select {_COLUMNAS} {_DE} where v.raiz_id = :r and v.estado = 'pendiente' and v.clase = :c "
                    f"and coalesce(v.fila_id, cast('{_NULO}' as uuid)) = coalesce(cast(:f as uuid), cast('{_NULO}' as uuid))"
                ),
                {"r": str(raiz_id), "c": clase, "f": str(fila_id) if fila_id else None},
            )
        ).mappings().first()
        return dict(fila) if fila else None
