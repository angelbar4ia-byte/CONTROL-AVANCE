"""Trabes, contratrabes, nervaduras, zapata Z-1 y columna C-1 de la biblioteca (Ola 3B): catálogo, cálculo por ml y por pieza, y
conciliación con la composición real del catálogo (dominio puro)."""

from __future__ import annotations

import re

import pytest

from obractrl.domain.cuantificacion.biblioteca_de_elementos import (
    BIBLIOTECA,
    elemento_de_la_biblioteca,
)
from obractrl.domain.cuantificacion.colado_por_ml import CLAVES_PROVISIONALES
from obractrl.domain.cuantificacion.elementos_lineales import (
    EntradaElementoEstructural,
    ErrorDeElementoEstructural,
    calcular_elemento,
    camino_de_colado_y_cimbra,
    claves_de_elementos_estructurales,
    definicion_del_elemento,
    elemento_estructural,
)
from obractrl.domain.cuantificacion.elementos_lineales_catalogo import ELEMENTOS, INSUMOS

TRABES = [e for e in ELEMENTOS if e["categoria"] == "trabes"]
CONTRATRABES = [e for e in ELEMENTOS if e["categoria"] == "contratrabes"]
NERVADURAS = [e for e in ELEMENTOS if e["categoria"] == "nervaduras"]
LINEALES = [*TRABES, *CONTRATRABES, *NERVADURAS]


def calc(clave: str, **kw: object):  # type: ignore[no-untyped-def]
    return calcular_elemento(EntradaElementoEstructural(clave, **kw))  # type: ignore[arg-type]


def fila(c: dict, clave: str) -> dict:  # type: ignore[type-arg]
    """La fila de conciliación de un insumo en la primera conciliación del cálculo."""
    return next(f for f in c["conciliacion"][0]["filas"] if f["clave"] == clave)


# --- El catálogo -------------------------------------------------------------------------------------------------


def test_trae_los_elementos_del_alcance() -> None:
    assert (len(TRABES), len(CONTRATRABES), len(NERVADURAS)) == (24, 7, 5)
    assert elemento_estructural("Z-1") is not None and elemento_estructural("C-1") is not None
    assert len(claves_de_elementos_estructurales()) == 38
    # Fuera de alcance: ZA-1, ZA-2, capitel, dado, EST-02330.
    for fuera in ("ZA-1", "ZA-2", "CAPITEL", "EST-02330", "D-1"):
        assert elemento_estructural(fuera) is None


def test_la_seccion_de_la_clave_es_ancho_por_peralte() -> None:
    """Q54: «15x25» = ancho × peralte, también T-14 (17×60) y T-15 (35×30)."""
    for e in LINEALES:
        m = re.search(r"(\d+)x(\d+)$", e["clave"])
        assert m, e["clave"]
        assert (float(m.group(1)), float(m.group(2))) == (e["ancho_cm"], e["peralte_cm"]), e["clave"]
    t14 = elemento_estructural("T-14-17x60")
    t15 = elemento_estructural("T-15-35x30")
    assert (t14["ancho_cm"], t14["peralte_cm"]) == (17, 60)  # type: ignore[index]
    assert (t15["ancho_cm"], t15["peralte_cm"]) == (35, 30)  # type: ignore[index]


def test_las_claves_con_la_seccion_van_en_trabes_de_losa_sin_renombrar() -> None:
    """Q53: las claves como T-1-15x25 quedan en «Trabes de losa (catálogo)»; no se renombran ni se separan en piso y cubierta."""
    assert {e["subcategoria"] for e in TRABES} == {"losa"}
    assert "T-1-15x25" in claves_de_elementos_estructurales()
    trabes = next(c for c in BIBLIOTECA if c["clave"] == "trabes")
    (sub,) = trabes["subcategorias"]
    assert sub["nombre"] == "Trabes de losa (catálogo)"
    assert len(sub["elementos"]) == 24


