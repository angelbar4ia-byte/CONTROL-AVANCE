"""Repositorios del cuantificador (`plano`, `trazo`, `enlace_cuantificacion`,
`nota_plano`, migración 0057).

Spec §12.11 (adaptador de persistencia) · cerebro MODELO.md §1b · §12.4
(RLS).

Las cuatro tablas entran a sus propias políticas (`plano_scope`/
`trazo_scope`/`enlace_cuantificacion_scope`/`nota_plano_scope`, migración
0057), todas por `app.obra_visible` encadenado hasta `plano.obra_id`:
ningún método de aquí filtra por `org_id`, `obra_id` o visibilidad a mano
— eso lo impone la base. `org_id` en cada INSERT sale de
`current_setting('app.org_id')`, igual que en `expediente_sql.py`.

**Aquí, y solo aquí, PostGIS entra en juego** (§12.11: el dominio nunca lo
toca). `ST_GeomFromText` convierte el WKT de captura a geometría nativa al
escribir; `ST_Area`/`ST_Perimeter`/`ST_Length` —o el literal `1` para
`conteo`, que no es una función de PostGIS— calculan la medida al leer.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "RepositorioEnlacesCuantificacionSQL",
    "RepositorioNotasPlanoSQL",
    "RepositorioPlanosSQL",
    "RepositorioTrazosSQL",
]

# `ST_Area`/`ST_Perimeter`/`ST_Length` sobre la geometría nativa; `conteo`
# es un literal (MODELO.md §1b: "cuántas filas de trazo enlaza, no una
# función de PostGIS") — este `case` es la única fórmula que decide cuál
# aplicar, y la usan todas las consultas que leen `medida_valor`.
#
# La medida se lee **ya escalada** (migración 0069): `p.escala_m_por_unidad` son
# los metros por unidad de plano, `null` = sin calibrar = 1. Un área escala con el
# cuadrado, un largo con la escala, un conteo no escala. Toda consulta que use
# esta fórmula debe unir `plano p` (`p.id = t.plano_id`).
_ESCALA_SQL = "coalesce(p.escala_m_por_unidad, 1)"
#
# La geometría que se mide es la **efectiva** (0086): la del trazo menos sus huecos. Y el
# área de una línea con grosor es largo × grosor (un muro), no el área de un segmento.
_GEOMETRIA_SQL = "app.geometria_efectiva(t.id, t.geometria)"
# Una línea inclinada mide más que su proyección en planta: × √(1 + (pendiente/100)²) (0087).
_PENDIENTE_SQL = "sqrt(1 + power(coalesce(t.pendiente_pct, 0) / 100.0, 2))"
_MEDIDA_VALOR_SQL = f"""
    case e.medida
      when 'area'      then case
                              when t.grosor_m is not null
                                then ST_Length({_GEOMETRIA_SQL}) * {_ESCALA_SQL} * t.grosor_m * {_PENDIENTE_SQL}
                              else ST_Area({_GEOMETRIA_SQL}) * power({_ESCALA_SQL}, 2)
                            end
      when 'perimetro'  then ST_Perimeter({_GEOMETRIA_SQL}) * {_ESCALA_SQL}
      when 'longitud'   then ST_Length({_GEOMETRIA_SQL}) * {_ESCALA_SQL} * {_PENDIENTE_SQL}
      when 'conteo'     then 1
    end
