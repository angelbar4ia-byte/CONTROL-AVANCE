"""Reglas de la estimación semanal.

Spec §6 · §3.2 (folio) · §11.3 workflow E.

Ciclo: ``borrador`` (R/S generan) → ``enviada`` (R/S) → ``validada`` (C).
A diferencia del cierre (§4), aquí no hay distinción autorizar/validar: un
solo paso de Control de obra cierra el flujo.

``modo`` (destajo · concepto · subcontrato) no es una preferencia de
presentación: selecciona **qué actividades entran** a la estimación —solo
las que se pagan de esa forma (`actividad.modo_pago`)— y **qué precio** se
usa para cada una (`PrecioUnitario.para_modo`, §6). Dos corridas del mismo
modo sobre la misma semana solo repiten el subconjunto; no hay dos formas de
cobrar la misma actividad en la misma estimación.

Módulo puro: sin BD, sin FastAPI, 100% testeable (§12.11).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from obractrl.domain.shared.diccionario import (
    EstatusEstimacion,
    ModoPago,
    Rol,
    TipoSemana,
)
from obractrl.domain.shared.folio import Folio
from obractrl.domain.shared.valores import Dinero, PrecioUnitario

__all__ = [
    "TRANSICIONES",
    "ConceptoEstimado",
    "ErrorDeEstimacion",
    "Estimacion",
    "seleccionar_estimables",
]


class ErrorDeEstimacion(ValueError):
    """Violación de una regla de estimación (§6, §11.3 E)."""


TRANSICIONES: dict[EstatusEstimacion, set[EstatusEstimacion]] = {
    EstatusEstimacion.BORRADOR: {EstatusEstimacion.ENVIADA},
    EstatusEstimacion.ENVIADA: {EstatusEstimacion.VALIDADA},
    EstatusEstimacion.VALIDADA: set(),
}
"""A diferencia del cierre (§6), la estimación no tiene rechazo modelado: es
un corte lineal borrador → enviada → validada (§11.3 E)."""


@dataclass(frozen=True, slots=True)
class ConceptoEstimado:
    """Línea de estimación: una actividad con avance validado (§11.3 E.2)."""

    actividad_id: str
    concepto_id: str | None
    cantidad_validada: Decimal
    precio_unitario: Dinero
    importe: Dinero

    @property
    def fuera_catalogo(self) -> bool:
        return self.concepto_id is None

    @classmethod
    def desde_actividad(
        cls,
        *,
        actividad_id: str,
        concepto_id: str | None,
        cantidad_validada: Decimal,
        precio: PrecioUnitario,
        modo: ModoPago,
    ) -> ConceptoEstimado:
        precio_aplicable = precio.para_modo(modo)
        return cls(
            actividad_id=actividad_id,
            concepto_id=concepto_id,
            cantidad_validada=cantidad_validada,
            precio_unitario=precio_aplicable,
            importe=precio_aplicable * cantidad_validada,
        )


def seleccionar_estimables(
    filas: list[dict], modo: ModoPago
) -> list[ConceptoEstimado]:
    """Filtra las actividades estimables al ``modo`` de esta corrida y arma
    sus líneas (§11.3 E.2).

    ``filas`` es la salida cruda de
    ``RepositorioEstimaciones.actividades_estimables``: cada una trae
    ``actividad_id``, ``concepto_id``, ``cantidad_validada``,
    ``precio_unitario``, ``precio_destajo`` y ``modo_pago`` (el modo real de
    esa actividad, no el de la corrida). Una actividad que se paga distinto
    del ``modo`` pedido simplemente no entra —queda para la corrida de su
    propio modo.
    """
    conceptos = []
    for fila in filas:
        if ModoPago(fila["modo_pago"]) is not modo:
            continue
        precio = PrecioUnitario(
            total=Dinero(fila["precio_unitario"]), destajo=Dinero(fila["precio_destajo"])
        )
        conceptos.append(
            ConceptoEstimado.desde_actividad(
                actividad_id=str(fila["actividad_id"]),
                concepto_id=str(fila["concepto_id"]) if fila.get("concepto_id") else None,
                cantidad_validada=Decimal(str(fila["cantidad_validada"])),
                precio=precio,
                modo=modo,
            )
        )
    return conceptos


@dataclass(slots=True)
class Estimacion:
    """Entidad de dominio de la estimación semanal (§7.6, §11.3 E)."""

    obra_id: str
    semana: int
    anio: int
    modo: ModoPago
    conceptos: list[ConceptoEstimado]
    creada_por: str
    tipo_semana: TipoSemana = TipoSemana.OBRA
    folio: Folio | None = None
    origen_erp: bool = False
    estatus: EstatusEstimacion = EstatusEstimacion.BORRADOR
    validada_por: str | None = None
    _monto_total: Dinero = field(init=False, repr=False)

    def __post_init__(self) -> None:
        total = Dinero(0)
        for concepto in self.conceptos:
            total = total + concepto.importe
        self._monto_total = total

    @property
    def monto_total(self) -> Dinero:
        return self._monto_total

    @classmethod
    def generar(
        cls,
        *,
        obra_id: str,
        semana: int,
        anio: int,
        modo: ModoPago,
        conceptos: list[ConceptoEstimado],
        creada_por: str,
        rol: Rol,
        folio: Folio | None = None,
        tipo_semana: TipoSemana = TipoSemana.OBRA,
        origen_erp: bool = False,
    ) -> Estimacion:
        """Genera la estimación en borrador (§11.3 E.1)."""
        if rol not in (Rol.RESIDENTE, Rol.SUPERVISOR):
            raise ErrorDeEstimacion(
                f"Solo Residente o Supervisor generan una estimación; el rol "
                f"{rol.value!r} no puede."
            )
        if not conceptos:
            raise ErrorDeEstimacion(
                "No hay actividades con cierre validado para ese modo en la "
                "semana activa (§11.3 E.2)."
            )
        return cls(
            obra_id=obra_id,
            semana=semana,
            anio=anio,
            modo=modo,
            conceptos=list(conceptos),
            creada_por=creada_por,
            tipo_semana=tipo_semana,
            folio=folio,
            origen_erp=origen_erp,
        )

    def _transicionar(self, destino: EstatusEstimacion) -> None:
        permitidas = TRANSICIONES[self.estatus]
        if destino not in permitidas:
            esperadas = ", ".join(sorted(e.value for e in permitidas)) or "ninguna"
            raise ErrorDeEstimacion(
                f"No se puede pasar de {self.estatus.value!r} a "
                f"{destino.value!r}. Transiciones válidas: {esperadas}."
            )
        self.estatus = destino

    def enviar(self, *, rol: Rol) -> None:
        """Residente o Supervisor envían la estimación (§11.3 E.3)."""
        if rol not in (Rol.RESIDENTE, Rol.SUPERVISOR):
            raise ErrorDeEstimacion(
                f"Solo Residente o Supervisor envían una estimación; el rol "
                f"{rol.value!r} no puede."
            )
        self._transicionar(EstatusEstimacion.ENVIADA)

    def validar(self, *, usuario_id: str, rol: Rol) -> None:
        """Control de obra valida: bloquea el periodo (§11.3 E.4)."""
        if rol is not Rol.CONTROL_OBRA:
            raise ErrorDeEstimacion(
                f"Solo Control de obra valida una estimación; el rol "
                f"{rol.value!r} no puede."
            )
        self._transicionar(EstatusEstimacion.VALIDADA)
        self.validada_por = usuario_id
