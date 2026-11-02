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


def test_el_factor_por_peso_es_el_peso_en_kg_y_entre_mil_en_toneladas() -> None:
    from decimal import Decimal

    from obractrl.domain.cuantificacion.medicion import (
        MEDIDA_BASE_DEL_PESO,
        factor_por_peso,
    )

    assert factor_por_peso(Decimal("38"), "kg") == Decimal("38.000000")
    assert factor_por_peso(Decimal("38"), "KG ") == Decimal("38.000000")
    assert factor_por_peso(Decimal("38"), "ton") == Decimal("0.038000")
    assert factor_por_peso(Decimal("0.56"), "ton") == Decimal("0.000560")
    assert MEDIDA_BASE_DEL_PESO == {"conteo": "conteo", "lineal": "longitud", "area": "area"}


@pytest.mark.parametrize("unidad", ["m2", "pza", "", None])
def test_el_peso_solo_alimenta_conceptos_en_kg_o_ton(unidad: str | None) -> None:
    from decimal import Decimal

    from obractrl.domain.cuantificacion.medicion import factor_por_peso

    with pytest.raises(ErrorDeCuantificacion):
        factor_por_peso(Decimal("38"), unidad)


def test_un_peso_demasiado_chico_en_toneladas_no_redondea_a_cero_en_silencio() -> None:
    from decimal import Decimal

    from obractrl.domain.cuantificacion.medicion import factor_por_peso

    with pytest.raises(ErrorDeCuantificacion):
        factor_por_peso(Decimal("0.0004"), "ton")


def test_un_enlace_derivado_admite_factor_fraccionario_con_conteo_y_uno_normal_no() -> None:
    from decimal import Decimal

    from obractrl.domain.cuantificacion.reglas import EnlaceCuantificacion
    from obractrl.domain.shared.diccionario import MedidaCuantificacion

    comun = {"trazo_id": "t", "actividad_id": "a", "prototipo_nodo_id": None, "medida": MedidaCuantificacion.CONTEO}
    EnlaceCuantificacion(**comun, factor=Decimal("38.5"), derivado=True)
    with pytest.raises(ErrorDeCuantificacion):
        EnlaceCuantificacion(**comun, factor=Decimal("38.5"))
