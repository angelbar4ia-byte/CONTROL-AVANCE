"""Endpoints de evaluación de desempeño.

Spec §11.2 (Evaluación) · §11.3 workflow H · §6.

Controladores delgados: validan el DTO, delegan en el caso de uso y mapean
el resultado. **Cero lógica de negocio aquí** (§12.11) — las reglas de
permisos por nivel viven en `domain.evaluaciones.reglas`.

`POST /evaluaciones` no trae una guarda `exigir_rol` fija: el nivel
(auto/control/final) sale del body, no de la ruta, y cada nivel lo puede
crear un rol distinto (§11.2: "auto R · control C · final SI"). Fijar un solo
rol en el endpoint obligaría a tres rutas distintas para lo que el dominio ya
resuelve con un único `Evaluacion.crear` — así que el endpoint deja pasar
cualquier rol autenticado y es el dominio quien decide, igual que
`SolicitudCierre.solicitar` valida `rol=Residente` puertas adentro en vez de
en el router.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import AgregarRespuestasDep, CrearEvaluacionDep
from obractrl.adapters.api.dependencias import ContextoActual, SesionRLS, exigir_rol
from obractrl.adapters.repos.evaluaciones_sql import RepositorioEvaluacionesSQL
from obractrl.application.casos_uso.gestionar_evaluacion import (
    ComandoAgregarRespuestas,
    ComandoCrearEvaluacion,
    RespuestaEntrada,
)
from obractrl.domain.evaluaciones.reglas import Evaluacion
from obractrl.domain.shared.diccionario import NivelEvaluacion, Rol, SujetoEvaluacion

router = APIRouter(tags=["evaluaciones"])

FiltroNivel = Annotated[
    NivelEvaluacion | None, Query(description="Filtra por nivel (§8.2).")
]
FiltroSujetoTipo = Annotated[
    SujetoEvaluacion | None, Query(description="Filtra por sujeto evaluado (§8.2).")
]
FiltroAplicaA = Annotated[
    SujetoEvaluacion | None,
    Query(description="Filtra el catálogo por sujeto al que aplica (§7.8)."),
]


class CrearEvaluacionPeticion(BaseModel):
    """Alta de una evaluación en el nivel indicado (§11.3 H)."""

    nivel: NivelEvaluacion
    sujeto_tipo: SujetoEvaluacion
    sujeto_id: UUID
    periodo: str = Field(min_length=1, description="'WWYY' o 'YYYY-MM' (§7.8).")
    obra_id: UUID | None = Field(
        default=None,
        description=(
            "Obra a la que pertenece la evaluación. Para sujeto_tipo=obra es, "
            "por definición, el mismo id que sujeto_id si se omite."
        ),
    )


class RespuestaItem(BaseModel):
    criterio_id: UUID
    valor: Decimal = Field(ge=0)
    comentario: str | None = None


class AgregarRespuestasPeticion(BaseModel):
    respuestas: list[RespuestaItem] = Field(min_length=1)


class EvaluacionRespuesta(BaseModel):
    id: UUID
    sujeto_tipo: str
    sujeto_id: UUID
    obra_id: UUID | None
    evaluador_id: UUID
    nivel: str
    periodo: str
    puntaje: Decimal | None
    comentarios: str | None
    respuestas: list[RespuestaItem] = Field(default_factory=list)

    @classmethod
    def desde_dominio(cls, evaluacion_id: UUID, evaluacion: Evaluacion) -> EvaluacionRespuesta:
        return cls(
            id=evaluacion_id,
            sujeto_tipo=evaluacion.sujeto_tipo.value,
            sujeto_id=UUID(evaluacion.sujeto_id),
            obra_id=UUID(evaluacion.obra_id) if evaluacion.obra_id else None,
            evaluador_id=UUID(evaluacion.evaluador_id),
            nivel=evaluacion.nivel.value,
            periodo=evaluacion.periodo,
            puntaje=evaluacion.puntaje,
            comentarios=evaluacion.comentarios,
            respuestas=[
                RespuestaItem(
                    criterio_id=UUID(respuesta.criterio_id),
                    valor=respuesta.valor,
                    comentario=respuesta.comentario,
                )
                for respuesta in evaluacion.respuestas
            ],
        )

    @classmethod
    def desde_fila(cls, fila: dict) -> EvaluacionRespuesta:
        return cls(
            id=fila["id"],
            sujeto_tipo=fila["sujeto_tipo"],
            sujeto_id=fila["sujeto_id"],
            obra_id=fila["obra_id"],
            evaluador_id=fila["evaluador_id"],
            nivel=fila["nivel"],
            periodo=fila["periodo"],
            puntaje=fila["puntaje"],
            comentarios=fila["comentarios"],
        )


class CriterioRespuesta(BaseModel):
    id: UUID
    aplica_a: str
    clave: str
    nombre: str
    peso: Decimal
    estatus: str

    @classmethod
    def desde_fila(cls, fila: dict) -> CriterioRespuesta:
        return cls(
            id=fila["id"],
            aplica_a=fila["aplica_a"],
            clave=fila["clave"],
            nombre=fila["nombre"],
            peso=fila["peso"],
            estatus=fila["estatus"],
        )


@router.post(
    "/evaluaciones",
    response_model=EvaluacionRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una evaluación (auto R · control C · final SI)",
    responses={
        404: {"description": "La obra referida no existe o está fuera de tu alcance."},
        422: {"description": "El rol no puede crear ese nivel, o el sujeto no aplica (§6)."},
    },
)
async def crear_evaluacion(
    peticion: CrearEvaluacionPeticion,
    ctx: ContextoActual,
    caso_uso: CrearEvaluacionDep,
) -> EvaluacionRespuesta:
    """Crea una evaluación en el nivel pedido; el dominio valida el permiso
    del rol para ese nivel y, en `nivel=auto`, que el sujeto sea el propio
    Residente o su propia obra (§11.3 H)."""
    creada = await caso_uso.ejecutar(
        ComandoCrearEvaluacion(
            nivel=peticion.nivel,
            evaluador_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
            sujeto_tipo=peticion.sujeto_tipo,
            sujeto_id=peticion.sujeto_id,
            periodo=peticion.periodo,
            obra_id=peticion.obra_id,
        )
    )
    return EvaluacionRespuesta.desde_dominio(creada.id, creada.evaluacion)


@router.post(
    "/evaluaciones/{evaluacion_id}/respuestas",
    response_model=EvaluacionRespuesta,
    summary="Registrar respuestas de una evaluación",
    responses={
        404: {"description": "La evaluación no existe o está fuera de tu alcance."},
        409: {"description": "Respuesta inválida o criterio ya respondido (§7.8)."},
    },
)
async def agregar_respuestas(
    evaluacion_id: UUID,
    peticion: AgregarRespuestasPeticion,
    ctx: ContextoActual,
    caso_uso: AgregarRespuestasDep,
) -> EvaluacionRespuesta:
    """Adjunta respuestas contra el catálogo de criterios; solo quien creó
    la evaluación puede responderla (§7.8)."""
    evaluacion = await caso_uso.ejecutar(
        ComandoAgregarRespuestas(
            evaluacion_id=evaluacion_id,
            usuario_id=ctx.usuario_id,
            respuestas=[
                RespuestaEntrada(
                    criterio_id=item.criterio_id,
                    valor=item.valor,
                    comentario=item.comentario,
                )
                for item in peticion.respuestas
            ],
        )
    )
    return EvaluacionRespuesta.desde_dominio(evaluacion_id, evaluacion)


@router.get(
    "/evaluaciones",
    response_model=list[EvaluacionRespuesta],
    summary="Bandeja de evaluaciones por rol",
)
async def listar_evaluaciones(
    sesion: SesionRLS,
    nivel: FiltroNivel = None,
    sujeto_tipo: FiltroSujetoTipo = None,
) -> list[EvaluacionRespuesta]:
    """Bandeja de evaluaciones visibles para el rol actual.

    Lectura simple sin orquestación de dominio —como `GET /cierres`
    (`adapters/api/v1/cierres.py`)—: consulta el repo directo, sin caso de
    uso, porque RLS ya acota el alcance (§12.4).
    """
    repo = RepositorioEvaluacionesSQL(sesion)
    filas = await repo.listar(
        nivel=nivel.value if nivel else None,
        sujeto_tipo=sujeto_tipo.value if sujeto_tipo else None,
    )
    return [EvaluacionRespuesta.desde_fila(fila) for fila in filas]


@router.get(
    "/criterios-evaluacion",
    response_model=list[CriterioRespuesta],
    summary="Catálogo de criterios de evaluación",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA))],
)
async def listar_criterios(
    sesion: SesionRLS, aplica_a: FiltroAplicaA = None
) -> list[CriterioRespuesta]:
    """Catálogo `criterio_evaluacion` vigente (§11.2, §8.7 semilla editable)."""
    repo = RepositorioEvaluacionesSQL(sesion)
    filas = await repo.listar_criterios(aplica_a=aplica_a.value if aplica_a else None)
    return [CriterioRespuesta.desde_fila(fila) for fila in filas]
