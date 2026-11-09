"""Repositorio de escritura del árbol WBS del prototipo (§7.4).

Spec §12.11 (adaptador de persistencia) · §10.8 (idempotencia de la carga) ·
§12.4 (RLS).

Primer escritor de `prototipo_nodo` — hasta el cargador de presupuesto
jerárquico, la tabla solo se leía (`RepositorioObras.arbol_prototipo`,
otra fachada, §11.1). El `upsert` por `(org_id, prototipo_id, parent_id,
clave)` (`uq_prototipo_nodo_posicion`, migración 0038) es lo que conserva
el `id` de un nodo entre recargas: regenerarlo rompería en silencio
`programa_base_item.prototipo_nodo_id` y `actividad.prototipo_nodo_id`, que
lo referencian por igualdad literal.

La clave sola no basta de identidad: un archivo real repite la misma clave
de `CONCEPTO` colgada de dos etapas distintas **del mismo** prototipo, cada
una con su propia cantidad (migración 0038). `parent_id` entra al índice
—con un `coalesce` a un sentinel para la raíz, que no cuelga de nadie— para
que cada posición del árbol tenga su propia fila en vez de pisarse entre
sí.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioPrototipoNodoSQL"]


class RepositorioPrototipoNodoSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def guardar_datos_catalogo(self, nodo_id: UUID, datos: dict[str, str]) -> None:
        """Mezcla en el nodo las columnas del catálogo sin campo propio (0123). Sin la columna (base sin migrar), nada."""
        if not datos:
            return
        hay = (
            await self._sesion.execute(
                text(
                    "select exists (select 1 from information_schema.columns where table_schema = 'public' "
                    "and table_name = 'prototipo_nodo' and column_name = 'datos_catalogo')"
                )
            )
        ).scalar_one()
        if not hay:
            return
        await self._sesion.execute(
            text("update prototipo_nodo set datos_catalogo = datos_catalogo || cast(:d as jsonb) where id = :id"),
            {"d": json.dumps(datos, ensure_ascii=False), "id": str(nodo_id)},
        )

    async def por_prototipo(self, prototipo_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select id, parent_id, tipo, nombre, clave, concepto_id,
                           nivel_id, etapa_id, orden, cantidad, ponderacion,
                           modo_cantidad, ocurrencia, wbs, nivel_erp
                      from prototipo_nodo
                     where org_id = cast(current_setting('app.org_id') as uuid)
                       and prototipo_id = :prototipo_id
                    """
                ),
                {"prototipo_id": str(prototipo_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def arbol(self, prototipo_id: UUID) -> list[dict[str, Any]]:
        """Los mismos nodos que `por_prototipo`, en recorrido en profundidad.

        `orden` solo es comparable entre hermanos (es una columna por nivel,
        no una posición global): un `ORDER BY orden` plano intercalaría
        ramas distintas. El CTE recursivo arma la ruta de "orden"s desde la
        raíz y ordena por esa ruta — mismo patrón ya probado en
        `RepositorioObras.arbol_prototipo` (§11.1, ese lee para el workflow
        A; este lee para pintar la pantalla).

        `tipo_prototipo_nodo` no distingue concepto de concepto auxiliar
        —los dos se guardan como `'concepto'`, el archivo real solo lo dice
        en `concepto.tipo` (§10.1)—, así que el `left join` trae
        `concepto_tipo` para que la pantalla sí pueda distinguirlos.
        """
        filas = (
            await self._sesion.execute(
                text(
                    """
                    with recursive arbol as (
                        select id, parent_id, tipo, nombre, clave,
                               concepto_id, nivel_id, etapa_id, orden,
                               cantidad, ponderacion, modo_cantidad,
                               array[orden] as ruta
                        from prototipo_nodo
                        where org_id = cast(current_setting('app.org_id') as uuid)
                          and prototipo_id = :prototipo_id
                          and parent_id is null

                        union all

                        select h.id, h.parent_id, h.tipo, h.nombre, h.clave,
                               h.concepto_id, h.nivel_id, h.etapa_id, h.orden,
                               h.cantidad, h.ponderacion, h.modo_cantidad,
                               a.ruta || h.orden
                        from prototipo_nodo h
                        join arbol a on h.parent_id = a.id
                    )
                    select a.id, a.parent_id, a.tipo, a.nombre, a.clave,
                           a.concepto_id, a.nivel_id, a.etapa_id, a.orden,
                           a.cantidad, a.ponderacion, a.modo_cantidad,
                           c.tipo as concepto_tipo
                    from arbol a
                    left join concepto c on c.id = a.concepto_id
                    order by a.ruta
                    """
                ),
                {"prototipo_id": str(prototipo_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def upsert(
        self, prototipo_id: UUID, *, clave: str | None, datos: dict[str, Any]
    ) -> tuple[UUID, bool]:
        """Inserta o actualiza por `(org_id, prototipo_id, parent_id, clave)`.

        Claves esperadas en ``datos``: ``parent_id``, ``tipo``, ``nombre``,
        opcionales ``concepto_id``, ``nivel_id``, ``etapa_id``, ``orden``,
        ``cantidad``. Sin ``clave`` (nodo sin identidad natural) siempre
        inserta — no hay match posible.

        ``xmax = 0`` en el `RETURNING` distingue insert de update: es el
        idioma estándar de Postgres para un `INSERT ... ON CONFLICT ... DO
        UPDATE` de una sola sentencia.
        """
        parametros = {
            "prototipo_id": str(prototipo_id),
            "clave": clave,
            "parent_id": str(datos["parent_id"]) if datos.get("parent_id") else None,
            "tipo": datos["tipo"],
            "nombre": datos["nombre"],
            "concepto_id": str(datos["concepto_id"]) if datos.get("concepto_id") else None,
            "nivel_id": str(datos["nivel_id"]) if datos.get("nivel_id") else None,
            "etapa_id": str(datos["etapa_id"]) if datos.get("etapa_id") else None,
            "orden": datos.get("orden", 0),
            "cantidad": datos.get("cantidad", 0),
            "ocurrencia": datos.get("ocurrencia", 1),
            "wbs": datos.get("wbs"),
            "nivel_erp": datos.get("nivel_erp"),
        }

        if clave is None:
            fila = (
                await self._sesion.execute(
                    text(
                        """
                        insert into prototipo_nodo
                            (org_id, prototipo_id, parent_id, tipo, nombre, clave,
                             concepto_id, nivel_id, etapa_id, orden, cantidad,
                             wbs, nivel_erp)
                        values
                            (cast(current_setting('app.org_id') as uuid), :prototipo_id,
                             cast(:parent_id as uuid), cast(:tipo as tipo_prototipo_nodo),
                             :nombre, null, cast(:concepto_id as uuid),
                             cast(:nivel_id as uuid), cast(:etapa_id as uuid),
                             :orden, :cantidad, :wbs, :nivel_erp)
                        returning id
                        """
                    ),
                    parametros,
                )
            ).one()
            return fila.id, True

        fila = (
            await self._sesion.execute(
                text(
                    """
                    insert into prototipo_nodo
                        (org_id, prototipo_id, parent_id, tipo, nombre, clave,
                         concepto_id, nivel_id, etapa_id, orden, cantidad, ocurrencia,
                         wbs, nivel_erp)
                    values
                        (cast(current_setting('app.org_id') as uuid), :prototipo_id,
                         cast(:parent_id as uuid), cast(:tipo as tipo_prototipo_nodo),
                         :nombre, :clave, cast(:concepto_id as uuid),
                         cast(:nivel_id as uuid), cast(:etapa_id as uuid),
                         :orden, :cantidad, :ocurrencia, :wbs, :nivel_erp)
                    on conflict (
                        org_id, prototipo_id,
                        coalesce(parent_id, '00000000-0000-0000-0000-000000000000'::uuid),
                        clave, ocurrencia
                    ) where clave is not null
                    do update set
                        parent_id   = excluded.parent_id,
                        tipo        = excluded.tipo,
                        nombre      = excluded.nombre,
                        concepto_id = excluded.concepto_id,
                        nivel_id    = excluded.nivel_id,
                        etapa_id    = excluded.etapa_id,
                        orden       = excluded.orden,
                        cantidad    = excluded.cantidad,
                        wbs         = excluded.wbs,
                        nivel_erp   = excluded.nivel_erp
                    returning id, (xmax = 0) as es_alta
                    """
                ),
                parametros,
            )
        ).one()
        return fila.id, bool(fila.es_alta)

    async def clonar_estructura(
        self,
        *,
        origen_prototipo_id: UUID,
        destino_prototipo_id: UUID,
        sin_cantidades: bool = False,
    ) -> int:
        """Ver protocolo. El árbol de un prototipo tiene pocos niveles
        (nivel -> etapa -> [agrupador] -> concepto), así que se clona por
        pasadas en Python en vez de un `WITH RECURSIVE` de escritura
        (Postgres no deja insertar recursivamente sobre una tabla que se
        está llenando en la misma sentencia): cada pasada inserta los
        nodos cuyo padre ya tiene su `id` nuevo (o no tiene padre), hasta
        que no quede ninguno pendiente.

        Nada de esto se registra nodo por nodo en el snapshot del lote: el
        único `carga_snapshot` que `AplicadorIngenieriaLote` guarda para
        este paso es el alta del `prototipo` nuevo — revertirla borra ese
        `prototipo` y, por `on delete cascade` (migración 0006), se lleva
        consigo cada nodo clonado aquí sin que el snapshot necesite saber
        cuáles son.
        """
        origen = (
            await self._sesion.execute(
                text(
                    """
                    select id, parent_id, tipo, nombre, clave, concepto_id,
                           nivel_id, etapa_id, orden, cantidad, ponderacion, ocurrencia,
                           wbs, nivel_erp
                      from prototipo_nodo
                     where org_id = cast(current_setting('app.org_id') as uuid)
                       and prototipo_id = :origen_id
                    """
                ),
                {"origen_id": str(origen_prototipo_id)},
            )
        ).mappings().all()

        por_id = {fila["id"]: dict(fila) for fila in origen}
        mapa_ids: dict[Any, Any] = {}
        pendientes = set(por_id)
        clonados = 0

        while pendientes:
            listos = [
                nid
                for nid in pendientes
                if por_id[nid]["parent_id"] is None
                or por_id[nid]["parent_id"] in mapa_ids
            ]
            if not listos:
                raise ValueError(
                    "clonar_estructura: hay nodos cuyo parent_id no "
                    "aparece en el mismo prototipo de origen (árbol "
                    "inconsistente)."
                )
            for nid in listos:
                fila_origen = por_id[nid]
                nuevo_parent = (
                    mapa_ids.get(fila_origen["parent_id"])
                    if fila_origen["parent_id"] is not None
                    else None
                )
                nuevo = (
                    await self._sesion.execute(
                        text(
                            """
                            insert into prototipo_nodo
                                (org_id, prototipo_id, parent_id, tipo, nombre,
                                 clave, concepto_id, nivel_id, etapa_id, orden,
                                 cantidad, ponderacion, modo_cantidad, ocurrencia,
                                 wbs, nivel_erp)
                            values
                                (cast(current_setting('app.org_id') as uuid),
                                 :destino_id, cast(:parent_id as uuid),
                                 cast(:tipo as tipo_prototipo_nodo), :nombre,
                                 :clave, cast(:concepto_id as uuid),
                                 cast(:nivel_id as uuid), cast(:etapa_id as uuid),
                                 :orden, :cantidad, :ponderacion, 'heredada', :ocurrencia,
                                 :wbs, :nivel_erp)
                            returning id
                            """
                        ),
                        {
                            "destino_id": str(destino_prototipo_id),
                            "parent_id": str(nuevo_parent) if nuevo_parent else None,
                            "tipo": fila_origen["tipo"],
                            "nombre": fila_origen["nombre"],
                            "clave": fila_origen["clave"],
                            "concepto_id": (
                                str(fila_origen["concepto_id"])
                                if fila_origen["concepto_id"]
                                else None
                            ),
                            "nivel_id": (
                                str(fila_origen["nivel_id"])
                                if fila_origen["nivel_id"]
                                else None
                            ),
                            "etapa_id": (
                                str(fila_origen["etapa_id"])
                                if fila_origen["etapa_id"]
                                else None
                            ),
                            "orden": fila_origen["orden"],
                            # El catálogo base de una obra «Nueva» (0081) es la estructura y
                            # los conceptos, sin cantidades: esas llegan midiendo.
                            "cantidad": 0 if sin_cantidades else fila_origen["cantidad"],
                            "ponderacion": fila_origen["ponderacion"],
                            "ocurrencia": fila_origen["ocurrencia"],
                            "wbs": fila_origen["wbs"],
                            "nivel_erp": fila_origen["nivel_erp"],
                        },
                    )
                ).one()
                mapa_ids[nid] = nuevo.id
                clonados += 1
            pendientes -= set(listos)

        return clonados

    async def actualizar_cantidad(
        self,
        destino_prototipo_id: UUID,
        *,
        parent_id: UUID | None,
        clave: str,
        cantidad: Decimal,
        modo_cantidad: str,
    ) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    update prototipo_nodo set
                        cantidad      = :cantidad,
                        modo_cantidad = cast(:modo_cantidad as modo_cantidad)
                     where org_id = cast(current_setting('app.org_id') as uuid)
                       and prototipo_id = :prototipo_id
                       and coalesce(parent_id, '00000000-0000-0000-0000-000000000000'::uuid)
                           = coalesce(cast(:parent_id as uuid), '00000000-0000-0000-0000-000000000000'::uuid)
                       and clave = :clave
                    returning id, parent_id, tipo, nombre, clave, concepto_id,
                              nivel_id, etapa_id, orden, cantidad, ponderacion,
                              modo_cantidad
                    """
                ),
                {
                    "prototipo_id": str(destino_prototipo_id),
                    "parent_id": str(parent_id) if parent_id else None,
                    "clave": clave,
                    "cantidad": cantidad,
                    "modo_cantidad": modo_cantidad,
                },
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def obtener(self, prototipo_nodo_id: UUID) -> dict[str, Any] | None:
        """Un solo nodo por su `id` (`application.puertos.repositorios.
        RepositorioPrototipoNodo.obtener`): resuelve `prototipo_id`,
        `parent_id` y `clave` para que el cuantificador (camino
        "diseño_nuevo") pueda llamar a `actualizar_cantidad`, que identifica
        el nodo por esa terna y no por `id`."""
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select id, prototipo_id, parent_id, tipo, nombre, clave,
                           concepto_id, nivel_id, etapa_id, orden, cantidad,
                           ponderacion, modo_cantidad
                      from prototipo_nodo
                     where org_id = cast(current_setting('app.org_id') as uuid)
                       and id = :id
                    """
                ),
                {"id": str(prototipo_nodo_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None
