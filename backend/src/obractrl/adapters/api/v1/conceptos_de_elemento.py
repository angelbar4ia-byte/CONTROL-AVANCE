"""Endpoints de los conceptos que paga un elemento paramétrico por contexto y escalón (plan de elementos de muro, fase C; 0128).

Un elemento paga cada parte de su receta con un concepto que depende del contexto (nivel, ubicación) y, en el acero de un
castillo, del alto (escalones). Leer es de cualquiera que vea el catálogo; escribir lo hacen Control de obra y Costos. Un
concepto nuevo queda `propuesto`, sin precio, hasta que Control de obra lo autorice (fase de roles y versiones).
Controladores delgados.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import GestionarConceptosDeElementoDep
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.application.casos_uso.conceptos_de_elemento import (
    ComandoAgregarConceptoDeElemento,
)
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["elementos parametricos"])

ROLES_QUE_DEFINEN = (Rol.CONTROL_OBRA, Rol.COSTOS)
"""Igual que el elemento: lo definen Control de obra y Costos (D-602). Autorizar un concepto nuevo es de la fase siguiente."""

UbicacionDelMuro = Literal["pretil", "barda"]


class ConceptoPorContextoRespuesta(BaseModel):
    id: UUID = Field(description="Identifica la fila (elemento, concepto, contexto, escalón).")
    concepto_id: UUID | None = Field(description="El concepto del catálogo; `null` si es un concepto nuevo propuesto.")
    clave: str = Field(description="La del catálogo o, en uno nuevo, la propuesta.")
    descripcion: str
    descripcion_catalogo: str | None = Field(description="La descripción del catálogo si la fila la cambió; `null` en un concepto nuevo.")
    nuevo: bool = Field(description="Concepto que aún no está en el catálogo.")
    estado: Literal["propuesto", "autorizado"] = Field(description="`propuesto` = nuevo, pendiente de autorizar por Control de obra.")
    unidad: str
    ranura: Literal["acero", "colado", "completo"] | None = Field(description="La parte de la receta que paga, según lo que toma.")
    toma: dict[str, bool]
    nivel_min: int | None
    nivel_max: int | None
    ubicacion: UbicacionDelMuro | None
    contexto: str = Field(description="El contexto en palabras (`niveles 1 a 2`, `nivel 3 en adelante`, `Todo contexto`).")
    alto_hasta_m: float | None = Field(description="Escalón por altura: sirve hasta este alto. `null` si no es un escalón.")
    elegido: bool | None = Field(description="Con nivel o ubicación en la consulta: si este concepto es el que paga su parte. `null` sin ellos.")


class ConceptosPorContextoRespuesta(BaseModel):
    alto_m: float | None = Field(description="El alto con que se eligen los escalones (el del castillo, o el pedido).")
    nivel: int | None
    ubicacion: UbicacionDelMuro | None
    conceptos: list[ConceptoPorContextoRespuesta]
    por_parte: dict[str, str] = Field(description="Con nivel o ubicación: la clave del concepto que paga cada grupo (acero, concreto, cimbra).")
    avisos: list[str] = Field(description="Un alto sin escalón, una parte sin concepto o tomada dos veces.")


class ConceptoPorContextoPeticion(BaseModel):
    concepto_id: UUID | None = Field(default=None, description="Un concepto del catálogo. Sin él, hay que proponer uno nuevo con `clave_propuesta`.")
    clave_propuesta: str | None = Field(default=None, max_length=20, description="Clave de un concepto NUEVO (queda propuesto, sin precio).")
    descripcion: str | None = Field(default=None, max_length=600, description="Obligatoria en un concepto nuevo; en uno del catálogo, la que el elemento le da.")
    unidad: Literal["pza", "ml", "m²"]
    toma: dict[str, bool] = Field(description="Qué materiales toma: concreto, acero, estribos, alambre, cimbra.")
    nivel_min: int | None = Field(default=None, ge=1, le=99, description="Nivel mínimo (1 = planta baja); sin él, desde el primero.")
    nivel_max: int | None = Field(default=None, ge=1, le=99, description="Nivel máximo; sin él, sin límite.")
    ubicacion: UbicacionDelMuro | None = None
    alto_hasta_m: Decimal | None = Field(default=None, gt=0, lt=100, description="Escalón: el concepto sirve hasta este alto en metros. Queda fijo.")


class ConceptoPorContextoCreado(BaseModel):
    id: UUID


class DescripcionDelConceptoPeticion(BaseModel):
    descripcion: str = Field(min_length=1, max_length=600)


def _fila(f: dict[str, object]) -> ConceptoPorContextoRespuesta:
    alto = f["alto_hasta_m"]
    return ConceptoPorContextoRespuesta(
        id=f["id"],  # type: ignore[arg-type]
        concepto_id=f["concepto_id"],  # type: ignore[arg-type]
        clave=f["clave"],  # type: ignore[arg-type]
        descripcion=f["descripcion"],  # type: ignore[arg-type]
        descripcion_catalogo=f["descripcion_catalogo"],  # type: ignore[arg-type]
        nuevo=f["concepto_id"] is None,
        estado=f["estado"],  # type: ignore[arg-type]
        unidad=f["unidad"],  # type: ignore[arg-type]
        ranura=f["ranura"],  # type: ignore[arg-type]
        toma={str(k): bool(v) for k, v in dict(f["toma"] or {}).items()},  # type: ignore[call-overload]
        nivel_min=f["nivel_min"],  # type: ignore[arg-type]
        nivel_max=f["nivel_max"],  # type: ignore[arg-type]
        ubicacion=f["ubicacion"],  # type: ignore[arg-type]
        contexto=f["contexto"],  # type: ignore[arg-type]
        alto_hasta_m=float(alto) if alto is not None else None,  # type: ignore[arg-type]
        elegido=f["elegido"],  # type: ignore[arg-type]
    )


@router.get(
    "/elementos-parametricos/{elemento_id}/conceptos-por-contexto",
    response_model=ConceptosPorContextoRespuesta,
    summary="Los conceptos que paga el elemento, por contexto y escalón de altura",
    responses={404: {"description": "El elemento no existe o está fuera de tu alcance."}},
)
async def conceptos_por_contexto(
    elemento_id: UUID,
    caso_uso: GestionarConceptosDeElementoDep,
    nivel: Annotated[int | None, Query(ge=1, le=99, description="Nivel del muro (1 = planta baja): marca el concepto que paga cada parte.")] = None,
    ubicacion: Annotated[UbicacionDelMuro | None, Query(description="Ubicación del muro.")] = None,
    alto_m: Annotated[Decimal | None, Query(gt=0, lt=100, description="Alto con que se elige el escalón; sin él, el del castillo.")] = None,
) -> ConceptosPorContextoRespuesta:
    """Sin nivel ni ubicación lista todos los conceptos del elemento y avisa de los escalones que no alcanzan su alto. Con
    ellos dice cuáles aplican, cuál paga cada parte y qué avisos hay (parte sin concepto, tomada dos veces, alto sin escalón)."""
    r = await caso_uso.por_contexto(elemento_id, nivel=nivel, ubicacion=ubicacion, alto_m=alto_m)
    return ConceptosPorContextoRespuesta(
        alto_m=float(r["alto_m"]) if r["alto_m"] is not None else None,
        nivel=r["nivel"],
        ubicacion=r["ubicacion"],
        conceptos=[_fila(f) for f in r["conceptos"]],
        por_parte=r["por_parte"],
        avisos=r["avisos"],
    )


@router.post(
    "/elementos-parametricos/{elemento_id}/conceptos-por-contexto",
    response_model=ConceptoPorContextoCreado,
    status_code=status.HTTP_201_CREATED,
    summary="El elemento paga una parte con un concepto en un contexto (o escalón); uno nuevo queda propuesto",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_DEFINEN))],
    responses={
        403: {"description": "Lo definen Control de obra y Costos."},
        404: {"description": "El elemento o el concepto no existen o están fuera de tu alcance."},
        422: {"description": "La parte ya la toma otro concepto en ese contexto, la clave nueva ya está en el catálogo, o el contexto o la unidad no valen."},
    },
)
async def agregar_concepto_por_contexto(
    elemento_id: UUID, peticion: ConceptoPorContextoPeticion, ctx: ContextoActual, caso_uso: GestionarConceptosDeElementoDep
) -> ConceptoPorContextoCreado:
    """Un concepto nuevo se guarda `propuesto`: sin precio y sin entrar al catálogo hasta que Control de obra lo autorice."""
    nuevo = await caso_uso.agregar(
        ComandoAgregarConceptoDeElemento(
            elemento_id=elemento_id,
            unidad=peticion.unidad,
            toma=dict(peticion.toma),
            autor_id=ctx.usuario_id,
            concepto_id=peticion.concepto_id,
            clave_propuesta=peticion.clave_propuesta,
            descripcion=peticion.descripcion,
            nivel_min=peticion.nivel_min,
            nivel_max=peticion.nivel_max,
            ubicacion=peticion.ubicacion,
            alto_hasta_m=peticion.alto_hasta_m,
        )
    )
    return ConceptoPorContextoCreado(id=nuevo)


@router.patch(
    "/elementos-parametricos/{elemento_id}/conceptos-por-contexto/{fila_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cambiar la descripción de un concepto del elemento (la clave y el «hasta» del escalón son fijos)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_DEFINEN))],
    responses={
        403: {"description": "Lo definen Control de obra y Costos."},
        404: {"description": "El elemento o el concepto no existen o están fuera de tu alcance."},
    },
)
async def cambiar_descripcion_del_concepto(
    elemento_id: UUID, fila_id: UUID, peticion: DescripcionDelConceptoPeticion, caso_uso: GestionarConceptosDeElementoDep
) -> None:
    await caso_uso.cambiar_descripcion(elemento_id, fila_id, peticion.descripcion)


@router.delete(
    "/elementos-parametricos/{elemento_id}/conceptos-por-contexto/{fila_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Quitar un concepto del elemento en su contexto (para corregir una clave o un escalón)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_DEFINEN))],
    responses={
        403: {"description": "Lo definen Control de obra y Costos."},
        404: {"description": "El elemento o el concepto no existen o están fuera de tu alcance."},
    },
)
async def quitar_concepto_por_contexto(elemento_id: UUID, fila_id: UUID, caso_uso: GestionarConceptosDeElementoDep) -> None:
    await caso_uso.quitar(elemento_id, fila_id)
