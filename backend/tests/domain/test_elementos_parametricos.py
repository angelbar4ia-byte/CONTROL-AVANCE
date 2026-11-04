"""La receta de una muestra de elemento paramétrico (D-602, D-604): las cuentas del mockup del cuantificador."""

from __future__ import annotations

import pytest

from obractrl.domain.cuantificacion.elementos_parametricos import (
    ErrorDeElementoParametrico,
    normalizar_parametros,
    receta,
)


def test_castillo_k1_da_lo_del_mockup() -> None:
    # 15 × 15 × 2.6, 4 var #4, estribos #2 @ 20: concreto 0.0585 m³, estribo de 0.50 m, 1 vara por pieza.
    r = receta("castillo", {})
    assert r["concreto"] == pytest.approx(0.0585)
    assert r["long_estribo_m"] == pytest.approx(0.5)
    assert r["n_estribos"] == 14
    assert r["varas"] == pytest.approx(1.0)
    assert r["acero_kg"] == pytest.approx(4 * 2.6 * 0.994 * 1.05)
    assert r["n_amarres"] == 56
    assert r["cimbra_m2"] == {4: pytest.approx(1.56), 3: pytest.approx(1.17), 2: pytest.approx(0.78)}


def test_trabe_se_calcula_por_metro() -> None:
    r = receta("lineal", {})
    assert r["unidad"] == "ml"
    assert r["concreto"] == pytest.approx(0.2 * 0.4)
    assert r["n_estribos"] == pytest.approx(5)
    assert r["cimbra_m2"] == {3: pytest.approx(1.0), 2: pytest.approx(0.8)}


def test_zapata_lleva_parrilla_en_dos_sentidos() -> None:
    r = receta("zapata", {})
    assert r["concreto"] == pytest.approx(1.2 * 1.2 * 0.25)
    assert r["n_amarres"] == 9 * 9  # ⌈1.1 / 0.15⌉ + 1 = 9 en cada sentido
    assert r["cimbra_m2"] == {4: pytest.approx(2 * 2.4 * 0.25)}


def test_losa_se_calcula_por_metro_cuadrado() -> None:
    r = receta("losa", {"lechos": 2})
    assert r["unidad"] == "m²"
    assert r["concreto"] == pytest.approx(0.1)
    assert r["n_amarres"] == pytest.approx(2 * 4 * 4)
    assert r["cimbra_m2"] == {1: 1.0}


def test_un_parametro_que_no_vale_se_rechaza() -> None:
    for malo in ({"alto": 0}, {"no_var": 7}, {"am_cal": 10}, {"n_var": 2.5}, {"inventado": 1}, {"sep": -1}):
        with pytest.raises(ErrorDeElementoParametrico):
            normalizar_parametros("castillo", malo)
    with pytest.raises(ErrorDeElementoParametrico):
        normalizar_parametros("trabe", {})
