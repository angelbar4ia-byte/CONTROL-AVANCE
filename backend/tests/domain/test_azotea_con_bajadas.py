"""El relleno dinámico de azotea: espesor de arenilla según las bajadas, su integral numérica determinista, su error y las guías (líneas de pendiente e hilos de nivel)."""

from __future__ import annotations

import math

import pytest

from obractrl.domain.cuantificacion.azotea_con_bajadas import (
    CELDAS_FINAS,
    ESPESOR_EN_BAJADA_M,
    ESPESOR_MORTERO_M,
    PENDIENTE_POR_OMISION_PCT,
    Bajada,
    area_de_poligono,
    distancia_al_borde,
    distancia_de_drenaje,
    espesor_de_arenilla,
    guias_de_pendiente,
    integrar_arenilla,
    punto_en_zona,
)
from obractrl.domain.cuantificacion.relleno import (
    CONCEPTO_ARENILLA,
    DEFECTOS,
    EntradaRelleno,
    ErrorDeRelleno,
    PoligonoDeRelleno,
    calcular_relleno,
    concepto_nuevo_de_arenilla,
    definicion_de_relleno,
    validar_parametros,
)


def _rect(x0: float, y0: float, x1: float, y1: float):
    return (((x0, y0), (x1, y0), (x1, y1), (x0, y1)),)


def _referencia_ingenua(poligono, bajadas, pendiente_pct: float, n: int = 700) -> float:
    """El volumen por fuerza bruta (una retícula de n×n sobre la caja) para comparar: independiente del barrido por filas del módulo."""
    xs = [p[0] for p in poligono[0]]
    ys = [p[1] for p in poligono[0]]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    hx, hy = (x1 - x0) / n, (y1 - y0) / n
    suma = 0.0
    for i in range(n):
        for j in range(n):
            c = (x0 + (i + 0.5) * hx, y0 + (j + 0.5) * hy)
            if punto_en_zona(c, [poligono]):
                suma += espesor_de_arenilla(c, bajadas, pendiente_pct=pendiente_pct)
                suma -= 0.0
    # Solo sirve con polígonos cuya área por celdas es la exacta (rectángulos y rectángulos con hueco alineado): cada celda pesa hx × hy.
    return suma * hx * hy


def test_los_valores_por_omision_son_los_del_usuario_y_la_pendiente_un_conservador_editable() -> None:
    assert (ESPESOR_EN_BAJADA_M, ESPESOR_MORTERO_M) == (0.05, 0.05)
    assert PENDIENTE_POR_OMISION_PCT == 2.0
    assert DEFECTOS["azotea"]["pendiente_zona_pct"] == 2.0 and DEFECTOS["azotea"]["espesor_bajada_m"] == 0.05 and DEFECTOS["azotea"]["mortero_espesor_m"] == 0.05
    assert DEFECTOS["azotea"]["factor_abundamiento"] == 1.0 and DEFECTOS["compactado"]["factor_abundamiento"] == 1.0


def test_el_espesor_es_5_cm_en_la_bajada_y_sube_con_la_pendiente_por_la_distancia() -> None:
    b = [Bajada("1", 0.0, 0.0)]
    assert espesor_de_arenilla((0.0, 0.0), b, pendiente_pct=2.0) == pytest.approx(0.05)  # 5 cm mínimo en la bajada
    assert espesor_de_arenilla((3.0, 4.0), b, pendiente_pct=2.0) == pytest.approx(0.05 + 0.02 * 5.0)
    assert espesor_de_arenilla((3.0, 4.0), b, pendiente_pct=0.0) == pytest.approx(0.05)
    assert espesor_de_arenilla((3.0, 4.0), b, pendiente_pct=2.0, compensacion_m=0.08) == pytest.approx(0.05 + 0.10 + 0.08)
    with pytest.raises(ValueError, match="Sin bajadas"):
        espesor_de_arenilla((0.0, 0.0), [], pendiente_pct=2.0)


