"""Reglas de evaluación de desempeño (3 niveles).

Spec §6 · §7.8 (control y flujos) · §8.2 (`sujeto_evaluacion`/`nivel_evaluacion`) ·
§11.3 workflow H.

A diferencia de `SolicitudCierre` (`domain.cierres.reglas`), aquí **no hay
máquina de transición de estatus**: cada nivel —``auto``, ``control``,
``final``— es una evaluación independiente que se crea una sola vez y luego
acumula respuestas contra el catálogo de `criterio_evaluacion` (semilla
editable, §8.7). La regla delicada no es "qué transición sigue", sino "quién
puede crear cada nivel, y sobre quién":

    auto    → Residente, solo a sí mismo o a su propia obra.
    control → Control de obra, sobre obra / residente / contratista.
    final   → Super intendente, consolida.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from obractrl.domain.shared.diccionario import NivelEvaluacion, Rol, SujetoEvaluacion

__all__ = [
    "ErrorDeEvaluacion",
    "Evaluacion",
    "RespuestaEvaluacion",
    "calcular_puntaje",
]


class ErrorDeEvaluacion(ValueError):
    """Permiso o dato inválido al crear una evaluación o registrar respuestas (§6)."""


@dataclass(frozen=True, slots=True)
class RespuestaEvaluacion:
    """Respuesta a un criterio del catálogo (`criterio_evaluacion`, §7.8).

    El criterio en sí —nombre, peso, a qué sujeto aplica— es semilla editable
    en BD (§8.7): el dominio no lo conoce, solo referencia su id y usa el
    peso que le pasa el caso de uso para ponderar (`calcular_puntaje`).
    """

    criterio_id: str
    valor: Decimal
    comentario: str | None = None

    def __post_init__(self) -> None:
        if self.valor < 0:
            raise ErrorDeEvaluacion(
                f"El valor de una respuesta no puede ser negativo: {self.valor}."
            )


def calcular_puntaje(
    respuestas: list[RespuestaEvaluacion], pesos: dict[str, Decimal]
) -> Decimal | None:
    """Promedio ponderado por criterio (`criterio_evaluacion.peso`, §7.8).

    Sin respuestas —o sin peso conocido para ninguna— no hay puntaje: se
    devuelve ``None`` y no cero, porque cero afirmaría una calificación
    mínima que nadie dio.
    """
    aportes = [
        (respuesta.valor * pesos[respuesta.criterio_id], pesos[respuesta.criterio_id])
        for respuesta in respuestas
        if respuesta.criterio_id in pesos
    ]
    if not aportes:
        return None
    peso_total = sum((peso for _, peso in aportes), Decimal(0))
    if peso_total == 0:
        return None
    return sum((valor for valor, _ in aportes), Decimal(0)) / peso_total


@dataclass(slots=True)
class Evaluacion:
    """Entidad de dominio de una evaluación de desempeño (§7.8, §11.3 H).

    Sin estatus ni transición (a diferencia de `SolicitudCierre`): se crea
    una vez por nivel y acumula respuestas. `obra_id` ubica la evaluación en
    una obra —lo que RLS usa como alcance de respaldo cuando el sujeto no es
    directamente el usuario (`evaluacion_select`, migración 0012)—; para
    `sujeto_tipo=obra` es, por definición, el mismo id que `sujeto_id`.
    """

    sujeto_tipo: SujetoEvaluacion
    sujeto_id: str
    evaluador_id: str
    nivel: NivelEvaluacion
    periodo: str
    obra_id: str | None = None
    puntaje: Decimal | None = None
    comentarios: str | None = None
    respuestas: list[RespuestaEvaluacion] = field(default_factory=list)

    @classmethod
    def crear(
        cls,
        *,
        nivel: NivelEvaluacion,
        evaluador_id: str,
        rol: Rol,
        sujeto_tipo: SujetoEvaluacion,
        sujeto_id: str,
        periodo: str,
        obra_id: str | None = None,
        obra_residente_id: str | None = None,
    ) -> Evaluacion:
        """Crea una evaluación validando el permiso del rol para ese nivel (§6, §11.3 H).

        `obra_residente_id` es el `residente_id` de `obra_id` ya resuelto por
        el caso de uso —el dominio no consulta la obra, solo compara ids—,
        igual que `SolicitudCierre.solicitar` recibe el `precio_unitario` ya
        resuelto en vez de ir a buscarlo (§11.3 C.1). Solo hace falta para
        validar la autoevaluación de obra (nivel=auto, sujeto=obra).
        """
        if nivel is NivelEvaluacion.AUTO:
            cls._validar_auto(
                rol=rol,
                evaluador_id=evaluador_id,
                sujeto_tipo=sujeto_tipo,
                sujeto_id=sujeto_id,
                obra_residente_id=obra_residente_id,
            )
        elif nivel is NivelEvaluacion.CONTROL:
            cls._validar_control(rol=rol)
        elif nivel is NivelEvaluacion.FINAL:
            cls._validar_final(rol=rol)
        else:  # pragma: no cover - NivelEvaluacion no tiene más miembros (§8.2)
            raise ErrorDeEvaluacion(f"Nivel de evaluación desconocido: {nivel!r}.")

        return cls(
            sujeto_tipo=sujeto_tipo,
            sujeto_id=sujeto_id,
            evaluador_id=evaluador_id,
            nivel=nivel,
            periodo=periodo,
            obra_id=obra_id,
        )

    @staticmethod
    def _validar_auto(
        *,
        rol: Rol,
        evaluador_id: str,
        sujeto_tipo: SujetoEvaluacion,
        sujeto_id: str,
        obra_residente_id: str | None,
    ) -> None:
        """Auto: solo el Residente, y solo a sí mismo o a su obra (§6, §11.3 H.1)."""
        if rol is not Rol.RESIDENTE:
            raise ErrorDeEvaluacion(
                f"Solo el Residente se autoevalúa (nivel=auto); "
                f"el rol {rol.value!r} no puede."
            )
        if sujeto_tipo is SujetoEvaluacion.RESIDENTE:
            if sujeto_id != evaluador_id:
                raise ErrorDeEvaluacion(
                    "El Residente solo puede autoevaluarse a sí mismo, no a "
                    "otro residente."
                )
        elif sujeto_tipo is SujetoEvaluacion.OBRA:
            if obra_residente_id != evaluador_id:
                raise ErrorDeEvaluacion(
                    "El Residente solo puede autoevaluar su propia obra."
                )
        else:
            raise ErrorDeEvaluacion(
                f"Una autoevaluación (nivel=auto) es a sí mismo o a su obra, "
                f"no a {sujeto_tipo.value!r}."
            )

    @staticmethod
    def _validar_control(*, rol: Rol) -> None:
        """Control: Control de obra evalúa obra + residente + contratista (§11.3 H.2)."""
        if rol is not Rol.CONTROL_OBRA:
            raise ErrorDeEvaluacion(
                f"Solo Control de obra evalúa en nivel=control; "
                f"el rol {rol.value!r} no puede."
            )

    @staticmethod
    def _validar_final(*, rol: Rol) -> None:
        """Final: solo el Super intendente consolida (§11.3 H.3)."""
        if rol is not Rol.SUPER_INTENDENTE:
            raise ErrorDeEvaluacion(
                f"Solo el Super intendente consolida en nivel=final; "
                f"el rol {rol.value!r} no puede."
            )

    def agregar_respuestas(
        self,
        respuestas: list[RespuestaEvaluacion],
        *,
        usuario_id: str,
        pesos: dict[str, Decimal],
    ) -> None:
        """Adjunta respuestas contra el catálogo y recalcula el puntaje (§7.8).

        Solo quien registró la evaluación puede responderla —la misma regla
        que impone la política de escritura de `evaluacion_respuesta`
        (`evaluador_id = current_usuario_id()`, migración 0012); se repite
        aquí para dar un error de negocio legible en vez de que la petición
        reviente contra la política de RLS.
        """
        if usuario_id != self.evaluador_id:
            raise ErrorDeEvaluacion(
                "Solo quien registró la evaluación puede agregar sus respuestas."
            )
        if not respuestas:
            raise ErrorDeEvaluacion("No hay respuestas que agregar.")

        vistos = {r.criterio_id for r in self.respuestas}
        for respuesta in respuestas:
            if respuesta.criterio_id in vistos:
                raise ErrorDeEvaluacion(
                    f"El criterio {respuesta.criterio_id} ya tiene respuesta "
                    f"en esta evaluación."
                )
            vistos.add(respuesta.criterio_id)

        self.respuestas.extend(respuestas)
        self.puntaje = calcular_puntaje(self.respuestas, pesos)
