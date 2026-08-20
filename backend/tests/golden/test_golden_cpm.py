"""Dataset golden del motor CPM (§11.7, §7.5).

Un cronograma realista —doce actividades de una vivienda, con las cuatro formas
de dependencia que el motor soporta— congelado con sus fechas, holguras y ruta
crítica.

## Por qué este cronograma y no uno de tres nodos

Tres nodos en cadena no ejercitan nada: cualquier implementación los ordena
bien. Lo que rompe un CPM son los caminos que convergen —dos predecesoras con
duraciones distintas—, las dependencias `SS` con lag, y las ramas que no están
en la ruta crítica pero se acercan. Este cronograma tiene las tres.
"""

from __future__ import annotations

from datetime import date

from obractrl.domain.programacion.cpm import (
    Dependencia,
    NodoCPM,
    TipoDependencia,
    calcular_cpm,
)

INICIO = date(2026, 3, 2)
CORTE = date(2026, 3, 30)


def _cronograma() -> list[NodoCPM]:
    """Una vivienda: de trazo a limpieza.

    Las duraciones no son redondas a propósito: con todo en múltiplos de cinco,
    un error de un día en la aritmética de fechas puede quedar escondido detrás
    de un fin de semana.
    """
    fs = TipoDependencia.FIN_INICIO
    ss = TipoDependencia.INICIO_INICIO

    return [
        NodoCPM(ref="TRAZO", duracion_dias=2, avance_pct=100.0),
        NodoCPM(
            ref="EXCAV",
            duracion_dias=3,
            dependencias=(Dependencia(ref="TRAZO", tipo=fs),),
            avance_pct=100.0,
        ),
        NodoCPM(
            ref="CIMENT",
            duracion_dias=6,
            dependencias=(Dependencia(ref="EXCAV", tipo=fs),),
            avance_pct=80.0,
        ),
        # Rama corta que converge con CIMENT: existe para que haya holgura real
        # que medir.
        NodoCPM(
            ref="INST_HIDRO",
            duracion_dias=2,
            dependencias=(Dependencia(ref="EXCAV", tipo=fs),),
            avance_pct=50.0,
        ),
        NodoCPM(
            ref="MUROS",
            duracion_dias=7,
            dependencias=(
                Dependencia(ref="CIMENT", tipo=fs),
                Dependencia(ref="INST_HIDRO", tipo=fs),
            ),
        ),
        # `SS` con lag: arranca con MUROS pero tres días después.
        NodoCPM(
            ref="INST_ELEC",
            duracion_dias=4,
            dependencias=(Dependencia(ref="MUROS", tipo=ss, lag_dias=3),),
        ),
        NodoCPM(
            ref="LOSA",
            duracion_dias=5,
            dependencias=(Dependencia(ref="MUROS", tipo=fs),),
        ),
        NodoCPM(
            ref="ACABADOS",
            duracion_dias=9,
            dependencias=(
                Dependencia(ref="LOSA", tipo=fs),
                Dependencia(ref="INST_ELEC", tipo=fs),
            ),
        ),
        NodoCPM(
            ref="PINTURA",
            duracion_dias=4,
            dependencias=(Dependencia(ref="ACABADOS", tipo=fs),),
        ),
        # Una rama que puede empezar temprano y termina holgada.
        NodoCPM(
            ref="JARDIN",
            duracion_dias=2,
            dependencias=(Dependencia(ref="CIMENT", tipo=fs),),
        ),
        NodoCPM(
            ref="LIMPIEZA",
            duracion_dias=1,
            dependencias=(
                Dependencia(ref="PINTURA", tipo=fs),
                Dependencia(ref="JARDIN", tipo=fs),
            ),
        ),
        # Sin dependencias y sin sucesoras: el caso que a veces se rompe.
        NodoCPM(ref="TRAMITES", duracion_dias=3),
    ]


def _serializar(resultados: dict) -> dict:
    return {
        ref: {
            "inicio_temprano": r.inicio_temprano.isoformat(),
            "fin_temprano": r.fin_temprano.isoformat(),
            "inicio_tardio": r.inicio_tardio.isoformat(),
            "fin_tardio": r.fin_tardio.isoformat(),
            "holgura": r.holgura,
            "es_critica": r.es_critica,
            "desfase": r.desfase,
        }
        for ref, r in sorted(resultados.items())
    }


def test_golden_cronograma_de_vivienda(golden) -> None:
    """Las fechas, holguras y criticidad de un cronograma completo."""
    resultados = calcular_cpm(_cronograma(), INICIO, fecha_corte=CORTE)
    golden("cpm_vivienda", _serializar(resultados))


def test_golden_con_tolerancia_de_holgura(golden) -> None:
    """La misma red con `tolerancia_holgura=2`.

    Se congela aparte porque cambia **qué es crítico**, que es la salida que más
    consecuencias tiene: la Torre la muestra, el Gantt la pinta y el cierre de
    obra la cuenta. Un cambio accidental en el criterio de criticidad se vería
    aquí como un puñado de `es_critica` que pasan de `false` a `true`.
    """
    resultados = calcular_cpm(
        _cronograma(), INICIO, fecha_corte=CORTE, tolerancia_holgura=2.0
    )
    golden("cpm_vivienda_tolerancia_2", _serializar(resultados))


def test_el_golden_no_depende_del_orden_de_entrada(golden) -> None:
    """El mismo cronograma con los nodos al revés da el mismo resultado.

    No es una obviedad: un CPM que dependiera del orden de la lista en vez de
    del orden topológico daría fechas distintas según cómo venga la consulta —y
    `programacion_de_obra` no promete ningún orden en particular.
    """
    al_reves = list(reversed(_cronograma()))
    resultados = calcular_cpm(al_reves, INICIO, fecha_corte=CORTE)
    golden("cpm_vivienda", _serializar(resultados))
