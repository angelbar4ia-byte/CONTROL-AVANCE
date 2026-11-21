"""Puerto de los cimientos de las zonas de losa (migración 0146): los muros de cimentación medidos sobre una línea del plano con cotas de desplante."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from uuid import UUID

__all__ = ["RepositorioCimientosDeZona"]


@runtime_checkable
class RepositorioCimientosDeZona(Protocol):
    async def de_la_zona(self, zona_id: UUID) -> list[dict[str, Any]]:
        """Los cimientos de la zona en orden de alta: `{id, zona_id, elemento_clave, trazo_id, cota_desplante_m, punto_nivel_id, cota_corona_m, caras, dentellon,
        espacio_id, geojson}` (los numéricos como `Decimal`; `geojson` es la línea del plano)."""
        ...

    async def uno(self, cimiento_id: UUID) -> dict[str, Any] | None: ...

    async def agregar(self, *, zona_id: UUID, datos: dict[str, Any], autor_id: UUID) -> UUID: ...

    async def actualizar(self, cimiento_id: UUID, datos: dict[str, Any]) -> None: ...

    async def eliminar(self, cimiento_id: UUID) -> None: ...

    async def con_la_linea(self, trazo_id: UUID) -> UUID | None:
        """El cimiento (de cualquier zona) que ya mide esa línea del plano, o `None`."""
        ...

    async def espacio_existe(self, obra_id: UUID, espacio_id: UUID) -> bool:
        """El espacio es de esa obra (0143)."""
        ...
