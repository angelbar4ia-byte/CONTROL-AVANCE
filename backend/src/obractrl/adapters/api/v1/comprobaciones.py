"""Comprobación y validación del excedente de ejecución (migración 0066).

La decisión del usuario: si se puede ejecutar más de lo programado, **el
excedente se va a comprobación y validación**. Capturar avance nunca se bloquea
(`PATCH /actividades/{id}/avance`); lo que pase de lo programado aparece aquí, y
Control de obra decide su destino (cerebro WORKFLOWS.md §8.1, CONOCIMIENTO.md
§13.3):

    validar  -> se vuelve control de cambio y sube el techo de la actividad
    pérdida  -> se ejecutó y no se cobra

Lectura abierta a quien ve la obra (RLS); decidir es de Control de obra y del
Super intendente — quienes autorizan un control de cambio (§4).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    ConsultarComprobacionesDep,
    DeclararPerdidaDeExcedenteDep,
    ValidarExcedenteDep,
)
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.application.casos_uso.comprobar_excedente import ComandoDecidirExcedente
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["comprobaciones"])

ROLES_QUE_COMPRUEBAN = (Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE)


class ExcedentePendiente(BaseModel):
    actividad_id: UUID
    obra_id: UUID
    obra_clave: str
    concepto_clave: str | None = None
    descripcion: str | None = None
    unidad: str | None = None
    cant_programada: Decimal
    cant_ejecutada: Decimal
    cant_perdida: Decimal
    cant_excedente: Decimal = Field(
        description="Lo ejecutado por encima de lo programado que aún no se decidió."
    )
    excedente_desde: date | None = None
    dias: int | None = Field(
        default=None, description="Antigüedad del excedente, en días."
    )


class DecisionHistorial(BaseModel):
    id: UUID
    actividad_id: UUID
    decision: str
    cantidad: Decimal
    nota: str
    orden_cambio: str | None = None
    control_cambio_id: UUID | None = None
    decidido_por: UUID
    decidido_por_nombre: str | None = None
    decidido_en: datetime


class DecisionPeticion(BaseModel):
    nota: str = Field(min_length=1, description="Qué se comprobó. Queda como constancia.")
    orden_cambio: str | None = Field(
        default=None,
        description="Obligatoria al validar: la orden de cambio que respalda el excedente.",
    )


class DecisionRespuesta(BaseModel):
    decision_id: UUID
    decision: str
    cantidad: Decimal = Field(description="El excedente que cubrió esta decisión.")
    control_cambio_id: UUID | None = Field(
        default=None, description="El control de cambio que quedó, si se validó."
    )


@router.get(
    "/comprobaciones",
    response_model=list[ExcedentePendiente],
    summary="Lo ejecutado de más que espera comprobación y validación",
)
async def bandeja(caso_uso: ConsultarComprobacionesDep) -> list[ExcedentePendiente]:
    """Las actividades con excedente por decidir, las más viejas primero. Lo ve
    quien ve la obra; lo decide Control de obra."""
    return [ExcedentePendiente(**fila) for fila in await caso_uso.pendientes()]


@router.get(
    "/actividades/{actividad_id}/excedente",
    response_model=list[DecisionHistorial],
    summary="Qué se ha decidido sobre el excedente de una actividad",
)
async def historial(
    actividad_id: UUID, caso_uso: ConsultarComprobacionesDep
) -> list[DecisionHistorial]:
    return [DecisionHistorial(**fila) for fila in await caso_uso.historial(actividad_id)]


_RESPUESTAS = {
    403: {"description": "Solo Control de obra y el Super intendente deciden un excedente."},
    404: {"description": "La actividad no existe o está fuera de tu alcance."},
    409: {"description": "La actividad no tiene excedente pendiente (quizá ya se decidió)."},
    422: {"description": "Falta la nota o, al validar, la orden de cambio."},
}


@router.post(
    "/actividades/{actividad_id}/excedente/validar",
    response_model=DecisionRespuesta,
    summary="Validar el excedente: se vuelve control de cambio",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_COMPRUEBAN))],
    responses=_RESPUESTAS,
)
async def validar(
    actividad_id: UUID,
    peticion: DecisionPeticion,
    ctx: ContextoActual,
    caso_uso: ValidarExcedenteDep,
) -> DecisionRespuesta:
    """Sube el techo de la actividad a lo ejecutado y deja un control de cambio
    ya autorizado con su orden de cambio. Es lo que vuelve cobrable el
    excedente."""
    resultado = await caso_uso.ejecutar(
        ComandoDecidirExcedente(
            actividad_id=actividad_id,
            usuario_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
            nota=peticion.nota,
            orden_cambio=peticion.orden_cambio,
        )
    )
    return DecisionRespuesta(
        decision_id=resultado.decision_id,
        decision=resultado.decision,
        cantidad=resultado.cantidad,
        control_cambio_id=resultado.control_cambio_id,
    )


@router.post(
    "/actividades/{actividad_id}/excedente/perdida",
    response_model=DecisionRespuesta,
    summary="Declarar el excedente como pérdida: se ejecutó y no se cobra",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_COMPRUEBAN))],
    responses=_RESPUESTAS,
)
async def perdida(
    actividad_id: UUID,
    peticion: DecisionPeticion,
    ctx: ContextoActual,
    caso_uso: DeclararPerdidaDeExcedenteDep,
) -> DecisionRespuesta:
    """El excedente deja de ser pendiente y no sube el techo: no se estima."""
    resultado = await caso_uso.ejecutar(
        ComandoDecidirExcedente(
            actividad_id=actividad_id,
            usuario_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
            nota=peticion.nota,
        )
    )
    return DecisionRespuesta(
        decision_id=resultado.decision_id,
        decision=resultado.decision,
        cantidad=resultado.cantidad,
        control_cambio_id=None,
    )
