"""Endpoints para armar el árbol desde el cuantificador (entrega 7, migración 0093).

Niveles y etapas del catálogo, partidas de una obra y la unidad de un concepto. Controladores delgados: validan el DTO
y delegan en `application.casos_uso.arbol`. Roles: Control de obra y Costos.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import ArmarArbolDep
from obractrl.adapters.api.dependencias import exigir_rol
from obractrl.application.casos_uso.arbol import ComandoAgregarPartida
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(
    tags=["arbol"], dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.COSTOS))]
)


class NivelPeticion(BaseModel):
    clave: str = Field(min_length=1, max_length=60)
    descripcion: str = Field(min_length=1)


class EtapaPeticion(NivelPeticion):
    nivel_id: UUID


class IdCreado(BaseModel):
    id: UUID


class UnidadPeticion(BaseModel):
    unidad_id: UUID


class UnidadCambiadaRespuesta(BaseModel):
    concepto_id: UUID
    unidad_anterior: str | None = None
    unidad_nueva: str
    tipo_anterior: str | None = Field(
        default=None, description="area, lineal, conteo, volumen o derivada."
    )
    tipo_nuevo: str | None = None


class PartidaPeticion(BaseModel):
    concepto_id: UUID
    etapa_id: UUID | None = Field(
        default=None, description="La etapa donde va; suelta si falta."
    )


class PartidaRespuesta(BaseModel):
    actividad_id: UUID
    concepto_id: UUID
    clave: str
    parte: str


class UbicacionPeticion(BaseModel):
    etapa_id: UUID | None = Field(
        default=None, description="La etapa a la que pasa; `null` la deja suelta."
    )


class UbicacionRespuesta(BaseModel):
    actividad_id: UUID
    etapa_id: UUID | None = None
    nivel_id: UUID | None = None


@router.post(
    "/niveles",
    response_model=IdCreado,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un nivel del árbol",
    responses={422: {"description": "Clave repetida o sin descripción."}},
)
async def crear_nivel(peticion: NivelPeticion, caso_uso: ArmarArbolDep) -> IdCreado:
    return IdCreado(
        id=await caso_uso.crear_nivel(
            clave=peticion.clave, descripcion=peticion.descripcion
        )
    )


@router.post(
    "/etapas",
    response_model=IdCreado,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una etapa dentro de un nivel",
    responses={
        422: {"description": "Clave repetida, sin descripción o nivel inexistente."}
    },
)
async def crear_etapa(peticion: EtapaPeticion, caso_uso: ArmarArbolDep) -> IdCreado:
    return IdCreado(
        id=await caso_uso.crear_etapa(
            nivel_id=peticion.nivel_id,
            clave=peticion.clave,
            descripcion=peticion.descripcion,
        )
    )


@router.put(
    "/conceptos/{concepto_id}/unidad",
    response_model=UnidadCambiadaRespuesta,
    summary="Cambiar la unidad de un concepto (cambia cómo se mide)",
    responses={
        404: {"description": "El concepto no existe o está fuera de tu alcance."},
        422: {
            "description": "El concepto ya mide con algo que la unidad nueva no admite, o la unidad no existe."
        },
    },
)
async def cambiar_unidad_del_concepto(
    concepto_id: UUID, peticion: UnidadPeticion, caso_uso: ArmarArbolDep
) -> UnidadCambiadaRespuesta:
    """Es un cambio **del catálogo**: vale para todas las obras que usen el concepto."""
    r = await caso_uso.cambiar_unidad(concepto_id, peticion.unidad_id)
    return UnidadCambiadaRespuesta(
        concepto_id=r.concepto_id,
        unidad_anterior=r.unidad_anterior,
        unidad_nueva=r.unidad_nueva,
        tipo_anterior=r.tipo_anterior,
        tipo_nuevo=r.tipo_nuevo,
    )


@router.post(
    "/obras/{obra_id}/partidas",
    response_model=PartidaRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar a la obra una partida con un concepto que ya existe (sin cantidad)",
    responses={
        404: {
            "description": "La obra o el concepto no existen o están fuera de tu alcance."
        },
        409: {"description": "La parte ya está asignada: es control de cambio."},
        422: {"description": "Ya es una partida de esa etapa, o la etapa no existe."},
    },
)
async def agregar_partida(
    obra_id: UUID, peticion: PartidaPeticion, caso_uso: ArmarArbolDep
) -> PartidaRespuesta:
    return PartidaRespuesta(
        **await caso_uso.agregar_partida(
            ComandoAgregarPartida(
                obra_id=obra_id,
                concepto_id=peticion.concepto_id,
                etapa_id=peticion.etapa_id,
            )
        )
    )


@router.put(
    "/actividades/{actividad_id}/ubicacion",
    response_model=UbicacionRespuesta,
    summary="Mover una partida a otra etapa",
    responses={
        404: {"description": "La partida no existe o está fuera de tu alcance."},
        409: {
            "description": "Ya tiene avance, o una de las dos partes ya está asignada."
        },
        422: {"description": "La etapa no existe."},
    },
)
async def mover_partida(
    actividad_id: UUID, peticion: UbicacionPeticion, caso_uso: ArmarArbolDep
) -> UbicacionRespuesta:
    return UbicacionRespuesta(
        **await caso_uso.mover_partida(actividad_id, peticion.etapa_id)
    )
