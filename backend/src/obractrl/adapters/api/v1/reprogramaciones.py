"""Reprogramar lo asignado (migración 0072; cerebro D-533, P-4).

«Las fechas asignadas no se mueven solas.» El `PATCH` de programación rechaza con 409 el
intento de mover directo la fecha de una actividad con contratista; el camino es esta
cadena:

    propone              revisa        valida           realiza
    Residente            Supervisor    Control de obra  Control de obra
    Supervisor           (se salta)    Control de obra  Control de obra

Al realizarse se mueve la fecha (con su rastro en la bitácora del programa) y se
notifica a los demás. Controladores delgados: las reglas viven en
`domain.programacion.reprogramacion`.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    AplicarReprogramacionDep,
    ConsultarReprogramacionesDep,
    ObservarReprogramacionDep,
    ProponerReprogramacionDep,
    RechazarReprogramacionDep,
    RevisarReprogramacionDep,
    ValidarReprogramacionDep,
)
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.adapters.api.idempotencia import Idempotencia
from obractrl.application.casos_uso.gestionar_reprogramacion import (
    ComandoAplicarReprogramacion,
    ComandoObservarReprogramacion,
    ComandoProponerReprogramacion,
    ComandoRechazarReprogramacion,
    ComandoRevisarReprogramacion,
    ComandoValidarReprogramacion,
)
from obractrl.domain.programacion.reprogramacion import Reprogramacion
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["programacion"])


class ProponerReprogramacionPeticion(BaseModel):
    fecha_inicio: date | None = Field(default=None, description="La fecha de inicio nueva.")
    fecha_termino: date | None = Field(default=None, description="La fecha de término nueva.")
    motivo: str = Field(min_length=1, description="Obligatorio: por qué se mueve lo asignado.")


class RechazarReprogramacionPeticion(BaseModel):
    motivo: str = Field(min_length=1, description="Obligatorio: es lo que quien propuso corrige.")


class ObservarReprogramacionPeticion(BaseModel):
    texto: str = Field(
        min_length=1,
        description="La observación para el residente y el supervisor. No cambia el estatus.",
    )


class ObservacionRespuesta(BaseModel):
    id: UUID
    reprogramacion_id: UUID
    usuario_id: UUID
    usuario_nombre: str | None = None
    rol: str
    texto: str
    creada_en: datetime


class ReprogramacionRespuesta(BaseModel):
    id: UUID
    actividad_id: UUID
    estatus: str = Field(
        description="`propuesta` · `revisada` · `validada` · `aplicada` · `rechazada`."
    )
    fecha_inicio: date | None = None
    fecha_termino: date | None = None
    motivo: str
    propuesta_por: UUID
    propuesta_rol: str
    revisada_por: UUID | None = Field(
        default=None, description="Vacío si propuso el supervisor: la revisión se salta."
    )
    validada_por: UUID | None = None
    aplicada_por: UUID | None = None
    rechazada_por: UUID | None = None
    motivo_rechazo: str | None = None

    @classmethod
    def desde_dominio(
        cls, reprogramacion_id: UUID, reprogramacion: Reprogramacion
    ) -> ReprogramacionRespuesta:
        def _id(valor: str | None) -> UUID | None:
            return UUID(valor) if valor else None

        return cls(
            id=reprogramacion_id,
            actividad_id=UUID(reprogramacion.actividad_id),
            estatus=reprogramacion.estatus.value,
            fecha_inicio=reprogramacion.fecha_inicio,
            fecha_termino=reprogramacion.fecha_termino,
            motivo=reprogramacion.motivo,
            propuesta_por=UUID(reprogramacion.propuesta_por),
            propuesta_rol=reprogramacion.propuesta_rol.value,
            revisada_por=_id(reprogramacion.revisada_por),
            validada_por=_id(reprogramacion.validada_por),
            aplicada_por=_id(reprogramacion.aplicada_por),
            rechazada_por=_id(reprogramacion.rechazada_por),
            motivo_rechazo=reprogramacion.motivo_rechazo,
        )


class ReprogramacionDeObraRespuesta(BaseModel):
    """Una reprogramación con lo que la lista necesita: la actividad, las fechas de
    antes y quién intervino en cada paso de la cadena."""

    id: UUID
    obra_id: UUID
    actividad_id: UUID
    actividad: str | None = None
    concepto_clave: str | None = None
    contratista: str | None = None
    estatus: str
    fecha_inicio: date | None = None
    fecha_termino: date | None = None
    fecha_inicio_anterior: date | None = Field(
        default=None, description="La fecha de inicio que había cuando se propuso."
    )
    fecha_termino_anterior: date | None = None
    motivo: str
    propuesta_por: UUID
    propuesta_por_nombre: str | None = None
    propuesta_rol: str
    propuesta_en: datetime
    revisada_por: UUID | None = None
    revisada_por_nombre: str | None = None
    revisada_en: datetime | None = None
    validada_por: UUID | None = None
    validada_por_nombre: str | None = None
    validada_en: datetime | None = None
    aplicada_por: UUID | None = None
    aplicada_por_nombre: str | None = None
    aplicada_en: datetime | None = None
    rechazada_por: UUID | None = None
    rechazada_por_nombre: str | None = None
    rechazada_en: datetime | None = None
    motivo_rechazo: str | None = None
    observaciones: list[ObservacionRespuesta] = Field(
        default_factory=list,
        description="Lo que control de obra le ha dicho al residente y al supervisor, en orden.",
    )


_PASO = {
    404: {"description": "La reprogramación no existe o está fuera de tu alcance."},
    409: {"description": "Ese paso no corresponde en el estado actual de la cadena."},
}


@router.get(
    "/obras/{obra_id}/reprogramaciones",
    response_model=list[ReprogramacionDeObraRespuesta],
    summary="Las reprogramaciones de lo asignado de una obra",
    responses={404: {"description": "La obra no existe o está fuera de tu alcance."}},
)
async def reprogramaciones_de_la_obra(
    obra_id: UUID, caso_uso: ConsultarReprogramacionesDep
) -> list[ReprogramacionDeObraRespuesta]:
    """Todos los roles, cada uno con su alcance (RLS). Lo más reciente, primero."""
    return [ReprogramacionDeObraRespuesta(**f) for f in await caso_uso.ejecutar(obra_id)]


@router.post(
    "/actividades/{actividad_id}/reprogramaciones",
    response_model=ReprogramacionRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Proponer la fecha nueva de una actividad asignada",
    dependencies=[Depends(exigir_rol(Rol.RESIDENTE, Rol.SUPERVISOR)), Idempotencia],
    responses={
        404: {"description": "La actividad no existe o está fuera de tu alcance."},
        409: {
            "description": (
                "La actividad no está asignada, no hay nada que mover, o ya tiene una "
                "reprogramación en la cadena."
            )
        },
    },
)
async def proponer_reprogramacion(
    actividad_id: UUID,
    peticion: ProponerReprogramacionPeticion,
    ctx: ContextoActual,
    caso_uso: ProponerReprogramacionDep,
) -> ReprogramacionRespuesta:
    """Propone el residente (lo revisa el supervisor) o el supervisor (la revisión se
    salta). Solo se reprograma lo asignado; lo demás se edita directo."""
    reprogramacion_id, reprogramacion = await caso_uso.ejecutar(
        ComandoProponerReprogramacion(
            actividad_id=actividad_id,
            usuario_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
            motivo=peticion.motivo,
            fecha_inicio=peticion.fecha_inicio,
            fecha_termino=peticion.fecha_termino,
        )
    )
    return ReprogramacionRespuesta.desde_dominio(reprogramacion_id, reprogramacion)


@router.post(
    "/reprogramaciones/{reprogramacion_id}/revisar",
    response_model=ReprogramacionRespuesta,
    summary="Revisar la reprogramación propuesta por el residente",
    dependencies=[Depends(exigir_rol(Rol.SUPERVISOR)), Idempotencia],
    responses=_PASO,
)
async def revisar_reprogramacion(
    reprogramacion_id: UUID, ctx: ContextoActual, caso_uso: RevisarReprogramacionDep
) -> ReprogramacionRespuesta:
    reprogramacion = await caso_uso.ejecutar(
        ComandoRevisarReprogramacion(
            reprogramacion_id=reprogramacion_id, usuario_id=ctx.usuario_id, rol=Rol(ctx.rol)
        )
    )
    return ReprogramacionRespuesta.desde_dominio(reprogramacion_id, reprogramacion)


@router.post(
    "/reprogramaciones/{reprogramacion_id}/validar",
    response_model=ReprogramacionRespuesta,
    summary="Validar la fecha nueva",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA)), Idempotencia],
    responses=_PASO,
)
async def validar_reprogramacion(
    reprogramacion_id: UUID, ctx: ContextoActual, caso_uso: ValidarReprogramacionDep
) -> ReprogramacionRespuesta:
    reprogramacion = await caso_uso.ejecutar(
        ComandoValidarReprogramacion(
            reprogramacion_id=reprogramacion_id, usuario_id=ctx.usuario_id, rol=Rol(ctx.rol)
        )
    )
    return ReprogramacionRespuesta.desde_dominio(reprogramacion_id, reprogramacion)


@router.post(
    "/reprogramaciones/{reprogramacion_id}/aplicar",
    response_model=ReprogramacionRespuesta,
    summary="Realizar la reprogramación: mueve la fecha de lo asignado y avisa",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA)), Idempotencia],
    responses=_PASO,
)
async def aplicar_reprogramacion(
    reprogramacion_id: UUID, ctx: ContextoActual, caso_uso: AplicarReprogramacionDep
) -> ReprogramacionRespuesta:
    """Control de obra realiza lo validado. La fecha se mueve y la reprogramación queda
    aplicada en la misma transacción; después se notifica a los demás."""
    reprogramacion = await caso_uso.ejecutar(
        ComandoAplicarReprogramacion(
            reprogramacion_id=reprogramacion_id, usuario_id=ctx.usuario_id, rol=Rol(ctx.rol)
        )
    )
    return ReprogramacionRespuesta.desde_dominio(reprogramacion_id, reprogramacion)


@router.post(
    "/reprogramaciones/{reprogramacion_id}/rechazar",
    response_model=ReprogramacionRespuesta,
    summary="Rechazar la reprogramación",
    dependencies=[Depends(exigir_rol(Rol.SUPERVISOR, Rol.CONTROL_OBRA)), Idempotencia],
    responses=_PASO,
)
async def rechazar_reprogramacion(
    reprogramacion_id: UUID,
    peticion: RechazarReprogramacionPeticion,
    ctx: ContextoActual,
    caso_uso: RechazarReprogramacionDep,
) -> ReprogramacionRespuesta:
    reprogramacion = await caso_uso.ejecutar(
        ComandoRechazarReprogramacion(
            reprogramacion_id=reprogramacion_id,
            usuario_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
            motivo=peticion.motivo,
        )
    )
    return ReprogramacionRespuesta.desde_dominio(reprogramacion_id, reprogramacion)


@router.post(
    "/reprogramaciones/{reprogramacion_id}/observaciones",
    response_model=ObservacionRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Dejar una observación al residente y al supervisor",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA)), Idempotencia],
    responses={
        404: {"description": "La reprogramación no existe o está fuera de tu alcance."},
        409: {"description": "El texto de la observación está vacío."},
    },
)
async def observar_reprogramacion(
    reprogramacion_id: UUID,
    peticion: ObservarReprogramacionPeticion,
    ctx: ContextoActual,
    caso_uso: ObservarReprogramacionDep,
) -> ObservacionRespuesta:
    """Control de obra dice algo sin mover la cadena: cabe en cualquier estatus, también
    aplicada o rechazada. Se avisa al residente y al supervisor de la obra (correo y push).
    Las observaciones solo se agregan."""
    observacion = await caso_uso.ejecutar(
        ComandoObservarReprogramacion(
            reprogramacion_id=reprogramacion_id,
            usuario_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
            texto=peticion.texto,
        )
    )
    return ObservacionRespuesta(**observacion)
