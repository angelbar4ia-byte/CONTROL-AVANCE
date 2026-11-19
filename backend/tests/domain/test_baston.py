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
from obractrl.domain.cuantificacion.biblioteca_de_elementos import (
    BIBLIOTECA,
    elemento_de_la_biblioteca,
)


def _calc(**kw: object) -> dict:
    return calcular_baston(EntradaDeBaston(**kw))  # type: ignore[arg-type]


def test_el_mockup_80_cm_a_cada_50_en_varilla_de_media_pulgada() -> None:
    # La regla del mockup: piezas = ceil(trazo ÷ sep) + 1; el exacto da floor(12 ÷ 0.8) = 15 por varilla y kg = piezas × largo × peso.
    r = _calc(trazo_m=10, varilla_numero=4, sep_cm=50, largo_cm=80, ganchos=0)  # sin gancho: la regla pura del mockup
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
    c = _calc(largo_cm=largo_cm, ganchos=0)["ajustado"]["corte"]
    assert c["piezas_por_baston"] == 1 and c["modulo_m"] == modulo and c["piezas_por_varilla"] == por_varilla


def test_un_baston_de_7_m_se_corta_en_dos_piezas_con_traslape_de_40_diametros() -> None:
    r = _calc(largo_cm=700, sep_cm=40, trazo_m=4)
    c = r["ajustado"]["corte"]
    assert c["piezas_por_baston"] == 2 and c["modulo_m"] == 4.0
    assert c["traslape_m"] == pytest.approx(40 * 3 / 8 * 25.4 / 1000)  # 0.381 m en 3/8
    assert r["ajustado"]["bastones"] == 11 and r["ajustado"]["varillas"] == math.ceil(22 / 3)
    assert any("2 piezas" in a for a in r["avisos"])


def test_las_puntas_se_suman_al_largo() -> None:
    assert _calc(largo_cm=100, ganchos=0)["ajustado"]["corte"]["modulo_m"] == 1.0
    con_puntas = _calc(largo_cm=100, puntas_cm=50, ganchos=0)["ajustado"]["corte"]
    assert con_puntas["modulo_m"] == 1.5 and con_puntas["puntas_m"] == 0.5 and con_puntas["gancho_m"] == 0.0


@pytest.mark.parametrize(
    ("varilla", "cada_cm"), [(3, 11.43), (4, 15.24), (5, 19.05), (6, 22.86)]
)
def test_el_gancho_por_defecto_es_12_diametros_por_punta_y_2_ganchos(varilla: int, cada_cm: float) -> None:
    g = _calc(varilla_numero=varilla)["gancho"]
    assert g["ganchos"] == 2 and g["diametros"] == 12 and g["longitud_cm"] == pytest.approx(cada_cm, abs=1e-6)
    assert g["total_por_baston_cm"] == pytest.approx(2 * cada_cm, abs=1e-6) and "12 diámetros" in g["origen"]


def test_el_largo_capturado_incluye_los_ganchos_y_es_el_corte() -> None:
    # Se captura 122.86 cm: el corte es 1.2286 m (no cabe en el módulo de 1.00 m, se corta del de 1.50 m) y el tramo recto es
    # 122.86 − 2 × 11.43 = 100 cm.
    con = _calc(largo_cm=122.86)
    c = con["ajustado"]["corte"]
    assert c["necesario_m"] == pytest.approx(1.2286) and c["gancho_m"] == pytest.approx(0.2286) and c["recto_m"] == pytest.approx(1.0)
    assert c["modulo_m"] == 1.5 and c["piezas_por_varilla"] == 8
    assert con["parametros"]["recto_cm"] == pytest.approx(100.0)
    # Sin ganchos, el corte es el largo capturado y el tramo recto es el mismo.
    sin = _calc(largo_cm=122.86, ganchos=0)
    assert sin["ajustado"]["corte"]["necesario_m"] == pytest.approx(1.2286) and sin["parametros"]["recto_cm"] == pytest.approx(122.86)
    assert any("incluye los ganchos" in a and "de los cuales 22.86 cm son de ganchos" in a for a in con["avisos"])
    assert not any("incluye los ganchos" in a for a in sin["avisos"])


def test_el_escalon_se_nombra_por_el_tramo_recto_no_por_el_largo_capturado() -> None:
    # 142.86 cm capturados con 2 ganchos de 11.43 cm = recto de 120 cm: el escalón AUX-02010 (1.20 @25), exacto.
    r = _calc(largo_cm=142.86)
    assert r["escalon"] == "exacto" and r["concepto"]["clave"] == "AUX-02010" and r["concepto"]["largo_m"] == 1.2
    assert r["ajustado"]["corte"]["necesario_m"] == pytest.approx(1.4286)


def test_si_el_largo_capturado_no_alcanza_para_los_ganchos_avisa_y_no_hay_escalon() -> None:
    r = _calc(largo_cm=20)  # 2 × 11.43 = 22.86 cm de ganchos
    assert r["parametros"]["recto_cm"] == 0.0 and r["escalon"] == "sin_escalon"
    assert any("no alcanza para los ganchos" in a for a in r["avisos"])
    assert r["ajustado"]["corte"]["necesario_m"] == pytest.approx(0.2)


