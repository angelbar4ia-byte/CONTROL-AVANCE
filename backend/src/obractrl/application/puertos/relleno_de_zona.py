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

    # ── Bajadas pluviales del relleno dinámico de azotea (0147) ──────────────────────────────────────────

    async def bajadas_de_la_zona(self, zona_id: UUID) -> list[dict[str, Any]]:
        """Las bajadas de todos los rellenos de la zona en orden de alta: `{id, relleno_id, trazo_id, linea_trazo_id, rotulo, geojson, geojson_linea}` (la geometría
        sale de los trazos: el punto y, si hay, la línea de pendiente)."""
        ...

    async def bajada(self, bajada_id: UUID) -> dict[str, Any] | None: ...

    async def agregar_bajada(self, *, relleno_id: UUID, trazo_id: UUID, linea_trazo_id: UUID | None, rotulo: str | None, autor_id: UUID) -> UUID: ...

    async def actualizar_bajada(self, bajada_id: UUID, *, linea_trazo_id: UUID | None, rotulo: str | None) -> None: ...

    async def eliminar_bajada(self, bajada_id: UUID) -> None: ...

    async def bajada_del_punto(self, trazo_id: UUID) -> UUID | None:
        """La bajada que ya usa ese punto del plano (un punto sirve a una sola), o `None`."""
        ...

    async def bajada_de_la_linea(self, trazo_id: UUID) -> UUID | None:
        """La bajada que ya usa esa línea del plano (una línea sirve a una sola), o `None`."""
        ...
