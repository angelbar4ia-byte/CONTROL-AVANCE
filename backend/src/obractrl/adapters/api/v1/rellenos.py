"""El relleno como elemento (Fase 3 de las zonas de losa): ficha, cálculo, rellenos de la zona y propuesta del concepto nuevo.

- **Biblioteca** (`/biblioteca-de-elementos/relleno/…`): la ficha del relleno de azotea (REL-AZOTEA, concepto ALB-03014 del catálogo) y del compactado
  (REL-COMPACTADO, concepto nuevo propuesto EJ-810), el **cálculo suelto** (con los polígonos que se mandan; no guarda nada ni pide sesión) y la propuesta del
  concepto nuevo (regla F7). Se registra **antes** que las de la biblioteca: `/biblioteca-de-elementos/{clave}/calcular` también casaría.
- **Zona** (`/zonas-de-losa/{zona_id}/rellenos`): los rellenos de la zona (de toda la zona o de un polígono del plano, con parámetros editables y espacio), su
  **cálculo** con lo que hay en el plano y la base (con la conciliación contra ALB-03014 si se pide) y la propuesta de su concepto. Todos los roles que ven el
  plano leen; **solo Control de obra escribe** (lo exige también RLS).

El cálculo vive en el dominio (`relleno`); controladores delgados.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    GestionarPropuestasDeRellenoDep,
    GestionarRellenosDep,
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
from obractrl.domain.cuantificacion.relleno import (
    EntradaRelleno,
    ErrorDeRelleno,
    PoligonoDeRelleno,
    calcular_relleno,
    definicion_de_relleno,
    elemento_de_relleno,
    validar_parametros,
)
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["rellenos"])

ROLES_QUE_PROPONEN = (Rol.CONTROL_OBRA, Rol.COSTOS)
ROLES_QUE_EDITAN = (Rol.CONTROL_OBRA,)
ROLES_QUE_LEEN = (Rol.RESIDENTE, Rol.SUPERVISOR, Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE, Rol.COSTOS)

_NO_HAY_RELLENO = {404: {"description": "No hay un elemento de relleno con esa clave (REL-AZOTEA o REL-COMPACTADO)."}}
_PROPONEN = {403: {"description": "Proponen Costos y Control de obra."}, 404: {"description": "No existe ese elemento."}}


# ── Modelos ─────────────────────────────────────────────────────────────────────────────────────────────


class ParametrosDelRelleno(BaseModel):
    espesor_m: float = Field(description="Espesor mínimo del relleno (m); a él se suman la compensación de espesores de losa y la pendiente.")
    pendiente_pct: float = Field(description="Pendiente del relleno (%): con el recorrido da el volumen en cuña (pendiente × recorrido / 2).")
    recorrido_m: float = Field(description="Recorrido (m) sobre el que corre la pendiente.")
    compensar_espesores: bool = Field(description="Las subzonas de losa más delgadas reciben la diferencia contra la más gruesa de la zona.")
    abundamiento_pct: float = Field(description="Solo el compactado: % de material suelto de más; es (factor_abundamiento − 1) × 100 (el catálogo no trae factor; por omisión 0).")
    mortero_m3_por_m2: float = Field(description="Solo la azotea sin bajadas: m³ de mortero por m² (el del catálogo: 0.0735).")
    pendiente_zona_pct: float = Field(
        default=2.0, description="Solo la azotea con bajadas: pendiente (%) de la zona; el espesor de la arenilla sube pendiente × distancia desde la bajada (2 % por omisión)."
    )
    espesor_bajada_m: float = Field(default=0.05, description="Solo la azotea con bajadas: espesor mínimo de arenilla en cada bajada (5 cm por omisión).")
    mortero_espesor_m: float = Field(default=0.05, description="Solo la azotea con bajadas: espesor de la plantilla de mortero sobre la arenilla (5 cm por omisión).")
    factor_abundamiento: float = Field(
        default=1.0, description="Solo el compactado: la cantidad del concepto es el volumen compactado × este factor (1.00 por omisión; sin destajo)."
    )


class InsumoDeLaFichaDelRelleno(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    por_m2: float
    m3_por_viaje: float | None = None
    fuente: str


class DefinicionDelRelleno(BaseModel):
    clave: str
    nombre: str
    tipo: Literal["azotea", "compactado"]
    se_mide_por: str
    categoria: ClaveYNombreDeLosa
    subcategoria: ClaveYNombreDeLosa
    concepto: ConceptoDeLaFicha
    parametros_por_defecto: ParametrosDelRelleno
    concepto_arenilla: ConceptoDeLaFicha | None = Field(
        default=None, description="Solo la azotea: el concepto nuevo propuesto (EJ-830, por m³) de la arenilla del relleno con bajadas."
    )
    tezontle: InsumoDeLaFichaDelRelleno | None
    mortero: InsumoDeLaFichaDelRelleno | None
    destajos_candidatos: list[DestajoCandidato]
    pendientes: list[PendienteDeLaLosa]


class PoligonoDelRellenoPeticion(BaseModel):
    area_m2: float = Field(ge=0, le=1_000_000, description="Área neta del polígono de losa que el relleno cubre (ya sin huecos).")
    espesor_de_losa_m: float | None = Field(default=None, gt=0, le=3, description="Subzona: espesor estructural propio; sin él vale el de la zona.")
    espacio_id: str | None = Field(default=None, max_length=60, description="Una etiqueta del espacio donde cae el polígono (0143): reparte el cálculo por espacio.")


class CalculoDelRellenoPeticion(BaseModel):
    espesor_de_la_zona_m: float = Field(default=0.12, gt=0, le=3, description="Espesor de la losa de la zona.")
    espesor_maximo_de_la_zona_m: float | None = Field(
        default=None, gt=0, le=3, description="La losa más gruesa de toda la zona (referencia de la compensación); sin ella vale la más gruesa de los polígonos."
    )
    poligonos: list[PoligonoDelRellenoPeticion] = Field(default_factory=list, max_length=200)
    espesor_m: float | None = Field(default=None, ge=0, le=2, description="Sin él vale el de omisión del elemento.")
    pendiente_pct: float | None = Field(default=None, ge=0, le=30)
    recorrido_m: float | None = Field(default=None, ge=0, le=100)
    compensar_espesores: bool | None = None
    abundamiento_pct: float | None = Field(default=None, ge=0, le=60)
    mortero_m3_por_m2: float | None = Field(default=None, ge=0, le=0.5)
    pendiente_zona_pct: float | None = Field(default=None, ge=0, le=30)
    espesor_bajada_m: float | None = Field(default=None, ge=0.01, le=0.30)
    mortero_espesor_m: float | None = Field(default=None, ge=0, le=0.20)
    factor_abundamiento: float | None = Field(default=None, ge=1, le=1.6, description="Solo el compactado: el factor del abundamiento (1.00 por omisión).")
    espacio_id: str | None = Field(default=None, max_length=60, description="Una etiqueta de espacio para todo el relleno (0143).")


class PoligonoCalculadoDelRelleno(BaseModel):
    id: str
    area_m2: float
    espesor_de_losa_m: float
    subzona: bool
    compensacion_m: float = Field(description="Lo que el relleno suma para igualar la losa más gruesa de la zona.")
    espesor_m: float = Field(description="El espesor del relleno en este polígono: mínimo + compensación + pendiente.")
    volumen_m3: float
    espacio_id: str | None


class InsumoDelRelleno(BaseModel):
    parte: Literal["tezontle", "mortero", "arenilla"]
    clave: str
    descripcion: str
    unidad: str
    cantidad: float
    origen: Literal["zona", "catalogo"]
    nota: str


class ConceptoDelRelleno(BaseModel):
    parte: Literal["relleno", "arenilla"] = Field(description="`relleno`: el concepto del relleno; `arenilla`: la arenilla del relleno de azotea con bajadas (EJ-830, por m³).")
    elemento_clave: str
    ref: str | None
    concepto: ConceptoDeLaFicha
    toma: list[str]
    cantidad: float = Field(description="La cantidad medida, en la unidad del concepto (azotea: m²; compactado: m³).")
    unidad: str
    nota: str
    propuesta: PropuestaDelConceptoDeLosa | None = Field(
        default=None, description="Si el concepto es provisional: su propuesta vigente (pendiente o autorizada); `null` si nadie la ha propuesto."
    )


class ConceptoDelRellenoPorEspacio(ConceptoDelRelleno):
    resolucion: ResolucionDelConcepto | None = Field(
        default=None, description="En qué partida del árbol se mide (solo el cálculo de una zona; el cálculo suelto no consulta el árbol)."
    )


class GrupoDelRellenoPorEspacio(BaseModel):
    espacio_id: str | None = Field(description="El espacio; `null` = lo que no está asignado a ninguno.")
    espacio_nombre: str | None = None
    area_m2: float
    volumen_m3: float
    conceptos: list[ConceptoDelRellenoPorEspacio]


class BajadaCalculada(BaseModel):
    id: str
    x: float = Field(description="Coordenadas de la bajada en unidades del plano.")
    y: float
    rotulo: str | None
    linea_trazada: bool
    area_m2: float | None = Field(default=None, description="Lo que esta bajada drena (m²); sin él, el cálculo no corrió (sin escala).")
    distancia_maxima_m: float | None = None
    espesor_maximo_m: float | None = Field(default=None, description="El espesor de arenilla en el punto más lejano que drena esta bajada.")
    fuera_de_la_zona: bool | None = None


class GuiaDelRelleno(BaseModel):
    tipo: Literal["pendiente", "hilo"] = Field(
        description="`pendiente`: la línea que marca hacia dónde van las pendientes; `hilo`: un hilo de nivel (maestra) punteado, donde el espesor es constante."
    )
    origen: Literal["trazada", "generada"]
    bajada_id: str
    puntos: list[list[float]] = Field(description="Vértices de la polilínea en unidades del plano; en una línea de pendiente, el último es la bajada.")
    espesor_m: float | None = Field(default=None, description="De un hilo de nivel: el espesor de la arenilla sobre él.")


class DinamicoDelRelleno(BaseModel):
    estado: Literal["calculado", "sin_escala"] = Field(description="`sin_escala`: el plano no tiene escala calibrada y no hay cantidades.")
    pendiente_pct: float | None = None
    espesor_en_bajada_m: float | None = None
    mortero_espesor_m: float | None = None
    volumen_arenilla_m3: float | None = None
    espesor_arenilla_medio_m: float | None = None
    espesor_arenilla_maximo_m: float | None = None
    volumen_mortero_m3: float | None = None
    metodo: str | None = Field(default=None, description="Cómo se integró el espesor sobre el área (determinista).")
    celda_m: float | None = Field(default=None, description="Paso de la retícula de integración.")
    muestras: int | None = None
    error_estimado_m3: float | None = Field(default=None, description="Diferencia contra la retícula gruesa: cota práctica del error del volumen.")
    error_relativo: float | None = None
    bajadas: list[BajadaCalculada]
    guias: list[GuiaDelRelleno] = Field(default_factory=list)


class RellenoCalculado(BaseModel):
    clave: str
    nombre: str
    tipo: Literal["azotea", "compactado"]
    parametros: ParametrosDelRelleno
    espesor_de_la_zona_m: float
    espesor_maximo_de_la_zona_m: float
    area_m2: float
    volumen_m3: float
    volumen_suelto_m3: float | None = Field(description="Solo el compactado: el volumen compactado con el abundamiento.")
    espesor_medio_m: float
    extra_de_pendiente_m: float
    modo: Literal["uniforme", "bajadas"] = Field(description="`bajadas`: la azotea tiene bajadas pluviales y es dinámica (arenilla + mortero).")
    dinamico: DinamicoDelRelleno | None = Field(default=None, description="Solo con bajadas: el espesor de la arenilla, el método, el error, las bajadas y las guías.")
    poligonos: list[PoligonoCalculadoDelRelleno]
    insumos: list[InsumoDelRelleno]
    conceptos: list[ConceptoDelRelleno]
    por_espacio: list[GrupoDelRellenoPorEspacio] = Field(
        description="El mismo relleno repartido por espacio (0143): cada polígono cae en un solo grupo, así que la suma de los grupos es el total (sin doble conteo)."
    )
    mano_de_obra: ManoDeObraDeLaLosa
    advertencias: list[str]
    pendientes: list[PendienteDeLaLosa]


class RellenoDeLaZonaPeticion(BaseModel):
    elemento_clave: Literal["REL-AZOTEA", "REL-COMPACTADO"]
    trazo_id: UUID | None = Field(
        default=None,
        description="Un polígono de losa de la zona: su área (con la escala del plano) es la que se rellena, derivada al calcular. Sin él cubre todos los polígonos de la zona.",
    )
    espacio_id: UUID | None = Field(
        default=None, description="El espacio donde está el relleno (0143); `null` = el de cada polígono que cubre. Con espacio, su concepto se mide en la partida de ese espacio."
    )
    espesor_m: float | None = Field(default=None, ge=0, le=2, description="Sin él vale el de omisión del elemento.")
    pendiente_pct: float | None = Field(default=None, ge=0, le=30)
    recorrido_m: float | None = Field(default=None, ge=0, le=100)
    compensar_espesores: bool | None = None
    abundamiento_pct: float | None = Field(default=None, ge=0, le=60)
    mortero_m3_por_m2: float | None = Field(default=None, ge=0, le=0.5)
    pendiente_zona_pct: float | None = Field(default=None, ge=0, le=30, description="Azotea con bajadas: la pendiente de la zona (%); sin él vale 2 %.")
    espesor_bajada_m: float | None = Field(default=None, ge=0.01, le=0.30, description="Azotea con bajadas: el espesor mínimo de arenilla en la bajada; sin él, 5 cm.")
    mortero_espesor_m: float | None = Field(default=None, ge=0, le=0.20, description="Azotea con bajadas: el espesor de la plantilla de mortero; sin él, 5 cm.")
    factor_abundamiento: float | None = Field(default=None, ge=1, le=1.6, description="Compactado: cantidad = volumen compactado × factor; sin él, 1.00.")


class BajadaDelRellenoPeticion(BaseModel):
    trazo_id: UUID = Field(description="El PUNTO del plano que identifica la bajada (un punto sirve a una sola bajada).")
    linea_trazo_id: UUID | None = Field(
        default=None, description="Opcional: la LÍNEA del plano, dibujada hacia la bajada, que marca hacia dónde van las pendientes; sin ella el sistema la genera."
    )
    rotulo: str | None = Field(default=None, max_length=40)


class BajadaDelRellenoCambio(BaseModel):
    linea_trazo_id: UUID | None = Field(default=None, description="La línea de pendiente; `null` la quita y el sistema vuelve a generar la dirección.")
    rotulo: str | None = Field(default=None, max_length=40)


class BajadaDelRelleno(BaseModel):
    id: UUID
    relleno_id: UUID
    trazo_id: UUID
    linea_trazo_id: UUID | None
    rotulo: str | None


class BajadaDeLaZona(BaseModel):
    id: UUID
    trazo_id: UUID
    linea_trazo_id: UUID | None
    rotulo: str | None
    x: float = Field(description="Coordenadas del punto en unidades del plano.")
    y: float
    linea: list[list[float]] | None = Field(default=None, description="La línea de pendiente trazada hacia la bajada (unidades del plano), si la hay.")


class BajadaDelPlano(BaseModel):
    id: UUID
    relleno_id: UUID
    zona_id: UUID
    x: float
    y: float
    rotulo: str | None


class GuiaDelPlano(GuiaDelRelleno):
    relleno_id: UUID
    zona_id: UUID


class GuiasDeRellenoDelPlano(BaseModel):
    plano_id: UUID
    escala_definida: bool = Field(description="Sin escala calibrada no hay guías: el relleno con bajadas no da cantidades.")
    bajadas: list[BajadaDelPlano]
    guias: list[GuiaDelPlano]


class RellenoDeLaZona(ParametrosDelRelleno):
    id: UUID
    zona_id: UUID
    elemento_clave: Literal["REL-AZOTEA", "REL-COMPACTADO"]
    tipo: Literal["azotea", "compactado"] | None
    trazo_id: UUID | None
    espacio_id: UUID | None


class ZonaDelRelleno(BaseModel):
    id: UUID
    plano_id: UUID
    nombre: str
    nivel: str | None
    espesor_m: float
    espesor_maximo_m: float


class RellenoDeLaZonaCalculado(RellenoCalculado):
    id: UUID
    trazo_id: UUID | None
    espacio_id: UUID | None
    bajadas: list[BajadaDeLaZona] = Field(default_factory=list, description="Las bajadas pluviales del relleno de azotea (puntos del plano).")
    origen: Literal["zona", "poligono"] = Field(description="`poligono`: cubre un polígono del plano (medición derivada); `zona`: todos los de la zona.")
    conciliacion: ConciliacionDeLaLosa | None = Field(
        default=None, description="Solo el de azotea y si se pidió `conciliar`: lo que calcula por m² contra la composición de ALB-03014 del catálogo vigente."
    )


class ConceptoDeLosTotales(BaseModel):
    concepto: ConceptoDeLaFicha
    unidad: str
    cantidad: float
    propuesta: PropuestaDelConceptoDeLosa | None = None


class TotalesDeLosRellenos(BaseModel):
    area_m2: float
    volumen_m3: float
    conceptos: list[ConceptoDeLosTotales]


class CalculoDeLosRellenosDeLaZona(BaseModel):
    zona: ZonaDelRelleno
    escala_definida: bool = Field(description="Sin escala calibrada se toma 1 unidad de plano = 1 m y no se escribe nada en las partidas.")
    rellenos: list[RellenoDeLaZonaCalculado]
    totales: TotalesDeLosRellenos
    por_espacio: list[GrupoDelRellenoPorEspacio] = Field(
        description="Lo que paga el relleno de cada espacio de la zona y en qué partida se mide; la suma de los grupos es el total (sin doble conteo)."
    )
    advertencias: list[str]


# ── Biblioteca: la ficha, el cálculo suelto y las propuestas del relleno ─────────────────────────────────


@router.get(
    "/biblioteca-de-elementos/relleno/{clave}",
    response_model=DefinicionDelRelleno,
    summary="La ficha del relleno de azotea o compactado (qué calcula, lo que toma del catálogo, su concepto y los pendientes)",
    responses=_NO_HAY_RELLENO,
)
async def definicion_del_relleno(clave: str) -> dict[str, Any]:
    d = definicion_de_relleno(clave)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No hay un elemento de relleno «{clave}» en la biblioteca.")
    return d


@router.post(
    "/biblioteca-de-elementos/relleno/{clave}/calcular",
    response_model=RellenoCalculado,
    summary="Calcula un relleno con los polígonos que se mandan (solo cálculo; no guarda nada)",
    responses={**_NO_HAY_RELLENO, 422: {"description": "Un dato no vale."}},
)
async def calcular_el_relleno(clave: str, peticion: CalculoDelRellenoPeticion) -> dict[str, Any]:
    tipo = elemento_de_relleno(clave)
    if tipo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No hay un elemento de relleno «{clave}» en la biblioteca.")
    try:
        parametros = {
            k: v for k, v in peticion.model_dump().items()
            if k in (
                "espesor_m", "pendiente_pct", "recorrido_m", "compensar_espesores", "abundamiento_pct", "mortero_m3_por_m2", "pendiente_zona_pct", "espesor_bajada_m",
                "mortero_espesor_m", "factor_abundamiento",
            )
            and v is not None
        }
        p = validar_parametros(tipo, parametros)
        return calcular_relleno(
            EntradaRelleno(
                tipo=tipo, espesor_de_la_zona_m=peticion.espesor_de_la_zona_m, espesor_maximo_de_la_zona_m=peticion.espesor_maximo_de_la_zona_m,
                poligonos=[
                    PoligonoDeRelleno(area_m2=lo.area_m2, espesor_de_losa_m=lo.espesor_de_losa_m, espacio_id=lo.espacio_id) for lo in peticion.poligonos
                ],
                espacio_id=peticion.espacio_id, **p,
            )
        )
    except ErrorDeRelleno as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e


@router.get(
    "/biblioteca-de-elementos/relleno/{clave}/propuestas",
    response_model=list[PropuestaDeEstructura],
    summary="Las propuestas de concepto nuevo del relleno: pendientes, autorizadas y rechazadas",
    responses=_NO_HAY_RELLENO,
)
async def propuestas_del_relleno(clave: str, caso_uso: GestionarPropuestasDeRellenoDep) -> list[PropuestaDeEstructura]:
    return [a_propuesta(f) for f in await caso_uso.listar(clave)]


@router.post(
    "/biblioteca-de-elementos/relleno/{clave}/propuestas/concepto",
    response_model=ResultadoDeProponer,
    status_code=status.HTTP_201_CREATED,
    summary="Proponer el concepto nuevo del relleno compactado por m³ (clave provisional, sin precio ni destajo; lo autoriza Control de obra)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_PROPONEN))],
    responses={**_PROPONEN, 422: {"description": "El relleno de azotea usa ALB-03014 del catálogo: no necesita concepto nuevo."}},
)
async def proponer_concepto_del_relleno(clave: str, ctx: ContextoActual, caso_uso: GestionarPropuestasDeRellenoDep) -> ResultadoDeProponer:
    return ResultadoDeProponer(**await caso_uso.proponer_concepto_de_relleno(clave, usuario_id=ctx.usuario_id, rol=ctx.rol))


# ── Zona: rellenos y cálculo ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/zonas-de-losa/{zona_id}/rellenos",
    response_model=list[RellenoDeLaZona],
    summary="Los rellenos de una zona de losa, con sus parámetros",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_LEEN))],
)
async def rellenos_de_la_zona(zona_id: UUID, caso_uso: GestionarRellenosDep) -> list[dict[str, Any]]:
    return await caso_uso.rellenos(zona_id)


@router.post(
    "/zonas-de-losa/{zona_id}/rellenos",
    response_model=RellenoDeLaZona,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar un relleno a la zona (solo Control de obra)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
    responses={422: {"description": "El elemento, un parámetro, el polígono o el espacio no valen, o el relleno cubriría dos veces lo mismo."}},
)
async def agregar_relleno(zona_id: UUID, peticion: RellenoDeLaZonaPeticion, ctx: ContextoActual, caso_uso: GestionarRellenosDep) -> dict[str, Any]:
    datos = peticion.model_dump()
    return await caso_uso.agregar(
        zona_id, elemento_clave=datos.pop("elemento_clave"), trazo_id=datos.pop("trazo_id"), espacio_id=datos.pop("espacio_id"), parametros=datos,
        autor_id=ctx.usuario_id,
    )


@router.put(
    "/rellenos-de-zona/{relleno_id}",
    response_model=RellenoDeLaZona,
    summary="Cambiar un relleno de la zona (solo Control de obra); sin `espacio_id` conserva su espacio y un parámetro que no viene vuelve al de omisión",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
    responses={422: {"description": "El elemento, un parámetro, el polígono o el espacio no valen, o el relleno cubriría dos veces lo mismo."}},
)
async def cambiar_relleno(relleno_id: UUID, peticion: RellenoDeLaZonaPeticion, caso_uso: GestionarRellenosDep) -> dict[str, Any]:
    datos = peticion.model_dump()
    espacio: dict[str, Any] = {"espacio_id": datos.pop("espacio_id")} if "espacio_id" in peticion.model_fields_set else {}
    return await caso_uso.cambiar(relleno_id, elemento_clave=datos.pop("elemento_clave"), trazo_id=datos.pop("trazo_id"), parametros=datos, **espacio)


@router.delete(
    "/rellenos-de-zona/{relleno_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Quitar un relleno de la zona (solo Control de obra)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
)
async def quitar_relleno(relleno_id: UUID, caso_uso: GestionarRellenosDep) -> None:
    await caso_uso.quitar(relleno_id)


@router.get(
    "/zonas-de-losa/{zona_id}/rellenos/calculo",
    response_model=CalculoDeLosRellenosDeLaZona,
    summary="El cálculo de los rellenos de una zona: volumen, espesor por polígono, insumos, conceptos y lo que paga cada espacio",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_LEEN))],
    responses={422: {"description": "Un dato de la zona no vale."}},
)
async def calculo_de_los_rellenos(
    zona_id: UUID,
    caso_uso: GestionarRellenosDep,
    conciliar: bool = Query(default=False, description="Concilia el relleno de azotea contra la composición de ALB-03014 del catálogo vigente."),
) -> dict[str, Any]:
    return await caso_uso.calculo(zona_id, conciliar=conciliar)


@router.post(
    "/zonas-de-losa/{zona_id}/rellenos/propuestas",
    response_model=ResultadoDeProponer,
    status_code=status.HTTP_201_CREATED,
    summary="Proponer el concepto nuevo que los rellenos de la zona necesitan (el del compactado; idempotente)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_PROPONEN))],
    responses=_PROPONEN,
)
async def proponer_conceptos_de_los_rellenos(zona_id: UUID, ctx: ContextoActual, caso_uso: GestionarRellenosDep) -> ResultadoDeProponer:
    return ResultadoDeProponer(**await caso_uso.proponer_conceptos(zona_id, usuario_id=ctx.usuario_id, rol=ctx.rol))


# ── Bajadas pluviales del relleno dinámico de azotea (0147) ──────────────────────────────────────────────

_BAJADA_422 = {422: {"description": "El punto o la línea no valen (no son del plano, no son un punto o una línea, o ya sirven a otra bajada) o el relleno no es de azotea."}}


@router.post(
    "/rellenos-de-zona/{relleno_id}/bajadas",
    response_model=BajadaDelRelleno,
    status_code=status.HTTP_201_CREATED,
    summary="Convertir un punto del plano en una bajada pluvial del relleno de azotea (solo Control de obra)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
    responses=_BAJADA_422,
)
async def agregar_bajada(relleno_id: UUID, peticion: BajadaDelRellenoPeticion, ctx: ContextoActual, caso_uso: GestionarRellenosDep) -> dict[str, Any]:
    return await caso_uso.agregar_bajada(
        relleno_id, trazo_id=peticion.trazo_id, linea_trazo_id=peticion.linea_trazo_id, rotulo=peticion.rotulo, autor_id=ctx.usuario_id
    )


@router.put(
    "/bajadas-de-relleno/{bajada_id}",
    response_model=BajadaDelRelleno,
    summary="Cambiar el rótulo o la línea de pendiente de una bajada (solo Control de obra); sin línea el sistema genera la dirección",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
    responses=_BAJADA_422,
)
async def cambiar_bajada(bajada_id: UUID, peticion: BajadaDelRellenoCambio, caso_uso: GestionarRellenosDep) -> dict[str, Any]:
    return await caso_uso.cambiar_bajada(bajada_id, linea_trazo_id=peticion.linea_trazo_id, rotulo=peticion.rotulo)


@router.delete(
    "/bajadas-de-relleno/{bajada_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Quitar una bajada del relleno (solo Control de obra); el punto queda en el plano como un trazo cualquiera",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
)
async def quitar_bajada(bajada_id: UUID, caso_uso: GestionarRellenosDep) -> None:
    await caso_uso.quitar_bajada(bajada_id)


@router.get(
    "/planos/{plano_id}/guias-de-relleno",
    response_model=GuiasDeRellenoDelPlano,
    summary="Las bajadas y las guías del relleno dinámico del plano: líneas de pendiente e hilos de nivel punteados (en unidades del plano)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_LEEN))],
)
async def guias_de_relleno_del_plano(plano_id: UUID, caso_uso: GestionarRellenosDep) -> dict[str, Any]:
    return await caso_uso.guias_del_plano(plano_id)
