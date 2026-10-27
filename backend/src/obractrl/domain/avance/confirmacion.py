"""Confirmar el avance antes de estimar (migración 0070; cerebro MODELO.md
D-533, D-534, D-535).

El cerebro separa **registrar** el avance —anotar lo que se hizo, siempre, sin
bloqueo— de **confirmarlo**: el residente afirma que esa cifra es la real. Hay
dos momentos, al terminar una actividad y antes de estimar.

*Confirmar no es un candado*, pero lo que se estima por encima de lo confirmado
es **una alerta importante** (D-535); su salida es bajar las cantidades de la
estimación. Aquí vive la aritmética de las dos preguntas —¿está al día la
confirmación? ¿el renglón de la estimación tiene respaldo?— y quién confirma. Sin
BD ni FastAPI (§12.11).
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from obractrl.domain.shared.diccionario import Rol

__all__ = [
    "AlertaDeRespaldo",
    "ErrorDeConfirmacion",
    "EstadoDeConfirmacion",
    "alerta_de_respaldo",
    "estado_de_confirmacion",
    "exigir_algo_que_confirmar",
    "exigir_residente",
]


class ErrorDeConfirmacion(ValueError):
    """La confirmación no se puede registrar."""


class EstadoDeConfirmacion(StrEnum):
    SIN_CONFIRMAR = "sin_confirmar"
    """Nadie la ha confirmado nunca."""
    DESACTUALIZADA = "desactualizada"
    """Se confirmó, pero el avance cambió después: hay que volver a confirmar."""
    CONFIRMADA = "confirmada"
    """Lo confirmado es lo ejecutado."""


class AlertaDeRespaldo(StrEnum):
    """`pago_sin_respaldo_avance` (MODELO.md §5a), leída contra la confirmación."""

    SIN_CONFIRMAR = "sin_confirmar"
    """Se estima una actividad cuyo avance nadie confirmó."""
    POR_ENCIMA = "por_encima"
    """Se estima más de lo que se confirmó."""


def exigir_residente(rol: Rol) -> None:
    """Confirma el **residente** (D-534): es quien afirma que lo registrado es lo
    que se hizo. El supervisor y Control revisan y validan, pero no confirman."""
    if rol is not Rol.RESIDENTE:
        raise ErrorDeConfirmacion(
            f"Confirma el avance el residente; el rol {rol.value!r} no puede."
        )


def exigir_algo_que_confirmar(cant_ejecutada: Decimal) -> None:
    if cant_ejecutada <= 0:
        raise ErrorDeConfirmacion(
            "La actividad no tiene avance capturado: no hay nada que confirmar."
        )


def estado_de_confirmacion(
    cant_ejecutada: Decimal, cant_confirmada: Decimal | None
) -> EstadoDeConfirmacion:
    if cant_confirmada is None:
        return EstadoDeConfirmacion.SIN_CONFIRMAR
    if cant_confirmada == cant_ejecutada:
        return EstadoDeConfirmacion.CONFIRMADA
    return EstadoDeConfirmacion.DESACTUALIZADA


def alerta_de_respaldo(
    cantidad_estimada: Decimal, cant_confirmada: Decimal | None
) -> tuple[AlertaDeRespaldo, Decimal] | None:
    """La alerta de un renglón de la estimación y **cuánto** excede, o `None` si
    tiene respaldo.

    Sin confirmación todo lo estimado carece de respaldo; con ella, lo que pase de
    lo confirmado. No bloquea nada: avisa a quienes la resuelven (supervisor y
    Control de obra, WORKFLOWS.md §8), y se resuelve bajando la cantidad estimada
    o confirmando el avance real.
    """
    if cantidad_estimada <= 0:
        return None
    if cant_confirmada is None:
        return AlertaDeRespaldo.SIN_CONFIRMAR, cantidad_estimada
    if cantidad_estimada > cant_confirmada:
        return AlertaDeRespaldo.POR_ENCIMA, cantidad_estimada - cant_confirmada
    return None
