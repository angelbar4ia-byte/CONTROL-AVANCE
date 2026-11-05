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

__all__ = ["ALTURA_POR_DEFECTO_M", "CARAS_POR_DEFECTO", "ParteDeAltura", "altura_efectiva", "factor_de_muro"]

ALTURA_POR_DEFECTO_M = Decimal("2.6")
CARAS_POR_DEFECTO = 2


@dataclass(frozen=True, slots=True)
class ParteDeAltura:
    nombre: str
    desde_m: Decimal
    hasta_m: Decimal
    suma: bool = True


def altura_efectiva(altura_m: Decimal | None, partes: Sequence[ParteDeAltura] | None) -> Decimal:
    """La altura que suma a la cantidad: la de las partes que suman, o la altura única (2.6 m si no hay ninguna)."""
    if partes:
        for p in partes:
            if p.desde_m < 0 or p.hasta_m <= p.desde_m:
                raise ErrorDeCuantificacion(f"La parte «{p.nombre}» debe ir de un «desde» a un «hasta» mayor.")
        return sum((p.hasta_m - p.desde_m for p in partes if p.suma), Decimal(0))
    return altura_m if altura_m is not None else ALTURA_POR_DEFECTO_M


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
