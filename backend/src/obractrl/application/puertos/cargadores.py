"""Puertos de los cargadores de datos.

Spec §12.11 (inversión de dependencias: los puertos se declaran en la
aplicación y se implementan en el borde) · §9.2 (pipeline) · §10.8 (lote
reversible).

El caso de uso de cargas no sabe que el origen es un `.xlsx`: pide un
`LectorDeCarga` y recibe una `LecturaCarga` ya validada por el dominio. Si
mañana entra un CSV o una API, cambia el adaptador y no el caso de uso.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from obractrl.domain.cargadores.reporte import LecturaCarga

__all__ = ["LectorDeCarga", "RepositorioCargas"]


@runtime_checkable
class LectorDeCarga(Protocol):
    """Lee un archivo de un tipo del §10.6 y devuelve filas ya validadas."""

    def leer(self, contenido: bytes) -> LecturaCarga: ...


@runtime_checkable
class RepositorioCargas(Protocol):
    """Lotes de carga, su snapshot y la bandeja de pendientes (§9.4, §10.3, §10.8).

    `carga_datos`, `carga_snapshot` y `pendiente` comparten política RLS
    (`database/migrations/20260814000012`): alcance de organización **y**
    `app.es_config()` —o sea, Control de obra y Super intendente (§5.1)—.
    Ninguna implementación filtra `org_id` a mano.
    """

    async def crear(
        self,
        *,
        tipo: str,
        modo: str,
        archivo_nombre: str,
        archivo_hash: str,
        usuario_id: UUID | None,
    ) -> UUID:
        """Abre el lote en estatus `pendiente` (§9.4, workflow G.1)."""
        ...

    async def obtener(self, carga_id: UUID) -> dict | None: ...

    async def listar(self, *, tipo: str | None = None) -> list[dict]: ...

    async def buscar_aplicada_por_hash(self, *, tipo: str, archivo_hash: str) -> dict | None:
        """Carga **aplicada y no revertida** con ese hash (§10.8, §12.3).

        Es el corto circuito de la idempotencia: "si es idéntico, no crea
        versión".
        """
        ...

    async def siguiente_version(self, *, tipo: str) -> int:
        """Número de la versión que generaría la próxima carga de ese tipo (§10.8)."""
        ...

    async def finalizar(
        self,
        carga_id: UUID,
        *,
        estatus: str,
        resumen: dict,
        errores: list[dict],
        version_generada: int | None,
    ) -> None:
        """Cierra el lote con su resumen, su reporte por fila y su versión."""
        ...

    async def registrar_snapshots(self, carga_id: UUID, operaciones: list[dict]) -> None:
        """Guarda el antes/después de cada registro tocado, en orden (§10.8)."""
        ...

    async def snapshots(self, carga_id: UUID) -> list[dict]:
        """Operaciones del lote en orden **inverso**, listas para revertir (§10.8)."""
        ...

    async def revertir_operacion(self, operacion: dict) -> None:
        """Deshace una operación del snapshot dejando el dato como estaba (§10.8)."""
        ...

    async def marcar_revertida(self, carga_id: UUID, *, usuario_id: UUID | None) -> None: ...

    async def dependientes_de(self, carga_id: UUID) -> list[dict]:
        """Cargas aplicadas y no revertidas, más nuevas que esta, que
        tocaron (misma ``tabla`` + ``registro_id``) algo que esta carga
        también tocó (§10.8).

        Es la señal de "esto ya se recargó después": revertir esta carga
        sola dejaría una referencia rota (el caso real: el alta de un
        concepto se revierte mientras una carga posterior que recargó ese
        mismo concepto sigue aplicada). Vacío = se puede revertir sola.
        """
        ...

    async def eliminar(self, carga_id: UUID) -> None:
        """Borra el registro del lote (§10.8). `carga_snapshot` y
        `pendiente` se van solos por `on delete cascade` — el caso de uso
        (`EliminarCarga`) ya verificó que no hay nada que perder."""
        ...

    async def crear_pendientes(self, carga_id: UUID, pendientes: list[dict]) -> None:
        """Alta en la bandeja del §10.3. El sistema propone; el humano confirma."""
        ...

    async def listar_pendientes(
        self, *, carga_id: UUID | None = None, solo_abiertos: bool = True
    ) -> list[dict]: ...

    async def resolver_pendiente(
        self,
        pendiente_id: UUID,
        *,
        usuario_id: UUID | None,
        aprobado: bool,
        nota: str | None,
    ) -> dict | None:
        """Aprobar/rechazar un renglón de la bandeja (§10.3). `None` si ya
        no existe o ya estaba resuelto — resolver es de una sola vez."""
        ...

    async def mapeos(self, entidad: str) -> dict[str, str]:
        """Alias → clave canónica ya confirmados para esa entidad (§10.3).

        Lo que el humano resolvió en la bandeja re-alimenta la siguiente
        carga: por eso el cargador consulta esta tabla antes de declarar que
        un alias no cruza.
        """
        ...
