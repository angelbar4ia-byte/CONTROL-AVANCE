"""Cómo se forma la cantidad de un componente por unidad de su concepto.

La obra no captura «0.335»: lo calcula. Para habilitar el acero de un castillo K2 —4 varillas del no. 3— sabiendo
que una varilla completa mide 12 ml, **por cada ml de castillo** hacen falta 4 ÷ 12 = 0.333333 varillas, más un
0.5 % de desperdicio: 0.333333 × 1.005 = 0.335. Esa es la fórmula de **piezas comerciales**.

Módulo puro, sin infraestructura (§12.11). La cantidad se redondea a 6 decimales, que es lo que guarda `explosion`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from obractrl.domain.catalogos.reglas import ErrorDeCatalogo

__all__ = ["FormulaDePiezasComerciales", "cantidad_por_piezas_comerciales"]

_SEIS_DECIMALES = Decimal("0.000001")


@dataclass(frozen=True, slots=True)
class FormulaDePiezasComerciales:
    piezas: Decimal
    """Cuántas piezas lleva **una unidad del concepto** (4 varillas por cada ml de castillo… ver `largo`)."""
    largo: Decimal
    """Lo que mide una pieza comercial completa, en la unidad del concepto (una varilla: 12 ml)."""
    desperdicio_pct: Decimal = Decimal(0)

    def como_json(self) -> dict[str, object]:
        return {
            "tipo": "piezas_comerciales",
            "piezas": float(self.piezas),
            "largo": float(self.largo),
            "desperdicio_pct": float(self.desperdicio_pct),
        }


def cantidad_por_piezas_comerciales(formula: FormulaDePiezasComerciales) -> Decimal:
    """`piezas ÷ largo × (1 + desperdicio %)`, a 6 decimales."""
    if formula.piezas <= 0:
        raise ErrorDeCatalogo("Las piezas por unidad van por encima de cero.")
    if formula.largo <= 0:
        raise ErrorDeCatalogo("Lo que mide la pieza comercial va por encima de cero.")
    if not (Decimal(0) <= formula.desperdicio_pct <= Decimal(100)):
        raise ErrorDeCatalogo("El desperdicio es un porcentaje de 0 a 100.")
    bruto = formula.piezas / formula.largo
    return (bruto * (1 + formula.desperdicio_pct / 100)).quantize(
        _SEIS_DECIMALES, rounding=ROUND_HALF_UP
    )
