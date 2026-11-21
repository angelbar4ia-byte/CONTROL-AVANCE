"""Lo que paga el relleno de cada espacio de una zona de losa, escrito en la partida del árbol donde se mide (0143, 0144).

Igual que `TomasDeLosas`: el cálculo del relleno (`relleno_de_zona`) dice qué concepto paga cada espacio y cuánto mide; el espacio dice en qué partida se mide.
Una `toma` es `(partida, concepto, cantidad, unidad)`; `SincronizarTomas` las suma a las de la obra y las escribe en la actividad de esa partida.

Qué cuenta y qué no (valor conservador, el mismo de la losa):

- Solo cuenta lo que está **asignado a un espacio** (el del relleno o el de su polígono) y cuyo concepto **existe en el catálogo** y **tiene partida** en el
  árbol (en ese espacio o una general). Lo demás avisa en el cálculo y no escribe: sin espacio, concepto propuesto (el relleno compactado EJ-810 hasta que
  se autorice y esté en el catálogo), falta la partida.
- Una zona cuyo plano **no tiene escala calibrada** no escribe nada.
- Cada polígono va en **un** espacio y el relleno se paga con un concepto distinto del de la losa, así que lo escrito suma lo que dice el cálculo: sin doble conteo.
- Lo medido directo con trazos sobre la partida manda sobre lo tomado (D-584): lo resuelve la escritura, no esta clase.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = ["TomasDeRellenos"]


class TomasDeRellenos:
    def __init__(self, *, zonas: Any, rellenos: Any) -> None:
        self._zonas = zonas
        self._rellenos = rellenos

    async def tomas_de_la_obra(self, obra_id: UUID) -> list[tuple[UUID, UUID, Decimal, str]]:
        """`(partida_id, concepto_id, cantidad, unidad)` de lo que paga el relleno de cada espacio de la obra y cuenta."""
        salida: list[tuple[UUID, UUID, Decimal, str]] = []
        for zona in await self._zonas.zonas_de_la_obra(obra_id):
            try:
                r = await self._rellenos.calculo(UUID(str(zona["id"])))
            except ErrorDeCuantificacion:
                continue  # una zona con un dato que no vale se omite; su cálculo dice por qué
            if not r.get("escala_definida"):
                continue
            for grupo in r["por_espacio"]:
                for c in grupo["conceptos"]:
                    res = c["resolucion"]
                    if res["cuenta"] and res["partida_id"] is not None and res["concepto_id"] is not None:
                        salida.append((UUID(str(res["partida_id"])), UUID(str(res["concepto_id"])), Decimal(str(c["cantidad"])), str(c["unidad"])))
        return salida