def test_todo_elemento_trae_su_concepto_y_su_composicion_del_catalogo() -> None:
    for e in ELEMENTOS:
        assert e["catalogo"], e["clave"]
        for c in e["catalogo"]:
            assert c["filas"], (e["clave"], c["clave"])
            assert all(f[6].split(":")[0].startswith(("ANALISIS_DE_BASICOS", "CATALOGO")) for f in c["filas"])
    assert {e["fuente"] for e in TRABES}.issuperset({"AUX-00001", "AUX-00008", "AUX-11410"})


def test_los_insumos_del_elemento_existen_en_la_tabla() -> None:
    for e in ELEMENTOS:
        usados = {e["concreto"], e["alambre"], *(c[0] for c in e["cimbra"])}
        a = e["armado"]
        usados |= {i for _, i in a.get("sup", ())} | {i for _, i in a.get("inf", ())} | {i for _, i in a.get("varillas", ())}
        usados |= {i for _, i in a.get("anillos", ())}
        usados |= {a[k] for k in ("armex", "varilla") if k in a}
        assert usados <= set(INSUMOS), (e["clave"], usados - set(INSUMOS))


def test_la_biblioteca_los_lista_sin_la_definicion_del_muro_de_piedra() -> None:
    claves = {e["clave"] for c in BIBLIOTECA for s in c["subcategorias"] for e in s["elementos"]}
    assert {"MCT-01010", "T-1-15x25", "CT1-15x25", "N-1-12x25", "Z-1", "C-1"} <= claves
    assert elemento_de_la_biblioteca("T-1-15x25") is None  # su definición está en /biblioteca-de-elementos/estructura/{clave}
    assert elemento_de_la_biblioteca("MCT-01010") is not None
    nombres = {c["clave"]: c["nombre"] for c in BIBLIOTECA}
    assert nombres["contratrabes"] == "Contratrabes" and nombres["nervaduras"] == "Nervaduras" and nombres["zapatas"] == "Zapatas"


# --- Por metro lineal --------------------------------------------------------------------------------------------


def test_trabe_por_ml_reproduce_el_acero_del_catalogo() -> None:
    """T-1-15x25 (AUX-00008): el anillo y el alambre salen igual que el catálogo (=) y la varilla a −4.4 % (traslape de 40 diámetros
    contra el 8 % del catálogo: ≈)."""
    r = calc("T-1-15x25")
    assert r["modo"] == "ml" and r["unidad"] == "ml"
    assert r["concreto"]["m3"] == pytest.approx(0.15 * 0.25 * 1.05)
    assert r["cimbra"]["m2"] == pytest.approx(2 * 0.25 + 0.15)  # dos costados y el fondo
    assert fila(r, "ACE-00005")["marca"] == "=" and fila(r, "ACE-00005")["elemento"] == pytest.approx(0.8217, abs=1e-3)
    assert fila(r, "ACE-00001")["marca"] == "="
    v = fila(r, "ACR-00001")
    assert v["marca"] == "≈" and v["diferencia_pct"] == pytest.approx(-4.37, abs=0.05)
    assert v["elemento"] == pytest.approx(4 * 12 / (12 - 40 * 0.009525) / 12, rel=1e-6)
    assert r["conciliacion"][0]["concepto"]["clave"] == "AUX-00008"
    assert r["conciliacion"][0]["resumen"]["≠"] == 0


def test_cada_elemento_lineal_calcula_por_ml_y_por_pieza() -> None:
    for e in LINEALES:
        ml = calc(e["clave"])
        pieza = calc(e["clave"], modo="pieza", largo_m=5.0)
        assert ml["unidad"] == "ml" and pieza["unidad"] == "pza"
        assert ml["concreto"]["m3"] == pytest.approx(e["ancho_cm"] / 100 * e["peralte_cm"] / 100 * 1.05)
        assert pieza["concreto"]["m3"] == pytest.approx(ml["concreto"]["m3"] * 5.0)
        assert pieza["longitud_m"] == 5.0
        assert pieza["receta_acero"]["forma"] == "pieza"
        assert any("por metro" in a for a in pieza["advertencias"])
        assert ml["mano_de_obra"]["estado"] == "sin_mano_de_obra"


