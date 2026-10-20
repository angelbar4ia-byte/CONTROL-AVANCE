"""Consolidar la ingeniería de un lote: varios archivos, un solo total por
clave y por etapa (CONOCIMIENTO.md §11.8 "Se suman, no se reemplazan").

Cada archivo de `domain.cargadores.ingenieria_lote` cubre su propio tramo
del presupuesto (una cimentación, una planta, un ajuste): ninguno
reemplaza a otro, así que consolidar es sumar — nunca el último que gana
(a diferencia de `cpu._agrupar_conceptos_plano`, donde una clave repetida
SÍ sustituye al bloque anterior, §10.2). Esto es una vista agregada de
lectura (P-36 del cerebro, "no se consolida al cargar — cada lector agrupa
a su modo"): no hay nada que persistir aquí, las `FilaInsumoIngenieria`
originales siguen siendo la fuente.

Módulo puro: sin FastAPI, SQLModel ni RLS (§12.11).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from obractrl.domain.cargadores.ingenieria_lote import FilaInsumoIngenieria

__all__ = ["ConsolidadoLote", "InsumoConsolidado", "consolidar_lote"]


@dataclass(frozen=True, slots=True)
class InsumoConsolidado:
    cantidad: Decimal
    importe: Decimal


@dataclass(frozen=True, slots=True)
class ConsolidadoLote:
    """El lote entero, sumado de todos los archivos que lo componen."""

    total_importe: Decimal
    total_por_etapa: dict[str, Decimal] = field(default_factory=dict)
    """Solo las filas con ``etapa`` conocida (``ECO-...``); las de un
    archivo `SUELTA`/`CON_CONCEPTO` sin etapa no entran aquí, pero sí en
    `total_importe`."""

    por_clave: dict[str, InsumoConsolidado] = field(default_factory=dict)
    por_etapa_y_clave: dict[tuple[str, str], InsumoConsolidado] = field(default_factory=dict)
    """Clave de la reversión por destajo (§11.9/D-489): "los candidatos de
    un destajo son los conceptos de ESA MISMA etapa", así que el destajo
    también se consolida POR etapa, no solo por clave global."""


def consolidar_lote(filas: Sequence[FilaInsumoIngenieria]) -> ConsolidadoLote:
    """Suma, por clave y por (etapa, clave), todas las filas de insumo del
    lote — de cuantos archivos sea.
    """
    total_importe = Decimal(0)
    total_por_etapa: dict[str, Decimal] = defaultdict(Decimal)
    cant_por_clave: dict[str, Decimal] = defaultdict(Decimal)
    imp_por_clave: dict[str, Decimal] = defaultdict(Decimal)
    cant_por_etapa_clave: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    imp_por_etapa_clave: dict[tuple[str, str], Decimal] = defaultdict(Decimal)

    for f in filas:
        importe = f.importe or Decimal(0)
        total_importe += importe
        cant_por_clave[f.clave] += f.cantidad
        imp_por_clave[f.clave] += importe
        if f.etapa is not None:
            total_por_etapa[f.etapa] += importe
            cant_por_etapa_clave[(f.etapa, f.clave)] += f.cantidad
            imp_por_etapa_clave[(f.etapa, f.clave)] += importe

    por_clave = {
        clave: InsumoConsolidado(cantidad=cant_por_clave[clave], importe=imp_por_clave[clave])
        for clave in cant_por_clave
    }
    por_etapa_y_clave = {
        llave: InsumoConsolidado(cantidad=cant_por_etapa_clave[llave], importe=imp_por_etapa_clave[llave])
        for llave in cant_por_etapa_clave
    }
    return ConsolidadoLote(
        total_importe=total_importe,
        total_por_etapa=dict(total_por_etapa),
        por_clave=por_clave,
        por_etapa_y_clave=por_etapa_y_clave,
    )
