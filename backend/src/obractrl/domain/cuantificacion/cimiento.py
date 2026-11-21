"""El muro de cimentación de piedra con COTAS DE DESPLANTE (Fase 4b): el CIM-01010 de la biblioteca 3D medido sobre una línea del plano.

Decisión del usuario (2026-11-21, «Fase 4»): la cimentación usa cotas de desplante, relativas al piso terminado de PB = 0 (las zonas de losa y los puntos de nivel exterior
ya existen). Este módulo no vuelve a calcular el muro: **reutiliza** `calcular_muro_de_cimentacion` (sección con corona de 40 cm, escarpio fijo 1.5 : 1, dentellón opcional desde
2.00 m) y solo le pone lo que le faltaba para colocarse en el plano:

    altura del muro = cota de la corona − cota de desplante
    volumen         = m³ por metro lineal (del muro) × longitud de la línea del plano

- **Cota de desplante**: la del fondo del cimiento (negativa bajo el piso de PB). Se teclea, o se toma de un **punto de nivel exterior** del plano (medición derivada: si el
  punto cambia, el cimiento cambia). La tecleada manda.
- **Cota de la corona**: la tecleada o, sin ella, el piso de la zona (``cota_piso_m``).
- **Longitud**: la de la línea del plano (con la escala), derivada al calcular; no se guarda.
- Se paga con el concepto **existente** MCT-01011 por m³ (regla F7: no hay concepto nuevo), el mismo del muro de contención. No lleva dren, filtro de grava ni carpeta (los de la
  contención no se tocan). Las dalas, castillos empotrados y cimientos perpendiculares de la norma 8.4 se miden aparte (D12).

Sin precios ni destajos. Función pura; no lee ningún driver de la obra.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from obractrl.domain.cuantificacion.muro_cimentacion import (
    CLAVE_ELEMENTO,
    EntradaMuroDeCimentacion,
    ErrorDeMuroDeCimentacion,
    calcular_muro_de_cimentacion,
)
from obractrl.domain.cuantificacion.muro_contencion import (
    CLAVE_CONCEPTO,
    DESCRIPCION_CONCEPTO,
)
from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = [
    "CLAVE_DE_CIMIENTO",
    "CONCEPTO_DE_CIMIENTO",
    "PENDIENTES",
    "EntradaCimiento",
    "ErrorDeCimiento",
    "calcular_cimiento",
    "elemento_de_cimiento",
]

CLAVE_DE_CIMIENTO = CLAVE_ELEMENTO
"""``CIM-01010``: el mismo elemento de la biblioteca (Muros de cimentación › Mampostería de piedra); aquí se coloca en el plano."""

CONCEPTO_DE_CIMIENTO: dict[str, Any] = {
    "clave": CLAVE_CONCEPTO, "descripcion": DESCRIPCION_CONCEPTO, "unidad": "m3", "estado": "catalogo", "provisional": False,
}
"""El concepto EXISTENTE con que se paga (MCT-01011, por m³). No se edita."""

PENDIENTES: tuple[dict[str, str], ...] = (
    {
        "clave": "C1",
        "texto": "El material del usuario no da la cota de desplante ni la de la corona. Se teclean (o el desplante sale de un punto de nivel exterior); la corona vale el piso de "
        "la zona si no se dice. ¿La corona es el piso terminado, el arranque de la cadena de desplante u otro nivel?",
    },
    {
        "clave": "C2",
        "texto": "Zapatas (Z-1 y la zapata corrida EST-03110): no se colocan con cotas de desplante en esta fase. El mockup solo da la excavación de la zapata corrida como "
        "(ancho + holgura) × desplante, sin concepto. Q107: un tramo se mide con un solo cimiento (muro de piedra o zapata corrida). ¿Se construye la zapata con desplante?",
    },
    {
        "clave": "C3",
        "texto": "La excavación del cimiento (el catálogo trae OBE-03010 «excavación manual tipo I», por m³) no se calcula: el material del usuario no da el ancho de la zanja ni la holgura.",
    },
    {
        "clave": "C4",
        "texto": "El relleno de cimentación y el filtro de grava no están definidos por el material del usuario. El filtro de grava es solo del muro de contención (D11) y ya lo calcula "
        "ese elemento; el relleno de cimentación puede medirse con el relleno compactado (REL-COMPACTADO, EJ-810 propuesto) sobre la zona de cimentación. ¿Qué espesor y qué cotas?",
    },
    {
        "clave": "C5",
        "texto": "Una línea del plano mide un solo cimiento. La altura sigue la regla del muro de piedra (Q38): una sola altura por línea; un terreno con desnivel pide varios tramos.",
    },
)
"""Lo que el material del usuario no resuelve y se dejó con valor conservador."""

_ALTURA_MAXIMA_M = 20.0


class ErrorDeCimiento(ErrorDeCuantificacion):
    """Un dato que no vale: el cimiento no se puede calcular con él."""


@dataclass(frozen=True)
class EntradaCimiento:
    cota_desplante_m: float
    cota_corona_m: float
    longitud_m: float
    caras: int = 1
    dentellon: bool = False
    espacio_id: str | None = None


def elemento_de_cimiento(clave: str) -> bool:
    """¿La clave es la del muro de cimentación de piedra (``CIM-01010``)?"""
    return clave == CLAVE_DE_CIMIENTO


def calcular_cimiento(i: EntradaCimiento) -> dict[str, Any]:
    """El cimiento: su altura de las cotas, el volumen por metro y total, los insumos, el concepto que paga y su cantidad."""
    for que, v in (("La cota de desplante", i.cota_desplante_m), ("La cota de la corona", i.cota_corona_m)):
        if not math.isfinite(v) or not -30.0 <= v <= 100.0:
            raise ErrorDeCimiento(f"{que} va de -30 a 100 m.")
    if not math.isfinite(i.longitud_m) or not 0 < i.longitud_m <= 100_000:
        raise ErrorDeCimiento("La longitud del cimiento va de más de 0 a 100,000 m.")
    alto = i.cota_corona_m - i.cota_desplante_m
    if alto <= 1e-9:
        raise ErrorDeCimiento("La corona debe estar por encima del desplante: el cimiento tiene altura.")
    if alto > _ALTURA_MAXIMA_M:
        raise ErrorDeCimiento(f"La altura del cimiento (corona − desplante) va de más de 0 a {_ALTURA_MAXIMA_M:g} m.")
    try:
        m = calcular_muro_de_cimentacion(EntradaMuroDeCimentacion(alto_m=alto, caras=i.caras, dentellon=i.dentellon))
    except ErrorDeMuroDeCimentacion as e:
        raise ErrorDeCimiento(str(e)) from e

    v = m["volumen"]
    total = v["total_m3_ml"] * i.longitud_m
    advertencias: list[str] = [str(a) for a in m["advertencias"]]
    if i.cota_desplante_m > 0:
        advertencias.append("El desplante está por encima del piso terminado de PB (cota positiva): revisa que no sea una cota de otra referencia.")
    conceptos = [
        {
            "parte": "cimiento", "elemento_clave": CLAVE_DE_CIMIENTO, "ref": None,
            "concepto": {k: CONCEPTO_DE_CIMIENTO[k] for k in ("clave", "descripcion", "unidad", "estado", "provisional")},
            "toma": ["longitud", "altura"], "cantidad": total, "unidad": "m3",
            "nota": (
                "El concepto del catálogo MCT-01011 se mide por m³ de mampostería (regla F7: un concepto existente, no hay concepto nuevo): "
                f"{v['total_m3_ml']:.3f} m³ por metro × {i.longitud_m:.2f} m."
            ),
        }
    ]
    return {
        "clave": CLAVE_DE_CIMIENTO,
        "cotas": {"desplante_m": i.cota_desplante_m, "corona_m": i.cota_corona_m, "altura_m": alto},
        "longitud_m": i.longitud_m,
        "seccion": m["seccion"],
        "escarpio": {k: m["escarpio"][k] for k in ("minimo", "real", "cumple")},
        "dentellon": m["dentellon"],
        "volumen_m3_ml": v["total_m3_ml"],
        "volumen_m3": total,
        "insumos": {
            "piedra_a_comprar_m3": v["piedra_a_comprar_m3_ml"] * i.longitud_m,
            "cemento_kg": v["cemento_kg_ml"] * i.longitud_m,
            "arena_m3": v["arena_m3_ml"] * i.longitud_m,
            "agua_l": v["agua_l_ml"] * i.longitud_m,
        },
        "conceptos": conceptos,
        "por_espacio": [{"espacio_id": i.espacio_id, "conceptos": [dict(c) for c in conceptos]}],
        "no_incluye": [dict(x) for x in m["no_incluye"]],
        "mano_de_obra": {
            "estado": "sin_mano_de_obra",
            "nota": "El elemento no calcula mano de obra con importe: el destajo del concepto MCT-01011 del catálogo no se toca. Sin precios.",
        },
        "advertencias": advertencias,
        "pendientes": [dict(p) for p in PENDIENTES],
    }
