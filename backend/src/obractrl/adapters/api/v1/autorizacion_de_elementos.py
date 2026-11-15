"""Endpoints de las versiones y la autorización de los elementos y sus conceptos (plan de elementos de muro, fase I; 0130).

**Costos propone y Control de obra autoriza.** Lo que Costos da de alta o cambia queda pendiente; Control de obra lo autoriza (y
nace la versión siguiente, con quién propuso, quién autorizó y cuándo) o lo rechaza. Los cambios de Control de obra se aplican al
momento y quedan como versión. «Confirmar cálculo → actualizar APU» lleva los coeficientes del cálculo del elemento al APU del
concepto (el APU manda; ±3 % es solo un aviso) y la conciliación compara, en las dos direcciones, el estimado por APU con la salida
de material del cálculo. Controladores delgados.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    ActualizarApuDesdeElementoDep,
    AutorizarElementosDep,
)
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["elementos parametricos"])

ROLES_QUE_PROPONEN = (Rol.CONTROL_OBRA, Rol.COSTOS)
ROLES_QUE_AUTORIZAN = (Rol.CONTROL_OBRA,)

_RESPUESTAS_DE_AUTORIZAR = {
    403: {"description": "Solo Control de obra autoriza."},
    404: {"description": "No existe o está fuera de tu alcance."},
    422: {"description": "Ya fue decidido, o el cambio ya no es válido."},
}

Clase = Literal["elemento", "concepto", "apu"]
EstadoDeLaRevision = Literal["pendiente", "autorizada", "rechazada"]


class VersionDeElemento(BaseModel):
    id: UUID
    clase: Clase = Field(description="Qué cambió: el elemento, un concepto nuevo del elemento o el APU de un concepto.")
    estado: EstadoDeLaRevision
    version: int | None = Field(description="El número de la versión; `null` mientras la propuesta está pendiente o si se rechazó.")
    fila_id: UUID | None = Field(description="El concepto del elemento al que se refiere; `null` si es del elemento.")
    concepto_clave: str | None
    resumen: str
    propuso_id: UUID | None
    propuso_nombre: str | None
    propuso_rol: str | None
    propuesto_en: datetime
    decidio_id: UUID | None
    decidio_nombre: str | None
    decidio_rol: str | None
    decidido_en: datetime | None
    motivo: str | None = Field(description="Por qué se rechazó.")


class AutorizacionDelElemento(BaseModel):
    elemento_id: UUID
    estado: Literal["autorizado", "pendiente"]
    version: int | None = Field(description="La última versión autorizada del elemento; `null` si aún no tiene.")
    versiones: list[VersionDeElemento] = Field(description="Propuestas y versiones del elemento y de sus conceptos, de la más nueva a la más vieja.")


class PendienteDeAutorizar(BaseModel):
    tipo: Literal["revision", "elemento_nuevo", "concepto_nuevo"]
    ref: UUID = Field(description="La propuesta (`revision`), el elemento (`elemento_nuevo`) o el concepto del elemento (`concepto_nuevo`).")
    elemento_id: UUID
    elemento_clave: str
    elemento_nombre: str
    fila_id: UUID | None
    concepto_clave: str | None
    clase: Clase
    resumen: str
    propuso_nombre: str | None
    desde: datetime


class VersionAutorizada(BaseModel):
    version: int


class RechazoPeticion(BaseModel):
    motivo: str | None = Field(default=None, max_length=300)


class FilaDelPlanDeApu(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    apu: float | None = Field(description="Lo que el APU lleva del insumo por unidad del concepto (con los auxiliares expandidos).")
    calculo: float | None = Field(description="Lo que calcula el elemento por unidad del concepto.")
    diferencia_pct: float | None
    marca: Literal["=", "≈", "≠", "solo_catalogo", "solo_elemento"]
    accion: Literal["sin_cambio", "actualizar", "agregar", "en_auxiliar", "solo_apu", "sin_insumo"] = Field(
        description="Qué haría confirmar el cálculo con este insumo."
    )
    motivo: str


class PlanDeApuRespuesta(BaseModel):
    fila_id: UUID
    concepto_clave: str
    concepto_descripcion: str
    unidad: str
    sin_catalogo: bool = Field(description="Concepto nuevo: no tiene APU en el catálogo.")
    manda: Literal["apu"]
    filas: list[FilaDelPlanDeApu]
    avisos: list[str]
    hay_cambios: bool
    pu_vigente: float | None = Field(description="El precio unitario del APU vigente.")
    pu_con_el_calculo: float | None = Field(description="El precio unitario si se confirma el cálculo.")
    propuesta_pendiente: UUID | None = Field(description="Hay una propuesta de actualización esperando a Control de obra.")


class ConfirmarApuRespuesta(BaseModel):
    aplicado: bool = Field(description="`true` si el APU ya cambió (Control de obra); `false` si quedó propuesto (Costos).")
    revision_id: UUID
    version: int | None
    resumen: str
    pu_antes: float
    pu_despues: float


class FilaDeConciliacion(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    estimado: float | None = Field(description="Cantidad × lo que lleva el APU.")
    salida: float | None = Field(description="Cantidad × lo que calcula el elemento.")
    diferencia_cantidad: float | None
    diferencia_pct: float | None
    costo: float | None
    importe_apu: float | None
    importe_salida: float | None
    diferencia_importe: float | None
    marca: Literal["=", "≈", "≠", "solo_catalogo", "solo_elemento"]
    sentido: Literal["se_justifican", "difieren", "estimado_sin_salida", "salida_sin_estimado"]
    avisa: bool = Field(description="Fuera de ±3 %: solo un aviso visual.")


class ConciliacionRespuesta(BaseModel):
    fila_id: UUID
    concepto_clave: str
    unidad: str
    sin_catalogo: bool
    cantidad: float
    manda: Literal["apu"]
    tolerancia_pct: float
    filas: list[FilaDeConciliacion]
    importe_apu: float
    importe_salida: float
    sin_precio: bool = Field(description="Algún insumo no tiene precio: su importe queda vacío (no se inventa).")
    resumen: dict[str, int]
    avisos: list[str]


@router.get(
    "/elementos-parametricos/{elemento_id}/autorizacion",
    response_model=AutorizacionDelElemento,
    summary="El estado de autorización del elemento y su historial de propuestas y versiones",
    responses={404: {"description": "El elemento no existe o está fuera de tu alcance."}},
)
async def autorizacion_del_elemento(elemento_id: UUID, caso_uso: AutorizarElementosDep) -> AutorizacionDelElemento:
    h = await caso_uso.historial(elemento_id)
    return AutorizacionDelElemento(
        elemento_id=elemento_id,
        estado=h["estado"],
        version=h["version"],
        versiones=[VersionDeElemento(**{k: v for k, v in f.items() if k in VersionDeElemento.model_fields}) for f in h["versiones"]],
    )


@router.get(
    "/autorizaciones-pendientes",
    response_model=list[PendienteDeAutorizar],
    summary="Todo lo que espera la autorización de Control de obra: elementos, conceptos y propuestas",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_PROPONEN))],
    responses={403: {"description": "Lo ven Control de obra y Costos."}},
)
async def autorizaciones_pendientes(caso_uso: AutorizarElementosDep) -> list[PendienteDeAutorizar]:
    return [
        PendienteDeAutorizar(**{k: v for k, v in f.items() if k in PendienteDeAutorizar.model_fields})
        for f in await caso_uso.pendientes()
    ]


@router.post(
    "/elementos-parametricos/{elemento_id}/autorizar",
    response_model=VersionAutorizada,
    summary="Autorizar un elemento nuevo que propuso Costos: queda como su versión 1",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_AUTORIZAN))],
    responses=_RESPUESTAS_DE_AUTORIZAR,
)
async def autorizar_elemento(elemento_id: UUID, ctx: ContextoActual, caso_uso: AutorizarElementosDep) -> VersionAutorizada:
    return VersionAutorizada(version=await caso_uso.autorizar_elemento(elemento_id, usuario_id=ctx.usuario_id, rol=ctx.rol))


@router.post(
    "/elementos-parametricos/{elemento_id}/conceptos-por-contexto/{fila_id}/autorizar",
    response_model=VersionAutorizada,
    summary="Autorizar un concepto nuevo del elemento: entra al catálogo sin precio y desde aquí cuenta en el presupuesto",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_AUTORIZAN))],
    responses=_RESPUESTAS_DE_AUTORIZAR,
)
async def autorizar_concepto_del_elemento(
    elemento_id: UUID, fila_id: UUID, ctx: ContextoActual, caso_uso: AutorizarElementosDep
) -> VersionAutorizada:
    return VersionAutorizada(version=await caso_uso.autorizar_concepto(elemento_id, fila_id, usuario_id=ctx.usuario_id, rol=ctx.rol))


@router.post(
    "/revisiones-de-elementos/{revision_id}/autorizar",
    response_model=VersionAutorizada,
    summary="Autorizar la propuesta de Costos (un cambio del elemento o la actualización de un APU): se aplica y nace la versión",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_AUTORIZAN))],
    responses=_RESPUESTAS_DE_AUTORIZAR,
)
async def autorizar_revision(revision_id: UUID, ctx: ContextoActual, caso_uso: AutorizarElementosDep) -> VersionAutorizada:
    return VersionAutorizada(version=await caso_uso.autorizar_revision(revision_id, usuario_id=ctx.usuario_id, rol=ctx.rol))


@router.post(
    "/revisiones-de-elementos/{revision_id}/rechazar",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Rechazar la propuesta de Costos: no se aplica y queda en el historial",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_AUTORIZAN))],
    responses=_RESPUESTAS_DE_AUTORIZAR,
)
async def rechazar_revision(revision_id: UUID, peticion: RechazoPeticion, ctx: ContextoActual, caso_uso: AutorizarElementosDep) -> None:
    await caso_uso.rechazar_revision(revision_id, usuario_id=ctx.usuario_id, rol=ctx.rol, motivo=peticion.motivo)


@router.get(
    "/elementos-parametricos/{elemento_id}/conceptos-por-contexto/{fila_id}/apu",
    response_model=PlanDeApuRespuesta,
    summary="Lo que haría «Confirmar cálculo → actualizar APU»: el APU contra el cálculo del elemento, insumo por insumo",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_PROPONEN))],
    responses={403: {"description": "Lo ven Control de obra y Costos."}, 404: {"description": "No existe o está fuera de tu alcance."}},
)
async def plan_de_apu(elemento_id: UUID, fila_id: UUID, caso_uso: ActualizarApuDesdeElementoDep) -> PlanDeApuRespuesta:
    return PlanDeApuRespuesta(**await caso_uso.plan(elemento_id, fila_id))


@router.post(
    "/elementos-parametricos/{elemento_id}/conceptos-por-contexto/{fila_id}/apu/confirmar",
    response_model=ConfirmarApuRespuesta,
    summary="Confirmar el cálculo del elemento y actualizar el APU del concepto (Control de obra lo aplica; Costos lo propone)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_PROPONEN))],
    responses={
        403: {"description": "Lo hacen Control de obra y Costos."},
        404: {"description": "No existe o está fuera de tu alcance."},
        422: {"description": "El concepto es nuevo (sin APU), el cálculo ya coincide con el APU o hay una propuesta pendiente."},
    },
)
async def confirmar_calculo(
    elemento_id: UUID, fila_id: UUID, ctx: ContextoActual, caso_uso: ActualizarApuDesdeElementoDep
) -> ConfirmarApuRespuesta:
    return ConfirmarApuRespuesta(**await caso_uso.confirmar(elemento_id, fila_id, usuario_id=ctx.usuario_id, rol=ctx.rol))


@router.get(
    "/elementos-parametricos/{elemento_id}/conceptos-por-contexto/{fila_id}/conciliacion",
    response_model=ConciliacionRespuesta,
    summary="Conciliación en las dos direcciones: el estimado por APU contra la salida de material del cálculo del elemento",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_PROPONEN))],
    responses={403: {"description": "Lo ven Control de obra y Costos."}, 404: {"description": "No existe o está fuera de tu alcance."}},
)
async def conciliacion_del_concepto(
    elemento_id: UUID,
    fila_id: UUID,
    caso_uso: ActualizarApuDesdeElementoDep,
    cantidad: float = Query(default=1.0, gt=0, le=1_000_000, description="Cuántas unidades del concepto (m², ml, pza) se concilian."),
) -> ConciliacionRespuesta:
    return ConciliacionRespuesta(**await caso_uso.conciliacion(elemento_id, fila_id, cantidad))
