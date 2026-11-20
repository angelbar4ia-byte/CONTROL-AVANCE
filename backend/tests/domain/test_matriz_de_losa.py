"""La matriz de conceptos de la losa (fase 2): área, concreto, cimbra, acero de los elementos y los conceptos que paga cada parte (dominio puro)."""

from __future__ import annotations

import pytest

from obractrl.domain.cuantificacion.biblioteca_de_elementos import BIBLIOTECA
from obractrl.domain.cuantificacion.colado_por_ml import CLAVES_PROVISIONALES
from obractrl.domain.cuantificacion.elementos_lineales import (
    EntradaElementoEstructural,
    calcular_elemento,
)
from obractrl.domain.cuantificacion.matriz_de_losa import (
    CLAVES_DE_LOSA,
    CONCEPTOS_DE_LOSA,
    DESTAJOS_DE_LOSA_DEL_CATALOGO,
    ElementoDeLosa,
    EntradaMatrizDeLosa,
    ErrorDeMatrizDeLosa,
    LosaDeEntrada,
    area_de_poligonos,
    calcular_matriz_de_losa,
    concepto_nuevo_de_losa,
    definicion_de_losa,
    elemento_de_losa,
    longitud_de_linea,
    validar_elemento_de_losa,
)
from obractrl.domain.cuantificacion.receta_acero import DriversDeReceta


def matriz(tipo: str = "maciza", **kw):  # type: ignore[no-untyped-def]
    kw.setdefault("espesor_m", 0.12 if tipo == "maciza" else 0.20)
    kw.setdefault("losas", [LosaDeEntrada(area_m2=100.0)])
    return calcular_matriz_de_losa(EntradaMatrizDeLosa(tipo=tipo, **kw))  # type: ignore[arg-type]


def por_clave(r: dict, parte: str, clave: str) -> float:  # type: ignore[type-arg]
    return sum(f["cantidad"] for f in r["insumos"] if f["parte"] == parte and f["clave"] == clave)


# ── Geometría ───────────────────────────────────────────────────────────────────────────────────────


def test_el_area_resta_los_huecos_y_suma_los_poligonos() -> None:
    cuadro = ((0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0))
    hueco = ((2.0, 1.0), (4.0, 1.0), (4.0, 3.0), (2.0, 3.0))
    assert area_de_poligonos([(cuadro,)]) == pytest.approx(50.0)
    assert area_de_poligonos([(cuadro, hueco)]) == pytest.approx(46.0)
    assert area_de_poligonos([(cuadro, hueco), (cuadro,)]) == pytest.approx(96.0)
    assert area_de_poligonos([]) == 0.0
    assert longitud_de_linea([(0.0, 0.0), (3.0, 4.0), (3.0, 10.0)]) == pytest.approx(11.0)


# ── La losa maciza ──────────────────────────────────────────────────────────────────────────────────


def test_la_maciza_cuenta_concreto_por_espesor_cimbra_por_m2_y_la_parrilla_del_catalogo() -> None:
    r = matriz("maciza", losas=[LosaDeEntrada(area_m2=125.0)])
    assert r["area_m2"] == 125.0
    assert r["concreto"]["geometrico_m3"] == pytest.approx(125 * 0.12)
    assert r["concreto"]["con_desperdicio_m3"] == pytest.approx(125 * 0.12 * 1.05)
    assert r["concreto"]["clave"] == "CON-00003"  # entrepiso
    assert r["cimbra"] == {"clave": "MAD-00001", "descripcion": "CIMBRA 3 MTS", "m2": 125.0}
    p = r["parrilla"]
    assert p["clave"] == "AUX-06010"
    assert {i["clave"]: i["total"] for i in p["insumos"]} == {"ACR-00001": pytest.approx(0.9 * 125), "ACE-00001": pytest.approx(0.20685 * 125)}
    assert por_clave(r, "acero", "ACR-00001") == pytest.approx(112.5)
    assert r["conceptos"][0]["concepto"] == {
        "clave": "EJ-800", "descripcion": CONCEPTOS_DE_LOSA["maciza"]["descripcion"], "unidad": "m²", "estado": "propuesto", "provisional": True,
    }
    assert r["conceptos"][0]["cantidad"] == 125.0 and r["conceptos"][0]["unidad"] == "m²"


