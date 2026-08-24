"""Presupuesto y rendimientos (§11.2, §5.1, §7.3).

Un área entera del §5.1 —«Presupuesto de obras» y «Rendimientos» en el sidebar
de Control de obra y de Super intendente— que tenía sus tablas con RLS desde la
migración 0006 y **ni un repositorio ni un endpoint**.

## Solo lectura, y no por falta de tiempo

El presupuesto entra por **carga de Excel** (`TipoCarga.presupuesto`, §10) y se
versiona ahí (§10.8). Un `POST /presupuestos` que dejara capturarlo a mano
abriría un segundo camino de alta con otro versionado y otra reversa, para el
mismo dato. Lo que faltaba era poder **leerlo y compararlo**, que es lo que hace
este módulo.

## Quién

`exigir_rol(C, SI)`: el §5.1 pone estas dos entradas solo en esos dos sidebars.
Es RBAC del borde y no RLS, porque `presupuesto` es **catálogo** —alcance de
organización— y acotarlo por rol en la política cambiaría el alcance de todo lo
demás que vive en ese array. La razón está escrita en el encabezado de
`adapters/repos/presupuestos_sql.py`.

Los rendimientos por obra sí quedan acotados por RLS: la consulta arranca en
`obra`, que trae su alcance por rol.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.dependencias import SesionRLS, exigir_rol
from obractrl.adapters.repos.presupuestos_sql import RepositorioPresupuestosSQL
from obractrl.domain.presupuesto.rendimiento import UMBRAL_DESVIACION, desviacion_de
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["presupuesto"])

CONSULTA_PRESUPUESTO = Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE))
"""«Presupuesto de obras» y «Rendimientos» son de C y SI (§5.1)."""

Umbral = Annotated[
    Decimal | None,
    Query(
        description=(
            "Porcentaje a partir del cual una desviación se marca (§3.6). Es "
            "configurable por organización; sin él se usa el default."
        )
    ),
]


class PartidaRespuesta(BaseModel):
    id: UUID
    concepto_id: UUID | None = None
    concepto_clave: str | None = None
    concepto_descripcion: str | None = None
    unidad_clave: str | None = None
    prototipo_nodo_id: UUID | None = None
    cantidad: Decimal
    precio_unitario: Decimal
    importe: Decimal
    orden: int


class PresupuestoRespuesta(BaseModel):
    """El presupuesto vigente del prototipo que la obra instancia (§7.3)."""

    id: UUID
    prototipo_id: UUID
    prototipo_clave: str
    prototipo_nombre: str | None = None
    version: int
    origen: str
    monto_total: Decimal
    created_at: datetime
    partidas: list[PartidaRespuesta]


class VersionRespuesta(BaseModel):
    id: UUID
    version: int
    vigente: bool
    origen: str
    carga_id: UUID | None = None
    monto_total: Decimal
    created_at: datetime


class RendimientoPorConceptoRespuesta(BaseModel):
    """Presupuestado contra ejecutado, concepto por concepto (§5.1)."""

    concepto_id: UUID | None = None
    concepto_clave: str | None = None
    concepto_descripcion: str | None = None
    unidad_clave: str | None = None

    cantidad_presupuestada: Decimal
    importe_presupuestado: Decimal
    cantidad_ejecutada: Decimal
    importe_ejecutado: Decimal

    desviacion_importe: Decimal = Field(
        description="Ejecutado menos presupuestado. Positivo es gastar de más."
    )
    desviacion_pct: Decimal | None = Field(
        default=None,
        description=(
            "`null` cuando no había presupuesto: dividir entre cero no da "
            "infinito, da que la pregunta no aplica."
        ),
    )
    clasificacion: str = Field(
        description=(
            "sin_presupuesto | no_ejecutado | sobre_costo | bajo_costo | "
            "dentro_de_rango. `no_ejecutado` no es un ahorro: es trabajo que no "
            "se hizo."
        )
    )
    extra: bool = Field(
        default=False, description="Incluye alta extra-catálogo (§11.2)."
    )


class RendimientoPorCuadrillaRespuesta(BaseModel):
    """Lo que produjo cada cuadrilla (§5.1).

    Sin contraparte presupuestada: el presupuesto es por concepto y no reparte
    el trabajo entre cuadrillas. Lo comparable es su `rendimiento` de catálogo.
    """

    cuadrilla_id: UUID
    cuadrilla_clave: str
    cuadrilla_nombre: str
    contratista_nombre: str | None = None
    rendimiento_esperado: Decimal | None = None
    actividades: int
    concluidas: int
    cantidad_ejecutada: Decimal | None = None
    importe_ejecutado: Decimal | None = None


class ResumenDeObraRespuesta(BaseModel):
    """Un renglón de «Presupuesto de obras» (§5.1)."""

    obra_id: UUID
    obra_clave: str
    obra_estatus: str
    avance_pct: Decimal
    es_urba: bool = Field(
        description=(
            "Una obra URBA no tiene prototipo y por lo tanto no tiene "
            "presupuesto (§7.2). Aparece con cero, no desaparece."
        )
    )
    prototipo_clave: str | None = None
    cluster_clave: str
    proyecto_clave: str
    proyecto_id: UUID

    monto_presupuestado: Decimal
    monto_ejecutado: Decimal
    desviacion_importe: Decimal
    desviacion_pct: Decimal | None = None
    clasificacion: str
    actividades: int


def _con_desviacion(
    fila: dict, *, presupuestado: str, ejecutado: str, umbral: Decimal
) -> dict:
    """Agrega la desviación calculada por el dominio a una fila del repo."""
    desviacion = desviacion_de(
        importe_presupuestado=Decimal(str(fila[presupuestado] or 0)),
        importe_ejecutado=Decimal(str(fila[ejecutado] or 0)),
        umbral=umbral,
    )
    return {
        **fila,
        "desviacion_importe": desviacion.importe,
        "desviacion_pct": desviacion.porcentaje,
        "clasificacion": desviacion.clasificacion,
    }


@router.get(
    "/obras/{obra_id}/presupuesto",
    response_model=PresupuestoRespuesta,
    summary="Presupuesto vigente de la obra",
    dependencies=[CONSULTA_PRESUPUESTO],
    responses={
        404: {
            "description": (
                "La obra no existe, está fuera de tu alcance, es URBA —sin "
                "prototipo— o su prototipo no tiene presupuesto cargado."
            )
        }
    },
)
async def presupuesto_de_obra(
    obra_id: UUID, sesion: SesionRLS
) -> PresupuestoRespuesta:
    """El presupuesto del **prototipo** que la obra instancia (§7.3).

    Una obra no tiene presupuesto propio: lo tiene el modelo de vivienda, y
    todas las obras que lo instancian comparten el mismo.
    """
    repo = RepositorioPresupuestosSQL(sesion)
    cabecera = await repo.presupuesto_de_obra(obra_id)
    if cabecera is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No hay presupuesto para la obra {obra_id}: no existe, está "
                f"fuera de tu alcance, es URBA o su prototipo aún no tiene uno "
                f"cargado (§10)."
            ),
        )
    partidas = await repo.partidas(UUID(str(cabecera["id"])))
    return PresupuestoRespuesta(**cabecera, partidas=partidas)  # type: ignore[arg-type]


@router.get(
    "/prototipos/{prototipo_id}/presupuesto",
    response_model=PresupuestoRespuesta,
    summary="Presupuesto vigente del prototipo",
    dependencies=[CONSULTA_PRESUPUESTO],
    responses={
        404: {
            "description": (
                "El prototipo no existe, está fuera de tu alcance, o todavía "
                "no tiene un presupuesto cargado (§10)."
            )
        }
    },
)
async def presupuesto_de_prototipo(
    prototipo_id: UUID, sesion: SesionRLS
) -> PresupuestoRespuesta:
    """El mismo presupuesto que `GET /obras/{id}/presupuesto`, pero sin pasar
    por una obra — para pantallas que ya están paradas sobre el prototipo
    (el árbol de Prototipos, Programas base) y no tienen una obra a mano."""
    repo = RepositorioPresupuestosSQL(sesion)
    cabecera = await repo.vigente_de_prototipo(prototipo_id)
    if cabecera is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No hay presupuesto para el prototipo {prototipo_id}: no "
                f"existe, está fuera de tu alcance, o todavía no tiene uno "
                f"cargado (§10)."
            ),
        )
    partidas = await repo.partidas(UUID(str(cabecera["id"])))
    return PresupuestoRespuesta(**cabecera, partidas=partidas)  # type: ignore[arg-type]


@router.get(
    "/prototipos/{prototipo_id}/presupuestos",
    response_model=list[VersionRespuesta],
    summary="Historial de versiones del presupuesto",
    dependencies=[CONSULTA_PRESUPUESTO],
)
async def versiones_de_presupuesto(
    prototipo_id: UUID, sesion: SesionRLS
) -> list[dict]:
    """Qué versión estuvo vigente y de qué carga vino (§10.8)."""
    return await RepositorioPresupuestosSQL(sesion).versiones_de_prototipo(
        prototipo_id
    )


@router.get(
    "/obras/{obra_id}/rendimientos",
    response_model=list[RendimientoPorConceptoRespuesta],
    summary="Presupuestado contra ejecutado, por concepto",
    dependencies=[CONSULTA_PRESUPUESTO],
)
async def rendimientos_de_obra(
    obra_id: UUID, sesion: SesionRLS, umbral: Umbral = None
) -> list[dict]:
    """El comparativo de la obra (§5.1).

    Incluye los conceptos **presupuestados y no ejecutados** y los **ejecutados
    sin presupuestar** —los extra-catálogo—: sin ellos el comparativo escondería
    justo lo que explica por qué la obra costó lo que costó.
    """
    filas = await RepositorioPresupuestosSQL(sesion).rendimiento_por_concepto(obra_id)
    tope = umbral if umbral is not None else UMBRAL_DESVIACION
    return [
        _con_desviacion(
            fila,
            presupuestado="importe_presupuestado",
            ejecutado="importe_ejecutado",
            umbral=tope,
        )
        for fila in filas
    ]


@router.get(
    "/obras/{obra_id}/rendimientos/cuadrillas",
    response_model=list[RendimientoPorCuadrillaRespuesta],
    summary="Lo ejecutado por cada cuadrilla",
    dependencies=[CONSULTA_PRESUPUESTO],
)
async def rendimientos_por_cuadrilla(obra_id: UUID, sesion: SesionRLS) -> list[dict]:
    """Qué produjo cada cuadrilla en esta obra (§5.1)."""
    return await RepositorioPresupuestosSQL(sesion).rendimiento_por_cuadrilla(obra_id)


@router.get(
    "/presupuestos/obras",
    response_model=list[ResumenDeObraRespuesta],
    summary="Presupuesto contra ejecutado, obra por obra",
    dependencies=[CONSULTA_PRESUPUESTO],
)
async def presupuesto_de_obras(
    sesion: SesionRLS,
    proyecto_id: Annotated[
        UUID | None, Query(description="Acota a un proyecto.")
    ] = None,
    umbral: Umbral = None,
) -> list[dict]:
    """La pantalla «Presupuesto de obras» (§5.1).

    Arranca en `obra`, así que el alcance por rol lo impone RLS: un Control de
    obra compara las obras de sus proyectos y nada más.
    """
    filas = await RepositorioPresupuestosSQL(sesion).resumen_por_obra(
        proyecto_id=proyecto_id
    )
    tope = umbral if umbral is not None else UMBRAL_DESVIACION
    return [
        _con_desviacion(
            fila,
            presupuestado="monto_presupuestado",
            ejecutado="monto_ejecutado",
            umbral=tope,
        )
        for fila in filas
    ]
