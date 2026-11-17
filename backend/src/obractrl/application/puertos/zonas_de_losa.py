"""Puerto de las zonas de losa (migración 0137): zonas, polígonos con rol de losa y puntos de nivel exterior."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

__all__ = ["RepositorioZonasDeLosa"]


@runtime_checkable
class RepositorioZonasDeLosa(Protocol):
    async def plano(self, plano_id: UUID) -> dict[str, Any] | None:
        """`{id, escala_m_por_unidad}`; `None` si no existe o no es visible."""
        ...

    async def zonas(self, plano_id: UUID) -> list[dict[str, Any]]: ...

    async def zona(self, zona_id: UUID) -> dict[str, Any] | None: ...

    async def losas(self, plano_id: UUID) -> list[dict[str, Any]]:
        """Los polígonos con rol de losa: `{id, zona_id, espesor_propio_m, geojson}` (con sus huecos ya restados)."""
        ...

    async def puntos_de_nivel(self, plano_id: UUID) -> list[dict[str, Any]]:
        """`{id, x, y, cota_m, rotulo}` en coordenadas de plano."""
        ...

    async def crear(self, *, plano_id: UUID, datos: dict[str, Any], autor_id: UUID) -> UUID: ...

    async def actualizar(self, zona_id: UUID, datos: dict[str, Any]) -> None: ...

    async def eliminar(self, zona_id: UUID) -> None: ...

    async def trazo(self, trazo_id: UUID) -> dict[str, Any] | None:
        """`{id, plano_id, tipo, hueco_de, grosor_m, geojson}`; `None` si no existe o no es visible."""
        ...

    async def fijar_losa(self, trazo_id: UUID, zona_id: UUID | None, espesor_m: Decimal | None) -> None: ...

    async def fijar_nivel_exterior(self, trazo_id: UUID, cota_m: Decimal | None, rotulo: str | None) -> None: ...
