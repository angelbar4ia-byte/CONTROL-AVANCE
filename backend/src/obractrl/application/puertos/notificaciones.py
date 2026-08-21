"""Puertos de notificación: correo y push.

Spec §11.1 ("`EstimacionValidada` → **notificar (Resend)** + bloquear el
periodo") · §12.2 ("Notificaciones — **Resend** (correo) + Expo Push") ·
§12.11 (inversión de dependencias).

Se declaran aquí, del lado de la aplicación, y se implementan en el borde
(`infrastructure/notificaciones/resend.py` y `.../expo.py`): el caso de uso
que notifica no conoce a Resend ni a Expo ni a `httpx`, igual que no conoce a
SQLAlchemy.

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

__all__ = ["Aviso", "Correo", "EnviadorDeCorreo", "EnviadorDePush"]


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


@dataclass(frozen=True, slots=True)
class Aviso:
    """Una notificación push lista para salir (§12.2).

    Corta por definición: en la pantalla de bloqueo de un teléfono caben dos
    líneas. `datos` viaja para que la app sepa **a dónde llevar** al usuario
    cuando toca la notificación —una obra, una incidencia— y por eso lleva
    ids, no contenido: la app ya tiene los datos en su réplica local (§12.5) y
    el payload de push no es un lugar donde poner información de obra.
    """

    tokens: tuple[str, ...]
    titulo: str
    cuerpo: str
    datos: dict[str, str] = field(default_factory=dict)


@runtime_checkable
class EnviadorDePush(Protocol):
    async def enviar(self, aviso: Aviso) -> int:
        """Manda el aviso. Devuelve cuántos dispositivos lo aceptaron.

        No levanta, por la misma razón que `EnviadorDeCorreo.enviar`: la
        notificación ocurre **después** de que el hecho ya está commiteado
        (§11.3 E.5). Un proveedor caído no puede deshacerlo.

        Devuelve un entero y no un booleano porque un aviso va a varios
        dispositivos y el resultado normal es parcial: tres teléfonos, uno con
        la app desinstalada. Un `False` por ese uno haría creer que nadie se
        enteró.
        """
        ...
