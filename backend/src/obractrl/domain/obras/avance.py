"""Avance de la obra: se **deriva** del avance de sus actividades (§6, §8.2).

Cerebro (`MODELO.md` §3b, D-514): el estatus de la obra «se deriva del avance
físico», y ese avance se agrega **ponderado por costo**, no por promedio simple
(`MODELO.md` §5, `frente_listo_para_cierre`: «ejecutado ÷ ingeniería, ponderado
por costo»).

El peso de cada actividad es su **importe** (`cant_base × precio_unitario`), el
mismo con el que `domain.programacion.jerarquia` pesa las barras resumen del
Gantt: un promedio simple diría que una obra va al 50 % con el muro de $122k en
cero y el castillo de $10k terminado, y esa obra va al 7.58 %.

Si ninguna actividad tiene importe (una obra recién cargada, sin precios) no hay
a quién darle más peso y cae al promedio simple.

**La regla se define aquí y la base la repite.** El móvil escribe el avance
directo a Postgres por PowerSync, sin pasar por los casos de uso (decisión D5),
así que el recálculo vive en el trigger `app.obra_recalcular_avance`
(migración 0064). `tests/integracion/test_avance_de_obra_endtoend.py` comprueba
que la base y esta función dan lo mismo.

Módulo puro: sin FastAPI, SQLModel ni RLS (§12.11).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from obractrl.domain.shared.valores import Avance

__all__ = ["ActividadParaAvance", "avance_de_obra"]


@dataclass(frozen=True, slots=True)
class ActividadParaAvance:
    """Lo que pesa y lo que avanzó una actividad."""

    importe: Decimal
    """`cant_base × precio_unitario`. Un importe negativo no resta peso: se
    toma como cero."""
    avance: Avance


def avance_de_obra(actividades: Sequence[ActividadParaAvance]) -> Avance:
    """Avance de la obra: promedio de sus actividades ponderado por importe.

    Sin actividades no hay nada que medir: cero. Redondea a centésimas con
    `ROUND_HALF_UP`, igual que `Avance` y que el `round()` de Postgres.
    """
    if not actividades:
        return Avance(0)

    pesos = [max(a.importe, Decimal(0)) for a in actividades]
    total = sum(pesos, Decimal(0))

    if total <= 0:
        return Avance(
            sum((a.avance.pct for a in actividades), Decimal(0)) / len(actividades)
        )

    acumulado = sum(
        (p * a.avance.pct for p, a in zip(pesos, actividades, strict=True)), Decimal(0)
    )
    return Avance(acumulado / total)