def test_nervadura_sin_cimbra_y_con_anillo_de_largo_fijo() -> None:
    r = calc("N-1-12x25")
    assert r["cimbra"]["m2"] == 0 and r["cimbra"]["lados"] == 0
    assert r["concreto"]["clave"] == "CON-00004"  # concreto de azotea
    # 4 anillos por metro de 0.324 m de alambrón (0.249 kg/m) = 0.3227 kg: el del catálogo.
    assert fila(r, "ACE-00002")["marca"] == "="
    assert r["receta_acero"]["anillos"]["largo_anillo_m"] == pytest.approx(0.324)


def test_contratrabe_lleva_dos_costados_y_el_consumo_de_clavo_y_tabla() -> None:
    r = calc("CT1-15x25")
    assert r["concreto"]["clave"] == "CON-00001"
    assert r["cimbra"]["lados"] == 2 and r["cimbra"]["m2"] == pytest.approx(0.5)
    claves = {c["clave"] for c in r["cimbra"]["consumos"]}
    assert claves == {"ACE-00012", "ACE-00013", "MAD-00004"}


def test_trabe_con_armex_cuenta_la_pieza_con_traslape_de_15_cm() -> None:
    r = calc("T-3B-12x15")
    assert r["receta_acero"]["armex"]["piezas_comerciales"] == pytest.approx(1 / (6 - 0.15))
    assert fila(r, "ACE-00011")["marca"] == "="
    assert r["receta_acero"]["anillos"] is None


def test_el_anillo_de_varilla_se_compra_por_pieza() -> None:
    """T-14 hace el anillo con varilla de 3/8 (que el catálogo cuenta en pza); T-14 trae además 2 var #3 que su descripción no menciona
    (Q56): queda como diferencia, no se corrige."""
    r = calc("T-14-17x70")
    est = next(i for i in r["insumos"] if i["parte"] == "estribos")
    assert est["clave"] == "ACR-00001" and est["unidad"] == "pza"
    assert fila(r, "ACR-00002")["marca"] == "solo_elemento"
    assert fila(r, "ACR-00004")["marca"] == "="  # las 8 var #6
    assert r["conciliacion"][0]["coincide"] is False


def test_las_diferencias_de_q56_se_muestran_y_no_se_corrigen() -> None:
    """Q56: T-15, T-16 y T-18 (35 cm de ancho) traen un anillo que el catálogo calcula con la sección completa, sin recubrimiento
    (14 % más que el elemento: ≠); AUX-10205 trae dos anillos (el segundo solo está en el catálogo) y AUX-00060 usa un anillo 10×25 en
    una sección de 12×30. Se muestran como diferencia; los CSV y los datos del catálogo no se tocan."""
    for k in ("T-15-35x30", "T-16-35x30", "T-18-35x25"):
        f = next(x for x in calc(k)["conciliacion"][0]["filas"] if x["marca"] == "≠")
        assert f["clave"] == "ACR-00001" and f["diferencia_pct"] == pytest.approx(-14, abs=1.5)
    t2 = calc("T-2-12x20")
    assert fila(t2, "ACE-00029")["marca"] == "solo_catalogo" and fila(t2, "ACE-00004")["marca"] == "≠"
    assert fila(calc("T-5-12x30"), "ACE-00006")["marca"] == "≈"


# --- Por pieza ---------------------------------------------------------------------------------------------------


def test_trabe_por_pieza_corta_la_varilla_y_pone_puntas() -> None:
    r = calc("T-1-15x25", modo="pieza", largo_m=4.0)
    v = r["receta_acero"]["varillas"][0]
    assert v["puntas_m"] == pytest.approx(2 * 40 * 0.009525)
    assert v["corte"]["piezas"] >= 1 and v["corte"]["cubre_completo"]
    assert r["unidad"] == "pza" and r["longitud_m"] == 4.0
    # Un tramo de 4 m con 4 varillas de 3/8: 6 m de corte por varilla = 2.0 pza comerciales de 12 m.
    assert fila(r, "ACR-00001")["elemento"] == pytest.approx(0.5)


