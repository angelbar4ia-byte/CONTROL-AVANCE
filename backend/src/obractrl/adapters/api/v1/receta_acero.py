"""Cálculo de la receta del acero de los elementos lineales y de pieza (solo cálculo, no guarda nada).

`POST /biblioteca-de-elementos/receta-acero/calcular`: el cálculo vive en el dominio (`receta_acero`); aquí solo se
valida la entrada y se devuelve el resultado. Controlador delgado.

Este router se registra **antes** que el de la biblioteca: la ruta `/biblioteca-de-elementos/{clave}/calcular` de
aquel también casaría con `receta-acero` como si fuera una clave de elemento.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from obractrl.domain.cuantificacion.receta_acero import (
    Armex,
    ConsumoDeCimbra,
    DriversDeReceta,
    EntradaRecetaAcero,
    ErrorDeRecetaAcero,
    GrupoDeVarillas,
    Varilla,
    ZonaDeAnillo,
    calcular_receta_acero,
)

router = APIRouter(tags=["biblioteca de elementos"])


class DriversDeRecetaPeticion(BaseModel):
    """Los drivers del acero; lo que no se manda toma el valor por defecto del mockup."""

    traslape_armex_cm: float = Field(default=15.0, ge=0, le=100)
    traslape_varilla_diametros: float = Field(default=40.0, ge=0, le=100)
    puntas_inferior_diametros: float = Field(default=40.0, ge=0, le=100)
    puntas_superior_diametros: float = Field(default=40.0, ge=0, le=100)
    puntas_armex_cm: float = Field(default=50.0, ge=0, le=500)
    tolerancia_corte_cm: float = Field(default=0.0, ge=0, le=100)
    max_piezas_corte: int = Field(default=3, ge=1, le=12)
    desperdicio_acero_pct: float = Field(default=0.0, ge=0, le=50)


class VarillaPeticion(BaseModel):
    clave: str
    numero: int = Field(ge=2, le=12, description="Número de varilla: 3 = 3/8 pulg, 4 = 1/2 pulg…")
    largo_m: float = Field(default=12.0, gt=0, le=24)
    peso_kg_m: float | None = Field(default=None, ge=0)
    cantidad: int = Field(ge=1, le=100, description="Cuántas varillas de este tipo lleva el elemento.")
    etiqueta: str = ""


class ArmexPeticion(BaseModel):
    clave: str
    largo_m: float = Field(default=6.0, gt=0, le=24)
    peso_kg_m: float | None = Field(default=None, ge=0, description="El catálogo no lo da: queda sin dato.")


class ZonaDeAnilloPeticion(BaseModel):
    sep_cm: float = Field(gt=0, le=200)
    peso_kg_m: float = Field(ge=0)
    len_cm: float | None = Field(
        default=None,
        ge=0,
        le=3000,
        description="Largo de la zona (en cada extremo en una trabe por pieza); vacío = el resto o el centro.",
    )
    clave: str | None = None


class ConsumoDeCimbraPeticion(BaseModel):
    clave: str
    por_ml: float | None = Field(default=None, ge=0, description="Consumo por metro de elemento.")
    por_m2: float | None = Field(default=None, ge=0, description="Consumo por m² de cimbra.")


class RecetaDeAceroPeticion(BaseModel):
    forma: Literal["castillo", "pieza", "ml"] = Field(
        description="castillo = por pieza de altura conocida; pieza = trabe o contratrabe por pieza; ml = por metro de trazo."
    )
    ancho_cm: float = Field(gt=0, le=500)
    peralte_cm: float = Field(gt=0, le=500, description="Peralte; en un castillo, el largo de la sección.")
    longitud_m: float | None = Field(
        default=None, gt=0, le=30, description="Alto (castillo) o largo (pieza) en METROS; no aplica en ml."
    )
    lados_cimbra: int = Field(default=0, ge=0, le=4)
    varillas: list[VarillaPeticion] = Field(default_factory=list, max_length=20)
    armex: ArmexPeticion | None = None
    anillos: list[ZonaDeAnilloPeticion] = Field(default_factory=list, max_length=10)
    gancho_cm: float = Field(default=10.0, ge=0, le=100)
    recubrimiento_cm: float = Field(default=2.5, ge=0, le=50)
    factor_anillo: float = Field(default=1.0, gt=0, le=3)
    alambre_por_amarre_m: float = Field(default=0.3, ge=0, le=5)
    alambre_peso_kg_m: float = Field(default=0.0095, ge=0)
    alambre_kg_ml: float | None = Field(default=None, ge=0, description="Kg por ml del catálogo; vacío = por amarres.")
    cimbra: list[ConsumoDeCimbraPeticion] = Field(default_factory=list, max_length=20)
    cantidad: float = Field(default=1.0, gt=0, le=1_000_000)
    drivers: DriversDeRecetaPeticion = Field(default_factory=DriversDeRecetaPeticion)


class CorteDeLaVarilla(BaseModel):
    piezas: int
    modulo_m: float
    total_m: float
    alto_que_cubre_m: float
    necesario_m: float
    traslape_m: float
    puntas_m: float
    sobrante_m: float
    excede_maximo: bool
    cubre_completo: bool


class ArmexDeLaReceta(BaseModel):
    clave: str
    largo_pieza_m: float
    ml: float
    piezas_comerciales: float
    kg: float | None
    traslape_m: float
    puntas_m: float
    corte: CorteDeLaVarilla | None


class VarillaDeLaReceta(BaseModel):
    clave: str
    etiqueta: str
    numero: int
    varillas: int
    largo_pieza_m: float
    diametro_m: float
    traslape_m: float
    puntas_m: float
    ml: float
    piezas_comerciales: float
    kg: float | None
    corte: CorteDeLaVarilla | None


class ZonaDeAnilloDeLaReceta(BaseModel):
    clave: str | None
    len_cm: float | None
    sep_cm: float
    largo_m: float
    pza: float
    kg: float


class AnillosDeLaReceta(BaseModel):
    largo_anillo_m: float
    pza: float
    kg: float
    zonas: list[ZonaDeAnilloDeLaReceta]


class AlambreDeLaReceta(BaseModel):
    kg: float
    kg_por_ml: float | None


class ConsumoDeCimbraDeLaReceta(BaseModel):
    clave: str
    cantidad: float


class CimbraDeLaReceta(BaseModel):
    m2: float
    lados: int
    consumos: list[ConsumoDeCimbraDeLaReceta]


class DesperdicioDeLaReceta(BaseModel):
    sobrante_de_corte_m: float
    traslape_m: float
    puntas_m: float
    desperdicio_acero_pct: float


class TotalDeLaReceta(BaseModel):
    clave: str
    unidad: str
    cantidad_exacta: float
    cantidad_a_comprar: float


class RecetaDeAceroCalculada(BaseModel):
    forma: str
    unidad: str
    longitud_m: float
    cantidad: float
    armex: ArmexDeLaReceta | None
    varillas: list[VarillaDeLaReceta]
    anillos: AnillosDeLaReceta | None
    alambre: AlambreDeLaReceta
    cimbra: CimbraDeLaReceta
    acero_kg: float
    acero_kg_completo: bool
    desperdicio: DesperdicioDeLaReceta
    totales: list[TotalDeLaReceta]
    drivers: DriversDeRecetaPeticion
    advertencias: list[str]


def _entrada(p: RecetaDeAceroPeticion) -> EntradaRecetaAcero:
    return EntradaRecetaAcero(
        forma=p.forma,
        ancho_cm=p.ancho_cm,
        peralte_cm=p.peralte_cm,
        longitud_m=p.longitud_m,
        lados_cimbra=p.lados_cimbra,
        varillas=[
            GrupoDeVarillas(v.cantidad, Varilla(v.clave, v.numero, v.largo_m, v.peso_kg_m), v.etiqueta)
            for v in p.varillas
        ],
        armex=Armex(p.armex.clave, p.armex.largo_m, p.armex.peso_kg_m) if p.armex else None,
        anillos=[ZonaDeAnillo(z.sep_cm, z.peso_kg_m, z.len_cm, z.clave) for z in p.anillos],
        gancho_cm=p.gancho_cm,
        recubrimiento_cm=p.recubrimiento_cm,
        factor_anillo=p.factor_anillo,
        alambre_por_amarre_m=p.alambre_por_amarre_m,
        alambre_peso_kg_m=p.alambre_peso_kg_m,
        alambre_kg_ml=p.alambre_kg_ml,
        cimbra=[ConsumoDeCimbra(c.clave, c.por_ml, c.por_m2) for c in p.cimbra],
        cantidad=p.cantidad,
        drivers=DriversDeReceta(**p.drivers.model_dump()),
    )


@router.post(
    "/biblioteca-de-elementos/receta-acero/calcular",
    response_model=RecetaDeAceroCalculada,
    summary="Calcula la receta del acero de un elemento lineal o de pieza (solo cálculo)",
)
async def calcular_receta(peticion: RecetaDeAceroPeticion) -> dict[str, Any]:
    try:
        return calcular_receta_acero(_entrada(peticion))
    except ErrorDeRecetaAcero as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
