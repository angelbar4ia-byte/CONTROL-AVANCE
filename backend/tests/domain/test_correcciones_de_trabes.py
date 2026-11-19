"""D7 (Q56): las correcciones de T-2-12x20 y T-5-12x30 como versiones propuestas de concepto; el catálogo no se edita."""

from __future__ import annotations

import pytest

from obractrl.domain.cuantificacion.correcciones_de_catalogo import correcciones_de
from obractrl.domain.cuantificacion.correcciones_de_trabes import correcciones_de_elemento_lineal
from obractrl.domain.cuantificacion.elementos_lineales import (
    EntradaElementoEstructural,
    calcular_elemento,
    elemento_estructural,
)
from obractrl.domain.cuantificacion.elementos_lineales_catalogo import ELEMENTOS


def test_t2_12x20_pasa_de_dos_anillos_a_uno_con_los_kg_del_elemento() -> None:
    (p,) = correcciones_de_elemento_lineal("T-2-12x20")
    assert (p["clase"], p["concepto_clave"], p["elemento_clave"]) == ("version_de_concepto", "AUX-10205", "T-2-12x20")
    cambios = {c["insumo"]: c for c in p["detalle"]["cambios"]}
    assert set(cambios) == {"ACE-00004", "ACE-00029"}
    assert cambios["ACE-00004"]["antes"] == pytest.approx(0.71214) and cambios["ACE-00004"]["despues"] == pytest.approx(0.646404)
    assert cambios["ACE-00029"]["antes"] == pytest.approx(0.668316) and cambios["ACE-00029"]["despues"] == 0
    assert all(c["unidad"] == "kg" for c in cambios.values())
    assert "Q56" in p["detalle"]["motivos"][0]


def test_t5_12x30_lleva_los_kg_que_calcula_el_elemento_sin_inventar_un_insumo() -> None:
    (p,) = correcciones_de_elemento_lineal("T-5-12x30")
    assert p["concepto_clave"] == "AUX-00060"
    (c,) = p["detalle"]["cambios"]
    assert (c["insumo"], c["antes"], c["despues"]) == ("ACE-00006", pytest.approx(1.940125), pytest.approx(1.803175))
    assert "no se inventa" in p["detalle"]["motivos"][0]


def test_la_propuesta_es_lo_que_calcula_el_elemento() -> None:
    """Con la versión propuesta la conciliación del elemento queda igual al catálogo (menos el insumo que se quita)."""
    for clave in ("T-2-12x20", "T-5-12x30"):
        (p,) = correcciones_de_elemento_lineal(clave)
        filas = {f["clave"]: f for f in calcular_elemento(EntradaElementoEstructural(clave))["conciliacion"][0]["filas"]}
        for c in p["detalle"]["cambios"]:
            esperado = filas[c["insumo"]]["elemento"] or 0.0
            assert c["despues"] == pytest.approx(esperado, abs=1e-6)


def test_solo_esas_dos_trabes_tienen_correccion_y_correcciones_de_las_despacha() -> None:
    con = [e["clave"] for e in ELEMENTOS if correcciones_de_elemento_lineal(e["clave"])]
    assert sorted(con) == ["T-2-12x20", "T-5-12x30"]
    assert correcciones_de("T-2-12x20") == correcciones_de_elemento_lineal("T-2-12x20")
    assert correcciones_de("T-1-15x25") == []


def test_el_catalogo_del_elemento_no_se_edita() -> None:
    """La versión propuesta no cambia los datos del catálogo: el vigente sigue activo."""
    filas = {f[0]: f[3] for f in elemento_estructural("T-2-12x20")["catalogo"][0]["filas"]}  # type: ignore[index]
    assert filas["ACE-00029"] == pytest.approx(0.668316) and filas["ACE-00004"] == pytest.approx(0.71214)
    correcciones_de_elemento_lineal("T-2-12x20")
    filas = {f[0]: f[3] for f in elemento_estructural("T-2-12x20")["catalogo"][0]["filas"]}  # type: ignore[index]
    assert filas["ACE-00029"] == pytest.approx(0.668316)