def test_trabe_por_pieza_con_zonas_de_anillo_en_los_extremos() -> None:
    simple = calc("T-1-15x25", modo="pieza", largo_m=6.0)
    zonas = calc("T-1-15x25", modo="pieza", largo_m=6.0, zonas_de_anillo=[(50.0, 10.0), (None, 25.0)])
    a, b = simple["receta_acero"]["anillos"], zonas["receta_acero"]["anillos"]
    assert len(b["zonas"]) == 2 and b["pza"] > a["pza"]
    assert b["zonas"][0]["largo_m"] == pytest.approx(1.0)  # 50 cm en cada extremo


def test_los_totales_a_comprar_se_redondean_hacia_arriba() -> None:
    r = calc("T-1-15x25", cantidad=10)
    var = next(i for i in r["insumos"] if i["clave"] == "ACR-00001")
    assert var["total"] == pytest.approx(3.4429, abs=1e-3)
    assert var["a_comprar"] == 4.0
    kg = next(i for i in r["insumos"] if i["clave"] == "ACE-00005")
    assert kg["a_comprar"] is None


# --- Zapata Z-1 y columna C-1 ------------------------------------------------------------------------------------


def test_z1_reproduce_el_catalogo_y_no_incluye_dado() -> None:
    r = calc("Z-1", modo="pieza")
    assert r["unidad"] == "pza" and r["longitud_m"] is None
    assert r["parrilla"]["varillas_por_sentido"] == [5, 5]
    assert fila(r, "ACR-00001")["marca"] == "=" and fila(r, "ACR-00001")["elemento"] == pytest.approx(0.5)
    assert fila(r, "ACE-00001")["marca"] == "="
    assert fila(r, "MEZ-01020")["marca"] == "≈"  # 0.072 del catálogo contra 0.0756 con 5 % de desperdicio
    assert r["concreto"]["m3"] == pytest.approx(0.6 * 0.6 * 0.2 * 1.05)
    # El dado (20×20×60 = 0.024 m³) no se suma y se avisa.
    assert any("dado" in a for a in r["advertencias"])
    assert [c["concepto"]["clave"] for c in r["conciliacion"]] == ["EST-03020"]
    assert r["conciliacion"][0]["mano_de_obra"][0]["clave"] == "MOE-05010"  # el destajo va en el concepto


def test_c1_se_calcula_por_pieza_de_altura_y_compara_con_los_dos_conceptos() -> None:
    r = calc("C-1", modo="pieza", alto_m=6.0)
    assert r["longitud_m"] == 6.0 and r["unidad"] == "pza"
    assert r["concreto"]["m3"] == pytest.approx(0.3 * 0.3 * 6 * 1.05)
    claves = [c["concepto"]["clave"] for c in r["conciliacion"]]
    assert claves == ["EST-11011", "EST-12011"]
    colado = r["conciliacion"][1]
    assert colado["sobre"].startswith("por metro")
    assert next(f for f in colado["filas"] if f["clave"] == "MEZ-01020")["marca"] == "="
    assert next(f for f in colado["filas"] if f["clave"] == "ACE-00001")["marca"] == "solo_catalogo"
    assert colado["mano_de_obra"][0]["clave"] == "MOE-20210"


def test_c1_avisa_si_pasa_del_escalon_del_catalogo() -> None:
    r = calc("C-1", modo="pieza", alto_m=7.0)
    assert any("pasa del escalón" in a for a in r["advertencias"])
    assert not any("pasa del escalón" in a for a in calc("C-1", modo="pieza", alto_m=6.0)["advertencias"])


# --- Lo que se contempla y no se ejecuta -------------------------------------------------------------------------


