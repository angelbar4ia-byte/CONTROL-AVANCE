"""El muro de cimentación con cotas de desplante (Fase 4b) y la losa de cimentación: altura de las cotas, volumen por la longitud, concepto del catálogo, uso «cimentación»."""

from __future__ import annotations

import pytest

from obractrl.domain.cuantificacion.cimiento import (
    CLAVE_DE_CIMIENTO,
    CONCEPTO_DE_CIMIENTO,
    EntradaCimiento,
    ErrorDeCimiento,
    calcular_cimiento,
    elemento_de_cimiento,
)
from obractrl.domain.cuantificacion.matriz_de_losa import (
    CONCEPTO_DE_LOSA_DE_CIMENTACION,
    CONCRETO_POR_USO,
    USOS_DE_LOSA,
    EntradaMatrizDeLosa,
    ErrorDeMatrizDeLosa,
    LosaDeEntrada,
    calcular_matriz_de_losa,
    concepto_nuevo_de_losa,
)
from obractrl.domain.cuantificacion.muro_cimentacion import (
    EntradaMuroDeCimentacion,
    calcular_muro_de_cimentacion,
)


def _cimiento(desplante: float = -0.8, corona: float = 0.0, longitud: float = 10.0, **kw: object) -> dict:
    return calcular_cimiento(EntradaCimiento(cota_desplante_m=desplante, cota_corona_m=corona, longitud_m=longitud, **kw))  # type: ignore[arg-type]


def test_la_altura_sale_de_las_cotas_y_el_volumen_es_el_del_muro_de_cimentacion_por_la_longitud() -> None:
    r = _cimiento(-0.8, 0.0, 10.0)
    assert r["cotas"] == {"desplante_m": -0.8, "corona_m": 0.0, "altura_m": pytest.approx(0.8)}
    por_metro = calcular_muro_de_cimentacion(EntradaMuroDeCimentacion(alto_m=0.8))["volumen"]["total_m3_ml"]
    assert r["volumen_m3_ml"] == pytest.approx(por_metro) and r["volumen_m3"] == pytest.approx(por_metro * 10)
    assert r["seccion"]["corona_m"] == 0.4 and r["seccion"]["base_m"] == pytest.approx(0.93)
    assert _cimiento(-1.2, 0.0, 5.0)["seccion"]["alto_m"] == pytest.approx(1.2)


def test_se_paga_con_el_concepto_existente_del_catalogo_por_m3() -> None:
    [c] = _cimiento()["conceptos"]
    assert c["concepto"] == {k: CONCEPTO_DE_CIMIENTO[k] for k in ("clave", "descripcion", "unidad", "estado", "provisional")}
    assert (c["concepto"]["clave"], c["concepto"]["estado"], c["unidad"]) == ("MCT-01011", "catalogo", "m3")
    assert c["cantidad"] == pytest.approx(_cimiento()["volumen_m3"])
    assert _cimiento()["mano_de_obra"]["estado"] == "sin_mano_de_obra"


def test_el_dentellon_y_las_caras_se_reutilizan_del_muro() -> None:
    sin = _cimiento(-2.5, 0.0)
    con = _cimiento(-2.5, 0.0, dentellon=True)
    assert con["dentellon"]["aplica"] is True and con["volumen_m3_ml"] - sin["volumen_m3_ml"] == pytest.approx(0.21)
    assert _cimiento(-1.0, 0.0, caras=2)["seccion"]["base_m"] > _cimiento(-1.0, 0.0, caras=1)["seccion"]["base_m"]
    assert any("dalas" in x["clave"] for x in sin["no_incluye"])


def test_la_escarpa_y_el_espacio_caen_en_un_solo_grupo() -> None:
    r = _cimiento(espacio_id="e1")
    assert [g["espacio_id"] for g in r["por_espacio"]] == ["e1"]
    assert r["por_espacio"][0]["conceptos"][0]["cantidad"] == pytest.approx(r["volumen_m3"])
    assert _cimiento()["por_espacio"][0]["espacio_id"] is None


