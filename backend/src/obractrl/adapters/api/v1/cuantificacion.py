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
    AgregarHuecoDep,
    AprobarTrazoDep,
    CalibrarEscalaDePlanoDep,
    ConsultarCuantificacionDep,
    ConsultarMatricesDep,
    ConversionDelEnlaceDep,
    EliminarTrazoDep,
    FijarVistaDePlanoDep,
    GestionarVanosDep,
    QuitarHuecoDep,
    ReemplazarEnlaceDep,
    RegistrarNotaPlanoDep,
    RegistrarPlanoDep,
    RegistrarTrazoConEnlacesDep,
    TraerTrazoDep,
    TransformarTrazosDep,
)
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.application.casos_uso.cuantificar import (
    ComandoAgregarHueco,
    ComandoAgregarVano,
    ComandoAprobarTrazo,
    ComandoCalibrarEscala,
    ComandoEliminarTrazo,
    ComandoFijarVistaDePlano,
    ComandoReemplazarEnlace,
    ComandoRegistrarNotaPlano,
    ComandoRegistrarTrazo,
    ComandoTraerTrazo,
    ComandoTransformarTrazos,
    IntencionEnlace,
    NodoCuantificado,
    NuevoEnlace,
    PlanoNoEncontrado,
    ResultadoDeRecalculo,
)
from obractrl.domain.cuantificacion.muro import ParteDeAltura, altura_efectiva
from obractrl.domain.shared.diccionario import FuenteTrazo, MedidaCuantificacion, Rol
from obractrl.infrastructure.storage.r2 import firmar_descarga

router = APIRouter(tags=["cuantificacion"])

ROLES_QUE_TRAZAN = (
    Rol.RESIDENTE,
    Rol.SUPERVISOR,
    Rol.CONTROL_OBRA,
    Rol.SUPER_INTENDENTE,
    Rol.COSTOS,  # cuantifica: es su trabajo (D-575)
)
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
    matriz_concepto_id: UUID | None = Field(
        default=None,
        description=(
            "Si lo que se mide es una matriz interna de la actividad (nervaduras, trabes…) y no la "
            "actividad entera (D-583). Solo con `actividad_id`."
        ),
    )

    @model_validator(mode="after")
    def _exactamente_un_nodo(self) -> IntencionEnlacePeticion:
        tiene_actividad = self.actividad_id is not None
        tiene_prototipo = self.prototipo_nodo_id is not None
        if tiene_actividad == tiene_prototipo:
            raise ValueError(
                "Un enlace apunta a actividad_id o a prototipo_nodo_id, "
                "nunca a los dos ni a ninguno."
            )
        if self.matriz_concepto_id is not None and not tiene_actividad:
            raise ValueError("Una matriz interna se mide dentro de una actividad: falta actividad_id.")
        return self


class FormaDeTrazo(BaseModel):
    """Con qué plantilla y a qué tamaño se estampó un punto con forma (un castillo, una columna)."""

    tipo: Literal["circulo", "cuadrado", "rectangulo", "triangulo", "hexagono", "libre"]
    ancho_m: Decimal = Field(gt=0, le=1000)
    alto_m: Decimal = Field(gt=0, le=1000)
    rotacion_grados: Decimal = Field(default=Decimal(0), ge=-360, le=360)
    nombre: str | None = Field(
        default=None, max_length=80, description="El elemento que representa: castillo, columna..."
    )
    vertices: list[tuple[float, float]] | None = Field(
        default=None,
        max_length=200,
        description="Solo en `libre`: el contorno normalizado a una caja de 1 × 1 centrada en el origen.",
    )


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
    grosor_m: Decimal | None = Field(
        default=None,
        gt=0,
        le=100,
        description=(
            "Grosor en metros de una **línea** (un muro de 0.15 o de 0.30 m). Con grosor, el "
            "área de la línea es su largo × grosor. Va junto con `alineacion`."
        ),
    )
    alineacion: Literal["centro", "izquierda", "derecha"] | None = Field(
        default=None,
        description=(
            "De qué lado del eje dibujado queda el cuerpo de la línea, mirando en el sentido "
            "en que se dibujó. Solo orienta al visor: el área no depende de ella."
        ),
    )
    forma: FormaDeTrazo | None = Field(
        default=None,
        description="Plantilla con la que se estampó un polígono que nació de un punto con forma.",
    )
    medicion_id: UUID | None = Field(
        default=None,
        description=(
            "La medición (capa sombra, 0088) a la que entra el trazo: hereda los enlaces de su medición "
            "y de las que la contienen. Una medición solo admite trazos de su tipo."
        ),
    )
    pendiente_pct: Decimal | None = Field(
        default=None,
        gt=0,
        le=1000,
        description=(
            "Pendiente en % de una **línea** inclinada (desnivel / recorrido × 100): su longitud "
            "real es la de la planta × √(1 + p²). Solo de una línea."
        ),
    )

    @model_validator(mode="after")
    def _grosor_y_alineacion_juntos(self) -> TrazoPeticion:
        if (self.grosor_m is None) != (self.alineacion is None):
            raise ValueError("`grosor_m` y `alineacion` van juntos o no va ninguno.")
        return self


class HuecoPeticion(BaseModel):
    """Un hueco dentro de un área ya trazada (la ventana de un muro, el cubo de una escalera)."""

    geometria_wkt: str = Field(
        min_length=1, description="`POLYGON((...))` en coordenadas de plano, dentro del área."
    )