def test_el_corte_exacto_de_referencia_es_el_largo_capturado() -> None:
    r = _calc(trazo_m=10, varilla_numero=4, sep_cm=50, largo_cm=110.48)
    # 1.1048 m capturados (ya con los ganchos): floor(12 ÷ 1.1048) = 10 por varilla.
    assert r["exacto"]["material_m"] == pytest.approx(21 * 1.1048) and r["exacto"]["varillas"] == math.ceil(21 / 10)


def test_gancho_cm_capturado_manda_sobre_los_diametros_y_un_gancho_es_uno() -> None:
    g = _calc(gancho_cm=15, ganchos=1, gancho_diametros=20)["gancho"]
    assert g["longitud_cm"] == 15 and g["total_por_baston_cm"] == 15 and g["origen"] == "gancho_cm capturado"
    assert _calc(gancho_diametros=0)["ajustado"]["corte"]["gancho_m"] == 0.0


def test_el_gancho_aparece_en_los_parametros_del_desglose() -> None:
    p = _calc()["parametros"]
    assert p["ganchos"] == 2.0 and p["gancho_diametros"] == 12.0 and p["gancho_cm"] == pytest.approx(11.43)


def test_las_piezas_son_ceil_del_trazo_entre_la_separacion_mas_uno() -> None:
    assert _calc(trazo_m=1, sep_cm=25)["ajustado"]["bastones"] == 5
    assert _calc(trazo_m=1.01, sep_cm=25)["ajustado"]["bastones"] == 6
    assert _calc(trazo_m=0.1, sep_cm=25)["ajustado"]["bastones"] == 2


def test_el_escalon_exacto_del_catalogo_y_su_conciliacion() -> None:
    r = _calc(largo_cm=142.86)  # 1.20 m rectos @25 en 3/8 (más 2 ganchos de 11.43 cm incluidos en lo capturado)
    assert r["escalon"] == "exacto" and r["concepto"]["clave"] == "AUX-02010" and r["concepto"]["estado"] == "catalogo"
    (bloque,) = r["conciliacion"]
    varilla = next(f for f in bloque["filas"] if f["clave"] == "ACR-00001")
    assert varilla["catalogo"] == pytest.approx(0.432) and varilla["elemento"] == pytest.approx(0.5)
    assert varilla["marca"] == "≠"  # el módulo de 1.5 m gasta más que el 8 % del catálogo
    alambre = next(f for f in bloque["filas"] if f["clave"] == "ACE-00001")
    assert alambre["marca"] == "solo_catalogo" and alambre["elemento"] is None  # el alambre no se inventa
    assert bloque["mano_de_obra"] == []


def test_el_escalon_mayor_se_usa_y_avisa_y_el_concepto_nuevo_no_se_propone_solo() -> None:
    r = _calc(largo_cm=157.86, sep_cm=25)  # recto de 1.35 m
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
        concepto_nuevo_de(EntradaDeBaston(largo_cm=142.86))


def test_los_escalones_se_leen_del_csv_con_su_composicion() -> None:
    por_clave = {e[0]: e for e in ESCALONES_DE_CATALOGO}
    assert len(por_clave) == 28
    assert por_clave["AUX-02010"][1:5] == (1.2, 25, 0.432, 0.164724)
    assert por_clave["AUX-02072"][1:5] == (0.8, 50, 0.144, 0.049417)
    assert por_clave["AUX-02100"][1:5] == (4.0, 40, 0.9, 0.185315)
    assert escalon_para(3, 80, 50)["escalon"][0] == "AUX-02072"
    # El catálogo trae 8 % de desperdicio: 1.20 m a 25 cm = 4 bastones/m × 1.2 ÷ 12 × 1.08.
    assert pytest.approx(0.432) == 4 * 1.2 / 12 * 1.08


def test_confirmar_el_calculo_propone_una_version_con_el_antes_y_el_despues() -> None:
    (p,) = propuestas_de_actualizacion_de_apu(_calc(largo_cm=142.86))
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
        ({"ganchos": 3}, "ganchos por bastón"),
        ({"gancho_diametros": 50}, "diámetros"),
        ({"gancho_cm": 150}, "0 a 100 cm"),
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
    assert f["parametros_por_defecto"]["ganchos"] == 2 and f["parametros_por_defecto"]["gancho_diametros"] == 12.0
    with pytest.raises(ElementoDeBastonNoEncontrado):
        definicion_de("BA-9")
    sub = next(s for c in BIBLIOTECA if c["clave"] == "aceros" for s in c["subcategorias"])
    assert [e["clave"] for e in sub["elementos"]] == ["BA-1"] and sub["elementos"][0]["tipo"] == "baston"
    assert elemento_de_la_biblioteca("BA-1") is None  # su ficha es propia, como la del tabique
