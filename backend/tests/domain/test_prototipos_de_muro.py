"""Los prototipos de la plantilla de muro confinado y sus ejemplos (Oro PB y PA, y la global de 1 y 2 plantas)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.cuantificacion.colocacion_de_plantilla import colocar_plantilla
from obractrl.domain.cuantificacion.prototipos_de_muro import (
    PROTOTIPOS,
    ejemplos_de_prototipo,
    nombre_de_plantilla,
    plantas_de,
    validar_prototipo_y_planta,
)
from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

D = Decimal


def test_las_plantas_de_cada_prototipo_son_la_inferencia_del_subcapitulo_planta_alta() -> None:
    uno = {"zafiro_1", "rubi", "jade", "global_1"}
    for p in PROTOTIPOS:
        assert plantas_de(p["clave"]) == (("PB",) if p["clave"] in uno else ("PB", "PA")), p["clave"]


def test_la_planta_se_valida_contra_las_plantas_del_prototipo() -> None:
    assert validar_prototipo_y_planta(None, None) == (None, None)
    assert validar_prototipo_y_planta("oro_401", "PA") == ("oro_401", "PA")
    assert validar_prototipo_y_planta("global_2", None) == ("global_2", None)
    for prototipo, planta in (("zafiro_1", "PA"), ("oro_401", None), ("global_1", "PB"), (None, "PB"), ("platino", "PB"), ("oro_401", "PX")):
        with pytest.raises(ErrorDeCuantificacion):
            validar_prototipo_y_planta(prototipo, planta)


def test_el_nombre_de_la_plantilla() -> None:
    assert nombre_de_plantilla("oro_401", "PB") == "Muro confinado · Oro 4.01 · PB"
    assert nombre_de_plantilla("global_1", None) == "Muro confinado · Global · 1 planta"


def test_los_ejemplos_son_oro_pb_y_pa_y_las_dos_globales_todos_por_confirmar() -> None:
    ejemplos = {e["nombre"]: e for e in ejemplos_de_prototipo()}
    assert list(ejemplos) == [
        "Muro confinado · Oro 4.01 · PB", "Muro confinado · Oro 4.01 · PA", "Muro confinado · Global · 1 planta", "Muro confinado · Global · 2 plantas",
    ]
    assert all(e["por_confirmar"] and e["tipo"] == "confinado" for e in ejemplos.values())
    for e in ejemplos.values():
        validar_prototipo_y_planta(e["prototipo"], e["planta"])
        assert len(e["notas"]) < 6000 and "POR CONFIRMAR" in e["notas"]


def test_oro_trae_las_cantidades_del_excel_con_su_celda() -> None:
    pb = next(e for e in ejemplos_de_prototipo() if e["planta"] == "PB" and e["prototipo"] == "oro_401")
    totales = {x["tipo"]: (D(x["total_m"]), D(x["base_m2"]), x["origen"]) for x in pb["lineas"] if x["clase"] == "castillo"}
    assert {k: (v[0], v[1]) for k, v in totales.items()} == {"K-1": (126, 286), "K-2": (83, 286), "K-3": (20, 286), "K-7": (24, 286)}
    assert "ASIGNACIÓN!K2152" in totales["K-1"][2] and "ASIGNACIÓN!K2155" in totales["K-7"][2]
    pa = next(e for e in ejemplos_de_prototipo() if e["planta"] == "PA")
    assert {x["tipo"]: (D(x["total_m"]), D(x["base_m2"])) for x in pa["lineas"] if x["clase"] == "castillo"} == {
        "K-1": (D("33.6"), D("246.42")), "K-2": (84, D("246.42")), "K-3": (21, D("246.42")), "K-6": (D("14.4"), D("246.42")), "K-7": (D("16.2"), D("246.42")),
    }
    assert [x["tipo"] for x in pa["lineas"] if x["clase"] == "cadena"] == ["CE-1", "CE-2"]
    # Las dos bases suman el divisor MURO de Oro en el Excel (RESUMEN!I38).
    assert D("286") + D("246.42") == D("532.42")


def test_la_regla_total_de_oro_reproduce_el_total_del_excel_si_el_muro_mide_la_base() -> None:
    """Un muro de 286 m² (la base de planta baja) cuenta los 126 m de K-1 del Excel: es la misma fórmula L = I / D3 × D4 del libro."""
    pb = next(e for e in ejemplos_de_prototipo() if e["planta"] == "PB" and e["prototipo"] == "oro_401")
    k1 = next(x for x in pb["lineas"] if x["tipo"] == "K-1")
    elemento = {"uid": "K-1", "ref": "K-1", "clase": "castillo", "modo": "estimado", **{k: k1[k] for k in ("regla", "total_m", "base_m2")}}
    c = colocar_plantilla([elemento], largo_m=D(100), altura_m=D("2.86"), anchos_m={})  # 100 m × 2.86 m = 286 m²
    (i,) = c.instancias
    assert i.metros == pytest.approx(D(126), abs=D("0.01"))
    # Una parte de la base reparte una parte del total: 143 m² llevan la mitad.
    mitad = colocar_plantilla([elemento], largo_m=D(50), altura_m=D("2.86"), anchos_m={}).instancias[0]
    assert mitad.metros == pytest.approx(D(63), abs=D("0.01"))
