"""Endpoints del cuantificador: `plano → medida → cantidad` (cerebro
MODELO.md §1b, migración 0057).

Controladores delgados: validan el DTO, delegan en el caso de uso
(`application.casos_uso.cuantificar`) y mapean el resultado. Cero lógica
de negocio aquí — las invariantes del enlace viven en
`domain.cuantificacion.reglas` y el gobierno del camino `prototipo_nodo`
en el caso de uso (ver su docstring).

**RBAC — quién hace qué (cerebro MODELO.md §1b, "Quién puede trazar"):**

    trazar         -> Residente, Supervisor, Control de obra, Super
                       intendente ("Costos·Control·Residente·Supervisor,
                       no Cotizador" en el vocabulario de cerebro; en
                       ObraCtrl no existen los roles "Costos" ni
                       "Cotizador" por separado — de los cuatro roles que
                       sí existen (`domain.shared.diccionario.Rol`),
                       ninguno se excluye: los cuatro trazan igual).
    reemplazar un
    enlace         -> mismos cuatro roles que trazan (acción manual sobre
                       un enlace ya existente, misma familia de permiso).
    anotar_plano   -> SOLO Residente y Supervisor (cerebro, "FUNCION_
                       ATOMICA gana una decimoquinta: anotar_plano ->
                       Residente, Supervisor" — Control y Super
                       intendente NO anotan, a diferencia de trazar).
    alta de plano  -> no está en el vocabulario de cerebro (PLANO no
                       existe ahí, ver migración 0057): se decide aquí,
                       sin especificación previa, que son los mismos
                       cuatro roles que trazan — subir un plano es
                       prerrequisito de trazar, no una acción distinta.

Ningún endpoint valida aquí que un enlace contra `prototipo_nodo` exija
Control/Super intendente — eso lo hace
`application.casos_uso.cuantificar._exigir_gobierno` puertas adentro
(mismo criterio que `expediente.py`: la guarda HTTP de rol general + la
regla de dominio más fina, no un solo lugar).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, model_validator

from obractrl.adapters.api.casos_uso import (
    AprobarTrazoDep,
    CalibrarEscalaDePlanoDep,
    ConsultarCuantificacionDep,
    ReemplazarEnlaceDep,
    RegistrarNotaPlanoDep,
    RegistrarPlanoDep,
    RegistrarTrazoConEnlacesDep,
)
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.application.casos_uso.cuantificar import (
    ComandoAprobarTrazo,
    ComandoCalibrarEscala,
    ComandoReemplazarEnlace,
    ComandoRegistrarNotaPlano,
    ComandoRegistrarTrazo,
    IntencionEnlace,
    NodoCuantificado,
    NuevoEnlace,
    PlanoNoEncontrado,
    ResultadoDeRecalculo,
)
from obractrl.domain.shared.diccionario import FuenteTrazo, MedidaCuantificacion, Rol
from obractrl.infrastructure.storage.r2 import firmar_descarga

router = APIRouter(tags=["cuantificacion"])

ROLES_QUE_TRAZAN = (Rol.RESIDENTE, Rol.SUPERVISOR, Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE)
"""Los cuatro roles existentes en ObraCtrl (ver docstring del módulo): el
vocabulario de cerebro excluye a "Cotizador", que no tiene equivalente
aquí, así que ninguno de los cuatro queda fuera."""

ROLES_QUE_APRUEBAN = (Rol.CONTROL_OBRA,)
"""`aprobar_trazo` -> Control de obra (cerebro MODELO.md §1b, «Quién puede
trazar»). Ni Residente ni Supervisor aprueban lo que trazan; Super intendente
tampoco: la función es solo de Control."""

ROLES_QUE_ANOTAN = (Rol.RESIDENTE, Rol.SUPERVISOR)
"""Cerebro es explícito y distinto de `ROLES_QUE_TRAZAN`: anotar el plano
es solo de Residente y Supervisor."""


class PlanoPeticion(BaseModel):
    """Alta de metadatos de un plano (§11.2-equivalente, migración 0057).
    El archivo ya está subido a R2 con `POST /evidencias/presigned`."""

    nombre: str = Field(min_length=1, description="Nombre legible del plano.")
    archivo_url: str = Field(
        min_length=1,
        description=(
            "Clave del objeto ya subido a R2 con `POST /evidencias/presigned` "
            "(§12.2). El archivo no viaja por la API."
        ),
    )
    version: int = Field(default=1, gt=0, description="Versión del plano (default 1).")
    capas: list[str] | None = Field(
        default=None, description="Capas del archivo CAD/BIM de origen, informativo."
    )


class PlanoRespuesta(BaseModel):
    id: UUID
    obra_id: UUID
    nombre: str
    archivo_url: str
    version: int
    capas: list[str] | None = None


class IntencionEnlacePeticion(BaseModel):
    """Un enlace querido, dentro del mismo alta de trazo (MODELO.md §1b,
    "un trazo, varios enlaces"). Exactamente uno de `actividad_id`/
    `prototipo_nodo_id` (ver docstring de `ck_enlace_cuantificacion_nodo`,
    migración 0057)."""

    medida: MedidaCuantificacion
    factor: Decimal = Field(gt=0)
    actividad_id: UUID | None = None
    prototipo_nodo_id: UUID | None = None

    @model_validator(mode="after")
    def _exactamente_un_nodo(self) -> IntencionEnlacePeticion:
        tiene_actividad = self.actividad_id is not None
        tiene_prototipo = self.prototipo_nodo_id is not None
        if tiene_actividad == tiene_prototipo:
            raise ValueError(
                "Un enlace apunta a actividad_id o a prototipo_nodo_id, "
                "nunca a los dos ni a ninguno."
            )
        return self


class TrazoPeticion(BaseModel):
    """Alta de un trazo con sus enlaces (MODELO.md §1b, Decisión 3 de 3:
    WKT para capturar un trazo nuevo mientras se dibuja)."""

    version_plano: int = Field(gt=0)
    capa: str | None = None
    fuente: FuenteTrazo
    geometria_wkt: str = Field(
        min_length=1,
        description=(
            "WKT del trazo (p. ej. `POLYGON((...))`, `LINESTRING(...)`, "
            "`POINT(...)`). Coordenadas de plano, no geográficas (SRID 0)."
        ),
    )
    enlaces: list[IntencionEnlacePeticion] = Field(default_factory=list)


class ResultadoRecalculoRespuesta(BaseModel):
    cantidad_total: Decimal
    desviacion_id: UUID | None = None
    prototipo_nodo_actualizado: UUID | None = None

    @classmethod
    def desde_dominio(cls, r: ResultadoDeRecalculo) -> ResultadoRecalculoRespuesta:
        return cls(
            cantidad_total=r.cantidad_total,
            desviacion_id=r.desviacion_id,
            prototipo_nodo_actualizado=r.prototipo_nodo_actualizado,
        )


class TrazoRespuesta(BaseModel):
    trazo_id: UUID
    enlace_ids: list[UUID]
    recalculos: list[ResultadoRecalculoRespuesta]


class NuevoEnlacePeticion(BaseModel):
    """El reemplazo, cuando se crea en la misma llamada — hereda el nodo
    del enlace que reemplaza (ver `NuevoEnlace` en el caso de uso)."""

    trazo_id: UUID
    medida: MedidaCuantificacion
    factor: Decimal = Field(gt=0)


class ReemplazarEnlacePeticion(BaseModel):
    nuevo: NuevoEnlacePeticion | None = None


class NotaPlanoPeticion(BaseModel):
    version_plano: int = Field(gt=0)
    ubicacion_wkt: str = Field(min_length=1, description="WKT de un punto, SRID 0.")
    texto: str = Field(min_length=1)
    actividad_id: UUID | None = None


class NotaPlanoRespuesta(BaseModel):
    id: UUID


@router.post(
    "/obras/{obra_id}/planos",
    response_model=PlanoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Alta de un plano ejecutivo",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
)
async def registrar_plano(
    obra_id: UUID,
    peticion: PlanoPeticion,
    ctx: ContextoActual,
    caso_uso: RegistrarPlanoDep,
) -> PlanoRespuesta:
    """Metadatos del plano; el binario ya está en R2 (§12.2). Subir un
    plano es prerrequisito de trazar, así que comparte el mismo gobierno
    (ver docstring del módulo)."""
    plano_id = await caso_uso.ejecutar(
        obra_id=obra_id,
        nombre=peticion.nombre,
        archivo_url=peticion.archivo_url,
        version=peticion.version,
        capas=peticion.capas,
        subido_por=ctx.usuario_id,
    )
    return PlanoRespuesta(
        id=plano_id,
        obra_id=obra_id,
        nombre=peticion.nombre,
        archivo_url=peticion.archivo_url,
        version=peticion.version,
        capas=peticion.capas,
    )


@router.post(
    "/planos/{plano_id}/trazos",
    response_model=TrazoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un trazo con sus enlaces de cuantificación",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={
        403: {
            "description": (
                "Un enlace apunta a un prototipo_nodo (camino "
                "'diseño_nuevo') y el rol no es Control de obra ni Super "
                "intendente."
            )
        },
        422: {"description": "Factor no positivo, medida/nodo inconsistentes."},
    },
)
async def registrar_trazo(
    plano_id: UUID,
    peticion: TrazoPeticion,
    ctx: ContextoActual,
    caso_uso: RegistrarTrazoConEnlacesDep,
) -> TrazoRespuesta:
    """Un trazo, varios enlaces (MODELO.md §1b). Por cada nodo tocado,
    recalcula la cantidad vigente y aplica su consecuencia: compara contra
    `actividad.cant_base` (candidata de `Desviacion`) o sobreescribe
    `prototipo_nodo.cantidad` (camino 'diseño_nuevo') — nunca las dos."""
    resultado = await caso_uso.ejecutar(
        ComandoRegistrarTrazo(
            plano_id=plano_id,
            version_plano=peticion.version_plano,
            capa=peticion.capa,
            fuente=peticion.fuente.value,
            geometria_wkt=peticion.geometria_wkt,
            autor_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
            enlaces=tuple(
                IntencionEnlace(
                    medida=e.medida,
                    factor=e.factor,
                    actividad_id=e.actividad_id,
                    prototipo_nodo_id=e.prototipo_nodo_id,
                )
                for e in peticion.enlaces
            ),
        ),
        detectada_en=datetime.now(UTC),
    )
    return TrazoRespuesta(
        trazo_id=resultado.trazo_id,
        enlace_ids=list(resultado.enlace_ids),
        recalculos=[
            ResultadoRecalculoRespuesta.desde_dominio(r) for r in resultado.recalculos
        ],
    )


class EscalaPeticion(BaseModel):
    """Calibrar la escala de un plano (migración 0069): dos puntos de una distancia
    conocida del plano y los metros que son."""

    punto_a: tuple[float, float] = Field(description="Coordenada de plano `[x, y]`.")
    punto_b: tuple[float, float] = Field(description="Coordenada de plano `[x, y]`.")
    distancia_m: Decimal = Field(
        gt=0, description="Los metros reales entre `punto_a` y `punto_b`."
    )


class EscalaRespuesta(BaseModel):
    escala_m_por_unidad: Decimal = Field(description="Metros por unidad de plano.")
    recalculos: list[ResultadoRecalculoRespuesta] = Field(
        description=(
            "Una por cada nodo que alimentan los trazos del plano: su cantidad "
            "cambió con la escala."
        )
    )


@router.put(
    "/planos/{plano_id}/escala",
    response_model=EscalaRespuesta,
    summary="Calibrar la escala de un plano con dos puntos y una distancia real",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={
        403: {
            "description": (
                "El plano alimenta cantidades de un prototipo_nodo y el rol no es "
                "Control de obra ni Super intendente."
            )
        },
        404: {"description": "El plano no existe o está fuera de tu alcance."},
        422: {"description": "Puntos iguales, distancia no positiva o escala implausible."},
    },
)
async def calibrar_escala(
    plano_id: UUID,
    peticion: EscalaPeticion,
    ctx: ContextoActual,
    caso_uso: CalibrarEscalaDePlanoDep,
) -> EscalaRespuesta:
    """Sin escala, lo que se mide está en unidades de plano —píxeles del visor— y
    no se puede comparar con el presupuesto. Calibrar corrige todos los trazos del
    plano de golpe (la medida se lee ya escalada) y recalcula lo que alimentan.
    Se puede repetir: la última calibración manda."""
    resultado = await caso_uso.ejecutar(
        ComandoCalibrarEscala(
            plano_id=plano_id,
            punto_a=peticion.punto_a,
            punto_b=peticion.punto_b,
            distancia_m=peticion.distancia_m,
            usuario_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
        ),
        detectada_en=datetime.now(UTC),
    )
    return EscalaRespuesta(
        escala_m_por_unidad=resultado.escala_m_por_unidad,
        recalculos=[
            ResultadoRecalculoRespuesta.desde_dominio(r) for r in resultado.recalculos
        ],
    )


@router.post(
    "/enlaces-cuantificacion/{enlace_id}/reemplazar",
    response_model=ResultadoRecalculoRespuesta,
    summary="Reemplazar un enlace de cuantificación (acción manual)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={
        403: {
            "description": (
                "El enlace apunta a un prototipo_nodo y el rol no es "
                "Control de obra ni Super intendente."
            )
        },
        404: {"description": "El enlace no existe o está fuera de tu alcance."},
    },
)
async def reemplazar_enlace(
    enlace_id: UUID,
    peticion: ReemplazarEnlacePeticion,
    ctx: ContextoActual,
    caso_uso: ReemplazarEnlaceDep,
) -> ResultadoRecalculoRespuesta:
    """Marca `vigente=false` y, si se manda `nuevo`, crea el reemplazo
    vigente en la misma llamada — siempre una acción explícita (MODELO.md
    §1b: nunca un emparejamiento automático por cercanía espacial)."""
    resultado = await caso_uso.ejecutar(
        ComandoReemplazarEnlace(
            enlace_id=enlace_id,
            rol=Rol(ctx.rol),
            nuevo=(
                NuevoEnlace(
                    trazo_id=peticion.nuevo.trazo_id,
                    medida=peticion.nuevo.medida,
                    factor=peticion.nuevo.factor,
                )
                if peticion.nuevo is not None
                else None
            ),
        ),
        detectada_en=datetime.now(UTC),
    )
    return ResultadoRecalculoRespuesta.desde_dominio(resultado)


class TrazoAprobadoRespuesta(BaseModel):
    trazo_id: UUID
    aprobado_por: UUID
    aprobado_en: datetime
    ya_estaba_aprobado: bool = Field(
        description=(
            "`true` si el trazo ya estaba aprobado: no se pisa quién ni cuándo "
            "aprobó primero."
        )
    )


@router.post(
    "/trazos/{trazo_id}/aprobar",
    response_model=TrazoAprobadoRespuesta,
    summary="Aprobar un trazo (marca de revisión, no cambia la cantidad)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_APRUEBAN))],
    responses={
        403: {"description": "Solo Control de obra aprueba un trazo (§1b)."},
        404: {"description": "El trazo no existe o está fuera de tu alcance."},
    },
)
async def aprobar_trazo(
    trazo_id: UUID, ctx: ContextoActual, caso_uso: AprobarTrazoDep
) -> TrazoAprobadoRespuesta:
    """Idempotente. **No es una compuerta:** un trazo cuenta en la cantidad
    desde que se guarda, aprobado o no — el cerebro no define lo contrario
    (migración 0065). Aprobar solo deja constancia de quién lo revisó y cuándo."""
    resultado = await caso_uso.ejecutar(
        ComandoAprobarTrazo(trazo_id=trazo_id, aprobador_id=ctx.usuario_id)
    )
    return TrazoAprobadoRespuesta(
        trazo_id=resultado.trazo_id,
        aprobado_por=resultado.aprobado_por,
        aprobado_en=resultado.aprobado_en,
        ya_estaba_aprobado=resultado.ya_estaba_aprobado,
    )


@router.post(
    "/planos/{plano_id}/notas",
    response_model=NotaPlanoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Anotar el plano (nunca produce cantidad)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_ANOTAN))],
    responses={
        403: {"description": "Solo Residente y Supervisor anotan el plano (§1b)."},
    },
)
async def registrar_nota_plano(
    plano_id: UUID,
    peticion: NotaPlanoPeticion,
    ctx: ContextoActual,
    caso_uso: RegistrarNotaPlanoDep,
) -> NotaPlanoRespuesta:
    """Residente y Supervisor, solamente (cerebro MODELO.md §1b: distinto
    de los cuatro roles que trazan)."""
    resultado = await caso_uso.ejecutar(
        ComandoRegistrarNotaPlano(
            plano_id=plano_id,
            version_plano=peticion.version_plano,
            ubicacion_wkt=peticion.ubicacion_wkt,
            autor_id=ctx.usuario_id,
            texto=peticion.texto,
            actividad_id=peticion.actividad_id,
        )
    )
    return NotaPlanoRespuesta(id=resultado.nota_id)


# --- Lectura -------------------------------------------------------------
#
# Abierta a quien tiene acceso a la obra (MODELO.md §1b: "visualizar el estado
# de cuantificación no es una función atómica ... es lectura"): ninguna de
# estas rutas lleva `exigir_rol`; el alcance lo impone RLS.


class PlanoDetalleRespuesta(BaseModel):
    id: UUID
    obra_id: UUID
    nombre: str
    archivo_url: str
    version: int
    capas: list[str] | None
    subido_por: UUID | None
    created_at: datetime
    n_trazos: int
    n_trazos_por_revisar: int = Field(
        description=(
            "Trazos hechos sobre una versión anterior del plano: quedan marcados "
            "para revisión y no se recalculan solos (MODELO.md §1b)."
        )
    )
    escala_m_por_unidad: Decimal | None = Field(
        default=None,
        description=(
            "Metros por unidad de plano; `null` = sin calibrar (se asume 1 unidad = "
            "1 m y las cantidades están en unidades de plano). Migración 0069."
        ),
    )
    escala_referencia: dict[str, Any] | None = Field(
        default=None,
        description="Los dos puntos y la distancia real con que se calibró.",
    )
    escala_calibrada_en: datetime | None = None


class EnlaceDeTrazoRespuesta(BaseModel):
    enlace_id: UUID
    tipo_nodo: str
    nodo_id: UUID = Field(
        description="`actividad_id` o `prototipo_nodo_id`, según `tipo_nodo`."
    )
    medida: str
    factor: Decimal
    vigente: bool
    medida_valor: Decimal = Field(
        description="`ST_Area`/`ST_Perimeter`/`ST_Length`, o 1 si es conteo."
    )
    cantidad: Decimal = Field(description="`medida_valor × factor`.")


class TrazoPropiedades(BaseModel):
    trazo_id: UUID
    version_plano: int
    capa: str | None
    fuente: str
    autor_id: UUID | None
    por_revisar: bool
    aprobado_por: UUID | None = Field(
        description="Control de obra que lo aprobó, o `null` si aún no está aprobado."
    )
    aprobado_en: datetime | None
    nodo_ids: list[UUID] = Field(
        description=(
            "Nodos a los que el trazo alimenta con un enlace **vigente**: lo que "
            "el visor necesita para resolver el clic (MODELO.md §1b). Un trazo "
            "puede alimentar varios (el área da el piso, el perímetro el zoclo)."
        )
    )
    enlaces: list[EnlaceDeTrazoRespuesta]


class TrazoFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: UUID
    geometry: dict[str, Any] = Field(
        description=(
            "Geometría GeoJSON en **coordenadas de plano** (SRID 0), no lon/lat: "
            "es una desviación deliberada de RFC 7946 (MODELO.md §1b)."
        )
    )
    properties: TrazoPropiedades


class TrazosDePlanoRespuesta(BaseModel):
    """`FeatureCollection` de GeoJSON con los trazos de un plano."""

    type: Literal["FeatureCollection"] = "FeatureCollection"
    plano_id: UUID
    version_plano: int
    escala_m_por_unidad: Decimal | None = Field(
        default=None, description="Metros por unidad de plano; `null` = sin calibrar."
    )
    features: list[TrazoFeature]


class NodoCuantificadoRespuesta(BaseModel):
    tipo_nodo: str
    nodo_id: UUID
    descripcion: str | None
    cant_base: Decimal | None
    cantidad_medida: Decimal = Field(
        description="Suma de `medida × factor` de los enlaces **vigentes**."
    )
    diferencia: Decimal | None = Field(
        description=(
            "`cantidad_medida − cant_base`. Informa, no corrige: sobre una "
            "actividad la medida se compara y nunca reemplaza a `cant_base`."
        )
    )
    enlaces_vigentes: int
    enlaces_reemplazados: int
    trazos_por_revisar: int

    @classmethod
    def desde_dominio(cls, nodo: NodoCuantificado) -> NodoCuantificadoRespuesta:
        return cls(
            tipo_nodo=nodo.tipo_nodo,
            nodo_id=nodo.nodo_id,
            descripcion=nodo.descripcion,
            cant_base=nodo.cant_base,
            cantidad_medida=nodo.cantidad_medida,
            diferencia=nodo.diferencia,
            enlaces_vigentes=nodo.enlaces_vigentes,
            enlaces_reemplazados=nodo.enlaces_reemplazados,
            trazos_por_revisar=nodo.trazos_por_revisar,
        )


@router.get(
    "/obras/{obra_id}/planos",
    response_model=list[PlanoDetalleRespuesta],
    summary="Planos de una obra",
    responses={404: {"description": "La obra no existe o está fuera de tu alcance."}},
)
async def listar_planos(
    obra_id: UUID, caso_uso: ConsultarCuantificacionDep
) -> list[PlanoDetalleRespuesta]:
    filas = await caso_uso.planos_de_obra(obra_id)
    return [PlanoDetalleRespuesta(**fila) for fila in filas]


@router.get(
    "/planos/{plano_id}/trazos",
    response_model=TrazosDePlanoRespuesta,
    summary="Trazos de un plano, como GeoJSON",
    responses={404: {"description": "El plano no existe o está fuera de tu alcance."}},
)
async def trazos_de_plano(
    plano_id: UUID, caso_uso: ConsultarCuantificacionDep
) -> TrazosDePlanoRespuesta:
    """`FeatureCollection` con un `Feature` por trazo (MODELO.md §1b, "Cómo viaja
    la geometría hacia el frontend"). Los enlaces reemplazados vienen también,
    con `vigente = false`: quedan como evidencia y no cuentan en `nodo_ids`."""
    plano, trazos = await caso_uso.trazos_de_plano(plano_id)

    features = []
    for trazo in trazos:
        enlaces = [
            EnlaceDeTrazoRespuesta(
                enlace_id=e["id"],
                tipo_nodo=str(e["tipo_nodo"]),
                nodo_id=e["actividad_id"] or e["prototipo_nodo_id"],
                medida=str(e["medida"]),
                factor=e["factor"],
                vigente=e["vigente"],
                medida_valor=Decimal(str(e["medida_valor"])),
                cantidad=Decimal(str(e["medida_valor"])) * Decimal(str(e["factor"])),
            )
            for e in trazo["enlaces"]
        ]
        features.append(
            TrazoFeature(
                id=trazo["id"],
                geometry=trazo["geometria"],
                properties=TrazoPropiedades(
                    trazo_id=trazo["id"],
                    version_plano=trazo["version_plano"],
                    capa=trazo["capa"],
                    fuente=str(trazo["fuente"]),
                    autor_id=trazo["autor_id"],
                    por_revisar=trazo["por_revisar"],
                    aprobado_por=trazo["aprobado_por"],
                    aprobado_en=trazo["aprobado_en"],
                    nodo_ids=list(dict.fromkeys(e.nodo_id for e in enlaces if e.vigente)),
                    enlaces=enlaces,
                ),
            )
        )
    return TrazosDePlanoRespuesta(
        plano_id=plano["id"],
        version_plano=plano["version"],
        escala_m_por_unidad=plano.get("escala_m_por_unidad"),
        features=features,
    )


class NotaPlanoDetalleRespuesta(BaseModel):
    id: UUID
    version_plano: int
    texto: str
    autor_id: UUID | None
    actividad_id: UUID | None = Field(
        description="Concepto sobre el que habla la nota; `null` si es solo un lugar del plano."
    )
    created_at: datetime
    por_revisar: bool = Field(
        description="Hecha sobre una versión anterior del plano: el lugar pudo haberse movido."
    )
    ubicacion: dict[str, Any] = Field(
        description="`Point` GeoJSON en **coordenadas de plano** (SRID 0), no lon/lat."
    )


@router.get(
    "/planos/{plano_id}/notas",
    response_model=list[NotaPlanoDetalleRespuesta],
    summary="Notas flotantes de un plano",
    responses={404: {"description": "El plano no existe o está fuera de tu alcance."}},
)
async def notas_de_plano(
    plano_id: UUID, caso_uso: ConsultarCuantificacionDep
) -> list[NotaPlanoDetalleRespuesta]:
    """Leerlas está abierto a quien ve la obra; anotar es de Residente y
    Supervisor (MODELO.md §1b). Una nota nunca produce cantidad."""
    filas = await caso_uso.notas_de_plano(plano_id)
    return [NotaPlanoDetalleRespuesta(**fila) for fila in filas]


@router.get(
    "/obras/{obra_id}/cuantificacion",
    response_model=list[NodoCuantificadoRespuesta],
    summary="Cómo va la cuantificación de la obra, nodo por nodo",
    responses={404: {"description": "La obra no existe o está fuera de tu alcance."}},
)
async def estado_de_cuantificacion(
    obra_id: UUID, caso_uso: ConsultarCuantificacionDep
) -> list[NodoCuantificadoRespuesta]:
    nodos = await caso_uso.estado_de_obra(obra_id)
    return [NodoCuantificadoRespuesta.desde_dominio(n) for n in nodos]


class ArchivoDePlanoRespuesta(BaseModel):
    url: str = Field(description="URL firmada para leer el archivo; caduca.")
    expira_en_segundos: int
    expira_en: datetime


@router.get(
    "/planos/{plano_id}/archivo",
    response_model=ArchivoDePlanoRespuesta,
    summary="URL firmada para ver el archivo de un plano",
    responses={
        404: {
            "description": (
                "El plano no existe, está fuera de tu alcance, o su archivo no "
                "cuelga del almacenamiento de tu organización."
            )
        },
        503: {"description": "El almacenamiento no está configurado en este entorno."},
    },
)
async def archivo_de_plano(
    plano_id: UUID, ctx: ContextoActual, caso_uso: ConsultarCuantificacionDep
) -> ArchivoDePlanoRespuesta:
    """El visor pinta los trazos sobre el plano; el archivo vive en R2 y no
    pasa por la API (§12.2), así que se entrega una URL de lectura.

    `archivo_url` la escribió quien dio de alta el plano, no el servidor: sin
    la comprobación del prefijo, un usuario podría registrar una clave de otra
    organización y pedir que se la firmen. R2 no tiene RLS (§12.4); el prefijo
    por `org_id` es la frontera, y aquí se hace valer."""
    plano, _ = await caso_uso.trazos_de_plano(plano_id)
    clave = str(plano["archivo_url"])
    if not clave.startswith(f"{ctx.org_id}/"):
        raise PlanoNoEncontrado(
            f"El plano {plano_id} no tiene un archivo en el almacenamiento de tu organización."
        )
    firma = firmar_descarga(clave=clave)
    return ArchivoDePlanoRespuesta(
        url=firma.url,
        expira_en_segundos=firma.expira_en_segundos,
        expira_en=firma.expira_en,
    )
