"""Puerto del excedente de ejecución (migración 0066)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

__all__ = ["RepositorioComprobaciones"]


class RepositorioComprobaciones(Protocol):
    async def pendientes(self) -> list[dict[str, Any]]:
        """Actividades con excedente por comprobar, dentro del alcance (RLS),
        las más viejas primero."""
        ...

    async def historial(self, actividad_id: UUID) -> list[dict[str, Any]]:
        """Las decisiones tomadas sobre el excedente de una actividad."""
        ...

    async def obtener_para_decidir(self, actividad_id: UUID) -> dict[str, Any] | None:
        """La actividad con su fila **bloqueada** hasta el commit, o `None` si no
        existe o no se ve. El bloqueo evita que dos decisiones simultáneas
        apliquen el mismo excedente dos veces."""
        ...

    async def subir_techo(
        self,
        actividad_id: UUID,
        *,
        cant_programada: Decimal,
        cant_autorizada: Decimal,
        orden_cambio: str,
    ) -> None: ...

    async def declarar_perdida(self, actividad_id: UUID, cantidad: Decimal) -> None: ...

    async def abrir_control_de_cambio_autorizado(
        self,
        *,
        obra_id: UUID,
        actividad_id: UUID,
        cantidad_techo: Decimal,
        orden_cambio: str,
        motivo: str,
        usuario_id: UUID,
    ) -> UUID: ...

    async def registrar_decision(
        self,
        *,
        actividad_id: UUID,
        decision: str,
        cantidad: Decimal,
        nota: str,
        orden_cambio: str | None,
        control_cambio_id: UUID | None,
        usuario_id: UUID,
    ) -> UUID: ...
