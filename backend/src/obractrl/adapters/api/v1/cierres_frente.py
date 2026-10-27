"""El cierre de un frente (migración 0071; cerebro D-515/D-522/D-261).

Un frente es un **nivel constructivo**. El residente solicita su cierre al 90 % de
avance, el supervisor lo aprueba y control de obra lo valida; rechaza el supervisor o
control, con motivo. Cerrado el frente, el residente ya no registra avance ahí (D-516);
para los demás roles sigue abierto hasta la entrega de la casa.

Controladores delgados: las reglas viven en `domain.cierres.frente`.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    AprobarCierreDeFrenteDep,
    ConsultarFrentesDeObraDep,
    RechazarCierreDeFrenteDep,
    SolicitarCierreDeFrenteDep,
    ValidarCierreDeFrenteDep,
)
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.adapters.api.idempotencia import Idempotencia
from obractrl.application.casos_uso.gestionar_cierre_de_frente import (
    ComandoAprobarCierreDeFrente,
    ComandoRechazarCierreDeFrente,
    ComandoSolicitarCierreDeFrente,
    ComandoValidarCierreDeFrente,
)
from obractrl.domain.cierres.frente import CierreDeFrente
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["cierres"])


class SolicitarCierreDeFrentePeticion(BaseModel):
    nivel_id: UUID = Field(description="El frente que se cierra: un nivel de la obra.")


class ValidarCierreDeFrentePeticion(BaseModel):
    comentario: str | None = None


class RechazarCierreDeFrentePeticion(BaseModel):
    motivo: str = Field(min_length=1, description="Obligatorio: es lo que el residente corrige.")


class CierreDeFrenteRespuesta(BaseModel):
    id: UUID
    nivel_id: UUID
    estatus: str = Field(description="`solicitado` · `aprobado` · `validado` · `rechazado`.")
    avance_pct: Decimal = Field(description="El avance del frente cuando se solicitó.")
    solicitado_por: UUID
    aprobado_por: UUID | None = None
    validado_por: UUID | None = None
    comentarios: str | None = None

    @classmethod
    def desde_dominio(cls, cierre_id: UUID, cierre: CierreDeFrente) -> CierreDeFrenteRespuesta:
        return cls(
            id=cierre_id,
            nivel_id=UUID(cierre.nivel_id),
            estatus=cierre.estatus.value,
            avance_pct=cierre.avance_pct,
            solicitado_por=UUID(cierre.solicitado_por),
            aprobado_por=UUID(cierre.aprobado_por) if cierre.aprobado_por else None,
            validado_por=UUID(cierre.validado_por) if cierre.validado_por else None,
            comentarios=cierre.comentarios,
        )


class FrenteParaCierreRespuesta(BaseModel):
    nivel_id: UUID
    clave: str
    descripcion: str | None = None
    n_actividades: int
    avance_pct: Decimal = Field(description="Ponderado por costo, como el avance de la obra.")
    umbral_pct: Decimal = Field(description="Desde aquí el residente puede solicitar el cierre.")
    listo_para_cierre: bool = Field(
        description=(
            "`frente_listo_para_cierre`: llegó al umbral y no se ha solicitado su cierre. "
            "Avisa, no cierra: el cierre pregunta, no impide."
        )
    )
    cierre_id: UUID | None = None
    cierre_estatus: str | None = Field(
        default=None,
        description="El cierre vivo del frente, o el rechazado más reciente (con su motivo).",
    )
    cierre_avance_pct: Decimal | None = None
    solicitado_en: datetime | None = None
    aprobado_en: datetime | None = None
    validado_en: datetime | None = None
    cierre_comentarios: str | None = None


_PASO = {
    404: {"description": "El cierre no existe o está fuera de tu alcance."},
    409: {"description": "Transición de cierre no permitida."},
}


@router.get(
    "/obras/{obra_id}/cierres-frente",
    response_model=list[FrenteParaCierreRespuesta],
    summary="Los frentes de una obra con su avance y su cierre",
    responses={404: {"description": "La obra no existe o está fuera de tu alcance."}},
)
async def frentes_de_la_obra(
    obra_id: UUID, caso_uso: ConsultarFrentesDeObraDep
) -> list[FrenteParaCierreRespuesta]:
    """Todos los roles, cada uno con su alcance. Marca los frentes listos para
    cierre (90 %): una alerta que avisa, no cierra."""
    return [FrenteParaCierreRespuesta(**f) for f in await caso_uso.ejecutar(obra_id)]


@router.post(
    "/obras/{obra_id}/cierres-frente",
    response_model=CierreDeFrenteRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Solicitar el cierre de un frente (al 90 % de avance)",
    dependencies=[Depends(exigir_rol(Rol.RESIDENTE)), Idempotencia],
    responses={
        404: {"description": "La obra no tiene actividades en ese frente."},
        409: {"description": "El frente aún no llega al 90 %, o ya tiene un cierre vivo."},
    },
)
async def solicitar_cierre_de_frente(
    obra_id: UUID,
    peticion: SolicitarCierreDeFrentePeticion,
    ctx: ContextoActual,
    caso_uso: SolicitarCierreDeFrenteDep,
) -> CierreDeFrenteRespuesta:
    """El residente solicita el cierre del frente."""
    cierre_id, cierre = await caso_uso.ejecutar(
        ComandoSolicitarCierreDeFrente(
            obra_id=obra_id,
            nivel_id=peticion.nivel_id,
            residente_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
        )
    )
    return CierreDeFrenteRespuesta.desde_dominio(cierre_id, cierre)


@router.post(
    "/cierres-frente/{cierre_id}/aprobar",
    response_model=CierreDeFrenteRespuesta,
    summary="Aprobar el cierre de un frente",
    dependencies=[Depends(exigir_rol(Rol.SUPERVISOR)), Idempotencia],
    responses=_PASO,
)
async def aprobar_cierre_de_frente(
    cierre_id: UUID, ctx: ContextoActual, caso_uso: AprobarCierreDeFrenteDep
) -> CierreDeFrenteRespuesta:
    cierre = await caso_uso.ejecutar(
        ComandoAprobarCierreDeFrente(
            cierre_id=cierre_id, usuario_id=ctx.usuario_id, rol=Rol(ctx.rol)
        )
    )
    return CierreDeFrenteRespuesta.desde_dominio(cierre_id, cierre)


@router.post(
    "/cierres-frente/{cierre_id}/validar",
    response_model=CierreDeFrenteRespuesta,
    summary="Validar el cierre de un frente (el residente ya no registra avance ahí)",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA)), Idempotencia],
    responses=_PASO,
)
async def validar_cierre_de_frente(
    cierre_id: UUID,
    peticion: ValidarCierreDeFrentePeticion,
    ctx: ContextoActual,
    caso_uso: ValidarCierreDeFrenteDep,
) -> CierreDeFrenteRespuesta:
    cierre = await caso_uso.ejecutar(
        ComandoValidarCierreDeFrente(
            cierre_id=cierre_id,
            usuario_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
            comentario=peticion.comentario,
        )
    )
    return CierreDeFrenteRespuesta.desde_dominio(cierre_id, cierre)


@router.post(
    "/cierres-frente/{cierre_id}/rechazar",
    response_model=CierreDeFrenteRespuesta,
    summary="Rechazar el cierre de un frente",
    dependencies=[Depends(exigir_rol(Rol.SUPERVISOR, Rol.CONTROL_OBRA)), Idempotencia],
    responses=_PASO,
)
async def rechazar_cierre_de_frente(
    cierre_id: UUID,
    peticion: RechazarCierreDeFrentePeticion,
    ctx: ContextoActual,
    caso_uso: RechazarCierreDeFrenteDep,
) -> CierreDeFrenteRespuesta:
    cierre = await caso_uso.ejecutar(
        ComandoRechazarCierreDeFrente(
            cierre_id=cierre_id,
            usuario_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
            motivo=peticion.motivo,
        )
    )
    return CierreDeFrenteRespuesta.desde_dominio(cierre_id, cierre)