def test_cada_punto_lo_drena_la_bajada_mas_cercana() -> None:
    b = [Bajada("1", 0.0, 0.0), Bajada("2", 10.0, 0.0)]
    assert espesor_de_arenilla((2.0, 0.0), b, pendiente_pct=2.0) == pytest.approx(0.05 + 0.02 * 2.0)
    assert espesor_de_arenilla((8.0, 0.0), b, pendiente_pct=2.0) == pytest.approx(0.05 + 0.02 * 2.0)
    assert espesor_de_arenilla((5.0, 0.0), b, pendiente_pct=2.0) == pytest.approx(0.05 + 0.02 * 5.0)  # la mediatriz: el máximo entre las dos


def test_el_volumen_de_un_cuadrado_con_la_bajada_en_la_esquina_coincide_con_la_integral_exacta() -> None:
    # ∬ r dA sobre [0,a]² con la bajada en una esquina = a³ (√2 + ln(1 + √2)) / 3.
    a, pend = 10.0, 2.0
    exacto = a * a * 0.05 + pend / 100 * a**3 * (math.sqrt(2) + math.log(1 + math.sqrt(2))) / 3
    r = integrar_arenilla([(_rect(0, 0, a, a), 0.0)], [Bajada("1", 0.0, 0.0)], pendiente_pct=pend)
    assert r.area_m2 == pytest.approx(100.0)  # el área es la exacta, no la de las celdas
    assert r.volumen_m3 == pytest.approx(exacto, rel=1e-3)
    # El error estimado acota el error real, y es pequeño frente al volumen (documentado: menos de 0.1 %).
    assert abs(r.volumen_m3 - exacto) <= r.error_estimado_m3 * 2 + 1e-9
    assert r.error_estimado_m3 / r.volumen_m3 < 1e-3
    assert r.espesor_medio_m == pytest.approx(exacto / 100, rel=1e-3)
    assert r.espesor_maximo_m == pytest.approx(0.05 + 0.02 * a * math.sqrt(2), rel=1e-2)


def test_sin_pendiente_el_volumen_es_el_area_por_5_cm_y_sin_pendiente_no_hay_hilos() -> None:
    poligono = _rect(0, 0, 12.5, 8.0)
    b = [Bajada("1", 3.0, 3.0)]
    r = integrar_arenilla([(poligono, 0.0)], b, pendiente_pct=0.0)
    assert r.volumen_m3 == pytest.approx(100.0 * 0.05) and r.error_estimado_m3 == pytest.approx(0.0, abs=1e-12)
    guias = guias_de_pendiente([poligono], b, r, pendiente_pct=0.0, espesor_en_bajada_m=0.05)
    assert [g["tipo"] for g in guias] == ["pendiente"]  # solo la línea de pendiente generada: sin pendiente no hay nivel que cambie


def test_con_dos_bajadas_la_zona_se_reparte_y_el_volumen_es_menor_que_con_una() -> None:
    poligono = _rect(0, 0, 20, 10)
    una = integrar_arenilla([(poligono, 0.0)], [Bajada("1", 0.0, 5.0)], pendiente_pct=2.0)
    dos = integrar_arenilla([(poligono, 0.0)], [Bajada("1", 0.0, 5.0), Bajada("2", 20.0, 5.0)], pendiente_pct=2.0)
    assert dos.volumen_m3 < una.volumen_m3
    assert dos.por_bajada["1"]["area_m2"] == pytest.approx(100.0, rel=1e-2) and dos.por_bajada["2"]["area_m2"] == pytest.approx(100.0, rel=1e-2)
    assert dos.por_bajada["1"]["area_m2"] + dos.por_bajada["2"]["area_m2"] == pytest.approx(200.0)  # nada se cuenta dos veces: la suma es el área
    # Contra una referencia independiente por fuerza bruta.
    ref = _referencia_ingenua(poligono, [Bajada("1", 0.0, 5.0), Bajada("2", 20.0, 5.0)], 2.0)
    assert dos.volumen_m3 == pytest.approx(ref, rel=2e-3)


def test_un_hueco_no_se_rellena_ni_cuenta_en_el_area() -> None:
    con_hueco = ((( 0, 0), (20, 0), (20, 10), (0, 10)), ((5, 3), (9, 3), (9, 7), (5, 7)))
    assert area_de_poligono(con_hueco) == pytest.approx(200.0 - 16.0)
    b = [Bajada("1", 0.0, 5.0)]
    r = integrar_arenilla([(con_hueco, 0.0)], b, pendiente_pct=2.0)
    assert r.area_m2 == pytest.approx(184.0)
    ref = _referencia_ingenua(con_hueco, b, 2.0)
    assert r.volumen_m3 == pytest.approx(ref, rel=3e-3)
    assert not punto_en_zona((7.0, 5.0), [con_hueco]) and punto_en_zona((2.0, 5.0), [con_hueco])


