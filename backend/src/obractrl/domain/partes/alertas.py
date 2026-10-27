"""La alerta de desfase del presupuesto (cerebro WORKFLOWS.md §8.9, D-575 a D-577).

«El presupuesto debe ir por delante de la programación; si no hay programación, se retrasa la
obra.» Una parte debe estar **presupuestada y autorizada al menos 1 semana antes de lo que el
programa base necesita programarla, de preferencia 2** (D-576): a **2 semanas** de que el
programa la necesite y sin autorizar es un **aviso**; a **1 semana** (o ya vencida) es
**importante**. Los umbrales son **globales y afectan a cada obra** (D-577). Avisan; no bloquean.

Módulo puro: sin BD ni FastAPI (§12.11).
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

__all__ = [
    "AVISO_DIAS",
    "IMPORTANTE_DIAS",
    "ErrorDeUmbrales",
    "Severidad",
    "dias_para_necesitarla",
    "severidad_del_desfase",
    "validar_umbrales",
]

AVISO_DIAS = 14
"""Dos semanas: lo preferible (D-576)."""
IMPORTANTE_DIAS = 7
"""Una semana: lo mínimo (D-576)."""


class Severidad(StrEnum):
    AVISO = "aviso"
    IMPORTANTE = "importante"


class ErrorDeUmbrales(ValueError):
    """Los umbrales de la alerta no son coherentes."""


def validar_umbrales(aviso_dias: int, importante_dias: int) -> tuple[int, int]:
    if importante_dias < 0:
        raise ErrorDeUmbrales("Los días de la alerta importante no pueden ser negativos.")
    if aviso_dias < importante_dias:
        raise ErrorDeUmbrales(
            "El aviso va antes que la alerta importante: sus días deben ser iguales o más."
        )
    return aviso_dias, importante_dias


def dias_para_necesitarla(inicio: date, hoy: date) -> int:
    """Cuántos días faltan para que el programa necesite la parte (negativo: ya la necesitaba)."""
    return (inicio - hoy).days


def severidad_del_desfase(
    dias: int, *, aviso_dias: int = AVISO_DIAS, importante_dias: int = IMPORTANTE_DIAS
) -> Severidad | None:
    """`importante` a la semana o menos (o vencida), `aviso` a las dos semanas, nada más lejos."""
    if dias <= importante_dias:
        return Severidad.IMPORTANTE
    if dias <= aviso_dias:
        return Severidad.AVISO
    return None
