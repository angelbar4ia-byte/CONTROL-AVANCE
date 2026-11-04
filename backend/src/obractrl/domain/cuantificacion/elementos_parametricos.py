"""Elementos paramétricos (D-602, D-604): una pieza con medidas, armado y estribos de la que salen concreto, acero,
estribos, alambre de amarre y cimbra. Es la «muestra» de la receta de un concepto.

La unidad de cálculo de la muestra depende del elemento: **pieza** (castillo, zapata), **metro lineal** (trabe y
cadenas) o **m²** (losa maciza). La receta es la de UNA muestra; el trazo aporta 1 pieza, sus metros o sus m².
La cimbra se da **por número de lados** (4, 3 o 2 en un castillo según esté aislado, junto a un vano o en un muro
continuo); el diseño de la cimbra (forro, usos, alambre) es un sub-elemento que llega aparte (D-603).

Función pura, sin base de datos: las constantes físicas son las de `CONSTANTE_FISICA` (D-326).
"""

from __future__ import annotations

import math
from typing import Any

from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = [
    "PARAMETROS_POR_TIPO",
    "PESO_ALAMBRE_KG_M",
    "PESO_VARILLA_KG_M",
    "TIPOS_DE_ELEMENTO",
    "UNIDAD_DE_CALCULO",
    "VARA_COMERCIAL_M",
    "ErrorDeElementoParametrico",
    "normalizar_parametros",
    "receta",
]

TIPOS_DE_ELEMENTO = ("castillo", "lineal", "zapata", "losa")
UNIDAD_DE_CALCULO = {"castillo": "pza", "lineal": "ml", "zapata": "pza", "losa": "m²"}

VARA_COMERCIAL_M = 12.0
# kg por metro por número de varilla (octavos de pulgada) y por calibre de alambre recocido.
PESO_VARILLA_KG_M = {2: 0.249, 3: 0.560, 4: 0.994, 5: 1.552, 6: 2.235, 8: 3.973}
PESO_ALAMBRE_KG_M = {14: 0.0275, 16: 0.0168, 18: 0.0095, 20: 0.0049}

_AMARRE = {"am_l": 0.3, "am_cal": 18}

# (valor por defecto, mínimo exclusivo/inclusivo se valida abajo). Las claves enteras llevan `int`.
PARAMETROS_POR_TIPO: dict[str, dict[str, Any]] = {
    "castillo": {
        "largo": 0.15, "ancho": 0.15, "alto": 2.6, "n_var": 4, "no_var": 4, "sep": 0.2, "no_est": 2,
        "gancho": 0.1, "rec": 0.025, "desp": 5.0, **_AMARRE,
    },
    "lineal": {
        "ancho": 0.2, "alto": 0.4, "n_sup": 3, "no_sup": 4, "n_inf": 3, "no_inf": 4, "sep": 0.2, "no_est": 2,
        "gancho": 0.1, "rec": 0.025, "desp": 5.0, "lados": 3, **_AMARRE,
    },
    "zapata": {
        "largo": 1.2, "ancho": 1.2, "alto": 0.25, "sep_l": 0.15, "sep_a": 0.15, "no_par": 4, "rec": 0.05,
        "gancho": 0.15, "desp": 5.0, **_AMARRE,
    },
    "losa": {"alto": 0.1, "sep_x": 0.25, "sep_y": 0.25, "no_par": 3, "lechos": 1, "desp": 5.0, **_AMARRE},
}

_ENTEROS = {"n_var", "n_sup", "n_inf", "lechos", "lados", "am_cal", "no_var", "no_est", "no_sup", "no_inf", "no_par"}
_NUMEROS_DE_VARILLA = {"no_var", "no_est", "no_sup", "no_inf", "no_par"}
_PUEDEN_SER_CERO = {"rec", "gancho", "desp"}


class ErrorDeElementoParametrico(ErrorDeCuantificacion):
    """Un parámetro que no vale: la receta no se puede calcular con él."""


def normalizar_parametros(tipo: str, parametros: dict[str, Any]) -> dict[str, Any]:
    """Completa con los valores por defecto del tipo y valida; devuelve solo las claves del tipo."""
    if tipo not in PARAMETROS_POR_TIPO:
        raise ErrorDeElementoParametrico(f"Tipo de elemento desconocido: {tipo}.")
    base = PARAMETROS_POR_TIPO[tipo]
    desconocidos = sorted(set(parametros) - set(base))
    if desconocidos:
        raise ErrorDeElementoParametrico(f"Parámetros que {tipo} no tiene: {', '.join(desconocidos)}.")
    salida: dict[str, Any] = {}
    for clave, defecto in base.items():
        crudo = parametros.get(clave, defecto)
        try:
            valor = float(crudo)
        except (TypeError, ValueError):
            raise ErrorDeElementoParametrico(f"«{clave}» debe ser un número.") from None
        if not math.isfinite(valor):
            raise ErrorDeElementoParametrico(f"«{clave}» debe ser un número.")
        if clave in _ENTEROS:
            if valor != int(valor):
                raise ErrorDeElementoParametrico(f"«{clave}» debe ser un entero.")
            valor = int(valor)
        if valor < 0 or (valor == 0 and clave not in _PUEDEN_SER_CERO):
            raise ErrorDeElementoParametrico(f"«{clave}» debe ser mayor que cero.")
        if clave in _NUMEROS_DE_VARILLA and valor not in PESO_VARILLA_KG_M:
            raise ErrorDeElementoParametrico(f"«{clave}» no es un número de varilla conocido ({sorted(PESO_VARILLA_KG_M)}).")
        if clave == "am_cal" and valor not in PESO_ALAMBRE_KG_M:
            raise ErrorDeElementoParametrico(f"El calibre {valor} no está en la tabla ({sorted(PESO_ALAMBRE_KG_M)}).")
        if clave == "lados" and valor not in (2, 3):
            raise ErrorDeElementoParametrico("Una trabe o cadena tiene 3 lados de cimbra (fondo y costados) o 2 (costados).")
        if clave == "lechos" and valor not in (1, 2):
            raise ErrorDeElementoParametrico("La losa lleva 1 o 2 lechos de acero.")
        salida[clave] = valor
    return salida


