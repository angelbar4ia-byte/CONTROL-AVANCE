"""Torre de control y actividades (§5.1, §11.2).

Spec §5.1 (primera entrada de Supervisor, Control de obra y Super intendente) ·
§5.3 (pantalla compartida) · §12.4 (RLS decide el alcance) · §12.11.

Tres rutas de **lectura**, sin caso de uso de por medio: no hay ninguna regla de
negocio que aplicar entre la consulta y la respuesta, y meter una capa vacía
solo para respetar una forma sería ceremonia. Es el mismo criterio que
`GET /me` en `identidad.py` y que los listados de `cargas.py`.

## Quién ve qué

Ninguna de las tres lleva `exigir_rol`, y es deliberado: el §5.1 pone la Torre
en el sidebar de tres roles, y el residente —que no la tiene— llega a las
actividades de **su** obra por la pantalla de avance. Lo que cada quien ve lo
decide RLS (`obra_select`, migración 0012), que ya sabe distinguir "las obras de
mis clusters" de "las de mis proyectos". Un `exigir_rol` aquí sería una segunda
lista de roles que mantener sincronizada con el sidebar, y la única
consecuencia de olvidarla es que alguien vea una tabla vacía.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import DarDeAltaExtraDep
from obractrl.adapters.api.dependencias import ContextoActual, SesionRLS, exigir_rol
from obractrl.adapters.api.idempotencia import Idempotencia
from obractrl.adapters.repos.torre_sql import RepositorioTorreSQL
from obractrl.application.casos_uso.dar_de_alta_extra import ComandoDarDeAltaExtra
from obractrl.domain.catalogos.rendimientos import (
    jornadas_por_unidad,
    razon_teorico_calculado,
    rendimiento_calculado,
)
from obractrl.domain.obras.extra_catalogo import ActividadExtra
from obractrl.domain.obras.precio_armado import (
    LineaDeCuadrilla,
    LineaDeMaterial,
    armar_precio,
)
from obractrl.domain.shared.diccionario import EstatusActividad, ModoPago, Rol

router = APIRouter(tags=["torre"])

FiltroProyecto = Annotated[UUID | None, Query(description="Acota a un proyecto.")]
FiltroCluster = Annotated[UUID | None, Query(description="Acota a un cluster.")]


class EstadoDeObraRespuesta(BaseModel):
    """El renglón de la Torre: una obra y lo que le falta (§5.1)."""

    obra_id: UUID
    obra_clave: str
    obra_estatus: str
    avance_pct: Decimal
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    cluster_id: UUID
    cluster_clave: str
    proyecto_id: UUID
    proyecto_clave: str
    residente_nombre: str | None = None

    actividades: int
    criticas: int = Field(description="En la ruta crítica (§7.5).")
    bloqueadas: int = Field(
        description="Detenidas por una incidencia con impacto `detiene` (§11.3 F)."
    )
    concluidas: int

    incidencias_abiertas: int = Field(
        description="Sin cerrar ni rechazar: las que todavía le tocan a alguien."
    )
    incidencias_detienen: int
    cierres_pendientes: int = Field(
        description="Solicitados o autorizados: esperan a supervisor o a control (§11.3 C)."
    )


class ActividadRespuesta(BaseModel):
    """Una actividad de la obra (§11.2 `GET /obras/{id}/actividades`)."""

    id: UUID
    obra_id: UUID
    concepto_id: UUID | None = None
    frente_id: UUID | None = None
    descripcion: str | None = None
    frente_nombre: str | None = None
    concepto_clave: str | None = None
    unidad: str | None = None

    # La jerarquía como el residente mira su obra (§7.4): el nivel es el
    # frente de trabajo y la etapa el sub-frente. No confundir `nivel_clave`
    # con `contratacion_clave`, que dice a quién se le compra.
    nivel_id: UUID | None = None
    nivel_clave: str | None = Field(default=None, description="El **frente**.")
    nivel_descripcion: str | None = None
    etapa_id: UUID | None = None
    etapa_clave: str | None = Field(default=None, description="El **sub-frente**.")
    etapa_descripcion: str | None = None
    contratacion_clave: str | None = Field(
        default=None,
        description="A quién se le compra: OBRA, INSTALACIONES, SUBCONTRATOS, PINTURA.",
    )
    especialidad_clave: str | None = Field(
        default=None, description="El oficio del concepto (migración 0047)."
    )
    orden_cambio: str | None = None
    orden: int | None = Field(default=None, description="Su lugar entre las partidas de su etapa; vacío = por clave (0116).")
    contratista_id: UUID | None = None
    contratista_nombre: str | None = None
    cuadrilla_id: UUID | None = None
    cuadrilla_nombre: str | None = None

    cant_base: Decimal
    cant_programada: Decimal
    cant_ejecutada: Decimal
    cant_excedente: Decimal = Field(
        default=Decimal(0),
        description=(
            "Lo ejecutado por encima de lo programado que aún espera comprobación "
            "y validación de Control de obra (migración 0066). Registrar nunca se "
            "bloquea: el excedente se registra y se decide aparte."
        ),
    )
    excedente_desde: date | None = Field(
        default=None, description="Desde cuándo hay excedente pendiente: su antigüedad."
    )
    tolerancia_pct: Decimal = Field(
        default=Decimal(20),
        description=(
            "Cuánto puede exceder la programada a la base sin control de "
            "cambio (§6, migración 0049). Copia del umbral de la obra."
        ),
    )
    cant_autorizada: Decimal | None = Field(
        default=None,
        description=(
            "Techo que un control de cambio ya autorizó. Cuando existe manda "
            "sobre la tolerancia: es la cantidad que Control firmó."
        ),
    )
    avance_pct: Decimal

    estatus: str
    bloqueada: bool
    extra: bool = Field(description="Alta extra-catálogo con OC (§5.1).")
    es_critica: bool
    holgura: Decimal | None = None
    desfase: Decimal | None = None

    fecha_inicio: date | None = None
    fecha_termino: date | None = None
    duracion_dias: Decimal

    modo_pago: str
    precio_unitario: Decimal
    precio_destajo: Decimal


class DarDeAltaExtraPeticion(BaseModel):
    """Trabajo que apareció en obra y no estaba en el prototipo (§11.2)."""

    obra_id: UUID
    descripcion: str = Field(
        min_length=1,
        description="Qué trabajo es. Sin esto el extra no se puede revisar ni estimar.",
    )
    orden_cambio: str = Field(
        min_length=1,
        description=(
            "Orden de cambio que autoriza el trabajo. **Obligatoria**: no hay "
            "extra sin autorización (§11.2). La base lo repite como `CHECK`."
        ),
    )
    cant_base: Decimal = Field(gt=0)
    modo_pago: ModoPago = ModoPago.DESTAJO
    precio_unitario: Decimal = Field(default=Decimal(0), ge=0)
    precio_destajo: Decimal = Field(default=Decimal(0), ge=0)
    concepto_id: UUID | None = None
    frente_id: UUID | None = None
    nivel_id: UUID | None = Field(
        default=None,
        description=(
            "El **frente** donde cae el trabajo (§7.4). Sin él la actividad no "
            "aparece en ningún grupo de la pantalla del residente, que agrupa "
            "por nivel y etapa."
        ),
    )
    etapa_id: UUID | None = Field(
        default=None,
        description="El **sub-frente**: la etapa dentro del nivel (§7.4).",
    )
    duracion_dias: Decimal = Field(default=Decimal(1), gt=0)


class ExtraRespuesta(BaseModel):
    """Lo que quedó dado de alta (§11.2)."""

    id: UUID
    obra_id: UUID
    descripcion: str
    orden_cambio: str
    cant_base: Decimal
    modo_pago: str
    estatus: str = Field(
        description="Nace en `extra_catalogo` y avanza sola al capturar (§8.2)."
    )

    @classmethod
    def desde_dominio(cls, extra_id: UUID, extra: ActividadExtra) -> ExtraRespuesta:
        return cls(
            id=extra_id,
            obra_id=UUID(extra.obra_id),
            descripcion=extra.descripcion,
            orden_cambio=extra.orden_cambio,
            cant_base=extra.cant_base,
            modo_pago=extra.modo_pago.value,
            estatus=extra.estatus.value,
        )


class ActividadDetalleRespuesta(ActividadRespuesta):
    """Lo mismo, más lo que solo interesa al abrirla (§11.2 `GET /actividades/{id}`)."""

    obra_clave: str
    dependencias: list = Field(default_factory=list)
    notas: str | None = None
    orden_cambio: str | None = Field(
        default=None, description="Si es extra-catálogo, la OC que lo autorizó (§11.2)."
    )
    contratista_nombre: str | None = None
    cuadrilla_nombre: str | None = None


@router.get(
    "/torre",
    response_model=list[EstadoDeObraRespuesta],
    summary="Estado de cada obra en el alcance",
)
async def torre_de_control(
    sesion: SesionRLS,
    proyecto_id: FiltroProyecto = None,
    cluster_id: FiltroCluster = None,
    solo_pendientes: Annotated[
        bool,
        Query(
            description=(
                "Solo las obras con algo esperando: incidencia abierta, cierre "
                "por resolver o actividad bloqueada."
            )
        ),
    ] = False,
) -> list[dict]:
    """Una fila por obra visible, con sus contadores (§5.1).

    Agregado a propósito: resolverlo desde el cliente serían cinco peticiones
    por obra, y el §12.1 habla de 60–80 obras activas. El razonamiento completo
    está en el encabezado de `adapters/repos/torre_sql.py`.
    """
    return await RepositorioTorreSQL(sesion).estado_de_obras(
        proyecto_id=proyecto_id,
        cluster_id=cluster_id,
        solo_con_pendientes=solo_pendientes,
    )


@router.get(
    "/obras/{obra_id}/actividades",
    response_model=list[ActividadRespuesta],
    summary="Actividades de una obra",
)
async def actividades_de_obra(
    obra_id: UUID,
    sesion: SesionRLS,
    estatus: Annotated[
        EstatusActividad | None, Query(description="Filtra por estatus (§8.2).")
    ] = None,
    solo_criticas: Annotated[
        bool, Query(description="Solo las de la ruta crítica (§7.5).")
    ] = False,
) -> list[dict]:
    """El detalle de una obra en la Torre (§11.2).

    Una obra fuera del alcance devuelve **lista vacía**, no 404: RLS ya la hizo
    invisible, y un 404 aquí obligaría a una consulta extra solo para
    distinguir "no existe" de "no la ves" — que hacia afuera son lo mismo
    (§12.4).
    """
    return await RepositorioTorreSQL(sesion).actividades_de_obra(
        obra_id,
        estatus=estatus.value if estatus else None,
        solo_criticas=solo_criticas,
    )


class TrabajoDeObraRespuesta(BaseModel):
    """Un destajo (o subcontrato) de la receta de un concepto de la obra, con su cuadrilla.

    Los datos capturados son la cuadrilla y el rendimiento teórico; el calculado, las jornadas por
    unidad y la razón se derivan (`CATALOGOS.md` §10). La cantidad del destajo es la del concepto ×
    `factor`, y la del concepto la pone la pantalla: lo medido en el plano o, si no hay, lo
    presupuestado.
    """

    actividad_id: UUID
    concepto_id: UUID
    concepto_clave: str | None = None
    concepto_descripcion: str | None = None
    concepto_unidad: str | None = None
    cantidad_presupuestada: Decimal | None = None
    insumo_id: UUID
    clave: str
    descripcion: str
    unidad: str | None = None
    precio: Decimal = Field(description="Precio del destajo (costo base).")
    factor: Decimal = Field(description="Unidades del destajo por cada unidad del concepto.")
    categoria: str
    cuadrilla_id: UUID | None = None
    cuadrilla_clave: str | None = None
    cuadrilla_nombre: str | None = None
    costo_cuadrilla: Decimal | None = Field(
        default=None, description="Lo que cuesta una jornada de la cuadrilla."
    )
    rendimiento_teorico: Decimal | None = None
    rendimiento_calculado: Decimal | None = Field(
        default=None, description="Costo de la cuadrilla ÷ precio del destajo."
    )
    jornadas_por_unidad: Decimal | None = None
    razon_teorico_calculado: Decimal | None = None
    origen_rendimiento: str | None = None

    @classmethod
    def desde_fila(cls, fila: dict) -> TrabajoDeObraRespuesta:
        costo = fila.get("costo_cuadrilla")
        precio = fila["precio"]
        calculado = rendimiento_calculado(costo, precio)
        return cls(
            **fila,
            rendimiento_calculado=calculado,
            jornadas_por_unidad=jornadas_por_unidad(costo, precio),
            razon_teorico_calculado=razon_teorico_calculado(
                fila.get("rendimiento_teorico"), calculado
            ),
        )


@router.get(
    "/obras/{obra_id}/trabajos",
    response_model=list[TrabajoDeObraRespuesta],
    summary="Destajos y cuadrillas de los conceptos de una obra",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE, Rol.COSTOS))],
)
async def trabajos_de_obra(obra_id: UUID, sesion: SesionRLS) -> list[TrabajoDeObraRespuesta]:
    """La pestaña Trabajos del cuantificador: por cada concepto de la obra, los destajos de su receta
    con la cuadrilla y el rendimiento de cada uno. Una obra fuera del alcance devuelve lista vacía
    (RLS), igual que sus actividades. Control de obra, Super intendente y Costos: el costo de una
    cuadrilla es del catálogo de costos."""
    filas = await RepositorioTorreSQL(sesion).trabajos_de_obra(obra_id)
    return [TrabajoDeObraRespuesta.desde_fila(f) for f in filas]


@router.get(
    "/actividades/{actividad_id}",
    response_model=ActividadDetalleRespuesta,
    summary="Detalle de una actividad",
    responses={
        404: {"description": "La actividad no existe o está fuera de tu alcance."}
    },
)
async def actividad(actividad_id: UUID, sesion: SesionRLS) -> dict:
    """Una actividad con su programación, su costeo y su contexto (§11.2).

    Aquí sí es 404 y no lista vacía: se pidió **una** cosa concreta y no está.
    Que la causa sea RLS o que no exista es indistinguible a propósito.
    """
    fila = await RepositorioTorreSQL(sesion).actividad(actividad_id)
    if fila is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"La actividad {actividad_id} no existe o está fuera de tu alcance."
            ),
        )
    return fila


@router.post(
    "/actividades",
    response_model=ExtraRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Alta extra-catálogo con orden de cambio",
    # Solo el Residente (§11.2). El dominio lo vuelve a comprobar: aquí el 403
    # es legible, allá la regla queda escrita donde vive.
    dependencies=[Depends(exigir_rol(Rol.RESIDENTE)), Idempotencia],
    responses={
        403: {"description": "Solo el residente da de alta trabajo extra (§11.2)."},
        422: {"description": "Falta la orden de cambio, o el precio no permite estimar."},
    },
)
async def dar_de_alta_extra(
    peticion: DarDeAltaExtraPeticion,
    ctx: ContextoActual,
    caso: DarDeAltaExtraDep,
) -> ExtraRespuesta:
    """Registra trabajo que apareció en obra y no estaba en el prototipo.

    Idempotente porque un doble clic crearía **dos** actividades con la misma
    orden de cambio, y las dos se estimarían: el extra duplicado se paga dos
    veces y nadie lo nota hasta la conciliación.

    La obra viaja en el cuerpo y no en la ruta porque la actividad es el
    recurso que se crea; si esa obra no es visible, la política de `actividad`
    rechaza el INSERT (§12.4) — no hace falta preguntarle antes al repo de
    Obras (§11.1).
    """
    resultado = await caso.ejecutar(
        ComandoDarDeAltaExtra(
            obra_id=peticion.obra_id,
            descripcion=peticion.descripcion,
            orden_cambio=peticion.orden_cambio,
            cant_base=peticion.cant_base,
            rol=Rol(ctx.rol),
            modo_pago=peticion.modo_pago,
            precio_unitario=peticion.precio_unitario,
            precio_destajo=peticion.precio_destajo,
            concepto_id=peticion.concepto_id,
            frente_id=peticion.frente_id,
            nivel_id=peticion.nivel_id,
            etapa_id=peticion.etapa_id,
            duracion_dias=peticion.duracion_dias,
        )
    )
    return ExtraRespuesta.desde_dominio(resultado.id, resultado.actividad)


# --- El precio de un trabajo fuera de catálogo (§11.2, migración 0048) -----


class LineaDeCuadrillaPeticion(BaseModel):
    cuadrilla_id: UUID
    cuadrillas: Decimal = Field(gt=0, description="Cuántas cuadrillas de ésas.")
    dias: Decimal = Field(gt=0, description="Cuántos días las va a tener.")


class LineaDeMaterialPeticion(BaseModel):
    insumo_id: UUID
    cantidad: Decimal = Field(gt=0)


class ArmarPrecioPeticion(BaseModel):
    """Con qué se va a hacer un trabajo que no está en el catálogo.

    El jefe de obra lo describió así: *"el residente dice qué cuadrilla va a
    utilizar, cuántas y el tiempo, también el material, y se crea el precio"*.
    """

    cantidad: Decimal = Field(
        gt=0,
        description=(
            "La cantidad del **trabajo** —30 m² de muro—, no de gente: el "
            "precio unitario es lo que se cobra por unidad de obra."
        ),
    )
    cuadrillas: list[LineaDeCuadrillaPeticion] = Field(default_factory=list)
    materiales: list[LineaDeMaterialPeticion] = Field(default_factory=list)


class PrecioArmadoRespuesta(BaseModel):
    mano_obra: Decimal
    materiales: Decimal
    total: Decimal
    precio_unitario: Decimal
    jornadas: Decimal
    sin_costo: list[str] = Field(
        default_factory=list,
        description=(
            "Lo que se incluyó sin saber cuánto vale. Mientras haya algo aquí "
            "el total está **por debajo** del costo real, y autorizar contra "
            "esa cifra es autorizar de menos."
        ),
    )
    completo: bool


@router.post(
    "/actividades/precio-armado",
    response_model=PrecioArmadoRespuesta,
    summary="Armar el precio de un trabajo fuera de catálogo",
    dependencies=[Depends(exigir_rol(Rol.RESIDENTE, Rol.CONTROL_OBRA))],
    responses={422: {"description": "El precio no se puede armar con eso (§11.2)."}},
)
async def armar_precio_de_extra(
    peticion: ArmarPrecioPeticion, sesion: SesionRLS
) -> PrecioArmadoRespuesta:
    """Calcula sin guardar: es una simulación mientras el residente decide.

    El cálculo vive en el servidor y no en la pantalla a propósito. Los costos
    —jornada de la cuadrilla, costo del insumo— son del catálogo, y mandarlos al
    cliente para que multiplique allá significaría exponer el costo a quien solo
    necesita el precio, y tener la fórmula en dos lugares que un día divergen.
    """
    repo = RepositorioTorreSQL(sesion)
    costos_cuadrilla = await repo.costos_de_cuadrillas(
        [linea.cuadrilla_id for linea in peticion.cuadrillas]
    )
    costos_insumo = await repo.costos_de_insumos(
        [material.insumo_id for material in peticion.materiales]
    )

    precio = armar_precio(
        cantidad=peticion.cantidad,
        cuadrillas=[
            LineaDeCuadrilla(
                cuadrilla_id=str(linea.cuadrilla_id),
                nombre=costos_cuadrilla.get(str(linea.cuadrilla_id), {}).get(
                    "nombre", "(cuadrilla desconocida)"
                ),
                cuadrillas=linea.cuadrillas,
                dias=linea.dias,
                costo_jornada=costos_cuadrilla.get(
                    str(linea.cuadrilla_id), {}
                ).get("costo_jornada"),
            )
            for linea in peticion.cuadrillas
        ],
        materiales=[
            LineaDeMaterial(
                insumo_id=str(material.insumo_id),
                descripcion=costos_insumo.get(str(material.insumo_id), {}).get(
                    "descripcion", "(insumo desconocido)"
                ),
                cantidad=material.cantidad,
                costo=costos_insumo.get(str(material.insumo_id), {}).get("costo"),
            )
            for material in peticion.materiales
        ],
    )

    return PrecioArmadoRespuesta(
        mano_obra=precio.mano_obra,
        materiales=precio.materiales,
        total=precio.total,
        precio_unitario=precio.precio_unitario,
        jornadas=precio.jornadas,
        sin_costo=list(precio.sin_costo),
        completo=precio.completo,
    )
