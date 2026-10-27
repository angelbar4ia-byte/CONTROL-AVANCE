"""Endpoints de las mediciones: la capa sombra del cuantificador (migración 0088).

Controladores delgados: validan el DTO y delegan en `application.casos_uso.mediciones`.
Una medición agrupa trazos de un tipo (área, lineal o conteo) sin depender de ningún concepto y se
asigna después a uno o varios; asignar crea los enlaces de sus trazos y los de sus submediciones.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import GestionarElementosDep, GestionarMedicionesDep
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.adapters.api.v1.cuantificacion import (
    ROLES_QUE_TRAZAN,
    ResultadoRecalculoRespuesta,
)
from obractrl.application.casos_uso.elementos import ComandoCrearElemento
from obractrl.application.casos_uso.mediciones import (
    ComandoCrearAsignacion,
    ComandoCrearMedicion,
)
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["mediciones"])

TipoDeMedicion = Literal["area", "lineal", "conteo"]
MedidaDeAsignacion = Literal["area", "perimetro", "longitud", "conteo"]

_UNIDAD = {"area": "m²", "lineal": "m", "conteo": "pza"}


class AsignacionRespuesta(BaseModel):
    id: UUID
    actividad_id: UUID
    concepto_clave: str
    descripcion: str
    matriz_concepto_id: UUID | None = None
    matriz_clave: str | None = None
    medida: str
    factor: Decimal
    usa_peso: bool = Field(default=False, description="El factor es el peso del elemento de la medición (kg o ton).")


class ElementoDeMedicion(BaseModel):
    id: UUID
    nombre: str
    peso_kg: Decimal


class MedicionRespuesta(BaseModel):
    id: UUID
    parent_id: UUID | None = None
    nombre: str
    tipo: TipoDeMedicion
    orden: int
    n_trazos: int = Field(description="Trazos de la medición y de sus submediciones.")
    valor: Decimal = Field(
        description="Lo que miden esos trazos: m² (área), m (lineal) o piezas (conteo), ya con la escala del plano."
    )
    unidad: str
    elemento: ElementoDeMedicion | None = Field(
        default=None, description="El elemento con peso de esta medición (0089); alimenta conceptos en kg o ton."
    )
    asignaciones: list[AsignacionRespuesta]


class MedicionPeticion(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    tipo: TipoDeMedicion
    parent_id: UUID | None = Field(
        default=None, description="La medición que la contiene; del mismo tipo (espacios de una losa)."
    )


class MedicionCreada(BaseModel):
    id: UUID


class RenombrarPeticion(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)


class AsignacionPeticion(BaseModel):
    actividad_id: UUID
    matriz_concepto_id: UUID | None = None
    medida: MedidaDeAsignacion
    factor: Decimal = Field(default=Decimal(1), gt=0)
    usar_peso: bool = Field(
        default=False,
        description=(
            "El factor es el peso del elemento de la medición, convertido a la unidad del concepto (kg o "
            "ton): la medición derivada. Si cambia el peso, la asignación se rehace sola."
        ),
    )


class AsignacionCreada(BaseModel):
    id: UUID | None
    trazos_enlazados: int = Field(description="Trazos a los que se les creó (o quitó) el enlace.")
    recalculos: list[ResultadoRecalculoRespuesta]


class TrazoEnMedicionPeticion(BaseModel):
    medicion_id: UUID | None = Field(default=None, description="`null` saca el trazo de su medición.")


class TrazoEnMedicionRespuesta(BaseModel):
    recalculos: list[ResultadoRecalculoRespuesta]


@router.get(
    "/planos/{plano_id}/mediciones",
    response_model=list[MedicionRespuesta],
    summary="Las mediciones de un plano, con lo que miden y a qué conceptos alimentan",
    responses={404: {"description": "El plano no existe o está fuera de tu alcance."}},
)
async def listar_mediciones(plano_id: UUID, caso_uso: GestionarMedicionesDep) -> list[MedicionRespuesta]:
    filas = await caso_uso.listar(plano_id)
    return [
        MedicionRespuesta(
            id=f["id"],
            parent_id=f["parent_id"],
            nombre=f["nombre"],
            tipo=f["tipo"],
            orden=f["orden"],
            n_trazos=int(f["n_trazos"]),
            valor=Decimal(str(f["valor"])),
            unidad=_UNIDAD[f["tipo"]],
            elemento=(
                ElementoDeMedicion(id=f["elemento_id"], nombre=f["elemento_nombre"], peso_kg=f["elemento_peso_kg"])
                if f["elemento_id"]
                else None
            ),
            asignaciones=[
                AsignacionRespuesta(
                    id=a["id"],
                    actividad_id=a["actividad_id"],
                    concepto_clave=a["concepto_clave"],
                    descripcion=a["descripcion"],
                    matriz_concepto_id=a["matriz_concepto_id"],
                    matriz_clave=a["matriz_clave"],
                    medida=a["medida"],
                    factor=a["factor"],
                    usa_peso=a["usa_peso"],
                )
                for a in f["asignaciones"]
            ],
        )
        for f in filas
    ]


@router.post(
    "/planos/{plano_id}/mediciones",
    response_model=MedicionCreada,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una medición (o una submedición)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={
        404: {"description": "El plano o la medición madre no existen o están fuera de tu alcance."},
        422: {"description": "Nombre repetido entre hermanas, tipo distinto del de la madre o nombre vacío."},
    },
)
async def crear_medicion(
    plano_id: UUID, peticion: MedicionPeticion, ctx: ContextoActual, caso_uso: GestionarMedicionesDep
) -> MedicionCreada:
    medicion_id = await caso_uso.crear(
        ComandoCrearMedicion(
            plano_id=plano_id,
            nombre=peticion.nombre,
            tipo=peticion.tipo,
            parent_id=peticion.parent_id,
            autor_id=ctx.usuario_id,
        )
    )
    return MedicionCreada(id=medicion_id)


@router.patch(
    "/mediciones/{medicion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Renombrar una medición",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={404: {"description": "La medición no existe o está fuera de tu alcance."}},
)
async def renombrar_medicion(
    medicion_id: UUID, peticion: RenombrarPeticion, caso_uso: GestionarMedicionesDep
) -> None:
    await caso_uso.renombrar(medicion_id, peticion.nombre)


@router.delete(
    "/mediciones/{medicion_id}",
    response_model=TrazoEnMedicionRespuesta,
    summary="Borrar una medición y sus asignaciones (sus trazos quedan sueltos)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={
        404: {"description": "La medición no existe o está fuera de tu alcance."},
        422: {"description": "Tiene submediciones."},
    },
)
async def eliminar_medicion(
    medicion_id: UUID, ctx: ContextoActual, caso_uso: GestionarMedicionesDep
) -> TrazoEnMedicionRespuesta:
    """Los enlaces de sus asignaciones quedan como evidencia (no vigentes) y los conceptos se recalculan."""
    recalculos = await caso_uso.eliminar(medicion_id, usuario_id=ctx.usuario_id, detectada_en=datetime.now(UTC))
    return TrazoEnMedicionRespuesta(recalculos=[ResultadoRecalculoRespuesta.desde_dominio(r) for r in recalculos])


@router.put(
    "/trazos/{trazo_id}/medicion",
    response_model=TrazoEnMedicionRespuesta,
    summary="Meter un trazo en una medición, o sacarlo de ella",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={
        404: {"description": "El trazo o la medición no existen o están fuera de tu alcance."},
        422: {"description": "El trazo no es del tipo de la medición, o es de otro plano."},
    },
)
async def poner_trazo_en_medicion(
    trazo_id: UUID,
    peticion: TrazoEnMedicionPeticion,
    ctx: ContextoActual,
    caso_uso: GestionarMedicionesDep,
) -> TrazoEnMedicionRespuesta:
    """Al entrar recibe los enlaces de la medición (y de las que la contienen); al salir pierde los que
    le venían de ella. Los enlaces quitados quedan como evidencia, no vigentes."""
    recalculos = await caso_uso.asignar_trazo(
        trazo_id=trazo_id,
        medicion_id=peticion.medicion_id,
        usuario_id=ctx.usuario_id,
        detectada_en=datetime.now(UTC),
    )
    return TrazoEnMedicionRespuesta(
        recalculos=[ResultadoRecalculoRespuesta.desde_dominio(r) for r in recalculos]
    )


@router.post(
    "/mediciones/{medicion_id}/asignaciones",
    response_model=AsignacionCreada,
    status_code=status.HTTP_201_CREATED,
    summary="Asignar una medición a un concepto de la obra",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={
        404: {"description": "La medición no existe o está fuera de tu alcance."},
        422: {"description": "Medida que no corresponde al tipo, concepto de otra obra o asignación repetida en la rama."},
    },
)
async def asignar_medicion(
    medicion_id: UUID,
    peticion: AsignacionPeticion,
    ctx: ContextoActual,
    caso_uso: GestionarMedicionesDep,
) -> AsignacionCreada:
    """Crea un enlace por cada trazo de la medición y de sus submediciones, y recalcula el concepto.
    Un trazo que entre después a la medición hereda este enlace."""
    resultado = await caso_uso.crear_asignacion(
        ComandoCrearAsignacion(
            medicion_id=medicion_id,
            actividad_id=peticion.actividad_id,
            matriz_concepto_id=peticion.matriz_concepto_id,
            medida=peticion.medida,
            factor=peticion.factor,
            usar_peso=peticion.usar_peso,
            autor_id=ctx.usuario_id,
        ),
        detectada_en=datetime.now(UTC),
    )
    return AsignacionCreada(
        id=resultado.asignacion_id,
        trazos_enlazados=resultado.trazos_enlazados,
        recalculos=[ResultadoRecalculoRespuesta.desde_dominio(r) for r in resultado.recalculos],
    )


@router.delete(
    "/asignaciones-de-medicion/{asignacion_id}",
    response_model=AsignacionCreada,
    summary="Quitar la asignación de una medición a un concepto",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={404: {"description": "La asignación no existe o está fuera de tu alcance."}},
)
async def quitar_asignacion(
    asignacion_id: UUID, ctx: ContextoActual, caso_uso: GestionarMedicionesDep
) -> AsignacionCreada:
    """Los enlaces que nacieron de ella quedan como evidencia (no vigentes) y el concepto se recalcula."""
    resultado = await caso_uso.quitar_asignacion(
        asignacion_id, usuario_id=ctx.usuario_id, detectada_en=datetime.now(UTC)
    )
    return AsignacionCreada(
        id=None,
        trazos_enlazados=resultado.trazos_enlazados,
        recalculos=[ResultadoRecalculoRespuesta.desde_dominio(r) for r in resultado.recalculos],
    )


# --- Elementos con peso (migración 0089) -----------------------------------------------------------------

ROLES_QUE_PONEN_PESO = (Rol.CONTROL_OBRA, Rol.COSTOS)
"""El peso de un elemento cambia cantidades de presupuesto (kg y ton): lo ponen Control de obra y Costos."""


class ElementoRespuesta(BaseModel):
    id: UUID
    nombre: str
    tipo: TipoDeMedicion
    peso_kg: Decimal = Field(description="kg por pieza (conteo), por metro (lineal) o por m² (área).")
    n_mediciones: int = Field(description="Mediciones que lo usan.")


class ElementoPeticion(BaseModel):
    nombre: str = Field(min_length=1, max_length=80)
    tipo: TipoDeMedicion
    peso_kg: Decimal = Field(gt=0)


class ElementoCambio(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=80)
    peso_kg: Decimal | None = Field(default=None, gt=0)


class ElementoPuestoEnMedicion(BaseModel):
    elemento_id: UUID | None = Field(default=None, description="`null` le quita el elemento a la medición.")


@router.get(
    "/elementos",
    response_model=list[ElementoRespuesta],
    summary="Los elementos con peso de la organización (K1, varilla 3/8…)",
)
async def listar_elementos(caso_uso: GestionarElementosDep) -> list[ElementoRespuesta]:
    return [
        ElementoRespuesta(
            id=f["id"], nombre=f["nombre"], tipo=f["tipo"], peso_kg=f["peso_kg"], n_mediciones=int(f["n_mediciones"])
        )
        for f in await caso_uso.listar()
    ]


@router.post(
    "/elementos",
    response_model=MedicionCreada,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un elemento con peso",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_PONEN_PESO))],
    responses={
        403: {"description": "El peso lo ponen Control de obra y Costos."},
        422: {"description": "Nombre repetido, vacío o peso no positivo."},
    },
)
async def crear_elemento(
    peticion: ElementoPeticion, ctx: ContextoActual, caso_uso: GestionarElementosDep
) -> MedicionCreada:
    elemento_id = await caso_uso.crear(
        ComandoCrearElemento(
            nombre=peticion.nombre, tipo=peticion.tipo, peso_kg=peticion.peso_kg, autor_id=ctx.usuario_id
        )
    )
    return MedicionCreada(id=elemento_id)


@router.patch(
    "/elementos/{elemento_id}",
    response_model=TrazoEnMedicionRespuesta,
    summary="Cambiar el nombre o el peso de un elemento (rehace las asignaciones que lo usan)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_PONEN_PESO))],
    responses={
        403: {"description": "El peso lo ponen Control de obra y Costos."},
        404: {"description": "El elemento no existe o está fuera de tu alcance."},
    },
)
async def actualizar_elemento(
    elemento_id: UUID, peticion: ElementoCambio, ctx: ContextoActual, caso_uso: GestionarElementosDep
) -> TrazoEnMedicionRespuesta:
    """Un peso nuevo rehace de inmediato las asignaciones por peso: sus enlaces quedan como evidencia y
    los nuevos llevan el factor al día; los conceptos en kg o ton se recalculan."""
    recalculos = await caso_uso.actualizar(
        elemento_id,
        nombre=peticion.nombre,
        peso_kg=peticion.peso_kg,
        usuario_id=ctx.usuario_id,
        detectada_en=datetime.now(UTC),
    )
    return TrazoEnMedicionRespuesta(recalculos=[ResultadoRecalculoRespuesta.desde_dominio(r) for r in recalculos])


@router.delete(
    "/elementos/{elemento_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Borrar un elemento que ningún concepto usa por su peso",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_PONEN_PESO))],
    responses={
        403: {"description": "El peso lo ponen Control de obra y Costos."},
        404: {"description": "El elemento no existe o está fuera de tu alcance."},
        422: {"description": "Hay conceptos que reciben cantidad con su peso."},
    },
)
async def eliminar_elemento(elemento_id: UUID, caso_uso: GestionarElementosDep) -> None:
    await caso_uso.eliminar(elemento_id)


@router.put(
    "/mediciones/{medicion_id}/elemento",
    response_model=TrazoEnMedicionRespuesta,
    summary="Darle a una medición un elemento con peso, o quitárselo",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_TRAZAN))],
    responses={
        404: {"description": "La medición o el elemento no existen o están fuera de tu alcance."},
        422: {"description": "El elemento es de otro tipo, o la medición alimenta conceptos con su peso."},
    },
)
async def poner_elemento_en_medicion(
    medicion_id: UUID,
    peticion: ElementoPuestoEnMedicion,
    ctx: ContextoActual,
    caso_uso: GestionarMedicionesDep,
) -> TrazoEnMedicionRespuesta:
    recalculos = await caso_uso.poner_elemento(
        medicion_id, peticion.elemento_id, usuario_id=ctx.usuario_id, detectada_en=datetime.now(UTC)
    )
    return TrazoEnMedicionRespuesta(recalculos=[ResultadoRecalculoRespuesta.desde_dominio(r) for r in recalculos])
