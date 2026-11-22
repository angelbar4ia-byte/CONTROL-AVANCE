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
    GIROS_DE_DESCANSO,
    PARRILLA_POR_M2,
    RADIO_DE_HUELLA_M,
    AbanicoDeEscalera,
    DescansoDeEscalera,
    EntradaEscalera,
    ErrorDeEscalera,
    calcular_escalera,
    categorias_de_biblioteca,
    concepto_nuevo_de_descanso,
    definicion_de_escalera,
    elemento_de_escalera,
    solapes_de_escaleras,
    validar_abanico,
    validar_descanso,
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


# ── Descansos propios (Fase 4d) ─────────────────────────────────────────────────────────────────────


def test_sin_descansos_propios_la_escalera_calcula_igual_que_en_4a() -> None:
    # Aditivo: sin filas nuevas, el descanso implícito (ancho × largo del descanso) y todos los números de siempre.
    base = _escalera(rampas=3, largo_descanso_m=1.5)
    g = base["geometria"]
    assert g["descansos"] == 2 and g["area_de_descanso_m2"] == pytest.approx(2 * 1.2 * 1.5) and g["peldanos"] == g["peldanos_rectos"] == 18 and g["peldanos_de_abanico"] == 0
    assert [(d["posicion"], d["origen"], d["giro_grados"]) for d in g["descansos_detalle"]] == [(1, "implicito", None), (2, "implicito", None)]
    assert g["abanicos"] == [] and g["area_de_abanico_m2"] == 0 and g["escalones_de_catalogo"] == pytest.approx(18.0)
    assert [c["concepto"]["clave"] for c in base["conceptos"]] == ["EST-01510", "EJ-820"] and {i["parte"] for i in base["insumos"]} == {"rampa", "descanso"}


def test_un_descanso_propio_trae_sus_medidas_su_espesor_y_su_giro_y_las_demas_posiciones_conservan_el_implicito() -> None:
    r = _escalera(rampas=3, descansos=(DescansoDeEscalera(posicion=2, giro_grados=180, largo_m=1.4, ancho_m=2.6, espesor_m=0.15),))
    g = r["geometria"]
    d1, d2 = g["descansos_detalle"]
    assert (d1["posicion"], d1["origen"], d1["area_m2"]) == (1, "implicito", pytest.approx(1.44))
    assert (d2["posicion"], d2["origen"], d2["giro_grados"], d2["area_m2"], d2["espesor_m"]) == (2, "dimensiones", 180, pytest.approx(1.4 * 2.6), 0.15)
    assert g["area_de_descanso_m2"] == pytest.approx(1.44 + 1.4 * 2.6)
    # Cada descanso lleva su espesor: el concreto es la suma de los volúmenes, la cimbra y el acero van por m².
    assert g["volumen_de_descanso_m3"] == pytest.approx(1.44 * 0.12 + 1.4 * 2.6 * 0.15)
    de_descanso = {i["clave"]: i["cantidad"] for i in r["insumos"] if i["parte"] == "descanso"}
    assert de_descanso["CON-00004"] == pytest.approx(g["volumen_de_descanso_m3"]) and de_descanso["MAD-00001"] == pytest.approx(g["area_de_descanso_m2"])
    # Una escalera, un concepto: EJ-820 junta las áreas (sin doble conteo con la rampa).
    [escalon, descanso] = r["conceptos"]
    assert descanso["concepto"]["clave"] == "EJ-820" and descanso["cantidad"] == pytest.approx(g["area_de_descanso_m2"]) and "1 con medidas propias" in descanso["nota"]
    assert escalon["cantidad"] == pytest.approx(18.0)


def test_las_medidas_de_un_descanso_toman_su_omision_segun_el_giro() -> None:
    for giro, ancho_esperado in ((0, 1.2), (90, 1.2), (180, 2.4)):
        [d] = _escalera(rampas=2, descansos=(DescansoDeEscalera(posicion=1, giro_grados=giro),))["geometria"]["descansos_detalle"]
        assert (d["largo_m"], d["ancho_m"], d["espesor_m"]) == (pytest.approx(1.2), pytest.approx(ancho_esperado), 0.12), giro
    # El largo de la escalera (largo_descanso_m) también manda sobre la omisión del descanso propio.
    [d] = _escalera(rampas=2, largo_descanso_m=1.5, descansos=(DescansoDeEscalera(posicion=1),))["geometria"]["descansos_detalle"]
    assert d["largo_m"] == pytest.approx(1.5) and d["area_m2"] == pytest.approx(1.5 * 1.2)
    assert GIROS_DE_DESCANSO == (0, 90, 180)


