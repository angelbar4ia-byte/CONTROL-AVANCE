"""Reinicio de organización: borrado profundo, sin deshacer (§5.1).

Spec §12.4 (RLS) · §5.1 (Control de obra, "Configuración").

Un solo paso, a propósito: a diferencia de una carga (que primero se
revierte y luego se elimina, §10.8), esto no tiene reversa — es la acción
más destructiva del sistema, y así se pidió: confirmación simple en la
pantalla, sin vista previa ni deshacer.
"""

from __future__ import annotations

from obractrl.application.puertos.repositorios import (
    RepositorioOrganizacion,
    UnidadDeTrabajo,
)

__all__ = ["ReiniciarOrganizacion"]


class ReiniciarOrganizacion:
    def __init__(
        self, *, organizacion: RepositorioOrganizacion, uow: UnidadDeTrabajo
    ) -> None:
        self._organizacion = organizacion
        self._uow = uow

    async def ejecutar(self) -> dict[str, int]:
        async with self._uow:
            resumen = await self._organizacion.reiniciar()
            await self._uow.commit()
        return resumen
