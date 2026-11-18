"""Zonas de losa (Fase 1): la altura de cada tramo de muro, el enrase y la cara interior o exterior, con geometría pura."""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.cuantificacion.zonas_de_losa import (
    ErrorDeZonaDeLosa,
    LosaEnPlano,
    PuntoDeNivelExterior,
    ZonaDeLosa,
    elegir_altura,
    resolver_muro,
    validar_zona,
)

D = Decimal
Z300 = ZonaDeLosa(id="z3", nombre="Entrepiso 3.00", altura_libre_m=D("3.00"), espesor_m=D("0.12"))
Z420 = ZonaDeLosa(id="z4", nombre="Entrepiso 4.20", altura_libre_m=D("4.20"), espesor_m=D("0.20"))


def _rect(x0: float, y0: float, x1: float, y1: float):  # noqa: ANN202
    return (((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)),)


def _losa(id_: str, zona: str, x0: float, y0: float, x1: float, y1: float, espesor: str | None = None) -> LosaEnPlano:
    return LosaEnPlano(id=id_, zona_id=zona, poligonos=(_rect(x0, y0, x1, y1),), espesor_m=D(espesor) if espesor else None)


# Dos cuartos contiguos de 6 × 4 m: el de 3.00 de x 0 a 6 y el de 4.20 de x 6 a 12 (y de -4 a 0, hacia arriba en pantalla).
LOSAS = [_losa("l3", "z3", 0, -4, 6, 0), _losa("l4", "z4", 6, -4, 12, 0)]
ESTANDAR = D("3.00")


def _r(linea, **kw):  # noqa: ANN001, ANN202
    kw.setdefault("zonas", [Z300, Z420])
    kw.setdefault("losas", LOSAS)
    kw.setdefault("altura_estandar_m", ESTANDAR)
    return resolver_muro(linea, **kw)


def test_un_muro_bajo_la_losa_de_3_toma_su_altura_libre_y_sus_dos_caras_son_interiores() -> None:
    r = _r([(1, -2), (5, -2)])
    assert len(r.tramos) == 1 and not r.parte_el_muro and r.con_zona
    t = r.tramos[0]
    assert (t.altura_m, t.origen_de_altura) == (D("3.000"), "zona")
    assert (t.lado_a.cara, t.lado_b.cara) == ("interior", "interior")
    assert t.lado_a.zona == "Entrepiso 3.00" and t.lado_b.espesor_m == D("0.12")
    assert t.enrase is None and [p["rol"] for p in t.partes] == ["cuerpo"]


def test_el_muro_que_cruza_el_limite_entre_zonas_se_parte_en_tramos_con_su_altura() -> None:
    r = _r([(2, -2), (10, -2)])
    assert r.parte_el_muro
    assert [(t.desde_m, t.hasta_m, t.altura_m) for t in r.tramos] == [
        (D("0.000"), D("4.000"), D("3.000")),
        (D("4.000"), D("8.000"), D("4.200")),
    ]
    assert [t.lado_a.zona for t in r.tramos] == ["Entrepiso 3.00", "Entrepiso 4.20"]
    assert sum(t.longitud_m for t in r.tramos) == D("8.000")


def test_un_vertice_dentro_de_la_misma_zona_no_parte_el_muro() -> None:
    r = _r([(1, -1), (3, -1), (5, -3)])
    assert len(r.tramos) == 1 and not r.parte_el_muro


def test_el_muro_en_el_limite_entre_3_y_4_20_lleva_enrase_y_cada_cara_su_altura() -> None:
    # Camina de x=0 a x=12 sobre y=-4: encima nada; probamos un muro vertical sobre x=6 (el límite) de y=-4 a y=0.
    r = _r([(6, 0), (6, -4)])
    t = r.tramos[0]
    # Dibujado hacia arriba (y decrece): la izquierda en pantalla es x menor (la losa de 3.00).
    assert (t.lado_a.zona, t.lado_b.zona) == ("Entrepiso 3.00", "Entrepiso 4.20")
    assert (t.lado_a.altura_m, t.lado_b.altura_m) == (D("3.000"), D("4.200"))
    assert t.altura_m == D("4.200") and t.origen_de_altura == "zona"
    assert t.enrase == {"desde_m": D("3.000"), "hasta_m": D("4.200")}
    cuerpo, enrase = t.partes
    assert (cuerpo["rol"], cuerpo["desde_m"], cuerpo["hasta_m"]) == ("cuerpo", D(0), D("3.000"))
    assert (cuerpo["cara_a"], cuerpo["cara_b"]) == ("interior", "interior")
    # Altura por cara: el lado de la losa baja (A, 3.00) es exterior de 3.00 a 4.20; el de la losa alta (B, 4.20) sigue interior.
    # La losa más baja solo SUGIERE: nada queda aplicado.
    assert (enrase["rol"], enrase["cara_a"], enrase["cara_b"]) == ("enrase", "exterior", "interior")
    assert [s["indice"] for s in t.sugerencias] == [1]
    assert r.aplicada is False


