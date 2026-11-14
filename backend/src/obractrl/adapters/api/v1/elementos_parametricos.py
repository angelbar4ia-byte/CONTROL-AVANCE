"""Endpoints de los elementos paramétricos (D-602, D-604; migración 0104).

Una pieza con medidas, armado y estribos —castillo, trabe o cadena, zapata, losa— de la que salen concreto, acero,
estribos, alambre y cimbra. Son del catálogo de la organización; los define Control de obra y Costos. Cada lectura
trae la **receta de una muestra** calculada por el servidor. Controladores delgados.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import GestionarElementosParametricosDep
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.adapters.api.v1.cuantificacion import ROLES_QUE_TRAZAN
from obractrl.application.casos_uso.elementos_parametricos import (
    ComandoCrearElementoParametrico,
)
from obractrl.domain.cuantificacion.clasificacion_de_elementos import CATEGORIAS
from obractrl.domain.cuantificacion.elementos_parametricos import (
    PARAMETROS_POR_TIPO,
    UNIDAD_DE_CALCULO,
)
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["elementos parametricos"])

ROLES_QUE_DEFINEN = (Rol.CONTROL_OBRA, Rol.COSTOS)
"""El elemento es del catálogo de la organización y alimenta recetas: lo definen Control de obra y Costos (D-602)."""

TipoDeElementoParametrico = Literal["castillo", "lineal", "zapata", "losa"]


class RecetaRespuesta(BaseModel):
    unidad: str = Field(description="La unidad de cálculo de la muestra: pza, ml o m².")
    concreto: float = Field(description="m³ por muestra.")
    acero_kg: float
    estribos_kg: float
    n_estribos: float
    long_estribo_m: float
    n_amarres: float
    alambre_kg: float
    varas: float = Field(description="Varas comerciales de 12 m por muestra.")
    cimbra_m2: dict[str, float] = Field(description="m² de cimbra por número de lados.")


class MaterialesDelElemento(BaseModel):
    """Con qué insumo de la base de datos se paga cada parte de la receta del elemento (claves de insumo)."""

    concreto: str | None = Field(default=None, max_length=30, description="Insumo del concreto (Mezclas · Concretos o Prefabricados · Concretos).")
    alambre: str | None = Field(default=None, max_length=30, description="Insumo del alambre de amarre (Aceros).")
    varilla: str | None = Field(default=None, max_length=30, description="Insumo de la varilla longitudinal (Acero De Refuerzo).")
    anillo: str | None = Field(default=None, max_length=30, description="Insumo del anillo o estribo (Aceros).")
    armex: str | None = Field(default=None, max_length=30, description="Insumo del armex (Aceros).")
    cimbra: dict[str, float] | None = Field(
        default=None, description="Consumos de cimbra por unidad de cálculo del elemento: {clave del insumo: consumo} (Cimbra, clavos, alambre)."
    )


def _materiales(m: MaterialesDelElemento | None) -> dict[str, Any] | None:
    return None if m is None else m.model_dump(exclude_none=True)


class ElementoParametricoRespuesta(BaseModel):
    id: UUID
    clave: str
    nombre: str
    tipo: TipoDeElementoParametrico
    categoria: str = Field(description="Categoría de la biblioteca (castillos, cadenas, trabes…).")
    subcategoria: str = Field(description="Subcategoría: el uso del elemento (cerramiento, desplante…). Forma parte de su identidad.")
    parametros: dict[str, float]
    materiales: MaterialesDelElemento = Field(
        default_factory=MaterialesDelElemento, description="Los insumos que el elemento eligió; entran a la firma anti-duplicados."
    )
    receta: RecetaRespuesta
    version: int = Field(default=1, description="Sube al cambiar la receta con obras asignadas que lo usan (D-639).")


class ElementoParametricoPeticion(BaseModel):
    clave: str = Field(min_length=1, max_length=20)
    nombre: str = Field(min_length=1, max_length=80)
    tipo: TipoDeElementoParametrico
    parametros: dict[str, float] = Field(default_factory=dict, description="Los que falten toman el valor por defecto del tipo.")
    categoria: str | None = Field(
        default=None, max_length=40, description="Sin categoría ni subcategoría, el tipo toma las de defecto (castillos/muro, cadenas/cerramiento…)."
    )
    subcategoria: str | None = Field(default=None, max_length=40, description="Sola, toma la primera de su categoría.")
    materiales: MaterialesDelElemento | None = Field(
        default=None, description="Insumos que elige el elemento; deben existir y ser de las familias de su tipo."
    )


class ElementoParametricoCambio(BaseModel):
    clave: str | None = Field(default=None, min_length=1, max_length=20)
    nombre: str | None = Field(default=None, min_length=1, max_length=80)
    parametros: dict[str, float] | None = Field(default=None, description="Solo los que cambian.")
    categoria: str | None = Field(default=None, max_length=40, description="Reclasifica el elemento; sin la subcategoría pasa a la primera de la nueva categoría.")
    subcategoria: str | None = Field(default=None, max_length=40, description="Cambia el uso dentro de la categoría actual (o de la nueva, si se manda).")
    materiales: MaterialesDelElemento | None = Field(
        default=None, description="Reemplaza los materiales del elemento (un objeto vacío los quita); sin él se conservan."
    )


class ElementoParametricoCreado(BaseModel):
    id: UUID


class SubcategoriaDeClasificacion(BaseModel):
    clave: str
    nombre: str
    prefijo: str
    posiciones: list[str] | None = Field(
        description="Dónde del muro se coloca un elemento de esta subcategoría (desplante, cerramiento, remate); `null` si no se coloca por posición."
    )
    en_muro: bool = Field(description="Si el elemento se coloca en un muro (las trabes y las zapatas no).")


class CategoriaDeClasificacion(BaseModel):
    clave: str
    nombre: str
    tipo: TipoDeElementoParametrico = Field(description="Con qué tipo de elemento se calcula.")
    prefijo: str
    construida: bool
    subcategorias: list[SubcategoriaDeClasificacion]


class TipoDeElementoRespuesta(BaseModel):
    tipo: TipoDeElementoParametrico
    unidad: str
    parametros_por_defecto: dict[str, float]


def _respuesta(fila: dict[str, Any]) -> ElementoParametricoRespuesta:
    r = fila["receta"]
    return ElementoParametricoRespuesta(
        id=fila["id"],
        clave=fila["clave"],
        nombre=fila["nombre"],
        tipo=fila["tipo"],
        categoria=fila["categoria"],
        subcategoria=fila["subcategoria"],
        parametros={k: float(v) for k, v in fila["parametros"].items()},
        materiales=MaterialesDelElemento(**dict(fila.get("materiales") or {})),
        version=int(fila.get("version") or 1),
        receta=RecetaRespuesta(**{**r, "cimbra_m2": {str(k): float(v) for k, v in r["cimbra_m2"].items()}}),
    )


@router.get(
    "/elementos-parametricos/tipos",
    response_model=list[TipoDeElementoRespuesta],
    summary="Los tipos de elemento paramétrico y sus parámetros por defecto",
)
async def tipos_de_elemento() -> list[TipoDeElementoRespuesta]:
    return [
        TipoDeElementoRespuesta(
            tipo=t,  # type: ignore[arg-type]
            unidad=UNIDAD_DE_CALCULO[t],
            parametros_por_defecto={k: float(v) for k, v in PARAMETROS_POR_TIPO[t].items()},
        )
        for t in PARAMETROS_POR_TIPO
    ]


@router.get(
    "/elementos-parametricos/clasificacion",
    response_model=list[CategoriaDeClasificacion],
    summary="Las categorías y subcategorías de la biblioteca de elementos paramétricos, con el límite de posición de cada una",
)
async def clasificacion_de_elementos() -> list[CategoriaDeClasificacion]:
    return [
        CategoriaDeClasificacion(
            clave=c["clave"],
            nombre=c["nombre"],
            tipo=c["tipo"],
            prefijo=c["prefijo"],
            construida=c["construida"],
            subcategorias=[
                SubcategoriaDeClasificacion(
                    clave=s["clave"],
                    nombre=s["nombre"],
                    prefijo=s["prefijo"],
                    posiciones=list(s["posiciones"]) if s["posiciones"] else None,
                    en_muro=s["en_muro"],
                )
                for s in c["subcategorias"]
            ],
        )
        for c in CATEGORIAS
    ]


@router.get(
    "/elementos-parametricos",
    response_model=list[ElementoParametricoRespuesta],
    summary="Los elementos paramétricos de la organización, con la receta de una muestra",
)
async def listar_elementos_parametricos(caso_uso: GestionarElementosParametricosDep) -> list[ElementoParametricoRespuesta]:
    return [_respuesta(f) for f in await caso_uso.listar()]


@router.post(
    "/elementos-parametricos",
    response_model=ElementoParametricoCreado,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un elemento paramétrico",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_DEFINEN))],
    responses={
        403: {"description": "Lo definen Control de obra y Costos."},
        409: {"description": "Ya existe un elemento idéntico (misma categoría, subcategoría, medidas y armado): se usa el existente."},
        422: {"description": "Clave repetida, categoría o subcategoría que no existe, un parámetro que no vale o un material que no existe o es de otra familia."},
    },
)
async def crear_elemento_parametrico(
    peticion: ElementoParametricoPeticion, ctx: ContextoActual, caso_uso: GestionarElementosParametricosDep
) -> ElementoParametricoCreado:
    nuevo = await caso_uso.crear(
        ComandoCrearElementoParametrico(
            clave=peticion.clave,
            nombre=peticion.nombre,
            tipo=peticion.tipo,
            parametros=dict(peticion.parametros),
            autor_id=ctx.usuario_id,
            categoria=peticion.categoria,
            subcategoria=peticion.subcategoria,
            materiales=_materiales(peticion.materiales),
        )
    )
    return ElementoParametricoCreado(id=nuevo)


@router.patch(
    "/elementos-parametricos/{elemento_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cambiar la clave, el nombre o algunos parámetros de un elemento paramétrico",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_DEFINEN))],
    responses={
        403: {"description": "Lo definen Control de obra y Costos."},
        404: {"description": "El elemento no existe o está fuera de tu alcance."},
        409: {"description": "El cambio lo dejaría idéntico a otro elemento: se usa el existente."},
        422: {"description": "Clave repetida, categoría o subcategoría que no existe, un parámetro que no vale o un material que no existe o es de otra familia."},
    },
)
async def actualizar_elemento_parametrico(
    elemento_id: UUID, peticion: ElementoParametricoCambio, ctx: ContextoActual, caso_uso: GestionarElementosParametricosDep
) -> None:
    """Si cambia la receta y hay obras asignadas que lo usan, nace una versión nueva (D-639): esas obras conservan la
    anterior y el resto pasa a la nueva."""
    await caso_uso.actualizar(
        elemento_id,
        clave=peticion.clave,
        nombre=peticion.nombre,
        parametros=dict(peticion.parametros) if peticion.parametros is not None else None,
        autor_id=ctx.usuario_id,
        categoria=peticion.categoria,
        subcategoria=peticion.subcategoria,
        materiales=_materiales(peticion.materiales),
    )


@router.delete(
    "/elementos-parametricos/{elemento_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Borrar un elemento paramétrico",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_DEFINEN))],
    responses={
        403: {"description": "Lo definen Control de obra y Costos."},
        404: {"description": "El elemento no existe o está fuera de tu alcance."},
    },
)
async def eliminar_elemento_parametrico(elemento_id: UUID, caso_uso: GestionarElementosParametricosDep) -> None:
    await caso_uso.eliminar(elemento_id)


class ElementoEnTrazoPeticion(BaseModel):
    elemento_id: UUID | None = Field(default=None, description="`null` le quita el elemento al trazo.")
    lados_cimbra: int | None = Field(default=None, ge=1, le=4, description="Fija a mano los lados de cimbra de esta pieza.")


class TotalDeElementoRespuesta(BaseModel):
    elemento_id: UUID
    clave: str
    nombre: str
    tipo: TipoDeElementoParametrico
    unidad: str
    colocados: int = Field(description="Cuántos trazos del plano son este elemento.")
    cantidad: float = Field(description="Piezas, metros o m² que suman, según la unidad.")
    concreto_m3: float
    acero_kg: float
    estribos_kg: float
    alambre_kg: float
    cimbra_m2: float
    cimbra_por_lados: dict[str, float]


class TrazoConElementoRespuesta(BaseModel):
    trazo_id: UUID
    elemento_id: UUID
    lados_cimbra: int | None


class ElementosDelPlanoRespuesta(BaseModel):
    totales: list[TotalDeElementoRespuesta]
    trazos: list[TrazoConElementoRespuesta]


@router.put(
    "/trazos/{trazo_id}/elemento-parametrico",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Marcar un trazo como un elemento paramétrico, o quitarle la marca",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={
        404: {"description": "El trazo o el elemento no existen o están fuera de tu alcance."},
        422: {"description": "El elemento se coloca con otra geometría, o la cimbra no tiene esos lados."},
    },
)
async def poner_elemento_en_trazo(
    trazo_id: UUID, peticion: ElementoEnTrazoPeticion, caso_uso: GestionarElementosParametricosDep
) -> None:
    """Un punto es una pieza (castillo, zapata), una línea son sus metros (trabe, cadena) y un área son sus m² (losa)."""
    await caso_uso.poner_en_trazo(trazo_id, peticion.elemento_id, peticion.lados_cimbra)


@router.get(
    "/planos/{plano_id}/elementos-parametricos",
    response_model=ElementosDelPlanoRespuesta,
    summary="Lo que llevan en total los elementos paramétricos colocados en un plano",
)
async def elementos_del_plano(plano_id: UUID, caso_uso: GestionarElementosParametricosDep) -> ElementosDelPlanoRespuesta:
    """La receta de una muestra × lo que aporta cada trazo (1 pieza, sus metros o sus m², con la escala calibrada)."""
    r = await caso_uso.totales_del_plano(plano_id)
    return ElementosDelPlanoRespuesta(
        totales=[
            TotalDeElementoRespuesta(**{**t, "cimbra_por_lados": {str(k): v for k, v in t["cimbra_por_lados"].items()}})
            for t in r["totales"]
        ],
        trazos=[TrazoConElementoRespuesta(**t) for t in r["trazos"]],
    )


class MaterialTomadoRespuesta(BaseModel):
    cantidad: float
    unidad: str


class ConceptoDelElementoRespuesta(BaseModel):
    concepto_id: UUID
    clave: str
    descripcion: str
    unidad: str = Field(description="En qué unidad se cuenta el concepto: pza, ml o m².")
    toma: dict[str, bool] = Field(description="Qué materiales toma: concreto, acero, estribos, alambre, cimbra.")
    por_unidad: dict[str, MaterialTomadoRespuesta] = Field(description="Lo que toma por unidad del concepto.")
    cantidad_por_muestra: float = Field(description="Cuántas unidades del concepto trae una muestra del elemento.")
    lados: int = Field(description="Los lados de cimbra con que se calcula.")


class ConceptoTomaPeticion(BaseModel):
    unidad: Literal["pza", "ml", "m²"]
    toma: dict[str, bool] = Field(description="Qué materiales toma: concreto, acero, estribos, alambre, cimbra.")


class ConceptoDelPlanoRespuesta(BaseModel):
    elemento_id: UUID
    concepto_id: UUID
    clave: str
    descripcion: str
    unidad: str
    cantidad: float = Field(description="Cuánto suma el concepto en el plano, en su unidad.")
    materiales: dict[str, MaterialTomadoRespuesta] = Field(description="Lo que toma en total, por material.")


@router.get(
    "/elementos-parametricos/{elemento_id}/conceptos",
    response_model=list[ConceptoDelElementoRespuesta],
    summary="Los conceptos que toman una parte de la receta del elemento",
    responses={404: {"description": "El elemento no existe o está fuera de tu alcance."}},
)
async def conceptos_del_elemento(elemento_id: UUID, caso_uso: GestionarElementosParametricosDep) -> list[ConceptoDelElementoRespuesta]:
    return [ConceptoDelElementoRespuesta(**c) for c in await caso_uso.conceptos(elemento_id)]


@router.put(
    "/elementos-parametricos/{elemento_id}/conceptos/{concepto_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Un concepto toma una parte de la receta del elemento",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_DEFINEN))],
    responses={
        404: {"description": "El elemento o el concepto no existen o están fuera de tu alcance."},
        422: {"description": "No toma ningún material, o la unidad no corresponde al elemento."},
    },
)
async def tomar_del_elemento(
    elemento_id: UUID, concepto_id: UUID, peticion: ConceptoTomaPeticion, ctx: ContextoActual, caso_uso: GestionarElementosParametricosDep
) -> None:
    await caso_uso.fijar_concepto(
        elemento_id, concepto_id, unidad=peticion.unidad, toma=peticion.toma, autor_id=ctx.usuario_id
    )


@router.delete(
    "/elementos-parametricos/{elemento_id}/conceptos/{concepto_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="El concepto deja de tomar del elemento",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_DEFINEN))],
    responses={404: {"description": "El elemento no existe o está fuera de tu alcance."}},
)
async def dejar_de_tomar_del_elemento(
    elemento_id: UUID, concepto_id: UUID, caso_uso: GestionarElementosParametricosDep
) -> None:
    await caso_uso.quitar_concepto(elemento_id, concepto_id)


@router.get(
    "/planos/{plano_id}/elementos-parametricos/conceptos",
    response_model=list[ConceptoDelPlanoRespuesta],
    summary="Lo que cada concepto toma, en total, de los elementos colocados en un plano",
)
async def conceptos_del_plano(plano_id: UUID, caso_uso: GestionarElementosParametricosDep) -> list[ConceptoDelPlanoRespuesta]:
    """La cantidad del concepto en su unidad y los materiales que toma, según los elementos que lleva el plano."""
    return [ConceptoDelPlanoRespuesta(**c) for c in await caso_uso.conceptos_del_plano(plano_id)]


@router.post(
    "/obras/{obra_id}/tomas/sincronizar",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Rehacer lo que las matrices de la obra toman de los elementos colocados",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
)
async def sincronizar_tomas(obra_id: UUID, caso_uso: GestionarElementosParametricosDep) -> None:
    """Se llama al borrar o mover trazos de elementos: la cantidad medida de cada matriz que toma de ellos se rehace
    (D-639). Lo trazado directo sobre la matriz manda sobre lo tomado."""
    await caso_uso.sincronizar_obra(obra_id)
