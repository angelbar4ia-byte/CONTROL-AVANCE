"""Repositorio de conceptos, su explosión y sus versiones de CPU.

Spec §12.11 (adaptador de persistencia) · §7.3 (APU) · §10.1 (catálogo de
conceptos con composición y versión) · §10.8 (versionado) · §3.3 (la CLAVE
manda) · §12.4 (RLS).

`concepto`, `explosion` y `cpu` están en el bloque A de `rls_policies`
(`database/migrations/20260814000012`): lectura para toda la organización,
escritura solo para `app.es_config()`. `org_id` en los INSERT sale de
`current_setting('app.org_id')`.

**El repositorio no calcula el CPU.** Solo trae la materia prima —las filas
de `Explosion` de todo concepto alcanzable, con sus claves ya resueltas— y el
dominio (`domain.catalogos.apu`) hace la recursión, la detección de ciclos y
la aritmética. Es la misma división que con el CPM: SQL trae el grafo, el
dominio lo recorre.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioConceptosSQL"]

_COLUMNAS = """
    id, tipo, clave, descripcion, unidad_id, familia_id, estatus
"""

_PROFUNDIDAD_MAXIMA = 32
"""Espeja `domain.catalogos.apu._PROFUNDIDAD_MAXIMA`.

El corte de aquí es solo para que un catálogo mal cargado no haga trabajar de
más al motor recursivo; quien reporta el problema —ciclo o anidamiento
absurdo— es el dominio, con un error legible.
"""

_ALCANCE = f"""
    with recursive alcance as (
        select cast(:id as uuid) as concepto_id,
               array[cast(:id as uuid)] as camino
        union all
        select e.concepto_hijo_id, a.camino || e.concepto_hijo_id
        from explosion e
        join alcance a on e.concepto_id = a.concepto_id
        where e.tipo_hijo = 'concepto'
          and e.concepto_hijo_id is not null
          -- Corta el ciclo para que el CTE termine; la arista que lo cierra
          -- SÍ sale en el resultado (el padre ya está en `alcance`), y es el
          -- dominio quien la reporta como `CicloEnExplosion` (§7.3).
          and not (e.concepto_hijo_id = any(a.camino))
          and cardinality(a.camino) <= {_PROFUNDIDAD_MAXIMA}
    )
