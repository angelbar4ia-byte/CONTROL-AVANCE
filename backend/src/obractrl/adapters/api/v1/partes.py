"""Las partes de una obra y sus plantas (migración 0074; cerebro D-571, D-575).

Una **parte** es una etapa de construcción o un concepto independiente (losas, pisos): lo que
los escenarios de arranque envían, autorizan y programan por separado. Las plantas (1 o 2)
fijan el catálogo base de cuantificación y el plazo base del programa.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    CambiarEstadoDePartesDep,
    ConsultarBitacoraDePartesDep,
    ConsultarPartesDep,
    FijarPlantasDeObraDep,
    FijarPlantasDePrototipoDep,
    MarcarParteIndependienteDep,
)
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.adapters.api.idempotencia import Idempotencia
from obractrl.application.casos_uso.gestionar_partes import ComandoCambiarEstadoDePartes
from obractrl.domain.partes.estado import Accion, EstadoDeParte
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["partes"])


class ParteRespuesta(BaseModel):
    clave: str = Field(description="`etapa:<id>`, `concepto:<id>` o `sin_etapa:-`.")
    tipo: str = Field(description="`etapa` · `concepto` (independiente) · `sin_etapa`.")
    id: UUID | None = Field(default=None, description="La etapa o la actividad independiente.")
    nombre: str
    estado: str = Field(
        description=(
            "`cuantificando` · `enviada_presupuesto` · `por_validar` · `autorizada` · "
            "`enviada_programa` · `programada` · `asignada`. Sin renglón: `cuantificando`."
        )
    )
    n_actividades: int
    actividad_ids: list[UUID]
    importe: Decimal
    avance_pct: Decimal = Field(description="Ponderado por importe, como el de la obra.")


class PartesDeObraRespuesta(BaseModel):
    obra_id: UUID
    plantas: int | None = Field(default=None, description="1 o 2; nace del prototipo.")
    plantas_del_prototipo: int | None = None
    partes: list[ParteRespuesta]


class ParteIndependientePeticion(BaseModel):
    independiente: bool = Field(
        description="`true`: la actividad es una parte por sí sola (losa, piso…)."
    )


class PlantasPeticion(BaseModel):
    plantas: int | None = Field(default=None, description="1 o 2; `null` la deja sin decir.")


class CambiarEstadoPeticion(BaseModel):
    accion: Accion = Field(description="Qué se hace con las partes.")
    claves: list[str] = Field(default_factory=list, description="Las partes (por `clave`).")
    todas: bool = Field(
        default=False,
        description="Todas las partes que están en el paso que la acción pide («el total»).",
    )
    a: EstadoDeParte | None = Field(
        default=None, description="Solo `devolver`: el paso anterior al que se vuelve."
    )
    nota: str | None = None


class PasoDeParteRespuesta(BaseModel):
    clave: str
    de: str
    a: str


class TransicionDeParteRespuesta(BaseModel):
    id: UUID
    clave: str
    accion: str
    de: str
    a: str
    usuario_id: UUID
    usuario_nombre: str | None = None
    rol: str
    nota: str | None = None
    creada_en: datetime


_NO_ENCONTRADO = {404: {"description": "No existe o está fuera de tu alcance (§12.4)."}}


@router.get(
    "/obras/{obra_id}/partes",
    response_model=PartesDeObraRespuesta,
    summary="Las partes de una obra: etapas y conceptos independientes",
    responses=_NO_ENCONTRADO,
)
async def partes_de_la_obra(obra_id: UUID, caso_uso: ConsultarPartesDep) -> PartesDeObraRespuesta:
    """Todos los roles, cada uno con su alcance (RLS)."""
    return PartesDeObraRespuesta(**await caso_uso.ejecutar(obra_id))


@router.put(
    "/actividades/{actividad_id}/parte-independiente",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Una actividad es una parte por sí sola, o vuelve a viajar con su etapa",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.SUPERVISOR))],
    responses=_NO_ENCONTRADO,
)
async def marcar_parte_independiente(
    actividad_id: UUID, peticion: ParteIndependientePeticion, caso_uso: MarcarParteIndependienteDep
) -> None:
    await caso_uso.ejecutar(actividad_id, peticion.independiente)


@router.put(
    "/obras/{obra_id}/plantas",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Las plantas de la obra (1 o 2)",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA))],
    responses={**_NO_ENCONTRADO, 422: {"description": "Una casa tiene 1 o 2 plantas."}},
)
async def fijar_plantas_de_obra(
    obra_id: UUID, peticion: PlantasPeticion, caso_uso: FijarPlantasDeObraDep
) -> None:
    await caso_uso.ejecutar(obra_id, peticion.plantas)


@router.put(
    "/prototipos/{prototipo_id}/plantas",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Las plantas del prototipo (1 o 2)",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA))],
    responses={**_NO_ENCONTRADO, 422: {"description": "Una casa tiene 1 o 2 plantas."}},
)
async def fijar_plantas_de_prototipo(
    prototipo_id: UUID, peticion: PlantasPeticion, caso_uso: FijarPlantasDePrototipoDep
) -> None:
    await caso_uso.ejecutar(prototipo_id, peticion.plantas)


@router.post(
    "/obras/{obra_id}/partes/transicion",
    response_model=list[PasoDeParteRespuesta],
    summary="Mandar, autorizar, validar, programar, asignar o devolver partes",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.SUPERVISOR)), Idempotencia],
    responses={
        **_NO_ENCONTRADO,
        403: {"description": "Tu rol no puede hacer esa acción sobre una parte."},
        409: {"description": "Una parte no está en el paso que la acción pide (no se escribe ninguna)."},
    },
)
async def cambiar_estado_de_partes(
    obra_id: UUID,
    peticion: CambiarEstadoPeticion,
    ctx: ContextoActual,
    caso_uso: CambiarEstadoDePartesDep,
) -> list[PasoDeParteRespuesta]:
    """Una, varias o todas («total o por partes»). Todo o nada: si una parte no puede dar el
    paso, no se escribe ninguna. Cada paso queda en la bitácora."""
    pasos = await caso_uso.ejecutar(
        ComandoCambiarEstadoDePartes(
            obra_id=obra_id,
            accion=peticion.accion,
            usuario_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
            claves=tuple(peticion.claves),
            todas=peticion.todas,
            a=peticion.a,
            nota=peticion.nota,
        )
    )
    return [PasoDeParteRespuesta(**p) for p in pasos]


@router.get(
    "/obras/{obra_id}/partes/bitacora",
    response_model=list[TransicionDeParteRespuesta],
    summary="Bitácora de las partes: quién mandó, autorizó o devolvió qué",
    responses=_NO_ENCONTRADO,
)
async def bitacora_de_partes(
    obra_id: UUID, caso_uso: ConsultarBitacoraDePartesDep
) -> list[TransicionDeParteRespuesta]:
    """Todos los roles, cada uno con su alcance. Lo más reciente, primero. No se edita."""
    return [TransicionDeParteRespuesta(**f) for f in await caso_uso.ejecutar(obra_id)]
