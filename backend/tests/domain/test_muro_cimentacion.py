"""El muro de cimentación de piedra CIM-01010 y el trazo con pendiente de los muros de piedra."""

from __future__ import annotations

import pytest

from obractrl.domain.cuantificacion.biblioteca_de_elementos import (
    elemento_de_la_biblioteca,
)
from obractrl.domain.cuantificacion.muro_cimentacion import (
    EntradaMuroDeCimentacion,
    ErrorDeMuroDeCimentacion,
    calcular_muro_de_cimentacion,
)
from obractrl.domain.cuantificacion.muro_contencion import (
    EntradaMuroDeContencion,
    calcular_muro_de_contencion,
)
from obractrl.domain.cuantificacion.trazo_de_muro import ErrorDeTrazo, calcular_trazo


def cim(**kw: object) -> dict:
    return calcular_muro_de_cimentacion(EntradaMuroDeCimentacion(**kw))  # type: ignore[arg-type]


def test_a_2_m_la_base_sale_del_escarpio_173_cm() -> None:
    r = cim(alto_m=2.0)
    assert r["seccion"]["corona_m"] == pytest.approx(0.40)
    assert r["seccion"]["base_m"] == pytest.approx(1.73)  # 40 + 133
    assert r["volumen"]["muro_m3_ml"] == pytest.approx((0.40 + 1.73) / 2 * 2.0)
    assert r["escarpio"]["cumple"] is True
    assert r["concepto"]["clave"] == "MCT-01011"


def test_la_corona_es_siempre_de_40_cm_y_dos_caras_ensanchan_mas() -> None:
    assert cim(alto_m=1.0)["seccion"]["corona_m"] == pytest.approx(0.40)
    assert cim(alto_m=1.0)["seccion"]["base_m"] == pytest.approx(1.07)
    assert cim(alto_m=1.0, caras=2)["seccion"]["base_m"] == pytest.approx(1.73)
    assert cim(alto_m=3.0)["seccion"]["corona_m"] == pytest.approx(0.40)


def test_el_dentellon_es_opcional_y_solo_desde_2_m() -> None:
    assert cim(alto_m=2.0)["volumen"]["dentellon_m3_ml"] == 0.0
    con = cim(alto_m=2.0, dentellon=True)
    assert con["volumen"]["dentellon_m3_ml"] == pytest.approx(0.21)
    assert con["volumen"]["total_m3_ml"] == pytest.approx(
        con["volumen"]["muro_m3_ml"] + 0.21
    )
    corto = cim(alto_m=1.5, dentellon=True)
    assert corto["dentellon"]["aplica"] is False
    assert any("dentellón" in a for a in corto["advertencias"])


def test_comparte_con_el_muro_de_contencion_el_consumo_por_m3() -> None:
    c = cim(alto_m=2.0, dentellon=True)
    m = calcular_muro_de_contencion(EntradaMuroDeContencion(alto_m=2.0))
    v, w = c["volumen"], m["volumen"]
    assert v["abundamiento"] == w["abundamiento"]
    assert v["cemento_kg_ml"] / v["total_m3_ml"] == pytest.approx(
        w["cemento_kg_ml"] / w["total_m3_ml"]
    )


def test_a_mano_avisa_si_el_escarpio_queda_mas_tendido() -> None:
    r = cim(alto_m=2.0, base_m=3.0)
    assert r["escarpio"]["cumple"] is False
    assert r["seccion"]["manual"] is True
    assert any("escarpio" in a.lower() for a in r["advertencias"])


def test_rechaza_lo_que_no_vale() -> None:
    for kw in (
        {"alto_m": 0},
        {"alto_m": 21},
        {"alto_m": 2, "caras": 3},
        {"alto_m": 2, "corona_m": 1.0, "base_m": 0.5},
    ):
        with pytest.raises(ErrorDeMuroDeCimentacion):
            cim(**kw)


def test_el_contraste_con_el_catalogo_muestra_la_piedra_corta() -> None:
    contraste = cim(alto_m=2.0)["contraste"]
    filas = {f["clave"]: f for f in contraste["filas"]}
    assert filas["PET-00004"]["catalogo"] == pytest.approx(0.10)
    assert filas["PET-00004"]["elemento"] == pytest.approx(0.25)
    assert filas["PET-00004"]["marca"] == "≠"
    assert filas["ADH-00005"]["marca"] == "="
    assert filas["PET-00015"]["marca"] == "="
    assert [m["clave"] for m in contraste["mano_de_obra"]] == ["MOP-00303"]
    assert contraste["version_propuesta"]["version"] == 2


