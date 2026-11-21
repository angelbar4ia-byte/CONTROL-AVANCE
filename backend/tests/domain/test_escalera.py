"""La escalera como elemento (Fase 4a): peldaños desde el desnivel, huella y contrahuella, rampas y descanso, conceptos y lo que no se cuenta dos veces."""

from __future__ import annotations

import math

import pytest

from obractrl.domain.cuantificacion.biblioteca_de_elementos import (
    BIBLIOTECA,
    elemento_de_la_biblioteca,
)
from obractrl.domain.cuantificacion.escalera import (
    CLAVE_DE_ESCALERA,
    COMPOSICION_DEL_ESCALON,
    CONCEPTO_DE_DESCANSO,
    CONCEPTO_DE_ESCALON,
    DEFECTOS,
    PARRILLA_POR_M2,
    EntradaEscalera,
    ErrorDeEscalera,
    calcular_escalera,
    categorias_de_biblioteca,
    concepto_nuevo_de_descanso,
    definicion_de_escalera,
    elemento_de_escalera,
    solapes_de_escaleras,
    validar_parametros,
)


def _escalera(arranque: float = 0.0, llegada: float = 3.12, **kw: object) -> dict:
    return calcular_escalera(EntradaEscalera(cota_arranque_m=arranque, cota_llegada_m=llegada, **kw))  # type: ignore[arg-type]


def test_los_peldanos_salen_del_desnivel_y_reproducen_los_de_la_hoja_de_oro() -> None:
    # 3.00 m de altura libre y 12 cm de losa: 3.12 m = 18 peldaños; la segunda planta (4.20 − 3.12 = 1.08 m) = 6. Son los 18 + 6 de la hoja ESCALERA de Oro.
    pb = _escalera(0.0, 3.12)["geometria"]
    pa = _escalera(3.12, 4.20)["geometria"]
    assert (pb["peldanos"], pb["origen_de_peldanos"]) == (18, "desnivel")
    assert pa["peldanos"] == 6
    assert pb["contrahuella_m"] == pytest.approx(3.12 / 18) and pa["contrahuella_m"] == pytest.approx(0.18)
    assert pb["contrahuella_m"] <= DEFECTOS["contrahuella_max_m"]


def test_el_catalogo_cuenta_la_pieza_como_un_escalon_de_1_20_y_la_cantidad_escala_con_el_ancho() -> None:
    r = _escalera()
    [c] = r["conceptos"]
    # F7: se liga a un concepto que YA existe en el catálogo; no hay concepto nuevo para el escalón.
    assert c["concepto"] == {k: CONCEPTO_DE_ESCALON[k] for k in ("clave", "descripcion", "unidad", "estado", "provisional")}
    assert (c["concepto"]["clave"], c["unidad"], c["cantidad"]) == ("EST-01510", "pza", pytest.approx(18.0))
    ancho_doble = _escalera(ancho_m=2.4)["conceptos"][0]
    assert ancho_doble["cantidad"] == pytest.approx(36.0)
    fraccionaria = _escalera(ancho_m=0.9)
    assert fraccionaria["conceptos"][0]["cantidad"] == pytest.approx(13.5) and any("múltiplo de 1.20" in a for a in fraccionaria["advertencias"])
    assert r["mano_de_obra"]["estado"] == "sin_mano_de_obra" and [d["clave"] for d in r["mano_de_obra"]["destajos_candidatos"]] == ["MOE-02311", "MOE-02312"]


def test_el_concreto_y_el_acero_salen_de_la_geometria_y_de_la_parrilla_del_catalogo() -> None:
    r = _escalera()
    g = r["geometria"]
    inclinada = math.hypot(0.25, 3.12 / 18)
    assert g["longitud_inclinada_m"] == pytest.approx(inclinada)
    assert g["superficie_de_rampa_m2"] == pytest.approx(18 * inclinada * 1.2)
    por_clave = {i["clave"]: i for i in r["insumos"] if i["parte"] == "rampa"}
    assert por_clave["CON-00004"]["cantidad"] == pytest.approx(g["superficie_de_rampa_m2"] * 0.12)
    for clave, _desc, _u, por_m2, _f in PARRILLA_POR_M2:
        assert por_clave[clave]["cantidad"] == pytest.approx(g["superficie_de_rampa_m2"] * por_m2)
    # Lo que el catálogo trae y el elemento no calcula (tabique, mezcla, cimbraplay) no está entre los insumos: la conciliación lo marca «solo en el catálogo».
    assert {"PET-00001", "MEZ-07010", "MAD-00003"}.isdisjoint(por_clave)
    assert {c[0] for c in COMPOSICION_DEL_ESCALON} >= {"PET-00001", "MEZ-07010", "MAD-00003", "CON-00004", "ACR-00001", "ACE-00001"}
    assert r["advertencias"] == []


