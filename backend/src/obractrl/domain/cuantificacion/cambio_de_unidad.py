"""Cambiar la unidad de un concepto a otro tipo de medición (D-623). Reglas puras, sin base de datos.

- Solo cambia de «tipo» lo que cruza dimensión (conteo, longitud, área): m → ml o m² → m² no piden nada.
- La equivalencia es «unidades nuevas por una antigua» (48 m² por pieza) y las cantidades de la matriz se **dividen**
  entre ella; si la unidad nueva es de conteo (m² → pieza) es «antiguas por una nueva» y se **multiplican**.
- Los precios unitarios de los insumos no cambian; las cantidades sí.
- Un trazo ya medido pasa a la medida que cabe en la unidad nueva.
"""

from __future__ import annotations

from decimal import Decimal

from obractrl.domain.cuantificacion.muro import ALTURA_POR_DEFECTO_M, CARAS_POR_DEFECTO
from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = ["TIPOS_CONVERTIBLES", "cruza_de_tipo", "divisor_de_cantidades", "medida_para", "ya_mide_lo_que_corresponde"]

# Volumen y lo derivado (kg, ton, litros) tienen su propia conversión (espesor, peso): no pasan por aquí.
TIPOS_CONVERTIBLES = frozenset({"conteo", "lineal", "area"})


def cruza_de_tipo(anterior: str | None, nuevo: str | None) -> bool:
    """¿Cambiar de una unidad a otra cruza de tipo? Una unidad que no se reconoce cuenta como otro tipo."""
    return anterior != nuevo


def divisor_de_cantidades(tipo_anterior: str | None, tipo_nuevo: str, equivalencia: Decimal) -> Decimal:
    """Entre cuánto se dividen las cantidades de la matriz: la equivalencia, o su inverso si la unidad nueva es un conteo."""
    if tipo_nuevo not in TIPOS_CONVERTIBLES or (tipo_anterior is not None and tipo_anterior not in TIPOS_CONVERTIBLES):
        raise ErrorDeCuantificacion(
            "Este cambio no se hace con una equivalencia: el volumen y lo que se pesa (kg, ton) se convierten con "
            "su espesor o su peso."
        )
    if equivalencia <= 0:
        raise ErrorDeCuantificacion("La equivalencia debe ser mayor que cero.")
    if tipo_nuevo == "conteo":
        return Decimal(1) / equivalencia
    return equivalencia


def medida_para(
    tipo_nuevo: str, geometria: str, con_grosor: bool, altura_base: Decimal = ALTURA_POR_DEFECTO_M
) -> tuple[str, Decimal] | None:
    """La medida y el factor con que un trazo mide un concepto del tipo nuevo, o `None` si no cabe (un punto en m²).

    `geometria`: `punto`, `linea` o `area`. Una línea sin grosor sobre un concepto en m² mide su largo × su altura base
    (la del artefacto o la de la herramienta, 3.00 m de partida; no el driver) × las caras por defecto, como en la pantalla. Antes el factor
    era 5.2 fijo (2.6 m × 2); la altura de un enlace que ya existe no se toca aquí (`ya_mide_lo_que_corresponde`, Q1).
    """
    if tipo_nuevo == "conteo":
        return ("conteo", Decimal(1))
    if tipo_nuevo == "area":
        if geometria == "area":
            return ("area", Decimal(1))
        if geometria == "linea":
            return ("area", Decimal(1)) if con_grosor else ("longitud", altura_base * CARAS_POR_DEFECTO)
        return None
    if tipo_nuevo == "lineal":
        if geometria == "area":
            return ("perimetro", Decimal(1))
        if geometria == "linea":
            return ("longitud", Decimal(1))
        return None
    return None


def ya_mide_lo_que_corresponde(
    medida: tuple[str, Decimal] | None, medida_actual: str, factor_actual: Decimal
) -> bool:
    """Si el enlace que ya tiene el trazo sirve para el concepto nuevo y no hay que rehacerlo.

    Es el mismo si mide lo mismo con el mismo factor. Y una línea que ya mide su largo × una altura propia (factor mayor que 1:
    la que traía al trazarse) la CONSERVA aunque el driver de hoy sea otro: lo guardado no se recalcula (Q1).
    """
    if medida is None:
        return False
    if medida == (medida_actual, factor_actual):
        return True
    return medida[0] == "longitud" and medida[1] != 1 and medida_actual == "longitud" and factor_actual > 1
