"""Muro de contención de piedra (MCT-01010): el primer elemento de la biblioteca de elementos.

Categoría «Muros de contención» › subcategoría «Mampostería». Se mide por **metro lineal de trazo** y se paga con
un solo concepto por m³, el **MCT-01011** (muro de mampostería de piedra de cerro). El dren va **dentro** de ese
concepto: el elemento calcula cuánto tubo, grava y mortero de carpeta hace falta y lo reparte entre el volumen del
muro para sumarlo al APU por m³.

Reglas (mockup de muros paramétricos, decisiones M-31…M-78; Cuadro 1 de un manual que aportó el usuario):

- La altura se captura en **metros**. Corona y base salen del Cuadro 1: se toma la fila de la altura **igual o
  inmediata superior** (sin interpolar); el volumen usa la altura exacta. Corona y base se pueden fijar a mano.
- Dentellón opcional (por defecto sí) **desde 2.00 m**: b2 0.40, b1 0.30, h 0.60 m = 0.21 m³ por metro; su
  excavación es igual a su volumen.
- Dren desde 2.00 m: lloraderos de 3" al tresbolillo, cada 3.00 m (1.50 m con lluvia alta); primera hilera a
  0.50 m y luego cada 1.00 m mientras quepa; filtro de grava detrás del muro; carpeta de mortero de 3 cm en la corona.
- La tubería se calcula en ml (lloraderos por metro × espesor medio del muro) y se convierte a **piezas
  comerciales** (PVC de 6.00 m o concreto de 1.00 m) para el APU.
- Los insumos del dren que aún no tienen precio (INS-D001, INS-D002, INS-D003) son **provisionales**: se marcan
  como tales y el precio unitario avisa que no los incluye.

Lo que la especificación deja abierto no se inventa: el espesor del filtro de grava queda como parámetro sin valor
(«por definir»), y las preguntas abiertas se devuelven en `PENDIENTES` para mostrarlas. Función pura, sin base de datos.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = [
    "CLAVE_CONCEPTO",
    "CLAVE_ELEMENTO",
    "CUADRO_1",
    "DENTELLON",
    "DESCRIPCION_CONCEPTO",
    "FUENTE_CUADRO_1",
    "PENDIENTES",
    "EntradaMuroDeContencion",
    "ErrorDeMuroDeContencion",
    "calcular_muro_de_contencion",
    "fila_del_cuadro_1",
    "piezas_de_tubo",
]

CLAVE_ELEMENTO = "MCT-01010"
CLAVE_CONCEPTO = "MCT-01011"
DESCRIPCION_CONCEPTO = "MURO DE MAMPOSTERÍA DE PIEDRA DE CERRO"

FUENTE_CUADRO_1 = (
    "Cuadro 1 «Volumetría de 1 m lineal de muro de mampostería» y recomendaciones de drenaje del manual que aportó "
    "el usuario (título y autor por confirmar)."
)

# H, base (B), corona (B1), volumen del muro por metro (Vm), piedra a comprar, cemento (kg), arena (m³), agua (l).
CUADRO_1: tuple[dict[str, float], ...] = (
    {
        "H": 1.0,
        "B": 0.45,
        "B1": 0.30,
        "Vm": 0.38,
        "piedra": 0.57,
        "cemento_kg": 32.0,
        "arena_m3": 0.16,
        "agua_l": 30.0,
    },
    {
        "H": 1.5,
        "B": 0.65,
        "B1": 0.35,
        "Vm": 0.75,
        "piedra": 1.13,
        "cemento_kg": 62.0,
        "arena_m3": 0.31,
        "agua_l": 59.25,
    },
    {
        "H": 2.0,
        "B": 0.80,
        "B1": 0.60,
        "Vm": 1.40,
        "piedra": 2.10,
        "cemento_kg": 116.0,
        "arena_m3": 0.57,
        "agua_l": 111.0,
    },
    {
        "H": 2.5,
        "B": 1.05,
        "B1": 0.60,
        "Vm": 2.06,
        "piedra": 3.10,
        "cemento_kg": 171.0,
        "arena_m3": 0.84,
        "agua_l": 163.0,
    },
    {
        "H": 3.0,
        "B": 1.20,
        "B1": 0.60,
        "Vm": 2.70,
        "piedra": 4.05,
        "cemento_kg": 225.0,
        "arena_m3": 1.10,
        "agua_l": 213.0,
    },
    {
        "H": 3.5,
        "B": 1.44,
        "B1": 0.60,
        "Vm": 3.57,
        "piedra": 5.36,
        "cemento_kg": 297.0,
        "arena_m3": 1.50,
        "agua_l": 282.0,
    },
    {
        "H": 4.0,
        "B": 1.64,
        "B1": 0.60,
        "Vm": 4.48,
        "piedra": 6.72,
        "cemento_kg": 373.0,
        "arena_m3": 1.83,
        "agua_l": 354.0,
    },
    {
        "H": 4.5,
        "B": 1.85,
        "B1": 0.60,
        "Vm": 5.54,
        "piedra": 8.31,
        "cemento_kg": 461.0,
        "arena_m3": 2.26,
        "agua_l": 438.0,
    },
    {
        "H": 5.0,
        "B": 2.05,
        "B1": 0.60,
        "Vm": 6.65,
        "piedra": 9.98,
        "cemento_kg": 554.0,
        "arena_m3": 2.71,
        "agua_l": 525.0,
    },
    {
        "H": 5.5,
        "B": 2.25,
        "B1": 0.60,
        "Vm": 7.86,
        "piedra": 11.80,
        "cemento_kg": 654.0,
        "arena_m3": 3.20,
        "agua_l": 621.0,
    },
    {
        "H": 6.0,
        "B": 2.47,
        "B1": 0.60,
        "Vm": 9.18,
        "piedra": 13.77,
        "cemento_kg": 810.0,
        "arena_m3": 3.75,
        "agua_l": 725.0,
    },
)
ALTURA_MAXIMA_DE_LA_TABLA_M = 6.0

DENTELLON = {
    "desde_H": 2.0,
    "hasta_H": 6.0,
    "b2": 0.40,
    "b1": 0.30,
    "h": 0.60,
    "volumen_m3": 0.21,
}
ABUNDAMIENTO_DE_LA_PIEDRA = 1.5
POR_M3_DE_MAMPOSTERIA = {"cemento_kg": 83.3, "arena_m3": 0.408, "agua_l": 79.0}

DREN = {
    "desde_H": 2.0,
    "primera_hilera_m": 0.5,
    "separacion_vertical_m": 1.0,
    "separacion_longitudinal_m": {"baja": 3.0, "alta": 1.5},
    "diametro_pulgadas": 3,
}
ESPESOR_DE_LA_CARPETA_M = 0.03

# Insumos del dren. Los INS-D* no están en el catálogo y no tienen precio: son provisionales hasta que Costos los precie.
INSUMOS_DEL_DREN: dict[str, dict[str, Any]] = {
    "pvc": {
        "clave": "INS-D001",
        "descripcion": 'TUBO PVC SANITARIO DE 3" (PIEZA DE 6 M) PARA LLORADERO',
        "unidad": "pza",
        "largo_m": 6.0,
        "provisional": True,
    },
    "concreto": {
        "clave": "INS-D002",
        "descripcion": 'TUBO DE CONCRETO DE 3" (PIEZA DE 1 M) PARA LLORADERO',
        "unidad": "pza",
        "largo_m": 1.0,
        "provisional": True,
    },
}
GRAVA = {
    "clave": "INS-D003",
    "descripcion": "GRAVA PARA FILTRO DE DREN",
    "unidad": "m3",
    "provisional": True,
}
MORTERO_DE_CARPETA = {
    "clave": "MEZ-03060",
    "descripcion": "MEZCLA CEMENTO-ARENA 1:6",
    "unidad": "m3",
    "provisional": False,
}

# Preguntas abiertas de la especificación que tocan a este elemento: se muestran, no se resuelven por cuenta propia.
PENDIENTES: tuple[dict[str, str], ...] = (
    {
        "clave": "Q34",
        "texto": 'Faltan los precios del tubo de 3" (PVC o concreto) y de la grava, y el espesor del filtro de grava, que el manual no da. La longitud de cada lloradero se supone igual al espesor medio del muro y el mortero de la carpeta se supone el mismo 1:6 del concepto.',
    },
    {
        "clave": "Q43",
        "texto": "Se supone que la cara vertical es el trasdós (lado del relleno) y que el filtro de grava va detrás de ella. Confirmar con el usuario.",
    },
    {
        "clave": "Q44",
        "texto": 'Largos comerciales del tubo del lloradero: se supone 6.00 m para el PVC sanitario de 3" y 1.00 m para el tubo de concreto. Falta confirmar que son los que se compran y que se aprovechan los sobrantes.',
    },
    {
        "clave": "Q47",
        "texto": "El dentellón viene en el Cuadro 1 (desde 2.00 m, 0.21 m³ por metro) y por eso es opción activa por defecto; falta confirmar si el muro lo lleva.",
    },
    {
        "clave": "Q48",
        "texto": "Con el relleno sobre la cara inclinada: falta confirmar si lleva además una capa de grava o geotextil bajo el relleno, y desde qué lado se miden los lloraderos.",
    },
    {
        "clave": "Q35",
        "texto": "El muro de contención todavía no se coloca desde el Cuantificador (por metro lineal de trazo): por ahora solo existe en Elementos.",
    },
    {
        "clave": "Q37",
        "texto": "Falta el título, autor y año del manual del Cuadro 1 para registrarlo como fuente y confirmar si hay una norma que lo respalde.",
    },
    {
        "clave": "estabilidad",
        "texto": "El elemento no calcula volteo ni deslizamiento: la estabilidad la valida el estructurista.",
    },
)


class ErrorDeMuroDeContencion(ErrorDeCuantificacion):
    """Un parámetro del muro que no vale: no se puede calcular con él."""


@dataclass(frozen=True)
class EntradaMuroDeContencion:
    """Lo que se captura del muro. La altura en **metros**."""

    alto_m: float
    corona_m: float | None = None
    base_m: float | None = None
    dentellon: bool = True
    lluvia: str = "baja"
    tubo: str = "pvc"
    filtro_cm: float | None = None
    relleno: str = "vertical"
    tramo_m: float = 6.0


def fila_del_cuadro_1(alto_m: float) -> tuple[dict[str, float], bool]:
    """La fila de la altura igual o inmediata superior (sin interpolar) y si la altura rebasa la tabla."""
    for fila in CUADRO_1:
        if alto_m <= fila["H"] + 1e-9:
            return fila, False
    return CUADRO_1[-1], True


def piezas_de_tubo(largo_lloradero_m: float, largo_pieza_m: float) -> dict[str, float]:
    """Piezas comerciales por lloradero.

    Si el lloradero cabe en una pieza se cortan `floor(pieza ÷ lloradero)` por pieza (y cada lloradero gasta
    `1/n` de pieza); si no cabe se unen `ceil(lloradero ÷ pieza)` piezas.
    """
    if not (largo_lloradero_m > 0) or not (largo_pieza_m > 0):
        return {"por_pieza": 0, "piezas_por_lloradero": 0.0}
    if largo_lloradero_m <= largo_pieza_m + 1e-9:
        n = max(1, math.floor(largo_pieza_m / largo_lloradero_m + 1e-9))
        return {"por_pieza": n, "piezas_por_lloradero": 1 / n}
    return {
        "por_pieza": 0,
        "piezas_por_lloradero": float(
            math.ceil(largo_lloradero_m / largo_pieza_m - 1e-9)
        ),
    }


def _validar(e: EntradaMuroDeContencion) -> None:
    if not (e.alto_m > 0) or e.alto_m > 20:
        raise ErrorDeMuroDeContencion(
            "La altura se captura en metros y debe ser mayor que cero (máximo 20 m)."
        )
    for nombre, valor in (("corona", e.corona_m), ("base", e.base_m)):
        if valor is not None and not (0 < valor <= 10):
            raise ErrorDeMuroDeContencion(
                f"La {nombre} se captura en metros y debe estar entre 0 y 10."
            )
    if e.lluvia not in DREN["separacion_longitudinal_m"]:
        raise ErrorDeMuroDeContencion("La lluvia es «baja» o «alta».")
    if e.tubo not in INSUMOS_DEL_DREN:
        raise ErrorDeMuroDeContencion("El tubo del lloradero es «pvc» o «concreto».")
    if e.relleno not in ("vertical", "inclinada"):
        raise ErrorDeMuroDeContencion(
            "El relleno va del lado de la cara «vertical» o «inclinada»."
        )
    if e.filtro_cm is not None and not (0 < e.filtro_cm <= 200):
        raise ErrorDeMuroDeContencion(
            "El espesor del filtro de grava va en centímetros, entre 0 y 200."
        )
    if not (0 < e.tramo_m <= 50):
        raise ErrorDeMuroDeContencion("El tramo de las vistas va entre 0 y 50 m.")


def _xs_de_la_hilera(indice: int, separacion: float, tramo: float) -> list[float]:
    """Posiciones de los lloraderos de una hilera: las pares arrancan a ¼ de la separación, las impares a ¾ (tresbolillo)."""
    x = separacion / 4 if indice % 2 == 0 else 3 * separacion / 4
    xs: list[float] = []
    while x < tramo - 1e-9:
        xs.append(round(x, 6))
        x += separacion
    return xs


def calcular_muro_de_contencion(e: EntradaMuroDeContencion) -> dict[str, Any]:
    """Todo lo que sale del muro por metro de trazo: sección, volúmenes, dren, insumos por m³ y datos de las vistas."""
    _validar(e)
    alto = e.alto_m
    fila, fuera = fila_del_cuadro_1(alto)
    manual = e.corona_m is not None or e.base_m is not None
    corona = e.corona_m if e.corona_m is not None else fila["B1"]
    base = e.base_m if e.base_m is not None else fila["B"]
    if base < corona:
        raise ErrorDeMuroDeContencion("La base no puede ser menor que la corona.")

    espesor_medio = (base + corona) / 2
    vm = espesor_medio * alto
    aplica_dentellon = bool(e.dentellon) and DENTELLON["desde_H"] - 1e-9 <= alto
    den = DENTELLON["volumen_m3"] if aplica_dentellon else 0.0
    vt = vm + den

    # Dren.
    con_dren = DREN["desde_H"] - 1e-9 <= alto
    alturas: list[float] = []
    if con_dren:
        p = DREN["primera_hilera_m"]
        while p < alto - 1e-9:
            alturas.append(round(p, 6))
            p += DREN["separacion_vertical_m"]
    hileras = len(alturas)
    sep = DREN["separacion_longitudinal_m"][e.lluvia]
    lloraderos_ml = hileras / sep

    tubo = INSUMOS_DEL_DREN[e.tubo]
    cortes = (
        piezas_de_tubo(espesor_medio, tubo["largo_m"])
        if hileras
        else {"por_pieza": 0, "piezas_por_lloradero": 0.0}
    )
    ml_tubo_ml = lloraderos_ml * espesor_medio
    piezas_ml = lloraderos_ml * cortes["piezas_por_lloradero"]

    inclinada = e.relleno == "inclinada"
    longitud_cara = math.hypot(alto, base - corona) if inclinada else alto
    filtro_m3_ml = (
        (e.filtro_cm / 100 * longitud_cara) if (e.filtro_cm and hileras) else None
    )
    carpeta_m3_ml = corona * ESPESOR_DE_LA_CARPETA_M

    # Lo que el dren suma al APU del concepto, por m³ de muro (todo entre el volumen por metro).
    insumos: list[dict[str, Any]] = []
    if hileras:
        insumos.append(
            {
                **{k: tubo[k] for k in ("clave", "descripcion", "unidad", "provisional")},
                "cantidad": piezas_ml / vt,
                "detalle": (
                    f"{hileras} hilera(s) × {1 / sep:.2f} por metro = {lloraderos_ml:.2f} lloraderos por metro; "
                    f"cada uno del espesor medio ({espesor_medio:.2f} m) = {ml_tubo_ml:.2f} ml de tubo por metro de trazo; "
                    + (
                        f"{int(cortes['por_pieza'])} lloradero(s) por pieza de {tubo['largo_m']:.2f} m"
                        if cortes["por_pieza"]
                        else f"{cortes['piezas_por_lloradero']:.0f} piezas de {tubo['largo_m']:.2f} m por lloradero"
                    )
                    + f" = {piezas_ml:.3f} pza por metro de trazo"
                ),
            }
        )
        if filtro_m3_ml is not None:
            insumos.append(
                {
                    **{
                        k: GRAVA[k]
                        for k in ("clave", "descripcion", "unidad", "provisional")
                    },
                    "cantidad": filtro_m3_ml / vt,
                    "detalle": (
                        f"espesor {e.filtro_cm:g} cm × longitud de la cara {'inclinada' if inclinada else 'vertical'} "
                        f"({longitud_cara:.2f} m) = {filtro_m3_ml:.3f} m³ por metro de trazo"
                    ),
                }
            )
        else:
            insumos.append(
                {
                    **{
                        k: GRAVA[k]
                        for k in ("clave", "descripcion", "unidad", "provisional")
                    },
                    "cantidad": 0.0,
                    "detalle": "falta el espesor del filtro de grava (el manual no lo da)",
                }
            )
    insumos.append(
        {
            **{
                k: MORTERO_DE_CARPETA[k]
                for k in ("clave", "descripcion", "unidad", "provisional")
            },
            "cantidad": carpeta_m3_ml / vt,
            "detalle": (
                f"carpeta de 3 cm × corona {corona:.2f} m = {carpeta_m3_ml:.3f} m³ por metro de trazo "
                "(mortero 1:6, supuesto)"
            ),
        }
    )

    advertencias: list[str] = []
    if fuera:
        advertencias.append(
            f"La altura rebasa el Cuadro 1, que llega a {ALTURA_MAXIMA_DE_LA_TABLA_M:.2f} m: se usó su última fila. "
            "Lo valida el estructurista."
        )
    if e.dentellon and not aplica_dentellon:
        advertencias.append(
            "El dentellón aplica desde 2.00 m de altura: con esta altura no se agrega."
        )
    if hileras and e.filtro_cm is None:
        advertencias.append(
            "Falta el espesor del filtro de grava: el manual no lo da, queda por definir."
        )
    sin_precio = [i["clave"] for i in insumos if i["provisional"] and i["cantidad"] > 0]
    if sin_precio:
        advertencias.append(
            "El precio unitario del concepto no incluye "
            + ", ".join(sin_precio)
            + ": son insumos provisionales sin "
            "precio; Costos los asigna."
        )
    if hileras == 0:
        advertencias.append("Con menos de 2.00 m de altura el manual no pide drenes.")

    return {
        "clave": CLAVE_ELEMENTO,
        "unidad": "m³ por metro lineal de trazo",
        "concepto": {
            "clave": CLAVE_CONCEPTO,
            "descripcion": DESCRIPCION_CONCEPTO,
            "unidad": "m3",
        },
        "seccion": {
            "alto_m": alto,
            "corona_m": corona,
            "base_m": base,
            "espesor_medio_m": espesor_medio,
            "manual": manual,
            "fila_cuadro_1": {"H": fila["H"], "B": fila["B"], "B1": fila["B1"]},
            "fuera_de_tabla": fuera,
        },
        "volumen": {
            "muro_m3_ml": vm,
            "dentellon_m3_ml": den,
            "excavacion_dentellon_m3_ml": den,
            "total_m3_ml": vt,
            "piedra_a_comprar_m3_ml": vt * ABUNDAMIENTO_DE_LA_PIEDRA,
            "abundamiento": ABUNDAMIENTO_DE_LA_PIEDRA,
            "cemento_kg_ml": vt * POR_M3_DE_MAMPOSTERIA["cemento_kg"],
            "arena_m3_ml": vt * POR_M3_DE_MAMPOSTERIA["arena_m3"],
            "agua_l_ml": vt * POR_M3_DE_MAMPOSTERIA["agua_l"],
        },
        "dentellon": {
            "aplica": aplica_dentellon,
            "opcion": bool(e.dentellon),
            "b2_m": DENTELLON["b2"],
            "b1_m": DENTELLON["b1"],
            "h_m": DENTELLON["h"],
        },
        "dren": {
            "aplica": hileras > 0,
            "hileras": hileras,
            "alturas_m": alturas,
            "separacion_m": sep,
            "lluvia": e.lluvia,
            "lloraderos_por_ml": lloraderos_ml,
            "tubo": {
                "clave": tubo["clave"],
                "descripcion": tubo["descripcion"],
                "material": e.tubo,
                "largo_pieza_m": tubo["largo_m"],
                "ml_por_ml_de_trazo": ml_tubo_ml,
                "lloraderos_por_pieza": cortes["por_pieza"],
                "piezas_por_lloradero": cortes["piezas_por_lloradero"],
                "piezas_por_ml_de_trazo": piezas_ml,
                "provisional": True,
            },
            "filtro": {
                "espesor_cm": e.filtro_cm,
                "relleno": e.relleno,
                "longitud_cara_m": longitud_cara,
                "volumen_m3_ml": filtro_m3_ml,
                "por_definir": hileras > 0 and e.filtro_cm is None,
            },
            "carpeta": {
                "espesor_m": ESPESOR_DE_LA_CARPETA_M,
                "volumen_m3_ml": carpeta_m3_ml,
            },
        },
        "insumos_por_m3": insumos,
        "vistas": {
            "tramo_m": e.tramo_m,
            "hileras": [
                {"altura_m": alturas[k], "x_m": _xs_de_la_hilera(k, sep, e.tramo_m)}
                for k in range(hileras)
            ],
        },
        "advertencias": advertencias,
    }
