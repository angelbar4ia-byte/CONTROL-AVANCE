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

import json
from collections.abc import Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.application.puertos.repositorios import (
    RegistroNoEncontrado,
    VersionVigenteNoEliminable,
)

__all__ = ["RepositorioConceptosSQL"]

_COLUMNAS = """
    id, tipo, clave, descripcion, unidad_id, familia_id, estatus, especialidad_id
"""

_CAMPOS_EDITABLES: dict[str, str] = {
    "tipo": "tipo = cast(:tipo as tipo_concepto)",
    "descripcion": "descripcion = :descripcion",
    "unidad_id": "unidad_id = cast(:unidad_id as uuid)",
    "familia_id": "familia_id = cast(:familia_id as uuid)",
    "estatus": "estatus = cast(:estatus as estatus_registro)",
    "especialidad_id": "especialidad_id = cast(:especialidad_id as uuid)",
}
"""Lista blanca de campos editables; también evita armar SQL con nombres que
vengan de un archivo externo. La `clave` no está: es la identidad (§3.3)."""

_COLUMNAS_EXPLOSION = """
    id, concepto_id, cpu_id, tipo_hijo, insumo_id, concepto_hijo_id,
    categoria, cantidad, rendimiento, costo_unitario, importe, orden
"""

_PROFUNDIDAD_MAXIMA = 32
"""Espeja `domain.catalogos.apu._PROFUNDIDAD_MAXIMA`.

El corte de aquí es solo para que un catálogo mal cargado no haga trabajar de
más al motor recursivo; quien reporta el problema —ciclo o anidamiento
absurdo— es el dominio, con un error legible.
"""

