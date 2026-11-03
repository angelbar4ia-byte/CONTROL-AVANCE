"""Semilla cuadrilla-rendimiento: validación de fila (D-616).

`SEMILLA-cuadrilla-rendimiento.csv` (265 filas, 7 columnas): por cada destajo,
la cuadrilla a la que se liga y su rendimiento teórico (D-386, D-406, D-439).
Ninguna columna se ignora.

Módulo puro (§12.11).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from obractrl.domain.cargadores.cabeceras import MapaColumnas
from obractrl.domain.cargadores.reporte import ErrorEnFila
from obractrl.domain.shared.normalizacion import (
    ValorNoConvertible,
    a_decimal,
    esta_vacio,
    texto_limpio,
)
from obractrl.domain.shared.valores import Clave

__all__ = ["FilaSemilla", "validar_semilla"]


@dataclass(frozen=True, slots=True)
class FilaSemilla:
    clave: Clave
    """Clave del destajo."""
    cuadrilla: Clave
    """Clave de la cuadrilla a la que se liga (MOCU-xxx)."""
    rendimiento_teorico: Decimal
    origen: str | None = None
    """«migrado», «completado · factor 1.085 de MOCU-023»..."""
    descripcion_ref: str | None = None
    unidad_ref: str | None = None
    costo_ref: Decimal | None = None
    fila: int = 0

    @property
    def llave(self) -> str:
        return str(self.clave)


def _clave(celda: object, columna: str) -> Clave:
    if esta_vacio(celda):
        raise ErrorEnFila(f"{columna}: es obligatoria (§3.3).", columna=columna)
    try:
        return Clave(str(celda))
    except ValueError as exc:
        raise ErrorEnFila(str(exc), columna=columna, valor=celda) from exc


def validar_semilla(
    fila: Sequence[object], mapa: MapaColumnas, numero: int = 0
) -> FilaSemilla:
    celda_rend = mapa.valor(fila, "rendimiento_teorico")
    try:
        rendimiento = a_decimal(celda_rend, campo="rendimiento_teorico")
    except ValorNoConvertible as exc:
        raise ErrorEnFila(
            str(exc), columna="rendimiento_teorico", valor=celda_rend
        ) from exc
    if rendimiento <= 0:
        raise ErrorEnFila(
            f"rendimiento_teorico: debe ser mayor que cero ({rendimiento}).",
            columna="rendimiento_teorico",
            valor=celda_rend,
        )

    costo_ref: Decimal | None = None
    celda_costo = mapa.valor(fila, "costo_ref")
    if not esta_vacio(celda_costo):
        try:
            costo_ref = a_decimal(celda_costo, campo="costo_ref")
        except ValorNoConvertible as exc:
            raise ErrorEnFila(str(exc), columna="costo_ref", valor=celda_costo) from exc

    return FilaSemilla(
        clave=_clave(mapa.valor(fila, "clave"), "clave"),
        cuadrilla=_clave(mapa.valor(fila, "cuadrilla"), "cuadrilla"),
        rendimiento_teorico=rendimiento,
        origen=texto_limpio(mapa.valor(fila, "origen_rendimiento")) or None,
        descripcion_ref=texto_limpio(mapa.valor(fila, "descripcion_ref")) or None,
        unidad_ref=texto_limpio(mapa.valor(fila, "unidad_ref")) or None,
        costo_ref=costo_ref,
        fila=numero,
    )
