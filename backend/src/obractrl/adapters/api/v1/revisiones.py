"""Endpoints de revisión física en campo.

Spec §11.2 ("Revisión física (móvil · Control de obra)": `POST
/obras/{id}/revisiones` — fotos + comentario + calidad (C) · `GET
/revisiones`) · §7.8 · §2 (glosario).

Controladores delgados: validan el DTO, delegan en el caso de uso y mapean el
resultado. **Cero lógica de negocio aquí** (§12.11) — el rol y la escala de
calidad los decide `domain.revisiones.reglas`.

Las `fotos` son **URLs ya subidas**, no archivos: el cliente pide primero una
presigned URL (`POST /evidencias/presigned`, `adapters/api/v1/evidencias.py`),
sube directo a R2 y luego manda aquí las claves resultantes. El binario nunca
viaja por la API (§12.2).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import RegistrarRevisionFisicaDep
from obractrl.adapters.api.dependencias import ContextoActual, SesionRLS, exigir_rol
from obractrl.adapters.repos.revisiones_sql import RepositorioRevisionesSQL
from obractrl.application.casos_uso.registrar_revision_fisica import (
    ComandoRegistrarRevision,
)
from obractrl.domain.revisiones.reglas import (
    CALIDAD_MAXIMA,
    CALIDAD_MINIMA,
    RevisionFisica,
)
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["revisiones"])

FiltroObra = Annotated[UUID | None, Query(description="Filtra por obra.")]


class RegistrarRevisionPeticion(BaseModel):
    """Captura en campo (§11.2): fotos + comentario + calidad."""

    fecha: date | None = Field(
        default=None,
        description="Día de la revisión; por omisión, hoy (`revision_fisica.fecha`).",
    )
    fotos: list[str] = Field(
        default_factory=list,
        description=(
            "Claves de los objetos ya subidos a R2 con `POST "
            "/evidencias/presigned` (§12.2). El archivo no viaja por la API."
        ),
    )
    comentario: str | None = None
    calidad: int | None = Field(
        default=None,
        ge=CALIDAD_MINIMA,
        le=CALIDAD_MAXIMA,
        description=f"Escala {CALIDAD_MINIMA}–{CALIDAD_MAXIMA} (§7.8).",
    )
    actividad_id: UUID | None = Field(
        default=None, description="Vínculo opcional a un avance (§7.8)."
    )
    incidencia_id: UUID | None = Field(
        default=None, description="Vínculo opcional a una incidencia (§7.8)."
    )


class RevisionRespuesta(BaseModel):
    id: UUID
    obra_id: UUID
    actividad_id: UUID | None
    incidencia_id: UUID | None
    usuario_id: UUID | None
    fecha: date
    fotos: list[str]
    comentario: str | None
    calidad: int | None

    @classmethod
    def desde_dominio(
        cls, revision_id: UUID, revision: RevisionFisica
    ) -> RevisionRespuesta:
        return cls(
            id=revision_id,
            obra_id=UUID(revision.obra_id),
            actividad_id=UUID(revision.actividad_id) if revision.actividad_id else None,
            incidencia_id=(
                UUID(revision.incidencia_id) if revision.incidencia_id else None
            ),
            usuario_id=UUID(revision.usuario_id),
            fecha=revision.fecha,
            fotos=revision.fotos,
            comentario=revision.comentario,
            calidad=revision.calidad,
        )

    @classmethod
    def desde_fila(cls, fila: dict) -> RevisionRespuesta:
        return cls(
            id=fila["id"],
            obra_id=fila["obra_id"],
            actividad_id=fila["actividad_id"],
            incidencia_id=fila["incidencia_id"],
            usuario_id=fila["usuario_id"],
            fecha=fila["fecha"],
            fotos=fila["fotos"],
            comentario=fila["comentario"],
            calidad=fila["calidad"],
        )


@router.post(
    "/obras/{obra_id}/revisiones",
    response_model=RevisionRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar una revisión física en campo",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA))],
    responses={
        404: {"description": "La obra no existe o está fuera de tu alcance."},
        422: {"description": "Rol o calidad fuera de lo permitido (§7.8, §11.2)."},
    },
)
async def registrar_revision(
    obra_id: UUID,
    peticion: RegistrarRevisionPeticion,
    ctx: ContextoActual,
    caso_uso: RegistrarRevisionFisicaDep,
) -> RevisionRespuesta:
    """Control de obra captura fotos, comentario y calidad (§11.2).

    La obra sale de la ruta, no del body: RLS decide si es visible para el
    usuario y, si no lo es, la política de `revision_fisica` rechaza el INSERT
    —no hace falta preguntarle primero al repo de Obras (§11.1: ningún módulo
    lee las tablas de otro).
    """
    registrada = await caso_uso.ejecutar(
        ComandoRegistrarRevision(
            obra_id=obra_id,
            usuario_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
            fecha=peticion.fecha or date.today(),
            fotos=peticion.fotos,
            comentario=peticion.comentario,
            calidad=peticion.calidad,
            actividad_id=peticion.actividad_id,
            incidencia_id=peticion.incidencia_id,
        )
    )
    return RevisionRespuesta.desde_dominio(registrada.id, registrada.revision)


@router.get(
    "/revisiones",
    response_model=list[RevisionRespuesta],
    summary="Bandeja de revisiones físicas",
)
async def listar_revisiones(
    sesion: SesionRLS, obra_id: FiltroObra = None
) -> list[RevisionRespuesta]:
    """Revisiones visibles para el rol actual (§11.2 `GET /revisiones`).

    Lectura simple sin orquestación de dominio —como `GET /cierres`
    (`adapters/api/v1/cierres.py`)—: consulta el repo directo, sin caso de uso,
    porque RLS ya acota el alcance (§12.4). Sin `exigir_rol`: el §11.2 pone la
    `(C)` solo sobre el alta, y la bandeja la ve quien vea la obra.
    """
    repo = RepositorioRevisionesSQL(sesion)
    filas = await repo.listar(obra_id=obra_id)
    return [RevisionRespuesta.desde_fila(fila) for fila in filas]
