"""Lo que paga el cimiento de cada espacio de una zona de losa, escrito en la partida del árbol donde se mide (0143, 0146).

Igual que `TomasDeEscaleras`: el cálculo del cimiento dice qué concepto paga (MCT-01011, del catálogo) y cuánto mide; el espacio dice en qué partida se mide. Solo cuenta lo
asignado a un espacio, con concepto en el catálogo y partida en el árbol; sin escala calibrada o con un dato que no vale no escribe. Cada cimiento va en **un** espacio: sin doble conteo.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = ["TomasDeCimientos"]


class TomasDeCimientos:
    def __init__(self, *, zonas: Any, cimientos: Any) -> None:
        self._zonas = zonas
        self._cimientos = cimientos

    async def tomas_de_la_obra(self, obra_id: UUID) -> list[tuple[UUID, UUID, Decimal, str]]:
        salida: list[tuple[UUID, UUID, Decimal, str]] = []
        for zona in await self._zonas.zonas_de_la_obra(obra_id):
            try:
                r = await self._cimientos.calculo(UUID(str(zona["id"])))
            except ErrorDeCuantificacion:
                continue
            if not r.get("escala_definida"):
                continue
            for grupo in r["por_espacio"]:
                for c in grupo["conceptos"]:
                    res = c["resolucion"]
                    if res["cuenta"] and res["partida_id"] is not None and res["concepto_id"] is not None:
                        salida.append((UUID(str(res["partida_id"])), UUID(str(res["concepto_id"])), Decimal(str(c["cantidad"])), str(c["unidad"])))
        return salida
