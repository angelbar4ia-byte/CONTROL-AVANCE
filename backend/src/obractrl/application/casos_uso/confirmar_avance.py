"""Casos de uso: confirmar el avance antes de estimar (migración 0070).

El residente afirma que lo registrado en una actividad es lo que se hizo
(`ConfirmarAvance`), y cualquiera que ve la obra puede ver qué falta por confirmar
(`ConsultarConfirmaciones`). Confirmar **no bloquea nada** (D-535): lo que se estima
por encima de lo confirmado es una alerta que se lee en la estimación.

La confirmación guarda lo ejecutado **en ese momento**: si luego se captura más
avance, queda detrás y la pantalla pide confirmar de nuevo, pero la anterior sigue
siendo la constancia de lo que se afirmó entonces.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.generar_obra_desde_prototipo import ObraNoEncontrada
from obractrl.application.puertos.confirmacion import RepositorioConfirmaciones
from obractrl.application.puertos.repositorios import (
    RepositorioActividades,
    RepositorioObras,
    UnidadDeTrabajo,
)
from obractrl.domain.avance.confirmacion import (
    ErrorDeConfirmacion,
    estado_de_confirmacion,
    exigir_algo_que_confirmar,
    exigir_residente,
)
from obractrl.domain.shared.diccionario import Rol

__all__ = [
    "ActividadSinConfirmacion",
    "ComandoConfirmarAvance",
    "ConfirmacionRegistrada",
    "ConfirmarAvance",
    "ConsultarConfirmaciones",
    "ErrorDeConfirmacion",
    "PeriodoBloqueadoParaConfirmar",
]

MOMENTOS = ("al_terminar", "antes_de_estimar")


class ActividadSinConfirmacion(LookupError):
    """La actividad no existe o salió del alcance (RLS): indistinguibles a
    propósito (§12.4)."""


class PeriodoBloqueadoParaConfirmar(RuntimeError):
    """La semana activa de la obra ya la cerró una estimación validada (D-540)."""


@dataclass(frozen=True, slots=True)
class ComandoConfirmarAvance:
    actividad_id: UUID
    usuario_id: UUID
    rol: Rol
    momento: str = "antes_de_estimar"
    nota: str | None = None


@dataclass(frozen=True, slots=True)
class ConfirmacionRegistrada:
    id: UUID
    cantidad: Decimal
    momento: str


class ConfirmarAvance:
    def __init__(
        self,
        *,
        actividades: RepositorioActividades,
        confirmaciones: RepositorioConfirmaciones,
        uow: UnidadDeTrabajo,
    ) -> None:
        self._actividades = actividades
        self._confirmaciones = confirmaciones
        self._uow = uow

    async def ejecutar(self, cmd: ComandoConfirmarAvance) -> ConfirmacionRegistrada:
        exigir_residente(cmd.rol)
        if cmd.momento not in MOMENTOS:
            raise ErrorDeConfirmacion(
                f"El momento de la confirmación es uno de {', '.join(MOMENTOS)}; "
                f"llegó {cmd.momento!r}."
            )

        actividad = await self._actividades.obtener(cmd.actividad_id)
        if actividad is None:
            raise ActividadSinConfirmacion(
                f"Actividad {cmd.actividad_id} no encontrada en tu alcance."
            )
        cantidad = Decimal(str(actividad["cant_ejecutada"]))
        exigir_algo_que_confirmar(cantidad)

        obra_id = UUID(str(actividad["obra_id"]))
        if await self._confirmaciones.periodo_activo_bloqueado(obra_id):
            raise PeriodoBloqueadoParaConfirmar(
                "La semana activa de esta obra ya la cerró una estimación validada: "
                "esa semana no admite confirmar avance, para nadie."
            )

        nota = (cmd.nota or "").strip() or None
        async with self._uow:
            confirmacion_id = await self._confirmaciones.registrar(
                obra_id=obra_id,
                actividad_id=cmd.actividad_id,
                cantidad=cantidad,
                momento=cmd.momento,
                nota=nota,
                usuario_id=cmd.usuario_id,
            )
            await self._uow.commit()
        return ConfirmacionRegistrada(
            id=confirmacion_id, cantidad=cantidad, momento=cmd.momento
        )


class ConsultarConfirmaciones:
    """`GET /obras/{id}/avance/confirmaciones`: cada actividad con su estado de
    confirmación (sin confirmar · desactualizada · confirmada)."""

    def __init__(
        self, *, confirmaciones: RepositorioConfirmaciones, obras: RepositorioObras
    ) -> None:
        self._confirmaciones = confirmaciones
        self._obras = obras

    async def ejecutar(self, obra_id: UUID) -> list[dict[str, Any]]:
        if await self._obras.obtener(obra_id) is None:
            raise ObraNoEncontrada(f"Obra {obra_id} no encontrada en tu alcance.")
        filas = await self._confirmaciones.de_obra(obra_id)
        return [
            {
                **fila,
                "estado": estado_de_confirmacion(
                    Decimal(str(fila["cant_ejecutada"])),
                    None
                    if fila["cant_confirmada"] is None
                    else Decimal(str(fila["cant_confirmada"])),
                ).value,
            }
            for fila in filas
        ]
