"""Caso de uso: registrar una salida de almacén (§7.7, §10.5, §11.2 "Materiales").

Spec §10.5 (motivos con signo) · §7.7 (`SalidaAlmacen`) · §12.11 (capa de
aplicación).

Es el módulo más simple del backend: no hay máquina de estados como en
Cierres o Estimación, solo una secuencia lineal —leer el motivo, validar el
signo con la regla de dominio, insertar— entre el repo y
`domain.materiales.reglas`. La lectura de `consumo vs presupuesto` no tiene
caso de uso: es lectura directa del repo sobre `v_consumo_vs_presupuesto`,
como `GET /me` (`adapters/api/v1/identidad.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from obractrl.application.puertos.repositorios import (
    RepositorioMateriales,
    UnidadDeTrabajo,
)
from obractrl.domain.materiales.reglas import validar_signo_salida

__all__ = [
    "ComandoRegistrarSalida",
    "MotivoAlmacenNoEncontrado",
    "RegistrarSalidaAlmacen",
    "SalidaRegistrada",
]


class MotivoAlmacenNoEncontrado(LookupError):
    """El motivo no existe o está fuera del alcance del usuario (RLS)."""


@dataclass(frozen=True, slots=True)
class ComandoRegistrarSalida:
    obra_id: UUID
    insumo_id: UUID
    motivo_id: UUID
    cantidad: Decimal
    costo: Decimal
    fecha: date
    usuario_id: UUID
    concepto_id: UUID | None = None
    contratista_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class SalidaRegistrada:
    id: UUID
    cantidad: Decimal
    costo: Decimal


class RegistrarSalidaAlmacen:
    """Control de obra registra un movimiento de almacén (§11.2 "Materiales")."""

    def __init__(self, *, materiales: RepositorioMateriales, uow: UnidadDeTrabajo) -> None:
        self._materiales = materiales
        self._uow = uow

    async def ejecutar(self, cmd: ComandoRegistrarSalida) -> SalidaRegistrada:
        motivo = await self._materiales.obtener_motivo(cmd.motivo_id)
        if motivo is None:
            raise MotivoAlmacenNoEncontrado(
                f"Motivo {cmd.motivo_id} no encontrado en tu alcance."
            )

        # La cantidad ya trae signo (§10.5); el motivo solo clasifica el
        # bucket, pero su signo debe ser consistente con lo capturado.
        validar_signo_salida(cmd.cantidad, int(motivo["signo"]))

        async with self._uow:
            salida_id = await self._materiales.crear_salida(
                {
                    "obra_id": cmd.obra_id,
                    "insumo_id": cmd.insumo_id,
                    "motivo_id": cmd.motivo_id,
                    "concepto_id": cmd.concepto_id,
                    "contratista_id": cmd.contratista_id,
                    "usuario_id": cmd.usuario_id,
                    "fecha": cmd.fecha,
                    "cantidad": cmd.cantidad,
                    "costo": cmd.costo,
                }
            )
            await self._uow.commit()

        return SalidaRegistrada(id=salida_id, cantidad=cmd.cantidad, costo=cmd.costo)