def test_el_colado_y_el_destajo_por_ml_se_registran_como_propuesta_sin_precio_ni_destajo_con_importe() -> None:
    """Q51 y Q52 con la fase 2 de la losa (D8): el camino trae la clave provisional del concepto de colado por ml y el destajo por ml sin importe."""
    for e in LINEALES:
        c = camino_de_colado_y_cimbra(e["clave"])
        assert c is not None and c["estado"] == "por_registrar"
        assert c["borrador"]["clave_propuesta"].startswith("EJ-7")
        assert c["borrador"]["clave_propuesta"] == CLAVES_PROVISIONALES[e["clave"]]
        assert c["borrador"]["toma"]["concreto"] is True
        assert c["mano_de_obra"]["destajo"] == c["borrador"]["clave_propuesta"] + "-MO"
        assert c["mano_de_obra"]["estado"] == "destajo_por_ml_sin_importe"
        assert "precio" not in str(c["borrador"]).lower().replace("sin precio", "")
    assert camino_de_colado_y_cimbra("Z-1")["estado"] == "no_aplica"  # type: ignore[index]
    assert camino_de_colado_y_cimbra("C-1")["estado"] == "no_aplica"  # type: ignore[index]
    # El cálculo del elemento no crea ningún concepto: solo describe el camino.
    assert "EJ-7" not in str(calc("T-1-15x25")["insumos"])


def test_la_nervadura_no_pide_cimbra_en_el_borrador_de_colado() -> None:
    d = definicion_del_elemento("N-1-12x25")
    assert d is not None and d["lados_de_cimbra"] == 0
    assert d["camino_de_colado_y_cimbra"]["borrador"]["toma"] == {"concreto": True, "cimbra": False}


def test_la_definicion_trae_modos_pendientes_y_conceptos_del_catalogo() -> None:
    d = definicion_del_elemento("T-1-15x25")
    assert d is not None
    assert d["modos"] == ["ml", "pieza"] and d["modo_por_defecto"] == "ml" and d["largo_por_defecto_m"] == 4.0
    assert {p["clave"] for p in d["pendientes"]} >= {"Q51", "Q52", "Q56"}
    assert d["conceptos_del_catalogo"][0]["clave"] == "AUX-00008" and d["conceptos_del_catalogo"][0]["unidad"] == "m"
    assert d["usos_total"] == 1 and d["usado_en"][0]["clave"] == "EST-52040"
    z = definicion_del_elemento("Z-1")
    assert z is not None and z["modos"] == ["pieza"] and {p["clave"] for p in z["pendientes"]} >= {"Q57", "Q58"}
    assert definicion_del_elemento("XX") is None


# --- Entradas que no valen ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("clave", "kw"),
    [
        ("NO-EXISTE", {}),
        ("T-1-15x25", {"cantidad": 0}),
        ("T-1-15x25", {"modo": "ml", "largo_m": 4.0}),
        ("T-1-15x25", {"modo": "ml", "zonas_de_anillo": [(None, 20.0)]}),
        ("T-1-15x25", {"modo": "pieza", "largo_m": 31.0}),
        ("T-1-15x25", {"alto_m": 3.0}),
        ("T-1-15x25", {"desperdicio_concreto_pct": 80.0}),
        ("Z-1", {"modo": "ml"}),
        ("Z-1", {"modo": "pieza", "alto_m": 2.0}),
        ("C-1", {"modo": "ml"}),
        ("C-1", {"modo": "pieza", "largo_m": 3.0}),
        ("C-1", {"modo": "pieza", "alto_m": 0.0}),
    ],
)
def test_entradas_que_no_valen(clave: str, kw: dict) -> None:  # type: ignore[type-arg]
    with pytest.raises(ErrorDeElementoEstructural):
        calc(clave, **kw)


# --- D5: altura habitual de C-1; D6: el anclaje como sugerencia --------------------------------------------------


