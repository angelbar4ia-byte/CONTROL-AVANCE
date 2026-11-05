"""Cómo cuenta un trazo para su concepto: la conversión del enlace (cerebro D-633).

Un trazo no cuenta igual para todos los conceptos: un muro puede contarse por **largo**, por **área** (por el eje, por
una cara o por las dos, con altura única o por partes), por **volumen** o por **piezas**; un área, por **área**, **volumen**
(espesor y descuento), **piezas** (la pieza y su merma) o **perímetro** (con altura). Esa elección y sus parámetros son la
*conversión*; la cantidad la calcula la base de datos (`app.cantidad_conversion`) y aquí solo se validan los parámetros,
se arman los valores por defecto y se escribe la fórmula para quien la lee. Funciones puras.
"""

from __future__ import annotations

from typing import Any

from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = [
    "CAMPOS_POR_MODO",
    "MODOS_POR_TIPO",
    "PIEZAS_DE_MUESTRA",
    "coincide_la_unidad",
    "conversion_por_defecto",
    "formula_en_texto",
    "medida_natural",
    "normalizar_conversion",
]

MODOS_POR_TIPO: dict[str, tuple[tuple[str, str], ...]] = {
    "muro": (("largo", "Largo"), ("area", "Área"), ("vol", "Volumen"), ("pza", "Piezas")),
    "linea": (("largo", "Largo"), ("area", "Área"), ("vol", "Volumen"), ("pza", "Piezas")),
    "area": (("area", "Área"), ("vol", "Volumen"), ("pza", "Piezas"), ("perim", "Perímetro")),
}
"""Los modos de cada tipo de trazo (los demás tipos siguen contando como siempre, por medida × factor)."""

# Qué parámetros pide cada (tipo, modo): clave, etiqueta, unidad.
CAMPOS_POR_MODO: dict[str, tuple[tuple[str, str, str], ...]] = {
    "muro/area": (("alt", "Altura", "m"),),
    "linea/area": (("alt", "Altura", "m"),),
    "muro/vol": (("alt", "Altura", "m"), ("gro", "Grosor (una cara)", "m")),
    "linea/vol": (("alt", "Altura", "m"), ("gro", "Grosor (una cara)", "m")),
    "muro/pza": (("sep", "Una cada", "m"),),
    "linea/pza": (("sep", "Una cada", "m"),),
    "area/vol": (("esp", "Espesor", "m"), ("desc", "Descuento", "m³")),
    "area/pza": (("pw", "Ancho de la pieza", "m"), ("ph", "Alto de la pieza", "m"), ("merma", "Merma", "%")),
    "area/perim": (("alt", "Altura (0 = solo largo)", "m"),),
}

PIEZAS_DE_MUESTRA: dict[str, tuple[float, float]] = {
    "Loseta 60×60": (0.6, 0.6),
    "Block 40×20": (0.4, 0.2),
    "Ladrillo 24×11": (0.24, 0.11),
    "Tablero 1.22×2.44": (1.22, 2.44),
}

_NUMEROS = ("alt", "gro", "esp", "desc", "pw", "ph", "merma", "sep")
_SEPARADOR_DE_ALTURA = ("area",)


def medida_natural(tipo: str) -> str:
    """La medida con la que se guarda el enlace (el valor ya trae la cantidad final; el factor es 1)."""
    return {"muro": "longitud", "linea": "longitud", "area": "area"}.get(tipo, "conteo")


def _numero(valor: Any, que: str) -> float:
    try:
        n = float(str(valor).replace(",", "."))
    except (TypeError, ValueError) as e:
        raise ErrorDeCuantificacion(f"{que} debe ser un número.") from e
    if n != n or n in (float("inf"), float("-inf")):
        raise ErrorDeCuantificacion(f"{que} debe ser un número.")
    return n


def conversion_por_defecto(tipo: str, unidad_del_concepto: str | None) -> dict[str, Any]:
    """Cómo cuenta un trazo si nadie lo ha dicho: según la unidad del concepto (el `convDefecto` del mockup)."""
    u = (unidad_del_concepto or "").lower().replace("²", "2").replace("³", "3")
    base: dict[str, Any] = {
        "mide": "cara2", "cara": "int", "lado": "der", "gro": None, "esp": 0.12, "desc": 0.0, "pw": 0.6, "ph": 0.6,
        "merma": 5.0, "alt": 2.6, "sep": 2.5, "partes": [],
    }
    if tipo == "area":
        if u in ("ml", "m"):
            return {**base, "alt": 0.0, "modo": "perim"}
        return {**base, "modo": "vol" if u == "m3" else "pza" if u in ("pza", "lote") else "area"}
    if tipo in ("muro", "linea"):
        return {**base, "modo": "area" if u == "m2" else "vol" if u == "m3" else "pza" if u in ("pza", "lote") else "largo"}
    return {**base, "modo": "pza"}


