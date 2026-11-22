"""El muro de cimentación con cotas de desplante (Fase 4b): cimientos de la zona y su cálculo.

- **Zona** (`/zonas-de-losa/{zona_id}/cimientos`): los muros de cimentación de piedra (CIM-01010) medidos sobre una línea del plano con su cota de desplante (tecleada o de un
  punto de nivel exterior), su corona (tecleada o, sin ella, el arranque de la cadena de desplante: piso de la zona − 20 cm) y su espacio; su **cálculo** con lo que hay en el plano y la base. Todos los roles que ven el plano leen;
  **solo Control de obra escribe** (lo exige también RLS). Se pagan con el concepto existente MCT-01011 (m³): no hay propuesta de concepto nuevo.

El cálculo vive en el dominio (`cimiento`, que reutiliza el muro de cimentación); controladores delgados.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import GestionarCimientosDep
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.adapters.api.v1.losas import (
    ConceptoDeLaFicha,
    PendienteDeLaLosa,
    ResolucionDelConcepto,
)
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["cimientos"])

ROLES_QUE_EDITAN = (Rol.CONTROL_OBRA,)
ROLES_QUE_LEEN = (Rol.RESIDENTE, Rol.SUPERVISOR, Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE, Rol.COSTOS)
_422 = {422: {"description": "Una cota, la línea, el punto de nivel, el espacio o un parámetro no valen, o la línea ya mide otro cimiento."}}


class CimientoDeLaZonaPeticion(BaseModel):
    elemento_clave: Literal["CIM-01010"] = "CIM-01010"
    trazo_id: UUID = Field(description="La línea del plano que mide el cimiento: su longitud (con la escala) se deriva al calcular. Una línea mide un solo cimiento.")
    cota_desplante_m: float | None = Field(default=None, ge=-30, le=100, description="Cota del fondo del cimiento (relativa al piso terminado de PB = 0); manda sobre el punto de nivel.")
    punto_nivel_id: UUID | None = Field(default=None, description="Un punto de nivel exterior del plano cuya cota es la del desplante (medición derivada).")
    cota_corona_m: float | None = Field(default=None, ge=-30, le=100, description="Cota de la corona; sin ella vale el arranque de la cadena de desplante (piso de la zona − peralte de la cadena, 20 cm). Una cota tecleada manda.")
    caras: Literal[1, 2] = Field(default=1, description="Caras inclinadas del muro: 1 (cimiento de lindero) o 2 (simétrico).")
    dentellon: bool = Field(default=False, description="Dentellón opcional, desde 2.00 m de altura.")
    espacio_id: UUID | None = Field(default=None, description="El espacio donde está el cimiento (0143); `null` = sin espacio (no se escribe en ninguna partida).")


class CimientoDeLaZona(BaseModel):
    id: UUID
    zona_id: UUID
    elemento_clave: Literal["CIM-01010"]
    trazo_id: UUID
    cota_desplante_m: float | None
    punto_nivel_id: UUID | None
    cota_corona_m: float | None
    caras: int
    dentellon: bool
    espacio_id: UUID | None


class CotasDelCimiento(BaseModel):
    desplante_m: float
    corona_m: float
    altura_m: float = Field(description="Corona − desplante.")


class SeccionDelCimiento(BaseModel):
    alto_m: float
    corona_m: float
    base_m: float
    espesor_medio_m: float
    caras: int
    manual: bool


class EscarpioDelCimiento(BaseModel):
    minimo: float
    real: float | None
    cumple: bool


class DentellonDelCimiento(BaseModel):
    aplica: bool
    opcion: bool
    b2_m: float
    b1_m: float
    h_m: float


class InsumosDelCimiento(BaseModel):
    piedra_a_comprar_m3: float
    cemento_kg: float
    arena_m3: float
    agua_l: float


class ConceptoDelCimiento(BaseModel):
    parte: Literal["cimiento"]
    elemento_clave: str
    ref: str | None
    concepto: ConceptoDeLaFicha
    toma: list[str]
    cantidad: float = Field(description="m³ de mampostería, en la unidad del concepto.")
    unidad: str
    nota: str


class ConceptoDelCimientoPorEspacio(ConceptoDelCimiento):
    resolucion: ResolucionDelConcepto | None = None


class GrupoDelCimientoPorEspacio(BaseModel):
    espacio_id: str | None
    espacio_nombre: str | None = None
    conceptos: list[ConceptoDelCimientoPorEspacio]


class NoIncluyeDelCimiento(BaseModel):
    clave: str
    texto: str


class ManoDeObraDelCimiento(BaseModel):
    estado: Literal["sin_mano_de_obra"]
    nota: str


class CimientoCalculado(BaseModel):
    clave: str
    cotas: CotasDelCimiento
    longitud_m: float
    seccion: SeccionDelCimiento
    escarpio: EscarpioDelCimiento
    dentellon: DentellonDelCimiento
    volumen_m3_ml: float
    volumen_m3: float
    insumos: InsumosDelCimiento
    conceptos: list[ConceptoDelCimiento]
    por_espacio: list[GrupoDelCimientoPorEspacio]
    no_incluye: list[NoIncluyeDelCimiento]
    mano_de_obra: ManoDeObraDelCimiento
    advertencias: list[str]
    pendientes: list[PendienteDeLaLosa]


class OrigenDeLasCotasDelCimiento(BaseModel):
    desplante: Literal["explicita", "punto_de_nivel", "sin_cota"]
    corona: Literal["explicita", "cadena_de_desplante", "zona"] = Field(
        description="`cadena_de_desplante` (defecto desde C1): piso de la zona − peralte de la cadena de desplante. `zona` (piso de la zona) ya no se emite; se conserva por compatibilidad del contrato."
    )


class CimientoDeLaZonaCalculado(BaseModel):
    id: UUID
    trazo_id: UUID
    punto_nivel_id: UUID | None
    espacio_id: UUID | None
    origen_de_cotas: OrigenDeLasCotasDelCimiento
    longitud_m: float = Field(description="La de la línea del plano con la escala (derivada).")
    error: str | None = Field(description="Si un dato no vale (p. ej. la corona quedó por debajo del desplante): el motivo; sin él no hay cálculo.")
    calculo: CimientoCalculado | None


class ConceptoDeLosTotalesDeCimientos(BaseModel):
    concepto: ConceptoDeLaFicha
    unidad: str
    cantidad: float
    propuesta: None = None


class TotalesDeLosCimientos(BaseModel):
    longitud_m: float
    volumen_m3: float
    conceptos: list[ConceptoDeLosTotalesDeCimientos]


class ZonaDelCimiento(BaseModel):
    id: UUID
    plano_id: UUID
    nombre: str
    nivel: str | None
    cota_piso_m: float


class CalculoDeLosCimientosDeLaZona(BaseModel):
    zona: ZonaDelCimiento
    escala_definida: bool = Field(description="Sin escala calibrada se toma 1 unidad de plano = 1 m y no se escribe nada en las partidas.")
    cimientos: list[CimientoDeLaZonaCalculado]
    totales: TotalesDeLosCimientos
    por_espacio: list[GrupoDelCimientoPorEspacio]
    advertencias: list[str]


@router.get(
    "/zonas-de-losa/{zona_id}/cimientos",
    response_model=list[CimientoDeLaZona],
    summary="Los cimientos (muros de cimentación con cotas de desplante) de una zona de losa",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_LEEN))],
)
async def cimientos_de_la_zona(zona_id: UUID, caso_uso: GestionarCimientosDep) -> list[dict[str, Any]]:
    return await caso_uso.cimientos(zona_id)


@router.post(
    "/zonas-de-losa/{zona_id}/cimientos",
    response_model=CimientoDeLaZona,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar un cimiento a la zona, medido con una línea del plano (solo Control de obra)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
    responses=_422,
)
async def agregar_cimiento(zona_id: UUID, peticion: CimientoDeLaZonaPeticion, ctx: ContextoActual, caso_uso: GestionarCimientosDep) -> dict[str, Any]:
    return await caso_uso.agregar(zona_id, autor_id=ctx.usuario_id, **peticion.model_dump())


@router.put(
    "/cimientos-de-zona/{cimiento_id}",
    response_model=CimientoDeLaZona,
    summary="Cambiar un cimiento (solo Control de obra); sin `espacio_id` conserva su espacio",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
    responses=_422,
)
async def cambiar_cimiento(cimiento_id: UUID, peticion: CimientoDeLaZonaPeticion, caso_uso: GestionarCimientosDep) -> dict[str, Any]:
    datos = peticion.model_dump()
    asignado = datos.pop("espacio_id")
    espacio: dict[str, Any] = {"espacio_id": asignado} if "espacio_id" in peticion.model_fields_set else {}
    return await caso_uso.cambiar(cimiento_id, **datos, **espacio)


@router.delete(
    "/cimientos-de-zona/{cimiento_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Quitar un cimiento de la zona (solo Control de obra)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
)
async def quitar_cimiento(cimiento_id: UUID, caso_uso: GestionarCimientosDep) -> None:
    await caso_uso.quitar(cimiento_id)


@router.get(
    "/zonas-de-losa/{zona_id}/cimientos/calculo",
    response_model=CalculoDeLosCimientosDeLaZona,
    summary="El cálculo de los cimientos de una zona: altura de las cotas, volumen, insumos, concepto y lo que paga cada espacio",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_LEEN))],
)
async def calculo_de_los_cimientos(zona_id: UUID, caso_uso: GestionarCimientosDep) -> dict[str, Any]:
    return await caso_uso.calculo(zona_id)
