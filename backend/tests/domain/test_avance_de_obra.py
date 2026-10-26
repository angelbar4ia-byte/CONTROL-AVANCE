"""Avance de la obra: promedio de sus actividades ponderado por importe (§6)."""

from __future__ import annotations

from decimal import Decimal

from obractrl.domain.obras.avance import ActividadParaAvance, avance_de_obra
from obractrl.domain.shared.valores import Avance


def _act(importe: str, avance: str) -> ActividadParaAvance:
    return ActividadParaAvance(importe=Decimal(importe), avance=Avance(avance))


def test_sin_actividades_el_avance_es_cero() -> None:
    assert avance_de_obra([]).pct == Decimal("0.00")


def test_pesa_por_importe_y_no_por_promedio_simple() -> None:
    # El caso del docstring: el muro de $122k en cero y el castillo de $10k
    # terminado. Promedio simple: 50 %. Ponderado: 10/132.
    obra = [_act("122000", "0"), _act("10000", "100")]
    assert avance_de_obra(obra).pct == Decimal("7.58")


def test_una_actividad_terminada_y_otra_a_la_mitad() -> None:
    obra = [_act("100", "100"), _act("100", "50")]
    assert avance_de_obra(obra).pct == Decimal("75.00")


def test_sin_importes_cae_al_promedio_simple() -> None:
    obra = [_act("0", "100"), _act("0", "50"), _act("0", "0")]
    assert avance_de_obra(obra).pct == Decimal("50.00")


def test_un_importe_negativo_no_resta_peso() -> None:
    obra = [_act("-500", "100"), _act("100", "20")]
    assert avance_de_obra(obra).pct == Decimal("20.00")


def test_todas_terminadas_es_cien() -> None:
    assert avance_de_obra([_act("10", "100"), _act("990", "100")]).pct == Decimal(
        "100.00"
    )


def test_redondea_a_centesimas_hacia_arriba_en_el_empate() -> None:
    # 0.005 exacto: ROUND_HALF_UP, como Avance y como round() de Postgres.
    obra = [_act("1", "0.01"), _act("1", "0")]
    assert avance_de_obra(obra).pct == Decimal("0.01")
