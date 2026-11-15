"""Muro de piedra sobre un trazo con pendiente (Q38): altura inicial en el primer punto, corona de nivel constante.

El trazo se mide en planta (`longitud_m`). La **altura inicial** es la del primer punto; la corona va a **nivel
constante**, de modo que la altura del muro sigue el terreno: `H(s) = H0 + pendiente ÷ 100 × s` (pendiente positiva: el
terreno baja y el muro crece hacia el final; negativa: decrece). El largo real del muro es el inclinado,
`L × √(1 + p²)`. Se parte el trazo en rebanadas de unos 0.50 m (hasta 200) y cada una se calcula con la función del
elemento por metro de trazo (`calcular(altura)`), así que el trazo **reutiliza** el dominio de cada muro en lugar de
duplicarlo. Función pura, sin base de datos.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = ["ALTURA_MINIMA_M", "ErrorDeTrazo", "calcular_trazo"]

ALTURA_MINIMA_M = 0.1
PASO_M = 0.5
REBANADAS_MAXIMAS = 200


class ErrorDeTrazo(ErrorDeCuantificacion):
    """Un dato del trazo que no vale."""


def calcular_trazo(
    calcular: Callable[[float], dict[str, Any]],
    *,
    longitud_m: float,
    altura_inicial_m: float,
    pendiente_pct: float = 0.0,
) -> dict[str, Any]:
    if not (0 < longitud_m <= 500):
        raise ErrorDeTrazo("El largo del trazo va entre 0 y 500 m.")
    if not (altura_inicial_m > 0):
        raise ErrorDeTrazo("La altura inicial debe ser mayor que cero.")
    if not (-100 <= pendiente_pct <= 100):
        raise ErrorDeTrazo("La pendiente va entre -100 % y 100 %.")

    factor = math.sqrt(1 + (pendiente_pct / 100) ** 2)
    largo_real = longitud_m * factor
    n = max(1, min(REBANADAS_MAXIMAS, math.ceil(longitud_m / PASO_M - 1e-9)))
    ds = largo_real / n

    muro = dentellon = total = 0.0
    h_min, h_max = math.inf, 0.0
    perfil: list[dict[str, float]] = []
    por_clave: dict[str, dict[str, Any]] = {}
    recortada = False
    for i in range(n):
        s = (i + 0.5) / n * longitud_m
        h_crudo = altura_inicial_m + pendiente_pct / 100 * s
        h = max(ALTURA_MINIMA_M, h_crudo)
        recortada = recortada or h_crudo < ALTURA_MINIMA_M
        r = calcular(h)
        v = r["volumen"]
        muro += v["muro_m3_ml"] * ds
        dentellon += v["dentellon_m3_ml"] * ds
        total += v["total_m3_ml"] * ds
        for ins in r.get("insumos_por_m3", []):
            acum = por_clave.setdefault(
                ins["clave"],
                {k: ins[k] for k in ("clave", "descripcion", "unidad", "provisional")}
                | {"total": 0.0},
            )
            acum["total"] += ins["cantidad"] * v["total_m3_ml"] * ds
        h_min, h_max = min(h_min, h), max(h_max, h)
        perfil.append({"s_m": s, "altura_m": h})

    advertencias: list[str] = []
    if recortada:
        advertencias.append(
            f"La pendiente lleva la altura por debajo de {ALTURA_MINIMA_M:g} m: se usó {ALTURA_MINIMA_M:g} m en esas rebanadas."
        )
    if h_min < 1.0:
        advertencias.append("Parte del trazo queda con menos de 1.00 m de altura.")

    return {
        "longitud_m": longitud_m,
        "longitud_real_m": largo_real,
        "altura_inicial_m": altura_inicial_m,
        "pendiente_pct": pendiente_pct,
        "altura_final_m": max(
            ALTURA_MINIMA_M, altura_inicial_m + pendiente_pct / 100 * longitud_m
        ),
        "altura_minima_m": h_min,
        "altura_maxima_m": h_max,
        "rebanadas": n,
        "volumen": {
            "muro_m3": muro,
            "dentellon_m3": dentellon,
            "total_m3": total,
        },
        "insumos": [
            {
                "clave": a["clave"],
                "descripcion": a["descripcion"],
                "unidad": a["unidad"],
                "provisional": a["provisional"],
                "cantidad_total": a["total"],
                "cantidad_por_m3": a["total"] / total if total > 0 else 0.0,
            }
            for a in por_clave.values()
        ],
        "perfil": perfil,
        "advertencias": advertencias,
    }
