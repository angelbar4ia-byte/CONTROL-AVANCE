"""Los castillos K-1 a K-8, los aparentes y las columnas forjadas: cálculo, escalones, correcciones y conciliación (Ola 3, 3A).

Las cantidades del catálogo salen de `ANALISIS_DE_BASICOS_CONCEPTOS.csv` (opus); `scripts/verificar_estructura_contra_csv.py`
las compara con el CSV cuando se corre a mano.
"""

from __future__ import annotations

import pytest

from obractrl.domain.cuantificacion.biblioteca_de_elementos import (
    BIBLIOTECA,
    elemento_de_la_biblioteca,
)
from obractrl.domain.cuantificacion.clasificacion_de_elementos import (
    CATEGORIAS,
    validar_posicion,
)
from obractrl.domain.cuantificacion.comparacion_con_catalogo import FilaDeComposicion
from obractrl.domain.cuantificacion.correcciones_de_catalogo import (
    COEFICIENTES_DEL_CATALOGO,
    conciliar_con_catalogo,
    correcciones_de,
    numero_de_version,
    propuesta_de_concepto_nuevo,
)
from obractrl.domain.cuantificacion.estructura_de_catalogo import (
    ALTO_DE_LA_FORJADA_M,
    ELEMENTOS_DE_ESTRUCTURA,
    ElementoDeEstructuraNoEncontrado,
    ErrorDeEstructura,
    calcular_elemento,
    claves_de_concepto,
    concepto_nuevo_por_altura,
    definicion_de,
    elemento_de_estructura,
)


def _concepto(r: dict, clave: str) -> dict:
    return next(c for c in r["conceptos"] if c["clave"] == clave)


# --- La biblioteca y la clasificación ---------------------------------------------------------------------------------


def test_los_elementos_estan_en_su_categoria_y_subcategoria_de_la_clasificacion() -> None:
    subcategorias = {(c["clave"], s["clave"]) for c in CATEGORIAS for s in c["subcategorias"]}
    for e in ELEMENTOS_DE_ESTRUCTURA.values():
        assert (e.categoria, e.subcategoria) in subcategorias, e.clave
    tipos = {c["clave"]: c["tipo"] for c in CATEGORIAS}
    assert all(tipos[e.categoria] == e.tipo for e in ELEMENTOS_DE_ESTRUCTURA.values())


def test_las_cadenas_aparentes_van_en_cadenas_y_el_castillo_aparente_en_castillos() -> None:
    """Q84: BAP-03010 y BAP-03030 son cadenas, no castillos; BAP-03020 sí es castillo."""
    ubicacion = {e.clave: (e.categoria, e.subcategoria) for e in ELEMENTOS_DE_ESTRUCTURA.values()}
    assert ubicacion["BAP-03010"] == ("cadenas", "desplante_aparente")
    assert ubicacion["BAP-03030"] == ("cadenas", "cerramiento_aparente")
    assert ubicacion["BAP-03020"] == ("castillos", "aparentes")
    assert ubicacion["EST-07010"] == ("columnas", "forjada")
    validar_posicion("cadenas", "desplante_aparente", "desplante")
    validar_posicion("cadenas", "cerramiento_aparente", "remate")


def test_la_biblioteca_trae_los_trece_elementos_con_sus_nombres() -> None:
    claves = {e["clave"]: (c["clave"], s["clave"]) for c in BIBLIOTECA for s in c["subcategorias"] for e in s["elementos"]}
    assert set(ELEMENTOS_DE_ESTRUCTURA) <= set(claves)
    assert len(ELEMENTOS_DE_ESTRUCTURA) == 13
    assert claves["EST-02130"] == ("castillos", "muro")
    nombres = {e["clave"]: e["nombre"] for c in BIBLIOTECA for s in c["subcategorias"] for e in s["elementos"]}
    assert nombres["EST-02130"].startswith("K-3 ·")
    # Los de estructura no tienen el cuadro del muro de piedra: la ficha pasa por su propia ruta.
    assert elemento_de_la_biblioteca("EST-02130") is None
    assert elemento_de_la_biblioteca("MCT-01010") is not None


