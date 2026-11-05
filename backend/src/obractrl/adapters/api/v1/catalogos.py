"""Endpoints de catálogos maestros y APU.

Spec §11.2 ("Catálogos · APU") · §7.3 · §10.1 · §3.5 (IVA) · §3.3 (clave).

Controladores delgados: validan el DTO, delegan en el caso de uso y mapean el
resultado. **Cero lógica de negocio aquí** (§12.11) — las invariantes viven en
`domain.catalogos.reglas` y el APU en `domain.catalogos.apu`.

Roles (§11.2): `GET/POST` de `/unidades`, `/familias`, `/insumos`,
`/conceptos`, `/materiales` y `/contratistas` son de **Control de obra**;
`GET /conceptos/{id}/cpu` y `/explosion` los ven además el **Super
intendente**; publicar una versión de CPU vuelve a ser de Control de obra.

**`/materiales` no es otro catálogo:** `Material` = `Insumo` con
`tipo='material'` (§7.3). Las dos rutas son la misma tabla, el mismo
repositorio y el mismo caso de uso, con el tipo fijado aquí en el borde.

La **lectura** de catálogos también se sirve directo de Supabase al front
(§10.7); estos `GET` existen para el mismo dato por la ruta del backend
—Orval genera hooks de ambos— y para que el móvil no dependa de supabase-js.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    CrearConceptoDep,
    CrearContratistaDep,
    CrearCuadrillaDep,
    CrearFamiliaDep,
    CrearInsumoDep,
    CrearUnidadDep,
    EliminarVersionDeCPUDep,
    EliminarVersionDeCuadrillaDep,
    ExplotarConceptoDep,
    GestionarMatricesDeConceptoDep,
    ObtenerCPUDep,
    PublicarVersionCPUDep,
)
from obractrl.adapters.api.dependencias import SesionRLS, exigir_rol
from obractrl.adapters.repos.conceptos_sql import RepositorioConceptosSQL
from obractrl.adapters.repos.contratistas_sql import RepositorioContratistasSQL
from obractrl.adapters.repos.cuadrillas_sql import RepositorioCuadrillasSQL
from obractrl.adapters.repos.familias_sql import RepositorioFamiliasSQL
from obractrl.adapters.repos.insumos_sql import RepositorioInsumosSQL
from obractrl.adapters.repos.niveles_etapas_sql import RepositorioNivelesEtapasSQL
from obractrl.adapters.repos.unidades_sql import RepositorioUnidadesSQL
from obractrl.application.casos_uso.calcular_cpu import (
    ComandoPublicarVersionCPU,
    CPUDelConcepto,
    VersionPublicada,
)
from obractrl.application.casos_uso.gestionar_catalogos import (
    ComandoCrearConcepto,
    ComandoCrearContratista,
    ComandoCrearCuadrilla,
    ComandoCrearFamilia,
    ComandoCrearInsumo,
    ComandoCrearUnidad,
    InsumoCreado,
)
from obractrl.application.casos_uso.matrices_de_concepto import (
    ComandoPonerMatriz,
    MatrizNueva,
)
from obractrl.domain.catalogos.apu import ExplosionCalculada, VersionCPU
from obractrl.domain.catalogos.cantidad import FormulaDePiezasComerciales
from obractrl.domain.catalogos.reglas import ErrorDeCatalogo, Insumo
from obractrl.domain.catalogos.rendimientos import (
    jornadas_por_unidad,
    razon_teorico_calculado,
    rendimiento_calculado,
)
from obractrl.domain.shared.diccionario import (
    CategoriaExplosion,
    Rol,
    TipoConcepto,
    TipoHijoExplosion,
    TipoInsumo,
)
from obractrl.domain.shared.valores import PrecioUnitario

router = APIRouter(tags=["catalogos"])

CATALOGOS = Depends(exigir_rol(Rol.CONTROL_OBRA))
"""Catálogos y APU: Control de obra (§11.2, §5.1 "Configuración")."""

LECTURA_PARA_ALTAS = Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.COSTOS))
"""Unidades, niveles y etapas: lo que Costos necesita para dar de alta un concepto desde el
cuantificador (entrega 5). Solo lectura; escribir sigue siendo de Control de obra."""

CONSULTA_CPU_Y_COSTOS = Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE, Rol.COSTOS))
PUBLICA_CPU = Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.COSTOS))
"""El costo del catálogo: Costos lo ve y publica una versión nueva cuando cambia la composición
de un concepto (entrega 6, migración 0090)."""

CONSULTA_CPU = Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE))
"""`GET /conceptos/{id}/cpu` y `/explosion`: C y SI (§11.2)."""

IncluirInactivos = Annotated[
    bool, Query(description="Incluye los registros dados de baja (§8.7).")
]
FiltroFamilia = Annotated[
    UUID | None, Query(description="Acota a una familia del árbol (§7.3).")
]
FiltroVariante = Annotated[
    str | None,
    Query(description="Receta alterna del concepto; vacío = receta base (§2.2)."),
]


# --- Unidades (§7.3, §3.5) -----------------------------------------------


class CrearUnidadPeticion(BaseModel):
    clave: str = Field(min_length=1, description="Clave única del catálogo (§3.3).")
    nombre: str = Field(min_length=1)
    sinonimos: list[str] = Field(
        default_factory=list, description="Alias que cruzan a esta unidad (§10.3)."
    )
    factor: Decimal = Field(default=Decimal(1), description="Factor de conversión (§3.5).")


class UnidadRespuesta(BaseModel):
    id: UUID
    clave: str
    nombre: str
    sinonimos: list[str] = Field(default_factory=list)
    factor: Decimal = Decimal(1)
    estatus: str = "activo"

    @classmethod
    def desde_fila(cls, fila: dict) -> UnidadRespuesta:
        return cls(
            id=fila["id"],
            clave=fila["clave"],
            nombre=fila["nombre"],
            sinonimos=list(fila["sinonimos"] or []),
            factor=fila["factor"],
            estatus=fila["estatus"],
        )


@router.get(
    "/unidades",
    response_model=list[UnidadRespuesta],
    summary="Catálogo de unidades",
    dependencies=[LECTURA_PARA_ALTAS],
)
async def listar_unidades(
    sesion: SesionRLS, incluir_inactivos: IncluirInactivos = False
) -> list[UnidadRespuesta]:
    """Lectura simple sin orquestación de dominio —como `GET /proyectos`— así
    que consulta el repo directo: RLS ya acota el alcance (§12.4)."""
    filas = await RepositorioUnidadesSQL(sesion).listar(
        solo_activos=not incluir_inactivos
    )
    return [UnidadRespuesta.desde_fila(fila) for fila in filas]


@router.post(
    "/unidades",
    response_model=UnidadRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Alta de unidad",
    dependencies=[CATALOGOS],
    responses={422: {"description": "Datos de catálogo inválidos (§7.3)."}},
)
async def crear_unidad(
    peticion: CrearUnidadPeticion, caso_uso: CrearUnidadDep
) -> UnidadRespuesta:
    creada = await caso_uso.ejecutar(
        ComandoCrearUnidad(
            clave=peticion.clave,
            nombre=peticion.nombre,
            sinonimos=peticion.sinonimos,
            factor=peticion.factor,
        )
    )
    return UnidadRespuesta(
        id=creada.id,
        clave=str(creada.unidad.clave),
        nombre=creada.unidad.nombre,
        sinonimos=list(creada.unidad.sinonimos),
        factor=creada.unidad.factor,
    )


# --- Familias (§7.3, §3.5) -----------------------------------------------


class CrearFamiliaPeticion(BaseModel):
    clave: str = Field(min_length=1)
    nombre: str = Field(min_length=1)
    parent_id: UUID | None = Field(default=None, description="Padre en el árbol (§7.3).")
    aplica_a: str = Field(
        default="material", description="Familias de materiales o de conceptos (§10.1)."
    )
    iva_aplica: bool = Field(
        default=True,
        description=(
            "IVA de la familia (§3.5). Cada insumo puede sobrescribirlo; la "
            "tasa es configurable y se lee de BD (§8.7)."
        ),
    )


class FamiliaRespuesta(BaseModel):
    id: UUID
    clave: str
    nombre: str
    parent_id: UUID | None = None
    aplica_a: str = "material"
    iva_aplica: bool = True
    estatus: str = "activo"

    @classmethod
    def desde_fila(cls, fila: dict) -> FamiliaRespuesta:
        return cls(
            id=fila["id"],
            clave=fila["clave"],
            nombre=fila["nombre"],
            parent_id=fila["parent_id"],
            aplica_a=fila["aplica_a"],
            iva_aplica=fila["iva_aplica"],
            estatus=fila["estatus"],
        )


@router.get(
    "/familias",
    response_model=list[FamiliaRespuesta],
    summary="Árbol de familias",
    dependencies=[CATALOGOS],
)
async def listar_familias(
    sesion: SesionRLS,
    aplica_a: Annotated[
        str | None, Query(description="`material` o `concepto` (§10.1).")
    ] = None,
    incluir_inactivos: IncluirInactivos = False,
) -> list[FamiliaRespuesta]:
    filas = await RepositorioFamiliasSQL(sesion).listar(
        aplica_a=aplica_a, solo_activos=not incluir_inactivos
    )
    return [FamiliaRespuesta.desde_fila(fila) for fila in filas]


@router.post(
    "/familias",
    response_model=FamiliaRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Alta de familia",
    dependencies=[CATALOGOS],
    responses={422: {"description": "Datos de catálogo inválidos (§7.3)."}},
)
async def crear_familia(
    peticion: CrearFamiliaPeticion, caso_uso: CrearFamiliaDep
) -> FamiliaRespuesta:
    creada = await caso_uso.ejecutar(
        ComandoCrearFamilia(
            clave=peticion.clave,
            nombre=peticion.nombre,
            parent_id=peticion.parent_id,
            aplica_a=peticion.aplica_a,
            iva_aplica=peticion.iva_aplica,
        )
    )
    return FamiliaRespuesta(
        id=creada.id,
        clave=str(creada.familia.clave),
        nombre=creada.familia.nombre,
        parent_id=UUID(creada.familia.parent_id) if creada.familia.parent_id else None,
        aplica_a=creada.familia.aplica_a,
        iva_aplica=creada.familia.iva_aplica,
    )


# --- Insumos y materiales (§7.3) -----------------------------------------


class CrearInsumoPeticion(BaseModel):
    clave: str = Field(min_length=1)
    descripcion: str = Field(min_length=1)
    tipo: TipoInsumo = TipoInsumo.MATERIAL
    unidad_id: UUID | None = None
    familia_id: UUID | None = None
    costo_base: Decimal = Decimal(0)
    iva_aplica: bool | None = Field(
        default=None,
        description=(
            "Override del IVA de la familia (§3.5). Nulo = hereda de la familia."
        ),
    )
    factor_conversion: Decimal = Decimal(1)
    dias_entrega: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Plazo de entrega en dias: con cuanta anticipacion hay que pedirlo "
            "para tenerlo cuando el cronograma lo pide (§10.1). Vacio = usa la "
            "anticipacion global de quien consulta; cero = llega el mismo dia."
        ),
    )


class CrearMaterialPeticion(BaseModel):
    """`POST /materiales` — mismo cuerpo, sin `tipo`: es siempre `material` (§7.3)."""

    clave: str = Field(min_length=1)
    descripcion: str = Field(min_length=1)
    unidad_id: UUID | None = None
    familia_id: UUID | None = None
    costo_base: Decimal = Decimal(0)
    iva_aplica: bool | None = None
    factor_conversion: Decimal = Decimal(1)
    dias_entrega: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Plazo de entrega en dias: con cuanta anticipacion hay que pedirlo "
            "para tenerlo cuando el cronograma lo pide (§10.1). Vacio = usa la "
            "anticipacion global de quien consulta; cero = llega el mismo dia."
        ),
    )


class InsumoRespuesta(BaseModel):
    id: UUID
    tipo: TipoInsumo
    clave: str
    descripcion: str
    unidad_id: UUID | None = None
    familia_id: UUID | None = None
    costo_base: Decimal = Decimal(0)
    costo_base_actualizado: Decimal | None = None
    costo_promedio_almacen: Decimal | None = None
    costo_ultimo: Decimal | None = None
    origen: str = "base"
    iva_aplica: bool | None = None
    factor_conversion: Decimal = Decimal(1)
    cuadrilla_id: UUID | None = None
    """Cuadrilla asignada a este destajo (§10.6). Solo ``tipo=mano_obra``."""
    rendimiento_teorico: Decimal | None = None
    """Del archivo de mano de obra (§10.6). El "real" se deriva de la
    duración real de la obra — no es dato que se cargue ni se exponga aquí."""
    dias_entrega: int | None = None
    """Plazo de entrega (§10.1, migración 0044). `null` = no capturado, y ahí
    manda la anticipación global de quien consulta."""
    estatus: str = "activo"

    @classmethod
    def desde_fila(cls, fila: dict) -> InsumoRespuesta:
        return cls(
            id=fila["id"],
            tipo=TipoInsumo(str(fila["tipo"])),
            clave=fila["clave"],
            descripcion=fila["descripcion"],
            unidad_id=fila["unidad_id"],
            familia_id=fila["familia_id"],
            costo_base=fila["costo_base"],
            costo_base_actualizado=fila["costo_base_actualizado"],
            costo_promedio_almacen=fila["costo_promedio_almacen"],
            costo_ultimo=fila["costo_ultimo"],
            origen=fila["origen"],
            iva_aplica=fila["iva_aplica"],
            factor_conversion=fila["factor_conversion"],
            cuadrilla_id=fila["cuadrilla_id"],
            rendimiento_teorico=fila["rendimiento_teorico"],
            dias_entrega=fila["dias_entrega"],
            estatus=fila["estatus"],
        )


def _insumo_creado(creado: InsumoCreado) -> InsumoRespuesta:
    """Mapea el resultado del caso de uso al DTO (§12.11: DTOs en el borde)."""
    return InsumoRespuesta(
        id=creado.id,
        tipo=creado.insumo.tipo,
        clave=str(creado.insumo.clave),
        descripcion=creado.insumo.descripcion,
        unidad_id=UUID(creado.insumo.unidad_id) if creado.insumo.unidad_id else None,
        familia_id=UUID(creado.insumo.familia_id) if creado.insumo.familia_id else None,
        costo_base=creado.insumo.costo_base,
        iva_aplica=creado.insumo.iva_aplica,
        factor_conversion=creado.insumo.factor_conversion,
        dias_entrega=creado.insumo.dias_entrega,
    )


@router.get(
    "/insumos",
    response_model=list[InsumoRespuesta],
    summary="Catálogo de insumos",
    dependencies=[CATALOGOS],
)
async def listar_insumos(
    sesion: SesionRLS,
    tipo: Annotated[
        TipoInsumo | None, Query(description="Filtra por tipo de insumo (§8.2).")
    ] = None,
    familia_id: FiltroFamilia = None,
    incluir_inactivos: IncluirInactivos = False,
) -> list[InsumoRespuesta]:
    filas = await RepositorioInsumosSQL(sesion).listar(
        tipo=str(tipo) if tipo else None,
        familia_id=familia_id,
        solo_activos=not incluir_inactivos,
    )
    return [InsumoRespuesta.desde_fila(fila) for fila in filas]


@router.post(
    "/insumos",
    response_model=InsumoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Alta de insumo",
    dependencies=[CATALOGOS],
    responses={422: {"description": "Datos de catálogo inválidos (§7.3)."}},
)
async def crear_insumo(
    peticion: CrearInsumoPeticion, caso_uso: CrearInsumoDep
) -> InsumoRespuesta:
    return _insumo_creado(
        await caso_uso.ejecutar(
            ComandoCrearInsumo(
                tipo=str(peticion.tipo),
                clave=peticion.clave,
                descripcion=peticion.descripcion,
                unidad_id=peticion.unidad_id,
                familia_id=peticion.familia_id,
                costo_base=peticion.costo_base,
                iva_aplica=peticion.iva_aplica,
                factor_conversion=peticion.factor_conversion,
                dias_entrega=peticion.dias_entrega,
            )
        )
    )


@router.get(
    "/materiales",
    response_model=list[InsumoRespuesta],
    summary="Catálogo de materiales",
    dependencies=[CATALOGOS],
)
async def listar_materiales(
    sesion: SesionRLS,
    familia_id: FiltroFamilia = None,
    incluir_inactivos: IncluirInactivos = False,
) -> list[InsumoRespuesta]:
    """`Material` = `Insumo` con `tipo='material'` (§7.3): mismo repositorio,
    filtro fijado aquí. No hay tabla ni catálogo aparte."""
    filas = await RepositorioInsumosSQL(sesion).listar(
        tipo=str(TipoInsumo.MATERIAL),
        familia_id=familia_id,
        solo_activos=not incluir_inactivos,
    )
    return [InsumoRespuesta.desde_fila(fila) for fila in filas]


@router.post(
    "/materiales",
    response_model=InsumoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Alta de material",
    dependencies=[CATALOGOS],
    responses={422: {"description": "Datos de catálogo inválidos (§7.3)."}},
)
async def crear_material(
    peticion: CrearMaterialPeticion, caso_uso: CrearInsumoDep
) -> InsumoRespuesta:
    return _insumo_creado(
        await caso_uso.ejecutar(
            ComandoCrearInsumo(
                tipo=str(TipoInsumo.MATERIAL),
                clave=peticion.clave,
                descripcion=peticion.descripcion,
                unidad_id=peticion.unidad_id,
                familia_id=peticion.familia_id,
                costo_base=peticion.costo_base,
                iva_aplica=peticion.iva_aplica,
                factor_conversion=peticion.factor_conversion,
                dias_entrega=peticion.dias_entrega,
            )
        )
    )


# --- Contratistas (§7.3, §10.1) ------------------------------------------


class CrearContratistaPeticion(BaseModel):
    clave: str = Field(min_length=1)
    razon_social: str = Field(min_length=1)
    rfc: str | None = None
    contacto: str | None = None
    telefono: str | None = None
    email: str | None = None
    calificacion: Decimal | None = None
    frentes: list[UUID] = Field(
        default_factory=list, description="Frentes que atiende (`ContratistaFrente`)."
    )


class ContratistaRespuesta(BaseModel):
    id: UUID
    clave: str
    razon_social: str
    rfc: str | None = None
    contacto: str | None = None
    telefono: str | None = None
    email: str | None = None
    calificacion: Decimal | None = None
    estatus: str = "activo"

    @classmethod
    def desde_fila(cls, fila: dict) -> ContratistaRespuesta:
        return cls(
            id=fila["id"],
            clave=fila["clave"],
            razon_social=fila["razon_social"],
            rfc=fila["rfc"],
            contacto=fila["contacto"],
            telefono=fila["telefono"],
            email=fila["email"],
            calificacion=fila["calificacion"],
            estatus=fila["estatus"],
        )


@router.get(
    "/contratistas",
    response_model=list[ContratistaRespuesta],
    summary="Catálogo de contratistas",
    dependencies=[CATALOGOS],
)
async def listar_contratistas(
    sesion: SesionRLS, incluir_inactivos: IncluirInactivos = False
) -> list[ContratistaRespuesta]:
    filas = await RepositorioContratistasSQL(sesion).listar(
        solo_activos=not incluir_inactivos
    )
    return [ContratistaRespuesta.desde_fila(fila) for fila in filas]


@router.post(
    "/contratistas",
    response_model=ContratistaRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Alta de contratista",
    dependencies=[CATALOGOS],
    responses={422: {"description": "Datos de catálogo inválidos (§7.3)."}},
)
async def crear_contratista(
    peticion: CrearContratistaPeticion, caso_uso: CrearContratistaDep
) -> ContratistaRespuesta:
    creado = await caso_uso.ejecutar(
        ComandoCrearContratista(
            clave=peticion.clave,
            razon_social=peticion.razon_social,
            rfc=peticion.rfc,
            contacto=peticion.contacto,
            telefono=peticion.telefono,
            email=peticion.email,
            calificacion=peticion.calificacion,
            frentes=peticion.frentes,
        )
    )
    return ContratistaRespuesta(
        id=creado.id,
        clave=str(creado.contratista.clave),
        razon_social=creado.contratista.razon_social,
        rfc=creado.contratista.rfc,
        contacto=creado.contratista.contacto,
        telefono=creado.contratista.telefono,
        email=creado.contratista.email,
        calificacion=creado.contratista.calificacion,
    )


# --- Niveles y etapas de construcción (§7.4, §10.1, §10.6) ---------------
#
# Catálogo compartido por organización, no por prototipo: la clave se repite
# igual en cada prototipo del archivo de ingeniería (§7.4). Solo lectura
# aquí — el alta/edición la trae el cargador dedicado (migración 0037,
# `RepositorioNivelesEtapasSQL.crear_nivel`/`crear_etapa`, §10.6) o el
# árbol de presupuesto (`AplicadorPresupuesto`); ningún flujo hoy da de
# alta un nivel o etapa suelto desde esta pantalla.


class NivelRespuesta(BaseModel):
    id: UUID
    clave: str
    descripcion: str
    orden: int = 0
    importe: Decimal | None = None

    @classmethod
    def desde_fila(cls, fila: dict) -> NivelRespuesta:
        return cls(
            id=fila["id"],
            clave=fila["clave"],
            descripcion=fila["descripcion"],
            orden=fila["orden"],
            importe=fila["importe"],
        )


class EtapaRespuesta(BaseModel):
    id: UUID
    nivel_id: UUID | None = None
    frente_id: UUID | None = Field(
        default=None,
        description=(
            "Frente al que pertenece la etapa (§8.3, migración 0045). Un "
            "frente agrupa varias; vacío = sin asignar todavía."
        ),
    )
    clave: str
    descripcion: str
    orden: int = 0
    ponderacion: Decimal = Decimal(0)
    importe: Decimal | None = None

    @classmethod
    def desde_fila(cls, fila: dict) -> EtapaRespuesta:
        return cls(
            id=fila["id"],
            nivel_id=fila["nivel_id"],
            frente_id=fila["frente_id"],
            clave=fila["clave"],
            descripcion=fila["descripcion"],
            orden=fila["orden"],
            ponderacion=fila["ponderacion"],
            importe=fila["importe"],
        )


@router.get(
    "/niveles",
    response_model=list[NivelRespuesta],
    summary="Catálogo de niveles de construcción",
    dependencies=[LECTURA_PARA_ALTAS],
)
async def listar_niveles(sesion: SesionRLS) -> list[NivelRespuesta]:
    """Lectura simple sin orquestación de dominio —como `GET /unidades`—
    así que consulta el repo directo: RLS ya acota el alcance (§12.4)."""
    filas = await RepositorioNivelesEtapasSQL(sesion).listar_niveles()
    return [NivelRespuesta.desde_fila(fila) for fila in filas]


@router.get(
    "/etapas",
    response_model=list[EtapaRespuesta],
    summary="Catálogo de etapas de construcción",
    dependencies=[LECTURA_PARA_ALTAS],
)
async def listar_etapas(sesion: SesionRLS) -> list[EtapaRespuesta]:
    filas = await RepositorioNivelesEtapasSQL(sesion).listar_etapas()
    return [EtapaRespuesta.desde_fila(fila) for fila in filas]


class NivelDeLaEtapaPeticion(BaseModel):
    """A qué nivel pertenece la etapa (§7.4).

    `null` lo quita: corregir uno mal puesto es tan válido como ponerlo.
    """

    nivel_id: UUID | None = None


@router.put(
    "/etapas/{etapa_id}/nivel",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="A qué nivel pertenece esta etapa",
    dependencies=[CATALOGOS],
)
async def asignar_nivel_a_la_etapa(
    etapa_id: UUID, peticion: NivelDeLaEtapaPeticion, sesion: SesionRLS
) -> None:
    """Cierra a mano lo que el árbol del prototipo no puede derivar.

    El nivel de una etapa se deduce del árbol WBS —ahí cuelga de él— y eso
    resuelve las que algún prototipo usa. Las que ningún prototipo toca todavía
    no tienen de dónde derivarse, y sin nivel no caen en ninguna tarjeta cuando
    el residente mira su obra agrupada.
    """
    await RepositorioNivelesEtapasSQL(sesion).asignar_nivel(etapa_id, peticion.nivel_id)
    await sesion.commit()


# --- Cuadrillas (§7.6, §10.6) ---------------------------------------------
#
# El alta manual de aquí es mínima (clave, nombre, unidad); la composición y
# el PU versionado los carga `AplicadorCuadrillas` desde
# `CABECERAS_CUADRILLAS.xlsx` (§10.6) — no hay `POST` para eso, es lo que la
# pantalla de Cargas de datos ya resuelve.


class CrearCuadrillaPeticion(BaseModel):
    clave: str = Field(min_length=1, description="Clave única del catálogo (§3.3).")
    nombre: str = Field(min_length=1)
    unidad_id: UUID | None = Field(
        default=None, description="Unidad del PU de la cuadrilla (p.ej. jornal, §10.6)."
    )


class CuadrillaRespuesta(BaseModel):
    id: UUID
    clave: str
    nombre: str
    unidad_id: UUID | None = None
    rendimiento: Decimal | None = Field(
        default=None,
        description="Rendimiento teórico asignado por el cargador de mano de obra (§10.6).",
    )
    precio_unitario: Decimal | None = Field(
        default=None, description="PU de la versión vigente, si ya se cargó una (§10.8)."
    )
    costo_jornada: Decimal | None = Field(
        default=None,
        description=(
            "Lo que cuesta un día de esta cuadrilla (§7.6, migración 0048). Con "
            "`rendimiento` se sabe cuánto hace en un día; con esto, cuánto vale. "
            "Nulo = no capturado; un cero diría que la cuadrilla es gratis."
        ),
    )
    version_vigente: int | None = None
    estatus: str = "activo"

    @classmethod
    def desde_fila(cls, fila: dict) -> CuadrillaRespuesta:
        return cls(
            id=fila["id"],
            clave=fila["clave"],
            nombre=fila["nombre"],
            unidad_id=fila.get("unidad_id"),
            rendimiento=fila.get("rendimiento"),
            precio_unitario=fila.get("precio_unitario"),
            costo_jornada=fila.get("costo_jornada"),
            version_vigente=fila.get("version_vigente"),
            estatus=fila["estatus"],
        )


class VersionCuadrillaRespuesta(BaseModel):
    id: UUID
    version: int
    precio_unitario: Decimal
    vigente: bool

    @classmethod
    def desde_fila(cls, fila: dict) -> VersionCuadrillaRespuesta:
        return cls(
            id=fila["id"],
            version=fila["version"],
            precio_unitario=fila["precio_unitario"],
            vigente=bool(fila["vigente"]),
        )


@router.get(
    "/cuadrillas",
    response_model=list[CuadrillaRespuesta],
    summary="Catálogo de cuadrillas",
    dependencies=[CATALOGOS],
)
async def listar_cuadrillas(
    sesion: SesionRLS, incluir_inactivos: IncluirInactivos = False
) -> list[CuadrillaRespuesta]:
    """Lectura simple sin orquestación de dominio —como `GET /unidades`—, así
    que consulta el repo directo: RLS ya acota el alcance (§12.4)."""
    repo = RepositorioCuadrillasSQL(sesion)
    filas = await repo.listar(solo_activos=not incluir_inactivos)
    respuestas = []
    for fila in filas:
        vigente = next(
            (v for v in await repo.versiones(fila["id"]) if v["vigente"]), None
        )
        respuestas.append(
            CuadrillaRespuesta.desde_fila(
                {
                    **fila,
                    "precio_unitario": vigente["precio_unitario"] if vigente else None,
                    "version_vigente": vigente["version"] if vigente else None,
                }
            )
        )
    return respuestas


class CostoDeJornadaPeticion(BaseModel):
    """Lo que cuesta un día de esta cuadrilla (§7.6, migración 0048).

    `null` lo quita: dejar de saberlo es un estado real —una cuadrilla nueva sin
    precio negociado— y un cero diría que es gratis.
    """

    costo_jornada: Decimal | None = Field(default=None, ge=0)


@router.put(
    "/cuadrillas/{cuadrilla_id}/costo-jornada",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cuánto cuesta un día de esta cuadrilla",
    dependencies=[CATALOGOS],
)
async def asignar_costo_de_jornada(
    cuadrilla_id: UUID, peticion: CostoDeJornadaPeticion, sesion: SesionRLS
) -> None:
    """La otra mitad del precio que el residente arma (§11.2).

    `rendimiento` dice cuánto hace la cuadrilla en un día y esto cuánto vale ese
    día. Sin lo segundo, un trabajo fuera de catálogo se puede describir pero no
    costear: el precio armado sale reportando que le falta esta cuadrilla, y
    autorizarlo así sería autorizar por debajo del costo.
    """
    await RepositorioCuadrillasSQL(sesion).actualizar(
        cuadrilla_id, {"costo_jornada": peticion.costo_jornada}
    )
    await sesion.commit()


class DestajoRespuesta(BaseModel):
    """Un trabajo con su cuadrilla y sus rendimientos (`CATALOGOS.md` §10,
    `CONOCIMIENTO.md` §6.2).

    ``cuadrilla`` y ``rendimiento_teorico`` son los dos datos que se capturan
    (semilla y edición); el calculado, las jornadas por unidad y la razón se
    derivan y no se guardan.
    """

    id: UUID
    clave: str
    tipo: TipoInsumo
    descripcion: str
    unidad: str | None = None
    precio: Decimal = Field(description="Precio del destajo (costo base).")
    familia_id: UUID | None = None
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
    jornadas_por_unidad: Decimal | None = Field(
        default=None, description="Precio del destajo ÷ costo de la cuadrilla."
    )
    razon_teorico_calculado: Decimal | None = Field(
        default=None, description="Teórico ÷ calculado: cerca de 1, el precio concuerda."
    )
    origen_rendimiento: str | None = None
    ref_descripcion: str | None = None
    ref_unidad: str | None = None
    ref_costo_unitario: Decimal | None = None

    @classmethod
    def desde_fila(cls, fila: dict) -> DestajoRespuesta:
        costo = fila.get("costo_cuadrilla")
        precio = fila["costo_base"]
        calculado = rendimiento_calculado(costo, precio)
        return cls(
            id=fila["id"],
            clave=fila["clave"],
            tipo=TipoInsumo(str(fila["tipo"])),
            descripcion=fila["descripcion"],
            unidad=fila.get("unidad"),
            precio=precio,
            familia_id=fila.get("familia_id"),
            cuadrilla_id=fila.get("cuadrilla_id"),
            cuadrilla_clave=fila.get("cuadrilla_clave"),
            cuadrilla_nombre=fila.get("cuadrilla_nombre"),
            costo_cuadrilla=costo,
            rendimiento_teorico=fila.get("rendimiento_teorico"),
            rendimiento_calculado=calculado,
            jornadas_por_unidad=jornadas_por_unidad(costo, precio),
            razon_teorico_calculado=razon_teorico_calculado(
                fila.get("rendimiento_teorico"), calculado
            ),
            origen_rendimiento=fila.get("origen_rendimiento"),
            ref_descripcion=fila.get("ref_descripcion"),
            ref_unidad=fila.get("ref_unidad"),
            ref_costo_unitario=fila.get("ref_costo_unitario"),
        )


@router.get(
    "/destajos",
    response_model=list[DestajoRespuesta],
    summary="Trabajos con su cuadrilla y rendimientos",
    dependencies=[CATALOGOS],
)
async def listar_destajos(
    sesion: SesionRLS,
    cuadrilla_id: Annotated[
        UUID | None, Query(description="Solo los trabajos de esta cuadrilla.")
    ] = None,
    sin_cuadrilla: Annotated[
        bool, Query(description="Solo los que todavía no tienen cuadrilla.")
    ] = False,
) -> list[DestajoRespuesta]:
    """Las columnas del catálogo de cuadrilla y rendimiento (`CATALOGOS.md`
    §10): lo capturado (cuadrilla y rendimiento teórico) y lo derivado."""
    filas = await RepositorioInsumosSQL(sesion).destajos_con_cuadrilla()
    if cuadrilla_id is not None:
        filas = [f for f in filas if f["cuadrilla_id"] == cuadrilla_id]
    if sin_cuadrilla:
        filas = [f for f in filas if f["cuadrilla_id"] is None]
    return [DestajoRespuesta.desde_fila(f) for f in filas]


class CuadrillaDelDestajoPeticion(BaseModel):
    """Los dos datos que OPUS no entrega y que viven en el ERP (`CATALOGOS.md`
    §10). `null` en uno lo quita: no saberlo es un estado real."""

    cuadrilla_id: UUID | None = None
    rendimiento_teorico: Decimal | None = Field(default=None, gt=0)


@router.put(
    "/destajos/{insumo_id}/cuadrilla",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cuadrilla y rendimiento teórico de un trabajo",
    dependencies=[CATALOGOS],
    responses={404: {"description": "El trabajo o la cuadrilla no existen."}},
)
async def asignar_cuadrilla_a_destajo(
    insumo_id: UUID, peticion: CuadrillaDelDestajoPeticion, sesion: SesionRLS
) -> None:
    """La edición posterior a la semilla: «se cargan una sola vez y de ahí en
    adelante viven en el ERP y se editan ahí». Queda marcado como editado."""
    insumos = RepositorioInsumosSQL(sesion)
    destajo = await insumos.obtener(insumo_id)
    if destajo is None or str(destajo["tipo"]) not in ("mano_obra", "subcontrato", "acarreo"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El trabajo no existe en tu alcance.")
    if (
        peticion.cuadrilla_id is not None
        and await RepositorioCuadrillasSQL(sesion).obtener(peticion.cuadrilla_id) is None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La cuadrilla no existe en tu alcance.")
    await insumos.actualizar(
        insumo_id,
        {
            "cuadrilla_id": peticion.cuadrilla_id,
            "rendimiento_teorico": peticion.rendimiento_teorico,
            "origen_rendimiento": "editado en el ERP",
        },
    )
    await sesion.commit()


class DestajoNuevoPeticion(BaseModel):
    clave: str | None = Field(default=None, description="Vacía = una consecutiva (MO-00001…).")
    descripcion: str = Field(min_length=1)
    unidad_id: UUID | None = Field(default=None, description="Vacía = la unidad del concepto.")
    precio: Decimal = Field(default=Decimal(0), ge=0, description="Lo que se paga por unidad del destajo; los costos se definen en Presupuesto, vacío = 0.")
    factor: Decimal = Field(default=Decimal(1), gt=0, description="Unidades del destajo por cada unidad del concepto.")
    cuadrilla_id: UUID | None = None
    rendimiento_teorico: Decimal | None = Field(default=None, gt=0)


class DestajoNuevoRespuesta(BaseModel):
    insumo_id: UUID
    clave: str


@router.post(
    "/conceptos/{concepto_id}/destajos",
    response_model=DestajoNuevoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar un destajo a la receta de un concepto",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.COSTOS))],
    responses={
        404: {"description": "El concepto o la cuadrilla no existen en tu alcance."},
        422: {"description": "Clave repetida o datos de catálogo inválidos."},
    },
)
async def agregar_destajo_al_concepto(
    concepto_id: UUID, peticion: DestajoNuevoPeticion, sesion: SesionRLS
) -> DestajoNuevoRespuesta:
    """Crea el destajo (un insumo de mano de obra con su precio) y lo pone en la receta del concepto. Es del **catálogo**:
    vale para todas las obras que usen el concepto. La cuadrilla y el rendimiento teórico son opcionales."""
    conceptos, insumos = RepositorioConceptosSQL(sesion), RepositorioInsumosSQL(sesion)
    concepto = await conceptos.obtener(concepto_id)
    if concepto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El concepto no existe en tu alcance.")
    if peticion.cuadrilla_id is not None and await RepositorioCuadrillasSQL(sesion).obtener(peticion.cuadrilla_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La cuadrilla no existe en tu alcance.")
    clave = (peticion.clave or "").strip().upper()
    if not clave:
        existentes = {str(f["clave"]) for f in await insumos.listar(familia_id=None, solo_activos=False)}
        n = len([c for c in existentes if c.startswith("MO-")]) + 1
        while f"MO-{n:05d}" in existentes:
            n += 1
        clave = f"MO-{n:05d}"
    try:
        dominio = Insumo.crear(
            tipo=TipoInsumo.MANO_OBRA,
            clave=clave,
            descripcion=peticion.descripcion,
            unidad_id=str(peticion.unidad_id or concepto.get("unidad_id") or "") or None,
            costo_base=peticion.precio,
        )
    except ErrorDeCatalogo as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    if any(str(f["clave"]) == str(dominio.clave) for f in await insumos.listar(familia_id=None, solo_activos=False)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Ya existe un insumo con la clave {dominio.clave}.")
    insumo_id = await insumos.crear(
        {
            "tipo": str(dominio.tipo),
            "clave": str(dominio.clave),
            "descripcion": dominio.descripcion,
            "unidad_id": dominio.unidad_id,
            "familia_id": None,
            "costo_base": dominio.costo_base,
            "cuadrilla_id": peticion.cuadrilla_id,
            "rendimiento_teorico": peticion.rendimiento_teorico,
        }
    )
    await conceptos.poner_destajo(concepto_id, insumo_id, peticion.factor)
    await sesion.commit()
    return DestajoNuevoRespuesta(insumo_id=insumo_id, clave=str(dominio.clave))


@router.delete(
    "/conceptos/{concepto_id}/destajos/{insumo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Quitar un destajo de la receta de un concepto",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.COSTOS))],
    responses={404: {"description": "Ese destajo no es parte de la receta del concepto."}},
)
async def quitar_destajo_del_concepto(concepto_id: UUID, insumo_id: UUID, sesion: SesionRLS) -> None:
    """El destajo sigue en el catálogo de insumos; solo deja de ser parte de la receta de este concepto."""
    if not await RepositorioConceptosSQL(sesion).quitar_destajo(concepto_id, insumo_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese destajo no es parte de la receta del concepto.")
    await sesion.commit()


@router.post(
    "/cuadrillas",
    response_model=CuadrillaRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Alta de cuadrilla",
    dependencies=[CATALOGOS],
    responses={422: {"description": "Datos de catálogo inválidos (§7.6)."}},
)
async def crear_cuadrilla(
    peticion: CrearCuadrillaPeticion, caso_uso: CrearCuadrillaDep
) -> CuadrillaRespuesta:
    creada = await caso_uso.ejecutar(
        ComandoCrearCuadrilla(
            clave=peticion.clave,
            nombre=peticion.nombre,
            unidad_id=peticion.unidad_id,
        )
    )
    return CuadrillaRespuesta(
        id=creada.id,
        clave=str(creada.cuadrilla.clave),
        nombre=creada.cuadrilla.nombre,
        unidad_id=UUID(creada.cuadrilla.unidad_id) if creada.cuadrilla.unidad_id else None,
    )


@router.get(
    "/cuadrillas/{cuadrilla_id}/versiones",
    response_model=list[VersionCuadrillaRespuesta],
    summary="Historial de PU de la cuadrilla",
    dependencies=[CATALOGOS],
)
async def listar_versiones_de_cuadrilla(
    sesion: SesionRLS, cuadrilla_id: UUID
) -> list[VersionCuadrillaRespuesta]:
    """Todas las versiones (§10.8): la carga de `CABECERAS_CUADRILLAS.xlsx`
    publica una nueva cada vez que la composición cambia."""
    filas = await RepositorioCuadrillasSQL(sesion).versiones(cuadrilla_id)
    return [VersionCuadrillaRespuesta.desde_fila(fila) for fila in filas]


@router.delete(
    "/cuadrillas/{cuadrilla_id}/versiones/{version_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar una versión retirada del historial",
    dependencies=[CATALOGOS],
    responses={
        404: {"description": "La versión no existe para esa cuadrilla."},
        409: {"description": "Es la versión vigente: no se puede eliminar."},
    },
)
async def eliminar_version_de_cuadrilla(
    cuadrilla_id: UUID, version_id: UUID, caso_uso: EliminarVersionDeCuadrillaDep
) -> None:
    """Mantenimiento directo del historial (§10.8): no crea ni revierte
    ninguna carga, solo limpia una versión ya retirada."""
    await caso_uso.ejecutar(cuadrilla_id, version_id)


# --- Conceptos y APU (§7.3) ----------------------------------------------


class CrearConceptoPeticion(BaseModel):
    clave: str = Field(min_length=1, description="Clave con prefijo `EST`… (§10.1).")
    descripcion: str = Field(min_length=1)
    tipo: TipoConcepto = Field(
        default=TipoConcepto.CONCEPTO,
        description="`auxiliar` y `matriz` son los que otros conceptos anidan (§7.3).",
    )
    unidad_id: UUID | None = None
    familia_id: UUID | None = None


class ConceptoRespuesta(BaseModel):
    id: UUID
    tipo: TipoConcepto
    clave: str
    descripcion: str
    unidad_id: UUID | None = None
    familia_id: UUID | None = None
    estatus: str = "activo"
    especialidad_id: UUID | None = Field(
        default=None,
        description=(
            "El oficio con el que se ejecuta (§8.3, migración 0047). Vacío en "
            "los conceptos que el catálogo cargado todavía no clasifica: salen "
            "como «Sin oficio» al desglosar un frente y se completan desde el "
            "catálogo."
        ),
    )

    @classmethod
    def desde_fila(cls, fila: dict) -> ConceptoRespuesta:
        return cls(
            id=fila["id"],
            tipo=TipoConcepto(str(fila["tipo"])),
            clave=fila["clave"],
            descripcion=fila["descripcion"],
            unidad_id=fila["unidad_id"],
            familia_id=fila["familia_id"],
            estatus=fila["estatus"],
            especialidad_id=fila.get("especialidad_id"),
        )


class PrecioUnitarioRespuesta(BaseModel):
    """CPU con su desglose de destajo (§7.3, §11.1)."""

    total: Decimal = Field(description="Materiales + auxiliares + matrices + MO + equipo.")
    destajo: Decimal = Field(description="Lo que cobra la cuadrilla: MO o subcontrato.")
    materiales: Decimal = Field(description="Porción que no es destajo.")


class LineaExplosionRespuesta(BaseModel):
    ruta: list[str]
    nivel: int
    tipo_hijo: TipoHijoExplosion
    referencia: str = Field(description="Clave del insumo o del concepto hijo (§3.3).")
    categoria: CategoriaExplosion
    cantidad_unitaria: Decimal = Field(description="Por unidad del padre inmediato.")
    cantidad: Decimal = Field(description="Acumulada por unidad del concepto raíz.")
    costo_unitario: Decimal
    importe: Decimal
    es_destajo: bool


class ExplosionRespuesta(BaseModel):
    clave: str
    lineas: list[LineaExplosionRespuesta]
    precio: PrecioUnitarioRespuesta

    @classmethod
    def desde_dominio(cls, calculada: ExplosionCalculada) -> ExplosionRespuesta:
        return cls(
            clave=calculada.clave,
            lineas=[
                LineaExplosionRespuesta(
                    ruta=list(linea.ruta),
                    nivel=linea.nivel,
                    tipo_hijo=linea.tipo_hijo,
                    referencia=linea.referencia,
                    categoria=linea.categoria,
                    cantidad_unitaria=linea.cantidad_unitaria,
                    cantidad=linea.cantidad,
                    costo_unitario=linea.costo_unitario,
                    importe=linea.importe,
                    es_destajo=linea.es_destajo,
                )
                for linea in calculada.lineas
            ],
            precio=_precio(calculada.precio),
        )


class VersionCPURespuesta(BaseModel):
    version: int
    variante: str | None = None
    vigente: bool = False
    precio: PrecioUnitarioRespuesta

    @classmethod
    def desde_dominio(cls, version: VersionCPU) -> VersionCPURespuesta:
        return cls(
            version=version.version,
            variante=version.variante,
            vigente=version.vigente,
            precio=_precio(version.precio),
        )


class CPURespuesta(BaseModel):
    concepto_id: UUID
    clave: str
    variante: str | None = None
    vigente: VersionCPURespuesta | None = None
    historial: list[VersionCPURespuesta]
    calculado: PrecioUnitarioRespuesta = Field(
        description=(
            "CPU recalculado desde la explosión de hoy. Si difiere del vigente, "
            "el catálogo cambió y toca publicar una versión nueva (§10.8)."
        )
    )

    @classmethod
    def desde_dominio(cls, cpu: CPUDelConcepto) -> CPURespuesta:
        return cls(
            concepto_id=cpu.concepto_id,
            clave=cpu.clave,
            variante=cpu.variante,
            vigente=(
                VersionCPURespuesta.desde_dominio(cpu.vigente)
                if cpu.vigente is not None
                else None
            ),
            historial=[VersionCPURespuesta.desde_dominio(v) for v in cpu.historial],
            calculado=_precio(cpu.calculado),
        )


class PublicarCPUPeticion(BaseModel):
    variante: str | None = Field(
        default=None, description="Receta alterna; nulo = receta base (§2.2)."
    )
    precio_unitario: Decimal | None = Field(
        default=None,
        description=(
            "Precio explícito. Si se omite —lo normal—, el CPU se calcula de "
            "la explosión del concepto (§7.3)."
        ),
    )
    precio_destajo: Decimal | None = None


class VersionPublicadaRespuesta(BaseModel):
    id: UUID
    concepto_id: UUID
    version: VersionCPURespuesta
    retiradas: list[int] = Field(
        description="Versiones que dejaron de estar vigentes; siguen en el histórico (§10.8)."
    )

    @classmethod
    def desde_dominio(cls, publicada: VersionPublicada) -> VersionPublicadaRespuesta:
        return cls(
            id=publicada.id,
            concepto_id=publicada.concepto_id,
            version=VersionCPURespuesta.desde_dominio(publicada.version),
            retiradas=list(publicada.retiradas),
        )


def _precio(precio: PrecioUnitario) -> PrecioUnitarioRespuesta:
    """`PrecioUnitario` (dominio) → DTO. `Dinero` no cruza el borde (§12.11)."""
    return PrecioUnitarioRespuesta(
        total=precio.total.monto,
        destajo=precio.destajo.monto,
        materiales=precio.materiales.monto,
    )


@router.get(
    "/conceptos",
    response_model=list[ConceptoRespuesta],
    summary="Catálogo de conceptos",
    dependencies=[LECTURA_PARA_ALTAS],
)
async def listar_conceptos(
    sesion: SesionRLS,
    tipo: Annotated[
        TipoConcepto | None, Query(description="Filtra por tipo de concepto (§8.2).")
    ] = None,
    familia_id: FiltroFamilia = None,
    incluir_inactivos: IncluirInactivos = False,
) -> list[ConceptoRespuesta]:
    filas = await RepositorioConceptosSQL(sesion).listar(
        tipo=str(tipo) if tipo else None,
        familia_id=familia_id,
        solo_activos=not incluir_inactivos,
    )
    return [ConceptoRespuesta.desde_fila(fila) for fila in filas]


class OficioDelConceptoPeticion(BaseModel):
    """Con qué oficio se ejecuta este concepto (§8.3, migración 0047).

    `null` lo deja sin oficio: quitarlo —"esto no era carpintería"— es un cambio
    tan válido como ponerlo, y omitir el campo no podría expresarlo.
    """

    especialidad_id: UUID | None = None


@router.put(
    "/conceptos/{concepto_id}/especialidad",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Con qué oficio se ejecuta este concepto",
    dependencies=[CATALOGOS],
)
async def asignar_especialidad_al_concepto(
    concepto_id: UUID, peticion: OficioDelConceptoPeticion, sesion: SesionRLS
) -> None:
    """Rellenar a mano lo que el catálogo cargado no clasifica.

    El archivo del cliente cubre 461 de 898 conceptos; el resto sale agrupado
    como «Sin oficio» al desglosar un frente en la pantalla de cuadrillas. Esto
    permite completarlo renglón por renglón, sin volver a subir un Excel.

    Uno por uno y no la lista entera —para eso está
    `PUT /especialidades/{id}/conceptos`—: corregir un concepto suelto no debe
    obligar a mandar los otros cuatrocientos, donde cualquiera que se olvide se
    quedaría sin oficio.
    """
    await RepositorioConceptosSQL(sesion).actualizar(
        concepto_id, {"especialidad_id": peticion.especialidad_id}
    )
    await sesion.commit()


@router.post(
    "/conceptos",
    response_model=ConceptoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Alta de concepto",
    dependencies=[CATALOGOS],
    responses={422: {"description": "Datos de catálogo inválidos (§7.3)."}},
)
async def crear_concepto(
    peticion: CrearConceptoPeticion, caso_uso: CrearConceptoDep
) -> ConceptoRespuesta:
    creado = await caso_uso.ejecutar(
        ComandoCrearConcepto(
            tipo=str(peticion.tipo),
            clave=peticion.clave,
            descripcion=peticion.descripcion,
            unidad_id=peticion.unidad_id,
            familia_id=peticion.familia_id,
        )
    )
    return ConceptoRespuesta(
        id=creado.id,
        tipo=creado.concepto.tipo,
        clave=str(creado.concepto.clave),
        descripcion=creado.concepto.descripcion,
        unidad_id=UUID(creado.concepto.unidad_id) if creado.concepto.unidad_id else None,
        familia_id=(
            UUID(creado.concepto.familia_id) if creado.concepto.familia_id else None
        ),
    )


class MatrizNuevaPeticion(BaseModel):
    clave: str = Field(min_length=1, max_length=60)
    descripcion: str = Field(min_length=1)
    unidad_id: UUID


class FormulaPeticion(BaseModel):
    """Cantidad por piezas comerciales: `piezas ÷ largo × (1 + desperdicio %)` por unidad del concepto padre."""

    piezas: Decimal = Field(gt=0, description="Piezas que lleva una unidad del concepto (4 varillas).")
    largo: Decimal = Field(gt=0, description="Lo que mide una pieza comercial completa (una varilla: 12).")
    desperdicio_pct: Decimal = Field(default=Decimal(0), ge=0, le=100, description="Por ejemplo 0.5.")


class PonerMatrizPeticion(BaseModel):
    cantidad: Decimal | None = Field(
        default=None, gt=0, description="Cuánto lleva por unidad del concepto padre, capturada a mano."
    )
    formula: FormulaPeticion | None = Field(
        default=None, description="O cómo se forma esa cantidad; el servidor la calcula. Una sola de las dos."
    )
    matriz_id: UUID | None = Field(default=None, description="Un concepto que ya existe…")
    nueva: MatrizNuevaPeticion | None = Field(default=None, description="…o uno que nace aquí.")


class MatrizPuestaRespuesta(BaseModel):
    concepto_id: UUID
    matriz_id: UUID
    cantidad: Decimal
    formula: dict[str, object] | None = Field(default=None, description="Cómo se formó la cantidad, si no fue a mano.")


@router.post(
    "/conceptos/{concepto_id}/matrices",
    response_model=MatrizPuestaRespuesta,
    summary="Poner una matriz bajo el concepto (o cambiarle la cantidad)",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.COSTOS))],
    responses={
        404: {"description": "El concepto no existe o está fuera de tu alcance."},
        422: {"description": "Ciclo, clave repetida, cantidad que no suma o ni matriz ni nueva."},
    },
)
async def poner_matriz_al_concepto(
    concepto_id: UUID, peticion: PonerMatrizPeticion, caso_uso: GestionarMatricesDeConceptoDep
) -> MatrizPuestaRespuesta:
    """Cambia la composición del **catálogo**: vale para todas las obras que usen el concepto."""
    return MatrizPuestaRespuesta(
        **await caso_uso.poner(
            ComandoPonerMatriz(
                concepto_id=concepto_id,
                cantidad=peticion.cantidad,
                formula=(
                    FormulaDePiezasComerciales(
                        piezas=peticion.formula.piezas,
                        largo=peticion.formula.largo,
                        desperdicio_pct=peticion.formula.desperdicio_pct,
                    )
                    if peticion.formula
                    else None
                ),
                hijo_id=peticion.matriz_id,
                nueva=(
                    MatrizNueva(
                        clave=peticion.nueva.clave,
                        descripcion=peticion.nueva.descripcion,
                        unidad_id=peticion.nueva.unidad_id,
                    )
                    if peticion.nueva
                    else None
                ),
            )
        )
    )


@router.delete(
    "/conceptos/{concepto_id}/matrices/{matriz_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Quitar una matriz del concepto",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.COSTOS))],
    responses={404: {"description": "El concepto o esa matriz directa no existen."}},
)
async def quitar_matriz_del_concepto(
    concepto_id: UUID, matriz_id: UUID, caso_uso: GestionarMatricesDeConceptoDep
) -> None:
    await caso_uso.quitar(concepto_id, matriz_id)


@router.get(
    "/conceptos/{concepto_id}/explosion",
    response_model=ExplosionRespuesta,
    summary="Explosión recursiva del concepto",
    dependencies=[CONSULTA_CPU],
    responses={
        404: {"description": "El concepto no existe o está fuera de tu alcance."},
        422: {"description": "La composición tiene un ciclo (§7.3)."},
    },
)
async def explotar_concepto(
    concepto_id: UUID, caso_uso: ExplotarConceptoDep
) -> ExplosionRespuesta:
    """Árbol completo del APU: insumos y conceptos anidados (§7.3)."""
    return ExplosionRespuesta.desde_dominio(await caso_uso.ejecutar(concepto_id))


@router.get(
    "/conceptos/{concepto_id}/cpu",
    response_model=CPURespuesta,
    summary="CPU del concepto: versión vigente e historial",
    dependencies=[CONSULTA_CPU_Y_COSTOS],
    responses={
        404: {"description": "El concepto no existe o está fuera de tu alcance."},
        422: {"description": "La composición tiene un ciclo (§7.3)."},
    },
)
async def obtener_cpu(
    concepto_id: UUID, caso_uso: ObtenerCPUDep, variante: FiltroVariante = None
) -> CPURespuesta:
    return CPURespuesta.desde_dominio(
        await caso_uso.ejecutar(concepto_id, variante=variante)
    )


@router.delete(
    "/conceptos/{concepto_id}/cpu/{version}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar una versión de CPU retirada del historial",
    dependencies=[CATALOGOS],
    responses={
        404: {"description": "Esa versión no existe para el concepto."},
        409: {"description": "Es la versión vigente: no se puede eliminar."},
    },
)
async def eliminar_version_de_cpu(
    concepto_id: UUID,
    version: int,
    caso_uso: EliminarVersionDeCPUDep,
    variante: FiltroVariante = None,
) -> None:
    """Mantenimiento directo del historial (§10.8): no crea ni revierte
    ninguna carga, solo limpia una versión ya retirada."""
    await caso_uso.ejecutar(concepto_id, version=version, variante=variante)


@router.post(
    "/conceptos/{concepto_id}/cpu",
    response_model=VersionPublicadaRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Publica una nueva versión del CPU",
    dependencies=[PUBLICA_CPU],
    responses={
        404: {"description": "El concepto no existe o está fuera de tu alcance."},
        422: {"description": "Composición cíclica o precio inválido (§7.3)."},
    },
)
async def publicar_cpu(
    concepto_id: UUID,
    peticion: PublicarCPUPeticion,
    caso_uso: PublicarVersionCPUDep,
) -> VersionPublicadaRespuesta:
    """Nueva versión vigente; la anterior pasa al histórico (§10.8)."""
    return VersionPublicadaRespuesta.desde_dominio(
        await caso_uso.ejecutar(
            ComandoPublicarVersionCPU(
                concepto_id=concepto_id,
                variante=peticion.variante,
                precio_unitario=peticion.precio_unitario,
                precio_destajo=peticion.precio_destajo,
            )
        )
    )
