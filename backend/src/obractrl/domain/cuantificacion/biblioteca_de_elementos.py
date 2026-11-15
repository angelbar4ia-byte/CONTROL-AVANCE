"""La biblioteca de elementos: categorías y subcategorías que clasifican a los elementos paramétricos.

Trae el muro de contención de piedra MCT-01010 (categoría «Muros de contención», subcategoría «Mampostería») y los
elementos estructurales de la Ola 3B (trabes, contratrabes, nervaduras, zapata Z-1 y columna C-1; ver `elementos_lineales`).
Los demás (castillos, cadenas, losas…) pasarán aquí cuando se construyan. Cada familia aporta sus categorías y aquí se
unen por clave de categoría y de subcategoría. Función pura, sin base de datos.
"""

from __future__ import annotations

from typing import Any

from obractrl.domain.cuantificacion.elementos_lineales import (
    categorias_de_biblioteca as _categorias_de_estructura,
)
from obractrl.domain.cuantificacion.elementos_lineales import (
    claves_de_elementos_estructurales as _claves_de_estructura,
)
from obractrl.domain.cuantificacion.muro_contencion import (
    CLAVE_CONCEPTO,
    CLAVE_ELEMENTO,
    CUADRO_1,
    DENTELLON,
    DESCRIPCION_CONCEPTO,
    FUENTE_CUADRO_1,
    PENDIENTES,
)

__all__ = ["BIBLIOTECA", "elemento_de_la_biblioteca"]

_MCT_01010: dict[str, Any] = {
    "clave": CLAVE_ELEMENTO,
    "nombre": "Muro de piedra",
    "tipo": "muro_de_contencion_de_piedra",
    "se_mide_por": "metro lineal de trazo",
    "concepto": {
        "clave": CLAVE_CONCEPTO,
        "descripcion": DESCRIPCION_CONCEPTO,
        "unidad": "m3",
    },
    "parametros_por_defecto": {
        "alto_m": 2.0,
        "dentellon": True,
        "lluvia": "baja",
        "tubo": "pvc",
        "filtro_cm": None,
        "relleno": "vertical",
    },
}

def _unir(*familias: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    """Une las categorías de cada familia: la misma categoría (o subcategoría) de dos familias es una sola, con sus elementos juntos."""
    categorias: dict[str, dict[str, Any]] = {}
    for familia in familias:
        for cat in familia:
            destino = categorias.setdefault(
                cat["clave"], {**cat, "subcategorias": {}}
            )
            for sub in cat["subcategorias"]:
                previa = destino["subcategorias"].setdefault(sub["clave"], {**sub, "elementos": ()})
                previa["elementos"] = (*previa["elementos"], *sub["elementos"])
    return tuple(
        {**c, "subcategorias": tuple(c["subcategorias"].values())} for c in categorias.values()
    )


_CONTENCION: tuple[dict[str, Any], ...] = (
    {
        "clave": "contencion",
        "nombre": "Muros de contención",
        "prefijo": "MCT",
        "subcategorias": (
            {
                "clave": "mamposteria",
                "nombre": "Mampostería",
                "prefijo": "MCT",
                "elementos": (_MCT_01010,),
            },
        ),
    },
)

BIBLIOTECA: tuple[dict[str, Any], ...] = _unir(_CONTENCION, _categorias_de_estructura())


def elemento_de_la_biblioteca(clave: str) -> dict[str, Any] | None:
    """La definición del elemento con el Cuadro 1 del muro de contención. Los elementos de estructura (trabes, Z-1, C-1…) tienen
    su propia definición en `/biblioteca-de-elementos/lineales/{clave}`: aquí no."""
    if clave in _claves_de_estructura():
        return None
    for categoria in BIBLIOTECA:
        for sub in categoria["subcategorias"]:
            for elemento in sub["elementos"]:
                if elemento["clave"] == clave:
                    return {
                        **elemento,
                        "categoria": {
                            "clave": categoria["clave"],
                            "nombre": categoria["nombre"],
                        },
                        "subcategoria": {"clave": sub["clave"], "nombre": sub["nombre"]},
                        "cuadro_1": [dict(f) for f in CUADRO_1],
                        "fuente": FUENTE_CUADRO_1,
                        "dentellon": dict(DENTELLON),
                        "pendientes": [dict(p) for p in PENDIENTES],
                    }
    return None
