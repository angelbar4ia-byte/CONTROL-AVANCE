"""Puerto de la bitácora de ediciones del programa (migración 0067)."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

__all__ = ["RepositorioEdicionesDePrograma"]


class RepositorioEdicionesDePrograma(Protocol):
    async def registrar(
        self,
        *,
        obra_id: UUID,
        actividad_id: UUID,
        usuario_id: UUID,
        rol: str,
        tipo: str,
        antes: dict[str, Any],
        despues: dict[str, Any],
    ) -> UUID:
        """Agrega una edición. La bitácora no se reescribe ni se borra."""
        ...

    async def de_obra(self, obra_id: UUID, *, limite: int = 200) -> list[dict[str, Any]]:
        """Las últimas ediciones de una obra, las más recientes primero."""
        ...
