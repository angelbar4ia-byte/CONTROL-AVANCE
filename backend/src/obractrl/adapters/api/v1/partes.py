"""Las partes de una obra y sus plantas (migración 0074; cerebro D-571, D-575).

Una **parte** es una etapa de construcción o un concepto independiente (losas, pisos): lo que
los escenarios de arranque envían, autorizan y programan por separado. Las plantas (1 o 2)
fijan el catálogo base de cuantificación y el plazo base del programa.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    AgregarActividadNuevaDep,
    CambiarEstadoDePartesDep,
    ConsultarAlertasDePartesDep,
    ConsultarArranqueDep,
    ConsultarBitacoraDePartesDep,
    ConsultarCargaDePartesDep,
    ConsultarCatalogosBaseDep,
    ConsultarCotizacionesDep,
    ConsultarDesfaseDePartesDep,
    ConsultarModificacionesDep,
    ConsultarPartesDep,
    ConsultarValuacionDep,
    CotizarLoModificadoDep,
    CrearConceptoEnObraDep,
    CrearObraDesdeCatalogoBaseDep,
    CrearObraDesdeCeroDep,
    FijarCandadoDeAsignarDep,
    FijarDesfaseDePartesDep,
    FijarPlantasDeObraDep,
    FijarPlantasDePrototipoDep,
    MarcarParteIndependienteDep,
    ModificarActividadDep,
    RedisenarParteDep,
    ResponderCotizacionDep,
)
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.adapters.api.idempotencia import Idempotencia
from obractrl.application.casos_uso.conceptos_en_obra import ComandoCrearConceptoEnObra
from obractrl.application.casos_uso.cotizacion_al_cliente import ComandoCotizar
from obractrl.application.casos_uso.crear_obra_desde_catalogo_base import (
    ComandoCrearObraDesdeCatalogoBase,
    ComandoCrearObraDesdeCero,
)
from obractrl.application.casos_uso.gestionar_partes import (
    ComandoAgregarActividadNueva,
    ComandoCambiarEstadoDePartes,
    ComandoModificarActividad,
)
from obractrl.application.casos_uso.valuacion_de_partes import ComandoRedisenarParte
from obractrl.domain.partes.cotizacion import MetodoDePrecio
from obractrl.domain.partes.estado import Accion, EstadoDeParte
from obractrl.domain.partes.modificacion import TipoDeModificacion
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["partes"])


class ParteRespuesta(BaseModel):
    clave: str = Field(description="`etapa:<id>`, `concepto:<id>` o `sin_etapa:-`.")
    tipo: str = Field(description="`etapa` · `concepto` (independiente) · `sin_etapa`.")
    id: UUID | None = Field(default=None, description="La etapa o la actividad independiente.")
    nombre: str
    estado: str = Field(
        description=(
            "`cuantificando` · `enviada_presupuesto` · `por_validar` · `autorizada` · "
            "`enviada_programa` · `programada` · `asignada`. Sin renglón: `cuantificando`."
        )
    )
    programa_por_revisar: bool = Field(
        default=False,
        description=(
            "La parte se devolvió teniendo programa: ese programa puede estar desactualizado. "
            "Se quita al volver a programarla."
        ),
    )
    n_actividades: int
    actividad_ids: list[UUID]
    importe: Decimal
    avance_pct: Decimal = Field(description="Ponderado por importe, como el de la obra.")


class PartesDeObraRespuesta(BaseModel):
    obra_id: UUID
    plantas: int | None = Field(default=None, description="1 o 2; nace del prototipo.")
    plantas_del_prototipo: int | None = None
    partes: list[ParteRespuesta]


class ParteIndependientePeticion(BaseModel):
    independiente: bool = Field(
        description="`true`: la actividad es una parte por sí sola (losa, piso…)."
    )


class PlantasPeticion(BaseModel):
    plantas: int | None = Field(default=None, description="1 o 2; `null` la deja sin decir.")


class CambiarEstadoPeticion(BaseModel):
    accion: Accion = Field(description="Qué se hace con las partes.")
    claves: list[str] = Field(default_factory=list, description="Las partes (por `clave`).")
    todas: bool = Field(
        default=False,
        description="Todas las partes que están en el paso que la acción pide («el total»).",
    )
    a: EstadoDeParte | None = Field(
        default=None, description="Solo `devolver`: el paso anterior al que se vuelve."
    )
    nota: str | None = None


class PasoDeParteRespuesta(BaseModel):
    clave: str
    de: str
    a: str
    aviso: str | None = Field(
        default=None,
        description="Se puede seguir, pero hay algo que ver: cantidad solo estimada (D-579).",
    )


class TransicionDeParteRespuesta(BaseModel):
    id: UUID
    clave: str
    accion: str
    de: str
    a: str
    usuario_id: UUID
    usuario_nombre: str | None = None
    rol: str
    nota: str | None = None
    creada_en: datetime


class AlertaDeParteRespuesta(BaseModel):
    clave: str
    nombre: str
    estado: str
    inicio: date = Field(description="Cuándo necesita el programa la parte.")
    dias: int = Field(description="Días para necesitarla; negativo si ya la necesitaba.")
    severidad: str = Field(description="`aviso` (a las 2 semanas) · `importante` (a la semana).")


class AlertasDePartesRespuesta(BaseModel):
    obra_id: UUID
    aviso_dias: int
    importante_dias: int
    alertas: list[AlertaDeParteRespuesta]


class CargaDeParteRespuesta(BaseModel):
    clave: str
    nombre: str
    etapa: str | None = Field(default=None, description="La clave de la etapa (`ECO-…`).")
    estado: str = Field(description="`incompleto` · `completo`.")
    porcentaje_cargado: Decimal = Field(description="Importe cargado / presupuestado, de 0 a 100.")
    importe_presupuestado: Decimal
    importe_pendiente: Decimal = Field(description="Lo que falta cargar.")


class CargaDePartesRespuesta(BaseModel):
    obra_id: UUID
    incompletas: int
    partes: list[CargaDeParteRespuesta]


class ModificacionPeticion(BaseModel):
    tipo: Literal["cambio", "adicional"] = Field(
        description="`cambio` puede restar (se elimina del presupuesto); `adicional` solo suma."
    )
    delta: Decimal = Field(description="Cuánto cambia la cantidad; negativo solo en un cambio.")
    nota: str | None = None


class ModificacionRespuesta(BaseModel):
    actividad_id: UUID
    clave: str = Field(description="La parte a la que pertenece.")
    tipo: str
    cantidad_antes: Decimal
    delta: Decimal
    cantidad_despues: Decimal
    parte_reabierta: bool = Field(
        description="La parte ya estaba validada o más allá: volvió a cuantificarse."
    )


class ActividadNuevaPeticion(BaseModel):
    tipo: Literal["cambio", "adicional"]
    descripcion: str = Field(min_length=1)
    cantidad: Decimal = Field(gt=0)
    precio_unitario: Decimal = Field(default=Decimal(0), ge=0)
    concepto_id: UUID | None = Field(default=None, description="Si el concepto es del catálogo.")
    etapa_id: UUID | None = Field(default=None, description="La etapa donde nace; suelta si falta.")
    nivel_id: UUID | None = None
    nota: str | None = None


class ActividadNuevaRespuesta(BaseModel):
    actividad_id: UUID
    clave: str
    tipo: str
    cantidad: Decimal
    parte_reabierta: bool


class RegistroDeModificacionRespuesta(BaseModel):
    id: UUID
    actividad_id: UUID
    descripcion: str
    concepto_clave: str | None = None
    tipo: str
    cantidad_antes: Decimal
    delta: Decimal
    cantidad_despues: Decimal
    nace_nueva: bool
    nota: str | None = None
    usuario_id: UUID
    usuario_nombre: str | None = None
    rol: str
    creada_en: datetime


class CatalogoBaseRespuesta(BaseModel):
    plantas: int
    plazo_base_semanas: int = Field(description="El número de plantas fija el plazo base (D-419).")
    prototipo_clave: str | None = Field(
        default=None, description="El prototipo de cuya estructura se forma el catálogo."
    )
    prototipo_nombre: str | None = None
    n_nodos: int
    disponible: bool


class ObraNuevaPeticion(BaseModel):
    cluster_id: UUID
    clave: str = Field(min_length=1)
    plantas: Literal[1, 2] = Field(description="El catálogo base: de 1 planta o de 2.")
    residente_id: UUID | None = None


class ObraNuevaRespuesta(BaseModel):
    obra_id: UUID
    prototipo_id: UUID
    plantas: int
    plazo_base_semanas: int
    base_clave: str = Field(description="El prototipo de cuya estructura se formó el catálogo.")
    nodos: int = Field(description="Nodos del catálogo, sin cantidades.")


class ObraDesdeCeroPeticion(BaseModel):
    cluster_id: UUID
    clave: str = Field(min_length=1)
    plantas: Literal[1, 2] | None = None
    residente_id: UUID | None = None


class ObraDesdeCeroRespuesta(BaseModel):
    obra_id: UUID
    prototipo_id: UUID
    presupuesto_id: UUID = Field(description="Donde los ensambles componen sus instancias.")
    plantas: int | None = None


class ValuacionRespuesta(BaseModel):
    forma: str = Field(description="`pu` · `parametrico` · `mixto` (se reporta, no se guarda).")
    importe: Decimal
    importe_parametrico: Decimal
    porcentaje_parametrico: Decimal = Field(description="Del importe, 0 a 100.")
    n_estimadas: int
    n_renglones: int
    estimado_original: Decimal = Field(description="Lo que valía, al precio de hoy, lo que ya se midió.")
    medido: Decimal
    desviacion_pct: Decimal | None = Field(
        default=None, description="Cuánto se alejó lo medido de lo estimado; vuelve al paramétrico."
    )


class ValuacionDeParteRespuesta(ValuacionRespuesta):
    clave: str
    nombre: str


class ValuacionDeObraRespuesta(BaseModel):
    obra_id: UUID
    obra: ValuacionRespuesta
    partes: list[ValuacionDeParteRespuesta]


class RedisenoPeticion(BaseModel):
    clave: str = Field(description="La parte (`etapa:<id>`, `concepto:<id>` o `sin_etapa:-`).")
    ensamble_id: UUID
    factor: Decimal = Field(gt=0, description="Cuántas veces entra el ensamble en esta parte.")
    aplicar: bool = Field(default=False, description="Sin esto solo propone.")


class PropuestaDeRedisenoRespuesta(BaseModel):
    actividad_id: UUID
    concepto_clave: str
    descripcion: str
    cantidad_actual: Decimal
    cantidad_estimada: Decimal
    importe_actual: Decimal
    importe_estimado: Decimal
    ya_estimada: bool


class RedisenoRespuesta(BaseModel):
    clave: str
    ensamble_clave: str
    factor: Decimal
    aplicado: bool
    propuestas: list[PropuestaDeRedisenoRespuesta]
    sin_renglon_en_la_parte: list[str] = Field(
        description="Conceptos del ensamble que la parte no tiene: no se agregan."
    )
    conservan_pu: int = Field(description="Renglones de la parte que el ensamble no cubre.")
    forma_despues: str
    porcentaje_parametrico_despues: Decimal


class CotizacionPeticion(BaseModel):
    metodo_precio: Literal["por_diferencia", "por_m2"] = Field(
        description="`por_diferencia`: lo que entra menos lo que sale entre el factor (0.7). "
        "`por_m2`: los m² de la ampliación por el precio por m²."
    )
    m2_ampliacion: Decimal | None = Field(default=None, gt=0)
    precio_m2: Decimal | None = Field(default=None, gt=0, description="Si falta, el configurado (17,000).")
    nota: str | None = None


class LineaDeCotizacionRespuesta(BaseModel):
    bloque: str = Field(description="`entra` o `sale`: las cantidades van positivas y el sistema resta.")
    actividad_id: UUID
    descripcion: str
    concepto_clave: str | None = None
    cantidad: Decimal
    precio_unitario: Decimal
    costo_directo: Decimal


class CotizacionRespuesta(BaseModel):
    id: UUID
    obra_id: UUID
    folio: str
    metodo_precio: str
    estado: str = Field(description="`enviada` · `aceptada` · `rechazada`.")
    factor: Decimal
    costo_entra: Decimal
    costo_sale: Decimal
    m2_ampliacion: Decimal | None = None
    precio_m2: Decimal | None = None
    precio_por_diferencia: Decimal
    precio_por_m2: Decimal | None = None
    precio: Decimal = Field(description="El que se le cobra al cliente, según el método elegido.")
    por_m2_coincide_con_la_diferencia: bool | None = Field(
        default=None,
        description="Por m² y por diferencia no siempre coinciden: no se corrige solo (D-533).",
    )
    entra: list[LineaDeCotizacionRespuesta]
    sale: list[LineaDeCotizacionRespuesta]
    nota: str | None = None
    creada_por: UUID
    creada_por_nombre: str | None = None
    creada_en: datetime
    respondida_en: datetime | None = None


class RespuestaDelClientePeticion(BaseModel):
    aceptada: bool
    nota: str | None = None


class ParteSinAutorizarRespuesta(BaseModel):
    clave: str
    nombre: str
    estado: str


class ArranqueRespuesta(BaseModel):
    obra_id: UUID
    candado_asignar: bool
    total: int
    por_estado: dict[str, int]
    sin_autorizar: list[ParteSinAutorizarRespuesta]
    todo_validado: bool = Field(
        description="Todas las partes están autorizadas o más. Requisito de la junta; avisa."
    )
    programas_por_revisar: int


class CandadoPeticion(BaseModel):
    activo: bool = Field(
        description=(
            "Con el candado, validar una parte exige una anotación y asignarla exige que quien "
            "la validó la haya dejado."
        )
    )


class DesfaseDePartesPeticion(BaseModel):
    aviso_dias: int = Field(ge=0, description="Días antes de que el programa la necesite: aviso.")
    importante_dias: int = Field(ge=0, description="Días antes: alerta importante.")


class DesfaseDePartesRespuesta(BaseModel):
    aviso_dias: int
    importante_dias: int


_NO_ENCONTRADO = {404: {"description": "No existe o está fuera de tu alcance (§12.4)."}}


@router.get(
    "/obras/{obra_id}/partes",
    response_model=PartesDeObraRespuesta,
    summary="Las partes de una obra: etapas y conceptos independientes",
    responses=_NO_ENCONTRADO,
)
async def partes_de_la_obra(obra_id: UUID, caso_uso: ConsultarPartesDep) -> PartesDeObraRespuesta:
    """Todos los roles, cada uno con su alcance (RLS)."""
    return PartesDeObraRespuesta(**await caso_uso.ejecutar(obra_id))


@router.put(
    "/actividades/{actividad_id}/parte-independiente",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Una actividad es una parte por sí sola, o vuelve a viajar con su etapa",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.SUPERVISOR))],
    responses=_NO_ENCONTRADO,
)
async def marcar_parte_independiente(
    actividad_id: UUID, peticion: ParteIndependientePeticion, caso_uso: MarcarParteIndependienteDep
) -> None:
    await caso_uso.ejecutar(actividad_id, peticion.independiente)


@router.put(
    "/obras/{obra_id}/plantas",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Las plantas de la obra (1 o 2)",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA))],
    responses={**_NO_ENCONTRADO, 422: {"description": "Una casa tiene 1 o 2 plantas."}},
)
async def fijar_plantas_de_obra(
    obra_id: UUID, peticion: PlantasPeticion, caso_uso: FijarPlantasDeObraDep
) -> None:
    await caso_uso.ejecutar(obra_id, peticion.plantas)


@router.put(
    "/prototipos/{prototipo_id}/plantas",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Las plantas del prototipo (1 o 2)",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA))],
    responses={**_NO_ENCONTRADO, 422: {"description": "Una casa tiene 1 o 2 plantas."}},
)
async def fijar_plantas_de_prototipo(
    prototipo_id: UUID, peticion: PlantasPeticion, caso_uso: FijarPlantasDePrototipoDep
) -> None:
    await caso_uso.ejecutar(prototipo_id, peticion.plantas)


@router.post(
    "/obras/{obra_id}/partes/transicion",
    response_model=list[PasoDeParteRespuesta],
    summary="Mandar, autorizar, validar, programar, asignar o devolver partes",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.SUPERVISOR, Rol.COSTOS)), Idempotencia],
    responses={
        **_NO_ENCONTRADO,
        403: {"description": "Tu rol no puede hacer esa acción sobre una parte."},
        409: {"description": "Una parte no está en el paso que la acción pide (no se escribe ninguna)."},
    },
)
async def cambiar_estado_de_partes(
    obra_id: UUID,
    peticion: CambiarEstadoPeticion,
    ctx: ContextoActual,
    caso_uso: CambiarEstadoDePartesDep,
) -> list[PasoDeParteRespuesta]:
    """Una, varias o todas («total o por partes»). Todo o nada: si una parte no puede dar el
    paso, no se escribe ninguna. Cada paso queda en la bitácora."""
    pasos = await caso_uso.ejecutar(
        ComandoCambiarEstadoDePartes(
            obra_id=obra_id,
            accion=peticion.accion,
            usuario_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
            claves=tuple(peticion.claves),
            todas=peticion.todas,
            a=peticion.a,
            nota=peticion.nota,
        )
    )
    return [PasoDeParteRespuesta(**p) for p in pasos]


@router.get(
    "/obras/{obra_id}/partes/bitacora",
    response_model=list[TransicionDeParteRespuesta],
    summary="Bitácora de las partes: quién mandó, autorizó o devolvió qué",
    responses=_NO_ENCONTRADO,
)
async def bitacora_de_partes(
    obra_id: UUID, caso_uso: ConsultarBitacoraDePartesDep
) -> list[TransicionDeParteRespuesta]:
    """Todos los roles, cada uno con su alcance. Lo más reciente, primero. No se edita."""
    return [TransicionDeParteRespuesta(**f) for f in await caso_uso.ejecutar(obra_id)]


@router.get(
    "/obras/{obra_id}/partes/alertas",
    response_model=AlertasDePartesRespuesta,
    summary="Partes sin autorizar que el programa necesita pronto",
    responses=_NO_ENCONTRADO,
)
async def alertas_de_partes(
    obra_id: UUID, caso_uso: ConsultarAlertasDePartesDep
) -> AlertasDePartesRespuesta:
    """El presupuesto debe ir por delante del programa (D-575): a 2 semanas de que lo necesite y
    sin autorizar, aviso; a 1 semana o vencida, importante. Avisa; no bloquea."""
    return AlertasDePartesRespuesta(**await caso_uso.ejecutar(obra_id))


@router.get(
    "/obras/{obra_id}/partes/carga",
    response_model=CargaDePartesRespuesta,
    summary="Cuánta ingeniería de cada parte ya llegó (ESTADO_CARGA)",
    responses=_NO_ENCONTRADO,
)
async def carga_de_partes(
    obra_id: UUID, caso_uso: ConsultarCargaDePartesDep
) -> CargaDePartesRespuesta:
    """Importe cargado entre presupuestado, por etapa. Una carga incompleta avisa, nunca
    bloquea (D-30): se puede mandar a programar con lo que llegó."""
    return CargaDePartesRespuesta(**await caso_uso.ejecutar(obra_id))


@router.post(
    "/actividades/{actividad_id}/modificacion",
    response_model=ModificacionRespuesta,
    summary="Un cambio o un adicional sobre un concepto del prototipo (antes de asignar)",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.COSTOS)), Idempotencia],
    responses={
        **_NO_ENCONTRADO,
        409: {"description": "La parte ya está asignada: cambiarla es control de cambio."},
        422: {"description": "Delta cero, adicional que resta, o cantidad que quedaría negativa."},
    },
)
async def modificar_actividad(
    actividad_id: UUID,
    peticion: ModificacionPeticion,
    ctx: ContextoActual,
    caso_uso: ModificarActividadDep,
) -> ModificacionRespuesta:
    """Escenario 3 · prototipo modificado (D-573/D-574). Se dice cuánto cambia: un cambio puede
    restar, un adicional solo suma. Si la parte ya estaba validada vuelve a cuantificarse."""
    return ModificacionRespuesta(
        **await caso_uso.ejecutar(
            ComandoModificarActividad(
                actividad_id=actividad_id,
                tipo=TipoDeModificacion(peticion.tipo),
                delta=peticion.delta,
                usuario_id=ctx.usuario_id,
                rol=Rol(ctx.rol),
                nota=peticion.nota,
            )
        )
    )


@router.post(
    "/obras/{obra_id}/modificaciones/nueva",
    response_model=ActividadNuevaRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Lo que cambia nace nuevo: un highlight, un concepto fuera de catálogo o uno agregado",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.COSTOS)), Idempotencia],
    responses={
        **_NO_ENCONTRADO,
        409: {"description": "La parte ya está asignada: agregarle algo es control de cambio."},
        422: {"description": "Sin descripción o con cantidad que no suma."},
    },
)
async def agregar_actividad_nueva(
    obra_id: UUID,
    peticion: ActividadNuevaPeticion,
    ctx: ContextoActual,
    caso_uso: AgregarActividadNuevaDep,
) -> ActividadNuevaRespuesta:
    return ActividadNuevaRespuesta(
        **await caso_uso.ejecutar(
            ComandoAgregarActividadNueva(
                obra_id=obra_id,
                tipo=TipoDeModificacion(peticion.tipo),
                descripcion=peticion.descripcion,
                cantidad=peticion.cantidad,
                precio_unitario=peticion.precio_unitario,
                usuario_id=ctx.usuario_id,
                rol=Rol(ctx.rol),
                concepto_id=peticion.concepto_id,
                etapa_id=peticion.etapa_id,
                nivel_id=peticion.nivel_id,
                nota=peticion.nota,
            )
        )
    )


class ConceptoNuevoPeticion(BaseModel):
    clave: str = Field(min_length=1, max_length=60)
    descripcion: str = Field(min_length=1)
    unidad_id: UUID = Field(description="Su unidad decide el tipo de medición: m², m o pza.")
    precio_unitario: Decimal = Field(default=Decimal(0), ge=0)
    etapa_id: UUID | None = Field(default=None, description="La etapa donde nace; suelto si falta.")
    nivel_id: UUID | None = None
    familia_id: UUID | None = None


class ConceptoNuevoRespuesta(BaseModel):
    concepto_id: UUID
    actividad_id: UUID
    clave: str
    parte: str


@router.post(
    "/obras/{obra_id}/conceptos-nuevos",
    response_model=ConceptoNuevoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Un concepto que no estaba en el catálogo: se da de alta y entra a la obra sin cantidad",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.COSTOS)), Idempotencia],
    responses={
        **_NO_ENCONTRADO,
        409: {"description": "La parte ya está asignada: agregarle algo es control de cambio."},
        422: {"description": "Clave repetida, sin descripción o precio negativo."},
    },
)
async def crear_concepto_en_la_obra(
    obra_id: UUID, peticion: ConceptoNuevoPeticion, caso_uso: CrearConceptoEnObraDep
) -> ConceptoNuevoRespuesta:
    """Desde el cuantificador: nace adicional y sin cantidad, que llega midiendo."""
    return ConceptoNuevoRespuesta(
        **await caso_uso.ejecutar(
            ComandoCrearConceptoEnObra(
                obra_id=obra_id,
                clave=peticion.clave,
                descripcion=peticion.descripcion,
                unidad_id=peticion.unidad_id,
                precio_unitario=peticion.precio_unitario,
                etapa_id=peticion.etapa_id,
                nivel_id=peticion.nivel_id,
                familia_id=peticion.familia_id,
            )
        )
    )


@router.get(
    "/obras/{obra_id}/modificaciones",
    response_model=list[RegistroDeModificacionRespuesta],
    summary="Los cambios y adicionales de la obra, lo más reciente primero",
    responses=_NO_ENCONTRADO,
)
async def modificaciones_de_la_obra(
    obra_id: UUID, caso_uso: ConsultarModificacionesDep
) -> list[RegistroDeModificacionRespuesta]:
    """Todos los roles, cada uno con su alcance. Solo se agrega."""
    return [RegistroDeModificacionRespuesta(**f) for f in await caso_uso.ejecutar(obra_id)]


@router.get(
    "/catalogos-base",
    response_model=list[CatalogoBaseRespuesta],
    summary="Los catálogos base de cuantificación: de 1 planta y de 2",
)
async def catalogos_base(caso_uso: ConsultarCatalogosBaseDep) -> list[CatalogoBaseRespuesta]:
    return [CatalogoBaseRespuesta(**f) for f in await caso_uso.ejecutar()]


@router.post(
    "/obras/desde-catalogo-base",
    response_model=ObraNuevaRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una obra «Nueva» desde el cuantificador, con su catálogo base",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA)), Idempotencia],
    responses={
        **_NO_ENCONTRADO,
        422: {"description": "Plantas inválidas, clave inválida o sin prototipo de dónde formar el catálogo."},
    },
)
async def crear_obra_desde_catalogo_base(
    peticion: ObraNuevaPeticion, caso_uso: CrearObraDesdeCatalogoBaseDep
) -> ObraNuevaRespuesta:
    """Escenario «Nuevo» (D-571): una obra cuyo proyecto es diferente de todos los prototipos.
    Se crea la obra y se forma su catálogo con la estructura y los conceptos del prototipo de 1 o
    de 2 plantas, **sin cantidades**: llegan midiendo, y lo medido es el presupuesto."""
    return ObraNuevaRespuesta(
        **await caso_uso.ejecutar(
            ComandoCrearObraDesdeCatalogoBase(
                cluster_id=peticion.cluster_id,
                clave=peticion.clave,
                plantas=peticion.plantas,
                residente_id=peticion.residente_id,
            )
        )
    )


@router.post(
    "/obras/desde-cero",
    response_model=ObraDesdeCeroRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una obra «desde cero»: el paramétrico primero y luego se mide",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA)), Idempotencia],
    responses={**_NO_ENCONTRADO, 422: {"description": "Plantas o clave inválidas."}},
)
async def crear_obra_desde_cero(
    peticion: ObraDesdeCeroPeticion, caso_uso: CrearObraDesdeCeroDep
) -> ObraDesdeCeroRespuesta:
    """Escenario 4 (D-578): sin obra anterior de dónde copiar. Nace con un prototipo de un solo
    uso vacío y su presupuesto; los ensambles (uno por tipo de espacio, D-579) componen la
    estructura con cantidades estimadas, y después se mide por partes."""
    return ObraDesdeCeroRespuesta(
        **await caso_uso.ejecutar(
            ComandoCrearObraDesdeCero(
                cluster_id=peticion.cluster_id,
                clave=peticion.clave,
                plantas=peticion.plantas,
                residente_id=peticion.residente_id,
            )
        )
    )


@router.get(
    "/obras/{obra_id}/partes/valuacion",
    response_model=ValuacionDeObraRespuesta,
    summary="Cómo se valúa cada parte: por PU, por ensamble o mixto (en porcentaje)",
    responses=_NO_ENCONTRADO,
)
async def valuacion_de_partes(
    obra_id: UUID, caso_uso: ConsultarValuacionDep
) -> ValuacionDeObraRespuesta:
    """*Mixto no se guarda, se reporta en porcentaje* (§8.1). Y lo medido vuelve al paramétrico:
    cuánto se alejó de lo estimado lo que una medición ya sustituyó (propone, no aplica)."""
    return ValuacionDeObraRespuesta(**await caso_uso.ejecutar(obra_id))


@router.post(
    "/obras/{obra_id}/partes/rediseno",
    response_model=RedisenoRespuesta,
    summary="Rediseñar una parte a paramétrico o mixto: se valúa por ensamble",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.COSTOS)), Idempotencia],
    responses={
        **_NO_ENCONTRADO,
        409: {"description": "La parte ya está asignada: cambiarla es control de cambio."},
        422: {"description": "Factor inválido."},
    },
)
async def redisenar_parte(
    obra_id: UUID,
    peticion: RedisenoPeticion,
    ctx: ContextoActual,
    caso_uso: RedisenarParteDep,
) -> RedisenoRespuesta:
    """En presupuesto se autoriza, o se rediseña (D-571). Los renglones de la parte cuyo concepto
    está en el ensamble pasan a la cantidad estimada; el resto se queda por PU: queda mixto y se
    reporta en porcentaje. Sin `aplicar` solo propone."""
    return RedisenoRespuesta(
        **await caso_uso.ejecutar(
            ComandoRedisenarParte(
                obra_id=obra_id,
                clave=peticion.clave,
                ensamble_id=peticion.ensamble_id,
                factor=peticion.factor,
                usuario_id=ctx.usuario_id,
                rol=Rol(ctx.rol),
                aplicar=peticion.aplicar,
            )
        )
    )


@router.post(
    "/obras/{obra_id}/cotizaciones",
    response_model=CotizacionRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Cotizar al cliente lo que la obra modificó",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA)), Idempotencia],
    responses={**_NO_ENCONTRADO, 422: {"description": "Nada modificado que cotizar, o falta un dato del modo."}},
)
async def cotizar_lo_modificado(
    obra_id: UUID,
    peticion: CotizacionPeticion,
    ctx: ContextoActual,
    caso_uso: CotizarLoModificadoDep,
) -> CotizacionRespuesta:
    """Antes de un control de cambio se hace un presupuesto al cliente (D-531). Control de obra
    cotiza; el factor y el precio por m² son parámetros editables."""
    return CotizacionRespuesta(
        **await caso_uso.ejecutar(
            ComandoCotizar(
                obra_id=obra_id,
                metodo=MetodoDePrecio(peticion.metodo_precio),
                usuario_id=ctx.usuario_id,
                m2_ampliacion=peticion.m2_ampliacion,
                precio_m2=peticion.precio_m2,
                nota=peticion.nota,
            )
        )
    )


@router.get(
    "/obras/{obra_id}/cotizaciones",
    response_model=list[CotizacionRespuesta],
    summary="Las cotizaciones al cliente de la obra, la más reciente primero",
    responses=_NO_ENCONTRADO,
)
async def cotizaciones_de_la_obra(
    obra_id: UUID, caso_uso: ConsultarCotizacionesDep
) -> list[CotizacionRespuesta]:
    return [CotizacionRespuesta(**f) for f in await caso_uso.ejecutar(obra_id)]


@router.post(
    "/cotizaciones/{cotizacion_id}/respuesta",
    response_model=CotizacionRespuesta,
    summary="Registrar la respuesta del cliente a una cotización",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA)), Idempotencia],
    responses={
        **_NO_ENCONTRADO,
        409: {"description": "El cliente ya respondió esta cotización."},
    },
)
async def responder_cotizacion(
    cotizacion_id: UUID,
    peticion: RespuestaDelClientePeticion,
    ctx: ContextoActual,
    caso_uso: ResponderCotizacionDep,
) -> CotizacionRespuesta:
    """Aceptada o rechazada, una sola vez. Quien debería registrarla —Proyectos y atención al
    cliente— no es todavía un rol: hoy lo registra Control de obra."""
    return CotizacionRespuesta(
        **await caso_uso.ejecutar(
            cotizacion_id, aceptada=peticion.aceptada, usuario_id=ctx.usuario_id, nota=peticion.nota
        )
    )


@router.get(
    "/obras/{obra_id}/arranque",
    response_model=ArranqueRespuesta,
    summary="Lo que la junta de arranque tiene a la vista: ¿todo validado?",
    responses=_NO_ENCONTRADO,
)
async def arranque_de_la_obra(obra_id: UUID, caso_uso: ConsultarArranqueDep) -> ArranqueRespuesta:
    """El requisito «todo validado» de la junta (D-574): qué partes aún no están autorizadas.
    Avisa; lo que impide es asignar, con el candado (por obra)."""
    return ArranqueRespuesta(**await caso_uso.ejecutar(obra_id))


@router.put(
    "/obras/{obra_id}/candado-asignar",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="El candado de asignar de la obra",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA))],
    responses=_NO_ENCONTRADO,
)
async def fijar_candado_de_asignar(
    obra_id: UUID, peticion: CandadoPeticion, caso_uso: FijarCandadoDeAsignarDep
) -> None:
    """Lo edita Control de obra, por obra (D-574)."""
    await caso_uso.ejecutar(obra_id, peticion.activo)


@router.get(
    "/configuracion/desfase-de-partes",
    response_model=DesfaseDePartesRespuesta,
    summary="Los umbrales de la alerta de desfase del presupuesto (globales)",
)
async def desfase_de_partes(caso_uso: ConsultarDesfaseDePartesDep) -> DesfaseDePartesRespuesta:
    return DesfaseDePartesRespuesta(**await caso_uso.ejecutar())


@router.put(
    "/configuracion/desfase-de-partes",
    response_model=DesfaseDePartesRespuesta,
    summary="Editar los umbrales de la alerta de desfase (afectan a cada obra)",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE))],
    responses={422: {"description": "El aviso va antes que la alerta importante."}},
)
async def fijar_desfase_de_partes(
    peticion: DesfaseDePartesPeticion, caso_uso: FijarDesfaseDePartesDep
) -> DesfaseDePartesRespuesta:
    """Son globales y afectan a cada obra (D-577): 2 semanas de aviso y 1 de alerta importante
    por defecto."""
    return DesfaseDePartesRespuesta(
        **await caso_uso.ejecutar(peticion.aviso_dias, peticion.importante_dias)
    )
