"""La fachada por BANDAS de altura (F1, decisión del usuario del 2026-11-19): la franja «+3.00» se calcula con lo que el plano ya sabe.

El Excel de paramétricos arrastraba tres defectos: la cantidad de «+3.00» se copiaba de la partida de 3.00, un selector de texto
(«3.00»/«4.20») cambiaba cuál se cobraba sin medir nada y la franja de 255 m² se cobraba siempre. Aquí no hay selector: la fachada es la
**cara exterior** de los muros reales del plano y cada m² cae en **una sola banda** de altura:

- **banda baja**: de 0 al límite bajo (3.00 m);
- **banda media (la franja «+3.00»)**: del límite bajo al límite alto (4.20 m);
- **resto**: lo que pasa del límite alto.

La altura se mide desde el **suelo de la cara exterior**: el punto de nivel exterior de ese lado si existe (la «altura de la cara exterior»,
regla A4) y, si no, el arranque del muro (el piso terminado de su zona de losa más baja; 0 = piso terminado de PB). Una cara exterior sale
de las partes de altura del muro (cara A = izquierda del sentido de dibujo, B = derecha; solo las partes que suman) o de la zona de losa; los
vanos se descuentan en la banda donde caen. Los límites (3.00 y 4.20 m) son constantes de la decisión F1, no drivers.

Esto NO cobra nada y no pone precios: reparte metros cuadrados. Funciones puras, sin base de datos.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = [
    "LIMITE_ALTO_POR_DEFECTO_M",
    "LIMITE_BAJO_POR_DEFECTO_M",
    "Banda",
    "ErrorDeFachada",
    "FranjaExterior",
    "MetrosDeBanda",
    "ParteConCaras",
    "ReparticionPorBandas",
    "TramoConCaras",
    "VanoEnTramo",
    "bandas_de_fachada",
    "franjas_exteriores",
    "redondear",
    "repartir_en_bandas",
]

LIMITE_BAJO_POR_DEFECTO_M = Decimal("3.00")
LIMITE_ALTO_POR_DEFECTO_M = Decimal("4.20")
_CENTESIMA = Decimal("0.01")
_CERO = Decimal(0)


class ErrorDeFachada(ErrorDeCuantificacion):
    """Un dato de la fachada por bandas que no vale."""


@dataclass(frozen=True, slots=True)
class Banda:
    clave: str
    nombre: str
    desde_m: Decimal
    hasta_m: Decimal | None
    """`None`: sin tope (el resto)."""


def bandas_de_fachada(limite_bajo_m: Decimal = LIMITE_BAJO_POR_DEFECTO_M, limite_alto_m: Decimal = LIMITE_ALTO_POR_DEFECTO_M) -> tuple[Banda, ...]:
    """Las tres bandas (baja, media «+3.00» y resto) con los límites dados; el alto debe ser mayor que el bajo."""
    if not _CERO < limite_bajo_m < limite_alto_m:
        raise ErrorDeFachada(
            f"Los límites de las bandas de fachada deben cumplir 0 < baja < alta (hoy {limite_bajo_m:g} y {limite_alto_m:g} m)."
        )
    return (
        Banda("baja", f"0 a {limite_bajo_m:g} m", _CERO, limite_bajo_m),
        Banda("media", f"{limite_bajo_m:g} a {limite_alto_m:g} m (+{limite_bajo_m:g})", limite_bajo_m, limite_alto_m),
        Banda("resto", f"Más de {limite_alto_m:g} m", limite_alto_m, None),
    )


@dataclass(frozen=True, slots=True)
class ParteConCaras:
    """Una parte de altura del muro (sobre su arranque) con la cara de cada lado. ``suma`` falso: un cerramiento que no se aplana."""

    desde_m: Decimal
    hasta_m: Decimal
    cara_a: str | None
    cara_b: str | None
    suma: bool = True


@dataclass(frozen=True, slots=True)
class VanoEnTramo:
    """Un vano del tramo: ancho × piezas y su altura sobre el arranque del muro (el antepecho y el antepecho más el alto)."""

    ancho_m: Decimal
    desde_m: Decimal
    hasta_m: Decimal


@dataclass(frozen=True, slots=True)
class TramoConCaras:
    """Un tramo del muro (a lo largo) con lo necesario para saber cuánta cara exterior tiene y a qué altura."""

    largo_m: Decimal
    partes: tuple[ParteConCaras, ...]
    base_m: Decimal = _CERO
    """La cota del arranque del muro (piso terminado de su zona más baja; PB = 0)."""
    suelo_a_m: Decimal | None = None
    suelo_b_m: Decimal | None = None
    """La cota del punto de nivel exterior de cada lado (A, B), si lo hay: desde ahí se mide la altura de esa cara."""
    vanos: tuple[VanoEnTramo, ...] = ()


@dataclass(frozen=True, slots=True)
class FranjaExterior:
    """Un trozo de cara exterior: ``largo_m`` de ancho y de ``desde_m`` a ``hasta_m`` de altura sobre el suelo de esa cara."""

    largo_m: Decimal
    desde_m: Decimal
    hasta_m: Decimal
    vanos: tuple[tuple[Decimal, Decimal, Decimal], ...] = ()
    """(ancho, desde, hasta) de cada vano sobre el mismo suelo."""


def franjas_exteriores(tramo: TramoConCaras) -> list[FranjaExterior]:
    """Las franjas de cara exterior de un tramo: por cada lado y cada parte que suma con esa cara exterior, de su altura sobre el suelo de la
    cara. Con punto de nivel exterior, la parte que arranca en el muro baja (o sube) hasta ese suelo."""
    franjas: list[FranjaExterior] = []
    if tramo.largo_m <= 0:
        return franjas
    for lado in ("a", "b"):
        suelo = tramo.suelo_a_m if lado == "a" else tramo.suelo_b_m
        referencia = suelo if suelo is not None else tramo.base_m
        for p in tramo.partes:
            if not p.suma or (p.cara_a if lado == "a" else p.cara_b) != "exterior":
                continue
            if p.hasta_m <= p.desde_m:
                raise ErrorDeFachada("Una parte de altura va de un «desde» a un «hasta» mayor.")
            desde = tramo.base_m + p.desde_m
            if suelo is not None and p.desde_m == 0:
                desde = suelo  # la cara exterior arranca en el suelo exterior, esté más abajo o más arriba del piso del muro
            hasta = tramo.base_m + p.hasta_m
            if hasta <= desde:
                continue
            franjas.append(
                FranjaExterior(
                    largo_m=tramo.largo_m,
                    desde_m=desde - referencia,
                    hasta_m=hasta - referencia,
                    vanos=tuple(
                        (v.ancho_m, tramo.base_m + v.desde_m - referencia, tramo.base_m + v.hasta_m - referencia) for v in tramo.vanos
                    ),
                )
            )
    return franjas


def _solape(a0: Decimal, a1: Decimal, b0: Decimal, b1: Decimal | None) -> Decimal:
    """Cuánto se encima el intervalo [a0, a1] con [b0, b1] (b1 `None`: sin tope)."""
    techo = a1 if b1 is None else min(a1, b1)
    return max(techo - max(a0, b0), _CERO)


@dataclass(frozen=True, slots=True)
class MetrosDeBanda:
    banda: Banda
    bruto_m2: Decimal
    vanos_m2: Decimal
    neto_m2: Decimal


@dataclass(frozen=True, slots=True)
class ReparticionPorBandas:
    bandas: tuple[MetrosDeBanda, ...]
    bruto_m2: Decimal = field(default=_CERO)
    vanos_m2: Decimal = field(default=_CERO)
    neto_m2: Decimal = field(default=_CERO)


def repartir_en_bandas(franjas: Sequence[FranjaExterior], bandas: Sequence[Banda]) -> ReparticionPorBandas:
    """Reparte las franjas en las bandas: cada m² cae en UNA sola (las bandas no se encima ni dejan huecos, así que la suma de las bandas
    es el m² de las franjas). Los vanos se descuentan en la banda donde caen, solo dentro de la franja."""
    brutos = dict.fromkeys((b.clave for b in bandas), _CERO)
    vanos = dict.fromkeys((b.clave for b in bandas), _CERO)
    for f in franjas:
        for b in bandas:
            brutos[b.clave] += f.largo_m * _solape(f.desde_m, f.hasta_m, b.desde_m, b.hasta_m)
            for ancho, v0, v1 in f.vanos:
                dentro0, dentro1 = max(v0, f.desde_m), min(v1, f.hasta_m)
                if dentro1 > dentro0:
                    vanos[b.clave] += ancho * _solape(dentro0, dentro1, b.desde_m, b.hasta_m)
    filas = tuple(
        MetrosDeBanda(b, brutos[b.clave], vanos[b.clave], max(brutos[b.clave] - vanos[b.clave], _CERO)) for b in bandas
    )
    return ReparticionPorBandas(
        bandas=filas,
        bruto_m2=sum((x.bruto_m2 for x in filas), _CERO),
        vanos_m2=sum((x.vanos_m2 for x in filas), _CERO),
        neto_m2=sum((x.neto_m2 for x in filas), _CERO),
    )


def redondear(valor: Decimal) -> Decimal:
    """m² al centésimo, como se muestran."""
    return valor.quantize(_CENTESIMA, ROUND_HALF_UP)
