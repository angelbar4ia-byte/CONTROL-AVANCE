"""Quién propone y quién autoriza un cambio a un driver (F3) y qué se puede proponer (F4)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.cuantificacion.autorizacion_de_drivers import (
    armar_propuesta,
    estado_de_alta,
    puede_autorizar,
    validar_que_autoriza,
    validar_que_propone,
)
from obractrl.domain.cuantificacion.drivers import ErrorDeDriver, definicion_de


def _d(clave: str):
    d = definicion_de(clave)
    assert d is not None
    return d


@pytest.mark.parametrize("rol", ["costos", "control_obra"])
def test_costos_y_control_de_obra_proponen(rol: str) -> None:
    validar_que_propone(rol)


@pytest.mark.parametrize("rol", ["residente", "supervisor", "super_intendente", "almacen"])
def test_los_demas_roles_no_proponen_ni_autorizan(rol: str) -> None:
    with pytest.raises(ErrorDeDriver):
        validar_que_propone(rol)
    with pytest.raises(ErrorDeDriver):
        validar_que_autoriza(rol)


def test_solo_control_de_obra_autoriza_y_lo_suyo_nace_autorizado() -> None:
    assert puede_autorizar("control_obra") and not puede_autorizar("costos")
    with pytest.raises(ErrorDeDriver, match="Control de obra autoriza"):
        validar_que_autoriza("costos")
    assert estado_de_alta("control_obra") == "autorizada" and estado_de_alta("costos") == "pendiente"


def test_el_global_pide_valor_o_modo_y_los_valida() -> None:
    d = _d("altura_estandar")
    p = armar_propuesta(d, alcance="global", valor="2,8")
    assert (p.valor, p.modo, p.accion) == (Decimal("2.8"), None, "fijar")
    assert armar_propuesta(d, alcance="global", modo="fijo").modo == "fijo"
    with pytest.raises(ErrorDeDriver):
        armar_propuesta(d, alcance="global")
    with pytest.raises(ErrorDeDriver):
        armar_propuesta(d, alcance="global", valor="0")
    with pytest.raises(ErrorDeDriver):
        armar_propuesta(d, alcance="global", accion="quitar")


def test_el_ajuste_de_obra_solo_cabe_en_un_driver_ajustable_y_no_lleva_modo() -> None:
    d = _d("altura_estandar")
    assert armar_propuesta(d, alcance="obra", valor="2.6", modo_global_actual="ajustable").valor == Decimal("2.6")
    with pytest.raises(ErrorDeDriver, match="es fijo"):
        armar_propuesta(d, alcance="obra", valor="2.6", modo_global_actual="fijo")
    with pytest.raises(ErrorDeDriver):
        armar_propuesta(d, alcance="obra", valor="2.6", modo="fijo", modo_global_actual="ajustable")
    with pytest.raises(ErrorDeDriver):
        armar_propuesta(d, alcance="obra", modo_global_actual="ajustable")  # sin valor
    # Quitar el ajuste vale aunque el global ya sea fijo (la obra vuelve al global) y no lleva valor.
    assert armar_propuesta(d, alcance="obra", accion="quitar", modo_global_actual="fijo").accion == "quitar"
    with pytest.raises(ErrorDeDriver):
        armar_propuesta(d, alcance="obra", accion="quitar", valor="2")


@pytest.mark.parametrize("clave", ["escarpio_minimo", "corona_cimiento_cm"])
def test_f4_el_escarpio_y_la_corona_no_se_proponen_de_ninguna_forma(clave: str) -> None:
    d = _d(clave)
    assert d.inmutable and d.modo_inicial == "fijo"
    for kw in ({"valor": "2"}, {"modo": "ajustable"}, {"modo": "fijo"}):
        with pytest.raises(ErrorDeDriver, match="no se cambia"):
            armar_propuesta(d, alcance="global", **kw)  # type: ignore[arg-type]
    with pytest.raises(ErrorDeDriver, match="no se cambia"):
        armar_propuesta(d, alcance="obra", valor="2", modo_global_actual="fijo")
    with pytest.raises(ErrorDeDriver, match="no se cambia"):
        armar_propuesta(d, alcance="obra", accion="quitar")
