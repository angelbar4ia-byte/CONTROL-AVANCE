"""Reglas puras de las mediciones (migración 0088)."""

import pytest

from obractrl.domain.cuantificacion.medicion import (
    admite_geometria,
    medida_admitida,
    motivo_de_incompatibilidad,
    normalizar_nombre,
)
from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion


@pytest.mark.parametrize(
    ("tipo", "geometria", "forma", "cabe"),
    [
        ("area", "ST_Polygon", False, True),
        ("area", "ST_Polygon", True, False),  # una pieza estampada se cuenta, no es un área
        ("area", "ST_LineString", False, False),
        ("lineal", "ST_LineString", False, True),
        ("lineal", "ST_Polygon", False, False),
        ("conteo", "ST_Point", False, True),
        ("conteo", "ST_Polygon", True, True),
        ("conteo", "ST_Polygon", False, False),
        ("conteo", "ST_LineString", False, False),
        ("raro", "ST_Point", False, False),
    ],
)
def test_que_geometrias_admite_cada_tipo(tipo: str, geometria: str, forma: bool, cabe: bool) -> None:
    assert admite_geometria(tipo, geometria, forma) is cabe
    assert (motivo_de_incompatibilidad(tipo, geometria, forma) is None) is cabe


def test_el_motivo_dice_que_no_cabe_y_que_si_admite_cada_tipo() -> None:
    motivo = motivo_de_incompatibilidad("lineal", "ST_Polygon", False)
    assert motivo is not None and "lineal" in motivo and "un área" in motivo


def test_las_medidas_que_se_asignan_dependen_del_tipo() -> None:
    assert medida_admitida("area", "area") and medida_admitida("area", "perimetro")
    assert not medida_admitida("area", "longitud")
    assert medida_admitida("lineal", "longitud") and medida_admitida("lineal", "area")  # el área de un muro
    assert medida_admitida("conteo", "conteo") and not medida_admitida("conteo", "area")
    assert not medida_admitida("raro", "area")


def test_el_nombre_se_limpia_y_no_puede_quedar_vacio_ni_pasar_de_120() -> None:
    assert normalizar_nombre("  Recámara   1 ") == "Recámara 1"
    with pytest.raises(ErrorDeCuantificacion):
        normalizar_nombre("   ")
    with pytest.raises(ErrorDeCuantificacion):
        normalizar_nombre("x" * 121)