_ALCANCE = f"""
    with recursive alcance as (
        -- Se siembra desde un ARREGLO y no desde un id suelto: explotar los
        -- ~150 conceptos de una obra uno por uno serían 150 recorridos
        -- recursivos, y los auxiliares compartidos se recorrerían una vez por
        -- padre. Con varias raíces el motor los visita una sola vez, y el
        -- resultado ya viene agrupado por `concepto_clave`, que es como el
        -- dominio lo indexa.
        select raiz as concepto_id, array[raiz] as camino
        from unnest(cast(:ids as uuid[])) as raiz
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

    async def actualizar(self, concepto_id: UUID, cambios: dict[str, Any]) -> None:
        """Edición parcial; solo las claves presentes en ``cambios`` se escriben.

        La usa el cargador de CPU (§10.6) cuando el archivo trae un concepto
        que ya existe: en modo Actualizar se refresca descripción, unidad y
        familia (§10.2). La `clave` no es editable — es la identidad (§3.3).
        """
        asignaciones = [
            _CAMPOS_EDITABLES[campo] for campo in cambios if campo in _CAMPOS_EDITABLES
        ]
        if not asignaciones:
            return

        parametros: dict[str, Any] = {"id": str(concepto_id)}
        for campo in cambios:
            if campo not in _CAMPOS_EDITABLES:
                continue
            valor = cambios[campo]
            parametros[campo] = (
                str(valor) if campo.endswith("_id") and valor is not None else valor
            )

        await self._sesion.execute(
            text(f"update concepto set {', '.join(asignaciones)} where id = :id"),
            parametros,
        )

    async def obtener(self, concepto_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} from concepto where id = :id"),
                {"id": str(concepto_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def obtener_por_clave(self, clave: str) -> dict[str, Any] | None:
        """Para `ResolverPendiente` (§10.3): un `CPU_NUEVO` rechazado se
        identifica por `valor_origen` (la clave), no por id."""
        fila = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} from concepto where clave = :clave"),
                {"clave": clave},
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
        """La composición de UN concepto. Ver `composicion_recursiva_de`."""
        return await self.composicion_recursiva_de([concepto_id])

    async def composicion_recursiva_de(
        self, ids: Sequence[UUID]
    ) -> list[dict[str, Any]]:
        """Filas de `Explosion` de todo concepto alcanzable desde las raíces (§7.3).

        Recibe **varias** raíces de una vez porque quien las necesita en lote
        —los insumos programados de una obra— tendría que hacer una consulta
        por concepto, cada una con su propio recorrido recursivo, y los
        auxiliares que comparten se recorrerían una vez por padre. El
        resultado ya viene agrupado por `concepto_clave`, así que el dominio
        explota N conceptos sobre un solo mapa de composiciones.

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
                {"ids": [str(cid) for cid in ids]},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def explosion_directa(self, concepto_id: UUID) -> list[dict[str, Any]]:
        """Filas de `Explosion` **propias** del concepto, sin recursión (§7.3).

        A diferencia de `composicion_recursiva`, esto no explota el árbol: es
        lo que el cargador de CPU necesita para saber qué composición va a
        sustituir y guardar su `antes` en el snapshot del lote (§10.8).
        """
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS_EXPLOSION}
                    from explosion
                    where concepto_id = :id
                    order by orden, id
                    """
                ),
                {"id": str(concepto_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def alcanza(self, desde: UUID, objetivo: UUID) -> bool:
        """¿`objetivo` está dentro de la composición (a cualquier profundidad) de `desde`?

        Es la pregunta del ciclo: antes de poner a `hijo` bajo `padre` hay que ver que `padre` no
        esté ya dentro de `hijo`.
        """
        hay = (
            await self._sesion.execute(
                text(f"{_ALCANCE} select exists (select 1 from alcance where concepto_id = :objetivo)"),
                {"ids": [str(desde)], "objetivo": str(objetivo)},
            )
        ).scalar_one()
        return bool(hay)

    async def matriz_directa(self, padre_id: UUID, hijo_id: UUID) -> dict[str, Any] | None:
        """La fila viva (sin versión de CPU) que pone a `hijo` directamente bajo `padre`."""
        fila = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS_EXPLOSION} from explosion
                     where concepto_id = :padre and concepto_hijo_id = :hijo
                       and tipo_hijo = 'concepto' and cpu_id is null
                    """
                ),
                {"padre": str(padre_id), "hijo": str(hijo_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def poner_matriz(
        self, padre_id: UUID, hijo_id: UUID, cantidad: Decimal, formula: dict[str, Any] | None = None
    ) -> UUID:
        """Alta o cambio de cantidad de una matriz directa. Devuelve el id de la fila.

        `formula` es cómo se formó la cantidad (0094), o `None` si se capturó a mano; al cambiarla se reemplaza.
        """
        existente = await self.matriz_directa(padre_id, hijo_id)
        carga = json.dumps(formula) if formula is not None else None
        if existente is not None:
            await self._sesion.execute(
                text("update explosion set cantidad = :c, formula = cast(:f as jsonb) where id = :id"),
                {"c": cantidad, "f": carga, "id": str(existente["id"])},
            )
            return UUID(str(existente["id"]))
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into explosion
                        (org_id, concepto_id, cpu_id, tipo_hijo, concepto_hijo_id, categoria,
                         cantidad, rendimiento, costo_unitario, importe, orden, formula)
                    values (cast(current_setting('app.org_id') as uuid), :padre, null, 'concepto',
                            :hijo, 'matriz', cast(:c as numeric), 0, 0, 0,
                            coalesce((select max(orden) + 1 from explosion where concepto_id = :padre), 0),
                            cast(:f as jsonb))
                    returning id
                    """
                ),
                {"padre": str(padre_id), "hijo": str(hijo_id), "c": cantidad, "f": carga},
            )
        ).scalar_one()

    async def poner_destajo(self, concepto_id: UUID, insumo_id: UUID, factor: Decimal) -> UUID:
        """Un destajo en la receta del concepto: renglón de insumo, categoría destajo, `factor` unidades del destajo por
        cada unidad del concepto. Si ya estaba, solo cambia el factor. Composición viva (sin versión de CPU)."""
        existente = (
            await self._sesion.execute(
                text(
                    "select id from explosion where concepto_id = :c and insumo_id = :i and tipo_hijo = 'insumo' "
                    "and categoria = 'destajo' and cpu_id is null"
                ),
                {"c": str(concepto_id), "i": str(insumo_id)},
            )
        ).scalar_one_or_none()
        if existente is not None:
            await self._sesion.execute(
                text("update explosion set cantidad = cast(:f as numeric) where id = :id"),
                {"f": factor, "id": str(existente)},
            )
            return UUID(str(existente))
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into explosion
                        (org_id, concepto_id, cpu_id, tipo_hijo, insumo_id, categoria,
                         cantidad, rendimiento, costo_unitario, importe, orden)
                    values (cast(current_setting('app.org_id') as uuid), :c, null, 'insumo', :i, 'destajo',
                            cast(:f as numeric), 0, 0, 0,
                            coalesce((select max(orden) + 1 from explosion where concepto_id = :c), 0))
                    returning id
                    """
                ),
                {"c": str(concepto_id), "i": str(insumo_id), "f": factor},
            )
        ).scalar_one()

    async def quitar_destajo(self, concepto_id: UUID, insumo_id: UUID) -> bool:
        resultado = await self._sesion.execute(
            text(
                "delete from explosion where concepto_id = :c and insumo_id = :i and tipo_hijo = 'insumo' "
                "and categoria = 'destajo' and cpu_id is null"
            ),
            {"c": str(concepto_id), "i": str(insumo_id)},
        )
        return bool(resultado.rowcount)

    async def quitar_matriz(self, padre_id: UUID, hijo_id: UUID) -> bool:
        resultado = await self._sesion.execute(
            text(
                "delete from explosion where concepto_id = :padre and concepto_hijo_id = :hijo "
                "and tipo_hijo = 'concepto' and cpu_id is null"
            ),
            {"padre": str(padre_id), "hijo": str(hijo_id)},
        )
        return bool(resultado.rowcount)

    async def eliminar_explosion(self, concepto_id: UUID) -> None:
        """Borra la composición vigente del concepto.

        El cargador de CPU **sustituye** la composición en vez de acumularla:
        `v_consumo_vs_presupuesto` (migración 0008) suma `explosion` por
        `concepto_id` sin filtrar versión, así que dejar las filas viejas al
        publicar una versión nueva duplicaría el consumo teórico (§7.7).
        Lo borrado queda en el snapshot del lote y la reversa lo repone
        (§10.8).
        """
        await self._sesion.execute(
            text("delete from explosion where concepto_id = :id"),
            {"id": str(concepto_id)},
        )

    async def agregar_explosion(
        self, concepto_id: UUID, *, cpu_id: UUID | None, filas: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Inserta la composición nueva y devuelve las filas ya persistidas.

        Devuelve el registro completo —no solo el id— porque el snapshot del
        §10.8 guarda el ``despues`` de cada operación, y armarlo desde el
        `returning` evita releer.
        """
        insertadas: list[dict[str, Any]] = []
        for orden, fila in enumerate(filas):
            registro = (
                await self._sesion.execute(
                    text(
                        f"""
                        insert into explosion
                            (org_id, concepto_id, cpu_id, tipo_hijo, insumo_id,
                             concepto_hijo_id, categoria, cantidad, rendimiento,
                             costo_unitario, importe, orden)
                        values (cast(current_setting('app.org_id') as uuid),
                                :concepto_id, cast(:cpu_id as uuid),
                                cast(:tipo_hijo as tipo_hijo_explosion),
                                cast(:insumo_id as uuid),
                                cast(:concepto_hijo_id as uuid),
                                cast(:categoria as categoria_explosion),
                                -- El cast a numeric no es decorativo: sin él
                                -- asyncpg puede inferir entero y perder los
                                -- decimales del rendimiento en silencio.
                                cast(:cantidad as numeric),
                                cast(:rendimiento as numeric),
                                cast(:costo_unitario as numeric),
                                cast(:importe as numeric),
                                :orden)
                        returning {_COLUMNAS_EXPLOSION}
                        """
                    ),
                    {
                        "concepto_id": str(concepto_id),
                        "cpu_id": str(cpu_id) if cpu_id else None,
                        "tipo_hijo": fila["tipo_hijo"],
                        "insumo_id": (
                            str(fila["insumo_id"]) if fila.get("insumo_id") else None
                        ),
                        "concepto_hijo_id": (
                            str(fila["concepto_hijo_id"])
                            if fila.get("concepto_hijo_id")
                            else None
                        ),
                        "categoria": fila["categoria"],
                        "cantidad": fila.get("cantidad", 0),
                        "rendimiento": fila.get("rendimiento", 0),
                        "costo_unitario": fila.get("costo_unitario", 0),
                        "importe": fila.get("importe", 0),
                        "orden": fila.get("orden", orden),
                    },
                )
            ).mappings().one()
            insertadas.append(dict(registro))
        return insertadas

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

    async def eliminar_version_cpu(
        self, concepto_id: UUID, *, version: int, variante: str | None = None
    ) -> None:
        """Borra una versión de CPU ya retirada (mantenimiento directo,
        §10.8, no ligado a una carga). La `explosion` atada a ese `cpu_id`
        se va con `on delete cascade`; la composición "viva" (`cpu_id is
        null`) no se toca. Se identifica por versión + variante, como
        `publicar_version_cpu` — no por el id interno de la fila."""
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select id, vigente from cpu
                    where concepto_id = cast(:concepto_id as uuid)
                      and version = :version
                      and coalesce(variante, '') = coalesce(:variante, '')
                    """
                ),
                {"concepto_id": str(concepto_id), "version": version, "variante": variante},
            )
        ).mappings().first()
        if fila is None:
            raise RegistroNoEncontrado(
                f"La versión {version} (variante {variante!r}) no existe para "
                f"el concepto {concepto_id}."
            )
        if fila["vigente"]:
            raise VersionVigenteNoEliminable(
                f"La versión {version} es la vigente: no se puede eliminar (§10.8)."
            )
        await self._sesion.execute(
            text("delete from cpu where id = cast(:id as uuid)"),
            {"id": str(fila["id"])},
        )
