"""Armar el precio de un trabajo que no está en el catálogo (§11.2, §7.3).

El jefe de obra lo describió así: *"para una actividad fuera de catálogo el
residente dice qué cuadrilla va a utilizar, cuántas y el tiempo, también el
material a utilizar, y se crea el precio"*.

## Por qué no se reusa el APU

El APU (`domain.catalogos.apu`) explota un **concepto del catálogo** en sus
insumos, con rendimientos ya capturados. Aquí no hay concepto: eso es lo que
significa "fuera de catálogo". Lo que hay es un residente parado en la obra
diciendo con qué la va a hacer, y esto convierte eso en un precio.

La forma es la misma que un APU —mano de obra más materiales— y a propósito: el
día que ese trabajo se repita y alguien lo suba al catálogo, la cifra no debe
cambiar de método.

## Lo que NO hace

**No inventa un precio cuando falta un dato.** Una cuadrilla sin costo por
jornada capturado no vale cero: no se sabe cuánto vale. Devolverlo como cero
haría que el extra se autorizara por menos de lo que cuesta y que alguien lo
descubriera al pagarlo. Sale reportado en `sin_costo` y quien arma el precio
decide: capturar el costo, o cobrarlo de otro modo.

Módulo puro (§12.11): sin BD, sin reloj.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

__all__ = [
    "ErrorDePrecioArmado",
    "LineaDeCuadrilla",
    "LineaDeMaterial",
    "PrecioArmado",
    "armar_precio",
]

_CERO = Decimal(0)
ESCALA_DINERO = Decimal("0.01")


class ErrorDePrecioArmado(ValueError):
    """El precio no se puede armar con lo que se dio."""

    def __init__(self, mensaje: str, campo: str) -> None:
        super().__init__(mensaje)
        self.campo = campo


@dataclass(frozen=True, slots=True)
class LineaDeCuadrilla:
    """Qué cuadrilla, cuántas y cuántos días.

    `costo_jornada` es `None` cuando el catálogo todavía no lo trae: el renglón
    se acepta igual —el residente sí sabe a quién va a poner— y la línea sale
    reportada en vez de valer cero.
    """

    cuadrilla_id: str
    nombre: str
    cuadrillas: Decimal
    dias: Decimal
    costo_jornada: Decimal | None = None

    @property
    def jornadas(self) -> Decimal:
        """Una jornada es una cuadrilla trabajando un día.

        Misma definición que en la planeación (`domain.planeacion.cuadrillas`),
        y no por casualidad: si aquí significara otra cosa, el precio de un
        extra y el conteo de gente de la obra hablarían de unidades distintas.
        """
        return self.cuadrillas * self.dias

    @property
    def importe(self) -> Decimal:
        return _CERO if self.costo_jornada is None else self.jornadas * self.costo_jornada


@dataclass(frozen=True, slots=True)
class LineaDeMaterial:
    """Qué material y cuánto, al costo del catálogo."""

    insumo_id: str
    descripcion: str
    cantidad: Decimal
    costo: Decimal | None = None

    @property
    def importe(self) -> Decimal:
        return _CERO if self.costo is None else self.cantidad * self.costo


@dataclass(frozen=True, slots=True)
class PrecioArmado:
    """El precio y de qué está hecho."""

    mano_obra: Decimal
    materiales: Decimal
    total: Decimal
    precio_unitario: Decimal
    """Total entre la cantidad del trabajo. Es lo que se guarda en la actividad
    y con lo que después se estima."""

    jornadas: Decimal
    sin_costo: tuple[str, ...]
    """Lo que se incluyó sin saber cuánto vale.

    No es una advertencia cosmética: mientras haya algo aquí, el total está
    **por debajo** del costo real, y autorizar contra esa cifra es autorizar de
    menos. Quien arma el precio tiene que verlo antes de mandarlo.
    """

    @property
    def completo(self) -> bool:
        return not self.sin_costo


def armar_precio(
    *,
    cantidad: Decimal,
    cuadrillas: Sequence[LineaDeCuadrilla] = (),
    materiales: Sequence[LineaDeMaterial] = (),
) -> PrecioArmado:
    """Mano de obra + materiales → precio, y el unitario entre la cantidad.

    `cantidad` es la del trabajo —30 m² de muro—, no la de gente: el precio
    unitario es lo que se cobra por unidad de obra, que es como se estima
    después (§11.3 E). Sin ella no hay unitario que calcular, así que es un
    error y no un cero.
    """
    if cantidad <= 0:
        raise ErrorDePrecioArmado(
            f"La cantidad del trabajo debe ser mayor que cero para poder "
            f"repartir el precio entre ella: {cantidad}.",
            campo="cantidad",
        )

    for linea in cuadrillas:
        if linea.cuadrillas <= 0 or linea.dias <= 0:
            raise ErrorDePrecioArmado(
                f"«{linea.nombre}»: las cuadrillas y los días deben ser mayores "
                f"que cero.",
                campo="cuadrillas",
            )
    for material in materiales:
        if material.cantidad <= 0:
            raise ErrorDePrecioArmado(
                f"«{material.descripcion}»: la cantidad debe ser mayor que cero.",
                campo="materiales",
            )

    mano_obra = sum((linea.importe for linea in cuadrillas), _CERO)
    importe_materiales = sum((m.importe for m in materiales), _CERO)
    total = mano_obra + importe_materiales

    sin_costo = [
        linea.nombre for linea in cuadrillas if linea.costo_jornada is None
    ] + [m.descripcion for m in materiales if m.costo is None]

    return PrecioArmado(
        mano_obra=_redondear(mano_obra),
        materiales=_redondear(importe_materiales),
        total=_redondear(total),
        precio_unitario=_redondear(total / cantidad),
        jornadas=sum((linea.jornadas for linea in cuadrillas), _CERO),
        sin_costo=tuple(sin_costo),
    )


def _redondear(valor: Decimal) -> Decimal:
    """A centavos, media hacia arriba.

    Se redondea al final y no línea por línea: redondear cada renglón acumula
    el error y el total deja de ser la suma de lo que la pantalla enseña.
    """
    return valor.quantize(ESCALA_DINERO, rounding=ROUND_HALF_UP)
