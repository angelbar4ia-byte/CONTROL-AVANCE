"""SQL de los espacios de una obra (migración 0143). RLS por organización; solo Control de obra escribe la estructura."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.domain.cuantificacion.espacios import ErrorDeEspacio

__all__ = ["RepositorioEspaciosSQL"]

_SELECCION = """
    select e.id, e.obra_id, e.nombre, e.tipo, e.nivel_id, e.area_m2, e.orden,
           (select count(*) from trazo t where (t.espacio_id = e.id or t.espacio_comparte_id = e.id)
               and geometrytype(t.geometria) = 'LINESTRING' and t.hueco_de is null) as muros,
           (select count(*) from trazo t where t.espacio_id = e.id and t.losa_zona_id is not null) as losas,
           (select count(*) from losa_elemento l where l.espacio_id = e.id) as elementos,
           coalesce((select array_agg(n.prototipo_nodo_id order by n.created_at, n.id) from espacio_nodo n where n.espacio_id = e.id), '{}') as nodos
      from espacio e
"""


class RepositorioEspaciosSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def obra_visible(self, obra_id: UUID) -> bool:
        fila = (await self._sesion.execute(text("select 1 from obra where id = :o"), {"o": str(obra_id)})).first()
        return fila is not None

    async def listar(self, obra_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(text(_SELECCION + " where e.obra_id = :o order by e.orden, lower(e.nombre), e.id"), {"o": str(obra_id)})
        ).mappings().all()
        return [dict(f) for f in filas]

    async def uno(self, espacio_id: UUID) -> dict[str, Any] | None:
        fila = (await self._sesion.execute(text(_SELECCION + " where e.id = :e"), {"e": str(espacio_id)})).mappings().first()
        return dict(fila) if fila else None

    async def crear(self, *, obra_id: UUID, datos: dict[str, Any], autor_id: UUID) -> UUID:
        try:
            async with self._sesion.begin_nested():
                nuevo = (
                    await self._sesion.execute(
                        text(
                            """
                            insert into espacio (org_id, obra_id, nombre, tipo, nivel_id, area_m2, orden, autor_id)
                            select app.current_org_id(), :o, :nombre, :tipo, cast(:nivel as uuid), :area,
                                   coalesce((select max(orden) + 1 from espacio where obra_id = :o), 0), :autor
                            returning id
                            """
                        ),
                        self._valores(datos) | {"o": str(obra_id), "autor": str(autor_id)},
                    )
                ).scalar_one()
        except IntegrityError as e:
            raise self._conflicto(e, datos["nombre"]) from e
        return UUID(str(nuevo))

    async def actualizar(self, espacio_id: UUID, datos: dict[str, Any]) -> None:
        try:
            async with self._sesion.begin_nested():
                await self._sesion.execute(
                    text("update espacio set nombre = :nombre, tipo = :tipo, nivel_id = cast(:nivel as uuid), area_m2 = :area where id = :e"),
                    self._valores(datos) | {"e": str(espacio_id)},
                )
        except IntegrityError as e:
            raise self._conflicto(e, datos["nombre"]) from e

    @staticmethod
    def _valores(d: dict[str, Any]) -> dict[str, Any]:
        return {"nombre": d["nombre"], "tipo": d["tipo"], "nivel": str(d["nivel_id"]) if d.get("nivel_id") else None, "area": d["area_m2"]}

    @staticmethod
    def _conflicto(error: IntegrityError, nombre: str) -> ErrorDeEspacio:
        texto = str(error.orig)
        if "ux_espacio_nombre" in texto:
            return ErrorDeEspacio(f"Ya hay un espacio llamado «{nombre}» en esta obra.")
        if "espacio_nivel_id_fkey" in texto:
            return ErrorDeEspacio("El nivel no existe.")
        return ErrorDeEspacio("Los datos del espacio no valen.")

    async def eliminar(self, espacio_id: UUID) -> None:
        # Lo asignado al espacio queda sin espacio (las claves foráneas lo sueltan); sus ramas del árbol vuelven a ser generales.
        await self._sesion.execute(text("delete from espacio where id = :e"), {"e": str(espacio_id)})

    async def nodos_de_la_obra(self, obra_id: UUID, nodo_ids: list[UUID]) -> list[UUID]:
        if not nodo_ids:
            return []
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select n.id from prototipo_nodo n join obra o on o.prototipo_id = n.prototipo_id
                     where o.id = :o and n.id = any(cast(:ids as uuid[]))
                    """
                ),
                {"o": str(obra_id), "ids": [str(i) for i in nodo_ids]},
            )
        ).scalars().all()
        return [UUID(str(i)) for i in filas]

    async def fijar_nodos(self, *, obra_id: UUID, espacio_id: UUID, nodo_ids: list[UUID]) -> None:
        await self._sesion.execute(text("delete from espacio_nodo where espacio_id = :e"), {"e": str(espacio_id)})
        for nodo in nodo_ids:
            # Un nodo pertenece a lo más a un espacio por obra: si estaba en otro, pasa a este.
            await self._sesion.execute(
                text("delete from espacio_nodo where obra_id = :o and prototipo_nodo_id = :n"), {"o": str(obra_id), "n": str(nodo)}
            )
            await self._sesion.execute(
                text(
                    "insert into espacio_nodo (org_id, obra_id, espacio_id, prototipo_nodo_id) "
                    "values (app.current_org_id(), :o, :e, :n)"
                ),
                {"o": str(obra_id), "e": str(espacio_id), "n": str(nodo)},
            )

    async def trazo(self, trazo_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select t.id, p.obra_id, geometrytype(t.geometria) as tipo, t.hueco_de,
                           t.espacio_id, t.espacio_comparte_id, t.espacio_reparto_pct
                      from trazo t join plano p on p.id = t.plano_id where t.id = :t
                    """
                ),
                {"t": str(trazo_id)},
            )
        ).mappings().first()
        return dict(fila) if fila else None

    async def fijar_espacio_de_trazo(
        self, trazo_id: UUID, espacio_id: UUID | None, comparte_id: UUID | None, reparto_pct: Any
    ) -> None:
        await self._sesion.execute(
            text(
                "update trazo set espacio_id = cast(:e as uuid), espacio_comparte_id = cast(:c as uuid), espacio_reparto_pct = :p where id = :t"
            ),
            {
                "e": str(espacio_id) if espacio_id else None, "c": str(comparte_id) if comparte_id else None,
                "p": reparto_pct, "t": str(trazo_id),
            },
        )
