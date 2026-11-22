"""El relleno DINÁMICO de azotea: arenilla de espesor variable según las bajadas pluviales, bajo una plantilla de mortero.

Decisión del usuario (2026-11-22, «Relleno azotea con bajadas», opción 1): el relleno de azotea lleva **dos capas**, primero una de **arenilla** de espesor
variable y encima una **plantilla de mortero** de 5 cm. El espesor de la arenilla lo calcula el sistema según las bajadas: **5 cm mínimo en cada bajada** y el
resto según la pendiente. La pendiente es un % por zona; un ÁREA marca la zona, un PUNTO identifica cada bajada y una LÍNEA dice hacia dónde van las
pendientes (si no se traza, el sistema la genera: la dirección hacia la bajada que drena cada punto). Las líneas punteadas («maestras» o «hilos de nivel») son
las guías del relleno: el sistema las genera y el visor las muestra.

El modelo
---------
El espesor de la arenilla en un punto ``p`` de la zona es

    e(p) = e_bajada  +  pendiente × d(p)  +  compensación

- ``e_bajada``: el espesor mínimo en la bajada (5 cm por omisión).
- ``pendiente``: la pendiente de la zona como fracción (2 % = 0.02; 2 % es el valor conservador por omisión, editable).
- ``d(p)``: la distancia de **drenaje** de ``p`` a la bajada que lo drena, que es la más cercana. Sin línea trazada es la distancia en línea recta a la bajada.
  Con una línea trazada para esa bajada (dibujada **hacia** la bajada) es la distancia al punto más cercano de la línea más lo que falta recorrer por la línea
  hasta su extremo y de ahí a la bajada: la pendiente baja hacia la línea y luego corre por ella.
- ``compensación``: lo que suma el relleno de una subzona de losa más delgada para igualar la más gruesa de la zona (la misma de ``relleno``; 0 si se apaga).

El volumen de la arenilla es la **integral del espesor sobre el área de la zona**: ``V = ∫∫ e(p) dA = A × ē`` con ``ē`` el espesor medio. La plantilla de mortero
es un espesor fijo (5 cm): ``A × 0.05`` m³ y ``A`` m² del concepto ``ALB-03014``.

El método numérico y su error
-----------------------------
El espesor no tiene primitiva cerrada en un polígono con huecos y varias bajadas (la frontera entre dos bajadas es una mediatriz y el espesor tiene un pliegue
sobre ella), así que se integra numéricamente, **de forma determinista** (misma entrada, mismo resultado, sin azar):

1. El área ``A`` es la **exacta** de la fórmula del zapatero (con los huecos restados); no se aproxima.
2. El espesor medio ``ē`` se estima con la **regla del punto medio** sobre una retícula cuadrada de paso ``h`` anclada en la esquina de la caja del polígono: el
   espesor de cada centro de celda que cae dentro del polígono (regla par-impar por barrido de filas, que respeta los huecos) y ``ē ≈ Σ e(cᵢ) / n``.
3. Se hace con dos retículas, una de ≈ 2 500 celdas y otra de ≈ 10 000 (paso a la mitad); **se reporta la fina** y como **error estimado** la diferencia entre las
   dos (en una regla de primer orden, que es lo que da una frontera irregular, la diferencia entre ``h`` y ``h/2`` es una cota práctica del error de la fina).
4. Cota teórica sin línea trazada: ``e`` es Lipschitz con constante ``pendiente`` (``d`` es 1-Lipschitz), así que cada celda se equivoca a lo más
   ``pendiente × h × √2 / 2`` en el espesor y ``|ē − ē_h| ≤ pendiente × h × √2 / 2`` más el sesgo de las celdas de borde, que es de orden ``h × perímetro / A`` del
   mismo espesor. Con 10 000 celdas ``h ≈ √(A / 10 000)`` (7 cm en 50 m²) y el error es de milímetros de espesor: menos de 0.1 % del volumen en los casos de una
   azotea. En un polígono muy delgado el paso se reduce hasta que caen al menos 25 centros de celda.

Las **guías** se generan sin integrar: la línea de pendiente de cada bajada va del punto más lejano que drena a la bajada (o es la línea trazada), y los **hilos de
nivel** son los arcos de circunferencia ``d = k × 1 m`` alrededor de cada bajada (sin línea trazada) recortados a la zona y a la región que esa bajada drena: sobre
ellos el espesor es constante (``e_bajada + pendiente × k``), por eso son hilos de nivel.

Función pura, sin base de datos. Las coordenadas llegan en metros (el plano ya multiplicado por su escala).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

Punto = tuple[float, float]
Anillo = tuple[Punto, ...]
Poligono = tuple[Anillo, ...]
"""Un polígono: el primer anillo es el exterior y los demás son huecos (coordenadas en metros)."""

__all__ = [
    "CELDAS_FINAS",
    "CELDAS_GRUESAS",
    "ESPESOR_EN_BAJADA_M",
    "ESPESOR_MORTERO_M",
    "METODO",
    "PASO_DE_HILOS_M",
    "PENDIENTE_POR_OMISION_PCT",
    "Bajada",
    "ResultadoDeIntegral",
    "area_de_poligono",
    "bajada_que_drena",
    "distancia_al_borde",
    "distancia_de_drenaje",
    "espesor_de_arenilla",
    "guias_de_pendiente",
    "integrar_arenilla",
    "punto_en_zona",
    "region_de_una_bajada",
]

ESPESOR_EN_BAJADA_M = 0.05
"""Los 5 cm mínimos de arenilla en cada bajada (decisión del usuario)."""
ESPESOR_MORTERO_M = 0.05
"""La plantilla de mortero de 5 cm (decisión del usuario)."""
PENDIENTE_POR_OMISION_PCT = 2.0
"""Valor conservador por omisión (el usuario no lo dio): 2 % es la pendiente mínima habitual de una azotea. Editable por zona."""
PASO_DE_HILOS_M = 1.0
"""Cada hilo de nivel está a 1 m más de drenaje que el anterior (el espesor sube ``pendiente × 1 m``)."""
CELDAS_GRUESAS = 2_500
CELDAS_FINAS = 10_000
_MINIMO_DE_CENTROS = 25
_MAXIMO_DE_HILOS = 40
_PASO_ANGULAR_GRADOS = 1.5

METODO = (
    "Integral numérica determinista: área exacta (fórmula del zapatero) por espesor medio con la regla del punto medio sobre una retícula cuadrada "
    "(≈10 000 celdas; el error estimado es la diferencia contra la de ≈2 500 celdas)."
)


@dataclass(frozen=True)
class Bajada:
    """Una bajada pluvial: su punto en el plano (m) y, si se trazó, la línea de pendiente que baja hacia ella (m, dibujada hacia la bajada)."""

    id: str
    x: float
    y: float
    rotulo: str | None = None
    linea: tuple[Punto, ...] | None = None


@dataclass
class ResultadoDeIntegral:
    area_m2: float
    espesor_medio_m: float
    volumen_m3: float
    espesor_maximo_m: float
    muestras: int
    celda_m: float
    error_estimado_m3: float
    por_bajada: dict[str, dict[str, float]] = field(default_factory=dict)
    """`{id de la bajada: {area_m2, distancia_maxima_m, espesor_maximo_m}}` de lo que cada bajada drena."""
    lejano: dict[str, Punto] = field(default_factory=dict)
    """El punto más lejano que drena cada bajada (de ahí arranca su línea de pendiente automática)."""


# --------------------------------------------------------------------------------------------------------------
# Geometría
# --------------------------------------------------------------------------------------------------------------


def _area_anillo(anillo: Sequence[Punto]) -> float:
    s = 0.0
    n = len(anillo)
    for i in range(n):
        x0, y0 = anillo[i]
        x1, y1 = anillo[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return abs(s) / 2


def area_de_poligono(p: Poligono) -> float:
    """El área neta de un polígono: el exterior menos los huecos."""
    if not p:
        return 0.0
    return max(_area_anillo(p[0]) - sum(_area_anillo(h) for h in p[1:]), 0.0)


def _distancia_a_segmento(p: Punto, a: Punto, b: Punto) -> tuple[float, float, Punto]:
    """`(distancia, t, punto más cercano)` de `p` al segmento `ab` (t en 0..1)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    largo2 = dx * dx + dy * dy
    t = 0.0 if largo2 <= 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / largo2))
    q = (a[0] + t * dx, a[1] + t * dy)
    return math.hypot(p[0] - q[0], p[1] - q[1]), t, q