"""


class RepositorioConceptosSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def crear(self, datos: dict[str, Any]) -> UUID:
        """Alta de concepto (§11.2 `POST /conceptos`, rol C).

        Claves esperadas: ``tipo``, ``clave`` y ``descripcion``, ya
        normalizados por `domain.catalogos.reglas.Concepto`. Opcionales:
        ``unidad_id``, ``familia_id``.
        """
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into concepto
                        (org_id, tipo, clave, descripcion, unidad_id, familia_id)
                    values (cast(current_setting('app.org_id') as uuid),
                            cast(:tipo as tipo_concepto), :clave, :descripcion,
                            cast(:unidad_id as uuid), cast(:familia_id as uuid))
                    returning id
                    """
                ),
                {
                    "tipo": datos["tipo"],
                    "clave": datos["clave"],
                    "descripcion": datos["descripcion"],
                    "unidad_id": (
                        str(datos["unidad_id"]) if datos.get("unidad_id") else None
                    ),
                    "familia_id": (
                        str(datos["familia_id"]) if datos.get("familia_id") else None
                    ),
                },
            )
        ).scalar_one()

    async def obtener(self, concepto_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} from concepto where id = :id"),
                {"id": str(concepto_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def listar(
        self,
        *,
        tipo: str | None = None,
        familia_id: UUID | None = None,
        solo_activos: bool = True,
    ) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS}
                    from concepto
                    -- El cast del lado `is null` fija el tipo del parámetro;
                    -- sin él asyncpg levanta AmbiguousParameterError.
                    where (cast(:tipo as tipo_concepto) is null
                           or tipo = cast(:tipo as tipo_concepto))
                      and (cast(:familia_id as uuid) is null
                           or familia_id = cast(:familia_id as uuid))
                      and (not cast(:solo_activos as boolean) or estatus = 'activo')
                    order by clave
                    """
                ),
                {
                    "tipo": tipo,
                    "familia_id": str(familia_id) if familia_id else None,
                    "solo_activos": solo_activos,
                },
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def composicion_recursiva(self, concepto_id: UUID) -> list[dict[str, Any]]:
        """Filas de `Explosion` de todo concepto alcanzable desde la raíz (§7.3).

        Las claves vienen resueltas porque el dominio explota por CLAVE
        (§3.3). ``costo_insumo_vigente`` es el costo del catálogo
        (`costo_base_actualizado` = costo vigente, y `costo_base` como
        respaldo, §10.1); lo usa el dominio cuando la fila del APU no trae PU
        propio (columna F del archivo, §10.6).

        **Qué filas cuentan (§10.8):** una fila sin `cpu_id` es la composición
        viva del concepto; una con `cpu_id` pertenece a la versión que la
        coteó. Se leen ambas mientras esa versión sea la **vigente**; las
        filas de versiones retiradas quedan en el histórico y no entran al
        cálculo.
        """
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    {_ALCANCE}
                    select
                        padre.clave                as concepto_clave,
                        e.tipo_hijo                as tipo_hijo,
                        e.categoria                as categoria,
                        e.cantidad                 as cantidad,
                        e.rendimiento              as rendimiento,
                        e.costo_unitario           as costo_unitario,
                        e.orden                    as orden,
                        i.clave                    as insumo_clave,
                        coalesce(i.costo_base_actualizado, i.costo_base)
                                                   as costo_insumo_vigente,
                        hijo.clave                 as concepto_hijo_clave
                    from explosion e
                    join concepto padre on padre.id = e.concepto_id
                    left join insumo   i    on i.id    = e.insumo_id
                    left join concepto hijo on hijo.id = e.concepto_hijo_id
                    where e.concepto_id in (select concepto_id from alcance)
                      and (e.cpu_id is null
                           or e.cpu_id in (select id from cpu where vigente))
                    order by padre.clave, e.orden, e.id
                    """
                ),
                {"id": str(concepto_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def versiones_cpu(self, concepto_id: UUID) -> list[dict[str, Any]]:
        """Historial de CPU del concepto, todas sus variantes (§7.3, §10.8)."""
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select id, concepto_id, version, variante, precio_unitario,
                           precio_destajo, vigente, created_at
                    from cpu
                    where concepto_id = :id
                    order by coalesce(variante, ''), version
                    """
                ),
                {"id": str(concepto_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def publicar_version_cpu(
        self,
        concepto_id: UUID,
        *,
        version: int,
        precio_unitario: Decimal,
        precio_destajo: Decimal,
        variante: str | None,
        retirar: list[int],
    ) -> UUID:
        """Retira las versiones indicadas e inserta la nueva como vigente.

        El orden importa y por eso las dos escrituras van juntas:
        `uq_cpu_vigente` es un índice único parcial —no diferible—, así que
        insertar el nuevo vigente antes de bajar el anterior violaría la
        restricción. Qué versión se retira lo decidió el dominio
        (`apu.publicar_version`), no este método.
        """
        if retirar:
            await self._sesion.execute(
                text(
                    """
                    update cpu
                       set vigente = false
                     where concepto_id = :id
                       and coalesce(variante, '') = coalesce(:variante, '')
                       and version = any(cast(:retirar as integer[]))
                    """
                ),
                {
                    "id": str(concepto_id),
                    "variante": variante,
                    "retirar": list(retirar),
                },
            )

        return (
            await self._sesion.execute(
                text(
                    """
                    insert into cpu
                        (org_id, concepto_id, version, variante,
                         precio_unitario, precio_destajo, vigente)
                    values (cast(current_setting('app.org_id') as uuid),
                            :id, :version, :variante,
                            -- El cast fija el tipo del parámetro; sin él un
                            -- Decimal puede viajar como entero y perder los
                            -- decimales en silencio.
                            cast(:precio_unitario as numeric),
                            cast(:precio_destajo as numeric), true)
                    returning id
                    """
                ),
                {
                    "id": str(concepto_id),
                    "version": version,
                    "variante": variante,
                    "precio_unitario": precio_unitario,
                    "precio_destajo": precio_destajo,
                },
            )
        ).scalar_one()
