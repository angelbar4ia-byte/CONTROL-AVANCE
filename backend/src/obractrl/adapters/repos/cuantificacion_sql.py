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

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
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
# aplicar, repetida en los dos lugares que necesitan `medida_valor`
# (`_crear` de trazos+enlace en un solo golpe no existe: `enlaces_de_nodo`
# es el único lector real).
_MEDIDA_VALOR_SQL = """
    case e.medida
      when 'area'      then ST_Area(t.geometria)
      when 'perimetro'  then ST_Perimeter(t.geometria)
      when 'longitud'   then ST_Length(t.geometria)
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
                           subido_por, created_at
                      from plano
                     where id = :id
                    """
                ),
                {"id": str(plano_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None


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
