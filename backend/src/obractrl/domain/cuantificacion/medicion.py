"""Mediciones: la capa sombra del cuantificador (migración 0088).

Una medición es un grupo con nombre de trazos de **un tipo** —área, lineal o conteo— que vive sobre
el plano sin depender de ningún concepto y después se asigna a uno o varios. Aquí solo están las
reglas puras: qué tipo admite qué geometría, qué medidas se le pueden asignar y cómo se limpia el
nombre. Nada de SQL ni de PostGIS (§12.11).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = [
    "MEDIDAS_POR_TIPO",
    "MEDIDA_BASE_DEL_PESO",
    "TIPOS_DE_MEDICION",
    "admite_geometria",
    "factor_por_peso",
    "medida_admitida",
    "motivo_de_incompatibilidad",
    "normalizar_nombre",
]

TIPOS_DE_MEDICION = ("area", "lineal", "conteo")

#: Qué medidas se pueden asignar a un concepto según el tipo de la medición. Un área da su área o su
#: perímetro; una línea su longitud (o el área de un muro, si lleva grosor); un conteo, piezas.
MEDIDAS_POR_TIPO: dict[str, frozenset[str]] = {
    "area": frozenset({"area", "perimetro"}),
    "lineal": frozenset({"longitud", "area"}),
    "conteo": frozenset({"conteo"}),
}

_NOMBRE_DE_TIPO = {"area": "de área", "lineal": "lineal", "conteo": "de conteo"}


def normalizar_nombre(nombre: str) -> str:
    """El nombre sin espacios sobrantes; no puede quedar vacío ni pasar de 120 caracteres."""
    limpio = " ".join(nombre.split())
    if not limpio:
        raise ErrorDeCuantificacion("La medición necesita un nombre.")
    if len(limpio) > 120:
        raise ErrorDeCuantificacion("El nombre de la medición no puede pasar de 120 caracteres.")
    return limpio


def medida_admitida(tipo: str, medida: str) -> bool:
    return medida in MEDIDAS_POR_TIPO.get(tipo, frozenset())


def admite_geometria(tipo: str, geometria: str, tiene_forma: bool) -> bool:
    """¿Un trazo con esa geometría (`ST_Polygon`, `ST_LineString`, `ST_Point`) cabe en una medición de
    ese tipo? Un polígono estampado con una forma (un castillo) es una pieza que se cuenta: es de
    conteo, no de área."""
    if tipo == "area":
        return geometria == "ST_Polygon" and not tiene_forma
    if tipo == "lineal":
        return geometria == "ST_LineString"
    if tipo == "conteo":
        return geometria == "ST_Point" or (geometria == "ST_Polygon" and tiene_forma)
    return False


def motivo_de_incompatibilidad(tipo: str, geometria: str, tiene_forma: bool) -> str | None:
    """Por qué ese trazo no cabe en una medición de ese tipo, o `None` si cabe."""
    if admite_geometria(tipo, geometria, tiene_forma):
        return None
    que = {
        "ST_Polygon": "una pieza estampada (se cuenta)" if tiene_forma else "un área",
        "ST_LineString": "una línea",
        "ST_Point": "un punto",
    }.get(geometria, "ese trazo")
    return (
        f"Una medición {_NOMBRE_DE_TIPO.get(tipo, tipo)} no admite {que}: "
        "área admite áreas, lineal admite líneas y conteo admite puntos y piezas estampadas."
    )


#: La medida cuya unidad es la del peso de un elemento: kg por pieza → conteo; por metro → longitud;
#: por m² → área.
MEDIDA_BASE_DEL_PESO = {"conteo": "conteo", "lineal": "longitud", "area": "area"}

_UNIDADES_DE_PESO = {"kg": Decimal(1), "ton": Decimal("0.001")}


def factor_por_peso(peso_kg: Decimal, unidad: str | None) -> Decimal:
    """El factor del enlace que convierte la medición de un elemento al concepto en kg o ton: el peso
    del elemento, ÷ 1000 si el concepto es en toneladas. Seis decimales, como la columna."""
    clave = (unidad or "").strip().lower()
    if clave not in _UNIDADES_DE_PESO:
        raise ErrorDeCuantificacion(
            "El peso de un elemento solo alimenta conceptos en kg o ton; este concepto es en "
            f"«{unidad or 'sin unidad'}»."
        )
    factor = (Decimal(peso_kg) * _UNIDADES_DE_PESO[clave]).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    if factor <= 0:
        raise ErrorDeCuantificacion("Ese peso en toneladas es demasiado chico: redondea a cero.")
    return factor