def test_lo_que_no_vale_se_rechaza() -> None:
    with pytest.raises(ErrorDeCimiento, match="por encima"):
        _cimiento(0.0, -0.5)
    with pytest.raises(ErrorDeCimiento, match="por encima"):
        _cimiento(-0.5, -0.5)
    with pytest.raises(ErrorDeCimiento, match="altura"):
        _cimiento(-30.0, 0.0)
    with pytest.raises(ErrorDeCimiento, match="-30 a 100"):
        _cimiento(-40.0, 0.0)
    with pytest.raises(ErrorDeCimiento, match="longitud"):
        _cimiento(longitud=0.0)
    with pytest.raises(ErrorDeCimiento):
        _cimiento(caras=3)
    assert any("por encima del piso" in a for a in _cimiento(0.5, 1.5)["advertencias"])
    assert elemento_de_cimiento(CLAVE_DE_CIMIENTO) and not elemento_de_cimiento("ESC-FORJADA")


def test_la_losa_de_cimentacion_usa_el_concreto_td_200_y_la_malla_del_catalogo_sin_cimbra_por_m2() -> None:
    assert "cimentacion" in USOS_DE_LOSA and CONCRETO_POR_USO["cimentacion"] == "CON-00001"
    r = calcular_matriz_de_losa(EntradaMatrizDeLosa(tipo="maciza", uso="cimentacion", espesor_m=0.14, losas=[LosaDeEntrada(area_m2=100.0)]))
    assert r["concreto"]["clave"] == "CON-00001" and r["concreto"]["geometrico_m3"] == pytest.approx(14.0)
    por_clave = {f["clave"]: f["cantidad"] for f in r["insumos"]}
    assert "MAD-00001" not in por_clave and r["cimbra"]["m2"] == 0
    assert por_clave["ACE-00018"] == pytest.approx(1.1494) and por_clave["ACE-00001"] == pytest.approx(5.0829)
    assert r["parrilla"]["clave"] == "AUX-00030"
    [losa] = [c for c in r["conceptos"] if c["parte"] == "losa"]
    assert losa["concepto"]["clave"] == "EJ-802" == CONCEPTO_DE_LOSA_DE_CIMENTACION["clave"]
    assert (losa["concepto"]["estado"], losa["concepto"]["provisional"], losa["toma"]) == ("propuesto", True, ["concreto", "acero"])
    assert any("no se calcula cimbra por m²" in a for a in r["advertencias"])
    # Entrepiso y azotea siguen igual: con cimbra y la parrilla AUX-06010.
    e = calcular_matriz_de_losa(EntradaMatrizDeLosa(tipo="maciza", espesor_m=0.12, losas=[LosaDeEntrada(area_m2=100.0)]))
    assert e["cimbra"]["m2"] == 100 and e["parrilla"]["clave"] == "AUX-06010"


def test_la_losa_de_cimentacion_es_maciza_y_su_concepto_se_propone_con_clave_provisional() -> None:
    with pytest.raises(ErrorDeMatrizDeLosa, match="maciza"):
        calcular_matriz_de_losa(EntradaMatrizDeLosa(tipo="nervada", uso="cimentacion", espesor_m=0.2, losas=[LosaDeEntrada(area_m2=10.0)]))  # type: ignore[arg-type]
    with pytest.raises(ErrorDeMatrizDeLosa, match="maciza"):
        concepto_nuevo_de_losa("nervada", "cimentacion")
    p = concepto_nuevo_de_losa("maciza", "cimentacion")
    assert (p["elemento_clave"], p["concepto_clave"], p["clase"]) == ("LOSA-MACIZA", "EJ-802", "concepto_nuevo")
    assert p["detalle"]["toma"]["cimbra"] is False and "CON-00001" in p["detalle"]["insumos"] and "MAD-00001" not in p["detalle"]["insumos"]
    assert concepto_nuevo_de_losa("maciza")["concepto_clave"] == "EJ-800"


def test_c1_la_corona_por_defecto_es_el_arranque_de_la_cadena_de_desplante() -> None:
    from obractrl.domain.cuantificacion.cimiento import (
        PERALTE_DE_LA_CADENA_DE_DESPLANTE_M,
        corona_por_defecto,
    )

    assert pytest.approx(0.20) == PERALTE_DE_LA_CADENA_DE_DESPLANTE_M  # el peralte de BAP-03010
    assert corona_por_defecto(0.0) == pytest.approx(-0.20) and corona_por_defecto(2.5) == pytest.approx(2.30)
    # Una cota tecleada manda: teclear el piso reproduce el criterio anterior (altura 0.80), el defecto da 0.60.
    assert _cimiento(-0.8, 0.0)["cotas"]["altura_m"] == pytest.approx(0.8)
    assert _cimiento(-0.8, corona_por_defecto(0.0))["cotas"]["altura_m"] == pytest.approx(0.6)
    assert not any(p["clave"] == "C1" for p in _cimiento()["pendientes"])
