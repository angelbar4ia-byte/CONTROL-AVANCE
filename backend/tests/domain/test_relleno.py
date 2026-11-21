"""El relleno como elemento (Fase 3 de las zonas de losa): cálculo, conciliación con ALB-03014, conceptos, espacio y lo que no se cuenta dos veces."""

from __future__ import annotations

import pytest

from obractrl.domain.cuantificacion.biblioteca_de_elementos import (
    BIBLIOTECA,
    elemento_de_la_biblioteca,
)
from obractrl.domain.cuantificacion.relleno import (
    CLAVES_DE_RELLENO,
    CONCEPTO_AZOTEA,
    CONCEPTOS_DE_RELLENO,
    DEFECTOS,
    ESPESOR_DEL_CATALOGO_M,
    MORTERO_AZOTEA,
    TEZONTLE,
    EntradaRelleno,
    ErrorDeRelleno,
    PoligonoDeRelleno,
    calcular_relleno,
    categorias_de_biblioteca,
    concepto_nuevo_de_relleno,
    definicion_de_relleno,
    elemento_de_relleno,
    solapes_de_rellenos,
    validar_parametros,
)


def _azotea(poligonos: list[PoligonoDeRelleno] | None = None, **kw: object) -> dict:
    return calcular_relleno(
        EntradaRelleno(
            tipo="azotea", espesor_de_la_zona_m=0.12, poligonos=poligonos if poligonos is not None else [PoligonoDeRelleno(area_m2=100.0)],
            **{**DEFECTOS["azotea"], **kw},  # type: ignore[arg-type]
        )
    )


def test_el_espesor_de_omision_de_la_azotea_es_el_que_implica_el_catalogo() -> None:
    # 0.012857 viaje de 7 m³ por m² son 0.09 m³ por m²: 9 cm.
    assert TEZONTLE["por_m2_del_catalogo"] * TEZONTLE["m3_por_viaje"] == pytest.approx(ESPESOR_DEL_CATALOGO_M, abs=1e-5)
    assert DEFECTOS["azotea"]["espesor_m"] == ESPESOR_DEL_CATALOGO_M
    assert DEFECTOS["azotea"]["mortero_m3_por_m2"] == MORTERO_AZOTEA["por_m2_del_catalogo"]


def test_sin_pendiente_ni_subzonas_la_azotea_reproduce_la_composicion_del_catalogo_por_m2() -> None:
    r = _azotea()
    assert r["area_m2"] == 100.0 and r["volumen_m3"] == pytest.approx(9.0) and r["espesor_medio_m"] == pytest.approx(0.09)
    por_clave = {i["clave"]: i["cantidad"] for i in r["insumos"]}
    assert por_clave["PET-00069"] / 100 == pytest.approx(TEZONTLE["por_m2_del_catalogo"], abs=1e-5)  # viajes por m²
    assert por_clave["CON-00020"] / 100 == pytest.approx(0.0735)
    [c] = r["conceptos"]
    # F7: el relleno de azotea se liga a un concepto que YA existe en el catálogo; no hay concepto nuevo.
    assert c["concepto"] == {**CONCEPTO_AZOTEA, "estado": "catalogo", "provisional": False}
    assert (c["cantidad"], c["unidad"]) == (100.0, "m²")
    assert r["mano_de_obra"]["estado"] == "sin_mano_de_obra" and r["mano_de_obra"]["destajos_candidatos"][0]["clave"] == "MOA-05012"
    assert r["advertencias"] == []


def test_la_pendiente_suma_una_cuna_y_sin_recorrido_no_suma_nada() -> None:
    r = _azotea(pendiente_pct=2.0, recorrido_m=5.0)
    assert r["extra_de_pendiente_m"] == pytest.approx(0.05)  # 2 % × 5 m / 2
    assert r["volumen_m3"] == pytest.approx(100 * (0.09 + 0.05))
    sin_recorrido = _azotea(pendiente_pct=2.0)
    assert sin_recorrido["volumen_m3"] == pytest.approx(9.0)
    assert any("no suma volumen" in a for a in sin_recorrido["advertencias"])
    assert any("no suma volumen" in a for a in _azotea(recorrido_m=3.0)["advertencias"])


def test_el_relleno_se_adapta_a_los_espesores_estructurales_distintos_de_la_zona() -> None:
    cuartos = [PoligonoDeRelleno(area_m2=24.0, id="a"), PoligonoDeRelleno(area_m2=8.0, espesor_de_losa_m=0.20, id="b")]
    r = _azotea(cuartos)
    a, b = r["poligonos"]
    assert (a["compensacion_m"], b["compensacion_m"]) == (pytest.approx(0.08), 0.0)  # la subzona gruesa fija el mínimo; la delgada recibe la diferencia
    assert (a["espesor_m"], b["espesor_m"]) == (pytest.approx(0.17), pytest.approx(0.09))
    assert r["volumen_m3"] == pytest.approx(24 * 0.17 + 8 * 0.09)
    assert any("espesores estructurales" in x for x in r["advertencias"])
    # Apagar la compensación deja el espesor mínimo en todos.
    sin = _azotea(cuartos, compensar_espesores=False)
    assert sin["volumen_m3"] == pytest.approx(32 * 0.09) and all(p["compensacion_m"] == 0 for p in sin["poligonos"])


