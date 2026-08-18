"""Envío de correo por Resend.

Spec §12.2 ("**Notificaciones** — **Resend** (correo) + Expo Push") · §11.1
("`EstimacionValidada` → notificar (Resend) …") · §11.3 E.5 · §12.4
(seguridad) · §12.8 (entornos).

Implementa `application.puertos.notificaciones.EnviadorDeCorreo`. Se habla con
la API por HTTP con `httpx` —que ya es dependencia del proyecto— en vez de
sumar el SDK de Resend: son dos campos y un `POST /emails`, y el SDK oficial
es síncrono.

**No levanta nunca.** `enviar` devuelve `True`/`False` y registra el motivo.
La razón está en el puerto: la notificación es el paso 5 del workflow E, ya
con la estimación validada y commiteada; un proveedor caído no puede deshacer
eso. Falta de API key incluida — un entorno de desarrollo sin Resend no debe
hacer fallar la validación de una estimación (§12.8).

**La API key no sale nunca.** Ni en la respuesta, ni en el log, ni en el
mensaje de un error: solo viaja en la cabecera `Authorization` de la petición
saliente. Lo que se registra es el código HTTP y el `id` que devuelve Resend
—el rastro que el operador necesita— y jamás el cuerpo completo de la
petición, que además lleva los correos de los destinatarios.
"""

from __future__ import annotations

import logging

import httpx

from obractrl.application.puertos.notificaciones import Correo
from obractrl.infrastructure.config import Config, obtener_config

__all__ = ["ClienteResend", "CorreoNoConfigurado"]

_log = logging.getLogger(__name__)

URL_EMAILS = "https://api.resend.com/emails"
TIMEOUT_SEGUNDOS = 10.0
"""Corto: esto corre detrás de un evento de dominio, no de una petición del
usuario, pero comparte el worker de Render (§12.8) y no puede quedarse
colgado."""


class CorreoNoConfigurado(RuntimeError):
    """Falta `RESEND_API_KEY` o el remitente en este entorno (§12.8).

    Existe para que la causa sea nombrable en el log y en una prueba. **No
    se propaga al borde**: `ClienteResend.enviar` la atrapa y devuelve
    `False`, porque una notificación no puede tumbar la validación de una
    estimación (§11.3 E.5).
    """


class ClienteResend:
    """Adaptador de Resend (§12.2)."""

    def __init__(
        self, cfg: Config | None = None, cliente: httpx.AsyncClient | None = None
    ) -> None:
        self._cfg = cfg or obtener_config()
        # El cliente se puede inyectar para probar contra un transporte
        # falso, igual que `Config` se inyecta en `firmar_subida`.
        self._cliente = cliente

    def _credenciales(self) -> tuple[str, str]:
        faltantes = [
            nombre
            for nombre, valor in (
                ("RESEND_API_KEY", self._cfg.resend_api_key),
                ("RESEND_REMITENTE", self._cfg.resend_remitente),
            )
            if not valor
        ]
        if faltantes:
            # Se nombran las variables que faltan, nunca su valor: quien opera
            # el despliegue necesita saber cuál poner, y el nombre no es
            # secreto (mismo criterio que `firmar_subida` con R2).
            raise CorreoNoConfigurado(
                "El envío de correo no está configurado en este entorno; "
                f"faltan: {', '.join(faltantes)} (§12.8)."
            )
        return self._cfg.resend_api_key, self._cfg.resend_remitente

    async def enviar(self, correo: Correo) -> bool:
        """Manda el correo. `True` si Resend lo aceptó. No levanta."""
        try:
            api_key, remitente = self._credenciales()
        except CorreoNoConfigurado as exc:
            _log.warning("No se envió '%s': %s", correo.asunto, exc)
            return False

        if not correo.para:
            _log.warning("No se envió '%s': sin destinatarios.", correo.asunto)
            return False

        cuerpo: dict[str, object] = {
            "from": remitente,
            "to": list(correo.para),
            "subject": correo.asunto,
            "html": correo.html,
        }
        if correo.texto:
            cuerpo["text"] = correo.texto
        if correo.etiquetas:
            cuerpo["tags"] = [
                {"name": nombre, "value": valor}
                for nombre, valor in correo.etiquetas.items()
            ]

        try:
            return await self._postear(api_key, cuerpo, asunto=correo.asunto)
        except Exception as exc:  # noqa: BLE001 — ver el encabezado del módulo
            _log.exception(
                "Falló el envío de '%s' por Resend (%s).",
                correo.asunto,
                type(exc).__name__,
            )
            return False

    async def _postear(
        self, api_key: str, cuerpo: dict[str, object], *, asunto: str
    ) -> bool:
        cabeceras = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if self._cliente is not None:
            respuesta = await self._cliente.post(
                URL_EMAILS, json=cuerpo, headers=cabeceras
            )
        else:
            async with httpx.AsyncClient(timeout=TIMEOUT_SEGUNDOS) as cliente:
                respuesta = await cliente.post(
                    URL_EMAILS, json=cuerpo, headers=cabeceras
                )

        if respuesta.status_code >= 400:
            # El cuerpo de error de Resend describe la petición rechazada
            # (destinatario inválido, dominio no verificado); no contiene la
            # llave —viaja en la cabecera— pero sí puede traer correos, así
            # que solo se registra el código.
            _log.error(
                "Resend rechazó el envío de '%s': HTTP %s.",
                asunto,
                respuesta.status_code,
            )
            return False

        _log.info(
            "Correo '%s' aceptado por Resend (id=%s).",
            asunto,
            _id_de(respuesta),
        )
        return True


def _id_de(respuesta: httpx.Response) -> str:
    """`id` del envío, para rastrearlo en el panel de Resend."""
    try:
        datos = respuesta.json()
    except ValueError:  # pragma: no cover - Resend responde JSON
        return "(sin id)"
    return str(datos.get("id", "(sin id)")) if isinstance(datos, dict) else "(sin id)"
