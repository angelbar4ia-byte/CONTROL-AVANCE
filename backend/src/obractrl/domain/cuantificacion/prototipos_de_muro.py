"""Los prototipos de la plantilla de «muro confinado de tabique» y los ejemplos que se cargan (plan de elementos de muro, Ola 4,
«plantillas de muro por prototipo»; M-4).

El muro confinado se usa cuando NO hay plano estructural: la plantilla PROPONE (estima) los castillos. Lleva varios castillos y hay una
variante por **prototipo** (Zafiro, Oro, Diamante…) y por **planta** (PB o PA), más una plantilla **global** —el promedio de los
prototipos más parecidos— separada en 1 planta y 2 plantas.

- **El número de plantas de cada prototipo se infiere** del subcapítulo «PLANTA ALTA» del Excel del cerebro (no hay una celda que lo
  diga; el usuario aceptó la inferencia): Zafiro 1.0, Rubí y Jade son de 1 planta; Zafiro Plus, Diamante − y +, y Oro 4.01, de 2.
- **Oro es el único ejemplo con datos** (primera entrega). Sus castillos salen de `PARAMETRICOS_7_PROTOTIPOS.xlsx`, hoja `ASIGNACIÓN`,
  columna K (cantidad que se cobra, metros de castillo colado); cada línea guarda su celda. El divisor es el de `Paramétrico MURO PB` /
  `MURO PA` (`D3`, m² de tabique de esa planta) de `CATALOGO_PARAMETRICO_ORO_v23.xlsx`: así la regla «total» reparte los metros de
  castillo por m² de muro, igual que la fórmula `L = I / $D$3` del libro.
- Los demás prototipos quedan como estructura capturable (sin castillos) y la global, como ejemplo **por confirmar**.

Nada de esto trae precios ni destajos. Funciones y datos puros, sin base de datos.
"""

from __future__ import annotations

from typing import Any

