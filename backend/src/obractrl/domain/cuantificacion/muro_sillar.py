"""Muro de sillar amarillo de 19 cm, BAP-01010 (elemento paramétrico de la biblioteca; decisión del usuario 2026-11-20: «realizar el elemento»).

El PR 195 dejó el material `sillar_amarillo` con su concepto sugerido BAP-01010 y el aviso `material_sin_elemento`. Este módulo construye el
elemento que lo paga, con el mismo patrón que `muro_tabique` (versionado por propuestas, conciliación contra el catálogo vigente, desglose y
tarjeta en la biblioteca) y las dos reglas de la decisión:

- **F7**: todo elemento nuevo tiene su concepto en el catálogo igual que una matriz. El concepto **ya existe**: BAP-01010 («Muro de 19 cm. de
  espesor, de sillar amarillo 19x25x45, asentado con mezcla cemento-arena 1:4, acabado aparente»), es una matriz del catálogo y cubre el
  elemento completo (pieza, mezcla y destajo). Por eso el elemento **se liga a ese concepto** y no propone un concepto nuevo ni inventa precios.
- **F6**: el desperdicio del elemento lo da el driver `desperdicio_mamposteria` (petición > obra > valor de partida). El tabique de 14 cm y sus
  aparejos **no** lo leen (su desperdicio va en el elemento, M-105).

Lo que sale del catálogo (verificado con `scripts/verificar_sillar_contra_csv.py`):

=====================  ==========================================================================  =================================
Dato                   Valor                                                                       Línea del CSV
=====================  ==========================================================================  =================================
Pieza                  PET-00008 «SILLAR 19X25X45 AMARILLO», 19 (espesor) × 25 (alto) × 45 cm       ANALISIS_DE_BASICOS_CONCEPTOS:501
Mezcla                 MEZ-07010 cemento-arena 1:4, 0.0292 m³ por m²                                 ANALISIS_DE_BASICOS_CONCEPTOS:502
Destajo                MOE-02016 «MO MURO DE SILLAR- HILO», por m²                                   ANALISIS_DE_BASICOS_CONCEPTOS:503
Catálogo por m²        9 pza de sillar                                                               ANALISIS_DE_BASICOS_CONCEPTOS:501
=====================  ==========================================================================  =================================

El sillar se coloca **a hilo** (soga): la cara de 45 × 25 cm queda a la vista y la pieza aporta sus 19 cm de espesor (el nombre del concepto
dice «muro de 19 cm»). Con eso el elemento calcula las piezas y la mezcla por **geometría**, igual que el tabique, y muestra la diferencia contra
lo que trae el catálogo (el catálogo no se edita: si hace falta se propone una nueva versión de BAP-01010 y solo Control de obra la autoriza).

Supuestos (el catálogo y la especificación no los traen; todos son editables y se muestran en la tarjeta):

- **Junta de 2 cm**: el catálogo no trae el espesor de la junta del sillar. Se usa la misma de 2 cm que el usuario confirmó para el tabique (Ola 3,
  lane 3C). Para cerrarla hace falta la junta real del sillar (pregunta abierta).
- **Desperdicio** de pieza y de mezcla: **un solo** porcentaje, el del driver `desperdicio_mamposteria` (5 % de partida; el driver sigue «por
  confirmar»). No se inventa un desperdicio propio del sillar.
- **Sin herramienta ni equipo** (el catálogo no trae insumos de esa clase) y sin precios: el destajo MOE-02016 es el del catálogo y el elemento no
  lo calcula.

Función pura, sin base de datos.
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
from obractrl.domain.cuantificacion.muro_tabique import CLAVE_MEZCLA, MEZCLA_COMPUESTA
from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = [
    "CLAVE_DEL_DRIVER_DE_DESPERDICIO",
    "CLAVE_DEL_ELEMENTO",
    "CLAVE_MEZCLA",
    "CLAVE_PIEZA",
    "DESPERDICIO_POR_DEFECTO_PCT",
    "ELEMENTOS_DE_SILLAR",
    "JUNTA_POR_DEFECTO_CM",
    "ElementoDeSillarNoEncontrado",
    "EntradaMuroDeSillar",
    "ErrorDeMuroDeSillar",
    "calcular_muro_de_sillar",
    "categorias_de_biblioteca",
    "claves_de_sillar",
    "concepto_nuevo_de",
    "definicion_de",
    "elemento_de_sillar",
    "propuestas_de_actualizacion_de_apu",
]

CLAVE_DEL_ELEMENTO = "BAP-01010"
CLAVE_PIEZA = "PET-00008"
CLAVE_DEL_DRIVER_DE_DESPERDICIO = "desperdicio_mamposteria"
ESPESOR_CM = 19.0
ALTO_CM = 25.0
LARGO_CM = 45.0
JUNTA_POR_DEFECTO_CM = 2.0
DESPERDICIO_POR_DEFECTO_PCT = 5.0
"""Debe valer lo mismo que el valor de partida del driver `desperdicio_mamposteria` (una prueba lo comprueba)."""

_DESCRIPCIONES = {CLAVE_PIEZA: "SILLAR 19X25X45 AMARILLO", CLAVE_MEZCLA: "MEZCLA CEMENTO-ARENA 1:4"}
_C = "ANALISIS_DE_BASICOS_CONCEPTOS"
_DESTAJO = ("MOE-02016", "MO MURO DE SILLAR- HILO", "m2")

_COMPOSICION_DEL_CATALOGO: tuple[tuple[str, float, bool, float | None, str], ...] = (
    (CLAVE_PIEZA, 9.0, False, 13.0, f"{_C}:501"),
    (CLAVE_MEZCLA, 0.0292, False, 2058.26, f"{_C}:502"),
    ("MOE-02016", 1.0, True, 190.0, f"{_C}:503"),
)
"""La composición real de BAP-01010: (insumo, cantidad por m², es mano de obra, costo, línea del CSV). Solo la mano de obra lleva costo aquí."""

_DESCRIPCION_DEL_CONCEPTO = (
    "Muro de 19 cm. de espesor, de sillar amarillo 19x25x45, asentado con mezcla cemento-arena 1:4, acabado aparente"
)
_FUENTE = (
    "BAP-01010 (CATALOGO_DE_MATRICES línea 91; composición en ANALISIS_DE_BASICOS_CONCEPTOS líneas 501 a 503); pieza PET-00008 (CATALOGO_DE_MATERIALES "
    "línea 285); destajo MOE-02016 (CATALOGO_DE_TRABAJOS línea 134). La junta de 2 cm y el desperdicio del driver son supuestos, no datos del catálogo."
)

_PENDIENTES: tuple[tuple[str, str], ...] = (
    (
        "S1",
        "La junta del sillar no viene en el catálogo: se calcula con 2 cm (la del tabique) y es editable. Con 2 cm y 5 % el elemento da 8.3 pza y "
        "0.0226 m³ por m² contra 9 pza y 0.0292 m³ del catálogo: la diferencia se muestra y el catálogo no se edita.",
    ),
    (
        "S2",
        "El desperdicio sale del driver «desperdicio_mamposteria» (5 % de partida, por confirmar); es uno solo para la pieza y la mezcla. Si el "
        "sillar necesita otro, Control de obra lo ajusta por obra en el Paramétrico.",
    ),
    (
        "S3",
        "BAP-01010 ya es una matriz del catálogo (regla F7): el elemento se liga a ese concepto y no propone un concepto nuevo. Si Costos quiere "
        "que el catálogo refleje el cálculo, propone una nueva versión de BAP-01010 («Confirmar cálculo → actualizar APU»).",
    ),
    ("S4", "El destajo MOE-02016 es el del catálogo: el elemento no lo calcula ni pone precio."),
)


class ErrorDeMuroDeSillar(ErrorDeCuantificacion):
    """Un parámetro del muro de sillar que no vale."""


class ElementoDeSillarNoEncontrado(ErrorDeMuroDeSillar):
    """No hay un elemento de sillar con esa clave."""


@dataclass(frozen=True, slots=True)
class ElementoDeSillar:
    clave: str
    nombre: str
    nombre_nominal: str
    espesor_cm: float
    alto_cm: float
    largo_cm: float
    concepto_clave: str
    concepto_descripcion: str
    destajo: tuple[str, str, str]


_LISTA: tuple[ElementoDeSillar, ...] = (
    ElementoDeSillar(
        clave=CLAVE_DEL_ELEMENTO,
        nombre="Muro de sillar amarillo 19 cm, a hilo",
        nombre_nominal="Muro de sillar amarillo de 19 cm",
        espesor_cm=ESPESOR_CM,
        alto_cm=ALTO_CM,
        largo_cm=LARGO_CM,
        concepto_clave=CLAVE_DEL_ELEMENTO,
        concepto_descripcion=_DESCRIPCION_DEL_CONCEPTO,
        destajo=_DESTAJO,
    ),
)

ELEMENTOS_DE_SILLAR: dict[str, ElementoDeSillar] = {e.clave: e for e in _LISTA}


def claves_de_sillar() -> tuple[str, ...]:
    return tuple(ELEMENTOS_DE_SILLAR)


def elemento_de_sillar(clave: str) -> ElementoDeSillar:
    e = ELEMENTOS_DE_SILLAR.get(clave.strip().upper())
    if e is None:
        raise ElementoDeSillarNoEncontrado(f"No hay un elemento de sillar {clave}.")
    return e


# --- Biblioteca ------------------------------------------------------------------------------------------------------------


def categorias_de_biblioteca() -> tuple[dict[str, Any], ...]:
    """Lo que el elemento agrega a la biblioteca: Muros › Muros de sillar (se une a la categoría «Muros» del tabique)."""
    elementos = tuple(
        {
            "clave": e.clave,
            "nombre": e.nombre,
            "tipo": "sillar",
            "se_mide_por": "m²",
            "concepto": {"clave": e.concepto_clave, "descripcion": e.concepto_descripcion, "unidad": "m2"},
        }
        for e in _LISTA
    )
    return (
        {
            "clave": "muros", "nombre": "Muros", "prefijo": "MT",
            "subcategorias": ({"clave": "sillar", "nombre": "Muros de sillar", "prefijo": "MS", "elementos": elementos},),
        },
    )


# --- Cálculo -----------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class EntradaMuroDeSillar:
    """Lo que se captura. `cantidad` son m² de muro ya sin huecos; el desperdicio ya viene resuelto (petición > obra > valor de partida)."""

    cantidad: float = 1.0
    junta_cm: float = JUNTA_POR_DEFECTO_CM
    desperdicio_pct: float = DESPERDICIO_POR_DEFECTO_PCT


def _validar(i: EntradaMuroDeSillar) -> None:
    if not (0 < i.cantidad <= 1_000_000):
        raise ErrorDeMuroDeSillar("La cantidad debe ser mayor que cero (m² del muro, ya sin huecos).")
    if not (0 <= i.junta_cm <= 10):
        raise ErrorDeMuroDeSillar("La junta va en centímetros, entre 0 y 10.")
    if not (0 <= i.desperdicio_pct <= 100):
        raise ErrorDeMuroDeSillar("El desperdicio va en por ciento, entre 0 y 100.")


def _geometria(e: ElementoDeSillar, i: EntradaMuroDeSillar) -> dict[str, Any]:
    espesor, alto, largo, j = e.espesor_cm / 100, e.alto_cm / 100, e.largo_cm / 100, i.junta_cm / 100
    volumen_de_pieza = espesor * alto * largo
    netas = 1 / ((largo + j) * (alto + j))
    mezcla_neta = max(0.0, espesor - netas * volumen_de_pieza)
    return {
        "netas": netas,
        "mezcla_neta": mezcla_neta,
        "hilada_cm": round((alto + j) * 100, 6),
        "piezas_por_hilada": 1 / (largo + j),
        "hiladas": [
            {
                "peso": 1.0,
                "espesor_cm": round(espesor * 100, 4),
                "filas": [
                    {
                        "orientacion": "hilo",
                        "etiqueta": "a hilo",
                        "visible_cm": round(largo * 100, 4),
                        "alto_cm": round(alto * 100, 4),
                        "espesor_cm": round(espesor * 100, 4),
                        "piezas_netas_m2": netas,
                    }
                ],
            }
        ],
    }


def _conciliar(piezas: float, mezcla: float) -> list[dict[str, Any]]:
    composicion = [
        FilaDeComposicion(
            clave=clave, cantidad=cantidad, descripcion=_DESCRIPCIONES.get(clave) or _DESTAJO[1],
            unidad=("pza" if clave == CLAVE_PIEZA else "m3" if clave == CLAVE_MEZCLA else "m2"),
            es_mano_de_obra=es_mo, costo=costo if es_mo else None,
        )
        for clave, cantidad, es_mo, costo, _ in _COMPOSICION_DEL_CATALOGO
    ]
    comparado = comparar_con_concepto({CLAVE_PIEZA: piezas, CLAVE_MEZCLA: mezcla}, composicion, descripciones=_DESCRIPCIONES)
    return [
        {
            "concepto": {"clave": CLAVE_DEL_ELEMENTO, "descripcion": _DESCRIPCION_DEL_CONCEPTO, "unidad": "m2"},
            "sobre": "por m² de muro",
            "filas": comparado["filas"],
            "mano_de_obra": comparado["mano_de_obra"],
            "resumen": comparado["resumen"],
            "coincide": comparado["coincide"],
            "fuente_de_las_filas": [linea for *_, linea in _COMPOSICION_DEL_CATALOGO],
            "avisos": [],
        }
    ]


def calcular_muro_de_sillar(clave: str, i: EntradaMuroDeSillar | None = None) -> dict[str, Any]:
    """Piezas y mezcla por m², el concepto, el contraste con el catálogo y los totales de `cantidad`."""
    e = elemento_de_sillar(clave)
    entrada = i or EntradaMuroDeSillar()
    _validar(entrada)
    g = _geometria(e, entrada)
    desperdicio = entrada.desperdicio_pct / 100
    piezas = g["netas"] * (1 + desperdicio)
    mezcla = g["mezcla_neta"] * (1 + desperdicio)
    cantidad = entrada.cantidad
    total_mezcla = mezcla * cantidad
    insumos = [
        {
            "parte": "sillar", "clave": CLAVE_PIEZA, "descripcion": _DESCRIPCIONES[CLAVE_PIEZA], "unidad": "pza",
            "por_unidad": piezas, "total": piezas * cantidad, "a_comprar": float(math.ceil(piezas * cantidad - 1e-9)),
        },
        {
            "parte": "mezcla", "clave": CLAVE_MEZCLA, "descripcion": _DESCRIPCIONES[CLAVE_MEZCLA], "unidad": "m3",
            "por_unidad": mezcla, "total": total_mezcla, "a_comprar": None,
        },
    ]
    compuesta = [
        {"clave": k, "descripcion": d, "unidad": u, "por_m3": q, "total": q * total_mezcla, "linea": linea}
        for k, d, u, q, linea in MEZCLA_COMPUESTA
    ]
    conciliacion = _conciliar(piezas, mezcla)
    avisos = []
    if not all(f["marca"] == "=" for f in conciliacion[0]["filas"]):
        avisos.append(
            f"El catálogo trae {_COMPOSICION_DEL_CATALOGO[0][1]:g} pza y {_COMPOSICION_DEL_CATALOGO[1][1]:g} m³ por m²; con la pieza 19×25×45, junta de "
            f"{entrada.junta_cm:g} cm y {entrada.desperdicio_pct:g} % el cálculo da {piezas:.2f} pza y {mezcla:.4f} m³. La diferencia está en la "
            "conciliación: el catálogo no se edita."
        )
    return {
        "clave": e.clave,
        "nombre": e.nombre,
        "medida": "m2",
        "unidad": "m²",
        "cantidad": cantidad,
        "nivel": None,
        "concepto": {
            "clave": e.concepto_clave,
            "descripcion": e.concepto_descripcion,
            "unidad": "m2",
            "etiqueta": "Concepto del catálogo (matriz BAP-01010)",
            "estado": "catalogo",
            "clave_provisional": False,
            "nivel_desde": None,
        },
        "pieza": {"insumo": CLAVE_PIEZA, "ancho_cm": e.espesor_cm, "alto_cm": e.alto_cm, "largo_cm": e.largo_cm},
        "parametros": {
            "junta_cm": entrada.junta_cm,
            "junta_entre_hileras_cm": None,
            "desperdicio_de_pieza_pct": entrada.desperdicio_pct,
            "desperdicio_de_mezcla_pct": entrada.desperdicio_pct,
            "cama_cm": None,
            "tipo_de_sardinel": None,
            "nivel_desde_3er_nivel": None,
        },
        "geometria": {
            "espesor_real_cm": e.espesor_cm,
            "espesor_minimo_cm": e.espesor_cm,
            "espesor_medio_cm": e.espesor_cm,
            "hilada_promedio_cm": g["hilada_cm"],
            "piezas_por_hilada": g["piezas_por_hilada"],
            "hiladas": g["hiladas"],
        },
        "piezas": {"netas_por_unidad": g["netas"], "por_unidad": piezas, "total": piezas * cantidad, "a_comprar": math.ceil(piezas * cantidad - 1e-9)},
        "mezcla": {"neta_por_unidad": g["mezcla_neta"], "por_unidad": mezcla, "total_m3": total_mezcla},
        "insumos": insumos,
        "mezcla_compuesta": compuesta,
        "mano_de_obra": {
            "estado": "destajo_del_catalogo",
            "destajo": {"clave": e.destajo[0], "descripcion": e.destajo[1], "unidad": e.destajo[2]},
            "cantidad": cantidad,
            "nota": "El destajo es el del catálogo y se paga por m² con el concepto; el elemento no lo calcula ni pone precio.",
        },
        "herramienta": [],
        "conciliacion": conciliacion,
        "avisos": avisos,
    }


# --- Definición ---------------------------------------------------------------------------------------------------------------


def definicion_de(clave: str) -> dict[str, Any]:
    """La ficha del elemento: sus parámetros por defecto, el aparejo, el concepto que lo paga y los pendientes."""
    e = elemento_de_sillar(clave)
    g = _geometria(e, EntradaMuroDeSillar())
    return {
        "clave": e.clave,
        "nombre": e.nombre,
        "nombre_nominal": e.nombre_nominal,
        "tipo": "sillar",
        "medida": "m2",
        "se_mide_por": "m²",
        "categoria": {"clave": "muros", "nombre": "Muros"},
        "subcategoria": {"clave": "sillar", "nombre": "Muros de sillar"},
        "espesor_nominal_cm": int(e.espesor_cm),
        "espesor_real_cm": e.espesor_cm,
        "aparejo": "a hilo (soga)",
        "aparejo_largo": "A hilo: la cara de 45 × 25 cm queda a la vista, tendida",
        "aparejo_texto": (
            "colocada a hilo: la cara de 45 × 25 cm queda a la vista y tendida; el espesor del muro es el de la pieza, 19 cm. Las hiladas se traban "
            "a media pieza."
        ),
        "planta_nota": "Planta de la hilada: una pieza a hilo de 19 cm de espesor.",
        "pieza": {"insumo": CLAVE_PIEZA, "ancho_cm": e.espesor_cm, "alto_cm": e.alto_cm, "largo_cm": e.largo_cm},
        "mezcla": CLAVE_MEZCLA,
        "parametros_por_defecto": {
            "junta_cm": JUNTA_POR_DEFECTO_CM,
            "junta_entre_hileras_cm": None,
            "desperdicio_de_pieza_pct": DESPERDICIO_POR_DEFECTO_PCT,
            "desperdicio_de_mezcla_pct": DESPERDICIO_POR_DEFECTO_PCT,
            "cama_cm": None,
            "tipo_de_sardinel": None,
            "nivel_desde_3er_nivel": None,
        },
        "tipos_de_sardinel": [],
        "hiladas": [{"peso": 1.0, "filas": ["hilo"]}],
        "conceptos": [
            {
                "clave": e.concepto_clave,
                "etiqueta": "Concepto del catálogo (matriz BAP-01010)",
                "descripcion": e.concepto_descripcion,
                "unidad": "m2",
                "estado": "catalogo",
                "clave_provisional": False,
                "en_catalogo": True,
                "destajo": {"clave": e.destajo[0], "descripcion": e.destajo[1], "unidad": e.destajo[2]},
                "nivel_desde": None,
            }
        ],
        "driver_de_desperdicio": CLAVE_DEL_DRIVER_DE_DESPERDICIO,
        "piezas_por_unidad_de_partida": g["netas"] * (1 + DESPERDICIO_POR_DEFECTO_PCT / 100),
        "fuente": _FUENTE,
        "avisos_de_catalogo": [],
        "pendientes": [{"clave": k, "texto": t} for k, t in _PENDIENTES],
    }


# --- Propuestas de versión de concepto ---------------------------------------------------------------------------------------------


def concepto_nuevo_de(clave: str) -> dict[str, Any]:
    """El sillar amarillo **no** necesita concepto nuevo: BAP-01010 ya es una matriz del catálogo y cubre el elemento (regla F7)."""
    e = elemento_de_sillar(clave)
    raise ErrorDeMuroDeSillar(f"{e.clave} ya está en el catálogo (matriz BAP-01010): no hace falta un concepto nuevo.")


def propuestas_de_actualizacion_de_apu(calculo: Mapping[str, Any]) -> list[dict[str, Any]]:
    """«Confirmar cálculo → actualizar APU»: una nueva versión propuesta de BAP-01010 cuando algún insumo difiere del cálculo (marca ≈ o ≠).
    Los coeficientes `antes` son los del catálogo; el catálogo no se edita. Sin cambios, no hay propuesta."""
    propuestas: list[dict[str, Any]] = []
    clave = str(calculo["clave"])
    params = calculo["parametros"]
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
                "elemento_clave": clave,
                "concepto_clave": concepto,
                "clase": "version_de_concepto",
                "resumen": f"Nueva versión de {concepto}: " + "; ".join(f"{c['insumo']} {c['antes']:g} → {c['despues']:g}" for c in cambios),
                "detalle": {
                    "cambios": cambios,
                    "motivos": [
                        "Confirmar cálculo → actualizar APU: los coeficientes del cálculo con la pieza 19×25×45, "
                        f"junta de {params['junta_cm']:g} cm y {params['desperdicio_de_pieza_pct']:g} % de desperdicio (driver desperdicio_mamposteria).",
                        "La junta del sillar no viene en el catálogo (supuesto de 2 cm, editable): Control de obra decide si autoriza la versión.",
                    ],
                    "hasta_m": None,
                },
            }
        )
    return propuestas

