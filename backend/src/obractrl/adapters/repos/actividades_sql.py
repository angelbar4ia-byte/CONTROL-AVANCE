"""Repositorio de actividades.

Spec §12.11 (adaptador de persistencia) · §7.6 (ejecución y avance) ·
§6 (CPM) · §12.4 (RLS).

RLS ya filtra `actividad` por alcance de rol (política `actividad_scope`,
`database/migrations/0012`, vía `app.obra_visible(obra_id)`): ningún método
de aquí filtra por `org_id` u `obra_id` de forma manual para decidir qué es
visible — eso lo impone la base. `org_id` en los INSERT se resuelve leyendo
`current_setting('app.org_id')`, que es el mismo valor que `sesion_con_rls`
fijó con `SET LOCAL` (§12.4): así ningún método de este repo necesita que el
caso de uso le pase `org_id` explícito.

`json` se usa solo para **serializar hacia la BD** (`evidencias`, dict de
`guardar_resultado_cpm`); lo que la BD **devuelve** en columnas `jsonb` ya
llega deserializado por el dialecto asyncpg de SQLAlchemy — confirmado
empíricamente, no hace falta `json.loads` en las lecturas.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.application.puertos.repositorios import RegistroNoEncontrado
from obractrl.domain.programacion.cpm import Dependencia, NodoCPM, Tramo

__all__ = ["ActividadNoModificada", "RepositorioActividadesSQL"]

_COLUMNAS_PROGRAMACION = """
    id, prototipo_nodo_id, frente_id, etapa_id, nivel_id, descripcion,
    duracion_dias, dependencias, tramos, fecha_inicio, fecha_termino,
    avance_pct, estatus, bloqueada, es_critica, holgura, desfase,
    cant_base, precio_unitario
"""
"""Lo que el cronograma y el Gantt necesitan de una actividad (§7.6, §11.2).

Es un `select` propio y no `_COLUMNAS` del avance porque son dos vistas de la
misma fila con consumidores distintos: la captura mira cantidades y precios,
la programación mira fechas, duración y dependencias.

`cant_base` y `precio_unitario` son la excepción, y entran por la programación
jerárquica (§7.4): su producto es el **importe** con el que se pondera el
reparto de una ventana gruesa y el avance de una barra resumen
(`domain.programacion.jerarquia`). Se leen de aquí y no del presupuesto vigente
porque la actividad ya **es** el registro que la obra guarda de ese importe —lo
copió el workflow A del CPU vigente (§11.3 A.2)—, y cruzar al contexto
Presupuesto por un dato que ya está en la fila sobraría (§11.1).
"""

_CAMPOS_PROGRAMACION = {
    "duracion_dias": "duracion_dias = :duracion_dias",
    "dependencias": "dependencias = cast(:dependencias as jsonb)",
    "tramos": "tramos = cast(:tramos as jsonb)",
    "frente_id": "frente_id = cast(:frente_id as uuid)",
    "fecha_inicio": "fecha_inicio = :fecha_inicio",
    "fecha_termino": "fecha_termino = :fecha_termino",
}
"""Columnas que `PATCH /actividades/{id}/programacion` puede tocar (§11.2).

