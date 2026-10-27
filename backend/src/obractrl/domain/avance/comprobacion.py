"""Comprobación y validación del excedente de ejecución (migración 0066).

Cuando se ejecuta más de lo programado, **se registra** —el cerebro lo dice de
frente: «registrar nunca se bloquea»— y el excedente queda pendiente de
comprobación y validación de Control de obra. Tiene dos destinos
(WORKFLOWS.md §8.1, CONOCIMIENTO.md §13.3):

  * **se valida**: se vuelve control de cambio —la orden que lo respalda— y sube
    el techo de la actividad a lo que de verdad se ejecutó;
  * **es pérdida**: se ejecutó y no se cobra; deja de ser pendiente.

Módulo puro: sin BD ni FastAPI (§12.11). Qué cuenta como excedente es
`domain.avance.reglas.excedente_de`; aquí vive quién decide y con qué.
"""

from __future__ import annotations

from decimal import Decimal

from obractrl.domain.obras.control_cambio import puede_autorizar
from obractrl.domain.shared.diccionario import Rol

__all__ = [
    "ErrorDeComprobacion",
    "SinExcedente",
    "exigir_nota",
    "exigir_orden_de_cambio",
    "puede_comprobar",
    "techo_tras_validar",
]


class ErrorDeComprobacion(ValueError):
    """Dato inválido al decidir sobre un excedente (422)."""

    def __init__(self, mensaje: str, campo: str) -> None:
        super().__init__(mensaje)
        self.campo = campo


class SinExcedente(RuntimeError):
    """La actividad no tiene excedente pendiente: nada que decidir (409).

    También es lo que se ve cuando dos personas deciden a la vez: la segunda
    llega y ya no hay nada pendiente.
    """


def puede_comprobar(rol: Rol) -> bool:
    """Quien decide el excedente es quien autoriza un control de cambio: Control
    de obra y el Super intendente (§4). No el residente, que lo originó al
    ejecutarlo: es la misma separación del cierre y del control de cambio."""
    return puede_autorizar(rol)


def exigir_nota(nota: str | None) -> str:
    texto = (nota or "").strip()
    if not texto:
        raise ErrorDeComprobacion(
            "Decidir un excedente deja constancia: escribe qué se comprobó.", "nota"
        )
    return texto


def exigir_orden_de_cambio(orden_cambio: str | None) -> str:
    texto = (orden_cambio or "").strip()
    if not texto:
        raise ErrorDeComprobacion(
            "Validar necesita la orden de cambio que lo respalda: sin ella la "
            "validación no autoriza nada.",
            "orden_cambio",
        )
    return texto


def techo_tras_validar(
    *, cant_ejecutada: Decimal, cant_autorizada: Decimal | None
) -> tuple[Decimal, Decimal]:
    """`(cant_programada, cant_autorizada)` después de validar.

    Lo programado sube a lo ejecutado: lo que se hizo y se validó ya es lo que
    se mandó hacer. Y `cant_autorizada` —el techo que Control firmó, 0049— nunca
    baja: si ya había una autorización más alta, se conserva.
    """
    return cant_ejecutada, max(cant_ejecutada, cant_autorizada or Decimal(0))
