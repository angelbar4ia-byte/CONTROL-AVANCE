"""Caso de uso: un concepto que nace desde el cuantificador (entrega 5).

Medir pide a veces un concepto que el catálogo todavía no tiene. En vez de mandar a quien mide a
otra pantalla, el concepto se da de alta aquí y entra a la obra en el mismo paso: nace como
**adicional**, **sin cantidad** —llega midiendo, y lo medido es el presupuesto (D-571)— y en la
etapa que se diga, o suelto. Una parte ya asignada no admite renglones nuevos: eso es control de
cambio, no una modificación.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.generar_obra_desde_prototipo import ObraNoEncontrada
from obractrl.application.puertos.partes import RepositorioPartes
from obractrl.application.puertos.repositorios import RepositorioObras, UnidadDeTrabajo
from obractrl.domain.catalogos.reglas import Concepto, ErrorDeCatalogo
from obractrl.domain.partes.estado import ErrorDeParte, EstadoDeParte

__all__ = ["ComandoCrearConceptoEnObra", "CrearConceptoEnObra"]


@dataclass(frozen=True, slots=True)
class ComandoCrearConceptoEnObra:
    obra_id: UUID
    clave: str
    descripcion: str
    unidad_id: UUID
    precio_unitario: Decimal = Decimal(0)
    etapa_id: UUID | None = None
    nivel_id: UUID | None = None
    familia_id: UUID | None = None


class CrearConceptoEnObra:
    """`POST /obras/{id}/conceptos-nuevos` (Control de obra y Costos)."""

    def __init__(
        self,
        *,
        conceptos: Any,
        partes: RepositorioPartes,
        obras: RepositorioObras,
        uow: UnidadDeTrabajo,
    ) -> None:
        self._conceptos = conceptos
        self._partes = partes
        self._obras = obras
        self._uow = uow

    async def ejecutar(self, cmd: ComandoCrearConceptoEnObra) -> dict[str, Any]:
        if await self._obras.obtener(cmd.obra_id) is None:
            raise ObraNoEncontrada(f"Obra {cmd.obra_id} no encontrada en tu alcance.")
        if cmd.precio_unitario < 0:
            raise ErrorDeCatalogo("El precio unitario no puede ser negativo.")
        concepto = Concepto.crear(
            tipo="concepto",
            clave=cmd.clave,
            descripcion=cmd.descripcion,
            unidad_id=str(cmd.unidad_id),
            familia_id=str(cmd.familia_id) if cmd.familia_id else None,
        )
        if await self._conceptos.obtener_por_clave(str(concepto.clave)) is not None:
            raise ErrorDeCatalogo(f"Ya existe un concepto con la clave {concepto.clave}.")

        clave_parte = f"etapa:{cmd.etapa_id}" if cmd.etapa_id else "sin_etapa:-"
        estado = (await self._partes.estados_de_obra(cmd.obra_id)).get(
            clave_parte, EstadoDeParte.CUANTIFICANDO.value
        )
        if estado == EstadoDeParte.ASIGNADA.value:
            raise ErrorDeParte(
                "La parte ya está asignada: agregarle algo es control de cambio, no una modificación."
            )

        async with self._uow:
            concepto_id = await self._conceptos.crear(
                {
                    "tipo": str(concepto.tipo),
                    "clave": str(concepto.clave),
                    "descripcion": concepto.descripcion,
                    "unidad_id": concepto.unidad_id,
                    "familia_id": concepto.familia_id,
                }
            )
            actividad_id = await self._partes.crear_actividad_nueva(
                {
                    "obra_id": cmd.obra_id,
                    "descripcion": concepto.descripcion,
                    "cantidad": Decimal(0),
                    "precio_unitario": cmd.precio_unitario,
                    "concepto_id": concepto_id,
                    "etapa_id": cmd.etapa_id,
                    "nivel_id": cmd.nivel_id,
                    "tipo": "adicional",
                }
            )
            await self._uow.commit()
        return {
            "concepto_id": concepto_id,
            "actividad_id": actividad_id,
            "clave": str(concepto.clave),
            "parte": clave_parte,
        }
