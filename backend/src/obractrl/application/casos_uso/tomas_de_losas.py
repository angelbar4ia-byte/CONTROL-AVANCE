"""Lo que paga la matriz de cada espacio de una zona de losa, escrito en la partida del árbol donde se mide (0143).

La matriz de una zona (`matriz_de_losa`) calcula qué conceptos paga la losa y cuánto mide cada uno. La capa «espacio» dice en qué cuarto cae cada
polígono y cada elemento, y el espacio dice en qué partida del árbol se mide el concepto: de ahí salen las tomas. Una `toma` es
`(partida, concepto, cantidad, unidad)`; `SincronizarTomas` las suma a las de la obra y las escribe en la actividad de esa partida.

Qué cuenta y qué no (valor conservador):

- Solo cuenta lo que está **asignado a un espacio** y cuyo concepto **existe en el catálogo** y **tiene partida** en el árbol (en ese espacio o una
  general). Lo demás avisa en la matriz y no escribe: sin espacio, concepto propuesto, falta la partida.
- Una zona cuyo plano **no tiene escala calibrada** no escribe nada (la matriz toma 1 unidad de plano = 1 m solo para mostrar).
- Cada polígono y cada elemento va en **un** espacio, así que lo escrito suma lo que dice la matriz de la zona: sin doble conteo.
- Lo medido directo con trazos sobre la partida manda sobre lo tomado (D-584): lo resuelve la escritura, no esta clase.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = ["TomasDeLosas"]


class TomasDeLosas:
    def __init__(self, *, zonas: Any, matriz: Any) -> None:
        self._zonas = zonas
        self._matriz = matriz

    async def tomas_de_la_obra(self, obra_id: UUID) -> list[tuple[UUID, UUID, Decimal, str]]:
        """`(partida_id, concepto_id, cantidad, unidad)` de lo que paga la losa de cada espacio de la obra y cuenta."""
        salida: list[tuple[UUID, UUID, Decimal, str]] = []
        for zona in await self._zonas.zonas_de_la_obra(obra_id):
            try:
                r = await self._matriz.matriz(UUID(str(zona["id"])))
            except ErrorDeCuantificacion:
                continue  # una zona con un dato que no vale se omite; su matriz dice por qué
            if not r.get("escala_definida"):
                continue
            for grupo in r["por_espacio"]:
                for c in grupo["conceptos"]:
                    res = c["resolucion"]
                    if res["cuenta"] and res["partida_id"] is not None and res["concepto_id"] is not None:
                        salida.append((UUID(str(res["partida_id"])), UUID(str(res["concepto_id"])), Decimal(str(c["cantidad"])), str(c["unidad"])))
        return salida
