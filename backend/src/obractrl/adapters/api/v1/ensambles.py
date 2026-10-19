"""Endpoints del catálogo de ensambles paramétricos.

Spec §11.2 ("Catálogos · APU") · skill `erp-parametrico` (cerebro
CONOCIMIENTO.md §5.7-§5.10) · §12.11.

Controladores delgados: validan el DTO, delegan en el caso de uso y mapean
el resultado. **Cero lógica de negocio aquí** (§12.11) — las invariantes
viven en `domain.catalogos.ensamble` y la orquestación en
`application.casos_uso.gestionar_ensamble`.

Roles (§11.2, mismo criterio que `/conceptos/*/cpu` y `/conceptos/*
/explosion` en `catalogos.py`): leer el catálogo, la explosión y la cohorte
es de **Control de obra** y **Super intendente**; crear un ensamble
(Extracción) y generar/regenerar una instancia son de **Control de obra**
—mismo rol que escribe presupuesto y el catálogo de APU.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    ExplotarEnsambleDep,
    ExtraerEnsambleDep,
    GenerarDesdeEnsambleDep,
)
from obractrl.adapters.api.dependencias import SesionRLS, exigir_rol
from obractrl.adapters.repos.ensambles_sql import RepositorioEnsamblesSQL
from obractrl.adapters.repos.generacion_ensamble_sql import (
    RepositorioGeneracionDePresupuestoSQL,
)
from obractrl.application.casos_uso.gestionar_ensamble import (
    ComandoExtraerEnsamble,
    ComandoGenerarDesdeEnsamble,
    EnsambleNoEncontrado,
    ReporteGeneracion,
)
from obractrl.domain.catalogos.ensamble import (
    EstadoRenglonGenerado,
    ExplosionEnsambleCalculada,
    PartidaExistente,
    RenglonEnsamble,
    RenglonGenerado,
    ValorPartida,
)
from obractrl.domain.shared.diccionario import (
    OrigenCantidadEnsamble,
    Rol,
    TipoHijoEnsamble,
)
from obractrl.domain.shared.valores import PrecioUnitario

router = APIRouter(tags=["ensambles"])

ENSAMBLES = Depends(exigir_rol(Rol.CONTROL_OBRA))
"""Alta de ensamble (Extracción) y Generación/regeneración: Control de obra."""

CONSULTA_ENSAMBLES = Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE))
"""Catálogo, renglones, cohorte y explosión: C y SI, igual que el CPU de APU."""

IncluirInactivos = Annotated[
    bool, Query(description="Incluye los ensambles dados de baja (§8.7).")
]
FactorPreview = Annotated[
    Decimal,
    Query(description="Cuántas veces entra el ensamble (§6); 1 = una instancia."),
]


# --- DTOs de respuesta -----------------------------------------------------


class EnsambleRespuesta(BaseModel):
    id: UUID
    clave: str
    nombre: str
    divisor_concepto_id: UUID | None = Field(
        default=None,
        description="El concepto que normaliza la tasa de este ensamble (§5.7).",
    )
    divisor_nombre: str | None = None
    tasa: Decimal | None = Field(
        default=None, description="Publicada sobre la cohorte declarada (§5.7)."
    )
    dispersion: Decimal | None = Field(
        default=None, description="Coeficiente de variación, en por ciento."
    )
    tasa_calculada_en: datetime | None = None
    estatus: str = "activo"

    @classmethod
    def desde_fila(cls, fila: dict) -> EnsambleRespuesta:
        return cls(
            id=fila["id"],
            clave=fila["clave"],
            nombre=fila["nombre"],
            divisor_concepto_id=fila["divisor_concepto_id"],
            divisor_nombre=fila["divisor_nombre"],
            tasa=fila["tasa"],
            dispersion=fila["dispersion"],
            tasa_calculada_en=fila["tasa_calculada_en"],
            estatus=fila["estatus"],
        )


class RenglonEnsambleRespuesta(BaseModel):
    id: UUID
    cantidad: Decimal
    origen: OrigenCantidadEnsamble
    orden: int
    concepto_id: UUID | None = None
    concepto_clave: str | None = None
    sub_ensamble_id: UUID | None = None
    sub_ensamble_clave: str | None = None
    presupuesto_origen_id: UUID | None = Field(
        default=None,
        description="Referencia informativa (§3): nunca una liga estructural.",
    )

    @classmethod
    def desde_fila(cls, fila: dict) -> RenglonEnsambleRespuesta:
        return cls(
            id=fila["id"],
            cantidad=fila["cantidad"],
            origen=fila["origen"],
            orden=fila["orden"],
            concepto_id=fila["concepto_id"],
            concepto_clave=fila["concepto_clave"],
            sub_ensamble_id=fila["sub_ensamble_id"],
            sub_ensamble_clave=fila["sub_ensamble_clave"],
            presupuesto_origen_id=fila["presupuesto_origen_id"],
        )


class CohorteItemRespuesta(BaseModel):
    prototipo_id: UUID
    prototipo_clave: str

    @classmethod
    def desde_fila(cls, fila: dict) -> CohorteItemRespuesta:
        return cls(prototipo_id=fila["prototipo_id"], prototipo_clave=fila["prototipo_clave"])


class InstanciaEnsambleRespuesta(BaseModel):
    """Un nodo del árbol de un prototipo que este ensamble generó (skill §6).

    Es lo que se le pasa a `POST /ensambles/{id}/generar` como
    `prototipo_nodo_id` para regenerarlo."""

    id: UUID
    prototipo_id: UUID
    prototipo_clave: str
    parent_id: UUID | None = None
    nombre: str
    factor: Decimal = Field(description="Cuántas veces entra el ensamble en esta instancia.")
    orden: int

    @classmethod
    def desde_fila(cls, fila: dict) -> InstanciaEnsambleRespuesta:
        return cls(
            id=fila["id"],
            prototipo_id=fila["prototipo_id"],
            prototipo_clave=fila["prototipo_clave"],
            parent_id=fila["parent_id"],
            nombre=fila["nombre"],
            factor=fila["ensamble_factor"],
            orden=fila["orden"],
        )


class PrecioEnsambleRespuesta(BaseModel):
    """Costo de un ensamble con su desglose de destajo (§7.3, skill §4).

    No se llama `PrecioUnitarioRespuesta` aunque se parezca al de
    `catalogos.py`: OpenAPI nombra los esquemas por la clase, y con dos
    homónimos FastAPI **renombra el que ya estaba publicado** (prefijo de
    módulo), lo que cambia los tipos que Orval genera para el front y el
    móvil. Un nombre propio deja el contrato existente intacto."""

    total: Decimal
    destajo: Decimal


def _precio(precio: PrecioUnitario) -> PrecioEnsambleRespuesta:
    return PrecioEnsambleRespuesta(total=precio.total.monto, destajo=precio.destajo.monto)


class LineaEnsambleRespuesta(BaseModel):
    ruta: list[str]
    nivel: int
    tipo_hijo: TipoHijoEnsamble
    referencia: str = Field(description="Clave del concepto o del sub-ensamble (§3.3).")
    cantidad_unitaria: Decimal = Field(description="Por unidad del padre inmediato.")
    cantidad: Decimal = Field(description="Acumulada desde la raíz, con el factor aplicado.")
    costo_unitario: Decimal
    destajo_unitario: Decimal
    importe: Decimal
    importe_destajo: Decimal


class ExplosionEnsambleRespuesta(BaseModel):
    clave: str
    lineas: list[LineaEnsambleRespuesta]
    precio: PrecioEnsambleRespuesta

    @classmethod
    def desde_dominio(cls, calculada: ExplosionEnsambleCalculada) -> ExplosionEnsambleRespuesta:
        return cls(
            clave=calculada.clave,
            lineas=[
                LineaEnsambleRespuesta(
                    ruta=list(linea.ruta),
                    nivel=linea.nivel,
                    tipo_hijo=linea.tipo_hijo,
                    referencia=linea.referencia,
                    cantidad_unitaria=linea.cantidad_unitaria,
                    cantidad=linea.cantidad,
                    costo_unitario=linea.costo_unitario,
                    destajo_unitario=linea.destajo_unitario,
                    importe=linea.importe,
                    importe_destajo=linea.importe_destajo,
                )
                for linea in calculada.lineas
            ],
            precio=_precio(calculada.precio),
        )


class EnsambleCreadoRespuesta(BaseModel):
    id: UUID
    clave: str
    nombre: str
    renglones: int
    cohorte: list[UUID]


class ValorPartidaRespuesta(BaseModel):
    cantidad: Decimal
    precio_unitario: Decimal

    @classmethod
    def desde_dominio(cls, valor: ValorPartida) -> ValorPartidaRespuesta:
        return cls(cantidad=valor.cantidad, precio_unitario=valor.precio_unitario)


class PartidaExistenteRespuesta(BaseModel):
    actual: ValorPartidaRespuesta
    snapshot: ValorPartidaRespuesta | None = Field(
        default=None,
        description="Lo que tenía al generarse. Nulo: partida capturada, nunca generada.",
    )

    @classmethod
    def desde_dominio(cls, existente: PartidaExistente) -> PartidaExistenteRespuesta:
        return cls(
            actual=ValorPartidaRespuesta.desde_dominio(existente.actual),
            snapshot=(
                ValorPartidaRespuesta.desde_dominio(existente.snapshot)
                if existente.snapshot is not None
                else None
            ),
        )


class RenglonGeneradoRespuesta(BaseModel):
    clave_concepto: str
    estado: EstadoRenglonGenerado
    receta: ValorPartidaRespuesta | None = Field(
        default=None, description="Lo que el ensamble pide hoy. Nulo solo en SOBRA."
    )
    existente: PartidaExistenteRespuesta | None = Field(
        default=None, description="Lo que ya hay en el presupuesto. Nulo solo en NUEVO."
    )

    @classmethod
    def desde_dominio(cls, renglon: RenglonGenerado) -> RenglonGeneradoRespuesta:
        return cls(
            clave_concepto=renglon.clave_concepto,
            estado=renglon.estado,
            receta=(
                ValorPartidaRespuesta.desde_dominio(renglon.receta)
                if renglon.receta is not None
                else None
            ),
            existente=(
                PartidaExistenteRespuesta.desde_dominio(renglon.existente)
                if renglon.existente is not None
                else None
            ),
        )


class ReporteGeneracionRespuesta(BaseModel):
    prototipo_nodo_id: UUID
    nuevos: list[str] = Field(description="Conceptos creados sin preguntar.")
    actualizados: list[str] = Field(description="Conceptos refrescados sin preguntar.")
    pendientes: list[RenglonGeneradoRespuesta] = Field(
        description=(
            "DESVINCULADO/CONFLICTO/SOBRA (§6, §8 regla 11): ninguno se "
            "escribió solo — hace falta una decisión para cada uno."
        )
    )

    @classmethod
    def desde_dominio(cls, reporte: ReporteGeneracion) -> ReporteGeneracionRespuesta:
        return cls(
            prototipo_nodo_id=reporte.prototipo_nodo_id,
            nuevos=list(reporte.nuevos),
            actualizados=list(reporte.actualizados),
            pendientes=[RenglonGeneradoRespuesta.desde_dominio(r) for r in reporte.pendientes],
        )


# --- DTOs de petición -------------------------------------------------------


class RenglonEnsamblePeticion(BaseModel):
    cantidad: Decimal
    origen: OrigenCantidadEnsamble
    clave_concepto: str | None = Field(
        default=None, description="Exactamente uno de clave_concepto/clave_sub_ensamble."
    )
    clave_sub_ensamble: str | None = None
    orden: int = 0

    def al_dominio(self) -> RenglonEnsamble:
        return RenglonEnsamble(
            cantidad=self.cantidad,
            origen=self.origen,
            clave_concepto=self.clave_concepto,
            clave_sub_ensamble=self.clave_sub_ensamble,
            orden=self.orden,
        )


class CrearEnsamblePeticion(BaseModel):
    clave: str
    nombre: str
    renglones: list[RenglonEnsamblePeticion] = Field(default_factory=list)
    divisor_concepto_clave: str | None = None
    divisor_nombre: str | None = None
    presupuesto_origen_id: UUID | None = Field(
        default=None, description="De qué presupuesto se extrajeron estos renglones (§3)."
    )
    cohorte_prototipo_ids: list[UUID] = Field(default_factory=list)


class GenerarDesdeEnsamblePeticion(BaseModel):
    presupuesto_id: UUID
    prototipo_id: UUID
    factor: Decimal = Field(description="Cuántas veces entra el ensamble en esta instancia.")
    nombre: str
    prototipo_nodo_id: UUID | None = Field(
        default=None,
        description="La instancia a regenerar. Vacío: se crea una instancia nueva.",
    )
    parent_id: UUID | None = Field(
        default=None, description="Dónde colgar la instancia nueva en el árbol."
    )
    orden: int = 0


# --- Endpoints ---------------------------------------------------------


@router.get(
    "/ensambles",
    response_model=list[EnsambleRespuesta],
    summary="Catálogo de ensambles paramétricos",
    dependencies=[CONSULTA_ENSAMBLES],
)
async def listar_ensambles(
    sesion: SesionRLS, incluir_inactivos: IncluirInactivos = False
) -> list[EnsambleRespuesta]:
    filas = await RepositorioEnsamblesSQL(sesion).listar(solo_activos=not incluir_inactivos)
    return [EnsambleRespuesta.desde_fila(fila) for fila in filas]


@router.get(
    "/ensambles/{ensamble_id}",
    response_model=EnsambleRespuesta,
    summary="Un ensamble por id",
    dependencies=[CONSULTA_ENSAMBLES],
    responses={404: {"description": "El ensamble no existe o está fuera de tu alcance."}},
)
async def obtener_ensamble(ensamble_id: UUID, sesion: SesionRLS) -> EnsambleRespuesta:
    fila = await RepositorioEnsamblesSQL(sesion).obtener(ensamble_id)
    if fila is None:
        raise EnsambleNoEncontrado(ensamble_id)
    return EnsambleRespuesta.desde_fila(fila)


@router.get(
    "/ensambles/{ensamble_id}/renglones",
    response_model=list[RenglonEnsambleRespuesta],
    summary="Renglones directos del ensamble (sin bajar por sub-ensamble)",
    dependencies=[CONSULTA_ENSAMBLES],
    responses={404: {"description": "El ensamble no existe o está fuera de tu alcance."}},
)
async def listar_renglones(
    ensamble_id: UUID, sesion: SesionRLS
) -> list[RenglonEnsambleRespuesta]:
    ensambles = RepositorioEnsamblesSQL(sesion)
    if await ensambles.obtener(ensamble_id) is None:
        raise EnsambleNoEncontrado(ensamble_id)
    filas = await ensambles.renglones(ensamble_id)
    return [RenglonEnsambleRespuesta.desde_fila(fila) for fila in filas]


@router.get(
    "/ensambles/{ensamble_id}/cohorte",
    response_model=list[CohorteItemRespuesta],
    summary="Prototipos de la cohorte declarada del ensamble",
    dependencies=[CONSULTA_ENSAMBLES],
    responses={404: {"description": "El ensamble no existe o está fuera de tu alcance."}},
)
async def listar_cohorte(ensamble_id: UUID, sesion: SesionRLS) -> list[CohorteItemRespuesta]:
    ensambles = RepositorioEnsamblesSQL(sesion)
    if await ensambles.obtener(ensamble_id) is None:
        raise EnsambleNoEncontrado(ensamble_id)
    filas = await ensambles.cohorte(ensamble_id)
    return [CohorteItemRespuesta.desde_fila(fila) for fila in filas]


@router.get(
    "/ensambles/{ensamble_id}/instancias",
    response_model=list[InstanciaEnsambleRespuesta],
    summary="Instancias que este ensamble ya generó (para regenerarlas)",
    dependencies=[CONSULTA_ENSAMBLES],
    responses={404: {"description": "El ensamble no existe o está fuera de tu alcance."}},
)
async def listar_instancias(
    ensamble_id: UUID, sesion: SesionRLS
) -> list[InstanciaEnsambleRespuesta]:
    if await RepositorioEnsamblesSQL(sesion).obtener(ensamble_id) is None:
        raise EnsambleNoEncontrado(ensamble_id)
    filas = await RepositorioGeneracionDePresupuestoSQL(sesion).instancias_de_ensamble(
        ensamble_id
    )
    return [InstanciaEnsambleRespuesta.desde_fila(fila) for fila in filas]


@router.get(
    "/ensambles/{ensamble_id}/explosion",
    response_model=ExplosionEnsambleRespuesta,
    summary="Preview de costo y composición (sin generar nada)",
    dependencies=[CONSULTA_ENSAMBLES],
    responses={404: {"description": "El ensamble no existe o está fuera de tu alcance."}},
)
async def explotar_ensamble(
    ensamble_id: UUID, caso_uso: ExplotarEnsambleDep, factor: FactorPreview = Decimal(1)
) -> ExplosionEnsambleRespuesta:
    """Árbol completo del ensamble: conceptos y sub-ensambles anidados,
    con costo y destajo (skill §4) — con el factor de una instancia
    hipotética, sin crear ni tocar nada."""
    calculada = await caso_uso.ejecutar(ensamble_id, factor=factor)
    return ExplosionEnsambleRespuesta.desde_dominio(calculada)


@router.post(
    "/ensambles",
    response_model=EnsambleCreadoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Extracción: arma un ensamble desde lo ya construido",
    dependencies=[ENSAMBLES],
    responses={
        404: {"description": "Un concepto o sub-ensamble referido no existe."},
        409: {"description": "Ya existe un ensamble con esa clave."},
        422: {"description": "Un renglón no apunta a concepto XOR sub-ensamble (§0, §2-§3)."},
    },
)
async def extraer_ensamble(
    peticion: CrearEnsamblePeticion, caso_uso: ExtraerEnsambleDep
) -> EnsambleCreadoRespuesta:
    """El llamador ya decidió, renglón por renglón, qué entra y con qué
    origen (§2) — este endpoint solo resuelve clave→id y persiste."""
    creado = await caso_uso.ejecutar(
        ComandoExtraerEnsamble(
            clave=peticion.clave,
            nombre=peticion.nombre,
            renglones=[r.al_dominio() for r in peticion.renglones],
            divisor_concepto_clave=peticion.divisor_concepto_clave,
            divisor_nombre=peticion.divisor_nombre,
            presupuesto_origen_id=peticion.presupuesto_origen_id,
            cohorte_prototipo_ids=peticion.cohorte_prototipo_ids,
        )
    )
    return EnsambleCreadoRespuesta(
        id=creado.id,
        clave=creado.clave,
        nombre=creado.nombre,
        renglones=creado.renglones,
        cohorte=list(creado.cohorte),
    )


@router.post(
    "/ensambles/{ensamble_id}/generar",
    response_model=ReporteGeneracionRespuesta,
    summary="Generación: compone (o regenera) una instancia en un presupuesto",
    dependencies=[ENSAMBLES],
    responses={
        404: {
            "description": (
                "El ensamble o el presupuesto no existen, o la instancia a "
                "regenerar no existe."
            )
        },
        409: {"description": "La instancia ya fue generada por otro ensamble."},
    },
)
async def generar_desde_ensamble(
    ensamble_id: UUID,
    peticion: GenerarDesdeEnsamblePeticion,
    caso_uso: GenerarDesdeEnsambleDep,
) -> ReporteGeneracionRespuesta:
    """Un mismo botón para generar (sin `prototipo_nodo_id`) y regenerar
    (con él): solo NUEVO/ACTUALIZADO se escriben, el resto se reporta en
    `pendientes` para que el usuario decida (§6, §8 regla 11)."""
    reporte = await caso_uso.ejecutar(
        ComandoGenerarDesdeEnsamble(
            presupuesto_id=peticion.presupuesto_id,
            prototipo_id=peticion.prototipo_id,
            ensamble_id=ensamble_id,
            factor=peticion.factor,
            nombre=peticion.nombre,
            prototipo_nodo_id=peticion.prototipo_nodo_id,
            parent_id=peticion.parent_id,
            orden=peticion.orden,
        )
    )
    return ReporteGeneracionRespuesta.desde_dominio(reporte)
