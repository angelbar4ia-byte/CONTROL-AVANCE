"""Confirmar el avance antes de estimar (migración 0070; cerebro D-533/D-534/D-535).

El residente **registra** el avance siempre, sin bloqueo (`PATCH
/actividades/{id}/avance`); aquí **confirma** que esa cifra es la real, al terminar
la actividad y antes de estimar. Confirmar no es un candado: lo que se estima por
encima de lo confirmado es una **alerta** que se lee en la estimación
(`GET /estimaciones/{id}`), y su salida es bajar las cantidades.

Confirma el residente (D-534); lo que falta por confirmar lo ve quien ve la obra.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    ConfirmarAvanceDep,
    ConsultarConfirmacionesDep,
)
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.adapters.api.idempotencia import Idempotencia
from obractrl.application.casos_uso.confirmar_avance import ComandoConfirmarAvance
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["avance"])


class ConfirmarPeticion(BaseModel):
    momento: Literal["al_terminar", "antes_de_estimar"] = Field(
        default="antes_de_estimar",
        description="Los dos momentos del cerebro (D-533): al terminar la actividad y antes de estimar.",
    )
    nota: str | None = None


class ConfirmacionRespuesta(BaseModel):
    id: UUID
    cantidad: Decimal = Field(description="Lo que se afirmó: el avance ejecutado en este momento.")
    momento: str


class ConfirmacionDeActividad(BaseModel):
    actividad_id: UUID
    concepto_clave: str | None = None
    descripcion: str | None = None
    unidad: str | None = None
    cant_ejecutada: Decimal
    cant_confirmada: Decimal | None = Field(
        default=None, description="La última confirmación; `null` = nunca."
    )
    confirmado_en: datetime | None = None
    confirmado_por_nombre: str | None = None
    momento: str | None = None
    estado: str = Field(
        description=(
            "`sin_confirmar` · `desactualizada` (el avance cambió después de confirmar) · "
            "`confirmada`."
        )
    )


@router.post(
    "/actividades/{actividad_id}/avance/confirmar",
    response_model=ConfirmacionRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Confirmar el avance de una actividad (el residente afirma que es el real)",
    dependencies=[Depends(exigir_rol(Rol.RESIDENTE)), Idempotencia],
    responses={
        403: {"description": "Confirma el residente (D-534)."},
        404: {"description": "La actividad no existe o está fuera de tu alcance."},
        409: {"description": "La semana activa ya la cerró una estimación validada (D-540)."},
        422: {"description": "La actividad no tiene avance capturado que confirmar."},
    },
)
async def confirmar_avance(
    actividad_id: UUID,
    peticion: ConfirmarPeticion,
    ctx: ContextoActual,
    caso_uso: ConfirmarAvanceDep,
) -> ConfirmacionRespuesta:
    """Guarda el avance ejecutado **en este momento** como lo confirmado. No
    bloquea nada; si luego se captura más avance, queda detrás y hay que confirmar
    de nuevo."""
    registrada = await caso_uso.ejecutar(
        ComandoConfirmarAvance(
            actividad_id=actividad_id,
            usuario_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
            momento=peticion.momento,
            nota=peticion.nota,
        )
    )
    return ConfirmacionRespuesta(
        id=registrada.id, cantidad=registrada.cantidad, momento=registrada.momento
    )


@router.get(
    "/obras/{obra_id}/avance/confirmaciones",
    response_model=list[ConfirmacionDeActividad],
    summary="Qué avances están confirmados, desactualizados o sin confirmar",
    responses={404: {"description": "La obra no existe o está fuera de tu alcance."}},
)
async def confirmaciones_de_obra(
    obra_id: UUID, caso_uso: ConsultarConfirmacionesDep
) -> list[ConfirmacionDeActividad]:
    """Todas las actividades de la obra con su estado de confirmación. Lo ve quien
    ve la obra (RLS)."""
    return [ConfirmacionDeActividad(**fila) for fila in await caso_uso.ejecutar(obra_id)]
