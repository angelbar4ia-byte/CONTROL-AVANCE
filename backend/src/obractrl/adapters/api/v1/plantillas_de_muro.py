"""Endpoints del Artefacto: las plantillas de muro, su validación contra la matriz y la ubicación por cara (plan de elementos de
muro, Ola 4A; M-1, M-4, M-6, M-19, Q9).

Una plantilla describe un muro (tipo, material, ubicación A/B, partes de altura) y las instancias de elementos que lleva
(castillos, cadenas, muro de tabique) enlazadas a sus conceptos. **Costos y Control de obra editan; solo Control de obra valida.**
Toda plantilla nace «por validar»; al cambiar una ya validada nace una versión nueva y los trazos ya medidos conservan la anterior.
Controladores delgados: las reglas viven en el dominio.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    ColocarElementosDeMuroDep,
    GestionarPlantillasDeMuroDep,
)
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.application.casos_uso.plantillas_de_muro import PlantillaEnUso
from obractrl.domain.cuantificacion.muro_tipo import CASTILLO_MODO_POR_TIPO, TIPOS_DE_MURO
from obractrl.domain.cuantificacion.muro_ubicacion import (
    CARAS,
    MATERIALES_DE_MURO,
    ROLES_DE_PARTE,
    UBICACIONES_DE_MURO,
    aplicar_ubicacion,
    sugerencia_por_losa,
    ubicacion_resultante,
)
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["artefacto de muros"])

ROLES_QUE_EDITAN = (Rol.CONTROL_OBRA, Rol.COSTOS)
ROLES_QUE_VALIDAN = (Rol.CONTROL_OBRA,)
ROLES_QUE_TRAZAN = (Rol.RESIDENTE, Rol.SUPERVISOR, Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE, Rol.COSTOS)

TipoDeMuro = Literal["confinado", "con_cadena", "tabique"]
Ubicacion = Literal["interior", "fachada_a", "fachada_b", "pretil", "barda", "personalizada"]
Cara = Literal["exterior", "interior"]
RolDeParte = Literal["cuerpo", "enrase", "pretil", "cadena"]
ClaseDeElemento = Literal["castillo", "cadena", "muro"]


class ParteDeAlturaDePlantilla(BaseModel):
    nombre: str = Field(default="", max_length=40)
    desde_m: Decimal = Field(ge=0)
    hasta_m: Decimal = Field(gt=0)
    suma: bool = True
    rol: RolDeParte | None = None
    cara_a: Cara | None = Field(default=None, description="Cara A: izquierda del sentido de dibujo. `null` = la de la ubicación.")
    cara_b: Cara | None = Field(default=None, description="Cara B: derecha del sentido de dibujo. `null` = la de la ubicación.")
    elemento_ref: str | None = Field(default=None, max_length=40, description="La cadena que define la parte.")


class ElementoDePlantilla(BaseModel):
    uid: str | None = Field(default=None, max_length=40, description="Identifica esta instancia; se genera si falta (K-1, K-1#2…).")
    ref: str = Field(min_length=1, max_length=40, description="La clave del elemento: del catálogo (K-1, CE-1) o de la biblioteca (EST-02010).")
    clase: ClaseDeElemento | None = Field(default=None, description="La resuelve el servidor; se ignora al guardar.")
    modo: Literal["estimado", "ubicado"] | None = Field(
        default=None, description="Solo castillos: sale del tipo (confinado: estimado; con_cadena: ubicado)."
    )
    sep_m: Decimal | None = Field(default=None, gt=0, description="Castillos estimados: separación (m); `null` = la del driver.")
    posicion: Literal["desplante", "cerramiento", "remate"] | None = Field(default=None, description="Solo cadenas.")
    z_m: Decimal | None = Field(default=None, ge=0, description="Altura de arranque sobre el cuerpo del muro (m).")


class PlantillaDeMuroPeticion(BaseModel):
    nombre: str = Field(min_length=1, max_length=80)
    tipo: TipoDeMuro
    material: str = Field(description="tabique_rojo, block_hueco o sillar_amarillo.")
    ubicacion: Ubicacion
    altura_m: Decimal | None = Field(default=None, gt=0, description="`null` = la altura estándar (driver).")
    partes: list[ParteDeAlturaDePlantilla] = Field(default_factory=list, max_length=20)
    elementos: list[ElementoDePlantilla] = Field(default_factory=list, max_length=40)
    acabado: dict[str, dict[str, bool]] | None = Field(default=None, description="Sí/No por capa y cara; lo que falta toma el defecto.")


class PlantillaDeMuro(BaseModel):
    id: UUID = Field(description="La versión de la plantilla; los trazos apuntan a esta fila.")
    raiz_id: UUID = Field(description="La misma para todas las versiones de la plantilla.")
    version: int
    vigente: bool
    nombre: str
    tipo: TipoDeMuro
    material: str
    ubicacion: Ubicacion
    altura_m: Decimal | None
    partes: list[ParteDeAlturaDePlantilla]
    elementos: list[ElementoDePlantilla]
    acabado: dict[str, dict[str, bool]] | None
    validacion: Literal["por_validar", "validada"]
    propuso_nombre: str | None
    propuso_rol: str | None
    validada_por_nombre: str | None
    validada_en: datetime | None
    trazos: int = Field(description="Cuántos trazos usan esta versión.")
    created_at: datetime
    updated_at: datetime


class PlantillaDeMuroGuardada(PlantillaDeMuro):
    version_nueva: bool = Field(default=False, description="`true` si el cambio creó una versión nueva (la anterior estaba validada).")


class AlertaDeValidacion(BaseModel):
    nivel: Literal["bloquea", "alerta"]
    codigo: str
    uid: str
    ref: str
    parte: str | None
    concepto: str | None
    mensaje: str


class RevisionDePlantilla(BaseModel):
    plantilla: PlantillaDeMuro
    alertas: list[AlertaDeValidacion]
    bloquea: bool = Field(description="Hay alertas que impiden validar.")
    validable: bool


class ValidarPeticion(BaseModel):
    aceptar_alertas: bool = Field(default=False, description="Control de obra acepta expresamente las alertas por revisar.")


class ElegirPlantillaPeticion(BaseModel):
    plantilla_id: UUID | None = Field(description="La plantilla (versión) para el muro; `null` la desliga.")


class ElegirPlantillaRespuesta(BaseModel):
    tipo: TipoDeMuro | None
    material: str | None
    ubicacion: Ubicacion | None
    plantilla_id: UUID | None
    acabado: dict[str, dict[str, bool]] | None


class TipoDeMuroFicha(BaseModel):
    clave: TipoDeMuro
    nombre: str
    castillo_modo: Literal["estimado", "ubicado"] | None
    descripcion: str


class MaterialDeMuro(BaseModel):
    clave: str
    nombre: str
    espesor_cm: float | None = Field(description="`null` = por confirmar con el usuario (Q4).")
    elemento: str | None = Field(description="El elemento de la biblioteca que lo paga (tabique rojo → EST-02010).")


class UbicacionDeMuroFicha(BaseModel):
    clave: Ubicacion
    nombre: str
    cara_a: Cara | None
    cara_b: Cara | None
    enrase_exterior: bool
    elementos_sugeridos: list[str]


class CatalogoDelArtefacto(BaseModel):
    tipos: list[TipoDeMuroFicha]
    materiales: list[MaterialDeMuro]
    ubicaciones: list[UbicacionDeMuroFicha]
    caras: list[Cara]
    roles_de_parte: list[RolDeParte]


class AplicarUbicacionPeticion(BaseModel):
    ubicacion: Ubicacion
    partes: list[ParteDeAlturaDePlantilla] = Field(max_length=20)
    altura_de_losa_m: Decimal | None = Field(
        default=None, gt=0, description="Con la losa más baja que el muro, sugiere exterior las partes que arrancan en la losa o arriba."
    )


class SugerenciaPorLosa(BaseModel):
    indice: int
    nombre: str
    cara_a: Cara
    cara_b: Cara


class AplicarUbicacionRespuesta(BaseModel):
    ubicacion: Ubicacion
    partes: list[ParteDeAlturaDePlantilla]
    sugerencias: list[SugerenciaPorLosa] = Field(description="Solo sugeridas: se aplican al confirmar.")


_DESCRIPCIONES_DE_TIPO = {
    "confinado": "Rápido: los castillos se estiman por separación, sin colocarlos en el plano.",
    "con_cadena": "Los castillos se colocan en el plano y se restan de los m² de la mampostería.",
    "tabique": "Sin cadenas ni castillos.",
}
_NOMBRES_DE_TIPO = {"confinado": "Muro confinado", "con_cadena": "Muro con cadena", "tabique": "Muro de tabique"}


def _plantilla(f: dict[str, Any]) -> PlantillaDeMuro:
    return PlantillaDeMuro.model_validate({k: v for k, v in f.items() if k in PlantillaDeMuro.model_fields})


def _guardada(f: dict[str, Any]) -> PlantillaDeMuroGuardada:
    return PlantillaDeMuroGuardada.model_validate({k: v for k, v in f.items() if k in PlantillaDeMuroGuardada.model_fields})


def _revision(r: dict[str, Any]) -> RevisionDePlantilla:
    return RevisionDePlantilla(
        plantilla=_plantilla(r["plantilla"]),
        alertas=[AlertaDeValidacion(**{k: getattr(a, k) for k in AlertaDeValidacion.model_fields}) for a in r["alertas"]],
        bloquea=r["bloquea"],
        validable=r["validable"],
    )


def _entrada(p: PlantillaDeMuroPeticion) -> dict[str, Any]:
    return p.model_dump(mode="python")


_NO_ENCONTRADA = {404: {"description": "La plantilla no existe o está fuera de tu alcance."}}


@router.get(
    "/muro-artefacto/catalogo",
    response_model=CatalogoDelArtefacto,
    summary="Tipos de muro, materiales y ubicaciones (con sus caras A y B) del Artefacto",
)
async def catalogo_del_artefacto() -> CatalogoDelArtefacto:
    return CatalogoDelArtefacto(
        tipos=[
            TipoDeMuroFicha(clave=t, nombre=_NOMBRES_DE_TIPO[t], castillo_modo=CASTILLO_MODO_POR_TIPO[t], descripcion=_DESCRIPCIONES_DE_TIPO[t])  # type: ignore[arg-type]
            for t in TIPOS_DE_MURO
        ],
        materiales=[MaterialDeMuro(clave=k, nombre=v["nombre"], espesor_cm=v["espesor_cm"], elemento=v["elemento"]) for k, v in MATERIALES_DE_MURO.items()],
        ubicaciones=[
            UbicacionDeMuroFicha(
                clave=k,  # type: ignore[arg-type]
                nombre=v["nombre"],
                cara_a=v["caras"][0] if v["caras"] else None,
                cara_b=v["caras"][1] if v["caras"] else None,
                enrase_exterior=v["enrase_exterior"],
                elementos_sugeridos=list(v["elementos_sugeridos"]),
            )
            for k, v in UBICACIONES_DE_MURO.items()
        ],
        caras=list(CARAS),  # type: ignore[arg-type]
        roles_de_parte=list(ROLES_DE_PARTE),  # type: ignore[arg-type]
    )


@router.post(
    "/muro-artefacto/ubicacion",
    response_model=AplicarUbicacionRespuesta,
    summary="Las caras A y B de cada parte de altura según la ubicación (no guarda nada)",
    responses={422: {"description": "La ubicación o las partes no valen."}},
)
async def aplicar_ubicacion_a_partes(peticion: AplicarUbicacionPeticion) -> AplicarUbicacionRespuesta:
    partes = [p.model_dump(mode="python") for p in peticion.partes]
    nuevas = aplicar_ubicacion(peticion.ubicacion, partes) if peticion.ubicacion != "personalizada" else partes
    sugerencias = sugerencia_por_losa(nuevas, peticion.altura_de_losa_m) if peticion.altura_de_losa_m else []
    return AplicarUbicacionRespuesta(
        ubicacion=ubicacion_resultante(peticion.ubicacion, nuevas),  # type: ignore[arg-type]
        partes=[ParteDeAlturaDePlantilla.model_validate(p) for p in nuevas],
        sugerencias=[SugerenciaPorLosa(**s) for s in sugerencias],
    )


@router.get("/muro-plantillas", response_model=list[PlantillaDeMuro], summary="Las plantillas de muro vigentes")
async def listar_plantillas(caso_uso: GestionarPlantillasDeMuroDep) -> list[PlantillaDeMuro]:
    return [_plantilla(f) for f in await caso_uso.listar()]


@router.post(
    "/muro-plantillas",
    response_model=PlantillaDeMuroGuardada,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una plantilla de muro (nace «por validar»)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
    responses={422: {"description": "La plantilla no vale: tipo, material, ubicación, partes o elementos."}},
)
async def crear_plantilla(peticion: PlantillaDeMuroPeticion, ctx: ContextoActual, caso_uso: GestionarPlantillasDeMuroDep) -> PlantillaDeMuroGuardada:
    return _guardada(await caso_uso.crear(_entrada(peticion), autor_id=ctx.usuario_id, rol=str(Rol(ctx.rol).value)))


@router.get(
    "/muro-plantillas/{plantilla_id}", response_model=PlantillaDeMuro, summary="Una plantilla de muro", responses=_NO_ENCONTRADA
)
async def ver_plantilla(plantilla_id: UUID, caso_uso: GestionarPlantillasDeMuroDep) -> PlantillaDeMuro:
    return _plantilla(await caso_uso.obtener(plantilla_id))


@router.put(
    "/muro-plantillas/{plantilla_id}",
    response_model=PlantillaDeMuroGuardada,
    summary="Cambiar una plantilla: por validar se edita en el lugar; validada crea la versión siguiente (Q9)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
    responses={**_NO_ENCONTRADA, 422: {"description": "La plantilla no vale o la versión ya no es la vigente."}},
)
async def cambiar_plantilla(
    plantilla_id: UUID, peticion: PlantillaDeMuroPeticion, ctx: ContextoActual, caso_uso: GestionarPlantillasDeMuroDep
) -> PlantillaDeMuroGuardada:
    return _guardada(await caso_uso.actualizar(plantilla_id, _entrada(peticion), autor_id=ctx.usuario_id, rol=str(Rol(ctx.rol).value)))


@router.delete(
    "/muro-plantillas/{plantilla_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Borrar una plantilla que ningún trazo usa",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
    responses={**_NO_ENCONTRADA, 409: {"description": "Algún trazo usa una versión de la plantilla."}},
)
async def borrar_plantilla(plantilla_id: UUID, ctx: ContextoActual, caso_uso: GestionarPlantillasDeMuroDep) -> Response:
    try:
        await caso_uso.eliminar(plantilla_id, rol=str(Rol(ctx.rol).value))
    except PlantillaEnUso as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/muro-plantillas/{plantilla_id}/versiones",
    response_model=list[PlantillaDeMuro],
    summary="Todas las versiones de la plantilla, de la más nueva a la más vieja",
    responses=_NO_ENCONTRADA,
)
async def versiones_de_la_plantilla(plantilla_id: UUID, caso_uso: GestionarPlantillasDeMuroDep) -> list[PlantillaDeMuro]:
    return [_plantilla(f) for f in await caso_uso.versiones(plantilla_id)]


@router.get(
    "/muro-plantillas/{plantilla_id}/revision",
    response_model=RevisionDePlantilla,
    summary="Lo que no cuadra entre los elementos de la plantilla y la matriz de sus conceptos (no cambia nada)",
    responses=_NO_ENCONTRADA,
)
async def revisar_plantilla(plantilla_id: UUID, caso_uso: GestionarPlantillasDeMuroDep) -> RevisionDePlantilla:
    return _revision(await caso_uso.revisar(plantilla_id))


@router.post(
    "/muro-plantillas/{plantilla_id}/validar",
    response_model=RevisionDePlantilla,
    summary="Control de obra valida la plantilla contra la matriz de los conceptos de sus elementos",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_VALIDAN))],
    responses={
        **_NO_ENCONTRADA,
        403: {"description": "Solo Control de obra valida."},
        422: {"description": "Hay alertas que bloquean, o alertas por revisar que no se aceptaron."},
    },
)
async def validar_plantilla(
    plantilla_id: UUID, peticion: ValidarPeticion, ctx: ContextoActual, caso_uso: GestionarPlantillasDeMuroDep
) -> RevisionDePlantilla:
    return _revision(
        await caso_uso.validar(
            plantilla_id, usuario_id=ctx.usuario_id, rol=str(Rol(ctx.rol).value), aceptar_alertas=peticion.aceptar_alertas
        )
    )


@router.put(
    "/trazos/{trazo_id}/muro/plantilla",
    response_model=ElegirPlantillaRespuesta,
    summary="Elegir la plantilla de muro de un trazo (guarda la versión; las cantidades no cambian)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={
        404: {"description": "El trazo o la plantilla no existen o están fuera de tu alcance."},
        422: {"description": "El trazo no es una línea."},
    },
)
async def elegir_plantilla_del_trazo(
    trazo_id: UUID, peticion: ElegirPlantillaPeticion, caso_uso: GestionarPlantillasDeMuroDep
) -> ElegirPlantillaRespuesta:
    r = await caso_uso.elegir_en_trazo(trazo_id, peticion.plantilla_id)
    return ElegirPlantillaRespuesta(**{k: r[k] for k in ElegirPlantillaRespuesta.model_fields})


# --- Colocar lo que trae la plantilla en el plano (Ola 4C) -----------------------------------------------------------------


class ConceptoColocadoRespuesta(BaseModel):
    ranura: Literal["acero", "colado", "completo"] | None
    concepto_id: UUID | None
    clave: str
    unidad: str
    cantidad: Decimal
    cuenta: bool = Field(description="Solo con el concepto autorizado, su unidad admitida y su partida en el árbol de la obra.")
    estado: Literal["cuenta", "falta_partida", "propuesto", "unidad_no_admitida"]
    origen: Literal["contexto", "ranura"] = Field(description="`contexto`: lo eligieron el nivel y el alto (2A). `ranura`: lo enlazó el Paramétrico (4B).")
    aviso: str | None
    partida_id: UUID | None


class ElementoColocadoRespuesta(BaseModel):
    uid: str
    ref: str
    nombre: str
    clase: Literal["castillo", "cadena"]
    modo: Literal["estimado", "ubicado"] | None
    piezas: int
    alto_m: Decimal | None = Field(description="Lo alto de cada castillo: la altura del muro menos su arranque.")
    z_m: Decimal
    metros: Decimal = Field(description="Castillos: piezas × alto. Cadena: el largo del muro.")
    posiciones_m: list[Decimal] = Field(description="El centro de cada castillo ubicado, en metros desde el inicio del muro.")
    se_coloca: bool = Field(description="Un castillo ubicado se coloca en el plano y resta de la mampostería; uno estimado solo se cuenta.")
    colocados: int = Field(description="Cuántas piezas de este elemento ya están colocadas en el plano.")
    descuento_m2_por_cara: Decimal
    conceptos: list[ConceptoColocadoRespuesta]


class ColocacionDelMuroRespuesta(BaseModel):
    trazo_id: UUID
    plantilla_id: UUID
    plantilla: str
    version: int
    largo_m: Decimal
    altura_m: Decimal = Field(description="La altura del muro: la suya o, si no tiene, el driver `altura_estandar` de la obra.")
    nivel: int | None = Field(description="El número de nivel con que se eligen los conceptos (el orden del nivel de la partida que ya mide el muro).")
    ubicacion: str | None
    elementos: list[ElementoColocadoRespuesta]
    avisos: list[str]


class MuroColocadoRespuesta(BaseModel):
    colocados: int
    reemplazados: int
    descuento_m2_por_cara: Decimal


class MuroRetiradoRespuesta(BaseModel):
    retirados: int


_COLOCAR = {
    403: {"description": "El muro alimenta un prototipo_nodo y el rol no es Control de obra ni Super intendente."},
    404: {"description": "El trazo no existe o está fuera de tu alcance."},
    422: {"description": "El muro no es una línea, no tiene plantilla o su plantilla no lleva castillos ubicados."},
}


@router.get(
    "/trazos/{trazo_id}/muro/plantilla/colocacion",
    response_model=ColocacionDelMuroRespuesta,
    summary="Lo que la plantilla coloca en este muro y a qué conceptos alimenta (no cambia nada)",
    responses={404: _COLOCAR[404], 422: _COLOCAR[422]},
)
async def colocacion_del_muro(trazo_id: UUID, caso_uso: ColocarElementosDeMuroDep) -> ColocacionDelMuroRespuesta:
    """Castillos (piezas, alto, posiciones) y cadenas (metros) de la plantilla según el largo, la altura y el nivel del muro, y el concepto
    que paga cada parte; si falta su partida en el árbol de la obra avisa y no cuenta."""
    return ColocacionDelMuroRespuesta.model_validate(await caso_uso.ver_colocacion(trazo_id))


@router.post(
    "/trazos/{trazo_id}/muro/plantilla/colocar",
    response_model=MuroColocadoRespuesta,
    summary="Colocar en el plano los castillos ubicados de la plantilla (reemplaza solo los de la plantilla)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses=_COLOCAR,
)
async def colocar_plantilla_en_el_muro(trazo_id: UUID, ctx: ContextoActual, caso_uso: ColocarElementosDeMuroDep) -> MuroColocadoRespuesta:
    """Cada castillo es una instancia del elemento de la plantilla: sube la altura del muro menos su arranque y resta de sus m².
    Idempotente: colocar de nuevo reemplaza las instancias anteriores; los vanos y castillos puestos a mano no se tocan."""
    r = await caso_uso.colocar(trazo_id, rol=Rol(ctx.rol), autor_id=ctx.usuario_id, detectada_en=datetime.now(UTC))
    return MuroColocadoRespuesta(colocados=r["colocados"], reemplazados=r["reemplazados"], descuento_m2_por_cara=r["descuento_m2_por_cara"])


@router.delete(
    "/trazos/{trazo_id}/muro/plantilla/colocar",
    response_model=MuroRetiradoRespuesta,
    summary="Retirar del plano lo que colocó la plantilla (los vanos puestos a mano no se tocan)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={403: _COLOCAR[403], 404: _COLOCAR[404]},
)
async def retirar_plantilla_del_muro(trazo_id: UUID, ctx: ContextoActual, caso_uso: ColocarElementosDeMuroDep) -> MuroRetiradoRespuesta:
    r = await caso_uso.retirar(trazo_id, rol=Rol(ctx.rol), autor_id=ctx.usuario_id, detectada_en=datetime.now(UTC))
    return MuroRetiradoRespuesta(retirados=r["retirados"])
