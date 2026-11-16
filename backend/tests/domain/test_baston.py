"""Bastones por longitud de trazo: corte con módulos, escalón del catálogo, conciliación y propuestas (Ola 4, 4D).

Los números del catálogo salen de `ANALISIS_DE_BASICOS_CONCEPTOS.csv` (opus); `scripts/verificar_baston_contra_csv.py` los compara
con el CSV cuando se corre a mano.
"""

from __future__ import annotations

import math

import pytest

from obractrl.domain.cuantificacion.baston import (
    ESCALONES_DE_CATALOGO,
    ElementoDeBastonNoEncontrado,
    EntradaDeBaston,
    ErrorDeBaston,
    calcular_baston,
    concepto_nuevo_de,
    definicion_de,
    escalon_para,
    propuestas_de_actualizacion_de_apu,
)
from obractrl.domain.cuantificacion.biblioteca_de_elementos import BIBLIOTECA, elemento_de_la_biblioteca


def _calc(**kw: object) -> dict:
    return calcular_baston(EntradaDeBaston(**kw))  # type: ignore[arg-type]


def test_el_mockup_80_cm_a_cada_50_en_varilla_de_media_pulgada() -> None:
    # La regla del mockup: piezas = ceil(trazo ÷ sep) + 1; el exacto da floor(12 ÷ 0.8) = 15 por varilla y kg = piezas × largo × peso.
    r = _calc(trazo_m=10, varilla_numero=4, sep_cm=50, largo_cm=80)
    assert r["ajustado"]["bastones"] == 21 == r["pago"]["cantidad"]
    assert r["exacto"]["varillas"] == math.ceil(21 / 15) == 2
    assert r["exacto"]["kg"] == pytest.approx(21 * 0.8 * 0.994)
    # Ajustado a módulos (Q28): el bastón de 0.80 m gasta el módulo de 1.00 m → 12 por varilla.
    assert r["ajustado"]["corte"]["modulo_m"] == 1.0 and r["ajustado"]["corte"]["piezas_por_varilla"] == 12
    assert r["ajustado"]["varillas"] == 2 and r["ajustado"]["kg"] == pytest.approx(21 * 1.0 * 0.994)
    assert r["ajustado"]["kg"] > r["exacto"]["kg"]


@pytest.mark.parametrize(
    ("largo_cm", "modulo", "por_varilla"),
    [(100, 1.0, 12), (120, 1.5, 8), (150, 1.5, 8), (170, 2.0, 6), (240, 3.0, 4), (400, 4.0, 3), (600, 6.0, 2)],
)
def test_el_bastón_se_corta_del_primer_módulo_que_lo_cubre(largo_cm: float, modulo: float, por_varilla: int) -> None:
    c = _calc(largo_cm=largo_cm)["ajustado"]["corte"]
    assert c["piezas_por_baston"] == 1 and c["modulo_m"] == modulo and c["piezas_por_varilla"] == por_varilla


def test_un_baston_de_7_m_se_corta_en_dos_piezas_con_traslape_de_40_diametros() -> None:
    r = _calc(largo_cm=700, sep_cm=40, trazo_m=4)
    c = r["ajustado"]["corte"]
    assert c["piezas_por_baston"] == 2 and c["modulo_m"] == 4.0
    assert c["traslape_m"] == pytest.approx(40 * 3 / 8 * 25.4 / 1000)  # 0.381 m en 3/8
    assert r["ajustado"]["bastones"] == 11 and r["ajustado"]["varillas"] == math.ceil(22 / 3)
    assert any("2 piezas" in a for a in r["avisos"])


def test_las_puntas_se_suman_al_largo_y_por_defecto_no_hay_gancho() -> None:
    assert _calc(largo_cm=100)["ajustado"]["corte"]["modulo_m"] == 1.0
    con_puntas = _calc(largo_cm=100, puntas_cm=50)["ajustado"]["corte"]
    assert con_puntas["modulo_m"] == 1.5 and con_puntas["puntas_m"] == 0.5


def test_las_piezas_son_ceil_del_trazo_entre_la_separacion_mas_uno() -> None:
    assert _calc(trazo_m=1, sep_cm=25)["ajustado"]["bastones"] == 5
    assert _calc(trazo_m=1.01, sep_cm=25)["ajustado"]["bastones"] == 6
    assert _calc(trazo_m=0.1, sep_cm=25)["ajustado"]["bastones"] == 2


def test_el_escalon_exacto_del_catalogo_y_su_conciliacion() -> None:
    r = _calc()  # 1.20 @25 en 3/8
    assert r["escalon"] == "exacto" and r["concepto"]["clave"] == "AUX-02010" and r["concepto"]["estado"] == "catalogo"
    (bloque,) = r["conciliacion"]
    varilla = next(f for f in bloque["filas"] if f["clave"] == "ACR-00001")
    assert varilla["catalogo"] == pytest.approx(0.432) and varilla["elemento"] == pytest.approx(0.5)
    assert varilla["marca"] == "≠"  # el módulo de 1.5 m gasta más que el 8 % del catálogo
    alambre = next(f for f in bloque["filas"] if f["clave"] == "ACE-00001")
    assert alambre["marca"] == "solo_catalogo" and alambre["elemento"] is None  # el alambre no se inventa
    assert bloque["mano_de_obra"] == []


