"""Reprogramar lo asignado: una cadena con salto (migración 0072; D-533, P-4).

«Las fechas de lo asignado no se mueven solas: reprogramar **propone** la fecha nueva y
alguien la acepta.» Ese alguien es una cadena del mismo molde que la de la incidencia
(D-269), con una diferencia: la **realiza** control de obra.

    propone              revisa        valida           realiza
    Residente            Supervisor    Control de obra  Control de obra
    Supervisor           (se salta)    Control de obra  Control de obra

y al aplicarse se notifica el cambio a los demás (`roles_a_avisar_al_aplicar`). Control
de obra, además, puede dejar **observaciones** al residente y al supervisor
(`texto_de_observacion`): no mueven la cadena, solo se dicen. Mientras nada está asignado no hay
nada que proponer: el residente edita las fechas y control de obra la estructura.

**Qué es «lo asignado» en ObraCtrl.** Una actividad asignada a un contratista: el del
trato de su frente en la obra (la planeación, `frente_obra`: «se contrata por frente») o
el que la actividad traiga directo. El cerebro lo llama `ESTADO_CONGELAMIENTO =
contratado` sobre el concepto; ObraCtrl no modela ese estado, dice «asignado», y la
asignación a un contratista es lo más cercano. Se decide en un solo lugar:
`esta_asignada`.

Módulo puro: sin BD ni FastAPI (§12.11).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from obractrl.domain.shared.diccionario import Rol

__all__ = [
    "ROLES_QUE_RECIBEN_OBSERVACIONES",
    "ErrorDeReprogramacion",
    "EstatusReprogramacion",
    "FechasDeLoAsignado",
    "Reprogramacion",
    "esta_asignada",
    "exigir_fechas_libres",
    "roles_a_avisar_al_aplicar",
    "texto_de_observacion",
]


class ErrorDeReprogramacion(ValueError):
    """La reprogramación o su paso no es válido."""


class FechasDeLoAsignado(RuntimeError):
    """Se quiso mover directo la fecha de algo asignado (P-4): hay que proponer una
    reprogramación y que alguien la acepte."""


class EstatusReprogramacion(StrEnum):
    """Es el enum de Postgres `estatus_reprogramacion`."""

    PROPUESTA = "propuesta"
    REVISADA = "revisada"
    VALIDADA = "validada"
    APLICADA = "aplicada"
    RECHAZADA = "rechazada"


def esta_asignada(*, contratista_id: object | None) -> bool:
    """Una actividad está asignada si tiene contratista (el de su frente o el suyo)."""
    return contratista_id is not None


def exigir_fechas_libres(*, asignada: bool, toca_fechas: bool) -> None:
    """Las fechas de lo asignado no se editan directo (P-4)."""
    if asignada and toca_fechas:
        raise FechasDeLoAsignado(
            "Esta actividad está asignada a un contratista: sus fechas no se mueven solas. Propón una "
            "reprogramación; el supervisor la revisa y control de obra la valida y la "
            "realiza."
        )


def roles_a_avisar_al_aplicar(propuesta_rol: Rol) -> frozenset[Rol]:
    """A quién se avisa cuando se aplica una reprogramación (D-533: «se notifica el
    cambio a los demás»). Depende de quién la propuso: los demás son los otros dos.

    * propuso el residente  → supervisor y control de obra;
    * propuso el supervisor → residente y control de obra.

    La persona que realiza la acción no se avisa a sí misma: eso lo resuelve quien
    notifica; aquí solo se dice qué **roles** son «los demás».
    """
    if propuesta_rol is Rol.RESIDENTE:
        return frozenset({Rol.SUPERVISOR, Rol.CONTROL_OBRA})
    if propuesta_rol is Rol.SUPERVISOR:
        return frozenset({Rol.RESIDENTE, Rol.CONTROL_OBRA})
    raise ErrorDeReprogramacion(
        f"Una reprogramación la propone el residente o el supervisor; no hay a quién "
        f"avisar si la propuso el rol {propuesta_rol.value!r}."
    )


ROLES_QUE_RECIBEN_OBSERVACIONES: frozenset[Rol] = frozenset({Rol.RESIDENTE, Rol.SUPERVISOR})
"""A quiénes les deja observaciones control de obra: al residente y al supervisor."""


def texto_de_observacion(*, rol: Rol, texto: str) -> str:
    """El texto limpio de una observación, o `ErrorDeReprogramacion`.

    Observa control de obra —quien valida y realiza— y no cambia el estatus de la
    reprogramación: es una nota para el residente y el supervisor, no un rechazo.
    Cabe en cualquier estatus, también después de aplicada o rechazada.
    """
    if rol is not Rol.CONTROL_OBRA:
        raise ErrorDeReprogramacion(
            f"Deja observaciones control de obra; el rol {rol.value!r} no."
        )
    limpio = texto.strip()
    if not limpio:
        raise ErrorDeReprogramacion("Una observación dice algo: falta el texto.")
    return limpio


_TRANSICIONES: dict[EstatusReprogramacion, set[EstatusReprogramacion]] = {
    EstatusReprogramacion.PROPUESTA: {
        EstatusReprogramacion.REVISADA,
        EstatusReprogramacion.RECHAZADA,
    },
    EstatusReprogramacion.REVISADA: {
        EstatusReprogramacion.VALIDADA,
        EstatusReprogramacion.RECHAZADA,
    },
    EstatusReprogramacion.VALIDADA: {
        EstatusReprogramacion.APLICADA,
        EstatusReprogramacion.RECHAZADA,
    },
    EstatusReprogramacion.APLICADA: set(),
    EstatusReprogramacion.RECHAZADA: set(),
}


@dataclass(slots=True)
class Reprogramacion:
    actividad_id: str
    propuesta_por: str
    propuesta_rol: Rol
    motivo: str
    fecha_inicio: date | None = None
    fecha_termino: date | None = None
    estatus: EstatusReprogramacion = EstatusReprogramacion.PROPUESTA
    revisada_por: str | None = None
    validada_por: str | None = None
    aplicada_por: str | None = None
    rechazada_por: str | None = None
    motivo_rechazo: str | None = None

    @classmethod
    def proponer(
        cls,
        *,
        actividad_id: str,
        usuario_id: str,
        rol: Rol,
        motivo: str,
        asignada: bool,
        fecha_inicio: date | None,
        fecha_termino: date | None,
        fecha_inicio_actual: date | None,
        fecha_termino_actual: date | None,
    ) -> Reprogramacion:
        """Propone el residente o el supervisor; el supervisor se salta la revisión."""
        if rol not in (Rol.RESIDENTE, Rol.SUPERVISOR):
            raise ErrorDeReprogramacion(
                f"Proponen una reprogramación el residente o el supervisor; el rol "
                f"{rol.value!r} no."
            )
        if not asignada:
            raise ErrorDeReprogramacion(
                "Solo se reprograma lo asignado: esta actividad no está asignada a ningún contratista. "
                "Sus fechas se editan directo."
            )
        if not motivo.strip():
            raise ErrorDeReprogramacion("Una reprogramación dice por qué: falta el motivo.")
        if fecha_inicio is None and fecha_termino is None:
            raise ErrorDeReprogramacion("Propón al menos una fecha nueva: inicio o término.")

        inicio = fecha_inicio if fecha_inicio is not None else fecha_inicio_actual
        termino = fecha_termino if fecha_termino is not None else fecha_termino_actual
        if inicio is not None and termino is not None and termino < inicio:
            raise ErrorDeReprogramacion(
                f"La fecha de término ({termino}) es anterior a la de inicio ({inicio})."
            )
        if fecha_inicio in (None, fecha_inicio_actual) and fecha_termino in (
            None,
            fecha_termino_actual,
        ):
            raise ErrorDeReprogramacion(
                "La fecha propuesta es la que ya tiene: no hay nada que reprogramar."
            )

        reprogramacion = cls(
            actividad_id=actividad_id,
            propuesta_por=usuario_id,
            propuesta_rol=rol,
            motivo=motivo.strip(),
            fecha_inicio=fecha_inicio,
            fecha_termino=fecha_termino,
        )
        if rol is Rol.SUPERVISOR:
            # La revisión se salta: es quien propone. `revisada_por` queda en null.
            reprogramacion.estatus = EstatusReprogramacion.REVISADA
        return reprogramacion

    def _transicionar(self, destino: EstatusReprogramacion) -> None:
        permitidas = _TRANSICIONES[self.estatus]
        if destino not in permitidas:
            esperadas = ", ".join(sorted(e.value for e in permitidas)) or "ninguna"
            raise ErrorDeReprogramacion(
                f"No se puede pasar de {self.estatus.value!r} a {destino.value!r}. "
                f"Transiciones válidas: {esperadas}."
            )
        self.estatus = destino

    def revisar(self, *, usuario_id: str, rol: Rol) -> None:
        """Revisa el supervisor lo que propuso el residente."""
        if rol is not Rol.SUPERVISOR:
            raise ErrorDeReprogramacion(
                f"Revisa una reprogramación el supervisor; el rol {rol.value!r} no."
            )
        self._transicionar(EstatusReprogramacion.REVISADA)
        self.revisada_por = usuario_id

    def validar(self, *, usuario_id: str, rol: Rol) -> None:
        if rol is not Rol.CONTROL_OBRA:
            raise ErrorDeReprogramacion(
                f"Valida una reprogramación control de obra; el rol {rol.value!r} no."
            )
        self._transicionar(EstatusReprogramacion.VALIDADA)
        self.validada_por = usuario_id

    def aplicar(self, *, usuario_id: str, rol: Rol) -> None:
        """La realiza control de obra: mueve la fecha de lo asignado."""
        if rol is not Rol.CONTROL_OBRA:
            raise ErrorDeReprogramacion(
                f"Realiza una reprogramación control de obra; el rol {rol.value!r} no."
            )
        self._transicionar(EstatusReprogramacion.APLICADA)
        self.aplicada_por = usuario_id

    def rechazar(self, *, usuario_id: str, rol: Rol, motivo: str) -> None:
        """Rechaza el supervisor (lo propuesto por el residente) o control de obra, con
        motivo. Lo aplicado ya no se rechaza."""
        if rol not in (Rol.SUPERVISOR, Rol.CONTROL_OBRA):
            raise ErrorDeReprogramacion(
                f"El rol {rol.value!r} no puede rechazar una reprogramación."
            )
        if rol is Rol.SUPERVISOR and self.estatus is not EstatusReprogramacion.PROPUESTA:
            raise ErrorDeReprogramacion(
                "El supervisor rechaza lo que revisa; después de eso decide control de obra."
            )
        if not motivo.strip():
            raise ErrorDeReprogramacion("Un rechazo requiere motivo.")
        self._transicionar(EstatusReprogramacion.RECHAZADA)
        self.rechazada_por = usuario_id
        self.motivo_rechazo = motivo.strip()
