"""El paramétrico de muro (F-22): cómo se construye un muro y qué capas de acabado lleva.

Es solo clasificación: ni el tipo ni el acabado cambian lo que mide el muro. Sirven para sumar después por tipo y capa
(el resumen por driver, F-23) contra el catálogo paramétrico.

Tipos (D-645, 0133):
- ``confinado``: con cadenas y castillos aún sin ubicar (se estiman por separación); para algo rápido.
- ``con_cadena``: los castillos ya se conocen y se colocan; restan de los m² del muro.
- ``tabique``: sin cadenas ni castillos.

Pretil y barda **ya no son tipos**: son ubicaciones del muro (``muro_ubicacion``, ver ``muro_ubicacion``), y el sillar es un
material (``muro_material``). Un muro se describe con tipo, material, ubicación y los elementos de su plantilla (M-4).

Acabado: capas con Sí/No por cara, ``interior`` y ``fachada``: obra gris (repellado), obra blanca (fino) y pintura. El
revestimiento no es una capa: es un concepto del catálogo con su largo y su altura.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

TIPOS_DE_MURO: tuple[str, ...] = ("confinado", "con_cadena", "tabique")
CASTILLO_MODO_POR_TIPO: dict[str, str | None] = {"confinado": "estimado", "con_cadena": "ubicado", "tabique": None}
"""Cómo se cuentan los castillos de cada tipo: estimados por separación, ubicados en el plano o ninguno (M-4)."""
TIPOS_ANTERIORES: tuple[str, ...] = ("sillar", "pretil", "barda")
"""Los tipos que existían antes de la 0133; ya no se aceptan (se migraron a ubicación o material)."""
CARAS_DE_ACABADO: tuple[str, ...] = ("interior", "fachada")
CAPAS_DE_ACABADO: tuple[str, ...] = ("gris", "blanca", "pintura")


def acabado_por_defecto() -> dict[str, dict[str, bool]]:
    """Nace con obra gris, obra blanca y pintura en Sí en las dos caras."""
    return {cara: dict.fromkeys(CAPAS_DE_ACABADO, True) for cara in CARAS_DE_ACABADO}


def acabado_normalizado(acabado: Mapping[str, Any] | None) -> dict[str, dict[str, bool]]:
    """El acabado completo: lo que falta se toma del defecto; lo que sobra o no vale es un error."""
    normal = acabado_por_defecto()
    if acabado is None:
        return normal
    for cara, capas in acabado.items():
        if cara not in CARAS_DE_ACABADO:
            raise ErrorDeCuantificacion(f"El acabado se define por cara: {', '.join(CARAS_DE_ACABADO)} (no «{cara}»).")
        if not isinstance(capas, Mapping):
            raise ErrorDeCuantificacion(f"El acabado de la cara «{cara}» debe decir Sí o No por capa.")
        for capa, valor in capas.items():
            if capa not in CAPAS_DE_ACABADO:
                raise ErrorDeCuantificacion(
                    f"Capas de acabado: {', '.join(CAPAS_DE_ACABADO)}. El revestimiento es un concepto, no una capa (no «{capa}»)."
                )
            if not isinstance(valor, bool):
                raise ErrorDeCuantificacion(f"La capa «{capa}» de «{cara}» es Sí o No.")
            normal[cara][capa] = valor
    return normal


def tipo_valido(tipo: str | None) -> str | None:
    if tipo is None:
        return None
    if tipo in TIPOS_ANTERIORES:
        raise ErrorDeCuantificacion(
            f"«{tipo}» ya no es un tipo de muro: pretil y barda son la ubicación del muro y el sillar es su material. "
            f"Tipo de muro: {', '.join(TIPOS_DE_MURO)}."
        )
    if tipo not in TIPOS_DE_MURO:
        raise ErrorDeCuantificacion(f"Tipo de muro: {', '.join(TIPOS_DE_MURO)} (no «{tipo}»).")
    return tipo
