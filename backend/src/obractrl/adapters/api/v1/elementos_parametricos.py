"""Endpoints de los elementos paramétricos (D-602, D-604; migración 0104).

Una pieza con medidas, armado y estribos —castillo, trabe o cadena, zapata, losa— de la que salen concreto, acero,
estribos, alambre y cimbra. Son del catálogo de la organización; los define Control de obra y Costos. Cada lectura
trae la **receta de una muestra** calculada por el servidor. Controladores delgados.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import GestionarElementosParametricosDep
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.application.casos_uso.elementos_parametricos import (
    ComandoCrearElementoParametrico,
)
from obractrl.domain.cuantificacion.elementos_parametricos import (
    PARAMETROS_POR_TIPO,
    UNIDAD_DE_CALCULO,
)
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["elementos parametricos"])

ROLES_QUE_DEFINEN = (Rol.CONTROL_OBRA, Rol.COSTOS)
"""El elemento es del catálogo de la organización y alimenta recetas: lo definen Control de obra y Costos (D-602)."""

TipoDeElementoParametrico = Literal["castillo", "lineal", "zapata", "losa"]


class RecetaRespuesta(BaseModel):
    unidad: str = Field(description="La unidad de cálculo de la muestra: pza, ml o m².")
    concreto: float = Field(description="m³ por muestra.")
    acero_kg: float
    estribos_kg: float
    n_estribos: float
    long_estribo_m: float
    n_amarres: float
    alambre_kg: float
    varas: float = Field(description="Varas comerciales de 12 m por muestra.")
    cimbra_m2: dict[str, float] = Field(description="m² de cimbra por número de lados.")


class ElementoParametricoRespuesta(BaseModel):
    id: UUID
    clave: str
    nombre: str
    tipo: TipoDeElementoParametrico
    parametros: dict[str, float]
    receta: RecetaRespuesta


class ElementoParametricoPeticion(BaseModel):
    clave: str = Field(min_length=1, max_length=20)
    nombre: str = Field(min_length=1, max_length=80)
    tipo: TipoDeElementoParametrico
    parametros: dict[str, float] = Field(default_factory=dict, description="Los que falten toman el valor por defecto del tipo.")


class ElementoParametricoCambio(BaseModel):
    clave: str | None = Field(default=None, min_length=1, max_length=20)
    nombre: str | None = Field(default=None, min_length=1, max_length=80)
    parametros: dict[str, float] | None = Field(default=None, description="Solo los que cambian.")


class ElementoParametricoCreado(BaseModel):
    id: UUID


class TipoDeElementoRespuesta(BaseModel):
    tipo: TipoDeElementoParametrico
    unidad: str
    parametros_por_defecto: dict[str, float]


def _respuesta(fila: dict[str, Any]) -> ElementoParametricoRespuesta:
    r = fila["receta"]
    return ElementoParametricoRespuesta(
        id=fila["id"],
        clave=fila["clave"],
        nombre=fila["nombre"],
        tipo=fila["tipo"],
        parametros={k: float(v) for k, v in fila["parametros"].items()},
        receta=RecetaRespuesta(**{**r, "cimbra_m2": {str(k): float(v) for k, v in r["cimbra_m2"].items()}}),
    )


@router.get(
    "/elementos-parametricos/tipos",
    response_model=list[TipoDeElementoRespuesta],
    summary="Los tipos de elemento paramétrico y sus parámetros por defecto",
)
async def tipos_de_elemento() -> list[TipoDeElementoRespuesta]:
    return [
        TipoDeElementoRespuesta(
            tipo=t,  # type: ignore[arg-type]
            unidad=UNIDAD_DE_CALCULO[t],
            parametros_por_defecto={k: float(v) for k, v in PARAMETROS_POR_TIPO[t].items()},
        )
        for t in PARAMETROS_POR_TIPO
    ]


@router.get(
    "/elementos-parametricos",
    response_model=list[ElementoParametricoRespuesta],
    summary="Los elementos paramétricos de la organización, con la receta de una muestra",
)
async def listar_elementos_parametricos(caso_uso: GestionarElementosParametricosDep) -> list[ElementoParametricoRespuesta]:
    return [_respuesta(f) for f in await caso_uso.listar()]


@router.post(
    "/elementos-parametricos",
    response_model=ElementoParametricoCreado,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un elemento paramétrico",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_DEFINEN))],
    responses={
        403: {"description": "Lo definen Control de obra y Costos."},
        422: {"description": "Clave repetida o un parámetro que no vale."},
    },
)
async def crear_elemento_parametrico(
    peticion: ElementoParametricoPeticion, ctx: ContextoActual, caso_uso: GestionarElementosParametricosDep
) -> ElementoParametricoCreado:
    nuevo = await caso_uso.crear(
        ComandoCrearElementoParametrico(
            clave=peticion.clave,
            nombre=peticion.nombre,
            tipo=peticion.tipo,
            parametros=dict(peticion.parametros),
            autor_id=ctx.usuario_id,
        )
    )
    return ElementoParametricoCreado(id=nuevo)


@router.patch(
    "/elementos-parametricos/{elemento_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cambiar la clave, el nombre o algunos parámetros de un elemento paramétrico",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_DEFINEN))],
    responses={
        403: {"description": "Lo definen Control de obra y Costos."},
        404: {"description": "El elemento no existe o está fuera de tu alcance."},
        422: {"description": "Clave repetida o un parámetro que no vale."},
    },
)
async def actualizar_elemento_parametrico(
    elemento_id: UUID, peticion: ElementoParametricoCambio, caso_uso: GestionarElementosParametricosDep
) -> None:
    await caso_uso.actualizar(
        elemento_id,
        clave=peticion.clave,
        nombre=peticion.nombre,
        parametros=dict(peticion.parametros) if peticion.parametros is not None else None,
    )


@router.delete(
    "/elementos-parametricos/{elemento_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Borrar un elemento paramétrico",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_DEFINEN))],
    responses={
        403: {"description": "Lo definen Control de obra y Costos."},
        404: {"description": "El elemento no existe o está fuera de tu alcance."},
    },
)
async def eliminar_elemento_parametrico(elemento_id: UUID, caso_uso: GestionarElementosParametricosDep) -> None:
    await caso_uso.eliminar(elemento_id)
