"""Puerto de publicación en vivo.

Spec §11.2 ("**Tiempo real** — `WS /ws` (o `GET /events` SSE) — Torre,
bandejas y notificaciones (todos, por alcance)") · §11.1 (eventos de dominio)
· §12.11 (inversión de dependencias).

Se declara aquí y se implementa en el borde
(`infrastructure/tiempo_real/canal.py`): el caso de uso que cierra una
actividad no sabe que existe SSE, ni Redis, igual que no sabe que existe
SQLAlchemy.

## Qué es un aviso y qué no

Un aviso dice **qué cambió y de qué obra**, nunca **qué quedó**. No lleva el
monto de la estimación ni el texto de la incidencia: lleva el tipo del hecho y
los ids. El cliente que lo recibe vuelve a consultar lo que le interesa por su
endpoint de siempre, con su propio token y su propio RLS.

Esa decisión es de seguridad, no de tamaño. Un canal en vivo es el lugar más
fácil para filtrar datos sin querer: basta un manejador que serialice el
agregado completo para que quien esté suscrito reciba campos que su rol no
podría pedir por HTTP. Mandando ids, la frontera sigue siendo la de siempre
(§12.4) y el canal no es una segunda API sin permisos.

## No levanta

Igual que `EnviadorDeCorreo.enviar`: el aviso viaja **detrás** de un hecho ya
commiteado (§11.1). Un canal caído no puede deshacer un cierre. El fallo queda
en el log.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

__all__ = ["Aviso", "PublicadorEnVivo"]


@dataclass(frozen=True, slots=True)
class Aviso:
    """Un hecho que acaba de pasar, listo para viajar por el canal."""

    org_id: UUID
    """A qué organización pertenece. Es lo que acota el canal: nadie recibe
    avisos de otra (§12.4)."""

    tipo: str
    """Nombre del hecho, en el vocabulario del §11.1: `actividad_cerrada`,
    `incidencia_detiene`, `estimacion_validada`, `cierre_de_obra_completado`.
    El cliente decide qué recargar a partir de esto."""

    datos: dict[str, str] = field(default_factory=dict)
    """Ids y nada más. Ver el encabezado del módulo."""

    def como_json(self) -> dict[str, Any]:
        return {"tipo": self.tipo, "datos": self.datos}


@runtime_checkable
class PublicadorEnVivo(Protocol):
    async def publicar(self, aviso: Aviso) -> None:
        """Manda el aviso a quien esté escuchando esa organización.

        No levanta: ver el encabezado del módulo.
        """
        ...
