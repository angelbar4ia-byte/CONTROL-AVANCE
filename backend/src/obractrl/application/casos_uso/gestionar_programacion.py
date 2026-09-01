"""Caso de uso: programación y ruta crítica (§11.2 "Programación · CPM").

Spec §6 (ruta crítica) · §7.5 (ProgramaBase · ProgramaObra) · §7.6 (campos de
programación de la Actividad) · §11.2 · §11.3 A.3 y C.4 · §12.11.

Cuatro operaciones, la misma forma que el resto de los casos de uso: cargan el
estado por sus puertos, dejan que el dominio decida —`domain.programacion`— y
solo entonces persisten. Ninguna regla vive aquí, solo la secuencia.

* `CrearProgramaBase` — la plantilla de duraciones de un prototipo (§7.5).
* `InstanciarProgramaObra` — baja esa plantilla al cronograma de una obra,
  versionando el `ProgramaObra` (§11.2 `POST /obras/{id}/programa`).
* `RecalcularRutaCritica` — corre el motor y **persiste** holgura, criticidad
  y desfase (§11.2 `POST /obras/{id}/ruta-critica/recalcular`).
  `ConsultarRutaCritica` es la misma lectura sin escribir (§11.2 `GET`).
* `EditarProgramacionActividad` — el ajuste manual (§11.2 `PATCH`).

**Un ciclo aborta antes de escribir.** Las tres operaciones que tocan el
cronograma calculan el CPM sobre el grafo resultante *en memoria* y solo
después abren la unidad de trabajo: si `calcular_cpm` levanta
`CicloEnGrafoError`, no se persistió nada (§6).

**Fronteras (§11.1):** los campos de programación viven en `actividad` por el
§7.6, y este contexto los toca **solo** por `RepositorioActividades`;
`RepositorioProgramas` cubre las tres tablas propias del contexto. La fecha de
arranque del cronograma sale de la obra, por `RepositorioObras` — un puerto,
no su tabla.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from obractrl.application.casos_uso.generar_obra_desde_prototipo import ObraNoEncontrada
from obractrl.application.puertos.repositorios import (
    RegistroNoEncontrado,
    RepositorioActividades,
    RepositorioObras,
    RepositorioProgramas,
    UnidadDeTrabajo,
)
from obractrl.domain.programacion.calendario import (
    SEMANA_NATURAL,
    CalendarioLaboral,
)
from obractrl.domain.programacion.cpm import (
    CicloEnGrafoError,
    Dependencia,
    ResultadoCPM,
    Tramo,
    calcular_cpm,
)
from obractrl.domain.programacion.reglas import (
    ActividadProgramable,
    ErrorDeProgramacion,
    ItemProgramaBase,
    ProgramacionDeActividad,
    editar_programacion,
    instanciar_programa,
    nodos_cpm,
    validar_item_base,
)

__all__ = [
    "ActividadEnRuta",
    "ActividadNoProgramable",
    "CalendarioLaboral",
    "CicloEnGrafoError",
    "ComandoCrearProgramaBase",
    "ComandoEditarProgramacion",
    "ComandoInstanciarPrograma",
    "ComandoRecalcularRutaCritica",
    "ConsultarRutaCritica",
    "CrearProgramaBase",
    "EditarProgramacionActividad",
    "ErrorDeProgramacion",
    "InstanciarProgramaObra",
    "ProgramaBaseCreado",
    "ProgramaBaseNoEncontrado",
    "ProgramaInstanciadoEnObra",
    "RecalcularRutaCritica",
    "RutaCritica",
]


class ProgramaBaseNoEncontrado(LookupError):
    """El programa base no existe o está fuera del alcance del usuario (RLS)."""


class ActividadNoProgramable(LookupError):
    """La actividad no existe o está fuera del alcance del usuario (RLS).

    Se declara aparte de `capturar_avance.ActividadNoEncontrada` porque es
    otro contexto (§11.1) y el borde la traduce a su propio `problem+json`;
    para el cliente las dos son un 404 indistinguible, que es lo que RLS
    exige (§12.4).
    """


# --- Comandos ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ComandoCrearProgramaBase:
    """§11.2 `POST /programas-base` (Control de obra).

    `calendario` es la elección de semana laboral o natural del §5.1: la hace
    Control de obra sobre la plantilla del prototipo, y de ahí baja a cada obra
    que se genere o instancie con ella. Sin elección explícita, semana natural
    —el comportamiento de siempre.
    """

    prototipo_id: UUID
    nombre: str | None = None
    items: tuple[ItemProgramaBase, ...] = ()
    calendario: CalendarioLaboral = SEMANA_NATURAL


@dataclass(frozen=True, slots=True)
class ComandoInstanciarPrograma:
    """§11.2 `POST /obras/{id}/programa` (Control de obra, Supervisor)."""

    obra_id: UUID
    fecha_corte: date | None = None


@dataclass(frozen=True, slots=True)
class ComandoRecalcularRutaCritica:
    """§11.2 `POST /obras/{id}/ruta-critica/recalcular` (Supervisor, C)."""

    obra_id: UUID
    fecha_corte: date | None = None


@dataclass(frozen=True, slots=True)
class ComandoEditarProgramacion:
    """§11.2 `PATCH /actividades/{id}/programacion` (Supervisor, C).

    `None` significa "no lo mandaron"; una lista vacía de `dependencias` sí
    es un cambio —deja la actividad sin predecesoras—, y una de `tramos` le
    quita la interrupción a la actividad (§7.6).
    """

    actividad_id: UUID
    duracion_dias: Decimal | None = None
    dependencias: tuple[Dependencia, ...] | None = None
    frente_id: UUID | None = None
    fecha_inicio: date | None = None
    fecha_termino: date | None = None
    tramos: tuple[Tramo, ...] | None = None


# --- Resultados ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProgramaBaseCreado:
    id: UUID
    version: int
    n_items: int
    calendario: CalendarioLaboral = SEMANA_NATURAL


@dataclass(frozen=True, slots=True)
class ActividadEnRuta:
    """Una actividad con su cálculo de CPM (§6, §7.6)."""

    actividad_id: UUID
    descripcion: str | None
    frente_id: UUID | None
    duracion_dias: Decimal
    dependencias: tuple[Dependencia, ...]
    inicio_temprano: date
    fin_temprano: date
    inicio_tardio: date
    fin_tardio: date
    holgura: float
    desfase: float
    es_critica: bool
    bloqueada: bool
    avance_pct: Decimal
    tramos: tuple[Tramo, ...] = ()


@dataclass(frozen=True, slots=True)
class RutaCritica:
    """Cronograma calculado de una obra (§11.2 `GET /obras/{id}/ruta-critica`)."""

    obra_id: UUID
    fecha_inicio: date
    fecha_corte: date
    programa_obra_id: UUID | None
    version: int | None
    actividades: tuple[ActividadEnRuta, ...]
    calendario: CalendarioLaboral = SEMANA_NATURAL
    """Con qué calendario se calcularon estas fechas (§7.5, 0040).

    Viaja en la respuesta porque el cliente lo necesita para **dibujar**: el
    Gantt convierte `duracion_dias` y los `offset_dias` de los tramos a ancho
    de barra, y sin saber qué días se saltan pintaría una actividad de cinco
    días laborales como cinco casillas corridas.
    """

    @property
    def fin_programado(self) -> date | None:
        """Última fecha temprana de término: el fin del cronograma (§6)."""
        if not self.actividades:
            return None
        return max(a.fin_temprano for a in self.actividades)

    @property
    def criticas(self) -> tuple[ActividadEnRuta, ...]:
        return tuple(a for a in self.actividades if a.es_critica)


@dataclass(frozen=True, slots=True)
class ProgramaInstanciadoEnObra:
    """Resultado de `POST /obras/{id}/programa` (§11.2)."""

    programa_obra_id: UUID
    version: int
    n_actividades: int
    ruta: RutaCritica
    sin_item: tuple[str, ...] = field(default=())
    refs_no_resueltas: tuple[str, ...] = field(default=())


# --- Mapeo de filas a dominio -------------------------------------------


def _a_actividad(fila: dict) -> ActividadProgramable:
    return ActividadProgramable(
        id=str(fila["id"]),
        prototipo_nodo_id=str(fila["prototipo_nodo_id"])
        if fila.get("prototipo_nodo_id")
        else None,
        etapa_id=str(fila["etapa_id"]) if fila.get("etapa_id") else None,
        frente_id=str(fila["frente_id"]) if fila.get("frente_id") else None,
        duracion_dias=Decimal(str(fila["duracion_dias"])),
        dependencias=tuple(
            Dependencia.desde_jsonb(dep) for dep in (fila["dependencias"] or [])
        ),
        fecha_inicio=fila["fecha_inicio"],
        fecha_termino=fila["fecha_termino"],
        avance_pct=Decimal(str(fila["avance_pct"] or 0)),
        bloqueada=bool(fila["bloqueada"]),
        tramos=tuple(Tramo.desde_jsonb(t) for t in (fila["tramos"] or [])),
    )


def _a_item(fila: dict) -> ItemProgramaBase:
    return ItemProgramaBase(
        duracion_dias=Decimal(str(fila["duracion_dias"])),
        prototipo_nodo_id=str(fila["prototipo_nodo_id"])
        if fila["prototipo_nodo_id"]
        else None,
        etapa_id=str(fila["etapa_id"]) if fila["etapa_id"] else None,
        frente_id=str(fila["frente_id"]) if fila["frente_id"] else None,
        dependencias=tuple(
            Dependencia.desde_jsonb(dep) for dep in (fila["dependencias"] or [])
        ),
        tramos=tuple(Tramo.desde_jsonb(t) for t in (fila["tramos"] or [])),
        orden=fila["orden"],
    )


def _serializar(dependencias: tuple[Dependencia, ...]) -> str:
    """Misma forma que escribe el workflow A (§11.3 A.2), para que el jsonb de
    `actividad.dependencias` tenga una sola representación."""
    return json.dumps(
        [
            {"ref": dep.ref, "tipo": dep.tipo, "lag_dias": dep.lag_dias}
            for dep in dependencias
        ]
    )


def _serializar_tramos(tramos: tuple[Tramo, ...]) -> str:
    """Misma forma que escribe el workflow A (§11.3 A.2), para que el jsonb de
    `actividad.tramos` tenga una sola representación."""
    return json.dumps([tramo.a_jsonb() for tramo in tramos])


def _a_registro(programacion: ProgramacionDeActividad) -> dict:
    return {
        "id": programacion.actividad_id,
        "duracion_dias": programacion.duracion_dias,
        "dependencias": _serializar(programacion.dependencias),
        "tramos": _serializar_tramos(programacion.tramos),
        "frente_id": programacion.frente_id,
        "fecha_inicio": programacion.fecha_inicio,
        "fecha_termino": programacion.fecha_termino,
    }


def _ensamblar_ruta(
    *,
    obra_id: UUID,
    filas: list[dict],
    resultados: dict[str, ResultadoCPM],
    fecha_inicio: date,
    fecha_corte: date,
    programa: dict | None,
    calendario: CalendarioLaboral,
) -> RutaCritica:
    actividades = tuple(
        ActividadEnRuta(
            actividad_id=fila["id"],
            descripcion=fila["descripcion"],
            frente_id=fila["frente_id"],
            duracion_dias=Decimal(str(fila["duracion_dias"])),
            dependencias=tuple(
                Dependencia.desde_jsonb(dep) for dep in (fila["dependencias"] or [])
            ),
            inicio_temprano=resultado.inicio_temprano,
            fin_temprano=resultado.fin_temprano,
            inicio_tardio=resultado.inicio_tardio,
            fin_tardio=resultado.fin_tardio,
            holgura=resultado.holgura,
            desfase=resultado.desfase,
            es_critica=resultado.es_critica,
            bloqueada=bool(fila["bloqueada"]),
            avance_pct=Decimal(str(fila["avance_pct"] or 0)),
            tramos=tuple(Tramo.desde_jsonb(t) for t in (fila["tramos"] or [])),
        )
        for fila in filas
        if (resultado := resultados.get(str(fila["id"]))) is not None
    )
    return RutaCritica(
        obra_id=obra_id,
        fecha_inicio=fecha_inicio,
        fecha_corte=fecha_corte,
        programa_obra_id=programa["id"] if programa else None,
        version=programa["version"] if programa else None,
        actividades=actividades,
        calendario=calendario,
    )


def _calendario_de(programa: dict | None) -> CalendarioLaboral:
    """El calendario con el que se debe calcular una obra (§7.5, 0040).

    Sin `ProgramaObra` vigente —una obra cuyo cronograma nunca se instanció—
    manda la semana natural: es el default de la columna y el del motor, y deja
    la ruta crítica calculable desde el día uno, igual que la `fecha_inicio`
    ausente cae a hoy (`_ConCronograma`).
    """
    if programa is None:
        return SEMANA_NATURAL
    return CalendarioLaboral.de(programa.get("dias_habiles"))


def _a_guardable(resultados: dict[str, ResultadoCPM]) -> dict[str, dict]:
    """Las tres salidas que `guardar_resultado_cpm` persiste (§7.6)."""
    return {
        ref: {
            "es_critica": r.es_critica,
            "holgura": r.holgura,
            "desfase": r.desfase,
        }
        for ref, r in resultados.items()
    }


class _ConCronograma:
    """Lo que comparten los casos de uso que leen el cronograma de una obra.

    La fecha de arranque sale de `obra.fecha_inicio` (§7.2); si la obra aún no
    la tiene fijada se usa hoy, que es lo mismo que hace el motor por default
    (`cpm.calcular_cpm`) y deja el cálculo utilizable desde el día uno.
    """

    def __init__(
        self,
        *,
        actividades: RepositorioActividades,
        obras: RepositorioObras,
        programas: RepositorioProgramas,
    ) -> None:
        self._actividades = actividades
        self._obras = obras
        self._programas = programas

    async def _contexto(
        self, obra_id: UUID, fecha_corte: date | None
    ) -> tuple[list[dict], date, date, dict | None]:
        obra = await self._obras.obtener(obra_id)
        if obra is None:
            raise ObraNoEncontrada(f"Obra {obra_id} no encontrada en tu alcance.")

        programa = await self._programas.programa_vigente(obra_id)
        filas = await self._actividades.programacion_de_obra(obra_id)

        arranque = obra["fecha_inicio"] or date.today()
        corte = fecha_corte or (programa or {}).get("fecha_corte") or date.today()
        return filas, arranque, corte, programa


class CrearProgramaBase:
    """`POST /programas-base` (Control de obra, §11.2).

    Cada alta es una **versión nueva** del programa base del prototipo y
    retira la anterior (§7.5, §10.8: cada carga es una versión). No se edita
    la vigente en su lugar: eso borraría contra qué plantilla se generaron las
    obras que ya existen.
    """

    def __init__(
        self, *, programas: RepositorioProgramas, uow: UnidadDeTrabajo
    ) -> None:
        self._programas = programas
        self._uow = uow

    async def ejecutar(self, cmd: ComandoCrearProgramaBase) -> ProgramaBaseCreado:
        items = [validar_item_base(item) for item in cmd.items]

        async with self._uow:
            programa_base_id = await self._programas.crear_base(
                {
                    "prototipo_id": cmd.prototipo_id,
                    "nombre": cmd.nombre,
                    "dias_habiles": cmd.calendario.a_lista(),
                }
            )
            await self._programas.agregar_items_base(
                programa_base_id,
                [
                    {
                        "prototipo_nodo_id": item.prototipo_nodo_id,
                        "etapa_id": item.etapa_id,
                        "frente_id": item.frente_id,
                        "duracion_dias": item.duracion_dias,
                        "dependencias": [
                            {
                                "ref": dep.ref,
                                "tipo": dep.tipo,
                                "lag_dias": dep.lag_dias,
                            }
                            for dep in item.dependencias
                        ],
                        "tramos": [tramo.a_jsonb() for tramo in item.tramos],
                        # Sin `orden` explícito manda la posición en la que
                        # llegó el renglón: es la que el cliente ve (§7.5).
                        "orden": item.orden or orden,
                    }
                    for orden, item in enumerate(items)
                ],
            )
            await self._uow.commit()

        creado = await self._programas.obtener_base(programa_base_id)
        return ProgramaBaseCreado(
            id=programa_base_id,
            version=creado["version"] if creado else 1,
            n_items=len(items),
            # Se relee, no se devuelve `cmd.calendario`: lo que el cliente debe
            # ver es el calendario que quedó guardado.
            calendario=CalendarioLaboral.de(
                creado["dias_habiles"] if creado else None
            ),
        )


class ConsultarRutaCritica(_ConCronograma):
    """`GET /obras/{id}/ruta-critica` (R su obra, S, C, SI — §11.2).

    Calcula sin escribir: `calcular_cpm` es puro y barato sobre el cronograma
    vigente, así que la lectura no necesita el recálculo persistido para dar
    fechas frescas (mismo criterio del docstring de `guardar_resultado_cpm`).
    """

    async def ejecutar(
        self, obra_id: UUID, *, fecha_corte: date | None = None
    ) -> RutaCritica:
        filas, arranque, corte, programa = await self._contexto(obra_id, fecha_corte)
        calendario = _calendario_de(programa)
        resultados = calcular_cpm(
            nodos_cpm([_a_actividad(f) for f in filas]),
            arranque,
            fecha_corte=corte,
            calendario=calendario,
        )
        return _ensamblar_ruta(
            obra_id=obra_id,
            filas=filas,
            resultados=resultados,
            fecha_inicio=arranque,
            fecha_corte=corte,
            programa=programa,
            calendario=calendario,
        )


class RecalcularRutaCritica(_ConCronograma):
    """`POST /obras/{id}/ruta-critica/recalcular` (S, C — §11.2).

    También es el manejador del evento `ActividadCerrada` (§11.1, §11.3 C.4):
    misma operación, otro disparador.

    Es **idempotente**: con el mismo cronograma y la misma fecha de corte el
    motor da el mismo resultado, así que correrlo dos veces deja exactamente
    los mismos `es_critica`, `holgura` y `desfase` (§6, "recálculo programado
    + on-demand" —lo programado y lo on-demand se pisan sin conflicto).
    """

    def __init__(
        self,
        *,
        actividades: RepositorioActividades,
        obras: RepositorioObras,
        programas: RepositorioProgramas,
        uow: UnidadDeTrabajo,
    ) -> None:
        super().__init__(actividades=actividades, obras=obras, programas=programas)
        self._uow = uow

    async def ejecutar(self, cmd: ComandoRecalcularRutaCritica) -> RutaCritica:
        filas, arranque, corte, programa = await self._contexto(
            cmd.obra_id, cmd.fecha_corte
        )
        calendario = _calendario_de(programa)
        resultados = calcular_cpm(
            nodos_cpm([_a_actividad(f) for f in filas]),
            arranque,
            fecha_corte=corte,
            calendario=calendario,
        )

        async with self._uow:
            await self._actividades.guardar_resultado_cpm(
                cmd.obra_id, _a_guardable(resultados)
            )
            if programa is not None:
                # Deja constancia de contra qué fecha se midió el desfase
                # (§7.5 `ProgramaObra.fecha_corte`).
                await self._programas.fijar_fecha_corte(programa["id"], corte)
            await self._uow.commit()

        return _ensamblar_ruta(
            obra_id=cmd.obra_id,
            filas=filas,
            resultados=resultados,
            fecha_inicio=arranque,
            fecha_corte=corte,
            programa=programa,
            calendario=calendario,
        )


class InstanciarProgramaObra(_ConCronograma):
    """`POST /obras/{id}/programa` — instanciar / versionar (C, S — §11.2).

    Es lo que cierra el pendiente que dejó el workflow A: la generación de la
    obra copia las dependencias del programa base **tal cual**, con `ref` que
    apuntan a nodos del prototipo; aquí se traducen a ids de actividad
    (`domain.programacion.reglas.instanciar_programa`) y el cronograma queda
    calculable de verdad.

    Vuelve a correr el motor y persiste su resultado en la misma unidad de
    trabajo: un programa instanciado cuya ruta crítica quedara sin calcular
    sería un cronograma a medias.
    """

    def __init__(
        self,
        *,
        actividades: RepositorioActividades,
        obras: RepositorioObras,
        programas: RepositorioProgramas,
        uow: UnidadDeTrabajo,
    ) -> None:
        super().__init__(actividades=actividades, obras=obras, programas=programas)
        self._uow = uow

    async def ejecutar(
        self, cmd: ComandoInstanciarPrograma
    ) -> ProgramaInstanciadoEnObra:
        obra = await self._obras.obtener(cmd.obra_id)
        if obra is None:
            raise ObraNoEncontrada(f"Obra {cmd.obra_id} no encontrada en tu alcance.")
        if not obra["prototipo_id"]:
            raise ErrorDeProgramacion(
                f"La obra {cmd.obra_id} no tiene prototipo (§7.2): no hay "
                f"programa base del cual instanciar su cronograma (§7.5)."
            )

        prototipo_id = UUID(str(obra["prototipo_id"]))
        filas = await self._actividades.programacion_de_obra(cmd.obra_id)
        items = [
            _a_item(f)
            for f in await self._programas.items_base_vigente(prototipo_id)
        ]
        # El calendario baja de la plantilla igual que las duraciones, pero no
        # viene con los items: es del cronograma completo, no de cada renglón
        # (`programas_sql.base_vigente`, 0040).
        base = await self._programas.base_vigente(prototipo_id)
        calendario = CalendarioLaboral.de(
            base["dias_habiles"] if base else None
        )

        actividades = [_a_actividad(f) for f in filas]
        instanciado = instanciar_programa(actividades=actividades, items=items)

        por_id = {p.actividad_id: p for p in instanciado.actividades}
        arranque = obra["fecha_inicio"] or date.today()
        corte = cmd.fecha_corte or date.today()

        # Antes de escribir: un ciclo levanta `CicloEnGrafoError` aquí y la
        # obra se queda con su cronograma anterior intacto (§6).
        resultados = calcular_cpm(
            nodos_cpm(actividades, por_id),
            arranque,
            fecha_corte=corte,
            calendario=calendario,
        )

        async with self._uow:
            programa = await self._programas.instanciar(
                cmd.obra_id,
                fecha_corte=corte,
                dias_habiles=calendario.a_lista(),
            )
            await self._actividades.aplicar_programacion(
                cmd.obra_id,
                programa_obra_id=programa["id"],
                programaciones=[
                    _a_registro(p) for p in instanciado.actividades
                ],
            )
            await self._actividades.guardar_resultado_cpm(
                cmd.obra_id, _a_guardable(resultados)
            )
            await self._uow.commit()

        # Se releen para que la ruta devuelta refleje lo recién escrito
        # (duración y dependencias nuevas), no lo que había antes.
        filas_nuevas = await self._actividades.programacion_de_obra(cmd.obra_id)
        return ProgramaInstanciadoEnObra(
            programa_obra_id=programa["id"],
            version=programa["version"],
            n_actividades=len(instanciado.actividades),
            sin_item=instanciado.sin_item,
            refs_no_resueltas=instanciado.refs_no_resueltas,
            ruta=_ensamblar_ruta(
                obra_id=cmd.obra_id,
                filas=filas_nuevas,
                resultados=resultados,
                fecha_inicio=arranque,
                fecha_corte=corte,
                programa=programa,
                calendario=calendario,
            ),
        )


class EditarProgramacionActividad:
    """`PATCH /actividades/{id}/programacion` (S, C — §11.2).

    Ajusta fechas, duración y dependencias de una actividad y recalcula la
    ruta crítica de su obra en la misma unidad de trabajo: cambiar una
    duración mueve la holgura de todas las demás, y dejar el CPM sin
    actualizar haría que la Torre reportara una ruta que ya no existe (§6).

    Lee `RepositorioProgramas` sólo para el calendario del cronograma (0040):
    los días que se ajustan aquí son días hábiles o corridos según lo que diga
    el `ProgramaObra` vigente, y recalcular con semana natural una obra
    programada en semana laboral movería las fechas de **todas** las demás
    actividades en la misma transacción.
    """

    def __init__(
        self,
        *,
        actividades: RepositorioActividades,
        obras: RepositorioObras,
        programas: RepositorioProgramas,
        uow: UnidadDeTrabajo,
    ) -> None:
        self._actividades = actividades
        self._obras = obras
        self._programas = programas
        self._uow = uow

    async def ejecutar(self, cmd: ComandoEditarProgramacion) -> ActividadEnRuta:
        fila = await self._actividades.programacion_de(cmd.actividad_id)
        if fila is None:
            raise ActividadNoProgramable(
                f"Actividad {cmd.actividad_id} no encontrada en tu alcance."
            )

        obra_id = fila["obra_id"]
        filas = await self._actividades.programacion_de_obra(obra_id)
        actividades = [_a_actividad(f) for f in filas]

        actual = next(
            a for a in actividades if a.id == str(cmd.actividad_id)
        )
        programacion = editar_programacion(
            actual,
            duracion_dias=cmd.duracion_dias,
            dependencias=cmd.dependencias,
            frente_id=str(cmd.frente_id) if cmd.frente_id else None,
            fecha_inicio=cmd.fecha_inicio,
            fecha_termino=cmd.fecha_termino,
            tramos=cmd.tramos,
            refs_de_la_obra=frozenset(a.id for a in actividades),
        )

        obra = await self._obras.obtener(obra_id)
        arranque = (obra or {}).get("fecha_inicio") or date.today()
        calendario = _calendario_de(await self._programas.programa_vigente(obra_id))

        # El ciclo se detecta sobre el grafo completo y **antes** de escribir.
        resultados = calcular_cpm(
            nodos_cpm(actividades, {programacion.actividad_id: programacion}),
            arranque,
            calendario=calendario,
        )

        async with self._uow:
            try:
                await self._actividades.actualizar_programacion(
                    cmd.actividad_id, _cambios(cmd, programacion)
                )
            except RegistroNoEncontrado as exc:
                raise ActividadNoProgramable(
                    f"Actividad {cmd.actividad_id} ya no está en tu alcance."
                ) from exc
            await self._actividades.guardar_resultado_cpm(
                obra_id, _a_guardable(resultados)
            )
            await self._uow.commit()

        # Se relee para devolver lo que quedó escrito, no lo que se propuso:
        # si el UPDATE recortó un decimal (`numeric(8,2)`), el cliente debe
        # ver el valor real.
        actualizada = await self._actividades.programacion_de(cmd.actividad_id)
        if actualizada is None:  # pragma: no cover - carrera con RLS
            raise ActividadNoProgramable(
                f"Actividad {cmd.actividad_id} ya no está en tu alcance."
            )

        ruta = _ensamblar_ruta(
            obra_id=obra_id,
            filas=[actualizada],
            resultados=resultados,
            fecha_inicio=arranque,
            fecha_corte=date.today(),
            programa=None,
            calendario=calendario,
        )
        return ruta.actividades[0]


def _cambios(
    cmd: ComandoEditarProgramacion, programacion: ProgramacionDeActividad
) -> dict:
    """Solo lo que el cliente mandó llega al UPDATE (§11.2 semántica de PATCH)."""
    cambios: dict = {}
    if cmd.duracion_dias is not None:
        cambios["duracion_dias"] = programacion.duracion_dias
    if cmd.dependencias is not None:
        cambios["dependencias"] = _serializar(programacion.dependencias)
    if cmd.tramos is not None:
        cambios["tramos"] = _serializar_tramos(programacion.tramos)
        # Partir una actividad redefine sus días de trabajo (`editar_programacion`
        # los deriva de la suma de los tramos), así que la duración se escribe
        # aunque el cliente no la haya mandado: dejar la columna con el valor
        # viejo la desincronizaría del detalle que sí se guardó.
        cambios["duracion_dias"] = programacion.duracion_dias
    if cmd.frente_id is not None:
        cambios["frente_id"] = programacion.frente_id
    if cmd.fecha_inicio is not None:
        cambios["fecha_inicio"] = programacion.fecha_inicio
    if cmd.fecha_termino is not None:
        cambios["fecha_termino"] = programacion.fecha_termino
    return cambios
