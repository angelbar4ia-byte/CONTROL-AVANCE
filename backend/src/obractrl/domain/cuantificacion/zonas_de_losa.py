"""Zonas de losa (Fase 1: geometría y cotas, sin conceptos de losa): de qué losa cuelga un muro, qué altura toma y qué cara es
interior o exterior.

Hay desniveles entre plantas (entrepisos de 3.00 y de 4.20 m en la misma planta) y el plano no viene dividido en ellos. Las zonas
las define Control de obra con el **artefacto de la losa**, reciclando los polígonos del plano: un polígono con rol de «losa» de
una **zona** (nombre, cota del piso terminado, altura libre hasta el nivel bajo de la losa y espesor). Una zona puede tener varias
losas y una losa puede traer un espesor estructural propio (subzona). Las cotas son relativas al piso terminado de la planta baja
(= 0, editable). El relleno de pendientes es otro elemento y no se modela aquí; tampoco conceptos, trabes ni cimbra de la losa.

Reglas (``reglas_de_ubicacion`` del mockup y aclaraciones del usuario del 2026-11-16):

1. **Altura del muro** (por tramo): la altura explícita del trazo > la altura libre de la losa bajo la que cae > el driver
   ``altura_estandar`` de la obra. Un muro sin zona se comporta exactamente como hasta hoy.
2. **Partir**: un muro que cruza el límite entre zonas se parte en **tramos** (a lo largo), cada uno con su altura y sus partes de
   altura (la estructura de partes con cara A/B de la 4A: ``muro_ubicacion``).
3. **Enrase**: en el límite entre una zona baja (3.00) y una alta (4.20) cada cara lleva su altura; el cuerpo llega a la losa baja y el
   **enrase** sube de ahí a la losa alta. La losa más baja que el muro solo **sugiere** (regla 4 del mockup): lo que devuelve este
   módulo es una resolución para mostrar, nunca algo aplicado; aplicarlo es una acción aparte de la persona.
4. **Cara interior o exterior** (A = izquierda del sentido de dibujo, B = derecha; Y hacia abajo como en el plano): se comparan las
   losas de cada lado. Con losa de un solo lado, el otro es exterior; con losa a los dos lados, ambas son interiores y el enrase
   decide el resto. Un **punto de nivel exterior** cercano al lado sin losa lo confirma como exterior y fija el suelo de esa cara.

Funciones puras, sin base de datos. Las coordenadas llegan ya en **metros** (quien llama aplica la escala del plano).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from decimal import ROUND_HALF_UP, Decimal
from itertools import pairwise
from typing import Any

from obractrl.domain.cuantificacion.muro_ubicacion import sugerencia_por_losa
from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = [
    "ALTURA_LIBRE_MAXIMA_M",
    "RADIO_DE_PUNTO_DE_NIVEL_M",
    "ErrorDeZonaDeLosa",
    "LadoDeMuro",
    "LosaEnPlano",
    "PuntoDeNivelExterior",
    "ResolucionDeMuro",
    "TramoDeMuro",
    "ZonaDeLosa",
    "elegir_altura",
    "resolver_muro",
    "validar_zona",
]

Punto = tuple[float, float]
Anillo = tuple[Punto, ...]
Poligono = tuple[Anillo, ...]
"""Un polígono: el primer anillo es el exterior y los demás son huecos (el hueco de una escalera, p. ej.)."""

ALTURA_LIBRE_MAXIMA_M = Decimal("30")
ESPESOR_MAXIMO_M = Decimal("3")
RADIO_DE_PUNTO_DE_NIVEL_M = 5.0
"""Un punto de nivel exterior vale para el lado sin losa de un muro si está a esta distancia o menos (m)."""
SEPARACION_MINIMA_M = 0.08
"""Cuánto se separa del eje del muro el punto con el que se mira de qué losa cuelga cada lado (más la mitad del grosor)."""
_MILIMETRO = Decimal("0.001")
_EPS = 1e-9


class ErrorDeZonaDeLosa(ErrorDeCuantificacion):
    """Un dato de una zona de losa o de un punto de nivel que no vale."""


@dataclass(frozen=True)
class ZonaDeLosa:
    id: str
    nombre: str
    altura_libre_m: Decimal
    espesor_m: Decimal
    cota_piso_m: Decimal = Decimal(0)
    nivel: str | None = None

    @property
    def cota_inferior_m(self) -> Decimal:
        """Cota del nivel bajo de la losa (piso terminado + altura libre), relativa al piso terminado de PB = 0."""
        return self.cota_piso_m + self.altura_libre_m

    @property
    def cota_superior_m(self) -> Decimal:
        return self.cota_inferior_m + self.espesor_m


@dataclass(frozen=True)
class LosaEnPlano:
    """Un polígono del plano con rol de losa de una zona. ``espesor_m`` solo si es una subzona con espesor estructural propio."""

    id: str
    zona_id: str
    poligonos: tuple[Poligono, ...]
    espesor_m: Decimal | None = None


@dataclass(frozen=True)
class PuntoDeNivelExterior:
    id: str
    x: float
    y: float
    cota_m: Decimal
    rotulo: str | None = None


@dataclass(frozen=True)
class LadoDeMuro:
    """Lo que hay a un lado de un tramo de muro: de qué losa cuelga o por qué es exterior."""

    lado: str
    cara: str | None
    origen: str
    zona_id: str | None = None
    zona: str | None = None
    losa_id: str | None = None
    espesor_m: Decimal | None = None
    cota_inferior_m: Decimal | None = None
    cota_superior_m: Decimal | None = None
    altura_m: Decimal | None = None
    punto_de_nivel_id: str | None = None
    nivel_exterior_m: Decimal | None = None
    rotulo_del_punto: str | None = None


@dataclass(frozen=True)
class TramoDeMuro:
    desde_m: Decimal
    hasta_m: Decimal
    longitud_m: Decimal
    lado_a: LadoDeMuro
    lado_b: LadoDeMuro
    altura_m: Decimal
    origen_de_altura: str
    enrase: dict[str, Decimal] | None
    partes: tuple[dict[str, Any], ...]
    sugerencias: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class ResolucionDeMuro:
    tramos: tuple[TramoDeMuro, ...]
    parte_el_muro: bool
    con_zona: bool
    advertencias: tuple[str, ...] = field(default_factory=tuple)
    aplicada: bool = False
    """Siempre falso: la resolución solo muestra lo que se sugiere; no cambia ningún muro."""


# ── Validación de una zona ─────────────────────────────────────────────────────────────────────────────


def _decimal(valor: Any, que: str) -> Decimal:
    try:
        d = Decimal(str(valor))
    except Exception as e:  # noqa: BLE001 - cualquier valor no numérico es el mismo error para quien captura
        raise ErrorDeZonaDeLosa(f"{que}: «{valor}» no es un número.") from e
    if not d.is_finite():
        raise ErrorDeZonaDeLosa(f"{que}: «{valor}» no es un número.")
    return d


def validar_zona(
    *,
    nombre: str,
    altura_libre_m: Any,
    espesor_m: Any,
    cota_piso_m: Any = 0,
    nivel: str | None = None,
) -> dict[str, Any]:
    """Revisa y normaliza los datos de una zona de losa (cotas en m, relativas al piso terminado de PB = 0)."""
    limpio = (nombre or "").strip()
    if not 1 <= len(limpio) <= 60:
        raise ErrorDeZonaDeLosa("El nombre de la zona va de 1 a 60 caracteres.")
    altura = _decimal(altura_libre_m, "La altura libre")
    if not 0 < altura <= ALTURA_LIBRE_MAXIMA_M:
        raise ErrorDeZonaDeLosa(
            f"La altura libre (del piso terminado al nivel bajo de la losa) va de más de 0 a {ALTURA_LIBRE_MAXIMA_M} m."
        )
    espesor = _decimal(espesor_m, "El espesor de la losa")
    if not 0 < espesor <= ESPESOR_MAXIMO_M:
        raise ErrorDeZonaDeLosa(
            f"El espesor de la losa va de más de 0 a {ESPESOR_MAXIMO_M} m."
        )
    cota = _decimal(cota_piso_m, "La cota del piso")
    if not -30 <= cota <= 100:
        raise ErrorDeZonaDeLosa(
            "La cota del piso terminado va de -30 a 100 m (relativa al piso terminado de PB = 0)."
        )
    nivel_limpio = (nivel or "").strip() or None
    if nivel_limpio is not None and len(nivel_limpio) > 40:
        raise ErrorDeZonaDeLosa("El nivel va de 1 a 40 caracteres.")
    return {
        "nombre": limpio,
        "nivel": nivel_limpio,
        "cota_piso_m": cota.quantize(_MILIMETRO, ROUND_HALF_UP),
        "altura_libre_m": altura.quantize(_MILIMETRO, ROUND_HALF_UP),
        "espesor_m": espesor.quantize(_MILIMETRO, ROUND_HALF_UP),
    }


def elegir_altura(
    *, explicita_m: Decimal | None, de_zona_m: Decimal | None, estandar_m: Decimal
) -> tuple[Decimal, str]:
    """Regla 1: la altura explícita del trazo, si no la de la zona de losa, si no el driver ``altura_estandar``. Devuelve la altura y
    de dónde salió: ``trazo``, ``zona`` o ``driver``."""
    if explicita_m is not None:
        return explicita_m, "trazo"
    if de_zona_m is not None:
        return de_zona_m, "zona"
    return estandar_m, "driver"


# ── Geometría plana ────────────────────────────────────────────────────────────────────────────────────


def _en_anillo(p: Punto, anillo: Anillo) -> bool:
    x, y = p
    dentro = False
    n = len(anillo)
    j = n - 1
    for i in range(n):
        xi, yi = anillo[i]
        xj, yj = anillo[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            dentro = not dentro
        j = i
    return dentro


def _en_poligono(p: Punto, poligono: Poligono) -> bool:
    if not poligono or not _en_anillo(p, poligono[0]):
        return False
    return not any(_en_anillo(p, hueco) for hueco in poligono[1:])


def _cruces(a: Punto, b: Punto, poligonos: Sequence[Poligono]) -> list[float]:
    """Los parámetros t (0 a 1) donde el segmento a→b cruza un borde de algún polígono."""
    ts: list[float] = []
    rx, ry = b[0] - a[0], b[1] - a[1]
    for poligono in poligonos:
        for anillo in poligono:
            n = len(anillo)
            for i in range(n):
                p, q = anillo[i], anillo[(i + 1) % n]
                sx, sy = q[0] - p[0], q[1] - p[1]
                den = rx * sy - ry * sx
                if abs(den) < _EPS:
                    continue  # paralelos (o sobre el mismo borde): el lado se mira con los puntos de muestra, no con el cruce
                t = ((p[0] - a[0]) * sy - (p[1] - a[1]) * sx) / den
                u = ((p[0] - a[0]) * ry - (p[1] - a[1]) * rx) / den
                if _EPS < t < 1 - _EPS and -_EPS <= u <= 1 + _EPS:
                    ts.append(t)
    return ts


def _mm(valor: float) -> Decimal:
    return Decimal(str(round(valor, 6))).quantize(_MILIMETRO, ROUND_HALF_UP)


# ── Qué hay a cada lado ────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Cubierta:
    losa: LosaEnPlano
    zona: ZonaDeLosa
    espesor_m: Decimal


def _cubierta_en(
    p: Punto, losas: Sequence[LosaEnPlano], zonas: dict[str, ZonaDeLosa], avisos: set[str]
) -> _Cubierta | None:
    """La losa bajo la que cae un punto. Con losas encimadas de zonas distintas gana la de nivel bajo más bajo (la que está más
    cerca del piso) y se avisa."""
    halladas = [
        _Cubierta(
            losa=lo,
            zona=zonas[lo.zona_id],
            espesor_m=lo.espesor_m
            if lo.espesor_m is not None
            else zonas[lo.zona_id].espesor_m,
        )
        for lo in losas
        if lo.zona_id in zonas and any(_en_poligono(p, poli) for poli in lo.poligonos)
    ]
    if not halladas:
        return None
    halladas.sort(
        key=lambda c: (c.zona.cota_inferior_m, c.zona.nombre.lower(), c.losa.id)
    )
    if len({c.zona.id for c in halladas}) > 1:
        nombres = ", ".join(sorted({c.zona.nombre for c in halladas}))
        avisos.add(
            f"Hay losas de zonas distintas encimadas ({nombres}): se tomó la de nivel más bajo."
        )
    return halladas[0]


def _punto_cercano(
    p: Punto, puntos: Sequence[PuntoDeNivelExterior]
) -> PuntoDeNivelExterior | None:
    mejor: tuple[float, str, PuntoDeNivelExterior] | None = None
    for q in puntos:
        d = math.hypot(q.x - p[0], q.y - p[1])
        if d <= RADIO_DE_PUNTO_DE_NIVEL_M and (
            mejor is None or (d, q.id) < (mejor[0], mejor[1])
        ):
            mejor = (d, q.id, q)
    return mejor[2] if mejor else None


def _lados(
    lado_a: _Cubierta | None,
    lado_b: _Cubierta | None,
    muestra_a: Punto,
    muestra_b: Punto,
    puntos: Sequence[PuntoDeNivelExterior],
) -> tuple[LadoDeMuro, LadoDeMuro]:
    """Regla 4: cara interior o exterior de cada lado y la altura de cada cara."""

    def con_losa(nombre: str, c: _Cubierta) -> LadoDeMuro:
        return LadoDeMuro(
            lado=nombre,
            cara="interior",
            origen="losa",
            zona_id=c.zona.id,
            zona=c.zona.nombre,
            losa_id=c.losa.id,
            espesor_m=c.espesor_m,
            cota_inferior_m=c.zona.cota_inferior_m,
            cota_superior_m=c.zona.cota_inferior_m + c.espesor_m,
            altura_m=c.zona.altura_libre_m,
        )

    def sin_losa(nombre: str, muestra: Punto, otra: _Cubierta | None) -> LadoDeMuro:
        punto = _punto_cercano(muestra, puntos)
        if otra is None and punto is None:
            return LadoDeMuro(lado=nombre, cara=None, origen="sin_zona")
        if punto is not None:
            altura = (
                (otra.zona.cota_inferior_m - punto.cota_m) if otra is not None else None
            )
            return LadoDeMuro(
                lado=nombre,
                cara="exterior",
                origen="punto_de_nivel",
                punto_de_nivel_id=punto.id,
                nivel_exterior_m=punto.cota_m,
                rotulo_del_punto=punto.rotulo,
                altura_m=altura.quantize(_MILIMETRO)
                if altura is not None and altura > 0
                else (otra.zona.altura_libre_m if otra else None),
            )
        assert otra is not None
        return LadoDeMuro(
            lado=nombre,
            cara="exterior",
            origen="sin_losa",
            altura_m=otra.zona.altura_libre_m,
        )

    a = con_losa("A", lado_a) if lado_a is not None else sin_losa("A", muestra_a, lado_b)
    b = con_losa("B", lado_b) if lado_b is not None else sin_losa("B", muestra_b, lado_a)
    return a, b


def _tramo(
    desde: float,
    hasta: float,
    a: LadoDeMuro,
    b: LadoDeMuro,
    *,
    altura_explicita_m: Decimal | None,
    altura_estandar_m: Decimal,
    cotas_de_piso: dict[str, Decimal],
) -> TramoDeMuro:
    cubiertos = [x for x in (a, b) if x.origen == "losa"]
    enrase: dict[str, Decimal] | None = None
    partes: list[dict[str, Any]] = []
    sugerencias: list[dict[str, Any]] = []
    if not cubiertos:
        altura, origen = elegir_altura(
            explicita_m=altura_explicita_m, de_zona_m=None, estandar_m=altura_estandar_m
        )
    else:
        base = min(cotas_de_piso[x.zona_id or ""] for x in cubiertos)
        inferiores = sorted(
            x.cota_inferior_m for x in cubiertos if x.cota_inferior_m is not None
        )
        de_zona = inferiores[-1] - base
        altura, origen = elegir_altura(
            explicita_m=altura_explicita_m,
            de_zona_m=de_zona,
            estandar_m=altura_estandar_m,
        )
        if origen == "zona":
            if inferiores[0] != inferiores[-1]:
                bajo = inferiores[0] - base
                enrase = {"desde_m": bajo, "hasta_m": altura}
                partes = [
                    {
                        "nombre": "Cuerpo",
                        "desde_m": Decimal(0),
                        "hasta_m": bajo,
                        "suma": True,
                        "rol": "cuerpo",
                        "cara_a": a.cara,
                        "cara_b": b.cara,
                    },
                    {
                        "nombre": "Enrase",
                        "desde_m": bajo,
                        "hasta_m": altura,
                        "suma": True,
                        "rol": "enrase",
                        "cara_a": None,
                        "cara_b": None,
                    },
                ]
                # Regla 4 del mockup: la losa más baja que el muro SUGIERE las partes de arriba exteriores; no se aplica.
                sugerencias = sugerencia_por_losa(
                    [
                        {
                            k: (str(v) if isinstance(v, Decimal) else v)
                            for k, v in p.items()
                        }
                        for p in partes
                    ],
                    bajo,
                )
                for s in sugerencias:
                    partes[s["indice"]]["cara_a"], partes[s["indice"]]["cara_b"] = (
                        s["cara_a"],
                        s["cara_b"],
                    )
            else:
                partes = [
                    {
                        "nombre": "Cuerpo",
                        "desde_m": Decimal(0),
                        "hasta_m": altura,
                        "suma": True,
                        "rol": "cuerpo",
                        "cara_a": a.cara,
                        "cara_b": b.cara,
                    }
                ]
    return TramoDeMuro(
        desde_m=_mm(desde),
        hasta_m=_mm(hasta),
        longitud_m=_mm(hasta - desde),
        lado_a=a,
        lado_b=b,
        altura_m=altura.quantize(_MILIMETRO, ROUND_HALF_UP),
        origen_de_altura=origen,
        enrase=enrase,
        partes=tuple(partes),
        sugerencias=tuple(sugerencias),
    )


def _firma(t: TramoDeMuro) -> tuple[Any, ...]:
    def lado(x: LadoDeMuro) -> tuple[Any, ...]:
        return (x.zona_id, x.cara, x.origen, x.punto_de_nivel_id)

    return (lado(t.lado_a), lado(t.lado_b), t.altura_m, t.origen_de_altura)


def resolver_muro(
    linea: Sequence[Punto],
    *,
    zonas: Sequence[ZonaDeLosa],
    losas: Sequence[LosaEnPlano],
    puntos_de_nivel: Sequence[PuntoDeNivelExterior] = (),
    altura_explicita_m: Decimal | None = None,
    altura_estandar_m: Decimal,
    grosor_m: float | None = None,
) -> ResolucionDeMuro:
    """Parte el muro (una polilínea en metros) en tramos por los límites de las losas y resuelve cada uno: de qué zona cuelga cada
    lado, su cara interior o exterior, su altura (y de dónde salió), el enrase y las partes de altura.

    Sin ninguna zona alcanzada, devuelve un solo tramo ``origen_de_altura`` ``trazo`` o ``driver`` sin caras: el muro se comporta
    como hasta hoy. No cambia nada: ``aplicada`` es siempre falso.
    """
    if len(linea) < 2:
        raise ErrorDeZonaDeLosa("El muro necesita al menos dos puntos.")
    por_id = {z.id: z for z in zonas}
    separacion = max(SEPARACION_MINIMA_M, (grosor_m or 0.0) / 2 + 0.05)
    cotas_de_piso = {z.id: z.cota_piso_m for z in zonas}
    poligonos = [poli for lo in losas if lo.zona_id in por_id for poli in lo.poligonos]
    avisos: set[str] = set()

    sin_firma: list[tuple[float, float, TramoDeMuro]] = []
    recorrido = 0.0
    for i in range(len(linea) - 1):
        a, b = linea[i], linea[i + 1]
        largo = math.hypot(b[0] - a[0], b[1] - a[1])
        if largo < _EPS:
            continue
        ts = sorted({0.0, 1.0, *_cruces(a, b, poligonos)})
        ux, uy = (b[0] - a[0]) / largo, (b[1] - a[1]) / largo
        izq = (
            uy,
            -ux,
        )  # normal izquierda con Y hacia abajo: la cara A (como `normalIzquierda` del visor)
        for t0, t1 in pairwise(ts):
            if (t1 - t0) * largo < 1e-6:
                continue
            tm = (t0 + t1) / 2
            m = (a[0] + (b[0] - a[0]) * tm, a[1] + (b[1] - a[1]) * tm)
            muestra_a = (m[0] + izq[0] * separacion, m[1] + izq[1] * separacion)
            muestra_b = (m[0] - izq[0] * separacion, m[1] - izq[1] * separacion)
            cub_a = _cubierta_en(muestra_a, losas, por_id, avisos)
            cub_b = _cubierta_en(muestra_b, losas, por_id, avisos)
            lado_a, lado_b = _lados(cub_a, cub_b, muestra_a, muestra_b, puntos_de_nivel)
            desde, hasta = recorrido + t0 * largo, recorrido + t1 * largo
            sin_firma.append(
                (
                    desde,
                    hasta,
                    _tramo(
                        desde,
                        hasta,
                        lado_a,
                        lado_b,
                        altura_explicita_m=altura_explicita_m,
                        altura_estandar_m=altura_estandar_m,
                        cotas_de_piso=cotas_de_piso,
                    ),
                )
            )
        recorrido += largo
    if not sin_firma:
        raise ErrorDeZonaDeLosa("El muro no tiene largo.")

    # Los tramos contiguos que cuelgan de lo mismo son uno solo (un vértice no parte el muro).
    unidos: list[tuple[float, float, TramoDeMuro]] = []
    for desde, hasta, t in sin_firma:
        if unidos and _firma(unidos[-1][2]) == _firma(t):
            d0, _, previo = unidos[-1]
            unidos[-1] = (
                d0,
                hasta,
                replace(
                    previo,
                    desde_m=_mm(d0),
                    hasta_m=_mm(hasta),
                    longitud_m=_mm(hasta - d0),
                ),
            )
        else:
            unidos.append((desde, hasta, t))
    tramos = tuple(t for _, _, t in unidos)

    con_zona = any(t.lado_a.origen == "losa" or t.lado_b.origen == "losa" for t in tramos)
    # Se parte solo si lo que cambia a lo largo es lo que se mide: la altura o sus partes (no basta con cambiar de zona).
    parte = (
        len(
            {
                (t.altura_m, tuple((p["desde_m"], p["hasta_m"]) for p in t.partes))
                for t in tramos
            }
        )
        > 1
    )
    advertencias = sorted(avisos)
    if altura_explicita_m is not None and con_zona:
        advertencias.append(
            "El muro trae su altura: manda sobre la de la zona de losa (la zona solo informa las caras)."
        )
    return ResolucionDeMuro(
        tramos=tramos,
        parte_el_muro=parte,
        con_zona=con_zona,
        advertencias=tuple(advertencias),
    )
