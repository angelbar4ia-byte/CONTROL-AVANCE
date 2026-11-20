"""Definición, cálculo y propuestas del muro de sillar amarillo BAP-01010 (elemento de la biblioteca, Muros › Muros de sillar).

El cálculo vive en el dominio (`muro_sillar`); aquí solo se valida la entrada y se devuelve el resultado. `calcular` no guarda nada. El
desperdicio sale del driver `desperdicio_mamposteria` (F6): lo que manda la petición > el driver de la obra (`obra_id`) > el valor de partida.
El elemento se liga al concepto BAP-01010 del catálogo (regla F7); las versiones de ese concepto se **proponen** (Costos o Control de obra) y
solo Control de obra las autoriza, con las mismas rutas de autorización de las propuestas de estructura. Estas rutas cuelgan de
`/biblioteca-de-elementos/sillar/…` y se registran **antes** que las de la biblioteca. Controladores delgados.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    DriversDeObraDep,
    GestionarPropuestasDeSillarDep,
)
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.adapters.api.v1.drivers_usados import DriverUsadoRespuesta, a_respuesta
from obractrl.adapters.api.v1.elementos_de_estructura import (
    PropuestaDeEstructura,
    ResultadoDeProponer,
)
from obractrl.adapters.api.v1.elementos_de_estructura import (
    _a_propuesta as a_propuesta,
)
from obractrl.adapters.api.v1.muros_de_tabique import (
    ClaveYNombreDeTabique,
    ConceptoDelTabique,
    ConceptoElegido,
    ConciliacionDelTabique,
    GeometriaDelTabique,
    HiladaDelAparejo,
    InsumoDeLaMezcla,
    ManoDeObraDelTabique,
    MezclaCalculada,
    ParametrosDelTabique,
    PendienteDelTabique,
    PiezaDeTabique,
    PiezasCalculadas,
    RenglonDeHerramientaCalculado,
)
from obractrl.domain.cuantificacion.drivers_de_elementos import (
    DriverUsado,
    valor_de_driver,
)
from obractrl.domain.cuantificacion.muro_sillar import (
    CLAVE_DEL_DRIVER_DE_DESPERDICIO,
    DESPERDICIO_POR_DEFECTO_PCT,
    ElementoDeSillarNoEncontrado,
    EntradaMuroDeSillar,
    ErrorDeMuroDeSillar,
    calcular_muro_de_sillar,
    definicion_de,
)
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["biblioteca de elementos"])

ROLES_QUE_PROPONEN = (Rol.CONTROL_OBRA, Rol.COSTOS)
Medida = Literal["m2"]


class DefinicionDelSillar(BaseModel):
    clave: str
    nombre: str
    nombre_nominal: str
    tipo: str
    medida: Medida
    se_mide_por: str
    categoria: ClaveYNombreDeTabique
    subcategoria: ClaveYNombreDeTabique
    espesor_nominal_cm: int
    espesor_real_cm: float
    aparejo: str
    aparejo_largo: str
    aparejo_texto: str
    planta_nota: str
    pieza: PiezaDeTabique
    mezcla: str
    parametros_por_defecto: ParametrosDelTabique
    hiladas: list[HiladaDelAparejo]
    conceptos: list[ConceptoDelTabique]
    driver_de_desperdicio: str = Field(description="El driver del Paramétrico que da el desperdicio (F6): `desperdicio_mamposteria`.")
    piezas_por_unidad_de_partida: float = Field(description="Piezas por m² con la junta y el desperdicio de partida.")
    fuente: str
    avisos_de_catalogo: list[str]
    pendientes: list[PendienteDelTabique]


class CalculoDelSillarPeticion(BaseModel):
    cantidad: float = Field(default=1.0, gt=0, le=1_000_000, description="m² de muro, ya sin huecos.")
    junta_cm: float = Field(
        default=2.0, ge=0, le=10, description="Junta entre piezas. El catálogo no la trae: 2 cm es un supuesto (la del tabique), editable."
    )
    desperdicio_pct: float | None = Field(
        default=None, ge=0, le=100,
        description="Desperdicio de pieza y de mezcla. Si no se manda, vale el driver `desperdicio_mamposteria` de la obra (5 % de partida).",
    )
    obra_id: UUID | None = Field(
        default=None,
        description="La obra cuyos drivers (Paramétrico) se leen. Precedencia: lo que manda la petición > el driver de la obra > el valor de partida. Sin obra, todo vale lo de siempre.",
    )


class InsumoDelSillar(BaseModel):
    parte: Literal["sillar", "mezcla"]
    clave: str
    descripcion: str
    unidad: str
    por_unidad: float
    total: float
    a_comprar: float | None


class CalculoDelSillar(BaseModel):
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
    insumos: list[InsumoDelSillar]
    mezcla_compuesta: list[InsumoDeLaMezcla]
    mano_de_obra: ManoDeObraDelTabique
    herramienta: list[RenglonDeHerramientaCalculado]
    conciliacion: list[ConciliacionDelTabique]
    avisos: list[str]
    drivers_usados: list[DriverUsadoRespuesta] = Field(
        default_factory=list, description="Los drivers que leyó el cálculo y de dónde salió cada valor."
    )


_RESPUESTAS_DE_ELEMENTO = {404: {"description": "No hay un elemento de sillar con esa clave."}}
_PROPONEN = {**_RESPUESTAS_DE_ELEMENTO, 403: {"description": "Proponen Costos y Control de obra."}}


async def _entrada(p: CalculoDelSillarPeticion, drivers_de_obra: DriversDeObraDep) -> tuple[EntradaMuroDeSillar, list[DriverUsado]]:
    """La entrada con el desperdicio resuelto: lo que la petición manda > el driver de la obra > el valor de partida."""
    vigentes = await drivers_de_obra.valores(p.obra_id)
    desperdicio = valor_de_driver(
        CLAVE_DEL_DRIVER_DE_DESPERDICIO, explicito=p.desperdicio_pct, defecto=DESPERDICIO_POR_DEFECTO_PCT, vigentes=vigentes
    )
    return EntradaMuroDeSillar(cantidad=p.cantidad, junta_cm=p.junta_cm, desperdicio_pct=desperdicio.valor), [desperdicio]


@router.get(
    "/biblioteca-de-elementos/sillar/{clave}",
    response_model=DefinicionDelSillar,
    summary="La ficha del muro de sillar amarillo de la biblioteca (pieza 19×25×45, concepto BAP-01010, supuestos y pendientes)",
    responses=_RESPUESTAS_DE_ELEMENTO,
)
async def definicion_del_sillar(clave: str) -> dict[str, Any]:
    try:
        return definicion_de(clave)
    except ElementoDeSillarNoEncontrado as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e


@router.post(
    "/biblioteca-de-elementos/sillar/{clave}/calcular",
    response_model=CalculoDelSillar,
    summary="Calcula el muro de sillar amarillo por m², lo contrasta con BAP-01010 y dice qué drivers leyó (solo cálculo)",
    responses={**_RESPUESTAS_DE_ELEMENTO, 422: {"description": "Un dato no vale."}},
)
async def calcular_sillar(clave: str, peticion: CalculoDelSillarPeticion, drivers_de_obra: DriversDeObraDep) -> dict[str, Any]:
    try:
        entrada, usados = await _entrada(peticion, drivers_de_obra)
        return {**calcular_muro_de_sillar(clave, entrada), "drivers_usados": a_respuesta(usados)}
    except ElementoDeSillarNoEncontrado as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    except ErrorDeMuroDeSillar as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e


@router.get(
    "/biblioteca-de-elementos/sillar/{clave}/propuestas",
    response_model=list[PropuestaDeEstructura],
    summary="Las versiones de concepto propuestas, autorizadas y rechazadas del muro de sillar",
    responses=_RESPUESTAS_DE_ELEMENTO,
)
async def propuestas_de_sillar(clave: str, caso_uso: GestionarPropuestasDeSillarDep) -> list[PropuestaDeEstructura]:
    return [a_propuesta(f) for f in await caso_uso.listar(clave)]


@router.post(
    "/biblioteca-de-elementos/sillar/{clave}/propuestas/actualizar-apu",
    response_model=ResultadoDeProponer,
    status_code=status.HTTP_201_CREATED,
    summary="Confirmar el cálculo: proponer como nueva versión de BAP-01010 los coeficientes que difieren del catálogo",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_PROPONEN))],
    responses={**_PROPONEN, 422: {"description": "Un dato no vale."}},
)
async def proponer_actualizacion_de_apu_del_sillar(
    clave: str, peticion: CalculoDelSillarPeticion, ctx: ContextoActual, drivers_de_obra: DriversDeObraDep, caso_uso: GestionarPropuestasDeSillarDep
) -> ResultadoDeProponer:
    try:
        entrada, _ = await _entrada(peticion, drivers_de_obra)
        r = await caso_uso.proponer_actualizacion_de_apu(clave, entrada, usuario_id=ctx.usuario_id, rol=ctx.rol)
    except ErrorDeMuroDeSillar as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    return ResultadoDeProponer(**r)
