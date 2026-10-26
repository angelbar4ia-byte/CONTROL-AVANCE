"""Desviaciones de una obra y la captura de su causa (cerebro MODELO.md §5g).

El cuantificador escribe una desviación cuando lo medido en el plano se aparta de
la cantidad base; aquí se ven y se les pone causa. Las cuatro reglas de captura
del cerebro se respetan tal cual: la detección no depende de nadie, «sin causa»
es un estado válido (la lista trae las desviaciones sin causa igual que las
demás), y la causa se agrega **después** y sin penalizar —también se puede
corregir—.

Lectura y captura son de quien ve la obra (RLS acota el alcance): quien sabe por
qué se desvió es quien está cerca del trabajo, no un rol en particular.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    CapturarCausaDeDesviacionDep,
    ConsultarDesviacionesDep,
)
from obractrl.adapters.api.dependencias import ContextoActual
from obractrl.adapters.api.idempotencia import Idempotencia
from obractrl.application.casos_uso.gestionar_desviaciones import ComandoCapturarCausa
from obractrl.domain.shared.diccionario import CausaDesviacion

router = APIRouter(tags=["desviaciones"])


class DesviacionRespuesta(BaseModel):
    id: UUID
    obra_id: UUID
    tipo_nodo: str = Field(description="`insumo` o `concepto`: dónde se detectó.")
    nodo_clave: str | None = None
    nodo_descripcion: str | None = None
    tipo: str = Field(description="`precio` o `consumo`: los dos factores, nunca sumados.")
    monto: Decimal = Field(description="El efecto en dinero de este factor, solamente.")
    cantidad_plan: Decimal | None = None
    cantidad_real: Decimal | None = None
    precio_plan: Decimal | None = None
    precio_real: Decimal | None = None
    causa: str | None = Field(
        default=None, description="`null` es «sin causa»: un estado válido, no un dato faltante."
    )
    causa_capturada_en: datetime | None = None
    causa_capturada_por: str | None = None
    detectada_en: datetime
    causas_posibles: list[str] = Field(
        description="Las causas del vocabulario controlado que caben en el factor de esta fila."
    )


class CausaPeticion(BaseModel):
    causa: CausaDesviacion


@router.get(
    "/obras/{obra_id}/desviaciones",
    response_model=list[DesviacionRespuesta],
    summary="Desviaciones de una obra, con o sin causa",
    responses={404: {"description": "La obra no existe o está fuera de tu alcance."}},
)
async def listar_desviaciones(
    obra_id: UUID, caso_uso: ConsultarDesviacionesDep
) -> list[DesviacionRespuesta]:
    """Las más recientes primero. Las que no tienen causa salen igual."""
    return [DesviacionRespuesta(**fila) for fila in await caso_uso.ejecutar(obra_id)]


@router.put(
    "/desviaciones/{desviacion_id}/causa",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Capturar (o corregir) la causa de una desviación",
    dependencies=[Idempotencia],
    responses={
        404: {"description": "La desviación no existe o está fuera de tu alcance."},
        422: {"description": "La causa es del otro factor: no cabe en esta desviación."},
    },
)
async def capturar_causa(
    desviacion_id: UUID,
    peticion: CausaPeticion,
    caso_uso: CapturarCausaDeDesviacionDep,
    ctx: ContextoActual,
) -> None:
    """La causa se agrega después de detectar la desviación, sin penalizar, y se
    puede corregir. Debe ser del mismo factor (`precio` o `consumo`) que la fila."""
    await caso_uso.ejecutar(
        ComandoCapturarCausa(
            desviacion_id=desviacion_id,
            causa=peticion.causa,
            usuario_id=ctx.usuario_id,
        )
    )
