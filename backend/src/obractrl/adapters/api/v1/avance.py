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

from obractrl.adapters.api.casos_uso import CapturarAvanceDep
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.application.casos_uso.capturar_avance import ComandoCapturarAvance
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["avance"])


class CapturaAvancePeticion(BaseModel):
    """Captura de avance (§6).

    Las mismas reglas se reflejan en el cliente para UX y se aplican de forma
    autoritativa en el servidor (§11.1).
    """

    cant_ejecutada: Decimal = Field(
        ge=0,
        description=(
            "Puede exceder la programada: registrar nunca se bloquea. Lo que "
            "pase de lo programado queda como excedente pendiente de "
            "comprobación y validación de Control de obra."
        ),
    )
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
    cant_excedente: Decimal = Field(
        description=(
            "Lo ejecutado por encima de lo programado que aún no se decidió. "
            "Va a comprobación y validación (`GET /comprobaciones`)."
        )
    )


@router.patch(
    "/actividades/{actividad_id}/avance",
    response_model=AvanceRespuesta,
    status_code=status.HTTP_200_OK,
    summary="Capturar avance de una actividad",
    dependencies=[Depends(exigir_rol(Rol.RESIDENTE))],
    responses={
        404: {"description": "La actividad no existe o está fuera de tu alcance."},
        409: {"description": "Actividad bloqueada por una incidencia que detiene."},
        422: {"description": "Violación de una regla de captura (§6)."},
    },
)
async def capturar_avance(
    actividad_id: UUID,
    peticion: CapturaAvancePeticion,
    ctx: ContextoActual,
    caso_uso: CapturarAvanceDep,
) -> AvanceRespuesta:
    """Captura el avance ejecutado de una actividad (§11.3 B) — **ruta web**.

    El móvil **no** pasa por aquí: su conciliación offline escribe directo a
    Postgres vía PowerSync, con RLS como única frontera (§11.3 B). Allá el
    total lo deriva el trigger `app.registro_avance_agregar` (migración 0017)
    a partir de la bitácora `registro_avance`; acá lo escribe este caso de
    uso. Las reglas del §6 son las mismas en ambas rutas porque las garantiza
    también la BD (CHECKs de la migración 0007; desde la 0066 lo ejecutado de
    más ya no se rechaza en ninguna de las dos).
    """
    resultado = await caso_uso.ejecutar(
        ComandoCapturarAvance(
            actividad_id=actividad_id,
            usuario_id=ctx.usuario_id,
            cant_ejecutada=peticion.cant_ejecutada,
            cant_programada=peticion.cant_programada,
            fecha=peticion.fecha,
            evidencias=tuple(peticion.evidencias),
        )
    )
    return AvanceRespuesta(
        actividad_id=actividad_id,
        cant_base=resultado.cant_base,
        cant_programada=resultado.cant_programada,
        cant_ejecutada=resultado.cant_ejecutada,
        avance_pct=resultado.avance.pct,
        estatus=resultado.estatus.value,
        cant_excedente=resultado.cant_excedente,
    )

