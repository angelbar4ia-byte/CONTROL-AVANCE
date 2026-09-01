"""Repositorio de obras.

Spec §12.11 (adaptador de persistencia) · §7.2 (estructura de proyecto) ·
§7.4 (árbol WBS del prototipo) · §11.3 workflow A.

RLS filtra `obra` por alcance de rol (política `obra_select` /
`obra_insert` / `obra_update` / `obra_delete`, `database/migrations/0012`):
igual que en `actividades_sql.py`, ningún método filtra `org_id` a mano.

**Por qué el alta genera el `id` en Python y no usa `RETURNING`:** igual que
en `proyectos_sql.py`, `obra_select` evalúa `app.obra_visible(id)` —función
`STABLE` que consulta `obra`— y Postgres aplica las políticas de `SELECT` al
`RETURNING` de un `INSERT`; bajo el snapshot de esa misma sentencia la fila
recién insertada aún no es visible, así que el `RETURNING` fallaría siempre.
Es la misma razón por la que `obra_insert` valida contra el **cluster** y no
contra la obra (comentario de la migración 0012). Con el uuid generado aquí el
`INSERT` no devuelve nada y la lectura posterior —otra sentencia, otro
snapshot— sí ve la fila.

**Fronteras de módulo:** este repositorio también lee `prototipo_nodo`, `cpu`
y `programa_base*`, que pertenecen a los contextos de Prototipo, Catálogos/APU
y Programación (§11.1). Es lo que el **workflow A** necesita para nacer
(§11.3 A.2) y sigue el precedente de `arbol_prototipo`; son lecturas de
referencia, nunca escrituras. Cuando esos contextos publiquen su fachada
(Fases 2 y 3 del roadmap) estos tres métodos se mueven detrás de ella —
`items_programa_base` ya tiene su equivalente en el repositorio de
Programación (`programas_sql.items_base_vigente`), que es a donde se moverá
cuando el workflow A pase a consumirlo por su puerto.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.application.puertos.repositorios import RegistroNoEncontrado

__all__ = ["ObraNoModificada", "RepositorioObrasSQL"]

_COLUMNAS = """
    id, cluster_id, prototipo_id, clave, residente_id, estatus,
    fecha_inicio, fecha_fin, avance_pct, m2, es_urba
"""

_COLUMNAS_O = """
    o.id, o.cluster_id, o.prototipo_id, o.clave, o.residente_id, o.estatus,
    o.fecha_inicio, o.fecha_fin, o.avance_pct, o.m2, o.es_urba
"""
"""Las mismas columnas calificadas, para el listado que hace join con `cluster`."""

_CAMPOS_EDITABLES = {
    "clave": "clave = :clave",
    "residente_id": "residente_id = cast(:residente_id as uuid)",
    "prototipo_id": "prototipo_id = cast(:prototipo_id as uuid)",
    "estatus": "estatus = cast(:estatus as estatus_obra)",
    "fecha_inicio": "fecha_inicio = :fecha_inicio",
    "fecha_fin": "fecha_fin = :fecha_fin",
    "m2": "m2 = :m2",
}
"""Columnas que `PATCH /obras/{id}` puede tocar (§11.2).

