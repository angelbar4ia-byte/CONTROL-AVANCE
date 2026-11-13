"""Endpoints de la biblioteca de elementos y del cálculo del muro de contención de piedra (MCT-01010).

El cálculo vive en el dominio (`muro_contencion`); aquí solo se valida la entrada y se devuelve el resultado.
No guarda nada: es el cálculo por metro lineal de trazo con los parámetros que se mandan. Controladores delgados.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from obractrl.domain.cuantificacion.biblioteca_de_elementos import (
    BIBLIOTECA,
    elemento_de_la_biblioteca,
)
from obractrl.domain.cuantificacion.muro_contencion import (
    CLAVE_ELEMENTO,
    EntradaMuroDeContencion,
    ErrorDeMuroDeContencion,
    calcular_muro_de_contencion,
)

router = APIRouter(tags=["biblioteca de elementos"])


class ConceptoDelElemento(BaseModel):
    clave: str
    descripcion: str
    unidad: str


class ElementoDeBiblioteca(BaseModel):
    clave: str
    nombre: str
    tipo: str
    se_mide_por: str
    concepto: ConceptoDelElemento


class SubcategoriaDeBiblioteca(BaseModel):
    clave: str
    nombre: str
    prefijo: str
    elementos: list[ElementoDeBiblioteca]


class CategoriaDeBiblioteca(BaseModel):
    clave: str
    nombre: str
    prefijo: str
    subcategorias: list[SubcategoriaDeBiblioteca]


class PendienteDelElemento(BaseModel):
    clave: str
    texto: str


class FilaDelCuadro1(BaseModel):
    H: float
    B: float
    B1: float
    Vm: float
    piedra: float
    cemento_kg: float
    arena_m3: float
    agua_l: float


class DefinicionDelElemento(BaseModel):
    clave: str
    nombre: str
    tipo: str
    se_mide_por: str
    concepto: ConceptoDelElemento
    categoria: dict[str, str]
    subcategoria: dict[str, str]
    parametros_por_defecto: dict[str, Any]
    cuadro_1: list[FilaDelCuadro1]
    fuente: str
    dentellon: dict[str, float]
    pendientes: list[PendienteDelElemento]


class CalculoDelMuroPeticion(BaseModel):
    alto_m: float = Field(gt=0, le=20, description="Altura del muro en METROS.")
    corona_m: float | None = Field(
        default=None, gt=0, le=10, description="Corona a mano; vacío usa el Cuadro 1."
    )
    base_m: float | None = Field(
        default=None, gt=0, le=10, description="Base a mano; vacío usa el Cuadro 1."
    )
    dentellon: bool = Field(
        default=True, description="Opcional; solo aplica desde 2.00 m de altura."
    )
    lluvia: Literal["baja", "alta"] = "baja"
    tubo: Literal["pvc", "concreto"] = "pvc"
    filtro_cm: float | None = Field(
        default=None,
        gt=0,
        le=200,
        description="Espesor del filtro de grava; el manual no lo da.",
    )
    relleno: Literal["vertical", "inclinada"] = "vertical"
    tramo_m: float = Field(
        default=6.0, gt=0, le=50, description="Largo del tramo que dibujan las vistas."
    )


class CalculoDelMuro(BaseModel):
    """El resultado completo (secciones anidadas) por metro lineal de trazo."""

    clave: str
    unidad: str
    concepto: dict[str, Any]
    seccion: dict[str, Any]
    volumen: dict[str, float]
    dentellon: dict[str, Any]
    dren: dict[str, Any]
    insumos_por_m3: list[dict[str, Any]]
    vistas: dict[str, Any]
    advertencias: list[str]


@router.get(
    "/biblioteca-de-elementos",
    response_model=list[CategoriaDeBiblioteca],
    summary="La biblioteca de elementos por categoría y subcategoría",
)
async def biblioteca_de_elementos() -> list[dict[str, Any]]:
    return [
        {
            **c,
            "subcategorias": [
                {**s, "elementos": list(s["elementos"])} for s in c["subcategorias"]
            ],
        }
        for c in BIBLIOTECA
    ]


@router.get(
    "/biblioteca-de-elementos/{clave}",
    response_model=DefinicionDelElemento,
    summary="La definición de un elemento de la biblioteca (Cuadro 1, pendientes y fuente)",
)
async def definicion_del_elemento(clave: str) -> dict[str, Any]:
    elemento = elemento_de_la_biblioteca(clave)
    if elemento is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"No hay un elemento {clave} en la biblioteca."
        )
    return elemento


@router.post(
    "/biblioteca-de-elementos/{clave}/calcular",
    response_model=CalculoDelMuro,
    summary="Calcula el muro de contención de piedra por metro lineal de trazo",
)
async def calcular_elemento(
    clave: str, peticion: CalculoDelMuroPeticion
) -> dict[str, Any]:
    if clave != CLAVE_ELEMENTO:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"No hay un elemento {clave} con cálculo en la biblioteca.",
        )
    try:
        return calcular_muro_de_contencion(
            EntradaMuroDeContencion(**peticion.model_dump())
        )
    except ErrorDeMuroDeContencion as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
