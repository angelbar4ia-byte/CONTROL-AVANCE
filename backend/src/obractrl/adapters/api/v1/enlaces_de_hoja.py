"""Endpoints de los enlaces entre hojas (migración 0091): una zona del plano que lleva a otra hoja.

Controladores delgados: validan el DTO y delegan en `application.casos_uso.enlaces_de_hoja`.
Navegación pura: nunca produce cantidad.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import GestionarEnlacesDeHojaDep
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.adapters.api.v1.cuantificacion import ROLES_QUE_TRAZAN
from obractrl.application.casos_uso.enlaces_de_hoja import ComandoCrearEnlaceDeHoja

router = APIRouter(tags=["enlaces-de-hoja"])


class EnlaceDeHojaPeticion(BaseModel):
    destino_plano_id: UUID = Field(
        description="La hoja a la que lleva (de la misma obra)."
    )
    etiqueta: str = Field(min_length=1, max_length=120, description="«Ver corte A-A».")
    x: float
    y: float
    ancho: float = Field(gt=0)
    alto: float = Field(gt=0)


class EnlaceDeHojaRespuesta(BaseModel):
    id: UUID
    plano_id: UUID
    destino_plano_id: UUID
    destino_nombre: str
    destino_version: int
    etiqueta: str
    x: float
    y: float
    ancho: float
    alto: float


class EnlaceDeHojaCreado(BaseModel):
    id: UUID


@router.get(
    "/planos/{plano_id}/enlaces",
    response_model=list[EnlaceDeHojaRespuesta],
    summary="Los enlaces a otras hojas que tiene un plano",
    responses={404: {"description": "El plano no existe o está fuera de tu alcance."}},
)
async def listar_enlaces_de_hoja(
    plano_id: UUID, caso_uso: GestionarEnlacesDeHojaDep
) -> list[EnlaceDeHojaRespuesta]:
    return [EnlaceDeHojaRespuesta(**f) for f in await caso_uso.listar(plano_id)]


@router.post(
    "/planos/{plano_id}/enlaces",
    response_model=EnlaceDeHojaCreado,
    status_code=status.HTTP_201_CREATED,
    summary="Marcar una zona del plano que lleva a otra hoja",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={
        404: {"description": "Una de las hojas no existe o está fuera de tu alcance."},
        422: {
            "description": "Sin etiqueta o zona, a la misma hoja o a una hoja de otra obra."
        },
    },
)
async def crear_enlace_de_hoja(
    plano_id: UUID,
    peticion: EnlaceDeHojaPeticion,
    ctx: ContextoActual,
    caso_uso: GestionarEnlacesDeHojaDep,
) -> EnlaceDeHojaCreado:
    enlace_id = await caso_uso.crear(
        ComandoCrearEnlaceDeHoja(
            plano_id=plano_id,
            destino_plano_id=peticion.destino_plano_id,
            etiqueta=peticion.etiqueta,
            x=peticion.x,
            y=peticion.y,
            ancho=peticion.ancho,
            alto=peticion.alto,
            autor_id=ctx.usuario_id,
        )
    )
    return EnlaceDeHojaCreado(id=enlace_id)


@router.delete(
    "/enlaces-de-hoja/{enlace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Quitar un enlace entre hojas",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={404: {"description": "El enlace no existe o está fuera de tu alcance."}},
)
async def eliminar_enlace_de_hoja(
    enlace_id: UUID, caso_uso: GestionarEnlacesDeHojaDep
) -> None:
    await caso_uso.eliminar(enlace_id)
