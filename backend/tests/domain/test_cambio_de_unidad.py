"""La medida con que un trazo mide un concepto de unidad nueva (D-623) y la altura estándar de la obra (Ola 4C, Q1)."""

from __future__ import annotations

from decimal import Decimal

from obractrl.domain.cuantificacion.cambio_de_unidad import (
    medida_para,
    ya_mide_lo_que_corresponde,
)


def test_una_linea_sin_grosor_en_m2_mide_su_largo_por_la_altura_estandar_y_dos_caras() -> None:
    assert medida_para("area", "linea", False) == ("longitud", Decimal("6.00"))  # 3.00 m de partida × 2 caras
    assert medida_para("area", "linea", False, Decimal("2.6")) == ("longitud", Decimal("5.2"))  # el driver de la obra manda
    assert medida_para("area", "linea", False, Decimal("2.75")) == ("longitud", Decimal("5.5"))


def test_lo_demas_no_depende_de_la_altura() -> None:
    assert medida_para("area", "linea", True, Decimal("2.6")) == ("area", Decimal(1))
    assert medida_para("area", "area", False, Decimal("2.6")) == ("area", Decimal(1))
    assert medida_para("area", "punto", False) is None
    assert medida_para("lineal", "linea", False, Decimal("2.6")) == ("longitud", Decimal(1))
    assert medida_para("conteo", "punto", False) == ("conteo", Decimal(1))


def test_un_enlace_que_ya_mide_lo_mismo_no_se_rehace() -> None:
    medida = medida_para("area", "linea", False, Decimal("3"))
    assert ya_mide_lo_que_corresponde(medida, "longitud", Decimal("6"))
    assert not ya_mide_lo_que_corresponde(None, "longitud", Decimal("6"))


def test_q1_una_linea_que_ya_trae_su_altura_la_conserva_aunque_el_driver_sea_otro() -> None:
    hoy = medida_para("area", "linea", False, Decimal("3"))  # el driver de hoy: 3.00 m
    assert ya_mide_lo_que_corresponde(hoy, "longitud", Decimal("5.2"))  # trazada con 2.6 m: se conserva
    # Pero un enlace de otra naturaleza sí se rehace.
    assert not ya_mide_lo_que_corresponde(hoy, "conteo", Decimal(1))
    assert not ya_mide_lo_que_corresponde(hoy, "longitud", Decimal(1))  # un metro lineal no es largo × altura
    # Y pasar a metros lineales con un enlace de largo × altura sí lo rehace a factor 1.
    assert not ya_mide_lo_que_corresponde(medida_para("lineal", "linea", False), "longitud", Decimal("5.2"))