def normalizar_conversion(tipo: str, conversion: dict[str, Any]) -> dict[str, Any]:
    """Valida la conversión contra el tipo de trazo y la deja con tipos limpios. Levanta `ErrorDeCuantificacion`."""
    modos = dict(MODOS_POR_TIPO.get(tipo, ()))
    if not modos:
        raise ErrorDeCuantificacion("Este tipo de trazo todavía cuenta solo por su medida y su factor.")
    modo = str(conversion.get("modo", ""))
    if modo not in modos and not (tipo == "area" and modo == "perim"):
        raise ErrorDeCuantificacion(f"Un trazo de tipo {tipo} no cuenta por «{modo}».")
    limpia: dict[str, Any] = {"modo": modo}
    for k in _NUMEROS:
        if conversion.get(k) in (None, ""):
            continue
        n = _numero(conversion[k], k)
        if n < 0:
            raise ErrorDeCuantificacion(f"{k} no puede ser negativo.")
        limpia[k] = n
    for k in ("sep", "pw", "ph"):
        if k in limpia and modo in ("pza",) and limpia[k] <= 0:
            raise ErrorDeCuantificacion("La separación y las medidas de la pieza van por encima de cero.")
    if "merma" in limpia and limpia["merma"] > 100:
        raise ErrorDeCuantificacion("La merma va de 0 a 100 %.")
    mide = str(conversion.get("mide", "cara2"))
    if mide not in ("eje", "cara1", "cara2"):
        raise ErrorDeCuantificacion("Se mide por el eje, una cara o dos caras.")
    cara = str(conversion.get("cara", "int"))
    lado = str(conversion.get("lado", "der"))
    if cara not in ("int", "ext") or lado not in ("izq", "der"):
        raise ErrorDeCuantificacion("La cara es interior o exterior; el interior queda a la izquierda o a la derecha.")
    limpia |= {"mide": mide, "cara": cara, "lado": lado}
    partes = []
    for p in conversion.get("partes") or []:
        d, h = _numero(p.get("desde_m"), "«desde»"), _numero(p.get("hasta_m"), "«hasta»")
        if d < 0 or h <= d:
            raise ErrorDeCuantificacion(f"La parte «{p.get('nombre', '')}» debe ir de un «desde» a un «hasta» mayor.")
        partes.append({"nombre": str(p.get("nombre", ""))[:40], "desde_m": d, "hasta_m": h, "suma": bool(p.get("suma", True))})
    limpia["partes"] = partes
    if modo == "area" and tipo in ("muro", "linea"):
        altura = sum(p["hasta_m"] - p["desde_m"] for p in partes if p["suma"]) if partes else limpia.get("alt", 2.6)
        if altura <= 0:
            raise ErrorDeCuantificacion("La altura que suma debe ser mayor que cero.")
    return limpia


def _m(n: float, d: int = 2) -> str:
    return f"{n:.{d}f}"


def _g(n: float) -> str:
    """Un parámetro como lo teclea quien lo escribe: 2.6, no 2.60."""
    return f"{n:g}"


def formula_en_texto(c: dict[str, Any], conv: dict[str, Any]) -> str:
    """La fórmula con los números, para quien revisa (como la del mockup)."""
    tipo, modo = c.get("tipo"), c.get("modo")
    vanos_m2, vanos_ml = float(c.get("vanos_m2") or 0), float(c.get("vanos_ml") or 0)
    partes = " (partes que suman)" if conv.get("partes") else ""

    def resta(x: float, u: str) -> str:
        return f" − {_m(x)} {u} de vanos" if x > 0 else ""

    if tipo in ("muro", "linea"):
        largo, alt = float(c["largo"]), float(c["altura"])
        if modo == "largo":
            return f"{_m(largo)} m de largo{resta(vanos_ml, 'm')}"
        if modo == "area":
            n = int(c["n_caras"])
            if conv.get("mide") == "eje":
                tramo = f"{_m(float(c['base']))} m de eje"
            elif conv.get("mide") == "cara1":
                tramo = f"{_m(float(c['base']))} m de cara {'exterior' if conv.get('cara') == 'ext' else 'interior'}"
            else:
                tramo = f"{_m(float(c['cara_interior']))} m int. + {_m(float(c['cara_exterior']))} m ext."
            return f"({tramo}) × {_g(alt)} m{resta(vanos_m2 * n, 'm²')}{partes}"
        if modo == "vol":
            g = conv.get("gro") or 0.15
            return f"({_m(largo)} m × {_g(alt)} m{resta(vanos_m2, 'm²')}) × {g} m{partes}"
        return f"⌈{_m(largo)} m ÷ {conv.get('sep', 2.5)} m⌉ + 1"
    if tipo == "area":
        a = float(c["area"])
        if modo == "area":
            return f"{_m(a)} m²{resta(vanos_m2, 'm²')}"
        if modo == "vol":
            return f"{_m(a)} m²{resta(vanos_m2, 'm²')} × {conv.get('esp', 0.12)} m" + (f" − {conv['desc']} m³" if conv.get("desc") else "")
        if modo == "pza":
            return f"{_m(a)} m² ÷ ({conv.get('pw', 0.6)} × {conv.get('ph', 0.6)}) × {1 + float(conv.get('merma', 5)) / 100:g}"
        p = float(c["perimetro"])
        return (
            f"{_m(p)} m × {conv['alt']} m{resta(vanos_m2, 'm²')}" if conv.get("alt") else f"{_m(p)} m de perímetro{resta(vanos_ml, 'm')}"
        )
    return "1 pieza"


def coincide_la_unidad(unidad_del_resultado: str, unidad_del_concepto: str | None) -> bool:
    """¿El resultado viene en la unidad en que se mide el concepto? (✓ coincide / ⚠ distinta unidad)."""
    def n(u: str | None) -> str:
        return (u or "").lower().replace("²", "2").replace("³", "3").replace("m2", "m2").strip()

    r, c = n(unidad_del_resultado), n(unidad_del_concepto)
    return r == c or (r == "ml" and c == "m") or (r == "m" and c == "ml")
