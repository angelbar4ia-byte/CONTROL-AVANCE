"""Puerto de notificación por correo.

Spec §11.1 ("`EstimacionValidada` → **notificar (Resend)** + bloquear el
periodo") · §12.2 ("Notificaciones — **Resend** (correo) + Expo Push") ·
§12.11 (inversión de dependencias).

Se declara aquí, del lado de la aplicación, y se implementa en el borde
(`infrastructure/notificaciones/resend.py`): el caso de uso que notifica no
conoce a Resend ni a `httpx`, igual que no conoce a SQLAlchemy.

**`enviar` no levanta.** Devuelve si el correo salió o no, y esa firma es la
regla, no un descuido: la notificación es el paso 5 del workflow E, *después*
de que la estimación ya quedó validada y commiteada (§11.3 E.5). Un proveedor
caído —o un entorno sin API key— no puede deshacer una validación legítima. El
fallo queda en el log, que es donde el operador puede actuar; es la misma
semántica con la que `BusEnProceso` se traga los fallos de un manejador
(`application/eventos.py`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

__all__ = ["Correo", "EnviadorDeCorreo"]


@dataclass(frozen=True, slots=True)
class Correo:
    """Un mensaje listo para salir. Lo arma el caso de uso; el adaptador solo
    lo transporta."""

    para: tuple[str, ...]
    asunto: str
    html: str
    texto: str = ""
    etiquetas: dict[str, str] = field(default_factory=dict)
    """Metadatos para el proveedor (p. ej. `{"tipo": "estimacion_validada"}`).
    Nunca lleva importes ni datos personales: se usa para agrupar envíos."""


@runtime_checkable
class EnviadorDeCorreo(Protocol):
    async def enviar(self, correo: Correo) -> bool:
        """Manda el correo. `True` si el proveedor lo aceptó.

        No levanta: ver el encabezado del módulo.
        """
        ...
