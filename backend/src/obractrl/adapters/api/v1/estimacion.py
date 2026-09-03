"""Endpoints de estimación semanal.

Spec §11.2 (Estimación) · §11.3 workflow E.

Controladores delgados: validan el DTO, delegan en el caso de uso y mapean
el resultado. **Cero lógica de negocio aquí** (§12.11) — las reglas de
permisos, selección de actividades y transición viven en
`domain.estimacion.reglas`.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    ArmarReporteDeEstimacionDep,
    EnviarEstimacionDep,
    GenerarEstimacionDep,
    ValidarEstimacionDep,
)
from obractrl.adapters.api.dependencias import ContextoActual, SesionRLS, exigir_rol
from obractrl.adapters.api.idempotencia import Idempotencia
from obractrl.adapters.repos.estimaciones_sql import RepositorioEstimacionesSQL
from obractrl.application.casos_uso.exportar_estimacion import EstimacionNoEncontrada
from obractrl.application.casos_uso.gestionar_estimacion import (
    ComandoEnviarEstimacion,
    ComandoGenerarEstimacion,
    ComandoValidarEstimacion,
    EstimacionCreada,
)
from obractrl.domain.estimacion.reglas import Estimacion
from obractrl.domain.reportes.estimacion import por_frente
from obractrl.domain.shared.diccionario import ModoPago, Rol

router = APIRouter(tags=["estimacion"])


class GenerarEstimacionPeticion(BaseModel):
    """Genera la estimación de la semana activa (§11.3 E.1).

    ``modo`` selecciona qué actividades entran: solo las que se pagan de esa
    forma (`actividad.modo_pago`, §6).
    """

    modo: ModoPago
    origen_erp: bool = Field(default=False, description="Metadato de origen (§3.2).")


class EstimacionRespuesta(BaseModel):
    id: UUID
    obra_id: UUID
    folio: str | None
    semana: int
    anio: int
    modo: str
    estatus: str
    monto_total: Decimal
    origen_erp: bool
    creada_por: UUID | None
    validada_por: UUID | None
    n_conceptos: int | None = Field(
        default=None, description="Solo presente justo al generar (§11.3 E.2)."
    )

    @classmethod
    def desde_dominio(cls, estimacion_id: UUID, estimacion: Estimacion) -> EstimacionRespuesta:
        return cls(
            id=estimacion_id,
            obra_id=UUID(estimacion.obra_id),
            folio=str(estimacion.folio) if estimacion.folio else None,
            semana=estimacion.semana,
            anio=estimacion.anio,
            modo=estimacion.modo.value,
            estatus=estimacion.estatus.value,
            monto_total=estimacion.monto_total.monto,
            origen_erp=estimacion.origen_erp,
            creada_por=UUID(estimacion.creada_por) if estimacion.creada_por else None,
            validada_por=UUID(estimacion.validada_por) if estimacion.validada_por else None,
            n_conceptos=len(estimacion.conceptos),
        )

    @classmethod
    def desde_fila(cls, fila: dict) -> EstimacionRespuesta:
        return cls(
            id=fila["id"],
            obra_id=fila["obra_id"],
            folio=fila["folio"],
            semana=fila["semana"],
            anio=fila["anio"],
            modo=fila["modo"],
            estatus=fila["estatus"],
            monto_total=fila["monto_total"],
            origen_erp=fila["origen_erp"],
            creada_por=fila["creada_por"],
            validada_por=fila["validada_por"],
        )


def _resultado(creada: EstimacionCreada) -> EstimacionRespuesta:
    return EstimacionRespuesta.desde_dominio(creada.id, creada.estimacion)


@router.post(
    "/obras/{obra_id}/estimaciones",
    response_model=EstimacionRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Generar la estimación de la semana activa",
    dependencies=[Depends(exigir_rol(Rol.RESIDENTE, Rol.SUPERVISOR)), Idempotencia],
    responses={
        409: {
            "description": (
                "No hay ancla de semana configurada (§3.1), o no hay "
                "actividades validadas para ese modo en la semana."
            )
        },
    },
)
async def generar_estimacion(
    obra_id: UUID,
    peticion: GenerarEstimacionPeticion,
    ctx: ContextoActual,
    caso_uso: GenerarEstimacionDep,
) -> EstimacionRespuesta:
    """Residente o Supervisor generan la estimación (§11.3 E.1-2)."""
    creada = await caso_uso.ejecutar(
        ComandoGenerarEstimacion(
            obra_id=obra_id,
            modo=peticion.modo,
            usuario_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
            origen_erp=peticion.origen_erp,
        )
    )
    return _resultado(creada)


@router.patch(
    "/estimaciones/{estimacion_id}",
    response_model=EstimacionRespuesta,
    summary="Enviar una estimación",
    dependencies=[Depends(exigir_rol(Rol.RESIDENTE, Rol.SUPERVISOR)), Idempotencia],
    responses={
        404: {"description": "La estimación no existe o está fuera de tu alcance."},
        409: {"description": "Transición de estimación no permitida."},
    },
)
async def enviar_estimacion(
    estimacion_id: UUID, ctx: ContextoActual, caso_uso: EnviarEstimacionDep
) -> EstimacionRespuesta:
    """Residente o Supervisor envían la estimación (§11.3 E.3)."""
    fila = await caso_uso.ejecutar(
        ComandoEnviarEstimacion(
            estimacion_id=estimacion_id, usuario_id=ctx.usuario_id, rol=Rol(ctx.rol)
        )
    )
    return EstimacionRespuesta.desde_fila(fila)


@router.post(
    "/estimaciones/{estimacion_id}/validar",
    response_model=EstimacionRespuesta,
    summary="Validar una estimación (bloquea el periodo)",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA)), Idempotencia],
    responses={
        404: {"description": "La estimación no existe o está fuera de tu alcance."},
        409: {"description": "Transición de estimación no permitida."},
    },
)
async def validar_estimacion(
    estimacion_id: UUID, ctx: ContextoActual, caso_uso: ValidarEstimacionDep
) -> EstimacionRespuesta:
    """Control de obra valida la estimación (§11.3 E.4)."""
    fila = await caso_uso.ejecutar(
        ComandoValidarEstimacion(
            estimacion_id=estimacion_id, usuario_id=ctx.usuario_id, rol=Rol(ctx.rol)
        )
    )
    return EstimacionRespuesta.desde_fila(fila)


@router.get(
    "/obras/{obra_id}/estimaciones",
    response_model=list[EstimacionRespuesta],
    summary="Bandeja de estimaciones de una obra",
)
async def listar_estimaciones(obra_id: UUID, sesion: SesionRLS) -> list[EstimacionRespuesta]:
    """Lectura simple sin orquestación de dominio —como `GET /cierres`
    (`adapters/api/v1/cierres.py`)— así que consulta el repo directo: RLS ya
    acota el alcance (§12.4)."""
    repo = RepositorioEstimacionesSQL(sesion)
    filas = await repo.listar(obra_id)
    return [EstimacionRespuesta.desde_fila(fila) for fila in filas]


# --- El detalle: guía de estimación, agrupada por frente (§11.3 E) --------


class ConceptoDelReporteRespuesta(BaseModel):
    actividad_id: str | None = None
    clave: str
    descripcion: str
    unidad: str
    cantidad: Decimal
    precio_unitario: Decimal
    importe: Decimal
    fuera_catalogo: bool
    nivel_id: str | None = None
    nivel_clave: str | None = None
    nivel_descripcion: str | None = None


class FrenteDelReporteRespuesta(BaseModel):
    """Un renglón de «Resumen general»: un frente, cuánto suma y qué
    proporción de la semana es."""

    clave: str
    nombre: str
    conceptos: int
    subtotal: Decimal
    porcentaje: Decimal = Field(description="0–100.")


class EstimacionDetalleRespuesta(BaseModel):
    """La guía de estimación completa: cabecera, renglones y el resumen por
    frente, en una sola lectura (§11.3 E).

    No es un job como el `.xlsx`: armar el reporte es una consulta barata —
    unos cuantos `select`—, así que se sirve síncrono. El Excel sigue siendo
    un job porque *dibujarlo* con openpyxl sí es trabajo que conviene sacar de
    la petición.
    """

    id: UUID
    folio: str | None
    obra_id: UUID
    obra_clave: str
    semana: int
    anio: int
    modo: str
    estatus: str
    monto_total: Decimal = Field(description="Lo que dice la cabecera guardada.")
    monto_calculado: Decimal = Field(description="Σ de los renglones, recalculada al leer.")
    cuadra: bool = Field(
        description="¿Cabecera y renglones coinciden? Falso es una señal de auditoría, no un error de captura."
    )
    conceptos: list[ConceptoDelReporteRespuesta]
    n_conceptos_catalogo: int
    n_conceptos_extra: int
    por_frente: list[FrenteDelReporteRespuesta]
    acumulado_proyecto: Decimal = Field(
        description="Suma de lo enviado y validado de esta obra a la fecha. No incluye borradores."
    )
    presupuesto_base: Decimal | None = Field(
        default=None,
        description="El presupuesto vigente del prototipo de la obra. `null` si el prototipo no tiene uno cargado.",
    )


@router.get(
    "/estimaciones/{estimacion_id}",
    response_model=EstimacionDetalleRespuesta,
    summary="La guía de estimación: renglones y resumen por frente",
    dependencies=[
        Depends(
            exigir_rol(
                Rol.RESIDENTE, Rol.SUPERVISOR, Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE
            )
        )
    ],
    responses={404: {"description": "La estimación no existe o está fuera de tu alcance."}},
)
async def detalle_de_estimacion(
    estimacion_id: UUID,
    sesion: SesionRLS,
    caso_uso: ArmarReporteDeEstimacionDep,
) -> EstimacionDetalleRespuesta:
    """La pantalla que reemplaza abrir el `.xlsx` para ver qué lleva la
    semana: mismo reporte que arma el job de exportación
    (`ArmarReporteDeEstimacion`), con el resumen por frente que en el Excel
    es una hoja aparte y aquí es la vista de entrada.
    """
    try:
        reporte = await caso_uso.ejecutar(estimacion_id)
    except EstimacionNoEncontrada as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error

    repo = RepositorioEstimacionesSQL(sesion)
    acumulado = await repo.acumulado_de(reporte.obra_id)
    base = await repo.presupuesto_base_de(reporte.obra_id)

    return EstimacionDetalleRespuesta(
        id=UUID(reporte.id),
        folio=reporte.folio,
        obra_id=UUID(reporte.obra_id),
        obra_clave=reporte.obra_clave,
        semana=reporte.semana,
        anio=reporte.anio,
        modo=reporte.modo.value,
        estatus=reporte.estatus.value,
        monto_total=reporte.monto_total.monto,
        monto_calculado=reporte.monto_calculado.monto,
        cuadra=reporte.cuadra,
        conceptos=[
            ConceptoDelReporteRespuesta(
                actividad_id=c.actividad_id or None,
                clave=c.clave,
                descripcion=c.descripcion,
                unidad=c.unidad,
                cantidad=c.cantidad,
                precio_unitario=c.precio_unitario.monto,
                importe=c.importe.monto,
                fuera_catalogo=c.fuera_catalogo,
                nivel_id=c.nivel_id,
                nivel_clave=c.nivel_clave,
                nivel_descripcion=c.nivel_descripcion,
            )
            for c in reporte.conceptos
        ],
        n_conceptos_catalogo=sum(1 for c in reporte.conceptos if not c.fuera_catalogo),
        n_conceptos_extra=sum(1 for c in reporte.conceptos if c.fuera_catalogo),
        por_frente=[
            FrenteDelReporteRespuesta(
                clave=f.clave,
                nombre=f.nombre,
                conceptos=f.conceptos,
                subtotal=f.subtotal.monto,
                porcentaje=f.porcentaje,
            )
            for f in por_frente(reporte)
        ],
        acumulado_proyecto=acumulado,
        presupuesto_base=base,
    )
