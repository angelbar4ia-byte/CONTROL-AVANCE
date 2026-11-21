"""La matriz de conceptos de la losa (fase 2 de las zonas de losa): ficha, cálculo, elementos de la zona y propuestas de concepto nuevo.

- **Biblioteca** (`/biblioteca-de-elementos/losa/…`): la ficha de la losa maciza y de la nervada, el **cálculo suelto** (con áreas y elementos que se
  mandan; no guarda nada y no pide sesión salvo que traiga `obra_id` para leer los drivers) y las propuestas del concepto nuevo de la losa por m²
  (regla F7). Se registra **antes** que las de la biblioteca: `/biblioteca-de-elementos/{clave}/calcular` también casaría.
- **Colado y cimbra por ml de las trabes** (D8): `POST /biblioteca-de-elementos/estructura/{clave}/propuestas/colado-por-ml` propone el concepto nuevo
  (clave provisional, sin precio) con su destajo por ml sin importe. Costos o Control de obra proponen; solo Control de obra autoriza.
- **Zona** (`/zonas-de-losa/{zona_id}/…`): los elementos de la zona (trabes, contratrabes y nervaduras, por ml o por pieza, con medición derivada de una
  línea del plano si se quiere), su **matriz calculada** con lo que hay en el plano y la base, y la propuesta de los conceptos que le faltan. Todos los
  roles que ven el plano leen; **solo Control de obra escribe elementos** (lo exige también RLS).

El cálculo vive en el dominio (`matriz_de_losa`); controladores delgados.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    DriversDeObraDep,
    GestionarMatrizDeLosaDep,
    GestionarPropuestasDeLosaDep,
)
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.adapters.api.v1.drivers_usados import (
    DriverUsadoRespuesta,
    a_respuesta,
    explicitos_de_receta,
)
from obractrl.adapters.api.v1.elementos_de_estructura import (
    PropuestaDeEstructura,
    ResultadoDeProponer,
)
from obractrl.adapters.api.v1.elementos_de_estructura import (
    _a_propuesta as a_propuesta,
)
from obractrl.adapters.api.v1.elementos_estructurales import (
    ManoDeObraDelCatalogo,
    Marca,
)
from obractrl.adapters.api.v1.receta_acero import DriversDeRecetaPeticion
from obractrl.domain.cuantificacion.drivers_de_elementos import (
    desperdicio_concreto_de_obra,
    receta_de_obra,
)
from obractrl.domain.cuantificacion.matriz_de_losa import (
    CAPA_DE_COMPRESION_CM,
    ElementoDeLosa,
    EntradaMatrizDeLosa,
    ErrorDeMatrizDeLosa,
    LosaDeEntrada,
    calcular_matriz_de_losa,
    definicion_de_losa,
    elemento_de_losa,
)
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["losas"])

ROLES_QUE_PROPONEN = (Rol.CONTROL_OBRA, Rol.COSTOS)
ROLES_QUE_EDITAN = (Rol.CONTROL_OBRA,)
ROLES_QUE_LEEN = (Rol.RESIDENTE, Rol.SUPERVISOR, Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE, Rol.COSTOS)

_NO_HAY_LOSA = {404: {"description": "No hay un elemento de losa con esa clave (LOSA-MACIZA o LOSA-NERVADA)."}}
_PROPONEN = {403: {"description": "Proponen Costos y Control de obra."}, 404: {"description": "No existe ese elemento."}}


# ── Modelos ─────────────────────────────────────────────────────────────────────────────────────────────


class ClaveYNombreDeLosa(BaseModel):
    clave: str
    nombre: str


class ConceptoDeLaFicha(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    estado: Literal["catalogo", "propuesto"]
    provisional: bool


class ConcretoPorUso(BaseModel):
    uso: Literal["entrepiso", "azotea", "cimentacion"]
    clave: str
    descripcion: str


class CimbraDeLaFicha(BaseModel):
    clave: str
    descripcion: str
    por_m2_de_losa: float


class InsumoDeLaParrilla(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    por_m2: float
    total: float | None = None
    fuente: str


class ParrillaDeLaLosa(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    cantidad: float | None = Field(default=None, description="Los m² de losa que cubre (solo en un cálculo).")
    insumos: list[InsumoDeLaParrilla]


class ElementoPermitido(BaseModel):
    clave: str
    tiene_concepto_de_colado: bool


class DestajoCandidato(BaseModel):
    clave: str
    descripcion: str
    unidad: str


class PendienteDeLaLosa(BaseModel):
    clave: str
    texto: str


class DefinicionDeLaLosa(BaseModel):
    clave: str
    nombre: str
    tipo: Literal["maciza", "nervada"]
    se_mide_por: str
    categoria: ClaveYNombreDeLosa
    subcategoria: ClaveYNombreDeLosa
    concepto: ConceptoDeLaFicha
    usos: list[str]
    concreto_por_uso: list[ConcretoPorUso]
    cimbra: CimbraDeLaFicha
    espesor_por_defecto_m: float
    capa_de_compresion_cm: float | None
    parrilla: ParrillaDeLaLosa | None
    elementos_permitidos: list[ElementoPermitido]
    destajos_candidatos: list[DestajoCandidato]
    pagos: list[str]
    pendientes: list[PendienteDeLaLosa]


class PoligonoDeLosaPeticion(BaseModel):
    area_m2: float = Field(ge=0, le=1_000_000, description="Área neta del polígono (ya sin huecos).")
    espesor_m: float | None = Field(default=None, gt=0, le=3, description="Subzona: espesor estructural propio; sin él vale el de la zona.")
    espacio_id: str | None = Field(default=None, max_length=60, description="Una etiqueta del espacio donde cae el polígono (0143): reparte la matriz por espacio.")


class ElementoDeLaMatrizPeticion(BaseModel):
    clave: str = Field(description="Una trabe, contratrabe o nervadura de la biblioteca (T-1-15x25, CT1-15x25, N-1-12x25…).")
    modo: Literal["ml", "pieza"] = "ml"
    cantidad: float = Field(default=1.0, gt=0, le=1_000_000, description="Metros (por ml) o piezas (por pieza).")
    largo_m: float | None = Field(default=None, gt=0, le=30, description="Largo de cada pieza (solo por pieza).")
    pago: Literal["en_la_losa", "propio"] = Field(
        default="en_la_losa",
        description="`en_la_losa`: la losa paga el concreto y la cimbra del elemento (lo que hace el catálogo); `propio`: los paga su concepto de colado por ml (D8).",
    )
    espacio_id: str | None = Field(default=None, max_length=60, description="Una etiqueta del espacio donde está el elemento (0143): reparte la matriz por espacio.")


class CalculoDeLaLosaPeticion(BaseModel):
    espesor_m: float = Field(default=0.12, gt=0, le=3, description="Espesor de la losa de la zona.")
    uso: Literal["entrepiso", "azotea", "cimentacion"] = "entrepiso"
    capa_de_compresion_cm: float = Field(default=CAPA_DE_COMPRESION_CM, gt=0, le=300, description="Solo la losa nervada.")
    losas: list[PoligonoDeLosaPeticion] = Field(default_factory=list, max_length=200)
    elementos: list[ElementoDeLaMatrizPeticion] = Field(default_factory=list, max_length=500)
    desperdicio_concreto_pct: float = Field(default=5.0, ge=0, le=50)
    drivers: DriversDeRecetaPeticion = Field(default_factory=DriversDeRecetaPeticion)
    obra_id: UUID | None = Field(
        default=None,
        description="La obra cuyos drivers (Paramétrico) se leen. Precedencia: lo que manda la petición > el driver de la obra > el valor por defecto. Sin obra, todo vale lo de siempre.",
    )


class LosaCalculada(BaseModel):
    id: str
    area_m2: float
    espesor_m: float
    subzona: bool
    espacio_id: str | None = Field(default=None, description="El espacio donde cae el polígono (0143).")
    concreto_m3: float = Field(description="Geométrico, sin desperdicio: área × espesor (maciza) o área × capa de compresión (nervada).")


class ConcretoDeLaLosa(BaseModel):
    clave: str
    descripcion: str
    geometrico_m3: float
    con_desperdicio_m3: float
    desperdicio_pct: float


class CimbraDeLaLosa(BaseModel):
    clave: str
    descripcion: str
    m2: float


class SeccionDelElementoDeLaZona(BaseModel):
    ancho_cm: float
    peralte_cm: float


class ElementoCalculado(BaseModel):
    id: str | None
    clave: str
    nombre: str
    categoria: str
    modo: Literal["ml", "pieza"]
    cantidad: float
    largo_m: float | None
    longitud_ml: float = Field(description="Los metros lineales que mide el elemento (por pieza: piezas × largo).")
    origen: Literal["manual", "trazo"] = Field(description="`trazo`: la medida sale de una línea del plano (medición derivada).")
    trazo_id: str | None
    longitud_del_trazo_m: float | None = None
    espacio_id: str | None = Field(default=None, description="El espacio donde está el elemento (0143).")
    pago: Literal["en_la_losa", "propio"]
    seccion: SeccionDelElementoDeLaZona
    acero_kg: float
    concreto_m3: float
    cimbra_m2: float
    advertencias: list[str]


class TotalesDeLaMatriz(BaseModel):
    area_m2: float
    longitud_de_elementos_ml: float
    concreto_m3: float = Field(description="Todo el concreto de la zona: el de la losa y el de sus elementos.")
    concreto_de_la_losa_m3: float
    concreto_de_los_elementos_m3: float
    concreto_pagado_por_la_losa_m3: float
    concreto_pagado_por_elementos_m3: float
    cimbra_m2: float
    cimbra_pagada_por_la_losa_m2: float
    cimbra_pagada_por_elementos_m2: float
    acero_de_elementos_kg: float
    solape_con_la_losa_m3: float = Field(description="Concreto del espesor de la losa que la trabe y la losa cuentan las dos; se informa, no se descuenta (L2).")


class InsumoDeLaMatriz(BaseModel):
    parte: Literal["acero", "concreto", "cimbra"]
    clave: str
    descripcion: str
    unidad: str
    cantidad: float
    origen: str = Field(description="`zona` (la losa), `elemento`, `catalogo` (un dato del auxiliar del catálogo) o `zona+elemento`.")
    paga: Literal["losa", "elemento"] = Field(description="Quién paga este insumo: la losa por m² o el concepto del elemento.")


class PropuestaDelConceptoDeLosa(BaseModel):
    id: UUID
    estado: Literal["pendiente", "autorizada", "rechazada"]
    version: int | None
    elemento_clave: str


class ConceptoDeLaMatriz(BaseModel):
    parte: Literal["losa", "acero", "colado"]
    elemento_clave: str
    ref: str | None = Field(description="El elemento de la zona del que sale la fila (`null` en la fila de la losa).")
    concepto: ConceptoDeLaFicha
    toma: list[str]
    cantidad: float = Field(description="La cantidad medida, en la unidad del concepto.")
    unidad: str
    nota: str
    propuesta: PropuestaDelConceptoDeLosa | None = Field(
        default=None, description="Si el concepto es provisional: su propuesta vigente (pendiente o autorizada); `null` si nadie la ha propuesto."
    )


class ResolucionDelConcepto(BaseModel):
    estado: Literal["cuenta", "sin_espacio", "propuesto", "sin_concepto", "falta_partida", "sin_cantidad"] = Field(
        description="`cuenta`: concepto del catálogo con partida en el árbol en ese espacio (o una general): su cantidad se escribe ahí. Lo demás avisa y no escribe."
    )
    cuenta: bool
    aviso: str | None
    concepto_id: UUID | None
    partida_id: UUID | None = Field(description="La partida del árbol donde se mide (solo si cuenta).")
    partida_nombre: str | None


class ConceptoPorEspacio(ConceptoDeLaMatriz):
    resolucion: ResolucionDelConcepto | None = Field(
        default=None, description="En qué partida del árbol se mide (solo la matriz de una zona; el cálculo suelto no consulta el árbol)."
    )


class GrupoPorEspacio(BaseModel):
    espacio_id: str | None = Field(description="El espacio; `null` = lo que no está asignado a ninguno.")
    espacio_nombre: str | None = None
    area_m2: float
    longitud_de_elementos_ml: float
    concreto_m3: float
    cimbra_m2: float
    acero_de_elementos_kg: float
    conceptos: list[ConceptoPorEspacio]


class ManoDeObraDeLaLosa(BaseModel):
    estado: Literal["sin_mano_de_obra"]
    nota: str
    destajos_candidatos: list[DestajoCandidato]


class ZonaDeLaMatriz(BaseModel):
    id: UUID
    plano_id: UUID
    nombre: str
    nivel: str | None
    altura_libre_m: float
    cota_piso_m: float


class FilaDeConciliacionDeLaLosa(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    catalogo: float | None
    elemento: float | None
    diferencia: float | None
    diferencia_pct: float | None
    marca: Marca


class ConceptoConciliadoDeLaLosa(BaseModel):
    clave: str
    descripcion: str
    unidad: str


class ConciliacionDeLaLosa(BaseModel):
    concepto: ConceptoConciliadoDeLaLosa
    nota: str
    filas: list[FilaDeConciliacionDeLaLosa]
    mano_de_obra: list[ManoDeObraDelCatalogo]
    resumen: dict[str, int]
    coincide: bool


class MatrizDeLosa(BaseModel):
    clave: str
    nombre: str
    tipo: Literal["maciza", "nervada"]
    uso: Literal["entrepiso", "azotea", "cimentacion"]
    espesor_m: float
    capa_de_compresion_cm: float | None
    area_m2: float
    losas: list[LosaCalculada]
    concreto: ConcretoDeLaLosa
    cimbra: CimbraDeLaLosa
    parrilla: ParrillaDeLaLosa | None
    elementos: list[ElementoCalculado]
    totales: TotalesDeLaMatriz
    insumos: list[InsumoDeLaMatriz]
    conceptos: list[ConceptoDeLaMatriz]
    por_espacio: list[GrupoPorEspacio] = Field(
        default_factory=list,
        description="La misma matriz repartida por espacio (0143): cada polígono y cada elemento cae en un solo grupo, así que la suma de los grupos es el total de la zona (sin doble conteo). Cada concepto dice en qué partida se mide.",
    )
    mano_de_obra: ManoDeObraDeLaLosa
    advertencias: list[str]
    pendientes: list[PendienteDeLaLosa]
    drivers_usados: list[DriverUsadoRespuesta] = Field(
        default_factory=list, description="Los drivers que leyó el cálculo y de dónde salió cada valor."
    )
    zona: ZonaDeLaMatriz | None = Field(default=None, description="La zona de la que sale la matriz (solo la de una zona del plano).")
    escala_definida: bool | None = Field(default=None, description="Sin escala calibrada se toma 1 unidad de plano = 1 m (solo la de una zona).")
    conciliacion: ConciliacionDeLaLosa | None = Field(
        default=None, description="El total de la zona contra un concepto del catálogo vigente, si se pidió `concepto_clave` (solo la de una zona)."
    )


class ElementoDeLaZonaPeticion(BaseModel):
    elemento_clave: str = Field(description="Una trabe, contratrabe o nervadura de la biblioteca.")
    modo: Literal["ml", "pieza"] = "ml"
    cantidad: float | None = Field(
        default=None, gt=0, le=1_000_000, description="Metros (por ml) o piezas (por pieza). Sin ella debe venir `trazo_id`: la medida sale de la línea."
    )
    largo_m: float | None = Field(default=None, gt=0, le=30, description="Largo de cada pieza (solo por pieza sin línea).")
    pago: Literal["en_la_losa", "propio"] = "en_la_losa"
    trazo_id: UUID | None = Field(
        default=None,
        description="Una línea del plano de la zona: su longitud (con la escala del plano) es la medida del elemento, derivada al calcular (por pieza, el largo de la pieza).",
    )
    espacio_id: UUID | None = Field(
        default=None, description="El espacio donde está el elemento (0143); `null` = sin espacio. Con espacio, su concepto se mide en la partida de ese espacio."
    )


class ElementoDeLaZona(BaseModel):
    id: UUID
    elemento_clave: str
    modo: Literal["ml", "pieza"]
    cantidad: float
    largo_m: float | None
    pago: Literal["en_la_losa", "propio"]
    trazo_id: UUID | None
    origen: Literal["manual", "trazo"]
    longitud_del_trazo_m: float | None
    espacio_id: UUID | None = None


# ── Biblioteca: la ficha, el cálculo suelto y las propuestas de la losa ─────────────────────────────────


@router.get(
    "/biblioteca-de-elementos/losa/{clave}",
    response_model=DefinicionDeLaLosa,
    summary="La ficha de la losa maciza o nervada (qué calcula, lo que toma del catálogo, su concepto nuevo propuesto y los pendientes)",
    responses=_NO_HAY_LOSA,
)
async def definicion_de_la_losa(clave: str) -> dict[str, Any]:
    d = definicion_de_losa(clave)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No hay un elemento de losa «{clave}» en la biblioteca.")
    return d


@router.post(
    "/biblioteca-de-elementos/losa/{clave}/calcular",
    response_model=MatrizDeLosa,
    summary="Calcula la matriz de una losa con las áreas y los elementos que se mandan (solo cálculo; no guarda nada)",
    responses={**_NO_HAY_LOSA, 422: {"description": "Un dato no vale."}},
)
async def calcular_la_losa(clave: str, peticion: CalculoDeLaLosaPeticion, drivers_de_obra: DriversDeObraDep) -> dict[str, Any]:
    tipo = elemento_de_losa(clave)
    if tipo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No hay un elemento de losa «{clave}» en la biblioteca.")
    vigentes = await drivers_de_obra.valores(peticion.obra_id)
    drivers, usados = receta_de_obra(vigentes, explicitos_de_receta(peticion.drivers))
    explicito = peticion.desperdicio_concreto_pct if "desperdicio_concreto_pct" in peticion.model_fields_set else None
    desperdicio_pct, u_concreto = desperdicio_concreto_de_obra(vigentes, explicito_pct=explicito)
    usados.append(u_concreto)
    try:
        r = calcular_matriz_de_losa(
            EntradaMatrizDeLosa(
                tipo=tipo, uso=peticion.uso, espesor_m=peticion.espesor_m, capa_de_compresion_cm=peticion.capa_de_compresion_cm,
                losas=[LosaDeEntrada(area_m2=lo.area_m2, espesor_m=lo.espesor_m, espacio_id=lo.espacio_id) for lo in peticion.losas],
                elementos=[
                    ElementoDeLosa(clave=e.clave, modo=e.modo, cantidad=e.cantidad, largo_m=e.largo_m, pago=e.pago, espacio_id=e.espacio_id)
                    for e in peticion.elementos
                ],
                desperdicio_concreto_pct=desperdicio_pct, drivers=drivers,
            )
        )
    except ErrorDeMatrizDeLosa as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    return {**r, "drivers_usados": a_respuesta(usados)}


@router.get(
    "/biblioteca-de-elementos/losa/{clave}/propuestas",
    response_model=list[PropuestaDeEstructura],
    summary="Las propuestas de concepto nuevo de la losa: pendientes, autorizadas y rechazadas",
    responses=_NO_HAY_LOSA,
)
async def propuestas_de_la_losa(clave: str, caso_uso: GestionarPropuestasDeLosaDep) -> list[PropuestaDeEstructura]:
    return [a_propuesta(f) for f in await caso_uso.listar(clave)]


@router.post(
    "/biblioteca-de-elementos/losa/{clave}/propuestas/concepto",
    response_model=ResultadoDeProponer,
    status_code=status.HTTP_201_CREATED,
    summary="Proponer el concepto nuevo de la losa por m² (clave provisional, sin precio ni destajo; lo autoriza Control de obra)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_PROPONEN))],
    responses=_PROPONEN,
)
async def proponer_concepto_de_la_losa(clave: str, ctx: ContextoActual, caso_uso: GestionarPropuestasDeLosaDep) -> ResultadoDeProponer:
    return ResultadoDeProponer(**await caso_uso.proponer_concepto_de_losa(clave, usuario_id=ctx.usuario_id, rol=ctx.rol))


@router.post(
    "/biblioteca-de-elementos/estructura/{clave}/propuestas/colado-por-ml",
    response_model=ResultadoDeProponer,
    status_code=status.HTTP_201_CREATED,
    summary="Proponer el concepto de colado y cimbra por ml de una trabe, contratrabe o nervadura, con su destajo por ml sin importe (D8)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_PROPONEN))],
    responses=_PROPONEN,
)
async def proponer_colado_por_ml(clave: str, ctx: ContextoActual, caso_uso: GestionarPropuestasDeLosaDep) -> ResultadoDeProponer:
    return ResultadoDeProponer(**await caso_uso.proponer_colado_por_ml(clave, usuario_id=ctx.usuario_id, rol=ctx.rol))


# ── Zona: elementos y matriz ────────────────────────────────────────────────────────────────────────────


@router.get(
    "/zonas-de-losa/{zona_id}/elementos",
    response_model=list[ElementoDeLaZona],
    summary="Los elementos (trabes, contratrabes, nervaduras) de una zona de losa, con la medida que cuentan",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_LEEN))],
)
async def elementos_de_la_zona(zona_id: UUID, caso_uso: GestionarMatrizDeLosaDep) -> list[dict[str, Any]]:
    return await caso_uso.elementos(zona_id)


@router.post(
    "/zonas-de-losa/{zona_id}/elementos",
    response_model=ElementoDeLaZona,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar un elemento a la zona (solo Control de obra)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
    responses={422: {"description": "El elemento, la medida o la línea no valen."}},
)
async def agregar_elemento(
    zona_id: UUID, peticion: ElementoDeLaZonaPeticion, ctx: ContextoActual, caso_uso: GestionarMatrizDeLosaDep
) -> dict[str, Any]:
    return await caso_uso.agregar_elemento(zona_id, autor_id=ctx.usuario_id, **peticion.model_dump())


@router.put(
    "/elementos-de-losa/{elemento_id}",
    response_model=ElementoDeLaZona,
    summary="Cambiar un elemento de la zona (solo Control de obra); sin `espacio_id` conserva su espacio",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
    responses={422: {"description": "El elemento, la medida o la línea no valen."}},
)
async def cambiar_elemento(elemento_id: UUID, peticion: ElementoDeLaZonaPeticion, caso_uso: GestionarMatrizDeLosaDep) -> dict[str, Any]:
    datos = peticion.model_dump()
    if "espacio_id" not in peticion.model_fields_set:
        del datos["espacio_id"]  # sin `espacio_id` el elemento conserva su espacio; con `null` queda sin espacio
    return await caso_uso.cambiar_elemento(elemento_id, **datos)


@router.delete(
    "/elementos-de-losa/{elemento_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Quitar un elemento de la zona (solo Control de obra)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
)
async def quitar_elemento(elemento_id: UUID, caso_uso: GestionarMatrizDeLosaDep) -> None:
    await caso_uso.quitar_elemento(elemento_id)


@router.get(
    "/zonas-de-losa/{zona_id}/matriz",
    response_model=MatrizDeLosa,
    summary="La matriz de conceptos de una zona de losa: concreto, cimbra, acero, elementos y los conceptos que paga cada parte",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_LEEN))],
    responses={422: {"description": "Un dato de la zona no vale, o el concepto no está en el catálogo."}},
)
async def matriz_de_la_zona(
    zona_id: UUID,
    caso_uso: GestionarMatrizDeLosaDep,
    concepto_clave: str | None = Query(
        default=None, max_length=40, description="Una clave del catálogo vigente (p. ej. EST-21011) contra la que se concilia el total de la zona."
    ),
) -> dict[str, Any]:
    r = await caso_uso.matriz(zona_id, concepto_clave=concepto_clave)
    return {**r, "drivers_usados": a_respuesta(r["drivers_usados"])}


@router.post(
    "/zonas-de-losa/{zona_id}/matriz/proponer-conceptos",
    response_model=ResultadoDeProponer,
    status_code=status.HTTP_201_CREATED,
    summary="Proponer los conceptos nuevos que la matriz de la zona necesita (el de la losa y el de colado por ml de los elementos con pago propio)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_PROPONEN))],
    responses=_PROPONEN,
)
async def proponer_conceptos_de_la_zona(zona_id: UUID, ctx: ContextoActual, caso_uso: GestionarMatrizDeLosaDep) -> ResultadoDeProponer:
    return ResultadoDeProponer(**await caso_uso.proponer_conceptos(zona_id, usuario_id=ctx.usuario_id, rol=ctx.rol))
