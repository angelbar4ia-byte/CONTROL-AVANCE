"""Endpoints de las mediciones: la capa sombra del cuantificador (migración 0088).

Controladores delgados: validan el DTO y delegan en `application.casos_uso.mediciones`.
Una medición agrupa trazos de un tipo (área, lineal o conteo) sin depender de ningún concepto y se
asigna después a uno o varios; asignar crea los enlaces de sus trazos y los de sus submediciones.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import GestionarMedicionesDep
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.adapters.api.v1.cuantificacion import (
    ROLES_QUE_TRAZAN,
    ResultadoRecalculoRespuesta,
)
from obractrl.application.casos_uso.mediciones import (
    ComandoCrearAsignacion,
    ComandoCrearMedicion,
)

router = APIRouter(tags=["mediciones"])

TipoDeMedicion = Literal["area", "lineal", "conteo"]
MedidaDeAsignacion = Literal["area", "perimetro", "longitud", "conteo"]

_UNIDAD = {"area": "m²", "lineal": "m", "conteo": "pza"}


class AsignacionRespuesta(BaseModel):
    id: UUID
    actividad_id: UUID
    concepto_clave: str
    descripcion: str
    matriz_concepto_id: UUID | None = None
    matriz_clave: str | None = None
    medida: str
    factor: Decimal


class MedicionRespuesta(BaseModel):
    id: UUID
    parent_id: UUID | None = None
    nombre: str
    tipo: TipoDeMedicion
    orden: int
    n_trazos: int = Field(description="Trazos de la medición y de sus submediciones.")
    valor: Decimal = Field(
        description="Lo que miden esos trazos: m² (área), m (lineal) o piezas (conteo), ya con la escala del plano."
    )
    unidad: str
    asignaciones: list[AsignacionRespuesta]


class MedicionPeticion(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    tipo: TipoDeMedicion
    parent_id: UUID | None = Field(
        default=None, description="La medición que la contiene; del mismo tipo (espacios de una losa)."
    )


class MedicionCreada(BaseModel):
    id: UUID


class RenombrarPeticion(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)


class AsignacionPeticion(BaseModel):
    actividad_id: UUID
    matriz_concepto_id: UUID | None = None
    medida: MedidaDeAsignacion
    factor: Decimal = Field(default=Decimal(1), gt=0)


class AsignacionCreada(BaseModel):
    id: UUID | None
    trazos_enlazados: int = Field(description="Trazos a los que se les creó (o quitó) el enlace.")
    recalculos: list[ResultadoRecalculoRespuesta]


class TrazoEnMedicionPeticion(BaseModel):
    medicion_id: UUID | None = Field(default=None, description="`null` saca el trazo de su medición.")


class TrazoEnMedicionRespuesta(BaseModel):
    recalculos: list[ResultadoRecalculoRespuesta]


@router.get(
    "/planos/{plano_id}/mediciones",
    response_model=list[MedicionRespuesta],
    summary="Las mediciones de un plano, con lo que miden y a qué conceptos alimentan",
    responses={404: {"description": "El plano no existe o está fuera de tu alcance."}},
)
async def listar_mediciones(plano_id: UUID, caso_uso: GestionarMedicionesDep) -> list[MedicionRespuesta]:
    filas = await caso_uso.listar(plano_id)
    return [
        MedicionRespuesta(
            id=f["id"],
            parent_id=f["parent_id"],
            nombre=f["nombre"],
            tipo=f["tipo"],
            orden=f["orden"],
            n_trazos=int(f["n_trazos"]),
            valor=Decimal(str(f["valor"])),
            unidad=_UNIDAD[f["tipo"]],
            asignaciones=[
                AsignacionRespuesta(
                    id=a["id"],
                    actividad_id=a["actividad_id"],
                    concepto_clave=a["concepto_clave"],
                    descripcion=a["descripcion"],
                    matriz_concepto_id=a["matriz_concepto_id"],
                    matriz_clave=a["matriz_clave"],
                    medida=a["medida"],
                    factor=a["factor"],
                )
                for a in f["asignaciones"]
            ],
        )
        for f in filas
    ]


@router.post(
    "/planos/{plano_id}/mediciones",
    response_model=MedicionCreada,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una medición (o una submedición)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={
        404: {"description": "El plano o la medición madre no existen o están fuera de tu alcance."},
        422: {"description": "Nombre repetido entre hermanas, tipo distinto del de la madre o nombre vacío."},
    },
)
async def crear_medicion(
    plano_id: UUID, peticion: MedicionPeticion, ctx: ContextoActual, caso_uso: GestionarMedicionesDep
) -> MedicionCreada:
    medicion_id = await caso_uso.crear(
        ComandoCrearMedicion(
            plano_id=plano_id,
            nombre=peticion.nombre,
            tipo=peticion.tipo,
            parent_id=peticion.parent_id,
            autor_id=ctx.usuario_id,
        )
    )
    return MedicionCreada(id=medicion_id)


@router.patch(
    "/mediciones/{medicion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Renombrar una medición",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={404: {"description": "La medición no existe o está fuera de tu alcance."}},
)
async def renombrar_medicion(
    medicion_id: UUID, peticion: RenombrarPeticion, caso_uso: GestionarMedicionesDep
) -> None:
    await caso_uso.renombrar(medicion_id, peticion.nombre)


@router.delete(
    "/mediciones/{medicion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Borrar una medición sin asignaciones ni submediciones (sus trazos quedan sueltos)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={
        404: {"description": "La medición no existe o está fuera de tu alcance."},
        422: {"description": "Alimenta conceptos o tiene submediciones."},
    },
)
async def eliminar_medicion(medicion_id: UUID, caso_uso: GestionarMedicionesDep) -> None:
    await caso_uso.eliminar(medicion_id)


@router.put(
    "/trazos/{trazo_id}/medicion",
    response_model=TrazoEnMedicionRespuesta,
    summary="Meter un trazo en una medición, o sacarlo de ella",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={
        404: {"description": "El trazo o la medición no existen o están fuera de tu alcance."},
        422: {"description": "El trazo no es del tipo de la medición, o es de otro plano."},
    },
)
async def poner_trazo_en_medicion(
    trazo_id: UUID,
    peticion: TrazoEnMedicionPeticion,
    ctx: ContextoActual,
    caso_uso: GestionarMedicionesDep,
) -> TrazoEnMedicionRespuesta:
    """Al entrar recibe los enlaces de la medición (y de las que la contienen); al salir pierde los que
    le venían de ella. Los enlaces quitados quedan como evidencia, no vigentes."""
    recalculos = await caso_uso.asignar_trazo(
        trazo_id=trazo_id,
        medicion_id=peticion.medicion_id,
        usuario_id=ctx.usuario_id,
        detectada_en=datetime.now(UTC),
    )
    return TrazoEnMedicionRespuesta(
        recalculos=[ResultadoRecalculoRespuesta.desde_dominio(r) for r in recalculos]
    )


@router.post(
    "/mediciones/{medicion_id}/asignaciones",
    response_model=AsignacionCreada,
    status_code=status.HTTP_201_CREATED,
    summary="Asignar una medición a un concepto de la obra",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={
        404: {"description": "La medición no existe o está fuera de tu alcance."},
        422: {"description": "Medida que no corresponde al tipo, concepto de otra obra o asignación repetida en la rama."},
    },
)
async def asignar_medicion(
    medicion_id: UUID,
    peticion: AsignacionPeticion,
    ctx: ContextoActual,
    caso_uso: GestionarMedicionesDep,
) -> AsignacionCreada:
    """Crea un enlace por cada trazo de la medición y de sus submediciones, y recalcula el concepto.
    Un trazo que entre después a la medición hereda este enlace."""
    resultado = await caso_uso.crear_asignacion(
        ComandoCrearAsignacion(
            medicion_id=medicion_id,
            actividad_id=peticion.actividad_id,
            matriz_concepto_id=peticion.matriz_concepto_id,
            medida=peticion.medida,
            factor=peticion.factor,
            autor_id=ctx.usuario_id,
        ),
        detectada_en=datetime.now(UTC),
    )
    return AsignacionCreada(
        id=resultado.asignacion_id,
        trazos_enlazados=resultado.trazos_enlazados,
        recalculos=[ResultadoRecalculoRespuesta.desde_dominio(r) for r in resultado.recalculos],
    )


@router.delete(
    "/asignaciones-de-medicion/{asignacion_id}",
    response_model=AsignacionCreada,
    summary="Quitar la asignación de una medición a un concepto",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={404: {"description": "La asignación no existe o está fuera de tu alcance."}},
)
async def quitar_asignacion(
    asignacion_id: UUID, ctx: ContextoActual, caso_uso: GestionarMedicionesDep
) -> AsignacionCreada:
    """Los enlaces que nacieron de ella quedan como evidencia (no vigentes) y el concepto se recalcula."""
    resultado = await caso_uso.quitar_asignacion(
        asignacion_id, usuario_id=ctx.usuario_id, detectada_en=datetime.now(UTC)
    )
    return AsignacionCreada(
        id=None,
        trazos_enlazados=resultado.trazos_enlazados,
        recalculos=[ResultadoRecalculoRespuesta.desde_dominio(r) for r in resultado.recalculos],
    )
