"""Puerto de los cierres por frente (migración 0071)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

__all__ = ["RepositorioCierresDeFrente"]


class RepositorioCierresDeFrente(Protocol):
    async def frentes_de_obra(self, obra_id: UUID) -> list[dict[str, Any]]:
        """Los frentes (niveles) de la obra con su avance ponderado por costo y su
        último cierre (el vivo, o el rechazado más reciente)."""
        ...

    async def avance_del_frente(self, obra_id: UUID, nivel_id: UUID) -> Decimal | None:
        """El avance ponderado del frente, o `None` si la obra no tiene actividades
        en ese nivel."""
        ...

    async def obtener(self, cierre_id: UUID) -> dict[str, Any] | None: ...

    async def crear(
        self, *, obra_id: UUID, nivel_id: UUID, avance_pct: Decimal, solicitado_por: UUID
    ) -> UUID: ...

    async def actualizar(
        self,
        cierre_id: UUID,
        *,
        estatus: str,
        aprobado_por: UUID | None = None,
        validado_por: UUID | None = None,
        comentarios: str | None = None,
    ) -> None: ...

    async def frente_de_actividad_cerrado(self, actividad_id: UUID) -> dict[str, Any] | None:
        """El frente de la actividad si **ya está cerrado** (cierre validado), con su
        clave y descripción; `None` si sigue abierto o la actividad no tiene frente."""
        ...
