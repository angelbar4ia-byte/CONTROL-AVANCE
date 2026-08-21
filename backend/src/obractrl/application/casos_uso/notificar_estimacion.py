"""Caso de uso: avisar que una estimación quedó validada.

Spec §11.1 ("`EstimacionValidada` → **notificar (Resend)** + bloquear el
periodo") · §11.3 E.5 · §12.2 (Resend) · §12.11.

Lo dispara el evento `EstimacionValidada`, que `ValidarEstimacion` publica
**después** de commitear (§11.1). Por eso todo aquí falla hacia adentro:

- `EnviadorDeCorreo.enviar` y `EnviadorDePush.enviar` no levantan: devuelven
  si salió o no (`application/puertos/notificaciones.py`).
- Si no hay destinatarios con correo, se registra y se sigue.
- Y aunque algo levantara, `BusEnProceso` se lo traga con traza
  (`application/eventos.py`): una notificación fallida no puede tumbar la
  validación de una estimación que ya está en la base.

**Dos canales, un solo intento (§12.2).** Sale correo *y* push, y ninguno
depende del otro: el residente que está en obra ve la notificación en el
teléfono y quien administra la ve en su bandeja. Si un usuario no tiene
dispositivo registrado no pasa nada —recibe solo el correo—, y al revés
también. El resultado se reporta como "salió por al menos un canal", que es
lo que de verdad importa: que alguien se haya enterado.

**El bloqueo del periodo NO vive aquí**, aunque el §11.1 nombre las dos cosas
en la misma línea. Va dentro de la transacción de `ValidarEstimacion`, por el
mismo motivo que `IncidenciaDetiene` bloquea las actividades en el caso de uso
y no en el manejador (ver su docstring en `application/eventos.py`): el bus
descarta los fallos, y un periodo que quedara sin bloquear sería un permiso
abierto de más —se podría volver a estimar y cobrar la misma semana—, no un
dato derivado que se recalcule después. Lo que sí puede viajar por el evento
es el aviso, que es exactamente lo que se pierde sin consecuencias.
"""

from __future__ import annotations

import logging
from uuid import UUID

from obractrl.application.eventos import EstimacionValidada
from obractrl.application.puertos.notificaciones import (
    Aviso,
    Correo,
    EnviadorDeCorreo,
    EnviadorDePush,
)
from obractrl.application.puertos.repositorios import (
    RepositorioEstimaciones,
    RepositorioObras,
    RepositorioUsuarios,
)

__all__ = ["NotificarEstimacionValidada"]

_log = logging.getLogger(__name__)


class NotificarEstimacionValidada:
    """Avisa a quien participó en la estimación que ya está validada (§11.3 E.5).

    Destinatarios: quien la creó, quien la validó y el residente de la obra
    (§4: son los tres roles que el workflow E toca). Se piden por el puerto de
    Identidad, no leyendo `usuario` desde aquí (§11.1), y se deduplican —el
    mismo usuario puede ocupar dos de esos papeles.
    """

    def __init__(
        self,
        *,
        estimaciones: RepositorioEstimaciones,
        obras: RepositorioObras,
        usuarios: RepositorioUsuarios,
        correo: EnviadorDeCorreo,
        push: EnviadorDePush | None = None,
    ) -> None:
        self._estimaciones = estimaciones
        self._obras = obras
        self._usuarios = usuarios
        self._correo = correo
        # Opcional a propósito: un entorno sin Expo configurado sigue
        # notificando por correo, y las pruebas que solo verifican el correo
        # no tienen que construir un doble de push (§12.8).
        self._push = push

    async def ejecutar(self, evento: EstimacionValidada) -> bool:
        estimacion = await self._estimaciones.obtener(evento.estimacion_id)
        if estimacion is None:
            # Se validó hace un instante; si ya no se ve, el alcance cambió.
            # No es motivo para levantar: solo no hay a quién avisarle.
            _log.warning(
                "No se notificó la estimación %s: ya no está en el alcance.",
                evento.estimacion_id,
            )
            return False

        obra = await self._obras.obtener(evento.obra_id) or {}
        destinatarios = await self._usuarios.correos_de(
            _ids_unicos(
                estimacion.get("creada_por"),
                estimacion.get("validada_por"),
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
                "La estimación %s se validó pero no hay a quién notificarle: "
                "ningún participante tiene correo ni dispositivo registrado.",
                evento.estimacion_id,
            )
            return False

        salio_correo = bool(correos) and await self._correo.enviar(
            _armar_correo(estimacion=estimacion, obra=obra, para=correos)
        )

        salio_push = False
        if self._push is not None and tokens:
            salio_push = (
                await self._push.enviar(
                    _armar_aviso(estimacion=estimacion, obra=obra, tokens=tokens)
                )
                > 0
            )

        return salio_correo or salio_push


def _ids_unicos(*valores: object) -> list[UUID]:
    """UUIDs no nulos, sin repetir y en orden estable."""
    vistos: dict[UUID, None] = {}
    for valor in valores:
        if valor is None:
            continue
        identificador = valor if isinstance(valor, UUID) else UUID(str(valor))
        vistos.setdefault(identificador, None)
    return list(vistos)


def _armar_correo(*, estimacion: dict, obra: dict, para: tuple[str, ...]) -> Correo:
    """Redacta el aviso. Sin importes de otras obras ni datos de terceros."""
    folio = estimacion.get("folio") or "(sin folio)"
    clave = obra.get("clave") or "(obra sin clave)"
    semana = estimacion["semana"]
    anio = estimacion["anio"]
    monto = estimacion.get("monto_total") or 0
    modo = estimacion.get("modo") or ""

    asunto = f"Estimación {folio} validada · {clave} · semana {semana:02d}/{anio}"
    texto = (
        f"La estimación {folio} de la obra {clave} quedó validada.\n"
        f"Semana {semana:02d}/{anio} · modo {modo} · monto {monto} MXN.\n"
        f"El periodo de esa semana queda bloqueado (§11.3 E.5)."
    )
    html = (
        f"<h2>Estimación {folio} validada</h2>"
        f"<p>Obra <strong>{clave}</strong> · semana "
        f"<strong>{semana:02d}/{anio}</strong> · modo {modo}.</p>"
        f"<p>Monto total: <strong>{monto} MXN</strong>.</p>"
        f"<p>El periodo de esa semana queda bloqueado.</p>"
    )
    return Correo(
        para=para,
        asunto=asunto,
        html=html,
        texto=texto,
        etiquetas={"tipo": "estimacion_validada"},
    )


def _armar_aviso(*, estimacion: dict, obra: dict, tokens: tuple[str, ...]) -> Aviso:
    """Redacta el push. Dos líneas y ningún importe.

    El correo sí lleva el monto: llega a una bandeja que exige contraseña. El
    push aparece en la pantalla de bloqueo, a la vista de cualquiera que tome
    el teléfono, y además pasa por servidores de Expo y de Google (§12.4). Lo
    que viaja es el folio y a dónde ir; el monto se ve al abrir la app, donde
    ya hay sesión.
    """
    folio = estimacion.get("folio") or "(sin folio)"
    clave = obra.get("clave") or "(obra sin clave)"
    semana = estimacion["semana"]
    anio = estimacion["anio"]

    return Aviso(
        tokens=tokens,
        titulo=f"Estimación {folio} validada",
        cuerpo=f"Obra {clave} · semana {semana:02d}/{anio}. El periodo queda bloqueado.",
        datos={"tipo": "estimacion_validada", "estimacion_id": str(estimacion.get("id", ""))},
    )
