"""Puerto de los elementos de las zonas de losa (migración 0142): las trabes, contratrabes y nervaduras que lleva cada zona."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from uuid import UUID

__all__ = ["RepositorioElementosDeLosa"]


@runtime_checkable
class RepositorioElementosDeLosa(Protocol):
    async def de_la_zona(self, zona_id: UUID) -> list[dict[str, Any]]:
        """Los elementos de la zona en orden de alta: `{id, zona_id, elemento_clave, modo, cantidad, largo_m, pago, trazo_id, geojson}` (el
        `geojson` es la línea del plano si el elemento se mide de ella, si no `None`)."""
        ...

    async def uno(self, elemento_id: UUID) -> dict[str, Any] | None: ...

    async def agregar(self, *, zona_id: UUID, datos: dict[str, Any], autor_id: UUID) -> UUID: ...

    async def actualizar(self, elemento_id: UUID, datos: dict[str, Any]) -> None: ...

    async def eliminar(self, elemento_id: UUID) -> None: ...
