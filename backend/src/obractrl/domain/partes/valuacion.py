"""Cómo se valúa una parte: por PU, por ensamble (paramétrico) o mixto (cerebro WORKFLOWS.md
§8.1 y §8.9; D-571, D-578, D-579).

*«Mixto no se guarda, se reporta en porcentaje»*: no hay un campo «mixto». Se calcula al leer, del
importe de los renglones **estimados** (los que vienen de un ensamble) sobre el importe de la
parte. Y *«lo medido vuelve al paramétrico»*: cuando una medición sustituye a lo estimado, la
diferencia entre las dos se reporta —se propone, no se aplica— para que el paramétrico aprenda.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

_CIEN = Decimal("100")
_DOS = Decimal("0.01")


class FormaDeValuacion(StrEnum):
    PU = "pu"
    PARAMETRICO = "parametrico"
    MIXTO = "mixto"


@dataclass(frozen=True, slots=True)
class LineaValuada:
    """Un renglón de la parte: lo que vale y de dónde sale su cantidad."""

    cantidad: Decimal
    precio: Decimal
    estimada: bool
    """Su cantidad viene de un ensamble y nadie la ha medido."""
    cant_estimada: Decimal | None = None
    """Lo que estimaba el paramétrico, si una medición ya lo sustituyó."""

    @property
    def importe(self) -> Decimal:
        return self.cantidad * self.precio


@dataclass(frozen=True, slots=True)
class ValuacionDeParte:
    forma: FormaDeValuacion
    importe: Decimal
    importe_parametrico: Decimal
    porcentaje_parametrico: Decimal
    n_estimadas: int
    n_total: int
    estimado_original: Decimal
    """Lo que valían, al precio de hoy, los renglones que una medición ya sustituyó."""
    medido: Decimal
    """Lo que valen esos mismos renglones medidos."""
    desviacion_pct: Decimal | None
    """Cuánto se alejó lo medido de lo estimado; `None` si aún no se sustituyó nada."""


def valuar(lineas: Sequence[LineaValuada]) -> ValuacionDeParte:
    importe = sum((x.importe for x in lineas), Decimal("0"))
    parametrico = sum((x.importe for x in lineas if x.estimada), Decimal("0"))
    n_estimadas = sum(1 for x in lineas if x.estimada)
    if importe > 0:
        pct = (parametrico / importe * _CIEN).quantize(_DOS)
    else:  # sin importe, lo que cuenta es cuántos renglones son estimados
        pct = (Decimal(n_estimadas) / len(lineas) * _CIEN).quantize(_DOS) if lineas else Decimal("0.00")
    forma = (
        FormaDeValuacion.PU
        if n_estimadas == 0
        else FormaDeValuacion.PARAMETRICO
        if n_estimadas == len(lineas)
        else FormaDeValuacion.MIXTO
    )
    sustituidas = [x for x in lineas if x.cant_estimada is not None]
    estimado = sum((x.cant_estimada * x.precio for x in sustituidas if x.cant_estimada is not None), Decimal("0"))
    medido = sum((x.importe for x in sustituidas), Decimal("0"))
    desviacion = ((medido - estimado) / estimado * _CIEN).quantize(_DOS) if estimado > 0 else None
    return ValuacionDeParte(
        forma, importe, parametrico, pct, n_estimadas, len(lineas), estimado, medido, desviacion
    )