def test_la_ficha_de_un_elemento_trae_sus_conceptos_y_escalones() -> None:
    ficha = definicion_de("K-1")
    acero = next(c for c in ficha["conceptos"] if c["ranura"] == "acero")
    assert [(x["clave"], x["hasta_m"]) for x in acero["escalones"]] == [
        ("EST-10013", 1.0), ("EST-10012", 1.5), ("EST-10010", 4.0), ("EST-10011", 6.0),
    ]
    assert definicion_de("EST-07010")["alto_fijo_m"] == ALTO_DE_LA_FORJADA_M
    with pytest.raises(ElementoDeEstructuraNoEncontrado):
        definicion_de("K-99")


# --- Secciones: 15x30 es ancho 15 (espesor del muro) por largo 30 (Q75) --------------------------------------------------


@pytest.mark.parametrize(
    ("clave", "largo", "concreto"),
    [("EST-02130", 30, 0.04725), ("EST-02150", 45, 0.070875), ("EST-02170", 20, 0.0315), ("EST-02180", 40, 0.063)],
)
def test_la_seccion_es_ancho_15_por_el_largo_del_catalogo(clave: str, largo: float, concreto: float) -> None:
    e = elemento_de_estructura(clave)
    assert (e.ancho_cm, e.largo_cm) == (15.0, largo)
    colado = next(c for c in calcular_elemento(clave)["conceptos"] if c["ranura"] == "colado" and not c["nuevo"])
    assert colado["insumos"]["MEZ-01020"] == pytest.approx(concreto)


def test_la_cimbra_del_castillo_es_de_dos_lados_por_el_largo() -> None:
    r = calcular_elemento("EST-02130", 3.0)
    assert r["acero"]["cimbra"]["lados"] == 2
    assert r["acero"]["cimbra"]["m2"] == pytest.approx(2 * 0.30 * 3.0)


# --- El acero por escalón y el colado contra los números del catálogo -----------------------------------------------------


def test_k1_a_6_m_pide_una_pieza_de_armex_como_el_catalogo() -> None:
    r = calcular_elemento("K-1", 6.0)
    acero = _concepto(r, "EST-10011")
    assert acero["insumos"]["ACE-00011"] == pytest.approx(8 / 6)  # 2 piezas de 4 m (traslape y puntas)
    r4 = calcular_elemento("K-1", 4.0)
    assert _concepto(r4, "EST-10010")["insumos"]["ACE-00011"] == pytest.approx(1.0)


def test_el_colado_de_k1_a_k8_coincide_con_el_catalogo() -> None:
    """El concreto con 5 % de desperdicio y los consumos de cimbra son los del catálogo (verificado contra el CSV)."""
    esperado = {
        "K-1": ("EST-02110", 0.023625, 0.210987),
        "K-2": ("EST-02120", 0.023625, 0.189888),
        "EST-02130": ("EST-02130", 0.04725, 0.189888),
        "EST-02140": ("EST-02140", 0.04725, 0.189888),
        "EST-02150": ("EST-02150", 0.070875, 0.223398),
        "EST-02160": ("EST-02160", 0.023625, 0.1),
        "EST-02170": ("EST-02170", 0.0315, 0.189888),
        "EST-02180": ("EST-02180", 0.063, 0.12),
    }
    for clave, (concepto, concreto, alambre) in esperado.items():
        c = _concepto(calcular_elemento(clave), concepto)
        assert c["unidad"] == "m"
        assert c["insumos"]["MEZ-01020"] == pytest.approx(concreto), clave
        assert c["insumos"]["ACE-00001"] == pytest.approx(alambre), clave


def test_k8_vale_el_acero_est_10081_y_el_armex_del_colado_es_concepto_nuevo() -> None:
    """Q77."""
    e = elemento_de_estructura("EST-02180")
    assert e.armado.armex is None and e.armado.varillas == ((8, 4, "ACR-00002"),)
    assert e.armado.anillo_sep_cm == 12.0
    r = calcular_elemento("EST-02180", 6.0)
    assert _concepto(r, "EST-10081")["unidad"] == "pza"
    nuevo = _concepto(r, "EJ-780")
    assert nuevo["nuevo"] is True
    assert nuevo["insumos"] == {"ACE-00020": pytest.approx(1 / 5.85)}
    assert "EJ-780" in claves_de_concepto(e)


def test_el_escalon_sigue_el_alto_y_avisa_si_lo_rebasa() -> None:
    assert _concepto(calcular_elemento("K-1", 1.2), "EST-10012")["hasta_m"] == 1.5
    assert _concepto(calcular_elemento("K-1", 0.8), "EST-10013")["hasta_m"] == 1.0
    r = calcular_elemento("EST-02130", 7.0)
    c = _concepto(r, "EST-10031")
    assert c["rebasa"] is True
    assert any("rebasa" in a and "EST-10031" in a for a in r["advertencias"])
    assert not calcular_elemento("EST-02130", 6.0)["advertencias"]


