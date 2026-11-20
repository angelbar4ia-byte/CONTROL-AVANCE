"""La matriz de conceptos de la losa (Fase 2 de las zonas de losa): concreto, cimbra, trabes, contratrabes y nervaduras de una zona.

La fase 1 (`zonas_de_losa`) solo trajo geometría y cotas: de qué losa cuelga un muro. La fase 2 construye **la losa como elemento**: a partir
de una zona (su espesor, el tipo de losa, los polígonos que la forman) y de los elementos de estructura que lleva (trabes, contratrabes y
nervaduras de la biblioteca 3B, por metro de trazo o por pieza), calcula **qué conceptos paga la zona y cuánto mide cada uno**.

Qué calcula
-----------
- **Área** de cada polígono de losa (con sus huecos, p. ej. el de la escalera) y, con ella, el **concreto** y la **cimbra** de la losa:
  - *Losa maciza*: concreto = área × espesor (el de la zona o el de la subzona); cimbra = 1 m² por m² de losa (el catálogo paga la cimbra
    ``MAD-00001`` por m² de losa).
  - *Losa nervada*: el concreto de la losa es la **capa de compresión** (5 cm, la del catálogo; editable) × área. Las nervaduras y las trabes
    son elementos de la zona y traen su propio concreto. **El casetón no se calcula**: el catálogo lo cuenta por pieza y su medida no está
    en el material del usuario (pregunta abierta).
- **Acero**: el de cada trabe, contratrabe y nervadura sale del elemento 3B (receta de acero con traslape de 40 diámetros, cortes por módulos,
  anillos, alambre). El de la **parrilla de la losa maciza** se toma del auxiliar del catálogo ``AUX-06010`` (varilla no. 3 @ 20 cm por m²:
  0.9 pza de ``ACR-00001`` y 0.20685 kg de ``ACE-00001`` por m², líneas 139 y 140 de ``ANALISIS_DE_BASICOS_COMPUESTOS``): es un dato del
  catálogo, no un cálculo nuevo. Bastones, malla y casetón de la losa nervada **no se calculan** (hay un auxiliar distinto por losa).
- **Conceptos**. Cada fila de la matriz dice qué concepto paga y cuánto mide en la unidad del concepto: el **acero** de cada elemento, con su
  auxiliar del catálogo (``AUX-xxxxx``, por ml); el **colado y cimbra** de un elemento con pago ``propio``, con su concepto nuevo por ml
  (``colado_por_ml``, D8); y la **losa**, con su concepto nuevo por m² (regla F7: la losa es un elemento nuevo y lleva su concepto, igual que
  una matriz). Los conceptos nuevos son **propuestos** con clave **provisional**, sin precio y pendientes de autorizar por Control de obra.

Quién paga el concreto y la cimbra de una trabe (Q49: valor conservador)
------------------------------------------------------------------------
El usuario no ha decidido la Q49 (matriz dentro de matriz). Se usa la propuesta del mockup: el elemento paga su **acero** con su auxiliar y,
por omisión, la **losa sigue pagando el concreto y la cimbra** (``pago = en_la_losa``, como el catálogo); una trabe suelta (de liga, contratrabe
corrida) puede marcarse ``pago = propio`` y entonces paga su colado y cimbra por ml. Nunca se paga lo mismo dos veces: el concreto y la cimbra de
un elemento van en **un** concepto, el de la losa o el suyo.

La sección de la trabe se mide **completa**: el concreto del espesor de la losa que comparte se cuenta en la trabe y en la losa. Se informa
el **solape** (``solape_con_la_losa_m3``) y no se descuenta (valor conservador; pregunta abierta).

Mano de obra: ninguna se calcula ni se elige. El catálogo de trabajos trae destajos de losa por m² (``MOE-02211`` a ``MOE-02218``) pero sus
propias matrices los usan de forma desigual (una losa nervada de 3.00 m con ``MOE-02211`` y otra con ``MOE-02215``): elegir uno sería inventar. Se
listan como candidatos; el destajo por ml de las trabes queda sin importe (D8). Sin precios. Función pura, sin base de datos.

El camino de lo que NO se construye aquí (para quien siga)
----------------------------------------------------------
- **Fase 3, el relleno**: es un elemento SEPARADO de la losa (decisión del usuario, 2026-11-16): su volumen sale de la pendiente y de los espesores
  estructurales distintos de la zona (las subzonas de ``losa_zona``/``trazo.losa_espesor_m``), no de la losa. Se construiría como una familia nueva de la
  biblioteca (categoría «Rellenos»), con su concepto propuesto (regla F7) y su propia tabla de elementos de zona; esta matriz solo le prestaría el área
  y los espesores por polígono que ya calcula (``losas``).
- **Fase 4, escaleras y cimentación**: la escalera sale de la diferencia de cotas entre zonas (``cota_inferior_m`` de cada zona) y la losa de cimentación
  es otra zona con ``uso_de_losa`` propio (hoy solo entrepiso y azotea) y sus contratrabes CT (que esta matriz ya admite). Falta decidir el uso
  «cimentación» (concreto CON-00001, TD 200) y el concepto de las 7 losas de cimentación del catálogo.
- **Capa «espacio»** (0143, ``espacios``): una zona de losa NO es un espacio (una zona puede cubrir varios cuartos), pero cada polígono de losa
  (``trazo.espacio_id``) y cada elemento (``losa_elemento.espacio_id``) puede decir en qué cuarto está. El cálculo de la zona NO cambia: ``por_espacio``
  solo reparte lo mismo por cuarto (cada polígono y cada elemento cae en **un** grupo, así que la suma de los grupos es el total de la zona: sin doble
  conteo). Lo que no tiene espacio forma el grupo «sin espacio» y se comporta como antes.

"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from itertools import pairwise
from typing import Any, Literal

from obractrl.domain.cuantificacion.colado_por_ml import concepto_de_colado
from obractrl.domain.cuantificacion.elementos_lineales import (
    TIPO_LINEAL,
    EntradaElementoEstructural,
    ErrorDeElementoEstructural,
    calcular_elemento,
    claves_de_elementos_estructurales,
    elemento_estructural,
)
from obractrl.domain.cuantificacion.elementos_lineales_catalogo import (
    DESCRIPCIONES_DE_INSUMOS,
    INSUMOS,
)
from obractrl.domain.cuantificacion.receta_acero import DriversDeReceta
from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = [
    "CAPA_DE_COMPRESION_CM",
    "CLAVES_DE_LOSA",
    "CONCEPTOS_DE_LOSA",
    "CONCRETO_POR_USO",
    "DESTAJOS_DE_LOSA_DEL_CATALOGO",
    "PENDIENTES",
    "TIPOS_DE_LOSA",
    "USOS_DE_LOSA",
    "ElementoDeLosa",
    "EntradaMatrizDeLosa",
    "ErrorDeMatrizDeLosa",
    "LosaDeEntrada",
    "area_de_poligonos",
    "calcular_matriz_de_losa",
    "categorias_de_biblioteca",
    "concepto_nuevo_de_losa",
    "definicion_de_losa",
    "elemento_de_losa",
    "longitud_de_linea",
    "validar_elemento_de_losa",
]

TipoDeLosa = Literal["maciza", "nervada"]
UsoDeLosa = Literal["entrepiso", "azotea"]
Pago = Literal["en_la_losa", "propio"]

TIPOS_DE_LOSA: tuple[str, ...] = ("maciza", "nervada")
USOS_DE_LOSA: tuple[str, ...] = ("entrepiso", "azotea")
PAGOS: tuple[str, ...] = ("en_la_losa", "propio")

CLAVES_DE_LOSA: dict[str, str] = {"maciza": "LOSA-MACIZA", "nervada": "LOSA-NERVADA"}
"""Los dos elementos de la biblioteca (categoría Losas): su clave por tipo de losa."""

CAPA_DE_COMPRESION_CM = 5.0
"""La capa de compresión de la losa nervada: 5 cm en las descripciones del catálogo («con capa de compresión de 5 cm»). Editable."""

CONCRETO_POR_USO: dict[str, str] = {"entrepiso": "CON-00003", "azotea": "CON-00004"}
"""El concreto de la losa por su uso, según la descripción del catálogo: «CONCRETO BOMBEADO 250 … (LOSAS ENTREPISO)» y «… (LOSAS AZOTEA Y
ROOF)». Las matrices del catálogo usan CON-00004 aun en entrepisos; se sigue la descripción (valor conservador, pregunta abierta)."""

CIMBRA_DE_LOSA = "MAD-00001"
"""CIMBRA 3 MTS, en m²: el catálogo la cuenta con la misma cantidad que el área de la losa (EST-21011: 125 m² de cimbra para 125 m² de losa)."""

PARRILLA_DE_MACIZA: dict[str, Any] = {
    "clave": "AUX-06010",
    "descripcion": "Acero para losa varilla del no. 3 @20 cm.",
    "unidad": "m²",
    "insumos": (
        ("ACR-00001", "VARILLA 3/8", "pza", 0.9, "ANALISIS_DE_BASICOS_COMPUESTOS:139"),
        ("ACE-00001", "ALAMBRE RECOCIDO", "kg", 0.20685, "ANALISIS_DE_BASICOS_COMPUESTOS:140"),
    ),
}
"""La parrilla de la losa maciza: un auxiliar del catálogo, por m². Es un dato del catálogo (no se recalcula)."""

DESTAJOS_DE_LOSA_DEL_CATALOGO: tuple[tuple[str, str], ...] = (
    ("MOE-02211", "MO ARMADO DE LOSA NERVADA"),
    ("MOE-02212", "MO DESCIMBRADO DE LOSA NERVADA"),
    ("MOE-02213", "MO ARMADO DE LOSA MACIZA"),
    ("MOE-02214", "MO DESCIMBRADO DE LOSA MACIZA"),
    ("MOE-02215", "MO ARMADO Y CIMBRADO LOSA 3.00"),
    ("MOE-02216", "MO DESCIMBRADO DE LOSA 3.00"),
    ("MOE-02217", "MO ARMADO Y CIMBRADO LOSA 4.20"),
    ("MOE-02218", "MO DESCIMBRADO DE LOSA 4.20"),
)
"""Los destajos de losa por m² del catálogo de trabajos (CATALOGO_DE_TRABAJOS). Se listan como candidatos; el elemento no elige uno."""

CONCEPTOS_DE_LOSA: dict[str, dict[str, Any]] = {
    "maciza": {
        "clave": "EJ-800",
        "descripcion": "Losa maciza de concreto armado por m²: concreto, cimbra y parrilla de acero (zona de losa)",
    },
    "nervada": {
        "clave": "EJ-801",
        "descripcion": "Losa nervada por m²: capa de compresión y cimbra; las trabes y nervaduras de la zona se miden aparte",
    },
}
"""El concepto nuevo de la losa por m² (regla F7: un elemento nuevo lleva su concepto). Clave **provisional**, propuesto, sin precio ni destajo."""

PENDIENTES: tuple[dict[str, str], ...] = (
    {
        "clave": "Q49",
        "texto": "Matriz dentro de matriz: el usuario no ha decidido quién paga el concreto y la cimbra de una trabe. Valor conservador: el elemento paga su acero con "
        "su auxiliar y la losa sigue pagando concreto y cimbra por m² (``en_la_losa``); una trabe suelta puede pagar su colado y cimbra por ml (``propio``).",
    },
    {
        "clave": "L1",
        "texto": "El casetón de la losa nervada no se calcula: el catálogo lo cuenta por pieza (40×40×20, 60×50×10-15-20) y la medida de la zona no lo dice. "
        "Tampoco se calculan los bastones, la malla ni la cimbra de los nervios.",
    },
    {
        "clave": "L2",
        "texto": "La trabe se mide con su sección completa: el concreto del espesor de la losa que comparte se cuenta en la trabe y en la losa. Se informa el solape y no "
        "se descuenta. ¿Se descuenta?",
    },
    {
        "clave": "L3",
        "texto": "El concreto de la losa por uso sigue la descripción del catálogo (entrepiso CON-00003, azotea CON-00004); las matrices del catálogo usan CON-00004 "
        "casi siempre. ¿Cuál vale para entrepiso?",
    },
    {
        "clave": "L4",
        "texto": "Los destajos de losa por m² (MOE-02211 a MOE-02218) los usan las matrices del catálogo de forma desigual; no se elige ninguno. El destajo por ml de las trabes "
        "queda sin importe (D8) hasta que Costos lo defina.",
    },
    {
        "clave": "L5",
        "texto": "Las claves provisionales del concepto de la losa (EJ-800 maciza, EJ-801 nervada) y las de colado por ml (EJ-7xx del mockup) las confirma Control de obra al autorizar.",
    },
)
"""Lo que el material del usuario no resuelve y se dejó con valor conservador."""

_EPS = 1e-9
_ESPESOR_MAXIMO_M = 3.0
_CANTIDAD_MAXIMA = 1_000_000.0


class ErrorDeMatrizDeLosa(ErrorDeCuantificacion):
    """Un dato que no vale: la matriz de la losa no se puede calcular con él."""


# --------------------------------------------------------------------------------------------------------------
# Geometría
# --------------------------------------------------------------------------------------------------------------

Punto = tuple[float, float]


def _area_de_anillo(anillo: Sequence[Punto]) -> float:
    """Área sin signo de un anillo (fórmula del topógrafo); el anillo puede venir cerrado o abierto."""
    n = len(anillo)
    if n < 3:
        return 0.0
    suma = 0.0
    for i in range(n):
        x1, y1 = anillo[i]
        x2, y2 = anillo[(i + 1) % n]
        suma += x1 * y2 - x2 * y1
    return abs(suma) / 2


def area_de_poligonos(poligonos: Sequence[Sequence[Sequence[Punto]]]) -> float:
    """El área neta (m²) de uno o varios polígonos: el primer anillo de cada uno es el exterior y los demás son huecos que se restan.
    Las coordenadas llegan en metros."""
    total = 0.0
    for poligono in poligonos:
        if not poligono:
            continue
        total += _area_de_anillo(poligono[0]) - sum(_area_de_anillo(h) for h in poligono[1:])
    return max(total, 0.0)


def longitud_de_linea(linea: Sequence[Punto]) -> float:
    """El largo (m) de una polilínea; las coordenadas llegan en metros."""
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in pairwise(linea))


# --------------------------------------------------------------------------------------------------------------
# Entrada
# --------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class LosaDeEntrada:
    """Un polígono de losa de la zona: su área neta y, si es una subzona, su espesor estructural propio."""

    area_m2: float
    espesor_m: float | None = None
    id: str | None = None
    espacio_id: str | None = None
    """El espacio donde cae el polígono (0143); `None` = sin espacio."""


@dataclass(frozen=True)
class ElementoDeLosa:
    """Un elemento de la zona: una trabe, contratrabe o nervadura de la biblioteca, por ml (``cantidad`` = metros) o por pieza (``cantidad`` = piezas de
    ``largo_m``). ``origen`` dice si la medida se tecleó o se tomó de una línea del plano (medición derivada)."""

    clave: str
    modo: Literal["ml", "pieza"] = "ml"
    cantidad: float = 1.0
    largo_m: float | None = None
    pago: Pago = "en_la_losa"
    id: str | None = None
    origen: Literal["manual", "trazo"] = "manual"
    trazo_id: str | None = None
    espacio_id: str | None = None
    """El espacio donde está el elemento (0143); `None` = sin espacio."""


@dataclass(frozen=True)
class EntradaMatrizDeLosa:
    tipo: TipoDeLosa
    espesor_m: float
    uso: UsoDeLosa = "entrepiso"
    losas: Sequence[LosaDeEntrada] = ()
    elementos: Sequence[ElementoDeLosa] = ()
    capa_de_compresion_cm: float = CAPA_DE_COMPRESION_CM
    desperdicio_concreto_pct: float = 5.0
    drivers: DriversDeReceta = field(default_factory=DriversDeReceta)
    concreto_clave: str | None = None
    """Solo para quien necesite otro concreto que el del uso (CON-00003 o CON-00004); sin él vale el del uso."""


# --------------------------------------------------------------------------------------------------------------
# Biblioteca
# --------------------------------------------------------------------------------------------------------------


def elemento_de_losa(clave: str) -> TipoDeLosa | None:
    """El tipo de losa de una clave de la biblioteca (`LOSA-MACIZA`, `LOSA-NERVADA`), o `None`."""
    for tipo, c in CLAVES_DE_LOSA.items():
        if c == clave:
            return tipo  # type: ignore[return-value]
    return None


def _nombre(tipo: str) -> str:
    return "Losa maciza" if tipo == "maciza" else "Losa nervada"


def categorias_de_biblioteca() -> tuple[dict[str, Any], ...]:
    """La categoría Losas de la biblioteca (forma de `BIBLIOTECA`): dos elementos, uno por tipo de losa."""

    def elemento(tipo: str) -> dict[str, Any]:
        c = CONCEPTOS_DE_LOSA[tipo]
        return {
            "clave": CLAVES_DE_LOSA[tipo],
            "nombre": _nombre(tipo),
            "tipo": "losa_de_concreto",
            "se_mide_por": "m² de losa de una zona del plano",
            "concepto": {"clave": c["clave"], "descripcion": c["descripcion"], "unidad": "m²"},
        }

    return (
        {
            "clave": "losas",
            "nombre": "Losas",
            "prefijo": "L",
            "subcategorias": (
                {"clave": "maciza", "nombre": "Losas macizas", "prefijo": "L", "elementos": (elemento("maciza"),)},
                {"clave": "nervada", "nombre": "Losas nervadas", "prefijo": "L", "elementos": (elemento("nervada"),)},
            ),
        },
    )


def _descripcion_de(clave: str) -> str:
    if clave in INSUMOS:
        return str(INSUMOS[clave]["descripcion"])
    return DESCRIPCIONES_DE_INSUMOS.get(clave, "")


def definicion_de_losa(clave: str) -> dict[str, Any] | None:
    """La ficha de un elemento de losa: qué calcula, qué toma del catálogo, sus conceptos nuevos propuestos y los pendientes."""
    tipo = elemento_de_losa(clave)
    if tipo is None:
        return None
    c = CONCEPTOS_DE_LOSA[tipo]
    maciza = tipo == "maciza"
    return {
        "clave": clave,
        "nombre": _nombre(tipo),
        "tipo": tipo,
        "se_mide_por": "m² de losa de una zona del plano",
        "categoria": {"clave": "losas", "nombre": "Losas"},
        "subcategoria": {"clave": tipo, "nombre": "Losas macizas" if maciza else "Losas nervadas"},
        "concepto": {"clave": c["clave"], "descripcion": c["descripcion"], "unidad": "m²", "estado": "propuesto", "provisional": True},
        "usos": list(USOS_DE_LOSA),
        "concreto_por_uso": [
            {"uso": u, "clave": k, "descripcion": _descripcion_de(k)} for u, k in CONCRETO_POR_USO.items()
        ],
        "cimbra": {"clave": CIMBRA_DE_LOSA, "descripcion": _descripcion_de(CIMBRA_DE_LOSA), "por_m2_de_losa": 1.0},
        "espesor_por_defecto_m": 0.12 if maciza else 0.20,
        "capa_de_compresion_cm": None if maciza else CAPA_DE_COMPRESION_CM,
        "parrilla": (
            {
                "clave": PARRILLA_DE_MACIZA["clave"], "descripcion": PARRILLA_DE_MACIZA["descripcion"], "unidad": "m²",
                "insumos": [
                    {"clave": k, "descripcion": d, "unidad": u, "por_m2": q, "fuente": f}
                    for k, d, u, q, f in PARRILLA_DE_MACIZA["insumos"]
                ],
            }
            if maciza
            else None
        ),
        "elementos_permitidos": [
            {"clave": k, "tiene_concepto_de_colado": concepto_de_colado(k) is not None}
            for k in _CLAVES_DE_LINEALES
        ],
        "destajos_candidatos": [{"clave": k, "descripcion": d, "unidad": "m²"} for k, d in DESTAJOS_DE_LOSA_DEL_CATALOGO],
        "pagos": list(PAGOS),
        "pendientes": [dict(p) for p in PENDIENTES],
    }


_CLAVES_DE_LINEALES: tuple[str, ...] = tuple(
    k for k in claves_de_elementos_estructurales() if (elemento_estructural(k) or {}).get("tipo") == TIPO_LINEAL
)


# --------------------------------------------------------------------------------------------------------------
# Propuesta del concepto de la losa
# --------------------------------------------------------------------------------------------------------------


def concepto_nuevo_de_losa(tipo: str) -> dict[str, Any]:
    """La propuesta de concepto nuevo de la losa por m² (clase ``concepto_nuevo``): clave provisional, sin destajo ni precio. Los insumos son
    los de **un m² de referencia** (espesor de 12 cm la maciza, capa de 5 cm la nervada, concreto de entrepiso); el elemento los recalcula con el
    espesor y el uso de cada zona."""
    if tipo not in TIPOS_DE_LOSA:
        raise ErrorDeMatrizDeLosa("El tipo de losa es «maciza» o «nervada».")
    c = CONCEPTOS_DE_LOSA[tipo]
    espesor = 0.12 if tipo == "maciza" else 0.20
    r = calcular_matriz_de_losa(
        EntradaMatrizDeLosa(tipo=tipo, espesor_m=espesor, losas=(LosaDeEntrada(area_m2=1.0),))  # type: ignore[arg-type]
    )
    insumos = {f["clave"]: round(float(f["cantidad"]), 6) for f in r["insumos"] if f["origen"] != "elemento"}
    return {
        "elemento_clave": CLAVES_DE_LOSA[tipo],
        "concepto_clave": c["clave"],
        "clase": "concepto_nuevo",
        "resumen": f"Concepto nuevo {c['clave']} (clave provisional): {c['descripcion']}, por m², sin destajo ni precio",
        "detalle": {
            "descripcion": c["descripcion"],
            "unidad": "m²",
            "clave_provisional": True,
            "toma": {"concreto": True, "cimbra": True, "acero": tipo == "maciza"},
            "insumos": insumos,
            "motivos": [
                "Fase 2 de la losa (regla F7): la losa es un elemento nuevo y lleva su concepto en el catálogo; el catálogo solo trae losas por prototipo, "
                "con un lote fijo de m² (EST-21011, EST-22010…).",
                "Los insumos son los de un m² de referencia (maciza de 12 cm, nervada con capa de 5 cm, concreto de entrepiso): el elemento los recalcula con "
                "el espesor y el uso de cada zona.",
                "Sin destajo: el catálogo trae destajos de losa por m² (MOE-02211 a MOE-02218) pero no se elige ninguno. Sin precio.",
                "Clave provisional: pendiente de autorizar por Control de obra.",
            ],
            "cambios": [],
        },
    }


# --------------------------------------------------------------------------------------------------------------
# Cálculo
# --------------------------------------------------------------------------------------------------------------


def _numero(valor: float, que: str, *, maximo: float, incluye_cero: bool = False) -> float:
    ok = math.isfinite(valor) and (valor >= 0 if incluye_cero else valor > 0) and valor <= maximo
    if not ok:
        raise ErrorDeMatrizDeLosa(f"{que} no vale: va de {'0' if incluye_cero else 'más de 0'} a {maximo:g}.")
    return float(valor)


def validar_elemento_de_losa(*, clave: str, modo: str, cantidad: float, largo_m: float | None, pago: str) -> dict[str, Any]:
    """Revisa un elemento antes de guardarlo en la zona: que sea una trabe, contratrabe o nervadura de la biblioteca, su modo y su pago, y que la
    medida cuadre con el modo (por ml, metros y sin largo de pieza; por pieza, piezas y el largo de cada una)."""
    cat = elemento_estructural(clave)
    if cat is None or cat["tipo"] != TIPO_LINEAL:
        raise ErrorDeMatrizDeLosa(
            f"«{clave}» no es una trabe, contratrabe ni nervadura de la biblioteca: la zapata y la columna no se miden en la losa."
        )
    if modo not in ("ml", "pieza"):
        raise ErrorDeMatrizDeLosa("El modo es «ml» o «pieza».")
    if pago not in PAGOS:
        raise ErrorDeMatrizDeLosa("El pago es «en_la_losa» o «propio».")
    _numero(cantidad, f"La cantidad de {clave}", maximo=_CANTIDAD_MAXIMA)
    if modo == "pieza":
        if largo_m is None:
            raise ErrorDeMatrizDeLosa(f"{clave} por pieza pide el largo de la pieza en metros.")
        _numero(largo_m, "El largo de la pieza", maximo=30.0)
    elif largo_m is not None:
        raise ErrorDeMatrizDeLosa(f"{clave} por ml no lleva largo de pieza: la cantidad son los metros.")
    return {"elemento_clave": clave, "modo": modo, "cantidad": round(float(cantidad), 3), "largo_m": round(float(largo_m), 3) if largo_m is not None else None, "pago": pago}


def _validar(i: EntradaMatrizDeLosa) -> None:
    if i.tipo not in TIPOS_DE_LOSA:
        raise ErrorDeMatrizDeLosa("El tipo de losa es «maciza» o «nervada».")
    if i.uso not in USOS_DE_LOSA:
        raise ErrorDeMatrizDeLosa("El uso de la losa es «entrepiso» o «azotea».")
    _numero(i.espesor_m, "El espesor de la losa", maximo=_ESPESOR_MAXIMO_M)
    _numero(i.desperdicio_concreto_pct, "El desperdicio de concreto", maximo=50, incluye_cero=True)
    if i.tipo == "nervada":
        _numero(i.capa_de_compresion_cm, "La capa de compresión", maximo=_ESPESOR_MAXIMO_M * 100)
    if i.concreto_clave is not None and i.concreto_clave not in CONCRETO_POR_USO.values():
        raise ErrorDeMatrizDeLosa("El concreto de la losa es CON-00003 (entrepiso) o CON-00004 (azotea).")
    for lo in i.losas:
        _numero(lo.area_m2, "El área de una losa", maximo=_CANTIDAD_MAXIMA, incluye_cero=True)
        if lo.espesor_m is not None:
            _numero(lo.espesor_m, "El espesor de una subzona", maximo=_ESPESOR_MAXIMO_M)


def _elemento_de_la_zona(e: ElementoDeLosa, i: EntradaMatrizDeLosa) -> dict[str, Any]:
    cat = elemento_estructural(e.clave)
    if cat is None or cat["tipo"] != TIPO_LINEAL:
        raise ErrorDeMatrizDeLosa(
            f"«{e.clave}» no es una trabe, contratrabe ni nervadura de la biblioteca: la zapata y la columna no se miden en la losa."
        )
    if e.pago not in PAGOS:
        raise ErrorDeMatrizDeLosa("El pago es «en_la_losa» o «propio».")
    if e.modo not in ("ml", "pieza"):
        raise ErrorDeMatrizDeLosa("El modo es «ml» o «pieza».")
    _numero(e.cantidad, f"La cantidad de {e.clave}", maximo=_CANTIDAD_MAXIMA)
    if e.modo == "pieza" and e.largo_m is None:
        raise ErrorDeMatrizDeLosa(f"{e.clave} por pieza pide el largo de la pieza en metros.")
    if e.modo == "ml" and e.largo_m is not None:
        raise ErrorDeMatrizDeLosa(f"{e.clave} por ml no lleva largo de pieza: la cantidad son los metros.")
    try:
        r = calcular_elemento(
            EntradaElementoEstructural(
                clave=e.clave, modo=e.modo, largo_m=e.largo_m if e.modo == "pieza" else None, cantidad=e.cantidad,
                desperdicio_concreto_pct=i.desperdicio_concreto_pct, drivers=i.drivers,
            )
        )
    except ErrorDeElementoEstructural as err:
        raise ErrorDeMatrizDeLosa(str(err)) from err
    ml = e.cantidad if e.modo == "ml" else e.cantidad * float(e.largo_m or 0.0)
    seccion = r["seccion"]
    return {
        "id": e.id,
        "clave": e.clave,
        "nombre": r["nombre"],
        "categoria": cat["categoria"],
        "modo": e.modo,
        "cantidad": e.cantidad,
        "largo_m": e.largo_m,
        "longitud_ml": ml,
        "origen": e.origen,
        "trazo_id": e.trazo_id,
        "espacio_id": e.espacio_id,
        "pago": e.pago,
        "seccion": {"ancho_cm": seccion["ancho_cm"], "peralte_cm": seccion["peralte_cm"]},
        "acero_kg": float(r["acero_kg"]) * e.cantidad,
        "concreto_m3": float(r["concreto"]["m3"]) * e.cantidad,
        "cimbra_m2": float(r["cimbra"]["m2"]) * e.cantidad,
        "insumos": r["insumos"],
        "advertencias": list(r["advertencias"]),
    }


def _fila_de_insumo(parte: str, clave: str, unidad: str, cantidad: float, origen: str, paga: str) -> dict[str, Any]:
    return {
        "parte": parte, "clave": clave, "descripcion": _descripcion_de(clave), "unidad": unidad, "cantidad": cantidad, "origen": origen, "paga": paga,
    }


def calcular_matriz_de_losa(i: EntradaMatrizDeLosa) -> dict[str, Any]:
    """La matriz de la zona: concreto, cimbra, acero, elementos y los conceptos que paga cada parte, en las unidades de cada concepto, y lo mismo
    repartido por espacio (``por_espacio``, 0143)."""
    r = _calcular(i)
    r["por_espacio"] = _por_espacio(i)
    return r


def _por_espacio(i: EntradaMatrizDeLosa) -> list[dict[str, Any]]:
    """La misma matriz repartida por espacio: cada polígono y cada elemento cae en **un** grupo (su espacio, o «sin espacio») y cada grupo se calcula
    como una zona más chica. El cálculo es lineal en las áreas y los metros, así que la suma de los grupos es el total de la zona (sin doble conteo).
    El orden es el de la primera aparición; sin nada, un solo grupo «sin espacio»."""
    claves: list[str | None] = []
    for x in [*i.losas, *i.elementos]:
        if x.espacio_id not in claves:
            claves.append(x.espacio_id)
    if not claves:
        claves.append(None)
    grupos: list[dict[str, Any]] = []
    for clave in claves:
        sub = replace(
            i,
            losas=[x for x in i.losas if x.espacio_id == clave],
            elementos=[x for x in i.elementos if x.espacio_id == clave],
        )
        r = _calcular(sub)
        grupos.append(
            {
                "espacio_id": clave,
                "area_m2": r["area_m2"],
                "longitud_de_elementos_ml": r["totales"]["longitud_de_elementos_ml"],
                "concreto_m3": r["totales"]["concreto_m3"],
                "cimbra_m2": r["totales"]["cimbra_m2"],
                "acero_de_elementos_kg": r["totales"]["acero_de_elementos_kg"],
                "conceptos": r["conceptos"],
            }
        )
    return grupos


def _calcular(i: EntradaMatrizDeLosa) -> dict[str, Any]:  # noqa: PLR0912, PLR0915 - un cálculo de punta a punta, legible de arriba abajo
    _validar(i)
    tipo = i.tipo
    nombre_del_elemento = _nombre(tipo)
    advertencias: list[str] = []
    desperdicio = 1 + i.desperdicio_concreto_pct / 100
    concreto_clave = i.concreto_clave or CONCRETO_POR_USO[i.uso]

    # 1. La losa: área, concreto y cimbra por polígono.
    losas: list[dict[str, Any]] = []
    for n, lo in enumerate(i.losas):
        espesor = lo.espesor_m if lo.espesor_m is not None else i.espesor_m
        grosor = espesor if tipo == "maciza" else min(i.capa_de_compresion_cm / 100, espesor)
        losas.append(
            {
                "id": lo.id or str(n + 1),
                "area_m2": lo.area_m2,
                "espesor_m": espesor,
                "subzona": lo.espesor_m is not None,
                "espacio_id": lo.espacio_id,
                "concreto_m3": lo.area_m2 * grosor,
            }
        )
    area = sum(x["area_m2"] for x in losas)
    if not losas:
        advertencias.append("La zona no tiene polígonos de losa: el área, el concreto y la cimbra de la losa son cero. Dibuja la losa de la zona en el plano.")
    elif area <= _EPS:
        advertencias.append("Los polígonos de losa de la zona no tienen área.")
    if tipo == "nervada" and i.capa_de_compresion_cm / 100 > i.espesor_m + _EPS:
        advertencias.append("La capa de compresión es mayor que el espesor de la losa: se usa el espesor.")
    concreto_geometrico = sum(x["concreto_m3"] for x in losas)
    concreto_de_losa = concreto_geometrico * desperdicio
    cimbra_m2 = area

    # 2. Los elementos de la zona.
    elementos = [_elemento_de_la_zona(e, i) for e in i.elementos]
    ml_total = sum(e["longitud_ml"] for e in elementos)
    grosor_compartido = i.espesor_m if tipo == "maciza" else min(i.capa_de_compresion_cm / 100, i.espesor_m)
    solape = sum(
        e["longitud_ml"] * (e["seccion"]["ancho_cm"] / 100) * min(grosor_compartido, e["seccion"]["peralte_cm"] / 100) for e in elementos
    )
    if elementos and solape > 0:
        advertencias.append(
            f"La sección de las trabes y nervaduras se mide completa: {solape:.3f} m³ de concreto del espesor de la losa que comparten se cuentan en la "
            "losa y en el elemento (solape informado, no descontado)."
        )

    # 3. Insumos agregados: lo que se compra, por clave, y quién lo paga.
    filas: list[dict[str, Any]] = []
    if area > _EPS:
        filas.append(_fila_de_insumo("concreto", concreto_clave, "m³", concreto_de_losa, "zona", "losa"))
        filas.append(_fila_de_insumo("cimbra", CIMBRA_DE_LOSA, "m²", cimbra_m2, "zona", "losa"))
    parrilla: dict[str, Any] | None = None
    if tipo == "maciza":
        p = PARRILLA_DE_MACIZA
        parrilla = {
            "clave": p["clave"], "descripcion": p["descripcion"], "unidad": "m²", "cantidad": area,
            "insumos": [
                {"clave": k, "descripcion": d, "unidad": u, "por_m2": q, "total": q * area, "fuente": f} for k, d, u, q, f in p["insumos"]
            ],
        }
        if area > _EPS:
            for k, _d, u, q, _f in p["insumos"]:
                filas.append(_fila_de_insumo("acero", k, u, q * area, "catalogo", "losa"))
    for e in elementos:
        paga_concreto = "losa" if e["pago"] == "en_la_losa" else "elemento"
        for f in e["insumos"]:
            parte = "acero" if f["parte"] in ("acero", "estribos", "alambre") else f["parte"]
            paga = "elemento" if parte == "acero" else paga_concreto
            filas.append(_fila_de_insumo(parte, f["clave"], f["unidad"], float(f["total"]), "elemento", paga))
    insumos = _agregar(filas)

    # 4. Los conceptos que paga cada parte.
    conceptos: list[dict[str, Any]] = []
    c_losa = CONCEPTOS_DE_LOSA[tipo]
    pagados_por_la_losa = {"concreto": True, "cimbra": True, "acero": tipo == "maciza"}
    conceptos.append(
        {
            "parte": "losa", "elemento_clave": CLAVES_DE_LOSA[tipo], "ref": None,
            "concepto": {"clave": c_losa["clave"], "descripcion": c_losa["descripcion"], "unidad": "m²", "estado": "propuesto", "provisional": True},
            "toma": [m for m, v in pagados_por_la_losa.items() if v],
            "cantidad": area, "unidad": "m²",
            "nota": "Concepto nuevo por m² de losa (regla F7): paga el concreto y la cimbra de la losa y, según el pago, los de los elementos «en la losa».",
        }
    )
    for e in elementos:
        cat = elemento_estructural(e["clave"]) or {}
        aux = cat["catalogo"][0]
        conceptos.append(
            {
                "parte": "acero", "elemento_clave": e["clave"], "ref": e["id"],
                "concepto": {"clave": aux["clave"], "descripcion": aux["descripcion"], "unidad": "ml", "estado": "catalogo", "provisional": False},
                "toma": ["acero"], "cantidad": e["longitud_ml"], "unidad": "ml",
                "nota": "El auxiliar del catálogo paga el acero por metro de elemento.",
            }
        )
        if e["pago"] == "propio":
            colado = concepto_de_colado(e["clave"])
            assert colado is not None  # toda trabe, contratrabe y nervadura de la biblioteca lo tiene
            conceptos.append(
                {
                    "parte": "colado", "elemento_clave": e["clave"], "ref": e["id"],
                    "concepto": {
                        "clave": colado["clave"], "descripcion": colado["descripcion"], "unidad": "ml", "estado": "propuesto", "provisional": True,
                    },
                    "toma": [m for m, v in colado["toma"].items() if v], "cantidad": e["longitud_ml"], "unidad": "ml",
                    "nota": "Colado y cimbra por ml (D8): este elemento los paga con su propio concepto y la losa no los cuenta.",
                }
            )

    concreto_de_elementos = sum(e["concreto_m3"] for e in elementos)
    concreto_pagado_por_la_losa = concreto_de_losa + sum(e["concreto_m3"] for e in elementos if e["pago"] == "en_la_losa")
    concreto_pagado_por_elementos = sum(e["concreto_m3"] for e in elementos if e["pago"] == "propio")
    cimbra_pagada_por_la_losa = cimbra_m2 + sum(e["cimbra_m2"] for e in elementos if e["pago"] == "en_la_losa")
    cimbra_pagada_por_elementos = sum(e["cimbra_m2"] for e in elementos if e["pago"] == "propio")
    if tipo == "nervada" and not any(e["categoria"] == "nervaduras" for e in elementos):
        advertencias.append("Losa nervada sin nervaduras en la zona: solo se cuenta la capa de compresión. Agrega las nervaduras (y las trabes) de la zona.")
    if tipo == "nervada":
        advertencias.append("El casetón, los bastones y la malla de la losa nervada no se calculan (L1).")
    for e in elementos:
        advertencias.extend(f"{e['clave']}: {a}" for a in e["advertencias"])

    salida_elementos = [{k: v for k, v in e.items() if k != "insumos"} for e in elementos]
    return {
        "clave": CLAVES_DE_LOSA[tipo],
        "nombre": nombre_del_elemento,
        "tipo": tipo,
        "uso": i.uso,
        "espesor_m": i.espesor_m,
        "capa_de_compresion_cm": i.capa_de_compresion_cm if tipo == "nervada" else None,
        "area_m2": area,
        "losas": losas,
        "concreto": {
            "clave": concreto_clave, "descripcion": _descripcion_de(concreto_clave), "geometrico_m3": concreto_geometrico,
            "con_desperdicio_m3": concreto_de_losa, "desperdicio_pct": i.desperdicio_concreto_pct,
        },
        "cimbra": {"clave": CIMBRA_DE_LOSA, "descripcion": _descripcion_de(CIMBRA_DE_LOSA), "m2": cimbra_m2},
        "parrilla": parrilla,
        "elementos": salida_elementos,
        "totales": {
            "area_m2": area,
            "longitud_de_elementos_ml": ml_total,
            "concreto_m3": concreto_de_losa + concreto_de_elementos,
            "concreto_de_la_losa_m3": concreto_de_losa,
            "concreto_de_los_elementos_m3": concreto_de_elementos,
            "concreto_pagado_por_la_losa_m3": concreto_pagado_por_la_losa,
            "concreto_pagado_por_elementos_m3": concreto_pagado_por_elementos,
            "cimbra_m2": cimbra_m2 + sum(e["cimbra_m2"] for e in elementos),
            "cimbra_pagada_por_la_losa_m2": cimbra_pagada_por_la_losa,
            "cimbra_pagada_por_elementos_m2": cimbra_pagada_por_elementos,
            "acero_de_elementos_kg": sum(e["acero_kg"] for e in elementos),
            "solape_con_la_losa_m3": solape,
        },
        "insumos": insumos,
        "conceptos": conceptos,
        "mano_de_obra": {
            "estado": "sin_mano_de_obra",
            "nota": (
                "El elemento no calcula mano de obra ni elige un destajo de losa: el catálogo trae destajos por m² (MOE-02211 a MOE-02218) que sus propias matrices usan "
                "de forma desigual. El destajo por ml de las trabes queda sin importe (D8). Sin precios."
            ),
            "destajos_candidatos": [{"clave": k, "descripcion": d, "unidad": "m²"} for k, d in DESTAJOS_DE_LOSA_DEL_CATALOGO],
        },
        "advertencias": advertencias,
        "pendientes": [dict(p) for p in PENDIENTES],
    }


def _agregar(filas: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Junta las filas del mismo insumo (por clave, quién la paga y de dónde sale), sumando la cantidad; el orden es el de la primera aparición."""
    juntas: dict[tuple[str, str, str], dict[str, Any]] = {}
    for f in filas:
        llave = (f["clave"], f["origen"] if f["origen"] == "catalogo" else "calculo", f["paga"])
        previa = juntas.get(llave)
        if previa is None:
            juntas[llave] = dict(f)
        else:
            previa["cantidad"] += f["cantidad"]
            if previa["origen"] != f["origen"]:
                previa["origen"] = "zona+elemento"
    return list(juntas.values())
