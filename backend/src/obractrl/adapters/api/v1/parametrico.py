"""Endpoints del Paramétrico: drivers (global, por obra, mixto) y enlace de ranuras con el árbol de la obra (Ola 4B; migración 0134).

Leen todos los roles con acceso a la obra; escriben **Costos y Control de obra** (Q3). Cambiar un driver no recalcula lo ya guardado
(Q1). Una ranura sin partida en el árbol avisa y no cuenta. Controladores delgados.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    GestionarDriversDep,
    GestionarEnlacesDeRanuraDep,
)
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["paramétrico"])

_ROLES = [Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.COSTOS))]
_RESPUESTAS = {
    403: {"description": "Lo editan Costos y Control de obra."},
    404: {"description": "El driver, la obra o el enlace no existen o están fuera de tu alcance."},
    422: {"description": "El valor no vale, el driver es fijo, o el concepto no existe en el catálogo."},
}

ModoDelDriver = Literal["fijo", "ajustable"]


class DriverRespuesta(BaseModel):
    clave: str
    nombre: str
    unidad: str
    nota: str
    por_confirmar: bool = Field(description="La especificación marca su valor como supuesto o por confirmar.")
    valor_inicial: Decimal = Field(description="El valor de partida: el que vale mientras nadie cambie el global.")
    modo_inicial: ModoDelDriver
    valor_global: Decimal = Field(description="El de la organización (el de partida si nadie lo ha cambiado).")
    modo: ModoDelDriver = Field(description="`fijo`: solo vale el global. `ajustable`: una obra puede tener el suyo.")
    valor_obra: Decimal | None = Field(description="Lo que la obra tiene guardado (puede no valer si el driver pasó a fijo).")
    valor_vigente: Decimal = Field(description="El que usan los cálculos: el de la obra si es ajustable y la obra lo cambió; si no, el global.")
    origen: Literal["obra", "global", "inicial"]
    ajuste_ignorado: bool = Field(description="La obra tiene un ajuste, pero el driver es fijo: manda el global.")
    editado: bool = Field(description="El global ya fue cambiado por alguien (si no, vale el de partida).")


class DriverGlobalPeticion(BaseModel):
    valor: Decimal | None = Field(default=None, description="El valor global. Si no se envía, se conserva.")
    modo: ModoDelDriver | None = Field(default=None, description="El modo. Si no se envía, se conserva.")


class DriverDeObraPeticion(BaseModel):
    valor: Decimal


@router.get(
    "/drivers",
    response_model=list[DriverRespuesta],
    summary="Los drivers del Paramétrico con su valor global y su modo",
)
async def drivers_globales(caso_uso: GestionarDriversDep) -> list[DriverRespuesta]:
    return [DriverRespuesta(**f) for f in await caso_uso.listar()]


@router.put(
    "/drivers/{clave}",
    response_model=DriverRespuesta,
    summary="Cambiar el valor y/o el modo (fijo, ajustable) del driver global",
    dependencies=_ROLES,
    responses=_RESPUESTAS,
)
async def fijar_driver_global(
    clave: str, peticion: DriverGlobalPeticion, ctx: ContextoActual, caso_uso: GestionarDriversDep
) -> DriverRespuesta:
    return DriverRespuesta(
        **await caso_uso.fijar_global(clave, valor=peticion.valor, modo=peticion.modo, usuario_id=ctx.usuario_id, rol=ctx.rol)
    )


@router.get(
    "/obras/{obra_id}/drivers",
    response_model=list[DriverRespuesta],
    summary="Los drivers con su valor vigente en una obra (global + ajustes de la obra)",
    responses={404: _RESPUESTAS[404]},
)
async def drivers_de_obra(obra_id: UUID, caso_uso: GestionarDriversDep) -> list[DriverRespuesta]:
    return [DriverRespuesta(**f) for f in await caso_uso.listar(obra_id)]


@router.put(
    "/obras/{obra_id}/drivers/{clave}",
    response_model=DriverRespuesta,
    summary="El valor propio de una obra para un driver ajustable",
    dependencies=_ROLES,
    responses=_RESPUESTAS,
)
async def fijar_driver_de_obra(
    obra_id: UUID, clave: str, peticion: DriverDeObraPeticion, ctx: ContextoActual, caso_uso: GestionarDriversDep
) -> DriverRespuesta:
    return DriverRespuesta(**await caso_uso.fijar_de_obra(obra_id, clave, valor=peticion.valor, usuario_id=ctx.usuario_id, rol=ctx.rol))


@router.delete(
    "/obras/{obra_id}/drivers/{clave}",
    response_model=DriverRespuesta,
    summary="Quitar el ajuste de la obra: vuelve al valor global",
    dependencies=_ROLES,
    responses=_RESPUESTAS,
)
async def quitar_driver_de_obra(obra_id: UUID, clave: str, ctx: ContextoActual, caso_uso: GestionarDriversDep) -> DriverRespuesta:
    return DriverRespuesta(**await caso_uso.quitar_de_obra(obra_id, clave, rol=ctx.rol))


# --- enlace de ranuras --------------------------------------------------------------------------------------------------


class CapaDelEnlace(BaseModel):
    nivel_id: UUID | None = None
    etapa_id: UUID | None = None
    ubicacion: str | None = None


EstadoDelEnlace = Literal["enlazado", "falta_partida", "sin_enlace"]


class EnlaceDeRanuraRespuesta(BaseModel):
    id: UUID
    ranura: str
    capa: CapaDelEnlace
    concepto_id: UUID
    concepto_clave: str
    concepto_descripcion: str
    unidad: str | None
    estado: EstadoDelEnlace = Field(description="`enlazado`: concepto y partida. `falta_partida`: el árbol no lo trae en esa capa.")
    cuenta: bool = Field(description="Solo cuenta con el concepto enlazado y su partida en el árbol.")
    aviso: str | None
    partida_id: UUID | None
    partida_nombre: str | None


class RanuraDePlantilla(BaseModel):
    ranura: str
    nombre: str
    grupo: Literal["mamposteria", "acabado"]
    sugerido_clave: str | None = Field(description="Un concepto del catálogo que la especificación propone; nunca se aplica solo.")


class CapaDelArbol(BaseModel):
    id: UUID
    clave: str
    descripcion: str


class EnlacesDeRanuraRespuesta(BaseModel):
    enlaces: list[EnlaceDeRanuraRespuesta]
    ranuras_de_plantilla: list[RanuraDePlantilla]
    niveles: list[CapaDelArbol] = Field(description="Los niveles que usa el árbol de la obra.")
    etapas: list[CapaDelArbol] = Field(description="Las etapas que usa el árbol de la obra.")
    partidas_del_arbol: int = Field(description="Cuántos conceptos tiene el árbol de la obra.")


class EnlaceDeRanuraPeticion(BaseModel):
    ranura: str = Field(min_length=1, max_length=120)
    concepto_clave: str = Field(min_length=1, max_length=60, description="Un concepto que ya existe en el catálogo.")
    nivel_id: UUID | None = None
    etapa_id: UUID | None = None
    ubicacion: str | None = Field(default=None, max_length=20)


class ResolucionDeRanura(BaseModel):
    ranura: str
    estado: EstadoDelEnlace
    cuenta: bool
    por_defecto: bool = Field(description="Una ranura de elemento sin enlace conserva los conceptos por defecto del elemento.")
    aviso: str | None
    enlace_id: UUID | None
    concepto_id: UUID | None
    concepto_clave: str | None
    partida_id: UUID | None
    partida_nombre: str | None


def _respuesta_de_enlace(f: dict) -> EnlaceDeRanuraRespuesta:
    c = f["capa"]
    return EnlaceDeRanuraRespuesta(
        **{k: v for k, v in f.items() if k not in ("capa", "nivel_id", "etapa_id", "ubicacion", "orden")},
        capa=CapaDelEnlace(nivel_id=c.nivel_id, etapa_id=c.etapa_id, ubicacion=c.ubicacion),
    )


@router.get(
    "/obras/{obra_id}/enlaces-de-ranura",
    response_model=EnlacesDeRanuraRespuesta,
    summary="Los enlaces de ranura de la obra, con lo que cuenta cada uno según el árbol",
    responses={404: _RESPUESTAS[404]},
)
async def enlaces_de_ranura(obra_id: UUID, caso_uso: GestionarEnlacesDeRanuraDep) -> EnlacesDeRanuraRespuesta:
    r = await caso_uso.listar(obra_id)
    return EnlacesDeRanuraRespuesta(
        enlaces=[_respuesta_de_enlace(e) for e in r["enlaces"]],
        ranuras_de_plantilla=[RanuraDePlantilla(**x) for x in r["ranuras_de_plantilla"]],
        niveles=[CapaDelArbol(**n) for n in r["niveles"]],
        etapas=[CapaDelArbol(**n) for n in r["etapas"]],
        partidas_del_arbol=r["partidas_del_arbol"],
    )


@router.get(
    "/obras/{obra_id}/enlaces-de-ranura/resolver",
    response_model=ResolucionDeRanura,
    summary="Lo que cuenta una ranura donde se mide: el concepto, su partida o el aviso de lo que falta",
    responses={404: _RESPUESTAS[404], 422: _RESPUESTAS[422]},
)
async def resolver_ranura(
    obra_id: UUID,
    caso_uso: GestionarEnlacesDeRanuraDep,
    ranura: str = Query(min_length=1, max_length=120),
    nivel_id: UUID | None = None,
    etapa_id: UUID | None = None,
    ubicacion: str | None = Query(default=None, max_length=20),
) -> ResolucionDeRanura:
    return ResolucionDeRanura(**await caso_uso.resolver(obra_id, ranura, nivel_id=nivel_id, etapa_id=etapa_id, ubicacion=ubicacion))


@router.put(
    "/obras/{obra_id}/enlaces-de-ranura",
    response_model=EnlaceDeRanuraRespuesta,
    summary="Enlazar una ranura con un concepto del catálogo en una capa (si la capa ya tenía enlace, lo cambia)",
    dependencies=_ROLES,
    responses=_RESPUESTAS,
)
async def enlazar_ranura(
    obra_id: UUID, peticion: EnlaceDeRanuraPeticion, ctx: ContextoActual, caso_uso: GestionarEnlacesDeRanuraDep, respuesta: Response
) -> EnlaceDeRanuraRespuesta:
    enlace, creado = await caso_uso.guardar(
        obra_id, ranura=peticion.ranura, concepto_clave=peticion.concepto_clave, nivel_id=peticion.nivel_id,
        etapa_id=peticion.etapa_id, ubicacion=peticion.ubicacion, usuario_id=ctx.usuario_id, rol=ctx.rol,
    )
    respuesta.status_code = status.HTTP_201_CREATED if creado else status.HTTP_200_OK
    return _respuesta_de_enlace(enlace)


@router.delete(
    "/obras/{obra_id}/enlaces-de-ranura/{enlace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Quitar un enlace de ranura",
    dependencies=_ROLES,
    responses=_RESPUESTAS,
)
async def quitar_enlace(obra_id: UUID, enlace_id: UUID, ctx: ContextoActual, caso_uso: GestionarEnlacesDeRanuraDep) -> None:
    await caso_uso.quitar(obra_id, enlace_id, rol=ctx.rol)