def test_un_relleno_de_un_poligono_compensa_contra_la_losa_mas_gruesa_de_toda_la_zona() -> None:
    solo_el_cuarto = calcular_relleno(
        EntradaRelleno(
            tipo="azotea", espesor_de_la_zona_m=0.12, poligonos=[PoligonoDeRelleno(area_m2=24.0)], espesor_maximo_de_la_zona_m=0.20,
            **DEFECTOS["azotea"],  # type: ignore[arg-type]
        )
    )
    assert solo_el_cuarto["poligonos"][0]["compensacion_m"] == pytest.approx(0.08) and solo_el_cuarto["espesor_maximo_de_la_zona_m"] == 0.20


def test_el_compactado_se_paga_por_m3_con_un_concepto_propuesto_y_el_abundamiento_da_el_suelto() -> None:
    r = calcular_relleno(
        EntradaRelleno(tipo="compactado", espesor_de_la_zona_m=0.12, poligonos=[PoligonoDeRelleno(area_m2=50.0)], **{**DEFECTOS["compactado"], "abundamiento_pct": 25.0})  # type: ignore[arg-type]
    )
    assert r["volumen_m3"] == pytest.approx(5.0) and r["volumen_suelto_m3"] == pytest.approx(6.25) and r["insumos"] == []
    [c] = r["conceptos"]
    assert c["concepto"] == {
        "clave": "EJ-810", "descripcion": CONCEPTOS_DE_RELLENO["compactado"]["descripcion"], "unidad": "m³", "estado": "propuesto", "provisional": True,
    }
    assert (c["cantidad"], c["unidad"]) == (pytest.approx(5.0), "m³")
    assert any("R4" in a for a in r["advertencias"])


def test_por_omision_no_hay_abundamiento_ni_pendiente_y_el_catalogo_no_trae_factor() -> None:
    for d in DEFECTOS.values():
        assert d["abundamiento_pct"] == 0.0 and d["pendiente_pct"] == 0.0 and d["recorrido_m"] == 0.0


def test_cada_poligono_cae_en_un_solo_espacio_y_la_suma_de_los_grupos_es_el_total() -> None:
    r = _azotea(
        [
            PoligonoDeRelleno(area_m2=12.0, espacio_id="rec"), PoligonoDeRelleno(area_m2=8.0, espacio_id="ban"),
            PoligonoDeRelleno(area_m2=5.0), PoligonoDeRelleno(area_m2=3.0, espacio_id="rec"),
        ]
    )
    grupos = {g["espacio_id"]: g for g in r["por_espacio"]}
    assert set(grupos) == {"rec", "ban", None} and r["por_espacio"][0]["espacio_id"] is None  # «sin espacio» va primero
    assert grupos["rec"]["area_m2"] == 15.0 and grupos["ban"]["area_m2"] == 8.0 and grupos[None]["area_m2"] == 5.0
    assert sum(g["conceptos"][0]["cantidad"] for g in r["por_espacio"]) == pytest.approx(r["conceptos"][0]["cantidad"])
    assert sum(g["volumen_m3"] for g in r["por_espacio"]) == pytest.approx(r["volumen_m3"])


def test_el_espacio_del_relleno_manda_sobre_el_de_sus_poligonos() -> None:
    r = calcular_relleno(
        EntradaRelleno(
            tipo="azotea", espesor_de_la_zona_m=0.12, poligonos=[PoligonoDeRelleno(area_m2=12.0, espacio_id="rec"), PoligonoDeRelleno(area_m2=8.0)],
            espacio_id="ban", **DEFECTOS["azotea"],  # type: ignore[arg-type]
        )
    )
    assert [g["espacio_id"] for g in r["por_espacio"]] == ["ban"] and r["por_espacio"][0]["area_m2"] == 20.0


def test_una_zona_sin_poligonos_avisa_y_mide_cero() -> None:
    r = _azotea([])
    assert r["area_m2"] == 0 and r["volumen_m3"] == 0 and r["por_espacio"] == [] and any("ningún polígono" in a for a in r["advertencias"])


def test_los_datos_que_no_valen_se_rechazan() -> None:
    for campo, valor in (("espesor_m", -0.1), ("espesor_m", 3.0), ("pendiente_pct", 31), ("recorrido_m", -1), ("abundamiento_pct", 61), ("mortero_m3_por_m2", 0.6)):
        with pytest.raises(ErrorDeRelleno):
            validar_parametros("compactado", {campo: valor})
    with pytest.raises(ErrorDeRelleno, match="abundamiento"):
        validar_parametros("azotea", {"abundamiento_pct": 5})
    with pytest.raises(ErrorDeRelleno, match="mortero"):
        validar_parametros("compactado", {"mortero_m3_por_m2": 0.07})
    with pytest.raises(ErrorDeRelleno):
        validar_parametros("zanja", {})
    with pytest.raises(ErrorDeRelleno):
        validar_parametros("azotea", {"espesor_m": "mucho"})
    with pytest.raises(ErrorDeRelleno):
        calcular_relleno(EntradaRelleno(tipo="azotea", espesor_de_la_zona_m=0, **DEFECTOS["azotea"]))  # type: ignore[arg-type]
    with pytest.raises(ErrorDeRelleno):
        _azotea([PoligonoDeRelleno(area_m2=-1)])
    with pytest.raises(ErrorDeRelleno):
        _azotea([PoligonoDeRelleno(area_m2=1, espesor_de_losa_m=0)])