def test_el_uso_elige_el_concreto_y_una_subzona_lleva_su_propio_espesor() -> None:
    assert matriz("maciza", uso="azotea")["concreto"]["clave"] == "CON-00004"
    r = matriz("maciza", losas=[LosaDeEntrada(area_m2=40.0), LosaDeEntrada(area_m2=10.0, espesor_m=0.2)])
    assert r["concreto"]["geometrico_m3"] == pytest.approx(40 * 0.12 + 10 * 0.2)
    assert [lo["subzona"] for lo in r["losas"]] == [False, True]
    assert r["concreto"]["clave"] == "CON-00003"
    assert matriz("maciza", concreto_clave="CON-00004")["concreto"]["clave"] == "CON-00004"


def test_el_desperdicio_de_concreto_es_el_de_la_obra() -> None:
    r = matriz("maciza", desperdicio_concreto_pct=0.0)
    assert r["concreto"]["con_desperdicio_m3"] == pytest.approx(r["concreto"]["geometrico_m3"])
    assert r["concreto"]["desperdicio_pct"] == 0.0


def test_una_zona_sin_poligonos_avisa_y_no_inventa_cantidades() -> None:
    r = matriz("maciza", losas=[])
    assert r["area_m2"] == 0.0 and r["insumos"] == []
    assert any("no tiene polígonos de losa" in a for a in r["advertencias"])
    assert r["conceptos"][0]["cantidad"] == 0.0


# ── La losa nervada ─────────────────────────────────────────────────────────────────────────────────


def test_la_nervada_cuenta_la_capa_de_compresion_y_no_calcula_el_caseton() -> None:
    r = matriz("nervada", losas=[LosaDeEntrada(area_m2=90.0)])
    assert r["concreto"]["geometrico_m3"] == pytest.approx(90 * 0.05)
    assert r["capa_de_compresion_cm"] == 5.0 and r["parrilla"] is None
    assert r["conceptos"][0]["concepto"]["clave"] == "EJ-801"
    assert r["conceptos"][0]["toma"] == ["concreto", "cimbra"]
    assert any("casetón" in a for a in r["advertencias"])
    assert any("sin nervaduras" in a for a in r["advertencias"])


def test_la_nervada_con_nervaduras_suma_el_concreto_de_sus_elementos() -> None:
    r = matriz("nervada", losas=[LosaDeEntrada(area_m2=90.0)], elementos=[ElementoDeLosa("N-1-12x25", cantidad=120.0), ElementoDeLosa("T-3-15x25", cantidad=51.0)])
    assert not any("sin nervaduras" in a for a in r["advertencias"])
    assert r["totales"]["concreto_de_los_elementos_m3"] > 0
    assert r["totales"]["concreto_m3"] == pytest.approx(r["totales"]["concreto_de_la_losa_m3"] + r["totales"]["concreto_de_los_elementos_m3"])
    assert r["cimbra"]["m2"] == 90.0
    # La nervadura no lleva cimbra (el casetón la forma): la de la zona es la de la losa más la de la trabe.
    nerv = next(e for e in r["elementos"] if e["clave"] == "N-1-12x25")
    assert nerv["cimbra_m2"] == 0.0


# ── Los elementos de la zona ────────────────────────────────────────────────────────────────────────