def _cruces(poligono: Poligono, y: float) -> list[float]:
    """Las x donde la horizontal `y` cruza algún borde del polígono (anillos exterior y huecos), con borde semiabierto para no contar dos veces un vértice."""
    xs: list[float] = []
    for anillo in poligono:
        n = len(anillo)
        for i in range(n):
            x0, y0 = anillo[i]
            x1, y1 = anillo[(i + 1) % n]
            if (y0 <= y < y1) or (y1 <= y < y0):
                xs.append(x0 + (y - y0) / (y1 - y0) * (x1 - x0))
    xs.sort()
    return xs


def punto_en_zona(p: Punto, poligonos: Sequence[Poligono]) -> bool:
    """El punto está dentro de alguno de los polígonos (par-impar: los huecos quedan fuera)."""
    for poli in poligonos:
        cruces = [x for x in _cruces(poli, p[1]) if x > p[0]]
        if len(cruces) % 2 == 1:
            return True
    return False


def distancia_al_borde(p: Punto, poligonos: Sequence[Poligono]) -> float:
    """La distancia (m) de un punto al borde más cercano de los polígonos (exteriores y huecos)."""
    mejor = math.inf
    for poli in poligonos:
        for anillo in poli:
            n = len(anillo)
            for i in range(n):
                mejor = min(mejor, _distancia_a_segmento(p, anillo[i], anillo[(i + 1) % n])[0])
    return mejor


