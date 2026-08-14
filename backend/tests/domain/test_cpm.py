"""Motor de ruta crítica (§6, §7.5)."""

from __future__ import annotations

from datetime import date

import pytest

from obractrl.domain.programacion.cpm import (
    CicloEnGrafoError,
    Dependencia,
    NodoCPM,
    TipoDependencia,
    actividades_bloqueadas_por,
    calcular_cpm,
)

INICIO = date(2026, 3, 2)  # lunes


def _cadena() -> list[NodoCPM]:
    """A(5) -> B(3) -> C(2): todo es crítico, no hay holgura."""
    return [
        NodoCPM(ref="A", duracion_dias=5),
        NodoCPM(ref="B", duracion_dias=3, dependencias=(Dependencia("A"),)),
        NodoCPM(ref="C", duracion_dias=2, dependencias=(Dependencia("B"),)),
    ]


def _con_rama_holgada() -> list[NodoCPM]:
    """A(5) -> {B(6), D(2)} -> C. La rama D tiene 4 días de holgura."""
    return [
        NodoCPM(ref="A", duracion_dias=5),
        NodoCPM(ref="B", duracion_dias=6, dependencias=(Dependencia("A"),)),
        NodoCPM(ref="D", duracion_dias=2, dependencias=(Dependencia("A"),)),
        NodoCPM(
            ref="C",
            duracion_dias=2,
            dependencias=(Dependencia("B"), Dependencia("D")),
        ),
    ]


class TestCadenaSimple:
    def test_fechas_tempranas(self) -> None:
        r = calcular_cpm(_cadena(), INICIO, fecha_corte=INICIO)
        assert r["A"].inicio_temprano == INICIO
        assert r["A"].fin_temprano == date(2026, 3, 7)   # +5
        assert r["B"].inicio_temprano == date(2026, 3, 7)
        assert r["C"].fin_temprano == date(2026, 3, 12)  # 5+3+2

    def test_todo_es_critico_sin_ramas(self) -> None:
        r = calcular_cpm(_cadena(), INICIO, fecha_corte=INICIO)
        assert all(n.es_critica for n in r.values())
        assert all(n.holgura == 0 for n in r.values())


class TestHolgura:
    def test_la_rama_corta_tiene_holgura(self) -> None:
        r = calcular_cpm(_con_rama_holgada(), INICIO, fecha_corte=INICIO)
        assert r["D"].holgura == 4
        assert not r["D"].es_critica

    def test_la_rama_larga_es_la_ruta_critica(self) -> None:
        r = calcular_cpm(_con_rama_holgada(), INICIO, fecha_corte=INICIO)
        criticas = {ref for ref, n in r.items() if n.es_critica}
        assert criticas == {"A", "B", "C"}


class TestDependencias:
    def test_lag_empuja_la_sucesora(self) -> None:
        nodos = [
            NodoCPM(ref="A", duracion_dias=5),
            NodoCPM(
                ref="B",
                duracion_dias=3,
                dependencias=(Dependencia("A", lag_dias=2),),
            ),
        ]
        r = calcular_cpm(nodos, INICIO, fecha_corte=INICIO)
        assert r["B"].inicio_temprano == date(2026, 3, 9)  # 5 + 2 de lag

    def test_inicio_inicio_arranca_junto(self) -> None:
        nodos = [
            NodoCPM(ref="A", duracion_dias=5),
            NodoCPM(
                ref="B",
                duracion_dias=3,
                dependencias=(
                    Dependencia("A", tipo=TipoDependencia.INICIO_INICIO),
                ),
            ),
        ]
        r = calcular_cpm(nodos, INICIO, fecha_corte=INICIO)
        assert r["B"].inicio_temprano == INICIO

    def test_ignora_dependencias_a_refs_inexistentes(self) -> None:
        """Un cronograma parcial debe poder calcularse igual."""
        nodos = [NodoCPM(ref="A", duracion_dias=5, dependencias=(Dependencia("FANTASMA"),))]
        r = calcular_cpm(nodos, INICIO, fecha_corte=INICIO)
        assert r["A"].inicio_temprano == INICIO

    def test_ciclo_es_error_explicito(self) -> None:
        nodos = [
            NodoCPM(ref="A", duracion_dias=1, dependencias=(Dependencia("B"),)),
            NodoCPM(ref="B", duracion_dias=1, dependencias=(Dependencia("A"),)),
        ]
        with pytest.raises(CicloEnGrafoError) as exc:
            calcular_cpm(nodos, INICIO)
        assert set(exc.value.involucradas) == {"A", "B"}


class TestDesfase:
    def test_actividad_en_curso_pasada_de_fecha(self) -> None:
        r = calcular_cpm(_cadena(), INICIO, fecha_corte=date(2026, 3, 10))
        assert r["A"].desfase == 3   # debía terminar el 7, hoy es 10
        assert r["A"].esta_atrasada

    def test_sin_atraso_el_desfase_es_cero(self) -> None:
        r = calcular_cpm(_cadena(), INICIO, fecha_corte=date(2026, 3, 5))
        assert r["A"].desfase == 0

    def test_concluida_se_mide_contra_su_fecha_real(self) -> None:
        nodos = [
            NodoCPM(
                ref="A",
                duracion_dias=5,
                avance_pct=100,
                fecha_real_termino=date(2026, 3, 9),
            )
        ]
        r = calcular_cpm(nodos, INICIO, fecha_corte=date(2026, 4, 1))
        assert r["A"].desfase == 2   # terminó el 9, debía el 7

    def test_concluida_a_tiempo_no_arrastra_el_corte(self) -> None:
        nodos = [
            NodoCPM(
                ref="A",
                duracion_dias=5,
                avance_pct=100,
                fecha_real_termino=date(2026, 3, 6),
            )
        ]
        r = calcular_cpm(nodos, INICIO, fecha_corte=date(2026, 6, 1))
        assert r["A"].desfase == 0


class TestBloqueoPorIncidencia:
    def test_propaga_en_cascada(self) -> None:
        """Una incidencia `detiene` bloquea la actividad y sus sucesoras (§6)."""
        bloqueadas = actividades_bloqueadas_por(_cadena(), {"A"})
        assert bloqueadas == {"B", "C"}

    def test_no_alcanza_ramas_independientes(self) -> None:
        bloqueadas = actividades_bloqueadas_por(_con_rama_holgada(), {"D"})
        assert bloqueadas == {"C"}
        assert "B" not in bloqueadas


def test_cronograma_vacio_no_revienta() -> None:
    assert calcular_cpm([], INICIO) == {}