def test_el_acero_de_un_elemento_es_el_del_elemento_por_la_cantidad() -> None:
    r = matriz(elementos=[ElementoDeLosa("T-3-15x25", cantidad=51.0)])
    unitario = calcular_elemento(EntradaElementoEstructural(clave="T-3-15x25", modo="ml", cantidad=1.0))
    assert r["elementos"][0]["acero_kg"] == pytest.approx(unitario["acero_kg"] * 51)
    assert r["totales"]["acero_de_elementos_kg"] == pytest.approx(unitario["acero_kg"] * 51)
    fila = next(c for c in r["conceptos"] if c["parte"] == "acero")
    assert fila["concepto"] == {
        "clave": "AUX-00001", "descripcion": "Trabe T-3 de 15x25 cm 4 var. del #3 est. no. 2 @25 cm.", "unidad": "ml", "estado": "catalogo", "provisional": False,
    }
    assert fila["cantidad"] == 51.0 and fila["toma"] == ["acero"] and fila["unidad"] == "ml"


def test_por_pieza_los_metros_son_piezas_por_largo() -> None:
    r = matriz(elementos=[ElementoDeLosa("T-1-15x25", modo="pieza", cantidad=3.0, largo_m=4.5)])
    assert r["elementos"][0]["longitud_ml"] == pytest.approx(13.5)
    assert next(c for c in r["conceptos"] if c["parte"] == "acero")["cantidad"] == pytest.approx(13.5)
    assert r["totales"]["longitud_de_elementos_ml"] == pytest.approx(13.5)


def test_con_pago_en_la_losa_el_colado_lo_paga_la_losa_y_con_pago_propio_su_concepto_por_ml() -> None:
    en_losa = matriz(elementos=[ElementoDeLosa("T-1-15x25", cantidad=20.0)])
    assert [c["parte"] for c in en_losa["conceptos"]] == ["losa", "acero"]
    assert all(f["paga"] == "losa" for f in en_losa["insumos"] if f["parte"] in ("concreto", "cimbra"))
    propio = matriz(elementos=[ElementoDeLosa("T-1-15x25", cantidad=20.0, pago="propio")])
    assert [c["parte"] for c in propio["conceptos"]] == ["losa", "acero", "colado"]
    colado = propio["conceptos"][2]
    assert colado["concepto"]["clave"] == CLAVES_PROVISIONALES["T-1-15x25"] == "EJ-703"
    assert (colado["concepto"]["estado"], colado["concepto"]["provisional"], colado["unidad"], colado["cantidad"]) == ("propuesto", True, "ml", 20.0)
    assert colado["toma"] == ["concreto", "cimbra"]


def test_nunca_se_paga_lo_mismo_dos_veces_el_concreto_y_la_cimbra_van_en_un_solo_concepto() -> None:
    elementos = [
        ElementoDeLosa("T-1-15x25", cantidad=20.0), ElementoDeLosa("T-2-12x20", cantidad=8.0, pago="propio"),
        ElementoDeLosa("T-3-15x25", modo="pieza", cantidad=2.0, largo_m=6.0, pago="propio"),
    ]
    r = matriz(elementos=elementos)
    t = r["totales"]
    assert t["concreto_pagado_por_la_losa_m3"] + t["concreto_pagado_por_elementos_m3"] == pytest.approx(t["concreto_m3"])
    assert t["cimbra_pagada_por_la_losa_m2"] + t["cimbra_pagada_por_elementos_m2"] == pytest.approx(t["cimbra_m2"])
    assert t["concreto_pagado_por_elementos_m3"] > 0 and t["cimbra_pagada_por_elementos_m2"] > 0
    # Los insumos agregados reparten lo mismo: lo que paga la losa y lo que pagan los elementos suman el total físico.
    assert sum(f["cantidad"] for f in r["insumos"] if f["parte"] == "concreto") == pytest.approx(t["concreto_m3"])
    assert sum(f["cantidad"] for f in r["insumos"] if f["parte"] == "cimbra") == pytest.approx(t["cimbra_m2"])
    # Un elemento paga su concreto en un solo lugar: o la losa o su concepto.
    for f in r["insumos"]:
        assert f["paga"] in ("losa", "elemento")
    colados = {c["elemento_clave"] for c in r["conceptos"] if c["parte"] == "colado"}
    assert colados == {"T-2-12x20", "T-3-15x25"}


