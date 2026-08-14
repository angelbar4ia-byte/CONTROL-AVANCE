"""Regla del movimiento de almacén (§7.7, §10.5).

Spec §10.5 (motivos con signo) · §7.7 (`SalidaAlmacen`).

`salida_almacen.cantidad` ya trae signo —columna `Efecto Qty` del archivo,
comentario en `database/migrations/20260814000008_materiales_y_almacen.sql`—
y el motivo (`motivo_almacen.signo`, semilla editable §8.7) solo clasifica el
bucket de KPI, no decide el signo (§10.5: "El signo viene en el archivo; el
motivo solo clasifica el bucket"). La única regla de dominio real aquí es de
consistencia: el signo capturado en `cantidad` debe coincidir con el signo
declarado por el motivo elegido. Si no coincide, no es "un movimiento válido
con signo distinto" — es un dato mal capturado (motivo equivocado o cantidad
con el signo volteado), y se rechaza antes de tocar la base.

Sin esta regla, un residente podría capturar una "Recepción de material"
(signo +) con cantidad negativa y el cruce contra presupuesto (§10.5,
`v_consumo_vs_presupuesto`) quedaría envenenado en silencio.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from obractrl.domain.shared.valores import Dinero

__all__ = ["ErrorDeMaterial", "MovimientoAlmacen", "validar_signo_salida"]


class ErrorDeMaterial(ValueError):
    """Movimiento de almacén inválido (§10.5)."""


def validar_signo_salida(cantidad: Decimal, motivo_signo: int) -> None:
    """El signo de ``cantidad`` debe coincidir con el signo del motivo (§10.5).

    Cantidad cero es inválida siempre: no hay movimiento de almacén sin
    cantidad, sin importar el motivo.
    """
    if motivo_signo not in (-1, 1):
        raise ErrorDeMaterial(
            f"Signo de motivo inválido: {motivo_signo!r}. Debe ser -1 o 1 (§10.5)."
        )
    if cantidad == 0:
        raise ErrorDeMaterial(
            "La cantidad de un movimiento de almacén no puede ser cero: no hay "
            "movimiento sin cantidad."
        )
    signo_cantidad = 1 if cantidad > 0 else -1
    if signo_cantidad != motivo_signo:
        raise ErrorDeMaterial(
            f"La cantidad ({cantidad}) trae signo {signo_cantidad:+d}, pero el "
            f"motivo exige signo {motivo_signo:+d} (§10.5). Revisa el motivo o "
            f"el signo de la cantidad capturada."
        )


@dataclass(frozen=True, slots=True)
class MovimientoAlmacen:
    """Movimiento de almacén ya validado contra su motivo (§10.5).

    Envuelve :func:`validar_signo_salida` en la construcción para que quien
    consuma el objeto reciba algo ya consistente, en vez de tener que
    acordarse de llamar la función suelta.
    """

    cantidad: Decimal
    costo: Dinero
    motivo_signo: int

    def __post_init__(self) -> None:
        validar_signo_salida(self.cantidad, self.motivo_signo)
