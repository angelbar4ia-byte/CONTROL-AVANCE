"""Endpoints del flujo de incidencias.

Spec §11.2 (Incidencias) · §11.3 workflow F · §6.

Controladores delgados: validan el DTO, delegan en el caso de uso y mapean
el resultado. **Cero lógica de negocio aquí** (§12.11) — las reglas de
permisos y transición viven en `domain.incidencias.reglas`.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    AbrirIncidenciaDep,
    CerrarIncidenciaDep,
    ProgramarIncidenciaDep,
    RechazarIncidenciaDep,
    RegistrarEventoIncidenciaDep,
)
from obractrl.adapters.api.dependencias import ContextoActual, SesionRLS, exigir_rol
from obractrl.adapters.api.idempotencia import Idempotencia
from obractrl.adapters.repos.incidencias_sql import RepositorioIncidenciasSQL
from obractrl.application.casos_uso.gestionar_incidencia import (
    ComandoAbrirIncidencia,
    ComandoCerrarIncidencia,
    ComandoProgramarIncidencia,
    ComandoRechazarIncidencia,
    ComandoRegistrarEventoIncidencia,
)
from obractrl.domain.incidencias.reglas import Incidencia
from obractrl.domain.shared.diccionario import (
    EstatusIncidencia,
    ImpactoIncidencia,
    Rol,
    TipoIncidencia,
)

router = APIRouter(tags=["incidencias"])

FiltroEstatus = Annotated[
    EstatusIncidencia | None,
    Query(description="Filtra por estatus del flujo (§7.8)."),
]


class AbrirIncidenciaPeticion(BaseModel):
    """Alta de incidencia (§11.3 F.1). Cualquier rol la abre."""

    obra_id: UUID
    tipo: TipoIncidencia
    impacto: ImpactoIncidencia
    titulo: str = Field(min_length=1)
    descripcion: str | None = None
    frente_id: UUID | None = None
    evidencias: list[str] = Field(default_factory=list)
    bloquea_actividades: list[UUID] = Field(
        default_factory=list,
        description="Solo válido con impacto 'detiene' (§6).",
    )
    fecha_limite: date | None = None


class ProgramarIncidenciaPeticion(BaseModel):
    asignada_a: UUID = Field(description="Usuario a quien se asigna (§11.3 F.2).")


class EventoIncidenciaPeticion(BaseModel):
    """Comentario y, opcionalmente, transición (§11.3 F.3)."""

    accion: str = Field(min_length=1)
    estatus_nuevo: EstatusIncidencia | None = Field(
        default=None,
        description="`en_atencion` o `cierre_solicitado`; omite para solo comentar.",
    )
    comentario: str | None = None


class CerrarIncidenciaPeticion(BaseModel):
    comentario: str | None = None


class RechazarIncidenciaPeticion(BaseModel):
    motivo: str = Field(min_length=1, description="Motivo obligatorio del rechazo.")


class IncidenciaRespuesta(BaseModel):
    id: UUID
    obra_id: UUID
    frente_id: UUID | None
    tipo: str
    impacto: str
    titulo: str
    descripcion: str | None
    creada_por: UUID | None
    asignada_a: UUID | None
    estatus: str
    fecha_limite: date | None
    bloquea_actividades: list[str]
    evidencias: list[str]

    @classmethod
    def desde_dominio(cls, incidencia_id: UUID, incidencia: Incidencia) -> IncidenciaRespuesta:
        return cls(
            id=incidencia_id,
            obra_id=UUID(incidencia.obra_id),
            frente_id=UUID(incidencia.frente_id) if incidencia.frente_id else None,
            tipo=incidencia.tipo.value,
            impacto=incidencia.impacto.value,
            titulo=incidencia.titulo,
            descripcion=incidencia.descripcion,
            creada_por=UUID(incidencia.creada_por) if incidencia.creada_por else None,
            asignada_a=UUID(incidencia.asignada_a) if incidencia.asignada_a else None,
            estatus=incidencia.estatus.value,
            fecha_limite=incidencia.fecha_limite,
            bloquea_actividades=incidencia.bloquea_actividades,
            evidencias=incidencia.evidencias,
        )

    @classmethod
    def desde_fila(cls, fila: dict) -> IncidenciaRespuesta:
        return cls(
            id=fila["id"],
            obra_id=fila["obra_id"],
            frente_id=fila["frente_id"],
            tipo=fila["tipo"],
            impacto=fila["impacto"],
            titulo=fila["titulo"],
            descripcion=fila["descripcion"],
            creada_por=fila["creada_por"],
            asignada_a=fila["asignada_a"],
            estatus=fila["estatus"],
            fecha_limite=fila["fecha_limite"],
            bloquea_actividades=fila["bloquea_actividades"],
            evidencias=fila["evidencias"],
        )


@router.post(
    "/incidencias",
    response_model=IncidenciaRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Abrir una incidencia",
    # `Idempotency-Key` (§11.2) porque el móvil la captura sin señal y la
    # reenvía desde su bandeja de salida (`mobile/src/salida/bandeja.ts`): si
    # la red se cae después de que el servidor escribió pero antes de que
    # llegue la respuesta, el reintento tiene que ser un no-op y no una
    # segunda incidencia — que con `impacto=detiene` sería además un segundo
    # bloqueo de las mismas actividades (§11.3 F.5).
    dependencies=[Idempotencia],
    responses={
        409: {"description": "Esta clave de idempotencia ya se procesó (§11.2)."},
        422: {"description": "Datos inválidos (§6)."},
    },
)
async def abrir_incidencia(
    peticion: AbrirIncidenciaPeticion,
    ctx: ContextoActual,
    caso_uso: AbrirIncidenciaDep,
) -> IncidenciaRespuesta:
    """Cualquier rol abre una incidencia (§11.3 F.1)."""
    creada = await caso_uso.ejecutar(
        ComandoAbrirIncidencia(
            obra_id=peticion.obra_id,
            creada_por=ctx.usuario_id,
            tipo=peticion.tipo,
            impacto=peticion.impacto,
            titulo=peticion.titulo,
            descripcion=peticion.descripcion,
            frente_id=peticion.frente_id,
            evidencias=peticion.evidencias,
            bloquea_actividades=peticion.bloquea_actividades,
            fecha_limite=peticion.fecha_limite,
        )
    )
    return IncidenciaRespuesta.desde_dominio(creada.id, creada.incidencia)


@router.patch(
    "/incidencias/{incidencia_id}",
    response_model=IncidenciaRespuesta,
    summary="Programar una incidencia (asignación)",
    dependencies=[Depends(exigir_rol(Rol.SUPERVISOR, Rol.CONTROL_OBRA))],
    responses={
        404: {"description": "La incidencia no existe o está fuera de tu alcance."},
        409: {"description": "Transición de incidencia no permitida."},
    },
)
async def programar_incidencia(
    incidencia_id: UUID,
    peticion: ProgramarIncidenciaPeticion,
    ctx: ContextoActual,
    caso_uso: ProgramarIncidenciaDep,
) -> IncidenciaRespuesta:
    """Supervisor o Control programan (asignación) (§11.3 F.2)."""
    incidencia = await caso_uso.ejecutar(
        ComandoProgramarIncidencia(
            incidencia_id=incidencia_id,
            usuario_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
            asignada_a=peticion.asignada_a,
        )
    )
    return IncidenciaRespuesta.desde_dominio(incidencia_id, incidencia)


@router.post(
    "/incidencias/{incidencia_id}/eventos",
    response_model=IncidenciaRespuesta,
    summary="Comentar o transicionar una incidencia",
    dependencies=[Idempotencia],
    responses={
        404: {"description": "La incidencia no existe o está fuera de tu alcance."},
        409: {"description": "Transición de incidencia no permitida."},
    },
)
async def registrar_evento_incidencia(
    incidencia_id: UUID,
    peticion: EventoIncidenciaPeticion,
    ctx: ContextoActual,
    caso_uso: RegistrarEventoIncidenciaDep,
) -> IncidenciaRespuesta:
    """Atención (`en_atencion`) y solicitud de cierre (`cierre_solicitado`);
    todos los que participan pueden registrar el evento (§11.3 F.3)."""
    incidencia = await caso_uso.ejecutar(
        ComandoRegistrarEventoIncidencia(
            incidencia_id=incidencia_id,
            usuario_id=ctx.usuario_id,
            accion=peticion.accion,
            estatus_nuevo=peticion.estatus_nuevo,
            comentario=peticion.comentario,
        )
    )
    return IncidenciaRespuesta.desde_dominio(incidencia_id, incidencia)


@router.post(
    "/incidencias/{incidencia_id}/cerrar",
    response_model=IncidenciaRespuesta,
    summary="Cerrar una incidencia",
    dependencies=[Depends(exigir_rol(Rol.SUPERVISOR, Rol.CONTROL_OBRA)), Idempotencia],
    responses={
        404: {"description": "La incidencia no existe o está fuera de tu alcance."},
        409: {"description": "Transición de incidencia no permitida."},
    },
)
async def cerrar_incidencia(
    incidencia_id: UUID,
    peticion: CerrarIncidenciaPeticion,
    ctx: ContextoActual,
    caso_uso: CerrarIncidenciaDep,
) -> IncidenciaRespuesta:
    """Supervisor o Control cierran; desbloquea actividades si aplicaba
    (§11.3 F.4, §6)."""
    incidencia = await caso_uso.ejecutar(
        ComandoCerrarIncidencia(
            incidencia_id=incidencia_id,
            usuario_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
            comentario=peticion.comentario,
        )
    )
    return IncidenciaRespuesta.desde_dominio(incidencia_id, incidencia)


@router.post(
    "/incidencias/{incidencia_id}/rechazar",
    response_model=IncidenciaRespuesta,
    summary="Rechazar una incidencia",
    dependencies=[Depends(exigir_rol(Rol.SUPERVISOR, Rol.CONTROL_OBRA)), Idempotencia],
    responses={
        404: {"description": "La incidencia no existe o está fuera de tu alcance."},
        409: {"description": "Transición de incidencia no permitida."},
    },
)
async def rechazar_incidencia(
    incidencia_id: UUID,
    peticion: RechazarIncidenciaPeticion,
    ctx: ContextoActual,
    caso_uso: RechazarIncidenciaDep,
) -> IncidenciaRespuesta:
    """Supervisor o Control rechazan la incidencia (§11.2)."""
    incidencia = await caso_uso.ejecutar(
        ComandoRechazarIncidencia(
            incidencia_id=incidencia_id,
            usuario_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
            motivo=peticion.motivo,
        )
    )
    return IncidenciaRespuesta.desde_dominio(incidencia_id, incidencia)


@router.get(
    "/incidencias",
    response_model=list[IncidenciaRespuesta],
    summary="Bandeja de incidencias por rol",
)
async def listar_incidencias(
    sesion: SesionRLS, estatus: FiltroEstatus = None
) -> list[IncidenciaRespuesta]:
    """Bandeja de incidencias visibles para el rol actual.

    Es una lectura simple sin orquestación de dominio —como `GET /cierres`
    (`adapters/api/v1/cierres.py`)— así que consulta el repo directo, sin
    caso de uso: RLS ya acota el alcance (§12.4).
    """
    repo = RepositorioIncidenciasSQL(sesion)
    filas = await repo.listar(estatus=estatus.value if estatus else None)
    return [IncidenciaRespuesta.desde_fila(fila) for fila in filas]
