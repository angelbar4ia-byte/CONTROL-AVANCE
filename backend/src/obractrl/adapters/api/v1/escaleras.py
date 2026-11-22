"""La escalera como elemento (Fase 4a: escaleras con cotas): ficha, cálculo, escaleras de la zona y propuesta del concepto nuevo del descanso.

- **Biblioteca** (`/biblioteca-de-elementos/escalera/…`): la ficha de la escalera forjada (ESC-FORJADA, concepto EST-01510 del catálogo por escalón de 1.20 m y concepto
  nuevo propuesto EJ-820 para el descanso), el **cálculo suelto** (con las cotas que se mandan; no guarda nada ni pide sesión) y la propuesta del concepto nuevo (regla
  F7). Se registra **antes** que las de la biblioteca: `/biblioteca-de-elementos/{clave}/calcular` también casaría.
- **Zona** (`/zonas-de-losa/{zona_id}/escaleras`): las escaleras que arrancan en la zona (las cotas salen de las zonas o se teclean; el recorrido, si se quiere, de una
  línea del plano; con espacio), su **cálculo** con lo que hay en el plano y la base (con la conciliación contra EST-01510 si se pide) y la propuesta de su concepto.
  Todos los roles que ven el plano leen; **solo Control de obra escribe** (lo exige también RLS).

- **Descansos y abanicos** (Fase 4d, migración 0148): `PUT /escaleras-de-zona/{id}/descansos` y `…/abanicos` dejan como únicos los que vienen (lista vacía = quita todos; los
  descansos sin fila propia conservan el implícito de 4a). Los leen las escaleras de la zona y su cálculo; escribe solo Control de obra.

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
    AbanicoDeEscalera,
    DescansoDeEscalera,
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


GiroDeDescanso = Literal[0, 90, 180]


class DescansoSuelto(BaseModel):
    posicion: int = Field(ge=1, le=3, description="Entre la rampa k y la k+1 (1 = entre la 1.ª y la 2.ª).")
    giro_grados: GiroDeDescanso = Field(default=90, description="El giro del recorrido en el descanso: 0 recto, 90 cambio de dirección, 180 vuelta.")
    largo_m: float | None = Field(default=None, ge=0.40, le=6.0, description="En el sentido de la marcha; sin él, el largo del descanso de la escalera o su ancho.")
    ancho_m: float | None = Field(default=None, ge=0.40, le=6.0, description="Transversal; sin él, el ancho de la escalera (el doble si gira 180°).")
    espesor_m: float | None = Field(default=None, ge=0.05, le=0.50, description="Sin él, el espesor de la escalera.")
    area_m2: float | None = Field(default=None, gt=0, le=100, description="El área medida (lo que daría un polígono del plano): manda sobre largo × ancho.")


class AbanicoDeLaPeticion(BaseModel):
    posicion: int = Field(ge=0, le=4, description="0 = antes de la 1.ª rampa; k = tras la rampa k.")
    escalones: int = Field(ge=1, le=12, description="Escalones de abanico del grupo: forman parte de los peldaños del desnivel.")
    ancho_interior_m: float = Field(ge=0.02, le=0.60, description="El fondo del peldaño en el borde interior (m).")
    ancho_exterior_m: float = Field(ge=0.10, le=0.80, description="El fondo del peldaño en el borde exterior (m); no menor que el interior. Su largo es el ancho de la escalera.")
    radio_huella_m: float | None = Field(
        default=None, ge=0.10, le=5.0, description="Distancia del borde interior a la línea de huella; sin él, 0.35 m (supuesto editable: el material dice 30 a 40 cm)."
    )


class DescansoDeLaPeticion(BaseModel):
    posicion: int = Field(ge=1, le=3, description="Entre la rampa k y la k+1 (1 = entre la 1.ª y la 2.ª).")
    giro_grados: GiroDeDescanso = Field(default=90, description="El giro del recorrido en el descanso: 0 recto, 90 cambio de dirección, 180 vuelta.")
    largo_m: float | None = Field(default=None, ge=0.40, le=6.0, description="En el sentido de la marcha; sin él, el largo del descanso de la escalera o su ancho.")
    ancho_m: float | None = Field(default=None, ge=0.40, le=6.0, description="Transversal; sin él, el ancho de la escalera (el doble si gira 180°).")
    espesor_m: float | None = Field(default=None, ge=0.05, le=0.50, description="Sin él, el espesor de la escalera.")
    trazo_id: UUID | None = Field(
        default=None, description="Un polígono del plano: su área (con la escala, al calcular) manda sobre largo × ancho. Un polígono no sirve a dos descansos ni puede ser una losa."
    )


class DescansosDeLaEscaleraPeticion(BaseModel):
    descansos: list[DescansoDeLaPeticion] = Field(max_length=3, description="Los únicos descansos propios; vacío = quita todos y vuelve al descanso implícito.")


class AbanicosDeLaEscaleraPeticion(BaseModel):
    abanicos: list[AbanicoDeLaPeticion] = Field(max_length=5, description="Los únicos grupos de abanico; vacío = quita todos.")


class DescansoDeLaEscalera(BaseModel):
    id: UUID
    posicion: int
    giro_grados: GiroDeDescanso
    largo_m: float | None
    ancho_m: float | None
    espesor_m: float | None
    trazo_id: UUID | None


class AbanicoDeLaEscalera(BaseModel):
    id: UUID
    posicion: int
    escalones: int
    ancho_interior_m: float
    ancho_exterior_m: float
    radio_huella_m: float


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
    radio_de_huella_por_defecto_m: float = Field(description="Supuesto editable: la línea de huella de un escalón de abanico se mide a esta distancia del borde interior.")
    giros_de_descanso: list[int] = Field(description="Los giros que admite un descanso: 0, 90 y 180 grados.")
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
    descansos: list[DescansoSuelto] = Field(default_factory=list, max_length=3, description="Descansos propios (Fase 4d); una posición sin descanso conserva el implícito.")
    abanicos: list[AbanicoDeLaPeticion] = Field(default_factory=list, max_length=5, description="Grupos de escalones de abanico (Fase 4d): forman parte de los peldaños del desnivel.")


class CotasDeLaEscalera(BaseModel):
    arranque_m: float
    llegada_m: float
    desnivel_m: float = Field(description="Llegada − arranque: de ahí salen los peldaños.")


class RampaDeLaEscalera(BaseModel):
    numero: int
    peldanos: int
    recorrido_m: float
    altura_m: float


class DescansoCalculado(BaseModel):
    id: UUID | None
    posicion: int
    giro_grados: GiroDeDescanso | None = Field(description="`null` = el descanso implícito (sin fila propia: no dice su giro).")
    largo_m: float | None = Field(description="`null` si el área sale de un polígono del plano.")
    ancho_m: float | None = Field(description="`null` si el área sale de un polígono del plano.")
    espesor_m: float
    area_m2: float
    volumen_m3: float
    origen: Literal["implicito", "dimensiones", "plano"] = Field(description="De dónde sale el área: el descanso implícito de 4a, sus dimensiones o un polígono del plano.")


class AbanicoCalculado(BaseModel):
    id: UUID | None
    posicion: int
    escalones: int
    ancho_interior_m: float
    ancho_exterior_m: float
    radio_huella_m: float
    huella_en_la_linea_m: float = Field(description="El fondo del peldaño a `radio_huella_m` del borde interior: la huella que se compara con la de referencia.")
    ancho_medio_m: float = Field(description="Promedio de los fondos del borde interior y del exterior.")
    angulo_por_escalon_grados: float
    giro_total_grados: float = Field(description="Lo que gira el grupo: escalones × ángulo por escalón (debería cerrar 90° o 180°).")
    radio_interior_m: float | None = Field(description="Distancia del vértice del abanico al borde interior; `null` si los dos bordes miden igual (no gira).")
    area_en_planta_m2: float
    superficie_m2: float = Field(description="Área en planta × la inclinación de la línea de huella.")
    volumen_m3: float
    escalones_de_catalogo: float = Field(description="Piezas de EST-01510 del grupo: ancho × fondo medio × escalones ÷ (1.20 × huella de referencia).")


class GeometriaDeLaEscalera(BaseModel):
    peldanos: int = Field(description="Los del desnivel: los rectos más los de abanico (no se cuentan dos veces).")
    peldanos_rectos: int
    peldanos_de_abanico: int
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
    descansos_detalle: list[DescansoCalculado]
    abanicos: list[AbanicoCalculado]
    area_de_abanico_m2: float
    superficie_de_abanico_m2: float
    volumen_de_abanico_m3: float
    escalones_rectos_de_catalogo: float = Field(description="Peldaños rectos × ancho ÷ 1.20 m.")
    escalones_de_abanico_de_catalogo: float
    escalones_de_catalogo: float = Field(description="Las piezas de EST-01510: peldaños rectos × ancho ÷ 1.20 m más las de los escalones de abanico.")


class InsumoDeLaEscalera(BaseModel):
    parte: Literal["rampa", "descanso", "abanico"]
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
    descansos: list[DescansoDeLaEscalera] = Field(default_factory=list, description="Los descansos propios (Fase 4d); una posición sin fila conserva el descanso implícito.")
    abanicos: list[AbanicoDeLaEscalera] = Field(default_factory=list, description="Los grupos de escalones de abanico (Fase 4d).")


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
    descansos: list[DescansoDeLaEscalera] = Field(default_factory=list, description="Los descansos propios de la escalera (filas editables).")
    abanicos: list[AbanicoDeLaEscalera] = Field(default_factory=list, description="Los grupos de abanico de la escalera (filas editables).")
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
    peldanos_de_abanico: int
    area_de_abanico_m2: float
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
                cota_arranque_m=peticion.cota_arranque_m, cota_llegada_m=peticion.cota_llegada_m, recorrido_m=peticion.recorrido_m, espacio_id=peticion.espacio_id, **p,
                descansos=tuple(DescansoDeEscalera(**d.model_dump()) for d in peticion.descansos),
                abanicos=tuple(
                    AbanicoDeEscalera(**{k: v for k, v in a.model_dump().items() if v is not None}) for a in peticion.abanicos
                ),
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


@router.put(
    "/escaleras-de-zona/{escalera_id}/descansos",
    response_model=EscaleraDeLaZona,
    summary="Dejar como únicos descansos propios de la escalera los que vienen (solo Control de obra; vacío = vuelve al descanso implícito)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
    responses={422: {"description": "Una posición, un giro, una medida o un polígono no valen, o el cambio deja la escalera sin poder calcularse."}, 404: {"description": "No existe esa escalera."}},
)
async def cambiar_descansos(escalera_id: UUID, peticion: DescansosDeLaEscaleraPeticion, ctx: ContextoActual, caso_uso: GestionarEscalerasDep) -> dict[str, Any]:
    return await caso_uso.cambiar_descansos(escalera_id, [d.model_dump() for d in peticion.descansos], ctx.usuario_id)


@router.put(
    "/escaleras-de-zona/{escalera_id}/abanicos",
    response_model=EscaleraDeLaZona,
    summary="Dejar como únicos grupos de escalones de abanico de la escalera los que vienen (solo Control de obra; vacío = quita todos)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
    responses={422: {"description": "Una posición, un fondo o un radio no valen, o los escalones de abanico no caben en los peldaños de la escalera."}, 404: {"description": "No existe esa escalera."}},
)
async def cambiar_abanicos(escalera_id: UUID, peticion: AbanicosDeLaEscaleraPeticion, ctx: ContextoActual, caso_uso: GestionarEscalerasDep) -> dict[str, Any]:
    return await caso_uso.cambiar_abanicos(escalera_id, [a.model_dump() for a in peticion.abanicos], ctx.usuario_id)


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
