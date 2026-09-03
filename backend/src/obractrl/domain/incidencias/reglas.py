"""Reglas de incidencias.

Spec §6 "Incidencias" · §7.8 (control y flujos) · §11.3 workflow F.

Ciclo (§6):
    abierta → programada → en_atencion → cierre_solicitado → cerrada | rechazada

Cualquier rol abre una incidencia; Supervisor o Control la programan, la
cierran o la rechazan. La atención y la solicitud de cierre (los pasos de
en medio) no tienen una mano única —cualquiera de los roles que participan
las registra vía el endpoint de eventos (§11.2)—, así que el dominio no les
impone un rol.

El impacto decide si la incidencia afecta el programa (``retraso`` y
``detiene``, vía ``ImpactoIncidencia.afecta_programa``) y si puede bloquear
actividades (``detiene``, vía ``ImpactoIncidencia.bloquea``, ambas ya
definidas en ``domain.shared.diccionario``). Bloquear/desbloquear las
actividades en sí es una escritura contra `RepositorioActividades`, no algo
que esta entidad haga: el dominio solo valida que la lista
`bloquea_actividades` sea coherente con el impacto — quién ejecuta el
bloqueo real vive en el caso de uso (§12.11, ningún módulo toca las tablas
de otro).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from obractrl.domain.shared.diccionario import (
    EstatusIncidencia,
    ImpactoIncidencia,
    Rol,
    TipoIncidencia,
)

__all__ = [
    "TRANSICIONES",
    "ErrorDeIncidencia",
    "Incidencia",
]


class ErrorDeIncidencia(ValueError):
    """Transición o permiso inválido en el flujo de incidencias (§6)."""


TRANSICIONES: dict[EstatusIncidencia, set[EstatusIncidencia]] = {
    EstatusIncidencia.ABIERTA: {EstatusIncidencia.PROGRAMADA},
    EstatusIncidencia.PROGRAMADA: {EstatusIncidencia.EN_ATENCION},
    EstatusIncidencia.EN_ATENCION: {EstatusIncidencia.CIERRE_SOLICITADO},
    EstatusIncidencia.CIERRE_SOLICITADO: {
        EstatusIncidencia.CERRADA,
        EstatusIncidencia.RECHAZADA,
    },
    # Terminales
    EstatusIncidencia.CERRADA: set(),
    EstatusIncidencia.RECHAZADA: set(),
}
"""Transiciones permitidas. El ciclo del §6 es lineal hasta el final, donde
se bifurca entre cerrar y rechazar."""


_ROLES_QUE_PROGRAMAN = (Rol.SUPERVISOR, Rol.CONTROL_OBRA)
_ROLES_QUE_RESUELVEN = (Rol.SUPERVISOR, Rol.CONTROL_OBRA)
"""Supervisor o Control programan, cierran y rechazan (§6, §11.2)."""


@dataclass(slots=True)
class Incidencia:
    """Entidad de dominio de una incidencia (§7.8)."""

    obra_id: str
    creada_por: str
    tipo: TipoIncidencia
    impacto: ImpactoIncidencia
    titulo: str
    descripcion: str | None = None
    frente_id: str | None = None
    nivel_id: str | None = None
    """Dónde en la obra: el nivel (§7.4). Mismo eje que `actividad.nivel_id`;
    `frente_id` sigue siendo el tipo de contratación (0005), otro eje."""
    etapa_id: str | None = None
    """El sub-frente dentro del nivel."""
    evidencias: list[str] = field(default_factory=list)
    bloquea_actividades: list[str] = field(default_factory=list)
    estatus: EstatusIncidencia = EstatusIncidencia.ABIERTA
    asignada_a: str | None = None
    fecha_limite: date | None = None

    @classmethod
    def abrir(
        cls,
        *,
        obra_id: str,
        creada_por: str,
        tipo: TipoIncidencia,
        impacto: ImpactoIncidencia,
        titulo: str,
        descripcion: str | None = None,
        frente_id: str | None = None,
        nivel_id: str | None = None,
        etapa_id: str | None = None,
        evidencias: list[str] | None = None,
        bloquea_actividades: list[str] | None = None,
        fecha_limite: date | None = None,
    ) -> Incidencia:
        """Cualquier rol abre una incidencia (§11.3 F.1)."""
        if not titulo.strip():
            raise ErrorDeIncidencia("El título es obligatorio.")

        refs = list(bloquea_actividades or [])
        if refs and not impacto.bloquea:
            raise ErrorDeIncidencia(
                f"Solo una incidencia con impacto 'detiene' puede bloquear "
                f"actividades; el impacto {impacto.value!r} no bloquea (§6)."
            )

        return cls(
            obra_id=obra_id,
            creada_por=creada_por,
            tipo=tipo,
            impacto=impacto,
            titulo=titulo,
            descripcion=descripcion,
            frente_id=frente_id,
            nivel_id=nivel_id,
            etapa_id=etapa_id,
            evidencias=list(evidencias or []),
            bloquea_actividades=refs,
            fecha_limite=fecha_limite,
        )

    def _transicionar(self, destino: EstatusIncidencia) -> None:
        permitidas = TRANSICIONES[self.estatus]
        if destino not in permitidas:
            esperadas = ", ".join(sorted(e.value for e in permitidas)) or "ninguna"
            raise ErrorDeIncidencia(
                f"No se puede pasar de {self.estatus.value!r} a "
                f"{destino.value!r}. Transiciones válidas: {esperadas}."
            )
        self.estatus = destino

    def programar(self, *, rol: Rol, asignada_a: str) -> None:
        """Supervisor o Control programan (asignación) (§11.3 F.2)."""
        if rol not in _ROLES_QUE_PROGRAMAN:
            raise ErrorDeIncidencia(
                f"Solo Supervisor o Control de obra programan una incidencia; "
                f"el rol {rol.value!r} no puede."
            )
        self._transicionar(EstatusIncidencia.PROGRAMADA)
        self.asignada_a = asignada_a

    def atender(self) -> None:
        """Evento de atención (§11.3 F.3). Cualquiera de los que participan
        lo registra; no hay una única mano en medio del flujo."""
        self._transicionar(EstatusIncidencia.EN_ATENCION)

    def solicitar_cierre(self) -> None:
        """Deja lista la incidencia para que Supervisor o Control la cierren
        o la rechacen (§11.3 F.3)."""
        self._transicionar(EstatusIncidencia.CIERRE_SOLICITADO)

    def cerrar(self, *, rol: Rol) -> None:
        """Supervisor o Control cierran la incidencia (§11.3 F.4)."""
        if rol not in _ROLES_QUE_RESUELVEN:
            raise ErrorDeIncidencia(
                f"Solo Supervisor o Control de obra cierran una incidencia; "
                f"el rol {rol.value!r} no puede."
            )
        self._transicionar(EstatusIncidencia.CERRADA)

    def rechazar(self, *, rol: Rol, motivo: str) -> None:
        """Rechaza la incidencia. Motivo obligatorio — mismo criterio que el
        rechazo de un cierre de actividad (§11.2, `domain.cierres.reglas`)."""
        if rol not in _ROLES_QUE_RESUELVEN:
            raise ErrorDeIncidencia(
                f"Solo Supervisor o Control de obra rechazan una incidencia; "
                f"el rol {rol.value!r} no puede."
            )
        if not motivo.strip():
            raise ErrorDeIncidencia("Un rechazo requiere motivo.")
        self._transicionar(EstatusIncidencia.RECHAZADA)

    @property
    def bloquea_actividades_activo(self) -> bool:
        """``True`` si la incidencia trae actividades bloqueadas vigentes."""
        return bool(self.bloquea_actividades) and self.impacto.bloquea