def test_la_cara_a_es_la_izquierda_del_sentido_de_dibujo_con_y_hacia_abajo() -> None:
    # Losa solo arriba (y de -4 a 0). De izquierda a derecha, la izquierda en pantalla es hacia arriba (y menor): cara A.
    solo_arriba = [_losa("l", "z3", 0, -4, 6, 0)]
    ida = _r([(1, 0), (5, 0)], losas=solo_arriba).tramos[0]
    assert (ida.lado_a.cara, ida.lado_b.cara) == ("interior", "exterior")
    vuelta = _r([(5, 0), (1, 0)], losas=solo_arriba).tramos[0]
    assert (vuelta.lado_a.cara, vuelta.lado_b.cara) == ("exterior", "interior")


def test_con_losa_de_un_solo_lado_el_otro_es_exterior_y_su_altura_es_la_del_lado_cubierto() -> None:
    t = _r([(1, 0), (5, 0)], losas=[_losa("l", "z3", 0, -4, 6, 0)]).tramos[0]
    assert t.lado_b.origen == "sin_losa" and t.lado_b.altura_m == D("3.000")
    assert t.altura_m == D("3.000")


def test_un_punto_de_nivel_exterior_confirma_la_cara_exterior_y_fija_la_altura_de_esa_cara() -> None:
    punto = PuntoDeNivelExterior(id="p1", x=3, y=1.5, cota_m=D("-0.30"), rotulo="Banqueta")
    t = _r([(1, 0), (5, 0)], losas=[_losa("l", "z3", 0, -4, 6, 0)], puntos_de_nivel=[punto]).tramos[0]
    assert t.lado_b.origen == "punto_de_nivel" and t.lado_b.cara == "exterior"
    assert (t.lado_b.nivel_exterior_m, t.lado_b.rotulo_del_punto) == (D("-0.30"), "Banqueta")
    assert t.lado_b.altura_m == D("3.300")  # de la banqueta (-0.30) al nivel bajo de la losa (3.00)
    # El punto lejano no cuenta.
    lejos = PuntoDeNivelExterior(id="p2", x=40, y=40, cota_m=D("-1"))
    assert _r([(1, 0), (5, 0)], losas=[_losa("l", "z3", 0, -4, 6, 0)], puntos_de_nivel=[lejos]).tramos[0].lado_b.origen == "sin_losa"


def test_prioridad_de_la_altura_explicita_zona_y_driver() -> None:
    assert elegir_altura(explicita_m=D("2.4"), de_zona_m=D("3"), estandar_m=D("2.6")) == (D("2.4"), "trazo")
    assert elegir_altura(explicita_m=None, de_zona_m=D("3"), estandar_m=D("2.6")) == (D("3"), "zona")
    assert elegir_altura(explicita_m=None, de_zona_m=None, estandar_m=D("2.6")) == (D("2.6"), "driver")
    r = _r([(1, -2), (5, -2)], altura_explicita_m=D("2.50"))
    assert r.tramos[0].altura_m == D("2.500") and r.tramos[0].origen_de_altura == "trazo"
    assert r.tramos[0].partes == () and any("manda" in a for a in r.advertencias)


def test_un_muro_sin_zona_se_comporta_como_hoy() -> None:
    r = _r([(20, 20), (25, 20)])
    t = r.tramos[0]
    assert not r.con_zona and not r.parte_el_muro
    assert (t.altura_m, t.origen_de_altura, t.lado_a.cara, t.lado_b.cara) == (D("3.000"), "driver", None, None)
    assert t.partes == () and t.enrase is None
    sin_zonas = _r([(1, -2), (5, -2)], zonas=[], losas=[], altura_estandar_m=D("2.60"))
    assert (sin_zonas.tramos[0].altura_m, sin_zonas.tramos[0].origen_de_altura) == (D("2.600"), "driver")
    assert _r([(20, 20), (25, 20)], altura_explicita_m=D("2.2")).tramos[0].origen_de_altura == "trazo"


def test_una_subzona_trae_su_espesor_estructural_y_varias_losas_comparten_la_zona() -> None:
    losas = [_losa("l1", "z3", 0, -4, 3, 0), _losa("l2", "z3", 3, -4, 6, 0, espesor="0.15")]
    a = _r([(1, -2), (2, -2)], losas=losas).tramos[0]
    b = _r([(4, -2), (5, -2)], losas=losas).tramos[0]
    assert (a.lado_a.espesor_m, b.lado_a.espesor_m) == (D("0.12"), D("0.15"))
    assert a.lado_a.cota_superior_m == D("3.120") and b.lado_a.cota_superior_m == D("3.150")
    # Una sola zona a lo largo de todo el muro: las dos losas no lo parten.
    todo = _r([(1, -2), (5, -2)], losas=losas)
    assert not todo.parte_el_muro and todo.tramos[0].altura_m == D("3.000")


