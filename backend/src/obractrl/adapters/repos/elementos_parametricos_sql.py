"""SQL de los elementos paramétricos (migración 0104). RLS por organización."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.adapters.repos.cuantificacion_sql import _hay_columna

__all__ = ["RepositorioElementosParametricosSQL"]

_COLUMNAS = "id, clave, nombre, tipo, parametros"


class RepositorioElementosParametricosSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def _con_versiones(self) -> bool:
        return await _hay_columna(self._sesion, "elemento_parametrico", "vigente")

    async def _columnas(self) -> str:
        return _COLUMNAS + (", version, raiz_id" if await self._con_versiones() else ", 1 as version, id as raiz_id")

    async def listar(self) -> list[dict[str, Any]]:
        """El catálogo: las versiones vigentes."""
        donde = " where vigente" if await self._con_versiones() else ""
        filas = (
            await self._sesion.execute(
                text(f"select {await self._columnas()} from elemento_parametrico{donde} order by lower(clave)")
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def listar_todos(self) -> list[dict[str, Any]]:
        """Todas las versiones, también las anteriores: las que aún usan los trazos de obras asignadas."""
        filas = (
            await self._sesion.execute(text(f"select {await self._columnas()} from elemento_parametrico order by lower(clave), version"))
        ).mappings().all()
        return [dict(f) for f in filas]

    async def obtener(self, elemento_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(f"select {await self._columnas()} from elemento_parametrico where id = :id"), {"id": str(elemento_id)}
            )
        ).mappings().first()
        return dict(fila) if fila else None

    async def obras_congeladas_con(self, elemento_id: UUID) -> list[UUID]:
        """Las obras con trazos de este elemento que ya tienen una parte asignada: conservan la versión con que midieron."""
        filas = (
            await self._sesion.execute(
                text(
                    "select distinct p.obra_id from trazo t join plano p on p.id = t.plano_id "
                    "where t.elemento_parametrico_id = :e "
                    "and exists (select 1 from parte_estado pe where pe.obra_id = p.obra_id and pe.estado = 'asignada')"
                ),
                {"e": str(elemento_id)},
            )
        ).scalars().all()
        return [UUID(str(f)) for f in filas]

    async def crear_version(self, elemento_id: UUID, *, clave: str, nombre: str, parametros: dict[str, Any], autor_id: UUID) -> UUID:
        """Una versión nueva del elemento: la anterior deja de estar vigente; los trazos de obras no asignadas y los vínculos
        con conceptos pasan a la nueva."""
        antes = (
            await self._sesion.execute(
                text("select tipo, coalesce(raiz_id, id) as raiz_id, version from elemento_parametrico where id = :id"),
                {"id": str(elemento_id)},
            )
        ).mappings().one()
        await self._sesion.execute(text("update elemento_parametrico set vigente = false where id = :id"), {"id": str(elemento_id)})
        nueva = UUID(
            str(
                (
                    await self._sesion.execute(
                        text(
                            """
                            insert into elemento_parametrico (org_id, clave, nombre, tipo, parametros, autor_id, version, raiz_id)
                            values (app.current_org_id(), :clave, :nombre, :tipo, cast(:p as jsonb), :autor, :v, :raiz)
                            returning id
                            """
                        ),
                        {
                            "clave": clave, "nombre": nombre, "tipo": antes["tipo"], "p": json.dumps(parametros),
                            "autor": str(autor_id), "v": int(antes["version"]) + 1, "raiz": str(antes["raiz_id"]),
                        },
                    )
                ).scalar_one()
            )
        )
        # Los conceptos que tomaban del elemento toman de la versión nueva (y siguen tomando de la anterior en lo congelado).
        await self._sesion.execute(
            text(
                "insert into elemento_concepto (org_id, elemento_id, concepto_id, unidad, toma, autor_id) "
                "select org_id, :n, concepto_id, unidad, toma, autor_id from elemento_concepto where elemento_id = :a"
            ),
            {"n": str(nueva), "a": str(elemento_id)},
        )
        # Los trazos de obras sin parte asignada pasan a la versión nueva.
        await self._sesion.execute(
            text(
                "update trazo t set elemento_parametrico_id = :n from plano p "
                "where p.id = t.plano_id and t.elemento_parametrico_id = :a "
                "and not exists (select 1 from parte_estado pe where pe.obra_id = p.obra_id and pe.estado = 'asignada')"
            ),
            {"n": str(nueva), "a": str(elemento_id)},
        )
        return nueva

    async def clave_en_uso(self, clave: str, *, salvo: UUID | None = None) -> bool:
        return bool(
            (
                await self._sesion.execute(
                    text(
                        "select exists (select 1 from elemento_parametrico "
                        "where lower(btrim(clave)) = lower(btrim(:c)) "
                        + ("and vigente " if await self._con_versiones() else "")
                        + "and (cast(:salvo as uuid) is null or id <> cast(:salvo as uuid)))"
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
        if await self._con_versiones():
            # La primera versión es su propia raíz: las siguientes comparten la raíz (0120).
            await self._sesion.execute(text("update elemento_parametrico set raiz_id = id where id = :id"), {"id": str(fila)})
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
        if await self._con_versiones():
            # Todas las versiones del elemento (comparten raíz).
            await self._sesion.execute(
                text(
                    "delete from elemento_parametrico where id = :id "
                    "or raiz_id = (select raiz_id from elemento_parametrico where id = :id)"
                ),
                {"id": str(elemento_id)},
            )
            return
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

    async def trazos_de_la_obra(self, obra_id: UUID) -> list[dict[str, Any]]:
        """Cada trazo de la obra (de todos sus planos) que es un elemento, con lo que aporta: 1 pieza, sus metros o sus m² (ya con la escala)."""
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
                     where p.obra_id = :obra and t.hueco_de is null and not t.propuesta
                    """
                ),
                {"obra": str(obra_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def obra_del_trazo(self, trazo_id: UUID) -> UUID | None:
        fila = (
            await self._sesion.execute(
                text("select p.obra_id from trazo t join plano p on p.id = t.plano_id where t.id = :t"), {"t": str(trazo_id)}
            )
        ).scalar_one_or_none()
        return UUID(str(fila)) if fila else None

    async def obras_con_el_elemento(self, elemento_id: UUID | None = None) -> list[UUID]:
        """Las obras con trazos marcados como este elemento (o como cualquiera, sin `elemento_id`)."""
        filas = (
            await self._sesion.execute(
                text(
                    "select distinct p.obra_id from trazo t join plano p on p.id = t.plano_id "
                    "where t.elemento_parametrico_id is not null "
                    "and (cast(:e as uuid) is null or t.elemento_parametrico_id = cast(:e as uuid))"
                ),
                {"e": str(elemento_id) if elemento_id else None},
            )
        ).scalars().all()
        return [UUID(str(f)) for f in filas]

    async def conceptos_de(self, elemento_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select ec.concepto_id, c.clave, c.descripcion, ec.unidad, ec.toma
                      from elemento_concepto ec join concepto c on c.id = ec.concepto_id
                     where ec.elemento_id = :e order by lower(c.clave)
                    """
                ),
                {"e": str(elemento_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def de_todos_los_elementos(self) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select ec.elemento_id, ec.concepto_id, c.clave, c.descripcion, ec.unidad, ec.toma
                      from elemento_concepto ec join concepto c on c.id = ec.concepto_id order by lower(c.clave)
                    """
                )
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def fijar_concepto(
        self, *, elemento_id: UUID, concepto_id: UUID, unidad: str, toma: dict[str, bool], autor_id: UUID
    ) -> None:
        await self._sesion.execute(
            text(
                """
                insert into elemento_concepto (org_id, elemento_id, concepto_id, unidad, toma, autor_id)
                select e.org_id, e.id, :c, :u, cast(:t as jsonb), :a from elemento_parametrico e where e.id = :e
                on conflict (elemento_id, concepto_id) do update set unidad = excluded.unidad, toma = excluded.toma,
                                                                      autor_id = excluded.autor_id
                """
            ),
            {"e": str(elemento_id), "c": str(concepto_id), "u": unidad, "t": json.dumps(toma), "a": str(autor_id)},
        )

    async def quitar_concepto(self, *, elemento_id: UUID, concepto_id: UUID) -> None:
        await self._sesion.execute(
            text("delete from elemento_concepto where elemento_id = :e and concepto_id = :c"),
            {"e": str(elemento_id), "c": str(concepto_id)},
        )

    async def concepto_existe(self, concepto_id: UUID) -> bool:
        return bool(
            (await self._sesion.execute(text("select 1 from concepto where id = :c"), {"c": str(concepto_id)})).first()
        )