def test_un_alto_que_no_vale_se_rechaza() -> None:
    with pytest.raises(ErrorDeEstructura):
        calcular_elemento("K-1", 0)
    with pytest.raises(ErrorDeEstructura):
        calcular_elemento("K-1", 31)


# --- Aparentes ------------------------------------------------------------------------------------------------------------


def test_los_aparentes_usan_las_medidas_del_titulo_y_un_solo_concepto_completo() -> None:
    """Q81: BAP-03010 es de 15×20, BAP-03020 de 25×20 y BAP-03030 de 20×25."""
    medidas = {"BAP-03010": (15, 20), "BAP-03020": (25, 20), "BAP-03030": (20, 25)}
    for clave, (a, b) in medidas.items():
        e = elemento_de_estructura(clave)
        # El castillo se lee largo × ancho; la cadena, ancho × peralte.
        assert ((e.largo_cm, e.ancho_cm) if e.tipo == "castillo" else (e.ancho_cm, e.peralte_cm)) == (a, b)
        r = calcular_elemento(clave)
        (c,) = r["conceptos"]
        assert c["ranura"] == "completo" and c["unidad"] == "m" and c["clave"] == clave
        assert c["insumos"]["MEZ-01020"] == pytest.approx(a * b / 10000 * 1.05)
        assert c["insumos"]["MAD-00030"] > 0
    assert calcular_elemento("BAP-03010")["seccion"] == {"ancho_cm": 15.0, "largo_cm": None, "peralte_cm": 20.0}


def test_el_mortero_del_aparente_queda_solo_en_el_catalogo() -> None:
    """Q82: el elemento no calcula lo que el catálogo no explica."""
    r = calcular_elemento("BAP-03020")
    assert [s["clave"] for s in r["solo_en_catalogo"]] == ["MEZ-07010"]
    assert "MEZ-07010" not in r["conceptos"][0]["insumos"]


# --- Columna forjada ------------------------------------------------------------------------------------------------------


def test_la_forjada_calcula_el_forro_por_geometria_y_la_cimbra_de_un_lado() -> None:
    r = calcular_elemento("EST-07010")
    assert r["alto_m"] == 4.2 and r["alto_fijo"] is True and r["lados_cimbra"] == 1
    forro = r["forro"]
    assert forro["cimbra_m2"] == pytest.approx(0.33 * 4.2)
    assert forro["pza_netas"] == pytest.approx(144.375)
    assert forro["tabique_pza"] == pytest.approx(161.7)
    assert forro["mezcla_m3"] == pytest.approx(0.1055, abs=1e-4)
    columna = _concepto(r, "EST-07010")
    assert columna["unidad"] == "pza"
    assert columna["insumos"]["MEZ-01020"] == pytest.approx(0.099225)  # el concreto del núcleo, como el catálogo
    assert columna["insumos"]["MAD-00002"] == pytest.approx(0.33 * 4.2)
    assert calcular_elemento("EST-07011")["conceptos"][1]["insumos"]["MEZ-01020"] == pytest.approx(0.19845)


def test_la_forjada_paga_el_acero_del_castillo_de_su_nucleo() -> None:
    """M-125 / Q88: EST-10011 para CM-1 (núcleo como K-1) y EST-10031 para CM-2 (núcleo como K-3)."""
    assert _concepto(calcular_elemento("EST-07010"), "EST-10011")["insumos"]["ACE-00011"] == pytest.approx(1.0)
    assert _concepto(calcular_elemento("EST-07011"), "EST-10031")["unidad"] == "pza"


def test_otra_altura_de_forjada_es_un_concepto_nuevo_pendiente() -> None:
    """Q91."""
    assert concepto_nuevo_por_altura(elemento_de_estructura("EST-07010"), 4.2) is None
    nuevo = concepto_nuevo_por_altura(elemento_de_estructura("EST-07010"), 3.8)
    assert nuevo is not None and nuevo["clave_propuesta"] == "EST-07010-H380"
    r = calcular_elemento("EST-07010", 3.8)
    assert r["concepto_nuevo_por_altura"]["clave_propuesta"] == "EST-07010-H380"
    assert any("concepto nuevo" in a for a in r["advertencias"])
    assert calcular_elemento("EST-07010")["concepto_nuevo_por_altura"] is None


