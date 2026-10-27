"""Modificar un prototipo antes de asignar: cambios y adicionales (cerebro WORKFLOWS.md §8.9,
escenario 3; D-573, D-574, D-575).

Dos tipos:

- **cambio**: puede ser negativo —se elimina del presupuesto— y es también modificación de
  muebles. Lo que cambia puede aplicar sobre un concepto del prototipo o nacer nuevo.
- **adicional**: los highlights y los conceptos fuera de catálogo. Solo suma.

Una ampliación puede ser un cambio, un adicional o ambos (D-575); pasar de una a dos plantas se
resuelve con estos mismos tipos. Se dice cuánto **cambia** (`delta`) y no la cantidad nueva:
así el cambio negativo es explícito y la bitácora cuenta la historia.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class TipoDeModificacion(StrEnum):
    CAMBIO = "cambio"
    ADICIONAL = "adicional"


class ErrorDeModificacion(ValueError):
    """La modificación no cabe: delta cero, adicional que resta, o cantidad que quedaría negativa."""


@dataclass(frozen=True, slots=True)
class Modificacion:
    tipo: TipoDeModificacion
    cantidad_antes: Decimal
    delta: Decimal
    cantidad_despues: Decimal


def modificar(tipo: TipoDeModificacion, *, cantidad_actual: Decimal, delta: Decimal) -> Modificacion:
    if delta == 0:
        raise ErrorDeModificacion("Una modificación que no cambia nada no se registra.")
    if tipo is TipoDeModificacion.ADICIONAL and delta < 0:
        raise ErrorDeModificacion(
            "Un adicional solo suma; para quitar algo del presupuesto usa un cambio."
        )
    despues = cantidad_actual + delta
    if despues < 0:
        raise ErrorDeModificacion(
            f"El cambio dejaría la cantidad en {despues}: eliminar el concepto es dejarla en cero."
        )
    return Modificacion(tipo, cantidad_actual, delta, despues)