from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = [
    "CLAVES_DE_ELEMENTO",
    "PLANTAS",
    "PROTOTIPOS",
    "ejemplos_de_prototipo",
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

CLAVES_DE_ELEMENTO: dict[str, tuple[str, ...]] = {
    "K-1": ("K-1", "EST-02110"),
    "K-2": ("K-2", "EST-02120"),
    "K-3": ("K-3", "EST-02130"),
    "K-4": ("K-4", "EST-02140"),
    "K-5": ("K-5", "EST-02150"),
    "K-6": ("K-6", "EST-02160"),
    "K-7": ("K-7", "EST-02170"),
    "K-8": ("K-8", "EST-02180"),
    "CE-1": ("CE-1", "EST-02310"),
    "CE-2": ("CE-2", "EST-02320"),
}
"""Cómo se busca en el catálogo de la organización cada tipo del Excel: por su clave de biblioteca o por la del concepto del catálogo."""


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


# --- Los ejemplos ----------------------------------------------------------------------------------------------------------

_LIBRO_7 = "PARAMETRICOS_7_PROTOTIPOS.xlsx"
_LIBRO_ORO = "CATALOGO_PARAMETRICO_ORO_v23.xlsx"


def _castillo(tipo: str, total_m: str, base_m2: str, celda: str, concepto: str) -> dict[str, Any]:
    return {
        "tipo": tipo, "clase": "castillo", "regla": "total", "total_m": total_m, "base_m2": base_m2,
        "origen": f"{_LIBRO_7} · ASIGNACIÓN!{celda} ({concepto}, {total_m} m)",
    }


def _cadena(tipo: str, celda: str, concepto: str, metros: str) -> dict[str, Any]:
    return {"tipo": tipo, "clase": "cadena", "origen": f"{_LIBRO_7} · ASIGNACIÓN!{celda} ({concepto}, {metros} m en el prototipo)"}


_NOTA_COMUN = (
    "Ejemplo POR CONFIRMAR: los datos son los del Excel del cerebro, sin revisar con el usuario. Las cantidades del libro son valores "
    "pegados (sin fórmula); la regla «total» las reparte por m² de muro con el divisor de {divisor}, igual que la fórmula L = I / $D$3 "
    "de {libro}. El muro mide largo × alto bruto (no descuenta vanos). La planta se infiere del subcapítulo PLANTA ALTA. "
    "Sin precios ni destajos."
)

_ORO_PB: dict[str, Any] = {
    "prototipo": "oro_401",
    "planta": "PB",
    "base_m2": "286",
    "divisor": "286 m² (Paramétrico MURO PB!D3, tabique de planta baja)",
    "lineas": (
        _castillo("K-1", "126", "286", "K2152", "EST-02110"),
        _castillo("K-2", "83", "286", "K2153", "EST-02120"),
        _castillo("K-3", "20", "286", "K2154", "EST-02130"),
        _castillo("K-7", "24", "286", "K2155", "EST-02170"),
        _cadena("CE-1", "K2156", "EST-02310 cadena intermedia CE1 15x20", "108.52"),
    ),
    "pendientes": (
        "Cadena intermedia 15x70 (EST-02330, 10 m², ASIGNACIÓN!K2159): se cuenta en m² y no es un elemento de la biblioteca; no se incluye.",
        "El acero de los castillos (EST-10010… en pza) lo toman los conceptos del elemento por su alto; el Excel lo trae en la serie "
        "de CIMENTACIÓN (ASIGNACIÓN filas 2100 a 2106) y no se copia aquí.",
    ),
}

_ORO_PA: dict[str, Any] = {
    "prototipo": "oro_401",
    "planta": "PA",
    "base_m2": "246.42",
    "divisor": "246.42 m² (Paramétrico MURO PA!D3, tabique de planta alta)",
    "lineas": (
        _castillo("K-1", "33.6", "246.42", "K2253", "EST-02110"),
        _castillo("K-2", "84", "246.42", "K2254", "EST-02120"),
        _castillo("K-3", "21", "246.42", "K2255", "EST-02130"),
        _castillo("K-6", "14.4", "246.42", "K2256", "EST-02160"),
        _castillo("K-7", "16.2", "246.42", "K2257", "EST-02170"),
        _cadena("CE-1", "K2258", "EST-02310 cadena intermedia CE1 15x20", "101.61"),
        _cadena("CE-2", "K2259", "EST-02320 cadena de cerramiento CE2 15x25", "7.3"),
    ),
    "pendientes": (
        "El acero de PA aparece en el subcapítulo PLANTA BAJA del Excel (ASIGNACIÓN filas 2161 a 2164 y 2263): ¿es de los castillos de PA? "
        "Lo toman los conceptos del elemento por su alto; no se copia aquí.",
    ),
}

# Global: promedio de los prototipos más parecidos (PROPUESTA de CASTILLOS-POR-PROTOTIPO.md §5, a decidir por el usuario). Los metros son el
# promedio simple del castillo colado del Excel (PB + PA juntos en la de 2 plantas) y la base, el promedio de los divisores MURO de los
# prototipos del grupo (m² de tabique del prototipo entero: el Excel no trae la base por planta salvo en Oro).
_GLOBAL_1_BASE = "298.36"  # promedio de Zafiro 1.0 (279) y Rubí (317.72)
_GLOBAL_2_BASE = "561.71"  # promedio de Oro 4.01 (532.42) y Diamante (591)


def _promedio(tipo: str, total_m: str, base_m2: str, origen: str) -> dict[str, Any]:
    return {"tipo": tipo, "clase": "castillo", "regla": "total", "total_m": total_m, "base_m2": base_m2, "origen": origen}


_GLOBAL_1: dict[str, Any] = {
    "prototipo": "global_1",
    "planta": None,
    "divisor": f"{_GLOBAL_1_BASE} m² (promedio de los divisores MURO de Zafiro 1.0, 279, y Rubí, 317.72: RESUMEN!C38 y D38)",
    "lineas": (
        _promedio("K-1", "145.35", _GLOBAL_1_BASE, "Promedio de Zafiro 1.0 (126.9 m) y Rubí (163.8 m): ASIGNACIÓN de cada prototipo, columna K"),
        _promedio("K-2", "63.3", _GLOBAL_1_BASE, "Promedio de Zafiro 1.0 (68.4 m) y Rubí (58.2 m)"),
        _promedio("K-3", "16", _GLOBAL_1_BASE, "Promedio de Zafiro 1.0 (4 m) y Rubí (28 m)"),
        _promedio("K-4", "8", _GLOBAL_1_BASE, "Promedio de Zafiro 1.0 (12 m) y Rubí (4 m)"),
        _promedio("K-7", "28.1", _GLOBAL_1_BASE, "Promedio de Zafiro 1.0 (23.2 m) y Rubí (33 m)"),
    ),
    "pendientes": (
        "La agrupación es una PROPUESTA (CASTILLOS-POR-PROTOTIPO.md §5): Jade queda fuera como variante; ¿promedio simple o ponderado por m²?",
        "Las cadenas no se promedian: el Excel de estos prototipos trae CE1 y CE2 en metros, pero no se ha decidido su regla global.",
    ),
}
_GLOBAL_2: dict[str, Any] = {
    "prototipo": "global_2",
    "planta": None,
    "divisor": f"{_GLOBAL_2_BASE} m² (promedio de los divisores MURO de Oro 4.01, 532.42, y Diamante, 591: RESUMEN!I38 y G38)",
    "lineas": (
        _promedio("K-1", "227.7", _GLOBAL_2_BASE, "Promedio de Oro (126 + 33.6 m) y Diamante (216 + 79.8 m), PB y PA juntos"),
        _promedio("K-2", "129.4", _GLOBAL_2_BASE, "Promedio de Oro (83 + 84 m) y Diamante (79.8 + 12 m)"),
        _promedio("K-3", "31", _GLOBAL_2_BASE, "Promedio de Oro (20 + 21 m) y Diamante (21 + 0 m)"),
        _promedio("K-6", "7.2", _GLOBAL_2_BASE, "Promedio de Oro (0 + 14.4 m) y Diamante (0 m)"),
        _promedio("K-7", "33.6", _GLOBAL_2_BASE, "Promedio de Oro (24 + 16.2 m) y Diamante (21 + 6 m)"),
        _promedio("K-8", "10.5", _GLOBAL_2_BASE, "Promedio de Oro (0 m) y Diamante (21 m)"),
    ),
    "pendientes": (
        "La agrupación es una PROPUESTA (CASTILLOS-POR-PROTOTIPO.md §5): Zafiro Plus queda fuera; Diamante − y + cuentan como uno.",
        "El Excel no trae los m² de tabique por planta de Diamante: la plantilla global cubre las dos plantas con un solo divisor.",
    ),
}

_EJEMPLOS: tuple[dict[str, Any], ...] = (_ORO_PB, _ORO_PA, _GLOBAL_1, _GLOBAL_2)


def ejemplos_de_prototipo() -> list[dict[str, Any]]:
    """Las plantillas de ejemplo (Oro PB y PA, y la global de 1 y de 2 plantas) con sus líneas de castillo y cadena, **sin resolver**: cada
    línea nombra su tipo (K-1, CE-1…) y el servidor lo busca en el catálogo de la organización. Todas nacen «por confirmar»."""
    salida: list[dict[str, Any]] = []
    for e in _EJEMPLOS:
        prototipo, planta = e["prototipo"], e["planta"]
        es_global = bool(prototipo_de(prototipo)["global"])
        libro = "el promedio de los prototipos (CASTILLOS-POR-PROTOTIPO.md §5)" if es_global else _LIBRO_ORO
        notas = [
            f"{'GLOBAL' if es_global else 'PROTOTIPO'} {prototipo_de(prototipo)['nombre']}{f' · {planta}' if planta else ''}. "
            + _NOTA_COMUN.format(divisor=e["divisor"], libro=libro),
            "Líneas:",
            *(f"· {x['tipo']}: {x['origen']}" for x in e["lineas"]),
            *(f"Pendiente: {p}" for p in e["pendientes"]),
        ]
        salida.append(
            {
                "nombre": nombre_de_plantilla(prototipo, planta),
                "prototipo": prototipo,
                "planta": planta,
                "tipo": "confinado",
                "material": "tabique_rojo",
                "ubicacion": "interior",
                "por_confirmar": True,
                "notas": "\n".join(notas),
                "lineas": [dict(x) for x in e["lineas"]],
            }
        )
    return salida
