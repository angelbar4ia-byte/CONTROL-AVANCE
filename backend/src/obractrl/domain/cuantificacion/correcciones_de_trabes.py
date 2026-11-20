"""Las correcciones al catálogo de las trabes (D7, Q56), como **versiones propuestas** de concepto.

Igual que las de los castillos (`correcciones_de_catalogo`): el catálogo y los CSV de opus no se editan. Lo que el catálogo trae mal se
propone como una **nueva versión del concepto** que solo Control de obra autoriza; la vigente sigue activa y la conciliación del
elemento muestra la diferencia. Dos conceptos del auxiliar de la trabe se corrigen:

- **AUX-10205 (T-2-12x20)** trae dos anillos (ANILLO 10X15 y ANILLO 8X15) donde la descripción habla de un solo estribo no. 2 @25 cm.
  La versión propuesta deja un anillo, con los kg que calcula el elemento (el perímetro del núcleo más el gancho), y quita el segundo.
- **AUX-00060 (T-5-12x30)** usa ANILLO 10X25 en una sección de 12×30: con 2.5 cm de recubrimiento el núcleo mide 7×25, y el anillo que
  trae es más ancho que la sección. Decisión del usuario (2026-11-20): el estribo de T-5 se hace con **ALAMBRÓN** (ACE-00002, kg, ya en
  el catálogo de insumos). La versión propuesta quita ACE-00006 y pone en ACE-00002 los kg reales del estribo, que calcula
  `receta_acero` (no se repite la fórmula aquí): largo del anillo = perímetro del núcleo (sección menos el recubrimiento por lado) ×
  `factor_anillo` + gancho; anillos por metro = 100 ÷ separación (12 cm); kg = anillos × largo × peso del alambrón por metro. Sin precio:
  el costo es el del catálogo de insumos.

La propuesta de **T-2-12x20** queda como está, marcada «pendiente de confirmar con Costos»: el usuario la revisa con Costos y no se autoriza
hasta entonces.

`antes` sale de la composición del catálogo que el elemento ya trae; `despues`, del cálculo del elemento por metro. Sin precios ni
destajos. Funciones puras, sin base de datos.
"""

from __future__ import annotations

from typing import Any

from obractrl.domain.cuantificacion.elementos_lineales import (
    EntradaElementoEstructural,
    calcular_elemento,
    elemento_estructural,
)
from obractrl.domain.cuantificacion.elementos_lineales_catalogo import INSUMOS

__all__ = ["correcciones_de_elemento_lineal"]

_Q56 = "Q56 / D7: "
PENDIENTE_CON_COSTOS = "Pendiente de confirmar con Costos: no se autoriza hasta que el usuario la revise con ellos."

_DEL_CALCULO_DE: dict[str, dict[str, str]] = {"T-5-12x30": {"ACE-00002": "ACE-00006"}}
"""Insumo nuevo de la versión propuesta → insumo del cálculo vigente del que toma sus kg (y que la propuesta quita).
El alambrón (ACE-00002) hace el estribo de T-5 con los mismos kg que calcula `receta_acero` para el anillo."""

_CORRECCIONES: dict[str, dict[str, str]] = {
    "T-2-12x20": {
        "ACE-00004": _Q56 + "el concepto trae dos anillos para un solo estribo no. 2 @25 cm; se deja uno, con los kg que calcula el elemento (perímetro del núcleo más gancho). " + PENDIENTE_CON_COSTOS,
        "ACE-00029": _Q56 + "segundo anillo del concepto (ANILLO 8X15) que la descripción no menciona; se quita.",
    },
    "T-5-12x30": {
        "ACE-00006": _Q56 + "el anillo 10×25 es más ancho que el núcleo de la sección 12×30 (7×25 con 2.5 cm de recubrimiento); el estribo de T-5 se hace con alambrón (ACE-00002): se quita el anillo.",
        "ACE-00002": _Q56 + "alambrón del estribo de T-5 (decisión del usuario, 2026-11-20): los kg son los reales que calcula el elemento (perímetro del núcleo × factor + gancho, a la separación del catálogo).",
    },
}
"""Qué insumos de qué trabe se corrigen y por qué. Solo lo que el usuario decidió corregir (D7)."""


def correcciones_de_elemento_lineal(clave: str) -> list[dict[str, Any]]:
    """Las propuestas de fábrica de la trabe (una por concepto del catálogo que se corrige; ninguna si no hay)."""
    e = elemento_estructural(clave)
    insumos = _CORRECCIONES.get(clave)
    if e is None or not insumos:
        return []
    concepto = e["catalogo"][0]
    calculo = calcular_elemento(EntradaElementoEstructural(clave=clave, modo="ml"))
    del_calculo: dict[str, float] = {}
    for f in calculo["conciliacion"][0]["filas"]:
        del_calculo[f["clave"]] = float(f["elemento"] or 0.0)
    cambios: list[dict[str, Any]] = []
    for insumo in insumos:
        antes = sum(fila[3] for fila in concepto["filas"] if fila[0] == insumo)
        unidad = next((fila[2] for fila in concepto["filas"] if fila[0] == insumo), None) or INSUMOS[insumo]["unidad"]
        sustituciones = _DEL_CALCULO_DE.get(clave, {})
        if insumo in sustituciones.values():
            despues = 0.0  # el insumo que el alambrón sustituye se quita
        else:
            despues = del_calculo.get(sustituciones.get(insumo, insumo), 0.0)
        cambios.append({"insumo": insumo, "unidad": unidad, "antes": round(antes, 6), "despues": round(despues, 6)})
    resumen = f"Nueva versión de {concepto['clave']}: " + "; ".join(
        f"{c['insumo']} {c['antes']:g} → {c['despues']:g}" for c in cambios
    )
    return [
        {
            "elemento_clave": clave,
            "concepto_clave": concepto["clave"],
            "clase": "version_de_concepto",
            "resumen": resumen,
            "detalle": {"cambios": cambios, "motivos": list(insumos.values()), "hasta_m": None},
        }
    ]

