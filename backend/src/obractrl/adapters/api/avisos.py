"""De evento de dominio a aviso en vivo.

Spec §11.1 (eventos de dominio) · §11.2 ("Tiempo real … Torre, bandejas y
notificaciones") · §12.11 (el borde ensambla).

Vive en `adapters/api/` y no en el dominio ni en la aplicación por la misma
razón que `casos_uso.py`: es **cableado**. `ValidarCierre` publica
`ActividadCerrada` sin saber que alguien la va a pintar en una Torre; que eso
llegue a un navegador es una decisión del borde, y cambiarla no debería tocar
un caso de uso (§11.1).

## Por qué una tabla y no un `__dict__`

Serializar el evento entero sería más corto y estaría mal. Un evento de
dominio es interno: puede ganar campos —un monto, un motivo— sin que nadie
piense en que eso sale por un canal en vivo hacia todos los conectados de la
organización. La tabla obliga a nombrar cada campo que viaja, así que agregar
uno es una decisión, no un descuido (§12.4).

Un evento que no esté aquí simplemente no se anuncia. Es el default correcto:
callar de más nunca filtró nada.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from obractrl.application.eventos import (
    ActividadCerrada,
    BusEnProceso,
    CierreDeObraCompletado,
    EstimacionValidada,
    IncidenciaDetiene,
    ReprogramacionAplicada,
)
from obractrl.application.puertos.tiempo_real import Aviso, PublicadorEnVivo
from obractrl.infrastructure.db.sesion import ContextoSesion

__all__ = ["TRADUCCIONES", "aviso_de", "suscribir_avisos"]


def _actividad_cerrada(evento: ActividadCerrada) -> tuple[str, dict[str, str]]:
    return "actividad_cerrada", {
        "obra_id": str(evento.obra_id),
        "actividad_id": str(evento.actividad_id),
    }


def _incidencia_detiene(evento: IncidenciaDetiene) -> tuple[str, dict[str, str]]:
    return "incidencia_detiene", {
        "obra_id": str(evento.obra_id),
        "incidencia_id": str(evento.incidencia_id),
        # Un booleano como texto: el canal transporta JSON con valores de
        # cadena para que el cliente no tenga que distinguir tipos por campo.
        # Lo que importa aquí es el sentido —se bloqueó o se liberó—, porque
        # decide si la Torre pinta la obra en rojo o la limpia.
        "bloquear": "si" if evento.bloquear else "no",
    }


def _estimacion_validada(evento: EstimacionValidada) -> tuple[str, dict[str, str]]:
    # Sin monto: el aviso llega a todos los conectados de la organización y el
    # importe lo pide quien tenga permiso, por su endpoint (§12.4).
    return "estimacion_validada", {
        "obra_id": str(evento.obra_id),
        "estimacion_id": str(evento.estimacion_id),
    }


def _cierre_de_obra(evento: CierreDeObraCompletado) -> tuple[str, dict[str, str]]:
    return "cierre_de_obra_completado", {
        "obra_id": str(evento.obra_id),
        "cierre_id": str(evento.cierre_id),
    }


def _reprogramacion_aplicada(evento: ReprogramacionAplicada) -> tuple[str, dict[str, str]]:
    # Sin fechas ni motivo: el aviso llega a todos los conectados de la organización y
    # el detalle lo pide quien tenga permiso, por su endpoint (§12.4).
    return "reprogramacion_aplicada", {
        "obra_id": str(evento.obra_id),
        "reprogramacion_id": str(evento.reprogramacion_id),
        "actividad_id": str(evento.actividad_id),
    }


TRADUCCIONES: dict[type, Callable[[Any], tuple[str, dict[str, str]]]] = {
    ActividadCerrada: _actividad_cerrada,
    IncidenciaDetiene: _incidencia_detiene,
    EstimacionValidada: _estimacion_validada,
    CierreDeObraCompletado: _cierre_de_obra,
    ReprogramacionAplicada: _reprogramacion_aplicada,
}
"""Los eventos del §11.1 que hoy existen (y el de D-533). Ver el encabezado sobre por
qué esto es una tabla explícita."""


def aviso_de(evento: object, *, org_id: UUID) -> Aviso | None:
    """Traduce un evento de dominio. `None` si ese evento no se anuncia."""
    traducir = TRADUCCIONES.get(type(evento))
    if traducir is None:
        return None
    tipo, datos = traducir(evento)
    return Aviso(org_id=org_id, tipo=tipo, datos=datos)


def suscribir_avisos(
    bus: BusEnProceso, *, ctx: ContextoSesion, canal: PublicadorEnVivo
) -> BusEnProceso:
    """Engancha el canal en vivo a un bus ya armado. Devuelve el mismo bus.

    Se llama al final de cada `_bus_de_*` de `casos_uso.py`, después de los
    manejadores de negocio. El orden importa poco —`BusEnProceso` los recorre
    en secuencia y ninguno depende del otro— pero anunciar al final significa
    que el aviso sale cuando el efecto ya ocurrió, que es lo que el cliente
    espera al recargar.

    **El `org_id` sale del contexto de la sesión**, no del evento: los eventos
    de dominio no lo llevan porque dentro de una petición es implícito
    (§12.4). Aquí se necesita explícito, porque el canal reparte por
    organización.
    """

    async def _anunciar(evento: object) -> None:
        aviso = aviso_de(evento, org_id=ctx.org_id)
        if aviso is not None:
            await canal.publicar(aviso)

    for tipo in TRADUCCIONES:
        bus.suscribir(tipo, _anunciar)
    return bus