# --------------------------------------------------------------------------------------------------------------
# Espesor
# --------------------------------------------------------------------------------------------------------------


def _largo_restante(linea: Sequence[Punto], segmento: int, t: float) -> float:
    """Lo que falta recorrer por la línea desde el punto `t` del segmento `segmento` hasta su extremo."""
    a, b = linea[segmento], linea[segmento + 1]
    resto = (1 - t) * math.hypot(b[0] - a[0], b[1] - a[1])
    return resto + sum(math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in pairwise(linea[segmento + 1 :]))


def distancia_de_drenaje(p: Punto, bajada: Bajada) -> float:
    """La distancia de drenaje de `p` a esa bajada: en línea recta, o por la línea de pendiente trazada hacia ella."""
    if bajada.linea is None or len(bajada.linea) < 2:
        return math.hypot(p[0] - bajada.x, p[1] - bajada.y)
    mejor = math.inf
    for i, (a, b) in enumerate(pairwise(bajada.linea)):
        d, t, _ = _distancia_a_segmento(p, a, b)
        mejor = min(mejor, d + _largo_restante(bajada.linea, i, t))
    fin = bajada.linea[-1]
    return mejor + math.hypot(fin[0] - bajada.x, fin[1] - bajada.y)


def bajada_que_drena(p: Punto, bajadas: Sequence[Bajada]) -> tuple[int, float]:
    """`(índice, distancia)` de la bajada que drena el punto: la de menor distancia de drenaje (en empate, la primera: determinista)."""
    mejor_i, mejor_d = 0, math.inf
    for i, b in enumerate(bajadas):
        d = distancia_de_drenaje(p, b)
        if d < mejor_d - 1e-12:
            mejor_i, mejor_d = i, d
    return mejor_i, mejor_d


