"""SQL de los elementos paramétricos (migración 0104). RLS por organización."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.adapters.repos.cuantificacion_sql import _hay_columna
from obractrl.domain.cuantificacion.clasificacion_de_elementos import ElementoDuplicado

__all__ = ["RepositorioElementosParametricosSQL"]

_COLUMNAS = "id, clave, nombre, tipo, parametros, categoria, subcategoria, firma, materiales"
_INDICE_DE_FIRMA = "ux_elemento_parametrico_firma"


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

    async def crear_version(
        self,
        elemento_id: UUID,
        *,
        clave: str,
        nombre: str,
        parametros: dict[str, Any],
        autor_id: UUID,
        categoria: str,
        subcategoria: str,
        firma: str,
        materiales: dict[str, Any] | None = None,
    ) -> UUID:
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
                            insert into elemento_parametrico
                                (org_id, clave, nombre, tipo, parametros, autor_id, version, raiz_id, categoria, subcategoria, firma, materiales)
                            values (app.current_org_id(), :clave, :nombre, :tipo, cast(:p as jsonb), :autor, :v, :raiz,
                                    :cat, :sub, :firma, cast(:mat as jsonb))
                            returning id
                            """
                        ),
                        {
                            "clave": clave, "nombre": nombre, "tipo": antes["tipo"], "p": json.dumps(parametros),
                            "autor": str(autor_id), "v": int(antes["version"]) + 1, "raiz": str(antes["raiz_id"]),
                            "cat": categoria, "sub": subcategoria, "firma": firma, "mat": json.dumps(materiales or {}),
                        },
                    )
                ).scalar_one()
            )
        )
        # Los insumos agregados al elemento pasan a la versión nueva.
        await self._sesion.execute(
            text(
                "insert into elemento_insumo (org_id, elemento_id, insumo_id, clase, cantidad, autor_id) "
                "select org_id, :n, insumo_id, clase, cantidad, autor_id from elemento_insumo where elemento_id = :a"
            ),
            {"n": str(nueva), "a": str(elemento_id)},
        )
        # Los conceptos que tomaban del elemento toman de la versión nueva (y siguen tomando de la anterior en lo congelado).
        await self._sesion.execute(
            text(
                "insert into elemento_concepto (org_id, elemento_id, concepto_id, unidad, toma, autor_id, nivel_min, nivel_max, ubicacion, "
                "alto_hasta_m, estado, clave_propuesta, descripcion) "
                "select org_id, :n, concepto_id, unidad, toma, autor_id, nivel_min, nivel_max, ubicacion, "
                "alto_hasta_m, estado, clave_propuesta, descripcion from elemento_concepto where elemento_id = :a"
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

    async def buscar_duplicado(self, firma: str, *, salvo: UUID | None = None) -> dict[str, Any] | None:
        """El elemento vigente con esa firma (otro que `salvo`). Los anteriores a la 0127 que quedaron sin firma se comparan
        con la que calcula la base al vuelo, así el duplicado de un elemento viejo tampoco pasa."""
        fila = (
            await self._sesion.execute(
                text(
                    "select id, clave from elemento_parametrico "
                    "where vigente and coalesce(firma, app.firma_elemento(categoria, subcategoria, tipo, parametros, materiales)) = :f "
                    "and (cast(:salvo as uuid) is null or id <> cast(:salvo as uuid)) order by created_at, id limit 1"
                ),
                {"f": firma, "salvo": str(salvo) if salvo else None},
            )
        ).mappings().first()
        return dict(fila) if fila else None

    async def _dar_por_duplicado(self, error: IntegrityError, firma: str, salvo: UUID | None) -> None:
        """Dos altas idénticas a la vez: el índice único de la firma ataja a la segunda (la 1.ª ya está confirmada)."""
        if _INDICE_DE_FIRMA not in str(error.orig) and _INDICE_DE_FIRMA not in str(error):
            raise error
        igual = await self.buscar_duplicado(firma, salvo=salvo)
        raise ElementoDuplicado(igual["clave"] if igual else "otro", igual["id"] if igual else None) from error

    async def crear(
        self,
        *,
        clave: str,
        nombre: str,
        tipo: str,
        parametros: dict[str, Any],
        autor_id: UUID,
        categoria: str,
        subcategoria: str,
        firma: str,
        materiales: dict[str, Any] | None = None,
    ) -> UUID:
        try:
            async with self._sesion.begin_nested():
                fila = (
                    await self._sesion.execute(
                        text(
                            """
                            insert into elemento_parametrico (org_id, clave, nombre, tipo, parametros, autor_id, categoria, subcategoria, firma, materiales)
                            values (app.current_org_id(), :clave, :nombre, :tipo, cast(:p as jsonb), :autor, :cat, :sub, :firma, cast(:mat as jsonb))
                            returning id
                            """
                        ),
                        {
                            "clave": clave, "nombre": nombre, "tipo": tipo, "p": json.dumps(parametros), "autor": str(autor_id),
                            "cat": categoria, "sub": subcategoria, "firma": firma, "mat": json.dumps(materiales or {}),
                        },
                    )
                ).scalar_one()
        except IntegrityError as e:
            await self._dar_por_duplicado(e, firma, None)
            raise
        if await self._con_versiones():
            # La primera versión es su propia raíz: las siguientes comparten la raíz (0120).
            await self._sesion.execute(text("update elemento_parametrico set raiz_id = id where id = :id"), {"id": str(fila)})
        return UUID(str(fila))

    async def actualizar(
        self,
        elemento_id: UUID,
        *,
        clave: str,
        nombre: str,
        parametros: dict[str, Any],
        categoria: str,
        subcategoria: str,
        firma: str | None,
        materiales: dict[str, Any] | None = None,
    ) -> None:
        try:
            async with self._sesion.begin_nested():
                await self._sesion.execute(
                    text(
                        "update elemento_parametrico set clave = :clave, nombre = :nombre, parametros = cast(:p as jsonb), "
                        "categoria = :cat, subcategoria = :sub, firma = :firma, materiales = cast(:mat as jsonb) where id = :id"
                    ),
                    {
                        "id": str(elemento_id), "clave": clave, "nombre": nombre, "p": json.dumps(parametros),
                        "cat": categoria, "sub": subcategoria, "firma": firma, "mat": json.dumps(materiales or {}),
                    },
                )
        except IntegrityError as e:
            if firma is None:
                raise
            await self._dar_por_duplicado(e, firma, elemento_id)
            raise

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
                     where ec.elemento_id = :e and ec.concepto_id is not null and ec.nivel_min is null and ec.nivel_max is null and ec.ubicacion is null and ec.alto_hasta_m is null order by lower(c.clave)
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
                      from elemento_concepto ec join concepto c on c.id = ec.concepto_id
                     where true and ec.concepto_id is not null and ec.nivel_min is null and ec.nivel_max is null and ec.ubicacion is null and ec.alto_hasta_m is null order by lower(c.clave)
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
                on conflict (elemento_id, concepto_id, coalesce(nivel_min, 0), coalesce(nivel_max, 0), coalesce(ubicacion, ''),
                             coalesce(alto_hasta_m, 0)) where concepto_id is not null do update set unidad = excluded.unidad, toma = excluded.toma,
                                                                      autor_id = excluded.autor_id
                """
            ),
            {"e": str(elemento_id), "c": str(concepto_id), "u": unidad, "t": json.dumps(toma), "a": str(autor_id)},
        )

    async def quitar_concepto(self, *, elemento_id: UUID, concepto_id: UUID) -> None:
        await self._sesion.execute(
            text(
                "delete from elemento_concepto where elemento_id = :e and concepto_id = :c and nivel_min is null and nivel_max is null "
                "and ubicacion is null and alto_hasta_m is null"
            ),
            {"e": str(elemento_id), "c": str(concepto_id)},
        )

    async def concepto_existe(self, concepto_id: UUID) -> bool:
        return bool(
            (await self._sesion.execute(text("select 1 from concepto where id = :c"), {"c": str(concepto_id)})).first()
        )

    # --- Conceptos por contexto y escalón (0128) -----------------------------------------------------------------

    async def conceptos_por_contexto(self, elemento_id: UUID) -> list[dict[str, Any]]:
        """Todos los conceptos del elemento: los del catálogo y los propuestos, con su contexto, escalón y estado."""
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select ec.id, ec.concepto_id, coalesce(c.clave, ec.clave_propuesta) as clave,
                           coalesce(ec.descripcion, c.descripcion) as descripcion, c.descripcion as descripcion_catalogo,
                           ec.unidad, ec.toma, ec.ranura, ec.estado, ec.nivel_min, ec.nivel_max, ec.ubicacion, ec.alto_hasta_m
                      from elemento_concepto ec left join concepto c on c.id = ec.concepto_id
                     where ec.elemento_id = :e
                     order by coalesce(ec.nivel_min, 0), coalesce(ec.ubicacion, ''), ec.ranura, coalesce(ec.alto_hasta_m, 0),
                              lower(coalesce(c.clave, ec.clave_propuesta))
                    """
                ),
                {"e": str(elemento_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def concepto_por_contexto(self, elemento_id: UUID, fila_id: UUID) -> dict[str, Any] | None:
        for f in await self.conceptos_por_contexto(elemento_id):
            if f["id"] == fila_id:
                return f
        return None

    async def clave_de_concepto(self, concepto_id: UUID) -> str | None:
        fila = (await self._sesion.execute(text("select clave from concepto where id = :c"), {"c": str(concepto_id)})).first()
        return str(fila[0]) if fila else None

    async def concepto_con_clave(self, clave: str) -> bool:
        return bool(
            (await self._sesion.execute(text("select 1 from concepto where upper(clave) = upper(:k)"), {"k": clave})).first()
        )

    async def agregar_concepto_por_contexto(
        self,
        *,
        elemento_id: UUID,
        concepto_id: UUID | None,
        clave_propuesta: str | None,
        descripcion: str | None,
        unidad: str,
        toma: dict[str, bool],
        nivel_min: int | None,
        nivel_max: int | None,
        ubicacion: str | None,
        alto_hasta_m: Any,
        estado: str,
        autor_id: UUID,
    ) -> UUID:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    insert into elemento_concepto (org_id, elemento_id, concepto_id, clave_propuesta, descripcion, unidad, toma,
                                                   nivel_min, nivel_max, ubicacion, alto_hasta_m, estado, autor_id)
                    select e.org_id, e.id, cast(:c as uuid), :k, :d, :u, cast(:t as jsonb), :nmin, :nmax, :ub, :h, :s, :a
                      from elemento_parametrico e where e.id = :e
                    returning id
                    """
                ),
                {
                    "e": str(elemento_id), "c": str(concepto_id) if concepto_id else None, "k": clave_propuesta, "d": descripcion,
                    "u": unidad, "t": json.dumps(toma), "nmin": nivel_min, "nmax": nivel_max, "ub": ubicacion, "h": alto_hasta_m,
                    "s": estado, "a": str(autor_id),
                },
            )
        ).scalar_one()
        return UUID(str(fila))

    async def cambiar_descripcion_de_concepto(self, fila_id: UUID, descripcion: str | None) -> None:
        await self._sesion.execute(
            text("update elemento_concepto set descripcion = :d where id = :i"), {"d": descripcion, "i": str(fila_id)}
        )

    async def quitar_concepto_por_contexto(self, fila_id: UUID) -> None:
        await self._sesion.execute(text("delete from elemento_concepto where id = :i"), {"i": str(fila_id)})
