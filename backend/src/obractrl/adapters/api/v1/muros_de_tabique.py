"""Definición, cálculo y propuestas de los muros de tabique, los aparejos nuevos y el piso de petatillo (Ola 3, 3C).

El cálculo vive en el dominio (`muro_tabique`); aquí solo se valida la entrada y se devuelve el resultado. `calcular` no guarda
nada. Las versiones de concepto y los conceptos nuevos se **proponen** (Costos o Control de obra) y solo Control de obra los autoriza,
con las mismas rutas de autorización de las propuestas de estructura. Estas rutas cuelgan de `/biblioteca-de-elementos/tabique/…`
y se registran **antes** que las del muro de piedra. Controladores delgados.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import GestionarPropuestasDeTabiqueDep
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.adapters.api.v1.elementos_de_estructura import (
    PropuestaDeEstructura,
    ResultadoDeProponer,
)
from obractrl.adapters.api.v1.elementos_de_estructura import (
    _a_propuesta as a_propuesta,
)
from obractrl.domain.cuantificacion.muro_tabique import (
    ElementoDeTabiqueNoEncontrado,
    EntradaMuroDeTabique,
    ErrorDeMuroDeTabique,
    calcular_muro_de_tabique,
    definicion_de,
    tabla_de_revision,
)
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["biblioteca de elementos"])

ROLES_QUE_PROPONEN = (Rol.CONTROL_OBRA, Rol.COSTOS)
Marca = Literal["=", "≈", "≠", "solo_catalogo", "solo_elemento"]
Medida = Literal["m2", "ml"]
EstadoDelConcepto = Literal["catalogo", "propuesto"]


class ClaveYNombreDeTabique(BaseModel):
    clave: str
    nombre: str


class PiezaDeTabique(BaseModel):
    insumo: str
    ancho_cm: float
    alto_cm: float
    largo_cm: float


class DestajoDelCatalogo(BaseModel):
    clave: str
    descripcion: str
    unidad: str


class ConceptoDelTabique(BaseModel):
    clave: str
    etiqueta: str
    descripcion: str
    unidad: str
    estado: EstadoDelConcepto
    clave_provisional: bool = Field(description="Concepto nuevo propuesto: su clave es provisional hasta que Control de obra la confirme.")
    en_catalogo: bool
    destajo: DestajoDelCatalogo | None = Field(description="El destajo del catálogo; `null` = sin destajo.")
    nivel_desde: int | None = Field(description="Desde qué nivel lo paga el elemento (3.er nivel); `null` = el concepto base.")


class HiladaDelAparejo(BaseModel):
    peso: float
    filas: list[str]


class ParametrosDelTabique(BaseModel):
    junta_cm: float
    junta_entre_hileras_cm: float | None
    desperdicio_de_pieza_pct: float
    desperdicio_de_mezcla_pct: float
    cama_cm: float | None = Field(description="Solo el petatillo: la cama de mortero (0 cm por defecto).")
    tipo_de_sardinel: str | None = Field(description="Solo el sardinel.")
    nivel_desde_3er_nivel: int | None = Field(description="Solo EST-02010/02011: desde qué nivel se paga EST-02011.")


class TipoDeSardinel(BaseModel):
    clave: str
    descripcion: str


class PendienteDelTabique(BaseModel):
    clave: str
    texto: str


class DefinicionDelTabique(BaseModel):
    clave: str
    nombre: str
    nombre_nominal: str
    tipo: str
    medida: Medida
    se_mide_por: str
    categoria: ClaveYNombreDeTabique
    subcategoria: ClaveYNombreDeTabique
    espesor_nominal_cm: int | None
    espesor_real_cm: float
    aparejo: str
    aparejo_largo: str
    aparejo_texto: str
    planta_nota: str
    pieza: PiezaDeTabique
    mezcla: str
    parametros_por_defecto: ParametrosDelTabique
    tipos_de_sardinel: list[TipoDeSardinel]
    hiladas: list[HiladaDelAparejo]
    conceptos: list[ConceptoDelTabique]
    fuente: str
    avisos_de_catalogo: list[str]
    pendientes: list[PendienteDelTabique]


class FilaDeTabiqueRevision(BaseModel):
    clave: str
    provisional: bool
    estado: EstadoDelConcepto
    nombre_nominal: str
    nombre: str
    espesor_real_cm: float
    aparejo: str
    unidad: str
    piezas_por_unidad: float
    mezcla_m3_por_unidad: float
    contraste: str


class RenglonDeHerramienta(BaseModel):
    descripcion: str = Field(min_length=1, max_length=120)
    unidad: str = Field(min_length=1, max_length=20)
    por_unidad: float = Field(ge=0, le=1_000_000, description="Cantidad por m² (o por ml); sin precio.")


class CalculoDelTabiquePeticion(BaseModel):
    cantidad: float = Field(default=1.0, gt=0, le=1_000_000, description="m² de muro (o metros de la hilada del sardinel), ya sin huecos.")
    nivel: int | None = Field(default=None, ge=1, le=100, description="Nivel del plano; desde el 3.º EST-02010 paga EST-02011.")
    nivel_desde_3er_nivel: int = Field(default=3, ge=2, le=100)
    junta_cm: float = Field(default=2.0, ge=0, le=10)
    junta_entre_hileras_cm: float | None = Field(default=None, ge=0, le=10)
    desperdicio_de_pieza_pct: float = Field(default=12.0, ge=0, le=100)
    desperdicio_de_mezcla_pct: float = Field(default=5.0, ge=0, le=100)
    pieza_alto_cm: float = Field(default=6.0, ge=1, le=100)
    pieza_largo_cm: float = Field(default=26.0, ge=1, le=100)
    cama_cm: float | None = Field(default=None, ge=0, le=20, description="Solo el petatillo.")
    tipo_de_sardinel: str | None = Field(default=None, max_length=40, description="Solo el sardinel; hoy solo existe «parado».")
    herramienta: list[RenglonDeHerramienta] = Field(default_factory=list, max_length=20)


class ConceptoElegido(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    etiqueta: str
    estado: EstadoDelConcepto
    clave_provisional: bool
    nivel_desde: int | None


class FilaDeHilera(BaseModel):
    orientacion: str
    etiqueta: str
    visible_cm: float
    alto_cm: float
    espesor_cm: float
    piezas_netas_m2: float


class HiladaCalculada(BaseModel):
    peso: float
    espesor_cm: float
    filas: list[FilaDeHilera]


class GeometriaDelTabique(BaseModel):
    espesor_real_cm: float
    espesor_minimo_cm: float
    espesor_medio_cm: float
    hilada_promedio_cm: float
    piezas_por_hilada: float
    hiladas: list[HiladaCalculada]


class PiezasCalculadas(BaseModel):
    netas_por_unidad: float
    por_unidad: float = Field(description="Con el desperdicio de pieza.")
    total: float
    a_comprar: int


class MezclaCalculada(BaseModel):
    neta_por_unidad: float
    por_unidad: float = Field(description="Con el desperdicio de mezcla.")
    total_m3: float


class InsumoDelTabique(BaseModel):
    parte: Literal["tabique", "mezcla"]
    clave: str
    descripcion: str
    unidad: str
    por_unidad: float
    total: float
    a_comprar: float | None


class InsumoDeLaMezcla(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    por_m3: float
    total: float
    linea: str


class ManoDeObraDelTabique(BaseModel):
    estado: Literal["destajo_del_catalogo", "sin_destajo"]
    destajo: DestajoDelCatalogo | None
    cantidad: float
    nota: str


class RenglonDeHerramientaCalculado(BaseModel):
    descripcion: str
    unidad: str
    por_unidad: float
    total: float


class FilaDeConciliacionDelTabique(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    catalogo: float | None
    elemento: float | None
    diferencia: float | None
    diferencia_pct: float | None
    marca: Marca


class ManoDeObraDelCatalogoDelTabique(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    cantidad: float
    costo: float | None


class ConceptoDeConciliacion(BaseModel):
    clave: str
    descripcion: str
    unidad: str


class ConciliacionDelTabique(BaseModel):
    concepto: ConceptoDeConciliacion
    sobre: str
    filas: list[FilaDeConciliacionDelTabique]
    mano_de_obra: list[ManoDeObraDelCatalogoDelTabique] = Field(description="El destajo del catálogo: el elemento no lo calcula.")
    resumen: dict[str, int]
    coincide: bool
    fuente_de_las_filas: list[str]
    avisos: list[str]


class CalculoDelTabique(BaseModel):
    clave: str
    nombre: str
    medida: Medida
    unidad: str
    cantidad: float
    nivel: int | None
    concepto: ConceptoElegido
    pieza: PiezaDeTabique
    parametros: ParametrosDelTabique
    geometria: GeometriaDelTabique
    piezas: PiezasCalculadas
    mezcla: MezclaCalculada
    insumos: list[InsumoDelTabique]
    mezcla_compuesta: list[InsumoDeLaMezcla]
    mano_de_obra: ManoDeObraDelTabique
    herramienta: list[RenglonDeHerramientaCalculado]
    conciliacion: list[ConciliacionDelTabique]
    avisos: list[str]


_RESPUESTAS_DE_ELEMENTO = {404: {"description": "No hay un elemento de tabique con esa clave."}}
_PROPONEN = {**_RESPUESTAS_DE_ELEMENTO, 403: {"description": "Proponen Costos y Control de obra."}}


def _entrada(p: CalculoDelTabiquePeticion) -> EntradaMuroDeTabique:
    return EntradaMuroDeTabique(
        cantidad=p.cantidad,
        nivel=p.nivel,
        nivel_desde_3er_nivel=p.nivel_desde_3er_nivel,
        junta_cm=p.junta_cm,
        junta_entre_hileras_cm=p.junta_entre_hileras_cm,
        desperdicio_de_pieza_pct=p.desperdicio_de_pieza_pct,
        desperdicio_de_mezcla_pct=p.desperdicio_de_mezcla_pct,
        pieza_alto_cm=p.pieza_alto_cm,
        pieza_largo_cm=p.pieza_largo_cm,
        cama_cm=p.cama_cm,
        tipo_de_sardinel=p.tipo_de_sardinel,
        herramienta=tuple((h.descripcion, h.unidad, h.por_unidad) for h in p.herramienta),
    )


@router.get(
    "/biblioteca-de-elementos/tabique/tabla-de-revision",
    response_model=list[FilaDeTabiqueRevision],
    summary="La tabla de revisión de claves, nombres nominales, espesores reales y contraste con el catálogo de los aparejos",
)
async def tabla_de_revision_de_tabique() -> list[dict[str, Any]]:
    return tabla_de_revision()


@router.get(
    "/biblioteca-de-elementos/tabique/{clave}",
    response_model=DefinicionDelTabique,
    summary="La ficha de un muro de tabique, aparejo o piso de petatillo de la biblioteca",
    responses=_RESPUESTAS_DE_ELEMENTO,
)
async def definicion_del_tabique(clave: str) -> dict[str, Any]:
    try:
        return definicion_de(clave)
    except ElementoDeTabiqueNoEncontrado as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e


@router.post(
    "/biblioteca-de-elementos/tabique/{clave}/calcular",
    response_model=CalculoDelTabique,
    summary="Calcula un muro de tabique, aparejo o piso por m² (o ml de hilada) y lo contrasta con el catálogo (solo cálculo)",
    responses={**_RESPUESTAS_DE_ELEMENTO, 422: {"description": "Un dato no vale."}},
)
async def calcular_tabique(clave: str, peticion: CalculoDelTabiquePeticion) -> dict[str, Any]:
    try:
        return calcular_muro_de_tabique(clave, _entrada(peticion))
    except ElementoDeTabiqueNoEncontrado as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    except ErrorDeMuroDeTabique as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e


@router.get(
    "/biblioteca-de-elementos/tabique/{clave}/propuestas",
    response_model=list[PropuestaDeEstructura],
    summary="Las versiones de concepto propuestas, autorizadas y rechazadas del elemento de tabique",
    responses=_RESPUESTAS_DE_ELEMENTO,
)
async def propuestas_de_tabique(clave: str, caso_uso: GestionarPropuestasDeTabiqueDep) -> list[PropuestaDeEstructura]:
    return [a_propuesta(f) for f in await caso_uso.listar(clave)]


@router.post(
    "/biblioteca-de-elementos/tabique/{clave}/propuestas/concepto-nuevo",
    response_model=ResultadoDeProponer,
    status_code=status.HTTP_201_CREATED,
    summary="Proponer el concepto nuevo de un aparejo que el catálogo no trae (clave provisional, sin destajo ni precio)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_PROPONEN))],
    responses={**_PROPONEN, 422: {"description": "El elemento ya está en el catálogo."}},
)
async def proponer_concepto_nuevo(clave: str, ctx: ContextoActual, caso_uso: GestionarPropuestasDeTabiqueDep) -> ResultadoDeProponer:
    return ResultadoDeProponer(**await caso_uso.proponer_concepto_nuevo(clave, usuario_id=ctx.usuario_id, rol=ctx.rol))


@router.post(
    "/biblioteca-de-elementos/tabique/{clave}/propuestas/actualizar-apu",
    response_model=ResultadoDeProponer,
    status_code=status.HTTP_201_CREATED,
    summary="Confirmar el cálculo: proponer como nueva versión del concepto los coeficientes que difieren del catálogo",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_PROPONEN))],
    responses={**_PROPONEN, 422: {"description": "Un dato no vale."}},
)
async def proponer_actualizacion_de_apu(
    clave: str, peticion: CalculoDelTabiquePeticion, ctx: ContextoActual, caso_uso: GestionarPropuestasDeTabiqueDep
) -> ResultadoDeProponer:
    try:
        r = await caso_uso.proponer_actualizacion_de_apu(clave, _entrada(peticion), usuario_id=ctx.usuario_id, rol=ctx.rol)
    except ErrorDeMuroDeTabique as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    return ResultadoDeProponer(**r)


@router.post(
    "/biblioteca-de-elementos/tabique/{clave}/propuestas/correcciones",
    response_model=ResultadoDeProponer,
    status_code=status.HTTP_201_CREATED,
    summary="Proponer las correcciones de fábrica del elemento (EST-02020: el cálculo; AUX-04010: el texto del mortero)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_PROPONEN))],
    responses=_PROPONEN,
)
async def proponer_correcciones_de_tabique(clave: str, ctx: ContextoActual, caso_uso: GestionarPropuestasDeTabiqueDep) -> ResultadoDeProponer:
    return ResultadoDeProponer(**await caso_uso.proponer_correcciones(clave, usuario_id=ctx.usuario_id, rol=ctx.rol))
