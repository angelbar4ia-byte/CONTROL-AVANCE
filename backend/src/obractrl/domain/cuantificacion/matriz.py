"""Las matrices internas de una actividad y lo que su medición cambia (cerebro WORKFLOWS.md §8.9,
«Las hojas del árbol»; D-565, D-583).

La matriz es la receta de un concepto; el concepto es la matriz madre y **un insumo puede ser otra
matriz** (nervaduras, trabes, bastones), a cualquier profundidad. Lo que se cuantifica son esas
matrices internas. Su cantidad medida es de **esa obra** y no reescribe el catálogo: con ella el
importe de la actividad se **ajusta**, sin tocar su cantidad base.

Reglas del ajuste:

- Una matriz medida cambia el importe en `(medido − lo que el catálogo implicaba) × su PU`.
- **Una matriz medida manda sobre las de adentro:** si se midieron las nervaduras, lo que se haya
  medido de las matrices dentro de ellas ya está en su cantidad y no se vuelve a ajustar.
- Si una misma matriz aparece por dos caminos (los estribos dentro de las nervaduras y de las
  trabes), lo que el catálogo implicaba es la suma de los caminos que quedan al descubierto.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class NodoDeMatriz:
    concepto_id: str
    ruta: tuple[str, ...]
    """Del concepto de la actividad (matriz madre) a esta matriz, ambos incluidos."""
    acumulada: Decimal
    """Cantidad de esta matriz por unidad de la actividad, multiplicada a lo largo de la ruta."""
    precio_unitario: Decimal
    cantidad_medida: Decimal | None = None

    def catalogo(self, cant_base: Decimal) -> Decimal:
        return self.acumulada * cant_base


@dataclass(frozen=True, slots=True)
class Ajuste:
    importe_ajuste: Decimal
    medidas: int
    """Cuántas matrices (distintas) cuentan en el ajuste."""


def ajuste_por_medicion(nodos: Sequence[NodoDeMatriz], *, cant_base: Decimal) -> Ajuste:
    medidos = {n.concepto_id for n in nodos if n.cantidad_medida is not None}
    ajuste = Decimal("0")
    contados: set[str] = set()
    for concepto in medidos:
        filas = [n for n in nodos if n.concepto_id == concepto]
        # Un camino queda al descubierto si ninguna matriz intermedia de su ruta está medida.
        descubiertas = [
            n for n in filas if not any(a in medidos for a in n.ruta[1:-1])
        ]
        if not descubiertas:
            continue  # todos sus caminos pasan por una matriz medida más arriba
        medida = next(n.cantidad_medida for n in filas if n.cantidad_medida is not None)
        implicada = sum((n.catalogo(cant_base) for n in descubiertas), Decimal("0"))
        ajuste += (medida - implicada) * descubiertas[0].precio_unitario
        contados.add(concepto)
    return Ajuste(ajuste, len(contados))