def test_las_cotas_se_miden_desde_el_piso_terminado_de_cada_zona() -> None:
    alta = ZonaDeLosa(id="zp", nombre="Planta alta", altura_libre_m=D("2.60"), espesor_m=D("0.12"), cota_piso_m=D("3.12"))
    t = resolver_muro(
        [(1, -2), (5, -2)], zonas=[alta], losas=[_losa("l", "zp", 0, -4, 6, 0)], altura_estandar_m=ESTANDAR
    ).tramos[0]
    assert t.altura_m == D("2.600")
    assert (t.lado_a.cota_inferior_m, t.lado_a.cota_superior_m) == (D("5.720"), D("5.840"))


def test_un_hueco_de_la_losa_no_cuenta_como_losa() -> None:
    con_hueco = LosaEnPlano(
        id="l", zona_id="z3", poligonos=((((0, -4), (6, -4), (6, 0), (0, 0), (0, -4)), ((2, -3), (4, -3), (4, -1), (2, -1), (2, -3))),)
    )
    t = _r([(1, -2), (5, -2)], losas=[con_hueco]).tramos[0:]
    # El eje pasa por el hueco: el tramo se parte a su paso y la parte del hueco queda sin losa a sus lados.
    assert [x.lado_a.origen for x in t] == ["losa", "sin_zona", "losa"]


def test_losas_encimadas_de_zonas_distintas_toman_la_mas_baja_y_avisan() -> None:
    r = _r([(1, -2), (5, -2)], losas=[_losa("l3", "z3", 0, -4, 6, 0), _losa("l4", "z4", 0, -4, 6, 0)])
    assert r.tramos[0].altura_m == D("3.000")
    assert any("encimadas" in a for a in r.advertencias)


def test_un_muro_degenerado_o_sin_puntos_se_rechaza() -> None:
    with pytest.raises(ErrorDeZonaDeLosa):
        _r([(1, 1)])
    with pytest.raises(ErrorDeZonaDeLosa):
        _r([(1, 1), (1, 1)])


def test_validar_zona_normaliza_y_rechaza() -> None:
    ok = validar_zona(nombre="  Zona 3.00 ", altura_libre_m="3", espesor_m="0.12", nivel=" PB ")
    assert ok == {
        "nombre": "Zona 3.00", "nivel": "PB", "cota_piso_m": D("0.000"), "altura_libre_m": D("3.000"), "espesor_m": D("0.120"),
    }
    for mal in (
        {"nombre": " ", "altura_libre_m": 3, "espesor_m": 0.1},
        {"nombre": "x", "altura_libre_m": 0, "espesor_m": 0.1},
        {"nombre": "x", "altura_libre_m": 31, "espesor_m": 0.1},
        {"nombre": "x", "altura_libre_m": 3, "espesor_m": 0},
        {"nombre": "x", "altura_libre_m": 3, "espesor_m": 4},
        {"nombre": "x", "altura_libre_m": 3, "espesor_m": 0.1, "cota_piso_m": 500},
        {"nombre": "x", "altura_libre_m": "tres", "espesor_m": 0.1},
        {"nombre": "x", "altura_libre_m": "NaN", "espesor_m": 0.1},
    ):
        with pytest.raises(ErrorDeZonaDeLosa):
            validar_zona(**mal)


def test_los_tramos_para_la_conversion_son_contiguos_y_unen_lo_que_mide_igual() -> None:
    from obractrl.domain.cuantificacion.zonas_de_losa import tramos_para_conversion

    r = _r([(2, -2), (10, -2)])
    assert tramos_para_conversion(r) == [
        {"desde_m": 0.0, "hasta_m": 4.0, "alt": 3.0},
        {"desde_m": 4.0, "hasta_m": 8.0, "alt": 4.2},
    ]
    # Un vértice dentro de la misma zona no parte los tramos.
    assert tramos_para_conversion(_r([(1, -1), (3, -1), (5, -3)])) == [{"desde_m": 0.0, "hasta_m": 4.828, "alt": 3.0}]
    # En el límite: un solo tramo con partes (cuerpo y enrase) y sus caras.
    limite = tramos_para_conversion(_r([(6, 0), (6, -4)]))
    assert len(limite) == 1 and [p["rol"] for p in limite[0]["partes"]] == ["cuerpo", "enrase"]
    assert (limite[0]["partes"][1]["cara_a"], limite[0]["partes"][1]["cara_b"]) == ("exterior", "interior")
