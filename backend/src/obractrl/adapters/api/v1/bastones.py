"""Definición, cálculo y propuestas de los bastones por longitud de trazo (Ola 4, 4D).

El cálculo vive en el dominio (`baston`); aquí solo se valida la entrada y se devuelve el resultado. `calcular` no guarda nada. Los
conceptos nuevos (escalones que el catálogo no trae) y las versiones se **proponen** (Costos o Control de obra) y solo Control de obra
los autoriza, con las mismas rutas de autorización de las propuestas de estructura. Estas rutas cuelgan de
`/biblioteca-de-elementos/baston/…` y se registran **antes** que las de la biblioteca. Controladores delgados.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import GestionarPropuestasDeBastonDep
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.adapters.api.v1.elementos_de_estructura import (
    PropuestaDeEstructura,
    ResultadoDeProponer,
)
from obractrl.adapters.api.v1.elementos_de_estructura import (
    _a_propuesta as a_propuesta,
)
from obractrl.domain.cuantificacion.baston import (
    ElementoDeBastonNoEncontrado,
    EntradaDeBaston,
    ErrorDeBaston,
    calcular_baston,
    definicion_de,
)
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["biblioteca de elementos"])

ROLES_QUE_PROPONEN = (Rol.CONTROL_OBRA, Rol.COSTOS)
Marca = Literal["=", "≈", "≠", "solo_catalogo", "solo_elemento"]
Escalon = Literal["exacto", "mayor", "sin_escalon"]


class ClaveYNombre(BaseModel):
    clave: str
    nombre: str


class VarillaDeBaston(BaseModel):
    numero: int
    clave: str
    nombre: str
    peso_kg_m: float


class EscalonDelCatalogo(BaseModel):
    clave: str
    largo_m: float
    sep_cm: float
    varilla_pza_por_ml: float
    alambre_kg_por_ml: float


class PendienteDelBaston(BaseModel):
    clave: str
    texto: str


class ParametrosDelBaston(BaseModel):
    varilla_numero: int
    sep_cm: float
    largo_cm: float
    puntas_cm: float
    traslape_diametros: float
    trazo_m: float


class DefinicionDelBaston(BaseModel):
    clave: str
    nombre: str
    tipo: str
    se_mide_por: str
    categoria: ClaveYNombre
    subcategoria: ClaveYNombre
    parametros_por_defecto: ParametrosDelBaston
    varillas: list[VarillaDeBaston]
    modulos_de_corte_m: list[float]
    escalones: list[EscalonDelCatalogo]
    fuente: str
    pendientes: list[PendienteDelBaston]


class CalculoDelBastonPeticion(BaseModel):
    trazo_m: float = Field(default=1.0, gt=0, le=1_000_000, description="Longitud de trazo a cubrir, en metros.")
    varilla_numero: int = Field(default=3, ge=3, le=6, description="3 = 3/8, 4 = 1/2, 5 = 5/8, 6 = 3/4.")
    sep_cm: float = Field(default=25.0, ge=5, le=200, description="Cada cuánto va un bastón.")
    largo_cm: float = Field(default=120.0, ge=10, le=3000, description="Largo del bastón.")
    puntas_cm: float = Field(default=0.0, ge=0, le=100, description="Anclaje adicional; 0 = sin gancho (Q28).")
    traslape_diametros: float = Field(default=40.0, ge=0, le=100, description="Traslape entre las piezas de un bastón largo (Q22).")


class VarillaCalculada(BaseModel):
    clave: str
    numero: int
    nombre: str
    peso_kg_m: float
    largo_m: float


class CorteDelBaston(BaseModel):
    piezas_por_baston: int
    modulo_m: float
    material_por_baston_m: float
    traslape_m: float
    puntas_m: float
    necesario_m: float
    sobrante_por_baston_m: float
    piezas_por_varilla: int
    excede_maximo: bool


class PlanAjustado(BaseModel):
    corte: CorteDelBaston
    bastones: int
    varillas: int = Field(description="Varillas de 12 m a comprar.")
    material_m: float
    kg: float
    sobra_m: float


class PlanExacto(BaseModel):
    bastones: int
    varillas: int
    material_m: float
    kg: float
    sobra_m: float


class PagoDelBaston(BaseModel):
    modo: Literal["pieza"]
    unidad: str
    cantidad: int
    texto: str


class ConceptoDelBaston(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    estado: Literal["catalogo", "propuesto"]
    clave_provisional: bool
    escalon: Escalon
    largo_m: float
    sep_cm: float


class FilaDeConciliacion(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    catalogo: float | None
    elemento: float | None
    diferencia: float | None
    diferencia_pct: float | None
    marca: Marca


class ManoDeObraDelCatalogo(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    cantidad: float
    costo: float | None


class ConceptoDeConciliacion(BaseModel):
    clave: str
    descripcion: str
    unidad: str


class ConciliacionDelBaston(BaseModel):
    concepto: ConceptoDeConciliacion
    sobre: str
    filas: list[FilaDeConciliacion]
    mano_de_obra: list[ManoDeObraDelCatalogo]
    resumen: dict[str, int]
    coincide: bool
    fuente_de_las_filas: list[str]
    avisos: list[str]


class CalculoDelBaston(BaseModel):
    clave: str
    nombre: str
    unidad: str
    trazo_m: float
    varilla: VarillaCalculada
    parametros: dict[str, float]
    bastones_por_metro: float
    ajustado: PlanAjustado = Field(description="El corte ajustado a módulos: lo que se paga (Q28, lo más conservador).")
    exacto: PlanExacto = Field(description="El corte exacto del mockup, solo como referencia.")
    varillas_por_metro: float
    pago: PagoDelBaston
    concepto: ConceptoDelBaston
    escalon: Escalon
    conciliacion: list[ConciliacionDelBaston]
    avisos: list[str]


_RESPUESTAS_DE_ELEMENTO = {404: {"description": "No hay un bastón con esa clave."}}
_PROPONEN = {**_RESPUESTAS_DE_ELEMENTO, 403: {"description": "Proponen Costos y Control de obra."}}


def _entrada(p: CalculoDelBastonPeticion) -> EntradaDeBaston:
    return EntradaDeBaston(
        trazo_m=p.trazo_m,
        varilla_numero=p.varilla_numero,
        sep_cm=p.sep_cm,
        largo_cm=p.largo_cm,
        puntas_cm=p.puntas_cm,
        traslape_diametros=p.traslape_diametros,
    )


@router.get(
    "/biblioteca-de-elementos/baston/{clave}",
    response_model=DefinicionDelBaston,
    summary="La ficha del bastón de la biblioteca: varillas, módulos de corte, escalones del catálogo y preguntas pendientes",
    responses=_RESPUESTAS_DE_ELEMENTO,
)
async def definicion_del_baston(clave: str) -> dict[str, Any]:
    try:
        return definicion_de(clave)
    except ElementoDeBastonNoEncontrado as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e


@router.post(
    "/biblioteca-de-elementos/baston/{clave}/calcular",
    response_model=CalculoDelBaston,
    summary="Calcula los bastones, varillas y kg de un trazo, el escalón del catálogo que los paga y su conciliación (solo cálculo)",
    responses={**_RESPUESTAS_DE_ELEMENTO, 422: {"description": "Un dato no vale."}},
)
async def calcular_el_baston(clave: str, peticion: CalculoDelBastonPeticion) -> dict[str, Any]:
    try:
        definicion_de(clave)
        return calcular_baston(_entrada(peticion))
    except ElementoDeBastonNoEncontrado as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    except ErrorDeBaston as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e


@router.get(
    "/biblioteca-de-elementos/baston/{clave}/propuestas",
    response_model=list[PropuestaDeEstructura],
    summary="Las versiones de concepto propuestas, autorizadas y rechazadas del bastón",
    responses=_RESPUESTAS_DE_ELEMENTO,
)
async def propuestas_del_baston(clave: str, caso_uso: GestionarPropuestasDeBastonDep) -> list[PropuestaDeEstructura]:
    return [a_propuesta(f) for f in await caso_uso.listar(clave)]


@router.post(
    "/biblioteca-de-elementos/baston/{clave}/propuestas/concepto-nuevo",
    response_model=ResultadoDeProponer,
    status_code=status.HTTP_201_CREATED,
    summary="Proponer el concepto nuevo del escalón que el catálogo no trae (clave provisional, sin destajo ni precio)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_PROPONEN))],
    responses={**_PROPONEN, 422: {"description": "El catálogo ya trae el escalón o un dato no vale."}},
)
async def proponer_concepto_nuevo(
    clave: str, peticion: CalculoDelBastonPeticion, ctx: ContextoActual, caso_uso: GestionarPropuestasDeBastonDep
) -> ResultadoDeProponer:
    try:
        r = await caso_uso.proponer_concepto_nuevo(clave, _entrada(peticion), usuario_id=ctx.usuario_id, rol=ctx.rol)
    except ErrorDeBaston as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    return ResultadoDeProponer(**r)


@router.post(
    "/biblioteca-de-elementos/baston/{clave}/propuestas/actualizar-apu",
    response_model=ResultadoDeProponer,
    status_code=status.HTTP_201_CREATED,
    summary="Confirmar el cálculo: proponer como nueva versión del escalón los coeficientes que difieren del catálogo",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_PROPONEN))],
    responses={**_PROPONEN, 422: {"description": "Un dato no vale."}},
)
async def proponer_actualizacion_de_apu(
    clave: str, peticion: CalculoDelBastonPeticion, ctx: ContextoActual, caso_uso: GestionarPropuestasDeBastonDep
) -> ResultadoDeProponer:
    try:
        r = await caso_uso.proponer_actualizacion_de_apu(clave, _entrada(peticion), usuario_id=ctx.usuario_id, rol=ctx.rol)
    except ErrorDeBaston as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    return ResultadoDeProponer(**r)
