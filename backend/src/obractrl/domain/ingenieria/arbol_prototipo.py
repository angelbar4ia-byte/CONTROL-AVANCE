"""Recorrido compartido del árbol de un prototipo (`domain.cargadores.
presupuesto.ArbolPrototipoCargado`): qué concepto cuelga de qué etapa.

Tanto identificar el prototipo (`identificacion.py`) como revertir por
destajo (`reversion.py`) necesitan lo mismo: para cada renglón `CONCEPTO`/
`CONCEPTO AUXILIAR` del árbol, su etapa (`ECO-...`) más cercana hacia la
raíz y su cantidad presupuestada EN ESA posición — la misma clave puede
colgar de dos etapas distintas con cantidades distintas
(`domain.cargadores.presupuesto`, docstring del módulo: "la misma clave de
CONCEPTO puede colgar de dos ETAPA distintas del mismo prototipo"), así que
no se puede resolver por diccionario clave→cantidad, hay que caminar el
árbol. Un solo recorrido aquí evita que las dos reglas de negocio diverjan
sobre cómo se encuentra "la etapa de este renglón".

Módulo puro: sin FastAPI, SQLModel ni RLS (§12.11).
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal

from obractrl.domain.cargadores.presupuesto import (
    ArbolPrototipoCargado,
    NodoLeido,
    TipoNodoPresupuesto,
)

__all__ = ["RenglonPrototipo", "renglones_por_etapa"]

_CONCEPTOS = (TipoNodoPresupuesto.CONCEPTO, TipoNodoPresupuesto.CONCEPTO_AUXILIAR)


class RenglonPrototipo:
    """Un `CONCEPTO`/`CONCEPTO AUXILIAR` del árbol, con la etapa que le
    tocó en esa posición."""

    __slots__ = ("etapa", "nodo")

    def __init__(self, etapa: str | None, nodo: NodoLeido) -> None:
        self.etapa = etapa
        self.nodo = nodo

    @property
    def clave(self) -> str:
        return self.nodo.clave

    @property
    def cantidad(self) -> Decimal:
        return self.nodo.cantidad or Decimal(0)


def renglones_por_etapa(arbol: ArbolPrototipoCargado) -> Iterator[RenglonPrototipo]:
    """Cada renglón `CONCEPTO`/`CONCEPTO AUXILIAR` del árbol, en el orden
    del archivo, con la `ETAPA` (`ECO-...`) más cercana hacia la raíz —
    ``None`` si cuelga directo de un `NIVEL`/`PROTOTIPO` sin etapa de por
    medio (no verificado en el archivo real, pero no se descarta)."""

    def recorrer(fila: int, etapa_actual: str | None) -> Iterator[RenglonPrototipo]:
        for hijo in arbol.hijos.get(fila, ()):
            etapa_hijo = hijo.clave if hijo.tipo is TipoNodoPresupuesto.ETAPA else etapa_actual
            if hijo.tipo in _CONCEPTOS:
                yield RenglonPrototipo(etapa_hijo, hijo)
            yield from recorrer(hijo.fila, etapa_hijo)

    yield from recorrer(arbol.raiz.fila, None)
