"""La **parte** de una obra (cerebro WORKFLOWS.md §8.9, D-575; migración 0074).

Los escenarios de arranque avanzan **por parte, no por obra**: una parte puede estar
programada mientras otra sigue cuantificándose. Una parte es **una etapa de construcción o
un concepto independiente** (losas, pisos):

* una actividad marcada `parte_independiente` es **una parte por sí sola**;
* las demás viajan con su **etapa**;
* si no tienen etapa, caen en una sola parte «sin etapa» para que nada quede fuera.

El avance de una parte es el de sus actividades ponderado por `cant_base × precio_unitario`
—el mismo peso que el de la obra—; sin importes, promedio simple.

Módulo puro: sin BD ni FastAPI (§12.11).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

__all__ = [
    "ActividadParaParte",
    "Parte",
    "TipoDeParte",
    "agrupar_en_partes",
]

_DOS = Decimal("0.01")


class TipoDeParte(StrEnum):
    ETAPA = "etapa"
    CONCEPTO = "concepto"
    SIN_ETAPA = "sin_etapa"


@dataclass(frozen=True, slots=True)
class ActividadParaParte:
    """Lo que hace falta saber de una actividad para ubicarla en su parte."""

    id: str
    descripcion: str
    avance_pct: Decimal
    importe: Decimal
    etapa_id: str | None = None
    etapa_nombre: str | None = None
    nivel_clave: str | None = None
    independiente: bool = False


@dataclass(slots=True)
class Parte:
    tipo: TipoDeParte
    id: str | None
    """`etapa_id` si es una etapa, `actividad_id` si es un concepto independiente,
    `None` en la parte «sin etapa»."""
    nombre: str
    actividad_ids: list[str] = field(default_factory=list)
    importe: Decimal = Decimal("0")
    avance_pct: Decimal = Decimal("0")

    @property
    def clave(self) -> str:
        return f"{self.tipo.value}:{self.id or '-'}"


def _avance(actividades: Sequence[ActividadParaParte]) -> Decimal:
    if not actividades:
        return Decimal("0")
    peso = sum((a.importe for a in actividades), Decimal("0"))
    if peso > 0:
        return (sum((a.avance_pct * a.importe for a in actividades), Decimal("0")) / peso).quantize(
            _DOS
        )
    return (sum((a.avance_pct for a in actividades), Decimal("0")) / len(actividades)).quantize(
        _DOS
    )


def agrupar_en_partes(actividades: Sequence[ActividadParaParte]) -> list[Parte]:
    """Las partes de la obra, en el orden en que aparece cada una por primera vez (quien
    llama ordena las actividades por nivel, etapa y concepto)."""
    grupos: dict[str, tuple[Parte, list[ActividadParaParte]]] = {}
    for a in actividades:
        if a.independiente:
            parte = Parte(TipoDeParte.CONCEPTO, a.id, a.descripcion)
        elif a.etapa_id is not None:
            nombre = (
                f"{a.nivel_clave} · {a.etapa_nombre}" if a.nivel_clave else (a.etapa_nombre or "")
            )
            parte = Parte(TipoDeParte.ETAPA, a.etapa_id, nombre)
        else:
            parte = Parte(TipoDeParte.SIN_ETAPA, None, "Sin etapa")
        _, miembros = grupos.setdefault(parte.clave, (parte, []))
        miembros.append(a)

    partes: list[Parte] = []
    for parte, miembros in grupos.values():
        parte.actividad_ids = [m.id for m in miembros]
        parte.importe = sum((m.importe for m in miembros), Decimal("0"))
        parte.avance_pct = _avance(miembros)
        partes.append(parte)
    return partes
