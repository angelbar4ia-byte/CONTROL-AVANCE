"""Motor de ruta crítica (CPM).

Spec §6 (ruta crítica) · §7.5 · §7.6 · §11.3 (recálculo por evento).

Calcula sobre el cronograma —actividades con inicio, duración y
dependencias— las fechas tempranas y tardías, la **holgura**, el **desfase**
y la **ruta crítica**. Recálculo programado y on-demand (§6).

Implementación clásica de dos pasadas sobre un DAG:
  * *forward pass*  → inicio/fin temprano (ES/EF)
  * *backward pass* → inicio/fin tardío (LS/LF)
  * ``holgura = LS − ES``; crítica ⇔ ``holgura ≤ 0``

**Trabajo vs. span.** Una actividad interrumpida (`Tramo`, §7.6) trabaja
menos días de los que ocupa en el calendario: el muro de tabique son 14 días
de trabajo repartidos en 19 de calendario porque en medio se cuela la losa.
El motor razona siempre sobre el **span** —lo que la barra ocupa de ES a EF—;
`duracion_dias` sigue siendo los días de trabajo, que es lo que miran costo,
recursos y destajo. Sin tramos las dos cifras coinciden y nada cambia.

**Días vs. fechas.** Todo lo que hay entre las dos pasadas es aritmética sobre
**índices de día**: la actividad arranca en el día 12 y ocupa 5. El calendario
—semana laboral o natural, `CalendarioLaboral`— entra en un solo punto, al
final, cuando esos índices se vuelven fechas. Por eso los cuatro tipos de
dependencia, los lags, los tramos y la holgura no cambian de fórmula al cambiar
de calendario: cambia a qué fecha corresponde el día 12, no cuál es el día 12.
Lo que sí cambia es qué **mide** un día: con semana natural son días corridos y
con semana laboral son días de trabajo, y eso vale para `duracion_dias`, el
`lag_dias` de cada dependencia, el `offset_dias` de cada tramo, la holgura y el
desfase por igual (ver `calendario.py`).

Módulo puro: recibe y devuelve dataclasses, no toca la BD (§12.11).
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from obractrl.domain.programacion.calendario import (
    SEMANA_NATURAL,
    CalendarioLaboral,
)

__all__ = [
    "CicloEnGrafoError",
    "Dependencia",
    "NodoCPM",
    "ResultadoCPM",
    "TipoDependencia",
    "Tramo",
    "calcular_cpm",
    "span_de",
    "trabajo_de",
]


class CicloEnGrafoError(ValueError):
    """El cronograma tiene una dependencia circular: no es planificable."""

    def __init__(self, involucradas: list[str]) -> None:
        super().__init__(
            "El cronograma tiene un ciclo de dependencias y no se puede "
            f"calcular: {', '.join(sorted(involucradas))}"
        )
        self.involucradas = involucradas


class TipoDependencia:
    """Tipos de precedencia soportados: los cuatro de MS Project."""

    FIN_INICIO = "FS"
    """Fin → Inicio. La sucesora arranca al terminar la predecesora."""

    INICIO_INICIO = "SS"
    """Inicio → Inicio. Arrancan juntas (con lag opcional)."""

    FIN_FIN = "FF"
    """Fin → Fin. La sucesora no puede terminar antes que la predecesora.

    Es la relación de los acabados que acompañan a la obra gruesa: la limpieza
    fina no termina antes que el último detalle, aunque haya empezado mucho
    antes."""

    INICIO_FIN = "SF"
    """Inicio → Fin. La sucesora no puede terminar antes de que arranque la
    predecesora. Es la más rara de las cuatro —lo típico es la actividad
    provisional (una bomba de achique) que solo se retira cuando arranca la
    definitiva."""


TIPOS_DEPENDENCIA = frozenset(
    {
        TipoDependencia.FIN_INICIO,
        TipoDependencia.INICIO_INICIO,
        TipoDependencia.FIN_FIN,
        TipoDependencia.INICIO_FIN,
    }
)
"""Los tipos que el motor sabe resolver. Un tipo fuera de este conjunto se
trata como `FS` (ver `calcular_cpm`), que es el default histórico del jsonb."""


@dataclass(frozen=True, slots=True)
class Tramo:
    """Un segmento de trabajo de una actividad interrumpida (§7.6).

    "El muro de tabique se hace las primeras dos semanas, para para levantar
    la losa, y después continúa con los pretiles": eso son dos tramos de la
    **misma** actividad, no dos actividades. El muro sigue siendo un concepto
    con una cantidad (317 m²) y un avance; partirlo en dos duplicaría el
    concepto y obligaría a repartir la cantidad a mano.

    `offset_dias` se mide desde el inicio de la actividad, no desde el tramo
    anterior: así un tramo se puede mover sin recalcular los que le siguen, y
    el hueco que el Gantt dibuja punteado sale de restar dos offsets.

    Las dos cifras son días **en la escala del calendario del cronograma**, no
    días corridos siempre: con semana laboral, un tramo de 10 días que arranca
    en `offset_dias = 0` un lunes cierra el viernes de la segunda semana, y una
    pausa de 5 días hábiles se dibuja sobre 7 casillas del calendario si le cae
    un domingo en medio. La aritmética de aquí —`fin_dias`, `span_de`,
    `trabajo_de`— no cambia: sigue siendo suma de índices, y quien sabe a qué
    fecha corresponde cada índice es `CalendarioLaboral` (`calendario.py`).
    """

    duracion_dias: float
    offset_dias: float = 0.0

    @property
    def fin_dias(self) -> float:
        """Día —relativo al inicio de la actividad— en que cierra el tramo."""
        return self.offset_dias + self.duracion_dias

    @classmethod
    def desde_jsonb(cls, dato: dict) -> Tramo:
        """Lee un tramo del jsonb de la BD (`actividad.tramos`)."""
        return cls(
            duracion_dias=float(dato["duracion_dias"]),
            offset_dias=float(dato.get("offset_dias", 0)),
        )

    def a_jsonb(self) -> dict[str, float]:
        return {
            "duracion_dias": self.duracion_dias,
            "offset_dias": self.offset_dias,
        }


def span_de(duracion_dias: float, tramos: Sequence[Tramo]) -> float:
    """Días que la actividad ocupa de su inicio a su fin, pausas incluidas.

    Sin tramos es la duración tal cual —el caso de siempre—. Con tramos es el
    cierre del **último**: lo que hay entre medio son pausas, y una sucesora
    `FS` tiene que esperar a que el trabajo acabe de verdad, no al primer
    tramo.

    Son días hábiles o días corridos según el calendario del cronograma; el
    span nunca se convierte a fechas aquí, así que la fórmula es la misma bajo
    los dos (`calendario.py`).
    """
    if not tramos:
        return duracion_dias
    return max(tramo.fin_dias for tramo in tramos)


def trabajo_de(duracion_dias: float, tramos: Sequence[Tramo]) -> float:
    """Días de trabajo efectivo: la suma de los tramos, sin las pausas.

    Es lo que consume recursos y lo que factura el destajo; el span no.
    """
    if not tramos:
        return duracion_dias
    return sum(tramo.duracion_dias for tramo in tramos)


@dataclass(frozen=True, slots=True)
class Dependencia:
    """Precedencia entre actividades. Se serializa a ``actividad.dependencias``."""

    ref: str
    tipo: str = TipoDependencia.FIN_INICIO
    lag_dias: float = 0.0

    @classmethod
    def desde_jsonb(cls, dato: dict | str) -> Dependencia:
        """Lee una dependencia del jsonb de la BD.

        Acepta la forma corta (solo la referencia) y la completa.
        """
        if isinstance(dato, str):
            return cls(ref=dato)
        return cls(
            ref=str(dato["ref"]),
            tipo=str(dato.get("tipo", TipoDependencia.FIN_INICIO)),
            lag_dias=float(dato.get("lag_dias", 0)),
        )


@dataclass(frozen=True, slots=True)
class NodoCPM:
    """Una actividad como la ve el motor.

    ``ref`` identifica el nodo dentro del cronograma (normalmente el id de la
    actividad). ``avance_pct`` y ``fecha_real_termino`` permiten medir el
    **desfase** contra lo programado.

    ``duracion_dias`` son los días de **trabajo**; con ``tramos`` la actividad
    ocupa más calendario que eso (ver ``span``).
    """

    ref: str
    duracion_dias: float
    dependencias: tuple[Dependencia, ...] = ()
    avance_pct: float = 0.0
    fecha_real_termino: date | None = None
    bloqueada: bool = False
    tramos: tuple[Tramo, ...] = ()
    inicio_dias: float | None = None
    """Ancla de arranque: el día en que la actividad empieza pase lo que pase
    con sus predecesoras. `None` = el arranque lo deriva el motor, que es el
    caso de siempre. Ver el forward pass de `calcular_cpm`."""

    @property
    def span(self) -> float:
        """Lo que la actividad ocupa de ES a EF. Sin tramos, la duración."""
        return span_de(self.duracion_dias, self.tramos)


@dataclass(slots=True)
class ResultadoCPM:
    """Cálculo de un nodo: fechas, holgura, desfase y criticidad."""

    ref: str
    inicio_temprano: date
    fin_temprano: date
    inicio_tardio: date
    fin_tardio: date
    holgura: float
    es_critica: bool
    desfase: float = 0.0

    @property
    def esta_atrasada(self) -> bool:
        return self.desfase > 0


@dataclass(slots=True)
class _Calculo:
    """Estado mutable interno de la pasada."""

    nodo: NodoCPM
    es: float = 0.0  # inicio temprano, en días desde el arranque
    ef: float = 0.0
    ls: float = 0.0
    lf: float = 0.0
    sucesoras: list[str] = field(default_factory=list)


def _orden_topologico(calcs: dict[str, _Calculo]) -> list[str]:
    """Kahn. Si sobran nodos al final, hay ciclo."""
    grado_entrada: dict[str, int] = {
        ref: len([d for d in c.nodo.dependencias if d.ref in calcs])
        for ref, c in calcs.items()
    }

    cola = deque(sorted(ref for ref, g in grado_entrada.items() if g == 0))
    orden: list[str] = []

    while cola:
        ref = cola.popleft()
        orden.append(ref)
        for suc in calcs[ref].sucesoras:
            grado_entrada[suc] -= 1
            if grado_entrada[suc] == 0:
                cola.append(suc)

    if len(orden) != len(calcs):
        raise CicloEnGrafoError([r for r in calcs if r not in set(orden)])

    return orden


def calcular_cpm(
    nodos: list[NodoCPM],
    fecha_inicio: date,
    *,
    fecha_corte: date | None = None,
    tolerancia_holgura: float = 0.0,
    calendario: CalendarioLaboral = SEMANA_NATURAL,
) -> dict[str, ResultadoCPM]:
    """Calcula la ruta crítica del cronograma.

    Args:
        nodos: actividades con duración y dependencias.
        fecha_inicio: arranque del cronograma (día 0).
        fecha_corte: fecha contra la que se mide el desfase. Por defecto hoy.
        tolerancia_holgura: holgura en días bajo la cual una actividad se
            considera crítica. ``0`` = solo las de holgura nula o negativa.
        calendario: qué días de la semana cuentan como trabajo (§7.5). Por
            defecto la **semana natural** —los siete—, que es el comportamiento
            histórico del motor: los días son días corridos y `fecha_inicio` es
            el día 0 tal cual. Con una semana laboral los días son días
            hábiles, el día 0 es el primer día que se trabaja en `fecha_inicio`
            o después, y los no laborables se saltan.

    Returns:
        Un ``ResultadoCPM`` por ``ref``.

    Raises:
        CicloEnGrafoError: si las dependencias forman un ciclo.

    Las dependencias que apuntan a un ``ref`` inexistente se ignoran: un
    cronograma parcial —una obra que aún no tiene todas sus actividades
    generadas— debe poder calcularse igual.
    """
    if not nodos:
        return {}

    calcs: dict[str, _Calculo] = {n.ref: _Calculo(nodo=n) for n in nodos}

    for ref, calc in calcs.items():
        for dep in calc.nodo.dependencias:
            if dep.ref in calcs:
                calcs[dep.ref].sucesoras.append(ref)

    orden = _orden_topologico(calcs)

    # --- Forward pass: inicio y fin tempranos ---------------------------
    #
    # Las cuatro relaciones son restricciones sobre el ES de la sucesora, con
    # `span` (no `duracion_dias`) como el largo de la barra:
    #   FS  ES_suc >= EF_pred + lag
    #   SS  ES_suc >= ES_pred + lag
    #   FF  EF_suc >= EF_pred + lag  ->  ES_suc >= EF_pred + lag - span_suc
    #   SF  EF_suc >= ES_pred + lag  ->  ES_suc >= ES_pred + lag - span_suc
    for ref in orden:
        calc = calcs[ref]
        span = calc.nodo.span
        # Arrancar en 0 clampea el resultado al inicio del proyecto. Con FF/SF
        # el candidato puede salir negativo (una sucesora larga que solo debe
        # *terminar* después de su predecesora corta querría empezar antes del
        # día 0); el clamp no rompe la relación porque las cuatro son
        # desigualdades `>=`: retrasar la sucesora las sigue cumpliendo, solo
        # deja de ser el caso apretado.
        es = 0.0
        for dep in calc.nodo.dependencias:
            pred = calcs.get(dep.ref)
            if pred is None:
                continue
            if dep.tipo == TipoDependencia.INICIO_INICIO:
                candidato = pred.es + dep.lag_dias
            elif dep.tipo == TipoDependencia.FIN_FIN:
                candidato = pred.ef + dep.lag_dias - span
            elif dep.tipo == TipoDependencia.INICIO_FIN:
                candidato = pred.es + dep.lag_dias - span
            else:  # FIN_INICIO, y cualquier tipo desconocido del jsonb
                candidato = pred.ef + dep.lag_dias
            es = max(es, candidato)

        # El ancla gana sobre todo lo anterior. Es el "Debe comenzar el" de MS
        # Project, no el "No comenzar antes del": si fuera un piso —`max(es,
        # ancla)`— una predecesora que se alargara arrastraría la actividad,
        # que es justo lo que el ancla existe para impedir ("el inicio manda
        # sobre la predecesora"). La relación queda entonces sin cumplirse y
        # eso se ve en el lag negativo que la pantalla muestra; soltarla es
        # cosa de quien edita, no del motor.
        if calc.nodo.inicio_dias is not None:
            es = max(0.0, calc.nodo.inicio_dias)

        calc.es = es
        calc.ef = es + span

    duracion_proyecto = max(c.ef for c in calcs.values())

    # --- Backward pass: inicio y fin tardíos ----------------------------
    #
    # Las mismas cuatro, ahora despejadas contra el LF de la predecesora:
    #   FS  LF_pred <= LS_suc - lag
    #   SS  LS_pred <= LS_suc - lag  ->  LF_pred <= LS_suc - lag + span_pred
    #   FF  LF_pred <= LF_suc - lag
    #   SF  LS_pred <= LF_suc - lag  ->  LF_pred <= LF_suc - lag + span_pred
    for ref in reversed(orden):
        calc = calcs[ref]
        span = calc.nodo.span
        # El fin del proyecto acota a TODOS los nodos, no solo a los
        # terminales. Con FS/SS la cota nunca manda —la sucesora siempre da un
        # LF menor—, pero con un lag negativo sí: un `FF` de −2 días deja que
        # la predecesora termine dos días DESPUÉS que su sucesora, y sin esta
        # cota una actividad que marca el fin del proyecto salía con holgura
        # positiva y dejaba de ser crítica.
        lf = duracion_proyecto
        for suc_ref in calc.sucesoras:
            suc = calcs[suc_ref]
            # Todas las aristas hacia esta predecesora, no solo la primera:
            # una sucesora puede declarar dos relaciones sobre la misma
            # predecesora (el par SS+FF con el que se amarra una actividad que
            # acompaña a otra de punta a punta). El forward pass ya las
            # considera todas, y quedarse con una sola aquí dejaría un LS que
            # no corresponde al ES calculado —holgura negativa inventada.
            for dep in suc.nodo.dependencias:
                if dep.ref != ref:
                    continue
                if dep.tipo == TipoDependencia.INICIO_INICIO:
                    candidato = suc.ls - dep.lag_dias + span
                elif dep.tipo == TipoDependencia.FIN_FIN:
                    candidato = suc.lf - dep.lag_dias
                elif dep.tipo == TipoDependencia.INICIO_FIN:
                    candidato = suc.lf - dep.lag_dias + span
                else:  # FIN_INICIO
                    candidato = suc.ls - dep.lag_dias
                lf = min(lf, candidato)
        calc.lf = lf
        calc.ls = calc.lf - span

    # --- Ensamble: fechas reales, holgura, desfase ----------------------
    #
    # El único punto donde el calendario entra. Hasta aquí todo fueron índices
    # de día; `fecha_de` los ancla al arranque del cronograma y salta los días
    # que no se trabajan. Con `SEMANA_NATURAL` es literalmente la suma de
    # `timedelta` que este bloque hacía antes (`calendario.conversor`).
    corte = fecha_corte or date.today()
    fecha_de = calendario.conversor(fecha_inicio)
    resultados: dict[str, ResultadoCPM] = {}

    for ref, calc in calcs.items():
        holgura = round(calc.ls - calc.es, 4)
        fin_temprano = fecha_de(calc.ef)

        resultados[ref] = ResultadoCPM(
            ref=ref,
            inicio_temprano=fecha_de(calc.es),
            fin_temprano=fin_temprano,
            inicio_tardio=fecha_de(calc.ls),
            fin_tardio=fecha_de(calc.lf),
            holgura=holgura,
            es_critica=holgura <= tolerancia_holgura,
            desfase=_calcular_desfase(calc.nodo, fin_temprano, corte, calendario),
        )

    return resultados


def _calcular_desfase(
    nodo: NodoCPM,
    fin_programado: date,
    corte: date,
    calendario: CalendarioLaboral,
) -> float:
    """Días de atraso de una actividad contra su fin programado.

    Una actividad concluida se mide contra su fecha real de término; una en
    curso, contra la fecha de corte. Sin atraso el desfase es ``0``: no se
    reportan adelantos como desfase negativo porque el consumidor —la alerta
    de actividad crítica atrasada (§6)— solo mira atrasos.

    El atraso se cuenta en la misma escala que la holgura: con semana laboral
    son días de **trabajo** perdidos, no casillas del calendario. Si no, un
    atraso de dos días que cae sobre un domingo se reportaría como tres y la
    comparación "el atraso ya se comió la holgura" (§6) dispararía de más cada
    fin de semana. Con semana natural `dias_entre` es la resta de fechas de
    siempre.
    """
    if nodo.avance_pct >= 100:
        if nodo.fecha_real_termino is None:
            return 0.0
        return max(
            0.0, float(calendario.dias_entre(fin_programado, nodo.fecha_real_termino))
        )

    if corte > fin_programado:
        return float(calendario.dias_entre(fin_programado, corte))

    return 0.0


def actividades_bloqueadas_por(
    nodos: list[NodoCPM], refs_detenidas: set[str]
) -> set[str]:
    """Propaga el bloqueo de una incidencia ``detiene`` (§6, §11.3 F).

    Una incidencia que frena la obra bloquea sus actividades y, en cascada,
    todo lo que dependa de ellas.
    """
    sucesoras: dict[str, list[str]] = defaultdict(list)
    for nodo in nodos:
        for dep in nodo.dependencias:
            sucesoras[dep.ref].append(nodo.ref)

    bloqueadas: set[str] = set()
    cola = deque(refs_detenidas)

    while cola:
        ref = cola.popleft()
        for suc in sucesoras.get(ref, []):
            if suc not in bloqueadas:
                bloqueadas.add(suc)
                cola.append(suc)

    return bloqueadas
