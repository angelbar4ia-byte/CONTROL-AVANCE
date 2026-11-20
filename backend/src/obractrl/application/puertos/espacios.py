"""Puerto de los espacios de una obra (migración 0143): el cuarto o área donde se asignan zonas de losa, muros y elementos."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from uuid import UUID

__all__ = ["RepositorioEspacios"]


@runtime_checkable
class RepositorioEspacios(Protocol):
    async def obra_visible(self, obra_id: UUID) -> bool:
        """La obra existe y está en el alcance de quien pregunta (RLS)."""
        ...

    async def listar(self, obra_id: UUID) -> list[dict[str, Any]]:
        """Los espacios de la obra con lo que tiene asignado: `{id, obra_id, nombre, tipo, nivel_id, area_m2, orden, muros, losas, elementos, nodos}`."""
        ...

    async def uno(self, espacio_id: UUID) -> dict[str, Any] | None: ...

    async def crear(self, *, obra_id: UUID, datos: dict[str, Any], autor_id: UUID) -> UUID: ...

    async def actualizar(self, espacio_id: UUID, datos: dict[str, Any]) -> None: ...

    async def eliminar(self, espacio_id: UUID) -> None: ...

    async def nodos_de_la_obra(self, obra_id: UUID, nodo_ids: list[UUID]) -> list[UUID]:
        """De esos nodos, los que son del árbol del prototipo de la obra."""
        ...

    async def fijar_nodos(self, *, obra_id: UUID, espacio_id: UUID, nodo_ids: list[UUID]) -> None:
        """Deja al espacio con exactamente esas ramas del árbol (un nodo pertenece a lo más a un espacio: pasa de uno a otro)."""
        ...

    async def trazo(self, trazo_id: UUID) -> dict[str, Any] | None:
        """`{id, obra_id, tipo, hueco_de, espacio_id, espacio_comparte_id, espacio_reparto_pct}`; `None` si no existe o no es visible."""
        ...

    async def fijar_espacio_de_trazo(
        self, trazo_id: UUID, espacio_id: UUID | None, comparte_id: UUID | None, reparto_pct: Any
    ) -> None: ...
