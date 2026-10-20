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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioCargasSQL", "ReversaEnConflicto", "TablaNoRevertible"]

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


class ReversaEnConflicto(ValueError):
    """Deshacer esta operación viola una restricción de la base (§10.8).

    No es un defecto del backend, a diferencia de `TablaNoRevertible`: es un
    conflicto real entre lotes, típicamente de llave foránea. Pasa al
    revertir cargas fuera de orden —por ejemplo, el alta de un concepto se
    revierte (lo borra; `on delete cascade` se lleva su `explosion`/`cpu`)
    mientras una carga *posterior* que recargó ese mismo concepto sigue
    aplicada; revertir después esa carga posterior intenta reinsertar una
    fila de `explosion` que apunta a un `concepto_id` que ya no existe. Se
    resuelve revirtiendo primero cualquier carga más reciente que dependa de
    lo que esta carga tocó.
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
        "prototipo_nodo",
        "presupuesto",
        "partida_presupuesto",
        "cuadrilla",
        "cuadrilla_version",
        "cuadrilla_integrante",
        "nivel",
        "etapa_constructiva",
        "unidad",
        "familia",
        "desviacion",
    )
}
# `cuadrilla`/`nivel`/`etapa_constructiva`/`unidad`/`familia` están aquí por
# el mismo motivo: cuando es OTRA carga (materiales, mano de obra, el árbol
# de presupuesto) la que los toca de pasada —homologando o dando de alta
# uno que no existía, `crear_o_existente`—, ese auto-alta nunca se registra
# en el snapshot: no es lo que esa carga versiona, así que no hay nada que
# este `_ELIMINAR` pueda revertir de más. Pero cuando es la propia carga
# **dueña** del catálogo la que lo da de alta —cuadrillas (su composición y
# PU, §10.6), niveles/etapas de construcción (migración 0037), o unidades/
# familias (su propio cargador dedicado)—, la fila es tan suya como un
# `concepto` lo es de su carga de CPU, y el aplicador correspondiente sí
# registra ese insert (`aplicar_carga.py`).
# `cuadrilla_version`/`cuadrilla_integrante` cascadean solas al borrar la
# cuadrilla, pero igual están aquí explícitas: cada versión es dueña
# exclusiva de sus integrantes, y el orden de reversa las deshace primero.
# `desviacion` es la que crea `AplicadorIngenieriaLote` (carga
# `ingenieria_lote`, extensión propia): cada `Desviacion` candidata que
# persiste es un insert propio de esa carga, igual de "dueña" que un
# `concepto` lo es de su CPU. Ya estaba prevista en `_REFERENCIAS_EXTERNAS`
# (apunta a `insumo`/`concepto`) desde la migración 0054; faltaba aquí.

_REFERENCIAS_EXTERNAS: tuple[tuple[str, str, str], ...] = (
    # (tabla que tiene la FK, columna FK, tabla de `_ELIMINAR` a la que apunta)
    # Las tres sin `on delete cascade` (`information_schema.referential_
    # constraints`): borrar la fila de la derecha sin haber revisado esto
    # antes es exactamente el `IntegrityError` crudo que motivó §10.8 — solo
    # que aquí el snapshot de las dos cargas nunca comparte `(tabla,
    # registro_id)`, porque lo que las liga es una FK, no la misma fila.
    ("explosion", "insumo_id", "insumo"),
    ("cuadrilla_integrante", "insumo_id", "insumo"),
    ("salida_almacen", "insumo_id", "insumo"),
    ("actividad", "concepto_id", "concepto"),
    ("estimacion_concepto", "concepto_id", "concepto"),
    ("explosion", "concepto_hijo_id", "concepto"),
    ("partida_presupuesto", "concepto_id", "concepto"),
    ("prototipo_nodo", "concepto_id", "concepto"),
    ("ensamble", "divisor_concepto_id", "concepto"),
    ("ensamble_renglon", "concepto_id", "concepto"),
    ("salida_almacen", "concepto_id", "concepto"),
    ("control_cambio_linea", "concepto_id", "concepto"),
    ("desviacion", "insumo_id", "insumo"),
    ("desviacion", "concepto_id", "concepto"),
    ("obra", "prototipo_id", "prototipo"),
    ("actividad", "cuadrilla_id", "cuadrilla"),
    ("insumo", "cuadrilla_id", "cuadrilla"),
    ("prototipo_nodo", "nivel_id", "nivel"),
    ("actividad", "nivel_id", "nivel"),
    ("control_cambio", "nivel_id", "nivel"),
    ("incidencia", "nivel_id", "nivel"),
    ("prototipo_nodo", "etapa_id", "etapa_constructiva"),
    ("actividad", "etapa_id", "etapa_constructiva"),
    ("programa_base_item", "etapa_id", "etapa_constructiva"),
    ("control_cambio", "etapa_id", "etapa_constructiva"),
    ("incidencia", "etapa_id", "etapa_constructiva"),
    ("insumo", "unidad_id", "unidad"),
    ("insumo", "familia_id", "familia"),
    ("concepto", "unidad_id", "unidad"),
    ("concepto", "familia_id", "familia"),
    ("cuadrilla", "unidad_id", "unidad"),
    ("grupo_funcional", "unidad_id", "unidad"),
)
"""Completa a `dependientes_de`: FKs sin cascada que entran a una tabla de
`_ELIMINAR` desde fuera. Un `test` en integración verifica esta lista contra
`information_schema` para que un FK nuevo no se quede fuera en silencio otra
vez (§10.8) — si Postgres agrega una, este archivo debe enterarse."""

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
            cuadrilla_id           = cast(a.j->>'cuadrilla_id' as uuid),
            rendimiento_teorico    = cast(a.j->>'rendimiento_teorico' as numeric),
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
    "nivel": """
        with a as (select cast(:antes as jsonb) as j)
        update nivel set descripcion = a.j->>'descripcion'
        from a
        where nivel.id = cast(:id as uuid)
    """,
    "etapa_constructiva": """
        with a as (select cast(:antes as jsonb) as j)
        update etapa_constructiva set descripcion = a.j->>'descripcion'
        from a
        where etapa_constructiva.id = cast(:id as uuid)
    """,
    "unidad": """
        with a as (select cast(:antes as jsonb) as j)
        update unidad set
            nombre    = a.j->>'nombre',
            sinonimos = coalesce(
                (select array_agg(value) from jsonb_array_elements_text(a.j->'sinonimos')),
                '{}'
            ),
            factor    = cast(a.j->>'factor' as numeric),
            -- El modo Reemplazar da de baja lógica lo que el archivo ya no
            -- trae (§10.2); sin esta línea la reversa no la desharía.
            estatus   = cast(coalesce(a.j->>'estatus', 'activo') as estatus_registro)
        from a
        where unidad.id = cast(:id as uuid)
    """,
    "contratista": """
        with a as (select cast(:antes as jsonb) as j)
        update contratista set
            razon_social = a.j->>'razon_social',
            rfc          = a.j->>'rfc',
            contacto     = a.j->>'contacto',
            telefono     = a.j->>'telefono',
            email        = a.j->>'email',
            estatus      = cast(coalesce(a.j->>'estatus', 'activo') as estatus_registro)
        from a
        where contratista.id = cast(:id as uuid)
    """,
    "familia": """
        with a as (select cast(:antes as jsonb) as j)
        update familia set
            nombre     = a.j->>'nombre',
            parent_id  = cast(a.j->>'parent_id' as uuid),
            aplica_a   = coalesce(a.j->>'aplica_a', 'material'),
            iva_aplica = coalesce(cast(a.j->>'iva_aplica' as boolean), true),
            estatus    = cast(coalesce(a.j->>'estatus', 'activo') as estatus_registro)
        from a
        where familia.id = cast(:id as uuid)
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
    "cuadrilla": """
        with a as (select cast(:antes as jsonb) as j)
        update cuadrilla set
            nombre    = a.j->>'nombre',
            unidad_id = cast(a.j->>'unidad_id' as uuid),
            estatus   = cast(coalesce(a.j->>'estatus', 'activo') as estatus_registro)
        from a
        where cuadrilla.id = cast(:id as uuid)
    """,
    "cuadrilla_version": """
        with a as (select cast(:antes as jsonb) as j)
        update cuadrilla_version set
            precio_unitario = cast(a.j->>'precio_unitario' as numeric),
            vigente         = cast(a.j->>'vigente' as boolean)
        from a
        where cuadrilla_version.id = cast(:id as uuid)
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
    "prototipo_nodo": """
        with a as (select cast(:antes as jsonb) as j)
        update prototipo_nodo set
            parent_id     = cast(a.j->>'parent_id' as uuid),
            tipo          = cast(a.j->>'tipo' as tipo_prototipo_nodo),
            nombre        = a.j->>'nombre',
            concepto_id   = cast(a.j->>'concepto_id' as uuid),
            nivel_id      = cast(a.j->>'nivel_id' as uuid),
            etapa_id      = cast(a.j->>'etapa_id' as uuid),
            orden         = cast(a.j->>'orden' as integer),
            cantidad      = cast(a.j->>'cantidad' as numeric),
            -- `AplicadorIngenieriaLote` (camino "diseño_nuevo") es el único
            -- aplicador que hoy registraría un "update" sobre esta tabla;
            -- por ahora no lo hace (el alta en cascada del prototipo nuevo
            -- ya cubre su reversa, ver `cargas_sql.py` §desviacion), pero
            -- se restaura igual para que un "update" futuro no deje
            -- `modo_cantidad` a medias si algo sí llega a registrarse.
            modo_cantidad = cast(coalesce(a.j->>'modo_cantidad', 'capturada') as modo_cantidad)
        from a
        where prototipo_nodo.id = cast(:id as uuid)
    """,
    "presupuesto": """
        with a as (select cast(:antes as jsonb) as j)
        update presupuesto set
            vigente = cast(a.j->>'vigente' as boolean)
        from a
        where presupuesto.id = cast(:id as uuid)
    """,
    "obra": """
        with a as (select cast(:antes as jsonb) as j)
        update obra set
            prototipo_id = cast(a.j->>'prototipo_id' as uuid)
        from a
        where obra.id = cast(:id as uuid)
    """,
    # Solo `prototipo_id`: es el único campo de `obra` que un aplicador de
    # carga toca hoy (`AplicadorIngenieriaLote`, camino "diseño_nuevo",
    # asigna el prototipo clonado a la obra, §11.4). Un `PATCH /obras/{id}`
    # normal no pasa por aquí —no es una carga reversible, es edición
    # directa (§11.2)— así que el resto de columnas editables de `obra`
    # nunca necesita su propia reversa de lote.
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

    async def dependientes_de(self, carga_id: UUID) -> list[dict[str, Any]]:
        """Cargas más nuevas que dependen de lo que esta tocó (§10.8): o
        tocaron la misma fila, o —vía `_REFERENCIAS_EXTERNAS`— dieron de
        alta algo que apunta, por FK sin cascada, a una fila que esta carga
        insertó. Ver `ix_carga_snapshot_registro` (migración 0033): sin ese
        índice, el primer `exists` sería un seq scan del snapshot completo.
        """
        columnas = "cd.id, cd.tipo, cd.archivo_nombre, cd.fecha, cd.version_generada, cd.estatus, cd.revertida_en"
        fk_union = " union all ".join(
            f"""
            select {columnas}
            from carga_snapshot propia
            join {tabla_hija} th on th.{columna} = propia.registro_id
            join carga_snapshot cs on cs.tabla = '{tabla_hija}' and cs.registro_id = th.id
            join carga_datos cd on cd.id = cs.carga_id
            where propia.carga_id = cast(:carga_id as uuid)
              and propia.tabla = '{tabla_padre}'
              and propia.operacion = 'insert'
            """
            for tabla_hija, columna, tabla_padre in _REFERENCIAS_EXTERNAS
        )
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select distinct id, tipo, archivo_nombre, fecha, version_generada
                    from (
                        select {columnas}
                        from carga_snapshot cs
                        join carga_datos cd on cd.id = cs.carga_id
                        where exists (
                            select 1 from carga_snapshot propia
                            where propia.carga_id = cast(:carga_id as uuid)
                              and propia.tabla = cs.tabla
                              and propia.registro_id = cs.registro_id
                        )
                        union all
                        {fk_union}
                    ) dependientes
                    where id != cast(:carga_id as uuid)
                      and estatus = 'aplicado'
                      and revertida_en is null
                      and fecha > (
                          select fecha from carga_datos where id = cast(:carga_id as uuid)
                      )
                    order by fecha
                    """
                ),
                {"carga_id": str(carga_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def eliminar(self, carga_id: UUID) -> None:
        # `carga_snapshot`/`pendiente` referencian `carga_id` con `on delete
        # cascade` desde el diseño original de estas tablas (§10.8): un solo
        # delete aquí basta, no hay nada más que limpiar a mano.
        await self._sesion.execute(
            text("delete from carga_datos where id = cast(:id as uuid)"),
            {"id": str(carga_id)},
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
            await self._ejecutar_reversa(sql, {"id": registro_id}, tabla, registro_id)
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
        await self._ejecutar_reversa(
            sql, {"id": registro_id, "antes": _json(antes)}, tabla, registro_id
        )

    async def _ejecutar_reversa(
        self, sql: str, parametros: dict[str, Any], tabla: str, registro_id: str
    ) -> None:
        """Ejecuta el SQL de reversa, traduciendo una violación de
        restricción a `ReversaEnConflicto` (§10.8) en vez de dejar subir el
        `IntegrityError` crudo de SQLAlchemy — ese detalle de infraestructura
        no le sirve a quien ve el 409, y `main.py` no puede distinguir "hay
        una restricción rota" de "el backend no sabe deshacer esto"
        (`TablaNoRevertible`) sin este límite explícito.
        """
        try:
            await self._sesion.execute(text(sql), parametros)
        except IntegrityError as exc:
            raise ReversaEnConflicto(
                f"No se pudo deshacer la operación sobre {tabla!r} (registro "
                f"{registro_id}): entra en conflicto con una restricción de la "
                f"base, probablemente porque una carga posterior que dependía "
                f"de este registro sigue aplicada. Revierte primero cualquier "
                f"carga más reciente que dependa de lo que tocó esta (§10.8)."
            ) from exc

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

    async def resolver_pendiente(
        self,
        pendiente_id: UUID,
        *,
        usuario_id: UUID | None,
        aprobado: bool,
        nota: str | None,
    ) -> dict[str, Any] | None:
        """Aprobar/rechazar (§10.3). `where not resuelto` es la guarda de
        idempotencia: resolver dos veces no pisa la primera resolución —
        devuelve `None`, y `ResolverPendiente` lo trata como 409."""
        fila = (
            await self._sesion.execute(
                text(
                    """
                    update pendiente set
                        resuelto     = true,
                        resuelto_por = cast(:usuario_id as uuid),
                        resuelto_en  = now(),
                        resolucion   = jsonb_build_object(
                            'accion', cast(:accion as text), 'nota', cast(:nota as text)
                        )
                    where id = cast(:id as uuid) and not resuelto
                    returning id, carga_id, tipo, entidad, valor_origen, propuesta,
                              resolucion, critico, resuelto, resuelto_por,
                              resuelto_en, origen_ref, created_at
                    """
                ),
                {
                    "id": str(pendiente_id),
                    "usuario_id": str(usuario_id) if usuario_id else None,
                    "accion": "aprobado" if aprobado else "rechazado",
                    "nota": nota,
                },
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

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

    async def registrar_mapeo(
        self, *, entidad: str, alias: str, clave_canonica: str
    ) -> None:
        """Deja escrito que un alias significa una clave del catálogo (§10.3).

        Es la mitad que faltaba: `mapeos()` ya lo leía —"lo resuelto re-alimenta
        la carga"— pero nada lo escribía, así que una decisión humana se perdía
        en la siguiente carga del mismo archivo.

        El caso concreto: al fusionar dos oficios que resultaron ser el mismo,
        el archivo del cliente sigue trayendo los dos nombres. Sin el mapeo, la
        próxima carga vuelve a crear el que se acaba de absorber y la fusión se
        deshace sola.

        Idempotente por el par entidad-alias: homologar dos veces es corregir,
        no acumular.
        """
        await self._sesion.execute(
            text(
                """
                insert into mapeo (org_id, entidad, alias, clave_canonica)
                values (cast(current_setting('app.org_id') as uuid),
                        :entidad, :alias, :clave_canonica)
                on conflict (org_id, entidad, alias)
                    do update set clave_canonica = excluded.clave_canonica
                """
            ),
            {"entidad": entidad, "alias": alias, "clave_canonica": clave_canonica},
        )
