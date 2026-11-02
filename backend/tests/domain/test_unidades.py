from obractrl.domain.cuantificacion.unidades import medidas_que_caben, tipo_de_unidad


def test_la_unidad_dice_el_tipo() -> None:
    assert tipo_de_unidad("m²") == "area"
    assert tipo_de_unidad("M2") == "area"
    assert tipo_de_unidad("ml") == "lineal"
    assert tipo_de_unidad("m3") == "volumen"
    assert tipo_de_unidad("Pza.") == "conteo"
    assert tipo_de_unidad("kg") == "derivada"
    assert tipo_de_unidad("jornal") is None
    assert tipo_de_unidad(None) is None


def test_que_medidas_caben() -> None:
    assert medidas_que_caben("area") == {"area", "perimetro"}
    assert medidas_que_caben("conteo") == {"conteo"}
    assert "longitud" not in (medidas_que_caben("area") or set())
    assert medidas_que_caben(None) is None