def test_la_integral_es_determinista_y_afina_los_poligonos_muy_delgados() -> None:
    p = _rect(0, 0, 40, 0.3)  # una franja de 30 cm: la retícula se afina hasta que caen centros
    b = [Bajada("1", 0.0, 0.15)]
    a = integrar_arenilla([(p, 0.0)], b, pendiente_pct=2.0)
    c = integrar_arenilla([(p, 0.0)], b, pendiente_pct=2.0)
    assert a == c and a.muestras >= 25
    assert a.volumen_m3 == pytest.approx(12.0 * 0.05 + 0.02 * 0.3 * 40**2 / 2, rel=1e-2)


def test_el_error_baja_al_afinar_y_el_paso_es_el_de_las_10000_celdas() -> None:
    poligono = _rect(0, 0, 10, 10)
    r = integrar_arenilla([(poligono, 0.0)], [Bajada("1", 0.0, 0.0)], pendiente_pct=2.0)
    assert r.celda_m == pytest.approx(math.sqrt(100.0 / CELDAS_FINAS), rel=1e-6)
    assert r.muestras == pytest.approx(CELDAS_FINAS, rel=0.02)


def test_la_compensacion_de_una_subzona_se_suma_al_espesor_de_toda_la_subzona() -> None:
    poligono = _rect(0, 0, 10, 10)
    b = [Bajada("1", 0.0, 0.0)]
    sin = integrar_arenilla([(poligono, 0.0)], b, pendiente_pct=2.0)
    con = integrar_arenilla([(poligono, 0.08)], b, pendiente_pct=2.0)
    assert con.volumen_m3 - sin.volumen_m3 == pytest.approx(100 * 0.08)


def test_con_una_linea_trazada_el_agua_baja_a_la_linea_y_corre_por_ella() -> None:
    linea = Bajada("1", 10.0, 0.0, linea=((0.0, 0.0), (10.0, 0.0)))  # dibujada hacia la bajada
    # Un punto sobre la línea a 4 m de su arranque: le faltan 6 m hasta la bajada.
    assert distancia_de_drenaje((4.0, 0.0), linea) == pytest.approx(6.0)
    # Un punto a 3 m de la línea (perpendicular) suma esos 3 m.
    assert distancia_de_drenaje((4.0, 3.0), linea) == pytest.approx(3.0 + 6.0)
    # Sin línea es la distancia en línea recta.
    assert distancia_de_drenaje((4.0, 3.0), Bajada("1", 10.0, 0.0)) == pytest.approx(math.hypot(6.0, 3.0))
    poligono = _rect(0, 0, 10, 6)
    recta = integrar_arenilla([(poligono, 0.0)], [Bajada("1", 10.0, 0.0)], pendiente_pct=2.0)
    guiada = integrar_arenilla([(poligono, 0.0)], [linea], pendiente_pct=2.0)
    assert guiada.volumen_m3 > recta.volumen_m3  # rodear por la línea nunca acorta el recorrido


def test_las_guias_son_una_linea_de_pendiente_por_bajada_y_hilos_de_nivel_con_espesor_constante() -> None:
    poligono = _rect(0, 0, 10, 10)
    b = [Bajada("1", 0.0, 0.0)]
    r = integrar_arenilla([(poligono, 0.0)], b, pendiente_pct=2.0)
    guias = guias_de_pendiente([poligono], b, r, pendiente_pct=2.0, espesor_en_bajada_m=0.05)
    [pendiente] = [g for g in guias if g["tipo"] == "pendiente"]
    assert pendiente["origen"] == "generada" and pendiente["puntos"][-1] == [0.0, 0.0]  # termina en la bajada
    lejos = pendiente["puntos"][0]
    assert math.hypot(*lejos) == pytest.approx(math.hypot(10, 10), rel=0.02)  # arranca en el punto más lejano que drena
    hilos = [g for g in guias if g["tipo"] == "hilo"]
    assert len(hilos) >= 10  # uno por metro de drenaje hasta la esquina lejana (14.1 m)
    for h in hilos:
        for x, y in h["puntos"]:
            assert punto_en_zona((x, y), [poligono]) or distancia_al_borde((x, y), [poligono]) < 1e-6
            # En todo el hilo el espesor es el mismo: es un hilo de nivel.
            assert espesor_de_arenilla((x, y), b, pendiente_pct=2.0) == pytest.approx(h["espesor_m"], abs=1e-9)
    assert sorted({round(h["espesor_m"], 6) for h in hilos})[0] == pytest.approx(0.07)


