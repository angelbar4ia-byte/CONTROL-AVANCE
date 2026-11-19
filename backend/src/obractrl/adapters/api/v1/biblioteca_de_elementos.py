"""Endpoints de la biblioteca de elementos y del cálculo de los muros de piedra: contención (MCT-01010) y cimentación (CIM-01010).

El cálculo vive en el dominio (`muro_contencion`); aquí solo se valida la entrada y se devuelve el resultado.
No guarda nada: es el cálculo por metro lineal de trazo con los parámetros que se mandan. Controladores delgados.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, ValidationError

from obractrl.domain.cuantificacion.biblioteca_de_elementos import (
    BIBLIOTECA,
    elemento_de_la_biblioteca,
)
from obractrl.domain.cuantificacion.muro_cimentacion import (
    CLAVE_ELEMENTO as CLAVE_CIMENTACION,
)
from obractrl.domain.cuantificacion.muro_cimentacion import (
    EntradaMuroDeCimentacion,
    calcular_muro_de_cimentacion,
)
from obractrl.domain.cuantificacion.muro_contencion import (
    CLAVE_CONCEPTO,
    CLAVE_ELEMENTO,
    DESCRIPCION_CONCEPTO,
    EntradaMuroDeContencion,
    calcular_muro_de_contencion,
)
from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion
from obractrl.domain.cuantificacion.trazo_de_muro import calcular_trazo

router = APIRouter(tags=["biblioteca de elementos"])


class ConceptoDelElemento(BaseModel):
    clave: str
    descripcion: str
    unidad: str


class ElementoDeBiblioteca(BaseModel):
    clave: str
    nombre: str
    tipo: str
    se_mide_por: str
    concepto: ConceptoDelElemento


class SubcategoriaDeBiblioteca(BaseModel):
    clave: str
    nombre: str
    prefijo: str
    elementos: list[ElementoDeBiblioteca]


class CategoriaDeBiblioteca(BaseModel):
    clave: str
    nombre: str
    prefijo: str
    subcategorias: list[SubcategoriaDeBiblioteca]


class PendienteDelElemento(BaseModel):
    clave: str
    texto: str


class FilaDelCuadro1(BaseModel):
    H: float
    B: float
    B1: float
    Vm: float
    piedra: float
    cemento_kg: float
    arena_m3: float
    agua_l: float


class DentellonDelCuadro(BaseModel):
    b2: float
    b1: float
    h: float
    volumen_m3: float


class ClaveYNombre(BaseModel):
    clave: str
    nombre: str


class DefinicionDelElemento(BaseModel):
    clave: str
    nombre: str
    tipo: str
    se_mide_por: str
    concepto: ConceptoDelElemento
    categoria: ClaveYNombre
    subcategoria: ClaveYNombre
    parametros_por_defecto: dict[str, Any]
    cuadro_1: list[FilaDelCuadro1]
    fuente: str
    dentellon: DentellonDelCuadro
    pendientes: list[PendienteDelElemento]


class CalculoDelMuroPeticion(BaseModel):
    alto_m: float = Field(gt=0, le=20, description="Altura del muro en METROS.")
    corona_m: float | None = Field(
        default=None, gt=0, le=10, description="Corona a mano; vacío usa el Cuadro 1."
    )
    base_m: float | None = Field(
        default=None, gt=0, le=10, description="Base a mano; vacío usa el Cuadro 1."
    )
    dentellon: bool = Field(
        default=True, description="Opcional; solo aplica desde 2.00 m de altura."
    )
    lluvia: Literal["baja", "alta"] = "baja"
    tubo: Literal["pvc", "concreto"] = "pvc"
    filtro_cm: float | None = Field(
        default=None,
        gt=0,
        le=200,
        description="Espesor del filtro de grava; el manual no lo da.",
    )
    relleno: Literal["vertical", "inclinada"] = "vertical"
    tramo_m: float = Field(
        default=6.0, gt=0, le=50, description="Largo del tramo que dibujan las vistas."
    )


class FilaDeCuadro1Usada(BaseModel):
    H: float
    B: float
    B1: float


class SeccionDelMuro(BaseModel):
    alto_m: float
    corona_m: float
    base_m: float
    espesor_medio_m: float
    manual: bool
    fila_cuadro_1: FilaDeCuadro1Usada
    fuera_de_tabla: bool


class VolumenDelMuro(BaseModel):
    muro_m3_ml: float
    dentellon_m3_ml: float
    excavacion_dentellon_m3_ml: float
    total_m3_ml: float
    piedra_a_comprar_m3_ml: float
    abundamiento: float
    cemento_kg_ml: float
    arena_m3_ml: float
    agua_l_ml: float


class DentellonDelMuro(BaseModel):
    aplica: bool
    opcion: bool
    b2_m: float
    b1_m: float
    h_m: float


class TuboDelDren(BaseModel):
    clave: str
    descripcion: str
    material: str
    largo_pieza_m: float
    ml_por_ml_de_trazo: float
    lloraderos_por_pieza: float
    piezas_por_lloradero: float
    piezas_por_ml_de_trazo: float
    provisional: bool


class FiltroDelDren(BaseModel):
    espesor_cm: float | None
    relleno: str
    longitud_cara_m: float
    volumen_m3_ml: float | None
    por_definir: bool


class CarpetaDelDren(BaseModel):
    espesor_m: float
    volumen_m3_ml: float


class DrenDelMuro(BaseModel):
    aplica: bool
    hileras: int
    alturas_m: list[float]
    separacion_m: float
    lluvia: str
    lloraderos_por_ml: float
    tubo: TuboDelDren
    filtro: FiltroDelDren
    carpeta: CarpetaDelDren


class InsumoDelDren(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    provisional: bool = Field(description="Sin precio en el catálogo: Costos lo asigna.")
    cantidad: float = Field(
        description="Cantidad por m³ de muro, para sumar al APU del concepto."
    )
    detalle: str


class HileraDeLloraderos(BaseModel):
    altura_m: float
    x_m: list[float]


class VistasDelMuro(BaseModel):
    tramo_m: float
    hileras: list[HileraDeLloraderos]


class CalculoDelMuro(BaseModel):
    """El resultado completo por metro lineal de trazo."""

    clave: str
    unidad: str
    concepto: ConceptoDelElemento
    seccion: SeccionDelMuro
    volumen: VolumenDelMuro
    dentellon: DentellonDelMuro
    dren: DrenDelMuro
    insumos_por_m3: list[InsumoDelDren]
    vistas: VistasDelMuro
    advertencias: list[str]


class CalculoDelCimientoPeticion(BaseModel):
    alto_m: float = Field(
        gt=0, le=20, description="Altura del muro de cimentación en METROS."
    )
    caras: Literal[1, 2] = Field(
        default=1,
        description="Caras inclinadas: 1 (lindero, la otra es vertical) o 2 (simétrico).",
    )
    dentellon: bool = Field(
        default=False, description="Opcional; solo aplica desde 2.00 m de altura."
    )
    corona_m: float | None = Field(
        default=None, gt=0, le=10, description="Corona a mano; vacío usa 40 cm."
    )
    base_m: float | None = Field(
        default=None,
        gt=0,
        le=10,
        description="Base a mano; vacío usa el escarpio 1.5 : 1.",
    )


class SeccionDelCimiento(BaseModel):
    alto_m: float
    corona_m: float
    base_m: float
    espesor_medio_m: float
    caras: int
    manual: bool


class EscarpioDelCimiento(BaseModel):
    minimo: float
    angulo_minimo_grados: float
    real: float | None
    angulo_real_grados: float | None
    cumple: bool
    fuente: str


class FilaDelContraste(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    catalogo: float | None
    elemento: float | None
    diferencia: float | None
    diferencia_pct: float | None
    marca: str


class ManoDeObraDelContraste(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    cantidad: float
    costo: float | None


class VersionPropuestaDelConcepto(BaseModel):
    version: int
    cambio: str
    estado: str


class ContrasteConElConcepto(BaseModel):
    """El elemento contra el concepto del catálogo por m³ de mampostería (la mano de obra no se compara)."""

    concepto: str
    version_vigente: int
    filas: list[FilaDelContraste]
    mano_de_obra: list[ManoDeObraDelContraste]
    resumen: dict[str, int]
    version_propuesta: VersionPropuestaDelConcepto


class NoIncluidoDelCimiento(BaseModel):
    clave: str
    texto: str


class CalculoDelCimiento(BaseModel):
    """El resultado completo del muro de cimentación por metro lineal de trazo."""

    clave: str
    unidad: str
    concepto: ConceptoDelElemento
    seccion: SeccionDelCimiento
    escarpio: EscarpioDelCimiento
    volumen: VolumenDelMuro
    dentellon: DentellonDelMuro
    contraste: ContrasteConElConcepto
    no_incluye: list[NoIncluidoDelCimiento] = Field(
        description="Dalas, castillos empotrados y cimientos perpendiculares de la sección 8.4: se miden aparte, no están en este muro (D12)."
    )
    advertencias: list[str]


class TrazoDelMuroPeticion(BaseModel):
    """El trazo con pendiente de un muro de piedra. `parametros` son los del muro (sin la altura): los de
    `CalculoDelMuroPeticion` para MCT-01010 o los de `CalculoDelCimientoPeticion` para CIM-01010."""

    longitud_m: float = Field(
        gt=0, le=500, description="Largo del trazo en planta, en metros."
    )
    altura_inicial_m: float = Field(
        gt=0, le=20, description="Altura en el primer punto del trazo, en metros."
    )
    pendiente_pct: float = Field(
        default=0.0,
        ge=-100,
        le=100,
        description="Pendiente del terreno en %: positiva, el muro crece hacia el final; negativa, decrece. La corona va a nivel.",
    )
    parametros: dict[str, Any] = Field(default_factory=dict)


class PuntoDelPerfil(BaseModel):
    s_m: float
    altura_m: float


class VolumenDelTrazo(BaseModel):
    muro_m3: float
    dentellon_m3: float
    total_m3: float


class InsumoDelTrazo(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    provisional: bool
    cantidad_total: float
    cantidad_por_m3: float


class CalculoDelTrazo(BaseModel):
    clave: str
    concepto: ConceptoDelElemento
    longitud_m: float
    longitud_real_m: float
    altura_inicial_m: float
    pendiente_pct: float
    altura_final_m: float
    altura_minima_m: float
    altura_maxima_m: float
    rebanadas: int
    volumen: VolumenDelTrazo
    insumos: list[InsumoDelTrazo]
    perfil: list[PuntoDelPerfil]
    advertencias: list[str]


@router.get(
    "/biblioteca-de-elementos",
    response_model=list[CategoriaDeBiblioteca],
    summary="La biblioteca de elementos por categoría y subcategoría",
)
async def biblioteca_de_elementos() -> list[dict[str, Any]]:
    return [
        {
            **c,
            "subcategorias": [
                {**s, "elementos": list(s["elementos"])} for s in c["subcategorias"]
            ],
        }
        for c in BIBLIOTECA
    ]


@router.get(
    "/biblioteca-de-elementos/{clave}",
    response_model=DefinicionDelElemento,
    summary="La definición de un elemento de la biblioteca (Cuadro 1, pendientes y fuente)",
)
async def definicion_del_elemento(clave: str) -> dict[str, Any]:
    elemento = elemento_de_la_biblioteca(clave)
    if elemento is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"No hay un elemento {clave} en la biblioteca."
        )
    return elemento


@router.post(
    f"/biblioteca-de-elementos/{CLAVE_CIMENTACION}/calcular",
    response_model=CalculoDelCimiento,
    summary="Calcula el muro de cimentación de piedra por metro lineal de trazo",
)
async def calcular_cimiento(peticion: CalculoDelCimientoPeticion) -> dict[str, Any]:
    try:
        return calcular_muro_de_cimentacion(
            EntradaMuroDeCimentacion(**peticion.model_dump())
        )
    except ErrorDeCuantificacion as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e


@router.post(
    "/biblioteca-de-elementos/{clave}/calcular-trazo",
    response_model=CalculoDelTrazo,
    summary="Calcula un muro de piedra sobre un trazo con pendiente (altura inicial, corona a nivel)",
)
async def calcular_el_trazo(clave: str, peticion: TrazoDelMuroPeticion) -> dict[str, Any]:
    try:
        if clave == CLAVE_ELEMENTO:
            params = {k: v for k, v in peticion.parametros.items() if k != "alto_m"}
            # Valida los parámetros con el mismo modelo del cálculo por metro.
            ok = CalculoDelMuroPeticion(
                alto_m=peticion.altura_inicial_m, **params
            ).model_dump()
            ok.pop("alto_m")
            ok.pop("tramo_m")

            def por_metro(alto: float) -> dict[str, Any]:
                return calcular_muro_de_contencion(
                    EntradaMuroDeContencion(alto_m=alto, **ok)
                )

        elif clave == CLAVE_CIMENTACION:
            params = {k: v for k, v in peticion.parametros.items() if k != "alto_m"}
            ok = CalculoDelCimientoPeticion(
                alto_m=peticion.altura_inicial_m, **params
            ).model_dump()
            ok.pop("alto_m")

            def por_metro(alto: float) -> dict[str, Any]:
                return calcular_muro_de_cimentacion(
                    EntradaMuroDeCimentacion(alto_m=alto, **ok)
                )

        else:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"No hay un elemento {clave} con trazo en la biblioteca.",
            )
        r = calcular_trazo(
            por_metro,
            longitud_m=peticion.longitud_m,
            altura_inicial_m=peticion.altura_inicial_m,
            pendiente_pct=peticion.pendiente_pct,
        )
    except ErrorDeCuantificacion as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    except ValidationError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    return {
        **r,
        "clave": clave,
        "concepto": {
            "clave": CLAVE_CONCEPTO,
            "descripcion": DESCRIPCION_CONCEPTO,
            "unidad": "m3",
        },
    }


@router.post(
    "/biblioteca-de-elementos/{clave}/calcular",
    response_model=CalculoDelMuro,
    summary="Calcula el muro de contención de piedra por metro lineal de trazo",
)
async def calcular_elemento(
    clave: str, peticion: CalculoDelMuroPeticion
) -> dict[str, Any]:
    if clave != CLAVE_ELEMENTO:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"No hay un elemento {clave} con cálculo en la biblioteca.",
        )
    try:
        return calcular_muro_de_contencion(
            EntradaMuroDeContencion(**peticion.model_dump())
        )
    except ErrorDeCuantificacion as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
