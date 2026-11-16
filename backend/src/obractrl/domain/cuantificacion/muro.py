"""El muro como cantidad: largo × altura × caras (cerebro D-627).

Una línea medida en m² suma su largo por la altura del muro por las caras que se cuentan. La altura es una sola o va
**por partes**: cada parte va de `desde_m` a `hasta_m` y puede no sumar a la cantidad (un cerramiento cuenta para la
altura del muro pero no se aplana). Funciones puras.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = [
    "ALTURA_ANTERIOR_M",
    "ALTURA_POR_DEFECTO_M",
    "CARAS_POR_DEFECTO",
    "ParteDeAltura",
    "altura_efectiva",
    "factor_de_muro",
]

ALTURA_POR_DEFECTO_M = Decimal("3.00")
"""El valor de partida del driver `altura_estandar` (M-9). Con una obra se lee el driver vigente de esa obra (Paramétrico, 0134);
esta constante solo vale donde no hay obra a la mano."""
ALTURA_ANTERIOR_M = Decimal("2.6")
"""La altura que contaba por defecto todo lo guardado antes del driver. Q1: lo ya guardado la CONSERVA; solo lo que nace sin
altura sigue al driver. La conversión de un enlace guardado sin `alt` la sigue usando (`app.cantidad_conversion`, 0115)."""
CARAS_POR_DEFECTO = 2


@dataclass(frozen=True, slots=True)
class ParteDeAltura:
    nombre: str
    desde_m: Decimal
    hasta_m: Decimal
    suma: bool = True
    # Ubicación por parte (0133, M-6): qué cara es exterior o interior (A = izquierda del sentido de dibujo, B = derecha),
    # el rol de la parte (cuerpo, enrase, pretil, cadena) y la cadena que la define. Opcionales: sin ellas la parte no dice caras.
    cara_a: str | None = None
    cara_b: str | None = None
    rol: str | None = None
    elemento_ref: str | None = None


def altura_efectiva(
    altura_m: Decimal | None, partes: Sequence[ParteDeAltura] | None, estandar_m: Decimal | None = None
) -> Decimal:
    """La altura que suma a la cantidad: la de las partes que suman, o la altura única; sin ninguna, la altura estándar de la
    obra (el driver `altura_estandar`; 3.00 m si no se da)."""
    if partes:
        for p in partes:
            if p.desde_m < 0 or p.hasta_m <= p.desde_m:
                raise ErrorDeCuantificacion(f"La parte «{p.nombre}» debe ir de un «desde» a un «hasta» mayor.")
        return sum((p.hasta_m - p.desde_m for p in partes if p.suma), Decimal(0))
    if altura_m is not None:
        return altura_m
    return estandar_m if estandar_m is not None else ALTURA_POR_DEFECTO_M


def factor_de_muro(altura: Decimal, caras: int) -> Decimal:
    """El factor del enlace de largo de una línea en m²: altura × caras."""
    if caras not in (1, 2):
        raise ErrorDeCuantificacion("Un muro suma una o dos caras.")
    if altura <= 0:
        raise ErrorDeCuantificacion("La altura que suma debe ser mayor que cero.")
    factor = altura * caras
    if factor == 1:
        raise ErrorDeCuantificacion(
            "Esa altura × caras equivale a un metro lineal: cámbiala (con factor 1 la línea se mide en metros)."
        )
    return factor