"""


class RepositorioPlanosSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def crear(
        self,
        *,
        obra_id: UUID,
        nombre: str,
        archivo_url: str,
        version: int,
        capas: list[str] | None,
        subido_por: UUID,
    ) -> UUID:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    insert into plano
                        (org_id, obra_id, nombre, archivo_url, version,
                         capas, subido_por)
                    values
                        (cast(current_setting('app.org_id') as uuid),
                         :obra_id, :nombre, :archivo_url, :version,
                         cast(:capas as text[]), :subido_por)
                    returning id
                    """
                ),
                {
                    "obra_id": str(obra_id),
                    "nombre": nombre,
                    "archivo_url": archivo_url,
                    "version": version,
                    "capas": capas,
                    "subido_por": str(subido_por),
                },
            )
        ).scalar_one()
        return fila

    async def obtener(self, plano_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select id, obra_id, nombre, archivo_url, version, capas,
                           subido_por, created_at, escala_m_por_unidad,
                           escala_referencia, escala_calibrada_en,
                           rotacion_grados, volteo_horizontal, volteo_vertical
                      from plano
                     where id = :id
                    """
                ),
                {"id": str(plano_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def obra_visible(self, obra_id: UUID) -> bool:
        return bool(
            (
                await self._sesion.execute(
                    text("select exists (select 1 from obra where id = :id)"),
                    {"id": str(obra_id)},
                )
            ).scalar_one()
        )

    async def fijar_escala(
        self,
        plano_id: UUID,
        *,
        escala_m_por_unidad: Decimal,
        referencia: dict[str, Any],
        usuario_id: UUID,
    ) -> None:
        """Calibra (o recalibra) el plano. La geometría de los trazos no se
        toca: la escala se aplica al leer la medida (migración 0069)."""
        await self._sesion.execute(
            text(
                """
                update plano
                   set escala_m_por_unidad  = :escala,
                       escala_referencia    = cast(:referencia as jsonb),
                       escala_calibrada_por = :usuario_id,
                       escala_calibrada_en  = now()
                 where id = :id
                """
            ),
            {
                "id": str(plano_id),
                "escala": escala_m_por_unidad,
                "referencia": json.dumps(referencia),
                "usuario_id": str(usuario_id),
            },
        )

    async def fijar_vista(
        self,
        plano_id: UUID,
        *,
        rotacion_grados: int,
        volteo_horizontal: bool,
        volteo_vertical: bool,
    ) -> None:
        """Cómo se ve el plano (0087). Presentación: no toca geometría ni cantidades."""
        await self._sesion.execute(
            text(
                """
                update plano
                   set rotacion_grados   = :rot,
                       volteo_horizontal = :vh,
                       volteo_vertical   = :vv
                 where id = :id
                """
            ),
            {
                "id": str(plano_id),
                "rot": rotacion_grados,
                "vh": volteo_horizontal,
                "vv": volteo_vertical,
            },
        )

    async def listar_de_obra(self, obra_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select p.id, p.obra_id, p.nombre, p.archivo_url, p.version,
                           p.capas, p.subido_por, p.created_at,
                           p.escala_m_por_unidad, p.escala_referencia,
                           p.escala_calibrada_en,
                           p.rotacion_grados, p.volteo_horizontal, p.volteo_vertical,
                           count(t.id) as n_trazos,
                           -- Trazados sobre una versión anterior del plano:
                           -- quedan marcados para revisión, no se recalculan
                           -- solos (MODELO.md §1b, "Si el plano cambia").
                           count(t.id) filter (
                               where t.version_plano < p.version
                           ) as n_trazos_por_revisar
                      from plano p
                      left join trazo t on t.plano_id = p.id and t.hueco_de is null
                     where p.obra_id = :obra_id
                     group by p.id
                     order by p.nombre, p.version desc, p.created_at
                    """
                ),
                {"obra_id": str(obra_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]


class RepositorioTrazosSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def crear(
        self,
        *,
        plano_id: UUID,
        version_plano: int,
        capa: str | None,
        geometria_wkt: str,
        fuente: str,
        autor_id: UUID,
        grosor_m: Decimal | None = None,
        alineacion: str | None = None,
        forma: dict[str, Any] | None = None,
        pendiente_pct: Decimal | None = None,
    ) -> UUID:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    insert into trazo
                        (org_id, plano_id, version_plano, capa, geometria,
                         fuente, autor_id, grosor_m, alineacion, forma, pendiente_pct)
                    values
                        (cast(current_setting('app.org_id') as uuid),
                         :plano_id, :version_plano, :capa,
                         -- WKT de captura -> geometría nativa de un solo
                         -- golpe (MODELO.md §1b, Decisión 3 de 3); SRID 0,
                         -- coordenadas de plano, no geográficas.
                         ST_GeomFromText(:geometria_wkt, 0),
                         cast(:fuente as fuente_trazo), :autor_id,
                         :grosor_m, :alineacion, cast(:forma as jsonb), :pendiente_pct)
                    returning id
                    """
                ),
                {
                    "plano_id": str(plano_id),
                    "version_plano": version_plano,
                    "capa": capa,
                    "geometria_wkt": geometria_wkt,
                    "fuente": fuente,
                    "autor_id": str(autor_id),
                    "grosor_m": grosor_m,
                    "alineacion": alineacion,
                    "forma": json.dumps(forma) if forma is not None else None,
                    "pendiente_pct": pendiente_pct,
                },
            )
        ).scalar_one()
        return fila

    async def tipo_de_geometria(self, geometria_wkt: str) -> str:
        """`ST_GeometryType` del WKT (`ST_Polygon`, `ST_LineString`, `ST_Point`...)."""
        return str(
            (
                await self._sesion.execute(
                    text("select ST_GeometryType(ST_GeomFromText(:wkt, 0))"),
                    {"wkt": geometria_wkt},
                )
            ).scalar_one()
        )

    async def motivo_de_hueco_invalido(self, trazo_id: UUID, geometria_wkt: str) -> str | None:
        """Por qué ese WKT no puede ser un hueco del trazo, o `None` si puede: el padre
        tiene que ser un área (y no ser él mismo un hueco) y el hueco tiene que quedar
        completamente dentro de lo que queda del padre."""
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select ST_GeometryType(t.geometria) as tipo,
                           t.hueco_de is not null as es_hueco,
                           ST_GeometryType(h.g) as tipo_hueco,
                           ST_Within(h.g, app.geometria_efectiva(t.id, t.geometria)) as dentro
                      from trazo t,
                           (select ST_GeomFromText(:wkt, 0) as g) h
                     where t.id = :id
                    """
                ),
                {"id": str(trazo_id), "wkt": geometria_wkt},
            )
        ).mappings().first()
        if fila is None:
            return "El trazo no existe o está fuera de tu alcance."
        if fila["es_hueco"] or fila["tipo"] not in ("ST_Polygon", "ST_MultiPolygon"):
            return "Solo un área (polígono) admite huecos."
        if fila["tipo_hueco"] != "ST_Polygon":
            return "El hueco tiene que ser un polígono."
        if not fila["dentro"]:
            return "El hueco tiene que quedar dentro del área, sin salirse ni cubrir otro hueco."
        return None

    async def eliminar(self, trazo_id: UUID) -> None:
        """Borra el trazo; sus enlaces y sus huecos se van con él (`on delete cascade`)."""
        await self._sesion.execute(text("delete from trazo where id = :id"), {"id": str(trazo_id)})

    async def crear_hueco(
        self, *, trazo_id: UUID, geometria_wkt: str, autor_id: UUID
    ) -> UUID:
        """El hueco es un trazo hijo del área, de la misma versión de plano y sin enlaces."""
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into trazo
                        (org_id, plano_id, version_plano, capa, geometria,
                         fuente, autor_id, hueco_de)
                    select t.org_id, t.plano_id, t.version_plano, t.capa,
                           ST_GeomFromText(:wkt, 0), t.fuente, :autor_id, t.id
                      from trazo t
                     where t.id = :id
                    returning id
                    """
                ),
                {"id": str(trazo_id), "wkt": geometria_wkt, "autor_id": str(autor_id)},
            )
        ).scalar_one()

    async def motivo_de_geometria_invalida(self, geometria_wkt: str) -> str | None:
        """Por qué el WKT no sirve para medir, o `None` si sirve.

        Dos cosas distintas pasan por aquí: un texto que ni siquiera es WKT
        (PostGIS lo rechaza al leerlo) y una geometría bien formada pero
        **inválida**, como un polígono cuyos bordes se cruzan. La segunda es la
        peligrosa: PostGIS la acepta y `ST_Area` devuelve 0 en silencio, así que
        el trazo sumaría cero a la cantidad sin que nadie lo notara.

        El `SAVEPOINT` (`begin_nested`) es lo que permite probar un WKT roto sin
        abortar la transacción de quien llama.
        """
        try:
            async with self._sesion.begin_nested():
                fila = (
                    await self._sesion.execute(
                        text(
                            """
                            select ST_IsValid(g) as valida,
                                   ST_IsValidReason(g) as motivo,
                                   ST_IsEmpty(g) as vacia
                              from (select ST_GeomFromText(:wkt, 0) as g) s
                            """
                        ),
                        {"wkt": geometria_wkt},
                    )
                ).one()
        except DBAPIError:
            return "No es una geometría WKT válida (revisa que tenga los puntos que su forma exige)."
        if fila.vacia:
            return "La geometría está vacía."
        if not fila.valida:
            return f"La geometría es inválida: {fila.motivo}."
        return None

    async def obtener(self, trazo_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select id, plano_id, version_plano, autor_id,
                           aprobado_por, aprobado_en, hueco_de
                      from trazo
                     where id = :id
                    """
                ),
                {"id": str(trazo_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def crear_propuesta(
        self,
        *,
        plano_id: UUID,
        version_plano: int,
        geometria_wkt: str,
        autor_id: UUID,
        origen: str,
        actividad_id: UUID,
        medida: str,
        confianza: Decimal | None,
    ) -> UUID:
        """Un trazo propuesto por una herramienta automática: sin enlaces, no suma nada."""
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into trazo
                        (org_id, plano_id, version_plano, geometria, fuente, autor_id,
                         propuesta, propuesta_origen, propuesta_actividad_id, propuesta_medida,
                         propuesta_confianza)
                    values
                        (cast(current_setting('app.org_id') as uuid), :plano, :version,
                         ST_GeomFromText(:wkt, 0), cast('pdf' as fuente_trazo), :autor,
                         true, :origen, :actividad, :medida, :confianza)
                    returning id
                    """
                ),
                {
                    "plano": str(plano_id),
                    "version": version_plano,
                    "wkt": geometria_wkt,
                    "autor": str(autor_id),
                    "origen": origen,
                    "actividad": str(actividad_id),
                    "medida": medida,
                    "confianza": confianza,
                },
            )
        ).scalar_one()

    async def propuestas(self, plano_id: UUID, trazo_ids: list[UUID]) -> list[dict[str, Any]]:
        """Las propuestas pendientes de esos trazos (los que no lo son no vuelven)."""
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select id, plano_id, propuesta_actividad_id as actividad_id,
                           propuesta_medida as medida, propuesta_origen as origen
                      from trazo
                     where plano_id = :plano and propuesta and id = any(cast(:ids as uuid[]))
                    """
                ),
                {"plano": str(plano_id), "ids": [str(i) for i in trazo_ids]},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def aceptar_propuesta(self, trazo_id: UUID) -> None:
        await self._sesion.execute(text("update trazo set propuesta = false where id = :id"), {"id": str(trazo_id)})

    async def para_traer(self, trazo_id: UUID) -> dict[str, Any] | None:
        """Todo lo que hace falta para dibujar el mismo trazo en otra versión del plano."""
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select t.id, t.plano_id, t.hueco_de, t.capa, t.fuente::text as fuente,
                           t.grosor_m, t.alineacion, t.forma, t.pendiente_pct,
                           ST_AsText(t.geometria) as geometria_wkt
                      from trazo t
                     where t.id = :id
                    """
                ),
                {"id": str(trazo_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def huecos_de(self, trazo_id: UUID) -> list[str]:
        """Los huecos de un trazo, cada uno como WKT."""
        filas = (
            await self._sesion.execute(
                text("select ST_AsText(geometria) from trazo where hueco_de = :id order by created_at, id"),
                {"id": str(trazo_id)},
            )
        ).scalars().all()
        return list(filas)

    async def trasladar(self, geometria_wkt: str, dx: Decimal, dy: Decimal) -> str:
        """El mismo WKT corrido (dx, dy) unidades de plano: el alineado de una versión con otra."""
        return (
            await self._sesion.execute(
                text("select ST_AsText(ST_Translate(ST_GeomFromText(:wkt, 0), :dx, :dy))"),
                {"wkt": geometria_wkt, "dx": float(dx), "dy": float(dy)},
            )
        ).scalar_one()

    async def aprobar(self, *, trazo_id: UUID, aprobador_id: UUID) -> bool:
        # `aprobado_por is null`: la primera aprobación manda y no se pisa.
        resultado = await self._sesion.execute(
            text(
                """
                update trazo
                   set aprobado_por = :aprobador_id, aprobado_en = now()
                 where id = :id and aprobado_por is null
                """
            ),
            {"id": str(trazo_id), "aprobador_id": str(aprobador_id)},
        )
        return resultado.rowcount == 1

    async def de_plano(self, plano_id: UUID) -> list[dict[str, Any]]:
        """Los trazos de un plano con sus enlaces, en dos consultas.

        `ST_AsGeoJSON(geometria, 9, 0)`: sin la propiedad `crs` (opción 0) —
        las coordenadas son **de plano**, SRID 0, no lon/lat (MODELO.md §1b,
        "Coordenadas de plano, no geográficas"); un `crs` inventado haría
        creer a un visor que son geográficas.
        """
        trazos = (
            await self._sesion.execute(
                text(
                    """
                    select t.id, t.version_plano, t.capa, t.fuente, t.autor_id,
                           t.aprobado_por, t.aprobado_en, t.created_at,
                           t.grosor_m, t.alineacion, t.forma, t.pendiente_pct, t.medicion_id,
                           t.propuesta, t.propuesta_origen, t.propuesta_actividad_id,
                           t.propuesta_medida, t.propuesta_confianza,
                           (select count(*) from trazo h where h.hueco_de = t.id) as n_huecos,
                           (t.version_plano < p.version) as por_revisar,
                           -- La geometría que se dibuja y se mide es la efectiva: con sus huecos.
                           ST_AsGeoJSON(app.geometria_efectiva(t.id, t.geometria), 9, 0) as geojson
                      from trazo t
                      join plano p on p.id = t.plano_id
                     where t.plano_id = :plano_id and t.hueco_de is null
                     order by t.created_at, t.id
                    """
                ),
                {"plano_id": str(plano_id)},
            )
        ).mappings().all()

        enlaces = (
            await self._sesion.execute(
                text(
                    f"""
                    select e.id, e.trazo_id, e.tipo_nodo, e.actividad_id,
                           e.prototipo_nodo_id, e.matriz_concepto_id, e.medida, e.factor,
                           e.vigente, {_MEDIDA_VALOR_SQL} as medida_valor
                      from enlace_cuantificacion e
                      join trazo t on t.id = e.trazo_id
                      join plano p on p.id = t.plano_id
                     where t.plano_id = :plano_id
                     order by e.created_at, e.id
                    """
                ),
                {"plano_id": str(plano_id)},
            )
        ).mappings().all()

        por_trazo: dict[Any, list[dict[str, Any]]] = {}
        for enlace in enlaces:
            por_trazo.setdefault(enlace["trazo_id"], []).append(dict(enlace))

        return [
            {
                **{k: v for k, v in trazo.items() if k != "geojson"},
                "geometria": json.loads(trazo["geojson"]),
                "enlaces": por_trazo.get(trazo["id"], []),
            }
            for trazo in trazos
        ]


class RepositorioEnlacesCuantificacionSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def crear(
        self,
        *,
        trazo_id: UUID,
        actividad_id: UUID | None,
        prototipo_nodo_id: UUID | None,
        medida: str,
        factor: Decimal,
        vigente: bool = True,
        matriz_concepto_id: UUID | None = None,
        asignacion_id: UUID | None = None,
    ) -> UUID:
        """`tipo_nodo` no se pide: se deriva de cuál de
        `actividad_id`/`prototipo_nodo_id` llegó lleno, igual que
        `desviaciones_sql.RepositorioDesviacionesSQL.crear` deriva
        `tipo_nodo` de `insumo_id`/`concepto_id` — así no puede llegar un
        `tipo_nodo` que contradiga a los ids que sí se escriben."""
        tipo_nodo = "actividad" if actividad_id else "prototipo_nodo"
        fila = (
            await self._sesion.execute(
                text(
                    """
                    insert into enlace_cuantificacion
                        (org_id, trazo_id, tipo_nodo, actividad_id,
                         prototipo_nodo_id, medida, factor, vigente, matriz_concepto_id,
                         asignacion_id)
                    values
                        (cast(current_setting('app.org_id') as uuid),
                         :trazo_id, cast(:tipo_nodo as tipo_nodo_cuantificacion),
                         cast(:actividad_id as uuid),
                         cast(:prototipo_nodo_id as uuid),
                         cast(:medida as medida_cuantificacion),
                         :factor, :vigente, cast(:matriz_concepto_id as uuid),
                         cast(:asignacion_id as uuid))
                    returning id
                    """
                ),
                {
                    "trazo_id": str(trazo_id),
                    "tipo_nodo": tipo_nodo,
                    "actividad_id": str(actividad_id) if actividad_id else None,
                    "prototipo_nodo_id": (
                        str(prototipo_nodo_id) if prototipo_nodo_id else None
                    ),
                    "medida": medida,
                    "factor": factor,
                    "vigente": vigente,
                    "matriz_concepto_id": str(matriz_concepto_id) if matriz_concepto_id else None,
                    "asignacion_id": str(asignacion_id) if asignacion_id else None,
                },
            )
        ).scalar_one()
        return fila

    async def obtener(self, enlace_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select id, trazo_id, tipo_nodo, actividad_id,
                           prototipo_nodo_id, matriz_concepto_id, medida, factor, vigente,
                           created_at
                      from enlace_cuantificacion
                     where id = :id
                    """
                ),
                {"id": str(enlace_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def marcar_no_vigente(self, enlace_id: UUID) -> None:
        await self._sesion.execute(
            text("update enlace_cuantificacion set vigente = false where id = :id"),
            {"id": str(enlace_id)},
        )

    async def enlaces_de_nodo(
        self,
        *,
        tipo_nodo: str,
        actividad_id: UUID | None,
        prototipo_nodo_id: UUID | None,
        matriz_concepto_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select e.id, e.vigente, e.factor,
                           {_MEDIDA_VALOR_SQL} as medida_valor
                      from enlace_cuantificacion e
                      join trazo t on t.id = e.trazo_id
                      join plano p on p.id = t.plano_id
                     where e.tipo_nodo = cast(:tipo_nodo as tipo_nodo_cuantificacion)
                       and (
                            (cast(:actividad_id as uuid) is not null
                             and e.actividad_id = cast(:actividad_id as uuid))
                         or (cast(:prototipo_nodo_id as uuid) is not null
                             and e.prototipo_nodo_id = cast(:prototipo_nodo_id as uuid))
                       )
                       -- La actividad entera no suma sus matrices internas, ni al revés.
                       and e.matriz_concepto_id is not distinct from cast(:matriz_concepto_id as uuid)
                    """
                ),
                {
                    "matriz_concepto_id": str(matriz_concepto_id) if matriz_concepto_id else None,
                    "tipo_nodo": tipo_nodo,
                    "actividad_id": str(actividad_id) if actividad_id else None,
                    "prototipo_nodo_id": (
                        str(prototipo_nodo_id) if prototipo_nodo_id else None
                    ),
                },
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def nodos_vigentes_de_plano(self, plano_id: UUID) -> list[dict[str, Any]]:
        """Los nodos distintos a los que enlazan, vigentes, los trazos de un
        plano: lo que hay que recalcular cuando cambia su escala."""
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select distinct e.tipo_nodo, e.actividad_id, e.prototipo_nodo_id,
                                    e.matriz_concepto_id
                      from enlace_cuantificacion e
                      join trazo t on t.id = e.trazo_id
                     where t.plano_id = :plano_id and e.vigente
                     order by e.tipo_nodo, e.actividad_id, e.prototipo_nodo_id,
                              e.matriz_concepto_id
                    """
                ),
                {"plano_id": str(plano_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def vigentes_de_trazo(self, trazo_id: UUID) -> list[dict[str, Any]]:
        """Los enlaces vigentes de un trazo, uno por uno (a diferencia de los nodos distintos)."""
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select e.id, e.tipo_nodo, e.actividad_id, e.prototipo_nodo_id,
                           e.matriz_concepto_id, e.medida, e.factor
                      from enlace_cuantificacion e
                     where e.trazo_id = :trazo_id and e.vigente
                     order by e.created_at, e.id
                    """
                ),
                {"trazo_id": str(trazo_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def nodos_vigentes_de_trazo(self, trazo_id: UUID) -> list[dict[str, Any]]:
        """Los nodos distintos a los que enlaza, vigentes, un trazo: lo que hay que
        recalcular cuando cambia lo que ese trazo mide (le abren un hueco)."""
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select distinct e.tipo_nodo, e.actividad_id, e.prototipo_nodo_id,
                                    e.matriz_concepto_id
                      from enlace_cuantificacion e
                     where e.trazo_id = :trazo_id and e.vigente
                     order by e.tipo_nodo, e.actividad_id, e.prototipo_nodo_id,
                              e.matriz_concepto_id
                    """
                ),
                {"trazo_id": str(trazo_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def de_obra(self, obra_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select e.id, e.tipo_nodo, e.actividad_id,
                           e.prototipo_nodo_id, e.matriz_concepto_id, e.medida, e.factor, e.vigente,
                           {_MEDIDA_VALOR_SQL} as medida_valor,
                           (t.version_plano < p.version) as por_revisar,
                           coalesce(a.descripcion, pn.nombre) as descripcion,
                           coalesce(a.cant_base, pn.cantidad) as cant_base
                      from enlace_cuantificacion e
                      join trazo t on t.id = e.trazo_id
                      join plano p on p.id = t.plano_id
                      left join actividad a on a.id = e.actividad_id
                      left join prototipo_nodo pn on pn.id = e.prototipo_nodo_id
                     where p.obra_id = :obra_id
                     order by e.created_at, e.id
                    """
                ),
                {"obra_id": str(obra_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]


class RepositorioNotasPlanoSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def crear(
        self,
        *,
        plano_id: UUID,
        version_plano: int,
        ubicacion_wkt: str,
        autor_id: UUID,
        texto: str,
        actividad_id: UUID | None,
        tipo: str = "nota",
        destino_wkt: str | None = None,
    ) -> UUID:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    insert into nota_plano
                        (org_id, plano_id, version_plano, ubicacion,
                         autor_id, texto, actividad_id, tipo, destino)
                    values
                        (cast(current_setting('app.org_id') as uuid),
                         :plano_id, :version_plano,
                         ST_GeomFromText(:ubicacion_wkt, 0),
                         :autor_id, :texto, cast(:actividad_id as uuid), :tipo,
                         case when cast(:destino_wkt as text) is null then null
                              else ST_GeomFromText(:destino_wkt, 0) end)
                    returning id
                    """
                ),
                {
                    "plano_id": str(plano_id),
                    "version_plano": version_plano,
                    "ubicacion_wkt": ubicacion_wkt,
                    "autor_id": str(autor_id),
                    "texto": texto,
                    "actividad_id": str(actividad_id) if actividad_id else None,
                    "tipo": tipo,
                    "destino_wkt": destino_wkt,
                },
            )
        ).scalar_one()
        return fila

    async def de_plano(self, plano_id: UUID) -> list[dict[str, Any]]:
        """Las notas de un plano, la ubicación como GeoJSON de plano (SRID 0,
        sin `crs`: mismo criterio que los trazos)."""
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select n.id, n.version_plano, n.autor_id, n.texto,
                           n.actividad_id, n.created_at, n.tipo,
                           (n.version_plano < p.version) as por_revisar,
                           ST_AsGeoJSON(n.ubicacion, 9, 0) as geojson,
                           ST_AsGeoJSON(n.destino, 9, 0) as geojson_destino
                      from nota_plano n
                      join plano p on p.id = n.plano_id
                     where n.plano_id = :plano_id
                     order by n.created_at, n.id
                    """
                ),
                {"plano_id": str(plano_id)},
            )
        ).mappings().all()
        return [
            {
                **{k: v for k, v in fila.items() if k not in ("geojson", "geojson_destino")},
                "ubicacion": json.loads(fila["geojson"]),
                "destino": json.loads(fila["geojson_destino"]) if fila["geojson_destino"] else None,
            }
            for fila in filas
        ]


class RepositorioMatricesSQL:
    """Las matrices internas de una actividad y su cantidad medida (migración 0085, D-583)."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def fijar_cantidad(
        self, *, actividad_id: UUID, concepto_id: UUID, cantidad: Decimal | None
    ) -> None:
        if cantidad is None:
            await self._sesion.execute(
                text("delete from actividad_matriz where actividad_id = :a and concepto_id = :c"),
                {"a": str(actividad_id), "c": str(concepto_id)},
            )
            return
        await self._sesion.execute(
            text(
                """
                insert into actividad_matriz (org_id, obra_id, actividad_id, concepto_id, cantidad_medida)
                select a.org_id, a.obra_id, a.id, cast(:concepto as uuid), :cantidad
                  from actividad a where a.id = :actividad
                on conflict (actividad_id, concepto_id) do update
                   set cantidad_medida = excluded.cantidad_medida, actualizada_en = now()
                """
            ),
            {"actividad": str(actividad_id), "concepto": str(concepto_id), "cantidad": cantidad},
        )

    async def arbol_de_actividad(self, actividad_id: UUID) -> dict[str, Any] | None:
        act = (
            await self._sesion.execute(
                text(
                    """
                    select a.id, a.concepto_id, a.cant_base, a.precio_unitario, c.clave as concepto_clave,
                           coalesce(a.descripcion, c.descripcion, '') as descripcion
                      from actividad a left join concepto c on c.id = a.concepto_id
                     where a.id = :id
                    """
                ),
                {"id": str(actividad_id)},
            )
        ).mappings().first()
        if act is None:
            return None
        matrices: list[dict[str, Any]] = []
        if act["concepto_id"] is not None:
            filas = (
                await self._sesion.execute(
                    text(
                        """
                        with recursive arbol as (
                            select e.concepto_hijo_id as concepto_id, e.concepto_id as padre_id,
                                   1 as nivel, e.cantidad::numeric as unitaria, e.cantidad::numeric as acumulada,
                                   array[e.concepto_id, e.concepto_hijo_id] as ruta, e.orden
                              from explosion e
                             where e.concepto_id = :raiz and e.tipo_hijo = 'concepto'
                               and (e.cpu_id is null
                                    or exists (select 1 from cpu k where k.id = e.cpu_id and k.vigente))
                            union all
                            select e.concepto_hijo_id, e.concepto_id, ar.nivel + 1, e.cantidad::numeric,
                                   ar.acumulada * e.cantidad, ar.ruta || e.concepto_hijo_id, e.orden
                              from arbol ar
                              join explosion e on e.concepto_id = ar.concepto_id
                             where e.tipo_hijo = 'concepto' and ar.nivel < 8
                               and not e.concepto_hijo_id = any(ar.ruta)
                               and (e.cpu_id is null
                                    or exists (select 1 from cpu k where k.id = e.cpu_id and k.vigente))
                        )
                        select ar.concepto_id, ar.padre_id, ar.nivel, ar.unitaria, ar.acumulada,
                               ar.ruta, c.clave, c.descripcion, u.clave as unidad,
                               coalesce((select k.precio_unitario from cpu k
                                          where k.concepto_id = ar.concepto_id and k.vigente
                                          order by k.version desc limit 1), 0) as precio_unitario,
                               m.cantidad_medida
                          from arbol ar
                          join concepto c on c.id = ar.concepto_id
                          left join unidad u on u.id = c.unidad_id
                          left join actividad_matriz m
                                 on m.actividad_id = :actividad and m.concepto_id = ar.concepto_id
                         order by ar.ruta, ar.orden
                        """
                    ),
                    {"raiz": str(act["concepto_id"]), "actividad": str(actividad_id)},
                )
            ).mappings().all()
            matrices = [dict(f) for f in filas]
        return {**dict(act), "matrices": matrices}


_CERO = "'00000000-0000-0000-0000-000000000000'::uuid"


class RepositorioMedicionesSQL:
    """`medicion` y `medicion_asignacion` (migración 0088)."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def crear(
        self, *, plano_id: UUID, nombre: str, tipo: str, parent_id: UUID | None, autor_id: UUID
    ) -> UUID:
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into medicion (org_id, plano_id, parent_id, nombre, tipo, autor_id, orden)
                    values (cast(current_setting('app.org_id') as uuid), :plano, :parent, :nombre, :tipo,
                            :autor,
                            coalesce((select max(orden) + 1 from medicion
                                       where plano_id = :plano
                                         and parent_id is not distinct from cast(:parent as uuid)), 0))
                    returning id
                    """
                ),
                {
                    "plano": str(plano_id),
                    "parent": str(parent_id) if parent_id else None,
                    "nombre": nombre,
                    "tipo": tipo,
                    "autor": str(autor_id),
                },
            )
        ).scalar_one()

    async def obtener(self, medicion_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text("select id, plano_id, parent_id, nombre, tipo, elemento_id from medicion where id = :id"),
                {"id": str(medicion_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def existe_hermana(
        self, *, plano_id: UUID, parent_id: UUID | None, nombre: str, excepto: UUID | None = None
    ) -> bool:
        return bool(
            (
                await self._sesion.execute(
                    text(
                        """
                        select exists (
                          select 1 from medicion
                           where plano_id = :plano
                             and parent_id is not distinct from cast(:parent as uuid)
                             and lower(btrim(nombre)) = lower(btrim(:nombre))
                             and (cast(:excepto as uuid) is null or id <> cast(:excepto as uuid)))
                        """
                    ),
                    {
                        "plano": str(plano_id),
                        "parent": str(parent_id) if parent_id else None,
                        "nombre": nombre,
                        "excepto": str(excepto) if excepto else None,
                    },
                )
            ).scalar_one()
        )

    async def renombrar(self, medicion_id: UUID, nombre: str) -> None:
        await self._sesion.execute(
            text("update medicion set nombre = :nombre where id = :id"),
            {"id": str(medicion_id), "nombre": nombre},
        )

    async def eliminar(self, medicion_id: UUID) -> None:
        await self._sesion.execute(text("delete from medicion where id = :id"), {"id": str(medicion_id)})

    async def dependencias(self, medicion_id: UUID) -> dict[str, int]:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select (select count(*) from medicion where parent_id = :id) as hijas,
                           (select count(*) from medicion_asignacion where medicion_id = :id) as asignaciones
                    """
                ),
                {"id": str(medicion_id)},
            )
        ).mappings().one()
        return {"hijas": int(fila["hijas"]), "asignaciones": int(fila["asignaciones"])}

    async def con_ancestros(self, medicion_id: UUID) -> list[UUID]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    with recursive arriba as (
                      select id, parent_id, 0 as dist from medicion where id = :id
                      union all
                      select m.id, m.parent_id, a.dist + 1
                        from medicion m join arriba a on m.id = a.parent_id
                       where a.dist < 20)
                    select id from arriba order by dist
                    """
                ),
                {"id": str(medicion_id)},
            )
        ).scalars().all()
        return list(filas)

    async def con_descendientes(self, medicion_id: UUID) -> list[UUID]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    with recursive abajo as (
                      select id, 0 as dist from medicion where id = :id
                      union all
                      select m.id, a.dist + 1 from medicion m join abajo a on m.parent_id = a.id
                       where a.dist < 20)
                    select id from abajo order by dist
                    """
                ),
                {"id": str(medicion_id)},
            )
        ).scalars().all()
        return list(filas)

    async def info_de_trazo(self, trazo_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select t.plano_id, ST_GeometryType(t.geometria) as geometria,
                           (t.forma is not null) as tiene_forma, t.medicion_id, t.hueco_de
                      from trazo t where t.id = :id
                    """
                ),
                {"id": str(trazo_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def poner_trazo(self, trazo_id: UUID, medicion_id: UUID | None) -> None:
        await self._sesion.execute(
            text("update trazo set medicion_id = cast(:m as uuid) where id = :id"),
            {"id": str(trazo_id), "m": str(medicion_id) if medicion_id else None},
        )

    async def trazos_de(self, medicion_ids: list[UUID]) -> list[UUID]:
        filas = (
            await self._sesion.execute(
                text("select id from trazo where medicion_id = any(:ids) and hueco_de is null order by created_at, id"),
                {"ids": list(medicion_ids)},
            )
        ).scalars().all()
        return list(filas)

    async def asignaciones_de(self, medicion_ids: list[UUID]) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select id, medicion_id, actividad_id, matriz_concepto_id, medida::text as medida, factor, usa_peso
                      from medicion_asignacion where medicion_id = any(:ids) order by created_at, id
                    """
                ),
                {"ids": list(medicion_ids)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def crear_asignacion(
        self,
        *,
        medicion_id: UUID,
        actividad_id: UUID,
        matriz_concepto_id: UUID | None,
        medida: str,
        factor: Decimal,
        autor_id: UUID,
        usa_peso: bool = False,
    ) -> UUID:
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into medicion_asignacion
                        (org_id, medicion_id, actividad_id, matriz_concepto_id, medida, factor, autor_id, usa_peso)
                    values (cast(current_setting('app.org_id') as uuid), :medicion, :actividad,
                            cast(:matriz as uuid), cast(:medida as medida_cuantificacion), :factor, :autor, :usa_peso)
                    returning id
                    """
                ),
                {
                    "medicion": str(medicion_id),
                    "actividad": str(actividad_id),
                    "matriz": str(matriz_concepto_id) if matriz_concepto_id else None,
                    "medida": medida,
                    "factor": factor,
                    "autor": str(autor_id),
                    "usa_peso": usa_peso,
                },
            )
        ).scalar_one()

    async def obtener_asignacion(self, asignacion_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select id, medicion_id, actividad_id, matriz_concepto_id, medida::text as medida, factor, usa_peso
                      from medicion_asignacion where id = :id
                    """
                ),
                {"id": str(asignacion_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def eliminar_asignacion(self, asignacion_id: UUID) -> None:
        await self._sesion.execute(
            text("delete from medicion_asignacion where id = :id"), {"id": str(asignacion_id)}
        )

    async def poner_elemento(self, medicion_id: UUID, elemento_id: UUID | None) -> None:
        await self._sesion.execute(
            text("update medicion set elemento_id = cast(:e as uuid) where id = :id"),
            {"id": str(medicion_id), "e": str(elemento_id) if elemento_id else None},
        )

    async def unidad_de_actividad(self, actividad_id: UUID) -> str | None:
        return (
            await self._sesion.execute(
                text(
                    """
                    select u.clave from actividad a
                      left join concepto c on c.id = a.concepto_id
                      left join unidad u on u.id = c.unidad_id
                     where a.id = :id
                    """
                ),
                {"id": str(actividad_id)},
            )
        ).scalar_one_or_none()

    async def asignaciones_con_peso(self, elemento_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select a.id, a.medicion_id, a.actividad_id, a.matriz_concepto_id,
                           a.medida::text as medida, a.factor, u.clave as unidad
                      from medicion_asignacion a
                      join medicion m on m.id = a.medicion_id
                      join actividad act on act.id = a.actividad_id
                      left join concepto c on c.id = act.concepto_id
                      left join unidad u on u.id = c.unidad_id
                     where m.elemento_id = :e and a.usa_peso
                     order by a.created_at, a.id
                    """
                ),
                {"e": str(elemento_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def fijar_factor_asignacion(self, asignacion_id: UUID, factor: Decimal) -> None:
        await self._sesion.execute(
            text("update medicion_asignacion set factor = :f where id = :id"),
            {"id": str(asignacion_id), "f": factor},
        )

    async def enlaces_de_asignacion(self, asignacion_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text("select id, trazo_id from enlace_cuantificacion where asignacion_id = :id and vigente"),
                {"id": str(asignacion_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def asignacion_equivalente(
        self,
        *,
        medicion_ids: list[UUID],
        actividad_id: UUID,
        matriz_concepto_id: UUID | None,
        medida: str,
    ) -> bool:
        return bool(
            (
                await self._sesion.execute(
                    text(
                        f"""
                        select exists (
                          select 1 from medicion_asignacion
                           where medicion_id = any(:ids) and actividad_id = :actividad
                             and coalesce(matriz_concepto_id, {_CERO}) = coalesce(cast(:matriz as uuid), {_CERO})
                             and medida = cast(:medida as medida_cuantificacion))
                        """
                    ),
                    {
                        "ids": list(medicion_ids),
                        "actividad": str(actividad_id),
                        "matriz": str(matriz_concepto_id) if matriz_concepto_id else None,
                        "medida": medida,
                    },
                )
            ).scalar_one()
        )

    async def enlace_vigente_equivalente(
        self,
        *,
        trazo_id: UUID,
        actividad_id: UUID,
        matriz_concepto_id: UUID | None,
        medida: str,
    ) -> bool:
        return bool(
            (
                await self._sesion.execute(
                    text(
                        f"""
                        select exists (
                          select 1 from enlace_cuantificacion
                           where trazo_id = :trazo and vigente and actividad_id = :actividad
                             and coalesce(matriz_concepto_id, {_CERO}) = coalesce(cast(:matriz as uuid), {_CERO})
                             and medida = cast(:medida as medida_cuantificacion))
                        """
                    ),
                    {
                        "trazo": str(trazo_id),
                        "actividad": str(actividad_id),
                        "matriz": str(matriz_concepto_id) if matriz_concepto_id else None,
                        "medida": medida,
                    },
                )
            ).scalar_one()
        )

    async def actividad_de_la_obra(self, actividad_id: UUID, plano_id: UUID) -> bool:
        return bool(
            (
                await self._sesion.execute(
                    text(
                        """
                        select exists (select 1 from actividad a join plano p on p.obra_id = a.obra_id
                                        where a.id = :actividad and p.id = :plano)
                        """
                    ),
                    {"actividad": str(actividad_id), "plano": str(plano_id)},
                )
            ).scalar_one()
        )

    async def de_plano(self, plano_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    with recursive sub as (
                      select m.id as raiz, m.id from medicion m where m.plano_id = :plano
                      union all
                      select s.raiz, h.id from sub s join medicion h on h.parent_id = s.id
                    )
                    select m.id, m.parent_id, m.nombre, m.tipo, m.orden,
                           e.id as elemento_id, e.nombre as elemento_nombre, e.peso_kg as elemento_peso_kg,
                           count(t.id) as n_trazos,
                           coalesce(sum(
                             case m.tipo
                               when 'area' then ST_Area(app.geometria_efectiva(t.id, t.geometria))
                                                * power(coalesce(p.escala_m_por_unidad, 1), 2)
                               when 'lineal' then ST_Length(app.geometria_efectiva(t.id, t.geometria))
                                                  * coalesce(p.escala_m_por_unidad, 1)
                                                  * sqrt(1 + power(coalesce(t.pendiente_pct, 0) / 100.0, 2))
                               else 1
                             end), 0) as valor
                      from medicion m
                      join plano p on p.id = m.plano_id
                      left join elemento e on e.id = m.elemento_id
                      left join sub s on s.raiz = m.id
                      left join trazo t on t.medicion_id = s.id and t.hueco_de is null
                     where m.plano_id = :plano
                     group by m.id, p.escala_m_por_unidad, e.id
                     order by m.orden, m.created_at, m.id
                    """
                ),
                {"plano": str(plano_id)},
            )
        ).mappings().all()
        asignaciones = (
            await self._sesion.execute(
                text(
                    """
                    select a.id, a.medicion_id, a.actividad_id, a.matriz_concepto_id,
                           a.medida::text as medida, a.factor, a.usa_peso,
                           coalesce(c.clave, '') as concepto_clave,
                           coalesce(act.descripcion, c.descripcion, '') as descripcion,
                           mc.clave as matriz_clave
                      from medicion_asignacion a
                      join medicion m on m.id = a.medicion_id
                      join actividad act on act.id = a.actividad_id
                      left join concepto c on c.id = act.concepto_id
                      left join concepto mc on mc.id = a.matriz_concepto_id
                     where m.plano_id = :plano
                     order by a.created_at, a.id
                    """
                ),
                {"plano": str(plano_id)},
            )
        ).mappings().all()
        por_medicion: dict[Any, list[dict[str, Any]]] = {}
        for a in asignaciones:
            por_medicion.setdefault(a["medicion_id"], []).append(dict(a))
        return [{**dict(f), "asignaciones": por_medicion.get(f["id"], [])} for f in filas]


class RepositorioElementosSQL:
    """`elemento` (migración 0089): elementos de obra con peso, catálogo de la organización."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def crear(self, *, nombre: str, tipo: str, peso_kg: Decimal, autor_id: UUID) -> UUID:
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into elemento (org_id, nombre, tipo, peso_kg, autor_id)
                    values (cast(current_setting('app.org_id') as uuid), :nombre, :tipo, :peso, :autor)
                    returning id
                    """
                ),
                {"nombre": nombre, "tipo": tipo, "peso": peso_kg, "autor": str(autor_id)},
            )
        ).scalar_one()

    async def obtener(self, elemento_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text("select id, nombre, tipo, peso_kg from elemento where id = :id"), {"id": str(elemento_id)}
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def listar(self) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select e.id, e.nombre, e.tipo, e.peso_kg,
                           (select count(*) from medicion m where m.elemento_id = e.id) as n_mediciones
                      from elemento e order by lower(e.nombre), e.id
                    """
                )
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def existe_nombre(self, nombre: str, excepto: UUID | None = None) -> bool:
        return bool(
            (
                await self._sesion.execute(
                    text(
                        """
                        select exists (select 1 from elemento
                                        where lower(btrim(nombre)) = lower(btrim(:n))
                                          and (cast(:x as uuid) is null or id <> cast(:x as uuid)))
                        """
                    ),
                    {"n": nombre, "x": str(excepto) if excepto else None},
                )
            ).scalar_one()
        )

    async def actualizar(self, elemento_id: UUID, *, nombre: str | None, peso_kg: Decimal | None) -> None:
        await self._sesion.execute(
            text(
                """
                update elemento set nombre = coalesce(:nombre, nombre), peso_kg = coalesce(:peso, peso_kg)
                 where id = :id
                """
            ),
            {"id": str(elemento_id), "nombre": nombre, "peso": peso_kg},
        )

    async def eliminar(self, elemento_id: UUID) -> None:
        await self._sesion.execute(text("delete from elemento where id = :id"), {"id": str(elemento_id)})

    async def uso(self, elemento_id: UUID) -> dict[str, int]:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select (select count(*) from medicion where elemento_id = :id) as mediciones,
                           (select count(*) from medicion_asignacion a join medicion m on m.id = a.medicion_id
                             where m.elemento_id = :id and a.usa_peso) as asignaciones_con_peso
                    """
                ),
                {"id": str(elemento_id)},
            )
        ).mappings().one()
        return {"mediciones": int(fila["mediciones"]), "asignaciones_con_peso": int(fila["asignaciones_con_peso"])}


class RepositorioEnlacesDeHojaSQL:
    """`plano_enlace` (migración 0091): zonas de una hoja que llevan a otra hoja de la obra."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def crear(
        self,
        *,
        plano_id: UUID,
        destino_plano_id: UUID,
        etiqueta: str,
        x: float,
        y: float,
        ancho: float,
        alto: float,
        autor_id: UUID,
    ) -> UUID:
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into plano_enlace
                        (org_id, plano_id, destino_plano_id, etiqueta, x, y, ancho, alto, autor_id)
                    values (cast(current_setting('app.org_id') as uuid),
                            :plano, :destino, :etiqueta, :x, :y, :ancho, :alto, :autor)
                    returning id
                    """
                ),
                {
                    "plano": str(plano_id),
                    "destino": str(destino_plano_id),
                    "etiqueta": etiqueta,
                    "x": x,
                    "y": y,
                    "ancho": ancho,
                    "alto": alto,
                    "autor": str(autor_id),
                },
            )
        ).scalar_one()

    async def de_plano(self, plano_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select e.id, e.plano_id, e.destino_plano_id, e.etiqueta, e.x, e.y, e.ancho, e.alto,
                           d.nombre as destino_nombre, d.version as destino_version
                      from plano_enlace e
                      join plano d on d.id = e.destino_plano_id
                     where e.plano_id = :plano
                     order by e.created_at, e.id
                    """
                ),
                {"plano": str(plano_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def eliminar(self, enlace_id: UUID) -> bool:
        resultado = await self._sesion.execute(
            text("delete from plano_enlace where id = :id"), {"id": str(enlace_id)}
        )
        return bool(resultado.rowcount)