def test_con_varias_rampas_hay_descansos_con_un_concepto_nuevo_propuesto() -> None:
    r = _escalera(rampas=2)
    g = r["geometria"]
    assert g["descansos"] == 1 and g["area_de_descanso_m2"] == pytest.approx(1.2 * 1.2)  # cuadrado por omisión
    assert [x["peldanos"] for x in g["rampas"]] == [9, 9] and g["recorrido_horizontal_m"] == pytest.approx((18 - 2) * 0.25)
    assert sum(x["altura_m"] for x in g["rampas"]) == pytest.approx(3.12)
    escalon, descanso = r["conceptos"]
    assert escalon["concepto"]["clave"] == "EST-01510"
    assert descanso["concepto"] == {k: CONCEPTO_DE_DESCANSO[k] for k in ("clave", "descripcion", "unidad", "estado", "provisional")}
    assert (descanso["concepto"]["clave"], descanso["concepto"]["estado"], descanso["concepto"]["provisional"]) == ("EJ-820", "propuesto", True)
    assert descanso["cantidad"] == pytest.approx(1.44) and descanso["unidad"] == "m²"
    de_descanso = {i["clave"]: i["cantidad"] for i in r["insumos"] if i["parte"] == "descanso"}
    assert de_descanso["CON-00004"] == pytest.approx(1.44 * 0.12) and de_descanso["MAD-00001"] == pytest.approx(1.44) and de_descanso["ACR-00001"] == pytest.approx(1.44 * 0.9)
    # El descanso con otro largo; con una sola rampa no hay descanso y teclear su largo avisa.
    assert _escalera(rampas=2, largo_descanso_m=2.0)["geometria"]["area_de_descanso_m2"] == pytest.approx(2.4)
    una = _escalera(largo_descanso_m=2.0)
    assert len(una["conceptos"]) == 1 and any("no hay descanso" in a for a in una["advertencias"])
    # Los peldaños sobrantes caen en las primeras rampas.
    assert [x["peldanos"] for x in _escalera(arranque=0.0, llegada=3.0, rampas=2)["geometria"]["rampas"]] == [9, 8]


def test_la_huella_sale_de_la_linea_del_plano_y_se_valida() -> None:
    # 18 peldaños en una rampa tienen 17 huellas: una línea de 4.25 m da la huella de 25 cm.
    r = _escalera(recorrido_m=4.25)
    assert r["geometria"]["huella_m"] == pytest.approx(0.25) and r["geometria"]["origen_de_huella"] == "linea"
    mas_larga = _escalera(recorrido_m=5.1)["geometria"]
    assert mas_larga["huella_m"] == pytest.approx(0.30) and mas_larga["recorrido_horizontal_m"] == pytest.approx(5.1)
    assert _escalera(huella_m=0.30)["geometria"]["origen_de_huella"] == "tecleada"
    # Una línea corta da una huella que no vale (< 15 cm): se rechaza con el motivo.
    with pytest.raises(ErrorDeEscalera, match="huella"):
        _escalera(recorrido_m=1.0)
    with pytest.raises(ErrorDeEscalera, match="no tiene largo"):
        _escalera(recorrido_m=0.0)


def test_los_peldanos_tecleados_mandan_y_la_contrahuella_alta_avisa() -> None:
    r = _escalera(peldanos=15)
    assert r["geometria"]["origen_de_peldanos"] == "tecleados" and r["geometria"]["contrahuella_m"] == pytest.approx(3.12 / 15)
    assert any("pasa de la máxima" in a for a in r["advertencias"])
    assert any("menor que la de referencia" in a for a in _escalera(huella_m=0.20)["advertencias"])


