"""Endpoints del cambio de unidad de un concepto a otro tipo de medición (D-623; migración 0106).

Se propone con una equivalencia (la del destajo o la que se teclee) y Control de obra o Costos lo aprueba; al aprobar
nace una versión del concepto con las cantidades de su matriz convertidas. Controladores delgados.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import CambioDeUnidadDep
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["cambio de unidad"])

ROLES_QUE_CAMBIAN_UNIDAD = (Rol.CONTROL_OBRA, Rol.COSTOS)
"""La unidad es del catálogo y cambia cantidades de presupuesto: la proponen y la aprueban Control de obra y Costos."""


class CambioDeUnidadPeticion(BaseModel):
    unidad_id: UUID
    equivalencia: Decimal | None = Field(
        default=None, gt=0, description="Unidades nuevas por una antigua (48 m² por pieza). Sin ella se busca en el destajo."
    )


class EquivalenciaPeticion(BaseModel):
    equivalencia: Decimal = Field(gt=0)


class CambioDeUnidadRespuesta(BaseModel):
    id: UUID
    concepto_id: UUID
    concepto_nuevo_id: UUID | None
    unidad_anterior_id: UUID | None
    unidad_nueva_id: UUID
    tipo_anterior: str | None
    tipo_nuevo: str
    equivalencia: Decimal | None
    origen_equivalencia: str | None = Field(description="destajo, tecleada o medida.")
    estado: str
    partidas: int = Field(description="Cuántas partidas usan el concepto.")
    partidas_bloqueadas: int = Field(description="Cuántas están asignadas o con avance y no se tocan.")


class ResultadoDelCambioRespuesta(BaseModel):
    concepto_nuevo_id: UUID
    clave_nueva: str
    partidas_movidas: int
    partidas_bloqueadas: int
    enlaces_rehechos: int
    enlaces_sin_medida: int


class MarcaDeCambioRespuesta(BaseModel):
    enlace_viejo_id: UUID
    enlace_nuevo_id: UUID | None
    medida_vieja: str
    medida_nueva: str | None
    nota: str | None
    unidad_anterior: str | None
    unidad_nueva: str
    tipo_anterior: str | None
    tipo_nuevo: str
    equivalencia: Decimal | None


def _respuesta(c: dict[str, Any]) -> CambioDeUnidadRespuesta:
    return CambioDeUnidadRespuesta(**{k: c[k] for k in CambioDeUnidadRespuesta.model_fields})


_ROL = [Depends(exigir_rol(*ROLES_QUE_CAMBIAN_UNIDAD))]
_RESPUESTAS = {
    403: {"description": "Lo proponen y aprueban Control de obra y Costos."},
    404: {"description": "El concepto o el cambio no existen o están fuera de tu alcance."},
    422: {"description": "El cambio no cruza de tipo, ya hay uno por resolver o falta la equivalencia."},
}


@router.post(
    "/conceptos/{concepto_id}/cambio-de-unidad",
    response_model=CambioDeUnidadRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Proponer cambiar la unidad de un concepto a otro tipo de medición",
    dependencies=_ROL,
    responses=_RESPUESTAS,
)
async def proponer_cambio(
    concepto_id: UUID, peticion: CambioDeUnidadPeticion, ctx: ContextoActual, caso_uso: CambioDeUnidadDep
) -> CambioDeUnidadRespuesta:
    return _respuesta(await caso_uso.proponer(concepto_id, peticion.unidad_id, peticion.equivalencia, ctx.usuario_id))


@router.get("/cambios-de-unidad/{cambio_id}", response_model=CambioDeUnidadRespuesta, summary="Ver un cambio de unidad", responses=_RESPUESTAS)
async def ver_cambio(cambio_id: UUID, caso_uso: CambioDeUnidadDep) -> CambioDeUnidadRespuesta:
    return _respuesta(await caso_uso.ver(cambio_id))


@router.put(
    "/cambios-de-unidad/{cambio_id}/equivalencia",
    response_model=CambioDeUnidadRespuesta,
    summary="Teclear la equivalencia de un cambio por resolver",
    dependencies=_ROL,
    responses=_RESPUESTAS,
)
async def teclear_equivalencia(cambio_id: UUID, peticion: EquivalenciaPeticion, caso_uso: CambioDeUnidadDep) -> CambioDeUnidadRespuesta:
    return _respuesta(await caso_uso.teclear_equivalencia(cambio_id, peticion.equivalencia))


@router.post(
    "/cambios-de-unidad/{cambio_id}/aprobar",
    response_model=ResultadoDelCambioRespuesta,
    summary="Aprobar el cambio: nace una versión del concepto con las cantidades convertidas",
    dependencies=_ROL,
    responses={**_RESPUESTAS, 409: {"description": "Todas las partidas están asignadas o con avance."}},
)
async def aprobar_cambio(cambio_id: UUID, ctx: ContextoActual, caso_uso: CambioDeUnidadDep) -> ResultadoDelCambioRespuesta:
    r = await caso_uso.aprobar(cambio_id, ctx.usuario_id, detectada_en=datetime.now(UTC))
    return ResultadoDelCambioRespuesta(
        concepto_nuevo_id=r.concepto_nuevo_id, clave_nueva=r.clave_nueva, partidas_movidas=r.partidas_movidas,
        partidas_bloqueadas=r.partidas_bloqueadas, enlaces_rehechos=r.enlaces_rehechos, enlaces_sin_medida=r.enlaces_sin_medida,
    )


@router.post(
    "/cambios-de-unidad/{cambio_id}/rechazar",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Rechazar el cambio de unidad",
    dependencies=_ROL,
    responses=_RESPUESTAS,
)
async def rechazar_cambio(cambio_id: UUID, ctx: ContextoActual, caso_uso: CambioDeUnidadDep) -> None:
    await caso_uso.rechazar(cambio_id, ctx.usuario_id)


@router.get(
    "/trazos/{trazo_id}/cambios-de-unidad",
    response_model=list[MarcaDeCambioRespuesta],
    summary="Qué enlaces de un trazo se rehicieron por un cambio de unidad",
)
async def marcas_del_trazo(trazo_id: UUID, caso_uso: CambioDeUnidadDep) -> list[MarcaDeCambioRespuesta]:
    return [MarcaDeCambioRespuesta(**m) for m in await caso_uso.marcas_del_trazo(trazo_id)]
