"""Casos de uso: comprobación y validación del excedente de ejecución (0066).

La decisión del usuario: si se puede ejecutar más de lo programado, **el
excedente se va a comprobación y validación**. Capturar nunca se bloquea
(`CapturarAvance` ya no rechaza); aquí Control de obra decide qué fue ese
excedente:

  * `ValidarExcedente`: se vuelve control de cambio (con su orden de cambio) y
    sube el techo a lo ejecutado;
  * `DeclararPerdida`: se ejecutó y no se cobra.

Lectura abierta a quien ve la obra (RLS); decidir es de quien autoriza un
control de cambio.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.application.puertos.comprobacion import RepositorioComprobaciones
from obractrl.application.puertos.repositorios import UnidadDeTrabajo
from obractrl.domain.avance.comprobacion import (
    ErrorDeComprobacion,
    SinExcedente,
    exigir_nota,
    exigir_orden_de_cambio,
    puede_comprobar,
    techo_tras_validar,
)
from obractrl.domain.avance.reglas import excedente_de
from obractrl.domain.shared.diccionario import Rol

__all__ = [
    "ActividadSinComprobacion",
    "ComandoDecidirExcedente",
    "ConsultarComprobaciones",
    "DecisionDeExcedente",
    "DeclararPerdidaDeExcedente",
    "ValidarExcedente",
]


class ActividadSinComprobacion(LookupError):
    """La actividad no existe o salió del alcance (RLS): indistinguibles a
    propósito (§12.4)."""


@dataclass(frozen=True, slots=True)
class ComandoDecidirExcedente:
    actividad_id: UUID
    usuario_id: UUID
    rol: Rol
    nota: str
    orden_cambio: str | None = None


@dataclass(frozen=True, slots=True)
class DecisionDeExcedente:
    decision_id: UUID
    decision: str
    cantidad: Decimal
    control_cambio_id: UUID | None


class ConsultarComprobaciones:
    """La bandeja de lo que espera comprobación y validación, y su historial."""

    def __init__(self, *, comprobaciones: RepositorioComprobaciones) -> None:
        self._comprobaciones = comprobaciones

    async def pendientes(self) -> list[dict[str, Any]]:
        return await self._comprobaciones.pendientes()

    async def historial(self, actividad_id: UUID) -> list[dict[str, Any]]:
        return await self._comprobaciones.historial(actividad_id)


class _DecisionBase:
    def __init__(
        self, *, comprobaciones: RepositorioComprobaciones, uow: UnidadDeTrabajo
    ) -> None:
        self._comprobaciones = comprobaciones
        self._uow = uow

    @staticmethod
    def _exigir_rol(rol: Rol) -> None:
        if not puede_comprobar(rol):
            raise ErrorDeComprobacion(
                f"Un {rol.value} no comprueba excedentes; lo hacen Control de obra "
                f"y el Super intendente (§4).",
                "rol",
            )

    async def _excedente_pendiente(self, actividad_id: UUID) -> tuple[dict[str, Any], Decimal]:
        actividad = await self._comprobaciones.obtener_para_decidir(actividad_id)
        if actividad is None:
            raise ActividadSinComprobacion(
                f"La actividad {actividad_id} no existe o no está en tu alcance."
            )
        excedente = excedente_de(
            Decimal(str(actividad["cant_ejecutada"])),
            Decimal(str(actividad["cant_programada"])),
            Decimal(str(actividad["cant_perdida"])),
        )
        if excedente <= 0:
            raise SinExcedente(
                "La actividad no tiene excedente pendiente de comprobación: "
                "quizá ya se decidió."
            )
        return actividad, excedente


class ValidarExcedente(_DecisionBase):
    """Se comprobó que el excedente fue trabajo real y se autoriza: se vuelve
    control de cambio y sube el techo."""

    async def ejecutar(self, cmd: ComandoDecidirExcedente) -> DecisionDeExcedente:
        self._exigir_rol(cmd.rol)
        nota = exigir_nota(cmd.nota)
        orden = exigir_orden_de_cambio(cmd.orden_cambio)

        async with self._uow:
            actividad, excedente = await self._excedente_pendiente(cmd.actividad_id)
            programada, autorizada = techo_tras_validar(
                cant_ejecutada=Decimal(str(actividad["cant_ejecutada"])),
                cant_autorizada=(
                    Decimal(str(actividad["cant_autorizada"]))
                    if actividad["cant_autorizada"] is not None
                    else None
                ),
            )
            control_id = await self._comprobaciones.abrir_control_de_cambio_autorizado(
                obra_id=actividad["obra_id"],
                actividad_id=cmd.actividad_id,
                cantidad_techo=autorizada,
                orden_cambio=orden,
                motivo=f"Excedente de ejecución comprobado: {excedente} por encima de lo programado.",
                usuario_id=cmd.usuario_id,
            )
            await self._comprobaciones.subir_techo(
                cmd.actividad_id,
                cant_programada=programada,
                cant_autorizada=autorizada,
                orden_cambio=orden,
            )
            decision_id = await self._comprobaciones.registrar_decision(
                actividad_id=cmd.actividad_id,
                decision="validado",
                cantidad=excedente,
                nota=nota,
                orden_cambio=orden,
                control_cambio_id=control_id,
                usuario_id=cmd.usuario_id,
            )
            await self._uow.commit()
        return DecisionDeExcedente(decision_id, "validado", excedente, control_id)


class DeclararPerdidaDeExcedente(_DecisionBase):
    """El excedente no se respalda: se ejecutó y no se cobra."""

    async def ejecutar(self, cmd: ComandoDecidirExcedente) -> DecisionDeExcedente:
        self._exigir_rol(cmd.rol)
        nota = exigir_nota(cmd.nota)

        async with self._uow:
            _, excedente = await self._excedente_pendiente(cmd.actividad_id)
            await self._comprobaciones.declarar_perdida(cmd.actividad_id, excedente)
            decision_id = await self._comprobaciones.registrar_decision(
                actividad_id=cmd.actividad_id,
                decision="perdida",
                cantidad=excedente,
                nota=nota,
                orden_cambio=None,
                control_cambio_id=None,
                usuario_id=cmd.usuario_id,
            )
            await self._uow.commit()
        return DecisionDeExcedente(decision_id, "perdida", excedente, None)