def test_el_area_de_un_poligono_del_plano_manda_sobre_largo_por_ancho() -> None:
    r = _escalera(rampas=2, descansos=(DescansoDeEscalera(posicion=1, giro_grados=90, largo_m=5.0, ancho_m=5.0, area_m2=2.0),))
    [d] = r["geometria"]["descansos_detalle"]
    assert d["origen"] == "plano" and d["area_m2"] == pytest.approx(2.0) and d["largo_m"] is None and d["ancho_m"] is None
    assert r["conceptos"][1]["cantidad"] == pytest.approx(2.0)
    with pytest.raises(ErrorDeEscalera, match="no tiene área"):
        _escalera(rampas=2, descansos=(DescansoDeEscalera(posicion=1, area_m2=0.0),))


def test_un_descanso_mal_puesto_se_rechaza_y_uno_chico_avisa() -> None:
    with pytest.raises(ErrorDeEscalera, match="tiene 2 rampas"):
        _escalera(rampas=2, descansos=(DescansoDeEscalera(posicion=2),))
    with pytest.raises(ErrorDeEscalera, match="tiene 1 rampa"):
        _escalera(rampas=1, descansos=(DescansoDeEscalera(posicion=1),))
    with pytest.raises(ErrorDeEscalera, match="dos descansos"):
        _escalera(rampas=3, descansos=(DescansoDeEscalera(posicion=1), DescansoDeEscalera(posicion=1)))
    chico = _escalera(rampas=2, descansos=(DescansoDeEscalera(posicion=1, giro_grados=180, largo_m=1.2, ancho_m=1.2),))
    assert any("más chico" in a and "180°" in a for a in chico["advertencias"])
    assert _escalera(rampas=2, descansos=(DescansoDeEscalera(posicion=1, giro_grados=90),))["advertencias"] == []


def test_los_descansos_y_los_abanicos_validados_traen_sus_omisiones() -> None:
    assert validar_descanso({"posicion": 1}) == {"posicion": 1, "giro_grados": 90, "largo_m": None, "ancho_m": None, "espesor_m": None}
    assert validar_abanico({"posicion": 0, "escalones": 3, "ancho_interior_m": 0.1, "ancho_exterior_m": 0.4})["radio_huella_m"] == RADIO_DE_HUELLA_M == 0.35
    for mal in ({"posicion": 0}, {"posicion": 4}, {"posicion": 1, "giro_grados": 45}, {"posicion": 1, "largo_m": 9}, {"posicion": 1, "espesor_m": 0.9}, {"posicion": True}):
        with pytest.raises(ErrorDeEscalera):
            validar_descanso(mal)
    base = {"posicion": 1, "escalones": 3, "ancho_interior_m": 0.1, "ancho_exterior_m": 0.4}
    for mal in (
        {"posicion": 5}, {"escalones": 0}, {"escalones": 13}, {"ancho_interior_m": 0.01}, {"ancho_exterior_m": 0.9}, {"ancho_exterior_m": 0.05}, {"radio_huella_m": 0.05},
        {"radio_huella_m": 6}, {"ancho_interior_m": 0.5, "ancho_exterior_m": 0.3},
    ):
        with pytest.raises(ErrorDeEscalera):
            validar_abanico({**base, **mal})


# ── Escalón tipo abanico (Fase 4d) ──────────────────────────────────────────────────────────────────

_ABANICO = AbanicoDeEscalera(posicion=1, escalones=3, ancho_interior_m=0.15, ancho_exterior_m=0.75)


