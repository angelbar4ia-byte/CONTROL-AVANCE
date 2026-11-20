"""Endpoints del Paramétrico: drivers (global, por obra, mixto) y enlace de ranuras con el árbol de la obra (Ola 4B; migración 0134).

Leen todos los roles con acceso a la obra; **proponen** Costos y Control de obra (Q3) y **solo Control de obra autoriza** (F3): lo que
propone Control de obra se aplica (200); lo de Costos queda pendiente y no cambia nada (202) hasta que Control de obra lo autorice. Cada
propuesta guarda quién y cuándo. Cambiar un driver no recalcula lo ya guardado (Q1). Una ranura sin partida en el árbol avisa y no cuenta. Controladores delgados.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    GestionarDriversDep,
    GestionarEnlacesDeRanuraDep,
    GestionarNumeroDeNivelDep,
)
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["parametrico"])

_ROLES = [Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.COSTOS))]
_RESPUESTAS = {
    202: {"description": "Costos propuso el cambio: queda pendiente y el driver no cambia hasta que Control de obra lo autorice."},
    403: {"description": "Lo proponen Costos y Control de obra; solo Control de obra autoriza."},
    404: {"description": "El driver, la obra o el enlace no existen o están fuera de tu alcance."},
    422: {"description": "El valor no vale, el driver es fijo, o el concepto no existe en el catálogo."},
}

ModoDelDriver = Literal["fijo", "ajustable"]


EstadoDeLaPropuesta = Literal["pendiente", "autorizada", "rechazada"]


class PropuestaDeDriver(BaseModel):
    id: UUID
    clave: str
    alcance: Literal["global", "obra"]
    obra_id: UUID | None
    accion: Literal["fijar", "quitar"]
    valor: Decimal | None = Field(description="El valor propuesto (`null` si solo cambia el modo o se quita el ajuste de la obra).")
    modo: ModoDelDriver | None
    valor_anterior: Decimal | None = Field(description="Lo que valía cuando se propuso.")
    modo_anterior: ModoDelDriver | None
    estado: EstadoDeLaPropuesta
    propuso_id: UUID | None
    propuso_nombre: str | None
    propuso_rol: str
    propuesto_en: datetime
    decidio_id: UUID | None
    decidio_nombre: str | None
    decidio_rol: str | None
    decidido_en: datetime | None
    motivo: str | None = Field(description="Por qué se rechazó.")


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
    lo_usan: list[ConsumidorDelDriver] = Field(
        default_factory=list, description="Los elementos y artefactos cuyo cálculo lee este driver (registro del dominio, probado)."
    )
    sin_consumidor: str | None = Field(default=None, description="Si ningún cálculo lo lee todavía: el motivo.")
    inmutable: bool = Field(default=False, description="F4: no se cambia ni se propone (el cálculo lo lee como constante del dominio).")
    propuestas_pendientes: list[PropuestaDeDriver] = Field(
        default_factory=list, description="Los cambios propuestos a este driver que Control de obra aún no decide (el global y, con obra, los de esa obra)."
    )
    propuesta: PropuestaDeDriver | None = Field(
        default=None, description="Solo al proponer, autorizar o rechazar: la propuesta de la que sale esta respuesta."
    )


class ConsumidorDelDriver(BaseModel):
    id: str
    tipo: Literal["elemento", "artefacto", "plano"]
    nombre: str
    lectura: Literal["driver", "constante"] = Field(
        description="`driver`: el cálculo lee el valor vigente de la obra. `constante`: el driver es fijo y el cálculo lo lee como constante."
    )


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


def _con_codigo(resultado: dict, respuesta: Response) -> DriverRespuesta:
    """200 si el cambio quedó aplicado; 202 si quedó pendiente de la autorización de Control de obra."""
    propuesta = resultado.get("propuesta")
    if propuesta is not None and propuesta["estado"] == "pendiente":
        respuesta.status_code = status.HTTP_202_ACCEPTED
    return DriverRespuesta(**resultado)


@router.put(
    "/drivers/{clave}",
    response_model=DriverRespuesta,
    summary="Proponer el valor y/o el modo (fijo, ajustable) del driver global (lo autoriza Control de obra)",
    dependencies=_ROLES,
    responses=_RESPUESTAS,
)
async def fijar_driver_global(
    clave: str, peticion: DriverGlobalPeticion, ctx: ContextoActual, caso_uso: GestionarDriversDep, respuesta: Response
) -> DriverRespuesta:
    return _con_codigo(
        await caso_uso.fijar_global(clave, valor=peticion.valor, modo=peticion.modo, usuario_id=ctx.usuario_id, rol=ctx.rol), respuesta
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
    summary="Proponer el valor propio de una obra para un driver ajustable (lo autoriza Control de obra)",
    dependencies=_ROLES,
    responses=_RESPUESTAS,
)
async def fijar_driver_de_obra(
    obra_id: UUID, clave: str, peticion: DriverDeObraPeticion, ctx: ContextoActual, caso_uso: GestionarDriversDep, respuesta: Response
) -> DriverRespuesta:
    return _con_codigo(
        await caso_uso.fijar_de_obra(obra_id, clave, valor=peticion.valor, usuario_id=ctx.usuario_id, rol=ctx.rol), respuesta
    )


@router.delete(
    "/obras/{obra_id}/drivers/{clave}",
    response_model=DriverRespuesta,
    summary="Proponer quitar el ajuste de la obra: vuelve al valor global (lo autoriza Control de obra)",
    dependencies=_ROLES,
    responses=_RESPUESTAS,
)
async def quitar_driver_de_obra(
    obra_id: UUID, clave: str, ctx: ContextoActual, caso_uso: GestionarDriversDep, respuesta: Response
) -> DriverRespuesta:
    return _con_codigo(await caso_uso.quitar_de_obra(obra_id, clave, usuario_id=ctx.usuario_id, rol=ctx.rol), respuesta)


class RechazoDePropuesta(BaseModel):
    motivo: str | None = Field(default=None, max_length=300, description="Por qué se rechaza (opcional).")


@router.get(
    "/drivers-propuestas",
    response_model=list[PropuestaDeDriver],
    summary="Las propuestas de cambio de drivers: quién propuso, quién decidió y cuándo (la bitácora)",
    responses={404: _RESPUESTAS[404]},
)
async def propuestas_de_drivers(
    caso_uso: GestionarDriversDep,
    estado: Annotated[EstadoDeLaPropuesta | None, Query(description="Solo las que están en este estado.")] = None,
    obra_id: Annotated[UUID | None, Query(description="Las globales y las de esta obra.")] = None,
    clave: Annotated[str | None, Query(description="Solo las de este driver.")] = None,
) -> list[PropuestaDeDriver]:
    return [PropuestaDeDriver(**p) for p in await caso_uso.propuestas(estado=estado, obra_id=obra_id, clave=clave)]


@router.post(
    "/drivers-propuestas/{propuesta_id}/autorizar",
    response_model=DriverRespuesta,
    summary="Autorizar un cambio de driver (solo Control de obra): se aplica y queda quién y cuándo",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA))],
    responses={403: {"description": "Solo Control de obra autoriza."}, 404: _RESPUESTAS[404], 422: _RESPUESTAS[422]},
)
async def autorizar_propuesta_de_driver(propuesta_id: UUID, ctx: ContextoActual, caso_uso: GestionarDriversDep) -> DriverRespuesta:
    return DriverRespuesta(**await caso_uso.autorizar(propuesta_id, usuario_id=ctx.usuario_id, rol=ctx.rol))


@router.post(
    "/drivers-propuestas/{propuesta_id}/rechazar",
    response_model=DriverRespuesta,
    summary="Rechazar un cambio de driver (solo Control de obra)",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA))],
    responses={403: {"description": "Solo Control de obra decide."}, 404: _RESPUESTAS[404], 422: _RESPUESTAS[422]},
)
async def rechazar_propuesta_de_driver(
    propuesta_id: UUID, peticion: RechazoDePropuesta, ctx: ContextoActual, caso_uso: GestionarDriversDep
) -> DriverRespuesta:
    return DriverRespuesta(**await caso_uso.rechazar(propuesta_id, usuario_id=ctx.usuario_id, rol=ctx.rol, motivo=peticion.motivo))


# --- enlace de ranuras --------------------------------------------------------------------------------------------------


class CapaDelEnlace(BaseModel):
    nivel_id: UUID | None = None
    etapa_id: UUID | None = None
    ubicacion: str | None = None
    espacio_id: UUID | None = Field(default=None, description="La capa «espacio» (0143): el enlace solo aplica a lo que se mide en ese espacio.")


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


class NivelDelArbol(CapaDelArbol):
    orden: int | None = Field(default=None, description="El orden del nivel en el árbol (puede tener saltos).")
    numero_de_nivel: int | None = Field(
        default=None, description="F5: el número de nivel explícito del contexto (PB = 1) con el que se eligen los conceptos de un elemento."
    )
    numero_efectivo: int | None = Field(
        default=None,
        description="El que se usa: el explícito; sin él, el orden si los niveles son consecutivos; con saltos y sin número, `null` (no descarta conceptos).",
    )


class EspacioDelArbol(BaseModel):
    id: UUID
    nombre: str
    tipo: str
    nivel_id: UUID | None = None
    area_m2: Decimal | None = None
    orden: int = 0


class NumeroDeNivelPeticion(BaseModel):
    numero_de_nivel: int | None = Field(ge=1, le=99, description="PB = 1. `null` quita el número explícito.")


class ConceptoDelArbol(BaseModel):
    clave: str
    descripcion: str


class EnlacesDeRanuraRespuesta(BaseModel):
    enlaces: list[EnlaceDeRanuraRespuesta]
    ranuras_de_plantilla: list[RanuraDePlantilla]
    niveles: list[NivelDelArbol] = Field(description="Los niveles que usa el árbol de la obra.")
    etapas: list[CapaDelArbol] = Field(description="Las etapas que usa el árbol de la obra.")
    espacios: list[EspacioDelArbol] = Field(default_factory=list, description="Los espacios de la obra (0143): una capa más donde enlazar.")
    partidas_del_arbol: int = Field(description="Cuántos conceptos tiene el árbol de la obra.")
    conceptos_del_arbol: list[ConceptoDelArbol] = Field(description="Los conceptos distintos que el árbol de la obra ya trae: los que se enlazan sin avisos.")


class EnlaceDeRanuraPeticion(BaseModel):
    ranura: str = Field(min_length=1, max_length=120)
    concepto_clave: str = Field(min_length=1, max_length=60, description="Un concepto que ya existe en el catálogo.")
    nivel_id: UUID | None = None
    etapa_id: UUID | None = None
    ubicacion: str | None = Field(default=None, max_length=20)
    espacio_id: UUID | None = Field(default=None, description="La capa «espacio» (0143); sin él el enlace aplica a cualquier espacio.")


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
        **{k: v for k, v in f.items() if k not in ("capa", "nivel_id", "etapa_id", "ubicacion", "espacio_id", "orden")},
        capa=CapaDelEnlace(nivel_id=c.nivel_id, etapa_id=c.etapa_id, ubicacion=c.ubicacion, espacio_id=c.espacio_id),
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
        niveles=[NivelDelArbol(**n) for n in r["niveles"]],
        etapas=[CapaDelArbol(**n) for n in r["etapas"]],
        espacios=[EspacioDelArbol(**n) for n in r.get("espacios", [])],
        partidas_del_arbol=r["partidas_del_arbol"],
        conceptos_del_arbol=[ConceptoDelArbol(**c) for c in r["conceptos_del_arbol"]],
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
    espacio_id: UUID | None = None,
) -> ResolucionDeRanura:
    return ResolucionDeRanura(
        **await caso_uso.resolver(obra_id, ranura, nivel_id=nivel_id, etapa_id=etapa_id, ubicacion=ubicacion, espacio_id=espacio_id)
    )


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
        espacio_id=peticion.espacio_id,
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


@router.put(
    "/niveles/{nivel_id}/numero-de-nivel",
    response_model=NivelDelArbol,
    summary="Fijar el número de nivel explícito del contexto (PB = 1); con saltos de nivel ya no se usa el orden",
    dependencies=_ROLES,
    responses=_RESPUESTAS,
)
async def fijar_numero_de_nivel(nivel_id: UUID, peticion: NumeroDeNivelPeticion, caso_uso: GestionarNumeroDeNivelDep) -> NivelDelArbol:
    return NivelDelArbol(**await caso_uso.fijar(nivel_id, peticion.numero_de_nivel))