class TrazoEliminadoRespuesta(BaseModel):
    trazo_id: UUID
    recalculos: list[ResultadoRecalculoRespuesta]


class TransformarTrazosPeticion(BaseModel):
    """Mover `(dx, dy)` o girar `grados`: una cosa o la otra.

    Las coordenadas son las del plano. `grados` es el giro en ese sistema (positivo de +x hacia +y);
    qué es «izquierda» en pantalla lo decide la vista del plano, y de eso se ocupa quien llama.
    Sin `pivote` cada trazo gira sobre el centro de su propia caja; con él, todos giran juntos
    alrededor de ese punto.
    """

    trazo_ids: list[UUID] = Field(min_length=1, max_length=200)
    dx: Decimal = Decimal(0)
    dy: Decimal = Decimal(0)
    grados: Decimal = Field(default=Decimal(0), ge=-360, le=360)
    pivote: tuple[Decimal, Decimal] | None = None

    @model_validator(mode="after")
    def _una_cosa(self) -> TransformarTrazosPeticion:
        mueve = self.dx != 0 or self.dy != 0
        gira = self.grados != 0
        if mueve and gira:
            raise ValueError("Pide mover o girar, no las dos cosas a la vez.")
        if not mueve and not gira:
            raise ValueError("No hay nada que hacer: pide un desplazamiento o un giro.")
        return self


class TrazoTransformadoRespuesta(BaseModel):
    trazo_id: UUID
    pivote: tuple[Decimal, Decimal] | None = Field(
        default=None, description="El centro usado al girar; sirve para deshacer el giro."
    )


class TransformarTrazosRespuesta(BaseModel):
    trazos: list[TrazoTransformadoRespuesta]


