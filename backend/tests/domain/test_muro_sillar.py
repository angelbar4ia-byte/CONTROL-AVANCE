"""El muro de sillar amarillo BAP-01010: geometría de la pieza 19×25×45, desperdicio, conciliación con el catálogo y propuestas.

Los números del catálogo salen de `ANALISIS_DE_BASICOS_CONCEPTOS.csv` (opus, líneas 501 a 503); `scripts/verificar_sillar_contra_csv.py` los
compara con el CSV cuando se corre a mano.
"""

from __future__ import annotations

import pytest

from obractrl.domain.cuantificacion.biblioteca_de_elementos import (
    BIBLIOTECA,
    elemento_de_la_biblioteca,
)
from obractrl.domain.cuantificacion.drivers import definicion_de as driver
from obractrl.domain.cuantificacion.muro_plantilla import alertas_del_material
from obractrl.domain.cuantificacion.muro_sillar import (
    DESPERDICIO_POR_DEFECTO_PCT,
    ELEMENTOS_DE_SILLAR,
    ElementoDeSillarNoEncontrado,
    EntradaMuroDeSillar,
    ErrorDeMuroDeSillar,
    calcular_muro_de_sillar,
    claves_de_sillar,
    concepto_nuevo_de,
    definicion_de,
    propuestas_de_actualizacion_de_apu,
)
from obractrl.domain.cuantificacion.muro_tabique import ELEMENTOS_DE_TABIQUE
from obractrl.domain.cuantificacion.muro_ubicacion import MATERIALES_DE_MURO


def _calc(**kw: object) -> dict:
    return calcular_muro_de_sillar("BAP-01010", EntradaMuroDeSillar(**kw))  # type: ignore[arg-type]


# --- La pieza 19×25×45 a hilo ------------------------------------------------------------------------------------------------


def test_la_pieza_es_la_del_catalogo_y_el_espesor_es_de_19_cm() -> None:
    r = _calc()
    assert r["pieza"] == {"insumo": "PET-00008", "ancho_cm": 19.0, "alto_cm": 25.0, "largo_cm": 45.0}
    assert r["geometria"]["espesor_real_cm"] == pytest.approx(19.0)
    assert r["geometria"]["hiladas"][0]["filas"][0]["etiqueta"] == "a hilo"
    assert (r["concepto"]["clave"], r["concepto"]["estado"], r["concepto"]["clave_provisional"]) == ("BAP-01010", "catalogo", False)


def test_las_piezas_y_la_mezcla_salen_de_la_geometria_con_junta_de_2_cm_y_el_desperdicio_del_driver() -> None:
    r = _calc()
    assert r["piezas"]["netas_por_unidad"] == pytest.approx(1 / (0.47 * 0.27))  # 7.8802 pza por m²
    assert r["piezas"]["por_unidad"] == pytest.approx(r["piezas"]["netas_por_unidad"] * 1.05)
    # La mezcla es el volumen de la hilada de 1 m² menos el de las piezas netas: 0.19 − n · (0.19 × 0.25 × 0.45).
    assert r["mezcla"]["neta_por_unidad"] == pytest.approx(0.19 - (1 / (0.47 * 0.27)) * 0.19 * 0.25 * 0.45)
    assert r["mezcla"]["por_unidad"] == pytest.approx(r["mezcla"]["neta_por_unidad"] * 1.05)
    assert r["parametros"]["junta_cm"] == 2.0 and r["parametros"]["desperdicio_de_pieza_pct"] == r["parametros"]["desperdicio_de_mezcla_pct"] == 5.0


def test_el_desperdicio_de_partida_es_el_valor_inicial_del_driver() -> None:
    assert float(driver("desperdicio_mamposteria").inicial) == DESPERDICIO_POR_DEFECTO_PCT


def test_los_totales_son_por_cantidad_y_las_piezas_a_comprar_suben_al_entero() -> None:
    r = _calc(cantidad=100.0)
    assert r["piezas"]["total"] == pytest.approx(r["piezas"]["por_unidad"] * 100)
    assert r["piezas"]["a_comprar"] == 828  # 827.4 pza
    assert r["insumos"][1]["total"] == pytest.approx(r["mezcla"]["por_unidad"] * 100)
    abierta = {m["clave"]: m["total"] for m in r["mezcla_compuesta"]}
    assert abierta["ADH-00005"] == pytest.approx(7.28 * r["mezcla"]["total_m3"])  # el cemento de la mezcla 1:4 del catálogo


