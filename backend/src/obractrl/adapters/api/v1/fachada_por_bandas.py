"""La fachada de un plano por bandas de altura (F1, 2026-11-19): los m² de cara exterior de los muros reales, en la banda baja (0 a 3.00),
la media («+3.00») y el resto, según sus zonas de losa y puntos de nivel exterior. Solo lee (todos los roles que ven el plano); no cobra ni
cambia nada guardado. Controladores delgados: las reglas viven en el dominio."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import ConsultarFachadaPorBandasDep

router = APIRouter(tags=["fachada"])


class BandaDeFachada(BaseModel):
    banda: Literal["baja", "media", "resto"]
    nombre: str
    desde_m: Decimal = Field(description="Altura sobre el suelo de la cara exterior donde empieza la banda.")
    hasta_m: Decimal | None = Field(description="Donde termina; `null` en «el resto».")
    bruto_m2: Decimal
    vanos_m2: Decimal = Field(description="Lo que descuentan los vanos que caen en esta banda.")
    neto_m2: Decimal


class FachadaDeMuro(BaseModel):
    trazo_id: UUID
    origen_de_caras: Literal["partes_del_muro", "zona_de_losa", "ubicacion"] = Field(
        description="De dónde salió cuál cara es exterior: las partes con caras del muro, su zona de losa o su ubicación."
    )
    ubicacion: str | None
    bandas: list[BandaDeFachada]
    neto_m2: Decimal


class MuroSinCaraExterior(BaseModel):
    trazo_id: UUID
    motivo: str


class FachadaPorBandasRespuesta(BaseModel):
    plano_id: UUID
    obra_id: UUID | None
    limite_bajo_m: Decimal = Field(description="Donde termina la banda baja (3.00 m, decisión F1).")
    limite_alto_m: Decimal = Field(description="Donde termina la franja «+3.00» (4.20 m, decisión F1).")
    bandas: list[BandaDeFachada] = Field(description="El total del plano: cada m² cae en una sola banda.")
    bruto_m2: Decimal
    vanos_m2: Decimal
    neto_m2: Decimal
    muros: list[FachadaDeMuro]
    muros_sin_cara_exterior: list[MuroSinCaraExterior] = Field(description="Muros que no se cuentan porque no dicen cuál cara es exterior.")


@router.get(
    "/planos/{plano_id}/fachada-por-bandas",
    response_model=FachadaPorBandasRespuesta,
    summary="Los m² de fachada del plano por banda de altura (0 a 3.00, «+3.00» de 3.00 a 4.20, resto)",
    responses={404: {"description": "El plano no existe o está fuera de tu alcance."}, 422: {"description": "Los límites de las bandas no valen."}},
)
async def fachada_por_bandas(plano_id: UUID, caso_uso: ConsultarFachadaPorBandasDep) -> FachadaPorBandasRespuesta:
    return FachadaPorBandasRespuesta(**await caso_uso.del_plano(plano_id))
