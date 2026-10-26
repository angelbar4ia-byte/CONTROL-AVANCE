"""Puerto de las reprogramaciones de lo contratado (migración 0072)."""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol
from uuid import UUID

__all__ = ["RepositorioReprogramaciones"]


class RepositorioReprogramaciones(Protocol):
    async def obtener(self, reprogramacion_id: UUID) -> dict[str, Any] | None:
        """La reprogramación con su obra y la actividad que mueve, o `None` si no
        existe o salió del alcance (RLS)."""
        ...

    async def viva_de(self, actividad_id: UUID) -> dict[str, Any] | None:
        """La reprogramación que sigue en la cadena (propuesta, revisada o validada)
        de esa actividad: solo cabe una a la vez."""
        ...

    async def de_obra(self, obra_id: UUID) -> list[dict[str, Any]]:
        """Las reprogramaciones de la obra, las más recientes primero, con la
        actividad, el concepto y los nombres de quien intervino en la cadena."""
        ...

    async def crear(
        self,
        *,
        obra_id: UUID,
        actividad_id: UUID,
        estatus: str,
        fecha_inicio: date | None,
        fecha_termino: date | None,
        fecha_inicio_anterior: date | None,
        fecha_termino_anterior: date | None,
        motivo: str,
        propuesta_por: UUID,
        propuesta_rol: str,
    ) -> UUID: ...

    async def actualizar(
        self,
        reprogramacion_id: UUID,
        *,
        estatus: str,
        revisada_por: UUID | None = None,
        validada_por: UUID | None = None,
        aplicada_por: UUID | None = None,
        rechazada_por: UUID | None = None,
        motivo_rechazo: str | None = None,
    ) -> None:
        """Avanza el estatus y sella a quien lo hizo y cuándo. Lo que no se pasa no
        se toca."""
        ...
