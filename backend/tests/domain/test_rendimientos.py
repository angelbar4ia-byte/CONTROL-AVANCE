"""Rendimientos derivados de un destajo (`CONOCIMIENTO.md` §6.2, `CATALOGOS.md` §10)."""

from __future__ import annotations

from decimal import Decimal

from obractrl.domain.catalogos.rendimientos import (
    jornadas_por_unidad,
    razon_teorico_calculado,
    rendimiento_calculado,
)


def test_el_ejemplo_del_cerebro_50_por_m2_con_una_cuadrilla_de_1452() -> None:
    # $50/m² ÷ $1,452/jornada → 0.0344 jor/m² = 29.04 m² por jornada.
    assert rendimiento_calculado(Decimal(1452), Decimal(50)) == Decimal("29.0400")
    assert jornadas_por_unidad(Decimal(1452), Decimal(50)) == Decimal("0.0344")


def test_el_castillo_k1_da_la_razon_de_un_cambio_de_salario() -> None:
    # MOE-02020: $130/m con MOCU-005 ($1,452) y teórico 12.12 → razón 1.085.
    calculado = rendimiento_calculado(Decimal(1452), Decimal(130))
    assert calculado == Decimal("11.1692")
    assert razon_teorico_calculado(Decimal("12.12"), calculado) == Decimal("1.0851")


def test_sin_dato_no_hay_cifra_ni_un_cero_que_mienta() -> None:
    assert rendimiento_calculado(None, Decimal(50)) is None
    assert rendimiento_calculado(Decimal(1452), None) is None
    assert rendimiento_calculado(Decimal(1452), Decimal(0)) is None
    assert jornadas_por_unidad(Decimal(0), Decimal(50)) is None
    assert razon_teorico_calculado(None, Decimal(10)) is None
    assert razon_teorico_calculado(Decimal(10), None) is None
