"""La escalera como elemento (Fase 4a: escaleras con cotas): ficha, cálculo, escaleras de la zona y propuesta del concepto nuevo del descanso.

- **Biblioteca** (`/biblioteca-de-elementos/escalera/…`): la ficha de la escalera forjada (ESC-FORJADA, concepto EST-01510 del catálogo por escalón de 1.20 m y concepto
  nuevo propuesto EJ-820 para el descanso), el **cálculo suelto** (con las cotas que se mandan; no guarda nada ni pide sesión) y la propuesta del concepto nuevo (regla
  F7). Se registra **antes** que las de la biblioteca: `/biblioteca-de-elementos/{clave}/calcular` también casaría.
- **Zona** (`/zonas-de-losa/{zona_id}/escaleras`): las escaleras que arrancan en la zona (las cotas salen de las zonas o se teclean; el recorrido, si se quiere, de una
  línea del plano; con espacio), su **cálculo** con lo que hay en el plano y la base (con la conciliación contra EST-01510 si se pide) y la propuesta de su concepto.
  Todos los roles que ven el plano leen; **solo Control de obra escribe** (lo exige también RLS).

El cálculo vive en el dominio (`escalera`); controladores delgados.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    GestionarEscalerasDep,
    GestionarPropuestasDeEscaleraDep,
)
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.adapters.api.v1.elementos_de_estructura import (
    PropuestaDeEstructura,
    ResultadoDeProponer,
)
from obractrl.adapters.api.v1.elementos_de_estructura import (
    _a_propuesta as a_propuesta,
)
from obractrl.adapters.api.v1.losas import (
    ClaveYNombreDeLosa,
    ConceptoDeLaFicha,
    ConciliacionDeLaLosa,
    DestajoCandidato,
    ManoDeObraDeLaLosa,
    PendienteDeLaLosa,
    PropuestaDelConceptoDeLosa,
    ResolucionDelConcepto,
)
from obractrl.domain.cuantificacion.escalera import (
    EntradaEscalera,
    ErrorDeEscalera,
    calcular_escalera,
    definicion_de_escalera,
    elemento_de_escalera,
    validar_parametros,
)
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["escaleras"])

ROLES_QUE_PROPONEN = (Rol.CONTROL_OBRA, Rol.COSTOS)
ROLES_QUE_EDITAN = (Rol.CONTROL_OBRA,)
ROLES_QUE_LEEN = (Rol.RESIDENTE, Rol.SUPERVISOR, Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE, Rol.COSTOS)

_NO_HAY_ESCALERA = {404: {"description": "No hay un elemento de escalera con esa clave (ESC-FORJADA)."}}
_PROPONEN = {403: {"description": "Proponen Costos y Control de obra."}, 404: {"description": "No existe ese elemento."}}
_CAMPOS = ("peldanos", "contrahuella_max_m", "huella_m", "ancho_m", "espesor_m", "rampas", "largo_descanso_m")


# ── Modelos ─────────────────────────────────────────────────────────────────────────────────────────────


class ParametrosDeLaEscalera(BaseModel):
    peldanos: int | None = Field(description="Número de peldaños; `null` = el que sale del desnivel y de la contrahuella máxima.")
    contrahuella_max_m: float = Field(description="Contrahuella máxima (m): con ella los peldaños salen del desnivel (valor de referencia: 0.18).")
    huella_m: float = Field(description="Huella (m): el fondo de cada peldaño (valor de referencia: 0.25). Si hay una línea del plano, manda el recorrido de la línea.")
    ancho_m: float = Field(description="Ancho de la escalera (m): el escalón del catálogo es de 1.20 m y la cantidad escala con ancho ÷ 1.20.")
    espesor_m: float = Field(description="Espesor del concreto de la rampa y del descanso (m).")
    rampas: int = Field(description="Número de rampas; entre ellas hay un descanso.")
    largo_descanso_m: float | None = Field(description="Largo del descanso (m); `null` = igual al ancho.")


class InsumoDeLaFichaDeLaEscalera(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    por_escalon: float
    fuente: str


class ParrillaDeLaFicha(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    por_m2: float
    fuente: str


class DefinicionDeLaEscalera(BaseModel):
    clave: str
    nombre: str
    se_mide_por: str
    categoria: ClaveYNombreDeLosa
    subcategoria: ClaveYNombreDeLosa
    concepto: ConceptoDeLaFicha
    concepto_del_descanso: ConceptoDeLaFicha
    largo_base_del_escalon_m: float
    parametros_por_defecto: ParametrosDeLaEscalera
    composicion_del_escalon: list[InsumoDeLaFichaDeLaEscalera]
    parrilla_por_m2: list[ParrillaDeLaFicha]
    destajos_candidatos: list[DestajoCandidato]
    pendientes: list[PendienteDeLaLosa]


class CalculoDeLaEscaleraPeticion(BaseModel):
    cota_arranque_m: float = Field(default=0.0, ge=-30, le=100, description="Cota del piso de arranque (relativa al piso terminado de PB = 0).")
    cota_llegada_m: float = Field(default=3.12, ge=-30, le=100, description="Cota de llegada: por omisión 3.12 m (3.00 m de altura libre más 12 cm de losa).")
    peldanos: int | None = Field(default=None, ge=2, le=120, description="Sin él salen del desnivel y de la contrahuella máxima.")
    contrahuella_max_m: float | None = Field(default=None, ge=0.10, le=0.30)
    huella_m: float | None = Field(default=None, ge=0.15, le=0.60)
    recorrido_m: float | None = Field(default=None, gt=0, le=100, description="El recorrido horizontal de las rampas (lo que mediría una línea del plano): manda sobre la huella.")
    ancho_m: float | None = Field(default=None, ge=0.40, le=5.0)
    espesor_m: float | None = Field(default=None, ge=0.05, le=0.50)
    rampas: int | None = Field(default=None, ge=1, le=4)
    largo_descanso_m: float | None = Field(default=None, ge=0.40, le=6.0)
    espacio_id: str | None = Field(default=None, max_length=60, description="Una etiqueta de espacio para toda la escalera (0143).")


class CotasDeLaEscalera(BaseModel):
    arranque_m: float
    llegada_m: float
    desnivel_m: float = Field(description="Llegada − arranque: de ahí salen los peldaños.")


class RampaDeLaEscalera(BaseModel):
    numero: int
    peldanos: int
    recorrido_m: float
    altura_m: float


class GeometriaDeLaEscalera(BaseModel):
    peldanos: int
    origen_de_peldanos: Literal["desnivel", "tecleados"]
    contrahuella_m: float = Field(description="Desnivel ÷ peldaños.")
    huella_m: float
    origen_de_huella: Literal["tecleada", "linea"] = Field(description="`linea`: salió del recorrido de una línea del plano (medición derivada).")
    longitud_inclinada_m: float = Field(description="Por peldaño: la hipotenusa de la huella y la contrahuella.")
    recorrido_horizontal_m: float
    rampas: list[RampaDeLaEscalera]
    descansos: int
    largo_del_descanso_m: float
    area_de_descanso_m2: float
    superficie_de_rampa_m2: float
    volumen_de_rampa_m3: float
    volumen_de_descanso_m3: float
    escalones_de_catalogo: float = Field(description="Peldaños × ancho ÷ 1.20 m: las piezas de EST-01510.")


class InsumoDeLaEscalera(BaseModel):
    parte: Literal["rampa", "descanso"]
    clave: str
    descripcion: str
    unidad: str
    cantidad: float
    origen: Literal["geometria", "catalogo"]
    nota: str


class ConceptoDeLaEscalera(BaseModel):
    parte: Literal["escalon", "descanso"]
    elemento_clave: str
    ref: str | None
    concepto: ConceptoDeLaFicha
    toma: list[str]
    cantidad: float = Field(description="La cantidad medida, en la unidad del concepto (escalón: pza de 1.20 m; descanso: m²).")
    unidad: str
    nota: str
    propuesta: PropuestaDelConceptoDeLosa | None = Field(
        default=None, description="Si el concepto es provisional: su propuesta vigente (pendiente o autorizada); `null` si nadie la ha propuesto."
    )


class ConceptoDeLaEscaleraPorEspacio(ConceptoDeLaEscalera):
    resolucion: ResolucionDelConcepto | None = Field(
        default=None, description="En qué partida del árbol se mide (solo el cálculo de una zona; el cálculo suelto no consulta el árbol)."
    )


class GrupoDeLaEscaleraPorEspacio(BaseModel):
    espacio_id: str | None = Field(description="El espacio; `null` = lo que no está asignado a ninguno.")
    espacio_nombre: str | None = None
    conceptos: list[ConceptoDeLaEscaleraPorEspacio]


class EscaleraCalculada(BaseModel):
    clave: str
    nombre: str
    parametros: ParametrosDeLaEscalera
    cotas: CotasDeLaEscalera
    geometria: GeometriaDeLaEscalera
    insumos: list[InsumoDeLaEscalera]
    conceptos: list[ConceptoDeLaEscalera]
    por_espacio: list[GrupoDeLaEscaleraPorEspacio] = Field(
        description="La escalera asignada a un espacio (0143): su cantidad se mide en la partida de ese espacio; la suma de los grupos es el total (sin doble conteo)."
    )
    mano_de_obra: ManoDeObraDeLaLosa
    advertencias: list[str]
    pendientes: list[PendienteDeLaLosa]


class EscaleraDeLaZonaPeticion(BaseModel):
    elemento_clave: Literal["ESC-FORJADA"] = "ESC-FORJADA"
    zona_llegada_id: UUID | None = Field(
        default=None, description="La zona cuyo piso es el de llegada (su cota de piso). Sin ella ni `cota_llegada_m`, la escalera llega a la cara alta de la losa de su zona."
    )
    cota_arranque_m: float | None = Field(default=None, ge=-30, le=100, description="Cota tecleada del arranque; sin ella vale el piso de la zona de arranque.")
    cota_llegada_m: float | None = Field(default=None, ge=-30, le=100, description="Cota tecleada de la llegada; no se combina con `zona_llegada_id`.")
    trazo_id: UUID | None = Field(
        default=None,
        description="Una línea del plano: su longitud (con la escala) es el recorrido horizontal de las rampas y da la huella, derivada al calcular. Una línea no sirve a dos escaleras.",
    )
    espacio_id: UUID | None = Field(
        default=None, description="El espacio donde está la escalera (0143); `null` = sin espacio (no se escribe en ninguna partida)."
    )
    peldanos: int | None = Field(default=None, ge=2, le=120)
    contrahuella_max_m: float | None = Field(default=None, ge=0.10, le=0.30)
    huella_m: float | None = Field(default=None, ge=0.15, le=0.60)
    ancho_m: float | None = Field(default=None, ge=0.40, le=5.0)
    espesor_m: float | None = Field(default=None, ge=0.05, le=0.50)
    rampas: int | None = Field(default=None, ge=1, le=4)
    largo_descanso_m: float | None = Field(default=None, ge=0.40, le=6.0)


class EscaleraDeLaZona(ParametrosDeLaEscalera):
    id: UUID
    zona_id: UUID
    elemento_clave: Literal["ESC-FORJADA"]
    zona_llegada_id: UUID | None
    cota_arranque_m: float | None
    cota_llegada_m: float | None
    trazo_id: UUID | None
    espacio_id: UUID | None


class ZonaDeLaEscalera(BaseModel):
    id: UUID
    plano_id: UUID
    nombre: str
    nivel: str | None
    cota_piso_m: float = Field(description="Cota del piso de la zona: el arranque por omisión.")
    cota_de_la_losa_m: float = Field(description="Cara alta de la losa de la zona (piso + altura libre + espesor): la llegada por omisión.")


class OrigenDeLasCotas(BaseModel):
    arranque: Literal["explicita", "zona"]
    llegada: Literal["explicita", "zona_de_llegada", "losa_de_la_zona"]


class EscaleraDeLaZonaCalculada(BaseModel):
    id: UUID
    trazo_id: UUID | None
    espacio_id: UUID | None
    zona_llegada_id: UUID | None
    origen_de_cotas: OrigenDeLasCotas
    error: str | None = Field(description="Si un dato de la escalera o de las zonas no vale (p. ej. la llegada quedó por debajo del arranque): el motivo; sin él no hay cálculo.")
    calculo: EscaleraCalculada | None
    conciliacion: ConciliacionDeLaLosa | None = Field(
        default=None, description="Solo si se pidió `conciliar`: lo que calcula por escalón contra la composición de EST-01510 del catálogo vigente."
    )


class ConceptoDeLosTotalesDeEscaleras(BaseModel):
    concepto: ConceptoDeLaFicha
    unidad: str
    cantidad: float
    propuesta: PropuestaDelConceptoDeLosa | None = None


class TotalesDeLasEscaleras(BaseModel):
    peldanos: int
    escalones_de_catalogo: float
    area_de_descanso_m2: float
    conceptos: list[ConceptoDeLosTotalesDeEscaleras]


class CalculoDeLasEscalerasDeLaZona(BaseModel):
    zona: ZonaDeLaEscalera
    escala_definida: bool = Field(description="Sin escala calibrada se toma 1 unidad de plano = 1 m para el recorrido y no se escribe nada en las partidas.")
    escaleras: list[EscaleraDeLaZonaCalculada]
    totales: TotalesDeLasEscaleras
    por_espacio: list[GrupoDeLaEscaleraPorEspacio] = Field(
        description="Lo que paga la escalera de cada espacio de la zona y en qué partida se mide; la suma de los grupos es el total (sin doble conteo)."
    )
    advertencias: list[str]


# ── Biblioteca: la ficha, el cálculo suelto y las propuestas de la escalera ──────────────────────────────


@router.get(
    "/biblioteca-de-elementos/escalera/{clave}",
    response_model=DefinicionDeLaEscalera,
    summary="La ficha de la escalera forjada (qué calcula, lo que toma del catálogo, sus dos conceptos y los pendientes)",
    responses=_NO_HAY_ESCALERA,
)
async def definicion_de_la_escalera(clave: str) -> dict[str, Any]:
    d = definicion_de_escalera(clave)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No hay un elemento de escalera «{clave}» en la biblioteca.")
    return d


@router.post(
    "/biblioteca-de-elementos/escalera/{clave}/calcular",
    response_model=EscaleraCalculada,
    summary="Calcula una escalera con las cotas que se mandan (solo cálculo; no guarda nada)",
    responses={**_NO_HAY_ESCALERA, 422: {"description": "Un dato no vale (p. ej. la llegada no está por encima del arranque)."}},
)
async def calcular_la_escalera(clave: str, peticion: CalculoDeLaEscaleraPeticion) -> dict[str, Any]:
    if not elemento_de_escalera(clave):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No hay un elemento de escalera «{clave}» en la biblioteca.")
    try:
        p = validar_parametros({k: getattr(peticion, k) for k in _CAMPOS})
        return calcular_escalera(
            EntradaEscalera(
                cota_arranque_m=peticion.cota_arranque_m, cota_llegada_m=peticion.cota_llegada_m, recorrido_m=peticion.recorrido_m, espacio_id=peticion.espacio_id, **p
            )
        )
    except ErrorDeEscalera as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e


@router.get(
    "/biblioteca-de-elementos/escalera/{clave}/propuestas",
    response_model=list[PropuestaDeEstructura],
    summary="Las propuestas de concepto nuevo de la escalera: pendientes, autorizadas y rechazadas",
    responses=_NO_HAY_ESCALERA,
)
async def propuestas_de_la_escalera(clave: str, caso_uso: GestionarPropuestasDeEscaleraDep) -> list[PropuestaDeEstructura]:
    return [a_propuesta(f) for f in await caso_uso.listar(clave)]


@router.post(
    "/biblioteca-de-elementos/escalera/{clave}/propuestas/concepto",
    response_model=ResultadoDeProponer,
    status_code=status.HTTP_201_CREATED,
    summary="Proponer el concepto nuevo del descanso de la escalera por m² (clave provisional, sin precio ni destajo; lo autoriza Control de obra)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_PROPONEN))],
    responses=_PROPONEN,
)
async def proponer_concepto_de_la_escalera(clave: str, ctx: ContextoActual, caso_uso: GestionarPropuestasDeEscaleraDep) -> ResultadoDeProponer:
    return ResultadoDeProponer(**await caso_uso.proponer_concepto_de_escalera(clave, usuario_id=ctx.usuario_id, rol=ctx.rol))


# ── Zona: escaleras y cálculo ────────────────────────────────────────────────────────────────────────────


@router.get(
    "/zonas-de-losa/{zona_id}/escaleras",
    response_model=list[EscaleraDeLaZona],
    summary="Las escaleras que arrancan en una zona de losa, con sus parámetros",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_LEEN))],
)
async def escaleras_de_la_zona(zona_id: UUID, caso_uso: GestionarEscalerasDep) -> list[dict[str, Any]]:
    return await caso_uso.escaleras(zona_id)


@router.post(
    "/zonas-de-losa/{zona_id}/escaleras",
    response_model=EscaleraDeLaZona,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar una escalera a la zona (solo Control de obra)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
    responses={422: {"description": "Una cota, un parámetro, la zona de llegada, la línea o el espacio no valen, o la línea ya da el recorrido de otra escalera."}},
)
async def agregar_escalera(zona_id: UUID, peticion: EscaleraDeLaZonaPeticion, ctx: ContextoActual, caso_uso: GestionarEscalerasDep) -> dict[str, Any]:
    datos = peticion.model_dump()
    return await caso_uso.agregar(
        zona_id, elemento_clave=datos.pop("elemento_clave"), zona_llegada_id=datos.pop("zona_llegada_id"), cota_arranque_m=datos.pop("cota_arranque_m"),
        cota_llegada_m=datos.pop("cota_llegada_m"), trazo_id=datos.pop("trazo_id"), espacio_id=datos.pop("espacio_id"), parametros=datos, autor_id=ctx.usuario_id,
    )


@router.put(
    "/escaleras-de-zona/{escalera_id}",
    response_model=EscaleraDeLaZona,
    summary="Cambiar una escalera de la zona (solo Control de obra); sin `espacio_id` conserva su espacio y un parámetro que no viene vuelve al de omisión",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
    responses={422: {"description": "Una cota, un parámetro, la zona de llegada, la línea o el espacio no valen, o la línea ya da el recorrido de otra escalera."}},
)
async def cambiar_escalera(escalera_id: UUID, peticion: EscaleraDeLaZonaPeticion, caso_uso: GestionarEscalerasDep) -> dict[str, Any]:
    datos = peticion.model_dump()
    espacio: dict[str, Any] = {"espacio_id": datos.pop("espacio_id")} if "espacio_id" in peticion.model_fields_set else {}
    return await caso_uso.cambiar(
        escalera_id, elemento_clave=datos.pop("elemento_clave"), zona_llegada_id=datos.pop("zona_llegada_id"), cota_arranque_m=datos.pop("cota_arranque_m"),
        cota_llegada_m=datos.pop("cota_llegada_m"), trazo_id=datos.pop("trazo_id"), parametros=datos, **espacio,
    )


@router.delete(
    "/escaleras-de-zona/{escalera_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Quitar una escalera de la zona (solo Control de obra)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
)
async def quitar_escalera(escalera_id: UUID, caso_uso: GestionarEscalerasDep) -> None:
    await caso_uso.quitar(escalera_id)


@router.get(
    "/zonas-de-losa/{zona_id}/escaleras/calculo",
    response_model=CalculoDeLasEscalerasDeLaZona,
    summary="El cálculo de las escaleras de una zona: cotas, peldaños, huella, descanso, insumos, conceptos y lo que paga cada espacio",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_LEEN))],
)
async def calculo_de_las_escaleras(
    zona_id: UUID,
    caso_uso: GestionarEscalerasDep,
    conciliar: bool = Query(default=False, description="Concilia la escalera contra la composición de EST-01510 del catálogo vigente, por escalón."),
) -> dict[str, Any]:
    return await caso_uso.calculo(zona_id, conciliar=conciliar)


@router.post(
    "/zonas-de-losa/{zona_id}/escaleras/propuestas",
    response_model=ResultadoDeProponer,
    status_code=status.HTTP_201_CREATED,
    summary="Proponer el concepto nuevo que las escaleras de la zona necesitan (el del descanso, si alguna lo lleva; idempotente)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_PROPONEN))],
    responses=_PROPONEN,
)
async def proponer_conceptos_de_las_escaleras(zona_id: UUID, ctx: ContextoActual, caso_uso: GestionarEscalerasDep) -> ResultadoDeProponer:
    return ResultadoDeProponer(**await caso_uso.proponer_conceptos(zona_id, usuario_id=ctx.usuario_id, rol=ctx.rol))
