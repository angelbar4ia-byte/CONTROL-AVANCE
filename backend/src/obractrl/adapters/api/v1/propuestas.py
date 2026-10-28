"""Endpoints de las propuestas por revisar (Fase 2 y 3, migración 0092).

Una herramienta automática (conteo por plantilla, takeoff) **propone** trazos; una propuesta no
tiene enlaces y **nunca suma cantidad** hasta que una persona la acepta. Controladores delgados:
validan el DTO y delegan en `application.casos_uso.propuestas`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    AceptarPropuestasDep,
    ProponerTrazosDep,
    RechazarPropuestasDep,
)
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.adapters.api.v1.cuantificacion import (
    ROLES_QUE_TRAZAN,
    ResultadoRecalculoRespuesta,
)
from obractrl.application.casos_uso.propuestas import ComandoProponerTrazos
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["propuestas"])


class PropuestaPeticion(BaseModel):
    wkt: str = Field(
        min_length=1, description="La geometría propuesta, en WKT (coordenadas de plano)."
    )
    confianza: Decimal | None = Field(
        default=None, ge=0, le=1, description="Qué tan segura estaba la herramienta."
    )


class ProponerTrazosPeticion(BaseModel):
    actividad_id: UUID = Field(
        description="El concepto para el que se propone (de la obra del plano)."
    )
    medida: Literal["area", "perimetro", "longitud", "conteo"]
    origen: Literal["conteo_auto", "takeoff"]
    propuestas: list[PropuestaPeticion] = Field(min_length=1, max_length=2000)


class ProponerTrazosRespuesta(BaseModel):
    trazo_ids: list[UUID]


class IdsDeTrazoPeticion(BaseModel):
    trazo_ids: list[UUID] = Field(min_length=1, max_length=2000)


class PropuestasAceptadasRespuesta(BaseModel):
    trazo_ids: list[UUID]
    recalculos: list[ResultadoRecalculoRespuesta]


class PropuestasRechazadasRespuesta(BaseModel):
    rechazadas: int


@router.post(
    "/planos/{plano_id}/propuestas",
    response_model=ProponerTrazosRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Proponer trazos encontrados por una herramienta automática (no suman hasta aceptarse)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={
        404: {"description": "El plano no existe o está fuera de tu alcance."},
        422: {
            "description": "Geometría inválida, medida que no va con ella o actividad de otra obra."
        },
    },
)
async def proponer_trazos(
    plano_id: UUID,
    peticion: ProponerTrazosPeticion,
    ctx: ContextoActual,
    caso_uso: ProponerTrazosDep,
) -> ProponerTrazosRespuesta:
    """Cada propuesta queda como trazo **sin enlaces**: no cuenta como medida hasta que se acepta."""
    ids = await caso_uso.ejecutar(
        ComandoProponerTrazos(
            plano_id=plano_id,
            actividad_id=peticion.actividad_id,
            medida=peticion.medida,
            origen=peticion.origen,
            geometrias_wkt=tuple(p.wkt for p in peticion.propuestas),
            confianzas=tuple(p.confianza for p in peticion.propuestas)
            if all(p.confianza is not None for p in peticion.propuestas)
            else (),
            autor_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
        )
    )
    return ProponerTrazosRespuesta(trazo_ids=ids)


@router.post(
    "/planos/{plano_id}/propuestas/aceptar",
    response_model=PropuestasAceptadasRespuesta,
    summary="Aceptar propuestas: cada una pasa a medir su concepto",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={
        422: {"description": "Ninguno de esos trazos es una propuesta pendiente."}
    },
)
async def aceptar_propuestas(
    plano_id: UUID,
    peticion: IdsDeTrazoPeticion,
    ctx: ContextoActual,
    caso_uso: AceptarPropuestasDep,
) -> PropuestasAceptadasRespuesta:
    resultado = await caso_uso.ejecutar(
        plano_id,
        peticion.trazo_ids,
        usuario_id=ctx.usuario_id,
        detectada_en=datetime.now(UTC),
    )
    return PropuestasAceptadasRespuesta(
        trazo_ids=list(resultado.trazo_ids),
        recalculos=[
            ResultadoRecalculoRespuesta.desde_dominio(r) for r in resultado.recalculos
        ],
    )


@router.post(
    "/planos/{plano_id}/propuestas/rechazar",
    response_model=PropuestasRechazadasRespuesta,
    summary="Rechazar propuestas: se borran, sin haber sumado nada",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={
        422: {"description": "Ninguno de esos trazos es una propuesta pendiente."}
    },
)
async def rechazar_propuestas(
    plano_id: UUID, peticion: IdsDeTrazoPeticion, caso_uso: RechazarPropuestasDep
) -> PropuestasRechazadasRespuesta:
    return PropuestasRechazadasRespuesta(
        rechazadas=await caso_uso.ejecutar(plano_id, peticion.trazo_ids)
    )
