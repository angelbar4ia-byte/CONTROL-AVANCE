"""Caso de uso: enlaces entre hojas (Fase 2, migración 0091).

Una zona de una hoja que dice «ver plano X» y salta a otra hoja de la **misma obra**. Es navegación:
nunca produce cantidad. Aquí se valida que las dos hojas existan, sean de la misma obra y distintas,
y que la zona tenga tamaño; el resto es del repositorio.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.cuantificar import (
    ErrorDeCuantificacion,
    PlanoNoEncontrado,
)
from obractrl.application.puertos.repositorios import UnidadDeTrabajo

__all__ = [
    "ComandoCrearEnlaceDeHoja",
    "EnlaceDeHojaNoEncontrado",
    "GestionarEnlacesDeHoja",
]


class EnlaceDeHojaNoEncontrado(LookupError):
    """El enlace no existe o está fuera del alcance."""


@dataclass(frozen=True, slots=True)
class ComandoCrearEnlaceDeHoja:
    plano_id: UUID
    destino_plano_id: UUID
    etiqueta: str
    x: float
    y: float
    ancho: float
    alto: float
    autor_id: UUID


class GestionarEnlacesDeHoja:
    def __init__(self, *, planos: Any, enlaces: Any, uow: UnidadDeTrabajo) -> None:
        self._planos = planos
        self._enlaces = enlaces
        self._uow = uow

    async def listar(self, plano_id: UUID) -> list[dict[str, Any]]:
        if await self._planos.obtener(plano_id) is None:
            raise PlanoNoEncontrado(
                f"El plano {plano_id} no existe o está fuera de tu alcance."
            )
        filas: list[dict[str, Any]] = await self._enlaces.de_plano(plano_id)
        return filas

    async def crear(self, cmd: ComandoCrearEnlaceDeHoja) -> UUID:
        etiqueta = cmd.etiqueta.strip()
        if not etiqueta:
            raise ErrorDeCuantificacion(
                "El enlace necesita una etiqueta («Ver corte A-A»)."
            )
        if cmd.ancho <= 0 or cmd.alto <= 0:
            raise ErrorDeCuantificacion("La zona del enlace necesita ancho y alto.")
        if cmd.plano_id == cmd.destino_plano_id:
            raise ErrorDeCuantificacion("El enlace lleva a otra hoja, no a esta misma.")
        origen = await self._planos.obtener(cmd.plano_id)
        destino = await self._planos.obtener(cmd.destino_plano_id)
        if origen is None or destino is None:
            raise PlanoNoEncontrado("La hoja no existe o está fuera de tu alcance.")
        if origen["obra_id"] != destino["obra_id"]:
            raise ErrorDeCuantificacion("Solo se enlaza a otra hoja de la misma obra.")
        async with self._uow:
            enlace_id = await self._enlaces.crear(
                plano_id=cmd.plano_id,
                destino_plano_id=cmd.destino_plano_id,
                etiqueta=etiqueta,
                x=cmd.x,
                y=cmd.y,
                ancho=cmd.ancho,
                alto=cmd.alto,
                autor_id=cmd.autor_id,
            )
            await self._uow.commit()
        creado: UUID = enlace_id
        return creado

    async def eliminar(self, enlace_id: UUID) -> None:
        async with self._uow:
            if not await self._enlaces.eliminar(enlace_id):
                raise EnlaceDeHojaNoEncontrado(
                    f"El enlace {enlace_id} no existe o está fuera de tu alcance."
                )
            await self._uow.commit()
