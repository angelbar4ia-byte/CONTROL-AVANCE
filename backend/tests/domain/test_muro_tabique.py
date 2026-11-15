"""Muros de tabique, aparejos y piso de petatillo: cálculo, concepto por nivel, conciliación y propuestas (Ola 3, 3C).

Los números del catálogo salen de `ANALISIS_DE_BASICOS_CONCEPTOS.csv` (opus); `scripts/verificar_tabique_contra_csv.py` los compara
con el CSV cuando se corre a mano.
"""

from __future__ import annotations

import pytest

from obractrl.domain.cuantificacion.biblioteca_de_elementos import (
    BIBLIOTECA,
    elemento_de_la_biblioteca,
)
from obractrl.domain.cuantificacion.muro_tabique import (
    ELEMENTOS_DE_TABIQUE,
    ElementoDeTabiqueNoEncontrado,
    EntradaMuroDeTabique,
    ErrorDeMuroDeTabique,
    calcular_muro_de_tabique,
    concepto_nuevo_de,
    definicion_de,
    propuestas_de_actualizacion_de_apu,
    tabla_de_revision,
)


def _calc(clave: str, **kw: object) -> dict:
    return calcular_muro_de_tabique(clave, EntradaMuroDeTabique(**kw))  # type: ignore[arg-type]


# --- La pieza 14×6×26 con junta de 2 cm --------------------------------------------------------------------------------------


def test_el_muro_de_14_cm_coincide_con_el_catalogo_con_12_y_5_por_ciento() -> None:
    r = _calc("EST-02010")
    assert r["piezas"]["netas_por_unidad"] == pytest.approx(44.6428571)
    assert r["piezas"]["por_unidad"] == pytest.approx(50.0)  # 50 pza del catálogo
    assert r["mezcla"]["neta_por_unidad"] == pytest.approx(0.0425)
    assert r["mezcla"]["por_unidad"] == pytest.approx(0.044625)  # 0.0447 del catálogo
    assert r["geometria"]["espesor_real_cm"] == pytest.approx(14.0)
    (bloque, tercer) = r["conciliacion"]
    assert {f["clave"]: f["marca"] for f in bloque["filas"]} == {"PET-00001": "=", "MEZ-07010": "="}
    assert tercer["concepto"]["clave"] == "EST-02011"
    assert [m["clave"] for m in bloque["mano_de_obra"]] == ["MOE-02010"]


@pytest.mark.parametrize(
    ("clave", "esp", "pza", "mezcla", "unidad"),
    [
        ("EST-02005", 6.0, 25.0, 0.0118125, "m²"),
        ("EST-02030", 26.0, 87.5, 0.0938438, "m²"),
        ("EST-02040", 42.0, 137.5, 0.1594688, "m²"),
        ("EST-02050", 6.0, 7.0, 0.0033075, "ml"),
        ("ACA-02090", 6.0, 25.0, 0.0118125, "m²"),
    ],
)
def test_los_aparejos_nuevos_dan_los_numeros_de_la_tabla_del_mockup(clave: str, esp: float, pza: float, mezcla: float, unidad: str) -> None:
    r = _calc(clave)
    assert r["geometria"]["espesor_real_cm"] == pytest.approx(esp)
    assert r["piezas"]["por_unidad"] == pytest.approx(pza, abs=0.05)
    assert r["mezcla"]["por_unidad"] == pytest.approx(mezcla, abs=5e-5)
    assert r["unidad"] == unidad
    assert r["concepto"]["estado"] == "propuesto" and r["concepto"]["clave_provisional"] is True
    assert r["conciliacion"] == []  # el catálogo no los trae
    assert r["mano_de_obra"]["estado"] == "sin_destajo" and r["mano_de_obra"]["destajo"] is None


