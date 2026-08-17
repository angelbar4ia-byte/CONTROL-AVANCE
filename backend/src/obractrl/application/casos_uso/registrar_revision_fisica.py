"""Caso de uso: registrar una revisión física en campo.

Spec §7.8 (`RevisionFisica`) · §11.2 ("Revisión física (móvil · Control de
obra)": `POST /obras/{id}/revisiones`) · §12.11 (capa de aplicación).

Secuencia lineal, como `registrar_salida_almacen.py`: el dominio valida
—rol y escala de calidad, `domain.revisiones.reglas`— y el repo persiste. No
hay máquina de estados porque el §7.8 no le define ciclo de vida a la
revisión.

La bandeja `GET /revisiones` no tiene caso de uso: es lectura directa del
repo, como `GET /cierres` (`adapters/api/v1/cierres.py`), porque RLS ya acota
el alcance (§12.4) y no hay nada de dominio que orquestar.

Las **fotos llegan como URLs ya subidas**, no como archivos: el móvil pide una
presigned URL (`POST /evidencias/presigned`, §11.2) y sube directo a R2 en
segundo plano; el binario nunca viaja por la API (§12.2 "las fotos se guardan
local y se suben directo a R2 en segundo plano (no viajan por la API)").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from obractrl.application.puertos.repositorios import (
    RepositorioRevisiones,
    UnidadDeTrabajo,
)
from obractrl.domain.revisiones.reglas import ErrorDeRevision, RevisionFisica
from obractrl.domain.shared.diccionario import Rol

__all__ = [
    "ComandoRegistrarRevision",
    "ErrorDeRevision",
    "RegistrarRevisionFisica",
    "RevisionRegistrada",
]


@dataclass(frozen=True, slots=True)
class ComandoRegistrarRevision:
    obra_id: UUID
    usuario_id: UUID
    rol: Rol
    fecha: date
    fotos: list[str] = field(default_factory=list)
    comentario: str | None = None
    calidad: int | None = None
    actividad_id: UUID | None = None
    incidencia_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class RevisionRegistrada:
    id: UUID
    revision: RevisionFisica


class RegistrarRevisionFisica:
    """Control de obra captura la revisión en campo (§11.2, §2 glosario)."""

    def __init__(
        self, *, revisiones: RepositorioRevisiones, uow: UnidadDeTrabajo
    ) -> None:
        self._revisiones = revisiones
        self._uow = uow

    async def ejecutar(self, cmd: ComandoRegistrarRevision) -> RevisionRegistrada:
        revision = RevisionFisica.registrar(
            obra_id=str(cmd.obra_id),
            usuario_id=str(cmd.usuario_id),
            rol=cmd.rol,
            fecha=cmd.fecha,
            fotos=cmd.fotos,
            comentario=cmd.comentario,
            calidad=cmd.calidad,
            actividad_id=str(cmd.actividad_id) if cmd.actividad_id else None,
            incidencia_id=str(cmd.incidencia_id) if cmd.incidencia_id else None,
        )

        async with self._uow:
            revision_id = await self._revisiones.crear(
                obra_id=cmd.obra_id,
                usuario_id=cmd.usuario_id,
                fecha=revision.fecha,
                fotos=revision.fotos,
                comentario=revision.comentario,
                calidad=revision.calidad,
                actividad_id=cmd.actividad_id,
                incidencia_id=cmd.incidencia_id,
            )
            await self._uow.commit()

        return RevisionRegistrada(id=revision_id, revision=revision)
