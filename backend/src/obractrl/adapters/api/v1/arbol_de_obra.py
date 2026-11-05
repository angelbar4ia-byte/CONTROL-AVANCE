"""Endpoints del árbol propio de una obra y las versiones de su presupuesto (D-624; migración 0107).

Control de obra y Costos. Solo una obra con árbol propio (un prototipo de un solo uso) se edita; el prototipo base es
compartido y no se toca. Controladores delgados.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import ArbolDeObraDep
from obractrl.adapters.api.dependencias import exigir_rol
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["arbol de la obra"])

_ROL = [Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.COSTOS))]
_RESPUESTAS = {
    403: {"description": "Lo hacen Control de obra y Costos."},
    404: {"description": "La obra no existe o está fuera de tu alcance."},
    409: {"description": "La parte ya está asignada, o el nodo ya generó partidas."},
    422: {"description": "El nodo no va ahí, falta un dato, o la obra no tiene árbol propio."},
}


class NodoDeArbolDeObraRespuesta(BaseModel):
    id: UUID
    parent_id: UUID | None
    tipo: str
    nombre: str
    clave: str | None
    concepto_id: UUID | None
    concepto_clave: str | None
    concepto_descripcion: str | None
    unidad: str | None
    orden: int
    cantidad: Decimal | None


class VersionDelPresupuestoRespuesta(BaseModel):
    id: UUID
    version: int
    estado: Literal["borrador", "confirmada"]
    vigente: bool
    nota: str | None
    monto_total: Decimal
    partidas: int


class ArbolDeLaObraRespuesta(BaseModel):
    propio: bool = Field(description="La obra tiene su árbol propio (editable); si no, usa el del prototipo base.")
    prototipo_id: UUID
    prototipo_clave: str
    prototipo_nombre: str
    borrador_id: UUID | None
    versiones: list[VersionDelPresupuestoRespuesta]
    nodos: list[NodoDeArbolDeObraRespuesta]


class ArbolPropioCreadoRespuesta(BaseModel):
    prototipo_id: UUID
    clave: str
    nodos: int
    partidas_religadas: int


class NodoPeticion(BaseModel):
    tipo: Literal["nivel", "etapa", "concepto"]
    parent_id: UUID | None = None
    nombre: str | None = Field(default=None, max_length=120)
    concepto_id: UUID | None = None


class NodoCreadoRespuesta(BaseModel):
    id: UUID


class AjusteDeNodoPeticion(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=120)
    orden: int | None = Field(default=None, ge=0, le=100000)


class ConfirmarVersionPeticion(BaseModel):
    nota: str | None = Field(default=None, max_length=300, description="Lo que cambió («se agregó la cocina»).")


@router.get("/obras/{obra_id}/arbol", response_model=ArbolDeLaObraRespuesta, summary="El árbol de la obra y las versiones de su presupuesto", responses=_RESPUESTAS)
async def ver_arbol(obra_id: UUID, caso_uso: ArbolDeObraDep) -> ArbolDeLaObraRespuesta:
    return ArbolDeLaObraRespuesta(**await caso_uso.ver(obra_id))


@router.post(
    "/obras/{obra_id}/arbol/propio",
    response_model=ArbolPropioCreadoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Crear el árbol propio de la obra: se clona el del prototipo y su presupuesto vigente",
    dependencies=_ROL,
    responses=_RESPUESTAS,
)
async def crear_arbol_propio(obra_id: UUID, caso_uso: ArbolDeObraDep) -> ArbolPropioCreadoRespuesta:
    """El prototipo base no se toca; la obra pasa a la copia y sus partidas se re-ligan a los nodos copiados."""
    return ArbolPropioCreadoRespuesta(**await caso_uso.crear_propio(obra_id))


@router.post(
    "/obras/{obra_id}/arbol/nodos",
    response_model=NodoCreadoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar un nivel, una etapa o un concepto al árbol propio",
    dependencies=_ROL,
    responses=_RESPUESTAS,
)
async def agregar_nodo(obra_id: UUID, peticion: NodoPeticion, caso_uso: ArbolDeObraDep) -> NodoCreadoRespuesta:
    """El primer cambio crea el borrador del presupuesto. Un concepto entra sin cantidad y con su precio vigente."""
    nodo = await caso_uso.crear_nodo(
        obra_id, tipo=peticion.tipo, parent_id=peticion.parent_id, nombre=peticion.nombre, concepto_id=peticion.concepto_id
    )
    return NodoCreadoRespuesta(id=nodo)


@router.patch(
    "/obras/{obra_id}/arbol/nodos/{nodo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Renombrar un nodo o cambiar su lugar entre sus hermanos",
    dependencies=_ROL,
    responses=_RESPUESTAS,
)
async def ajustar_nodo(obra_id: UUID, nodo_id: UUID, peticion: AjusteDeNodoPeticion, caso_uso: ArbolDeObraDep) -> None:
    await caso_uso.ajustar_nodo(obra_id, nodo_id, nombre=peticion.nombre, orden=peticion.orden)


@router.delete(
    "/obras/{obra_id}/arbol/nodos/{nodo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Quitar un nodo (con todo lo que cuelga de él) del árbol propio",
    dependencies=_ROL,
    responses=_RESPUESTAS,
)
async def quitar_nodo(obra_id: UUID, nodo_id: UUID, caso_uso: ArbolDeObraDep) -> None:
    await caso_uso.eliminar_nodo(obra_id, nodo_id)


@router.post(
    "/obras/{obra_id}/arbol/versiones/confirmar",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Confirmar el borrador del presupuesto: queda fijo",
    dependencies=_ROL,
    responses=_RESPUESTAS,
)
async def confirmar_version(obra_id: UUID, peticion: ConfirmarVersionPeticion, caso_uso: ArbolDeObraDep) -> None:
    await caso_uso.confirmar(obra_id, peticion.nota)


@router.post(
    "/obras/{obra_id}/arbol/versiones/{presupuesto_id}/activar",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Fijar una versión confirmada como la activa del presupuesto de la obra",
    dependencies=_ROL,
    responses=_RESPUESTAS,
)
async def activar_version(obra_id: UUID, presupuesto_id: UUID, caso_uso: ArbolDeObraDep) -> None:
    await caso_uso.activar(obra_id, presupuesto_id)


class EliminarObraPeticion(BaseModel):
    clave: str = Field(min_length=1, description="La clave de la obra, escrita: la segunda confirmación.")


@router.post(
    "/obras/{obra_id}/eliminar",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar una obra que sigue en diseño (nada programado ni asignado)",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA))],
    responses={
        **_RESPUESTAS,
        409: {"description": "La obra ya tiene partes programadas o asignadas, avance o estimaciones."},
        422: {"description": "La clave escrita no es la de la obra."},
    },
)
async def eliminar_obra(obra_id: UUID, peticion: EliminarObraPeticion, caso_uso: ArbolDeObraDep) -> None:
    """Borra la obra con todo lo suyo (planos, trazos, partidas, programa); si tenía un árbol propio, también ese árbol."""
    await caso_uso.eliminar_obra(obra_id, peticion.clave)


class ObraReiniciadaRespuesta(BaseModel):
    trazos: int = Field(description="Trazos borrados de los planos.")
    actividades: int = Field(description="Partidas borradas.")
    volvio_al_base: bool = Field(description="La obra volvió al prototipo base y su árbol propio se borró.")


@router.post(
    "/obras/{obra_id}/reiniciar",
    response_model=ObraReiniciadaRespuesta,
    summary="Reiniciar desde cero una obra que sigue en diseño",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA))],
    responses={
        **_RESPUESTAS,
        409: {"description": "La obra ya tiene partes programadas o asignadas, avance o estimaciones."},
        422: {"description": "La clave escrita no es la de la obra."},
    },
)
async def reiniciar_obra(obra_id: UUID, peticion: EliminarObraPeticion, caso_uso: ArbolDeObraDep) -> ObraReiniciadaRespuesta:
    """La obra se queda con su cluster y sus planos; se borra lo diseñado encima (partidas, programa, trazos, estados).
    Si tenía un árbol propio copiado de un prototipo base, vuelve a ese prototipo."""
    r = await caso_uso.reiniciar_obra(obra_id, peticion.clave)
    return ObraReiniciadaRespuesta(trazos=r["trazos"], actividades=r["actividades"], volvio_al_base=bool(r["volvio_al_base"]))