# --- Correcciones como nueva versión propuesta -----------------------------------------------------------------------------


def _por_concepto(clave: str) -> dict:
    return next(p for p in correcciones_de(clave) if p["clase"] == "version_de_concepto")


def test_el_armex_de_k7_se_propone_con_lo_que_pide_el_corte() -> None:
    """Q22 confirmado: puntas de 50 cm; EST-10071 pasa a 1.33 pza, EST-10070 a 1.0 y EST-10072 a 0.5 como nuevas versiones."""
    esperado = {"EST-10071": (0.833333, 4 / 3), "EST-10070": (0.666667, 1.0), "EST-10072": (0.333333, 0.5)}
    propuestas = {x["concepto_clave"]: x for x in correcciones_de("EST-02170") if x["clase"] == "version_de_concepto"}
    assert set(propuestas) == set(esperado)
    for concepto, (antes, despues) in esperado.items():
        (cambio,) = propuestas[concepto]["detalle"]["cambios"]
        assert (cambio["insumo"], cambio["unidad"], cambio["antes"]) == ("ACE-00020", "pza", antes)
        assert cambio["despues"] == pytest.approx(despues, abs=1e-6)
        assert concepto in propuestas[concepto]["resumen"]
        assert any("Q22" in m for m in propuestas[concepto]["detalle"]["motivos"])


def test_los_kg_de_anillo_se_igualan_al_calculo_del_elemento() -> None:
    """Q78: perímetro del núcleo más gancho; en K-2 el anillo real es de 0.50 m, no de 0.37 m."""
    p = next(x for x in correcciones_de("K-2") if x["concepto_clave"] == "EST-10020")
    (cambio,) = p["detalle"]["cambios"]
    assert (cambio["insumo"], cambio["antes"]) == ("ACE-00003", 1.9173)
    anillos = 21  # ceil(4.00 ÷ 0.20) + 1
    assert cambio["despues"] == pytest.approx(anillos * 0.5 * 0.249, abs=1e-4)
    assert cambio["despues"] > cambio["antes"]  # el catálogo traía el anillo más corto que el calculado
    assert any("Q78" in m for m in p["detalle"]["motivos"])


def test_las_correcciones_de_anillo_cubren_cada_acero_con_anillos_y_no_se_repiten() -> None:
    conceptos = []
    for e in ELEMENTOS_DE_ESTRUCTURA:
        conceptos.extend(p["concepto_clave"] for p in correcciones_de(e))
    assert len(conceptos) == len(set(conceptos))  # un concepto lo propone un solo elemento (la forjada usa el de su núcleo)
    for esperado in ("EST-10020", "EST-10021", "EST-10031", "EST-10041", "EST-10051", "EST-10060", "EST-10081", "EST-10070", "EST-10071", "EST-10072"):
        assert esperado in conceptos
    assert "EST-10011" not in conceptos


def test_los_aparentes_se_corrigen_a_la_medida_del_titulo_sin_inventar_destajos() -> None:
    p10 = _por_concepto("BAP-03010")
    assert p10["detalle"]["cambios"] == [{"insumo": "MEZ-01020", "unidad": "m³", "antes": 0.0525, "despues": 0.0315}]
    assert p10["detalle"]["destajo"]["destajo"] == "MOE-02202"
    p30 = _por_concepto("BAP-03030")
    assert p30["detalle"]["cambios"][0]["despues"] == pytest.approx(0.0525)
    assert "destajo" not in p30["detalle"]  # el destajo 20×25 sí corresponde
    p20 = _por_concepto("BAP-03020")
    assert p20["detalle"]["cambios"] == []  # su concreto ya es de 25×20; solo el destajo no corresponde
    assert p20["detalle"]["destajo"]["destajo"] == "MOE-02025"


def test_el_concepto_nuevo_de_k8_y_el_de_la_forjada_nacen_pendientes_sin_precio() -> None:
    (nuevo,) = [p for p in correcciones_de("EST-02180") if p["clase"] == "concepto_nuevo"]
    assert nuevo["concepto_clave"] == "EJ-780"
    assert nuevo["detalle"]["insumos"] == {"ACE-00020": pytest.approx(1 / 5.85)}
    por_altura = propuesta_de_concepto_nuevo(elemento_de_estructura("EST-07011"), alto_m=3.5)
    assert por_altura["concepto_clave"] == "EST-07011-H350" and por_altura["clase"] == "concepto_nuevo"
    with pytest.raises(Exception, match="no hace falta"):
        propuesta_de_concepto_nuevo(elemento_de_estructura("EST-07011"), alto_m=4.2)


