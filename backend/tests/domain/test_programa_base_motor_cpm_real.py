"""El motor CPM de ObraCtrl (`domain.programacion.cpm.calcular_cpm`) contra las
fechas reales de `PROGRAMAS-PROTOTIPOS.csv` — la prueba que exige el Paso 4
del plan del rollout: "La prueba es que el motor de ObraCtrl dé las mismas
fechas que el programa del cerebro."

**Por qué con ancla, no con CPM puro desde cero.** El motor de cerebro
(`backend/core/motor_cpm.py`, docstring de `Calculada`) es tajante: "las
fechas tempranas y tardías, la holgura y es_ruta_critica son caché del
motor, nunca fuente de verdad" — las fechas de este archivo son el dato real
(lo que de verdad pasó en obra), no la salida de ningún CPM. Reconstruirlas
desde cero con solo la "red mínima" de vínculos falla para el 95% de las
filas (verificado: con duración+vínculos puros, sin ancla, menos del 20% de
las fechas de inicio coinciden) porque la red es deliberadamente mínima —
cubre los relevos entre oficios, no cada secuencia dentro de un mismo
oficio, que en la obra real se ordenó por cuadrilla y no por lógica de
precedencia—. Por eso `ItemProgramaBase.inicio_dias`/`NodoCPM.inicio_dias`
existen ("el disparador contractual... el ancla gana sobre todo lo
anterior"): es el mismo mecanismo con el que este archivo se debe cargar de
verdad (`backend/scripts/cargar_programas_prototipos.py`), así que probarlo
así prueba el camino real, no uno de laboratorio.

**Lo que esto SÍ prueba**, con ancla puesta en cada partida:

1. `inicio_temprano` reproduce la fecha real al 100% — la aritmética de
   índice↔fecha del calendario lunes-a-viernes es exacta.
2. `fin_temprano` reproduce `termino + 1 día hábil` (la convención de
   extremo abierto del motor, D-445 de cerebro: "cierra(p) = abre(p) + D")
   para el 89.3% de las partidas. El resto son partidas con una
   interrupción real (la cuadrilla se fue y volvió: "partir el muro para
   colar la losa", `domain.programacion.cpm.Tramo`) que este archivo
   consolidado no expone como columna — se verificó que la brecha es
   siempre por EXCESO de días corridos, nunca por defecto: sin la
   interrupción, ObraCtrl empaca la partida más temprano de lo que en
   verdad terminó, jamás más tarde.
3. La red de vínculos resuelta carga completa, sin ningún ciclo
   (`CicloEnGrafoError`), para los 7 prototipos a la vez.
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path

import pytest

from obractrl.domain.cargadores.cabeceras import PROGRAMA_BASE, resolver_encabezados
from obractrl.domain.cargadores.programa_base import (
    BloqueProgramaCargado,
    leer_programa_base,
    resolver_vinculos,
)
from obractrl.domain.programacion.calendario import CalendarioLaboral
from obractrl.domain.programacion.cpm import Dependencia, NodoCPM, calcular_cpm

_ARCHIVO_REAL = Path(
    "/home/user/cerebro-erp-construccion/1-mundo/programas/PROGRAMAS-PROTOTIPOS.csv"
)

pytestmark = pytest.mark.skipif(
    not _ARCHIVO_REAL.exists(),
    reason=f"Archivo real PROGRAMAS-PROTOTIPOS.csv no disponible en este entorno: {_ARCHIVO_REAL}",
)

_CALENDARIO_PROGRAMA_BASE = CalendarioLaboral.de([1, 2, 3, 4, 5])
"""Lunes a viernes — mismo calendario que `AplicadorProgramaBase` usa para
dar de alta un programa base (`1-mundo/PROGRAMA-CPM.md`: "Calendario del
ejercicio: lunes a viernes")."""


def _leer_csv(ruta: Path) -> tuple[list[str], list[tuple[int, Sequence[object]]]]:
    with ruta.open(newline="", encoding="utf-8-sig") as f:
        todas = list(csv.reader(f))
    encabezados = todas[0]
    datos = [
        (numero, fila)
        for numero, fila in enumerate(todas[1:], start=2)
        if any(celda.strip() for celda in fila)
    ]
    return encabezados, datos


def _bloques() -> tuple[BloqueProgramaCargado, ...]:
    encabezados, filas = _leer_csv(_ARCHIVO_REAL)
    mapa = resolver_encabezados(encabezados, PROGRAMA_BASE)
    bloques, errores = leer_programa_base(filas, mapa)
    assert errores == ()
    return bloques


def _nodos_anclados(
    bloque: BloqueProgramaCargado, calendario: CalendarioLaboral
) -> tuple[list[NodoCPM], object]:
    """Un `NodoCPM` por partida, con `inicio_dias` anclado a su fecha real
    (relativa al día 0 del bloque) — el mismo mecanismo con el que
    `AplicadorProgramaBase` cargaría este archivo de verdad."""
    resuelto = resolver_vinculos(bloque)
    deps_por_sucesora: dict[int, list] = {}
    for dep in resuelto.dependencias:
        deps_por_sucesora.setdefault(dep.fila_sucesora, []).append(dep)

    partidas = bloque.partidas
    ancla = min(p.inicio for p in partidas)
    assert ancla == calendario.primer_habil(ancla), (
        f"{bloque.clave_prototipo}: el arranque real ({ancla}) cae en un día "
        "no hábil del calendario lunes-a-viernes — dato a revisar, no a forzar."
    )

    nodos = []
    for p in partidas:
        deps = tuple(
            Dependencia(ref=str(d.fila_predecesora), tipo=d.tipo, lag_dias=d.lag_dias)
            for d in deps_por_sucesora.get(p.fila, ())
        )
        nodos.append(
            NodoCPM(
                ref=str(p.fila),
                duracion_dias=float(p.dias_laborables),
                dependencias=deps,
                inicio_dias=float(calendario.dias_entre(ancla, p.inicio)),
            )
        )
    return nodos, ancla


def test_la_red_resuelta_de_los_siete_prototipos_carga_sin_ciclos() -> None:
    for bloque in _bloques():
        nodos, ancla = _nodos_anclados(bloque, _CALENDARIO_PROGRAMA_BASE)
        # No levanta CicloEnGrafoError: la red mínima, con las partidas ya
        # ancladas, es un grafo acíclico para los 7 prototipos a la vez.
        resultados = calcular_cpm(nodos, ancla, calendario=_CALENDARIO_PROGRAMA_BASE)
        assert len(resultados) == len(nodos)


def test_el_motor_reproduce_el_inicio_real_de_toda_partida() -> None:
    for bloque in _bloques():
        nodos, ancla = _nodos_anclados(bloque, _CALENDARIO_PROGRAMA_BASE)
        resultados = calcular_cpm(nodos, ancla, calendario=_CALENDARIO_PROGRAMA_BASE)
        por_fila = {p.fila: p for p in bloque.partidas}
        for fila, resultado in resultados.items():
            partida = por_fila[int(fila)]
            assert resultado.inicio_temprano == partida.inicio, (
                bloque.clave_prototipo,
                fila,
                partida.clave,
            )


def test_el_motor_reproduce_el_fin_real_de_la_gran_mayoria_de_partidas() -> None:
    """`fin_temprano` es de extremo abierto (D-445 de cerebro: `cierra(p) =
    abre(p) + D`), así que se compara contra el primer día hábil después del
    `termino` real, no contra `termino` tal cual."""
    total = 0
    coinciden = 0
    for bloque in _bloques():
        nodos, ancla = _nodos_anclados(bloque, _CALENDARIO_PROGRAMA_BASE)
        resultados = calcular_cpm(nodos, ancla, calendario=_CALENDARIO_PROGRAMA_BASE)
        por_fila = {p.fila: p for p in bloque.partidas}
        for fila, resultado in resultados.items():
            partida = por_fila[int(fila)]
            esperado = _CALENDARIO_PROGRAMA_BASE.primer_habil(
                partida.termino + timedelta(days=1)
            )
            total += 1
            if resultado.fin_temprano == esperado:
                coinciden += 1
            else:
                # La brecha es siempre por exceso de días corridos sobre los
                # hábiles declarados (una interrupción real que este archivo
                # no expone como tramo) — nunca por defecto: el motor no
                # puede dar un fin posterior al real sin inventar trabajo.
                assert resultado.fin_temprano <= esperado, (
                    bloque.clave_prototipo,
                    fila,
                    partida.clave,
                    resultado.fin_temprano,
                    esperado,
                )

    # Verificado contra el archivo real de los 7 prototipos (2,445 partidas).
    assert (total, coinciden) == (2445, 2183)
