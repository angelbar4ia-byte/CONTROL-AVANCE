"""El muro de contención de piedra MCT-01010: Cuadro 1, dentellón, dren y piezas de tubo."""

from __future__ import annotations

import pytest

from obractrl.domain.cuantificacion.biblioteca_de_elementos import (
    BIBLIOTECA,
    elemento_de_la_biblioteca,
)
from obractrl.domain.cuantificacion.muro_contencion import (
    EntradaMuroDeContencion,
    ErrorDeMuroDeContencion,
    calcular_muro_de_contencion,
    fila_del_cuadro_1,
    piezas_de_tubo,
)


def calcular(**kw: object) -> dict:
    return calcular_muro_de_contencion(EntradaMuroDeContencion(**kw))  # type: ignore[arg-type]


def test_a_3_m_sale_del_cuadro_1_con_dentellon() -> None:
    r = calcular(alto_m=3.0)
    assert (r["seccion"]["corona_m"], r["seccion"]["base_m"]) == (0.60, 1.20)
    assert r["volumen"]["muro_m3_ml"] == pytest.approx(2.70)
    assert r["volumen"]["dentellon_m3_ml"] == pytest.approx(0.21)
    assert r["volumen"]["excavacion_dentellon_m3_ml"] == pytest.approx(0.21)
    assert r["volumen"]["total_m3_ml"] == pytest.approx(2.91)
    assert r["volumen"]["piedra_a_comprar_m3_ml"] == pytest.approx(2.91 * 1.5)


def test_toma_la_fila_de_la_altura_igual_o_inmediata_superior_sin_interpolar() -> None:
    assert fila_del_cuadro_1(1.0)[0]["H"] == 1.0
    assert fila_del_cuadro_1(1.01)[0]["H"] == 1.5
    r = calcular(alto_m=2.2)
    assert (r["seccion"]["corona_m"], r["seccion"]["base_m"]) == (0.60, 1.05)
    # el volumen usa la altura exacta
    assert r["volumen"]["muro_m3_ml"] == pytest.approx((0.60 + 1.05) / 2 * 2.2)


def test_bajo_2_m_no_hay_dentellon_ni_dren() -> None:
    r = calcular(alto_m=1.5)
    assert r["dentellon"]["aplica"] is False
    assert r["volumen"]["dentellon_m3_ml"] == 0
    assert r["dren"]["aplica"] is False
    assert r["dren"]["hileras"] == 0
    assert [i["clave"] for i in r["insumos_por_m3"]] == ["MEZ-03060"]
    assert any("dentellón aplica desde 2.00" in a for a in r["advertencias"])


def test_el_dentellon_es_opcional() -> None:
    r = calcular(alto_m=3.0, dentellon=False)
    assert r["volumen"]["total_m3_ml"] == pytest.approx(2.70)


@pytest.mark.parametrize(
    ("alto", "hileras"), [(2.0, 2), (2.5, 2), (3.0, 3), (4.0, 4), (6.0, 6)]
)
def test_hileras_a_0_50_y_cada_metro(alto: float, hileras: int) -> None:
    r = calcular(alto_m=alto)
    assert r["dren"]["hileras"] == hileras
    assert r["dren"]["alturas_m"][0] == 0.5
    assert all(
        b - a == pytest.approx(1.0)
        for a, b in zip(r["dren"]["alturas_m"], r["dren"]["alturas_m"][1:], strict=False)
    )


def test_separacion_segun_la_lluvia() -> None:
    assert calcular(alto_m=3.0)["dren"]["separacion_m"] == 3.0
    alta = calcular(alto_m=3.0, lluvia="alta")
    assert alta["dren"]["separacion_m"] == 1.5
    assert alta["dren"]["lloraderos_por_ml"] == pytest.approx(2.0)


def test_tubo_en_piezas_comerciales_por_m3() -> None:
    r = calcular(
        alto_m=3.0
    )  # espesor medio 0.90, 1 lloradero por metro, pieza de 6 m: caben 6
    tubo = r["dren"]["tubo"]
    assert tubo["ml_por_ml_de_trazo"] == pytest.approx(0.90)
    assert tubo["lloraderos_por_pieza"] == 6
    assert tubo["piezas_por_ml_de_trazo"] == pytest.approx(1 / 6)
    fila = next(i for i in r["insumos_por_m3"] if i["clave"] == "INS-D001")
    assert fila["cantidad"] == pytest.approx((1 / 6) / 2.91)
    assert fila["provisional"] is True


