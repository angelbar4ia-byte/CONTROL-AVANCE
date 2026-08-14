"""Motor de ruta crítica (CPM).

Spec §6 (ruta crítica) · §7.5 · §7.6 · §11.3 (recálculo por evento).

Calcula sobre el cronograma —actividades con inicio, duración y
dependencias— las fechas tempranas y tardías, la **holgura**, el **desfase**
y la **ruta crítica**. Recálculo programado y on-demand (§6).

Implementación clásica de dos pasadas sobre un DAG:
  * *forward pass*  → inicio/fin temprano (ES/EF)
  * *backward pass* → inicio/fin tardío (LS/LF)
  * ``holgura = LS − ES``; crítica ⇔ ``holgura ≤ 0``

Módulo puro: recibe y devuelve dataclasses, no toca la BD (§12.11).
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date, timedelta

__all__ = [
    "CicloEnGrafoError",
    "Dependencia",
    "NodoCPM",
    "ResultadoCPM",
    "TipoDependencia",
    "calcular_cpm",
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
    """Tipos de precedencia soportados."""

    FIN_INICIO = "FS"
    """Fin → Inicio. La sucesora arranca al terminar la predecesora."""

    INICIO_INICIO = "SS"
    """Inicio → Inicio. Arrancan juntas (con lag opcional)."""


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
    """

    ref: str
    duracion_dias: float
    dependencias: tuple[Dependencia, ...] = ()
    avance_pct: float = 0.0
    fecha_real_termino: date | None = None
    bloqueada: bool = False


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
) -> dict[str, ResultadoCPM]:
    """Calcula la ruta crítica del cronograma.

    Args:
        nodos: actividades con duración y dependencias.
        fecha_inicio: arranque del cronograma (día 0).
        fecha_corte: fecha contra la que se mide el desfase. Por defecto hoy.
        tolerancia_holgura: holgura en días bajo la cual una actividad se
            considera crítica. ``0`` = solo las de holgura nula o negativa.

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
    for ref in orden:
        calc = calcs[ref]
        es = 0.0
        for dep in calc.nodo.dependencias:
            pred = calcs.get(dep.ref)
            if pred is None:
                continue
            if dep.tipo == TipoDependencia.INICIO_INICIO:
                candidato = pred.es + dep.lag_dias
            else:  # FIN_INICIO
                candidato = pred.ef + dep.lag_dias
            es = max(es, candidato)
        calc.es = es
        calc.ef = es + calc.nodo.duracion_dias

    duracion_proyecto = max(c.ef for c in calcs.values())

    # --- Backward pass: inicio y fin tardíos ----------------------------
    for ref in reversed(orden):
        calc = calcs[ref]
        if not calc.sucesoras:
            calc.lf = duracion_proyecto
        else:
            lf = float("inf")
            for suc_ref in calc.sucesoras:
                suc = calcs[suc_ref]
                dep = next(
                    d for d in suc.nodo.dependencias if d.ref == ref
                )
                if dep.tipo == TipoDependencia.INICIO_INICIO:
                    candidato = suc.ls - dep.lag_dias + calc.nodo.duracion_dias
                else:  # FIN_INICIO
                    candidato = suc.ls - dep.lag_dias
                lf = min(lf, candidato)
            calc.lf = lf
        calc.ls = calc.lf - calc.nodo.duracion_dias

    # --- Ensamble: fechas reales, holgura, desfase ----------------------
    corte = fecha_corte or date.today()
    resultados: dict[str, ResultadoCPM] = {}

    for ref, calc in calcs.items():
        holgura = round(calc.ls - calc.es, 4)
        fin_temprano = fecha_inicio + timedelta(days=calc.ef)

        resultados[ref] = ResultadoCPM(
            ref=ref,
            inicio_temprano=fecha_inicio + timedelta(days=calc.es),
            fin_temprano=fin_temprano,
            inicio_tardio=fecha_inicio + timedelta(days=calc.ls),
            fin_tardio=fecha_inicio + timedelta(days=calc.lf),
            holgura=holgura,
            es_critica=holgura <= tolerancia_holgura,
            desfase=_calcular_desfase(calc.nodo, fin_temprano, corte),
        )

    return resultados


def _calcular_desfase(nodo: NodoCPM, fin_programado: date, corte: date) -> float:
    """Días de atraso de una actividad contra su fin programado.

    Una actividad concluida se mide contra su fecha real de término; una en
    curso, contra la fecha de corte. Sin atraso el desfase es ``0``: no se
    reportan adelantos como desfase negativo porque el consumidor —la alerta
    de actividad crítica atrasada (§6)— solo mira atrasos.
    """
    if nodo.avance_pct >= 100:
        if nodo.fecha_real_termino is None:
            return 0.0
        return max(0.0, (nodo.fecha_real_termino - fin_programado).days)

    if corte > fin_programado:
        return float((corte - fin_programado).days)

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
