"""La comparación del elemento contra el concepto del catálogo, insumo por insumo (fase D; M-46): marcas =, ≈, ≠ y composición real."""

from __future__ import annotations

import pytest

from obractrl.domain.cuantificacion.comparacion_con_catalogo import (
    FilaDeComposicion,
    comparar_con_concepto,
    expandir_composicion,
    marca_de,
)


@pytest.mark.parametrize(
    ("catalogo", "elemento", "marca"),
    [
        (100.0, 100.0, "="),
        (100.0, 103.0, "="),  # justo en el 3 %
        (100.0, 97.0, "="),
        (100.0, 103.5, "≈"),
        (100.0, 96.0, "≈"),
        (100.0, 108.0, "≈"),  # justo en el 8 %
        (100.0, 108.5, "≠"),
        (100.0, 50.0, "≠"),
        (100.0, None, "solo_catalogo"),
        (None, 5.0, "solo_elemento"),
        (0.0, 0.0, "="),
        (0.0, 1.0, "≠"),
    ],
)
def test_las_marcas_siguen_los_umbrales_de_la_spec(catalogo: float | None, elemento: float | None, marca: str) -> None:
    assert marca_de(catalogo, elemento)[0] == marca


def test_la_diferencia_es_del_elemento_contra_el_catalogo() -> None:
    _, dif = marca_de(200.0, 210.0)
    assert dif == pytest.approx(0.05)
    assert marca_de(200.0, 190.0)[1] == pytest.approx(-0.05)


# Composición real de EST-02110 (ANALISIS_DE_BASICOS_CONCEPTOS.csv): colado y cimbra de un castillo por ml.
EST_02110 = [
    FilaDeComposicion("ACE-00001", 0.210987, "ALAMBRE RECOCIDO", "KG"),
    FilaDeComposicion("MEZ-01020", 0.023625, "CONCRETO", "M3"),
    FilaDeComposicion("ACE-00012", 0.017021, "CLAVO 2 1/2", "KG"),
    FilaDeComposicion("ACE-00013", 0.02, "CLAVO 4", "KG"),
    FilaDeComposicion("MOE-02020", 1.0, "MO CASTILLOS K1", "M", es_mano_de_obra=True, costo=130.0),
    FilaDeComposicion("MAD-00004", 0.01, "TABLAS", "PZ"),
]


def test_el_concepto_real_se_compara_insumo_por_insumo() -> None:
    elemento = {"MEZ-01020": 0.0225, "ACE-00001": 0.2, "ACE-00012": 0.0175, "ACE-00013": 0.0, "MAD-00099": 1.0}
    r = comparar_con_concepto(elemento, EST_02110)
    por = {f["clave"]: f for f in r["filas"]}
    assert por["MEZ-01020"]["marca"] == "≈" and por["MEZ-01020"]["diferencia_pct"] == pytest.approx(-4.76, abs=0.01)  # pasa del 3 %
    assert por["ACE-00001"]["marca"] == "≈" and por["ACE-00001"]["diferencia_pct"] == pytest.approx(-5.2, abs=0.01)
    assert por["ACE-00012"]["marca"] == "=" and por["ACE-00012"]["diferencia_pct"] == pytest.approx(2.81, abs=0.01)
    assert por["ACE-00013"]["marca"] == "≠" and por["ACE-00013"]["diferencia_pct"] == pytest.approx(-100.0)
    assert por["MAD-00004"]["marca"] == "solo_catalogo" and por["MAD-00004"]["elemento"] is None
    assert por["MAD-00099"]["marca"] == "solo_elemento" and por["MAD-00099"]["catalogo"] is None
    assert r["resumen"] == {"=": 1, "≈": 2, "≠": 1, "solo_catalogo": 1, "solo_elemento": 1}
    assert not r["coincide"]
    # La mano de obra (el destajo) no se compara: se lista aparte con su costo.
    assert "MOE-02020" not in por
    assert r["mano_de_obra"] == [{"clave": "MOE-02020", "descripcion": "MO CASTILLOS K1", "unidad": "M", "cantidad": 1.0, "costo": 130.0}]