def test_los_escalones_de_abanico_son_parte_de_los_peldanos_y_no_se_cuentan_dos_veces() -> None:
    sin = _escalera(rampas=2)
    r = _escalera(rampas=2, abanicos=(_ABANICO,))
    g = r["geometria"]
    # Los 18 peldaños del desnivel no cambian: 3 son de abanico y 15 rectos (se reparten entre las rampas).
    assert (g["peldanos"], g["peldanos_rectos"], g["peldanos_de_abanico"]) == (18, 15, 3) and sin["geometria"]["peldanos"] == 18
    assert [x["peldanos"] for x in g["rampas"]] == [8, 7] and g["contrahuella_m"] == pytest.approx(sin["geometria"]["contrahuella_m"])
    # La rampa solo mide sus 15 peldaños rectos; el abanico, su propia geometría.
    inclinada = math.hypot(0.25, 3.12 / 18)
    assert g["superficie_de_rampa_m2"] == pytest.approx(15 * inclinada * 1.2) and g["recorrido_horizontal_m"] == pytest.approx((15 - 2) * 0.25)
    [a] = g["abanicos"]
    # Fondo del peldaño en la línea de huella (35 cm del borde interior de 1.20 m): 15 + 60 × 0.35 / 1.20 = 32.5 cm.
    assert a["huella_en_la_linea_m"] == pytest.approx(0.15 + 0.60 * 0.35 / 1.2) and a["radio_huella_m"] == 0.35 and a["ancho_medio_m"] == pytest.approx(0.45)
    assert a["angulo_por_escalon_grados"] == pytest.approx(math.degrees(0.5)) and a["giro_total_grados"] == pytest.approx(3 * math.degrees(0.5))
    assert a["radio_interior_m"] == pytest.approx(1.2 * 0.15 / 0.6)
    assert a["area_en_planta_m2"] == pytest.approx(3 * 1.2 * 0.45) and g["area_de_abanico_m2"] == pytest.approx(1.62)
    assert a["superficie_m2"] == pytest.approx(1.62 * math.hypot(a["huella_en_la_linea_m"], 3.12 / 18) / a["huella_en_la_linea_m"])


def test_las_piezas_de_est_01510_suman_las_rectas_y_las_de_abanico_por_su_ancho_equivalente() -> None:
    r = _escalera(rampas=2, abanicos=(_ABANICO,))
    g = r["geometria"]
    # Rectos: 15 × 1.20 ÷ 1.20 = 15. Abanico: 3 escalones × (1.20 × 0.45 m de fondo medio) ÷ (1.20 × 0.25 de huella) = 5.4.
    assert g["escalones_rectos_de_catalogo"] == pytest.approx(15.0) and g["escalones_de_abanico_de_catalogo"] == pytest.approx(5.4)
    [escalon, _descanso] = r["conceptos"]
    assert escalon["cantidad"] == pytest.approx(20.4) and g["escalones_de_catalogo"] == pytest.approx(20.4) and "abanico" in escalon["toma"]
    assert "forman parte de los 18 peldaños" in escalon["nota"]
    # Con un fondo medio igual a la huella, cada escalón de abanico vale ancho ÷ 1.20, igual que uno recto (sin duplicar ni perder piezas).
    parejo = _escalera(abanicos=(AbanicoDeEscalera(posicion=0, escalones=3, ancho_interior_m=0.25, ancho_exterior_m=0.25),))
    assert parejo["geometria"]["escalones_de_catalogo"] == pytest.approx(18.0)
    [a] = parejo["geometria"]["abanicos"]
    assert a["angulo_por_escalon_grados"] == 0 and a["radio_interior_m"] is None and a["huella_en_la_linea_m"] == pytest.approx(0.25)
    # El ancho de la escalera escala las piezas igual que en los rectos.
    ancha = _escalera(ancho_m=2.4, abanicos=(_ABANICO,))["geometria"]
    assert ancha["escalones_de_catalogo"] == pytest.approx(15 * 2.0 + 3 * 2.4 * 0.45 / (1.2 * 0.25) * 1.0)


def test_el_concreto_y_el_acero_del_abanico_salen_de_su_geometria_sin_duplicar_el_de_la_rampa() -> None:
    r = _escalera(rampas=2, abanicos=(_ABANICO,))
    g = r["geometria"]
    del_abanico = {i["clave"]: i for i in r["insumos"] if i["parte"] == "abanico"}
    de_la_rampa = {i["clave"]: i for i in r["insumos"] if i["parte"] == "rampa"}
    assert del_abanico["CON-00004"]["cantidad"] == pytest.approx(g["superficie_de_abanico_m2"] * 0.12) and g["volumen_de_abanico_m3"] == pytest.approx(del_abanico["CON-00004"]["cantidad"])
    assert de_la_rampa["CON-00004"]["cantidad"] == pytest.approx(g["superficie_de_rampa_m2"] * 0.12)
    for clave, _d, _u, por_m2, _f in PARRILLA_POR_M2:
        assert del_abanico[clave]["cantidad"] == pytest.approx(g["superficie_de_abanico_m2"] * por_m2)
    # El concreto total de peldaños es el de la escalera recta menos lo que cambia al sustituir 3 rectos por 3 de abanico: la superficie de los 15 rectos más la del abanico.
    total = del_abanico["CON-00004"]["cantidad"] + de_la_rampa["CON-00004"]["cantidad"]
    assert total == pytest.approx((g["superficie_de_rampa_m2"] + g["superficie_de_abanico_m2"]) * 0.12)
    # El espesor de la escalera aplica al abanico.
    grueso = _escalera(rampas=2, espesor_m=0.2, abanicos=(_ABANICO,))["geometria"]
    assert grueso["volumen_de_abanico_m3"] == pytest.approx(grueso["superficie_de_abanico_m2"] * 0.2)


