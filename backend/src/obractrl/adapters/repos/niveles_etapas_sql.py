"""Repositorio de escritura del catálogo nivel/etapa constructiva (§10.1).

Spec §12.11 (adaptador de persistencia) · §12.4 (RLS).

Primer escritor de `nivel`/`etapa_constructiva` — hasta el cargador de
presupuesto jerárquico, ambas tablas solo se sembraban a mano. Son
catálogo compartido por organización (`uq_nivel_clave`/`uq_etapa_clave`,
`(org_id, clave)`, migración 0005), no por prototipo: la clave se repite
igual en cada prototipo del archivo, así que la primera carga que la trae
define su descripción y las siguientes solo la reutilizan.

El `on conflict ... do update set clave = excluded.clave` es un no-op a
propósito: no cambia ningún dato, solo hace que `returning id` dispare
también cuando la fila ya existía, sin una segunda consulta.

`listar_*`/`crear_*`/`actualizar_*` son para el cargador dedicado
(migración 0037, §10.6): a diferencia de `upsert_*`, sí actualizan la
descripción en cada carga — son el cargador dueño del catálogo, no una
referencia de otro cargador de pasada.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioNivelesEtapasSQL"]


class RepositorioNivelesEtapasSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def upsert_nivel(self, *, clave: str, descripcion: str, orden: int) -> UUID:
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into nivel (org_id, clave, descripcion, orden)
                    values (cast(current_setting('app.org_id') as uuid), :clave, :descripcion, :orden)
                    on conflict (org_id, clave) do update set clave = excluded.clave
                    returning id
                    """
                ),
                {"clave": clave, "descripcion": descripcion, "orden": orden},
            )
        ).scalar_one()

    async def upsert_etapa(
        self, *, clave: str, descripcion: str, nivel_id: UUID | None, orden: int
    ) -> UUID:
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into etapa_constructiva (org_id, nivel_id, clave, descripcion, orden)
                    values (cast(current_setting('app.org_id') as uuid), cast(:nivel_id as uuid),
                            :clave, :descripcion, :orden)
                    on conflict (org_id, clave) do update set clave = excluded.clave
                    returning id
                    """
                ),
                {
                    "nivel_id": str(nivel_id) if nivel_id else None,
                    "clave": clave,
                    "descripcion": descripcion,
                    "orden": orden,
                },
            )
        ).scalar_one()

    # --- CRUD para el cargador dedicado (§10.6) --------------------------

    async def listar_niveles(self) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text("select id, clave, descripcion, orden, importe from nivel order by orden, clave")
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def crear_nivel(self, datos: dict[str, Any]) -> UUID:
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into nivel (org_id, clave, descripcion)
                    values (cast(current_setting('app.org_id') as uuid), :clave, :descripcion)
                    returning id
                    """
                ),
                {"clave": datos["clave"], "descripcion": datos["descripcion"]},
            )
        ).scalar_one()

    async def actualizar_nivel(self, nivel_id: UUID, cambios: dict[str, Any]) -> None:
        if "descripcion" not in cambios:
            return
        await self._sesion.execute(
            text("update nivel set descripcion = :descripcion where id = :id"),
            {"id": str(nivel_id), "descripcion": cambios["descripcion"]},
        )

    async def listar_etapas(self) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    "select id, nivel_id, frente_id, clave, descripcion, orden, "
                    "       ponderacion, importe "
                    "from etapa_constructiva order by orden, clave"
                )
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def crear_etapa(self, datos: dict[str, Any]) -> UUID:
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into etapa_constructiva (org_id, clave, descripcion)
                    values (cast(current_setting('app.org_id') as uuid), :clave, :descripcion)
                    returning id
                    """
                ),
                {"clave": datos["clave"], "descripcion": datos["descripcion"]},
            )
        ).scalar_one()

    async def actualizar_etapa(self, etapa_id: UUID, cambios: dict[str, Any]) -> None:
        if "descripcion" not in cambios:
            return
        await self._sesion.execute(
            text("update etapa_constructiva set descripcion = :descripcion where id = :id"),
            {"id": str(etapa_id), "descripcion": cambios["descripcion"]},
        )

    async def asignar_nivel(self, etapa_id: UUID, nivel_id: UUID | None) -> None:
        """A qué nivel pertenece esta etapa (§7.4).

        `derivar_nivel_desde_arbol` resuelve las que el prototipo usa; esto
        cierra las que ningún prototipo toca todavía y que por eso no tienen de
        dónde derivarse. Sin nivel, la etapa no cae en ninguna tarjeta cuando el
        residente mira su obra agrupada por nivel.

        `None` lo quita: corregir un nivel mal puesto es tan válido como
        ponerlo, y omitir el campo no podría expresarlo.
        """
        await self._sesion.execute(
            text(
                "update etapa_constructiva set nivel_id = cast(:nivel_id as uuid) "
                "where id = cast(:id as uuid)"
            ),
            {"id": str(etapa_id), "nivel_id": str(nivel_id) if nivel_id else None},
        )

    async def asignar_frente(
        self, *, frente_id: UUID, etapa_ids: Sequence[UUID]
    ) -> None:
        """Deja ese frente con **exactamente** esas etapas (§8.3, 0045).

        Es un reemplazo y no un alta: primero suelta las que tenía y luego toma
        las que llegan. Así una etapa que se quitó de la lista queda sin frente
        en vez de arrastrarse, y la pantalla no necesita mandar dos llamadas
        para mover una etapa de un frente a otro.

        Una etapa pertenece a un frente y solo a uno, así que tomarla aquí la
        quita del frente en el que estuviera — sin eso, su trabajo se contaría
        dos veces al planear cuántas cuadrillas hacen falta.
        """
        await self._sesion.execute(
            text(
                "update etapa_constructiva set frente_id = null "
                "where frente_id = cast(:frente_id as uuid)"
            ),
            {"frente_id": str(frente_id)},
        )
        if not etapa_ids:
            return
        await self._sesion.execute(
            text(
                "update etapa_constructiva set frente_id = cast(:frente_id as uuid) "
                "where id = any(cast(:etapas as uuid[]))"
            ),
            {"frente_id": str(frente_id), "etapas": [str(e) for e in etapa_ids]},
        )

    async def asignar_frente_por_clave(
        self, *, frente_id: UUID | None, claves: list[str]
    ) -> int:
        """Le pone ese frente a las etapas de la lista, buscándolas por clave.

        La variante que usa el cargador. Por clave y no por id porque quien las
        trae es el archivo (§3.3: la clave manda), y resolver a id fila por fila
        serían cincuenta idas a la base para el mismo catálogo.

        A diferencia de `asignar_frente`, **no** suelta las etapas que el frente
        ya tenía: aquí cada etapa llega con su frente escrito al lado, así que
        lo que manda es la fila y no la lista. Soltar de más borraría el mapeo
        de una etapa que este archivo ni menciona.
        """
        return (
            await self._sesion.execute(
                text(
                    """
                    update etapa_constructiva
                       set frente_id = cast(:frente_id as uuid)
                     where clave = any(cast(:claves as text[]))
                    """
                ),
                {
                    "frente_id": str(frente_id) if frente_id else None,
                    "claves": claves,
                },
            )
        ).rowcount

    async def derivar_nivel_desde_arbol(self) -> int:
        """Le pone a cada etapa el nivel del que cuelga en el árbol WBS (§7.4).

        `etapa_constructiva.nivel_id` nació vacío: el catálogo de etapas del
        §10.1 no trae a qué nivel pertenece cada una —su columna `TIPO` es la
        clasificación del exportador, no una referencia— y asumirlo sería
        inventar una relación que el archivo no da (§3.3).

        Pero el **árbol del prototipo sí la da**: `prototipo_nodo` cuelga cada
        etapa de su nivel, y eso lo capturó una persona al armar la ingeniería.
        Derivarlo de ahí no es adivinar, es leer lo que ya está dicho.

        Es lo que deja agrupar la obra por nivel —cimentación, planta baja,
        azotea— que es como el residente la mira: sin esto, sus actividades solo
        se pueden agrupar por el tipo de contratación, que le dice a quién se le
        compra y no qué se está construyendo.

        Solo llena lo que está vacío: una etapa que alguien movió a mano no se
        pisa. Y solo cuando el árbol es **unánime** —`having count(distinct) = 1`—
        porque una etapa colgada de dos niveles distintos en dos prototipos no
        tiene un nivel que derivar, y elegir uno al azar sería peor que dejarla.
        """
        return (
            await self._sesion.execute(
                text(
                    """
                    with del_arbol as (
                      -- El `having` de abajo garantiza que hay uno solo,
                      -- así que el primero del arreglo ES el nivel.
                      -- (Postgres no tiene `min(uuid)`.)
                      select pe.etapa_id,
                             (array_agg(distinct pn.nivel_id))[1] as nivel_id
                        from prototipo_nodo pe
                        join prototipo_nodo pn on pn.id = pe.parent_id
                       where pe.etapa_id is not null
                         and pn.nivel_id is not null
                       group by pe.etapa_id
                      having count(distinct pn.nivel_id) = 1
                    )
                    update etapa_constructiva e
                       set nivel_id = d.nivel_id
                      from del_arbol d
                     where d.etapa_id = e.id
                       and e.nivel_id is null
                    """
                )
            )
        ).rowcount