def espesor_de_arenilla(
    p: Punto, bajadas: Sequence[Bajada], *, pendiente_pct: float, espesor_en_bajada_m: float = ESPESOR_EN_BAJADA_M, compensacion_m: float = 0.0
) -> float:
    """El espesor de la arenilla en un punto: el mínimo en la bajada que lo drena más la pendiente por la distancia, más la compensación."""
    if not bajadas:
        raise ValueError("Sin bajadas no hay espesor dinámico.")
    return espesor_en_bajada_m + pendiente_pct / 100 * bajada_que_drena(p, bajadas)[1] + compensacion_m


# --------------------------------------------------------------------------------------------------------------
# Integral
# --------------------------------------------------------------------------------------------------------------


def _muestrear(poligono: Poligono, h: float) -> list[Punto]:
    """Los centros de celda de la retícula de paso `h` (anclada en la esquina de la caja) que caen dentro del polígono, por barrido de filas."""
    xs_ext = [p[0] for p in poligono[0]]
    ys_ext = [p[1] for p in poligono[0]]
    x0, y0, y1 = min(xs_ext), min(ys_ext), max(ys_ext)
    centros: list[Punto] = []
    filas = math.ceil((y1 - y0) / h)
    for j in range(filas):
        y = y0 + (j + 0.5) * h
        cruces = _cruces(poligono, y)
        for a, b in zip(cruces[0::2], cruces[1::2], strict=False):
            i0 = math.ceil((a - x0) / h - 0.5)
            i1 = math.ceil((b - x0) / h - 0.5)  # exclusivo: el centro en el borde derecho no cuenta
            centros.extend((x0 + (i + 0.5) * h, y) for i in range(i0, i1))
    return centros


def _centros_de(poligono: Poligono, area: float, celdas: int) -> tuple[list[Punto], float]:
    """Los centros y el paso: se afina el paso hasta que caen al menos `_MINIMO_DE_CENTROS` (un polígono muy delgado)."""
    h = math.sqrt(area / celdas)
    for _ in range(12):
        centros = _muestrear(poligono, h)
        if len(centros) >= _MINIMO_DE_CENTROS:
            return centros, h
        h /= 2
    return centros, h


def _integrar_una_vez(
    poligonos: Sequence[tuple[Poligono, float, float]], bajadas: Sequence[Bajada], pendiente_pct: float, e0: float, celdas: int
) -> tuple[float, float, float, float, dict[str, dict[str, float]], dict[str, Punto], int]:
    """`(área, volumen, espesor máximo, paso, por bajada, lejano, muestras)` con una retícula de ≈`celdas` celdas por polígono. `poligonos`: `(polígono, área, compensación)`."""
    area_total = volumen = maximo = 0.0
    paso = 0.0
    muestras = 0
    por_bajada = {b.id: {"area_m2": 0.0, "distancia_maxima_m": 0.0, "espesor_maximo_m": 0.0} for b in bajadas}
    lejano: dict[str, Punto] = {}
    pendiente = pendiente_pct / 100
    for poligono, area, compensacion in poligonos:
        if area <= 1e-12:
            continue
        centros, h = _centros_de(poligono, area, celdas)
        paso = max(paso, h)
        if not centros:
            continue
        suma = 0.0
        por_celda = area / len(centros)  # el área de cada muestra: el área exacta repartida (la celda de borde no suma de más ni de menos)
        for c in centros:
            i, d = bajada_que_drena(c, bajadas)
            e = e0 + pendiente * d + compensacion
            suma += e
            maximo = max(maximo, e)
            g = por_bajada[bajadas[i].id]
            g["area_m2"] += por_celda
            if d > g["distancia_maxima_m"]:
                g["distancia_maxima_m"] = d
                lejano[bajadas[i].id] = c
            g["espesor_maximo_m"] = max(g["espesor_maximo_m"], e)
        area_total += area
        volumen += area * suma / len(centros)
        muestras += len(centros)
    return area_total, volumen, maximo, paso, por_bajada, lejano, muestras


