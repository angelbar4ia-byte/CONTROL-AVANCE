from decimal import Decimal

import pytest

from obractrl.domain.catalogos.cantidad import (
    FormulaDePiezasComerciales,
    cantidad_por_piezas_comerciales,
)
from obractrl.domain.catalogos.reglas import ErrorDeCatalogo


def _f(piezas: str, largo: str, desp: str = "0") -> FormulaDePiezasComerciales:
    return FormulaDePiezasComerciales(Decimal(piezas), Decimal(largo), Decimal(desp))


def test_el_castillo_k2_cuatro_varillas_de_doce_metros_con_medio_por_ciento() -> None:
    # 4 / 12 = 0.333333…; con 0.5 % de desperdicio: 0.335 por cada ml de castillo.
    assert cantidad_por_piezas_comerciales(_f("4", "12", "0.5")) == Decimal("0.335000")


def test_sin_desperdicio_es_la_division_a_seis_decimales() -> None:
    assert cantidad_por_piezas_comerciales(_f("4", "12")) == Decimal("0.333333")
    assert cantidad_por_piezas_comerciales(_f("1", "3")) == Decimal("0.333333")
    assert cantidad_por_piezas_comerciales(_f("2", "12", "10")) == Decimal("0.183333")


@pytest.mark.parametrize(
    ("piezas", "largo", "desp"), [("0", "12", "0"), ("4", "0", "0"), ("-1", "12", "0"), ("4", "12", "-1"), ("4", "12", "101")]
)
def test_lo_que_no_tiene_sentido_se_rechaza(piezas: str, largo: str, desp: str) -> None:
    with pytest.raises(ErrorDeCatalogo):
        cantidad_por_piezas_comerciales(_f(piezas, largo, desp))


def test_la_formula_se_guarda_como_json() -> None:
    assert _f("4", "12", "0.5").como_json() == {"tipo": "piezas_comerciales", "piezas": 4.0, "largo": 12.0, "desperdicio_pct": 0.5}
