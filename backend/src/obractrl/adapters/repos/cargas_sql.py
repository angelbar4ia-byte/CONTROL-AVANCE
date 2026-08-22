"""Repositorio de cargas: lote, snapshot, reversa y bandeja de pendientes.

Spec §9.4 (`CargaDatos`) · §10.2 (lote de carga) · §10.3 (mapeos y bandeja) ·
§10.8 (versionado y reversa) · §12.4 (RLS).

`carga_datos`, `carga_snapshot` y `pendiente` comparten la misma política en
`database/migrations/20260814000012_rls_policies.sql`: alcance de organización
**y** `app.es_config()` —Control de obra y Super intendente (§5.1)—. Por eso
ningún método filtra `org_id` a mano: eso lo impone la base. `mapeo` está en
el bloque de catálogos, con la misma regla.

**La reversa no borra registro por registro: revierte el lote** (§10.8). El
`carga_snapshot` guarda el `antes`/`despues` de cada operación con su `orden`,
y `revertir_operacion` las deshace una a una en orden inverso. Las tablas que
puede tocar están en una **lista blanca** (`_ELIMINAR`, `_RESTAURAR`,
`_REINSERTAR`): el nombre de tabla nunca sale de un archivo ni de la petición,
solo de lo que el propio backend escribió al aplicar la carga.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioCargasSQL", "TablaNoRevertible"]

_COLUMNAS = """
    id, tipo, modo, estatus, archivo_url, archivo_nombre, archivo_hash,
    usuario_id, resumen, errores, version_generada, revertida_en,
    revertida_por, fecha
