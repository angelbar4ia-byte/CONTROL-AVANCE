"""Lo que hace falta para armar el árbol de una obra (nivel → etapa → partida) y cambiar la unidad de un concepto.

Lecturas y escrituras chicas que ningún repositorio existente cubre; `RepositorioPartesSQL` pone la actividad nueva.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class RepositorioArbolSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def nivel_por_clave(self, clave: str) -> UUID | None:
        return (
            await self._sesion.execute(
                text("select id from nivel where clave = :c"), {"c": clave}
            )
        ).scalar()

    async def etapa_por_clave(self, clave: str) -> UUID | None:
        return (
            await self._sesion.execute(
                text("select id from etapa_constructiva where clave = :c"), {"c": clave}
            )
        ).scalar()

    async def nivel_existe(self, nivel_id: UUID) -> bool:
        return bool(
            (
                await self._sesion.execute(
                    text("select 1 from nivel where id = :i"), {"i": str(nivel_id)}
                )
            ).scalar()
        )

    async def crear_nivel(self, *, clave: str, descripcion: str) -> UUID:
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into nivel (org_id, clave, descripcion, orden)
                    values (cast(current_setting('app.org_id') as uuid), :clave, :descripcion,
                            coalesce((select max(orden) + 1 from nivel), 0))
                    returning id
                    """
                ),
                {"clave": clave, "descripcion": descripcion},
            )
        ).scalar_one()

    async def crear_etapa(self, *, nivel_id: UUID, clave: str, descripcion: str) -> UUID:
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into etapa_constructiva (org_id, nivel_id, clave, descripcion, orden)
                    values (cast(current_setting('app.org_id') as uuid), :nivel, :clave, :descripcion,
                            coalesce((select max(orden) + 1 from etapa_constructiva where nivel_id = :nivel), 0))
                    returning id
                    """
                ),
                {"nivel": str(nivel_id), "clave": clave, "descripcion": descripcion},
            )
        ).scalar_one()

    async def etapa(self, etapa_id: UUID) -> dict[str, Any] | None:
        fila = (
            (
                await self._sesion.execute(
                    text(
                        "select id, nivel_id, clave from etapa_constructiva where id = :i"
                    ),
                    {"i": str(etapa_id)},
                )
            )
            .mappings()
            .first()
        )
        return dict(fila) if fila else None

    async def unidad(self, unidad_id: UUID) -> dict[str, Any] | None:
        fila = (
            (
                await self._sesion.execute(
                    text("select id, clave, nombre from unidad where id = :i"),
                    {"i": str(unidad_id)},
                )
            )
            .mappings()
            .first()
        )
        return dict(fila) if fila else None

    async def concepto(self, concepto_id: UUID) -> dict[str, Any] | None:
        fila = (
            (
                await self._sesion.execute(
                    text(
                        """
                    select c.id, c.clave, c.descripcion, c.unidad_id, u.clave as unidad_clave
                      from concepto c left join unidad u on u.id = c.unidad_id
                     where c.id = :i
                    """
                    ),
                    {"i": str(concepto_id)},
                )
            )
            .mappings()
            .first()
        )
        return dict(fila) if fila else None

    async def poner_unidad(self, concepto_id: UUID, unidad_id: UUID) -> None:
        await self._sesion.execute(
            text("update concepto set unidad_id = :u where id = :c"),
            {"u": str(unidad_id), "c": str(concepto_id)},
        )

    async def medidas_vigentes_del_concepto(self, concepto_id: UUID) -> list[str]:
        """Con qué medidas de trazo está midiendo hoy el concepto (en cualquier obra)."""
        filas = (
            (
                await self._sesion.execute(
                    text(
                        """
                    select distinct e.medida::text
                      from enlace_cuantificacion e
                      join actividad a on a.id = e.actividad_id
                     where a.concepto_id = :c and e.vigente
                    """
                    ),
                    {"c": str(concepto_id)},
                )
            )
            .scalars()
            .all()
        )
        return list(filas)

    async def partida_repetida(
        self, obra_id: UUID, concepto_id: UUID, etapa_id: UUID | None
    ) -> bool:
        return bool(
            (
                await self._sesion.execute(
                    text(
                        """
                        select 1 from actividad
                         where obra_id = :o and concepto_id = :c and etapa_id is not distinct from cast(:e as uuid)
                         limit 1
                        """
                    ),
                    {
                        "o": str(obra_id),
                        "c": str(concepto_id),
                        "e": str(etapa_id) if etapa_id else None,
                    },
                )
            ).scalar()
        )

    async def precio_vigente(self, concepto_id: UUID) -> tuple[Any, Any]:
        fila = (
            await self._sesion.execute(
                text(
                    "select precio_unitario, precio_destajo from cpu "
                    "where concepto_id = :c and vigente order by version desc limit 1"
                ),
                {"c": str(concepto_id)},
            )
        ).first()
        return (fila[0], fila[1]) if fila else (0, 0)

    async def actividad(self, actividad_id: UUID) -> dict[str, Any] | None:
        fila = (
            (
                await self._sesion.execute(
                    text(
                        """
                    select id, obra_id, concepto_id, nivel_id, etapa_id, cant_ejecutada, parte_independiente
                      from actividad where id = :i
                    """
                    ),
                    {"i": str(actividad_id)},
                )
            )
            .mappings()
            .first()
        )
        return dict(fila) if fila else None

    async def hermanas_de_la_partida(self, actividad_id: UUID) -> list[UUID] | None:
        """Las partidas de la misma obra y etapa, en el orden en que se ven: por su lugar guardado y, sin él, por clave.
        `None` si la base aún no tiene la columna `orden` (0116)."""
        hay = (
            await self._sesion.execute(
                text(
                    "select exists (select 1 from information_schema.columns where table_schema = 'public' "
                    "and table_name = 'actividad' and column_name = 'orden')"
                )
            )
        ).scalar_one()
        if not hay:
            return None
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select h.id
                      from actividad a
                      join actividad h on h.obra_id = a.obra_id and h.etapa_id is not distinct from a.etapa_id
                      left join concepto c on c.id = h.concepto_id
                     where a.id = :i
                     order by h.orden nulls last, c.clave nulls last, h.created_at, h.id
                    """
                ),
                {"i": str(actividad_id)},
            )
        ).all()
        return [UUID(str(f[0])) for f in filas]

    async def fijar_ordenes(self, ids: list[UUID]) -> None:
        for n, i in enumerate(ids, start=1):
            await self._sesion.execute(text("update actividad set orden = :o where id = :i"), {"o": n, "i": str(i)})

    async def mover_actividad(
        self, actividad_id: UUID, *, nivel_id: UUID | None, etapa_id: UUID | None
    ) -> None:
        await self._sesion.execute(
            text(
                "update actividad set nivel_id = cast(:n as uuid), etapa_id = cast(:e as uuid) where id = :i"
            ),
            {
                "n": str(nivel_id) if nivel_id else None,
                "e": str(etapa_id) if etapa_id else None,
                "i": str(actividad_id),
            },
        )

    async def motivo_para_no_quitar(self, actividad_id: UUID) -> str | None:
        """Por qué una partida no se puede quitar sin perder trabajo ajeno; `None` si se puede."""
        fila = (
            (
                await self._sesion.execute(
                    text(
                        """
                    select
                      exists (select 1 from enlace_cuantificacion
                               where actividad_id = :i and vigente) as trazos,
                      exists (select 1 from estimacion_concepto where actividad_id = :i) as estimada,
                      exists (select 1 from control_cambio_linea where sustituye_a = :i) as sustituida
                    """
                    ),
                    {"i": str(actividad_id)},
                )
            )
            .mappings()
            .one()
        )
        if fila["trazos"]:
            return "La partida tiene trazos medidos: bórralos antes de quitarla."
        if fila["estimada"]:
            return "La partida ya está en una estimación: no se quita."
        if fila["sustituida"]:
            return "Un control de cambio sustituye a esta partida: no se quita."
        return None

    async def quitar_actividad(self, actividad_id: UUID) -> None:
        await self._sesion.execute(
            text("delete from actividad where id = :i"), {"i": str(actividad_id)}
        )

    async def ajustar_nivel(self, nivel_id: UUID, *, descripcion: str | None, orden: int | None) -> bool:
        r = await self._sesion.execute(
            text(
                "update nivel set descripcion = coalesce(:d, descripcion), orden = coalesce(:o, orden) where id = :i"
            ),
            {"i": str(nivel_id), "d": descripcion, "o": orden},
        )
        return bool(r.rowcount)

    async def ajustar_etapa(self, etapa_id: UUID, *, descripcion: str | None, orden: int | None) -> bool:
        r = await self._sesion.execute(
            text(
                "update etapa_constructiva set descripcion = coalesce(:d, descripcion), orden = coalesce(:o, orden) "
                "where id = :i"
            ),
            {"i": str(etapa_id), "d": descripcion, "o": orden},
        )
        return bool(r.rowcount)
