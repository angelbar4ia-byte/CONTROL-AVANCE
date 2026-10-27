"""La cotización al cliente de lo que la obra modificó (cerebro MODELO.md §3a; D-531 a D-533,
D-546; pendiente B-123).

Dos modos de precio:

- **por diferencia** (algo específico, como un cambio de sanitarios): lo que entra menos lo que
  sale, en costo directo, entre el factor (0.7). «Lo que sale» y «lo que entra» son dos bloques con
  cantidades positivas y el sistema resta (D-546); restar costos y dividir da lo mismo que restar
  precios.
- **por m²** (una ampliación): los m² por el precio por m² (17,000 por defecto), que abarca de la
  cimentación a los equipamientos y **se confirma con el presupuesto**: si no coinciden, no se
  corrige solo, se guardan los dos.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

FACTOR_POR_DEFECTO = Decimal("0.7")
PRECIO_M2_POR_DEFECTO = Decimal("17000")
_CENTAVOS = Decimal("0.01")


class MetodoDePrecio(StrEnum):
    POR_DIFERENCIA = "por_diferencia"
    POR_M2 = "por_m2"


class ErrorDeCotizacion(ValueError):
    """No hay qué cotizar, o al modo de precio le falta un dato."""


class CotizacionYaRespondida(ValueError):
    """El cliente ya respondió esta cotización: la respuesta se registra una sola vez."""


@dataclass(frozen=True, slots=True)
class Modificado:
    """Lo que una actividad cambió en neto desde el prototipo (`delta` puede ser negativo)."""

    actividad_id: str
    descripcion: str
    concepto_clave: str | None
    delta: Decimal
    precio_unitario: Decimal


@dataclass(frozen=True, slots=True)
class Cotizacion:
    metodo: MetodoDePrecio
    factor: Decimal
    costo_entra: Decimal
    costo_sale: Decimal
    precio_por_diferencia: Decimal
    precio_por_m2: Decimal | None
    precio: Decimal
    lineas: tuple[dict[str, object], ...]


def cotizar(
    modificados: Sequence[Modificado],
    *,
    metodo: MetodoDePrecio,
    factor: Decimal = FACTOR_POR_DEFECTO,
    m2_ampliacion: Decimal | None = None,
    precio_m2: Decimal | None = None,
) -> Cotizacion:
    if not (Decimal(0) < factor <= Decimal(1)):
        raise ErrorDeCotizacion("El factor va entre cero y uno.")
    netos = [m for m in modificados if m.delta != 0]
    if not netos:
        raise ErrorDeCotizacion("La obra no tiene nada modificado que cotizar.")

    lineas: list[dict[str, object]] = []
    entra = sale = Decimal("0")
    for m in netos:
        costo = abs(m.delta) * m.precio_unitario
        bloque = "entra" if m.delta > 0 else "sale"
        if m.delta > 0:
            entra += costo
        else:
            sale += costo
        lineas.append(
            {
                "bloque": bloque,
                "actividad_id": m.actividad_id,
                "descripcion": m.descripcion,
                "concepto_clave": m.concepto_clave,
                "cantidad": str(abs(m.delta)),  # positiva: el bloque dice si entra o sale
                "precio_unitario": str(m.precio_unitario),
                "costo_directo": str(costo),
            }
        )
    por_diferencia = ((entra - sale) / factor).quantize(_CENTAVOS)

    por_m2: Decimal | None = None
    if metodo is MetodoDePrecio.POR_M2:
        if m2_ampliacion is None or m2_ampliacion <= 0:
            raise ErrorDeCotizacion("Una cotización por m² necesita los m² de la ampliación.")
        if precio_m2 is None or precio_m2 <= 0:
            raise ErrorDeCotizacion("Una cotización por m² necesita el precio por m².")
        por_m2 = (m2_ampliacion * precio_m2).quantize(_CENTAVOS)

    precio = por_m2 if metodo is MetodoDePrecio.POR_M2 and por_m2 is not None else por_diferencia
    return Cotizacion(metodo, factor, entra, sale, por_diferencia, por_m2, precio, tuple(lineas))
