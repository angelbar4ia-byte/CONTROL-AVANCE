"""Endpoints de los espacios de una obra (D-565, D-566; migración 0143): el cuarto o área donde se asignan zonas de losa, muros y elementos.

Un **espacio** (recámara 1, baño, cochera…) es el nivel de agrupación entre el nivel/etapa y la partida del árbol del presupuesto: lo asignado a
un espacio se mide en la partida de ese espacio y alimenta la matriz del presupuesto sin doble conteo. Un muro que separa dos espacios se traza una
vez y se **reparte** (mitad y mitad por omisión). **Solo Control de obra escribe la estructura de los espacios y las asignaciones; todos los roles que
ven la obra leen.** Controladores delgados: las reglas viven en el dominio (`espacios`).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import GestionarEspaciosDep
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["espacios"])

ROLES_QUE_EDITAN = (Rol.CONTROL_OBRA,)
ROLES_QUE_LEEN = (Rol.RESIDENTE, Rol.SUPERVISOR, Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE, Rol.COSTOS)

TipoDeEspacio = Literal[
    "recamara", "bano", "cocina", "sala", "comedor", "estancia", "cochera", "pasillo", "escalera", "patio", "azotea", "bodega", "otro"
]

_ESCRIBE = {403: {"description": "Solo Control de obra edita los espacios."}, 404: {"description": "No existe o está fuera de tu alcance."}}


class EspacioPeticion(BaseModel):
    nombre: str = Field(min_length=1, max_length=60, description="Nombre del espacio (único en la obra), p. ej. «Recámara 1».")
    tipo: TipoDeEspacio | None = Field(default=None, description="Clasifica el espacio; sin él, «otro». No cambia ningún cálculo.")
    nivel_id: UUID | None = Field(default=None, description="El nivel donde está (informativo).")
    area_m2: Decimal | None = Field(default=None, gt=0, le=100000, description="m² del espacio, si se conocen.")


class Espacio(BaseModel):
    id: UUID
    obra_id: UUID
    nombre: str
    tipo: TipoDeEspacio
    nivel_id: UUID | None
    area_m2: Decimal | None
    orden: int
    muros: int = Field(description="Muros (líneas) asignados al espacio, solos o compartidos.")
    losas: int = Field(description="Polígonos de losa asignados al espacio.")
    elementos: int = Field(description="Elementos de zonas de losa (trabes, contratrabes, nervaduras) asignados al espacio.")
    nodos: list[UUID] = Field(description="Las ramas del árbol del presupuesto (nodos del prototipo) que pertenecen al espacio: sus partidas lo heredan.")


class NodosDelEspacioPeticion(BaseModel):
    nodo_ids: list[UUID] = Field(max_length=500, description="Las ramas del árbol del presupuesto del espacio; sustituyen a las anteriores. Un nodo es de un solo espacio.")


class AsignacionDeEspacioPeticion(BaseModel):
    espacio_id: UUID | None = Field(default=None, description="El espacio donde cae el muro o el polígono de losa; `null` lo deja sin espacio.")
    espacio_comparte_id: UUID | None = Field(
        default=None, description="Muro compartido: el otro espacio. El muro se traza una vez y su cantidad se reparte entre los dos."
    )
    reparto_pct: Decimal | None = Field(
        default=None, gt=0, lt=100, description="Muro compartido: el % del espacio principal; sin él, mitad y mitad. El resto es del otro espacio."
    )


class ParteDelReparto(BaseModel):
    espacio_id: UUID
    fraccion: Decimal = Field(description="La parte del muro que cuenta en ese espacio. Las partes suman exactamente 1: no hay doble conteo.")


class AsignacionDeEspacio(BaseModel):
    trazo_id: UUID
    espacio_id: UUID | None
    espacio_comparte_id: UUID | None
    reparto_pct: Decimal | None
    reparto: list[ParteDelReparto]


@router.get(
    "/obras/{obra_id}/espacios",
    response_model=list[Espacio],
    summary="Los espacios de la obra, con lo que tiene asignado cada uno",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_LEEN))],
    responses={404: _ESCRIBE[404]},
)
async def espacios_de_la_obra(obra_id: UUID, caso_uso: GestionarEspaciosDep) -> list[dict]:
    return await caso_uso.listar(obra_id)


@router.post(
    "/obras/{obra_id}/espacios",
    response_model=Espacio,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un espacio de la obra (solo Control de obra)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
    responses={**_ESCRIBE, 422: {"description": "El nombre se repite o un dato no vale."}},
)
async def crear_espacio(obra_id: UUID, peticion: EspacioPeticion, ctx: ContextoActual, caso_uso: GestionarEspaciosDep) -> dict:
    return await caso_uso.crear(obra_id, rol=ctx.rol, autor_id=ctx.usuario_id, **peticion.model_dump())


@router.put(
    "/espacios/{espacio_id}",
    response_model=Espacio,
    summary="Cambiar un espacio (solo Control de obra)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
    responses={**_ESCRIBE, 422: {"description": "El nombre se repite o un dato no vale."}},
)
async def cambiar_espacio(espacio_id: UUID, peticion: EspacioPeticion, ctx: ContextoActual, caso_uso: GestionarEspaciosDep) -> dict:
    return await caso_uso.cambiar(espacio_id, rol=ctx.rol, **peticion.model_dump())


@router.delete(
    "/espacios/{espacio_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Borrar un espacio (solo Control de obra): lo asignado queda sin espacio y sus ramas del árbol vuelven a ser generales",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
    responses=_ESCRIBE,
)
async def borrar_espacio(espacio_id: UUID, ctx: ContextoActual, caso_uso: GestionarEspaciosDep) -> None:
    await caso_uso.borrar(espacio_id, rol=ctx.rol)


@router.put(
    "/espacios/{espacio_id}/nodos",
    response_model=Espacio,
    summary="Fijar las ramas del árbol del presupuesto que pertenecen al espacio (sus partidas heredan el espacio; solo Control de obra)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
    responses={**_ESCRIBE, 422: {"description": "Un nodo no es del árbol de la obra."}},
)
async def fijar_nodos_del_espacio(
    espacio_id: UUID, peticion: NodosDelEspacioPeticion, ctx: ContextoActual, caso_uso: GestionarEspaciosDep
) -> dict:
    return await caso_uso.fijar_nodos(espacio_id, rol=ctx.rol, nodo_ids=peticion.nodo_ids)


@router.get(
    "/trazos/{trazo_id}/espacio",
    response_model=AsignacionDeEspacio,
    summary="El espacio de un muro o de un polígono de losa y cómo se reparte si el muro es compartido",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_LEEN))],
    responses={404: _ESCRIBE[404]},
)
async def espacio_del_trazo(trazo_id: UUID, caso_uso: GestionarEspaciosDep) -> dict:
    return await caso_uso.ver_trazo(trazo_id)


@router.put(
    "/trazos/{trazo_id}/espacio",
    response_model=AsignacionDeEspacio,
    summary="Asignar un muro o un polígono de losa a un espacio, o compartir el muro entre dos con su reparto (solo Control de obra)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
    responses={**_ESCRIBE, 422: {"description": "La asignación no vale: espacio de otra obra, compartir sin principal, reparto fuera de rango."}},
)
async def asignar_espacio_al_trazo(
    trazo_id: UUID, peticion: AsignacionDeEspacioPeticion, ctx: ContextoActual, caso_uso: GestionarEspaciosDep
) -> dict:
    return await caso_uso.asignar_trazo(
        trazo_id, rol=ctx.rol, espacio_id=peticion.espacio_id, comparte_id=peticion.espacio_comparte_id, reparto_pct=peticion.reparto_pct
    )
