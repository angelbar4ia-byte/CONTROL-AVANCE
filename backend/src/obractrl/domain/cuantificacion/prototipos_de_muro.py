"""Los prototipos de la plantilla de «muro confinado de tabique» (plan de elementos de muro, Ola 4, «plantillas de muro por prototipo»; M-4).

El muro confinado se usa cuando NO hay plano estructural: la plantilla PROPONE (estima) los castillos. Lleva varios castillos y hay una
variante por **prototipo** (Zafiro, Oro, Diamante…) y por **planta** (PB o PA), más una plantilla **global** separada en 1 planta y 2 plantas.

- **El número de plantas de cada prototipo se infiere** del subcapítulo «PLANTA ALTA» del Excel del cerebro (no hay una celda que lo
  diga; el usuario aceptó la inferencia): Zafiro 1.0, Rubí y Jade son de 1 planta; Zafiro Plus, Diamante − y +, y Oro 4.01, de 2.
- El Excel es solo **referencia**: no se carga como datos. Las plantillas de cada prototipo se capturan a mano.

Nada de esto trae precios ni destajos. Funciones y datos puros, sin base de datos.
"""

from __future__ import annotations

from typing import Any

from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = [
    "PLANTAS",
    "PROTOTIPOS",
    "nombre_de_plantilla",
    "plantas_de",
    "prototipo_de",
    "validar_prototipo_y_planta",
]

PLANTAS: tuple[str, ...] = ("PB", "PA")

PROTOTIPOS: tuple[dict[str, Any], ...] = (
    {"clave": "zafiro_1", "nombre": "Zafiro 1.0", "plantas": 1, "global": False, "muro_m2": "279"},
    {"clave": "rubi", "nombre": "Rubí", "plantas": 1, "global": False, "muro_m2": "317.72"},
    {"clave": "jade", "nombre": "Jade", "plantas": 1, "global": False, "muro_m2": "443"},
    {"clave": "zafiro_plus", "nombre": "Zafiro Plus", "plantas": 2, "global": False, "muro_m2": "378"},
    {"clave": "diamante_menos", "nombre": "Diamante −", "plantas": 2, "global": False, "muro_m2": "591"},
    {"clave": "diamante_mas", "nombre": "Diamante +", "plantas": 2, "global": False, "muro_m2": "591"},
    {"clave": "oro_401", "nombre": "Oro 4.01", "plantas": 2, "global": False, "muro_m2": "532.42"},
    {"clave": "global_1", "nombre": "Global · 1 planta", "plantas": 1, "global": True, "muro_m2": None},
    {"clave": "global_2", "nombre": "Global · 2 plantas", "plantas": 2, "global": True, "muro_m2": None},
)
"""Los prototipos y las dos plantillas globales. `plantas` es una INFERENCIA del subcapítulo PLANTA ALTA del Excel (a confirmar);
`muro_m2` es el divisor MURO del Excel (`RESUMEN!C38:I38`, m² de tabique del prototipo entero)."""

_POR_CLAVE: dict[str, dict[str, Any]] = {p["clave"]: p for p in PROTOTIPOS}

def prototipo_de(clave: str) -> dict[str, Any]:
    p = _POR_CLAVE.get(clave)
    if p is None:
        raise ErrorDeCuantificacion(f"Prototipo: {', '.join(_POR_CLAVE)} (no «{clave}»).")
    return p


def plantas_de(clave: str) -> tuple[str, ...]:
    """Las plantas que tiene el prototipo: PB, y PA si es de 2 plantas."""
    return PLANTAS[: int(prototipo_de(clave)["plantas"])]


def validar_prototipo_y_planta(prototipo: str | None, planta: str | None) -> tuple[str | None, str | None]:
    """El prototipo y la planta de una plantilla. Sin prototipo no hay planta. Un prototipo con nombre propio lleva su planta (PB o PA; uno de
    1 planta solo tiene PB). Una plantilla **global** cubre todo el prototipo promedio (1 o 2 plantas) y no lleva planta."""
    if prototipo in (None, ""):
        if planta not in (None, ""):
            raise ErrorDeCuantificacion("La planta (PB o PA) es de un prototipo: elige primero el prototipo.")
        return None, None
    assert prototipo is not None
    p = prototipo_de(prototipo)
    if p["global"]:
        if planta not in (None, ""):
            raise ErrorDeCuantificacion(f"La plantilla «{p['nombre']}» cubre todo el prototipo promedio: no lleva planta.")
        return prototipo, None
    plantas = plantas_de(prototipo)
    if planta in (None, ""):
        raise ErrorDeCuantificacion(f"Di la planta del prototipo {p['nombre']}: {' o '.join(plantas)}.")
    if planta not in plantas:
        raise ErrorDeCuantificacion(
            f"{p['nombre']} tiene {'una planta' if len(plantas) == 1 else 'dos plantas'} ({' y '.join(plantas)}): no hay planta «{planta}»."
        )
    return prototipo, planta


def nombre_de_plantilla(prototipo: str, planta: str | None) -> str:
    """El nombre con que nace la plantilla de confinado de un prototipo y planta (la global no lleva planta)."""
    p = prototipo_de(prototipo)
    return f"Muro confinado · {p['nombre']}" + (f" · {planta}" if planta else "")