def test_c1_nace_con_su_altura_habitual_de_4_20_m_y_es_editable() -> None:
    """D5: la altura habitual de C-1 es 4.20 m (no 6.00); otra altura se captura, y el escalón del catálogo sigue llegando a 6.00 m."""
    assert definicion_del_elemento("C-1")["alto_por_defecto_m"] == 4.2  # type: ignore[index]
    por_defecto = calc("C-1", modo="pieza")
    assert por_defecto["longitud_m"] == pytest.approx(4.2)
    assert por_defecto["concreto"]["m3"] == pytest.approx(0.3 * 0.3 * 4.2 * 1.05)
    assert not any("pasa del escalón" in a for a in por_defecto["advertencias"])
    assert calc("C-1", modo="pieza", alto_m=5.0)["longitud_m"] == 5.0
    assert [c["concepto"]["hasta_m"] for c in por_defecto["conciliacion"]] == [6.0, 6.0]


def test_el_anclaje_sugerido_es_de_40_diametros_por_extremo() -> None:
    r = calc("T-1-15x25", modo="pieza", largo_m=4.0)
    a = r["anclaje"]
    assert a["aplica"] is True and a["sugerido_diametros"] == 40 and a["capturado_cm"] is None and a["cumple"] is None
    g = a["grupos"][0]
    assert g["numero"] == 3 and g["sugerido_cm"] == pytest.approx(40 * 0.9525)  # la varilla no. 3 mide 3/8" = 0.9525 cm
    assert "Sugerido" in a["mensaje"]
    # Sin capturar, el cálculo es el de siempre (puntas de 40 diámetros en cada extremo).
    assert r["receta_acero"]["varillas"][0]["puntas_m"] == pytest.approx(2 * 40 * 0.009525)


def test_el_anclaje_capturado_avisa_si_cumple_y_el_calculo_lo_usa() -> None:
    sugerido = 40 * 0.9525
    cumple = calc("T-1-15x25", modo="pieza", largo_m=4.0, anclaje_cm=sugerido + 5)
    assert cumple["anclaje"]["cumple"] is True and cumple["anclaje"]["grupos"][0]["cumple"] is True
    assert "cumple" in cumple["anclaje"]["mensaje"] and "NO cumple" not in cumple["anclaje"]["mensaje"]
    assert cumple["receta_acero"]["varillas"][0]["puntas_m"] == pytest.approx(2 * (sugerido + 5) / 100)
    justo = calc("T-1-15x25", modo="pieza", largo_m=4.0, anclaje_cm=sugerido)
    assert justo["anclaje"]["cumple"] is True
    corto = calc("T-1-15x25", modo="pieza", largo_m=4.0, anclaje_cm=20.0)
    assert corto["anclaje"]["cumple"] is False and "NO cumple" in corto["anclaje"]["mensaje"]
    assert corto["receta_acero"]["varillas"][0]["puntas_m"] == pytest.approx(0.4)  # no se rechaza: es una sugerencia
    assert any("NO cumple" in a for a in corto["advertencias"])
    assert not any("NO cumple" in a for a in cumple["advertencias"])


def test_el_anclaje_con_varillas_de_dos_diametros_cumple_solo_si_cumple_la_mas_gruesa() -> None:
    r = calc("T-5-12x30", modo="pieza", largo_m=4.0, anclaje_cm=40 * 0.9525 + 1)  # alcanza la no. 3 y no la no. 4
    assert [g["cumple"] for g in r["anclaje"]["grupos"]] == [True, False]
    assert r["anclaje"]["cumple"] is False


def test_el_anclaje_aplica_a_la_columna_y_no_por_ml_ni_a_la_zapata() -> None:
    c = calc("C-1", modo="pieza", anclaje_cm=60.0)
    assert c["anclaje"]["aplica"] is True and c["anclaje"]["cumple"] is True
    por_ml = calc("T-1-15x25", modo="ml")
    assert por_ml["anclaje"]["aplica"] is False and por_ml["anclaje"]["cumple"] is None
    for clave, kw in (("T-1-15x25", {"modo": "ml"}), ("Z-1", {"modo": "pieza"})):
        with pytest.raises(ErrorDeElementoEstructural):
            calc(clave, anclaje_cm=30.0, **kw)
    for malo in (-1.0, 501.0, float("nan")):
        with pytest.raises(ErrorDeElementoEstructural):
            calc("T-1-15x25", modo="pieza", anclaje_cm=malo)