def test_un_elemento_que_coincide_en_todo_lo_dice() -> None:
    elemento = {f.clave: f.cantidad for f in EST_02110 if not f.es_mano_de_obra}
    r = comparar_con_concepto(elemento, EST_02110)
    assert r["coincide"] and r["resumen"]["="] == 5
    assert all(f["diferencia_pct"] == 0 for f in r["filas"])


def test_las_cantidades_del_catalogo_que_se_compensan_se_suman_por_clave() -> None:
    """EST-10011 trae el alambre dos veces: 0.032945 y −0.002945 (el catálogo resta con una cantidad negativa)."""
    comp = [
        FilaDeComposicion("ACE-00011", 1.0, "ARMEX 10X10-4", "PZ"),
        FilaDeComposicion("ACE-00001", 0.032945, "ALAMBRE RECOCIDO", "KG"),
        FilaDeComposicion("ACE-00001", -0.002945, "ALAMBRE RECOCIDO", "KG"),
    ]
    r = comparar_con_concepto({"ACE-00001": 0.03}, comp)
    por = {f["clave"]: f for f in r["filas"]}
    assert por["ACE-00001"]["catalogo"] == pytest.approx(0.03)
    assert por["ACE-00001"]["marca"] == "="
    assert por["ACE-00011"]["marca"] == "solo_catalogo"


def test_el_auxiliar_se_expande_hasta_los_insumos() -> None:
    """Un concepto que lleva un auxiliar (AUX-04010 × 3.36 m²) se compara contra lo que ese auxiliar contiene."""
    filas = [
        {"concepto_clave": "EST-07010", "tipo_hijo": "concepto", "categoria": "auxiliar", "cantidad": 3.36, "concepto_hijo_clave": "AUX-04010"},
        {"concepto_clave": "EST-07010", "tipo_hijo": "insumo", "categoria": "material", "cantidad": 0.099225, "insumo_clave": "MEZ-01020", "costo_unitario": 1500},
        {"concepto_clave": "EST-07010", "tipo_hijo": "insumo", "categoria": "destajo", "cantidad": 1, "insumo_clave": "MOE-02040", "costo_unitario": 1300},
        {"concepto_clave": "AUX-04010", "tipo_hijo": "insumo", "categoria": "material", "cantidad": 50.0, "insumo_clave": "PET-00001"},
        {"concepto_clave": "AUX-04010", "tipo_hijo": "insumo", "categoria": "material", "cantidad": 0.0447, "insumo_clave": "MEZ-07010"},
    ]
    comp = expandir_composicion(filas, "EST-07010")
    por = {c.clave: c for c in comp}
    assert por["PET-00001"].cantidad == pytest.approx(168.0)  # 50 × 3.36
    assert por["MEZ-07010"].cantidad == pytest.approx(0.150192)
    assert por["MEZ-01020"].cantidad == pytest.approx(0.099225)
    assert por["MOE-02040"].es_mano_de_obra and por["MOE-02040"].costo == 1300
    r = comparar_con_concepto({"PET-00001": 161.7, "MEZ-07010": 0.1055, "MEZ-01020": 0.099225}, comp)
    marcas = {f["clave"]: f["marca"] for f in r["filas"]}
    # Los números del mockup para la columna forjada: tabique −3.8 % (≈), mezcla −29.7 % (≠), concreto coincide.
    assert marcas == {"PET-00001": "≈", "MEZ-07010": "≠", "MEZ-01020": "="}


def test_un_ciclo_en_el_catalogo_se_corta() -> None:
    filas = [
        {"concepto_clave": "A", "tipo_hijo": "concepto", "categoria": "auxiliar", "cantidad": 1, "concepto_hijo_clave": "B"},
        {"concepto_clave": "B", "tipo_hijo": "concepto", "categoria": "auxiliar", "cantidad": 1, "concepto_hijo_clave": "A"},
        {"concepto_clave": "B", "tipo_hijo": "insumo", "categoria": "material", "cantidad": 2, "insumo_clave": "X-1"},
    ]
    assert [c.clave for c in expandir_composicion(filas, "A")] == ["X-1"]
