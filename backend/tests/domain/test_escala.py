"""La escala de un plano (migración 0069): de dos puntos y una distancia real a
metros por unidad."""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.cuantificacion.escala import escala_desde_referencia
from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion


def test_dos_puntos_a_cien_unidades_que_son_cinco_metros() -> None:
    assert escala_desde_referencia([0, 0], [100, 0], Decimal("5")) == Decimal("0.05")


def test_la_distancia_es_euclidiana_no_por_eje() -> None:
    # 3-4-5: el segmento mide 5 unidades; si son 10 m, cada unidad vale 2 m.
    assert escala_desde_referencia([0, 0], [3, 4], Decimal("10")) == Decimal("2")


def test_no_importa_el_sentido_de_los_puntos() -> None:
    assert escala_desde_referencia([100, 0], [0, 0], Decimal("5")) == escala_desde_referencia(
        [0, 0], [100, 0], Decimal("5")
    )


def test_redondea_a_nueve_decimales() -> None:
    assert escala_desde_referencia([0, 0], [3, 0], Decimal("1")) == Decimal("0.333333333")


@pytest.mark.parametrize("distancia", ["0", "-2"])
def test_la_distancia_real_debe_ser_positiva(distancia: str) -> None:
    with pytest.raises(ErrorDeCuantificacion, match="positiva"):
        escala_desde_referencia([0, 0], [10, 0], Decimal(distancia))


def test_dos_puntos_iguales_no_calibran_nada() -> None:
    with pytest.raises(ErrorDeCuantificacion, match="mismo"):
        escala_desde_referencia([5, 5], [5, 5], Decimal("3"))


def test_un_punto_mal_formado_se_rechaza() -> None:
    with pytest.raises(ErrorDeCuantificacion, match="punto_a"):
        escala_desde_referencia([1], [0, 0], Decimal("3"))
    with pytest.raises(ErrorDeCuantificacion, match="punto_b"):
        escala_desde_referencia([0, 0], [float("nan"), 0], Decimal("3"))


def test_una_escala_implausible_se_rechaza() -> None:
    # 10 mil metros en 1 unidad: casi seguro metros por centímetros.
    with pytest.raises(ErrorDeCuantificacion, match="plausible"):
        escala_desde_referencia([0, 0], [1, 0], Decimal("10000"))
    with pytest.raises(ErrorDeCuantificacion, match="plausible"):
        escala_desde_referencia([0, 0], [10_000_000, 0], Decimal("1"))
