"""Puerto de las confirmaciones de avance (migración 0070)."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

__all__ = ["RepositorioConfirmaciones"]


class RepositorioConfirmaciones(Protocol):
    async def registrar(
        self,
        *,
        obra_id: UUID,
        actividad_id: UUID,
        cantidad: Any,
        momento: str,
        nota: str | None,
        usuario_id: UUID,
    ) -> UUID:
        """Agrega una confirmación. No se reescribe ni se borra."""
        ...

    async def de_obra(self, obra_id: UUID) -> list[dict[str, Any]]:
        """Cada actividad de la obra con su última confirmación (o ninguna)."""
        ...

    async def periodo_activo_bloqueado(self, obra_id: UUID) -> bool:
        """¿La semana activa de la obra ya la cerró una estimación validada? Esa
        semana no admite confirmar avance, para nadie (D-540)."""
        ...