Es una lista blanca, no un `f"{campo} = ..."` armado con lo que llegue: la
clave del dict entra a la sentencia SQL, así que solo pueden entrar estas.
`cluster_id` y `org_id` no están: mover una obra de cluster la saca de su
proyecto y con eso de su alcance RLS — eso es un alta nueva, no una edición.
"""


class ObraNoModificada(RegistroNoEncontrado):
    """El UPDATE no afectó ninguna fila (carrera entre `obtener` y escribir,
    o la obra salió del alcance del usuario vía RLS)."""


class RepositorioObrasSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def obtener(self, obra_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} from obra where id = :id"),
                {"id": str(obra_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def listar(
        self,
        *,
        proyecto_id: UUID | None = None,
        cluster_id: UUID | None = None,
        residente_id: UUID | None = None,
        estatus: str | None = None,
    ) -> list[dict[str, Any]]:
        """Obras visibles para el rol actual (§11.2 `GET /obras`).

        El filtro por proyecto pasa por `cluster`, que trae su propia política
        de RLS: un rol que no vea el proyecto no ve sus clusters y el join se
        queda vacío —el alcance no se puede ampliar desde aquí.
        """
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS_O}
                    from obra o
                    join cluster c on c.id = o.cluster_id
                    -- El cast del lado `is null` fija el tipo del parámetro;
                    -- sin él asyncpg levanta AmbiguousParameterError.
                    where (cast(:proyecto_id as uuid) is null
                           or c.proyecto_id = cast(:proyecto_id as uuid))
                      and (cast(:cluster_id as uuid) is null
                           or o.cluster_id = cast(:cluster_id as uuid))
                      and (cast(:residente_id as uuid) is null
                           or o.residente_id = cast(:residente_id as uuid))
                      and (cast(:estatus as estatus_obra) is null
                           or o.estatus = cast(:estatus as estatus_obra))
                    order by o.clave
                    """
                ),
                {
                    "proyecto_id": str(proyecto_id) if proyecto_id else None,
                    "cluster_id": str(cluster_id) if cluster_id else None,
                    "residente_id": str(residente_id) if residente_id else None,
                    "estatus": estatus,
                },
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def crear(self, datos: dict[str, Any]) -> UUID:
        """Alta de obra (§11.2 `POST /obras`, Control de obra).

        Claves esperadas: ``cluster_id`` y ``clave``, ya validadas por
        `domain.obras.reglas.Obra`. Opcionales: ``prototipo_id``,
        ``residente_id``, ``fecha_inicio``, ``fecha_fin``, ``m2``, ``es_urba``.
        """
        (obra_id,) = await self.crear_en_lote([datos])
        return obra_id

    async def crear_en_lote(self, obras: list[dict[str, Any]]) -> list[UUID]:
        """Alta masiva (§11.2 `POST /obras/bulk`).

        Un solo `execute` con lista de parámetros —como
        `estimaciones_sql.agregar_conceptos`—; la atomicidad la da la unidad de
        trabajo del caso de uso, así que o entran todas o no entra ninguna.
        """
        if not obras:
            return []

        ids = [uuid4() for _ in obras]
        params = [
            {
                "id": str(obra_id),
                "cluster_id": str(datos["cluster_id"]),
                "prototipo_id": str(datos["prototipo_id"])
                if datos.get("prototipo_id")
                else None,
                "clave": datos["clave"],
                "residente_id": str(datos["residente_id"])
                if datos.get("residente_id")
                else None,
                "fecha_inicio": datos.get("fecha_inicio"),
                "fecha_fin": datos.get("fecha_fin"),
                "m2": datos.get("m2"),
                "es_urba": datos.get("es_urba", False),
            }
            for obra_id, datos in zip(ids, obras, strict=True)
        ]

        await self._sesion.execute(
            text(
                """
                insert into obra
                    (id, org_id, cluster_id, prototipo_id, clave, residente_id,
                     fecha_inicio, fecha_fin, m2, es_urba)
                values
                    (cast(:id as uuid), cast(current_setting('app.org_id') as uuid),
                     cast(:cluster_id as uuid), cast(:prototipo_id as uuid),
                     :clave, cast(:residente_id as uuid), :fecha_inicio,
                     :fecha_fin, :m2, :es_urba)
                """
            ),
            params,
        )
        return ids

    async def actualizar(self, obra_id: UUID, cambios: dict[str, Any]) -> None:
        """Edición parcial (§11.2 `PATCH /obras/{id}`).

        Solo se escriben las claves presentes en `cambios` y solo si están en
        `_CAMPOS_EDITABLES`; una clave desconocida es un error de programación
        del caso de uso, no una entrada del usuario, así que revienta fuerte.
        """
        desconocidos = set(cambios) - set(_CAMPOS_EDITABLES)
        if desconocidos:
            raise ValueError(
                f"Campos no editables en obra: {', '.join(sorted(desconocidos))}."
            )
        if not cambios:
            return

        asignaciones = ", ".join(_CAMPOS_EDITABLES[campo] for campo in cambios)
        params: dict[str, Any] = {"id": str(obra_id)}
        for campo, valor in cambios.items():
            if campo in ("residente_id", "prototipo_id") and valor is not None:
                params[campo] = str(valor)
            else:
                params[campo] = valor

        resultado = await self._sesion.execute(
            text(f"update obra set {asignaciones} where id = :id"),
            params,
        )
        if resultado.rowcount == 0:
            raise ObraNoModificada(
                f"No se actualizó la obra {obra_id}: ya no existe o salió de "
                f"tu alcance."
            )

    async def actualizar_avance(self, obra_id: UUID, avance_pct: Decimal) -> None:
        resultado = await self._sesion.execute(
            text("update obra set avance_pct = :avance_pct where id = :id"),
            {"avance_pct": avance_pct, "id": str(obra_id)},
        )
        if resultado.rowcount == 0:
            raise ObraNoModificada(
                f"No se actualizó la obra {obra_id}: ya no existe o salió de "
                f"tu alcance."
            )

    async def arbol_prototipo(self, prototipo_id: UUID) -> list[dict[str, Any]]:
        """Nodos WBS del prototipo en orden de recorrido (§7.4).

        `orden` solo es comparable **dentro** de un mismo padre (es una
        columna por nivel, no una posición global), así que un `ORDER BY
        orden` plano intercalaría ramas distintas. El CTE recursivo arma la
        ruta de "orden"s desde la raíz (`array[orden_raíz, orden_hijo, …]`) y
        ordena por esa ruta —lo que da el recorrido en profundidad,
        padre-antes-que-hijos, que necesita el workflow A (§11.3) para crear
        las `Actividad` en el orden correcto del árbol.
        """
        filas = (
            await self._sesion.execute(
                text(
                    """
                    with recursive arbol as (
                        select id, parent_id, tipo, nombre, clave,
                               concepto_id, nivel_id, etapa_id, orden,
                               cantidad, ponderacion,
                               array[orden] as ruta
                        from prototipo_nodo
                        where prototipo_id = :prototipo_id
                          and parent_id is null

                        union all

                        select h.id, h.parent_id, h.tipo, h.nombre, h.clave,
                               h.concepto_id, h.nivel_id, h.etapa_id, h.orden,
                               h.cantidad, h.ponderacion,
                               a.ruta || h.orden
                        from prototipo_nodo h
                        join arbol a on h.parent_id = a.id
                    )
                    select id, parent_id, tipo, nombre, clave, concepto_id,
                           nivel_id, etapa_id, orden, cantidad, ponderacion
                    from arbol
                    order by ruta
                    """
                ),
                {"prototipo_id": str(prototipo_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    # --- Workflow A: generación de la obra desde el prototipo (§11.3 A) ---

    async def tiene_actividades(self, obra_id: UUID) -> bool:
        """`True` si la obra ya se generó (§11.3 A.2)."""
        return bool(
            await self._sesion.scalar(
                text("select exists (select 1 from actividad where obra_id = :obra_id)"),
                {"obra_id": str(obra_id)},
            )
        )

    async def precios_vigentes(self, concepto_ids: list[UUID]) -> dict[str, dict[str, Any]]:
        """CPU vigente de cada concepto (§7.3, §11.3 A.2).

        Solo la versión `vigente` y solo la receta base (`variante is null`):
        `uq_cpu_vigente` permite un vigente **por variante** (§2.2), y elegir
        entre recetas alternas es decisión de catálogo, no de la generación de
        la obra. Los conceptos sin CPU vigente no aparecen en el resultado —el
        dominio decide qué hacer con ellos (`planear_actividades`).
        """
        if not concepto_ids:
            return {}

        filas = (
            await self._sesion.execute(
                text(
                    """
                    select concepto_id, precio_unitario, precio_destajo
                    from cpu
                    where vigente
                      and variante is null
                      and concepto_id = any(cast(:concepto_ids as uuid[]))
                    """
                ),
                {"concepto_ids": [str(cid) for cid in concepto_ids]},
            )
        ).mappings().all()

        return {
            str(fila["concepto_id"]): {
                "precio_unitario": fila["precio_unitario"],
                "precio_destajo": fila["precio_destajo"],
            }
            for fila in filas
        }

    async def items_programa_base(self, prototipo_id: UUID) -> list[dict[str, Any]]:
        """Items del `ProgramaBase` vigente del prototipo (§7.5).

        Lista vacía si el prototipo aún no tiene plantilla: la obra se genera
        igual, con duración por default, y la programación se ajusta después
        (§11.2 `PATCH /actividades/{id}/programacion`).
        """
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select i.prototipo_nodo_id, i.frente_id, i.etapa_id,
                           i.duracion_dias, i.dependencias, i.tramos, i.orden
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

    async def calendario_programa_base(
        self, prototipo_id: UUID
    ) -> list[int] | None:
        """Días hábiles del `ProgramaBase` vigente del prototipo (0040, §7.5).

        `None` si el prototipo no tiene plantilla todavía: la obra se genera
        igual y su cronograma nace con semana natural, que es lo que decide el
        dominio (`CalendarioLaboral.de(None)`) y no esta consulta.

        Vive aquí por la misma razón que `items_programa_base` —el workflow A
        aún consume programación por el repositorio de obras—; su gemela del
        contexto Programación es `programas_sql.base_vigente` (ver el docstring
        de fronteras del módulo).
        """
        dias = (
            await self._sesion.execute(
                text(
                    """
                    select dias_habiles
                    from programa_base
                    where prototipo_id = :prototipo_id and vigente
                    """
                ),
                {"prototipo_id": str(prototipo_id)},
            )
        ).scalar_one_or_none()
        return list(dias) if dias is not None else None

    async def instanciar_programa(
        self, obra_id: UUID, *, dias_habiles: list[int] | None = None
    ) -> UUID:
        """Crea el `ProgramaObra` vigente de la obra (§7.5, §11.3 A.2).

        `uq_programa_obra_vigente` deja un solo vigente por obra; la versión
        se toma como la siguiente de las existentes para que el versionado de
        la Fase 3 (instanciar/reversionar) encaje sin migrar datos. El
        `RETURNING` es seguro aquí: `programa_obra_scope` evalúa
        `app.obra_visible(obra_id)` sobre la **obra**, que ya existe.

        `dias_habiles` baja del programa base del prototipo (0040), como la
        duración y las dependencias: sin esto, la primera ruta crítica de una
        obra recién generada saldría en semana natural aunque su plantilla
        dijera otra cosa, y no se corregiría hasta el primer `POST
        /obras/{id}/programa`.
        """
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into programa_obra
                        (org_id, obra_id, version, vigente, dias_habiles)
                    select cast(current_setting('app.org_id') as uuid),
                           :obra_id,
                           coalesce(max(version), 0) + 1,
                           true,
                           -- Ver `programas_sql.crear_base`: el default de la
                           -- columna se repite porque un `insert ... select`
                           -- no puede escribir DEFAULT en la lista.
                           coalesce(
                               cast(:dias_habiles as smallint[]),
                               array[1,2,3,4,5,6,7]::smallint[]
                           )
                    from programa_obra
                    where obra_id = :obra_id
                    returning id
                    """
                ),
                {"obra_id": str(obra_id), "dias_habiles": dias_habiles},
            )
        ).scalar_one()

    async def crear_actividades(
        self,
        obra_id: UUID,
        programa_obra_id: UUID,
        actividades: list[dict[str, Any]],
    ) -> None:
        """Persiste las actividades ya planeadas por el dominio (§11.3 A.2).

        `avance_pct` y el estatus inicial no se mandan: los deriva el trigger
        `trg_actividad_recalcular` (§6, migración 0007), que es el espejo en BD
        de la misma regla. Cada dict trae `concepto_id`, `prototipo_nodo_id`,
        `descripcion`, `cant_base`, `precio_unitario`, `precio_destajo`,
        `modo_pago`, `duracion_dias`, `dependencias` y `tramos` (json ya
        serializados) y, opcionales, `frente_id`, `nivel_id` y `etapa_id`.
        """
        if not actividades:
            return

        params = [
            {
                "obra_id": str(obra_id),
                "programa_obra_id": str(programa_obra_id),
                "concepto_id": str(a["concepto_id"]),
                "prototipo_nodo_id": str(a["prototipo_nodo_id"])
                if a.get("prototipo_nodo_id")
                else None,
                "frente_id": str(a["frente_id"]) if a.get("frente_id") else None,
                "nivel_id": str(a["nivel_id"]) if a.get("nivel_id") else None,
                "etapa_id": str(a["etapa_id"]) if a.get("etapa_id") else None,
                "descripcion": a.get("descripcion"),
                "cant_base": a["cant_base"],
                "precio_unitario": a["precio_unitario"],
                "precio_destajo": a["precio_destajo"],
                "modo_pago": a["modo_pago"],
                "duracion_dias": a["duracion_dias"],
                "dependencias": a["dependencias"],
                "tramos": a["tramos"],
            }
            for a in actividades
        ]

        await self._sesion.execute(
            text(
                """
                insert into actividad
                    (org_id, obra_id, programa_obra_id, concepto_id,
                     prototipo_nodo_id, frente_id,
                     nivel_id, etapa_id, descripcion, cant_base,
                     precio_unitario, precio_destajo, modo_pago, duracion_dias,
                     dependencias, tramos)
                values
                    (cast(current_setting('app.org_id') as uuid),
                     cast(:obra_id as uuid), cast(:programa_obra_id as uuid),
                     cast(:concepto_id as uuid),
                     cast(:prototipo_nodo_id as uuid), cast(:frente_id as uuid),
                     cast(:nivel_id as uuid), cast(:etapa_id as uuid),
                     :descripcion, :cant_base, :precio_unitario,
                     :precio_destajo, cast(:modo_pago as modo_pago),
                     :duracion_dias, cast(:dependencias as jsonb),
                     cast(:tramos as jsonb))
                """
            ),
            params,
        )
