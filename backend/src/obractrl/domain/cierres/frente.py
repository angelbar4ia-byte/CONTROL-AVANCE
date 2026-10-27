"""El cierre de un frente (migración 0071; cerebro MODELO.md D-515/D-522/D-261).

El cierre tiene dos candados: **por frente** y, si se requiere, por actividad; el
segundo cierra todo el lote. Un frente es un **nivel constructivo** —cimentación,
planta baja, azotea—, y se cierra con las manos de siempre: el **residente**
solicita, al 90 % de avance; el **supervisor** aprueba; **control de obra** valida.
Rechaza el supervisor o control, con motivo.

Qué significa cerrar un frente (D-516): cierra **al residente** —ya no registra
avance ahí—, y para los demás roles sigue abierto hasta la entrega de la casa. Esa
regla de captura vive en el caso de uso de avance; aquí vive la cadena y su umbral.

Módulo puro: sin BD ni FastAPI (§12.11).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from obractrl.domain.cierres.reglas import ErrorDeCierre
from obractrl.domain.shared.diccionario import Rol

__all__ = [
    "UMBRAL_CIERRE_DE_FRENTE",
    "CierreDeFrente",
    "EstatusCierreFrente",
    "frente_listo_para_cierre",
]

UMBRAL_CIERRE_DE_FRENTE = Decimal(90)
"""El avance, en %, a partir del cual el residente puede solicitar el cierre de un
frente (D-261)."""


class EstatusCierreFrente(StrEnum):
    """Es el enum de Postgres `estatus_cierre_frente`."""

    SOLICITADO = "solicitado"
    APROBADO = "aprobado"
    VALIDADO = "validado"
    RECHAZADO = "rechazado"


_TRANSICIONES: dict[EstatusCierreFrente, set[EstatusCierreFrente]] = {
    EstatusCierreFrente.SOLICITADO: {
        EstatusCierreFrente.APROBADO,
        EstatusCierreFrente.RECHAZADO,
    },
    EstatusCierreFrente.APROBADO: {
        EstatusCierreFrente.VALIDADO,
        EstatusCierreFrente.RECHAZADO,
    },
    # Terminales: lo validado es definitivo y lo rechazado se vuelve a solicitar
    # con una solicitud nueva.
    EstatusCierreFrente.VALIDADO: set(),
    EstatusCierreFrente.RECHAZADO: set(),
}


def frente_listo_para_cierre(avance_pct: Decimal, *, estatus_vivo: str | None) -> bool:
    """`frente_listo_para_cierre` (MODELO.md §5a): el frente llegó al umbral y no se
    ha solicitado su cierre. **Avisa, no cierra**: el cierre pregunta, no impide."""
    return avance_pct >= UMBRAL_CIERRE_DE_FRENTE and estatus_vivo is None


@dataclass(slots=True)
class CierreDeFrente:
    """Un cierre de frente en su cadena de tres manos."""

    nivel_id: str
    solicitado_por: str
    avance_pct: Decimal
    estatus: EstatusCierreFrente = EstatusCierreFrente.SOLICITADO
    aprobado_por: str | None = None
    validado_por: str | None = None
    comentarios: str | None = None

    @classmethod
    def solicitar(
        cls, *, nivel_id: str, residente_id: str, rol: Rol, avance_pct: Decimal
    ) -> CierreDeFrente:
        """El residente solicita el cierre del frente, al 90 % (D-261)."""
        if rol is not Rol.RESIDENTE:
            raise ErrorDeCierre(
                f"Solicita el cierre de un frente el residente; el rol {rol.value!r} no puede."
            )
        if avance_pct < UMBRAL_CIERRE_DE_FRENTE:
            raise ErrorDeCierre(
                f"El frente va en {avance_pct:.2f} %: el cierre se solicita a partir "
                f"del {UMBRAL_CIERRE_DE_FRENTE} % de avance."
            )
        return cls(nivel_id=nivel_id, solicitado_por=residente_id, avance_pct=avance_pct)

    def _transicionar(self, destino: EstatusCierreFrente) -> None:
        permitidas = _TRANSICIONES[self.estatus]
        if destino not in permitidas:
            esperadas = ", ".join(sorted(e.value for e in permitidas)) or "ninguna"
            raise ErrorDeCierre(
                f"No se puede pasar de {self.estatus.value!r} a {destino.value!r}. "
                f"Transiciones válidas: {esperadas}."
            )
        self.estatus = destino

    def aprobar(self, *, usuario_id: str, rol: Rol) -> None:
        """El supervisor aprueba (D-269: las manos de siempre)."""
        if not rol.puede_autorizar_cierre:
            raise ErrorDeCierre(
                f"Aprueba el cierre de un frente el supervisor; el rol {rol.value!r} no."
            )
        self._transicionar(EstatusCierreFrente.APROBADO)
        self.aprobado_por = usuario_id

    def validar(self, *, usuario_id: str, rol: Rol, comentario: str | None = None) -> None:
        """Control de obra valida y comenta: el frente queda cerrado."""
        if not rol.puede_validar_cierre:
            raise ErrorDeCierre(
                f"Valida el cierre de un frente control de obra; el rol {rol.value!r} no."
            )
        self._transicionar(EstatusCierreFrente.VALIDADO)
        self.validado_por = usuario_id
        if comentario:
            self.comentarios = comentario

    def rechazar(self, *, usuario_id: str, rol: Rol, motivo: str) -> None:
        """Rechaza el supervisor o control de obra, con motivo."""
        if rol not in (Rol.SUPERVISOR, Rol.CONTROL_OBRA):
            raise ErrorDeCierre(f"El rol {rol.value!r} no puede rechazar un cierre de frente.")
        if not motivo.strip():
            raise ErrorDeCierre("Un rechazo requiere motivo.")
        self._transicionar(EstatusCierreFrente.RECHAZADO)
        self.comentarios = motivo

    @property
    def esta_cerrado(self) -> bool:
        """Solo un cierre validado cierra el frente (al residente)."""
        return self.estatus is EstatusCierreFrente.VALIDADO
