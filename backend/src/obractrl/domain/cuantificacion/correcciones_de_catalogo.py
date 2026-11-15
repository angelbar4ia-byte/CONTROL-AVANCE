"""Correcciones propuestas a un dato del catálogo, como nueva versión del concepto (Ola 3B; regla del usuario sobre el catálogo).

Una corrección a un dato del catálogo **no edita el catálogo ni los CSV de opus**: se registra como una *nueva versión del
concepto*, propuesta por Costos y pendiente de autorizar por Control de obra (las reglas de `autorizacion_de_elementos`), y la
conciliación muestra la diferencia contra el catálogo vigente. Aquí viven las correcciones **conocidas**: una lista cerrada, con el
valor que trae el catálogo y la fuente, para que nadie proponga a mano un valor que el catálogo no respalda.

Hoy trae una: la unidad de **EST-02330** (cadena intermedia de 15×70) de `m2` a `m` (Q59). El elemento de esa cadena **no se construye**
en esta ola; solo se deja registrada su corrección. Funciones puras, sin base de datos.
"""

from __future__ import annotations

from typing import Any

from obractrl.domain.cuantificacion.autorizacion_de_elementos import (
    siguiente_version,
    validar_que_autoriza,
    validar_que_propone,
)
from obractrl.domain.cuantificacion.elementos_parametricos import (
    ErrorDeElementoParametrico,
)

__all__ = [
    "CAMPOS_CORREGIBLES",
    "CORRECCIONES_CONOCIDAS",
    "correccion_conocida",
    "resumen_de_la_correccion",
    "siguiente_version",
    "validar_que_autoriza",
    "validar_que_propone",
]

CAMPOS_CORREGIBLES = ("unidad",)
"""Qué dato de un concepto se puede corregir por esta vía. Hoy solo la unidad."""

CORRECCIONES_CONOCIDAS: tuple[dict[str, Any], ...] = (
    {
        "concepto_clave": "EST-02330",
        "campo": "unidad",
        "valor_catalogo": "m2",
        "valor_propuesto": "m",
        "concepto": "Cadena intermedia de 15x70 cm de concreto h.o. f'c=150, armada con 4 var no.5, 2 var no.4 y estribos no.3 @20cms.",
        "motivo": (
            "El catálogo la cuenta en m2, pero todas sus cantidades son por metro lineal: 4 varillas de 5/8 de 1 m entre 12 m por 1.05 "
            "dan 0.35 pza, que es lo que trae. Una cadena se mide en metros."
        ),
        "fuente": "CATALOGO_DE_MATRICES:191 (unidad m2); ANALISIS_DE_BASICOS_CONCEPTOS:883-886 (cantidades por metro)",
        "preguntas": ("Q59",),
        "nota": "El elemento de esta cadena no se construye en esta ola: solo se registra la corrección de su unidad.",
    },
)


def correccion_conocida(concepto_clave: str, campo: str) -> dict[str, Any]:
    """La corrección conocida de ese dato del concepto; si no está en la lista, no se puede proponer."""
    clave = " ".join(concepto_clave.split()).upper()
    for c in CORRECCIONES_CONOCIDAS:
        if c["concepto_clave"] == clave and c["campo"] == campo:
            return c
    raise ErrorDeElementoParametrico(
        f"No hay una corrección conocida del dato «{campo}» del concepto {clave}: solo se registran las que el catálogo respalda."
    )


def resumen_de_la_correccion(c: dict[str, Any]) -> str:
    return f"{c['concepto_clave']}: {c['campo']} {c['valor_catalogo']} → {c['valor_propuesto']} (versión nueva del concepto)"
