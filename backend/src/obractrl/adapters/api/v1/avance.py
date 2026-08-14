"""Endpoints de ejecución y avance.

Spec §11.2 (Ejecución · Avance) · §11.3 workflow B.

Controlador delgado: valida el DTO, delega en el caso de uso y mapea el
resultado. **Cero lógica de negocio aquí** (§12.11) — las reglas del §6 viven
en `domain.avance.reglas`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.dependencias import ContextoActual, SesionRLS, exigir_rol
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["avance"])


class CapturaAvancePeticion(BaseModel):
    """Captura de avance (§6).

    Las mismas reglas se reflejan en el cliente para UX y se aplican de forma
    autoritativa en el servidor (§11.1).
    """

    cant_ejecutada: Decimal = Field(ge=0, description="No puede exceder la programada.")
    cant_programada: Decimal | None = Field(
        default=None,
        ge=0,
        description="Si se envía, se revalida contra cant_base × 1.2.",
    )
    fecha: date | None = Field(
        default=None, description="Fecha de la captura. Por defecto, hoy."
    )
    evidencias: list[str] = Field(
        default_factory=list,
        description="URLs ya subidas a R2 vía presigned URL (§11.2).",
    )


class AvanceRespuesta(BaseModel):
    actividad_id: UUID
    cant_base: Decimal
    cant_programada: Decimal
    cant_ejecutada: Decimal
    avance_pct: Decimal
    estatus: str


@router.patch(
    "/actividades/{actividad_id}/avance",
    response_model=AvanceRespuesta,
    status_code=status.HTTP_200_OK,
    summary="Capturar avance de una actividad",
    dependencies=[Depends(exigir_rol(Rol.RESIDENTE))],
    responses={
        422: {"description": "Violación de una regla de captura (§6)."},
        409: {"description": "Actividad bloqueada por una incidencia que detiene."},
    },
)
async def capturar_avance(
    actividad_id: UUID,
    peticion: CapturaAvancePeticion,
    ctx: ContextoActual,
    sesion: SesionRLS,
) -> AvanceRespuesta:
    """Captura el avance ejecutado de una actividad (§11.3 B).

    La ruta web y la conciliación offline del móvil pasan por el mismo caso de
    uso, para que ambas apliquen exactamente las mismas reglas.
    """
    raise NotImplementedError(
        "Pendiente: cablear ComandoCapturarAvance con el repositorio SQLModel. "
        "El caso de uso y las reglas de dominio ya están en "
        "application/casos_uso/capturar_avance.py y domain/avance/reglas.py."
    )
