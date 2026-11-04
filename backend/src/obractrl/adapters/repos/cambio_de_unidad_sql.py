"""SQL del cambio de unidad de un concepto (migración 0106, D-623). RLS por organización."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioCambioDeUnidadSQL"]

_COLUMNAS = """id, concepto_id, concepto_nuevo_id, unidad_anterior_id, unidad_nueva_id, tipo_anterior, tipo_nuevo,
               equivalencia, origen_equivalencia, estado, created_at, resuelto_en"""


class RepositorioCambioDeUnidadSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    # --- propuestas -------------------------------------------------------------------------------------------

    async def obtener(self, cambio_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} from cambio_de_unidad where id = :id"), {"id": str(cambio_id)}
            )
        ).mappings().first()
        return dict(fila) if fila else None

    async def pendiente_del_concepto(self, concepto_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(
                    f"select {_COLUMNAS} from cambio_de_unidad "
                    "where concepto_id = :c and estado = 'propuesto' order by created_at desc limit 1"
                ),
                {"c": str(concepto_id)},
            )
        ).mappings().first()
        return dict(fila) if fila else None

    async def crear(
        self,
        *,
        concepto_id: UUID,
        unidad_anterior_id: UUID | None,
        unidad_nueva_id: UUID,
        tipo_anterior: str | None,
        tipo_nuevo: str,
        equivalencia: Decimal | None,
        origen: str | None,
        autor_id: UUID,
    ) -> UUID:
        nuevo = (
            await self._sesion.execute(
                text(
                    """
                    insert into cambio_de_unidad
                        (org_id, concepto_id, unidad_anterior_id, unidad_nueva_id, tipo_anterior, tipo_nuevo,
                         equivalencia, origen_equivalencia, propuesto_por)
                    values (app.current_org_id(), :c, cast(:ua as uuid), :un, :ta, :tn, :eq, :origen, :autor)
                    returning id
                    """
                ),
                {
                    "c": str(concepto_id),
                    "ua": str(unidad_anterior_id) if unidad_anterior_id else None,
                    "un": str(unidad_nueva_id),
                    "ta": tipo_anterior,
                    "tn": tipo_nuevo,
                    "eq": equivalencia,
                    "origen": origen,
                    "autor": str(autor_id),
                },
            )
        ).scalar_one()
        return UUID(str(nuevo))

    async def teclear_equivalencia(self, cambio_id: UUID, equivalencia: Decimal) -> None:
        await self._sesion.execute(
            text("update cambio_de_unidad set equivalencia = :e, origen_equivalencia = 'tecleada' where id = :id"),
            {"e": equivalencia, "id": str(cambio_id)},
        )

    async def resolver(self, cambio_id: UUID, *, estado: str, usuario_id: UUID, concepto_nuevo_id: UUID | None) -> None:
        await self._sesion.execute(
            text(
                "update cambio_de_unidad set estado = :e, resuelto_por = :u, resuelto_en = now(), "
                "concepto_nuevo_id = cast(:n as uuid) where id = :id"
            ),
            {"e": estado, "u": str(usuario_id), "n": str(concepto_nuevo_id) if concepto_nuevo_id else None, "id": str(cambio_id)},
        )

    # --- la equivalencia sugerida: lo que dice el destajo del concepto --------------------------------------

    async def equivalencia_del_destajo(self, concepto_id: UUID, unidad_nueva_id: UUID) -> Decimal | None:
        """La cantidad del destajo (o subcontrato) de la matriz del concepto cuya unidad es la nueva: los «48 m²» de una pieza."""
        valor = (
            await self._sesion.execute(
                text(
                    """
                    select sum(e.cantidad)
                      from explosion e
                      join cpu p on p.id = e.cpu_id and p.vigente
                      join concepto h on h.id = e.concepto_hijo_id
                     where e.concepto_id = :c and e.tipo_hijo = 'concepto'
                       and e.categoria in ('destajo', 'subcontrato') and h.unidad_id = :u and e.cantidad > 0
                    """
                ),
                {"c": str(concepto_id), "u": str(unidad_nueva_id)},
            )
        ).scalar_one()
        return Decimal(str(valor)) if valor is not None else None

    # --- partidas ------------------------------------------------------------------------------------------

    async def partidas_del_concepto(self, concepto_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    "select id, obra_id, etapa_id, cant_base, cant_ejecutada from actividad where concepto_id = :c"
                ),
                {"c": str(concepto_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def pasar_partida(self, actividad_id: UUID, concepto_nuevo_id: UUID, divisor: Decimal) -> None:
        """La partida se va al concepto nuevo; su cantidad base se multiplica por el divisor (1 pza = 48 m²) y su precio se divide."""
        await self._sesion.execute(
            text(
                """
                update actividad set concepto_id = :n,
                       cant_base = round(cant_base * :d, 6),
                       cant_programada = round(cant_programada * :d, 6),
                       precio_unitario = round(precio_unitario / :d, 4),
                       precio_destajo = round(precio_destajo / :d, 4)
                 where id = :a
                """
            ),
            {"n": str(concepto_nuevo_id), "d": divisor, "a": str(actividad_id)},
        )

    # --- la versión del concepto -----------------------------------------------------------------------------

    async def clonar_concepto(self, concepto_id: UUID, unidad_nueva_id: UUID, sufijo: str, divisor: Decimal) -> UUID:
        """Crea el concepto nuevo (una versión con la unidad nueva): su receta es la del vigente con las cantidades ÷ `divisor`."""
        sesion = self._sesion
        origen = (
            await sesion.execute(
                text("select clave, descripcion, tipo, familia_id from concepto where id = :c"), {"c": str(concepto_id)}
            )
        ).mappings().one()
        clave = f"{origen['clave']}-{sufijo}"
        n = 1
        while (await sesion.execute(text("select 1 from concepto where clave = :k"), {"k": clave})).first() is not None:
            n += 1
            clave = f"{origen['clave']}-{sufijo}{n}"
        nuevo = UUID(
            str(
                (
                    await sesion.execute(
                        text(
                            """
                            insert into concepto (org_id, tipo, clave, descripcion, unidad_id, familia_id)
                            values (app.current_org_id(), :tipo, :clave, :desc, :u, cast(:f as uuid)) returning id
                            """
                        ),
                        {
                            "tipo": origen["tipo"],
                            "clave": clave,
                            "desc": origen["descripcion"],
                            "u": str(unidad_nueva_id),
                            "f": str(origen["familia_id"]) if origen["familia_id"] else None,
                        },
                    )
                ).scalar_one()
            )
        )
        cpu = (
            await sesion.execute(
                text(
                    "select id, precio_unitario, precio_destajo from cpu "
                    "where concepto_id = :c and vigente and variante is null"
                ),
                {"c": str(concepto_id)},
            )
        ).mappings().first()
        if cpu is not None:
            nuevo_cpu = (
                await sesion.execute(
                    text(
                        """
                        insert into cpu (org_id, concepto_id, version, precio_unitario, precio_destajo, vigente)
                        values (app.current_org_id(), :n, 1, round(cast(:pu as numeric) / cast(:d as numeric), 4), round(cast(:pd as numeric) / cast(:d as numeric), 4), true) returning id
                        """
                    ),
                    {"n": str(nuevo), "pu": cpu["precio_unitario"], "pd": cpu["precio_destajo"], "d": divisor},
                )
            ).scalar_one()
            # Las cantidades se convierten; el costo unitario de cada insumo no cambia, así que el importe sigue a la cantidad.
            await sesion.execute(
                text(
                    """
                    insert into explosion (org_id, concepto_id, cpu_id, tipo_hijo, insumo_id, concepto_hijo_id, categoria,
                                           cantidad, rendimiento, costo_unitario, importe, orden)
                    select org_id, :n, :cpu, tipo_hijo, insumo_id, concepto_hijo_id, categoria,
                           round(cantidad / :d, 6), rendimiento, costo_unitario, round(importe / :d, 4), orden
                      from explosion where cpu_id = :viejo
                    """
                ),
                {"n": str(nuevo), "cpu": str(nuevo_cpu), "viejo": str(cpu["id"]), "d": divisor},
            )
            await sesion.execute(
                text(
                    "insert into version_concepto (org_id, concepto_id, version, pu) "
                    "values (app.current_org_id(), :n, 1, round(cast(:pu as numeric) / cast(:d as numeric), 4))"
                ),
                {"n": str(nuevo), "pu": cpu["precio_unitario"], "d": divisor},
            )
        return nuevo

    # --- los enlaces de los trazos ----------------------------------------------------------------------------

    async def enlaces_a_rehacer(self, actividad_id: UUID) -> list[dict[str, Any]]:
        """Los enlaces vigentes directos de la partida (los de una medición asignada conservan su medida)."""
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select e.id, e.trazo_id, e.medida::text as medida, e.factor,
                           case ST_GeometryType(t.geometria) when 'ST_Point' then 'punto'
                                when 'ST_LineString' then 'linea' else 'area' end as geometria,
                           t.grosor_m is not null as con_grosor
                      from enlace_cuantificacion e join trazo t on t.id = e.trazo_id
                     where e.actividad_id = :a and e.vigente and e.matriz_concepto_id is null and e.asignacion_id is null
                    """
                ),
                {"a": str(actividad_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def retirar_enlace(self, enlace_id: UUID) -> None:
        await self._sesion.execute(
            text("update enlace_cuantificacion set vigente = false where id = :id"), {"id": str(enlace_id)}
        )

    async def enlazar(self, *, trazo_id: UUID, actividad_id: UUID, medida: str, factor: Decimal) -> UUID:
        nuevo = (
            await self._sesion.execute(
                text(
                    """
                    insert into enlace_cuantificacion (org_id, trazo_id, tipo_nodo, actividad_id, medida, factor, vigente)
                    values (app.current_org_id(), :t, 'actividad', :a, cast(:m as medida_cuantificacion), :f, true)
                    returning id
                    """
                ),
                {"t": str(trazo_id), "a": str(actividad_id), "m": medida, "f": factor},
            )
        ).scalar_one()
        return UUID(str(nuevo))

    async def marcar_enlace(
        self,
        *,
        cambio_id: UUID,
        trazo_id: UUID,
        viejo: UUID,
        nuevo: UUID | None,
        medida_vieja: str,
        medida_nueva: str | None,
        nota: str | None,
    ) -> None:
        await self._sesion.execute(
            text(
                """
                insert into cambio_de_unidad_enlace
                    (org_id, cambio_id, trazo_id, enlace_viejo_id, enlace_nuevo_id, medida_vieja, medida_nueva, nota)
                values (app.current_org_id(), :c, :t, :v, cast(:n as uuid), :mv, :mn, :nota)
                """
            ),
            {
                "c": str(cambio_id), "t": str(trazo_id), "v": str(viejo), "n": str(nuevo) if nuevo else None,
                "mv": medida_vieja, "mn": medida_nueva, "nota": nota,
            },
        )

    async def marcas_del_trazo(self, trazo_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select m.enlace_viejo_id, m.enlace_nuevo_id, m.medida_vieja, m.medida_nueva, m.nota,
                           c.tipo_anterior, c.tipo_nuevo, c.equivalencia, c.resuelto_en,
                           ua.clave as unidad_anterior, un.clave as unidad_nueva
                      from cambio_de_unidad_enlace m
                      join cambio_de_unidad c on c.id = m.cambio_id
                      left join unidad ua on ua.id = c.unidad_anterior_id
                      join unidad un on un.id = c.unidad_nueva_id
                     where m.trazo_id = :t order by c.resuelto_en nulls last, m.id
                    """
                ),
                {"t": str(trazo_id)},
            )
        ).mappings().all()
        return [dict(f) for f in filas]
