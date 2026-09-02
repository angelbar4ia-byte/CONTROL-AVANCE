"""Caso de uso: explosión y CPU de un concepto (§11.2 "Catálogos · APU").

Spec §7.3 (APU y costeo) · §10.6 (cabeceras del archivo de CPU) · §10.8
(versionado) · §12.11 (capa de aplicación).

Tres operaciones sobre el mismo árbol:

- `GET /conceptos/{id}/explosion` → :class:`ExplotarConcepto`
- `GET /conceptos/{id}/cpu` → :class:`ObtenerCPU` (versión vigente + historial)
- `POST /conceptos/{id}/cpu` → :class:`PublicarVersionCPU` (nueva versión)

El caso de uso solo **traduce**: pide al repositorio las filas de `Explosion`
alcanzables y las convierte en `Componente` del dominio. La recursión, la
detección de ciclos y la aritmética del destajo son de
`domain.catalogos.apu`; aquí no hay ninguna regla de negocio.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from obractrl.application.puertos.repositorios import (
    RepositorioConceptos,
    UnidadDeTrabajo,
)
from obractrl.domain.catalogos.apu import (
    Componente,
    ErrorDeAPU,
    ExplosionCalculada,
    VersionCPU,
    explotar,
    publicar_version,
    vigente_de,
)
from obractrl.domain.shared.diccionario import CategoriaExplosion, TipoHijoExplosion
from obractrl.domain.shared.valores import Dinero, PrecioUnitario

__all__ = [
    "CPUDelConcepto",
    "ComandoPublicarVersionCPU",
    "ConceptoNoEncontrado",
    "ErrorDeAPU",
    "ExplotarConcepto",
    "ObtenerCPU",
    "PublicarVersionCPU",
    "VersionPublicada",
]


class ConceptoNoEncontrado(LookupError):
    """El concepto no existe o está fuera del alcance del usuario (§12.4)."""


def _cantidad_de(fila: dict) -> Decimal:
    """Cantidad del componente: `cantidad`, o `rendimiento` si aquella es cero.

    El archivo de CPU trae **una sola** columna para esto —"rendimiento =
    CANTIDAD (E)" (§10.6)—, pero el esquema guarda las dos (§7.3,
    "`cantidad` / `rendimiento`"). Un cargador puede haber llenado una u
    otra, así que se toma la que traiga valor y `cantidad` manda si vienen
    ambas.
    """
    cantidad = Decimal(str(fila.get("cantidad") or 0))
    if cantidad != 0:
        return cantidad
    return Decimal(str(fila.get("rendimiento") or 0))


def componentes_por_clave(
    filas: Sequence[dict],
) -> tuple[dict[str, list[Componente]], dict[str, Decimal]]:
    """Traduce filas de `Explosion` al lenguaje del dominio (claves, §3.3)."""
    composiciones: dict[str, list[Componente]] = {}
    costos_insumo: dict[str, Decimal] = {}

    for fila in filas:
        es_insumo = str(fila["tipo_hijo"]) == TipoHijoExplosion.INSUMO
        clave_insumo = fila.get("insumo_clave") if es_insumo else None
        clave_concepto = None if es_insumo else fila.get("concepto_hijo_clave")

        costo_fila = fila.get("costo_unitario")
        costo_unitario = (
            Decimal(str(costo_fila))
            if costo_fila is not None and Decimal(str(costo_fila)) != 0
            # Fila sin PU propio: el costo lo pone el catálogo (§10.1,
            # `costo_base_actualizado` = costo vigente), que el repositorio ya
            # trajo en `costo_insumo_vigente`.
            else None
        )

        if clave_insumo and fila.get("costo_insumo_vigente") is not None:
            costos_insumo[clave_insumo] = Decimal(str(fila["costo_insumo_vigente"]))

        composiciones.setdefault(str(fila["concepto_clave"]), []).append(
            Componente(
                categoria=CategoriaExplosion(str(fila["categoria"])),
                cantidad=_cantidad_de(fila),
                clave_insumo=clave_insumo,
                clave_concepto=clave_concepto,
                costo_unitario=costo_unitario,
                orden=int(fila.get("orden") or 0),
            )
        )

    return composiciones, costos_insumo


def _versiones_de_dominio(filas: Sequence[dict]) -> list[VersionCPU]:
    return [
        VersionCPU(
            version=int(fila["version"]),
            precio=PrecioUnitario(
                total=Dinero(Decimal(str(fila["precio_unitario"]))),
                destajo=Dinero(Decimal(str(fila["precio_destajo"]))),
            ),
            vigente=bool(fila["vigente"]),
            variante=fila.get("variante"),
        )
        for fila in filas
    ]


@dataclass(frozen=True, slots=True)
class CPUDelConcepto:
    """Estado del CPU de un concepto (§11.2 `GET /conceptos/{id}/cpu`)."""

    concepto_id: UUID
    clave: str
    variante: str | None
    vigente: VersionCPU | None
    historial: tuple[VersionCPU, ...]
    calculado: PrecioUnitario
    """CPU recalculado desde la explosión de hoy.

    Se devuelve junto al vigente a propósito: si difieren, el catálogo cambió
    de costos desde que se publicó esa versión y toca publicar una nueva
    (§10.8, "detección de cambios").
    """


@dataclass(frozen=True, slots=True)
class ComandoPublicarVersionCPU:
    concepto_id: UUID
    variante: str | None = None
    precio_unitario: Decimal | None = None
    precio_destajo: Decimal | None = None
    """Precios explícitos. Si no vienen, se calculan de la explosión (§7.3)."""


@dataclass(frozen=True, slots=True)
class VersionPublicada:
    id: UUID
    concepto_id: UUID
    version: VersionCPU
    retiradas: tuple[int, ...]


class _ConCatalogoDeConceptos:
    """Base con la carga de la explosión, común a los tres casos de uso."""

    def __init__(self, *, conceptos: RepositorioConceptos) -> None:
        self._conceptos = conceptos

    async def _explotar(self, concepto_id: UUID) -> tuple[dict, ExplosionCalculada]:
        concepto = await self._conceptos.obtener(concepto_id)
        if concepto is None:
            # RLS hace indistinguible "no existe" de "no lo puedes ver"
            # a propósito (§12.4).
            raise ConceptoNoEncontrado(
                f"No existe el concepto {concepto_id} o está fuera de tu alcance."
            )

        filas = await self._conceptos.composicion_recursiva(concepto_id)
        composiciones, costos_insumo = componentes_por_clave(filas)
        calculada = explotar(
            str(concepto["clave"]),
            composiciones=composiciones,
            costos_insumo=costos_insumo,
        )
        return concepto, calculada


class ExplotarConcepto(_ConCatalogoDeConceptos):
    """`GET /conceptos/{id}/explosion` (Control de obra y Super intendente)."""

    async def ejecutar(self, concepto_id: UUID) -> ExplosionCalculada:
        _, calculada = await self._explotar(concepto_id)
        return calculada


class ObtenerCPU(_ConCatalogoDeConceptos):
    """`GET /conceptos/{id}/cpu` (Control de obra y Super intendente)."""

    async def ejecutar(
        self, concepto_id: UUID, *, variante: str | None = None
    ) -> CPUDelConcepto:
        concepto, calculada = await self._explotar(concepto_id)
        versiones = _versiones_de_dominio(
            await self._conceptos.versiones_cpu(concepto_id)
        )
        return CPUDelConcepto(
            concepto_id=concepto_id,
            clave=str(concepto["clave"]),
            variante=variante,
            vigente=vigente_de(versiones, variante=variante),
            historial=tuple(v for v in versiones if v.variante == variante),
            calculado=calculada.precio,
        )


class PublicarVersionCPU(_ConCatalogoDeConceptos):
    """`POST /conceptos/{id}/cpu` — nueva versión (Control de obra, §11.2).

    Por defecto el precio **se calcula** de la explosión vigente: capturar a
    mano un CPU que el APU ya determina es la vía rápida a un catálogo
    incoherente. Los precios explícitos existen para el concepto sin
    explosión —un `SUB-` cotizado a tanto alzado, §10.1—, y siguen pasando
    por las invariantes de `PrecioUnitario` (destajo ≤ total, §7.3).
    """

    def __init__(
        self, *, conceptos: RepositorioConceptos, uow: UnidadDeTrabajo
    ) -> None:
        super().__init__(conceptos=conceptos)
        self._uow = uow

    async def ejecutar(self, cmd: ComandoPublicarVersionCPU) -> VersionPublicada:
        _, calculada = await self._explotar(cmd.concepto_id)

        if cmd.precio_unitario is None and cmd.precio_destajo is None:
            precio = calculada.precio
        else:
            try:
                precio = PrecioUnitario(
                    total=Dinero(cmd.precio_unitario or Decimal(0)),
                    destajo=Dinero(cmd.precio_destajo or Decimal(0)),
                )
            except ValueError as exc:
                # `PrecioUnitario` protege sus invariantes con `ValueError`
                # pelón porque es un value object compartido; en este borde
                # es un error de APU y como tal debe llegar al cliente.
                raise ErrorDeAPU(str(exc)) from exc

        versiones = _versiones_de_dominio(
            await self._conceptos.versiones_cpu(cmd.concepto_id)
        )
        nueva, retiradas = publicar_version(versiones, precio, variante=cmd.variante)

        async with self._uow:
            cpu_id = await self._conceptos.publicar_version_cpu(
                cmd.concepto_id,
                version=nueva.version,
                precio_unitario=nueva.precio.total.monto,
                precio_destajo=nueva.precio.destajo.monto,
                variante=nueva.variante,
                retirar=list(retiradas),
            )
            await self._uow.commit()

        return VersionPublicada(
            id=cpu_id,
            concepto_id=cmd.concepto_id,
            version=nueva,
            retiradas=retiradas,
        )
