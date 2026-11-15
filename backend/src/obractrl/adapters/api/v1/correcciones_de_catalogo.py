"""Endpoints de las correcciones propuestas al catálogo, como nueva versión del concepto (Ola 3B; migración 0132).

**Una corrección al catálogo no lo edita**: Costos propone la versión nueva del concepto (por ejemplo la unidad de EST-02330, de m2 a m),
Control de obra la autoriza o la rechaza y nace el número de versión. Si la propone Control de obra queda autorizada al momento. Solo se
proponen las correcciones conocidas (las que el catálogo respalda). Controladores delgados.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import GestionarCorreccionesDeCatalogoDep
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["biblioteca de elementos"])

ROLES_QUE_PROPONEN = (Rol.CONTROL_OBRA, Rol.COSTOS)
ROLES_QUE_AUTORIZAN = (Rol.CONTROL_OBRA,)

_RESPUESTAS = {
    403: {"description": "Costos propone y Control de obra autoriza."},
    404: {"description": "No existe o está fuera de tu alcance."},
    422: {"description": "No es una corrección conocida, ya está propuesta o ya fue decidida."},
}

EstadoDeLaCorreccion = Literal["pendiente", "autorizada", "rechazada"]


class RevisionDeLaCorreccion(BaseModel):
    id: UUID
    estado: EstadoDeLaCorreccion
    version: int | None = Field(description="El número de la versión del concepto; `null` mientras está pendiente o si se rechazó.")
    valor_propuesto: str
    propuso_nombre: str | None
    propuso_rol: str | None
    propuesto_en: datetime
    decidio_nombre: str | None
    decidio_rol: str | None
    decidido_en: datetime | None
    motivo_rechazo: str | None


class CorreccionDelCatalogo(BaseModel):
    concepto_clave: str
    campo: Literal["unidad"]
    concepto: str = Field(description="Descripción del concepto, tal como la trae el catálogo.")
    valor_catalogo: str = Field(description="Lo que trae el catálogo vigente. No se edita.")
    valor_propuesto: str = Field(description="Lo que diría la versión nueva del concepto.")
    valor_vigente: str = Field(description="El valor con que cuenta hoy: el del catálogo, o el de la última versión autorizada.")
    motivo: str
    fuente: str = Field(description="Archivo y línea del catálogo que respaldan la corrección.")
    preguntas: list[str]
    nota: str
    estado: Literal["sin_proponer", "pendiente", "autorizada"]
    version_vigente: int | None
    pendiente_id: UUID | None
    historial: list[RevisionDeLaCorreccion]


class ProponerCorreccionPeticion(BaseModel):
    concepto_clave: str = Field(min_length=1, max_length=40)
    campo: Literal["unidad"] = "unidad"


class CorreccionPropuesta(BaseModel):
    id: UUID
    estado: Literal["pendiente", "autorizada"]
    version: int | None


class VersionDeLaCorreccion(BaseModel):
    version: int


class RechazoDeCorreccionPeticion(BaseModel):
    motivo: str | None = Field(default=None, max_length=300)


@router.get(
    "/correcciones-de-catalogo",
    response_model=list[CorreccionDelCatalogo],
    summary="Las correcciones conocidas al catálogo, con su estado y su historial de versiones",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_PROPONEN))],
    responses={403: {"description": "Lo ven Control de obra y Costos."}},
)
async def correcciones_de_catalogo(caso_uso: GestionarCorreccionesDeCatalogoDep) -> list[CorreccionDelCatalogo]:
    return [CorreccionDelCatalogo(**c) for c in await caso_uso.listar()]


@router.post(
    "/correcciones-de-catalogo",
    response_model=CorreccionPropuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Proponer la corrección como versión nueva del concepto (Costos: pendiente; Control de obra: autorizada)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_PROPONEN))],
    responses=_RESPUESTAS,
)
async def proponer_correccion(
    peticion: ProponerCorreccionPeticion, ctx: ContextoActual, caso_uso: GestionarCorreccionesDeCatalogoDep
) -> CorreccionPropuesta:
    return CorreccionPropuesta(
        **await caso_uso.proponer(peticion.concepto_clave, peticion.campo, usuario_id=ctx.usuario_id, rol=ctx.rol)
    )


@router.post(
    "/correcciones-de-catalogo/{correccion_id}/autorizar",
    response_model=VersionDeLaCorreccion,
    summary="Autorizar la corrección: nace la versión siguiente del concepto (el catálogo no se edita)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_AUTORIZAN))],
    responses=_RESPUESTAS,
)
async def autorizar_correccion(correccion_id: UUID, ctx: ContextoActual, caso_uso: GestionarCorreccionesDeCatalogoDep) -> VersionDeLaCorreccion:
    return VersionDeLaCorreccion(version=await caso_uso.autorizar(correccion_id, usuario_id=ctx.usuario_id, rol=ctx.rol))


@router.post(
    "/correcciones-de-catalogo/{correccion_id}/rechazar",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Rechazar la corrección: no se aplica y queda en el historial",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_AUTORIZAN))],
    responses=_RESPUESTAS,
)
async def rechazar_correccion(
    correccion_id: UUID, peticion: RechazoDeCorreccionPeticion, ctx: ContextoActual, caso_uso: GestionarCorreccionesDeCatalogoDep
) -> None:
    await caso_uso.rechazar(correccion_id, usuario_id=ctx.usuario_id, rol=ctx.rol, motivo=peticion.motivo)