def test_una_linea_trazada_se_devuelve_tal_cual_y_no_genera_hilos() -> None:
    poligono = _rect(0, 0, 10, 6)
    b = [Bajada("1", 10.0, 0.0, linea=((0.0, 0.0), (10.0, 0.0)))]
    r = integrar_arenilla([(poligono, 0.0)], b, pendiente_pct=2.0)
    guias = guias_de_pendiente([poligono], b, r, pendiente_pct=2.0, espesor_en_bajada_m=0.05)
    assert [g["origen"] for g in guias] == ["trazada"] and guias[0]["puntos"] == [[0.0, 0.0], [10.0, 0.0]]


# ── El relleno de azotea con bajadas, completo ──────────────────────────────────────────────────────


def _azotea(poligonos: list[PoligonoDeRelleno], bajadas: list[Bajada], **kw: object) -> dict:
    return calcular_relleno(
        EntradaRelleno(tipo="azotea", espesor_de_la_zona_m=0.12, poligonos=poligonos, bajadas=bajadas, **{**DEFECTOS["azotea"], **kw})  # type: ignore[arg-type]
    )


def test_la_azotea_con_bajadas_lleva_dos_capas_arenilla_por_m3_y_mortero_de_5_cm_por_m2() -> None:
    a = 10.0
    poligono = PoligonoDeRelleno(area_m2=a * a, id="p", piezas=[_rect(0, 0, a, a)])
    r = _azotea([poligono], [Bajada("b1", 0.0, 0.0, "BAP-1")], compensar_espesores=False)
    assert r["modo"] == "bajadas" and r["dinamico"]["estado"] == "calculado"
    exacto = 100 * 0.05 + 0.02 * a**3 * (math.sqrt(2) + math.log(1 + math.sqrt(2))) / 3
    assert r["volumen_m3"] == pytest.approx(exacto, rel=1e-3)
    por_clave = {c["concepto"]["clave"]: c for c in r["conceptos"]}
    # El mortero se paga con el concepto existente ALB-03014 por m²; la arenilla con el nuevo propuesto EJ-830 por m³.
    assert (por_clave["ALB-03014"]["cantidad"], por_clave["ALB-03014"]["unidad"], por_clave["ALB-03014"]["concepto"]["provisional"]) == (pytest.approx(100.0), "m²", False)
    assert (por_clave["EJ-830"]["cantidad"], por_clave["EJ-830"]["unidad"], por_clave["EJ-830"]["concepto"]["provisional"]) == (pytest.approx(exacto, rel=1e-3), "m³", True)
    assert por_clave["EJ-830"]["concepto"]["estado"] == "propuesto" and por_clave["EJ-830"]["parte"] == "arenilla"
    insumos = {i["parte"]: i for i in r["insumos"]}
    assert insumos["mortero"]["cantidad"] == pytest.approx(100 * 0.05)  # plantilla de 5 cm
    assert "tezontle" not in insumos and insumos["arenilla"]["cantidad"] == pytest.approx(exacto, rel=1e-3)
    d = r["dinamico"]
    assert d["volumen_arenilla_m3"] == pytest.approx(r["volumen_m3"]) and d["volumen_mortero_m3"] == pytest.approx(5.0)
    assert d["error_estimado_m3"] >= 0 and d["error_relativo"] < 1e-3 and "determinista" in d["metodo"]
    assert d["bajadas"][0]["espesor_maximo_m"] == pytest.approx(0.05 + 0.02 * a * math.sqrt(2), rel=1e-2)
    assert any(g["tipo"] == "hilo" for g in d["guias"]) and any(g["tipo"] == "pendiente" for g in d["guias"])
    # Sin precios ni importes.
    assert r["mano_de_obra"]["estado"] == "sin_mano_de_obra"