def test_el_escalon_mayor_se_usa_y_avisa_y_el_concepto_nuevo_no_se_propone_solo() -> None:
    r = _calc(largo_cm=135, sep_cm=25)
    assert r["escalon"] == "mayor" and r["concepto"]["clave"] == "AUX-02020" and r["concepto"]["largo_m"] == 1.5
    assert any("1.35" in a and "1.50" in a for a in r["avisos"])
    assert r["conciliacion"][0]["concepto"]["clave"] == "AUX-02020"


@pytest.mark.parametrize(
    ("kw", "texto"),
    [
        ({"varilla_numero": 4}, "solo trae bastones de varilla 3/8"),
        ({"sep_cm": 30}, "no trae bastones a 30 cm"),
        ({"largo_cm": 450, "sep_cm": 40}, "rebasa el último escalón"),
    ],
)
def test_sin_escalon_avisa_y_propone_un_concepto_nuevo_provisional(kw: dict, texto: str) -> None:
    r = _calc(**kw)
    assert r["escalon"] == "sin_escalon" and r["conciliacion"] == []
    c = r["concepto"]
    assert c["estado"] == "propuesto" and c["clave_provisional"] is True and c["clave"].startswith("AUX-B")
    assert any(texto in a for a in r["avisos"]) and any("concepto nuevo" in a for a in r["avisos"])
    p = concepto_nuevo_de(EntradaDeBaston(**kw))
    assert p["clase"] == "concepto_nuevo" and p["concepto_clave"] == c["clave"] and p["detalle"]["clave_provisional"] is True
    assert "precio" not in str(p["detalle"]).lower().replace("sin destajo ni precio", "").replace("sin precio", "")


def test_un_escalon_del_catalogo_no_lleva_concepto_nuevo() -> None:
    with pytest.raises(ErrorDeBaston, match="ya trae el escalón AUX-02010"):
        concepto_nuevo_de(EntradaDeBaston())


def test_los_escalones_se_leen_del_csv_con_su_composicion() -> None:
    por_clave = {e[0]: e for e in ESCALONES_DE_CATALOGO}
    assert len(por_clave) == 28
    assert por_clave["AUX-02010"][1:5] == (1.2, 25, 0.432, 0.164724)
    assert por_clave["AUX-02072"][1:5] == (0.8, 50, 0.144, 0.049417)
    assert por_clave["AUX-02100"][1:5] == (4.0, 40, 0.9, 0.185315)
    assert escalon_para(3, 80, 50)["escalon"][0] == "AUX-02072"
    # El catálogo trae 8 % de desperdicio: 1.20 m a 25 cm = 4 bastones/m × 1.2 ÷ 12 × 1.08.
    assert 4 * 1.2 / 12 * 1.08 == pytest.approx(0.432)


def test_confirmar_el_calculo_propone_una_version_con_el_antes_y_el_despues() -> None:
    (p,) = propuestas_de_actualizacion_de_apu(_calc())
    assert p["clase"] == "version_de_concepto" and p["concepto_clave"] == "AUX-02010"
    (c,) = p["detalle"]["cambios"]
    assert c["insumo"] == "ACR-00001" and c["antes"] == 0.432 and c["despues"] == pytest.approx(0.5)
    # Sin escalón no hay con qué comparar, así que no hay versión que proponer.
    assert propuestas_de_actualizacion_de_apu(_calc(sep_cm=30)) == []


@pytest.mark.parametrize(
    ("kw", "texto"),
    [
        ({"trazo_m": 0}, "longitud de trazo"),
        ({"varilla_numero": 9}, "varilla"),
        ({"sep_cm": 2}, "separación"),
        ({"largo_cm": 5}, "largo del bastón"),
        ({"puntas_cm": 200}, "puntas"),
        ({"traslape_diametros": -1}, "traslape"),
    ],
)
def test_los_datos_que_no_valen_se_rechazan(kw: dict, texto: str) -> None:
    with pytest.raises(ErrorDeBaston, match=texto):
        _calc(**kw)


def test_la_ficha_y_la_biblioteca() -> None:
    f = definicion_de("BA-1")
    assert f["modulos_de_corte_m"] == [1.0, 1.5, 2.0, 3.0, 4.0, 6.0] and len(f["escalones"]) == 28
    assert {v["clave"] for v in f["varillas"]} == {"ACR-00001", "ACR-00002", "ACR-00003", "ACR-00004"}
    assert [p["clave"] for p in f["pendientes"]][:1] == ["Q28"]
    with pytest.raises(ElementoDeBastonNoEncontrado):
        definicion_de("BA-9")
    sub = next(s for c in BIBLIOTECA if c["clave"] == "aceros" for s in c["subcategorias"])
    assert [e["clave"] for e in sub["elementos"]] == ["BA-1"] and sub["elementos"][0]["tipo"] == "baston"
    assert elemento_de_la_biblioteca("BA-1") is None  # su ficha es propia, como la del tabique
