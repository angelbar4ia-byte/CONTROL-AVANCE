"""Los drivers del Paramétrico (Ola 4B): valor vigente global / obra / mixto, validación, permisos (Q3) y el contraste con los
valores por defecto del acero que ya existen en el dominio."""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.cuantificacion.drivers import (
    ALTURA_ESTANDAR,
    CATALOGO_DE_DRIVERS,
    ErrorDeDriver,
    definicion_de,
    drivers_de_receta,
    puede_editar_drivers,
    resolver,
    validar_modo,
    validar_que_edita,
    validar_valor,
)
from obractrl.domain.cuantificacion.receta_acero import DriversDeReceta


def _d(clave: str):
    d = definicion_de(clave)
    assert d is not None
    return d


def test_el_catalogo_trae_los_catorce_drivers_de_la_especificacion() -> None:
    assert [d.clave for d in CATALOGO_DE_DRIVERS] == [
        "altura_estandar", "separacion_castillos", "desperdicio_mamposteria", "desperdicio_concreto", "traslape_armex_cm",
        "traslape_varilla_diametros", "desperdicio_acero", "puntas_inferior_diametros", "puntas_superior_diametros",
        "puntas_armex_cm", "tolerancia_corte_cm", "max_piezas_corte", "escarpio_minimo", "corona_cimiento_cm",
    ]
    assert len({d.clave for d in CATALOGO_DE_DRIVERS}) == 14


def test_la_altura_estandar_parte_de_3_00_m_y_es_ajustable() -> None:
    d = _d(ALTURA_ESTANDAR)
    assert d.inicial == Decimal("3.00") and d.modo_inicial == "ajustable" and d.unidad == "m"


def test_escarpio_y_corona_nacen_fijos_y_el_resto_ajustable() -> None:
    assert {d.clave for d in CATALOGO_DE_DRIVERS if d.modo_inicial == "fijo"} == {"escarpio_minimo", "corona_cimiento_cm"}


def test_los_valores_de_partida_coinciden_con_los_drivers_del_acero_ya_construidos() -> None:
    """Un solo valor de partida: el de `DriversDeReceta` (ola 1B) y el del catálogo de drivers no se contradicen."""
    base = DriversDeReceta()
    vigentes = {d.clave: d.inicial for d in CATALOGO_DE_DRIVERS}
    assert drivers_de_receta(vigentes) == base
    assert drivers_de_receta({}) == base


def test_drivers_de_receta_toma_los_valores_vigentes() -> None:
    r = drivers_de_receta({"traslape_armex_cm": Decimal("20"), "max_piezas_corte": Decimal("2"), "desperdicio_acero": Decimal("5")})
    assert r.traslape_armex_cm == 20.0 and r.max_piezas_corte == 2 and r.desperdicio_acero_pct == 5.0
    assert r.traslape_varilla_diametros == 40.0


def test_sin_global_ni_obra_vale_el_valor_de_partida() -> None:
    v = resolver(_d(ALTURA_ESTANDAR), valor_global=None, modo_global=None, valor_obra=None)
    assert (v.valor, v.origen, v.modo) == (Decimal("3.00"), "inicial", "ajustable")


def test_el_global_editado_manda_cuando_la_obra_no_ajusta() -> None:
    v = resolver(_d(ALTURA_ESTANDAR), valor_global=Decimal("2.8"), modo_global="ajustable", valor_obra=None)
    assert (v.valor, v.origen) == (Decimal("2.8"), "global")


def test_un_driver_ajustable_toma_el_valor_de_la_obra() -> None:
    v = resolver(_d(ALTURA_ESTANDAR), valor_global=Decimal("3"), modo_global="ajustable", valor_obra=Decimal("2.6"))
    assert (v.valor, v.origen, v.valor_global, v.ajuste_ignorado) == (Decimal("2.6"), "obra", Decimal("3"), False)


def test_un_driver_fijo_ignora_el_ajuste_de_la_obra_pero_lo_avisa() -> None:
    v = resolver(_d(ALTURA_ESTANDAR), valor_global=Decimal("3"), modo_global="fijo", valor_obra=Decimal("2.6"))
    assert (v.valor, v.origen, v.ajuste_ignorado, v.valor_obra) == (Decimal("3"), "global", True, Decimal("2.6"))


def test_un_ajuste_de_obra_de_un_driver_fijo_de_partida_no_vale() -> None:
    v = resolver(_d("escarpio_minimo"), valor_global=None, modo_global=None, valor_obra=Decimal("2"))
    assert (v.valor, v.origen, v.modo, v.ajuste_ignorado) == (Decimal("1.5"), "inicial", "fijo", True)


@pytest.mark.parametrize("valor", ["0", "-1", "abc", "", "NaN", "Infinity", "31"])
def test_la_altura_no_acepta_cero_negativos_texto_ni_exageros(valor: str) -> None:
    with pytest.raises(ErrorDeDriver):
        validar_valor(_d(ALTURA_ESTANDAR), valor)


def test_se_acepta_la_coma_decimal_y_se_limpia_a_seis_decimales() -> None:
    assert validar_valor(_d(ALTURA_ESTANDAR), "2,8") == Decimal("2.800000")
    assert validar_valor(_d(ALTURA_ESTANDAR), 3.25) == Decimal("3.250000")


def test_un_porcentaje_va_de_0_a_100_y_las_piezas_son_enteras() -> None:
    assert validar_valor(_d("desperdicio_acero"), "0") == 0
    with pytest.raises(ErrorDeDriver):
        validar_valor(_d("desperdicio_acero"), "101")
    assert validar_valor(_d("max_piezas_corte"), "4") == 4
    with pytest.raises(ErrorDeDriver):
        validar_valor(_d("max_piezas_corte"), "2.5")
    with pytest.raises(ErrorDeDriver):
        validar_valor(_d("max_piezas_corte"), "0")


def test_el_modo_es_fijo_o_ajustable() -> None:
    assert validar_modo("fijo") == "fijo" and validar_modo("ajustable") == "ajustable"
    with pytest.raises(ErrorDeDriver):
        validar_modo("mixto")


@pytest.mark.parametrize("rol", ["costos", "control_obra"])
def test_costos_y_control_de_obra_editan_los_drivers(rol: str) -> None:
    assert puede_editar_drivers(rol)
    validar_que_edita(rol)


@pytest.mark.parametrize("rol", ["residente", "supervisor", "super_intendente", ""])
def test_los_demas_roles_solo_leen(rol: str) -> None:
    assert not puede_editar_drivers(rol)
    with pytest.raises(ErrorDeDriver):
        validar_que_edita(rol)


def test_f4_solo_el_escarpio_y_la_corona_son_inmutables() -> None:
    """Siguen fijos (no ajustables): no basta con nacer «fijo» (el global fijo se podía editar y volver ajustable)."""
    assert {d.clave for d in CATALOGO_DE_DRIVERS if d.inmutable} == {"escarpio_minimo", "corona_cimiento_cm"}
    assert all(d.modo_inicial == "fijo" for d in CATALOGO_DE_DRIVERS if d.inmutable)
