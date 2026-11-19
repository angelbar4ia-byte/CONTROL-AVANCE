"""La ubicación de un muro: material, caras A y B y reglas por parte de altura (plan de elementos de muro, Ola 4A; M-4, M-6, M-8).

La **ubicación** dice qué cara de cada parte de altura es exterior y cuál interior. Cara A = izquierda del sentido de dibujo; cara B
= derecha. ``exterior`` equivale a ``fachada`` en ``trazo.muro_acabado``. Pretil y barda son ubicaciones (no tipos de muro); el
pretil lo trata Artefacto como una excepción del muro, no como un elemento (M-139).

Reglas (``reglas_de_ubicacion`` del mockup):
1. Al elegir una ubicación con caras definidas, todas las partes toman esas caras.
2. Si la ubicación tiene ``enrase_exterior``, la parte con rol ``enrase`` queda exterior en las dos caras.
3. Si el usuario cambia la cara de cualquier parte, la ubicación pasa a ``personalizada``.
4. Losa más baja que el muro: las partes con ``desde`` ≥ altura de losa se **sugieren** exterior; se aplican solo al confirmar.

El **material** de la mampostería es un parámetro de la plantilla, independiente de la **ubicación** (interior, pretil, barda…) y del
tipo de muro (F2): una barda puede ser de tabique rojo, de sillar amarillo o de cantera rosa. Hechos del catálogo (C2, F7): el tabique
rojo recocido es EST-02010 (14 cm); el sillar amarillo es de **19 cm** (BAP-01010, que existe como concepto pero aún no como elemento); no hay
concepto de block hueco ni de cantera rosa (por capturar: no se inventa ninguno).
Funciones puras, sin base de datos.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = [
    "CARAS",
    "MATERIALES_DE_MURO",
    "ROLES_DE_PARTE",
    "UBICACIONES_DE_MURO",
    "aplicar_ubicacion",
    "caras_de_ubicacion",
    "material_valido",
    "sugerencia_por_losa",
    "ubicacion_resultante",
    "ubicacion_valida",
    "validar_partes_con_caras",
]

CARAS: tuple[str, ...] = ("exterior", "interior")
ROLES_DE_PARTE: tuple[str, ...] = ("cuerpo", "enrase", "pretil", "cadena")

UBICACIONES_DE_MURO: dict[str, dict[str, Any]] = {
    "interior": {"nombre": "Interior", "caras": ("interior", "interior"), "enrase_exterior": True, "elementos_sugeridos": ()},
    "fachada_a": {"nombre": "Fachada, cara A exterior", "caras": ("exterior", "interior"), "enrase_exterior": False, "elementos_sugeridos": ()},
    "fachada_b": {"nombre": "Fachada, cara B exterior", "caras": ("interior", "exterior"), "enrase_exterior": False, "elementos_sugeridos": ()},
    "pretil": {"nombre": "Pretil", "caras": ("exterior", "exterior"), "enrase_exterior": False, "elementos_sugeridos": ("K-1",)},
    "barda": {"nombre": "Barda", "caras": ("exterior", "exterior"), "enrase_exterior": False, "elementos_sugeridos": ("K-1", "CE-1")},
    "personalizada": {"nombre": "Personalizada", "caras": None, "enrase_exterior": False, "elementos_sugeridos": ()},
}
"""Las ubicaciones del mockup. Los elementos sugeridos son una pista de la interfaz: no se colocan solos."""

MATERIALES_DE_MURO: dict[str, dict[str, Any]] = {
    "tabique_rojo": {"nombre": "Tabique rojo recocido 14 cm", "espesor_cm": 14, "elemento": "EST-02010", "concepto": "EST-02010"},
    "block_hueco": {"nombre": "Block hueco de concreto", "espesor_cm": None, "elemento": None, "concepto": None},
    "sillar_amarillo": {"nombre": "Sillar amarillo 19 cm", "espesor_cm": 19, "elemento": None, "concepto": "BAP-01010"},
    "cantera_rosa": {"nombre": "Cantera rosa", "espesor_cm": None, "elemento": None, "concepto": None},
}
"""Los materiales de la mampostería. `elemento` es el elemento de la biblioteca que lo paga (solo el tabique rojo, EST-02010); `concepto` es
el concepto del catálogo de presupuesto que lo cubre: `None` = no hay concepto, por capturar (block hueco y cantera rosa), y una plantilla
con ese material **no se puede validar** (C3). El sillar amarillo tiene concepto (BAP-01010, 19 cm) pero aún no es un elemento (F7)."""


def ubicacion_valida(ubicacion: str) -> str:
    if ubicacion not in UBICACIONES_DE_MURO:
        raise ErrorDeCuantificacion(f"Ubicación del muro: {', '.join(UBICACIONES_DE_MURO)} (no «{ubicacion}»).")
    return ubicacion


def material_valido(material: str) -> str:
    if material not in MATERIALES_DE_MURO:
        raise ErrorDeCuantificacion(f"Material del muro: {', '.join(MATERIALES_DE_MURO)} (no «{material}»).")
    return material


def caras_de_ubicacion(ubicacion: str, rol: str | None = None) -> tuple[str, str] | None:
    """(cara A, cara B) que la ubicación fija para una parte con ese rol; `None` si la ubicación no las fija (personalizada)."""
    u = UBICACIONES_DE_MURO[ubicacion_valida(ubicacion)]
    if u["caras"] is None:
        return None
    if u["enrase_exterior"] and rol == "enrase":
        return ("exterior", "exterior")
    return tuple(u["caras"])  # type: ignore[return-value]


def _cara(valor: Any, que: str) -> str | None:
    if valor is None:
        return None
    if valor not in CARAS:
        raise ErrorDeCuantificacion(f"La {que} es {' o '.join(CARAS)} (no «{valor}»).")
    return str(valor)


def validar_partes_con_caras(partes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Revisa y copia las partes de altura con sus caras, rol y cadena: cada una va de un «desde» a un «hasta» mayor."""
    salida: list[dict[str, Any]] = []
    for p in partes:
        nombre = str(p.get("nombre") or "")
        desde, hasta = Decimal(str(p["desde_m"])), Decimal(str(p["hasta_m"]))
        if desde < 0 or hasta <= desde:
            raise ErrorDeCuantificacion(f"La parte «{nombre}» debe ir de un «desde» a un «hasta» mayor.")
        rol = p.get("rol")
        if rol is not None and rol not in ROLES_DE_PARTE:
            raise ErrorDeCuantificacion(f"El rol de una parte es {', '.join(ROLES_DE_PARTE)} (no «{rol}»).")
        salida.append(
            {
                "nombre": nombre,
                "desde_m": str(desde),
                "hasta_m": str(hasta),
                "suma": bool(p.get("suma", True)),
                "rol": rol,
                "cara_a": _cara(p.get("cara_a"), "cara A"),
                "cara_b": _cara(p.get("cara_b"), "cara B"),
                "elemento_ref": (str(p["elemento_ref"]).strip() or None) if p.get("elemento_ref") else None,
            }
        )
    return salida