def test_el_sardinel_es_por_ml_de_una_hilada_y_el_tipo_es_un_parametro() -> None:
    r = _calc("EST-02050", cantidad=10)
    assert r["medida"] == "ml"
    assert r["piezas"]["por_unidad"] == pytest.approx(1 / 0.16 * 1.12)  # una pieza de 14 + 2 cm por hilada
    assert r["piezas"]["total"] == pytest.approx(70.0) and r["piezas"]["a_comprar"] == 70
    assert r["parametros"]["tipo_de_sardinel"] == "parado"
    assert definicion_de("EST-02050")["tipos_de_sardinel"][0]["clave"] == "parado"
    with pytest.raises(ErrorDeMuroDeTabique, match="no está definido"):
        _calc("EST-02050", tipo_de_sardinel="de lujo")
    with pytest.raises(ErrorDeMuroDeTabique, match="Solo el sardinel"):
        _calc("EST-02010", tipo_de_sardinel="parado")


def test_el_petatillo_lleva_cama_en_cero_editable_sin_mortero_inventado() -> None:
    base = _calc("ACA-02090")
    assert base["parametros"]["cama_cm"] == 0.0
    assert any("0 cm" in a for a in base["avisos"])
    con_cama = _calc("ACA-02090", cama_cm=2)
    assert con_cama["parametros"]["cama_cm"] == 2.0
    assert con_cama["mezcla"]["neta_por_unidad"] == pytest.approx(base["mezcla"]["neta_por_unidad"] + 0.02)
    with pytest.raises(ErrorDeMuroDeTabique, match="petatillo"):
        _calc("EST-02010", cama_cm=2)


def test_sin_el_driver_de_5_por_ciento_el_desperdicio_es_solo_el_del_elemento() -> None:
    sin = _calc("EST-02010", desperdicio_de_pieza_pct=0, desperdicio_de_mezcla_pct=0)
    assert sin["piezas"]["por_unidad"] == pytest.approx(44.6428571)
    assert sin["mezcla"]["por_unidad"] == pytest.approx(0.0425)
    ancha = _calc("EST-02010", junta_cm=3)
    assert ancha["piezas"]["por_unidad"] < _calc("EST-02010")["piezas"]["por_unidad"]


# --- El muro de 21 cm: 14 + 1 + 6 ---------------------------------------------------------------------------------------------


def test_el_muro_de_21_cm_es_tabique_de_14_junta_de_1_y_tabique_de_6() -> None:
    r = _calc("EST-02020")
    g = r["geometria"]
    assert g["espesor_real_cm"] == pytest.approx(21.0)
    (hilada,) = g["hiladas"]
    assert [f["orientacion"] for f in hilada["filas"]] == ["soga", "canto"]
    assert [f["espesor_cm"] for f in hilada["filas"]] == [14.0, 6.0]
    assert r["parametros"]["junta_entre_hileras_cm"] == 1.0 and r["parametros"]["junta_cm"] == 2.0
    # soga: 1 / (0.28 × 0.08) = 44.64; canto (14 cm de alto): 1 / (0.28 × 0.16) = 22.32
    assert r["piezas"]["netas_por_unidad"] == pytest.approx(44.6428571 + 22.3214286)
    assert r["piezas"]["por_unidad"] == pytest.approx(75.0)
    # mezcla neta: 0.21 de espesor − el volumen de las piezas por m²
    assert r["mezcla"]["neta_por_unidad"] == pytest.approx(0.21 - 66.9642857 * 0.14 * 0.06 * 0.26)
    assert r["mezcla"]["por_unidad"] == pytest.approx(0.06694, abs=1e-5)
    assert r["concepto"]["clave"] == "EST-02020" and r["concepto"]["nivel_desde"] is None


def test_el_21_muestra_la_diferencia_contra_el_catalogo_sin_editarlo() -> None:
    (bloque,) = _calc("EST-02020")["conciliacion"]
    filas = {f["clave"]: f for f in bloque["filas"]}
    assert filas["PET-00001"]["catalogo"] == 86.0 and filas["MEZ-07010"]["catalogo"] == pytest.approx(0.0939)
    assert filas["PET-00001"]["marca"] == "≠" and filas["PET-00001"]["diferencia_pct"] == pytest.approx(-12.79, abs=0.01)
    assert filas["MEZ-07010"]["marca"] == "≠" and filas["MEZ-07010"]["diferencia_pct"] == pytest.approx(-28.7, abs=0.1)
    assert bloque["mano_de_obra"][0]["clave"] == "MOE-02013"
    assert any("86 pza" in a for a in _calc("EST-02020")["avisos"])