class HuecoRespuesta(BaseModel):
    hueco_id: UUID
    recalculos: list[ResultadoRecalculoRespuesta]


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
    texto: str = Field(default="", description="Vacío solo en una flecha.")
    actividad_id: UUID | None = None
    tipo: Literal["nota", "texto", "flecha", "llamada"] = Field(
        default="nota",
        description=(
            "`nota` (rombo con texto), `texto` (rótulo suelto), `flecha` (señala `destino_wkt`) "
            "o `llamada` (texto con una flecha a `destino_wkt`). Ninguna produce cantidad."
        ),
    )
    destino_wkt: str | None = Field(
        default=None, description="WKT de un punto: a dónde apunta una flecha o una llamada."
    )


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
            grosor_m=peticion.grosor_m,
            alineacion=peticion.alineacion,
            forma=peticion.forma.model_dump(mode="json") if peticion.forma else None,
            pendiente_pct=peticion.pendiente_pct,
            medicion_id=peticion.medicion_id,
            enlaces=tuple(
                IntencionEnlace(
                    medida=e.medida,
                    factor=e.factor,
                    actividad_id=e.actividad_id,
                    prototipo_nodo_id=e.prototipo_nodo_id,
                    matriz_concepto_id=e.matriz_concepto_id,
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


@router.post(
    "/trazos/{trazo_id}/huecos",
    response_model=HuecoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Abrir un hueco en un área ya trazada",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={
        403: {"description": "El área alimenta un prototipo_nodo y el rol no es Control de obra ni Super intendente."},
        404: {"description": "El trazo no existe o está fuera de tu alcance."},
        422: {"description": "No es un área, el hueco no es un polígono válido o se sale del área."},
    },
)
async def agregar_hueco(
    trazo_id: UUID,
    peticion: HuecoPeticion,
    ctx: ContextoActual,
    caso_uso: AgregarHuecoDep,
) -> HuecoRespuesta:
    """El hueco resta del área y del perímetro del trazo; el trazo no se modifica (es un trazo
    hijo). Cada nodo que el área alimenta se recalcula, igual que al calibrar la escala."""
    resultado = await caso_uso.ejecutar(
        ComandoAgregarHueco(
            trazo_id=trazo_id,
            geometria_wkt=peticion.geometria_wkt,
            autor_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
        ),
        detectada_en=datetime.now(UTC),
    )
    return HuecoRespuesta(
        hueco_id=resultado.hueco_id,
        recalculos=[ResultadoRecalculoRespuesta.desde_dominio(r) for r in resultado.recalculos],
    )


@router.delete(
    "/trazos/{trazo_id}",
    response_model=TrazoEliminadoRespuesta,
    summary="Borrar un trazo (punto, línea o área) con sus enlaces y huecos",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={
        403: {
            "description": (
                "No es un trazo tuyo sin aprobar (Control de obra y Super intendente borran "
                "cualquiera), o alimenta un prototipo_nodo y el rol no puede tocarlo."
            )
        },
        404: {"description": "El trazo no existe o está fuera de tu alcance."},
    },
)
async def eliminar_trazo(
    trazo_id: UUID, ctx: ContextoActual, caso_uso: EliminarTrazoDep
) -> TrazoEliminadoRespuesta:
    """Cada nodo que el trazo alimentaba se recalcula; si era su último trazo vuelve a «sin
    medir» y no levanta una desviación."""
    resultado = await caso_uso.ejecutar(
        ComandoEliminarTrazo(trazo_id=trazo_id, usuario_id=ctx.usuario_id, rol=Rol(ctx.rol)),
        detectada_en=datetime.now(UTC),
    )
    return TrazoEliminadoRespuesta(
        trazo_id=resultado.trazo_id,
        recalculos=[ResultadoRecalculoRespuesta.desde_dominio(r) for r in resultado.recalculos],
    )


@router.post(
    "/trazos/transformar",
    response_model=TransformarTrazosRespuesta,
    summary="Mover o girar trazos, con sus huecos",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={
        403: {
            "description": (
                "No es un trazo tuyo sin aprobar (Control de obra y Super intendente tocan "
                "cualquiera), o alimenta un prototipo_nodo y el rol no puede tocarlo."
            )
        },
        404: {"description": "Un trazo no existe o está fuera de tu alcance."},
    },
)
async def transformar_trazos(
    peticion: TransformarTrazosPeticion, ctx: ContextoActual, caso_uso: TransformarTrazosDep
) -> TransformarTrazosRespuesta:
    """Un largo o un área no cambian al mover o girar: las cantidades de los enlaces siguen iguales.
    Todo o nada: si uno de los trazos no se puede tocar, no se mueve ninguno."""
    resultado = await caso_uso.ejecutar(
        ComandoTransformarTrazos(
            trazo_ids=tuple(peticion.trazo_ids),
            usuario_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
            dx=peticion.dx,
            dy=peticion.dy,
            grados=peticion.grados,
            pivote=peticion.pivote,
        )
    )
    return TransformarTrazosRespuesta(
        trazos=[TrazoTransformadoRespuesta(trazo_id=t.trazo_id, pivote=t.pivote) for t in resultado]
    )


@router.delete(
    "/trazos/{trazo_id}/huecos/{hueco_id}",
    response_model=TrazoEliminadoRespuesta,
    summary="Quitar un hueco de un área",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={
        403: {"description": "No es un trazo tuyo sin aprobar, o alimenta un prototipo_nodo."},
        404: {"description": "El trazo o su hueco no existen o están fuera de tu alcance."},
    },
)
async def quitar_hueco(
    trazo_id: UUID, hueco_id: UUID, ctx: ContextoActual, caso_uso: QuitarHuecoDep
) -> TrazoEliminadoRespuesta:
    """El área vuelve a medir lo que medía sin ese hueco; sus nodos se recalculan."""
    resultado = await caso_uso.ejecutar(
        trazo_id=trazo_id,
        hueco_id=hueco_id,
        usuario_id=ctx.usuario_id,
        rol=Rol(ctx.rol),
        detectada_en=datetime.now(UTC),
    )
    return TrazoEliminadoRespuesta(
        trazo_id=resultado.trazo_id,
        recalculos=[ResultadoRecalculoRespuesta.desde_dominio(r) for r in resultado.recalculos],
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


class VistaPeticion(BaseModel):
    """Cómo se ve el plano (migración 0087). Solo presentación: ninguna cantidad cambia."""

    rotacion_grados: Literal[0, 90, 180, 270] = 0
    volteo_horizontal: bool = False
    volteo_vertical: bool = False


@router.put(
    "/planos/{plano_id}/vista",
    response_model=VistaPeticion,
    summary="Girar o voltear el plano al verlo",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={404: {"description": "El plano no existe o está fuera de tu alcance."}},
)
async def fijar_vista(
    plano_id: UUID,
    peticion: VistaPeticion,
    caso_uso: FijarVistaDePlanoDep,
) -> VistaPeticion:
    """La rotación y el espejo se guardan con el plano para que todos lo vean igual. No tocan
    la geometría de los trazos ni las cantidades."""
    await caso_uso.ejecutar(
        ComandoFijarVistaDePlano(
            plano_id=plano_id,
            rotacion_grados=peticion.rotacion_grados,
            volteo_horizontal=peticion.volteo_horizontal,
            volteo_vertical=peticion.volteo_vertical,
        )
    )
    return peticion


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
            usuario_id=ctx.usuario_id,
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


class TraerTrazoPeticion(BaseModel):
    plano_destino_id: UUID = Field(description="La versión nueva del mismo plano.")
    dx: Decimal = Field(default=Decimal(0), description="Cuánto se corre el trazo en X (unidades de plano).")
    dy: Decimal = Field(default=Decimal(0), description="Cuánto se corre el trazo en Y (unidades de plano).")


class TrazoTraidoRespuesta(BaseModel):
    trazo_id: UUID
    enlace_ids: list[UUID]
    huecos: int
    recalculos: list[ResultadoRecalculoRespuesta]


@router.post(
    "/trazos/{trazo_id}/traer",
    response_model=TrazoTraidoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Traer un trazo de una versión anterior del plano a la nueva",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={
        403: {"description": "El trazo mide un prototipo_nodo y el rol no puede tocarlo."},
        404: {"description": "El trazo o el plano no existen o están fuera de tu alcance."},
        422: {"description": "No son versiones del mismo plano, o va de la nueva a la anterior."},
    },
)
async def traer_trazo(
    trazo_id: UUID, peticion: TraerTrazoPeticion, ctx: ContextoActual, caso_uso: TraerTrazoDep
) -> TrazoTraidoRespuesta:
    """Empalme de versiones (acción explícita, nunca por cercanía): el trazo se repite en la versión
    nueva —corrido `dx`, `dy`, con sus huecos y enlaces vigentes— y los enlaces del viejo dejan de
    ser vigentes, así que lo medido no se cuenta dos veces. El viejo queda como evidencia."""
    resultado = await caso_uso.ejecutar(
        ComandoTraerTrazo(
            trazo_id=trazo_id,
            plano_destino_id=peticion.plano_destino_id,
            usuario_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
            dx=peticion.dx,
            dy=peticion.dy,
        ),
        detectada_en=datetime.now(UTC),
    )
    return TrazoTraidoRespuesta(
        trazo_id=resultado.trazo_id,
        enlace_ids=list(resultado.enlace_ids),
        huecos=resultado.huecos,
        recalculos=[ResultadoRecalculoRespuesta.desde_dominio(r) for r in resultado.recalculos],
    )


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
            tipo=peticion.tipo,
            destino_wkt=peticion.destino_wkt,
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
    rotacion_grados: int = Field(
        default=0, description="Cuánto se gira el plano al verlo: 0, 90, 180 o 270 (0087)."
    )
    volteo_horizontal: bool = False
    volteo_vertical: bool = False


class EnlaceDeTrazoRespuesta(BaseModel):
    enlace_id: UUID
    tipo_nodo: str
    nodo_id: UUID = Field(
        description="`actividad_id` o `prototipo_nodo_id`, según `tipo_nodo`."
    )
    matriz_concepto_id: UUID | None = Field(
        default=None, description="La matriz interna de la actividad que mide este enlace (D-583)."
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
    grosor_m: Decimal | None = Field(
        default=None, description="Grosor en metros de una línea (un muro); `null` si no tiene."
    )
    alineacion: Literal["centro", "izquierda", "derecha"] | None = None
    pendiente_pct: Decimal | None = Field(
        default=None, description="Pendiente en % de una línea inclinada; `null` = horizontal."
    )
    medicion_id: UUID | None = Field(
        default=None, description="La medición a la que pertenece el trazo (0088); `null` = suelto."
    )
    forma: dict[str, Any] | None = Field(
        default=None, description="Plantilla con la que se estampó un punto con forma."
    )
    n_huecos: int = Field(
        default=0,
        description="Huecos que tiene el área. Su geometría ya viene restada en `geometry`.",
    )
    propuesta: bool = Field(
        default=False,
        description="Propuesto por una herramienta automática y aún sin revisar: no suma cantidad (0092).",
    )
    propuesta_origen: Literal["conteo_auto", "takeoff"] | None = None
    propuesta_actividad_id: UUID | None = Field(
        default=None, description="El concepto para el que se propuso."
    )
    propuesta_medida: str | None = None
    propuesta_confianza: Decimal | None = Field(default=None, description="De 0 a 1.")
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
                matriz_concepto_id=e.get("matriz_concepto_id"),
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
                    grosor_m=trazo.get("grosor_m"),
                    alineacion=trazo.get("alineacion"),
                    pendiente_pct=trazo.get("pendiente_pct"),
                    medicion_id=trazo.get("medicion_id"),
                    forma=trazo.get("forma"),
                    n_huecos=int(trazo.get("n_huecos") or 0),
                    propuesta=bool(trazo.get("propuesta")),
                    propuesta_origen=trazo.get("propuesta_origen"),
                    propuesta_actividad_id=trazo.get("propuesta_actividad_id"),
                    propuesta_medida=trazo.get("propuesta_medida"),
                    propuesta_confianza=trazo.get("propuesta_confianza"),
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
    tipo: Literal["nota", "texto", "flecha", "llamada"] = "nota"
    destino: dict[str, Any] | None = Field(
        default=None, description="`Point` GeoJSON al que apunta una flecha o una llamada."
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


class MatrizRespuesta(BaseModel):
    concepto_id: UUID
    padre_id: UUID = Field(description="La matriz de la que es insumo (la madre es el concepto).")
    nivel: int = Field(description="1 = insumo directo de la madre; 2 = dentro de una matriz…")
    clave: str
    descripcion: str
    unidad: str | None = None
    cantidad_unitaria: Decimal = Field(description="Por unidad de su matriz madre inmediata.")
    formula: dict[str, Any] | None = Field(
        default=None, description="Cómo se formó la cantidad unitaria (piezas ÷ largo × desperdicio), si no fue a mano."
    )
    cantidad_catalogo: Decimal = Field(description="Lo que el catálogo implica para esta actividad.")
    precio_unitario: Decimal
    cantidad_medida: Decimal | None = Field(
        default=None, description="Lo medido en esta obra; no reescribe el catálogo."
    )
    diferencia: Decimal | None = None


class MatricesDeActividadRespuesta(BaseModel):
    actividad_id: UUID
    concepto_id: UUID | None = Field(
        default=None, description="El concepto madre: a él se le agregan matrices en el catálogo."
    )
    concepto_clave: str | None = None
    descripcion: str
    cant_base: Decimal
    importe: Decimal
    importe_ajuste: Decimal = Field(
        description="Lo que cambia el importe por lo medido en las matrices internas."
    )
    importe_ajustado: Decimal
    medidas: int
    matrices: list[MatrizRespuesta]


@router.get(
    "/actividades/{actividad_id}/matrices",
    response_model=MatricesDeActividadRespuesta,
    summary="Las matrices internas de una actividad y lo medido de cada una",
    responses={404: {"description": "La actividad no existe o está fuera de tu alcance."}},
)
async def matrices_de_la_actividad(
    actividad_id: UUID, caso_uso: ConsultarMatricesDep
) -> MatricesDeActividadRespuesta:
    """El concepto es la matriz madre; un insumo puede ser otra matriz (nervaduras, trabes,
    bastones), a cualquier profundidad (D-583). Medirlas ajusta el importe de la actividad sin
    tocar su cantidad base ni el catálogo."""
    return MatricesDeActividadRespuesta(**await caso_uso.ejecutar(actividad_id))


class VanoPeticion(BaseModel):
    """Una puerta, ventana o paso colocado sobre una línea."""

    clave: str = Field(min_length=1, max_length=20)
    tipo: Literal["puerta", "ventana", "cancel", "arco", "paso"]
    ancho_m: Decimal = Field(gt=0, le=50)
    alto_m: Decimal = Field(gt=0, le=50)
    antepecho_m: Decimal = Field(default=Decimal(0), ge=0, le=50, description="Del piso al borde de abajo (ventanas).")
    piezas: int = Field(default=1, ge=1, le=999)
    posicion_m: Decimal | None = Field(default=None, ge=0, description="Distancia desde el inicio de la línea (o del borde de un área).")
    lado_muro: Literal[-1, 0, 1] = Field(default=0, description="De qué cara del muro cae el clic; solo afecta el dibujo.")


class VanoRespuesta(BaseModel):
    id: UUID
    clave: str
    tipo: str
    ancho_m: Decimal
    alto_m: Decimal
    antepecho_m: Decimal
    piezas: int
    posicion_m: Decimal | None
    llega_al_piso: bool
    lado_muro: Literal[-1, 0, 1] = 0
    bisagra: Literal[-1, 1] = Field(default=1, description="Extremo donde van las bisagras: 1 el inicial, -1 el otro.")
    lado_hoja: Literal[-1, 1] = Field(default=1, description="Hacia qué lado del muro abre la hoja.")
    apertura_grados: int = Field(default=90, ge=0, le=180, description="Cuánto está abierta la hoja al dibujarla.")


class VanoCambiadoRespuesta(BaseModel):
    vano_id: UUID
    recalculos: list[ResultadoRecalculoRespuesta]


@router.get(
    "/trazos/{trazo_id}/vanos",
    response_model=list[VanoRespuesta],
    summary="Los vanos colocados sobre una línea",
    responses={404: {"description": "El trazo no existe o está fuera de tu alcance."}},
)
async def listar_vanos(trazo_id: UUID, caso_uso: GestionarVanosDep) -> list[VanoRespuesta]:
    return [VanoRespuesta(**v) for v in await caso_uso.listar(trazo_id)]


@router.post(
    "/trazos/{trazo_id}/vanos",
    response_model=VanoCambiadoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Colocar un vano (puerta, ventana, paso) sobre una línea",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={
        403: {"description": "La línea alimenta un prototipo_nodo y el rol no es Control de obra ni Super intendente."},
        404: {"description": "El trazo no existe o está fuera de tu alcance."},
        422: {"description": "El trazo no es una línea o las medidas no valen."},
    },
)
async def colocar_vano(
    trazo_id: UUID, peticion: VanoPeticion, ctx: ContextoActual, caso_uso: GestionarVanosDep
) -> VanoCambiadoRespuesta:
    """Descuenta de lo que mide la línea: ancho × alto × piezas × caras en m², o su ancho en metros si llega al piso."""
    r = await caso_uso.agregar(
        ComandoAgregarVano(
            trazo_id=trazo_id,
            clave=peticion.clave,
            tipo=peticion.tipo,
            ancho_m=peticion.ancho_m,
            alto_m=peticion.alto_m,
            antepecho_m=peticion.antepecho_m,
            piezas=peticion.piezas,
            posicion_m=peticion.posicion_m,
            autor_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
            lado_muro=peticion.lado_muro,
        ),
        detectada_en=datetime.now(UTC),
    )
    return VanoCambiadoRespuesta(
        vano_id=r.vano_id, recalculos=[ResultadoRecalculoRespuesta.desde_dominio(x) for x in r.recalculos]
    )


class HojaDelVanoPeticion(BaseModel):
    bisagra: Literal[-1, 1] = 1
    lado_hoja: Literal[-1, 1] = 1
    apertura_grados: int = Field(default=90, ge=0, le=180)


@router.put(
    "/vanos/{vano_id}/hoja",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="La hoja de una puerta: bisagra, lado y apertura",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={404: {"description": "El vano no existe o está fuera de tu alcance."}},
)
async def fijar_hoja_del_vano(vano_id: UUID, peticion: HojaDelVanoPeticion, caso_uso: GestionarVanosDep) -> None:
    """Dibujo y especificación: no cambia lo que descuenta el vano, así que no recalcula cantidades."""
    await caso_uso.fijar_hoja(
        vano_id, bisagra=peticion.bisagra, lado_hoja=peticion.lado_hoja, apertura_grados=peticion.apertura_grados
    )


@router.delete(
    "/vanos/{vano_id}",
    response_model=VanoCambiadoRespuesta,
    summary="Quitar un vano",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={404: {"description": "El vano no existe o está fuera de tu alcance."}},
)
async def quitar_vano(vano_id: UUID, ctx: ContextoActual, caso_uso: GestionarVanosDep) -> VanoCambiadoRespuesta:
    """La línea vuelve a medir sin ese vano; sus nodos se recalculan."""
    r = await caso_uso.quitar(vano_id, autor_id=ctx.usuario_id, rol=Rol(ctx.rol), detectada_en=datetime.now(UTC))
    return VanoCambiadoRespuesta(
        vano_id=r.vano_id, recalculos=[ResultadoRecalculoRespuesta.desde_dominio(x) for x in r.recalculos]
    )


class ParteDeAlturaModelo(BaseModel):
    nombre: str = Field(default="", max_length=40)
    desde_m: Decimal = Field(ge=0)
    hasta_m: Decimal = Field(gt=0)
    suma: bool = Field(default=True, description="Si no suma, cuenta para la altura pero no para la cantidad.")


class MuroDelTrazoPeticion(BaseModel):
    altura_m: Decimal | None = Field(default=None, gt=0, description="Altura única; ignorada si hay partes.")
    caras: Literal[1, 2] = 2
    cara: Literal["interior", "exterior"] | None = Field(default=None, description="Con una sola cara, cuál.")
    partes: list[ParteDeAlturaModelo] | None = Field(default=None, description="Altura por partes.")


class MuroDelTrazoRespuesta(BaseModel):
    altura_m: Decimal | None
    caras: int
    cara: str | None
    partes: list[ParteDeAlturaModelo] | None
    altura_efectiva_m: Decimal = Field(description="La altura que suma a la cantidad.")


def _muro_respuesta(m: dict) -> MuroDelTrazoRespuesta:
    partes = [
        ParteDeAltura(nombre=p.get("nombre", ""), desde_m=Decimal(str(p["desde_m"])), hasta_m=Decimal(str(p["hasta_m"])), suma=bool(p.get("suma", True)))
        for p in (m["partes"] or [])
    ]
    altura = altura_efectiva(m["altura_m"], partes or None)
    return MuroDelTrazoRespuesta(
        altura_m=m["altura_m"],
        caras=m["caras"],
        cara=m["cara"],
        partes=[ParteDeAlturaModelo(nombre=p.nombre, desde_m=p.desde_m, hasta_m=p.hasta_m, suma=p.suma) for p in partes] or None,
        altura_efectiva_m=altura,
    )


@router.get(
    "/trazos/{trazo_id}/muro",
    response_model=MuroDelTrazoRespuesta,
    summary="Cómo cuenta un muro: altura, caras y partes",
    responses={404: {"description": "El trazo no existe o está fuera de tu alcance."}},
)
async def ver_muro(trazo_id: UUID, caso_uso: GestionarVanosDep) -> MuroDelTrazoRespuesta:
    return _muro_respuesta(await caso_uso.muro(trazo_id))


@router.put(
    "/trazos/{trazo_id}/muro",
    response_model=VanoCambiadoRespuesta,
    summary="Fijar cómo cuenta un muro: altura única o por partes y una o dos caras",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={
        403: {"description": "La línea alimenta un prototipo_nodo y el rol no es Control de obra ni Super intendente."},
        404: {"description": "El trazo no existe o está fuera de tu alcance."},
        422: {"description": "El trazo no es una línea o las partes no valen."},
    },
)
async def fijar_muro(
    trazo_id: UUID, peticion: MuroDelTrazoPeticion, ctx: ContextoActual, caso_uso: GestionarVanosDep
) -> VanoCambiadoRespuesta:
    """Rehace el factor de los enlaces de largo en m² del muro (altura × caras) y recalcula lo que alimenta."""
    r = await caso_uso.fijar_muro(
        trazo_id,
        altura_m=peticion.altura_m,
        caras=peticion.caras,
        cara=peticion.cara,
        partes=[ParteDeAltura(p.nombre, p.desde_m, p.hasta_m, p.suma) for p in peticion.partes] if peticion.partes else None,
        autor_id=ctx.usuario_id,
        rol=Rol(ctx.rol),
        detectada_en=datetime.now(UTC),
    )
    return VanoCambiadoRespuesta(
        vano_id=r.vano_id, recalculos=[ResultadoRecalculoRespuesta.desde_dominio(x) for x in r.recalculos]
    )


class ParteDeAlturaEnConversion(BaseModel):
    nombre: str = Field(default="", max_length=40)
    desde_m: float = Field(ge=0)
    hasta_m: float = Field(gt=0)
    suma: bool = True


class ConversionPeticion(BaseModel):
    """Cómo cuenta un trazo para su concepto (D-633). Los parámetros que no aplican al modo se ignoran."""

    modo: Literal["largo", "area", "vol", "pza", "perim"]
    alt: float | None = Field(default=None, ge=0, description="Altura (m); en un área en perímetro, 0 = solo largo.")
    gro: float | None = Field(default=None, ge=0, description="Grosor (m), en volumen de un muro.")
    esp: float | None = Field(default=None, ge=0, description="Espesor (m), en volumen de un área.")
    desc: float | None = Field(default=None, ge=0, description="Descuento (m³), en volumen de un área.")
    pw: float | None = Field(default=None, gt=0, description="Ancho de la pieza (m).")
    ph: float | None = Field(default=None, gt=0, description="Alto de la pieza (m).")
    merma: float | None = Field(default=None, ge=0, le=100, description="Merma (%).")
    sep: float | None = Field(default=None, gt=0, description="Una pieza cada (m), en piezas de un muro.")
    mide: Literal["eje", "cara1", "cara2"] = "cara2"
    cara: Literal["int", "ext"] = "int"
    lado: Literal["izq", "der"] = Field(default="der", description="De qué lado del sentido de dibujo queda el interior.")
    partes: list[ParteDeAlturaEnConversion] = Field(default_factory=list, description="Altura por partes.")


class ModoRespuesta(BaseModel):
    clave: str
    nombre: str


class CampoRespuesta(BaseModel):
    clave: str
    etiqueta: str
    unidad: str


class ConversionDelEnlaceRespuesta(BaseModel):
    enlace_id: UUID
    tipo: str = Field(description="muro, linea, area, punto…")
    unidad_del_concepto: str | None
    conversion: dict[str, Any] | None = Field(description="La vigente, o la de defecto; null si este tipo aún cuenta por medida × factor.")
    es_la_de_hoy: bool = Field(description="Falso = es la de defecto, todavía no se ha aplicado ninguna.")
    modos: list[ModoRespuesta]
    campos: dict[str, list[CampoRespuesta]] = Field(description="Los parámetros que pide cada modo.")


class CalculoDeConversionRespuesta(BaseModel):
    valor: float
    unidad: str
    formula: str
    unidad_del_concepto: str | None
    coincide: bool = Field(description="El resultado viene en la unidad del concepto.")
    conversion: dict[str, Any]
    componentes: dict[str, Any]


class AplicarConversionPeticion(BaseModel):
    conversion: ConversionPeticion
    a_todos: bool = Field(default=False, description="También a los demás trazos del mismo tipo de este concepto.")


class ConversionAplicadaRespuesta(BaseModel):
    aplicados: int
    resultado: ResultadoRecalculoRespuesta


def _conv(p: ConversionPeticion) -> dict[str, Any]:
    return p.model_dump(exclude_none=True)


@router.get(
    "/enlaces/{enlace_id}/conversion",
    response_model=ConversionDelEnlaceRespuesta,
    summary="Cómo cuenta un trazo para su concepto: lo vigente y lo que se puede elegir",
    responses={404: {"description": "El enlace no existe o está fuera de tu alcance."}, 422: {"description": "Ya fue reemplazado."}},
)
async def ver_conversion(enlace_id: UUID, caso_uso: ConversionDelEnlaceDep) -> ConversionDelEnlaceRespuesta:
    return ConversionDelEnlaceRespuesta(**await caso_uso.ver(enlace_id))


@router.post(
    "/enlaces/{enlace_id}/conversion/calcular",
    response_model=CalculoDeConversionRespuesta,
    summary="Calcular cuánto aportaría el trazo con esta conversión, sin guardar nada",
    responses={404: {"description": "El enlace no existe o está fuera de tu alcance."}, 422: {"description": "La conversión no vale."}},
)
async def calcular_conversion(
    enlace_id: UUID, peticion: ConversionPeticion, caso_uso: ConversionDelEnlaceDep
) -> CalculoDeConversionRespuesta:
    """La vista previa: el mismo cálculo que se guarda al aplicar, con la fórmula escrita y si coincide la unidad."""
    return CalculoDeConversionRespuesta(**await caso_uso.calcular(enlace_id, _conv(peticion)))


@router.post(
    "/enlaces/{enlace_id}/conversion",
    response_model=ConversionAplicadaRespuesta,
    summary="Aplicar la conversión: crea un enlace nuevo y el anterior queda como evidencia",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={
        403: {"description": "El enlace es de un prototipo_nodo y el rol no es Control de obra ni Super intendente."},
        404: {"description": "El enlace no existe o está fuera de tu alcance."},
        422: {"description": "La conversión no vale o el enlace ya fue reemplazado."},
    },
)
async def aplicar_conversion(
    enlace_id: UUID, peticion: AplicarConversionPeticion, ctx: ContextoActual, caso_uso: ConversionDelEnlaceDep
) -> ConversionAplicadaRespuesta:
    r = await caso_uso.aplicar(
        enlace_id,
        _conv(peticion.conversion),
        a_todos=peticion.a_todos,
        rol=Rol(ctx.rol),
        usuario_id=ctx.usuario_id,
        detectada_en=datetime.now(UTC),
    )
    return ConversionAplicadaRespuesta(
        aplicados=r["aplicados"], resultado=ResultadoRecalculoRespuesta.desde_dominio(r["resultado"])
    )


class UnionDeExtremoRespuesta(BaseModel):
    extremo: Literal["ini", "fin"]
    op: Literal["conexion", "union", "empalme"]
    con_trazo_id: UUID


class CandidatoDeUnionRespuesta(BaseModel):
    extremo: Literal["ini", "fin"]
    trazo_id: UUID
    grosor_m: Decimal | None
    distancia_m: Decimal = Field(description="A cuántos metros del extremo queda el otro muro.")


class UnionesDelMuroRespuesta(BaseModel):
    extremos: list[UnionDeExtremoRespuesta]
    candidatos: list[CandidatoDeUnionRespuesta] = Field(description="Los muros que se encuentran con cada extremo.")


class UnionPeticion(BaseModel):
    op: Literal["conexion", "union", "empalme"]
    con_trazo_id: UUID


class FusionPeticion(BaseModel):
    con_trazo_id: UUID


@router.get(
    "/trazos/{trazo_id}/uniones",
    response_model=UnionesDelMuroRespuesta,
    summary="Qué pasa en cada extremo del muro y con qué muros se encuentra",
    responses={404: {"description": "El trazo no existe o está fuera de tu alcance."}},
)
async def ver_uniones(trazo_id: UUID, caso_uso: GestionarVanosDep) -> UnionesDelMuroRespuesta:
    return UnionesDelMuroRespuesta(**await caso_uso.uniones(trazo_id))


_RESPUESTAS_UNION = {
    403: {"description": "La línea alimenta un prototipo_nodo y el rol no es Control de obra ni Super intendente."},
    404: {"description": "El trazo no existe o está fuera de tu alcance."},
    422: {"description": "No es una línea, o el otro muro no se encuentra con ese extremo."},
}


@router.put(
    "/trazos/{trazo_id}/uniones/{extremo}",
    response_model=VanoCambiadoRespuesta,
    summary="Fijar qué pasa en un extremo del muro: conexión, unión a tope o empalme",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses=_RESPUESTAS_UNION,
)
async def fijar_union(
    trazo_id: UUID, extremo: Literal["ini", "fin"], peticion: UnionPeticion, ctx: ContextoActual, caso_uso: GestionarVanosDep
) -> VanoCambiadoRespuesta:
    """La unión a tope resta medio grosor del otro muro del largo; el empalme, el tramo que se solapa."""
    r = await caso_uso.fijar_union(
        trazo_id,
        extremo=extremo,
        op=peticion.op,
        con_trazo_id=peticion.con_trazo_id,
        autor_id=ctx.usuario_id,
        rol=Rol(ctx.rol),
        detectada_en=datetime.now(UTC),
    )
    return VanoCambiadoRespuesta(vano_id=r.vano_id, recalculos=[ResultadoRecalculoRespuesta.desde_dominio(x) for x in r.recalculos])


@router.delete(
    "/trazos/{trazo_id}/uniones/{extremo}",
    response_model=VanoCambiadoRespuesta,
    summary="Quitar la unión de un extremo",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses=_RESPUESTAS_UNION,
)
async def quitar_union(
    trazo_id: UUID, extremo: Literal["ini", "fin"], ctx: ContextoActual, caso_uso: GestionarVanosDep
) -> VanoCambiadoRespuesta:
    r = await caso_uso.fijar_union(
        trazo_id,
        extremo=extremo,
        op=None,
        con_trazo_id=None,
        autor_id=ctx.usuario_id,
        rol=Rol(ctx.rol),
        detectada_en=datetime.now(UTC),
    )
    return VanoCambiadoRespuesta(vano_id=r.vano_id, recalculos=[ResultadoRecalculoRespuesta.desde_dominio(x) for x in r.recalculos])


@router.post(
    "/trazos/{trazo_id}/fusion",
    response_model=VanoCambiadoRespuesta,
    summary="Fusionar dos muros que se encuentran en un extremo: pasan a ser uno solo",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses=_RESPUESTAS_UNION,
)
async def fusionar_muros(
    trazo_id: UUID, peticion: FusionPeticion, ctx: ContextoActual, caso_uso: GestionarVanosDep
) -> VanoCambiadoRespuesta:
    """El primero conserva su identidad y absorbe al segundo; deben tener el mismo grosor y alimentar lo mismo."""
    r = await caso_uso.fusionar(
        trazo_id, peticion.con_trazo_id, autor_id=ctx.usuario_id, rol=Rol(ctx.rol), detectada_en=datetime.now(UTC)
    )
    return VanoCambiadoRespuesta(vano_id=r.vano_id, recalculos=[ResultadoRecalculoRespuesta.desde_dominio(x) for x in r.recalculos])


class VanoEnPlanoRespuesta(BaseModel):
    id: UUID
    trazo_id: UUID
    clave: str
    tipo: str
    ancho_m: Decimal
    alto_m: Decimal
    piezas: int
    posicion_m: Decimal | None
    bisagra: Literal[-1, 1] = 1
    lado_hoja: Literal[-1, 1] = 1
    apertura_grados: int = 90
    lado_muro: Literal[-1, 0, 1] = 0
    grosor_plano: float = Field(default=0, description="Grosor del muro en unidades de plano (0 si no tiene).")
    x: float = Field(description="Dónde va, en coordenadas del plano.")
    y: float
    angulo: float = Field(description="Hacia dónde corre el muro en ese punto, en grados (eje y hacia abajo).")
    ancho_plano: float = Field(description="Ancho del vano en unidades de plano.")


class VanoPosicionPeticion(BaseModel):
    posicion_m: Decimal = Field(ge=0, description="Metros desde el inicio de la línea.")


@router.get(
    "/planos/{plano_id}/vanos",
    response_model=list[VanoEnPlanoRespuesta],
    summary="Los vanos de un plano, con el punto donde van para dibujarlos",
)
async def vanos_del_plano(plano_id: UUID, caso_uso: GestionarVanosDep) -> list[VanoEnPlanoRespuesta]:
    return [VanoEnPlanoRespuesta(**v) for v in await caso_uso.del_plano(plano_id)]


@router.patch(
    "/vanos/{vano_id}/posicion",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Correr un vano por su muro",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={404: {"description": "El vano no existe o está fuera de tu alcance."}},
)
async def mover_vano(vano_id: UUID, peticion: VanoPosicionPeticion, caso_uso: GestionarVanosDep) -> None:
    """Dónde está el vano no cambia lo que mide la línea: no recalcula cantidades."""
    await caso_uso.mover(vano_id, peticion.posicion_m)
