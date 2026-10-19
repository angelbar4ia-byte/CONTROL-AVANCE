"""Caso de uso: Extracción de un ensamble paramétrico (skill `erp-parametrico`
§6, dirección presupuesto → ensamble).

Spec §5.7-§5.10 · §12.11 (capa de aplicación).

Extracción arma la **plantilla** (ensamble) a partir de lo ya construido: el
llamador decide, renglón por renglón, qué concepto o sub-ensamble entra, con
qué cantidad y con qué origen (§2, "heredada del concepto / heredada de un
destajo / manual") — este caso de uso no camina el árbol del presupuesto ni
inventa esa clasificación por sí solo. Esa es la misma disciplina que el
usuario fijó para `modo_cantidad`: "el sistema interpreta, el usuario decide,
y que sea reversible" — aquí la propuesta de qué renglones extraer y con qué
origen vive aguas arriba (quien llama a `ExtraerEnsamble`), y nada queda
escrito hasta que ese renglón se confirma.

El caso de uso solo **traduce y persiste**: valida cada renglón con el
dominio (`RenglonEnsamble`, que exige concepto XOR sub-ensamble), resuelve
clave→id contra los catálogos, y guarda. La aritmética de la explosión y de
la tasa/dispersión es de `domain.catalogos.ensamble`; aquí no hay ninguna
regla de negocio nueva.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from obractrl.application.casos_uso.calcular_cpu import ConceptoNoEncontrado
from obractrl.application.puertos.repositorios import (
    RepositorioConceptos,
    RepositorioEnsambles,
    UnidadDeTrabajo,
)
from obractrl.domain.catalogos.apu import ErrorDeAPU
from obractrl.domain.catalogos.ensamble import RenglonEnsamble
from obractrl.domain.shared.diccionario import TipoHijoEnsamble

__all__ = [
    "ClaveDeEnsambleEnUso",
    "ComandoExtraerEnsamble",
    "ConceptoNoEncontrado",
    "EnsambleCreado",
    "ExtraerEnsamble",
    "SubEnsambleNoEncontrado",
]


class ClaveDeEnsambleEnUso(ErrorDeAPU):
    """Ya existe un ensamble con esta clave (§3.3: la clave es la identidad)."""

    def __init__(self, clave: str) -> None:
        super().__init__(f"Ya existe un ensamble con la clave {clave!r}.")
        self.clave = clave


class SubEnsambleNoEncontrado(LookupError):
    """El sub-ensamble referido por un renglón no existe (o no es visible,
    §12.4 — RLS hace indistinguibles los dos casos a propósito)."""

    def __init__(self, clave: str) -> None:
        super().__init__(f"No existe el ensamble {clave!r} o está fuera de tu alcance.")
        self.clave = clave


@dataclass(frozen=True, slots=True)
class ComandoExtraerEnsamble:
    clave: str
    nombre: str
    renglones: Sequence[RenglonEnsamble]
    divisor_concepto_clave: str | None = None
    divisor_nombre: str | None = None
    presupuesto_origen_id: UUID | None = None
    """El presupuesto del que se extrajeron estos renglones (§3: referencia
    informativa, nunca liga estructural — se guarda en cada renglón, no en
    el ensamble, y sobrevive aunque esa partida se borre o reordene)."""
    cohorte_prototipo_ids: Sequence[UUID] = ()
    """Los prototipos que declaran, a mano, pertenecer a la cohorte de este
    ensamble (§5.7: la cohorte nunca se deriva, siempre se declara)."""


@dataclass(frozen=True, slots=True)
class EnsambleCreado:
    id: UUID
    clave: str
    nombre: str
    renglones: int
    cohorte: tuple[UUID, ...]


class ExtraerEnsamble:
    """`POST /ensambles` vía extracción (Control de obra y Super intendente,
    §11.2 — mismo rol que puede escribir presupuesto y catálogo de APU)."""

    def __init__(
        self,
        *,
        ensambles: RepositorioEnsambles,
        conceptos: RepositorioConceptos,
        uow: UnidadDeTrabajo,
    ) -> None:
        self._ensambles = ensambles
        self._conceptos = conceptos
        self._uow = uow

    async def ejecutar(self, cmd: ComandoExtraerEnsamble) -> EnsambleCreado:
        if await self._ensambles.obtener_por_clave(cmd.clave) is not None:
            raise ClaveDeEnsambleEnUso(cmd.clave)

        divisor_concepto_id: UUID | None = None
        if cmd.divisor_concepto_clave is not None:
            divisor = await self._conceptos.obtener_por_clave(cmd.divisor_concepto_clave)
            if divisor is None:
                raise ConceptoNoEncontrado(
                    f"No existe el concepto {cmd.divisor_concepto_clave!r} o está "
                    "fuera de tu alcance (divisor del ensamble)."
                )
            divisor_concepto_id = UUID(str(divisor["id"]))

        renglones_a_guardar = [
            await self._resolver_renglon(renglon, cmd.presupuesto_origen_id)
            for renglon in cmd.renglones
        ]

        async with self._uow:
            ensamble_id = await self._ensambles.crear(
                {
                    "clave": cmd.clave,
                    "nombre": cmd.nombre,
                    "divisor_concepto_id": divisor_concepto_id,
                    "divisor_nombre": cmd.divisor_nombre,
                }
            )
            if renglones_a_guardar:
                await self._ensambles.agregar_renglones(ensamble_id, renglones_a_guardar)
            if cmd.cohorte_prototipo_ids:
                await self._ensambles.agregar_cohorte(
                    ensamble_id, cmd.cohorte_prototipo_ids
                )
            await self._uow.commit()

        return EnsambleCreado(
            id=ensamble_id,
            clave=cmd.clave,
            nombre=cmd.nombre,
            renglones=len(renglones_a_guardar),
            cohorte=tuple(cmd.cohorte_prototipo_ids),
        )

    async def _resolver_renglon(
        self, renglon: RenglonEnsamble, presupuesto_origen_id: UUID | None
    ) -> dict:
        concepto_id: UUID | None = None
        sub_ensamble_id: UUID | None = None

        if renglon.tipo_hijo is TipoHijoEnsamble.CONCEPTO:
            concepto = await self._conceptos.obtener_por_clave(renglon.clave_concepto or "")
            if concepto is None:
                raise ConceptoNoEncontrado(
                    f"No existe el concepto {renglon.clave_concepto!r} o está "
                    "fuera de tu alcance."
                )
            concepto_id = UUID(str(concepto["id"]))
        else:
            sub_ensamble = await self._ensambles.obtener_por_clave(
                renglon.clave_sub_ensamble or ""
            )
            if sub_ensamble is None:
                raise SubEnsambleNoEncontrado(renglon.clave_sub_ensamble or "")
            sub_ensamble_id = UUID(str(sub_ensamble["id"]))

        return {
            "concepto_id": concepto_id,
            "sub_ensamble_id": sub_ensamble_id,
            "cantidad": Decimal(renglon.cantidad),
            "origen": str(renglon.origen),
            "presupuesto_origen_id": presupuesto_origen_id,
            "orden": renglon.orden,
        }