def test_tubo_de_concreto_de_1_m_cabe_un_lloradero_por_pieza() -> None:
    r = calcular(alto_m=3.0, tubo="concreto")  # 0.90 m en pieza de 1 m: 1 por pieza
    assert r["dren"]["tubo"]["clave"] == "INS-D002"
    assert r["dren"]["tubo"]["lloraderos_por_pieza"] == 1


def test_piezas_de_tubo_cuando_no_cabe_se_unen() -> None:
    assert piezas_de_tubo(1.2, 1.0) == {"por_pieza": 0, "piezas_por_lloradero": 2.0}
    assert piezas_de_tubo(0.9, 6.0) == {
        "por_pieza": 6,
        "piezas_por_lloradero": pytest.approx(1 / 6),
    }
    assert piezas_de_tubo(0, 6.0)["piezas_por_lloradero"] == 0


def test_el_filtro_queda_por_definir_si_no_se_da_el_espesor() -> None:
    r = calcular(alto_m=3.0)
    assert r["dren"]["filtro"]["por_definir"] is True
    assert r["dren"]["filtro"]["volumen_m3_ml"] is None
    grava = next(i for i in r["insumos_por_m3"] if i["clave"] == "INS-D003")
    assert grava["cantidad"] == 0
    assert any("filtro de grava" in a for a in r["advertencias"])
    assert any("INS-D001" in a and "provisionales" in a for a in r["advertencias"])


def test_filtro_con_relleno_vertical_e_inclinado() -> None:
    v = calcular(alto_m=3.0, filtro_cm=30)
    assert v["dren"]["filtro"]["volumen_m3_ml"] == pytest.approx(0.30 * 3.0)
    i = calcular(alto_m=3.0, filtro_cm=30, relleno="inclinada")
    assert i["dren"]["filtro"]["longitud_cara_m"] == pytest.approx(
        3.06, abs=0.005
    )  # 3.00 con corona 0.60 y base 1.20
    grava = next(x for x in i["insumos_por_m3"] if x["clave"] == "INS-D003")
    assert grava["cantidad"] == pytest.approx(i["dren"]["filtro"]["volumen_m3_ml"] / 2.91)


def test_carpeta_de_3_cm_sobre_la_corona() -> None:
    r = calcular(alto_m=3.0)
    assert r["dren"]["carpeta"]["volumen_m3_ml"] == pytest.approx(0.60 * 0.03)
    mezcla = next(i for i in r["insumos_por_m3"] if i["clave"] == "MEZ-03060")
    assert mezcla["cantidad"] == pytest.approx(0.018 / 2.91)
    assert mezcla["provisional"] is False


def test_tresbolillo_las_hileras_alternas_se_desplazan_la_mitad() -> None:
    h = calcular(alto_m=3.0, tramo_m=6.0)["vistas"]["hileras"]
    assert h[0]["x_m"] == [0.75, 3.75]
    assert h[1]["x_m"] == [2.25, 5.25]
    assert h[2]["x_m"] == h[0]["x_m"]


def test_corona_y_base_a_mano() -> None:
    r = calcular(alto_m=3.0, corona_m=0.5, base_m=1.0)
    assert r["seccion"]["manual"] is True
    assert r["volumen"]["muro_m3_ml"] == pytest.approx(0.75 * 3.0)


def test_mas_alto_que_la_tabla_avisa() -> None:
    r = calcular(alto_m=7.0)
    assert r["seccion"]["fuera_de_tabla"] is True
    assert r["seccion"]["base_m"] == 2.47
    assert any("rebasa el Cuadro 1" in a for a in r["advertencias"])


@pytest.mark.parametrize(
    "mal",
    [
        {"alto_m": 0},
        {"alto_m": -1},
        {"alto_m": 3, "lluvia": "media"},
        {"alto_m": 3, "tubo": "acero"},
        {"alto_m": 3, "relleno": "x"},
        {"alto_m": 3, "corona_m": 1.0, "base_m": 0.5},
        {"alto_m": 3, "filtro_cm": 0},
    ],
)
def test_parametros_que_no_valen_se_rechazan(mal: dict) -> None:
    with pytest.raises(ErrorDeMuroDeContencion):
        calcular(**mal)


def test_la_biblioteca_trae_solo_el_muro_de_piedra() -> None:
    elementos = [
        e["clave"] for c in BIBLIOTECA for s in c["subcategorias"] for e in s["elementos"]
    ]
    assert elementos == ["MCT-01010"]
    d = elemento_de_la_biblioteca("MCT-01010")
    assert d is not None
    assert d["concepto"]["clave"] == "MCT-01011"
    assert len(d["cuadro_1"]) == 11
    assert {p["clave"] for p in d["pendientes"]} >= {"Q34", "Q47"}
    assert elemento_de_la_biblioteca("CIM-01010") is None