def test_sin_bajadas_la_azotea_se_comporta_exactamente_igual_que_hoy() -> None:
    sin = _azotea([PoligonoDeRelleno(area_m2=100.0, piezas=[_rect(0, 0, 10, 10)])], [])
    assert sin["modo"] == "uniforme" and sin["dinamico"] is None and sin["volumen_m3"] == pytest.approx(9.0)
    assert [c["concepto"]["clave"] for c in sin["conceptos"]] == ["ALB-03014"]
    assert {i["parte"] for i in sin["insumos"]} == {"tezontle", "mortero"}


def test_la_compensacion_de_las_subzonas_se_conserva_con_bajadas_y_la_suma_por_espacio_es_el_total() -> None:
    p1 = PoligonoDeRelleno(area_m2=24.0, id="a", espacio_id="e1", piezas=[_rect(0, -4, 6, 0)])
    p2 = PoligonoDeRelleno(area_m2=8.0, espesor_de_losa_m=0.20, id="b", espacio_id="e2", piezas=[_rect(6, -4, 8, 0)])
    r = _azotea([p1, p2], [Bajada("b1", 0.0, 0.0)])
    a, b = r["poligonos"]
    assert a["compensacion_m"] == pytest.approx(0.08) and b["compensacion_m"] == 0.0
    # Nada se cuenta dos veces: cada polígono cae en un solo espacio y la suma de los grupos es el relleno.
    for clave in ("ALB-03014", "EJ-830"):
        total = next(c for c in r["conceptos"] if c["concepto"]["clave"] == clave)["cantidad"]
        grupos = sum(c["cantidad"] for g in r["por_espacio"] for c in g["conceptos"] if c["concepto"]["clave"] == clave)
        assert grupos == pytest.approx(total)
    assert sum(g["volumen_m3"] for g in r["por_espacio"]) == pytest.approx(r["volumen_m3"])
    assert r["area_m2"] == pytest.approx(32.0)


def test_sin_escala_calibrada_el_relleno_con_bajadas_no_da_cantidades() -> None:
    r = calcular_relleno(
        EntradaRelleno(
            tipo="azotea", espesor_de_la_zona_m=0.12, poligonos=[PoligonoDeRelleno(area_m2=100.0, piezas=[_rect(0, 0, 10, 10)])],
            bajadas=[Bajada("b1", 0.0, 0.0)], escala_definida=False, **DEFECTOS["azotea"],  # type: ignore[arg-type]
        )
    )
    assert r["dinamico"]["estado"] == "sin_escala" and r["volumen_m3"] == 0 and r["area_m2"] == 0
    assert all(c["cantidad"] == 0 for c in r["conceptos"]) and all(i["cantidad"] == 0 for i in r["insumos"])
    assert any("calibrar" in a for a in r["advertencias"])


def test_avisos_de_una_bajada_fuera_de_la_zona_una_que_no_drena_y_una_pendiente_cero() -> None:
    poligono = PoligonoDeRelleno(area_m2=100.0, piezas=[_rect(0, 0, 10, 10)])
    fuera = _azotea([poligono], [Bajada("1", 0.0, 0.0, "A"), Bajada("2", 50.0, 50.0, "LEJOS")])
    assert any("LEJOS" in a and "fuera" in a for a in fuera["advertencias"])
    # Dos bajadas en el mismo lugar: la segunda no drena nada.
    repetida = _azotea([poligono], [Bajada("1", 5.0, 5.0, "A"), Bajada("2", 5.0, 5.0, "B")])
    assert any("«B»" in a and "no drena" in a for a in repetida["advertencias"])
    plana = _azotea([poligono], [Bajada("1", 5.0, 5.0)], pendiente_zona_pct=0.0)
    assert plana["volumen_m3"] == pytest.approx(5.0) and any("0 %" in a for a in plana["advertencias"])


def test_un_poligono_sin_geometria_avisa_y_no_suma() -> None:
    r = _azotea([PoligonoDeRelleno(area_m2=100.0, id="x")], [Bajada("1", 0.0, 0.0)])
    assert r["volumen_m3"] == 0 and any("no trae geometría" in a for a in r["advertencias"])