def aplicar_ubicacion(ubicacion: str, partes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Regla 1 y 2: todas las partes toman las caras de la ubicación (el enrase, exterior si la ubicación lo pide). Con una
    ubicación personalizada las partes quedan como están."""
    ubicacion_valida(ubicacion)
    nuevas = validar_partes_con_caras(partes)
    for p in nuevas:
        caras = caras_de_ubicacion(ubicacion, p["rol"])
        if caras is not None:
            p["cara_a"], p["cara_b"] = caras
    return nuevas


def ubicacion_resultante(ubicacion: str, partes: Sequence[Mapping[str, Any]]) -> str:
    """Regla 3: si alguna parte trae una cara distinta de la que fija la ubicación, el muro pasa a «personalizada». Las partes
    sin caras (aún no ubicadas) no cuentan."""
    ubicacion_valida(ubicacion)
    if ubicacion == "personalizada":
        return ubicacion
    for p in validar_partes_con_caras(partes):
        if p["cara_a"] is None and p["cara_b"] is None:
            continue
        esperadas = caras_de_ubicacion(ubicacion, p["rol"])
        if esperadas is not None and (p["cara_a"], p["cara_b"]) != esperadas:
            return "personalizada"
    return ubicacion


def sugerencia_por_losa(partes: Sequence[Mapping[str, Any]], altura_de_losa_m: Decimal) -> list[dict[str, Any]]:
    """Regla 4: con la losa más baja que el muro, las partes que empiezan en la losa o arriba se sugieren exteriores. Solo
    sugiere (nunca cambia nada): la interfaz las aplica al confirmar."""
    if altura_de_losa_m <= 0:
        raise ErrorDeCuantificacion("La altura de la losa debe ser mayor que cero.")
    sugeridas: list[dict[str, Any]] = []
    for i, p in enumerate(validar_partes_con_caras(partes)):
        if Decimal(p["desde_m"]) >= altura_de_losa_m:
            sugeridas.append({"indice": i, "nombre": p["nombre"], "cara_a": "exterior", "cara_b": "exterior"})
    return sugeridas
