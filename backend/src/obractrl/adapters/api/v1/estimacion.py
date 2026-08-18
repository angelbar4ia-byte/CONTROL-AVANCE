"""Endpoints de estimación semanal.

Spec §11.2 (Estimación) · §11.3 workflow E.

Controladores delgados: validan el DTO, delegan en el caso de uso y mapean
el resultado. **Cero lógica de negocio aquí** (§12.11) — las reglas de
permisos, selección de actividades y transición viven en
`domain.estimacion.reglas`.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    EnviarEstimacionDep,
    GenerarEstimacionDep,
    ValidarEstimacionDep,
)
from obractrl.adapters.api.dependencias import ContextoActual, SesionRLS, exigir_rol
from obractrl.adapters.api.idempotencia import Idempotencia
from obractrl.adapters.repos.estimaciones_sql import RepositorioEstimacionesSQL
from obractrl.application.casos_uso.gestionar_estimacion import (
    ComandoEnviarEstimacion,
    ComandoGenerarEstimacion,
    ComandoValidarEstimacion,
    EstimacionCreada,
)
from obractrl.domain.estimacion.reglas import Estimacion
from obractrl.domain.shared.diccionario import ModoPago, Rol

router = APIRouter(tags=["estimacion"])


class GenerarEstimacionPeticion(BaseModel):
    """Genera la estimación de la semana activa (§11.3 E.1).

    ``modo`` selecciona qué actividades entran: solo las que se pagan de esa
    forma (`actividad.modo_pago`, §6).
    """

    modo: ModoPago
    origen_erp: bool = Field(default=False, description="Metadato de origen (§3.2).")


class EstimacionRespuesta(BaseModel):
    id: UUID
    obra_id: UUID
    folio: str | None
    semana: int
    anio: int
    modo: str
    estatus: str
    monto_total: Decimal
    origen_erp: bool
    creada_por: UUID | None
    validada_por: UUID | None
    n_conceptos: int | None = Field(
        default=None, description="Solo presente justo al generar (§11.3 E.2)."
    )

    @classmethod
    def desde_dominio(cls, estimacion_id: UUID, estimacion: Estimacion) -> EstimacionRespuesta:
        return cls(
            id=estimacion_id,
            obra_id=UUID(estimacion.obra_id),
            folio=str(estimacion.folio) if estimacion.folio else None,
            semana=estimacion.semana,
            anio=estimacion.anio,
            modo=estimacion.modo.value,
            estatus=estimacion.estatus.value,
            monto_total=estimacion.monto_total.monto,
            origen_erp=estimacion.origen_erp,
            creada_por=UUID(estimacion.creada_por) if estimacion.creada_por else None,
            validada_por=UUID(estimacion.validada_por) if estimacion.validada_por else None,
            n_conceptos=len(estimacion.conceptos),
        )

    @classmethod
    def desde_fila(cls, fila: dict) -> EstimacionRespuesta:
        return cls(
            id=fila["id"],
            obra_id=fila["obra_id"],
            folio=fila["folio"],
            semana=fila["semana"],
            anio=fila["anio"],
            modo=fila["modo"],
            estatus=fila["estatus"],
            monto_total=fila["monto_total"],
            origen_erp=fila["origen_erp"],
            creada_por=fila["creada_por"],
            validada_por=fila["validada_por"],
        )


def _resultado(creada: EstimacionCreada) -> EstimacionRespuesta:
    return EstimacionRespuesta.desde_dominio(creada.id, creada.estimacion)


@router.post(
    "/obras/{obra_id}/estimaciones",
    response_model=EstimacionRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Generar la estimación de la semana activa",
    dependencies=[Depends(exigir_rol(Rol.RESIDENTE, Rol.SUPERVISOR)), Idempotencia],
    responses={
        409: {
            "description": (
                "No hay ancla de semana configurada (§3.1), o no hay "
                "actividades validadas para ese modo en la semana."
            )
        },
    },
)
async def generar_estimacion(
    obra_id: UUID,
    peticion: GenerarEstimacionPeticion,
    ctx: ContextoActual,
    caso_uso: GenerarEstimacionDep,
) -> EstimacionRespuesta:
    """Residente o Supervisor generan la estimación (§11.3 E.1-2)."""
    creada = await caso_uso.ejecutar(
        ComandoGenerarEstimacion(
            obra_id=obra_id,
            modo=peticion.modo,
            usuario_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
            origen_erp=peticion.origen_erp,
        )
    )
    return _resultado(creada)


@router.patch(
    "/estimaciones/{estimacion_id}",
    response_model=EstimacionRespuesta,
    summary="Enviar una estimación",
    dependencies=[Depends(exigir_rol(Rol.RESIDENTE, Rol.SUPERVISOR)), Idempotencia],
    responses={
        404: {"description": "La estimación no existe o está fuera de tu alcance."},
        409: {"description": "Transición de estimación no permitida."},
    },
)
async def enviar_estimacion(
    estimacion_id: UUID, ctx: ContextoActual, caso_uso: EnviarEstimacionDep
) -> EstimacionRespuesta:
    """Residente o Supervisor envían la estimación (§11.3 E.3)."""
    fila = await caso_uso.ejecutar(
        ComandoEnviarEstimacion(
            estimacion_id=estimacion_id, usuario_id=ctx.usuario_id, rol=Rol(ctx.rol)
        )
    )
    return EstimacionRespuesta.desde_fila(fila)


@router.post(
    "/estimaciones/{estimacion_id}/validar",
    response_model=EstimacionRespuesta,
    summary="Validar una estimación (bloquea el periodo)",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA)), Idempotencia],
    responses={
        404: {"description": "La estimación no existe o está fuera de tu alcance."},
        409: {"description": "Transición de estimación no permitida."},
    },
)
async def validar_estimacion(
    estimacion_id: UUID, ctx: ContextoActual, caso_uso: ValidarEstimacionDep
) -> EstimacionRespuesta:
    """Control de obra valida la estimación (§11.3 E.4)."""
    fila = await caso_uso.ejecutar(
        ComandoValidarEstimacion(
            estimacion_id=estimacion_id, usuario_id=ctx.usuario_id, rol=Rol(ctx.rol)
        )
    )
    return EstimacionRespuesta.desde_fila(fila)


@router.get(
    "/obras/{obra_id}/estimaciones",
    response_model=list[EstimacionRespuesta],
    summary="Bandeja de estimaciones de una obra",
)
async def listar_estimaciones(obra_id: UUID, sesion: SesionRLS) -> list[EstimacionRespuesta]:
    """Lectura simple sin orquestación de dominio —como `GET /cierres`
    (`adapters/api/v1/cierres.py`)— así que consulta el repo directo: RLS ya
    acota el alcance (§12.4)."""
    repo = RepositorioEstimacionesSQL(sesion)
    filas = await repo.listar(obra_id)
    return [EstimacionRespuesta.desde_fila(fila) for fila in filas]
