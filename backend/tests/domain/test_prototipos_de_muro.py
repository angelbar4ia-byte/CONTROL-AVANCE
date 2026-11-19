"""Los prototipos de la plantilla de muro confinado: sus plantas y la validación de la planta."""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.cuantificacion.prototipos_de_muro import (
    PROTOTIPOS,
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