def receta(tipo: str, parametros: dict[str, Any]) -> dict[str, Any]:
    """Lo que lleva UNA muestra (una pieza, un metro o un m²).

    Devuelve `concreto` (m³), `acero_kg`, `estribos_kg`, `n_estribos`, `long_estribo_m`, `n_amarres`,
    `alambre_kg`, `varas` (comerciales de 12 m) y `cimbra_m2` por número de lados.
    """
    p = normalizar_parametros(tipo, parametros)
    pv = PESO_VARILLA_KG_M
    pa = PESO_ALAMBRE_KG_M[p["am_cal"]]
    f = 1 + p["desp"] / 100

    if tipo == "castillo":
        a, largo, ancho = p["alto"], p["largo"], p["ancho"]
        cortes = max(1, math.floor(VARA_COMERCIAL_M / a))
        n_est = math.ceil(a / p["sep"]) + 1
        l_est = 2 * ((ancho - 2 * p["rec"]) + (largo - 2 * p["rec"])) + p["gancho"]
        n_am = p["n_var"] * n_est
        return {
            "unidad": "pza",
            "concreto": largo * ancho * a,
            "acero_kg": p["n_var"] * a * pv[p["no_var"]] * f,
            "estribos_kg": n_est * l_est * pv[p["no_est"]],
            "n_estribos": n_est,
            "long_estribo_m": l_est,
            "n_amarres": n_am,
            "alambre_kg": n_am * p["am_l"] * pa,
            "varas": p["n_var"] / cortes,
            "cimbra_m2": {4: 2 * (largo + ancho) * a, 3: (2 * largo + ancho) * a, 2: 2 * largo * a},
        }
    if tipo == "lineal":
        b, h = p["ancho"], p["alto"]
        n_est = 1 / p["sep"]
        l_est = 2 * ((b - 2 * p["rec"]) + (h - 2 * p["rec"])) + p["gancho"]
        n_v = p["n_sup"] + p["n_inf"]
        n_am = n_v * n_est
        return {
            "unidad": "ml",
            "concreto": b * h,
            "acero_kg": (p["n_sup"] * pv[p["no_sup"]] + p["n_inf"] * pv[p["no_inf"]]) * f,
            "estribos_kg": n_est * l_est * pv[p["no_est"]],
            "n_estribos": n_est,
            "long_estribo_m": l_est,
            "n_amarres": n_am,
            "alambre_kg": n_am * p["am_l"] * pa,
            "varas": n_v / VARA_COMERCIAL_M,
            "cimbra_m2": {3: 2 * h + b, 2: 2 * h},
        }
    if tipo == "zapata":
        largo, ancho, h, r, g = p["largo"], p["ancho"], p["alto"], p["rec"], p["gancho"]
        n_a = math.ceil((ancho - 2 * r) / p["sep_a"] - 1e-9) + 1
        n_l = math.ceil((largo - 2 * r) / p["sep_l"] - 1e-9) + 1
        long_var = n_a * (largo - 2 * r + 2 * g) + n_l * (ancho - 2 * r + 2 * g)
        return {
            "unidad": "pza",
            "concreto": largo * ancho * h,
            "acero_kg": long_var * pv[p["no_par"]] * f,
            "estribos_kg": 0.0,
            "n_estribos": 0,
            "long_estribo_m": 0.0,
            "n_amarres": n_a * n_l,
            "alambre_kg": n_a * n_l * p["am_l"] * pa,
            "varas": long_var / VARA_COMERCIAL_M,
            "cimbra_m2": {4: 2 * (largo + ancho) * h},
        }
    ml = p["lechos"] * (1 / p["sep_x"] + 1 / p["sep_y"])
    n_am = p["lechos"] * (1 / p["sep_x"]) * (1 / p["sep_y"])
    return {
        "unidad": "m²",
        "concreto": p["alto"],
        "acero_kg": ml * pv[p["no_par"]] * f,
        "estribos_kg": 0.0,
        "n_estribos": 0,
        "long_estribo_m": 0.0,
        "n_amarres": n_am,
        "alambre_kg": n_am * p["am_l"] * pa,
        "varas": ml / VARA_COMERCIAL_M,
        "cimbra_m2": {1: 1.0},
    }
