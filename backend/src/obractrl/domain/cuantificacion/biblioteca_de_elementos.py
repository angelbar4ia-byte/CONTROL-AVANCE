"""La biblioteca de elementos: categorías y subcategorías que clasifican a los elementos paramétricos.

Hoy trae **un solo elemento**, el muro de contención de piedra MCT-01010 (categoría «Muros de contención»,
subcategoría «Mampostería»). Los demás (castillos, cadenas, trabes, zapatas, losas…) siguen definiéndose en el panel
de la pestaña Elementos y pasarán aquí cuando se construyan. Función pura, sin base de datos.
"""

from __future__ import annotations

from typing import Any

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

BIBLIOTECA: tuple[dict[str, Any], ...] = (
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


def elemento_de_la_biblioteca(clave: str) -> dict[str, Any] | None:
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