Lista blanca, igual que `_CAMPOS_EDITABLES` en `obras_sql.py`: la clave del
dict entra a la sentencia SQL, así que solo pueden entrar estas. Las salidas
del CPM (`es_critica`, `holgura`, `desfase`) no están: nadie las captura, las
deriva el motor y las escribe `guardar_resultado_cpm`.
"""


class ActividadNoModificada(RegistroNoEncontrado):
    """El UPDATE no afectó ninguna fila.

    Pasa si la actividad se borró o salió del alcance del usuario (RLS) entre
    el `obtener()` inicial y el `actualizar_avance()` posterior — una carrera
    genuina, no un bug de la query. Subclasea `RegistroNoEncontrado` (el
    puerto) para que `CapturarAvance` la pueda atrapar sin importar de este
    módulo del borde (§12.11).
    """


class RepositorioActividadesSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def obtener(self, actividad_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select id, obra_id, cant_base, cant_programada,
                           cant_ejecutada, avance_pct, estatus, bloqueada,
                           precio_unitario, precio_destajo, modo_pago
                    from actividad
                    where id = :id
                    """
                ),
                {"id": str(actividad_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def obtener_para_captura(self, actividad_id: UUID) -> dict[str, Any] | None:
        """Como `obtener`, pero **bloqueando la fila** hasta el commit.

        POR QUÉ HACE FALTA, Y POR QUÉ NO BASTA `obtener`

        `PATCH /actividades/{id}/avance` recibe un **absoluto** y el caso de uso
        deriva el delta restando lo que ya había (D6). Eso es un
        lee-modifica-escribe, y desde D5 hay **otro escritor**: el móvil manda
        sus deltas por PowerSync directo a Postgres, sin pasar por la API.

        Con `READ COMMITTED` —el default— la carrera es concreta: la actividad
        va en 10, la web lee 10 y el residente quiere dejarla en 12; entre la
        lectura y la escritura, el móvil sincroniza un +5 y la deja en 15. La
        web calcula delta = +2 sobre el 10 que leyó, y el total queda en 17. Ni
        12 ni 15: un número que nadie capturó.

        El `for update` serializa las dos escrituras. El trigger
        `app.registro_avance_agregar` actualiza `actividad`, así que la
        transacción del móvil espera aquí y el delta se calcula sobre el total
        de verdad.

        `nowait` **no** se usa a propósito: esperar unos milisegundos es mejor
        que devolverle un error al residente por algo que se resuelve solo.
        """
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select id, obra_id, cant_base, cant_programada,
                           cant_ejecutada, avance_pct, estatus, bloqueada,
                           precio_unitario, precio_destajo, modo_pago
                    from actividad
                    where id = :id
                    for update
                    """
                ),
                {"id": str(actividad_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def crear_extra(self, datos: dict[str, Any]) -> UUID:
        """Alta extra-catálogo (§11.2 `POST /actividades`, rol R).

        El uuid se genera en Python y no con `RETURNING`, igual que en
        `proyectos_sql` — aunque aquí la razón es otra: `actividad_scope` usa
        `app.obra_visible(obra_id)`, que consulta `obra` y no `actividad`, así
        que un `RETURNING` funcionaría. Se genera antes por consistencia con el
        resto de los repos que crean, y para que el caso de uso pueda
        registrarlo antes de commitear.

        `cant_programada` nace igual a `cant_base`: un extra se autoriza por la
        cantidad que se va a ejecutar, no hay una "cantidad de proyecto"
        anterior de la que desviarse. Y `cant_ejecutada` queda en cero — el
        avance entra por su camino de siempre (§6, D6).
        """
        actividad_id = uuid4()
        await self._sesion.execute(
            text(
                """
                insert into actividad
                    (id, org_id, obra_id, concepto_id, frente_id, descripcion,
                     cant_base, cant_programada, cant_ejecutada,
                     precio_unitario, precio_destajo, modo_pago,
                     duracion_dias, estatus, extra, orden_cambio)
                values
                    (:id, cast(current_setting('app.org_id') as uuid), :obra_id,
                     cast(:concepto_id as uuid), cast(:frente_id as uuid),
                     :descripcion, :cant_base, :cant_base, 0,
                     :precio_unitario, :precio_destajo,
                     cast(:modo_pago as modo_pago), :duracion_dias,
                     cast(:estatus as estatus_actividad), true, :orden_cambio)
                """
            ),
            {
                "id": str(actividad_id),
                "obra_id": str(datos["obra_id"]),
                "concepto_id": (
                    str(datos["concepto_id"]) if datos.get("concepto_id") else None
                ),
                "frente_id": (
                    str(datos["frente_id"]) if datos.get("frente_id") else None
                ),
                "descripcion": datos["descripcion"],
                "cant_base": datos["cant_base"],
                "precio_unitario": datos["precio_unitario"],
                "precio_destajo": datos["precio_destajo"],
                "modo_pago": datos["modo_pago"],
                "duracion_dias": datos["duracion_dias"],
                "estatus": datos["estatus"],
                "orden_cambio": datos["orden_cambio"],
            },
        )
        return actividad_id

    async def actualizar_avance(
        self,
        actividad_id: UUID,
        *,
        cant_programada: Decimal,
        estatus: str,
    ) -> None:
        """Escribe lo que **sí** se captura: la cantidad programada y el
        estatus de flujo.

        `cant_ejecutada` NO se escribe aquí: desde la decisión D5 la bitácora
        `registro_avance` es su única fuente, y el trigger
        `app.registro_avance_agregar` (migración 0017) la deriva de la suma de
        los deltas. La ruta web y la conciliación offline de PowerSync llegan
        así al mismo número por el mismo camino; si esto volviera a escribir
        un absoluto, la primera captura del móvil lo pisaría con Σ deltas.

        `avance_pct` tampoco: lo deriva `app.actividad_recalcular` (migración
        0007) con las fórmulas fijas del §6.
        """
        resultado = await self._sesion.execute(
            text(
                """
                update actividad
                   set cant_programada = :cant_programada,
                       estatus         = :estatus
                 where id = :id
                """
            ),
            {
                "cant_programada": cant_programada,
                "estatus": estatus,
                "id": str(actividad_id),
            },
        )
        if resultado.rowcount == 0:
            raise ActividadNoModificada(
                f"No se actualizó la actividad {actividad_id}: ya no existe o "
                f"salió de tu alcance."
            )

    async def registrar_captura(
        self,
        actividad_id: UUID,
        *,
        fecha: date,
        delta_ejecutado: Decimal,
        usuario_id: UUID,
        evidencias: list[str],
    ) -> UUID:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    insert into registro_avance
                        (org_id, actividad_id, fecha, delta_ejecutado,
                         usuario_id, evidencias, sync_status)
                    values
                        (cast(current_setting('app.org_id') as uuid),
                         :actividad_id, :fecha, :delta_ejecutado,
                         :usuario_id, cast(:evidencias as jsonb),
                         'sincronizado')
                    returning id
                    """
                ),
                {
                    "actividad_id": str(actividad_id),
                    "fecha": fecha,
                    "delta_ejecutado": delta_ejecutado,
                    "usuario_id": str(usuario_id),
                    "evidencias": json.dumps(evidencias),
                },
            )
        ).scalar_one()
        return fila

    async def nodos_cpm_de_obra(self, obra_id: UUID) -> list[NodoCPM]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select id, duracion_dias, dependencias, tramos, avance_pct,
                           fecha_termino, bloqueada
                    from actividad
                    where obra_id = :obra_id
                    """
                ),
                {"obra_id": str(obra_id)},
            )
        ).mappings().all()

        nodos = []
        for fila in filas:
            avance = float(fila["avance_pct"])
            nodos.append(
                NodoCPM(
                    ref=str(fila["id"]),
                    duracion_dias=float(fila["duracion_dias"]),
                    dependencias=tuple(
                        Dependencia.desde_jsonb(d) for d in fila["dependencias"]
                    ),
                    tramos=tuple(
                        Tramo.desde_jsonb(t) for t in (fila["tramos"] or [])
                    ),
                    avance_pct=avance,
                    # `fecha_termino` guarda la fecha real solo una vez
                    # concluida la actividad; antes de eso es la fecha
                    # planeada vigente, que el motor CPM no debe usar como
                    # "real" (invalidaría su propio cálculo de desfase).
                    fecha_real_termino=fila["fecha_termino"] if avance >= 100 else None,
                    bloqueada=bool(fila["bloqueada"]),
                )
            )
        return nodos

    async def guardar_resultado_cpm(
        self,
        obra_id: UUID,
        resultados: dict[str, dict[str, Any]],
    ) -> None:
        """Persiste las salidas del CPM que otras pantallas consultan sin
        recalcular (Torre de control, reportes): `es_critica`, `holgura`,
        `desfase`.

        Cada valor de ``resultados`` trae exactamente esas tres claves —
        ``{"es_critica": bool, "holgura": float, "desfase": float}``. Las
        fechas tempranas/tardías del CPM (`inicio_temprano`, `fin_temprano`…)
        no se persisten: `calcular_cpm` es una función pura y barata sobre el
        cronograma vigente, así que se recalculan bajo demanda en vez de
        guardarse por fila —evita la ambigüedad de qué es "fecha planeada"
        vs "fecha real" en la única columna `fecha_termino`.
        """
        if not resultados:
            return

        params = [
            {
                "id": ref,
                "es_critica": valores["es_critica"],
                "holgura": valores["holgura"],
                "desfase": valores["desfase"],
            }
            for ref, valores in resultados.items()
        ]

        await self._sesion.execute(
            text(
                """
                update actividad
                   set es_critica = :es_critica,
                       holgura    = :holgura,
                       desfase    = :desfase
                 where id = cast(:id as uuid)
                   and obra_id = cast(:obra_id as uuid)
                """
            ).bindparams(obra_id=str(obra_id)),
            params,
        )

    async def marcar_estatus(self, actividad_id: UUID, estatus: str) -> None:
        # No toca cant_base ni cant_ejecutada: el trigger `app.actividad_recalcular`
        # (database/migrations/0007) solo dispara con esas columnas, así que un
        # estatus de flujo (pendiente_cierre, concluida…) queda tal cual lo fijó
        # el caso de uso de cierres, sin que el auto-estatus del §6 lo pise.
        resultado = await self._sesion.execute(
            text("update actividad set estatus = :estatus where id = :id"),
            {"estatus": estatus, "id": str(actividad_id)},
        )
        if resultado.rowcount == 0:
            raise ActividadNoModificada(
                f"No se actualizó la actividad {actividad_id}: ya no existe o "
                f"salió de tu alcance."
            )

    # --- Programación · CPM (§7.5, §11.2) --------------------------------

    async def programacion_de_obra(self, obra_id: UUID) -> list[dict[str, Any]]:
        """Cronograma completo de la obra (§11.2 `GET /obras/{id}/ruta-critica`).

        Orden estable por antigüedad: la `actividad` no tiene columna de
        orden propia, y el workflow A las inserta en el recorrido en
        profundidad del árbol del prototipo (§11.3 A.2), así que `created_at`
        preserva ese recorrido. El `id` desempata los inserts del mismo lote,
        que comparten `created_at` al milisegundo.
        """
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS_PROGRAMACION}
                    from actividad
                    where obra_id = :obra_id
                    order by created_at, id
                    """
                ),
                {"obra_id": str(obra_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def programacion_de(self, actividad_id: UUID) -> dict[str, Any] | None:
        """Programación de una actividad, con su `obra_id` (§11.2 `PATCH`).

        Trae el `obra_id` porque el ajuste manual necesita el grafo completo
        de la obra para que el motor pueda detectar un ciclo: una arista
        suelta no dice nada (§6).
        """
        fila = (
            await self._sesion.execute(
                text(
                    f"""
                    select obra_id, programa_obra_id, {_COLUMNAS_PROGRAMACION}
                    from actividad
                    where id = :id
                    """
                ),
                {"id": str(actividad_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def aplicar_programacion(
        self,
        obra_id: UUID,
        *,
        programa_obra_id: UUID,
        programaciones: list[dict[str, Any]],
    ) -> None:
        """Baja el cronograma instanciado a las actividades (§7.5, §11.2).

        Ata cada actividad a la versión de `ProgramaObra` que la programó:
        sin eso no habría forma de saber contra qué versión del cronograma se
        midió un corte (§7.5).

        Cada dict trae `id`, `duracion_dias`, `dependencias` y `tramos` (json
        ya serializados), `frente_id`, `fecha_inicio` y `fecha_termino`.
        """
        if not programaciones:
            return

        params = [
            {
                "id": str(p["id"]),
                "duracion_dias": p["duracion_dias"],
                "dependencias": p["dependencias"],
                "tramos": p["tramos"],
                "frente_id": str(p["frente_id"]) if p.get("frente_id") else None,
                "fecha_inicio": p.get("fecha_inicio"),
                "fecha_termino": p.get("fecha_termino"),
            }
            for p in programaciones
        ]

        await self._sesion.execute(
            text(
                """
                update actividad
                   set duracion_dias    = :duracion_dias,
                       dependencias     = cast(:dependencias as jsonb),
                       tramos           = cast(:tramos as jsonb),
                       frente_id        = cast(:frente_id as uuid),
                       fecha_inicio     = :fecha_inicio,
                       fecha_termino    = :fecha_termino,
                       programa_obra_id = cast(:programa_obra_id as uuid)
                 where id = cast(:id as uuid)
                   and obra_id = cast(:obra_id as uuid)
                """
            ).bindparams(
                obra_id=str(obra_id), programa_obra_id=str(programa_obra_id)
            ),
            params,
        )

    async def actualizar_programacion(
        self, actividad_id: UUID, cambios: dict[str, Any]
    ) -> None:
        """Ajuste manual de una actividad (§11.2 `PATCH`).

        Solo se escriben las claves presentes en `cambios` y solo si están en
        `_CAMPOS_PROGRAMACION`; una clave desconocida es un error de
        programación del caso de uso, no una entrada del usuario, así que
        revienta fuerte —mismo criterio que `obras_sql.actualizar`.
        """
        desconocidos = set(cambios) - set(_CAMPOS_PROGRAMACION)
        if desconocidos:
            raise ValueError(
                f"Campos no programables en actividad: "
                f"{', '.join(sorted(desconocidos))}."
            )
        if not cambios:
            return

        asignaciones = ", ".join(_CAMPOS_PROGRAMACION[campo] for campo in cambios)
        params: dict[str, Any] = {"id": str(actividad_id)}
        for campo, valor in cambios.items():
            params[campo] = (
                str(valor) if campo == "frente_id" and valor is not None else valor
            )

        resultado = await self._sesion.execute(
            text(f"update actividad set {asignaciones} where id = :id"),
            params,
        )
        if resultado.rowcount == 0:
            raise ActividadNoModificada(
                f"No se actualizó la actividad {actividad_id}: ya no existe o "
                f"salió de tu alcance."
            )

    async def marcar_bloqueadas(
        self, obra_id: UUID, refs: set[str], bloqueada: bool
    ) -> None:
        """Bloquea o desbloquea actividades por una incidencia `detiene` (§6).

        `refs` puede llegar vacío —una incidencia que se cierra sin haber
        bloqueado nada— y en ese caso no hay nada que actualizar.
        """
        if not refs:
            return

        await self._sesion.execute(
            text(
                """
                update actividad
                   set bloqueada = :bloqueada
                 where obra_id = cast(:obra_id as uuid)
                   and id = any(cast(:refs as uuid[]))
                """
            ),
            {
                "obra_id": str(obra_id),
                "refs": list(refs),
                "bloqueada": bloqueada,
            },
        )