"""


class TablaNoRevertible(ValueError):
    """El snapshot menciona una tabla fuera de la lista blanca de reversa.

    Solo puede pasar si alguien escribió snapshots a mano en la base: el
    backend nunca registra una tabla que no sepa deshacer.
    """


def _json(valor: object) -> str:
    """Serializa a JSON lo que Postgres va a guardar como `jsonb`."""
    return json.dumps(valor, default=_convertir, ensure_ascii=False)


def _convertir(valor: object) -> object:
    if isinstance(valor, Decimal):
        # Como cadena y no como float: el §3.5 exige DECIMAL y un float
        # intermedio ya perdió precisión.
        return str(valor)
    if isinstance(valor, UUID):
        return str(valor)
    if isinstance(valor, datetime | date):
        return valor.isoformat()
    return str(valor)


# --- Lista blanca de reversa (§10.8) -------------------------------------
#
# Solo estas tablas escriben los cargadores implementados, así que solo estas
# se pueden deshacer. El diccionario es además lo que impide que un nombre de
# tabla arbitrario llegue a una sentencia.

_ELIMINAR: dict[str, str] = {
    tabla: f"delete from {tabla} where id = cast(:id as uuid)"
    for tabla in (
        "insumo",
        "concepto",
        "cpu",
        "explosion",
        "salida_almacen",
        "prototipo",
    )
}

_RESTAURAR: dict[str, str] = {
    "insumo": """
        with a as (select cast(:antes as jsonb) as j)
        update insumo set
            descripcion            = a.j->>'descripcion',
            unidad_id              = cast(a.j->>'unidad_id' as uuid),
            familia_id             = cast(a.j->>'familia_id' as uuid),
            costo_base             = cast(a.j->>'costo_base' as numeric),
            costo_base_actualizado = cast(a.j->>'costo_base_actualizado' as numeric),
            costo_promedio_almacen = cast(a.j->>'costo_promedio_almacen' as numeric),
            costo_ultimo           = cast(a.j->>'costo_ultimo' as numeric),
            origen                 = coalesce(a.j->>'origen', 'base'),
            iva_aplica             = cast(a.j->>'iva_aplica' as boolean),
            factor_conversion      = coalesce(cast(a.j->>'factor_conversion' as numeric), 1),
            -- El modo Reemplazar da de baja lógica lo que el archivo ya no
            -- trae (§10.2); sin esta línea la reversa no la desharía.
            estatus                = cast(coalesce(a.j->>'estatus', 'activo') as estatus_registro)
        from a
        where insumo.id = cast(:id as uuid)
    """,
    "concepto": """
        with a as (select cast(:antes as jsonb) as j)
        update concepto set
            tipo        = cast(a.j->>'tipo' as tipo_concepto),
            descripcion = a.j->>'descripcion',
            unidad_id   = cast(a.j->>'unidad_id' as uuid),
            familia_id  = cast(a.j->>'familia_id' as uuid),
            estatus     = cast(coalesce(a.j->>'estatus', 'activo') as estatus_registro)
        from a
        where concepto.id = cast(:id as uuid)
    """,
    "cpu": """
        with a as (select cast(:antes as jsonb) as j)
        update cpu set
            precio_unitario = cast(a.j->>'precio_unitario' as numeric),
            precio_destajo  = cast(a.j->>'precio_destajo' as numeric),
            vigente         = cast(a.j->>'vigente' as boolean)
        from a
        where cpu.id = cast(:id as uuid)
    """,
    "prototipo": """
        with a as (select cast(:antes as jsonb) as j)
        update prototipo set
            nombre    = a.j->>'nombre',
            m2        = cast(a.j->>'m2' as numeric),
            niveles   = cast(a.j->>'niveles' as smallint),
            recamaras = cast(a.j->>'recamaras' as smallint)
        from a
        where prototipo.id = cast(:id as uuid)
    """,
}

_REINSERTAR: dict[str, str] = {
    "explosion": """
        with a as (select cast(:antes as jsonb) as j)
        insert into explosion
            (id, org_id, concepto_id, cpu_id, tipo_hijo, insumo_id,
             concepto_hijo_id, categoria, cantidad, rendimiento,
             costo_unitario, importe, orden)
        select
            cast(a.j->>'id' as uuid),
            cast(current_setting('app.org_id') as uuid),
            cast(a.j->>'concepto_id' as uuid),
            cast(a.j->>'cpu_id' as uuid),
            cast(a.j->>'tipo_hijo' as tipo_hijo_explosion),
            cast(a.j->>'insumo_id' as uuid),
            cast(a.j->>'concepto_hijo_id' as uuid),
            cast(a.j->>'categoria' as categoria_explosion),
            cast(a.j->>'cantidad' as numeric),
            cast(a.j->>'rendimiento' as numeric),
            cast(a.j->>'costo_unitario' as numeric),
            cast(a.j->>'importe' as numeric),
            cast(a.j->>'orden' as integer)
        from a
    """,
}


class RepositorioCargasSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    # --- Lote (§9.4, §10.2) ----------------------------------------------

    async def crear(
        self,
        *,
        tipo: str,
        modo: str,
        archivo_nombre: str,
        archivo_hash: str,
        usuario_id: UUID | None,
    ) -> UUID:
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into carga_datos
                        (org_id, tipo, modo, estatus, archivo_nombre,
                         archivo_hash, usuario_id)
                    values (cast(current_setting('app.org_id') as uuid),
                            cast(:tipo as tipo_carga), cast(:modo as modo_carga),
                            'pendiente', :archivo_nombre, :archivo_hash,
                            cast(:usuario_id as uuid))
                    returning id
                    """
                ),
                {
                    "tipo": tipo,
                    "modo": modo,
                    "archivo_nombre": archivo_nombre,
                    "archivo_hash": archivo_hash,
                    "usuario_id": str(usuario_id) if usuario_id else None,
                },
            )
        ).scalar_one()

    async def obtener(self, carga_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} from carga_datos where id = :id"),
                {"id": str(carga_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def listar(self, *, tipo: str | None = None) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS}
                    from carga_datos
                    -- El cast del lado `is null` fija el tipo del parámetro;
                    -- sin él asyncpg levanta AmbiguousParameterError.
                    where cast(:tipo as tipo_carga) is null
                       or tipo = cast(:tipo as tipo_carga)
                    order by fecha desc
                    """
                ),
                {"tipo": tipo},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def buscar_aplicada_por_hash(
        self, *, tipo: str, archivo_hash: str
    ) -> dict[str, Any] | None:
        """Carga aplicada y **no revertida** con ese hash (§10.8, §12.3)."""
        fila = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS}
                    from carga_datos
                    where tipo = cast(:tipo as tipo_carga)
                      and archivo_hash = :archivo_hash
                      and estatus = 'aplicado'
                      and revertida_en is null
                    order by fecha desc
                    limit 1
                    """
                ),
                {"tipo": tipo, "archivo_hash": archivo_hash},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def siguiente_version(self, *, tipo: str) -> int:
        """Versión que le tocaría a la próxima carga de ese tipo (§10.8).

        Se cuenta por **tipo** y no por carga: el §10.8 versiona "el conjunto
        afectado" (los materiales, los CPU…), y el ejemplo del spec —v1, luego
        v2 con el diff— es exactamente esa numeración.
        """
        return int(
            (
                await self._sesion.execute(
                    text(
                        """
                        select coalesce(max(version_generada), 0) + 1
                        from carga_datos
                        where tipo = cast(:tipo as tipo_carga)
                        """
                    ),
                    {"tipo": tipo},
                )
            ).scalar_one()
        )

    async def finalizar(
        self,
        carga_id: UUID,
        *,
        estatus: str,
        resumen: dict[str, Any],
        errores: list[dict[str, Any]],
        version_generada: int | None,
    ) -> None:
        await self._sesion.execute(
            text(
                """
                update carga_datos set
                    estatus          = cast(:estatus as estatus_carga),
                    resumen          = cast(:resumen as jsonb),
                    errores          = cast(:errores as jsonb),
                    version_generada = cast(:version as integer)
                where id = cast(:id as uuid)
                """
            ),
            {
                "id": str(carga_id),
                "estatus": estatus,
                "resumen": _json(resumen),
                "errores": _json(errores),
                "version": version_generada,
            },
        )

    async def marcar_revertida(
        self, carga_id: UUID, *, usuario_id: UUID | None
    ) -> None:
        await self._sesion.execute(
            text(
                """
                update carga_datos set
                    revertida_en  = now(),
                    revertida_por = cast(:usuario_id as uuid)
                where id = cast(:id as uuid)
                """
            ),
            {"id": str(carga_id), "usuario_id": str(usuario_id) if usuario_id else None},
        )

    # --- Snapshot y reversa (§10.8) --------------------------------------

    async def registrar_snapshots(
        self, carga_id: UUID, operaciones: list[dict[str, Any]]
    ) -> None:
        """Guarda el antes/después de cada registro tocado, **en orden**.

        El `orden` es explícito porque `created_at` no sirve para ordenar
        dentro del lote: `now()` es constante en toda la transacción y el `id`
        es aleatorio (ver `database/migrations/20260814000019`).
        """
        for posicion, operacion in enumerate(operaciones):
            await self._sesion.execute(
                text(
                    """
                    insert into carga_snapshot
                        (org_id, carga_id, tabla, registro_id, operacion,
                         antes, despues, orden)
                    values (cast(current_setting('app.org_id') as uuid),
                            cast(:carga_id as uuid), :tabla,
                            cast(:registro_id as uuid), :operacion,
                            cast(:antes as jsonb), cast(:despues as jsonb),
                            :orden)
                    """
                ),
                {
                    "carga_id": str(carga_id),
                    "tabla": operacion["tabla"],
                    "registro_id": str(operacion["registro_id"]),
                    "operacion": operacion["operacion"],
                    "antes": _json(operacion["antes"]) if operacion.get("antes") else None,
                    "despues": (
                        _json(operacion["despues"]) if operacion.get("despues") else None
                    ),
                    "orden": posicion,
                },
            )

    async def snapshots(self, carga_id: UUID) -> list[dict[str, Any]]:
        """Operaciones del lote en orden **inverso**, listas para revertir."""
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select id, tabla, registro_id, operacion, antes, despues, orden
                    from carga_snapshot
                    where carga_id = cast(:id as uuid)
                    order by orden desc
                    """
                ),
                {"id": str(carga_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def revertir_operacion(self, operacion: dict[str, Any]) -> None:
        """Deshace una operación dejando el dato como estaba antes (§10.8)."""
        tabla = str(operacion["tabla"])
        accion = str(operacion["operacion"])
        registro_id = str(operacion["registro_id"])

        if accion == "insert":
            sql = _ELIMINAR.get(tabla)
            if sql is None:
                raise TablaNoRevertible(
                    f"El snapshot menciona la tabla {tabla!r}, que no está en la "
                    f"lista blanca de reversa (§10.8)."
                )
            await self._sesion.execute(text(sql), {"id": registro_id})
            return

        antes = operacion.get("antes")
        if antes is None:
            raise TablaNoRevertible(
                f"La operación {accion!r} sobre {tabla!r} no guardó el estado "
                f"previo; sin él no se puede revertir (§10.8)."
            )

        sql = _RESTAURAR.get(tabla) if accion == "update" else _REINSERTAR.get(tabla)
        if sql is None:
            raise TablaNoRevertible(
                f"No hay forma registrada de deshacer un {accion!r} sobre "
                f"{tabla!r} (§10.8)."
            )
        await self._sesion.execute(
            text(sql), {"id": registro_id, "antes": _json(antes)}
        )

    # --- Bandeja de pendientes (§10.3) -----------------------------------

    async def crear_pendientes(
        self, carga_id: UUID, pendientes: list[dict[str, Any]]
    ) -> None:
        for pendiente in pendientes:
            await self._sesion.execute(
                text(
                    """
                    insert into pendiente
                        (org_id, carga_id, tipo, entidad, valor_origen,
                         propuesta, critico, origen_ref)
                    values (cast(current_setting('app.org_id') as uuid),
                            cast(:carga_id as uuid), :tipo, :entidad,
                            :valor_origen, cast(:propuesta as jsonb),
                            cast(:critico as boolean), :origen_ref)
                    """
                ),
                {
                    "carga_id": str(carga_id),
                    "tipo": pendiente["tipo"],
                    "entidad": pendiente.get("entidad"),
                    "valor_origen": pendiente.get("valor_origen"),
                    "propuesta": _json(pendiente.get("propuesta") or {}),
                    "critico": bool(pendiente.get("critico", False)),
                    "origen_ref": pendiente.get("origen_ref"),
                },
            )

    async def listar_pendientes(
        self, *, carga_id: UUID | None = None, solo_abiertos: bool = True
    ) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select id, carga_id, tipo, entidad, valor_origen, propuesta,
                           resolucion, critico, resuelto, resuelto_por,
                           resuelto_en, origen_ref, created_at
                    from pendiente
                    -- El cast del lado `is null` fija el tipo del parámetro;
                    -- sin él asyncpg levanta AmbiguousParameterError.
                    where (cast(:carga_id as uuid) is null
                           or carga_id = cast(:carga_id as uuid))
                      and (not cast(:solo_abiertos as boolean) or not resuelto)
                    order by critico desc, created_at
                    """
                ),
                {
                    "carga_id": str(carga_id) if carga_id else None,
                    "solo_abiertos": solo_abiertos,
                },
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    # --- Mapeos confirmados (§10.3) --------------------------------------

    async def mapeos(self, entidad: str) -> dict[str, str]:
        """Alias → clave canónica ya confirmados para esa entidad.

        Es lo que hace que "lo resuelto re-alimente la carga" (§10.3): antes
        de mandar un alias a la bandeja, el cargador pregunta aquí si alguien
        ya lo homologó.
        """
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select alias, clave_canonica
                    from mapeo
                    where entidad = :entidad
                    """
                ),
                {"entidad": entidad},
            )
        ).mappings().all()
        return {str(fila["alias"]): str(fila["clave_canonica"]) for fila in filas}