def test_lo_que_no_vale_se_rechaza() -> None:
    with pytest.raises(ErrorDeEscalera, match="sube"):
        _escalera(3.0, 3.0)
    with pytest.raises(ErrorDeEscalera, match="sube"):
        _escalera(3.12, 0.0)
    with pytest.raises(ErrorDeEscalera, match="desnivel"):
        _escalera(0.0, 20.0)
    with pytest.raises(ErrorDeEscalera, match="-30 a 100"):
        _escalera(0.0, 120.0)
    for mal in ({"ancho_m": 0.1}, {"espesor_m": 0.9}, {"contrahuella_max_m": 0.5}, {"huella_m": 0.05}, {"rampas": 5}, {"rampas": 0}, {"peldanos": 1}, {"largo_descanso_m": 0.1}):
        with pytest.raises(ErrorDeEscalera):
            _escalera(**mal)
    with pytest.raises(ErrorDeEscalera, match="al menos 2 peldaños"):
        _escalera(peldanos=3, rampas=2)
    with pytest.raises(ErrorDeEscalera, match="al menos"):
        _escalera(0.0, 0.3, rampas=2)  # 2 peldaños no alcanzan para 2 rampas
    with pytest.raises(ErrorDeEscalera, match="máximo es 120"):
        _escalera(0.0, 14.0, contrahuella_max_m=0.10)


def test_los_parametros_validados_traen_los_de_omision() -> None:
    assert validar_parametros({}) == DEFECTOS
    p = validar_parametros({"ancho_m": 1.5, "rampas": 2, "huella_m": None})
    assert (p["ancho_m"], p["rampas"], p["huella_m"], p["peldanos"], p["largo_descanso_m"]) == (1.5, 2, 0.25, None, None)


def test_una_linea_no_sirve_a_dos_escaleras() -> None:
    assert solapes_de_escaleras([{"id": 1, "trazo_id": "a"}, {"id": 2, "trazo_id": "b"}, {"id": 3, "trazo_id": None}, {"id": 4, "trazo_id": None}]) == []
    [motivo] = solapes_de_escaleras([{"id": 1, "trazo_id": "a"}, {"id": 2, "trazo_id": "a"}])
    assert "misma línea" in motivo


def test_la_escalera_asignada_a_un_espacio_cae_en_un_solo_grupo_y_suma_el_total() -> None:
    r = _escalera(rampas=2, espacio_id="esc")
    [g] = r["por_espacio"]
    assert g["espacio_id"] == "esc"
    assert {c["concepto"]["clave"]: c["cantidad"] for c in g["conceptos"]} == {c["concepto"]["clave"]: c["cantidad"] for c in r["conceptos"]}
    assert _escalera()["por_espacio"][0]["espacio_id"] is None


def test_la_biblioteca_trae_la_categoria_escaleras_y_su_ficha() -> None:
    [cat] = categorias_de_biblioteca()
    assert cat["clave"] == "escaleras" and cat["nombre"] == "Escaleras"
    [elemento] = cat["subcategorias"][0]["elementos"]
    assert (elemento["clave"], elemento["tipo"], elemento["concepto"]["clave"], elemento["concepto"]["unidad"]) == (CLAVE_DE_ESCALERA, "escalera", "EST-01510", "pza")
    assert any(c["clave"] == "escaleras" for c in BIBLIOTECA)
    # No es un elemento paramétrico de los de colocar en un muro: la biblioteca no lo devuelve como tal.
    assert elemento_de_la_biblioteca(CLAVE_DE_ESCALERA) is None
    assert elemento_de_escalera("ESC-FORJADA") and not elemento_de_escalera("REL-AZOTEA")
    d = definicion_de_escalera("ESC-FORJADA")
    assert d is not None and d["concepto"]["estado"] == "catalogo" and d["concepto_del_descanso"]["clave"] == "EJ-820"
    assert {p["clave"] for p in d["pendientes"]} >= {"E1", "E2", "E3", "E4", "E5"} and d["largo_base_del_escalon_m"] == 1.2
    assert definicion_de_escalera("OTRA") is None


def test_el_concepto_nuevo_del_descanso_es_propuesto_con_clave_provisional_y_sin_precio() -> None:
    p = concepto_nuevo_de_descanso()
    assert (p["elemento_clave"], p["concepto_clave"], p["clase"]) == ("ESC-FORJADA", "EJ-820", "concepto_nuevo")
    d = p["detalle"]
    assert d["clave_provisional"] is True and d["unidad"] == "m²" and d["insumos"]["CON-00004"] == pytest.approx(0.12)
    assert any("F7" in m for m in d["motivos"]) and "precio" not in " ".join(d["motivos"]).replace("Sin precio", "")
