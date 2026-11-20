"""D7 (Q56): las correcciones de T-2-12x20 y T-5-12x30 como versiones propuestas de concepto; el catálogo no se edita."""

from __future__ import annotations

import pytest

from obractrl.domain.cuantificacion.correcciones_de_catalogo import correcciones_de
from obractrl.domain.cuantificacion.correcciones_de_trabes import (
    correcciones_de_elemento_lineal,
)
from obractrl.domain.cuantificacion.elementos_lineales import (
    EntradaElementoEstructural,
    calcular_elemento,
    elemento_estructural,
)
from obractrl.domain.cuantificacion.elementos_lineales_catalogo import ELEMENTOS, INSUMOS


def test_t2_12x20_pasa_de_dos_anillos_a_uno_con_los_kg_del_elemento() -> None:
    (p,) = correcciones_de_elemento_lineal("T-2-12x20")
    assert (p["clase"], p["concepto_clave"], p["elemento_clave"]) == ("version_de_concepto", "AUX-10205", "T-2-12x20")
    cambios = {c["insumo"]: c for c in p["detalle"]["cambios"]}
    assert set(cambios) == {"ACE-00004", "ACE-00029"}
    assert cambios["ACE-00004"]["antes"] == pytest.approx(0.71214) and cambios["ACE-00004"]["despues"] == pytest.approx(0.646404)
    assert cambios["ACE-00029"]["antes"] == pytest.approx(0.668316) and cambios["ACE-00029"]["despues"] == 0
    assert all(c["unidad"] == "kg" for c in cambios.values())
    assert "Q56" in p["detalle"]["motivos"][0]


def test_t5_12x30_pasa_del_anillo_al_alambron_con_los_kg_reales() -> None:
    """Decisión del usuario (2026-11-20): el estribo de T-5 es alambrón (ACE-00002, kg); no se inventa ningún insumo."""
    (p,) = correcciones_de_elemento_lineal("T-5-12x30")
    assert p["concepto_clave"] == "AUX-00060"
    cambios = {c["insumo"]: c for c in p["detalle"]["cambios"]}
    assert set(cambios) == {"ACE-00006", "ACE-00002"}
    assert (cambios["ACE-00006"]["antes"], cambios["ACE-00006"]["despues"]) == (pytest.approx(1.940125), 0)
    assert (cambios["ACE-00002"]["antes"], cambios["ACE-00002"]["despues"]) == (0, pytest.approx(1.803175))
    assert cambios["ACE-00002"]["unidad"] == "kg" and INSUMOS["ACE-00002"]["descripcion"] == "ALAMBRON"
    assert any("alambrón" in m for m in p["detalle"]["motivos"]) and "provisional" not in p["resumen"]


def test_t5_kg_del_alambron_son_la_formula_de_receta_acero() -> None:
    """kg/m = (100 ÷ separación) × (perímetro del núcleo × factor + gancho) × peso del alambrón."""
    e = elemento_estructural("T-5-12x30")
    assert e is not None
    a = e["armado"]
    sep, _ = a["anillos"][0]
    rec = a["rec_cm"] / 100
    largo = 2 * ((e["ancho_cm"] / 100 - 2 * rec) + (e["peralte_cm"] / 100 - 2 * rec)) * a["factor_anillo"] + a["gancho_cm"] / 100
    esperado = (100 / sep) * largo * INSUMOS["ACE-00002"]["peso_kg_m"]
    (p,) = correcciones_de_elemento_lineal("T-5-12x30")
    despues = next(c["despues"] for c in p["detalle"]["cambios"] if c["insumo"] == "ACE-00002")
    assert despues == pytest.approx(esperado, abs=1e-5)


def test_t2_12x20_queda_marcada_pendiente_de_confirmar_con_costos() -> None:
    (p,) = correcciones_de_elemento_lineal("T-2-12x20")
    assert "Pendiente de confirmar con Costos" in p["detalle"]["motivos"][0]


def test_la_propuesta_es_lo_que_calcula_el_elemento() -> None:
    """Con la versión propuesta la conciliación del elemento queda igual al catálogo (menos el insumo que se quita)."""
    for clave in ("T-2-12x20", "T-5-12x30"):
        (p,) = correcciones_de_elemento_lineal(clave)
        filas = {f["clave"]: f for f in calcular_elemento(EntradaElementoEstructural(clave))["conciliacion"][0]["filas"]}
        for c in p["detalle"]["cambios"]:
            if c["insumo"] == "ACE-00002":  # el alambrón de T-5 toma los kg que el cálculo vigente da al anillo
                assert c["despues"] == pytest.approx(filas["ACE-00006"]["elemento"], abs=1e-6)
                continue
            if c["insumo"] == "ACE-00006":  # y el anillo se quita
                assert c["despues"] == 0
                continue
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