def integrar_arenilla(
    poligonos: Sequence[tuple[Poligono, float]], bajadas: Sequence[Bajada], *, pendiente_pct: float, espesor_en_bajada_m: float = ESPESOR_EN_BAJADA_M
) -> ResultadoDeIntegral:
    """El volumen de arenilla: la integral del espesor sobre las piezas `(polígono, compensación en m)` de la zona. Ver el método en el módulo."""
    if not bajadas:
        raise ValueError("Sin bajadas no hay espesor dinámico.")
    piezas = [(p, area_de_poligono(p), c) for p, c in poligonos]
    gruesa = _integrar_una_vez(piezas, bajadas, pendiente_pct, espesor_en_bajada_m, CELDAS_GRUESAS)
    fina = _integrar_una_vez(piezas, bajadas, pendiente_pct, espesor_en_bajada_m, CELDAS_FINAS)
    area, volumen, maximo, paso, por_bajada, lejano, muestras = fina
    return ResultadoDeIntegral(
        area_m2=area,
        espesor_medio_m=volumen / area if area > 0 else 0.0,
        volumen_m3=volumen,
        espesor_maximo_m=maximo,
        muestras=muestras,
        celda_m=paso,
        error_estimado_m3=abs(fina[1] - gruesa[1]),
        por_bajada=por_bajada,
        lejano=lejano,
    )


# --------------------------------------------------------------------------------------------------------------
# Guías: líneas de pendiente e hilos de nivel
# --------------------------------------------------------------------------------------------------------------


def region_de_una_bajada(p: Punto, bajadas: Sequence[Bajada]) -> str:
    """El id de la bajada que drena el punto."""
    return bajadas[bajada_que_drena(p, bajadas)[0]].id


def guias_de_pendiente(
    poligonos: Sequence[Poligono], bajadas: Sequence[Bajada], resultado: ResultadoDeIntegral, *, pendiente_pct: float, espesor_en_bajada_m: float
) -> list[dict[str, Any]]:
    """Las guías del relleno en metros: una **línea de pendiente** por bajada (la trazada, o la generada del punto más lejano que drena a la bajada) y los **hilos
    de nivel** punteados (arcos de ``d = k × 1 m`` de las bajadas sin línea trazada, recortados a la zona y a la región de cada bajada)."""
    guias: list[dict[str, Any]] = []
    for b in bajadas:
        if b.linea is not None and len(b.linea) >= 2:
            guias.append({"tipo": "pendiente", "origen": "trazada", "bajada_id": b.id, "puntos": [list(p) for p in b.linea], "espesor_m": None})
        elif b.id in resultado.lejano:
            lejos = resultado.lejano[b.id]
            guias.append({"tipo": "pendiente", "origen": "generada", "bajada_id": b.id, "puntos": [list(lejos), [b.x, b.y]], "espesor_m": None})
    if pendiente_pct <= 0:
        return guias
    hilos = 0
    for i, b in enumerate(bajadas):
        if b.linea is not None and len(b.linea) >= 2:
            continue
        maxima = resultado.por_bajada.get(b.id, {}).get("distancia_maxima_m", 0.0)
        k = 1
        while k * PASO_DE_HILOS_M < maxima and hilos < _MAXIMO_DE_HILOS:
            radio = k * PASO_DE_HILOS_M
            espesor = espesor_en_bajada_m + pendiente_pct / 100 * radio
            arco: list[list[float]] = []
            n = int(360 / _PASO_ANGULAR_GRADOS)
            for s in range(n + 1):
                a = math.radians(s * _PASO_ANGULAR_GRADOS)
                q = (b.x + radio * math.cos(a), b.y + radio * math.sin(a))
                if punto_en_zona(q, poligonos) and bajada_que_drena(q, bajadas)[0] == i:
                    arco.append([q[0], q[1]])
                else:
                    if len(arco) >= 2:
                        guias.append({"tipo": "hilo", "origen": "generada", "bajada_id": b.id, "puntos": arco, "espesor_m": espesor})
                    arco = []
            if len(arco) >= 2:
                guias.append({"tipo": "hilo", "origen": "generada", "bajada_id": b.id, "puntos": arco, "espesor_m": espesor})
            hilos += 1
            k += 1
    return guias
