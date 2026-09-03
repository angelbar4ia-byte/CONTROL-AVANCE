"""Endpoints del control de cambio (§11.2, §11.3, §6).

El jefe de obra lo unificó: *"pueden pedir más cantidad, dar de alta trabajo
fuera de catálogo, cambiar una actividad por otra, o pedir una que existe en el
catálogo y no estaba; todo esto al final se clasifica como control de cambio
que recae al costo de la obra final"*.

Controlador delgado (§12.11): las reglas viven en
`domain.obras.control_cambio` y el efecto de autorizar en
`application.casos_uso.gestionar_control_cambio`.

## Quién pide y quién autoriza

El **residente** pide: es quien está en la obra y ve que hace falta. **Control
de obra** y el **Super intendente** autorizan. El residente no autoriza ni lo
suyo — autorizar lo que uno mismo pidió convierte el control en un trámite, y
es la misma separación que el cierre de actividad.

RLS acota a las obras de cada uno (`app.obra_visible`, migración 0042), así que
las guardas de rol solo evitan ofrecer la acción a quien no la tiene.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    ResolverControlDeCambioDep,
    SolicitarControlDeCambioDep,
)
from obractrl.adapters.api.dependencias import ContextoActual, SesionRLS, exigir_rol
from obractrl.adapters.repos.control_cambio_sql import RepositorioControlCambioSQL
from obractrl.application.casos_uso.gestionar_control_cambio import (
    ComandoResolverCambio,
    ComandoSolicitarCambio,
    ControlDeCambioNoResoluble,
)
from obractrl.domain.obras.control_cambio import LineaDeCambio, TipoControlCambio
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["control-cambio"])

SOLICITA = Depends(exigir_rol(Rol.RESIDENTE))
"""Quien está en la obra y ve que hace falta (§4)."""

RESUELVE = Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE))
"""Quien autoriza. No el residente, ni sobre lo suyo (§4)."""

CONSULTA = Depends(
    exigir_rol(Rol.RESIDENTE, Rol.SUPERVISOR, Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE)
)


class LineaPeticion(BaseModel):
    """Una actividad dentro de la solicitud.

    Varias a propósito: el residente pide por sub-frente, y si se le agotó el
    cemento en tres actividades de albañilería manda **una** solicitud con tres
    renglones, no tres que alguien tenga que relacionar después.
    """

    cantidad: Decimal = Field(gt=0)
    actividad_id: UUID | None = Field(
        default=None,
        description="La actividad afectada. Obligatoria al pedir más cantidad.",
    )
    concepto_id: UUID | None = Field(
        default=None, description="Obligatorio al traer algo del catálogo."
    )
    descripcion: str | None = Field(
        default=None, description="Obligatoria fuera de catálogo: no hay concepto."
    )
    precio_unitario: Decimal = Field(default=Decimal(0), ge=0)
    sustituye_a: UUID | None = Field(
        default=None, description="Obligatoria en una sustitución."
    )


class SolicitarCambioPeticion(BaseModel):
    tipo: TipoControlCambio
    motivo: str = Field(
        min_length=1,
        description=(
            "Por qué hace falta. Quien autoriza no estuvo en la obra: esto es "
            "todo lo que va a tener para decidir."
        ),
    )
    lineas: list[LineaPeticion] = Field(min_length=1)
    nivel_id: UUID | None = Field(default=None, description="El **frente** (§7.4).")
    etapa_id: UUID | None = Field(default=None, description="El **sub-frente**.")


class ResolverCambioPeticion(BaseModel):
    autorizado: bool
    orden_cambio: str | None = Field(
        default=None,
        description=(
            "**Obligatoria al autorizar**: es lo que vuelve válida la "
            "autorización. Se captura aquí y no al pedir — una orden tecleada "
            "por quien pide no autoriza nada. La base lo repite como CHECK."
        ),
    )
    nota: str | None = None
    descuenta_ejecutado: bool = Field(
        default=False,
        description=(
            "Solo en una sustitución. Lo ejecutado de la actividad reemplazada "
            "**se estima por defecto** —el trabajo se hizo y alguien lo pagó—; "
            "esto lo descuenta cuando el caso lo pide."
        ),
    )


class ControlCambioRespuesta(BaseModel):
    id: UUID
    obra_id: UUID
    tipo: str
    estatus: str
    motivo: str
    nivel_id: UUID | None = None
    etapa_id: UUID | None = None
    solicitado_por: UUID
    solicitado_en: datetime
    orden_cambio: str | None = None
    autorizado_por: UUID | None = None
    resuelto_en: datetime | None = None
    nota_resolucion: str | None = None
    descuenta_ejecutado: bool = False
    importe: Decimal = Field(
        default=Decimal(0),
        description="Lo que esta solicitud le mueve al costo final de la obra.",
    )
    renglones: int = 0


class EfectoRespuesta(BaseModel):
    """Qué cambió en la obra al autorizar."""

    actividades_afectadas: int
    actividades_creadas: int


@router.post(
    "/obras/{obra_id}/controles-cambio",
    status_code=status.HTTP_201_CREATED,
    summary="Pedir un control de cambio",
    dependencies=[SOLICITA],
    responses={422: {"description": "La solicitud no cumple su tipo (§11.3)."}},
)
async def solicitar_control_de_cambio(
    obra_id: UUID,
    peticion: SolicitarCambioPeticion,
    ctx: ContextoActual,
    caso_uso: SolicitarControlDeCambioDep,
) -> dict[str, str]:
    """El residente pide; no autoriza nada todavía (§11.3).

    La orden de cambio **no** viaja aquí: se captura al autorizar. Eso es lo que
    separa pedir de autorizar, y antes no existía — el residente tecleaba él
    mismo la orden al dar de alta un extra.
    """
    control_id = await caso_uso.ejecutar(
        ComandoSolicitarCambio(
            obra_id=obra_id,
            tipo=peticion.tipo,
            motivo=peticion.motivo,
            lineas=tuple(
                LineaDeCambio(
                    cantidad=linea.cantidad,
                    actividad_id=str(linea.actividad_id) if linea.actividad_id else None,
                    concepto_id=str(linea.concepto_id) if linea.concepto_id else None,
                    descripcion=linea.descripcion,
                    precio_unitario=linea.precio_unitario,
                    sustituye_a=str(linea.sustituye_a) if linea.sustituye_a else None,
                )
                for linea in peticion.lineas
            ),
            usuario_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
            nivel_id=peticion.nivel_id,
            etapa_id=peticion.etapa_id,
        )
    )
    return {"id": str(control_id)}


@router.post(
    "/controles-cambio/{control_id}/resolver",
    response_model=EfectoRespuesta,
    summary="Autorizar o rechazar un control de cambio",
    dependencies=[RESUELVE],
    responses={
        404: {"description": "No existe, no lo ves, o ya se resolvió (§12.4)."},
        422: {"description": "Autorizar sin orden de cambio (§11.3)."},
    },
)
async def resolver_control_de_cambio(
    control_id: UUID,
    peticion: ResolverCambioPeticion,
    ctx: ContextoActual,
    caso_uso: ResolverControlDeCambioDep,
) -> EfectoRespuesta:
    """Autorizar **aplica el efecto** en la misma transacción (§11.3).

    Subir el techo de una actividad, dar de alta el trabajo nuevo, o cancelar la
    que se sustituye. Guardar el "sí" y dejar el efecto para después haría que
    una solicitud autorizada y sin aplicar fuera invisible: ni sale como
    pendiente ni cambió nada.
    """
    try:
        efecto = await caso_uso.ejecutar(
            ComandoResolverCambio(
                control_id=control_id,
                usuario_id=ctx.usuario_id,
                rol=Rol(ctx.rol),
                autorizado=peticion.autorizado,
                orden_cambio=peticion.orden_cambio,
                nota=peticion.nota,
                descuenta_ejecutado=peticion.descuenta_ejecutado,
            )
        )
    except ControlDeCambioNoResoluble as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    return EfectoRespuesta(**efecto)


@router.get(
    "/controles-cambio",
    response_model=list[ControlCambioRespuesta],
    summary="Controles de cambio de tus obras",
    dependencies=[CONSULTA],
)
async def listar_controles_de_cambio(
    sesion: SesionRLS,
    obra_id: Annotated[UUID | None, Query(description="Filtra a una obra.")] = None,
    estatus: Annotated[
        str | None, Query(pattern="^(solicitado|autorizado|rechazado)$")
    ] = None,
) -> list[dict[str, Any]]:
    """Lo ven los cuatro roles: el residente para seguir lo suyo, Control para
    decidir, el supervisor y el Super intendente para saber cuánto se movió el
    costo. **RLS acota cuáles** son sus obras (§12.4)."""
    return await RepositorioControlCambioSQL(sesion).listar(
        obra_id=obra_id, estatus=estatus
    )


@router.get(
    "/controles-cambio/{control_id}/lineas",
    summary="Los renglones de un control de cambio",
    dependencies=[CONSULTA],
)
async def lineas_del_control(
    control_id: UUID, sesion: SesionRLS
) -> list[dict[str, Any]]:
    """Con la actividad afectada resuelta: cantidad base, programada y techo.

    Es lo que Control necesita para decidir sin abrir otra pantalla — cuánto
    tenía, cuánto lleva y cuánto se está pidiendo.
    """
    return await RepositorioControlCambioSQL(sesion).lineas_de(control_id)
