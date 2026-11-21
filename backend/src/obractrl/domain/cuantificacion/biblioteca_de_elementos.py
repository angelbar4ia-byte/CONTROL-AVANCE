"""La biblioteca de elementos: categorías y subcategorías que clasifican a los elementos paramétricos.

Hoy trae **dos elementos propios**: el muro de contención de piedra MCT-01010 (categoría «Muros de contención», subcategoría
«Mampostería») y el muro de cimentación de piedra CIM-01010 (categoría «Muros de cimentación», subcategoría «Mampostería
de piedra»); los dos se pagan con el concepto MCT-01011. Las trabes, contratrabes, nervaduras, Z-1 y C-1 (Ola 3B, `elementos_lineales`) se unen por clave de categoría y subcategoría. Los demás siguen definiéndose en el panel
de la pestaña Elementos y pasarán aquí cuando se construyan. Función pura, sin base de datos.
"""

from __future__ import annotations

from typing import Any

from obractrl.domain.cuantificacion import (
    baston,
    matriz_de_losa,
    muro_cimentacion,
    muro_sillar,
    muro_tabique,
    relleno,
)
from obractrl.domain.cuantificacion.elementos_lineales import (
    TIPOS as _TIPOS_LINEALES,
)
from obractrl.domain.cuantificacion.elementos_lineales import (
    categorias_de_biblioteca as _categorias_lineales,
)
from obractrl.domain.cuantificacion.estructura_de_catalogo import CATEGORIAS_DE_ESTRUCTURA
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

_CIM_01010: dict[str, Any] = {
    "clave": muro_cimentacion.CLAVE_ELEMENTO,
    "nombre": "Muro de cimentación de piedra",
    "tipo": "muro_de_cimentacion_de_piedra",
    "se_mide_por": "metro lineal de trazo",
    "concepto": {
        "clave": CLAVE_CONCEPTO,
        "descripcion": DESCRIPCION_CONCEPTO,
        "unidad": "m3",
    },
    "parametros_por_defecto": {"alto_m": 1.0, "caras": 1, "dentellon": False},
}

def _unir(*familias: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    """Une las categorías de cada familia: la misma categoría (o subcategoría) de dos familias es una sola, con sus elementos juntos."""
    categorias: dict[str, dict[str, Any]] = {}
    for familia in familias:
        for cat in familia:
            destino = categorias.setdefault(cat["clave"], {**cat, "subcategorias": {}})
            for sub in cat["subcategorias"]:
                previa = destino["subcategorias"].setdefault(sub["clave"], {**sub, "elementos": ()})
                previa["elementos"] = (*previa["elementos"], *sub["elementos"])
    return tuple({**c, "subcategorias": tuple(c["subcategorias"].values())} for c in categorias.values())


_EXISTENTES: tuple[dict[str, Any], ...] = (
    *CATEGORIAS_DE_ESTRUCTURA,
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
    {
        "clave": "muros_cimentacion",
        "nombre": "Muros de cimentación",
        "prefijo": "CIM",
        "subcategorias": (
            {
                "clave": "piedra",
                "nombre": "Mampostería de piedra",
                "prefijo": "CIM",
                "elementos": (_CIM_01010,),
            },
        ),
    },
)


BIBLIOTECA: tuple[dict[str, Any], ...] = _unir(
    _EXISTENTES, _categorias_lineales(), muro_tabique.categorias_de_biblioteca(), muro_sillar.categorias_de_biblioteca(), baston.categorias_de_biblioteca(),
    matriz_de_losa.categorias_de_biblioteca(), relleno.categorias_de_biblioteca(),
)


def elemento_de_la_biblioteca(clave: str) -> dict[str, Any] | None:
    for categoria in BIBLIOTECA:
        for sub in categoria["subcategorias"]:
            for elemento in sub["elementos"]:
                if elemento["clave"] == clave and elemento.get("tipo") != "estructura_de_catalogo" and elemento.get("tipo") not in _TIPOS_LINEALES and elemento.get("tipo") not in ("tabique", "sillar", "baston", "losa_de_concreto", "relleno"):
                    cimiento = clave == muro_cimentacion.CLAVE_ELEMENTO
                    return {
                        **elemento,
                        "categoria": {
                            "clave": categoria["clave"],
                            "nombre": categoria["nombre"],
                        },
                        "subcategoria": {"clave": sub["clave"], "nombre": sub["nombre"]},
                        # El cimiento no usa el Cuadro 1: su sección sale del escarpio.
                        "cuadro_1": [] if cimiento else [dict(f) for f in CUADRO_1],
                        "fuente": muro_cimentacion.FUENTE_ESCARPIO
                        if cimiento
                        else FUENTE_CUADRO_1,
                        "dentellon": dict(DENTELLON),
                        "pendientes": [
                            dict(p)
                            for p in (
                                muro_cimentacion.PENDIENTES if cimiento else PENDIENTES
                            )
                        ],
                    }
    return None
