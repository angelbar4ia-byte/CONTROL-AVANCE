"""Repositorio de desviaciones.

Spec §12.11 (adaptador de persistencia) · cerebro MODELO.md §5g ·
CONOCIMIENTO.md §13.6 · §12.4 (RLS).

RLS filtra `desviacion` por alcance de rol: entra con su propia política
`desviacion_scope` (`database/migrations/20260814000054_desviacion.sql`),
mismo predicado que `control_cambio` — ningún método de aquí filtra por
`org_id` u `obra_id` de forma manual para la fila individual, eso lo impone
la base. `org_id` en el INSERT sale de `current_setting('app.org_id')`,
igual que en `incidencias_sql.py`.

Las dos consultas de patrón (`patrones_por_insumo_o_concepto`,
`patrones_por_obra`) SÍ filtran explícito por `obra_id`/`org_id` cuando se
les pasa, porque agregan sobre varias filas a la vez y no hay una sola fila
"propietaria" en la que RLS pueda anclar un `USING` — el aislamiento de la
organización igual lo impone la política de SELECT de la tabla, la cláusula
WHERE solo acota más dentro de lo que la política ya deja ver.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.application.puertos.repositorios import RegistroNoEncontrado

__all__ = ["DesviacionNoModificada", "RepositorioDesviacionesSQL"]

_COLUMNAS = """
    id, org_id, obra_id, tipo_nodo, insumo_id, concepto_id, tipo, monto,
    cantidad_plan, cantidad_real, precio_plan, precio_real, causa,
    usuario_id, causa_capturada_en, detectada_en
"""


class DesviacionNoModificada(RegistroNoEncontrado):
    """El UPDATE de `capturar_causa` no afectó ninguna fila: la desviación
    ya no existe, o salió del alcance del usuario (RLS) entre que se leyó
    y se intentó capturar la causa."""


class RepositorioDesviacionesSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def obtener(self, desviacion_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} from desviacion where id = :id"),
                {"id": str(desviacion_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def crear(self, datos: dict[str, Any]) -> UUID:
        """Alta de una desviación. `causa` nunca se recibe aquí: nace en
        `null` siempre (regla de captura 1, MODELO.md §5g) — `capturar_causa`
        es la única escritura que la llena, aparte y después.

        `tipo_nodo` no se pide en `datos`: se deriva de cuál de
        `insumo_id`/`concepto_id` llegó lleno, igual que la propiedad
        `Desviacion.tipo_nodo` del dominio — así no puede llegar un
        `tipo_nodo` que contradiga a los ids que sí se escriben.
        """
        insumo_id = datos.get("insumo_id")
        concepto_id = datos.get("concepto_id")
        tipo_nodo = "insumo" if insumo_id else "concepto"
        fila = (
            await self._sesion.execute(
                text(
                    """
                    insert into desviacion
                        (org_id, obra_id, tipo_nodo, insumo_id, concepto_id,
                         tipo, monto, cantidad_plan, cantidad_real,
                         precio_plan, precio_real, detectada_en)
                    values
                        (cast(current_setting('app.org_id') as uuid),
                         :obra_id, cast(:tipo_nodo as tipo_nodo_desviacion),
                         cast(:insumo_id as uuid), cast(:concepto_id as uuid),
                         cast(:tipo as tipo_desviacion), :monto,
                         -- El cast fija el tipo del parámetro; sin él un
                         -- Decimal nulo perdería su tipo (mismo criterio
                         -- que materiales_sql.crear_salida).
                         cast(:cantidad_plan as numeric),
                         cast(:cantidad_real as numeric),
                         cast(:precio_plan as numeric),
                         cast(:precio_real as numeric),
                         coalesce(:detectada_en, now()))
                    returning id
                    """
                ),
                {
                    "obra_id": str(datos["obra_id"]),
                    "tipo_nodo": tipo_nodo,
                    "insumo_id": str(insumo_id) if insumo_id else None,
                    "concepto_id": str(concepto_id) if concepto_id else None,
                    "tipo": datos["tipo"],
                    "monto": datos["monto"],
                    "cantidad_plan": datos.get("cantidad_plan"),
                    "cantidad_real": datos.get("cantidad_real"),
                    "precio_plan": datos.get("precio_plan"),
                    "precio_real": datos.get("precio_real"),
                    "detectada_en": datos.get("detectada_en"),
                },
            )
        ).scalar_one()
        return fila

    async def capturar_causa(
        self, desviacion_id: UUID, *, causa: str, usuario_id: UUID
    ) -> None:
        """Escritura aparte de `crear` (regla de captura 4, MODELO.md §5g):
        `causa_capturada_en` es siempre `now()` de ESTA llamada, nunca una
        copia de `detectada_en` — puede llegar mucho después, sin
        penalización."""
        resultado = await self._sesion.execute(
            text(
                """
                update desviacion
                   set causa              = cast(:causa as causa_desviacion),
                       usuario_id          = :usuario_id,
                       causa_capturada_en  = now()
                 where id = :id
                """
            ),
            {
                "id": str(desviacion_id),
                "causa": causa,
                "usuario_id": str(usuario_id),
            },
        )
        if resultado.rowcount == 0:
            raise DesviacionNoModificada(
                f"No se capturó la causa de la desviación {desviacion_id}: "
                f"ya no existe o salió de tu alcance."
            )

    async def patrones_por_insumo_o_concepto(
        self, *, obra_id: UUID | None = None
    ) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select insumo_id, concepto_id,
                           count(*)                    as n,
                           sum(monto)                   as monto_total,
                           count(distinct obra_id)       as obras_distintas
                      from desviacion
                     where cast(:obra_id as uuid) is null
                        or obra_id = cast(:obra_id as uuid)
                     group by insumo_id, concepto_id
                     order by monto_total desc
                    """
                ),
                {"obra_id": str(obra_id) if obra_id else None},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def patrones_por_obra(
        self, *, obra_ids: Sequence[UUID] | None = None
    ) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select obra_id,
                           count(*)                        as n,
                           sum(monto)                       as monto_total,
                           count(distinct insumo_id)         as insumos_distintos,
                           count(distinct concepto_id)       as conceptos_distintos
                      from desviacion
                     where cast(:obra_ids as uuid[]) is null
                        or obra_id = any(cast(:obra_ids as uuid[]))
                     group by obra_id
                     order by monto_total desc
                    """
                ),
                {
                    "obra_ids": (
                        [str(o) for o in obra_ids] if obra_ids else None
                    ),
                },
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]