# ── Parámetros, factor de abundamiento y el concepto nuevo ──────────────────────────────────────────


def test_el_factor_de_abundamiento_manda_y_el_porcentaje_viejo_es_su_alias() -> None:
    assert validar_parametros("compactado", {})["factor_abundamiento"] == 1.0
    assert validar_parametros("compactado", {"abundamiento_pct": 25})["factor_abundamiento"] == pytest.approx(1.25)
    p = validar_parametros("compactado", {"factor_abundamiento": 1.2})
    assert p["factor_abundamiento"] == 1.2 and p["abundamiento_pct"] == pytest.approx(20.0)
    # El factor, si viene, manda sobre el porcentaje.
    assert validar_parametros("compactado", {"factor_abundamiento": 1.1, "abundamiento_pct": 40})["abundamiento_pct"] == pytest.approx(10.0)
    for malo in (0.9, 1.7):
        with pytest.raises(ErrorDeRelleno, match="factor_abundamiento"):
            validar_parametros("compactado", {"factor_abundamiento": malo})
    with pytest.raises(ErrorDeRelleno, match="abundamiento"):
        validar_parametros("azotea", {"factor_abundamiento": 1.1})


def test_el_compactado_mide_el_volumen_compactado_por_el_factor_sin_destajo() -> None:
    r = calcular_relleno(
        EntradaRelleno(tipo="compactado", espesor_de_la_zona_m=0.12, poligonos=[PoligonoDeRelleno(area_m2=50.0)], **{**DEFECTOS["compactado"], "factor_abundamiento": 1.2})  # type: ignore[arg-type]
    )
    assert r["volumen_m3"] == pytest.approx(5.0)  # compactado
    [c] = r["conceptos"]
    assert c["concepto"]["clave"] == "EJ-810" and c["cantidad"] == pytest.approx(6.0) and c["unidad"] == "m³"  # × 1.2
    assert r["por_espacio"][0]["conceptos"][0]["cantidad"] == pytest.approx(6.0)
    assert r["volumen_suelto_m3"] == pytest.approx(6.0) and r["mano_de_obra"]["destajos_candidatos"] == []
    por_omision = calcular_relleno(
        EntradaRelleno(tipo="compactado", espesor_de_la_zona_m=0.12, poligonos=[PoligonoDeRelleno(area_m2=50.0)], **DEFECTOS["compactado"])  # type: ignore[arg-type]
    )
    assert por_omision["conceptos"][0]["cantidad"] == pytest.approx(5.0)  # factor 1.00


def test_los_parametros_dinamicos_se_validan() -> None:
    for campo, valor in (("pendiente_zona_pct", -1), ("pendiente_zona_pct", 31), ("espesor_bajada_m", 0.0), ("espesor_bajada_m", 0.5), ("mortero_espesor_m", 0.3)):
        with pytest.raises(ErrorDeRelleno, match=campo):
            validar_parametros("azotea", {campo: valor})
    assert validar_parametros("azotea", {"pendiente_zona_pct": 1.5})["pendiente_zona_pct"] == 1.5


def test_la_arenilla_es_un_concepto_nuevo_propuesto_por_m3_con_clave_provisional_sin_precio() -> None:
    assert CONCEPTO_ARENILLA["clave"] == "EJ-830" and CONCEPTO_ARENILLA["unidad"] == "m³" and CONCEPTO_ARENILLA["provisional"] is True
    p = concepto_nuevo_de_arenilla()
    assert (p["elemento_clave"], p["concepto_clave"], p["clase"]) == ("REL-AZOTEA", "EJ-830", "concepto_nuevo")
    assert p["detalle"]["clave_provisional"] is True and p["detalle"]["insumos"] == {} and p["detalle"]["unidad"] == "m³"
    ficha = definicion_de_relleno("REL-AZOTEA")
    assert ficha["concepto_arenilla"]["clave"] == "EJ-830" and ficha["concepto"]["clave"] == "ALB-03014"
    assert definicion_de_relleno("REL-COMPACTADO")["concepto_arenilla"] is None
    assert {"R8", "R9", "R10", "R11", "R12"} <= {x["clave"] for x in ficha["pendientes"]}
