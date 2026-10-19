"""Repositorio del catálogo de ensambles paramétricos.

Spec §12.11 (adaptador de persistencia) · §12.4 (RLS, migración 0061) ·
skill `erp-parametrico`.

Igual que `conceptos_sql.py` con APU: el dominio (`domain.catalogos.
ensamble`) explota por CLAVE (§3.3); este adaptador guarda y lee por id,
y `renglones_recursivos` resuelve la clave de cada hijo para que el caso
de uso no tenga que ir y venir entre los dos mundos.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioEnsamblesSQL"]

_PROFUNDIDAD_MAXIMA = 32
"""Mismo tope que `domain.catalogos.apu`/`domain.catalogos.ensamble`: un
cinturón de seguridad para que el CTE termine, no una regla de negocio."""

_COLUMNAS = """
    id, clave, nombre, divisor_concepto_id, divisor_nombre, tasa,
    dispersion, tasa_calculada_en, estatus
"""

_ALCANCE = f"""
    with recursive alcance as (
        select cast(:ensamble_id as uuid) as ensamble_id,
               array[cast(:ensamble_id as uuid)] as camino
        union all
        select r.sub_ensamble_id, a.camino || r.sub_ensamble_id
        from ensamble_renglon r
        join alcance a on r.ensamble_id = a.ensamble_id
        where r.sub_ensamble_id is not null
          and not (r.sub_ensamble_id = any(a.camino))
          and cardinality(a.camino) <= {_PROFUNDIDAD_MAXIMA}
    )
"""


class RepositorioEnsamblesSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def crear(self, datos: dict[str, Any]) -> UUID:
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into ensamble
                        (org_id, clave, nombre, divisor_concepto_id, divisor_nombre)
                    values (cast(current_setting('app.org_id') as uuid),
                            :clave, :nombre, cast(:divisor_concepto_id as uuid),
                            :divisor_nombre)
                    returning id
                    """
                ),
                {
                    "clave": datos["clave"],
                    "nombre": datos["nombre"],
                    "divisor_concepto_id": (
                        str(datos["divisor_concepto_id"])
                        if datos.get("divisor_concepto_id")
                        else None
                    ),
                    "divisor_nombre": datos.get("divisor_nombre"),
                },
            )
        ).scalar_one()

    async def obtener(self, ensamble_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} from ensamble where id = :id"),
                {"id": str(ensamble_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def obtener_por_clave(self, clave: str) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} from ensamble where clave = :clave"),
                {"clave": clave},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def listar(self, *, solo_activos: bool = True) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS}
                    from ensamble
                    where not cast(:solo_activos as boolean) or estatus = 'activo'
                    order by clave
                    """
                ),
                {"solo_activos": solo_activos},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def renglones(self, ensamble_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select r.id, r.cantidad, r.origen, r.orden,
                           r.concepto_id, c.clave as concepto_clave,
                           r.sub_ensamble_id, s.clave as sub_ensamble_clave,
                           r.presupuesto_origen_id
                      from ensamble_renglon r
                      left join concepto c on c.id = r.concepto_id
                      left join ensamble s on s.id = r.sub_ensamble_id
                     where r.ensamble_id = cast(:ensamble_id as uuid)
                     order by r.orden, coalesce(c.clave, s.clave)
                    """
                ),
                {"ensamble_id": str(ensamble_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def renglones_recursivos(self, ensamble_id: UUID) -> list[dict[str, Any]]:
        """Ver el puerto (`RepositorioEnsambles.renglones_recursivos`):
        todo renglón alcanzable, con la clave del ensamble padre y la del
        hijo (concepto o sub-ensamble) ya resueltas."""
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    {_ALCANCE}
                    select
                        padre.clave       as ensamble_clave,
                        r.cantidad        as cantidad,
                        r.origen          as origen,
                        r.orden           as orden,
                        c.id              as concepto_id,
                        c.clave           as concepto_clave,
                        sub.clave         as sub_ensamble_clave
                      from ensamble_renglon r
                      join ensamble padre on padre.id = r.ensamble_id
                      left join concepto c    on c.id    = r.concepto_id
                      left join ensamble sub on sub.id = r.sub_ensamble_id
                     where r.ensamble_id in (select ensamble_id from alcance)
                     order by padre.clave, r.orden, coalesce(c.clave, sub.clave)
                    """
                ),
                {"ensamble_id": str(ensamble_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def agregar_renglones(
        self, ensamble_id: UUID, renglones: Sequence[dict[str, Any]]
    ) -> None:
        for renglon in renglones:
            await self._sesion.execute(
                text(
                    """
                    insert into ensamble_renglon
                        (org_id, ensamble_id, concepto_id, sub_ensamble_id,
                         cantidad, origen, presupuesto_origen_id, orden)
                    values (cast(current_setting('app.org_id') as uuid),
                            cast(:ensamble_id as uuid), cast(:concepto_id as uuid),
                            cast(:sub_ensamble_id as uuid), :cantidad,
                            cast(:origen as origen_cantidad_ensamble),
                            cast(:presupuesto_origen_id as uuid), :orden)
                    """
                ),
                {
                    "ensamble_id": str(ensamble_id),
                    "concepto_id": (
                        str(renglon["concepto_id"])
                        if renglon.get("concepto_id")
                        else None
                    ),
                    "sub_ensamble_id": (
                        str(renglon["sub_ensamble_id"])
                        if renglon.get("sub_ensamble_id")
                        else None
                    ),
                    "cantidad": Decimal(str(renglon["cantidad"])),
                    "origen": renglon["origen"],
                    "presupuesto_origen_id": (
                        str(renglon["presupuesto_origen_id"])
                        if renglon.get("presupuesto_origen_id")
                        else None
                    ),
                    "orden": int(renglon.get("orden") or 0),
                },
            )

    async def cohorte(self, ensamble_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select p.id as prototipo_id, p.clave as prototipo_clave
                      from ensamble_cohorte ec
                      join prototipo p on p.id = ec.prototipo_id
                     where ec.ensamble_id = cast(:ensamble_id as uuid)
                     order by p.clave
                    """
                ),
                {"ensamble_id": str(ensamble_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def agregar_cohorte(
        self, ensamble_id: UUID, prototipo_ids: Sequence[UUID]
    ) -> None:
        for prototipo_id in prototipo_ids:
            await self._sesion.execute(
                text(
                    """
                    insert into ensamble_cohorte (ensamble_id, org_id, prototipo_id)
                    values (cast(:ensamble_id as uuid),
                            cast(current_setting('app.org_id') as uuid),
                            cast(:prototipo_id as uuid))
                    on conflict (ensamble_id, prototipo_id) do nothing
                    """
                ),
                {"ensamble_id": str(ensamble_id), "prototipo_id": str(prototipo_id)},
            )

    async def publicar_tasa(
        self, ensamble_id: UUID, *, tasa: Decimal, dispersion: Decimal
    ) -> None:
        await self._sesion.execute(
            text(
                """
                update ensamble
                   set tasa = :tasa, dispersion = :dispersion,
                       tasa_calculada_en = now()
                 where id = cast(:ensamble_id as uuid)
                """
            ),
            {"ensamble_id": str(ensamble_id), "tasa": tasa, "dispersion": dispersion},
        )
