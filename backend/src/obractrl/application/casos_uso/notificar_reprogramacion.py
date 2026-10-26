"""Casos de uso: avisar de una reprogramación de lo asignado (D-533).

Dos avisos, los dos **después** de commitear (el evento se publica ya con todo
escrito), así que todo aquí falla hacia adentro, con el mismo molde y las mismas
razones que `notificar_estimacion`: un aviso perdido no deshace una fecha ya movida ni
una observación ya dicha.

**Al aplicarse** («se notifica el cambio a los demás»): depende de quién la propuso.

    propuso el residente  → se avisa al supervisor y a control de obra
    propuso el supervisor → se avisa al residente y a control de obra

(`roles_a_avisar_al_aplicar`). Son **roles de esa obra**, no solo quienes intervinieron:
el supervisor que llevaba la obra y no tocó la reprogramación también se entera. Quien
realiza la acción no se avisa a sí mismo.

**Al observar**: control de obra deja una observación al residente y al supervisor de la
obra (`ROLES_QUE_RECIBEN_OBSERVACIONES`).

El correo lleva las fechas y el texto de la observación; el push no (aparece en la
pantalla de bloqueo y pasa por servidores de terceros, §12.4): dice qué actividad y a
dónde ir.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Collection
from datetime import date
from typing import Any
from uuid import UUID

from obractrl.application.eventos import ReprogramacionAplicada, ReprogramacionObservada
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
from obractrl.domain.programacion.reprogramacion import (
    ROLES_QUE_RECIBEN_OBSERVACIONES,
    roles_a_avisar_al_aplicar,
)
from obractrl.domain.shared.diccionario import Rol

__all__ = ["NotificarReprogramacion"]

_log = logging.getLogger(__name__)


class NotificarReprogramacion:
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

    async def aplicada(self, evento: ReprogramacionAplicada) -> bool:
        reprogramacion = await self._reprogramaciones.obtener(evento.reprogramacion_id)
        if reprogramacion is None:
            _log.warning(
                "No se avisó la reprogramación %s: ya no está en el alcance.",
                evento.reprogramacion_id,
            )
            return False

        obra = await self._obras.obtener(evento.obra_id) or {}
        destinatarios = await self._destinatarios(
            evento.obra_id,
            roles=roles_a_avisar_al_aplicar(Rol(str(reprogramacion["propuesta_rol"]))),
            excepto=reprogramacion.get("aplicada_por"),
        )
        return await self._entregar(
            destinatarios,
            correo=lambda para: _correo_de_aplicada(
                reprogramacion=reprogramacion, obra=obra, para=para
            ),
            aviso=lambda tokens: _aviso_de_aplicada(
                reprogramacion=reprogramacion, obra=obra, tokens=tokens
            ),
            que=f"la reprogramación {evento.reprogramacion_id}",
        )

    async def observada(self, evento: ReprogramacionObservada) -> bool:
        observacion = await self._reprogramaciones.obtener_observacion(evento.observacion_id)
        reprogramacion = await self._reprogramaciones.obtener(evento.reprogramacion_id)
        if observacion is None or reprogramacion is None:
            _log.warning(
                "No se avisó la observación %s: ya no está en el alcance.",
                evento.observacion_id,
            )
            return False

        obra = await self._obras.obtener(evento.obra_id) or {}
        destinatarios = await self._destinatarios(
            evento.obra_id,
            roles=ROLES_QUE_RECIBEN_OBSERVACIONES,
            excepto=observacion.get("usuario_id"),
        )
        return await self._entregar(
            destinatarios,
            correo=lambda para: _correo_de_observacion(
                reprogramacion=reprogramacion, observacion=observacion, obra=obra, para=para
            ),
            aviso=lambda tokens: _aviso_de_observacion(
                reprogramacion=reprogramacion, obra=obra, tokens=tokens
            ),
            que=f"la observación {evento.observacion_id}",
        )

    async def _destinatarios(
        self, obra_id: UUID, *, roles: Collection[Rol], excepto: object | None
    ) -> list[dict[str, Any]]:
        """Los usuarios de esa obra con alguno de esos roles, sin quien hizo la acción."""
        pedidos = {rol.value for rol in roles}
        return [
            fila
            for fila in await self._usuarios.de_la_obra(obra_id)
            if str(fila["rol"]) in pedidos and str(fila["id"]) != str(excepto)
        ]

    async def _entregar(
        self,
        destinatarios: list[dict[str, Any]],
        *,
        correo: Callable[[tuple[str, ...]], Correo],
        aviso: Callable[[tuple[str, ...]], Aviso],
        que: str,
    ) -> bool:
        correos = tuple(
            str(fila["email"]).strip()
            for fila in destinatarios
            if str(fila.get("email") or "").strip()
        )
        ids = [UUID(str(fila["id"])) for fila in destinatarios]
        tokens = tuple(await self._usuarios.tokens_push_de(ids)) if self._push and ids else ()

        if not correos and not tokens:
            _log.warning(
                "No hay a quién avisar de %s: nadie tiene correo ni dispositivo registrado.",
                que,
            )
            return False

        salio_correo = bool(correos) and await self._correo.enviar(correo(correos))
        salio_push = False
        if self._push is not None and tokens:
            salio_push = (await self._push.enviar(aviso(tokens))) > 0
        return salio_correo or salio_push


def _fecha(valor: date | None) -> str:
    return valor.isoformat() if valor is not None else "sin fecha"


def _etiqueta(reprogramacion: dict[str, Any]) -> str:
    clave = reprogramacion.get("concepto_clave")
    descripcion = reprogramacion.get("actividad") or "(actividad sin descripción)"
    return f"{clave} {descripcion}" if clave else str(descripcion)


def _correo_de_aplicada(
    *, reprogramacion: dict[str, Any], obra: dict, para: tuple[str, ...]
) -> Correo:
    clave = obra.get("clave") or "(obra sin clave)"
    actividad = _etiqueta(reprogramacion)
    inicio_antes = _fecha(reprogramacion.get("fecha_inicio_anterior"))
    termino_antes = _fecha(reprogramacion.get("fecha_termino_anterior"))
    inicio = _fecha(
        reprogramacion.get("fecha_inicio") or reprogramacion.get("fecha_inicio_anterior")
    )
    termino = _fecha(
        reprogramacion.get("fecha_termino") or reprogramacion.get("fecha_termino_anterior")
    )
    motivo = reprogramacion.get("motivo") or ""

    texto = (
        f"Se reprogramó lo asignado en la obra {clave}: {actividad}.\n"
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


def _aviso_de_aplicada(
    *, reprogramacion: dict[str, Any], obra: dict, tokens: tuple[str, ...]
) -> Aviso:
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


def _correo_de_observacion(
    *,
    reprogramacion: dict[str, Any],
    observacion: dict[str, Any],
    obra: dict,
    para: tuple[str, ...],
) -> Correo:
    clave = obra.get("clave") or "(obra sin clave)"
    actividad = _etiqueta(reprogramacion)
    autor = observacion.get("usuario_nombre") or "Control de obra"
    texto_obs = observacion.get("texto") or ""
    estatus = reprogramacion.get("estatus") or ""

    texto = (
        f"{autor} dejó una observación sobre la reprogramación de {actividad} "
        f"(obra {clave}, {estatus}):\n\n{texto_obs}"
    )
    html = (
        f"<h2>Observación de control de obra · {clave}</h2>"
        f"<p><strong>{actividad}</strong> · reprogramación {estatus}.</p>"
        f"<p>{autor}:</p><blockquote>{texto_obs}</blockquote>"
    )
    return Correo(
        para=para,
        asunto=f"Observación sobre una reprogramación · {clave} · {actividad}",
        html=html,
        texto=texto,
        etiquetas={"tipo": "reprogramacion_observada"},
    )


def _aviso_de_observacion(
    *, reprogramacion: dict[str, Any], obra: dict, tokens: tuple[str, ...]
) -> Aviso:
    clave = obra.get("clave") or "(obra sin clave)"
    return Aviso(
        tokens=tokens,
        titulo="Observación de control de obra",
        cuerpo=f"Obra {clave} · {_etiqueta(reprogramacion)}. Ábrela para leerla.",
        datos={
            "tipo": "reprogramacion_observada",
            "reprogramacion_id": str(reprogramacion.get("id", "")),
        },
    )
