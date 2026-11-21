"""Endpoints de las zonas de losa (Fase 1: geometría y cotas; la matriz de conceptos de la losa es la fase 2, en `losas.py`).

Hay desniveles entre plantas y el plano no viene dividido en ellos: las zonas se definen con el artefacto de la losa, reciclando los
polígonos del plano. Una **zona** lleva sus cotas (relativas al piso terminado de PB = 0): la cota del piso, la altura libre hasta el
nivel bajo de la losa y el espesor. Un polígono del plano con rol de **losa** pertenece a una zona (varias losas por zona; el espesor
propio de un polígono es una subzona estructural). Un punto del plano puede ser un **punto de nivel exterior** con su cota y su rótulo.

**Solo Control de obra escribe zonas, losas y puntos de nivel; todos los roles que ven el plano leen.** La resolución de un muro
(altura, enrase, cara interior o exterior por tramo) solo muestra lo que se sugiere: no cambia nada guardado.
Controladores delgados: las reglas viven en el dominio.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import AplicarZonaAlMuroDep, GestionarZonasDeLosaDep
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.domain.cuantificacion.zonas_de_losa import LadoDeMuro, ResolucionDeMuro
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["zonas de losa"])

ROLES_QUE_EDITAN = (Rol.CONTROL_OBRA,)
ROLES_QUE_LEEN = (Rol.RESIDENTE, Rol.SUPERVISOR, Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE, Rol.COSTOS)

Cara = Literal["exterior", "interior"]


class ZonaDeLosaPeticion(BaseModel):
    nombre: str = Field(min_length=1, max_length=60, description="Nombre de la zona (único en el plano), p. ej. «Entrepiso 3.00».")
    nivel: str | None = Field(default=None, max_length=40, description="La planta o nivel al que pertenece (texto libre).")
    cota_piso_m: Decimal = Field(default=Decimal(0), description="Cota del piso terminado de la zona; el piso terminado de PB = 0.")
    altura_libre_m: Decimal = Field(gt=0, le=30, description="Del piso terminado al nivel BAJO de la losa: la altura que toma el muro.")
    espesor_m: Decimal = Field(gt=0, le=3, description="Espesor de la losa (la cota que sigue a la altura libre).")
    tipo_de_losa: Literal["maciza", "nervada"] | None = Field(
        default=None, description="Matriz de la losa (fase 2): maciza o nervada. Sin él, la zona conserva el suyo (al crearla, maciza)."
    )
    uso_de_losa: Literal["entrepiso", "azotea", "cimentacion"] | None = Field(
        default=None, description="Matriz de la losa (fase 2): entrepiso, azotea o cimentación, elige el concreto. Sin él, la zona conserva el suyo (al crearla, entrepiso)."
    )


class LosaDeZona(BaseModel):
    trazo_id: UUID
    espesor_propio_m: Decimal | None = Field(description="Subzona: espesor estructural propio; `null` = el de la zona.")
    espesor_m: Decimal = Field(description="El espesor que aplica (el propio, si hay).")


class ZonaDeLosa(BaseModel):
    id: UUID
    plano_id: UUID
    nombre: str
    nivel: str | None
    cota_piso_m: Decimal
    altura_libre_m: Decimal
    espesor_m: Decimal
    tipo_de_losa: Literal["maciza", "nervada"]
    uso_de_losa: Literal["entrepiso", "azotea", "cimentacion"]
    cota_inferior_m: Decimal = Field(description="Cota del nivel bajo de la losa (cota del piso + altura libre).")
    cota_superior_m: Decimal = Field(description="Cota del nivel alto de la losa (nivel bajo + espesor).")
    losas: list[LosaDeZona]
    created_at: datetime
    updated_at: datetime


class PuntoDeNivelDelPlano(BaseModel):
    trazo_id: UUID
    cota_m: Decimal
    rotulo: str | None


class ZonasDelPlano(BaseModel):
    plano_id: UUID
    escala_definida: bool = Field(description="Sin escala calibrada se toma 1 unidad de plano = 1 m (como las uniones de muro).")
    zonas: list[ZonaDeLosa]
    puntos_de_nivel: list[PuntoDeNivelDelPlano]


class LosaPeticion(BaseModel):
    zona_id: UUID | None = Field(description="La zona de la que este polígono es losa; `null` le quita el rol de losa.")
    espesor_m: Decimal | None = Field(
        default=None, gt=0, le=3, description="Subzona: espesor estructural propio dentro de la zona; `null` = el de la zona."
    )


class LosaFijada(BaseModel):
    trazo_id: UUID
    zona_id: UUID | None
    espesor_propio_m: Decimal | None


class NivelExteriorPeticion(BaseModel):
    cota_m: Decimal | None = Field(
        description="Cota del punto de nivel exterior (piso terminado de PB = 0); `null` quita la marca.", ge=-30, le=100
    )
    rotulo: str | None = Field(default=None, max_length=60, description="Rótulo del punto (p. ej. «Banqueta»).")


class NivelExteriorFijado(BaseModel):
    trazo_id: UUID
    cota_m: Decimal | None
    rotulo: str | None


class LadoDelTramo(BaseModel):
    lado: Literal["A", "B"] = Field(description="A = izquierda del sentido de dibujo; B = derecha.")
    cara: Cara | None = Field(description="`null` si el muro no cae en ninguna zona.")
    origen: Literal["losa", "punto_de_nivel", "sin_losa", "sin_zona"] = Field(
        description="Por qué: cuelga de una losa; lo confirma un punto de nivel exterior; sin losa de ese lado; fuera de toda zona."
    )
    zona_id: UUID | None = None
    zona: str | None = None
    losa_id: UUID | None = None
    espesor_m: Decimal | None = None
    cota_inferior_m: Decimal | None = None
    cota_superior_m: Decimal | None = None
    altura_m: Decimal | None = Field(default=None, description="La altura de esta cara.")
    punto_de_nivel_id: UUID | None = None
    nivel_exterior_m: Decimal | None = None
    rotulo_del_punto: str | None = None


class ParteDelTramo(BaseModel):
    nombre: str
    desde_m: Decimal
    hasta_m: Decimal
    suma: bool = True
    rol: Literal["cuerpo", "enrase"]
    cara_a: Cara | None
    cara_b: Cara | None


class EnraseDelTramo(BaseModel):
    desde_m: Decimal
    hasta_m: Decimal


class SugerenciaDeCaras(BaseModel):
    indice: int
    nombre: str
    cara_a: Cara
    cara_b: Cara


class TramoDelMuro(BaseModel):
    desde_m: Decimal = Field(description="Distancia al inicio del trazo, a lo largo (m).")
    hasta_m: Decimal
    longitud_m: Decimal
    lado_a: LadoDelTramo
    lado_b: LadoDelTramo
    altura_m: Decimal = Field(description="Lo alto del cuerpo del muro en este tramo.")
    origen_de_altura: Literal["trazo", "zona", "artefacto", "herramienta"] = Field(
        description="De dónde sale: la altura explícita del trazo, la zona de losa, la altura base del artefacto (plantilla) o la de la herramienta de trazo."
    )
    enrase: EnraseDelTramo | None = Field(description="Entre la losa baja y la alta, si los dos lados cuelgan de losas a distinta cota.")
    partes: list[ParteDelTramo] = Field(description="Partes de altura (la estructura de la 4A) que aplicarían a este tramo.")
    sugerencias: list[SugerenciaDeCaras] = Field(description="Lo que la losa más baja SUGIERE para el enrase; nunca se aplica solo.")


class VanoDelTramo(BaseModel):
    vano_id: UUID
    clave: str
    tipo: str
    posicion_m: Decimal | None


class ResolucionDelMuro(BaseModel):
    trazo_id: UUID
    escala_definida: bool
    altura_explicita_m: Decimal | None = Field(description="La altura que el trazo trae (partes o altura única); manda sobre la zona.")
    altura_base_m: Decimal = Field(
        description="La altura base con que nace un muro sin la suya ni zona: la de la plantilla elegida (artefacto) o la de la herramienta (3.00 m). No es el driver."
    )
    altura_guardada_m: Decimal | None = Field(description="Con la que ya mide hoy su conversión guardada (no se cambia sola, Q1).")
    con_zona: bool = Field(description="Algún lado del muro cuelga de una losa; si no, el muro se comporta como siempre.")
    parte_el_muro: bool = Field(description="Los tramos tienen alturas distintas: habría que partir el muro en el límite de zona.")
    aplicada: bool = Field(description="Siempre `false`: esto es lo que se sugiere, no algo aplicado.")
    advertencias: list[str]
    tramos: list[TramoDelMuro]
    vanos_por_tramo: list[list[VanoDelTramo]] = Field(description="Los vanos del muro repartidos por tramo: cada uno cae donde está su centro.")
    tramos_de_conversion: list[dict[str, Any]] = Field(description="Los tramos lógicos con los que contaría el muro si se aplican (`conversion.tramos`).")


class ZonaAplicadaAlMuro(BaseModel):
    trazo_id: UUID
    tramos: list[dict[str, Any]]
    enlaces_aplicados: int = Field(description="Cuántos enlaces del muro (en m² o m³) pasaron a contar con la zona.")
    enlaces_sin_conversion: int = Field(description="Enlaces antiguos de factor fijo: no se tocan (Q1).")


def _lado(lado: LadoDeMuro) -> LadoDelTramo:
    return LadoDelTramo.model_validate(lado, from_attributes=True)


def _resolucion(datos: dict[str, Any]) -> ResolucionDelMuro:
    r: ResolucionDeMuro = datos["resolucion"]
    return ResolucionDelMuro(
        trazo_id=datos["trazo_id"],
        escala_definida=datos["escala_definida"],
        altura_explicita_m=datos["altura_explicita_m"],
        altura_base_m=datos["altura_base_m"],
        altura_guardada_m=datos["altura_guardada_m"],
        con_zona=r.con_zona,
        parte_el_muro=r.parte_el_muro,
        aplicada=r.aplicada,
        advertencias=list(r.advertencias),
        vanos_por_tramo=[[VanoDelTramo(**v) for v in tramo] for tramo in datos["vanos_por_tramo"]],
        tramos_de_conversion=datos["tramos_de_conversion"],
        tramos=[
            TramoDelMuro(
                desde_m=t.desde_m, hasta_m=t.hasta_m, longitud_m=t.longitud_m, lado_a=_lado(t.lado_a), lado_b=_lado(t.lado_b),
                altura_m=t.altura_m, origen_de_altura=t.origen_de_altura,  # type: ignore[arg-type]
                enrase=EnraseDelTramo(**t.enrase) if t.enrase else None,
                partes=[ParteDelTramo(**p) for p in t.partes],
                sugerencias=[SugerenciaDeCaras(**s) for s in t.sugerencias],
            )
            for t in r.tramos
        ],
    )


@router.get(
    "/planos/{plano_id}/zonas-de-losa",
    response_model=ZonasDelPlano,
    summary="Las zonas de losa de un plano, sus losas y sus puntos de nivel exterior",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_LEEN))],
)
async def zonas_del_plano(plano_id: UUID, caso_uso: GestionarZonasDeLosaDep) -> ZonasDelPlano:
    return ZonasDelPlano.model_validate(await caso_uso.del_plano(plano_id))


@router.post(
    "/planos/{plano_id}/zonas-de-losa",
    response_model=ZonaDeLosa,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una zona de losa (solo Control de obra)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
    responses={422: {"description": "Cotas o espesor fuera de rango, o nombre repetido en el plano."}},
)
async def crear_zona(plano_id: UUID, peticion: ZonaDeLosaPeticion, caso_uso: GestionarZonasDeLosaDep, ctx: ContextoActual) -> ZonaDeLosa:
    z = await caso_uso.crear(plano_id, autor_id=ctx.usuario_id, **peticion.model_dump())
    return await _con_losas(caso_uso, z)


@router.put(
    "/zonas-de-losa/{zona_id}",
    response_model=ZonaDeLosa,
    summary="Cambiar las cotas o el nombre de una zona de losa (solo Control de obra)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
)
async def cambiar_zona(zona_id: UUID, peticion: ZonaDeLosaPeticion, caso_uso: GestionarZonasDeLosaDep) -> ZonaDeLosa:
    z = await caso_uso.cambiar(zona_id, **peticion.model_dump())
    return await _con_losas(caso_uso, z)


@router.delete(
    "/zonas-de-losa/{zona_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Borrar una zona de losa: sus polígonos quedan como trazos comunes (solo Control de obra)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
)
async def borrar_zona(zona_id: UUID, caso_uso: GestionarZonasDeLosaDep) -> None:
    await caso_uso.eliminar(zona_id)


@router.put(
    "/trazos/{trazo_id}/losa",
    response_model=LosaFijada,
    summary="Dar o quitar el rol de losa de una zona a un polígono (solo Control de obra)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
    responses={422: {"description": "El trazo no es un polígono, o la zona es de otro plano."}},
)
async def fijar_losa(trazo_id: UUID, peticion: LosaPeticion, caso_uso: GestionarZonasDeLosaDep) -> LosaFijada:
    return LosaFijada.model_validate(await caso_uso.fijar_losa(trazo_id, zona_id=peticion.zona_id, espesor_m=peticion.espesor_m))


@router.put(
    "/trazos/{trazo_id}/nivel-exterior",
    response_model=NivelExteriorFijado,
    summary="Marcar o quitar un punto de nivel exterior con su cota y su rótulo (solo Control de obra)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_EDITAN))],
    responses={422: {"description": "El trazo no es un punto o la cota está fuera de rango."}},
)
async def fijar_nivel_exterior(trazo_id: UUID, peticion: NivelExteriorPeticion, caso_uso: GestionarZonasDeLosaDep) -> NivelExteriorFijado:
    return NivelExteriorFijado.model_validate(
        await caso_uso.fijar_nivel_exterior(trazo_id, cota_m=peticion.cota_m, rotulo=peticion.rotulo)
    )


@router.get(
    "/trazos/{trazo_id}/zonas-de-losa",
    response_model=ResolucionDelMuro,
    summary="Qué zona, altura, enrase y cara aplicarían a un muro (solo muestra; no cambia nada)",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_LEEN))],
    responses={422: {"description": "El trazo no es una línea."}},
)
async def resolver_muro(trazo_id: UUID, caso_uso: GestionarZonasDeLosaDep) -> ResolucionDelMuro:
    return _resolucion(await caso_uso.resolver_muro(trazo_id))


@router.post(
    "/trazos/{trazo_id}/zonas-de-losa/aplicar",
    response_model=ZonaAplicadaAlMuro,
    summary="Aplicar al muro la altura, las partes por cara o los tramos de sus zonas de losa",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_LEEN))],
    responses={422: {"description": "El muro no cae bajo ninguna zona, o trae su altura (manda sobre la de la zona)."}},
)
async def aplicar_zona_al_muro(trazo_id: UUID, ctx: ContextoActual, caso_uso: AplicarZonaAlMuroDep) -> ZonaAplicadaAlMuro:
    """Un acto explícito: reemplaza el enlace del muro con la conversión de su zona (el anterior queda como evidencia) y recalcula lo que
    alimenta. Un muro que cruza zonas cuenta por tramos lógicos dentro del mismo trazo; los demás trazos no cambian."""
    return ZonaAplicadaAlMuro.model_validate(
        await caso_uso.ejecutar(trazo_id, rol=Rol(ctx.rol), usuario_id=ctx.usuario_id, detectada_en=datetime.now(UTC))
    )


async def _con_losas(caso_uso: Any, z: dict[str, Any]) -> ZonaDeLosa:
    """La zona recién guardada con sus losas y cotas, tal como la lista la devuelve."""
    del_plano = await caso_uso.del_plano(z["plano_id"])
    return next(ZonaDeLosa.model_validate(x) for x in del_plano["zonas"] if x["id"] == z["id"])
