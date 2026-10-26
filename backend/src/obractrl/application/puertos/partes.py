"""Puerto de las partes de una obra y de sus plantas (migración 0074)."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

__all__ = ["RepositorioPartes"]


class RepositorioPartes(Protocol):
    async def actividades_de_obra(self, obra_id: UUID) -> list[dict[str, Any]]:
        """Las actividades de la obra con su etapa, su nivel, su importe y su marca
        `parte_independiente`, ordenadas por nivel, etapa y concepto."""
        ...

    async def carga_por_etapa(self, obra_id: UUID) -> dict[str, Any]:
        """`{claves: {etapa_id: clave}, cargado: {clave de etapa: importe}}`: la clave de cada
        etapa de la obra y lo que la ingeniería ya aplicada (y no revertida) trajo de cada una."""
        ...

    async def actividad_a_modificar(self, actividad_id: UUID) -> dict[str, Any] | None:
        """`{obra_id, clave, descripcion, cant_base, cant_programada, cant_prototipo}` de una
        actividad que se ve, con la clave de su parte; `None` si no existe o no se ve."""
        ...

    async def aplicar_modificacion(
        self, actividad_id: UUID, *, tipo: str, cantidad: Any, cant_prototipo: Any
    ) -> None:
        """Escribe la cantidad base nueva, la marca del tipo y —solo la primera vez— lo que
        decía el prototipo; la cantidad programada no puede pasar de la nueva base."""
        ...

    async def crear_actividad_nueva(self, datos: dict[str, Any]) -> UUID:
        """Una actividad que nace con la modificación (cambio o adicional), sin prototipo."""
        ...

    async def registrar_modificacion(self, **datos: Any) -> None: ...

    async def modificaciones_de_obra(self, obra_id: UUID) -> list[dict[str, Any]]:
        """Bitácora de modificaciones de la obra, lo más reciente primero."""
        ...

    async def plantas_de_obra(self, obra_id: UUID) -> dict[str, Any] | None:
        """`{plantas, plantas_del_prototipo}` de la obra, o `None` si no se ve."""
        ...

    async def marcar_independiente(self, actividad_id: UUID, independiente: bool) -> bool:
        """Escribe la marca. `False` si la actividad no existe o no se ve."""
        ...

    async def fijar_plantas_de_obra(self, obra_id: UUID, plantas: int | None) -> bool: ...

    async def fijar_plantas_de_prototipo(self, prototipo_id: UUID, plantas: int | None) -> bool: ...

    async def parte_de_actividad(self, actividad_id: UUID) -> dict[str, Any] | None:
        """`{obra_id, clave}` de la parte a la que pertenece hoy la actividad."""
        ...

    async def estados_de_obra(self, obra_id: UUID) -> dict[str, str]:
        """`clave → estado` de las partes que ya tienen renglón. Sin renglón: cuantificando."""
        ...

    async def fijar_estado(
        self,
        obra_id: UUID,
        clave: str,
        estado: str,
        usuario_id: UUID | None,
        *,
        programa_por_revisar: bool | None = None,
    ) -> None:
        """Crea o actualiza el estado de una parte. `programa_por_revisar` solo se escribe si
        se pasa."""
        ...

    async def programas_por_revisar(self, obra_id: UUID) -> set[str]:
        """Las claves de las partes cuyo programa quedó por revisar (se devolvieron
        teniendo programa)."""
        ...

    async def registrar_transicion(
        self,
        *,
        obra_id: UUID,
        clave: str,
        accion: str,
        de: str,
        a: str,
        usuario_id: UUID,
        rol: str,
        nota: str | None,
    ) -> None:
        """Agrega a la bitácora. Solo se agrega."""
        ...

    async def bitacora_de_obra(self, obra_id: UUID, *, limite: int = 200) -> list[dict[str, Any]]:
        """Las últimas transiciones de la obra, las más recientes primero."""
        ...

    async def candado_de_obra(self, obra_id: UUID) -> bool | None:
        """El candado de asignar de la obra, o `None` si no se ve."""
        ...

    async def fijar_candado(self, obra_id: UUID, activo: bool) -> bool: ...

    async def validaciones_con_anotacion(self, obra_id: UUID) -> set[str]:
        """Las claves de las partes cuya **última validación** dejó una anotación."""
        ...
