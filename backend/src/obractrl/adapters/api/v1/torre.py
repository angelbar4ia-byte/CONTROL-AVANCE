"""Torre de control y actividades (§5.1, §11.2).

Spec §5.1 (primera entrada de Supervisor, Control de obra y Super intendente) ·
§5.3 (pantalla compartida) · §12.4 (RLS decide el alcance) · §12.11.

Tres rutas de **lectura**, sin caso de uso de por medio: no hay ninguna regla de
negocio que aplicar entre la consulta y la respuesta, y meter una capa vacía
solo para respetar una forma sería ceremonia. Es el mismo criterio que
`GET /me` en `identidad.py` y que los listados de `cargas.py`.

## Quién ve qué

Ninguna de las tres lleva `exigir_rol`, y es deliberado: el §5.1 pone la Torre
en el sidebar de tres roles, y el residente —que no la tiene— llega a las
actividades de **su** obra por la pantalla de avance. Lo que cada quien ve lo
decide RLS (`obra_select`, migración 0012), que ya sabe distinguir "las obras de
mis clusters" de "las de mis proyectos". Un `exigir_rol` aquí sería una segunda
lista de roles que mantener sincronizada con el sidebar, y la única
consecuencia de olvidarla es que alguien vea una tabla vacía.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.dependencias import SesionRLS
from obractrl.adapters.repos.torre_sql import RepositorioTorreSQL
from obractrl.domain.shared.diccionario import EstatusActividad

router = APIRouter(tags=["torre"])

FiltroProyecto = Annotated[UUID | None, Query(description="Acota a un proyecto.")]
FiltroCluster = Annotated[UUID | None, Query(description="Acota a un cluster.")]


class EstadoDeObraRespuesta(BaseModel):
    """El renglón de la Torre: una obra y lo que le falta (§5.1)."""

    obra_id: UUID
    obra_clave: str
    obra_estatus: str
    avance_pct: Decimal
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    cluster_id: UUID
    cluster_clave: str
    proyecto_id: UUID
    proyecto_clave: str
    residente_nombre: str | None = None

    actividades: int
    criticas: int = Field(description="En la ruta crítica (§7.5).")
    bloqueadas: int = Field(
        description="Detenidas por una incidencia con impacto `detiene` (§11.3 F)."
    )
    concluidas: int

    incidencias_abiertas: int = Field(
        description="Sin cerrar ni rechazar: las que todavía le tocan a alguien."
    )
    incidencias_detienen: int
    cierres_pendientes: int = Field(
        description="Solicitados o autorizados: esperan a supervisor o a control (§11.3 C)."
    )


class ActividadRespuesta(BaseModel):
    """Una actividad de la obra (§11.2 `GET /obras/{id}/actividades`)."""

    id: UUID
    obra_id: UUID
    concepto_id: UUID | None = None
    frente_id: UUID | None = None
    descripcion: str | None = None
    frente_nombre: str | None = None

    cant_base: Decimal
    cant_programada: Decimal
    cant_ejecutada: Decimal
    avance_pct: Decimal

    estatus: str
    bloqueada: bool
    extra: bool = Field(description="Alta extra-catálogo con OC (§5.1).")
    es_critica: bool
    holgura: Decimal | None = None
    desfase: Decimal | None = None

    fecha_inicio: date | None = None
    fecha_termino: date | None = None
    duracion_dias: Decimal

    modo_pago: str
    precio_unitario: Decimal
    precio_destajo: Decimal


class ActividadDetalleRespuesta(ActividadRespuesta):
    """Lo mismo, más lo que solo interesa al abrirla (§11.2 `GET /actividades/{id}`)."""

    obra_clave: str
    dependencias: list = Field(default_factory=list)
    notas: str | None = None
    contratista_nombre: str | None = None
    cuadrilla_nombre: str | None = None


@router.get(
    "/torre",
    response_model=list[EstadoDeObraRespuesta],
    summary="Estado de cada obra en el alcance",
)
async def torre_de_control(
    sesion: SesionRLS,
    proyecto_id: FiltroProyecto = None,
    cluster_id: FiltroCluster = None,
    solo_pendientes: Annotated[
        bool,
        Query(
            description=(
                "Solo las obras con algo esperando: incidencia abierta, cierre "
                "por resolver o actividad bloqueada."
            )
        ),
    ] = False,
) -> list[dict]:
    """Una fila por obra visible, con sus contadores (§5.1).

    Agregado a propósito: resolverlo desde el cliente serían cinco peticiones
    por obra, y el §12.1 habla de 60–80 obras activas. El razonamiento completo
    está en el encabezado de `adapters/repos/torre_sql.py`.
    """
    return await RepositorioTorreSQL(sesion).estado_de_obras(
        proyecto_id=proyecto_id,
        cluster_id=cluster_id,
        solo_con_pendientes=solo_pendientes,
    )


@router.get(
    "/obras/{obra_id}/actividades",
    response_model=list[ActividadRespuesta],
    summary="Actividades de una obra",
)
async def actividades_de_obra(
    obra_id: UUID,
    sesion: SesionRLS,
    estatus: Annotated[
        EstatusActividad | None, Query(description="Filtra por estatus (§8.2).")
    ] = None,
    solo_criticas: Annotated[
        bool, Query(description="Solo las de la ruta crítica (§7.5).")
    ] = False,
) -> list[dict]:
    """El detalle de una obra en la Torre (§11.2).

    Una obra fuera del alcance devuelve **lista vacía**, no 404: RLS ya la hizo
    invisible, y un 404 aquí obligaría a una consulta extra solo para
    distinguir "no existe" de "no la ves" — que hacia afuera son lo mismo
    (§12.4).
    """
    return await RepositorioTorreSQL(sesion).actividades_de_obra(
        obra_id,
        estatus=estatus.value if estatus else None,
        solo_criticas=solo_criticas,
    )


@router.get(
    "/actividades/{actividad_id}",
    response_model=ActividadDetalleRespuesta,
    summary="Detalle de una actividad",
    responses={
        404: {"description": "La actividad no existe o está fuera de tu alcance."}
    },
)
async def actividad(actividad_id: UUID, sesion: SesionRLS) -> dict:
    """Una actividad con su programación, su costeo y su contexto (§11.2).

    Aquí sí es 404 y no lista vacía: se pidió **una** cosa concreta y no está.
    Que la causa sea RLS o que no exista es indistinguible a propósito.
    """
    fila = await RepositorioTorreSQL(sesion).actividad(actividad_id)
    if fila is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"La actividad {actividad_id} no existe o está fuera de tu alcance."
            ),
        )
    return fila