def test_la_junta_entre_hileras_se_puede_cambiar() -> None:
    assert _calc("EST-02020", junta_entre_hileras_cm=2)["geometria"]["espesor_real_cm"] == pytest.approx(22.0)


# --- Concepto por nivel (2A) ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("nivel", "clave", "destajo"), [(1, "EST-02010", "MOE-02010"), (2, "EST-02010", "MOE-02010"), (3, "EST-02011", "MOE-02012"), (4, "EST-02011", "MOE-02012")])
def test_nivel_3_en_adelante_paga_est_02011(nivel: int, clave: str, destajo: str) -> None:
    r = _calc("EST-02010", nivel=nivel)
    assert r["concepto"]["clave"] == clave
    assert r["mano_de_obra"]["destajo"]["clave"] == destajo


def test_la_regla_del_tercer_nivel_es_configurable_y_sin_nivel_avisa() -> None:
    assert _calc("EST-02010", nivel=3, nivel_desde_3er_nivel=4)["concepto"]["clave"] == "EST-02010"
    r = _calc("EST-02010")
    assert r["concepto"]["clave"] == "EST-02010" and any("nivel" in a for a in r["avisos"])
    assert _calc("EST-02020", nivel=5)["concepto"]["clave"] == "EST-02020"  # Q98: sin variante de 3.er nivel


def test_aux_04010_no_lleva_destajo_y_avisa_la_diferencia_de_mortero() -> None:
    r = _calc("AUX-04010")
    assert r["mano_de_obra"]["estado"] == "sin_destajo" and r["concepto"]["estado"] == "catalogo"
    assert any("1:5" in a and "1:4" in a for a in r["avisos"])
    assert definicion_de("AUX-04010")["avisos_de_catalogo"]
    (bloque,) = r["conciliacion"]
    assert {f["marca"] for f in bloque["filas"]} == {"="}


# --- Validación y herramienta ---------------------------------------------------------------------------------------------------


def test_los_datos_que_no_valen_se_rechazan() -> None:
    for kw in ({"cantidad": 0}, {"junta_cm": -1}, {"junta_cm": 11}, {"desperdicio_de_pieza_pct": 101}, {"pieza_largo_cm": 0.5}, {"nivel": 0}):
        with pytest.raises(ErrorDeMuroDeTabique):
            _calc("EST-02010", **kw)
    with pytest.raises(ElementoDeTabiqueNoEncontrado):
        calcular_muro_de_tabique("EST-99999")


def test_la_herramienta_y_equipo_es_opcional_vacia_y_sin_precios() -> None:
    assert _calc("EST-02010")["herramienta"] == []
    r = _calc("EST-02010", cantidad=20, herramienta=(("ANDAMIO (renta por jornada)", "jornal", 0.05),))
    assert r["herramienta"] == [{"descripcion": "ANDAMIO (renta por jornada)", "unidad": "jornal", "por_unidad": 0.05, "total": 1.0}]
    assert "precio" not in str(r["herramienta"]).lower()
    with pytest.raises(ErrorDeMuroDeTabique):
        _calc("EST-02010", herramienta=(("", "jornal", 1.0),))


def test_la_mezcla_se_abre_en_cemento_arena_y_pipa() -> None:
    r = _calc("EST-02010", cantidad=100)
    total = r["mezcla"]["total_m3"]
    assert {c["clave"] for c in r["mezcla_compuesta"]} == {"ADH-00005", "PET-00015", "SER-00003"}
    assert next(c for c in r["mezcla_compuesta"] if c["clave"] == "ADH-00005")["total"] == pytest.approx(7.28 * total)


# --- Biblioteca, tabla de revisión y propuestas -----------------------------------------------------------------------------------


