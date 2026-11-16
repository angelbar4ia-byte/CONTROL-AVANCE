"""Endpoints de los elementos de estructura de la biblioteca: castillos K-1 a K-8, aparentes y columnas forjadas (Ola 3, 3A).

El cálculo vive en el dominio (`estructura_de_catalogo`, con la receta del acero); aquí solo se valida la entrada y se devuelve el
resultado. `calcular` no guarda nada. Las correcciones al catálogo se proponen como **nuevas versiones de concepto** que solo
Control de obra autoriza (`propuesta_de_estructura`, 0131): el catálogo no se edita. Controladores delgados.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    DriversDeObraDep,
    GestionarPropuestasDeEstructuraDep,
)
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.adapters.api.v1.drivers_usados import (
    DriverUsadoRespuesta,
    a_respuesta,
    explicitos_de_receta,
)
from obractrl.adapters.api.v1.receta_acero import (
    DriversDeRecetaPeticion,
    RecetaDeAceroCalculada,
)
from obractrl.domain.cuantificacion.drivers_de_elementos import (
    altura_de_obra,
    desperdicio_concreto_de_obra,
    receta_de_obra,
)
from obractrl.domain.cuantificacion.estructura_de_catalogo import (
    ElementoDeEstructuraNoEncontrado,
    ErrorDeEstructura,
    calcular_elemento,
    definicion_de,
)
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["biblioteca de elementos"])

ROLES_QUE_PROPONEN = (Rol.CONTROL_OBRA, Rol.COSTOS)
ROLES_QUE_AUTORIZAN = (Rol.CONTROL_OBRA,)
Marca = Literal["=", "≈", "≠", "solo_catalogo", "solo_elemento"]


class ClaveYNombreDeEstructura(BaseModel):
    clave: str
    nombre: str


class SeccionDeEstructura(BaseModel):
    ancho_cm: float = Field(description="El espesor del muro (castillo) o el ancho de la cadena.")
    largo_cm: float | None = Field(description="El largo de la sección del castillo; `null` en una cadena.")
    peralte_cm: float | None = Field(description="El peralte de la cadena; `null` en un castillo.")


class VarillaDelArmado(BaseModel):
    cantidad: int
    numero: int
    insumo: str


class AnilloDelArmado(BaseModel):
    insumo: str | None
    sep_cm: float | None


class ArmadoDeEstructura(BaseModel):
    tipo: Literal["armex", "varillas"]
    armex: str | None
    varillas: list[VarillaDelArmado]
    anillo: AnilloDelArmado | None
    alambre_kg_ml: float | None


class EscalonDeEstructura(BaseModel):
    clave: str
    hasta_m: float


class ConceptoDeLaDefinicion(BaseModel):
    ranura: Literal["acero", "colado", "completo"]
    unidad: str
    clave: str | None
    nuevo: bool = Field(description="Concepto que el catálogo no trae: queda propuesto, pendiente de autorizar.")
    escalones: list[EscalonDeEstructura]


class DefinicionDeEstructura(BaseModel):
    clave: str
    alias: str | None
    nombre: str
    tipo: Literal["castillo", "lineal"]
    categoria: ClaveYNombreDeEstructura
    subcategoria: ClaveYNombreDeEstructura
    seccion: SeccionDeEstructura
    posicion: str | None
    alto_fijo_m: float | None = Field(description="La forjada tiene alto fijo (4.20 m); otra altura es un concepto nuevo.")
    alto_por_defecto_m: float
    armado: ArmadoDeEstructura
    conceptos: list[ConceptoDeLaDefinicion]
    pendientes: list[str]
    fuente: str


class CalculoDeEstructuraPeticion(BaseModel):
    alto_m: float | None = Field(
        default=None, gt=0, le=30, description="Alto en METROS; vacío usa la altura estándar de 3.00 m (4.20 m en la forjada)."
    )
    drivers: DriversDeRecetaPeticion = Field(default_factory=DriversDeRecetaPeticion)
    obra_id: UUID | None = Field(
        default=None,
        description="La obra cuyos drivers (Paramétrico) se leen. Precedencia: lo que manda la petición > el driver de la obra > el valor por defecto. Sin obra, todo vale lo de siempre.",
    )


class ConceptoCalculado(BaseModel):
    ranura: Literal["acero", "colado", "completo"]
    unidad: str
    clave: str | None
    hasta_m: float | None
    escalones: list[EscalonDeEstructura]
    nuevo: bool
    rebasa: bool = Field(description="El alto rebasa el último escalón: falta un concepto para esa altura.")
    insumos: dict[str, float] = Field(description="Lo que calcula el elemento por unidad del concepto.")


class ConsumoDelColado(BaseModel):
    clave: str
    cantidad: float


class ColadoDeEstructura(BaseModel):
    concreto_m3_ml: float | None
    consumos: list[ConsumoDelColado]


class CaraDelForro(BaseModel):
    clave: str
    etiqueta: str
    caras: int
    largo_m: float
    area_m2: float
    hilada_m: float
    pza_por_m2: float
    pza_netas: float
    mezcla_neta_m3: float


class ForroDeEstructura(BaseModel):
    caras: list[CaraDelForro]
    pza_netas: float
    tabique_pza: float
    mezcla_neta_m3: float
    mezcla_m3: float
    cimbra_m2: float
    lados_cimbra: int


class ConceptoNuevoPorAltura(BaseModel):
    clave_propuesta: str
    descripcion: str
    unidad: str
    alto_m: float


class SoloEnElCatalogo(BaseModel):
    clave: str
    motivo: str


class CalculoDeEstructura(BaseModel):
    clave: str
    alias: str | None
    nombre: str
    tipo: Literal["castillo", "lineal"]
    categoria: str
    subcategoria: str
    posicion: str | None
    seccion: SeccionDeEstructura
    alto_m: float
    alto_fijo: bool
    unidad_de_calculo: str
    lados_cimbra: int
    armado: ArmadoDeEstructura
    acero: RecetaDeAceroCalculada
    colado: ColadoDeEstructura
    forro: ForroDeEstructura | None
    conceptos: list[ConceptoCalculado]
    concepto_nuevo_por_altura: ConceptoNuevoPorAltura | None
    solo_en_catalogo: list[SoloEnElCatalogo]
    pendientes: list[str]
    drivers_usados: list[DriverUsadoRespuesta] = Field(
        default_factory=list, description="Los drivers que leyó el cálculo y de dónde salió cada valor."
    )
    advertencias: list[str]
    fuente: str


class PropuestaDeLaFila(BaseModel):
    valor: float
    estado: Literal["pendiente", "autorizada"]
    propuesta_id: UUID | None
    marca: Marca
    diferencia_pct: float | None


class FilaDeConciliacionDeEstructura(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    catalogo: float | None
    elemento: float | None
    diferencia: float | None
    diferencia_pct: float | None
    marca: Marca
    motivo: str | None = Field(description="Por qué «solo en el catálogo»: lo que el elemento no calcula.")
    propuesta: PropuestaDeLaFila | None = Field(description="La versión propuesta del concepto para este insumo, si la hay.")


class ManoDeObraDelCatalogo(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    cantidad: float
    costo: float | None


class PropuestaDelConcepto(BaseModel):
    id: UUID
    estado: Literal["pendiente", "autorizada"]
    version: int | None
    resumen: str
    clase: Literal["version_de_concepto", "concepto_nuevo"]


class ConceptoConciliado(BaseModel):
    concepto_clave: str
    ranura: Literal["acero", "colado", "completo"]
    unidad: str
    alto_m: float
    hasta_m: float | None
    nuevo: bool
    sin_catalogo: bool
    en_catalogo: bool
    propuestas: list[PropuestaDelConcepto]
    filas: list[FilaDeConciliacionDeEstructura]
    mano_de_obra: list[ManoDeObraDelCatalogo] = Field(description="Destajo y mano de obra: el elemento no los calcula.")
    resumen: dict[str, int]
    coincide: bool


class ConciliacionDeEstructura(BaseModel):
    elemento_clave: str
    umbral_igual_pct: float
    umbral_aproximado_pct: float
    conceptos: list[ConceptoConciliado]


class CambioDeLaPropuesta(BaseModel):
    insumo: str
    unidad: str = ""
    antes: float
    despues: float


class PropuestaDeEstructura(BaseModel):
    id: UUID
    elemento_clave: str
    concepto_clave: str
    clase: Literal["version_de_concepto", "concepto_nuevo"]
    estado: Literal["pendiente", "autorizada", "rechazada"]
    version: int | None = Field(description="El número de la versión; `null` mientras está pendiente o si se rechazó.")
    resumen: str
    cambios: list[CambioDeLaPropuesta]
    motivos: list[str]
    destajo_por_definir: str | None = Field(description="El destajo del catálogo no corresponde a la medida: Costos lo define.")
    propuso_nombre: str | None
    propuso_rol: str | None
    propuesto_en: datetime
    decidio_nombre: str | None
    decidio_rol: str | None
    decidido_en: datetime | None
    motivo: str | None = Field(description="Por qué se rechazó.")


class ResultadoDeProponer(BaseModel):
    creadas: list[UUID]
    omitidas: list[str] = Field(description="Conceptos que ya tenían una propuesta pendiente o autorizada.")


class ConceptoPorAlturaPeticion(BaseModel):
    alto_m: float = Field(gt=0, le=30)


class PropuestaCreada(BaseModel):
    id: UUID


class VersionDeLaPropuesta(BaseModel):
    version: int


class RechazoDeLaPropuesta(BaseModel):
    motivo: str | None = Field(default=None, max_length=300)


def _a_propuesta(f: dict[str, Any]) -> PropuestaDeEstructura:
    detalle = dict(f.get("detalle") or {})
    destajo = detalle.get("destajo")
    return PropuestaDeEstructura(
        **{k: v for k, v in f.items() if k in PropuestaDeEstructura.model_fields and k not in ("cambios", "motivos")},
        cambios=[CambioDeLaPropuesta(**c) for c in detalle.get("cambios", [])],
        motivos=list(detalle.get("motivos", [])),
        destajo_por_definir=(
            f"{destajo['destajo']} dice {destajo['dice']}; corresponde {destajo['corresponde']}" if destajo else None
        ),
    )


_RESPUESTAS_DE_ELEMENTO = {404: {"description": "No hay un elemento de estructura con esa clave."}}
_RESPUESTAS_DE_DECIDIR = {
    403: {"description": "Solo Control de obra autoriza."},
    404: {"description": "La propuesta no existe o está fuera de tu alcance."},
    422: {"description": "Ya fue decidida."},
}


@router.get(
    "/biblioteca-de-elementos/estructura/{clave}",
    response_model=DefinicionDeEstructura,
    summary="La ficha de un castillo, aparente o columna forjada de la biblioteca",
    responses=_RESPUESTAS_DE_ELEMENTO,
)
async def definicion_de_estructura(clave: str) -> dict[str, Any]:
    try:
        return definicion_de(clave)
    except ElementoDeEstructuraNoEncontrado as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e


@router.post(
    "/biblioteca-de-elementos/estructura/{clave}/calcular",
    response_model=CalculoDeEstructura,
    summary="Calcula un castillo, aparente o columna forjada con su alto (solo cálculo)",
    responses=_RESPUESTAS_DE_ELEMENTO,
)
async def calcular_estructura(
    clave: str, peticion: CalculoDeEstructuraPeticion, drivers_de_obra: DriversDeObraDep
) -> dict[str, Any]:
    vigentes = await drivers_de_obra.valores(peticion.obra_id)
    drivers, usados = receta_de_obra(vigentes, explicitos_de_receta(peticion.drivers))
    desperdicio_pct, u_concreto = desperdicio_concreto_de_obra(vigentes)
    usados.append(u_concreto)
    alto_estandar = None
    try:
        # La altura estándar solo manda cuando el elemento no trae alto fijo (la forjada) y la petición no dice el suyo.
        if peticion.alto_m is None and not definicion_de(clave)["alto_fijo_m"]:
            alto_estandar, u_alto = altura_de_obra(vigentes)
            usados.append(u_alto)
        r = calcular_elemento(
            clave, peticion.alto_m, drivers=drivers, desperdicio_concreto=desperdicio_pct / 100, alto_estandar_m=alto_estandar
        )
        return {**r, "drivers_usados": a_respuesta(usados)}
    except ElementoDeEstructuraNoEncontrado as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    except ErrorDeEstructura as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e


@router.get(
    "/biblioteca-de-elementos/estructura/{clave}/conciliacion",
    response_model=ConciliacionDeEstructura,
    summary="El elemento contra el concepto del catálogo, insumo por insumo, con las versiones propuestas",
    responses=_RESPUESTAS_DE_ELEMENTO,
)
async def conciliacion_de_estructura(clave: str, caso_uso: GestionarPropuestasDeEstructuraDep) -> dict[str, Any]:
    return await caso_uso.conciliacion(clave)


@router.get(
    "/biblioteca-de-elementos/estructura/{clave}/propuestas",
    response_model=list[PropuestaDeEstructura],
    summary="Las versiones de concepto propuestas, autorizadas y rechazadas del elemento",
    responses=_RESPUESTAS_DE_ELEMENTO,
)
async def propuestas_de_estructura(clave: str, caso_uso: GestionarPropuestasDeEstructuraDep) -> list[PropuestaDeEstructura]:
    return [_a_propuesta(f) for f in await caso_uso.listar(clave)]


@router.post(
    "/biblioteca-de-elementos/estructura/{clave}/propuestas/correcciones",
    response_model=ResultadoDeProponer,
    status_code=status.HTTP_201_CREATED,
    summary="Proponer las correcciones del catálogo de este elemento como nuevas versiones de concepto",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_PROPONEN))],
    responses={**_RESPUESTAS_DE_ELEMENTO, 403: {"description": "Proponen Costos y Control de obra."}},
)
async def proponer_correcciones(clave: str, ctx: ContextoActual, caso_uso: GestionarPropuestasDeEstructuraDep) -> ResultadoDeProponer:
    r = await caso_uso.proponer_correcciones(clave, usuario_id=ctx.usuario_id, rol=ctx.rol)
    return ResultadoDeProponer(**r)


@router.post(
    "/biblioteca-de-elementos/estructura/{clave}/propuestas/concepto-por-altura",
    response_model=PropuestaCreada,
    status_code=status.HTTP_201_CREATED,
    summary="Proponer el concepto nuevo de una columna forjada con otra altura que 4.20 m",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_PROPONEN))],
    responses={**_RESPUESTAS_DE_ELEMENTO, 403: {"description": "Proponen Costos y Control de obra."}},
)
async def proponer_concepto_por_altura(
    clave: str, peticion: ConceptoPorAlturaPeticion, ctx: ContextoActual, caso_uso: GestionarPropuestasDeEstructuraDep
) -> PropuestaCreada:
    nuevo = await caso_uso.proponer_concepto_por_altura(clave, peticion.alto_m, usuario_id=ctx.usuario_id, rol=ctx.rol)
    return PropuestaCreada(id=nuevo)


@router.get(
    "/propuestas-de-estructura/pendientes",
    response_model=list[PropuestaDeEstructura],
    summary="Las propuestas de estructura que esperan la autorización de Control de obra",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_PROPONEN))],
    responses={403: {"description": "Lo ven Control de obra y Costos."}},
)
async def propuestas_pendientes(caso_uso: GestionarPropuestasDeEstructuraDep) -> list[PropuestaDeEstructura]:
    return [_a_propuesta(f) for f in await caso_uso.pendientes()]


@router.post(
    "/propuestas-de-estructura/{propuesta_id}/autorizar",
    response_model=VersionDeLaPropuesta,
    summary="Autorizar la propuesta: nace la versión siguiente del concepto",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_AUTORIZAN))],
    responses=_RESPUESTAS_DE_DECIDIR,
)
async def autorizar_propuesta(propuesta_id: UUID, ctx: ContextoActual, caso_uso: GestionarPropuestasDeEstructuraDep) -> VersionDeLaPropuesta:
    return VersionDeLaPropuesta(version=await caso_uso.autorizar(propuesta_id, usuario_id=ctx.usuario_id, rol=ctx.rol))


@router.post(
    "/propuestas-de-estructura/{propuesta_id}/rechazar",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Rechazar la propuesta (con el motivo)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_AUTORIZAN))],
    responses=_RESPUESTAS_DE_DECIDIR,
)
async def rechazar_propuesta(
    propuesta_id: UUID, peticion: RechazoDeLaPropuesta, ctx: ContextoActual, caso_uso: GestionarPropuestasDeEstructuraDep
) -> None:
    await caso_uso.rechazar(propuesta_id, usuario_id=ctx.usuario_id, rol=ctx.rol, motivo=peticion.motivo)
