"""Lo que toda obra recién creada recibe igual, venga de la entrada que venga (WORKFLOWS.md §8.10, D-626).

- Se guarda **cómo arrancó** (prototipo, catálogo base, ingeniería o desde cero): solo informativa.
- Se **generan sus partidas** solas desde el prototipo, para que quien la abra no tenga que acordarse de «Generar actividades».
  Si no se puede (el prototipo no tiene árbol, o le falta el costo vigente de algún concepto), la obra se queda creada y
  se dice por qué; generar no es motivo para fallar el alta.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.arbol_de_obra import ArbolDeObra
from obractrl.application.casos_uso.generar_obra_desde_prototipo import (
    ComandoGenerarObra,
    GenerarObraDesdePrototipo,
)

__all__ = ["PrepararObraNueva"]


class PrepararObraNueva:
    def __init__(self, *, arbol: ArbolDeObra, generar: GenerarObraDesdePrototipo) -> None:
        self._arbol = arbol
        self._generar = generar

    async def ejecutar(self, obra_id: UUID, forma: str, *, generar: bool = True) -> dict[str, Any]:
        await self._arbol.fijar_forma_de_arranque(obra_id, forma)
        if not generar:
            return {"actividades_generadas": 0, "motivo_sin_generar": None}
        return await self.generar_partidas(obra_id)

    async def generar_partidas(self, obra_id: UUID) -> dict[str, Any]:
        try:
            r = await self._generar.ejecutar(ComandoGenerarObra(obra_id=obra_id))
        except (ValueError, LookupError) as e:  # ErrorDeGeneracion y los demás errores de dominio de la generación
            return {"actividades_generadas": 0, "motivo_sin_generar": str(e)}
        return {"actividades_generadas": r.n_actividades, "motivo_sin_generar": None}
