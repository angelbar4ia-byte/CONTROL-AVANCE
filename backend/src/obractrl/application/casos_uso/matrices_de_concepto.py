"""Caso de uso: las matrices de un concepto del catálogo (entrega 5b).

Una matriz es un concepto que compone a otro: va en su `explosion` como hijo de tipo concepto,
con la cantidad que lleva **por unidad del padre**. Aquí se agregan, se les cambia la cantidad y se
quitan; la matriz puede ser una que ya existe o nacer en el mismo paso.

La composición es del **catálogo**: el cambio vale para todas las obras que usen el concepto. No
publica una versión nueva de CPU —el costo se recalcula aparte—, y la fila queda sin versión (la
«composición viva», §10.8), que el árbol del cuantificador ya lee. Una carga de CPU que sustituya la
composición del concepto reemplaza también estas filas.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.calcular_cpu import ConceptoNoEncontrado
from obractrl.application.puertos.repositorios import UnidadDeTrabajo
from obractrl.domain.catalogos.cantidad import (
    FormulaDePiezasComerciales,
    cantidad_por_piezas_comerciales,
)
from obractrl.domain.catalogos.reglas import Concepto, ErrorDeCatalogo

__all__ = ["ComandoPonerMatriz", "GestionarMatricesDeConcepto", "MatrizNueva"]


@dataclass(frozen=True, slots=True)
class MatrizNueva:
    clave: str
    descripcion: str
    unidad_id: UUID


@dataclass(frozen=True, slots=True)
class ComandoPonerMatriz:
    concepto_id: UUID
    cantidad: Decimal | None = None
    """Capturada a mano. Va **una sola** de `cantidad` o `formula`."""
    hijo_id: UUID | None = None
    nueva: MatrizNueva | None = None
    formula: FormulaDePiezasComerciales | None = None
    """Cómo se forma la cantidad (piezas ÷ largo de la pieza comercial × desperdicio); el servidor la calcula."""


class GestionarMatricesDeConcepto:
    def __init__(self, *, conceptos: Any, uow: UnidadDeTrabajo) -> None:
        self._conceptos = conceptos
        self._uow = uow

    async def poner(self, cmd: ComandoPonerMatriz) -> dict[str, Any]:
        if (cmd.hijo_id is None) == (cmd.nueva is None):
            raise ErrorDeCatalogo(
                "Di qué matriz es: una que ya existe o una nueva, no las dos."
            )
        if (cmd.cantidad is None) == (cmd.formula is None):
            raise ErrorDeCatalogo(
                "Di la cantidad a mano o con su fórmula, no las dos ni ninguna."
            )
        if cmd.formula is not None:
            cantidad = cantidad_por_piezas_comerciales(cmd.formula)
            formula_json: dict[str, Any] | None = cmd.formula.como_json()
        else:
            assert cmd.cantidad is not None
            cantidad, formula_json = cmd.cantidad, None
        if cantidad <= 0:
            raise ErrorDeCatalogo("La cantidad de una matriz va por encima de cero.")
        if await self._conceptos.obtener(cmd.concepto_id) is None:
            raise ConceptoNoEncontrado(
                f"Concepto {cmd.concepto_id} no encontrado en tu alcance."
            )

        nueva: Concepto | None = None
        if cmd.nueva is not None:
            nueva = Concepto.crear(
                tipo="matriz",
                clave=cmd.nueva.clave,
                descripcion=cmd.nueva.descripcion,
                unidad_id=str(cmd.nueva.unidad_id),
                familia_id=None,
            )
            if await self._conceptos.obtener_por_clave(str(nueva.clave)) is not None:
                raise ErrorDeCatalogo(
                    f"Ya existe un concepto con la clave {nueva.clave}."
                )
        else:
            assert cmd.hijo_id is not None
            if cmd.hijo_id == cmd.concepto_id:
                raise ErrorDeCatalogo("Un concepto no puede ser matriz de sí mismo.")
            if await self._conceptos.obtener(cmd.hijo_id) is None:
                raise ConceptoNoEncontrado(
                    f"Concepto {cmd.hijo_id} no encontrado en tu alcance."
                )
            if await self._conceptos.alcanza(cmd.hijo_id, cmd.concepto_id):
                raise ErrorDeCatalogo(
                    "Eso cerraría un ciclo: el concepto ya está dentro de esa matriz."
                )

        async with self._uow:
            hijo_id = cmd.hijo_id
            if nueva is not None:
                hijo_id = await self._conceptos.crear(
                    {
                        "tipo": str(nueva.tipo),
                        "clave": str(nueva.clave),
                        "descripcion": nueva.descripcion,
                        "unidad_id": nueva.unidad_id,
                        "familia_id": None,
                    }
                )
            assert hijo_id is not None
            await self._conceptos.poner_matriz(
                cmd.concepto_id, hijo_id, cantidad, formula_json
            )
            await self._uow.commit()
        return {
            "concepto_id": cmd.concepto_id,
            "matriz_id": hijo_id,
            "cantidad": cantidad,
            "formula": formula_json,
        }

    async def quitar(self, concepto_id: UUID, hijo_id: UUID) -> None:
        if await self._conceptos.obtener(concepto_id) is None:
            raise ConceptoNoEncontrado(
                f"Concepto {concepto_id} no encontrado en tu alcance."
            )
        async with self._uow:
            if not await self._conceptos.quitar_matriz(concepto_id, hijo_id):
                raise ConceptoNoEncontrado("Esa matriz no es parte directa del concepto.")
            await self._uow.commit()
