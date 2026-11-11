"""Versiones de vano del catálogo (D-635; migración 0117): P-01 0.9×2.1, V-01 1.2×1.2… Valen para todas las obras de la
organización. Las lee cualquiera; las define Control de obra y Costos. Editar una versión no cambia los vanos ya puestos
(cada uno conserva sus medidas)."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.dependencias import ContextoActual, SesionRLS, exigir_rol
from obractrl.adapters.repos.vanos_version_sql import (
    PREFIJO_DEL_TIPO,
    RepositorioVanosVersionSQL,
)
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["vanos catalogo"])

ROLES_QUE_DEFINEN = (Rol.CONTROL_OBRA, Rol.COSTOS)
TipoDeVano = Literal["puerta", "ventana", "cancel", "arco", "paso", "castillo"]


class VersionDeVanoRespuesta(BaseModel):
    id: UUID
    tipo: TipoDeVano
    clave: str
    ancho_m: Decimal
    alto_m: Decimal
    antepecho_m: Decimal


class VersionNuevaPeticion(BaseModel):
    tipo: TipoDeVano
    copiar_de: UUID | None = Field(default=None, description="Una versión existente cuyas medidas se copian.")


class VersionCambioPeticion(BaseModel):
    clave: str | None = Field(default=None, min_length=1, max_length=20)
    ancho_m: Decimal | None = Field(default=None, gt=0, le=50)
    alto_m: Decimal | None = Field(default=None, gt=0, le=50)
    antepecho_m: Decimal | None = Field(default=None, ge=0, le=50)


@router.get("/vanos-version", response_model=list[VersionDeVanoRespuesta], summary="Las versiones de vano del catálogo")
async def listar_versiones(sesion: SesionRLS, ctx: ContextoActual, tipo: TipoDeVano | None = None) -> list[VersionDeVanoRespuesta]:
    """Si la organización aún no tiene ninguna, nace con las de partida (P-01…P-03, V-01, V-02, C-01, A-01, PS-01)."""
    repo = RepositorioVanosVersionSQL(sesion)
    if not await repo.hay_alguna():
        await repo.sembrar(ctx.usuario_id)
        await sesion.commit()
    return [VersionDeVanoRespuesta(**f) for f in await repo.listar(tipo)]


@router.post(
    "/vanos-version",
    response_model=VersionDeVanoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Una versión nueva copiando la elegida",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_DEFINEN))],
    responses={404: {"description": "La versión a copiar no existe."}},
)
async def crear_version(peticion: VersionNuevaPeticion, sesion: SesionRLS, ctx: ContextoActual) -> VersionDeVanoRespuesta:
    repo = RepositorioVanosVersionSQL(sesion)
    ancho, alto, antepecho = Decimal("0.9"), Decimal("2.1"), Decimal(0)
    if peticion.copiar_de is not None:
        base = await repo.obtener(peticion.copiar_de)
        if base is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "La versión a copiar no existe en tu alcance.")
        ancho, alto, antepecho = base["ancho_m"], base["alto_m"], base["antepecho_m"]
    prefijo = PREFIJO_DEL_TIPO[peticion.tipo]
    n = await repo.cuantas_del_tipo(peticion.tipo) + 1
    while await repo.clave_en_uso(f"{prefijo}-{n:02d}"):
        n += 1
    clave = f"{prefijo}-{n:02d}"
    version_id = await repo.crear(
        tipo=peticion.tipo, clave=clave, ancho_m=ancho, alto_m=alto, antepecho_m=antepecho, autor_id=ctx.usuario_id
    )
    await sesion.commit()
    return VersionDeVanoRespuesta(**(await repo.obtener(version_id) or {}))


@router.patch(
    "/vanos-version/{version_id}",
    response_model=VersionDeVanoRespuesta,
    summary="Cambiar la clave o las medidas de una versión (cambia el catálogo)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_DEFINEN))],
    responses={404: {"description": "La versión no existe."}, 422: {"description": "Esa clave ya existe."}},
)
async def cambiar_version(version_id: UUID, peticion: VersionCambioPeticion, sesion: SesionRLS) -> VersionDeVanoRespuesta:
    repo = RepositorioVanosVersionSQL(sesion)
    if await repo.obtener(version_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La versión no existe en tu alcance.")
    cambios = peticion.model_dump(exclude_none=True)
    if "clave" in cambios:
        cambios["clave"] = cambios["clave"].strip().upper()
        if await repo.clave_en_uso(cambios["clave"], salvo=version_id):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Ya existe la versión {cambios['clave']}.")
    await repo.actualizar(version_id, cambios)
    await sesion.commit()
    return VersionDeVanoRespuesta(**(await repo.obtener(version_id) or {}))


@router.delete(
    "/vanos-version/{version_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Quitar una versión del catálogo (queda al menos una de cada tipo)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_DEFINEN))],
    responses={404: {"description": "La versión no existe."}, 422: {"description": "Es la única de su tipo."}},
)
async def quitar_version(version_id: UUID, sesion: SesionRLS) -> None:
    repo = RepositorioVanosVersionSQL(sesion)
    version = await repo.obtener(version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La versión no existe en tu alcance.")
    if await repo.cuantas_del_tipo(version["tipo"]) <= 1:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Es la única versión de su tipo: queda al menos una.")
    await repo.eliminar(version_id)
    await sesion.commit()
