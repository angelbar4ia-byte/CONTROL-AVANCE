"""Endpoints del flujo de cierre de actividad.

Spec §11.2 (Cierres) · §11.3 workflow C · §4 (validar ≠ autorizar).

Controladores delgados: validan el DTO, delegan en el caso de uso y mapean
el resultado. **Cero lógica de negocio aquí** (§12.11) — las reglas de
permisos y transición viven en `domain.cierres.reglas`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    AutorizarCierreDep,
    RechazarCierreDep,
    SolicitarCierreDep,
    ValidarCierreDep,
)
from obractrl.adapters.api.dependencias import ContextoActual, SesionRLS, exigir_rol
from obractrl.adapters.repos.cierres_sql import RepositorioCierresSQL
from obractrl.application.casos_uso.gestionar_cierre import (
    ComandoAutorizarCierre,
    ComandoRechazarCierre,
    ComandoSolicitarCierre,
    ComandoValidarCierre,
)
from obractrl.domain.cierres.reglas import SolicitudCierre
from obractrl.domain.shared.diccionario import EstatusSolicitudCierre, Rol

router = APIRouter(tags=["cierres"])

FiltroEstatus = Annotated[
    EstatusSolicitudCierre | None,
    Query(description="Filtra por estatus del flujo (§7.8)."),
]


class SolicitarCierrePeticion(BaseModel):
    """Solicitud de cierre de actividad (§6, §11.3 C.1)."""

    cantidad: Decimal = Field(ge=0, description="Cantidad que se cierra.")
    checklist: list[dict] = Field(min_length=1, description="Checklist obligatorio.")
    adjuntos: list[str] = Field(
        min_length=1, description="Evidencias ya subidas a R2 vía presigned URL."
    )


class ValidarCierrePeticion(BaseModel):
    comentario: str | None = Field(default=None, description="Comentario de Control de obra.")


class RechazarCierrePeticion(BaseModel):
    motivo: str = Field(min_length=1, description="Motivo obligatorio del rechazo.")


class CierreRespuesta(BaseModel):
    id: UUID
    actividad_id: UUID
    solicitada_por: UUID
    autorizada_por: UUID | None
    validada_por: UUID | None
    cantidad: Decimal
    monto: Decimal
    checklist: list[dict]
    adjuntos: list[str]
    comentarios: str | None
    estatus: str

    @classmethod
    def desde_dominio(cls, cierre_id: UUID, solicitud: SolicitudCierre) -> CierreRespuesta:
        return cls(
            id=cierre_id,
            actividad_id=UUID(solicitud.actividad_id),
            solicitada_por=UUID(solicitud.solicitada_por),
            autorizada_por=UUID(solicitud.autorizada_por) if solicitud.autorizada_por else None,
            validada_por=UUID(solicitud.validada_por) if solicitud.validada_por else None,
            cantidad=solicitud.cantidad,
            monto=solicitud.monto.monto,
            checklist=solicitud.checklist,
            adjuntos=solicitud.adjuntos,
            comentarios=solicitud.comentarios,
            estatus=solicitud.estatus.value,
        )

    @classmethod
    def desde_fila(cls, fila: dict) -> CierreRespuesta:
        return cls(
            id=fila["id"],
            actividad_id=fila["actividad_id"],
            solicitada_por=fila["solicitada_por"],
            autorizada_por=fila["autorizada_por"],
            validada_por=fila["validada_por"],
            cantidad=fila["cantidad"],
            monto=fila["monto"],
            checklist=fila["checklist"],
            adjuntos=fila["adjuntos"],
            comentarios=fila["comentarios"],
            estatus=fila["estatus"],
        )


@router.post(
    "/actividades/{actividad_id}/cierre",
    response_model=CierreRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Solicitar el cierre de una actividad",
    dependencies=[Depends(exigir_rol(Rol.RESIDENTE))],
    responses={
        404: {"description": "La actividad no existe o está fuera de tu alcance."},
        422: {"description": "Falta checklist o evidencias (§6)."},
    },
)
async def solicitar_cierre(
    actividad_id: UUID,
    peticion: SolicitarCierrePeticion,
    ctx: ContextoActual,
    caso_uso: SolicitarCierreDep,
) -> CierreRespuesta:
    """El Residente solicita el cierre de una actividad (§11.3 C.1)."""
    creada = await caso_uso.ejecutar(
        ComandoSolicitarCierre(
            actividad_id=actividad_id,
            residente_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
            cantidad=peticion.cantidad,
            checklist=peticion.checklist,
            adjuntos=peticion.adjuntos,
        )
    )
    return CierreRespuesta.desde_dominio(creada.id, creada.solicitud)


@router.post(
    "/cierres/{cierre_id}/autorizar",
    response_model=CierreRespuesta,
    summary="Autorizar un cierre (cierra la actividad)",
    dependencies=[Depends(exigir_rol(Rol.SUPERVISOR))],
    responses={
        404: {"description": "La solicitud no existe o está fuera de tu alcance."},
        409: {"description": "Transición de cierre no permitida."},
    },
)
async def autorizar_cierre(
    cierre_id: UUID, ctx: ContextoActual, caso_uso: AutorizarCierreDep
) -> CierreRespuesta:
    """El Supervisor **autoriza**: cierra la actividad (§4, §11.3 C.2)."""
    solicitud = await caso_uso.ejecutar(
        ComandoAutorizarCierre(cierre_id=cierre_id, usuario_id=ctx.usuario_id, rol=Rol(ctx.rol))
    )
    return CierreRespuesta.desde_dominio(cierre_id, solicitud)


@router.post(
    "/cierres/{cierre_id}/validar",
    response_model=CierreRespuesta,
    summary="Validar un cierre (habilita para estimación)",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA))],
    responses={
        404: {"description": "La solicitud no existe o está fuera de tu alcance."},
        409: {"description": "Transición de cierre no permitida."},
    },
)
async def validar_cierre(
    cierre_id: UUID,
    peticion: ValidarCierrePeticion,
    ctx: ContextoActual,
    caso_uso: ValidarCierreDep,
) -> CierreRespuesta:
    """Control de obra **valida y comenta**, no autoriza (§4, §11.3 C.3)."""
    solicitud = await caso_uso.ejecutar(
        ComandoValidarCierre(
            cierre_id=cierre_id,
            usuario_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
            comentario=peticion.comentario,
        )
    )
    return CierreRespuesta.desde_dominio(cierre_id, solicitud)


@router.post(
    "/cierres/{cierre_id}/rechazar",
    response_model=CierreRespuesta,
    summary="Rechazar una solicitud de cierre",
    dependencies=[Depends(exigir_rol(Rol.SUPERVISOR, Rol.CONTROL_OBRA))],
    responses={
        404: {"description": "La solicitud no existe o está fuera de tu alcance."},
        409: {"description": "Transición de cierre no permitida."},
    },
)
async def rechazar_cierre(
    cierre_id: UUID,
    peticion: RechazarCierrePeticion,
    ctx: ContextoActual,
    caso_uso: RechazarCierreDep,
) -> CierreRespuesta:
    """Supervisor o Control de obra rechazan la solicitud (§11.2)."""
    solicitud = await caso_uso.ejecutar(
        ComandoRechazarCierre(
            cierre_id=cierre_id,
            usuario_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
            motivo=peticion.motivo,
        )
    )
    return CierreRespuesta.desde_dominio(cierre_id, solicitud)


@router.get(
    "/cierres",
    response_model=list[CierreRespuesta],
    summary="Bandeja de cierres por rol",
)
async def listar_cierres(
    sesion: SesionRLS, estatus: FiltroEstatus = None
) -> list[CierreRespuesta]:
    """Bandeja de solicitudes visibles para el rol actual.

    Es una lectura simple sin orquestación de dominio —como `GET /me`
    (`adapters/api/v1/identidad.py`)— así que consulta el repo directo, sin
    caso de uso: RLS ya acota el alcance (§12.4).
    """
    repo = RepositorioCierresSQL(sesion)
    filas = await repo.listar(estatus=estatus.value if estatus else None)
    return [CierreRespuesta.desde_fila(fila) for fila in filas]
