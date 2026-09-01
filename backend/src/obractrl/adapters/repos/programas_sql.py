"""Repositorio de programación.

Spec §12.11 (adaptador de persistencia) · §7.5 (ProgramaBase ·
ProgramaBaseItem · ProgramaObra) · §11.2 ("Programación · CPM") · §12.4 (RLS).

Tres tablas, dos alcances distintos (`database/migrations/20260814000012`):

* `programa_base` y `programa_base_item` entran al bloque **A** de catálogo:
  las lee cualquier usuario de la organización y las escribe `app.es_config()`
  —Control de obra y Super intendente (§5.1)—. Como el predicado de `SELECT`
  es solo de organización, el `RETURNING` del alta es seguro (a diferencia de
  `proyectos_sql.py`).
* `programa_obra` entra al bloque **B** por obra
  (`app.obra_visible(obra_id)`). El `RETURNING` también es seguro aquí: el
  predicado se evalúa sobre la **obra**, que ya existe (mismo razonamiento que
  `obras_sql.instanciar_programa`).

Ningún método filtra por `org_id` a mano: eso lo impone la base. `org_id` en
los INSERT sale de `current_setting('app.org_id')`, igual que en el resto de
los repos.

**Fronteras de módulo (§11.1):** aquí *no* se toca `actividad`. Los campos de
programación viven en esa tabla por el §7.6, pero se leen y escriben por
`RepositorioActividades` —su puerto—, nunca desde este repositorio.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.application.puertos.repositorios import RegistroNoEncontrado

__all__ = ["ProgramaNoModificado", "RepositorioProgramasSQL"]

_COLUMNAS_BASE = """
    id, prototipo_id, version, vigente, nombre, dias_habiles,
    profundidad_captura
"""

_COLUMNAS_ITEM = """
    id, programa_base_id, prototipo_nodo_id, frente_id, etapa_id,
    duracion_dias, dependencias, tramos, orden
"""

_COLUMNAS_OBRA = """
    id, obra_id, version, vigente, fecha_corte, dias_habiles
