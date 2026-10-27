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
_MEDIDA_VALOR_SQL = f"""
    case e.medida
      when 'area'      then ST_Area(t.geometria) * power({_ESCALA_SQL}, 2)
      when 'perimetro'  then ST_Perimeter(t.geometria) * {_ESCALA_SQL}
      when 'longitud'   then ST_Length(t.geometria) * {_ESCALA_SQL}
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
                           escala_referencia, escala_calibrada_en
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

    async def listar_de_obra(self, obra_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select p.id, p.obra_id, p.nombre, p.archivo_url, p.version,
                           p.capas, p.subido_por, p.created_at,
                           p.escala_m_por_unidad, p.escala_referencia,
                           p.escala_calibrada_en,
                           count(t.id) as n_trazos,
                           -- Trazados sobre una versión anterior del plano:
                           -- quedan marcados para revisión, no se recalculan
                           -- solos (MODELO.md §1b, "Si el plano cambia").
                           count(t.id) filter (
                               where t.version_plano < p.version
                           ) as n_trazos_por_revisar
                      from plano p
                      left join trazo t on t.plano_id = p.id
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
    ) -> UUID:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    insert into trazo
                        (org_id, plano_id, version_plano, capa, geometria,
                         fuente, autor_id)
                    values
                        (cast(current_setting('app.org_id') as uuid),
                         :plano_id, :version_plano, :capa,
                         -- WKT de captura -> geometría nativa de un solo
                         -- golpe (MODELO.md §1b, Decisión 3 de 3); SRID 0,
                         -- coordenadas de plano, no geográficas.
                         ST_GeomFromText(:geometria_wkt, 0),
                         cast(:fuente as fuente_trazo), :autor_id)
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
                },
            )
        ).scalar_one()
        return fila

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
                           aprobado_por, aprobado_en
                      from trazo
                     where id = :id
                    """
                ),
                {"id": str(trazo_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

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
                           (t.version_plano < p.version) as por_revisar,
                           ST_AsGeoJSON(t.geometria, 9, 0) as geojson
                      from trazo t
                      join plano p on p.id = t.plano_id
                     where t.plano_id = :plano_id
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
                           e.prototipo_nodo_id, e.medida, e.factor, e.vigente,
                           {_MEDIDA_VALOR_SQL} as medida_valor
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
                         prototipo_nodo_id, medida, factor, vigente)
                    values
                        (cast(current_setting('app.org_id') as uuid),
                         :trazo_id, cast(:tipo_nodo as tipo_nodo_cuantificacion),
                         cast(:actividad_id as uuid),
                         cast(:prototipo_nodo_id as uuid),
                         cast(:medida as medida_cuantificacion),
                         :factor, :vigente)
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
                           prototipo_nodo_id, medida, factor, vigente,
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
                    """
                ),
                {
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
                    select distinct e.tipo_nodo, e.actividad_id, e.prototipo_nodo_id
                      from enlace_cuantificacion e
                      join trazo t on t.id = e.trazo_id
                     where t.plano_id = :plano_id and e.vigente
                     order by e.tipo_nodo, e.actividad_id, e.prototipo_nodo_id
                    """
                ),
                {"plano_id": str(plano_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def de_obra(self, obra_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select e.id, e.tipo_nodo, e.actividad_id,
                           e.prototipo_nodo_id, e.medida, e.factor, e.vigente,
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
    ) -> UUID:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    insert into nota_plano
                        (org_id, plano_id, version_plano, ubicacion,
                         autor_id, texto, actividad_id)
                    values
                        (cast(current_setting('app.org_id') as uuid),
                         :plano_id, :version_plano,
                         ST_GeomFromText(:ubicacion_wkt, 0),
                         :autor_id, :texto, cast(:actividad_id as uuid))
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
                           n.actividad_id, n.created_at,
                           (n.version_plano < p.version) as por_revisar,
                           ST_AsGeoJSON(n.ubicacion, 9, 0) as geojson
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
                **{k: v for k, v in fila.items() if k != "geojson"},
                "ubicacion": json.loads(fila["geojson"]),
            }
            for fila in filas
        ]