def test_cambiar_junta_y_desperdicio_mueve_el_calculo_en_el_sentido_correcto() -> None:
    base = _calc()
    sin_junta = _calc(junta_cm=0.0)
    assert sin_junta["piezas"]["netas_por_unidad"] == pytest.approx(1 / (0.45 * 0.25))  # 8.889 pza
    assert sin_junta["mezcla"]["neta_por_unidad"] == pytest.approx(0.0, abs=1e-12)  # sin junta no hay mezcla
    assert _calc(junta_cm=3.0)["piezas"]["por_unidad"] < base["piezas"]["por_unidad"]
    assert _calc(desperdicio_pct=10.0)["piezas"]["por_unidad"] == pytest.approx(base["piezas"]["netas_por_unidad"] * 1.10)
    assert _calc(desperdicio_pct=0.0)["mezcla"]["por_unidad"] == pytest.approx(base["mezcla"]["neta_por_unidad"])


# --- Conciliación con el catálogo vigente ---------------------------------------------------------------------------------------


def test_la_conciliacion_trae_la_composicion_real_del_catalogo_y_la_diferencia() -> None:
    r = _calc()
    (bloque,) = r["conciliacion"]
    assert bloque["concepto"]["clave"] == "BAP-01010"
    filas = {f["clave"]: f for f in bloque["filas"]}
    assert filas["PET-00008"]["catalogo"] == 9.0 and filas["MEZ-07010"]["catalogo"] == pytest.approx(0.0292)
    assert filas["PET-00008"]["elemento"] == pytest.approx(r["piezas"]["por_unidad"])
    assert filas["PET-00008"]["marca"] == "≠" and filas["MEZ-07010"]["marca"] == "≠"  # el catálogo no se edita: la diferencia se muestra
    assert [m["clave"] for m in bloque["mano_de_obra"]] == ["MOE-02016"]
    assert bloque["fuente_de_las_filas"] == ["ANALISIS_DE_BASICOS_CONCEPTOS:501", "ANALISIS_DE_BASICOS_CONCEPTOS:502", "ANALISIS_DE_BASICOS_CONCEPTOS:503"]
    assert any("9 pza" in a for a in r["avisos"])


def test_con_la_junta_y_el_desperdicio_que_implica_el_catalogo_el_elemento_coincide() -> None:
    """Con 2.4 cm de junta y 16.6 % de desperdicio la geometría reproduce los 9 pza y 0.0292 m³: el catálogo no es inconsistente, solo trae
    otros supuestos que no documenta (pregunta abierta S1)."""
    r = _calc(junta_cm=2.4, desperdicio_pct=16.6)
    filas = {f["clave"]: f["marca"] for f in r["conciliacion"][0]["filas"]}
    assert filas == {"PET-00008": "=", "MEZ-07010": "="}
    assert r["avisos"] == []


def test_la_mano_de_obra_es_el_destajo_del_catalogo_sin_precio() -> None:
    m = _calc()["mano_de_obra"]
    assert m["estado"] == "destajo_del_catalogo" and m["destajo"] == {"clave": "MOE-02016", "descripcion": "MO MURO DE SILLAR- HILO", "unidad": "m2"}
    assert "ni pone precio" in m["nota"] and _calc()["herramienta"] == []


# --- Propuestas de versión de concepto ------------------------------------------------------------------------------------------


def test_confirmar_el_calculo_propone_una_version_de_bap_01010_y_el_catalogo_no_se_edita() -> None:
    (p,) = propuestas_de_actualizacion_de_apu(_calc())
    assert (p["elemento_clave"], p["concepto_clave"], p["clase"]) == ("BAP-01010", "BAP-01010", "version_de_concepto")
    cambios = {c["insumo"]: c for c in p["detalle"]["cambios"]}
    assert cambios["PET-00008"]["antes"] == 9.0 and cambios["PET-00008"]["despues"] == pytest.approx(8.274232, abs=1e-6)
    assert cambios["MEZ-07010"]["antes"] == 0.0292
    assert all(c["insumo"] != "MOE-02016" for c in p["detalle"]["cambios"])  # la mano de obra no se calcula ni se propone
    # Sin diferencias no hay propuesta.
    assert propuestas_de_actualizacion_de_apu(_calc(junta_cm=2.4, desperdicio_pct=16.6)) == []