def test_los_parametros_que_faltan_toman_los_de_omision_del_tipo() -> None:
    assert validar_parametros("azotea", {}) == DEFECTOS["azotea"]
    assert validar_parametros("compactado", {"espesor_m": None, "recorrido_m": 4})["espesor_m"] == DEFECTOS["compactado"]["espesor_m"]


def test_dos_rellenos_que_cubren_lo_mismo_se_detectan() -> None:
    entera = {"id": 1, "elemento_clave": "REL-AZOTEA", "trazo_id": None}
    assert solapes_de_rellenos([entera]) == []
    assert solapes_de_rellenos([entera, {"id": 2, "elemento_clave": "REL-COMPACTADO", "trazo_id": None}]) == []  # otro elemento no se pisa
    assert solapes_de_rellenos([entera, {"id": 2, "elemento_clave": "REL-AZOTEA", "trazo_id": "p1"}])
    assert solapes_de_rellenos([entera, {"id": 2, "elemento_clave": "REL-AZOTEA", "trazo_id": None}])
    p1 = {"id": 3, "elemento_clave": "REL-AZOTEA", "trazo_id": "p1"}
    assert solapes_de_rellenos([p1, {"id": 4, "elemento_clave": "REL-AZOTEA", "trazo_id": "p2"}]) == []
    assert solapes_de_rellenos([p1, {"id": 5, "elemento_clave": "REL-AZOTEA", "trazo_id": "p1"}])


def test_la_biblioteca_trae_la_categoria_de_rellenos_con_sus_dos_elementos() -> None:
    assert CLAVES_DE_RELLENO == {"azotea": "REL-AZOTEA", "compactado": "REL-COMPACTADO"}
    [cat] = categorias_de_biblioteca()
    claves = [e["clave"] for s in cat["subcategorias"] for e in s["elementos"]]
    assert cat["clave"] == "rellenos" and cat["nombre"] == "Rellenos" and claves == ["REL-AZOTEA", "REL-COMPACTADO"]
    en_la_biblioteca = {c["clave"]: c for c in BIBLIOTECA}
    assert "rellenos" in en_la_biblioteca and "losas" in en_la_biblioteca  # el relleno es una familia aparte de la losa
    for k in claves:
        assert elemento_de_relleno(k) is not None
        assert elemento_de_la_biblioteca(k) is None  # no es un muro de piedra: lo atienden sus rutas propias
    assert elemento_de_relleno("LOSA-MACIZA") is None


def test_la_ficha_dice_el_concepto_lo_que_toma_del_catalogo_y_los_pendientes() -> None:
    a = definicion_de_relleno("REL-AZOTEA")
    assert a is not None and a["concepto"]["clave"] == "ALB-03014" and a["concepto"]["estado"] == "catalogo" and a["concepto"]["provisional"] is False
    assert a["tezontle"]["clave"] == "PET-00069" and a["mortero"]["clave"] == "CON-00020" and a["destajos_candidatos"][0]["clave"] == "MOA-05012"
    c = definicion_de_relleno("REL-COMPACTADO")
    assert c is not None and c["concepto"]["clave"] == "EJ-810" and c["concepto"]["provisional"] is True and c["tezontle"] is None and c["destajos_candidatos"] == []
    assert {p["clave"] for p in a["pendientes"]} >= {"R1", "R2", "R3", "R4"}
    assert definicion_de_relleno("LOSA-MACIZA") is None


def test_solo_el_compactado_necesita_un_concepto_nuevo_y_no_trae_precio_ni_destajo() -> None:
    p = concepto_nuevo_de_relleno()
    assert (p["elemento_clave"], p["concepto_clave"], p["clase"]) == ("REL-COMPACTADO", "EJ-810", "concepto_nuevo")
    d = p["detalle"]
    assert d["clave_provisional"] is True and d["unidad"] == "m³" and d["insumos"] == {} and "precio" not in d and "destajo" not in d
    assert any("F7" in m for m in d["motivos"])
    with pytest.raises(ErrorDeRelleno, match="ALB-03014"):
        concepto_nuevo_de_relleno("azotea")


def test_el_calculo_no_lee_ningun_driver_de_la_obra() -> None:
    # No hay entrada de drivers: el mismo cálculo da lo mismo siempre (consumidores_de_drivers no necesita registrar el relleno).
    assert _azotea() == _azotea()
    assert "drivers" not in EntradaRelleno.__dataclass_fields__
