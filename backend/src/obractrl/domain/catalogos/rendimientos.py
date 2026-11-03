"""Los rendimientos de un destajo que se derivan, no se capturan.

`CONOCIMIENTO.md` §6.2: de los cuatro rendimientos solo el teórico (y el real,
después) se captura. El **calculado** sale del enlace con la cuadrilla:

    rendimiento calculado = costo de la cuadrilla ÷ precio del destajo
    jornadas por unidad   = precio del destajo ÷ costo de la cuadrilla

Ej. (`CATALOGOS.md` §10): $50/m² con una cuadrilla de $1,452/jornada → 0.0344
jor/m² = 29.04 m² por jornada. La comparación con el teórico es el indicador:
una razón de 1.085 sin variación en los 22 trabajos de pintor era un cambio de
salario, no un desajuste.

Módulo puro (§12.11). Sin dato no hay cifra: ``None``, nunca un cero que
diría «la cuadrilla no rinde».
"""

from __future__ import annotations

from decimal import Decimal

__all__ = ["jornadas_por_unidad", "razon_teorico_calculado", "rendimiento_calculado"]

_CUATRO = Decimal("0.0001")


def _positivo(valor: Decimal | None) -> bool:
    return valor is not None and valor > 0


def rendimiento_calculado(
    costo_cuadrilla: Decimal | None, precio_destajo: Decimal | None
) -> Decimal | None:
    """Unidades por jornada que el precio pactado implica para esa cuadrilla."""
    if not (_positivo(costo_cuadrilla) and _positivo(precio_destajo)):
        return None
    assert costo_cuadrilla is not None and precio_destajo is not None  # noqa: S101
    return (costo_cuadrilla / precio_destajo).quantize(_CUATRO)


def jornadas_por_unidad(
    costo_cuadrilla: Decimal | None, precio_destajo: Decimal | None
) -> Decimal | None:
    """Jornadas de la cuadrilla que cuesta cada unidad del destajo."""
    if not (_positivo(costo_cuadrilla) and _positivo(precio_destajo)):
        return None
    assert costo_cuadrilla is not None and precio_destajo is not None  # noqa: S101
    return (precio_destajo / costo_cuadrilla).quantize(_CUATRO)


def razon_teorico_calculado(
    rendimiento_teorico: Decimal | None, calculado: Decimal | None
) -> Decimal | None:
    """Teórico ÷ calculado. Cerca de 1 = el precio y el rendimiento supuesto
    concuerdan; una razón constante por oficio es un cambio de salario; una
    dispersa (instalaciones) dice que el teórico heredado no es confiable."""
    if not (_positivo(rendimiento_teorico) and _positivo(calculado)):
        return None
    assert rendimiento_teorico is not None and calculado is not None  # noqa: S101
    return (rendimiento_teorico / calculado).quantize(_CUATRO)
