"""Muro de cimentación de piedra (CIM-01010): categoría «Muros de cimentación» › subcategoría «Mampostería de piedra».

Se mide por **metro lineal de trazo** y se paga con el mismo concepto por m³ que el muro de contención, el **MCT-01011**
(piedra de cerro asentada con mortero 1:6). Reutiliza del dominio de `muro_contencion` el concepto, el abundamiento de la
piedra, los consumos por m³ de mampostería y el dentellón del Cuadro 1; lo que cambia es la **sección**.

Reglas (mockup de muros paramétricos; norma de mampostería sección 8.4 «Cimientos», figura 8.1; respuestas Q38, Q39, Q43,
Q45, Q46 y Q47):

- La corona es **siempre de 40 cm**, sin importar la altura.
- La base sale del **escarpio 1.5 : 1** (1.5 verticales por 1 horizontal, unos 56.3° desde la horizontal), que no es editable:
  `base = corona + caras × altura ÷ 1.5`, con una cara inclinada (cimiento de lindero: la otra cara, el trasdós del lado del
  relleno, es vertical) o dos (simétrico). La base se redondea al centímetro, como lo hace el mockup (a 2.00 m: 40 + 133 = 173).
- Con una cara inclinada, la cara **vista** es la inclinada y el trasdós es vertical. No lleva dren, ni filtro de grava, ni
  carpeta (así lo dice el mockup; ver `PENDIENTES`).
- Dentellón opcional, **desde 2.00 m**: los mismos 0.21 m³ por metro del Cuadro 1.
- Corona y base se pueden fijar a mano; si el escarpio resultante es más tendido que 1.5 : 1 no se rechaza: se avisa.

Función pura, sin base de datos.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from obractrl.domain.cuantificacion.muro_contencion import (
    CLAVE_CONCEPTO,
    DENTELLON,
    DESCRIPCION_CONCEPTO,
    contraste_con_el_concepto,
    volumen_de_mamposteria,
)
from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = [
    "CLAVE_ELEMENTO",
    "CORONA_M",
    "ESCARPIO_MINIMO",
    "FUENTE_ESCARPIO",
    "PENDIENTES",
    "EntradaMuroDeCimentacion",
    "ErrorDeMuroDeCimentacion",
    "calcular_muro_de_cimentacion",
]

CLAVE_ELEMENTO = "CIM-01010"
CORONA_M = 0.40
ESCARPIO_MINIMO = 1.5

FUENTE_ESCARPIO = (
    "Norma de mampostería, sección 8.4 «Cimientos», figura 8.1: en cimientos de piedra braza la pendiente de las caras "
    "inclinadas, medida desde la arista de la dala o muro, no será menor que 1.5 (vertical) : 1 (horizontal). Título y año "
    "de la norma por confirmar."
)

PENDIENTES: tuple[dict[str, str], ...] = (
    {
        "clave": "Q42",
        "texto": "La sección 8.4 también pide dalas de concreto reforzado, castillos empotrados al menos 400 mm y cimientos perpendiculares a separaciones máximas (tabla 8.1), o revisar la torsión en cimientos trapeciales de lindero. El elemento no los calcula: se miden aparte.",
    },
    {
        "clave": "Q47",
        "texto": "El dentellón (desde 2.00 m, 0.21 m³ por metro) se confirmó para el muro de piedra. En el cimiento queda como opción apagada por defecto, como en el mockup; falta confirmar si el cimiento lo lleva siempre.",
    },
    {
        "clave": "Q39",
        "texto": "Con una cara inclinada, la vertical es el trasdós (lado del relleno) y la inclinada la cara vista. El mockup no lleva dren ni filtro de grava en el cimiento; falta confirmar si el filtro de grava detrás del trasdós también aplica aquí.",
    },
    {
        "clave": "Q38",
        "texto": "En un trazo con pendiente la altura inicial se mide en el primer punto y la corona va a nivel constante: la altura sigue el terreno.",
    },
    {
        "clave": "Q107",
        "texto": "El muro de cimentación reemplaza a la zapata corrida cuando el cimiento es de mampostería: un mismo tramo se mide con uno solo de los dos. Es regla de uso, el elemento no hace la exclusión.",
    },
    {
        "clave": "Q35",
        "texto": "El muro de cimentación todavía no se coloca desde el Cuantificador: por ahora solo existe en Elementos.",
    },
    {
        "clave": "estabilidad",
        "texto": "El elemento no calcula volteo ni deslizamiento: la estabilidad la valida el estructurista.",
    },
)


class ErrorDeMuroDeCimentacion(ErrorDeCuantificacion):
    """Un parámetro del muro de cimentación que no vale."""


@dataclass(frozen=True)
class EntradaMuroDeCimentacion:
    """Lo que se captura del muro de cimentación. La altura en **metros**."""

    alto_m: float
    caras: int = 1
    dentellon: bool = False
    corona_m: float | None = None
    base_m: float | None = None


def _validar(e: EntradaMuroDeCimentacion) -> None:
    if not (e.alto_m > 0) or e.alto_m > 20:
        raise ErrorDeMuroDeCimentacion(
            "La altura se captura en metros y debe ser mayor que cero (máximo 20 m)."
        )
    if e.caras not in (1, 2):
        raise ErrorDeMuroDeCimentacion(
            "Las caras inclinadas son 1 (cimiento de lindero) o 2 (simétrico)."
        )
    for nombre, valor in (("corona", e.corona_m), ("base", e.base_m)):
        if valor is not None and not (0 < valor <= 10):
            raise ErrorDeMuroDeCimentacion(
                f"La {nombre} se captura en metros y debe estar entre 0 y 10."
            )


def _al_centimetro(m: float) -> float:
    return math.floor(m * 100 + 0.5 + 1e-9) / 100


def calcular_muro_de_cimentacion(e: EntradaMuroDeCimentacion) -> dict[str, Any]:
    """Sección, volumen, escarpio y contraste con el concepto, por metro de trazo."""
    _validar(e)
    alto = e.alto_m
    manual = e.corona_m is not None or e.base_m is not None
    corona = e.corona_m if e.corona_m is not None else CORONA_M
    base = (
        e.base_m
        if e.base_m is not None
        else _al_centimetro(corona + e.caras * alto / ESCARPIO_MINIMO)
    )
    if base < corona:
        raise ErrorDeMuroDeCimentacion("La base no puede ser menor que la corona.")

    vm = (corona + base) / 2 * alto
    aplica_dentellon = bool(e.dentellon) and DENTELLON["desde_H"] - 1e-9 <= alto
    den = DENTELLON["volumen_m3"] if aplica_dentellon else 0.0

    # Escarpio real: desvío horizontal por cara por cada 1 de altura. Debe ser ≤ 1 ÷ 1.5.
    desvio = (base - corona) / (e.caras * alto)
    cumple = desvio <= 1 / ESCARPIO_MINIMO + 1e-9
    escarpio_real = (1 / desvio) if desvio > 1e-12 else None

    advertencias: list[str] = []
    if not cumple:
        advertencias.append(
            f"El escarpio resultante ({escarpio_real:.2f} : 1) es más tendido que el mínimo de {ESCARPIO_MINIMO:g} : 1 "
            "de la norma 8.4: revisar la base o la corona."
            if escarpio_real is not None
            else "El escarpio no cumple la norma 8.4."
        )
    if e.dentellon and not aplica_dentellon:
        advertencias.append(
            "El dentellón aplica desde 2.00 m de altura: con esta altura no se agrega."
        )
    if manual:
        advertencias.append(
            "Corona o base ajustadas a mano: ya no salen de la regla del escarpio."
        )

    return {
        "clave": CLAVE_ELEMENTO,
        "unidad": "m³ por metro lineal de trazo",
        "concepto": {
            "clave": CLAVE_CONCEPTO,
            "descripcion": DESCRIPCION_CONCEPTO,
            "unidad": "m3",
        },
        "seccion": {
            "alto_m": alto,
            "corona_m": corona,
            "base_m": base,
            "espesor_medio_m": (corona + base) / 2,
            "caras": e.caras,
            "manual": manual,
        },
        "escarpio": {
            "minimo": ESCARPIO_MINIMO,
            "angulo_minimo_grados": math.degrees(math.atan(ESCARPIO_MINIMO)),
            "real": escarpio_real,
            "angulo_real_grados": (
                math.degrees(math.atan(escarpio_real)) if escarpio_real else None
            ),
            "cumple": cumple,
            "fuente": FUENTE_ESCARPIO,
        },
        "volumen": volumen_de_mamposteria(vm, den),
        "dentellon": {
            "aplica": aplica_dentellon,
            "opcion": bool(e.dentellon),
            "b2_m": DENTELLON["b2"],
            "b1_m": DENTELLON["b1"],
            "h_m": DENTELLON["h"],
        },
        "contraste": contraste_con_el_concepto(),
        "advertencias": advertencias,
    }
