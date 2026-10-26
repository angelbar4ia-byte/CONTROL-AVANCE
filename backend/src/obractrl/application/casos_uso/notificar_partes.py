"""Caso de uso: avisar a quien tiene que dar el siguiente paso de una parte (D-571; §8.6).

«Se avisa a quien tiene que dar el siguiente paso de la cadena.» Cuando una o varias partes de
una obra cambian de paso, se avisa —por correo y push— a los usuarios **de esa obra** cuyo rol
puede darles el paso que sigue (`roles_del_siguiente_paso`), sin quien acaba de darlo:

    enviada a presupuesto → Costos y Control (autorizar)
    por validar           → Control (validar)
    autorizada            → Control (enviar a programar)
    enviada a programa    → Control y Supervisor (programar)
    programada            → Control (asignar)
    devuelta a un paso    → quien da ese paso (cuantificar: Costos y Control)

Falla hacia adentro, como `notificar_estimacion`: el estado ya está escrito y un aviso perdido
no lo deshace. El correo nombra las partes; el push no (pantalla de bloqueo, §12.4).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from uuid import UUID

from obractrl.application.casos_uso.gestionar_partes import _partes_de
from obractrl.application.eventos import PartesCambiaronDeEstado
from obractrl.application.puertos.notificaciones import (
    Aviso,
    Correo,
    EnviadorDeCorreo,
    EnviadorDePush,
)
from obractrl.application.puertos.partes import RepositorioPartes
from obractrl.application.puertos.repositorios import (
    RepositorioObras,
    RepositorioUsuarios,
)
from obractrl.domain.partes.estado import EstadoDeParte, roles_del_siguiente_paso

__all__ = ["NotificarPartes"]

_log = logging.getLogger(__name__)

_ETIQUETA = {
    "cuantificando": "cuantificando",
    "enviada_presupuesto": "en presupuesto",
    "por_validar": "por validar",
    "autorizada": "autorizada",
    "enviada_programa": "en programa",
    "programada": "programada",
    "asignada": "asignada",
}


class NotificarPartes:
    def __init__(
        self,
        *,
        partes: RepositorioPartes,
        obras: RepositorioObras,
        usuarios: RepositorioUsuarios,
        correo: EnviadorDeCorreo,
        push: EnviadorDePush | None = None,
    ) -> None:
        self._partes = partes
        self._obras = obras
        self._usuarios = usuarios
        self._correo = correo
        self._push = push

    async def ejecutar(self, evento: PartesCambiaronDeEstado) -> bool:
        if not evento.claves or len(evento.estados) != len(evento.claves):
            return False

        nombres = {p.clave: p.nombre for p in await _partes_de(self._partes, evento.obra_id)}
        por_estado: dict[str, list[str]] = defaultdict(list)
        for clave, estado in zip(evento.claves, evento.estados, strict=True):
            por_estado[estado].append(nombres.get(clave, clave))

        # A quién le toca el paso siguiente de cualquiera de esas partes.
        roles = {
            rol.value
            for estado in por_estado
            for rol in roles_del_siguiente_paso(EstadoDeParte(estado))
        }
        if not roles:
            return False  # lo asignado ya no tiene paso siguiente
        destinatarios = [
            u
            for u in await self._usuarios.de_la_obra(evento.obra_id)
            if str(u["rol"]) in roles and str(u["id"]) != str(evento.usuario_id)
        ]
        correos = tuple(
            str(u["email"]).strip() for u in destinatarios if str(u.get("email") or "").strip()
        )
        ids = [UUID(str(u["id"])) for u in destinatarios]
        tokens = tuple(await self._usuarios.tokens_push_de(ids)) if self._push and ids else ()
        if not correos and not tokens:
            _log.warning(
                "Las partes de la obra %s cambiaron de paso y no hay a quién avisar.",
                evento.obra_id,
            )
            return False

        obra = await self._obras.obtener(evento.obra_id) or {}
        clave_obra = obra.get("clave") or "(obra sin clave)"
        lineas = [
            f"· {', '.join(nombres_)}: ahora {_ETIQUETA.get(estado, estado)}"
            for estado, nombres_ in por_estado.items()
        ]
        resumen = f"{len(evento.claves)} {'parte' if len(evento.claves) == 1 else 'partes'}"

        salio_correo = bool(correos) and await self._correo.enviar(
            Correo(
                para=correos,
                asunto=f"Partes que esperan tu paso · {clave_obra}",
                texto=f"En la obra {clave_obra}: {resumen} cambiaron de paso y te toca el siguiente.\n"
                + "\n".join(lineas),
                html=f"<h2>Partes que esperan tu paso · {clave_obra}</h2><p>{resumen}.</p><ul>"
                + "".join(f"<li>{ln[2:]}</li>" for ln in lineas)
                + "</ul>",
                etiquetas={"tipo": "partes_cambiaron_de_estado"},
            )
        )
        salio_push = False
        if self._push is not None and tokens:
            salio_push = (
                await self._push.enviar(
                    Aviso(
                        tokens=tokens,
                        titulo="Partes que esperan tu paso",
                        cuerpo=f"Obra {clave_obra} · {resumen}.",
                        datos={"tipo": "partes_cambiaron_de_estado", "obra_id": str(evento.obra_id)},
                    )
                )
                > 0
            )
        return salio_correo or salio_push