"""


class ProgramaNoModificado(RegistroNoEncontrado):
    """El UPDATE no afectó ninguna fila: el programa se borró o salió del
    alcance del usuario (RLS) entre la lectura y la escritura (§12.4)."""


class RepositorioProgramasSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    # --- ProgramaBase (§7.5) ---------------------------------------------

    async def crear_base(self, datos: dict[str, Any]) -> UUID:
        """Alta de `ProgramaBase` (§11.2 `POST /programas-base`, rol C).

        Claves esperadas: ``prototipo_id``. Opcionales: ``nombre``,
        ``dias_habiles`` (lista de días ISO, migración 0040) y
        ``profundidad_captura`` (0041). El default de la columna cubre a los dos
        últimos si faltan, pero el caso de uso siempre los manda resueltos —el
        dominio ya decidió que sin elección son semana natural y captura por
        concepto— para que la plantilla nazca con los dos explícitos.

        Retirar el vigente anterior **antes** de insertar el nuevo no es
        opcional: `uq_programa_base_vigente` es un índice único parcial y no
        es diferible, así que insertar el nuevo vigente primero violaría la
        restricción — mismo caso que `conceptos_sql.publicar_version_cpu`.
        """
        prototipo_id = str(datos["prototipo_id"])

        await self._sesion.execute(
            text(
                """
                update programa_base
                   set vigente = false
                 where prototipo_id = cast(:prototipo_id as uuid)
                   and vigente
                """
            ),
            {"prototipo_id": prototipo_id},
        )

        return (
            await self._sesion.execute(
                text(
                    """
                    insert into programa_base
                        (org_id, prototipo_id, version, vigente, nombre,
                         dias_habiles, profundidad_captura)
                    select cast(current_setting('app.org_id') as uuid),
                           cast(:prototipo_id as uuid),
                           coalesce(max(version), 0) + 1,
                           true,
                           :nombre,
                           -- `insert ... select` no puede escribir DEFAULT en
                           -- la lista, así que el default de la columna se
                           -- repite aquí para el llamador que no manda
                           -- calendario (migración 0040: semana natural).
                           coalesce(
                               cast(:dias_habiles as smallint[]),
                               array[1,2,3,4,5,6,7]::smallint[]
                           ),
                           -- Mismo caso con la profundidad de captura (0041):
                           -- sin elección, 'concepto', que es renglón por
                           -- renglón — lo único que existía antes de la 0041.
                           coalesce(
                               cast(:profundidad_captura as tipo_prototipo_nodo),
                               'concepto'::tipo_prototipo_nodo
                           )
                    from programa_base
                    where prototipo_id = cast(:prototipo_id as uuid)
                    returning id
                    """
                ),
                {
                    "prototipo_id": prototipo_id,
                    "nombre": datos.get("nombre"),
                    "dias_habiles": datos.get("dias_habiles"),
                    "profundidad_captura": datos.get("profundidad_captura"),
                },
            )
        ).scalar_one()

    async def obtener_base(self, programa_base_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS_BASE} from programa_base where id = :id"),
                {"id": str(programa_base_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def listar_bases(
        self, *, prototipo_id: UUID | None = None, solo_vigentes: bool = False
    ) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS_BASE}
                    from programa_base
                    -- El cast del lado `is null` fija el tipo del parámetro;
                    -- sin él asyncpg levanta AmbiguousParameterError.
                    where (cast(:prototipo_id as uuid) is null
                           or prototipo_id = cast(:prototipo_id as uuid))
                      and (not cast(:solo_vigentes as boolean) or vigente)
                    order by prototipo_id, version desc
                    """
                ),
                {
                    "prototipo_id": str(prototipo_id) if prototipo_id else None,
                    "solo_vigentes": solo_vigentes,
                },
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def agregar_items_base(
        self, programa_base_id: UUID, items: list[dict[str, Any]]
    ) -> None:
        """Renglones de la plantilla, ya validados por el dominio (§7.5).

        Cada dict trae ``duracion_dias`` y ``orden``, y opcionales
        ``prototipo_nodo_id``, ``etapa_id``, ``frente_id``, ``dependencias`` y
        ``tramos`` (listas de dicts; se serializan aquí, que es el borde).
        """
        if not items:
            return

        params = [
            {
                "programa_base_id": str(programa_base_id),
                "prototipo_nodo_id": str(item["prototipo_nodo_id"])
                if item.get("prototipo_nodo_id")
                else None,
                "etapa_id": str(item["etapa_id"]) if item.get("etapa_id") else None,
                "frente_id": str(item["frente_id"]) if item.get("frente_id") else None,
                "duracion_dias": item["duracion_dias"],
                "dependencias": json.dumps(item.get("dependencias") or []),
                "tramos": json.dumps(item.get("tramos") or []),
                "orden": item.get("orden", 0),
            }
            for item in items
        ]

        await self._sesion.execute(
            text(
                """
                insert into programa_base_item
                    (org_id, programa_base_id, prototipo_nodo_id, etapa_id,
                     frente_id, duracion_dias, dependencias, tramos, orden)
                values
                    (cast(current_setting('app.org_id') as uuid),
                     cast(:programa_base_id as uuid),
                     cast(:prototipo_nodo_id as uuid),
                     cast(:etapa_id as uuid), cast(:frente_id as uuid),
                     :duracion_dias, cast(:dependencias as jsonb),
                     cast(:tramos as jsonb), :orden)
                """
            ),
            params,
        )

    async def listar_items_base(
        self, programa_base_id: UUID
    ) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS_ITEM}
                    from programa_base_item
                    where programa_base_id = :programa_base_id
                    order by orden
                    """
                ),
                {"programa_base_id": str(programa_base_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def base_vigente(self, prototipo_id: UUID) -> dict[str, Any] | None:
        """El `ProgramaBase` vigente del prototipo, sin sus renglones (§7.5).

        Existe aparte de `items_base_vigente` porque hay datos de la plantilla
        que no son de renglón: el calendario de trabajo (`dias_habiles`, 0040)
        es del cronograma completo, no de cada actividad. Instanciar necesita
        los dos, y meterlo repetido en cada item invitaría a que un renglón lo
        contradijera.
        """
        fila = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS_BASE}
                    from programa_base
                    where prototipo_id = :prototipo_id and vigente
                    """
                ),
                {"prototipo_id": str(prototipo_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def items_base_vigente(self, prototipo_id: UUID) -> list[dict[str, Any]]:
        """Renglones del programa base vigente del prototipo (§7.5).

        Es la misma lectura que `obras_sql.items_programa_base` hace para el
        workflow A; existe aquí porque este es el repositorio del contexto
        Programación, y el de obras la mantiene mientras el workflow A viva
        allá (ver su docstring de fronteras).
        """
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select i.id, i.programa_base_id, i.prototipo_nodo_id,
                           i.frente_id, i.etapa_id, i.duracion_dias,
                           i.dependencias, i.tramos, i.orden
                    from programa_base_item i
                    join programa_base b on b.id = i.programa_base_id
                    where b.prototipo_id = :prototipo_id
                      and b.vigente
                    order by i.orden
                    """
                ),
                {"prototipo_id": str(prototipo_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    # --- ProgramaObra (§7.5) ---------------------------------------------

    async def programa_vigente(self, obra_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS_OBRA}
                    from programa_obra
                    where obra_id = :obra_id and vigente
                    """
                ),
                {"obra_id": str(obra_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def programas_vigentes(
        self, obra_ids: Sequence[UUID]
    ) -> dict[str, dict[str, Any]]:
        """`programa_vigente` de varias obras en una sola consulta (§7.5).

        La pantalla de replicación masiva lo necesita para advertir, antes de
        replicar, cuáles de las obras del prototipo ya traen cronograma y en
        qué versión (§11.2 `POST /programas-base/{id}/replicar`): con 40 casas,
        preguntarlo obra por obra son 40 viajes a la base para pintar una
        columna.

        RLS sigue mandando: `programa_obra` entra al bloque por obra
        (`app.obra_visible(obra_id)`), así que una obra fuera del alcance
        simplemente no vuelve — igual que si no tuviera cronograma. Eso es
        deliberado (§12.4): la respuesta no distingue "no la puedes ver" de
        "no tiene versión".
        """
        if not obra_ids:
            return {}

        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS_OBRA}
                    from programa_obra
                    where obra_id = any(cast(:obra_ids as uuid[]))
                      and vigente
                    """
                ),
                {"obra_ids": [str(obra_id) for obra_id in obra_ids]},
            )
        ).mappings().all()
        return {str(fila["obra_id"]): dict(fila) for fila in filas}

    async def listar_programas(self, obra_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS_OBRA}
                    from programa_obra
                    where obra_id = :obra_id
                    order by version desc
                    """
                ),
                {"obra_id": str(obra_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def instanciar(
        self,
        obra_id: UUID,
        *,
        fecha_corte: date | None = None,
        dias_habiles: list[int] | None = None,
    ) -> dict[str, Any]:
        """Siguiente versión vigente del cronograma de la obra (§11.2).

        Mismo patrón que `crear_base`: primero se retira el vigente anterior
        —`uq_programa_obra_vigente` no es diferible— y luego se inserta la
        versión nueva. Versionar en vez de sobrescribir es lo que deja
        auditar contra qué programa se midió cada corte (§7.5).

        `dias_habiles` es el calendario que la obra hereda de su programa base
        (0040). Se **congela** en la versión: reinstanciar con otra plantilla
        crea una versión nueva con su propio calendario y deja intacto contra
        qué se calculó la anterior, igual que `fecha_corte`.
        """
        await self._sesion.execute(
            text(
                """
                update programa_obra
                   set vigente = false
                 where obra_id = cast(:obra_id as uuid)
                   and vigente
                """
            ),
            {"obra_id": str(obra_id)},
        )

        fila = (
            await self._sesion.execute(
                text(
                    f"""
                    insert into programa_obra
                        (org_id, obra_id, version, vigente, fecha_corte,
                         dias_habiles)
                    select cast(current_setting('app.org_id') as uuid),
                           cast(:obra_id as uuid),
                           coalesce(max(version), 0) + 1,
                           true,
                           cast(:fecha_corte as date),
                           -- Ver `crear_base`: el default de la columna se
                           -- repite porque un `insert ... select` no puede
                           -- escribir DEFAULT en la lista.
                           coalesce(
                               cast(:dias_habiles as smallint[]),
                               array[1,2,3,4,5,6,7]::smallint[]
                           )
                    from programa_obra
                    where obra_id = cast(:obra_id as uuid)
                    returning {_COLUMNAS_OBRA}
                    """
                ),
                {
                    "obra_id": str(obra_id),
                    "fecha_corte": fecha_corte,
                    "dias_habiles": dias_habiles,
                },
            )
        ).mappings().one()
        return dict(fila)

    async def fijar_fecha_corte(self, programa_obra_id: UUID, fecha: date) -> None:
        resultado = await self._sesion.execute(
            text(
                "update programa_obra set fecha_corte = :fecha where id = :id"
            ),
            {"fecha": fecha, "id": str(programa_obra_id)},
        )
        if resultado.rowcount == 0:
            raise ProgramaNoModificado(
                f"No se actualizó el programa {programa_obra_id}: ya no existe "
                f"o salió de tu alcance."
            )
