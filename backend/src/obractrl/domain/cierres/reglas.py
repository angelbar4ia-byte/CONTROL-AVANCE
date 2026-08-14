"""Reglas del cierre de actividad.

Spec §6 · §4 (validar ≠ autorizar) · §11.3 workflow C.

Flujo multi-actor:
    Residente **solicita** → Supervisor **autoriza** → Control de obra
    **valida y comenta** (no autoriza).

La distinción entre *autorizar* y *validar* es una regla de permisos, no un
detalle de UI: el Supervisor cierra la actividad; Control de obra revisa y
comenta sin poder cerrarla (§4). Se modela con transiciones explícitas para
que no se pueda confundir una con otra.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from obractrl.domain.shared.diccionario import EstatusSolicitudCierre, Rol
from obractrl.domain.shared.valores import Dinero

__all__ = [
    "TRANSICIONES",
    "ErrorDeCierre",
    "SolicitudCierre",
    "calcular_monto_cierre",
]


class ErrorDeCierre(ValueError):
    """Transición o permiso inválido en el flujo de cierre (§6)."""


TRANSICIONES: dict[EstatusSolicitudCierre, set[EstatusSolicitudCierre]] = {
    EstatusSolicitudCierre.SOLICITADA: {
        EstatusSolicitudCierre.AUTORIZADA,
        EstatusSolicitudCierre.RECHAZADA,
    },
    EstatusSolicitudCierre.AUTORIZADA: {
        EstatusSolicitudCierre.VALIDADA,
        EstatusSolicitudCierre.RECHAZADA,
    },
    # Terminales
    EstatusSolicitudCierre.VALIDADA: set(),
    EstatusSolicitudCierre.RECHAZADA: set(),
}
"""Transiciones permitidas. No se valida lo que no se autorizó primero."""


def calcular_monto_cierre(cantidad: Decimal, precio_unitario: Dinero) -> Dinero:
    """``monto = cantidad × precio_unitario`` (§6)."""
    if cantidad < 0:
        raise ErrorDeCierre("La cantidad a cerrar no puede ser negativa.")
    return precio_unitario * cantidad


@dataclass(slots=True)
class SolicitudCierre:
    """Entidad de dominio del cierre de actividad.

    Requiere checklist y evidencias para poder solicitarse (§6).
    """

    actividad_id: str
    solicitada_por: str
    cantidad: Decimal
    monto: Dinero
    checklist: list[dict]
    adjuntos: list[str]
    estatus: EstatusSolicitudCierre = EstatusSolicitudCierre.SOLICITADA
    autorizada_por: str | None = None
    validada_por: str | None = None
    comentarios: str | None = None

    @classmethod
    def solicitar(
        cls,
        *,
        actividad_id: str,
        residente_id: str,
        rol: Rol,
        cantidad: Decimal,
        precio_unitario: Dinero,
        checklist: list[dict],
        adjuntos: list[str],
    ) -> SolicitudCierre:
        """El Residente solicita el cierre (§11.3 C.1)."""
        if rol is not Rol.RESIDENTE:
            raise ErrorDeCierre(
                f"Solo el Residente solicita el cierre de una actividad; "
                f"el rol {rol.value!r} no puede."
            )
        if not checklist:
            raise ErrorDeCierre("El cierre requiere checklist (§6).")
        if not adjuntos:
            raise ErrorDeCierre("El cierre requiere evidencias (§6).")

        return cls(
            actividad_id=actividad_id,
            solicitada_por=residente_id,
            cantidad=cantidad,
            monto=calcular_monto_cierre(cantidad, precio_unitario),
            checklist=list(checklist),
            adjuntos=list(adjuntos),
        )

    def _transicionar(self, destino: EstatusSolicitudCierre) -> None:
        permitidas = TRANSICIONES[self.estatus]
        if destino not in permitidas:
            esperadas = ", ".join(sorted(e.value for e in permitidas)) or "ninguna"
            raise ErrorDeCierre(
                f"No se puede pasar de {self.estatus.value!r} a "
                f"{destino.value!r}. Transiciones válidas: {esperadas}."
            )
        self.estatus = destino

    def autorizar(self, *, usuario_id: str, rol: Rol) -> None:
        """El Supervisor **autoriza**: cierra la actividad (§4, §11.3 C.2)."""
        if not rol.puede_autorizar_cierre:
            raise ErrorDeCierre(
                f"Solo el Supervisor autoriza un cierre; el rol {rol.value!r} no. "
                f"Control de obra valida y comenta, pero no autoriza (§4)."
            )
        self._transicionar(EstatusSolicitudCierre.AUTORIZADA)
        self.autorizada_por = usuario_id

    def validar(
        self, *, usuario_id: str, rol: Rol, comentario: str | None = None
    ) -> None:
        """Control de obra **valida y comenta**, no autoriza (§4, §11.3 C.3)."""
        if not rol.puede_validar_cierre:
            raise ErrorDeCierre(
                f"Solo Control de obra valida un cierre; el rol {rol.value!r} no."
            )
        self._transicionar(EstatusSolicitudCierre.VALIDADA)
        self.validada_por = usuario_id
        if comentario:
            self.comentarios = comentario

    def rechazar(self, *, usuario_id: str, rol: Rol, motivo: str) -> None:
        """Rechaza el cierre. Lo pueden hacer Supervisor y Control (§11.2)."""
        if rol not in (Rol.SUPERVISOR, Rol.CONTROL_OBRA):
            raise ErrorDeCierre(
                f"El rol {rol.value!r} no puede rechazar un cierre."
            )
        if not motivo.strip():
            raise ErrorDeCierre("Un rechazo requiere motivo.")
        self._transicionar(EstatusSolicitudCierre.RECHAZADA)
        self.comentarios = motivo

    @property
    def esta_cerrada(self) -> bool:
        """Solo una solicitud validada habilita la actividad para estimación."""
        return self.estatus is EstatusSolicitudCierre.VALIDADA
