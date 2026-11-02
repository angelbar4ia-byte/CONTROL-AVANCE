"""De la unidad de un concepto al tipo con que se mide (espejo de `frontend/src/cuantificador/tipos.ts`).

El concepto manda: su unidad dice si se mide con un **área** (m²), una **longitud** (m, ml) o un **conteo**
(pza, lote…); un m³ se mide con un área y un espesor; kg y ton se **derivan** de un conteo por su peso. Cambiar
la unidad de un concepto cambia su tipo, y con él qué medidas de trazo le caben: `medidas_que_caben` es lo
que el caso de uso compara contra lo que ya está medido para no dejar un concepto incoherente.

Módulo puro, sin infraestructura (§12.11).
"""

from __future__ import annotations

import re
import unicodedata

__all__ = ["medidas_que_caben", "tipo_de_unidad"]

_AREA = {"m2", "mt2", "mts2", "metro2", "metros2", "metrocuadrado", "metroscuadrados"}
_LINEAL = {
    "m",
    "ml",
    "mt",
    "mts",
    "metro",
    "metros",
    "metrolineal",
    "metroslineales",
    "mlineal",
}
_VOLUMEN = {"m3", "mt3", "mts3", "metro3", "metros3", "metrocubico", "metroscubicos"}
_CONTEO = {
    "pza", "pzas", "pz", "pzs", "pieza", "piezas", "lote", "lotes", "jgo", "jgos", "juego", "juegos",
    "salida", "salidas", "par", "pares", "u", "un", "ud", "uds", "unidad", "unidades", "punto", "puntos",
}  # fmt: skip
_DERIVADA = {
    "kg", "kgs", "kilo", "kilos", "kilogramo", "kilogramos", "ton", "tons", "t", "tonelada", "toneladas",
    "lt", "lts", "l", "litro", "litros", "bulto", "bultos", "saco", "sacos", "galon", "galones",
}  # fmt: skip

# Qué medidas de trazo caben en cada tipo. Un área también da su perímetro; una línea con grosor (un muro)
# da su área; un volumen se mide con un área y un espesor (factor); lo derivado sale de un conteo.
_MEDIDAS: dict[str, frozenset[str]] = {
    "area": frozenset({"area", "perimetro"}),
    "lineal": frozenset({"longitud", "area"}),
    "conteo": frozenset({"conteo"}),
    "volumen": frozenset({"area"}),
    "derivada": frozenset({"conteo"}),
}


def _normalizar(unidad: str) -> str:
    sin_acentos = unicodedata.normalize("NFD", unidad.lower())
    sin_acentos = "".join(c for c in sin_acentos if not unicodedata.combining(c))
    return re.sub(r"[.\s]", "", sin_acentos.replace("²", "2").replace("³", "3"))


def tipo_de_unidad(unidad: str | None) -> str | None:
    """`area`, `lineal`, `volumen`, `conteo`, `derivada` o `None` si la unidad no se puede deducir."""
    if not unidad:
        return None
    u = _normalizar(unidad)
    for tipo, conjunto in (
        ("area", _AREA),
        ("lineal", _LINEAL),
        ("volumen", _VOLUMEN),
        ("conteo", _CONTEO),
        ("derivada", _DERIVADA),
    ):
        if u in conjunto:
            return tipo
    return None


def medidas_que_caben(tipo: str | None) -> frozenset[str] | None:
    """Las medidas de trazo que admite un tipo; `None` = no se sabe y cualquiera cabe."""
    return _MEDIDAS.get(tipo) if tipo else None
