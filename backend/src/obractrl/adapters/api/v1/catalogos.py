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

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    CrearConceptoDep,
    CrearContratistaDep,
    CrearFamiliaDep,
    CrearInsumoDep,
    CrearUnidadDep,
    ExplotarConceptoDep,
    ObtenerCPUDep,
    PublicarVersionCPUDep,
)
from obractrl.adapters.api.dependencias import SesionRLS, exigir_rol
from obractrl.adapters.repos.conceptos_sql import RepositorioConceptosSQL
from obractrl.adapters.repos.contratistas_sql import RepositorioContratistasSQL
from obractrl.adapters.repos.familias_sql import RepositorioFamiliasSQL
from obractrl.adapters.repos.insumos_sql import RepositorioInsumosSQL
from obractrl.adapters.repos.unidades_sql import RepositorioUnidadesSQL
from obractrl.application.casos_uso.calcular_cpu import (
    ComandoPublicarVersionCPU,
    CPUDelConcepto,
    VersionPublicada,
)
from obractrl.application.casos_uso.gestionar_catalogos import (
    ComandoCrearConcepto,
    ComandoCrearContratista,
    ComandoCrearFamilia,
    ComandoCrearInsumo,
    ComandoCrearUnidad,
    InsumoCreado,
)
from obractrl.domain.catalogos.apu import ExplosionCalculada, VersionCPU
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
    dependencies=[CATALOGOS],
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


class CrearMaterialPeticion(BaseModel):
    """`POST /materiales` — mismo cuerpo, sin `tipo`: es siempre `material` (§7.3)."""

    clave: str = Field(min_length=1)
    descripcion: str = Field(min_length=1)
    unidad_id: UUID | None = None
    familia_id: UUID | None = None
    costo_base: Decimal = Decimal(0)
    iva_aplica: bool | None = None
    factor_conversion: Decimal = Decimal(1)


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
    dependencies=[CATALOGOS],
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
    dependencies=[CONSULTA_CPU],
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


@router.post(
    "/conceptos/{concepto_id}/cpu",
    response_model=VersionPublicadaRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Publica una nueva versión del CPU",
    dependencies=[CATALOGOS],
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
