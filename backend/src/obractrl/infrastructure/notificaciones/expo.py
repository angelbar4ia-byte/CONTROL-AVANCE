"""Envío de notificaciones por Expo Push.

Spec §12.2 ("**Notificaciones** — Resend (correo) + **Expo Push**") · §11.3
E.5 · §12.4 (seguridad) · §12.8 (entornos) · migración 0028.

Implementa `application.puertos.notificaciones.EnviadorDePush`. Se habla con
la API por HTTP con `httpx` —ya es dependencia— en vez de sumar el SDK de
Expo: es un `POST /--/api/v2/push/send` con una lista de mensajes.

**No levanta nunca**, igual que `ClienteResend`: `enviar` devuelve cuántos
dispositivos aceptaron y registra el motivo de lo que falló. La razón es la
misma —la notificación viaja detrás de un hecho ya commiteado (§11.3 E.5)— y
aquí es todavía más clara: un teléfono sin batería no puede invalidar una
estimación.

## Lo que sí hace con los errores, y por qué importa

Expo responde 200 con un *ticket* por mensaje, y un ticket puede venir con
`status: "error"`. El que interesa es **`DeviceNotRegistered`**: significa que
la app se desinstaló y ese token está muerto para siempre. Se registra para
que el llamador lo pueda desactivar (`dispositivo_push.activo = false`).

Sin eso, la tabla acumularía tokens muertos que se reintentan en cada aviso:
Expo empieza a limitar por volumen, y el envío de todos —incluidos los
buenos— se degrada por culpa de teléfonos que ya no existen.

## Lo que no viaja

El payload no lleva importes, nombres de cliente ni descripciones de obra
—solo un título, una línea y los ids de a dónde ir—. Una notificación push
aparece en la pantalla de bloqueo, o sea a la vista de cualquiera que tome el
teléfono, y además pasa por los servidores de Expo y de Google (§12.4).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from obractrl.application.puertos.notificaciones import Aviso
from obractrl.infrastructure.config import Config, obtener_config

__all__ = ["ClienteExpoPush", "ResultadoDeEnvio"]

_log = logging.getLogger(__name__)

URL_ENVIO = "https://exp.host/--/api/v2/push/send"

TIMEOUT_SEGUNDOS = 10.0
"""Corto, como en Resend: corre detrás de un evento de dominio pero comparte
el worker de Render (§12.8) y no puede quedarse colgado."""

LOTE = 100
"""Tope de mensajes por petición que documenta Expo. Los envíos reales son de
tres o cuatro tokens; el lote existe para que un aviso a toda una obra no
falle entero por pasarse."""


@dataclass(frozen=True, slots=True)
class ResultadoDeEnvio:
    """Qué pasó con un envío, en términos accionables."""

    aceptados: int
    muertos: tuple[str, ...]
    """Tokens con `DeviceNotRegistered`: la app se desinstaló. Desactivarlos."""


class ClienteExpoPush:
    """Adaptador de Expo Push (§12.2)."""

    def __init__(
        self, cfg: Config | None = None, cliente: httpx.AsyncClient | None = None
    ) -> None:
        self._cfg = cfg or obtener_config()
        # Inyectable para probar contra un transporte falso, igual que
        # `ClienteResend` y `firmar_subida`.
        self._cliente = cliente

    async def enviar(self, aviso: Aviso) -> int:
        """Manda el aviso a todos sus tokens. Devuelve cuántos lo aceptaron."""
        resultado = await self.enviar_detallado(aviso)
        return resultado.aceptados

    async def enviar_detallado(self, aviso: Aviso) -> ResultadoDeEnvio:
        """Como `enviar`, pero además dice qué tokens están muertos.

        Existe aparte porque el puerto `EnviadorDePush` promete un entero —es
        lo que el caso de uso necesita— y quien administra la tabla de
        dispositivos necesita más. Meter los tokens muertos en el puerto
        obligaría a todo caso de uso que notifica a saber de `dispositivo_push`.
        """
        if not aviso.tokens:
            _log.warning("No se envió '%s': sin dispositivos registrados.", aviso.titulo)
            return ResultadoDeEnvio(aceptados=0, muertos=())

        try:
            return await self._postear(aviso)
        except Exception as exc:  # noqa: BLE001 — ver el encabezado del módulo
            _log.exception(
                "Falló el envío push de '%s' por Expo (%s).",
                aviso.titulo,
                type(exc).__name__,
            )
            return ResultadoDeEnvio(aceptados=0, muertos=())

    async def _postear(self, aviso: Aviso) -> ResultadoDeEnvio:
        mensajes = [
            {
                "to": token,
                "title": aviso.titulo,
                "body": aviso.cuerpo,
                "data": aviso.datos,
                # `default` y no `high`: un aviso de estimación validada no
                # justifica despertar el teléfono ni saltarse el ahorro de
                # batería. La prioridad alta se reserva para lo que detiene
                # una obra, si algún día se manda desde aquí.
                "priority": "default",
                "channelId": "default",
            }
            for token in aviso.tokens[:LOTE]
        ]

        cabeceras = {"Content-Type": "application/json"}
        if self._cfg.expo_access_token:
            # Solo si el proyecto activó "enhanced security" en Expo. Nunca se
            # registra: viaja en la cabecera y en ningún log (§12.4).
            cabeceras["Authorization"] = f"Bearer {self._cfg.expo_access_token}"

        if self._cliente is not None:
            respuesta = await self._cliente.post(URL_ENVIO, json=mensajes, headers=cabeceras)
        else:
            async with httpx.AsyncClient(timeout=TIMEOUT_SEGUNDOS) as cliente:
                respuesta = await cliente.post(URL_ENVIO, json=mensajes, headers=cabeceras)

        if respuesta.status_code >= 400:
            # Sin el cuerpo completo: puede traer de vuelta los tokens.
            _log.warning(
                "Expo rechazó el envío de '%s' con HTTP %s.",
                aviso.titulo,
                respuesta.status_code,
            )
            return ResultadoDeEnvio(aceptados=0, muertos=())

        return _leer_tickets(respuesta.json(), aviso.tokens[:LOTE], aviso.titulo)


def _leer_tickets(
    cuerpo: object, tokens: tuple[str, ...], asunto: str
) -> ResultadoDeEnvio:
    """Traduce la respuesta de Expo a aceptados + tokens muertos.

    Los tickets vienen **en el mismo orden** que los mensajes enviados, que es
    lo que permite asociar un error con su token: la respuesta no repite el
    token. Si vinieran menos tickets que mensajes —no debería—, se cuentan los
    que hay en vez de indexar fuera de rango.
    """
    if not isinstance(cuerpo, dict):
        _log.warning("Respuesta inesperada de Expo al enviar '%s'.", asunto)
        return ResultadoDeEnvio(aceptados=0, muertos=())

    tickets = cuerpo.get("data")
    if not isinstance(tickets, list):
        _log.warning("Respuesta de Expo sin tickets al enviar '%s'.", asunto)
        return ResultadoDeEnvio(aceptados=0, muertos=())

    aceptados = 0
    muertos: list[str] = []

    for indice, ticket in enumerate(tickets):
        if not isinstance(ticket, dict):
            continue
        if ticket.get("status") == "ok":
            aceptados += 1
            continue

        detalles = ticket.get("details")
        codigo = detalles.get("error") if isinstance(detalles, dict) else None
        if codigo == "DeviceNotRegistered" and indice < len(tokens):
            muertos.append(tokens[indice])
        else:
            _log.warning(
                "Expo rechazó un mensaje de '%s' (%s).", asunto, codigo or "sin código"
            )

    return ResultadoDeEnvio(aceptados=aceptados, muertos=tuple(muertos))
