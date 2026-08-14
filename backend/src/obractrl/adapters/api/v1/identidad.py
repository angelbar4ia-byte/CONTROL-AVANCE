"""Endpoints de identidad.

Spec §11.2 (Identidad y organización).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import text

from obractrl.adapters.api.dependencias import ContextoActual, SesionRLS

router = APIRouter(tags=["identidad"])


class PerfilRespuesta(BaseModel):
    """Perfil, rol y alcance del usuario del token (§11.2 `GET /me`)."""

    id: UUID
    nombre: str
    email: str
    rol: str = Field(description="residente | supervisor | control_obra | super_intendente")
    org_id: UUID
    org_nombre: str
    obras_en_alcance: int = Field(
        description="Cuántas obras ve este usuario; lo determina RLS, no la API."
    )


@router.get("/me", response_model=PerfilRespuesta, summary="Perfil y alcance")
async def obtener_perfil(ctx: ContextoActual, sesion: SesionRLS) -> PerfilRespuesta:
    """Devuelve el perfil del token y su alcance efectivo.

    El conteo de obras sale de una consulta normal: RLS ya filtra por rol, así
    que el número es el alcance real y no hay que calcularlo en la API (§12.4).
    """
    fila = (
        await sesion.execute(
            text(
                """
                select u.id, u.nombre, u.email, u.rol,
                       o.id as org_id, o.nombre as org_nombre,
                       (select count(*) from obra) as obras
                from usuario u
                join organizacion o on o.id = u.org_id
                where u.id = :usuario_id
                """
            ),
            {"usuario_id": str(ctx.usuario_id)},
        )
    ).first()

    if fila is None:  # pragma: no cover - el JWT ya validó al usuario
        raise LookupError("El usuario del token no existe en la organización.")

    return PerfilRespuesta(
        id=fila.id,
        nombre=fila.nombre,
        email=fila.email,
        rol=fila.rol,
        org_id=fila.org_id,
        org_nombre=fila.org_nombre,
        obras_en_alcance=fila.obras,
    )
