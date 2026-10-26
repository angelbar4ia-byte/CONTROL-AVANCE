"""Caso de uso: avisar que se reprogramó algo contratado (D-533).

«Al aplicarse se notifica el cambio a los demás.» Lo dispara el evento
`ReprogramacionAplicada`, que `AplicarReprogramacion` publica **después** de commitear,
así que todo aquí falla hacia adentro (mismo molde y mismas razones que
`notificar_estimacion`): un aviso perdido no deshace una fecha ya movida.

**Quiénes son «los demás».** El cerebro no los nombra. Se avisa a quien intervino en
la cadena (propone, revisa, valida, realiza) y al residente de la obra, que es quien
vive con la fecha. Si se quiere avisar también al contratista, es una decisión de
producto pendiente: hoy un contratista no es un usuario del sistema.

El correo lleva las fechas; el push no (aparece en la pantalla de bloqueo y pasa por
servidores de terceros, §12.4): dice qué actividad y a dónde ir.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any
from uuid import UUID

from obractrl.application.eventos import ReprogramacionAplicada
from obractrl.application.puertos.notificaciones import (
    Aviso,
    Correo,
    EnviadorDeCorreo,
    EnviadorDePush,
)
from obractrl.application.puertos.repositorios import (
    RepositorioObras,
    RepositorioUsuarios,
)
from obractrl.application.puertos.reprogramacion import RepositorioReprogramaciones

__all__ = ["NotificarReprogramacionAplicada"]

_log = logging.getLogger(__name__)


class NotificarReprogramacionAplicada:
    def __init__(
        self,
        *,
        reprogramaciones: RepositorioReprogramaciones,
        obras: RepositorioObras,
        usuarios: RepositorioUsuarios,
        correo: EnviadorDeCorreo,
        push: EnviadorDePush | None = None,
    ) -> None:
        self._reprogramaciones = reprogramaciones
        self._obras = obras
        self._usuarios = usuarios
        self._correo = correo
        self._push = push

    async def ejecutar(self, evento: ReprogramacionAplicada) -> bool:
        reprogramacion = await self._reprogramaciones.obtener(evento.reprogramacion_id)
        if reprogramacion is None:
            _log.warning(
                "No se notificó la reprogramación %s: ya no está en el alcance.",
                evento.reprogramacion_id,
            )
            return False

        obra = await self._obras.obtener(evento.obra_id) or {}
        destinatarios = await self._usuarios.correos_de(
            _ids_unicos(
                reprogramacion.get("propuesta_por"),
                reprogramacion.get("revisada_por"),
                reprogramacion.get("validada_por"),
                reprogramacion.get("aplicada_por"),
                obra.get("residente_id"),
            )
        )
        correos = tuple(
            str(fila["email"]).strip()
            for fila in destinatarios
            if str(fila.get("email") or "").strip()
        )
        ids = [fila["id"] for fila in destinatarios]
        tokens = tuple(await self._usuarios.tokens_push_de(ids)) if self._push else ()

        if not correos and not tokens:
            _log.warning(
                "La reprogramación %s se aplicó pero no hay a quién notificarle: nadie "
                "tiene correo ni dispositivo registrado.",
                evento.reprogramacion_id,
            )
            return False

        salio_correo = bool(correos) and await self._correo.enviar(
            _armar_correo(reprogramacion=reprogramacion, obra=obra, para=correos)
        )
        salio_push = False
        if self._push is not None and tokens:
            salio_push = (
                await self._push.enviar(
                    _armar_aviso(reprogramacion=reprogramacion, obra=obra, tokens=tokens)
                )
                > 0
            )
        return salio_correo or salio_push


def _ids_unicos(*valores: object) -> list[UUID]:
    vistos: dict[UUID, None] = {}
    for valor in valores:
        if valor is None:
            continue
        vistos.setdefault(valor if isinstance(valor, UUID) else UUID(str(valor)), None)
    return list(vistos)


def _fecha(valor: date | None) -> str:
    return valor.isoformat() if valor is not None else "sin fecha"


def _etiqueta(reprogramacion: dict[str, Any]) -> str:
    clave = reprogramacion.get("concepto_clave")
    descripcion = reprogramacion.get("actividad") or "(actividad sin descripción)"
    return f"{clave} {descripcion}" if clave else str(descripcion)


def _armar_correo(*, reprogramacion: dict[str, Any], obra: dict, para: tuple[str, ...]) -> Correo:
    clave = obra.get("clave") or "(obra sin clave)"
    actividad = _etiqueta(reprogramacion)
    inicio_antes = _fecha(reprogramacion.get("fecha_inicio_anterior"))
    termino_antes = _fecha(reprogramacion.get("fecha_termino_anterior"))
    inicio = _fecha(reprogramacion.get("fecha_inicio") or reprogramacion.get("fecha_inicio_anterior"))
    termino = _fecha(
        reprogramacion.get("fecha_termino") or reprogramacion.get("fecha_termino_anterior")
    )
    motivo = reprogramacion.get("motivo") or ""

    texto = (
        f"Se reprogramó lo contratado en la obra {clave}: {actividad}.\n"
        f"Inicio: {inicio_antes} → {inicio} · Término: {termino_antes} → {termino}.\n"
        f"Motivo: {motivo}"
    )
    html = (
        f"<h2>Reprogramación aplicada · {clave}</h2>"
        f"<p><strong>{actividad}</strong>.</p>"
        f"<p>Inicio: {inicio_antes} → <strong>{inicio}</strong><br>"
        f"Término: {termino_antes} → <strong>{termino}</strong></p>"
        f"<p>Motivo: {motivo}</p>"
    )
    return Correo(
        para=para,
        asunto=f"Reprogramación aplicada · {clave} · {actividad}",
        html=html,
        texto=texto,
        etiquetas={"tipo": "reprogramacion_aplicada"},
    )


def _armar_aviso(*, reprogramacion: dict[str, Any], obra: dict, tokens: tuple[str, ...]) -> Aviso:
    clave = obra.get("clave") or "(obra sin clave)"
    return Aviso(
        tokens=tokens,
        titulo="Reprogramación aplicada",
        cuerpo=f"Obra {clave} · {_etiqueta(reprogramacion)}. Revisa las fechas nuevas.",
        datos={
            "tipo": "reprogramacion_aplicada",
            "reprogramacion_id": str(reprogramacion.get("id", "")),
        },
    )
