"""Endpoints de planeación por obra (§8.3, §11.2, §11.3).

Contestan la pregunta del jefe de obra —*"cuántas cuadrillas necesito para
alcanzar la meta programada por frente"*— y guardan quién lleva cada frente.

Controlador delgado (§12.11): la división vive en
`domain.planeacion.cuadrillas` y el reparto sobre los periodos en
`domain.insumos.programado`.

## Quién planifica

El residente. El programa base es una guía y quien decide con qué gente se
cumple es quien está en la obra; el supervisor y Control entran porque ven las
mismas obras y a veces contratan ellos. **RLS acota** a las obras de cada uno
(`app.obra_visible`, migración 0042), así que la guarda de rol solo evita
ofrecérselo a quien no planifica.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    AsignarFrenteDeObraDep,
    ConsultarPlaneacionDep,
)
from obractrl.adapters.api.dependencias import exigir_rol
from obractrl.application.casos_uso.consultar_planeacion import (
    ComandoAsignarFrente,
    ComandoPlaneacion,
    PlaneacionDeObra,
)
from obractrl.domain.shared.diccionario import Rol, TipoSemana

router = APIRouter(tags=["planeacion"])

PLANIFICA = Depends(
    exigir_rol(Rol.RESIDENTE, Rol.SUPERVISOR, Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE)
)
"""Quién planifica su obra (§4). RLS decide **cuáles** son las suyas."""

_SIN_CALENDARIO: dict[int | str, dict[str, Any]] = {
    404: {
        "description": (
            "El rango cae en años sin calendario generado (§3.1) o la obra no "
            "está en tu alcance (§12.4)."
        )
    }
}


class PeriodoRespuesta(BaseModel):
    clave: str
    desde: date
    hasta: date = Field(description="Exclusivo: el día siguiente al último.")
    etiqueta: str
    dias_habiles: int = Field(
        description=(
            "Días que se trabajan en el periodo, según el calendario del "
            "cronograma de la obra (§7.5). Es el divisor de la cuenta."
        )
    )


class OficioDeFrenteRespuesta(BaseModel):
    """Cómo se reparte por oficio lo que un frente pide (§8.3, migración 0047).

    El frente solo es demasiado grueso para contratar: en la obra real OBRA
    concentra el 90% de las jornadas, y nadie contrata "noventa por ciento de la
    obra". Partido por oficio, cada renglón ya es algo que se le pide a alguien.
    """

    especialidad_id: str
    clave: str
    nombre: str = Field(
        description=(
            "«Sin oficio» en los conceptos a los que todavía no se les capturó "
            "especialidad. No se descartan: la suma de los oficios es el frente."
        )
    )
    jornadas: list[float]
    cuadrillas: list[float]
    total_jornadas: float
    pico_cuadrillas: float


class FrenteDeObraRespuesta(BaseModel):
    frente_id: str = Field(
        description="Vacío en el renglón que agrupa lo que no tiene frente."
    )
    frente_clave: str
    frente_nombre: str
    jornadas: list[float] = Field(
        description="Una por periodo. Una jornada es una cuadrilla un día."
    )
    cuadrillas: list[float] = Field(
        description=(
            "Cuadrillas que hacen falta en cada periodo. **Sin redondear**: "
            "2.3 dice que dos aprietan y tres sobran, y redondear escondería "
            "esa lectura justo donde se decide."
        )
    )
    total_jornadas: float
    pico_cuadrillas: float = Field(
        description=(
            "La semana más cargada. Es la cifra con la que se contrata: quien "
            "presta dos cuadrillas todo el mes no resuelve la que pide cinco."
        )
    )
    contratista_id: str | None = None
    contratista_nombre: str | None = None
    cuadrillas_plan: int | None = Field(
        default=None,
        description=(
            "Lo que el residente **decidió**, al lado de lo que el cálculo "
            "sugiere. Vacío = todavía no lo decide."
        ),
    )
    notas: str | None = None
    oficios: list[OficioDeFrenteRespuesta] = Field(
        default_factory=list,
        description="Desglose por oficio, de mayor a menor pico. Suma el frente.",
    )


class PlaneacionRespuesta(BaseModel):
    periodos: list[PeriodoRespuesta]
    frentes: list[FrenteDeObraRespuesta]


class AsignarFrentePeticion(BaseModel):
    """El trato de un frente en una obra.

    Los tres campos se escriben aunque vengan nulos: vaciar el contratista
    —"ya no sé quién lo lleva"— es un cambio tan válido como ponerlo.
    """

    contratista_id: UUID | None = None
    cuadrillas_plan: int | None = Field(default=None, ge=0)
    notas: str | None = None


@router.get(
    "/obras/{obra_id}/planeacion/frentes",
    response_model=PlaneacionRespuesta,
    summary="Cuántas cuadrillas pide cada frente, y quién lo lleva",
    dependencies=[PLANIFICA],
    responses=_SIN_CALENDARIO,
)
async def planeacion_por_frente(
    obra_id: UUID,
    caso_uso: ConsultarPlaneacionDep,
    desde: Annotated[date, Query(description="Primer día del rango.")],
    hasta: Annotated[date, Query(description="Último día del rango.")],
    granularidad: Annotated[
        str, Query(pattern="^(semana|mes)$", description="Columna por semana o mes.")
    ] = "semana",
    tipo_semana: TipoSemana = TipoSemana.ORDINARIA,
) -> PlaneacionRespuesta:
    """La vista con la que se contrata (§8.3).

    Las jornadas salen del programa por el APU; las cuadrillas, de dividirlas
    entre los días hábiles del periodo. Lo que ya se decidió viaja al lado, sin
    sustituir a la sugerencia: la sugerencia sale de un rendimiento del
    catálogo y la decisión la toma quien conoce al contratista.
    """
    return _respuesta(
        await caso_uso.ejecutar(
            ComandoPlaneacion(
                obra_id=obra_id,
                desde=desde,
                hasta=hasta,
                granularidad=granularidad,
                tipo_semana=tipo_semana,
            )
        )
    )


@router.put(
    "/obras/{obra_id}/planeacion/frentes/{frente_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Quién lleva este frente en esta obra",
    dependencies=[PLANIFICA],
    responses=_SIN_CALENDARIO,
)
async def asignar_frente(
    obra_id: UUID,
    frente_id: UUID,
    peticion: AsignarFrentePeticion,
    caso_uso: AsignarFrenteDeObraDep,
) -> None:
    """Idempotente por el par obra-frente: asignarlo dos veces es cambiar de
    contratista, no crear un segundo trato (§8.3)."""
    await caso_uso.ejecutar(
        ComandoAsignarFrente(
            obra_id=obra_id,
            frente_id=frente_id,
            contratista_id=peticion.contratista_id,
            cuadrillas_plan=peticion.cuadrillas_plan,
            notas=peticion.notas,
        )
    )


def _respuesta(planeacion: PlaneacionDeObra) -> PlaneacionRespuesta:
    return PlaneacionRespuesta(
        periodos=[
            PeriodoRespuesta(
                clave=periodo.clave,
                desde=periodo.desde,
                hasta=periodo.hasta,
                etiqueta=periodo.etiqueta,
                dias_habiles=habiles,
            )
            for periodo, habiles in zip(
                planeacion.periodos, planeacion.dias_habiles, strict=True
            )
        ],
        frentes=[
            FrenteDeObraRespuesta(
                frente_id=fila.frente_id,
                frente_clave=fila.frente_clave,
                frente_nombre=fila.frente_nombre,
                jornadas=[float(j) for j in fila.demanda.jornadas],
                cuadrillas=[float(c) for c in fila.demanda.cuadrillas],
                total_jornadas=float(fila.demanda.total_jornadas),
                pico_cuadrillas=float(fila.demanda.pico_cuadrillas),
                contratista_id=fila.contratista_id,
                contratista_nombre=fila.contratista_nombre,
                cuadrillas_plan=fila.cuadrillas_plan,
                notas=fila.notas,
                oficios=[
                    OficioDeFrenteRespuesta(
                        especialidad_id=oficio.especialidad_id,
                        clave=oficio.clave,
                        nombre=oficio.nombre,
                        jornadas=[float(j) for j in oficio.demanda.jornadas],
                        cuadrillas=[float(c) for c in oficio.demanda.cuadrillas],
                        total_jornadas=float(oficio.demanda.total_jornadas),
                        pico_cuadrillas=float(oficio.demanda.pico_cuadrillas),
                    )
                    for oficio in fila.oficios
                ],
            )
            for fila in planeacion.frentes
        ],
    )
