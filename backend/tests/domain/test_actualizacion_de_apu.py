"""«Confirmar cálculo → actualizar APU» y la conciliación en las dos direcciones (plan de elementos de muro, fase I; M-131)."""

from __future__ import annotations

import pytest

from obractrl.domain.cuantificacion.actualizacion_de_apu import (
    LineaDelApu,
    conciliar,
    planear,
)


def _apu() -> list[LineaDelApu]:
    return [
        LineaDelApu("MEZ-01020", cantidad=0.0225, directa=0.0225, costo=1500.0),
        LineaDelApu("ACR-00001", cantidad=0.40, directa=0.40, costo=133.01),
        # El alambre llega por un auxiliar: 0.05 directo y 0.03 dentro del auxiliar.
        LineaDelApu("ACE-00001", cantidad=0.08, directa=0.05, costo=24.68),
        # El tabique solo llega por un auxiliar.
        LineaDelApu("TAB-00001", cantidad=50.0, directa=None, costo=3.0),
        LineaDelApu("MAD-00007", cantidad=0.10, directa=0.10, costo=750.0),
        LineaDelApu("CUAD-001", cantidad=0.2, directa=0.2, costo=2068.0, es_mano_de_obra=True),
    ]


def test_el_plan_actualiza_los_renglones_directos_y_no_toca_lo_demas() -> None:
    salida = {"MEZ-01020": 0.0234, "ACR-00001": 0.40, "ACE-00001": 0.10, "TAB-00001": 52.0, "MEZ-01030": 0.01}
    plan = planear(salida, _apu(), insumos_existentes=["MEZ-01030"])
    por_clave = {f["clave"]: f for f in plan.filas}
    assert por_clave["MEZ-01020"]["accion"] == "actualizar"
    assert por_clave["ACR-00001"]["accion"] == "sin_cambio"
    # El alambre difiere en +0.02: se ajusta el renglón directo (0.05 -> 0.07), sin tocar lo que trae el auxiliar.
    assert por_clave["ACE-00001"]["accion"] == "actualizar"
    # El tabique llega por un auxiliar: se avisa y no se cambia.
    assert por_clave["TAB-00001"]["accion"] == "en_auxiliar"
    # El APU trae un insumo que el elemento no calcula: manda el APU.
    assert por_clave["MAD-00007"]["accion"] == "solo_apu"
    # Un insumo que el APU no trae y existe en la base se agrega.
    assert por_clave["MEZ-01030"]["accion"] == "agregar"
    # La mano de obra no se compara ni se toca.
    assert "CUAD-001" not in por_clave
    cambios = {c.clave: (c.accion, c.antes, round(c.despues, 6)) for c in plan.cambios}
    assert cambios == {
        "MEZ-01020": ("actualizar", 0.0225, 0.0234),
        "ACE-00001": ("actualizar", 0.05, 0.07),
        "MEZ-01030": ("agregar", None, 0.01),
    }
    assert plan.hay_cambios
    assert any("TAB-00001" in a for a in plan.avisos)


def test_un_insumo_que_no_existe_en_la_base_no_se_agrega() -> None:
    plan = planear({"XXX-00001": 1.0}, [], insumos_existentes=[])
    assert not plan.hay_cambios
    assert plan.filas[0]["accion"] == "sin_insumo"
    assert any("XXX-00001" in a for a in plan.avisos)


def test_un_ajuste_que_dejaria_el_renglon_directo_negativo_no_se_aplica() -> None:
    apu = [LineaDelApu("ACE-00001", cantidad=0.08, directa=0.01, costo=24.68)]
    plan = planear({"ACE-00001": 0.02}, apu)
    assert not plan.hay_cambios
    assert plan.filas[0]["accion"] == "en_auxiliar"


def test_sin_diferencias_no_hay_cambios() -> None:
    plan = planear({"MEZ-01020": 0.0225, "ACR-00001": 0.4}, _apu())
    assert not plan.hay_cambios


def test_la_conciliacion_va_en_las_dos_direcciones_y_manda_el_apu() -> None:
    salida = {"MEZ-01020": 0.0234, "ACR-00001": 0.40, "MEZ-01030": 0.01}
    c = conciliar(salida, _apu(), cantidad=100.0, precios={"MEZ-01030": 1650.0})
    assert c["manda"] == "apu"
    por_clave = {f["clave"]: f for f in c["filas"]}  # type: ignore[union-attr]
    # 0.0234 contra 0.0225: +4 %: difiere (aviso), no bloquea.
    mez = por_clave["MEZ-01020"]
    assert mez["estimado"] == pytest.approx(2.25)
    assert mez["salida"] == pytest.approx(2.34)
    assert mez["sentido"] == "difieren" and mez["avisa"] is True
    assert mez["diferencia_importe"] == pytest.approx(0.09 * 1500)
    # Igual: el estimado se justifica con la salida y al revés.
    assert por_clave["ACR-00001"]["sentido"] == "se_justifican"
    # Estimado por APU sin salida del cálculo (madera) y salida sin estimado (concreto 200).
    assert por_clave["MAD-00007"]["sentido"] == "estimado_sin_salida"
    assert por_clave["MEZ-01030"]["sentido"] == "salida_sin_estimado"
    assert por_clave["MEZ-01030"]["importe_salida"] == pytest.approx(1650.0)
    assert c["resumen"] == {"se_justifican": 1, "difieren": 1, "estimado_sin_salida": 3, "salida_sin_estimado": 1}  # type: ignore[comparison-overlap]
    assert c["sin_precio"] is False


def test_la_tolerancia_de_3_por_ciento_solo_avisa() -> None:
    apu = [LineaDelApu("MEZ-01020", cantidad=1.0, directa=1.0, costo=10.0)]
    dentro = conciliar({"MEZ-01020": 1.03}, apu, cantidad=1.0)
    fuera = conciliar({"MEZ-01020": 1.031}, apu, cantidad=1.0)
    assert dentro["filas"][0]["sentido"] == "se_justifican"  # type: ignore[index]
    assert fuera["filas"][0]["sentido"] == "difieren"  # type: ignore[index]
    assert fuera["filas"][0]["avisa"] is True  # type: ignore[index]


def test_sin_precio_no_se_inventa_un_importe() -> None:
    c = conciliar({"XXX-00001": 2.0}, [], cantidad=10.0)
    fila = c["filas"][0]  # type: ignore[index]
    assert fila["importe_salida"] is None and fila["costo"] is None
    assert c["sin_precio"] is True
