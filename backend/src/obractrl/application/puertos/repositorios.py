"""Puertos de persistencia.

Spec §12.11 (inversión de dependencias) · §11.1 (fachadas).

Los puertos se **declaran aquí** (lado de la aplicación) y se **implementan en
el borde** (`adapters/repos`). El dominio y los casos de uso solo conocen estas
interfaces; nunca a SQLModel ni a la sesión de base de datos.

Un módulo **nunca** toca las tablas ni el repositorio de otro: la comunicación
entre contextos es por fachada o por evento de dominio (§11.1).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable
from uuid import UUID

from obractrl.domain.programacion.cpm import NodoCPM
from obractrl.domain.shared.diccionario import TipoSemana

__all__ = [
    "RegistroNoEncontrado",
    "RepositorioActividades",
    "RepositorioCalendario",
    "RepositorioConfiguracion",
    "RepositorioEstimaciones",
    "RepositorioObras",
    "UnidadDeTrabajo",
]


class RegistroNoEncontrado(LookupError):
    """Una escritura scoped (`UPDATE ... WHERE id = ...`) no afectó ninguna fila.

    Cualquier implementación de un puerto que haga una escritura acotada bajo
    RLS debe levantar esto —o una subclase propia— cuando el `rowcount` es 0:
    la fila ya no existe, o salió del alcance del rol entre la lectura y la
    escritura (§12.4). Se declara aquí, en el puerto, y no en el adaptador
    concreto, para que los casos de uso puedan atraparla sin importar de
    `adapters/` —eso violaría la regla de dependencia que exige
    `import-linter` (§12.11): la aplicación no toca la infraestructura
    directamente, solo sus propias abstracciones.
    """


@runtime_checkable
class RepositorioActividades(Protocol):
    """Acceso a actividades. Siempre scoped por RLS (`org_id`) — §12.11."""

    async def obtener(self, actividad_id: UUID) -> dict | None: ...

    async def actualizar_avance(
        self,
        actividad_id: UUID,
        *,
        cant_programada: Decimal,
        cant_ejecutada: Decimal,
        avance_pct: Decimal,
        estatus: str,
    ) -> None: ...

    async def registrar_captura(
        self,
        actividad_id: UUID,
        *,
        fecha: date,
        delta_ejecutado: Decimal,
        usuario_id: UUID,
        evidencias: list[str],
    ) -> UUID: ...

    async def nodos_cpm_de_obra(self, obra_id: UUID) -> list[NodoCPM]:
        """Actividades de la obra como grafo para el motor CPM (§6)."""
        ...

    async def guardar_resultado_cpm(
        self,
        obra_id: UUID,
        resultados: dict[str, dict],
    ) -> None: ...

    async def marcar_bloqueadas(
        self, obra_id: UUID, refs: set[str], bloqueada: bool
    ) -> None: ...


@runtime_checkable
class RepositorioObras(Protocol):
    async def obtener(self, obra_id: UUID) -> dict | None: ...

    async def actualizar_avance(self, obra_id: UUID, avance_pct: Decimal) -> None: ...

    async def arbol_prototipo(self, prototipo_id: UUID) -> list[dict]:
        """Nodos WBS del prototipo, ordenados (§7.4). Alimenta el workflow A."""
        ...


@runtime_checkable
class RepositorioEstimaciones(Protocol):
    async def ultimo_consecutivo(self, semana: int, anio: int) -> int:
        """Último consecutivo de la semana.

        El contador es compartido entre ERP y no-ERP (§3.2), así que la
        implementación **no** debe filtrar por origen.
        """
        ...

    async def crear(self, datos: dict) -> UUID: ...

    async def actividades_estimables(
        self, obra_id: UUID, semana: int, anio: int
    ) -> list[dict]:
        """Actividades con avance validado de la semana (§11.3 E.2)."""
        ...


@runtime_checkable
class RepositorioCalendario(Protocol):
    """La tabla `calendario` es la única fuente de la base temporal (§3.1)."""

    async def semana_de(self, fecha: date, tipo: TipoSemana) -> tuple[int, int]: ...

    async def rango_de_semana(
        self, semana: int, anio: int, tipo: TipoSemana
    ) -> tuple[date, date]: ...

    async def semana_activa(self, tipo: TipoSemana) -> tuple[int, int]:
        """Ancla fijada por el admin (§3.1)."""
        ...


@runtime_checkable
class RepositorioConfiguracion(Protocol):
    """Configurables (§8.7).

    En runtime el sistema lee **primero** de aquí; el default canónico del
    código es solo el fallback. Nunca se clava un configurable como constante.
    """

    async def obtener(
        self, clave: str, *, ambito: str = "global", ambito_id: UUID | None = None
    ) -> object | None: ...

    async def decimal(
        self, clave: str, default: Decimal, *, ambito_id: UUID | None = None
    ) -> Decimal: ...


@runtime_checkable
class UnidadDeTrabajo(Protocol):
    """Transacción. El commit de una carga es atómico (§9.2)."""

    async def __aenter__(self) -> UnidadDeTrabajo: ...

    async def __aexit__(self, *exc_info: object) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
