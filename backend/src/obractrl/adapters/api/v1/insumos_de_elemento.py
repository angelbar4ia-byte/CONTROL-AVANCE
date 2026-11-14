"""Endpoints de los insumos de un elemento paramétrico y su comparación con el concepto del catálogo (plan de elementos de muro, fase D; 0129).

Cada tipo de elemento solo admite los insumos de sus familias (castillo, cadena y zapata: Aceros, Acero De Refuerzo, concretos y
Cimbra; mano de obra de Albañilería y Estructura; destajo de su tipo): un insumo de otra familia se rechaza con un 422 que dice
qué admite el tipo. Los insumos que el usuario crea desde la tarjeta nacen **provisionales y sin precio**. Leer es de cualquiera
que vea el catálogo; escribir lo hacen Control de obra y Costos. Controladores delgados.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import GestionarInsumosDeElementoDep
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.adapters.api.v1.elementos_parametricos import TipoDeElementoParametrico
from obractrl.application.casos_uso.insumos_de_elemento import (
    ComandoAgregarInsumos,
    ComandoCrearInsumoProvisional,
)
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["elementos parametricos"])

ROLES_QUE_DEFINEN = (Rol.CONTROL_OBRA, Rol.COSTOS)

ClaseDeInsumo = Literal["material", "trabajo", "mano_obra", "herramienta"]
MarcaDeComparacion = Literal["=", "≈", "≠", "solo_catalogo", "solo_elemento"]


class FamiliaDeInsumo(BaseModel):
    familia: str
    subfamilia: str | None
    total: int = Field(description="Cuántos insumos hay en ella.")
    usual: bool = Field(description="Si es de las familias que el tipo de elemento admite; las demás se muestran con una marca y no se pueden agregar.")


class SugerenciaDeHerramienta(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    subfamilia: str


class ClaseDeInsumoRespuesta(BaseModel):
    clase: ClaseDeInsumo
    nombre: str
    descripcion: str
    total: int
    admitidas: str = Field(description="Las familias que admite el tipo en esta clase, en palabras.")
    familias_usuales: list[str]
    familias: list[FamiliaDeInsumo]


class FamiliasDeInsumosRespuesta(BaseModel):
    tipo: TipoDeElementoParametrico
    clases: list[ClaseDeInsumoRespuesta]
    sugerencias_de_herramienta: list[SugerenciaDeHerramienta] = Field(
        description="Herramienta y equipo no trae insumos en el catálogo: el andamio se ofrece como sugerencia (insumo provisional sin precio)."
    )


class InsumoDeElementoRespuesta(BaseModel):
    id: UUID | None
    clave: str
    descripcion: str
    clase: ClaseDeInsumo | None
    familia: str | None
    subfamilia: str | None
    unidad: str | None
    precio: float | None = Field(description="`null` si el insumo no tiene precio (provisional): Costos se lo asigna.")
    sin_precio: bool
    provisional: bool = Field(description="Creado desde un elemento, sin precio hasta que Costos lo asigne.")
    permitido: bool = Field(description="Si el tipo de este elemento admite su familia: solo esos se pueden agregar.")


class MaterialElegido(BaseModel):
    material: Literal["concreto", "alambre", "varilla", "anillo", "armex", "cimbra"]
    clave: str
    consumo: float | None = Field(description="En la cimbra, el consumo por unidad de cálculo del elemento.")
    insumo: InsumoDeElementoRespuesta | None = Field(description="`null` si la clave ya no existe en la base de datos.")


class InsumoAgregado(BaseModel):
    id: UUID
    clase: ClaseDeInsumo
    cantidad: float = Field(description="Por unidad de cálculo del elemento.")
    insumo: InsumoDeElementoRespuesta


class InsumosDelElementoRespuesta(BaseModel):
    elemento_id: UUID
    tipo: TipoDeElementoParametrico
    materiales: list[MaterialElegido]
    insumos: list[InsumoAgregado]


class InsumoParaAgregar(BaseModel):
    insumo_id: UUID
    cantidad: float = Field(default=0, ge=0, le=1_000_000, description="Por unidad de cálculo del elemento; 0 = por definir.")


class AgregarInsumosPeticion(BaseModel):
    insumos: list[InsumoParaAgregar] = Field(min_length=1, max_length=100, description="Todo o nada: si uno es de otra familia no se agrega ninguno.")


class AgregarInsumosRespuesta(BaseModel):
    agregados: int = Field(description="Los que ya estaban en el elemento no se repiten.")


class CantidadDelInsumoPeticion(BaseModel):
    cantidad: float = Field(ge=0, le=1_000_000)


class InsumoProvisionalPeticion(BaseModel):
    clase: ClaseDeInsumo
    clave: str = Field(min_length=2, max_length=30)
    descripcion: str = Field(min_length=1, max_length=200)
    unidad: str = Field(min_length=1, max_length=12, description="Una unidad del catálogo (pza, kg, m3, jornal…) o su sinónimo.")
    familia: str | None = Field(default=None, max_length=80, description="Una de las familias que admite el tipo; en herramienta y equipo no se manda.")
    subfamilia: str | None = Field(default=None, max_length=80)


class InsumoProvisionalCreado(BaseModel):
    id: UUID


class FilaDeComparacion(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    catalogo: float | None = Field(description="Cantidad por unidad del concepto en el catálogo (con sus auxiliares expandidos); `null` si el catálogo no lo trae.")
    elemento: float | None = Field(description="Cantidad que calcula el elemento; `null` si no lo trae.")
    diferencia_pct: float | None = Field(description="(elemento − catálogo) ÷ catálogo × 100.")
    marca: MarcaDeComparacion = Field(description="= hasta 3 %, ≈ hasta 8 %, ≠ más; `solo_catalogo` / `solo_elemento` si un lado no lo trae.")


class ManoDeObraDelCatalogo(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    cantidad: float
    costo: float | None


class ResumenDeComparacion(BaseModel):
    igual: int = Field(description="Insumos con la marca `=`.")
    aproximado: int = Field(description="Insumos con la marca `≈`.")
    distinto: int = Field(description="Insumos con la marca `≠`.")
    solo_catalogo: int
    solo_elemento: int


class ConceptoComparado(BaseModel):
    fila_id: UUID = Field(description="La fila del concepto en el elemento (`conceptos-por-contexto`).")
    concepto_clave: str
    concepto_descripcion: str
    unidad: str
    estado: Literal["propuesto", "autorizado"]
    toma: dict[str, bool]
    sin_catalogo: bool = Field(description="Concepto nuevo propuesto: no tiene composición en el catálogo con qué comparar.")
    avisos: list[str]
    filas: list[FilaDeComparacion]
    mano_de_obra: list[ManoDeObraDelCatalogo] = Field(description="Mano de obra y destajo del concepto: el elemento no los calcula y no se comparan.")
    resumen: ResumenDeComparacion
    coincide: bool = Field(description="Ningún insumo es ≠ y ninguno sale solo en un lado.")


class ComparacionRespuesta(BaseModel):
    elemento_id: UUID
    umbral_igual_pct: float
    umbral_aproximado_pct: float
    conceptos: list[ConceptoComparado]


def _insumo(f: dict[str, object]) -> InsumoDeElementoRespuesta:
    return InsumoDeElementoRespuesta(**f)  # type: ignore[arg-type]


@router.get(
    "/elementos-parametricos/familias-de-insumos",
    response_model=FamiliasDeInsumosRespuesta,
    summary="Las clases y familias de insumos, con las que admite un tipo de elemento",
)
async def familias_de_insumos(
    tipo: Annotated[TipoDeElementoParametrico, Query(description="El tipo de elemento.")], caso_uso: GestionarInsumosDeElementoDep
) -> FamiliasDeInsumosRespuesta:
    """Salen todas las familias (M-55); las `usual` son las que el tipo admite. La losa aún no tiene lista."""
    return FamiliasDeInsumosRespuesta(**await caso_uso.familias(tipo))  # type: ignore[arg-type]


@router.get(
    "/elementos-parametricos/{elemento_id}/insumos-disponibles",
    response_model=list[InsumoDeElementoRespuesta],
    summary="Buscar insumos de la base de datos para agregar al elemento (clase, familia y texto)",
    responses={404: {"description": "El elemento no existe o está fuera de tu alcance."}},
)
async def buscar_insumos(
    elemento_id: UUID,
    caso_uso: GestionarInsumosDeElementoDep,
    clase: Annotated[ClaseDeInsumo | None, Query()] = None,
    familia: Annotated[str | None, Query(max_length=80, description="Familia o subfamilia.")] = None,
    q: Annotated[str | None, Query(max_length=80, description="Texto en la clave, la descripción o la familia.")] = None,
    limite: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[InsumoDeElementoRespuesta]:
    return [_insumo(f) for f in await caso_uso.buscar(elemento_id, clase=clase, familia=familia, q=q, limite=limite)]


@router.get(
    "/elementos-parametricos/{elemento_id}/insumos",
    response_model=InsumosDelElementoRespuesta,
    summary="Los materiales que eligió el elemento y los insumos que se le agregaron",
    responses={404: {"description": "El elemento no existe o está fuera de tu alcance."}},
)
async def insumos_del_elemento(elemento_id: UUID, caso_uso: GestionarInsumosDeElementoDep) -> InsumosDelElementoRespuesta:
    r = await caso_uso.del_elemento(elemento_id)
    return InsumosDelElementoRespuesta(
        elemento_id=r["elemento_id"],
        tipo=r["tipo"],
        materiales=[
            MaterialElegido(
                material=m["material"], clave=m["clave"], consumo=m["consumo"], insumo=_insumo(m["insumo"]) if m["insumo"] else None
            )
            for m in r["materiales"]
        ],
        insumos=[
            InsumoAgregado(id=i["id"], clase=i["clase"], cantidad=i["cantidad"], insumo=_insumo(i["insumo"])) for i in r["insumos"]
        ],
    )


@router.post(
    "/elementos-parametricos/{elemento_id}/insumos",
    response_model=AgregarInsumosRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar uno o varios insumos permitidos al elemento",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_DEFINEN))],
    responses={
        403: {"description": "Lo definen Control de obra y Costos."},
        404: {"description": "El elemento o un insumo no existen o están fuera de tu alcance."},
        422: {"description": "Un insumo es de una familia que el tipo de elemento no admite (el mensaje dice cuáles sí)."},
    },
)
async def agregar_insumos(
    elemento_id: UUID, peticion: AgregarInsumosPeticion, ctx: ContextoActual, caso_uso: GestionarInsumosDeElementoDep
) -> AgregarInsumosRespuesta:
    n = await caso_uso.agregar(
        ComandoAgregarInsumos(
            elemento_id=elemento_id, insumos=[(i.insumo_id, i.cantidad) for i in peticion.insumos], autor_id=ctx.usuario_id
        )
    )
    return AgregarInsumosRespuesta(agregados=n)


@router.patch(
    "/elementos-parametricos/{elemento_id}/insumos/{insumo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cambiar la cantidad de un insumo agregado al elemento",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_DEFINEN))],
    responses={403: {"description": "Lo definen Control de obra y Costos."}, 404: {"description": "El elemento no tiene ese insumo."}},
)
async def cambiar_cantidad_del_insumo(
    elemento_id: UUID, insumo_id: UUID, peticion: CantidadDelInsumoPeticion, caso_uso: GestionarInsumosDeElementoDep
) -> None:
    await caso_uso.cambiar_cantidad(elemento_id, insumo_id, peticion.cantidad)


@router.delete(
    "/elementos-parametricos/{elemento_id}/insumos/{insumo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Quitar un insumo del elemento",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_DEFINEN))],
    responses={403: {"description": "Lo definen Control de obra y Costos."}, 404: {"description": "El elemento no tiene ese insumo."}},
)
async def quitar_insumo(elemento_id: UUID, insumo_id: UUID, caso_uso: GestionarInsumosDeElementoDep) -> None:
    await caso_uso.quitar(elemento_id, insumo_id)


@router.post(
    "/elementos-parametricos/{elemento_id}/insumos-nuevos",
    response_model=InsumoProvisionalCreado,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un insumo desde el elemento: provisional y sin precio",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_DEFINEN))],
    responses={
        403: {"description": "Lo definen Control de obra y Costos."},
        404: {"description": "El elemento no existe o está fuera de tu alcance."},
        422: {"description": "La clave ya existe, la unidad no existe o la familia no es de las que admite el tipo de elemento."},
    },
)
async def crear_insumo_provisional(
    elemento_id: UUID, peticion: InsumoProvisionalPeticion, ctx: ContextoActual, caso_uso: GestionarInsumosDeElementoDep
) -> InsumoProvisionalCreado:
    """Solo se crea en las familias de su tipo de elemento; nunca lleva precio: Costos se lo asigna. Queda disponible en
    todos los selectores. El andamio de herramienta y equipo es la sugerencia de partida."""
    nuevo = await caso_uso.crear_provisional(
        ComandoCrearInsumoProvisional(
            elemento_id=elemento_id,
            clase=peticion.clase,
            clave=peticion.clave,
            descripcion=peticion.descripcion,
            unidad=peticion.unidad,
            autor_id=ctx.usuario_id,
            familia=peticion.familia,
            subfamilia=peticion.subfamilia,
        )
    )
    return InsumoProvisionalCreado(id=nuevo)


@router.get(
    "/elementos-parametricos/{elemento_id}/comparacion",
    response_model=ComparacionRespuesta,
    summary="Insumo por insumo: lo que calcula el elemento contra el concepto del catálogo",
    responses={404: {"description": "El elemento o el concepto no existen o están fuera de tu alcance."}},
)
async def comparar_con_el_catalogo(
    elemento_id: UUID,
    caso_uso: GestionarInsumosDeElementoDep,
    fila_id: Annotated[UUID | None, Query(description="Solo este concepto del elemento; sin él, todos.")] = None,
) -> ComparacionRespuesta:
    """Compara cada concepto que paga una parte del elemento con su composición real del catálogo (auxiliares expandidos):
    cantidad del elemento contra la del catálogo, diferencia en % y marca `=` (hasta 3 %), `≈` (hasta 8 %) o `≠`. La mano de
    obra no se compara. Lo que el catálogo contradice no se corrige: se muestra."""
    r = await caso_uso.comparacion(elemento_id, fila_id=fila_id)
    return ComparacionRespuesta(
        elemento_id=r["elemento_id"],
        umbral_igual_pct=r["umbral_igual_pct"],
        umbral_aproximado_pct=r["umbral_aproximado_pct"],
        conceptos=[
            ConceptoComparado(
                fila_id=c["fila_id"],
                concepto_clave=c["concepto_clave"],
                concepto_descripcion=c["concepto_descripcion"],
                unidad=c["unidad"],
                estado=c["estado"],
                toma=c["toma"],
                sin_catalogo=c["sin_catalogo"],
                avisos=c["avisos"],
                filas=[FilaDeComparacion(**{k: f[k] for k in FilaDeComparacion.model_fields}) for f in c["filas"]],
                mano_de_obra=[ManoDeObraDelCatalogo(**m) for m in c["mano_de_obra"]],
                resumen=ResumenDeComparacion(
                    igual=c["resumen"]["="],
                    aproximado=c["resumen"]["≈"],
                    distinto=c["resumen"]["≠"],
                    solo_catalogo=c["resumen"]["solo_catalogo"],
                    solo_elemento=c["resumen"]["solo_elemento"],
                ),
                coincide=c["coincide"],
            )
            for c in r["conceptos"]
        ],
    )