def test_el_concreto_de_una_contratrabe_cuenta_aunque_su_cimbra_sea_de_clavos_y_tablas() -> None:
    r = matriz(elementos=[ElementoDeLosa("CT1-15x25", cantidad=30.0, pago="propio")])
    assert r["totales"]["concreto_pagado_por_elementos_m3"] == pytest.approx(r["elementos"][0]["concreto_m3"])
    assert {f["clave"] for f in r["insumos"] if f["parte"] == "cimbra"} >= {"ACE-00012", "ACE-00013", "MAD-00004"}


def test_el_solape_con_la_losa_se_informa_y_no_se_descuenta() -> None:
    r = matriz(elementos=[ElementoDeLosa("T-1-15x25", cantidad=100.0)])
    # 100 ml × 0.15 m de ancho × min(espesor 0.12, peralte 0.25) = 1.8 m³
    assert r["totales"]["solape_con_la_losa_m3"] == pytest.approx(1.8)
    assert any("solape" in a for a in r["advertencias"])
    assert r["totales"]["concreto_m3"] == pytest.approx(r["totales"]["concreto_de_la_losa_m3"] + r["totales"]["concreto_de_los_elementos_m3"])


def test_los_drivers_del_acero_llegan_al_elemento() -> None:
    base = matriz(elementos=[ElementoDeLosa("T-3-15x25", modo="pieza", cantidad=1.0, largo_m=7.0)])
    con_traslape = matriz(
        elementos=[ElementoDeLosa("T-3-15x25", modo="pieza", cantidad=1.0, largo_m=7.0)], drivers=DriversDeReceta(puntas_inferior_diametros=0, puntas_superior_diametros=0),
    )
    assert base["totales"]["acero_de_elementos_kg"] != con_traslape["totales"]["acero_de_elementos_kg"]


# ── Sin mano de obra, sin precios ───────────────────────────────────────────────────────────────────


def test_no_calcula_ni_elige_mano_de_obra_y_lista_los_destajos_de_losa_como_candidatos() -> None:
    r = matriz(elementos=[ElementoDeLosa("T-1-15x25", cantidad=5.0, pago="propio")])
    mo = r["mano_de_obra"]
    assert mo["estado"] == "sin_mano_de_obra"
    assert [d["clave"] for d in mo["destajos_candidatos"]] == [k for k, _ in DESTAJOS_DE_LOSA_DEL_CATALOGO]
    assert not any(c["concepto"]["clave"].startswith("MO") for c in r["conceptos"])

    def claves(x: object) -> set[str]:
        if isinstance(x, dict):
            return {str(k) for k in x} | {k for v in x.values() for k in claves(v)}
        if isinstance(x, list | tuple):
            return {k for v in x for k in claves(v)}
        return set()

    assert not {k for k in claves(r) if "precio" in k or "costo" in k or "importe" in k}


# ── Validaciones ────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "kw",
    [
        {"tipo": "curva"},
        {"uso": "sótano"},
        {"espesor_m": 0.0},
        {"espesor_m": 4.0},
        {"desperdicio_concreto_pct": -1.0},
        {"desperdicio_concreto_pct": 60.0},
        {"losas": [LosaDeEntrada(area_m2=-1.0)]},
        {"losas": [LosaDeEntrada(area_m2=10.0, espesor_m=0.0)]},
        {"concreto_clave": "CON-00001"},
        {"elementos": [ElementoDeLosa("Z-1")]},
        {"elementos": [ElementoDeLosa("C-1")]},
        {"elementos": [ElementoDeLosa("XX-1")]},
        {"elementos": [ElementoDeLosa("T-1-15x25", cantidad=0.0)]},
        {"elementos": [ElementoDeLosa("T-1-15x25", modo="pieza", cantidad=1.0)]},
        {"elementos": [ElementoDeLosa("T-1-15x25", modo="ml", cantidad=1.0, largo_m=4.0)]},
        {"elementos": [ElementoDeLosa("T-1-15x25", modo="pieza", cantidad=1.0, largo_m=31.0)]},
        {"elementos": [ElementoDeLosa("T-1-15x25", pago="a_medias")]},  # type: ignore[arg-type]
    ],
)
def test_un_dato_que_no_vale_se_rechaza(kw: dict) -> None:  # type: ignore[type-arg]
    tipo = kw.pop("tipo", "maciza")
    with pytest.raises(ErrorDeMatrizDeLosa):
        matriz(tipo, **kw)


