"""Eventos de dominio y su bus en proceso.

Spec §11.1 ("Eventos de dominio ... in-process o vía Arq") · §11.3 (los
workflows los disparan) · §12.11.

Por qué existe esto: el §11.1 exige que **la comunicación entre contextos sea
solo por fachadas y eventos**, y que ningún módulo toque las tablas ni el
estado interno de otro. Cerrar una actividad (contexto Cierres) tiene que
recalcular el CPM (contexto Programación); si `ValidarCierre` importara el
caso de uso de Programación, los dos contextos quedarían atados y dejarían de
ser candidatos a microservicio —que es justo lo que el §11.1 quiere evitar.

Con el bus, el que publica no sabe quién escucha: `ValidarCierre` publica
`ActividadCerrada` y quien ensambla (el borde, `adapters/api/casos_uso.py`)
decide que eso recalcula la ruta crítica. Cambiar el transporte a Arq (§11.1)
es sustituir la implementación de `PublicadorEventos`, sin tocar ni un caso de
uso.

Este módulo es de la capa de aplicación y no importa infraestructura: el bus
en proceso solo necesita `asyncio` y `logging` de la biblioteca estándar.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

__all__ = [
    "ActividadCerrada",
    "BusEnProceso",
    "CierreDeObraCompletado",
    "EstimacionValidada",
    "IncidenciaDetiene",
    "Manejador",
    "PartesCambiaronDeEstado",
    "PublicadorEventos",
    "ReprogramacionAplicada",
    "ReprogramacionObservada",
]

_log = logging.getLogger(__name__)

Manejador = Callable[[Any], Awaitable[None]]
"""Reacción a un evento. Async porque toda escritura del sistema lo es."""


@dataclass(frozen=True, slots=True)
class ActividadCerrada:
    """§11.1 · §11.3 C.4 — "Evento `ActividadCerrada` → recalcular **CPM** +
    habilitar para estimación".

    Lo publica `ValidarCierre`, que es el paso que deja la actividad
    ``concluida`` (§11.3 C.3): autorizar (Supervisor) todavía no la cierra
    —el diagrama del §11.3 C pone el evento después de `validada`.
    """

    obra_id: UUID
    actividad_id: UUID


@dataclass(frozen=True, slots=True)
class IncidenciaDetiene:
    """§11.1 · §11.3 F.5 — "Si `impacto=detiene` → evento bloquea actividades
    + recalcular CPM (desfase)".

    Lo publican `AbrirIncidencia` (con ``bloquear=True``) y
    `CerrarIncidencia`/`RechazarIncidencia` (con ``bloquear=False``): los tres
    pasos del workflow F que mueven el bloqueo. `bloquear` distingue las dos
    caras del mismo hecho —la incidencia que detiene la obra empieza o deja de
    detenerla— en vez de partirlo en dos eventos, porque el suscriptor reacciona
    igual en ambos casos: recalcular la ruta crítica de la obra.

    El bloqueo en sí lo escribe el caso de uso **dentro** de su unidad de
    trabajo, por el puerto `RepositorioActividades` —igual que `ValidarCierre`
    escribe `actividad.estatus` por ese mismo puerto (§11.1: por fachada, nunca
    tocando la tabla de otro contexto)—. Ahí no cabe un evento: `BusEnProceso`
    se traga los fallos del manejador a propósito, y una actividad que quedara
    sin bloquear sería un permiso abierto de más, no un dato derivado que se
    pueda recalcular después. Lo que sí viaja por el evento es el recálculo del
    CPM, que es derivado e idempotente (`RecalcularRutaCritica`), igual que en
    `ActividadCerrada`.
    """

    obra_id: UUID
    incidencia_id: UUID
    refs_bloqueadas: tuple[str, ...] = ()
    bloquear: bool = True


@dataclass(frozen=True, slots=True)
class CierreDeObraCompletado:
    """§11.3 D.3 — los cuatro roles firmaron y la obra queda entregada.

    **Lo que este evento NO hace es congelar la obra.** Eso lo escribe
    `Participar` dentro de su unidad de trabajo, por el mismo razonamiento que
    explica `IncidenciaDetiene`: el bus se traga los fallos de sus manejadores,
    y `entregada` es una frontera de permisos —no un dato derivado—. Una obra
    cerrada sin congelar admitiría capturas sobre un acta ya firmada.

    El evento existe para lo que sí es derivado y puede reintentarse: avisar,
    archivar, recalcular indicadores.
    """

    obra_id: UUID
    cierre_id: UUID


@dataclass(frozen=True, slots=True)
class EstimacionValidada:
    """§11.1 · §11.3 E.5 — notificar y bloquear el periodo."""

    obra_id: UUID
    estimacion_id: UUID


@dataclass(frozen=True, slots=True)
class ReprogramacionAplicada:
    """D-533 — control de obra realizó una reprogramación de lo asignado: la fecha
    ya se movió y «se notifica el cambio a los demás».

    La fecha se mueve y la reprogramación queda `aplicada` en la **misma** transacción
    de `AplicarReprogramacion` (lo uno sin lo otro dejaría lo asignado movido sin
    constancia, o constancia sin movimiento). Lo que viaja por el evento es solo el
    aviso, que se puede perder sin consecuencias.
    """

    obra_id: UUID
    reprogramacion_id: UUID
    actividad_id: UUID


@dataclass(frozen=True, slots=True)
class ReprogramacionObservada:
    """D-533 — control de obra dejó una observación al residente y al supervisor sobre
    una reprogramación. La observación ya está escrita; el evento solo avisa."""

    obra_id: UUID
    reprogramacion_id: UUID
    observacion_id: UUID


@dataclass(frozen=True, slots=True)
class PartesCambiaronDeEstado:
    """D-571 — una o varias partes de una obra pasaron de un paso al siguiente (o volvieron
    a uno anterior). El estado ya está escrito; el evento solo avisa en vivo."""

    obra_id: UUID
    accion: str
    claves: tuple[str, ...]


@runtime_checkable
class PublicadorEventos(Protocol):
    """Puerto de publicación. Lo declara la aplicación, lo implementa quien
    decida el transporte (in-process hoy, Arq mañana, §11.1)."""

    async def publicar(self, evento: object) -> None: ...


class BusEnProceso:
    """Bus síncrono dentro de la misma petición (§11.1 "in-process").

    **Los fallos de un manejador no se propagan.** El publicador ya
    commiteó lo suyo —`ValidarCierre` cierra la actividad y *después*
    publica—, así que un recálculo de CPM que truena no puede deshacer un
    cierre válido: eso es exactamente lo que pasaría si la excepción subiera
    hasta el router. Es la misma semántica que tendría el job de Arq, donde
    el fallo se reintenta aparte y nunca revierte al productor. Queda en el
    log con traza para que el operador actúe.
    """

    def __init__(self) -> None:
        self._manejadores: dict[type, list[Manejador]] = defaultdict(list)

    def suscribir(self, tipo: type, manejador: Manejador) -> None:
        self._manejadores[tipo].append(manejador)

    async def publicar(self, evento: object) -> None:
        for manejador in self._manejadores.get(type(evento), []):
            try:
                await manejador(evento)
            except Exception:  # ver el docstring de la clase: no se propaga
                _log.exception(
                    "El manejador de %s falló; el evento se descarta.",
                    type(evento).__name__,
                )
