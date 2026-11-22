"""Puerto de las escaleras de las zonas de losa (migraciones 0145 y 0148): las escaleras forjadas que arrancan en cada zona, sus descansos propios y sus escalones de abanico."""

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

    # ── Descansos propios y escalones de abanico (0148) ──────────────────────────────────────────────────

    async def descansos_de_la_zona(self, zona_id: UUID) -> dict[UUID, list[dict[str, Any]]]:
        """Los descansos propios de las escaleras de la zona, por escalera y en orden de posición: `{id, escalera_id, posicion, giro_grados, largo_m, ancho_m,
        espesor_m, trazo_id, geojson}` (los numéricos como `Decimal`; `geojson` es el polígono del plano si hay `trazo_id`)."""
        ...

    async def abanicos_de_la_zona(self, zona_id: UUID) -> dict[UUID, list[dict[str, Any]]]:
        """Los grupos de abanico de las escaleras de la zona, por escalera y en orden de posición: `{id, escalera_id, posicion, escalones, ancho_interior_m,
        ancho_exterior_m, radio_huella_m}`."""
        ...

    async def reemplazar_descansos(self, escalera_id: UUID, filas: list[dict[str, Any]], autor_id: UUID | None) -> None:
        """Deja como únicos descansos de la escalera los de `filas` (`{posicion, giro_grados, largo_m, ancho_m, espesor_m, trazo_id}`)."""
        ...

    async def reemplazar_abanicos(self, escalera_id: UUID, filas: list[dict[str, Any]], autor_id: UUID | None) -> None:
        """Deja como únicos grupos de abanico de la escalera los de `filas` (`{posicion, escalones, ancho_interior_m, ancho_exterior_m, radio_huella_m}`)."""
        ...

    async def descanso_con_el_poligono(self, trazo_id: UUID) -> UUID | None:
        """La escalera (de cualquier zona) cuyo descanso ya usa ese polígono del plano para su área, o `None`."""
        ...

    async def trazo_es_de_losa(self, trazo_id: UUID) -> bool:
        """El polígono ya es una losa de una zona: no puede ser además un descanso (contaría su área dos veces)."""
        ...
