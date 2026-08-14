"""Reglas de captura de avance.

Spec §6 (reglas de negocio clave) · §11.1 (única fuente de verdad).

Estas reglas se definen **una sola vez, aquí**. El backend las aplica de forma
autoritativa; el frontend las refleja para UX desde ``packages/shared``; la BD
las repite como ``CHECK`` porque es la última frontera de la ruta directa de
PowerSync (§12.5). Si una cambia, cambia en los tres lados a la vez.

Reglas:
  * ``cant_programada ≤ cant_base × 1.2``
  * ``cant_ejecutada ≤ cant_programada``
  * ``avance_pct = cant_ejecutada / cant_base × 100``
  * auto-estatus: ``≥ 90% → casi`` · ``> 0 → en_proceso``

Módulo puro: sin BD, sin FastAPI, 100% testeable (§12.11).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from obractrl.domain.shared.diccionario import EstatusActividad
from obractrl.domain.shared.valores import Avance

__all__ = [
    "TOPE_SOBREPROGRAMA",
    "UMBRAL_CASI_PCT",
    "CapturaAvance",
    "ErrorDeCaptura",
    "aplicar_captura",
    "calcular_avance",
    "resolver_estatus",
    "validar_ejecucion",
    "validar_programacion",
]

TOPE_SOBREPROGRAMA = Decimal("1.2")
"""``cant_programada ≤ cant_base × 1.2`` (§6).

A diferencia del IVA o el umbral de desviación (§3.5, §3.6), el §6 escribe
este factor como fórmula fija, no como parámetro configurable de §8.7. Se
deja como argumento con default —no como constante inline— solo por
testabilidad; en producción siempre vale 1.2. La razón de fondo: un `CHECK`
de Postgres no puede leer una tabla de configuración (no admite subconsultas),
así que si este valor fuera configurable, la BD —que es la última frontera en
la ruta offline (§12.5)— no podría replicar la regla real y divergiría en
silencio de lo que aplica la app. Ver `ck_actividad_programada_vs_base` en
``database/migrations/0007_ejecucion_y_avance.sql``, que codifica el mismo 1.2.
"""

UMBRAL_CASI_PCT = Decimal("90")
"""Umbral fijo del auto-estatus ``casi`` (§6). Mismo razonamiento que arriba:
no es un configurable de §8.7, y el trigger `app.actividad_recalcular` de la
BD codifica este mismo 90 a propósito, para no divergir."""


class ErrorDeCaptura(ValueError):
    """Violación de una regla de captura (§6).

    Lleva el ``campo`` para que el borde lo mapee a un error
    ``problem+json`` con la ruta del campo (§11.2).
    """

    def __init__(self, mensaje: str, campo: str) -> None:
        super().__init__(mensaje)
        self.campo = campo


@dataclass(frozen=True, slots=True)
class CapturaAvance:
    """Resultado de aplicar una captura: cantidades ya validadas y derivadas."""

    cant_base: Decimal
    cant_programada: Decimal
    cant_ejecutada: Decimal
    avance: Avance
    estatus: EstatusActividad


def validar_programacion(
    cant_programada: Decimal,
    cant_base: Decimal,
    tope: Decimal = TOPE_SOBREPROGRAMA,
) -> None:
    """``cant_programada ≤ cant_base × tope`` (§6)."""
    if cant_programada < 0:
        raise ErrorDeCaptura(
            "La cantidad programada no puede ser negativa.", "cant_programada"
        )

    maximo = cant_base * tope
    if cant_programada > maximo:
        raise ErrorDeCaptura(
            f"La cantidad programada ({cant_programada}) excede el tope de "
            f"{tope:.0%} sobre la cantidad base ({cant_base}): máximo {maximo}.",
            "cant_programada",
        )


def validar_ejecucion(cant_ejecutada: Decimal, cant_programada: Decimal) -> None:
    """``cant_ejecutada ≤ cant_programada`` (§6)."""
    if cant_ejecutada < 0:
        raise ErrorDeCaptura(
            "La cantidad ejecutada no puede ser negativa.", "cant_ejecutada"
        )

    if cant_ejecutada > cant_programada:
        raise ErrorDeCaptura(
            f"La cantidad ejecutada ({cant_ejecutada}) no puede exceder la "
            f"programada ({cant_programada}). Reprograma primero.",
            "cant_ejecutada",
        )


def calcular_avance(cant_ejecutada: Decimal, cant_base: Decimal) -> Avance:
    """``avance_pct = cant_ejecutada / cant_base × 100`` (§6)."""
    return Avance.de_cantidades(cant_ejecutada, cant_base)


def resolver_estatus(
    avance: Avance,
    estatus_actual: EstatusActividad,
    umbral_casi: Decimal = UMBRAL_CASI_PCT,
) -> EstatusActividad:
    """Auto-estatus: ``≥ 90% → casi`` · ``> 0 → en_proceso`` (§6).

    Los estatus de flujo (``pendiente_cierre``, ``concluida``, ``retrasada``,
    ``extra_catalogo``) los fija el caso de uso correspondiente y **no se
    pisan**: una actividad con cierre solicitado no vuelve sola a ``en_proceso``.
    """
    if not estatus_actual.es_automatico:
        return estatus_actual

    if avance.pct >= umbral_casi:
        return EstatusActividad.CASI
    if avance.esta_iniciado:
        return EstatusActividad.EN_PROCESO
    return EstatusActividad.PROGRAMADA


def aplicar_captura(
    *,
    cant_base: Decimal,
    cant_programada: Decimal,
    cant_ejecutada: Decimal,
    estatus_actual: EstatusActividad = EstatusActividad.PROGRAMADA,
    tope: Decimal = TOPE_SOBREPROGRAMA,
    umbral_casi: Decimal = UMBRAL_CASI_PCT,
) -> CapturaAvance:
    """Valida y deriva una captura completa (§6).

    Es la entrada única del motor de avance: la usan el endpoint web
    (``PATCH /actividades/{id}/avance``) y la conciliación offline del móvil,
    para que ambas rutas apliquen exactamente las mismas reglas (§11.3, B).
    """
    validar_programacion(cant_programada, cant_base, tope)
    validar_ejecucion(cant_ejecutada, cant_programada)

    avance = calcular_avance(cant_ejecutada, cant_base)
    estatus = resolver_estatus(avance, estatus_actual, umbral_casi)

    return CapturaAvance(
        cant_base=cant_base,
        cant_programada=cant_programada,
        cant_ejecutada=cant_ejecutada,
        avance=avance,
        estatus=estatus,
    )
