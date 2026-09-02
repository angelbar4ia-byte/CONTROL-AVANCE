"""Caso de uso: alta de los catálogos maestros (§11.2 "Catálogos · APU").

Spec §7.3 · §10.1 · §3.3 (clave única) · §12.11 (capa de aplicación).

Cinco altas con la misma forma que el resto del backend: el dominio valida
(`domain.catalogos.reglas`), el caso de uso ordena la secuencia y el
repositorio persiste. Quién puede ejecutarlas es RBAC del borde —Control de
obra (§11.2 "Catálogos · APU")— reforzado por RLS (`app.es_config()`, §12.4).

**`Material` no tiene caso de uso propio:** es un `Insumo` con
``tipo='material'`` (§7.3), así que `POST /materiales` ejecuta
:class:`CrearInsumo` con el tipo fijado en el borde.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from obractrl.application.puertos.repositorios import (
    RepositorioConceptos,
    RepositorioContratistas,
    RepositorioCuadrillas,
    RepositorioFamilias,
    RepositorioInsumos,
    RepositorioUnidades,
    UnidadDeTrabajo,
)
from obractrl.domain.catalogos.reglas import (
    Concepto,
    Contratista,
    Cuadrilla,
    ErrorDeCatalogo,
    Familia,
    Insumo,
    Unidad,
)

__all__ = [
    "ComandoCrearConcepto",
    "ComandoCrearContratista",
    "ComandoCrearCuadrilla",
    "ComandoCrearFamilia",
    "ComandoCrearInsumo",
    "ComandoCrearUnidad",
    "ConceptoCreado",
    "ContratistaCreado",
    "CrearConcepto",
    "CrearContratista",
    "CrearCuadrilla",
    "CrearFamilia",
    "CrearInsumo",
    "CrearUnidad",
    "CuadrillaCreada",
    "EliminarVersionDeCPU",
    "EliminarVersionDeCuadrilla",
    "ErrorDeCatalogo",
    "FamiliaCreada",
    "InsumoCreado",
    "UnidadCreada",
]


@dataclass(frozen=True, slots=True)
class ComandoCrearUnidad:
    clave: str
    nombre: str
    sinonimos: list[str] | None = None
    factor: Decimal = Decimal(1)


@dataclass(frozen=True, slots=True)
class ComandoCrearFamilia:
    clave: str
    nombre: str
    parent_id: UUID | None = None
    aplica_a: str = "material"
    iva_aplica: bool = True


@dataclass(frozen=True, slots=True)
class ComandoCrearCuadrilla:
    clave: str
    nombre: str
    unidad_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ComandoCrearInsumo:
    tipo: str
    clave: str
    descripcion: str
    unidad_id: UUID | None = None
    familia_id: UUID | None = None
    costo_base: Decimal = Decimal(0)
    iva_aplica: bool | None = None
    factor_conversion: Decimal = Decimal(1)
    dias_entrega: int | None = None


@dataclass(frozen=True, slots=True)
class ComandoCrearConcepto:
    clave: str
    descripcion: str
    tipo: str = "concepto"
    unidad_id: UUID | None = None
    familia_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ComandoCrearContratista:
    clave: str
    razon_social: str
    rfc: str | None = None
    contacto: str | None = None
    telefono: str | None = None
    email: str | None = None
    calificacion: Decimal | None = None
    frentes: list[UUID] | None = None


@dataclass(frozen=True, slots=True)
class UnidadCreada:
    id: UUID
    unidad: Unidad


@dataclass(frozen=True, slots=True)
class FamiliaCreada:
    id: UUID
    familia: Familia


@dataclass(frozen=True, slots=True)
class CuadrillaCreada:
    id: UUID
    cuadrilla: Cuadrilla


@dataclass(frozen=True, slots=True)
class InsumoCreado:
    id: UUID
    insumo: Insumo


@dataclass(frozen=True, slots=True)
class ConceptoCreado:
    id: UUID
    concepto: Concepto


@dataclass(frozen=True, slots=True)
class ContratistaCreado:
    id: UUID
    contratista: Contratista


class CrearUnidad:
    """`POST /unidades` (Control de obra, §11.2)."""

    def __init__(self, *, unidades: RepositorioUnidades, uow: UnidadDeTrabajo) -> None:
        self._unidades = unidades
        self._uow = uow

    async def ejecutar(self, cmd: ComandoCrearUnidad) -> UnidadCreada:
        unidad = Unidad.crear(
            clave=cmd.clave,
            nombre=cmd.nombre,
            sinonimos=cmd.sinonimos,
            factor=cmd.factor,
        )
        async with self._uow:
            unidad_id = await self._unidades.crear(
                {
                    "clave": str(unidad.clave),
                    "nombre": unidad.nombre,
                    "sinonimos": list(unidad.sinonimos),
                    "factor": unidad.factor,
                }
            )
            await self._uow.commit()
        return UnidadCreada(id=unidad_id, unidad=unidad)


class CrearFamilia:
    """`POST /familias` (Control de obra, §11.2)."""

    def __init__(self, *, familias: RepositorioFamilias, uow: UnidadDeTrabajo) -> None:
        self._familias = familias
        self._uow = uow

    async def ejecutar(self, cmd: ComandoCrearFamilia) -> FamiliaCreada:
        familia = Familia.crear(
            clave=cmd.clave,
            nombre=cmd.nombre,
            parent_id=str(cmd.parent_id) if cmd.parent_id else None,
            aplica_a=cmd.aplica_a,
            iva_aplica=cmd.iva_aplica,
        )
        async with self._uow:
            familia_id = await self._familias.crear(
                {
                    "clave": str(familia.clave),
                    "nombre": familia.nombre,
                    "parent_id": familia.parent_id,
                    "aplica_a": familia.aplica_a,
                    "iva_aplica": familia.iva_aplica,
                }
            )
            await self._uow.commit()
        return FamiliaCreada(id=familia_id, familia=familia)


class CrearCuadrilla:
    """`POST /cuadrillas` (Control de obra, §11.2).

    Alta manual mínima: la composición y el PU se cargan por archivo
    (`AplicadorCuadrillas`, §10.6), no aquí.
    """

    def __init__(self, *, cuadrillas: RepositorioCuadrillas, uow: UnidadDeTrabajo) -> None:
        self._cuadrillas = cuadrillas
        self._uow = uow

    async def ejecutar(self, cmd: ComandoCrearCuadrilla) -> CuadrillaCreada:
        cuadrilla = Cuadrilla.crear(
            clave=cmd.clave,
            nombre=cmd.nombre,
            unidad_id=str(cmd.unidad_id) if cmd.unidad_id else None,
        )
        async with self._uow:
            cuadrilla_id = await self._cuadrillas.crear(
                {
                    "clave": str(cuadrilla.clave),
                    "nombre": cuadrilla.nombre,
                    "unidad_id": cuadrilla.unidad_id,
                }
            )
            await self._uow.commit()
        return CuadrillaCreada(id=cuadrilla_id, cuadrilla=cuadrilla)


class EliminarVersionDeCuadrilla:
    """`DELETE /cuadrillas/{id}/versiones/{version_id}` (Control de obra).

    Mantenimiento directo del historial (§10.8): no está ligado a ninguna
    carga, así que necesita su propia transacción — el repositorio por sí
    solo no comprometía la escritura (mismo defecto que tuvo `EliminarCarga`
    antes de llevar su `uow`).
    """

    def __init__(self, *, cuadrillas: RepositorioCuadrillas, uow: UnidadDeTrabajo) -> None:
        self._cuadrillas = cuadrillas
        self._uow = uow

    async def ejecutar(self, cuadrilla_id: UUID, version_id: UUID) -> None:
        async with self._uow:
            await self._cuadrillas.eliminar_version(cuadrilla_id, version_id)
            await self._uow.commit()


class EliminarVersionDeCPU:
    """`DELETE /conceptos/{id}/cpu/{version}` (Control de obra) — mismo
    mantenimiento que `EliminarVersionDeCuadrilla`, para CPU."""

    def __init__(self, *, conceptos: RepositorioConceptos, uow: UnidadDeTrabajo) -> None:
        self._conceptos = conceptos
        self._uow = uow

    async def ejecutar(
        self, concepto_id: UUID, *, version: int, variante: str | None = None
    ) -> None:
        async with self._uow:
            await self._conceptos.eliminar_version_cpu(
                concepto_id, version=version, variante=variante
            )
            await self._uow.commit()


class CrearInsumo:
    """`POST /insumos` y `POST /materiales` (Control de obra, §11.2).

    Un solo caso de uso para ambos endpoints: `Material` es un `Insumo` con
    ``tipo='material'`` (§7.3).
    """

    def __init__(self, *, insumos: RepositorioInsumos, uow: UnidadDeTrabajo) -> None:
        self._insumos = insumos
        self._uow = uow

    async def ejecutar(self, cmd: ComandoCrearInsumo) -> InsumoCreado:
        insumo = Insumo.crear(
            tipo=cmd.tipo,
            clave=cmd.clave,
            descripcion=cmd.descripcion,
            unidad_id=str(cmd.unidad_id) if cmd.unidad_id else None,
            familia_id=str(cmd.familia_id) if cmd.familia_id else None,
            costo_base=cmd.costo_base,
            iva_aplica=cmd.iva_aplica,
            factor_conversion=cmd.factor_conversion,
            dias_entrega=cmd.dias_entrega,
        )
        async with self._uow:
            insumo_id = await self._insumos.crear(
                {
                    "tipo": str(insumo.tipo),
                    "clave": str(insumo.clave),
                    "descripcion": insumo.descripcion,
                    "unidad_id": insumo.unidad_id,
                    "familia_id": insumo.familia_id,
                    "costo_base": insumo.costo_base,
                    # Viaja el `None` tal cual: en `insumo.iva_aplica` nulo
                    # significa "hereda de la familia" (§3.5), no "sin dato".
                    "iva_aplica": insumo.iva_aplica,
                    "factor_conversion": insumo.factor_conversion,
                    # Igual que `iva_aplica`: el `None` significa "no
                    # capturado", y ahi manda la anticipacion global de quien
                    # consulta (0044).
                    "dias_entrega": insumo.dias_entrega,
                }
            )
            await self._uow.commit()
        return InsumoCreado(id=insumo_id, insumo=insumo)


class CrearConcepto:
    """`POST /conceptos` (Control de obra, §11.2)."""

    def __init__(self, *, conceptos: RepositorioConceptos, uow: UnidadDeTrabajo) -> None:
        self._conceptos = conceptos
        self._uow = uow

    async def ejecutar(self, cmd: ComandoCrearConcepto) -> ConceptoCreado:
        concepto = Concepto.crear(
            tipo=cmd.tipo,
            clave=cmd.clave,
            descripcion=cmd.descripcion,
            unidad_id=str(cmd.unidad_id) if cmd.unidad_id else None,
            familia_id=str(cmd.familia_id) if cmd.familia_id else None,
        )
        async with self._uow:
            concepto_id = await self._conceptos.crear(
                {
                    "tipo": str(concepto.tipo),
                    "clave": str(concepto.clave),
                    "descripcion": concepto.descripcion,
                    "unidad_id": concepto.unidad_id,
                    "familia_id": concepto.familia_id,
                }
            )
            await self._uow.commit()
        return ConceptoCreado(id=concepto_id, concepto=concepto)


class CrearContratista:
    """`POST /contratistas` (Control de obra, §11.2)."""

    def __init__(
        self, *, contratistas: RepositorioContratistas, uow: UnidadDeTrabajo
    ) -> None:
        self._contratistas = contratistas
        self._uow = uow

    async def ejecutar(self, cmd: ComandoCrearContratista) -> ContratistaCreado:
        contratista = Contratista.crear(
            clave=cmd.clave,
            razon_social=cmd.razon_social,
            rfc=cmd.rfc,
            contacto=cmd.contacto,
            telefono=cmd.telefono,
            email=cmd.email,
            calificacion=cmd.calificacion,
            frentes=[str(f) for f in cmd.frentes or []],
        )
        async with self._uow:
            contratista_id = await self._contratistas.crear(
                {
                    "clave": str(contratista.clave),
                    "razon_social": contratista.razon_social,
                    "rfc": contratista.rfc,
                    "contacto": contratista.contacto,
                    "telefono": contratista.telefono,
                    "email": contratista.email,
                    "calificacion": contratista.calificacion,
                    "frentes": list(contratista.frentes),
                }
            )
            await self._uow.commit()
        return ContratistaCreado(id=contratista_id, contratista=contratista)