def test_validar_elemento_de_losa_normaliza() -> None:
    assert validar_elemento_de_losa(clave="T-1-15x25", modo="ml", cantidad=10.12349, largo_m=None, pago="propio") == {
        "elemento_clave": "T-1-15x25", "modo": "ml", "cantidad": 10.123, "largo_m": None, "pago": "propio",
    }
    with pytest.raises(ErrorDeMatrizDeLosa):
        validar_elemento_de_losa(clave="Z-1", modo="ml", cantidad=1, largo_m=None, pago="propio")


# ── La biblioteca y el concepto nuevo de la losa ────────────────────────────────────────────────────


def test_la_biblioteca_trae_la_categoria_losas_con_los_dos_elementos() -> None:
    cat = next(c for c in BIBLIOTECA if c["clave"] == "losas")
    assert [(s["clave"], [e["clave"] for e in s["elementos"]]) for s in cat["subcategorias"]] == [
        ("maciza", ["LOSA-MACIZA"]), ("nervada", ["LOSA-NERVADA"]),
    ]
    assert elemento_de_losa("LOSA-NERVADA") == "nervada" and elemento_de_losa("T-1-15x25") is None
    assert CLAVES_DE_LOSA == {"maciza": "LOSA-MACIZA", "nervada": "LOSA-NERVADA"}


def test_la_ficha_dice_lo_que_calcula_lo_que_toma_del_catalogo_y_los_pendientes() -> None:
    d = definicion_de_losa("LOSA-MACIZA")
    assert d is not None and d["parrilla"]["clave"] == "AUX-06010" and d["capa_de_compresion_cm"] is None
    assert d["concepto"]["provisional"] is True and d["concepto"]["estado"] == "propuesto"
    assert {x["clave"] for x in d["pendientes"]} >= {"Q49", "L1", "L2", "L3", "L4", "L5"}
    assert len(d["elementos_permitidos"]) == 36 and all(e["tiene_concepto_de_colado"] for e in d["elementos_permitidos"])
    assert definicion_de_losa("LOSA-NERVADA")["parrilla"] is None  # type: ignore[index]
    assert definicion_de_losa("OTRA") is None


@pytest.mark.parametrize("tipo", ["maciza", "nervada"])
def test_el_concepto_nuevo_de_la_losa_es_una_propuesta_con_clave_provisional_sin_precio_ni_destajo(tipo: str) -> None:
    p = concepto_nuevo_de_losa(tipo)
    assert p["clase"] == "concepto_nuevo" and p["elemento_clave"] == CLAVES_DE_LOSA[tipo]
    assert p["concepto_clave"] == CONCEPTOS_DE_LOSA[tipo]["clave"]
    d = p["detalle"]
    assert d["clave_provisional"] is True and d["unidad"] == "m²" and d["cambios"] == []
    assert d["insumos"]["MAD-00001"] == pytest.approx(1.0)
    assert "destajo" not in {k for k in d if k != "motivos"}
    assert any("Sin destajo" in m for m in d["motivos"])
    with pytest.raises(ErrorDeMatrizDeLosa):
        concepto_nuevo_de_losa("curva")
