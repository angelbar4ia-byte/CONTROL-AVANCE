"""Puerto de las escaleras de las zonas de losa (migración 0145): las escaleras forjadas que arrancan en cada zona."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from uuid import UUID

__all__ = ["RepositorioEscalerasDeZona"]


@runtime_checkable
class RepositorioEscalerasDeZona(Protocol):
    async def de_la_zona(self, zona_id: UUID) -> list[dict[str, Any]]:
        """Las escaleras que arrancan en la zona, en orden de alta: `{id, zona_id, elemento_clave, zona_llegada_id, cota_arranque_m, cota_llegada_m, peldanos,
        contrahuella_max_m, huella_m, ancho_m, espesor_m, rampas, largo_descanso_m, trazo_id, espacio_id, geojson}` (los numéricos como `Decimal`; `geojson` es
        la línea del plano si hay `trazo_id`)."""
        ...

    async def uno(self, escalera_id: UUID) -> dict[str, Any] | None: ...

    async def agregar(self, *, zona_id: UUID, datos: dict[str, Any], autor_id: UUID) -> UUID: ...

    async def actualizar(self, escalera_id: UUID, datos: dict[str, Any]) -> None: ...

    async def eliminar(self, escalera_id: UUID) -> None: ...

    async def con_la_linea(self, trazo_id: UUID) -> UUID | None:
        """La escalera (de cualquier zona) que ya usa esa línea del plano para su recorrido, o `None`."""
        ...

    async def espacio_existe(self, obra_id: UUID, espacio_id: UUID) -> bool:
        """El espacio es de esa obra (0143)."""
        ...
