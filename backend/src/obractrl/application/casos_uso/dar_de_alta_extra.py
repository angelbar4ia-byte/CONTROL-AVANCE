"""Caso de uso: alta extra-catálogo (§11.2 `POST /actividades`, rol R).

Spec §5.1 (el Residente trae «Extra-catálogo» en su sidebar) · §11.2 · §12.11.

Es de los casos de uso más cortos del sistema, y está bien que lo sea: el
dominio (`domain.obras.extra_catalogo`) decide todo lo que hay que decidir, y
aquí solo se ordena la secuencia y se persiste. Existe de todas formas porque
el router no debe conocer al repositorio (§12.11) y porque el día que un extra
tenga que notificar a Control de obra, el lugar donde eso se agrega es este.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from obractrl.application.puertos.repositorios import (
    RepositorioActividades,
    UnidadDeTrabajo,
)
from obractrl.domain.obras.extra_catalogo import ActividadExtra, ErrorDeExtraCatalogo
from obractrl.domain.shared.diccionario import ModoPago, Rol

__all__ = [
    "ComandoDarDeAltaExtra",
    "DarDeAltaExtra",
    "ErrorDeExtraCatalogo",
    "ExtraDadaDeAlta",
]


@dataclass(frozen=True, slots=True)
class ComandoDarDeAltaExtra:
    obra_id: UUID
    descripcion: str
    orden_cambio: str
    cant_base: Decimal
    rol: Rol
    """Rol de quien da el alta. Es parte de la regla (§11.2), no del contexto:
    solo el residente puede afirmar que ese trabajo existe en la obra."""
    modo_pago: ModoPago = ModoPago.DESTAJO
    precio_unitario: Decimal = Decimal(0)
    precio_destajo: Decimal = Decimal(0)
    concepto_id: UUID | None = None
    frente_id: UUID | None = None
    nivel_id: UUID | None = None
    """El **frente** donde cae el trabajo (§7.4): sin él la actividad no aparece
    en ningún grupo de la pantalla del residente."""
    etapa_id: UUID | None = None
    """El **sub-frente**: la etapa dentro del nivel."""
    duracion_dias: Decimal = Decimal(1)


@dataclass(frozen=True, slots=True)
class ExtraDadaDeAlta:
    id: UUID
    actividad: ActividadExtra


class DarDeAltaExtra:
    """`POST /actividades` (Residente, §11.2)."""

    def __init__(
        self, *, actividades: RepositorioActividades, uow: UnidadDeTrabajo
    ) -> None:
        self._actividades = actividades
        self._uow = uow

    async def ejecutar(self, cmd: ComandoDarDeAltaExtra) -> ExtraDadaDeAlta:
        actividad = ActividadExtra.crear(
            obra_id=str(cmd.obra_id),
            descripcion=cmd.descripcion,
            orden_cambio=cmd.orden_cambio,
            cant_base=cmd.cant_base,
            rol=cmd.rol,
            modo_pago=cmd.modo_pago,
            precio_unitario=cmd.precio_unitario,
            precio_destajo=cmd.precio_destajo,
            concepto_id=str(cmd.concepto_id) if cmd.concepto_id else None,
            frente_id=str(cmd.frente_id) if cmd.frente_id else None,
            nivel_id=str(cmd.nivel_id) if cmd.nivel_id else None,
            etapa_id=str(cmd.etapa_id) if cmd.etapa_id else None,
            duracion_dias=cmd.duracion_dias,
        )

        async with self._uow:
            actividad_id = await self._actividades.crear_extra(
                {
                    "obra_id": actividad.obra_id,
                    "descripcion": actividad.descripcion,
                    "orden_cambio": actividad.orden_cambio,
                    "cant_base": actividad.cant_base,
                    "modo_pago": actividad.modo_pago.value,
                    "precio_unitario": actividad.precio_unitario,
                    "precio_destajo": actividad.precio_destajo,
                    "concepto_id": actividad.concepto_id,
                    "frente_id": actividad.frente_id,
                    "nivel_id": actividad.nivel_id,
                    "etapa_id": actividad.etapa_id,
                    "duracion_dias": actividad.duracion_dias,
                    "estatus": actividad.estatus.value,
                }
            )
            await self._uow.commit()

        return ExtraDadaDeAlta(id=actividad_id, actividad=actividad)