def test_el_concepto_ya_esta_en_el_catalogo_asi_que_no_se_propone_un_concepto_nuevo() -> None:
    """Regla F7: BAP-01010 ya es una matriz del catálogo y cubre el elemento: se liga a él, no se inventa un concepto."""
    with pytest.raises(ErrorDeMuroDeSillar, match="ya está en el catálogo"):
        concepto_nuevo_de("BAP-01010")
    f = definicion_de("BAP-01010")
    assert [(c["clave"], c["estado"], c["en_catalogo"], c["clave_provisional"]) for c in f["conceptos"]] == [("BAP-01010", "catalogo", True, False)]


# --- Validación, ficha y biblioteca ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("kw", [{"cantidad": 0.0}, {"cantidad": -1.0}, {"junta_cm": -1.0}, {"junta_cm": 11.0}, {"desperdicio_pct": 101.0}, {"desperdicio_pct": -1.0}])
def test_lo_que_no_vale_se_rechaza(kw: dict) -> None:
    with pytest.raises(ErrorDeMuroDeSillar):
        _calc(**kw)


def test_una_clave_desconocida_no_existe() -> None:
    with pytest.raises(ElementoDeSillarNoEncontrado):
        calcular_muro_de_sillar("BAP-99999")
    assert claves_de_sillar() == ("BAP-01010",) == tuple(ELEMENTOS_DE_SILLAR)


def test_la_ficha_dice_los_supuestos_y_el_driver() -> None:
    f = definicion_de("bap-01010")
    assert (f["tipo"], f["espesor_real_cm"], f["driver_de_desperdicio"]) == ("sillar", 19.0, "desperdicio_mamposteria")
    assert f["parametros_por_defecto"]["junta_cm"] == 2.0
    assert {p["clave"] for p in f["pendientes"]} >= {"S1", "S2", "S3"}
    assert f["conceptos"][0]["destajo"]["clave"] == "MOE-02016"


def test_la_biblioteca_trae_muros_de_sillar_junto_a_los_de_tabique_y_su_ficha_es_de_sillar() -> None:
    muros = next(c for c in BIBLIOTECA if c["clave"] == "muros")
    assert [s["clave"] for s in muros["subcategorias"]] == ["tabique", "sillar"]
    sillar = next(s for s in muros["subcategorias"] if s["clave"] == "sillar")
    assert [(e["clave"], e["tipo"], e["concepto"]["clave"]) for e in sillar["elementos"]] == [("BAP-01010", "sillar", "BAP-01010")]
    assert elemento_de_la_biblioteca("BAP-01010") is None  # su ficha es la de /sillar, no la del muro de piedra
    assert "BAP-01010" not in ELEMENTOS_DE_TABIQUE


def test_el_material_sillar_amarillo_ya_tiene_elemento_y_el_aviso_desaparece() -> None:
    assert MATERIALES_DE_MURO["sillar_amarillo"]["elemento"] == MATERIALES_DE_MURO["sillar_amarillo"]["concepto"] == "BAP-01010"
    assert alertas_del_material("sillar_amarillo", lleva_muro_propio=False) == []
    # Lo que no tiene concepto sigue bloqueando: no se inventa un concepto ni un elemento (block hueco, cantera rosa).
    for material in ("block_hueco", "cantera_rosa"):
        (a,) = alertas_del_material(material, lleva_muro_propio=False)
        assert (a.nivel, a.codigo) == ("bloquea", "material_sin_concepto")


def test_el_aviso_material_sin_elemento_sigue_existiendo_para_un_material_con_concepto_y_sin_elemento(monkeypatch: pytest.MonkeyPatch) -> None:
    """La alerta no se borra del dominio: aplica a cualquier material que gane concepto antes que elemento."""
    monkeypatch.setitem(MATERIALES_DE_MURO, "block_hueco", {**MATERIALES_DE_MURO["block_hueco"], "concepto": "BLK-00001", "elemento": None})
    (a,) = alertas_del_material("block_hueco", lleva_muro_propio=False)
    assert (a.nivel, a.codigo, a.concepto) == ("alerta", "material_sin_elemento", "BLK-00001")
