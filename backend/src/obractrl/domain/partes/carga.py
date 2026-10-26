"""`ESTADO_CARGA` de una parte (cerebro MODELO.md §3, D-30, D-191).

El presupuesto llega por partes, a veces durante meses. Esto dice cuánta ingeniería de una
parte ya llegó: importe cargado entre importe presupuestado. Se calcula al leer —el cerebro
lo llama caché y «nunca fuente de verdad»— y **una carga incompleta nunca bloquea**: avisa.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

_CIEN = Decimal("100")
_DOS = Decimal("0.01")


class EstadoDeCarga(StrEnum):
    INCOMPLETO = "incompleto"
    COMPLETO = "completo"


@dataclass(frozen=True, slots=True)
class CargaDeParte:
    estado: EstadoDeCarga
    porcentaje_cargado: Decimal
    """0 a 100: lo cargado sobre lo presupuestado, sin pasar de 100."""
    importe_pendiente: Decimal
    """Lo que falta cargar (0 si ya está completa o se cargó de más)."""


def estado_de_carga(*, cargado: Decimal, presupuestado: Decimal) -> CargaDeParte:
    """`completo` solo cuando la ingeniería cubre el presupuesto vigente (100 %).

    Sin presupuesto no hay contra qué comparar: con algo cargado se da por completa; sin nada,
    incompleta en 0 %.
    """
    if presupuestado <= 0:
        completo = cargado > 0
        return CargaDeParte(
            EstadoDeCarga.COMPLETO if completo else EstadoDeCarga.INCOMPLETO,
            _CIEN if completo else Decimal("0.00"),
            Decimal("0"),
        )
    completo = cargado >= presupuestado
    # El redondeo no puede dar 100 a lo que todavía no cubre el presupuesto.
    pct = _CIEN if completo else min(
        Decimal("99.99"), (max(cargado, Decimal("0")) / presupuestado * _CIEN).quantize(_DOS)
    )
    return CargaDeParte(
        EstadoDeCarga.COMPLETO if completo else EstadoDeCarga.INCOMPLETO,
        pct,
        max(presupuestado - cargado, Decimal("0")),
    )
