"""Endpoints de Materiales: consumo vs presupuesto y salidas de almacén.

Spec §11.2 (Materiales) · §7.7 · §10.5.

Controladores delgados: validan el DTO, delegan y mapean el resultado. La
lectura de consumo y la bandeja de salidas son directas del repo —sin caso de
uso, como `GET /cierres` (`adapters/api/v1/cierres.py`)— porque no hay
orquestación de dominio que hacer, solo RLS acotando el alcance (§12.4). El
registro de una salida sí pasa por el caso de uso: ahí vive la regla de
signo (§10.5, `domain.materiales.reglas`).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import RegistrarSalidaAlmacenDep
from obractrl.adapters.api.dependencias import ContextoActual, SesionRLS, exigir_rol
from obractrl.adapters.api.idempotencia import Idempotencia
from obractrl.adapters.repos.materiales_sql import RepositorioMaterialesSQL
from obractrl.application.casos_uso.registrar_salida_almacen import (
    ComandoRegistrarSalida,
    SalidaRegistrada,
)
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["materiales"])


class ConsumoRespuesta(BaseModel):
    """Fila de `v_consumo_vs_presupuesto`: consumo real vs teórico (§7.7, §10.5)."""

    obra_id: UUID
    insumo_id: UUID
    cant_teorica: Decimal
    cant_real: Decimal
    desviacion_cant: Decimal
    desviacion_pct: Decimal | None
    costo_valuacion: Decimal | None

    @classmethod
    def desde_fila(cls, fila: dict) -> ConsumoRespuesta:
        return cls(
            obra_id=fila["obra_id"],
            insumo_id=fila["insumo_id"],
            cant_teorica=fila["cant_teorica"],
            cant_real=fila["cant_real"],
            desviacion_cant=fila["desviacion_cant"],
            desviacion_pct=fila["desviacion_pct"],
            costo_valuacion=fila["costo_valuacion"],
        )


class RegistrarSalidaPeticion(BaseModel):
    """Movimiento de almacén a registrar (§7.7, §10.5)."""

    insumo_id: UUID
    motivo_id: UUID
    cantidad: Decimal = Field(description="Cantidad con signo (§10.5); no puede ser cero.")
    costo: Decimal = Field(description="Importe con signo, sin IVA (§10.5, §10.6).")
    fecha: date
    concepto_id: UUID | None = Field(default=None, description="Liga al concepto (§10.6).")
    contratista_id: UUID | None = None


class SalidaRespuesta(BaseModel):
    id: UUID
    obra_id: UUID
    insumo_id: UUID
    motivo_id: UUID
    concepto_id: UUID | None
    contratista_id: UUID | None
    cantidad: Decimal
    costo: Decimal
    fecha: date

    @classmethod
    def desde_comando(
        cls, resultado: SalidaRegistrada, cmd: ComandoRegistrarSalida
    ) -> SalidaRespuesta:
        return cls(
            id=resultado.id,
            obra_id=cmd.obra_id,
            insumo_id=cmd.insumo_id,
            motivo_id=cmd.motivo_id,
            concepto_id=cmd.concepto_id,
            contratista_id=cmd.contratista_id,
            cantidad=resultado.cantidad,
            costo=resultado.costo,
            fecha=cmd.fecha,
        )

    @classmethod
    def desde_fila(cls, fila: dict) -> SalidaRespuesta:
        return cls(
            id=fila["id"],
            obra_id=fila["obra_id"],
            insumo_id=fila["insumo_id"],
            motivo_id=fila["motivo_id"],
            concepto_id=fila["concepto_id"],
            contratista_id=fila["contratista_id"],
            cantidad=fila["cantidad"],
            costo=fila["costo"],
            fecha=fila["fecha"],
        )


@router.get(
    "/obras/{obra_id}/materiales/consumo",
    response_model=list[ConsumoRespuesta],
    summary="Consumo de materiales vs presupuesto",
    dependencies=[
        Depends(exigir_rol(Rol.RESIDENTE, Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE))
    ],
)
async def consumo_vs_presupuesto(obra_id: UUID, sesion: SesionRLS) -> list[ConsumoRespuesta]:
    """Cruce consumo real vs teórico por insumo, ya resuelto en BD (§7.7, §10.5).

    Lectura directa sobre `v_consumo_vs_presupuesto`: no hay regla de dominio
    que aplicar, el cruce ya viene calculado por la vista.
    """
    repo = RepositorioMaterialesSQL(sesion)
    filas = await repo.consumo_vs_presupuesto(obra_id)
    return [ConsumoRespuesta.desde_fila(fila) for fila in filas]


@router.post(
    "/obras/{obra_id}/salidas",
    response_model=SalidaRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar una salida de almacén",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA)), Idempotencia],
    responses={
        404: {"description": "El motivo de almacén no existe o está fuera de tu alcance."},
        409: {"description": "El signo de la cantidad no coincide con el del motivo (§10.5)."},
    },
)
async def registrar_salida(
    obra_id: UUID,
    peticion: RegistrarSalidaPeticion,
    ctx: ContextoActual,
    caso_uso: RegistrarSalidaAlmacenDep,
) -> SalidaRespuesta:
    """Control de obra registra un movimiento de almacén (§11.2 "Materiales")."""
    cmd = ComandoRegistrarSalida(
        obra_id=obra_id,
        insumo_id=peticion.insumo_id,
        motivo_id=peticion.motivo_id,
        cantidad=peticion.cantidad,
        costo=peticion.costo,
        fecha=peticion.fecha,
        usuario_id=ctx.usuario_id,
        concepto_id=peticion.concepto_id,
        contratista_id=peticion.contratista_id,
    )
    resultado = await caso_uso.ejecutar(cmd)
    return SalidaRespuesta.desde_comando(resultado, cmd)


@router.get(
    "/salidas",
    response_model=list[SalidaRespuesta],
    summary="Bandeja de salidas de almacén",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE))],
)
async def listar_salidas(
    sesion: SesionRLS,
    obra_id: Annotated[UUID | None, Query(description="Filtra por obra.")] = None,
) -> list[SalidaRespuesta]:
    """Bandeja de movimientos de almacén; RLS ya acota el alcance (§11.2)."""
    repo = RepositorioMaterialesSQL(sesion)
    filas = await repo.listar_salidas(obra_id=obra_id)
    return [SalidaRespuesta.desde_fila(fila) for fila in filas]
