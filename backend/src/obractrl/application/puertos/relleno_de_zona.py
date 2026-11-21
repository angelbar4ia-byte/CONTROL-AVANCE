"""Puerto de los rellenos de las zonas de losa (migración 0144): el relleno de azotea o compactado que lleva cada zona."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from uuid import UUID

__all__ = ["RepositorioRellenosDeZona"]


@runtime_checkable
class RepositorioRellenosDeZona(Protocol):
    async def de_la_zona(self, zona_id: UUID) -> list[dict[str, Any]]:
        """Los rellenos de la zona en orden de alta: `{id, zona_id, elemento_clave, trazo_id, espesor_m, pendiente_pct, recorrido_m, compensar_espesores,
        abundamiento_pct, mortero_m3_por_m2, espacio_id}` (los numéricos como `Decimal`)."""
        ...

    async def uno(self, relleno_id: UUID) -> dict[str, Any] | None: ...

    async def agregar(self, *, zona_id: UUID, datos: dict[str, Any], autor_id: UUID) -> UUID: ...

    async def actualizar(self, relleno_id: UUID, datos: dict[str, Any]) -> None: ...

    async def eliminar(self, relleno_id: UUID) -> None: ...

    async def espacio_existe(self, obra_id: UUID, espacio_id: UUID) -> bool:
        """El espacio es de esa obra (0143)."""
        ...