def test_los_coeficientes_antes_son_los_del_catalogo_neto() -> None:
    assert COEFICIENTES_DEL_CATALOGO[("EST-10071", "ACE-00020")] == 0.833333
    assert COEFICIENTES_DEL_CATALOGO[("EST-10081", "ACE-00006")] == pytest.approx(16.297050 - 0.297050)
    assert COEFICIENTES_DEL_CATALOGO[("EST-10051", "ACE-00002")] == pytest.approx(8.81958 + 0.18042)


def test_las_versiones_nacen_en_la_2_para_un_concepto_del_catalogo_y_en_la_1_para_uno_nuevo() -> None:
    assert numero_de_version("version_de_concepto", []) == 2
    assert numero_de_version("version_de_concepto", [2, 3]) == 4
    assert numero_de_version("concepto_nuevo", []) == 1
    with pytest.raises(Exception, match="desconocida"):
        numero_de_version("otra", [])


# --- Conciliación contra el catálogo ---------------------------------------------------------------------------------------


def _comp(*filas: tuple[str, float]) -> list[FilaDeComposicion]:
    return [FilaDeComposicion(clave=k, cantidad=q) for k, q in filas]


def test_la_conciliacion_muestra_coincidencias_diferencias_y_lo_que_solo_trae_el_catalogo() -> None:
    comp = {
        "BAP-03020": _comp(
            ("ACE-00001", 0.3), ("ACE-00020", 0.175), ("ACE-00012", 0.025532), ("ACE-00013", 0.02), ("MAD-00030", 0.128205),
            ("MEZ-01020", 0.0525), ("MEZ-07010", 0.0021), ("MAD-00004", 0.01),
        )
    }
    r = conciliar_con_catalogo("BAP-03020", comp)
    (bloque,) = r["conceptos"]
    filas = {f["clave"]: f for f in bloque["filas"]}
    assert filas["MEZ-01020"]["marca"] == "="
    assert filas["MAD-00030"]["marca"] == "="
    assert filas["MEZ-07010"]["marca"] == "solo_catalogo" and "Q82" in filas["MEZ-07010"]["motivo"]
    assert filas["ACE-00020"]["marca"] == "≠"  # 0.2222 contra 0.175 (4.00 m de armex con puntas de 50 cm)
    assert bloque["coincide"] is False


def test_la_conciliacion_de_un_concepto_nuevo_no_tiene_catalogo() -> None:
    r = conciliar_con_catalogo("EST-02180", {})
    nuevo = next(b for b in r["conceptos"] if b["concepto_clave"] == "EJ-780")
    assert nuevo["nuevo"] and nuevo["sin_catalogo"]
    assert [f["marca"] for f in nuevo["filas"]] == ["solo_elemento"]


def test_la_conciliacion_pone_la_version_propuesta_junto_al_catalogo_vigente() -> None:
    propuesta = {
        "id": "00000000-0000-0000-0000-0000000000aa", "estado": "pendiente", "version": None, "clase": "version_de_concepto",
        "resumen": "Nueva versión de EST-10071", "concepto_clave": "EST-10071",
        "detalle": {"cambios": [{"insumo": "ACE-00020", "antes": 0.833333, "despues": 1.0}]},
    }
    comp = {"EST-10071": _comp(("ACE-00020", 0.833333), ("ACE-00001", 0.032945))}
    r = conciliar_con_catalogo("EST-02170", comp, propuestas=[propuesta])
    bloque = next(b for b in r["conceptos"] if b["concepto_clave"] == "EST-10071")
    fila = next(f for f in bloque["filas"] if f["clave"] == "ACE-00020")
    assert fila["catalogo"] == pytest.approx(0.833333)
    assert fila["propuesta"]["valor"] == 1.0 and fila["propuesta"]["estado"] == "pendiente"
    assert bloque["propuestas"][0]["resumen"].startswith("Nueva versión")
    otra = next(f for f in bloque["filas"] if f["clave"] == "ACE-00001")
    assert otra["propuesta"] is None