def test_la_biblioteca_trae_muros_de_tabique_y_pisos_de_petatillo() -> None:
    cats = {c["clave"]: c for c in BIBLIOTECA}
    muros = cats["muros"]["subcategorias"][0]
    assert muros["nombre"] == "Muros de tabique"
    assert [e["clave"] for e in muros["elementos"]] == ["EST-02005", "EST-02010", "EST-02020", "EST-02030", "EST-02040", "EST-02050", "AUX-04010"]
    pisos = cats["pisos"]["subcategorias"][0]
    assert pisos["nombre"] == "Pisos de petatillo (tabique)" and [e["clave"] for e in pisos["elementos"]] == ["ACA-02090"]
    assert all(e["tipo"] == "tabique" for e in muros["elementos"])
    assert elemento_de_la_biblioteca("EST-02010") is None  # su ficha es /tabique/…
    assert "MCT-01010" in str(BIBLIOTECA)  # no pierde lo que ya traía


def test_la_tabla_de_revision_trae_lo_que_el_usuario_pidio() -> None:
    filas = {f["clave"]: f for f in tabla_de_revision()}
    assert set(filas) == set(ELEMENTOS_DE_TABIQUE)
    for k in ("EST-02005", "EST-02030", "EST-02040", "EST-02050", "ACA-02090"):
        assert filas[k]["provisional"] is True and filas[k]["estado"] == "propuesto"
    for k in ("EST-02010", "EST-02020", "AUX-04010"):
        assert filas[k]["provisional"] is False
    assert filas["EST-02005"]["nombre_nominal"] == "Muro capuchino de 7 cm" and filas["EST-02005"]["espesor_real_cm"] == pytest.approx(6.0)
    assert "≠" in filas["EST-02020"]["contraste"] and "86 pza" in filas["EST-02020"]["contraste"]
    assert filas["EST-02010"]["contraste"].count("=") >= 2


def test_los_aparejos_nuevos_nacen_como_concepto_nuevo_provisional_sin_destajo_ni_precio() -> None:
    p = concepto_nuevo_de("EST-02030")
    assert p["clase"] == "concepto_nuevo" and p["concepto_clave"] == "EST-02030"
    assert p["detalle"]["clave_provisional"] is True and p["detalle"]["cambios"] == []
    assert p["detalle"]["insumos"]["PET-00001"] == pytest.approx(87.5)
    assert "destajo" not in p["detalle"] and "precio" in p["resumen"]
    with pytest.raises(ErrorDeMuroDeTabique, match="ya está en el catálogo"):
        concepto_nuevo_de("EST-02010")


def test_confirmar_el_calculo_propone_una_version_solo_donde_hay_diferencia() -> None:
    assert propuestas_de_actualizacion_de_apu(_calc("EST-02010")) == []  # = y =: nada que proponer
    (p,) = propuestas_de_actualizacion_de_apu(_calc("EST-02020"))
    assert p["clase"] == "version_de_concepto" and p["concepto_clave"] == "EST-02020"
    cambios = {c["insumo"]: c for c in p["detalle"]["cambios"]}
    assert cambios["PET-00001"]["antes"] == 86.0 and cambios["PET-00001"]["despues"] == pytest.approx(75.0)
    assert cambios["MEZ-07010"]["antes"] == pytest.approx(0.0939)
    assert not propuestas_de_actualizacion_de_apu(_calc("EST-02005"))
    # con otra junta el 14 cm también se aparta del catálogo y se propone en sus dos conceptos
    claves = {x["concepto_clave"] for x in propuestas_de_actualizacion_de_apu(_calc("EST-02010", junta_cm=1))}
    assert claves == {"EST-02010", "EST-02011"}


def test_cada_elemento_trae_su_ficha() -> None:
    for clave in ELEMENTOS_DE_TABIQUE:
        d = definicion_de(clave)
        assert d["pieza"] == {"insumo": "PET-00001", "ancho_cm": 14.0, "alto_cm": 6.0, "largo_cm": 26.0}
        assert d["pendientes"] and d["conceptos"] and d["hiladas"]
    assert definicion_de("ACA-02090")["categoria"] == {"clave": "pisos", "nombre": "Pisos"}