def test_el_radio_de_la_linea_de_huella_es_editable_y_se_valida() -> None:
    def con_radio(radio: float) -> dict:
        return _escalera(abanicos=(AbanicoDeEscalera(posicion=0, escalones=3, ancho_interior_m=0.15, ancho_exterior_m=0.75, radio_huella_m=radio),))["geometria"]["abanicos"][0]

    assert con_radio(0.30)["huella_en_la_linea_m"] == pytest.approx(0.15 + 0.6 * 0.30 / 1.2)
    assert con_radio(0.40)["huella_en_la_linea_m"] == pytest.approx(0.15 + 0.6 * 0.40 / 1.2)
    with pytest.raises(ErrorDeEscalera, match="pasa del ancho"):
        con_radio(1.5)


def test_un_abanico_que_no_cabe_o_no_camina_se_rechaza_y_uno_estrecho_avisa() -> None:
    with pytest.raises(ErrorDeEscalera, match="no caben"):
        _escalera(rampas=4, abanicos=(AbanicoDeEscalera(posicion=1, escalones=12, ancho_interior_m=0.15, ancho_exterior_m=0.75),))  # quedarían 6 rectos y 4 rampas piden 8
    with pytest.raises(ErrorDeEscalera, match="no cae en la escalera"):
        _escalera(rampas=1, abanicos=(AbanicoDeEscalera(posicion=2, escalones=3, ancho_interior_m=0.15, ancho_exterior_m=0.75),))
    with pytest.raises(ErrorDeEscalera, match="dos grupos de abanico"):
        _escalera(rampas=2, abanicos=(_ABANICO, AbanicoDeEscalera(posicion=1, escalones=2, ancho_interior_m=0.15, ancho_exterior_m=0.75)))
    # Fondo en la línea de huella menor a 15 cm: no se puede pisar.
    with pytest.raises(ErrorDeEscalera, match="línea de huella"):
        _escalera(abanicos=(AbanicoDeEscalera(posicion=0, escalones=3, ancho_interior_m=0.05, ancho_exterior_m=0.15),))
    # Entre 15 y 25 cm: se calcula y avisa. Un giro que no cierra 90° ni 180° también avisa.
    r = _escalera(abanicos=(AbanicoDeEscalera(posicion=0, escalones=3, ancho_interior_m=0.10, ancho_exterior_m=0.40),))
    assert any("menor que la huella de referencia" in a for a in r["advertencias"]) and any("no cierra un giro de 90° ni de 180°" in a for a in r["advertencias"])
    assert not any("no cierra" in a for a in _escalera(abanicos=(_ABANICO,))["advertencias"])  # 3 × 28.6° = 85.9°: cierra 90°


def test_un_descanso_que_gira_y_un_abanico_en_la_misma_posicion_avisan_del_giro_doble() -> None:
    r = _escalera(rampas=2, abanicos=(_ABANICO,), descansos=(DescansoDeEscalera(posicion=1, giro_grados=90),))
    assert any("el mismo giro" in a for a in r["advertencias"])
    assert not any("el mismo giro" in a for a in _escalera(rampas=2, abanicos=(_ABANICO,), descansos=(DescansoDeEscalera(posicion=1, giro_grados=0),))["advertencias"])


def test_el_recorrido_de_una_linea_mide_solo_los_peldanos_rectos() -> None:
    # 15 rectos en 2 rampas tienen 13 huellas: 3.25 m dan la huella de 25 cm (el abanico no está en la línea).
    r = _escalera(rampas=2, recorrido_m=3.25, abanicos=(_ABANICO,))
    assert r["geometria"]["huella_m"] == pytest.approx(0.25) and r["geometria"]["origen_de_huella"] == "linea"


def test_la_ficha_y_el_cuerpo_traen_los_pendientes_del_descanso_y_del_abanico() -> None:
    d = definicion_de_escalera("ESC-FORJADA")
    assert d is not None and {p["clave"] for p in d["pendientes"]} >= {"E9", "E10", "E11"}
    assert d["radio_de_huella_por_defecto_m"] == 0.35 and d["giros_de_descanso"] == [0, 90, 180]