def test_la_biblioteca_trae_el_cimiento_en_su_categoria() -> None:
    d = elemento_de_la_biblioteca("CIM-01010")
    assert d is not None
    assert d["categoria"]["nombre"] == "Muros de cimentación"
    assert d["subcategoria"]["nombre"] == "Mampostería de piedra"
    assert d["cuadro_1"] == []


def _por_metro(alto: float) -> dict:
    return calcular_muro_de_contencion(EntradaMuroDeContencion(alto_m=alto))


def test_trazo_sin_pendiente_es_longitud_por_metro() -> None:
    t = calcular_trazo(_por_metro, longitud_m=6.0, altura_inicial_m=3.0)
    assert t["volumen"]["total_m3"] == pytest.approx(2.91 * 6.0)
    assert (t["altura_minima_m"], t["altura_maxima_m"]) == (3.0, 3.0)
    assert t["longitud_real_m"] == pytest.approx(6.0)


def test_trazo_con_pendiente_la_altura_sigue_el_terreno_con_corona_a_nivel() -> None:
    t = calcular_trazo(
        _por_metro, longitud_m=10.0, altura_inicial_m=2.0, pendiente_pct=10.0
    )
    assert t["altura_final_m"] == pytest.approx(3.0)
    assert t["perfil"][0]["altura_m"] == pytest.approx(2.0 + 0.1 * t["perfil"][0]["s_m"])
    assert t["altura_minima_m"] < 2.1 and t["altura_maxima_m"] > 2.9
    assert t["longitud_real_m"] == pytest.approx(10.0 * (1.01) ** 0.5)
    # más volumen que el muro parejo a la altura inicial y menos que el parejo a la final
    v0 = calcular_trazo(_por_metro, longitud_m=10.0, altura_inicial_m=2.0)["volumen"][
        "total_m3"
    ]
    v1 = calcular_trazo(_por_metro, longitud_m=10.0, altura_inicial_m=3.0)["volumen"][
        "total_m3"
    ]
    assert v0 < t["volumen"]["total_m3"] < v1
    # los insumos del dren se acumulan y se reparten entre el volumen total
    assert {i["clave"] for i in t["insumos"]} >= {"MEZ-03060"}


def test_trazo_negativo_que_baja_de_la_altura_minima_avisa() -> None:
    t = calcular_trazo(
        _por_metro, longitud_m=10.0, altura_inicial_m=0.5, pendiente_pct=-20.0
    )
    assert t["altura_minima_m"] == pytest.approx(0.1)
    assert t["advertencias"]


def test_trazo_rechaza_datos_malos() -> None:
    for kw in (
        {"longitud_m": 0, "altura_inicial_m": 2},
        {"longitud_m": 5, "altura_inicial_m": 0},
        {"longitud_m": 5, "altura_inicial_m": 2, "pendiente_pct": 200},
    ):
        with pytest.raises(ErrorDeTrazo):
            calcular_trazo(_por_metro, **kw)


def test_dice_que_dalas_castillos_empotrados_y_cimientos_perpendiculares_se_miden_aparte() -> None:
    """D12: el muro de cimentación no incluye lo que la sección 8.4 pide junto al cimiento; el cálculo lo dice y no lo suma."""
    r = cim(alto_m=2.0)
    assert [x["clave"] for x in r["no_incluye"]] == ["dalas", "castillos_empotrados", "cimientos_perpendiculares"]
    assert all("se miden aparte" in x["texto"] for x in r["no_incluye"])
    # El volumen es solo el de la piedra del cimiento: el mismo con o sin la leyenda.
    assert r["volumen"]["muro_m3_ml"] == pytest.approx((0.40 + 1.73) / 2 * 2.0)
    d = elemento_de_la_biblioteca("CIM-01010")
    q42 = next(p for p in d["pendientes"] if p["clave"] == "Q42")  # type: ignore[index]
    assert "se miden aparte" in q42["texto"] and "no los incluye" in q42["texto"]
