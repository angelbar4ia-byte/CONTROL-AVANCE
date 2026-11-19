"""Bastones por longitud de trazo (plan de elementos de muro, Ola 4, lane 4D; mockup BA-1, M-38, Q22, Q27, Q28, Q30).

El **bastón** es una varilla corta (de espera o de refuerzo) que se coloca a cada ``sep_cm`` a lo largo de un trazo. El elemento se
mide por **metro de trazo**; sus parámetros son la varilla, la separación y el largo del bastón. Aquí vive todo el cálculo
(dominio puro, sin base de datos); la tarjeta solo manda parámetros y dibuja lo que responde.

Reglas (del mockup y de lo ya construido en `receta_acero`; nada se inventa):

- **Piezas**: ``ceil(trazo ÷ separación) + 1`` bastones. Para comparar con el catálogo (que paga por metro) se usa el coeficiente
  continuo ``100 ÷ separación`` bastones por metro.
- **Corte ajustado a módulos** (Q28, valor más conservador): el bastón (con su gancho) se corta con la regla de cortes de `receta_acero.corte_de`
  (módulos de 1, 1.5, 2, 3, 4 y 6 m que caben en la varilla de 12 m, con traslape de 40 diámetros entre piezas si un solo módulo no
  alcanza). Cada bastón gasta el módulo completo: un bastón de 0.80 m se corta de un módulo de 1.00 m, uno de 1.20 m de uno de 1.50 m.
  Las varillas de 12 m salen de ``ceil(bastones × piezas por bastón ÷ floor(12 ÷ módulo))``. El corte exacto del mockup
  (``floor(12 ÷ largo)`` bastones por varilla) se calcula **también** y se muestra como referencia, no es lo que se paga.
- **Gancho** (decisión E1 del usuario, 2026-11-19: «corte ajustado a módulos con todo y gancho»): el gancho **se incluye en la longitud
  de corte**. ``largo_cm`` es el tramo recto del bastón (el que nombra el escalón del catálogo) y el corte es
  ``largo + puntas + ganchos × gancho``. El gancho es un parámetro explícito: ``ganchos`` por bastón (0 a 2; 2 = uno en cada punta),
  ``gancho_diametros`` (12 por defecto) y, si se captura, ``gancho_cm`` que manda sobre los diámetros. Longitud de un gancho =
  ``gancho_cm`` si se capturó, si no ``gancho_diametros × diámetro de la varilla`` (3/8 → 11.43 cm, 1/2 → 15.24 cm, 5/8 → 19.05 cm,
  3/4 → 22.86 cm). El mockup (`spec.js`, Q28 y Q60) **no trae una tabla de ganchos por diámetro**: solo el ``gancho_cm`` fijo de los
  anillos (10 y 16.5 cm) y, en `drivers.py`, «gancho de 12 diámetros en un remate»; de ahí sale el 12. Con ``ganchos = 0`` el bastón
  vuelve a «sin gancho». El desglose del cálculo trae el bloque ``gancho`` con la fórmula y el origen de cada valor.
- **Puntas**: ``puntas_cm`` (0 por defecto): anclaje adicional que no es gancho (se suma igual al corte).
- **Pago por pieza** (Q28): se informan los bastones (pza) con los avisos del caso; el catálogo los paga por metro de trazo (unidad M)
  y por eso se concilia el coeficiente de varilla por metro contra el escalón del catálogo.
- **Escalón**: el catálogo trae bastones de varilla 3/8 por largo y separación (`AUX-02xxx`, unidad M = metro de trazo). Se elige el
  escalón de la misma separación cuyo largo coincide; si no coincide se usa el primero más largo y se **avisa** (se paga de más); si
  no hay (otra varilla, otra separación o un largo que rebasa el último escalón) se **avisa y se propone un concepto nuevo** con clave
  provisional, sin precio ni destajo, pendiente de autorizar por Control de obra (Q27, Q30). El catálogo no se edita.

Los números del catálogo salen de `CATALOGO_DE_MATERIALES.csv` y `ANALISIS_DE_BASICOS_CONCEPTOS.csv` (opus); la línea del CSV que
cita cada escalón la comprueba `scripts/verificar_baston_contra_csv.py` cuando se corre a mano.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from obractrl.domain.cuantificacion.comparacion_con_catalogo import (
    FilaDeComposicion,
    comparar_con_concepto,
)
from obractrl.domain.cuantificacion.elementos_parametricos import PESO_VARILLA_KG_M
from obractrl.domain.cuantificacion.receta_acero import (
    DriversDeReceta,
    ErrorDeRecetaAcero,
    corte_de,
    diametro_de_varilla_m,
)
from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = [
    "CLAVE_ELEMENTO",
    "ESCALONES_DE_CATALOGO",
    "GANCHOS_POR_BASTON_POR_DEFECTO",
    "GANCHO_DIAMETROS_POR_DEFECTO",
    "PENDIENTES",
    "VARILLAS",
    "ElementoDeBastonNoEncontrado",
    "EntradaDeBaston",
    "ErrorDeBaston",
    "calcular_baston",
    "categorias_de_biblioteca",
    "concepto_nuevo_de",
    "definicion_de",
    "escalon_para",
    "gancho_de",
    "propuestas_de_actualizacion_de_apu",
]

CLAVE_ELEMENTO = "BA-1"
NOMBRE_DEL_ELEMENTO = "Bastón de varilla"
LARGO_DE_VARILLA_M = 12.0
_EPS = 1e-9

VARILLAS: dict[int, tuple[str, str]] = {
    3: ("ACR-00001", "3/8"),
    4: ("ACR-00002", "1/2"),
    5: ("ACR-00003", "5/8"),
    6: ("ACR-00004", "3/4"),
}
"""Número de varilla → (clave del insumo, nombre), de `CATALOGO_DE_MATERIALES.csv` (familia Acero de refuerzo)."""

CLAVE_ALAMBRE = "ACE-00001"

GANCHO_DIAMETROS_POR_DEFECTO = 12.0
"""Longitud del gancho en diámetros de varilla: el «gancho de 12 diámetros» de `drivers.py` (`puntas_superior_diametros`). El mockup no trae
una tabla por diámetro (Q28/Q60 siguen abiertas): es un parámetro explícito, por confirmar con el estructurista."""
GANCHOS_POR_BASTON_POR_DEFECTO = 2
"""Ganchos por bastón: 2 = uno en cada punta («agregar gancho a las puntas del bastón», E1). Por confirmar."""

ESCALONES_DE_CATALOGO: tuple[tuple[str, float, int, float, float, int, int, int], ...] = (
    # (clave, largo m, separación cm, varilla 3/8 pza por metro de trazo, alambre recocido kg por metro de trazo,
    #  línea en CATALOGO_DE_MATERIALES.csv, línea de ACR-00001 y línea de ACE-00001 en ANALISIS_DE_BASICOS_CONCEPTOS.csv)
    ("AUX-02042", 1.0, 15, 0.75, 0.205905, 68, 370, 371),
    ("AUX-02011", 1.2, 15, 0.72, 0.164724, 55, 344, 345),
    ("AUX-02013", 1.2, 18, 0.9, 0.27454, 57, 348, 349),
    ("AUX-02141", 1.7, 18, 0.85, 0.228783, 81, 396, 397),
    ("AUX-02090", 0.65, 20, 0.2925, 0.082362, 77, 388, 389),
    ("AUX-02110", 0.85, 20, 0.3825, 0.082362, 79, 392, 393),
    ("AUX-02120", 0.9, 20, 0.405, 0.082362, 80, 394, 395),
    ("AUX-02041", 1.0, 20, 0.45, 0.123543, 67, 368, 369),
    ("AUX-02012", 1.2, 20, 0.54, 0.164724, 56, 346, 347),
    ("AUX-02021", 1.5, 20, 0.675, 0.247086, 60, 354, 355),
    ("AUX-02051", 1.71, 20, 0.7713, 0.247086, 70, 374, 375),
    ("AUX-02031", 2.0, 20, 0.9, 0.288267, 64, 362, 363),
    ("AUX-02082", 2.4, 20, 1.08, 0.247086, 75, 384, 385),
    ("AUX-02040", 1.0, 25, 0.36, 0.098834, 66, 366, 367),
    ("AUX-02010", 1.2, 25, 0.432, 0.164724, 54, 342, 343),
    ("AUX-02020", 1.5, 25, 0.54, 0.197669, 59, 352, 353),
    ("AUX-02030", 2.0, 25, 0.72, 0.230614, 63, 360, 361),
    ("AUX-02080", 2.4, 25, 0.864, 0.197669, 74, 382, 383),
    ("AUX-02060", 0.9, 40, 0.2025, 0.061772, 72, 378, 379),
    ("AUX-02043", 1.0, 40, 0.225, 0.061772, 69, 372, 373),
    ("AUX-02014", 1.2, 40, 0.27, 0.061772, 58, 350, 351),
    ("AUX-02023", 1.5, 40, 0.3375, 0.123543, 62, 358, 359),
    ("AUX-02033", 2.0, 40, 0.45, 0.123543, 65, 364, 365),
    ("AUX-02100", 4.0, 40, 0.9, 0.185315, 78, 390, 391),
    ("AUX-02072", 0.8, 50, 0.144, 0.049417, 73, 380, 381),
    ("AUX-02022", 1.5, 50, 0.27, 0.098834, 61, 356, 357),
    ("AUX-02053", 1.71, 50, 0.3078, 0.082362, 71, 376, 377),
    ("AUX-02083", 2.4, 50, 0.432, 0.098834, 76, 386, 387),
)
"""Los escalones que el catálogo trae: bastones de varilla 3/8, por metro de trazo (unidad M). Sin precios: el elemento no los usa."""

PENDIENTES: tuple[dict[str, str], ...] = (
    {
        "clave": "Q28",
        "texto": "¿El largo del bastón se corta exacto de la varilla o se ajusta a los módulos de corte (1, 1.5, 2, 3, 4 y 6 m)? ¿Se paga "
        "por metro de trazo, por pieza o por kg? ¿Lleva gancho o traslape? Decidido (E1): corte ajustado a módulos, pago por pieza con "
        "avisos y CON gancho incluido en la longitud de corte (12 diámetros por punta, 2 ganchos; por confirmar con el estructurista); "
        "el corte exacto se muestra como referencia.",
    },
    {
        "clave": "Q27",
        "texto": "Cuando el bastón rebasa el último escalón del catálogo (4.00 m a 40 cm) no hay concepto: el sistema avisa y propone uno "
        "nuevo. ¿Se crean escalones más largos?",
    },
    {
        "clave": "Q30",
        "texto": "Los largos que el catálogo no trae a una separación (por ejemplo 1.35 m a 25 cm) se crean como concepto nuevo propuesto: "
        "¿con qué largo máximo por escalón y qué precio? No se pone precio ni destajo.",
    },
    {
        "clave": "Q22",
        "texto": "Traslape de 40 diámetros entre las piezas de un bastón que no cabe en un solo módulo (confirmado por el usuario); las "
        "puntas del bastón se capturan, hoy 0 cm; el gancho es aparte (E1).",
    },
    {
        "clave": "E1",
        "texto": "Hecho: el gancho entra en la longitud de corte (2 ganchos de 12 diámetros por bastón, parámetros explícitos). Por confirmar "
        "con el estructurista: cuántos ganchos lleva un bastón y cuánto mide por diámetro; el mockup no trae esa tabla.",
    },
    {
        "clave": "E2",
        "texto": "PENDIENTE (no construido): traslape de 40 diámetros entre piezas de un bastón de más de 6 m (respuesta del usuario: sí).",
    },
    {
        "clave": "E3",
        "texto": "PENDIENTE (no construido): escalones nuevos (largos como 1.35 o 7 m, separación de 30 cm, varillas de 1/2 a 3/4) como "
        "propuesta, y que Costos defina el precio. Hoy se avisa y se propone el concepto nuevo provisional, sin precio.",
    },
    {
        "clave": "E4",
        "texto": "PENDIENTE (no construido): alambre de amarre de los bastones (respuesta del usuario: sí, después de definir la fórmula).",
    },
)


class ErrorDeBaston(ErrorDeCuantificacion):
    """Un parámetro del bastón que no vale."""


class ElementoDeBastonNoEncontrado(ErrorDeBaston):
    """No hay un bastón con esa clave."""


def _nombre_de_varilla(numero: int) -> str:
    return VARILLAS[numero][1]


def _descripcion_de(numero: int, largo_cm: float, sep_cm: float) -> str:
    return f'Bastones var {_nombre_de_varilla(numero)}" de {largo_cm / 100:.2f} @{sep_cm:g} cm'


def clave_provisional(numero: int, largo_cm: float, sep_cm: float) -> str:
    """La clave provisional de un escalón que el catálogo no trae: no existe en ningún CSV (lo comprueba el script de verificación)."""
    return f"AUX-B{numero}-{round(largo_cm)}-{round(sep_cm)}"


# --- Entrada y cálculo -------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class EntradaDeBaston:
    """Lo que se captura. `trazo_m` es la longitud de trazo a cubrir."""

    trazo_m: float = 1.0
    varilla_numero: int = 3
    sep_cm: float = 25.0
    largo_cm: float = 120.0
    puntas_cm: float = 0.0
    """Anclaje adicional que no es gancho: 0 por defecto."""
    ganchos: int = GANCHOS_POR_BASTON_POR_DEFECTO
    """Ganchos por bastón (0 = sin gancho, 2 = uno en cada punta). El gancho entra en la longitud de corte (E1)."""
    gancho_diametros: float = GANCHO_DIAMETROS_POR_DEFECTO
    """Largo de cada gancho en diámetros de la varilla; solo vale si no se captura `gancho_cm`."""
    gancho_cm: float | None = None
    """Largo de cada gancho en cm; si se captura, manda sobre `gancho_diametros`."""
    traslape_diametros: float = 40.0
    """Entre las piezas de un bastón largo; 40 diámetros confirmado (Q22). Es el driver `traslape_varilla_diametros`."""
    tolerancia_corte_cm: float = 0.0
    """Falta que se acepta sin pasar al corte siguiente. Es el driver `tolerancia_corte_cm`."""
    max_piezas_corte: int = 3
    """Máximo de piezas por bastón largo. Es el driver `max_piezas_corte`."""


def _validar(i: EntradaDeBaston) -> None:
    if not (0 < i.trazo_m <= 1_000_000):
        raise ErrorDeBaston("La longitud de trazo debe ser mayor que cero.")
    if i.varilla_numero not in VARILLAS:
        raise ErrorDeBaston(f"La varilla es una de {', '.join(f'no. {n} ({v[1]})' for n, v in VARILLAS.items())}.")
    if not (5 <= i.sep_cm <= 200):
        raise ErrorDeBaston("La separación va de 5 a 200 cm.")
    if not (10 <= i.largo_cm <= 3000):
        raise ErrorDeBaston("El largo del bastón va de 10 a 3000 cm.")
    if not (0 <= i.puntas_cm <= 100):
        raise ErrorDeBaston("Las puntas van de 0 a 100 cm.")
    if not (0 <= i.ganchos <= 2):
        raise ErrorDeBaston("Los ganchos por bastón son 0, 1 o 2.")
    if not (0 <= i.gancho_diametros <= 40):
        raise ErrorDeBaston("El gancho va de 0 a 40 diámetros.")
    if i.gancho_cm is not None and not (0 <= i.gancho_cm <= 100):
        raise ErrorDeBaston("El gancho va de 0 a 100 cm.")
    if not (0 <= i.traslape_diametros <= 100):
        raise ErrorDeBaston("El traslape va de 0 a 100 diámetros.")
    if not (0 <= i.tolerancia_corte_cm <= 200):
        raise ErrorDeBaston("La tolerancia de corte va de 0 a 200 cm.")
    if not (1 <= i.max_piezas_corte <= 12):
        raise ErrorDeBaston("El máximo de piezas por corte va de 1 a 12.")


def gancho_de(i: EntradaDeBaston) -> dict[str, Any]:
    """El gancho explícito del bastón: cuántos, cuánto mide cada uno y de dónde sale ese valor. Fórmula: ``ganchos × longitud``."""
    diametro_cm = diametro_de_varilla_m(i.varilla_numero) * 100
    if i.gancho_cm is not None:
        cada_cm, origen = i.gancho_cm, "gancho_cm capturado"
    else:
        cada_cm, origen = i.gancho_diametros * diametro_cm, f"{i.gancho_diametros:g} diámetros × {diametro_cm:.4f} cm de diámetro de la varilla"
    total_cm = i.ganchos * cada_cm
    return {
        "ganchos": i.ganchos,
        "diametros": i.gancho_diametros,
        "diametro_varilla_cm": round(diametro_cm, 6),
        "longitud_cm": round(cada_cm, 6),
        "total_por_baston_cm": round(total_cm, 6),
        "origen": origen,
        "formula": "corte = largo + puntas + ganchos × longitud del gancho",
    }


def _techo(x: float) -> int:
    return math.ceil(x - _EPS)


def _por_varilla(modulo_m: float) -> int:
    return max(1, math.floor(LARGO_DE_VARILLA_M / modulo_m + _EPS))


def _plan_ajustado(i: EntradaDeBaston, n_bastones: int, peso: float, gancho_m: float) -> dict[str, Any]:
    d = DriversDeReceta(
        traslape_varilla_diametros=i.traslape_diametros, tolerancia_corte_cm=i.tolerancia_corte_cm, max_piezas_corte=i.max_piezas_corte
    )
    traslape_m = i.traslape_diametros * diametro_de_varilla_m(i.varilla_numero)
    try:
        c = corte_de(i.largo_cm / 100, LARGO_DE_VARILLA_M, traslape_m, i.puntas_cm / 100 + gancho_m, d)
    except ErrorDeRecetaAcero as e:  # pragma: no cover - los módulos siempre caben en la varilla de 12 m
        raise ErrorDeBaston(str(e)) from e
    if not c.cubre_completo:
        raise ErrorDeBaston("El bastón es demasiado largo: ni 12 piezas de 6 m con su traslape alcanzan.")
    piezas = n_bastones * c.n
    barras = _techo(piezas / _por_varilla(c.modulo_m))
    material = piezas * c.modulo_m
    return {
        "corte": {
            "piezas_por_baston": c.n,
            "modulo_m": c.modulo_m,
            "material_por_baston_m": c.total_m,
            "traslape_m": round(c.traslape_m, 6) if c.n > 1 else 0.0,
            "puntas_m": i.puntas_cm / 100,
            "gancho_m": gancho_m,
            "necesario_m": c.necesario_m,
            "sobrante_por_baston_m": round(max(0.0, c.total_m - c.traslapes_m - c.necesario_m), 6),
            "piezas_por_varilla": _por_varilla(c.modulo_m),
            "excede_maximo": c.excede_maximo,
        },
        "bastones": n_bastones,
        "varillas": barras,
        "material_m": material,
        "kg": material * peso,
        "sobra_m": barras * LARGO_DE_VARILLA_M - material,
        "_por_metro": (100 / i.sep_cm) * c.n / _por_varilla(c.modulo_m),
    }


def _plan_exacto(i: EntradaDeBaston, n_bastones: int, peso: float, gancho_m: float) -> dict[str, Any]:
    """La referencia del mockup: cada bastón se corta de su largo exacto (más las puntas y el gancho); sin módulos."""
    traslape_m = i.traslape_diametros * diametro_de_varilla_m(i.varilla_numero)
    necesario = i.largo_cm / 100 + i.puntas_cm / 100 + gancho_m
    if necesario <= LARGO_DE_VARILLA_M + _EPS:
        por_varilla = max(1, math.floor(LARGO_DE_VARILLA_M / necesario + _EPS))
        barras = _techo(n_bastones / por_varilla)
        material = n_bastones * necesario
        por_metro = (100 / i.sep_cm) / por_varilla
    else:
        piezas = _techo((necesario - traslape_m) / (LARGO_DE_VARILLA_M - traslape_m))
        material = n_bastones * (necesario + (piezas - 1) * traslape_m)
        barras = _techo(material / LARGO_DE_VARILLA_M)
        por_metro = (100 / i.sep_cm) * (necesario + (piezas - 1) * traslape_m) / LARGO_DE_VARILLA_M
    return {
        "bastones": n_bastones,
        "varillas": barras,
        "material_m": material,
        "kg": material * peso,
        "sobra_m": barras * LARGO_DE_VARILLA_M - material,
        "_por_metro": por_metro,
    }


# --- Escalón del catálogo ------------------------------------------------------------------------------------------------------


def escalon_para(numero: int, largo_cm: float, sep_cm: float) -> dict[str, Any]:
    """El escalón del catálogo que corresponde a un bastón: `exacto`, `mayor` (el primero más largo a la misma separación, se paga
    de más) o `sin_escalon` (hay que proponer un concepto nuevo). No toca el catálogo ni pone precio."""
    nombre = _nombre_de_varilla(numero)
    if numero != 3:
        return {
            "estado": "sin_escalon",
            "motivo": f"El catálogo solo trae bastones de varilla 3/8, no de {nombre}.",
            "escalon": None,
        }
    mismos = sorted((e for e in ESCALONES_DE_CATALOGO if abs(e[2] - sep_cm) < 1e-6), key=lambda e: e[1])
    if not mismos:
        seps = sorted({e[2] for e in ESCALONES_DE_CATALOGO})
        return {
            "estado": "sin_escalon",
            "motivo": f"El catálogo no trae bastones a {sep_cm:g} cm (trae {', '.join(str(s) for s in seps)} cm).",
            "escalon": None,
        }
    largo_m = largo_cm / 100
    for e in mismos:
        if abs(e[1] - largo_m) < 0.005:
            return {"estado": "exacto", "motivo": None, "escalon": e}
    for e in mismos:
        if e[1] > largo_m:
            return {
                "estado": "mayor",
                "motivo": f"El catálogo no trae el bastón de {largo_m:.2f} m a {sep_cm:g} cm; el escalón más cercano que lo cubre es "
                f"{e[0]} de {e[1]:.2f} m (se pagaría {e[1] - largo_m:.2f} m de más por bastón).",
                "escalon": e,
            }
    ultimo = mismos[-1]
    return {
        "estado": "sin_escalon",
        "motivo": f"El bastón de {largo_m:.2f} m rebasa el último escalón del catálogo a {sep_cm:g} cm ({ultimo[0]}, {ultimo[1]:.2f} m): "
        "no hay concepto que lo pague (Q27).",
        "escalon": None,
    }


def _concepto_de(eleccion: dict[str, Any], i: EntradaDeBaston) -> dict[str, Any]:
    e = eleccion["escalon"]
    if eleccion["estado"] != "sin_escalon" and e is not None:
        return {
            "clave": e[0],
            "descripcion": _descripcion_de(3, e[1] * 100, e[2]),
            "unidad": "ml",
            "estado": "catalogo",
            "clave_provisional": False,
            "escalon": eleccion["estado"],
            "largo_m": e[1],
            "sep_cm": float(e[2]),
        }
    return {
        "clave": clave_provisional(i.varilla_numero, i.largo_cm, i.sep_cm),
        "descripcion": _descripcion_de(i.varilla_numero, i.largo_cm, i.sep_cm),
        "unidad": "ml",
        "estado": "propuesto",
        "clave_provisional": True,
        "escalon": "sin_escalon",
        "largo_m": i.largo_cm / 100,
        "sep_cm": i.sep_cm,
    }


def _conciliacion(eleccion: dict[str, Any], i: EntradaDeBaston, por_metro: float) -> list[dict[str, Any]]:
    e = eleccion["escalon"]
    if e is None:
        return []
    clave = VARILLAS[3][0]
    composicion = [
        FilaDeComposicion(clave, e[3], "VARILLA 3/8", "pza"),
        FilaDeComposicion(CLAVE_ALAMBRE, e[4], "ALAMBRE RECOCIDO", "kg"),
    ]
    r = comparar_con_concepto({clave: por_metro}, composicion)
    return [
        {
            "concepto": {"clave": e[0], "descripcion": _descripcion_de(3, e[1] * 100, e[2]), "unidad": "ml"},
            "sobre": "por metro de trazo",
            "filas": r["filas"],
            "mano_de_obra": r["mano_de_obra"],
            "resumen": r["resumen"],
            "coincide": r["coincide"],
            "fuente_de_las_filas": [f"ANALISIS_DE_BASICOS_CONCEPTOS:{e[6]}", f"ANALISIS_DE_BASICOS_CONCEPTOS:{e[7]}"],
            "avisos": [
                "El bastón no calcula el alambre recocido de amarre: queda «solo en el catálogo» y no se inventa.",
                *(
                    ["El escalón del catálogo es del bastón recto: el gancho incluido en el corte explica parte de la diferencia de la varilla."]
                    if i.ganchos > 0
                    else []
                ),
                *(
                    [f"El escalón {e[0]} es de {e[1]:.2f} m y el bastón es de {i.largo_cm / 100:.2f} m: se compara contra el escalón que lo cubre."]
                    if eleccion["estado"] == "mayor"
                    else []
                ),
            ],
        }
    ]


def calcular_baston(i: EntradaDeBaston) -> dict[str, Any]:
    """Los bastones, varillas y kg de un trazo, el escalón del catálogo que los paga y su conciliación. Sin precios."""
    _validar(i)
    insumo, nombre = VARILLAS[i.varilla_numero]
    peso = PESO_VARILLA_KG_M[i.varilla_numero]
    n = _techo(i.trazo_m * 100 / i.sep_cm) + 1
    gancho = gancho_de(i)
    gancho_m = gancho["total_por_baston_cm"] / 100
    ajustado = _plan_ajustado(i, n, peso, gancho_m)
    exacto = _plan_exacto(i, n, peso, gancho_m)
    eleccion = escalon_para(i.varilla_numero, i.largo_cm, i.sep_cm)
    concepto = _concepto_de(eleccion, i)
    avisos: list[str] = []
    c = ajustado["corte"]
    if c["piezas_por_baston"] > 1:
        avisos.append(
            f"El bastón de {i.largo_cm / 100:.2f} m no cabe en un solo módulo: se corta en {c['piezas_por_baston']} piezas de "
            f"{c['modulo_m']:g} m con traslape de {c['traslape_m']:.2f} m."
        )
    if i.ganchos > 0 and gancho["total_por_baston_cm"] > 0:
        avisos.append(
            f"Gancho incluido en el corte (E1): {i.ganchos} × {gancho['longitud_cm']:.2f} cm = {gancho['total_por_baston_cm']:.2f} cm por bastón "
            f"({gancho['origen']}); el bastón se corta de {c['necesario_m']:.2f} m. Longitud por confirmar con el estructurista."
        )
    if c["excede_maximo"]:
        avisos.append("El corte pasa del máximo de piezas por corte: revisar el largo del bastón.")
    if ajustado["varillas"] > exacto["varillas"] or ajustado["kg"] > exacto["kg"] + 1e-9:
        avisos.append(
            f"Con el corte ajustado a módulos salen {ajustado['varillas']} varillas y {ajustado['kg']:.2f} kg; con el corte exacto "
            f"saldrían {exacto['varillas']} y {exacto['kg']:.2f} kg (Q28: se toma el ajustado, más conservador)."
        )
    if eleccion["motivo"]:
        avisos.append(eleccion["motivo"])
    if concepto["estado"] == "propuesto":
        avisos.append(
            f"Falta el escalón en el catálogo: se propone el concepto nuevo {concepto['clave']} (clave provisional, sin precio ni destajo), "
            "pendiente de autorizar por Control de obra."
        )
    avisos.append("Pago por pieza (Q28): el catálogo paga el bastón por metro de trazo; el cálculo da piezas, varillas y kg.")
    por_metro = ajustado["_por_metro"]
    ajustado.pop("_por_metro")
    exacto.pop("_por_metro")
    return {
        "clave": CLAVE_ELEMENTO,
        "nombre": f'{NOMBRE_DEL_ELEMENTO} de {nombre}" a cada {i.sep_cm:g} cm',
        "unidad": "ml de trazo",
        "trazo_m": i.trazo_m,
        "varilla": {"clave": insumo, "numero": i.varilla_numero, "nombre": nombre, "peso_kg_m": peso, "largo_m": LARGO_DE_VARILLA_M},
        "parametros": {
            "sep_cm": i.sep_cm,
            "largo_cm": i.largo_cm,
            "puntas_cm": i.puntas_cm,
            "ganchos": float(i.ganchos),
            "gancho_diametros": i.gancho_diametros,
            "gancho_cm": gancho["longitud_cm"],
            "traslape_diametros": i.traslape_diametros,
            "tolerancia_corte_cm": i.tolerancia_corte_cm,
            "max_piezas_corte": float(i.max_piezas_corte),
        },
        "bastones_por_metro": 100 / i.sep_cm,
        "gancho": gancho,
        "ajustado": ajustado,
        "exacto": exacto,
        "varillas_por_metro": por_metro,
        "pago": {
            "modo": "pieza",
            "unidad": "pza",
            "cantidad": n,
            "texto": "Pago por pieza (Q28, lo más conservador): se cuenta cada bastón.",
        },
        "concepto": concepto,
        "escalon": eleccion["estado"],
        "conciliacion": _conciliacion(eleccion, i, por_metro),
        "avisos": avisos,
    }


# --- Ficha y biblioteca --------------------------------------------------------------------------------------------------------


def definicion_de(clave: str) -> dict[str, Any]:
    if clave != CLAVE_ELEMENTO:
        raise ElementoDeBastonNoEncontrado(f"No hay un bastón con la clave {clave}.")
    return {
        "clave": CLAVE_ELEMENTO,
        "nombre": NOMBRE_DEL_ELEMENTO,
        "tipo": "baston",
        "se_mide_por": "metro lineal de trazo",
        "categoria": {"clave": "aceros", "nombre": "Acero de refuerzo"},
        "subcategoria": {"clave": "bastones", "nombre": "Bastones"},
        "parametros_por_defecto": {
            "varilla_numero": 3,
            "sep_cm": 25.0,
            "largo_cm": 120.0,
            "puntas_cm": 0.0,
            "ganchos": GANCHOS_POR_BASTON_POR_DEFECTO,
            "gancho_diametros": GANCHO_DIAMETROS_POR_DEFECTO,
            "traslape_diametros": 40.0,
            "trazo_m": 1.0,
        },
        "varillas": [
            {"numero": n, "clave": v[0], "nombre": v[1], "peso_kg_m": PESO_VARILLA_KG_M[n]} for n, v in VARILLAS.items()
        ],
        "modulos_de_corte_m": [1.0, 1.5, 2.0, 3.0, 4.0, 6.0],
        "escalones": [
            {"clave": e[0], "largo_m": e[1], "sep_cm": float(e[2]), "varilla_pza_por_ml": e[3], "alambre_kg_por_ml": e[4]}
            for e in sorted(ESCALONES_DE_CATALOGO, key=lambda x: (x[2], x[1]))
        ],
        "fuente": "CATALOGO_DE_MATERIALES.csv (Bastones var 3/8, AUX-02xxx) y ANALISIS_DE_BASICOS_CONCEPTOS.csv; módulos de corte de receta_acero",
        "pendientes": [dict(p) for p in PENDIENTES],
    }


def categorias_de_biblioteca() -> tuple[dict[str, Any], ...]:
    return (
        {
            "clave": "aceros",
            "nombre": "Acero de refuerzo",
            "prefijo": "BA",
            "subcategorias": (
                {
                    "clave": "bastones",
                    "nombre": "Bastones",
                    "prefijo": "BA",
                    "elementos": (
                        {
                            "clave": CLAVE_ELEMENTO,
                            "nombre": NOMBRE_DEL_ELEMENTO,
                            "tipo": "baston",
                            "se_mide_por": "metro lineal de trazo",
                            "concepto": {
                                "clave": "AUX-02xxx",
                                "descripcion": "Bastones var 3/8 por largo y separación (escalón del catálogo)",
                                "unidad": "ml",
                            },
                        },
                    ),
                },
            ),
        },
    )


# --- Propuestas ------------------------------------------------------------------------------------------------------------------


def concepto_nuevo_de(i: EntradaDeBaston) -> dict[str, Any]:
    """El concepto nuevo de un escalón que el catálogo no trae (clave provisional, sin destajo ni precio)."""
    r = calcular_baston(i)
    c = r["concepto"]
    if c["estado"] != "propuesto":
        raise ErrorDeBaston(f"El catálogo ya trae el escalón {c['clave']}: no hace falta un concepto nuevo.")
    return {
        "elemento_clave": CLAVE_ELEMENTO,
        "concepto_clave": c["clave"],
        "clase": "concepto_nuevo",
        "resumen": f"Concepto nuevo {c['clave']} (clave provisional): {c['descripcion']}, por metro de trazo, sin destajo ni precio",
        "detalle": {
            "descripcion": c["descripcion"],
            "unidad": "ml",
            "clave_provisional": True,
            "insumos": {r["varilla"]["clave"]: round(r["varillas_por_metro"], 6)},
            "motivos": [
                "Q27/Q30: el catálogo no trae este escalón de bastón; queda como concepto nuevo propuesto, pendiente de autorizar por Control de obra.",
                "Q28/E1: corte ajustado a módulos con el gancho incluido en la longitud de corte; el alambre de amarre no se calcula.",
                "Sin destajo: pendiente de definir por Costos. Sin precio.",
            ],
            "cambios": [],
        },
    }


def propuestas_de_actualizacion_de_apu(calculo: Mapping[str, Any]) -> list[dict[str, Any]]:
    """«Confirmar cálculo → actualizar APU»: una versión propuesta del escalón del catálogo si su varilla por metro difiere del cálculo
    (marca ≈ o ≠). El catálogo no se edita. Sin cambios, no hay propuesta."""
    propuestas: list[dict[str, Any]] = []
    for bloque in calculo["conciliacion"]:
        cambios = [
            {"insumo": f["clave"], "unidad": f["unidad"], "antes": float(f["catalogo"]), "despues": round(float(f["elemento"]), 6)}
            for f in bloque["filas"]
            if f["marca"] in ("≈", "≠") and f["catalogo"] is not None and f["elemento"] is not None
        ]
        if not cambios:
            continue
        concepto = bloque["concepto"]["clave"]
        propuestas.append(
            {
                "elemento_clave": CLAVE_ELEMENTO,
                "concepto_clave": concepto,
                "clase": "version_de_concepto",
                "resumen": f"Nueva versión de {concepto}: " + "; ".join(f"{c['insumo']} {c['antes']:g} → {c['despues']:g}" for c in cambios),
                "detalle": {
                    "cambios": cambios,
                    "motivos": ["Confirmar cálculo → actualizar APU: la varilla por metro con el corte ajustado a módulos (Q28)."],
                    "hasta_m": None,
                },
            }
        )
    return propuestas
