"""Definición y cálculo de los elementos estructurales de la biblioteca (Ola 3B): trabes, contratrabes, nervaduras, zapata Z-1 y
columna C-1. Solo cálculo: no guarda nada.

El cálculo y la conciliación con el catálogo viven en el dominio (`elementos_lineales`); aquí se valida la entrada y se devuelve el
resultado. Controlador delgado. Estas rutas cuelgan de `/biblioteca-de-elementos/estructura-lineal/…` y se registran **antes** que las del muro
de piedra: `/biblioteca-de-elementos/{clave}/calcular` también casaría con ellas.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import DriversDeObraDep
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
    desperdicio_concreto_de_obra,
    receta_de_obra,
)
from obractrl.domain.cuantificacion.elementos_lineales import (
    EntradaElementoEstructural,
    ErrorDeElementoEstructural,
    calcular_elemento,
    definicion_del_elemento,
)

router = APIRouter(tags=["biblioteca de elementos"])

Marca = Literal["=", "≈", "≠", "solo_catalogo", "solo_elemento"]


class ConceptoDelElementoEstructural(BaseModel):
    clave: str
    descripcion: str
    unidad: str


class ClaveYNombreDelElemento(BaseModel):
    clave: str
    nombre: str


class SeccionDelElemento(BaseModel):
    ancho_cm: float
    peralte_cm: float
    largo_cm: float | None = Field(description="Solo la zapata: el otro lado de su planta.")


class ParteDelArmado(BaseModel):
    parte: str
    clave: str
    descripcion: str
    cantidad: float
    detalle: str


class InsumoNombrado(BaseModel):
    clave: str
    descripcion: str


class ConsumoDeCimbraDelElemento(BaseModel):
    clave: str
    descripcion: str
    consumo: Literal["por_m2", "por_ml"]
    cantidad: float


class ConceptoDelCatalogoDelElemento(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    toma: list[str]
    hasta_m: float | None
    fuente: str


class UsoEnLosa(BaseModel):
    clave: str
    cantidad: float


class PendienteDelElementoEstructural(BaseModel):
    clave: str
    texto: str


class BorradorDeConceptoDeColado(BaseModel):
    unidad: str
    toma: dict[str, bool]
    clave_propuesta: str | None = Field(description="Vacía a propósito: el concepto nuevo no se crea en esta ola.")
    descripcion_sugerida: str
    concreto: InsumoNombrado
    cimbra: list[ConsumoDeCimbraDelElemento]
    ruta: str


class ManoDeObraDelCamino(BaseModel):
    estado: str
    destajo: str | None
    nota: str | None = None


class CaminoDeColadoYCimbra(BaseModel):
    """Cómo se registraría después el concepto nuevo de colado y cimbra y el destajo por ml. No registra nada."""

    estado: Literal["por_registrar", "no_aplica"]
    motivo: str
    borrador: BorradorDeConceptoDeColado | None
    mano_de_obra: ManoDeObraDelCamino
    preguntas: list[str]


class DefinicionDelElementoEstructural(BaseModel):
    clave: str
    nombre: str
    tipo: str
    se_mide_por: str
    concepto: ConceptoDelElementoEstructural
    categoria: ClaveYNombreDelElemento
    subcategoria: ClaveYNombreDelElemento
    seccion: SeccionDelElemento
    lados_de_cimbra: int
    modos: list[Literal["ml", "pieza"]]
    modo_por_defecto: Literal["ml", "pieza"]
    largo_por_defecto_m: float | None
    alto_por_defecto_m: float | None
    armado: list[ParteDelArmado]
    concreto: InsumoNombrado
    alambre: InsumoNombrado
    cimbra: list[ConsumoDeCimbraDelElemento]
    conceptos_del_catalogo: list[ConceptoDelCatalogoDelElemento]
    camino_de_colado_y_cimbra: CaminoDeColadoYCimbra | None
    usado_en: list[UsoEnLosa]
    usos_total: int
    pendientes: list[PendienteDelElementoEstructural]


class ZonaDeAnilloDelElemento(BaseModel):
    len_cm: float | None = Field(
        default=None, ge=0, le=3000, description="Largo de la zona en cada extremo de la pieza; vacío = el resto o el centro."
    )
    sep_cm: float = Field(gt=0, le=200)


class CalculoDelElementoEstructuralPeticion(BaseModel):
    modo: Literal["ml", "pieza"] = Field(
        default="ml", description="ml = por metro de trazo; pieza = de largo conocido. La zapata y la columna son pieza."
    )
    largo_m: float | None = Field(default=None, gt=0, le=30, description="Largo de la pieza (trabe, contratrabe o nervadura por pieza); 4.00 m si no se manda.")
    alto_m: float | None = Field(default=None, gt=0, le=30, description="Altura de la columna C-1; 6.00 m si no se manda.")
    cantidad: float = Field(default=1.0, gt=0, le=1_000_000, description="Metros o piezas que se piden: da los totales a comprar.")
    zonas_de_anillo: list[ZonaDeAnilloDelElemento] = Field(default_factory=list, max_length=10)
    desperdicio_concreto_pct: float = Field(default=5.0, ge=0, le=50)
    drivers: DriversDeRecetaPeticion = Field(default_factory=DriversDeRecetaPeticion)
    obra_id: UUID | None = Field(
        default=None,
        description="La obra cuyos drivers (Paramétrico) se leen. Precedencia: lo que manda la petición > el driver de la obra > el valor por defecto. Sin obra, todo vale lo de siempre.",
    )


class SeccionCalculada(BaseModel):
    ancho_cm: float
    peralte_cm: float
    largo_cm: float | None


class ConcretoCalculado(BaseModel):
    clave: str
    descripcion: str
    m3: float = Field(description="Por unidad (metro o pieza), con el desperdicio.")
    desperdicio_pct: float


class ConsumoCalculado(BaseModel):
    clave: str
    descripcion: str
    cantidad: float


class CimbraCalculada(BaseModel):
    m2: float
    lados: int
    consumos: list[ConsumoCalculado]


class InsumoCalculado(BaseModel):
    parte: Literal["acero", "estribos", "alambre", "concreto", "cimbra"]
    clave: str
    descripcion: str
    unidad: str
    por_unidad: float = Field(description="Cantidad por metro o por pieza.")
    total: float = Field(description="Por la cantidad pedida.")
    a_comprar: float | None = Field(description="Piezas enteras a comprar (solo las que se compran por pieza).")
    kg: float | None
    ml: float | None
    detalle: str


class ParrillaCalculada(BaseModel):
    varillas_por_sentido: list[int]
    ml: float
    capas: int
    separacion_cm: float


class ManoDeObraDelElemento(BaseModel):
    estado: Literal["sin_mano_de_obra"]
    nota: str


class FilaDeConciliacionDelElemento(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    catalogo: float | None
    elemento: float | None
    diferencia: float | None
    diferencia_pct: float | None
    marca: Marca


class ManoDeObraDelCatalogo(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    cantidad: float
    costo: float | None


class ConciliacionConUnConcepto(BaseModel):
    concepto: ConceptoDelCatalogoDelElemento
    sobre: str = Field(description="Por qué unidad se compara: por metro o por pieza.")
    filas: list[FilaDeConciliacionDelElemento]
    mano_de_obra: list[ManoDeObraDelCatalogo] = Field(description="El destajo del catálogo: el elemento no lo calcula.")
    resumen: dict[str, int]
    coincide: bool
    fuente_de_las_filas: list[str]
    avisos: list[str]


class CalculoDelElementoEstructural(BaseModel):
    clave: str
    nombre: str
    tipo: str
    modo: Literal["ml", "pieza"]
    unidad: Literal["ml", "pza"]
    longitud_m: float | None
    cantidad: float
    seccion: SeccionCalculada
    concreto: ConcretoCalculado
    acero_kg: float
    cimbra: CimbraCalculada
    receta_acero: RecetaDeAceroCalculada | None = Field(description="El detalle de cortes, traslapes y anillos (no aplica a la zapata).")
    parrilla: ParrillaCalculada | None
    insumos: list[InsumoCalculado]
    mano_de_obra: ManoDeObraDelElemento
    conciliacion: list[ConciliacionConUnConcepto]
    camino_de_colado_y_cimbra: CaminoDeColadoYCimbra | None
    drivers_usados: list[DriverUsadoRespuesta] = Field(
        default_factory=list, description="Los drivers que leyó el cálculo y de dónde salió cada valor."
    )
    advertencias: list[str]


@router.get(
    "/biblioteca-de-elementos/estructura-lineal/{clave}",
    response_model=DefinicionDelElementoEstructural,
    summary="La definición de una trabe, contratrabe, nervadura, la zapata Z-1 o la columna C-1 de la biblioteca",
    responses={404: {"description": "No hay un elemento con esa clave en la familia de estructura."}},
)
async def definicion_del_elemento_estructural(clave: str) -> dict[str, Any]:
    d = definicion_del_elemento(clave)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No hay un elemento {clave} en la familia de estructura de la biblioteca.")
    return d


@router.post(
    "/biblioteca-de-elementos/estructura-lineal/{clave}/calcular",
    response_model=CalculoDelElementoEstructural,
    summary="Calcula un elemento estructural por ml o por pieza y lo contrasta con el catálogo (solo cálculo)",
    responses={404: {"description": "No hay un elemento con esa clave."}, 422: {"description": "Un dato no vale."}},
)
async def calcular_elemento_estructural(
    clave: str, peticion: CalculoDelElementoEstructuralPeticion, drivers_de_obra: DriversDeObraDep
) -> dict[str, Any]:
    if definicion_del_elemento(clave) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No hay un elemento {clave} en la familia de estructura de la biblioteca.")
    vigentes = await drivers_de_obra.valores(peticion.obra_id)
    drivers, usados = receta_de_obra(vigentes, explicitos_de_receta(peticion.drivers))
    explicito = peticion.desperdicio_concreto_pct if "desperdicio_concreto_pct" in peticion.model_fields_set else None
    desperdicio_pct, u_concreto = desperdicio_concreto_de_obra(vigentes, explicito_pct=explicito)
    usados.append(u_concreto)
    try:
        r = calcular_elemento(
            EntradaElementoEstructural(
                clave=clave,
                modo=peticion.modo,
                largo_m=peticion.largo_m,
                alto_m=peticion.alto_m,
                cantidad=peticion.cantidad,
                zonas_de_anillo=[(z.len_cm, z.sep_cm) for z in peticion.zonas_de_anillo],
                desperdicio_concreto_pct=desperdicio_pct,
                drivers=drivers,
            )
        )
        return {**r, "drivers_usados": a_respuesta(usados)}
    except ErrorDeElementoEstructural as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
