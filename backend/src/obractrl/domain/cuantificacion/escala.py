"""La escala de un plano: cuántos metros vale cada unidad (migración 0069).

El visor mide en coordenadas de plano; el presupuesto, en metros. La calibración
es el puente: se marcan dos puntos de una distancia conocida del plano y se dice
cuántos metros son. Aquí vive la aritmética y sus validaciones; no sabe de
PostGIS ni de la base (§12.11).

La medida se lee **ya escalada** (`area × k²`, `perimetro` y `longitud × k`,
`conteo` no cambia): la geometría guardada nunca se toca, así una recalibración
corrige todos los trazos del plano de golpe.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from decimal import ROUND_HALF_EVEN, Decimal

from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = [
    "DECIMALES_DE_ESCALA",
    "ESCALA_MAXIMA",
    "ESCALA_MINIMA",
    "escala_desde_referencia",
]

DECIMALES_DE_ESCALA = 9
"""Los de la columna `plano.escala_m_por_unidad` (`numeric(18,9)`)."""

ESCALA_MINIMA = Decimal("0.000001")
ESCALA_MAXIMA = Decimal("1000")
"""Metros por unidad de plano. Fuera de este rango la calibración casi seguro se
capturó mal —una distancia en centímetros dicha en metros, un punto fuera de
lugar—: un milímetro por unidad y mil metros por unidad son los extremos que
todavía describen un plano de obra."""


def escala_desde_referencia(
    punto_a: Sequence[float],
    punto_b: Sequence[float],
    distancia_m: Decimal,
) -> Decimal:
    """Metros por unidad de plano, dados dos puntos y la distancia real entre ellos.

    Raises:
        ErrorDeCuantificacion: los puntos no son dos coordenadas, coinciden, la
            distancia no es positiva o la escala sale de lo plausible.
    """
    for nombre, punto in (("punto_a", punto_a), ("punto_b", punto_b)):
        if len(punto) != 2 or not all(math.isfinite(c) for c in punto):
            raise ErrorDeCuantificacion(
                f"{nombre} debe ser una coordenada [x, y] finita."
            )
    if distancia_m <= 0:
        raise ErrorDeCuantificacion(
            "La distancia real debe ser positiva: son los metros entre los dos puntos."
        )

    en_plano = math.hypot(punto_b[0] - punto_a[0], punto_b[1] - punto_a[1])
    if en_plano == 0:
        raise ErrorDeCuantificacion(
            "Los dos puntos son el mismo: marca dos puntos distintos de una "
            "distancia conocida del plano."
        )

    escala = (distancia_m / Decimal(repr(en_plano))).quantize(
        Decimal(1).scaleb(-DECIMALES_DE_ESCALA), rounding=ROUND_HALF_EVEN
    )
    if not ESCALA_MINIMA <= escala <= ESCALA_MAXIMA:
        raise ErrorDeCuantificacion(
            f"La escala resultante ({escala} m por unidad de plano) no es "
            f"plausible: revisa que la distancia esté en metros y que los puntos "
            f"sean los de la cota."
        )
    return escala
