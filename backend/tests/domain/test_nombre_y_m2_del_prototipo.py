"""Nombre limpio y m² de un prototipo desde la descripción de su `Capítulo` (D-614)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.cargadores.presupuesto import nombre_y_m2_del_prototipo


@pytest.mark.parametrize(
    ("descripcion", "nombre", "m2"),
    [
        ("ZAFIRO 1.0 (172 M2)", "Zafiro 1.0", Decimal(172)),
        ("RUBÍ (207 M2)", "Rubí", Decimal(207)),
        ("DIAMANTE SIN CHIMENEA (239 m2)", "Diamante sin chimenea", Decimal(239)),
        ("ORO 4.01 - 4 REC Y 1 ESTUDIO (300 M2)", "Oro 4.01 - 4 rec y 1 estudio", Decimal(300)),
        ("  JADE   (230  M2)  ", "Jade", Decimal(230)),
        ("SIN METROS", "Sin metros", None),
        ("CASA (0 M2)", "Casa", None),
    ],
)
def test_nombre_limpio_y_m2_del_texto(descripcion: str, nombre: str, m2: Decimal | None) -> None:
    assert nombre_y_m2_del_prototipo(descripcion) == (nombre, m2)
