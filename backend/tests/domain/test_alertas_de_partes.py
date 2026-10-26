"""La alerta de desfase del presupuesto (D-575 a D-577)."""

from __future__ import annotations

from datetime import date

import pytest

from obractrl.domain.partes.alertas import (
    ErrorDeUmbrales,
    Severidad,
    dias_para_necesitarla,
    severidad_del_desfase,
    validar_umbrales,
)


def test_a_dos_semanas_es_aviso_y_a_una_es_importante() -> None:
    assert severidad_del_desfase(30) is None
    assert severidad_del_desfase(15) is None
    assert severidad_del_desfase(14) is Severidad.AVISO
    assert severidad_del_desfase(8) is Severidad.AVISO
    assert severidad_del_desfase(7) is Severidad.IMPORTANTE
    assert severidad_del_desfase(0) is Severidad.IMPORTANTE


def test_lo_que_ya_se_necesitaba_es_importante() -> None:
    assert severidad_del_desfase(-3) is Severidad.IMPORTANTE


def test_los_umbrales_son_configurables() -> None:
    assert severidad_del_desfase(20, aviso_dias=21, importante_dias=10) is Severidad.AVISO
    assert severidad_del_desfase(10, aviso_dias=21, importante_dias=10) is Severidad.IMPORTANTE


def test_dias_para_necesitarla() -> None:
    assert dias_para_necesitarla(date(2026, 3, 16), date(2026, 3, 2)) == 14
    assert dias_para_necesitarla(date(2026, 3, 1), date(2026, 3, 2)) == -1


def test_los_umbrales_tienen_que_ser_coherentes() -> None:
    assert validar_umbrales(14, 7) == (14, 7)
    assert validar_umbrales(7, 7) == (7, 7)
    with pytest.raises(ErrorDeUmbrales, match="aviso va antes"):
        validar_umbrales(5, 7)
    with pytest.raises(ErrorDeUmbrales, match="negativos"):
        validar_umbrales(14, -1)
