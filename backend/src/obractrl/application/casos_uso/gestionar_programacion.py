"""Caso de uso: programación y ruta crítica (§11.2 "Programación · CPM").

Spec §6 (ruta crítica) · §7.5 (ProgramaBase · ProgramaObra) · §7.6 (campos de
programación de la Actividad) · §11.2 · §11.3 A.3 y C.4 · §12.11.

Cuatro operaciones, la misma forma que el resto de los casos de uso: cargan el
estado por sus puertos, dejan que el dominio decida —`domain.programacion`— y
solo entonces persisten. Ninguna regla vive aquí, solo la secuencia.

* `CrearProgramaBase` — la plantilla de duraciones de un prototipo (§7.5).
* `ConsultarArbolPrograma` — el cronograma visto **como el árbol WBS**: las
  barras resumen derivadas de nivel y de etapa, con su avance ponderado y sus
  conflictos padre-hijo (§7.4, `GET /obras/{id}/programa/arbol`).
* `ProgramarNodoDelArbol` — captura gruesa: una ventana de días en un nodo
  `nivel` o `etapa` se reparte entre los conceptos que cuelgan de él
  (§11.2 `POST /obras/{id}/programa/nodos/{prototipo_nodo_id}`).
* `InstanciarProgramaObra` — baja esa plantilla al cronograma de una obra,
  versionando el `ProgramaObra` (§11.2 `POST /obras/{id}/programa`).
* `ReplicarProgramaEnObras` — la misma bajada a **muchas** obras del prototipo
  de una sola vez (§11.2 `POST /programas-base/{id}/replicar`). Es
  orquestación sobre `InstanciarProgramaObra`, no un motor aparte.
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
from collections.abc import Sequence
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
from obractrl.domain.programacion.jerarquia import (
    ConflictoJerarquia,
    ErrorDeJerarquia,
    HojaProgramable,
    NodoWBS,
    ResumenNodo,
    hojas_por_nodo,
    repartir_secuencial,
    resumir_arbol,
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
from obractrl.domain.shared.diccionario import ClaseNodo

__all__ = [
    "ActividadEnRuta",
    "ActividadNoProgramable",
    "ArbolDePrograma",
    "CalendarioLaboral",
    "CicloEnGrafoError",
    "ComandoCrearProgramaBase",
    "ComandoEditarProgramacion",
    "ComandoInstanciarPrograma",
    "ComandoProgramarNodo",
    "ComandoRecalcularRutaCritica",
    "ComandoReplicarPrograma",
    "ConflictoJerarquia",
    "ConflictoNoResuelto",
    "ConsultarArbolPrograma",
    "ConsultarRutaCritica",
    "CrearProgramaBase",
    "EditarProgramacionActividad",
    "ErrorDeJerarquia",
    "ErrorDeProgramacion",
    "InstanciarProgramaObra",
    "NodoNoProgramable",
    "NodoProgramado",
    "ProgramaBaseCreado",
    "ProgramaBaseNoEncontrado",
    "ProgramaInstanciadoEnObra",
    "ProgramarNodoDelArbol",
    "RecalcularRutaCritica",
    "ReplicaDePrograma",
    "ReplicaEnObra",
    "ReplicarProgramaEnObras",
    "ResumenNodo",
    "RutaCritica",
]


class ProgramaBaseNoEncontrado(LookupError):
    """El programa base no existe o está fuera del alcance del usuario (RLS)."""


class NodoNoProgramable(LookupError):
    """El nodo del árbol no existe en el prototipo de la obra, o no tiene
    ninguna actividad debajo que programar (§7.4).

    Es un `LookupError` y no un error de programación porque para el cliente es
    lo mismo que pedir una actividad inexistente: un 404 (§11.2). Un nodo real
    del árbol sin hojas debajo cae aquí a propósito — no hay nada que repartir,
    y decirlo con un 422 sugeriría que la ventana capturada estaba mal.
    """


class ConflictoNoResuelto(ErrorDeProgramacion):
    """La ventana que se quiere imponer al nodo choca con lo que ya traen sus
    hojas, y nadie ha decidido cuál cifra conservar (§7.5).

    **No se resuelve solo, y esa es la decisión.** Que el padre pisara al hijo
    borraría un ajuste fino que alguien capturó a propósito; que el hijo ganara
    volvería inútil la captura gruesa. La operación se aborta sin escribir nada
    y el conflicto viaja adentro para que el borde se lo presente al usuario con
    las dos cifras (§11.2). Reintentar con `forzar` es la respuesta "conservo la
    del padre"; no reintentar es "conservo la de los hijos".
    """

    def __init__(self, conflicto: ConflictoJerarquia) -> None:
        super().__init__(
            f"El nodo {conflicto.nombre!r} se programaría con "
            f"{conflicto.dias_capturados} días, pero sus "
            f"{len(conflicto.actividades)} concepto(s) ya programados ocupan "
            f"{conflicto.dias_derivados}. Decide cuál cifra conservar: repetir "
            f"la operación forzándola reparte los {conflicto.dias_capturados} "
            f"días y pisa lo capturado; no repetirla deja el detalle como está "
            f"(§7.5)."
        )
        self.conflicto = conflicto


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
    profundidad_captura: ClaseNodo = ClaseNodo.CONCEPTO
    """A qué altura del árbol WBS se sugiere capturar esta plantilla (0041).

    Es un **default de pantalla**, no una restricción: el editor abre ahí para
    que el equipo vea lo mismo, y cualquiera puede bajar a capturar más fino sin
    reversionar el programa base. Sin elección, `concepto` —renglón por
    renglón—, que es lo único que existía antes."""


@dataclass(frozen=True, slots=True)
class ComandoInstanciarPrograma:
    """§11.2 `POST /obras/{id}/programa` (Control de obra, Supervisor)."""

    obra_id: UUID
    fecha_corte: date | None = None


@dataclass(frozen=True, slots=True)
class ComandoReplicarPrograma:
    """§11.2 `POST /programas-base/{id}/replicar` (Control de obra, Supervisor).

    El gesto que pidió el jefe de obra: "componentes que ayuden a establecer el
    programa base del prototipo y de ahí replicarse para las obras". Un cluster
    de 40 casas del mismo modelo son 40 instanciaciones idénticas, y hacerlas
    de una en una por la pantalla de Programación no es operable.

    `obras` son las obras destino elegidas a mano, no "todas las del
    prototipo": replicar es una decisión de qué casas se reprograman, y las que
    ya van avanzadas con su cronograma ajustado no siempre entran.
    """

    programa_base_id: UUID
    obras: tuple[UUID, ...] = ()
    fecha_corte: date | None = None


@dataclass(frozen=True, slots=True)
class ComandoProgramarNodo:
    """§11.2 `POST /obras/{id}/programa/nodos/{prototipo_nodo_id}` (C, S).

    La captura gruesa del §7.4: se programa el nodo `nivel` o `etapa` y los
    conceptos que cuelgan de él se acomodan uno tras otro dentro de esa ventana
    (`domain.programacion.jerarquia.repartir_secuencial`).
    """

    obra_id: UUID
    prototipo_nodo_id: UUID
    duracion_dias: Decimal
    fecha_inicio: date | None = None
    """Ancla de la ventana. Sin ella se usa el inicio que ya traen las hojas del
    nodo y, si ninguna lo tiene, el arranque de la obra: reprogramar la duración
    de una etapa que ya está colocada en el calendario no debería moverla de
    lugar sin que nadie lo pidiera."""
    forzar: bool = False
    """La respuesta del usuario al conflicto padre-hijo: `True` es "conservo la
    cifra del padre" y pisa lo que las hojas traían. Sin él, un conflicto aborta
    la operación sin escribir nada (`ConflictoNoResuelto`)."""


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
    inicio_dias: Decimal | None = None


# --- Resultados ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProgramaBaseCreado:
    id: UUID
    version: int
    n_items: int
    calendario: CalendarioLaboral = SEMANA_NATURAL
    profundidad_captura: ClaseNodo = ClaseNodo.CONCEPTO


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


@dataclass(frozen=True, slots=True)
class ArbolDePrograma:
    """El cronograma de la obra visto como el árbol WBS (§7.4, §11.2).

    Un renglón por nodo con actividades debajo, en el orden en que el árbol se
    recorre —padre antes que hijos—, que es como se dibuja el Gantt. Los
    renglones de `nivel` y `etapa` son **barras resumen derivadas**: el
    residente sigue capturando sólo en conceptos, y estas se recalculan de sus
    hojas cada vez que se piden (§7.6).
    """

    obra_id: UUID
    prototipo_id: UUID
    profundidad_captura: ClaseNodo
    """Dónde abrir el editor, según lo que guardó el programa base (0041). Es
    una sugerencia, no una jaula: los renglones vienen todos y cada uno trae su
    `profundidad` para que el cliente pueda bajar."""
    calendario: CalendarioLaboral
    nodos: tuple[ResumenNodo, ...]

    @property
    def conflictos(self) -> tuple[ConflictoJerarquia, ...]:
        """Los nodos cuya ventana capturada no cuadra con sus hojas (§7.5).

        Es un aviso no bloqueante, del mismo tenor que
        `ProgramaInstanciado.sin_item`: la pantalla lo marca y el usuario elige
        cuál cifra conservar; nadie resuelve por él.
        """
        return tuple(
            nodo.conflicto for nodo in self.nodos if nodo.conflicto is not None
        )


@dataclass(frozen=True, slots=True)
class NodoProgramado:
    """Resultado de repartir una ventana gruesa (§11.2, §7.4)."""

    obra_id: UUID
    prototipo_nodo_id: UUID
    duracion_dias: Decimal
    fecha_inicio: date
    fecha_termino: date
    actividades: tuple[UUID, ...]
    """Las hojas que quedaron reprogramadas, en el orden en que se acomodaron."""
    ruta: RutaCritica
    omitidas: tuple[UUID, ...] = ()
    """Hojas que el reparto **no** tocó por estar interrumpidas en tramos (§7.6).

    Partir el muro para colar la losa es de la secuencia constructiva del
    prototipo, expresada en días de esa actividad; una ventana gruesa no tiene
    con qué decidir cómo volver a partirla. Reescalar los tramos a ojo o
    borrarlos serían las dos formas de destruir esa decisión en silencio, así
    que la actividad conserva lo suyo y se reporta para que el usuario la
    programe a mano si hace falta (§11.2 `PATCH`)."""


@dataclass(frozen=True, slots=True)
class ReplicaEnObra:
    """Qué pasó con **una** obra del lote (§11.2 `.../replicar`).

    Es a propósito el mismo reporte que da la instanciación individual —versión
    creada, actividades programadas, huecos de plantilla y referencias
    colgantes— más el `motivo` de la que no se pudo. Las dos mitades no
    coexisten: o quedó programada (`programa_obra_id` y `version` con valor) o
    trae `motivo`.
    """

    obra_id: UUID
    clave: str | None = None
    """Clave de la obra ("FRESNO 01", §10.1). Viaja en el resultado porque el
    reporte lo lee una persona: un renglón que solo dijera el UUID de la casa
    que falló obligaría a cruzarlo contra otra pantalla."""
    programa_obra_id: UUID | None = None
    version: int | None = None
    n_actividades: int = 0
    sin_item: tuple[str, ...] = ()
    refs_no_resueltas: tuple[str, ...] = ()
    motivo: str | None = None
    """Por qué **no** quedó programada, en el idioma del jefe de obra. `None`
    en las que sí."""

    @property
    def programada(self) -> bool:
        return self.motivo is None


@dataclass(frozen=True, slots=True)
class ReplicaDePrograma:
    """Resultado del lote completo (§11.2 `POST /programas-base/{id}/replicar`).

    Un renglón por obra pedida, en el orden en que se pidieron: el lote es de
    **mejor esfuerzo**, así que el resultado no es un sí o un no sino un parte
    por casa.
    """

    programa_base_id: UUID
    prototipo_id: UUID
    version_base: int
    obras: tuple[ReplicaEnObra, ...] = ()

    @property
    def programadas(self) -> tuple[ReplicaEnObra, ...]:
        return tuple(obra for obra in self.obras if obra.programada)

    @property
    def fallidas(self) -> tuple[ReplicaEnObra, ...]:
        return tuple(obra for obra in self.obras if not obra.programada)


# --- Mapeo de filas a dominio -------------------------------------------


def _a_decimal(valor: object) -> Decimal | None:
    """Columna `numeric` opcional → `Decimal`. `None` se conserva: es "sin
    ancla", no cero, y confundirlos clavaría todo al día 1."""
    return None if valor is None else Decimal(str(valor))


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
        inicio_dias=_a_decimal(fila.get("inicio_dias")),
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
        inicio_dias=_a_decimal(fila.get("inicio_dias")),
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
        "inicio_dias": programacion.inicio_dias,
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
                    "profundidad_captura": str(cmd.profundidad_captura),
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
                        "inicio_dias": item.inicio_dias,
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
            profundidad_captura=ClaseNodo(
                str(creado["profundidad_captura"])
                if creado and creado.get("profundidad_captura")
                else ClaseNodo.CONCEPTO
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


class ReplicarProgramaEnObras:
    """`POST /programas-base/{id}/replicar` — el programa base a muchas obras.

    Spec §7.5 · §11.2. Cierra el pedido del jefe de obra: se arma el programa
    base del prototipo una vez y de ahí se replica a las casas que lo usan, en
    vez de repetir la instanciación individual una por una.

    **No es todo-o-nada, y esa es la decisión central.** Cada obra se resuelve
    en su propia unidad de trabajo —la que abre `InstanciarProgramaObra`— y su
    fallo se atrapa aquí: si la casa 17 de 40 trae un ciclo, o todavía no se ha
    generado desde su prototipo, las otras 39 quedan programadas igual y el
    resultado dice casa por casa qué pasó. Un lote que abortara entero por una
    obra mala sería inservible en obra: obligaría a depurar el dato de una casa
    antes de poder programar las demás, que es justo el trabajo manual que esto
    viene a quitar.

    La transacción **sí** es por obra, no del lote: `InstanciarProgramaObra`
    commitea lo suyo antes de volver, y el `UnidadDeTrabajoSQL` que comparten
    hace rollback de lo que quedara a medias si algo revienta dentro de su
    bloque. Así una obra fallida no deja media programación escrita ni arrastra
    a las que ya se confirmaron.

    Lo que sí aborta el lote entero son las precondiciones del **programa**, no
    de las obras: que el programa base exista (404) y que sea el vigente de su
    prototipo (422). Lo segundo no es un tecnicismo: `instanciar_programa`
    resuelve la plantilla por `items_base_vigente(prototipo_id)`, así que
    replicar una versión retirada bajaría en silencio la vigente y el usuario
    creería haber repartido otra cosa.
    """

    def __init__(
        self,
        *,
        instanciar: InstanciarProgramaObra,
        obras: RepositorioObras,
        programas: RepositorioProgramas,
    ) -> None:
        self._instanciar = instanciar
        self._obras = obras
        self._programas = programas

    async def ejecutar(self, cmd: ComandoReplicarPrograma) -> ReplicaDePrograma:
        base = await self._programas.obtener_base(cmd.programa_base_id)
        if base is None:
            raise ProgramaBaseNoEncontrado(
                f"Programa base {cmd.programa_base_id} no encontrado en tu alcance."
            )
        if not base["vigente"]:
            raise ErrorDeProgramacion(
                f"El programa base v{base['version']} ya no es el vigente de su "
                f"prototipo: replicarlo bajaría la versión vigente y no esta "
                f"(§7.5). Ábrelo en el editor y guárdalo para volverlo vigente "
                f"antes de replicar."
            )

        prototipo_id = UUID(str(base["prototipo_id"]))
        resultados = [
            await self._replicar_en(obra_id, prototipo_id, cmd.fecha_corte)
            for obra_id in _sin_repetir(cmd.obras)
        ]

        return ReplicaDePrograma(
            programa_base_id=cmd.programa_base_id,
            prototipo_id=prototipo_id,
            version_base=base["version"],
            obras=tuple(resultados),
        )

    async def _replicar_en(
        self, obra_id: UUID, prototipo_id: UUID, fecha_corte: date | None
    ) -> ReplicaEnObra:
        """Una obra del lote. **Nunca levanta** por culpa de la obra: todo lo
        que puede salir mal de una casa concreta sale como `motivo`."""
        obra = await self._obras.obtener(obra_id)
        if obra is None:
            # Mismo criterio que el 404 individual: RLS hace indistinguible
            # "no existe" de "no la puedes ver" (§12.4), y en un lote eso no se
            # puede relajar sin convertir la respuesta en un detector de obras
            # ajenas.
            return ReplicaEnObra(
                obra_id=obra_id,
                motivo="La obra no existe o está fuera de tu alcance.",
            )

        clave = obra["clave"]
        if not obra["prototipo_id"]:
            return ReplicaEnObra(
                obra_id=obra_id,
                clave=clave,
                motivo=(
                    "La obra no tiene prototipo asignado (§7.2), así que ningún "
                    "programa base le aplica."
                ),
            )
        if UUID(str(obra["prototipo_id"])) != prototipo_id:
            # Se rechaza en vez de dejarla pasar: `InstanciarProgramaObra`
            # resuelve la plantilla por el prototipo de la **obra**, así que
            # una obra de otro modelo se programaría con su propio programa
            # base y el reporte diría "replicada" sobre algo que no se replicó.
            return ReplicaEnObra(
                obra_id=obra_id,
                clave=clave,
                motivo=(
                    "La obra es de otro prototipo: este programa base no es su "
                    "plantilla (§7.5)."
                ),
            )

        try:
            instanciado = await self._instanciar.ejecutar(
                ComandoInstanciarPrograma(obra_id=obra_id, fecha_corte=fecha_corte)
            )
        except CicloEnGrafoError as exc:
            return ReplicaEnObra(
                obra_id=obra_id,
                clave=clave,
                motivo=(
                    f"El cronograma que resultaría tiene dependencias "
                    f"circulares, así que no se calculó ni se escribió nada en "
                    f"esta obra: {exc}"
                ),
            )
        except (ErrorDeProgramacion, ObraNoEncontrada) as exc:
            return ReplicaEnObra(obra_id=obra_id, clave=clave, motivo=str(exc))

        return ReplicaEnObra(
            obra_id=obra_id,
            clave=clave,
            programa_obra_id=instanciado.programa_obra_id,
            version=instanciado.version,
            n_actividades=instanciado.n_actividades,
            sin_item=instanciado.sin_item,
            refs_no_resueltas=instanciado.refs_no_resueltas,
        )


def _sin_repetir(obras: tuple[UUID, ...]) -> tuple[UUID, ...]:
    """Quita obras repetidas conservando el orden en que llegaron.

    Una obra dos veces en la lista se programaría dos veces y quedaría con dos
    versiones nuevas de cronograma por un solo clic (§7.5): eso no es lo que
    nadie quiso pedir, y el resultado traería dos renglones para la misma casa.
    """
    vistas: set[UUID] = set()
    unicas: list[UUID] = []
    for obra_id in obras:
        if obra_id in vistas:
            continue
        vistas.add(obra_id)
        unicas.append(obra_id)
    return tuple(unicas)


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
            inicio_dias=cmd.inicio_dias,
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


# --- Programación jerárquica sobre el árbol WBS (§7.4, §11.2) -----------


def _a_nodo_wbs(fila: dict) -> NodoWBS:
    return NodoWBS(
        id=str(fila["id"]),
        tipo=ClaseNodo(str(fila["tipo"])),
        nombre=fila["nombre"],
        parent_id=str(fila["parent_id"]) if fila.get("parent_id") else None,
    )


def _a_hoja(fila: dict, resultado: ResultadoCPM | None) -> HojaProgramable:
    """Una actividad como hoja del árbol (§7.6).

    Lo capturado y lo que derivó el motor viajan **en campos distintos**, y no
    uno rellenando al otro. Para dibujar la barra resumen son intercambiables
    —manda la captura y el CPM cubre el hueco, igual que fusiona el Gantt
    (`filas.ts`)— pero para el conflicto del §7.5 no lo son: el motor siempre da
    una fecha, así que colapsarlos haría que toda actividad de toda obra pasara
    por "programada a mano" y el aviso saliera en cada nodo desde el primer día.
    """
    return HojaProgramable(
        actividad_id=str(fila["id"]),
        prototipo_nodo_id=str(fila["prototipo_nodo_id"])
        if fila.get("prototipo_nodo_id")
        else None,
        importe=Decimal(str(fila.get("cant_base") or 0))
        * Decimal(str(fila.get("precio_unitario") or 0)),
        duracion_dias=Decimal(str(fila["duracion_dias"])),
        fecha_inicio=fila["fecha_inicio"],
        fecha_termino=fila["fecha_termino"],
        inicio_calculado=resultado.inicio_temprano if resultado else None,
        termino_calculado=resultado.fin_temprano if resultado else None,
        avance_pct=Decimal(str(fila["avance_pct"] or 0)),
    )


def _ventanas_de(items: Sequence[dict]) -> dict[str, Decimal]:
    """Los días que el programa base declara para nodos **gruesos** del árbol.

    Un `programa_base_item` cuyo `prototipo_nodo_id` apunta a un nodo `nivel` o
    `etapa` siempre fue representable —la columna referencia cualquier nodo del
    árbol (migración 0006)— y hasta ahora nadie lo resolvía: `item_aplicable`
    sólo lo cruza contra actividades, y ninguna actividad nace de un nodo que no
    sea `concepto` (§11.3 A.2). Aquí es donde esa captura gruesa cobra sentido:
    es la ventana contra la que se compara el resumen de sus hojas.

    Se devuelven todos los items con nodo, no sólo los gruesos: filtrar por tipo
    necesitaría el árbol, y un item sobre un nodo `concepto` simplemente coincide
    con la duración de su única hoja y nunca produce conflicto.
    """
    return {
        str(item["prototipo_nodo_id"]): Decimal(str(item["duracion_dias"]))
        for item in items
        if item.get("prototipo_nodo_id")
    }


@dataclass(frozen=True, slots=True)
class _ContextoDelArbol:
    """El estado que los dos casos de uso jerárquicos necesitan leer (§7.4)."""

    prototipo_id: UUID
    nodos: tuple[NodoWBS, ...]
    filas: tuple[dict, ...]
    hojas: tuple[HojaProgramable, ...]
    calendario: CalendarioLaboral
    arranque: date
    corte: date
    programa: dict | None


class _ConArbol(_ConCronograma):
    """Lo que comparten los dos casos de uso jerárquicos (§7.4).

    Los dos necesitan lo mismo: el árbol del prototipo de la obra, sus
    actividades como hojas con fechas resueltas por el motor, y el calendario
    del cronograma. Cargarlo una vez aquí evita que la lectura y la escritura
    difieran en qué consideran "la hoja" — que es exactamente cómo el resumen
    dejaría de reproducir lo que la captura repartió.
    """

    async def _contexto_del_arbol(
        self, obra_id: UUID, fecha_corte: date | None = None
    ) -> _ContextoDelArbol:
        obra = await self._obras.obtener(obra_id)
        if obra is None:
            raise ObraNoEncontrada(f"Obra {obra_id} no encontrada en tu alcance.")
        if not obra["prototipo_id"]:
            raise ErrorDeProgramacion(
                f"La obra {obra_id} no tiene prototipo (§7.2): su cronograma no "
                f"cuelga de ningún árbol WBS que resumir (§7.4)."
            )

        prototipo_id = UUID(str(obra["prototipo_id"]))
        programa = await self._programas.programa_vigente(obra_id)
        filas = await self._actividades.programacion_de_obra(obra_id)
        arranque = obra["fecha_inicio"] or date.today()
        corte = fecha_corte or (programa or {}).get("fecha_corte") or date.today()

        calendario = _calendario_de(programa)
        resultados = calcular_cpm(
            nodos_cpm([_a_actividad(f) for f in filas]),
            arranque,
            fecha_corte=corte,
            calendario=calendario,
        )
        return _ContextoDelArbol(
            prototipo_id=prototipo_id,
            nodos=tuple(
                _a_nodo_wbs(f)
                for f in await self._obras.arbol_prototipo(prototipo_id)
            ),
            filas=tuple(filas),
            hojas=tuple(_a_hoja(f, resultados.get(str(f["id"]))) for f in filas),
            calendario=calendario,
            arranque=arranque,
            corte=corte,
            programa=programa,
        )


class ConsultarArbolPrograma(_ConArbol):
    """`GET /obras/{id}/programa/arbol` — el Gantt jerárquico (§7.4, §11.2).

    Devuelve una barra por nodo con actividades debajo: los conceptos con la
    suya y los nodos `nivel`/`etapa` con su **barra resumen derivada** —inicio
    el más temprano de sus hojas, fin el más tardío, avance el ponderado por
    importe (§6)—.

    **No escribe nada, y no es por prudencia: es el diseño.** Si el resumen se
    persistiera sería un segundo lugar donde vive la misma cifra, y el primero
    en quedar viejo en cuanto alguien ajustara una actividad por el `PATCH` del
    §11.2. Calcularlo es una pasada sobre las actividades que ya se leyeron,
    igual de barata que `ConsultarRutaCritica`.

    Los conflictos padre-hijo salen aquí, en el mismo renglón del nodo que los
    tiene: es donde el usuario está mirando cuando tiene que decidir.
    """

    async def ejecutar(
        self, obra_id: UUID, *, fecha_corte: date | None = None
    ) -> ArbolDePrograma:
        ctx = await self._contexto_del_arbol(obra_id, fecha_corte)

        base = await self._programas.base_vigente(ctx.prototipo_id)
        items = await self._programas.items_base_vigente(ctx.prototipo_id)

        return ArbolDePrograma(
            obra_id=obra_id,
            prototipo_id=ctx.prototipo_id,
            # Sin programa base vigente, captura por concepto: es el default de
            # la columna (0041) y el comportamiento que el editor siempre tuvo.
            profundidad_captura=ClaseNodo(
                str(base["profundidad_captura"])
                if base and base.get("profundidad_captura")
                else ClaseNodo.CONCEPTO
            ),
            calendario=ctx.calendario,
            nodos=resumir_arbol(
                nodos=ctx.nodos,
                hojas=ctx.hojas,
                calendario=ctx.calendario,
                ventanas=_ventanas_de(items),
            ),
        )


class ProgramarNodoDelArbol(_ConArbol):
    """`POST /obras/{id}/programa/nodos/{prototipo_nodo_id}` (C, S — §11.2).

    La captura gruesa que pidió el jefe de obra: 20 días en la etapa
    `ESTRUCTURA PB` acomodan a sus ocho conceptos **uno tras otro** dentro de
    esa ventana, repartidos en proporción a su importe (§7.4,
    `domain.programacion.jerarquia`).

    **No crea una actividad de resumen.** El nodo `nivel`/`etapa` sigue siendo
    estructura: lo que se escribe son las duraciones y las fechas de las hojas
    que ya existen (§11.3 A.2). Una fila de resumen duplicaría cantidad, avance
    y costo sobre los de sus hijos y rompería el §6 y el §7.6.

    Un conflicto con lo que las hojas ya traían **aborta sin escribir** y sube
    como `ConflictoNoResuelto`; repetir con `forzar` es la decisión del usuario
    de conservar la cifra del padre.

    Igual que el resto de las operaciones que tocan el cronograma, el motor
    corre **antes** de abrir la unidad de trabajo: un ciclo deja la obra con su
    programación anterior intacta (§6).
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

    async def ejecutar(self, cmd: ComandoProgramarNodo) -> NodoProgramado:
        ctx = await self._contexto_del_arbol(cmd.obra_id)
        nodo_id = str(cmd.prototipo_nodo_id)

        if all(nodo.id != nodo_id for nodo in ctx.nodos):
            raise NodoNoProgramable(
                f"El nodo {nodo_id} no está en el árbol del prototipo de esta "
                f"obra (§7.4)."
            )

        del_nodo = hojas_por_nodo(ctx.nodos, ctx.hojas).get(nodo_id, ())
        if not del_nodo:
            raise NodoNoProgramable(
                f"El nodo {nodo_id} no tiene ningún concepto debajo en esta "
                f"obra: no hay actividades entre las cuales repartir la ventana "
                f"(§7.4)."
            )

        actividades = [_a_actividad(f) for f in ctx.filas]
        interrumpidas = frozenset(a.id for a in actividades if a.tramos)
        repartibles = tuple(
            h for h in del_nodo if h.actividad_id not in interrumpidas
        )
        if not repartibles:
            raise NodoNoProgramable(
                f"Todos los conceptos debajo del nodo {nodo_id} están "
                f"interrumpidos en tramos: una ventana gruesa no sabe cómo "
                f"volver a partirlos, así que no hay nada que repartir. "
                f"Prográmalos uno por uno (§7.6, §11.2 `PATCH`)."
            )

        _verificar_conflicto(
            nodos=ctx.nodos,
            nodo_id=nodo_id,
            hojas=del_nodo,
            ventana=cmd.duracion_dias,
            calendario=ctx.calendario,
            forzar=cmd.forzar,
        )

        # El ancla: lo que el cliente pidió, o donde el nodo ya está colocado, o
        # el arranque de la obra. Cambiarle la duración a una etapa no debería
        # moverla de lugar en el calendario si nadie lo pidió.
        inicios = [h.fecha_inicio for h in del_nodo if h.fecha_inicio is not None]
        ancla = cmd.fecha_inicio or (min(inicios) if inicios else ctx.arranque)

        colocaciones = repartir_secuencial(
            hojas=repartibles,
            ventana_dias=cmd.duracion_dias,
            inicio=ancla,
            calendario=ctx.calendario,
        )
        por_id = {c.actividad_id: c for c in colocaciones}

        # El grafo con las duraciones nuevas, antes de escribir: un ciclo aborta
        # aquí y la obra se queda con su programación anterior intacta (§6).
        propuesta = {
            actividad.id: ProgramacionDeActividad(
                actividad_id=actividad.id,
                duracion_dias=por_id[actividad.id].duracion_dias,
                dependencias=actividad.dependencias,
                frente_id=actividad.frente_id,
                fecha_inicio=por_id[actividad.id].fecha_inicio,
                fecha_termino=por_id[actividad.id].fecha_termino,
                tramos=actividad.tramos,
            )
            for actividad in actividades
            if actividad.id in por_id
        }
        resultados = calcular_cpm(
            nodos_cpm(actividades, propuesta),
            ctx.arranque,
            fecha_corte=ctx.corte,
            calendario=ctx.calendario,
        )

        async with self._uow:
            for colocacion in colocaciones:
                try:
                    await self._actividades.actualizar_programacion(
                        UUID(colocacion.actividad_id),
                        {
                            "duracion_dias": colocacion.duracion_dias,
                            "fecha_inicio": colocacion.fecha_inicio,
                            "fecha_termino": colocacion.fecha_termino,
                        },
                    )
                except RegistroNoEncontrado as exc:
                    raise ActividadNoProgramable(
                        f"La actividad {colocacion.actividad_id} ya no está en "
                        f"tu alcance: el reparto del nodo {nodo_id} no se "
                        f"aplicó."
                    ) from exc
            await self._actividades.guardar_resultado_cpm(
                cmd.obra_id, _a_guardable(resultados)
            )
            await self._uow.commit()

        filas_nuevas = await self._actividades.programacion_de_obra(cmd.obra_id)
        return NodoProgramado(
            obra_id=cmd.obra_id,
            prototipo_nodo_id=cmd.prototipo_nodo_id,
            duracion_dias=cmd.duracion_dias,
            fecha_inicio=colocaciones[0].fecha_inicio,
            fecha_termino=colocaciones[-1].fecha_termino,
            actividades=tuple(UUID(c.actividad_id) for c in colocaciones),
            omitidas=tuple(
                UUID(h.actividad_id)
                for h in del_nodo
                if h.actividad_id in interrumpidas
            ),
            ruta=_ensamblar_ruta(
                obra_id=cmd.obra_id,
                filas=filas_nuevas,
                resultados=resultados,
                fecha_inicio=ctx.arranque,
                fecha_corte=ctx.corte,
                programa=ctx.programa,
                calendario=ctx.calendario,
            ),
        )


def _verificar_conflicto(
    *,
    nodos: Sequence[NodoWBS],
    nodo_id: str,
    hojas: Sequence[HojaProgramable],
    ventana: Decimal,
    calendario: CalendarioLaboral,
    forzar: bool,
) -> None:
    """Aborta si la ventana choca con lo que las hojas ya traen y nadie decidió.

    Se reusa `resumir_arbol` en vez de recalcular el criterio aquí: si el
    conflicto que avisa la pantalla (`ConsultarArbolPrograma`) y el que frena la
    escritura se calcularan por separado, tarde o temprano uno avisaría de algo
    que el otro deja pasar.

    Raises:
        ConflictoNoResuelto: hay desacuerdo y `forzar` es falso.
    """
    if forzar:
        return

    resumen = next(
        (
            r
            for r in resumir_arbol(
                nodos=nodos,
                hojas=hojas,
                calendario=calendario,
                ventanas={nodo_id: ventana},
            )
            if r.nodo_id == nodo_id
        ),
        None,
    )
    if resumen is not None and resumen.conflicto is not None:
        raise ConflictoNoResuelto(resumen.conflicto)
