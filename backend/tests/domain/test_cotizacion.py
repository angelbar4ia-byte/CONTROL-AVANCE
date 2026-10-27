"""La cotización al cliente de lo modificado: por diferencia entre 0.7 y por m² (D-533, D-546)."""

from decimal import Decimal

import pytest

from obractrl.domain.partes.cotizacion import (
    ErrorDeCotizacion,
    MetodoDePrecio,
    Modificado,
    cotizar,
)

D = Decimal


def mod(desc: str, delta: str, precio: str) -> Modificado:
    return Modificado(desc, desc, None, D(delta), D(precio))


def test_por_diferencia_resta_lo_que_sale_a_lo_que_entra_y_divide_entre_el_factor() -> None:
    # Entran 3 sanitarios nuevos a $1,000 y salen 3 viejos a $600: 1,200 de diferencia / 0.7.
    c = cotizar([mod("nuevo", "3", "1000"), mod("viejo", "-3", "600")], metodo=MetodoDePrecio.POR_DIFERENCIA)
    assert (c.costo_entra, c.costo_sale) == (D("3000"), D("1800"))
    assert c.precio == c.precio_por_diferencia == D("1714.29")
    # Los dos bloques llevan cantidades positivas; el sistema resta.
    assert {(x["bloque"], x["cantidad"]) for x in c.lineas} == {("entra", "3"), ("sale", "3")}


def test_restar_costos_y_dividir_da_lo_mismo_que_restar_precios() -> None:
    a = cotizar([mod("a", "2", "100"), mod("b", "-1", "50")], metodo=MetodoDePrecio.POR_DIFERENCIA)
    assert a.precio == ((D("200") / D("0.7")) - (D("50") / D("0.7"))).quantize(D("0.01"))


def test_por_m2_cobra_la_ampliacion_y_guarda_tambien_la_diferencia_sin_corregir() -> None:
    c = cotizar(
        [mod("ampliación", "10", "11000")],
        metodo=MetodoDePrecio.POR_M2,
        m2_ampliacion=D("10"),
        precio_m2=D("17000"),
    )
    assert c.precio == c.precio_por_m2 == D("170000.00")
    assert c.precio_por_diferencia == D("157142.86")  # 110,000 / 0.7: no coincide y no se corrige solo


def test_un_credito_neto_queda_en_negativo() -> None:
    c = cotizar([mod("sale", "-2", "100")], metodo=MetodoDePrecio.POR_DIFERENCIA)
    assert c.precio == D("-285.71")  # el monto del contrato puede quedar menor (D-551)


def test_sin_nada_modificado_o_sin_datos_del_modo_no_se_cotiza() -> None:
    with pytest.raises(ErrorDeCotizacion, match="nada modificado"):
        cotizar([], metodo=MetodoDePrecio.POR_DIFERENCIA)
    with pytest.raises(ErrorDeCotizacion, match="m²"):
        cotizar([mod("a", "1", "1")], metodo=MetodoDePrecio.POR_M2)
    with pytest.raises(ErrorDeCotizacion, match="precio por m²"):
        cotizar([mod("a", "1", "1")], metodo=MetodoDePrecio.POR_M2, m2_ampliacion=D("5"))
    with pytest.raises(ErrorDeCotizacion, match="factor"):
        cotizar([mod("a", "1", "1")], metodo=MetodoDePrecio.POR_DIFERENCIA, factor=D("1.5"))
