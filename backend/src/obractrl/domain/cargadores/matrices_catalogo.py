"""Cargador del catálogo de matrices (conceptos): validación de fila (D-609, D-610).

`CATALOGO_DE_MATRICES.csv` es el catálogo de conceptos del sistema. Cada fila
es un concepto con su clave, descripción, unidad y costo. Las 11 columnas del
archivo se conservan (D-610):

- `matriz_desglosable`: `+` marca que el concepto tiene matriz desglosable (su
  composición está en `ANALISIS_DE_BASICOS_CONCEPTOS`). Vacío significa que no.
- `costo_base`, `costo_base_me`, `costo_unitario`: valores **independientes**
  de la composición (D-226, D-227, D-228). Se cargan tal cual.
- `unidad`: se carga tal cual (`pza`, `sal`, `m2`, `m`, `act`, `ser`, `m3`).

Los conceptos auxiliares (`AUX`) no entran aquí (D-609).

Módulo puro (§12.11): recibe la fila ya leída como celdas y devuelve la
entidad validada o levanta :class:`ErrorEnFila`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from obractrl.domain.cargadores.cabeceras import MapaColumnas
from obractrl.domain.cargadores.reporte import ErrorEnFila
from obractrl.domain.shared.normalizacion import (
    a_decimal,
    a_fecha,
    esta_vacio,
    texto_limpio,
)
from obractrl.domain.shared.valores import Clave

__all__ = ["FilaMatrizCatalogo", "validar_matriz_catalogo"]

_MARCA_DESGLOSABLE = "+"


@dataclass(frozen=True, slots=True)
class FilaMatrizCatalogo:
    """Una fila válida del catálogo de matrices (D-610: las 11 columnas)."""

    clave: Clave
    descripcion: str
    unidad: str
    matriz_desglosable: bool
    tipo: str | None = None
    familia: str | None = None
    subfamilia: str | None = None
    costo_base: Decimal | None = None
    costo_base_me: Decimal | None = None
    costo_unitario: Decimal | None = None
    fecha: date | None = None
    fila: int = 0

    @property
    def llave(self) -> str:
        """Identidad para dedup y diff dentro del archivo (§3.3): la clave."""
        return str(self.clave)


def _costo(celda: object, *, campo: str) -> Decimal | None:
    if esta_vacio(celda):
        return None
    return a_decimal(celda, campo=campo)


def validar_matriz_catalogo(
    fila: Sequence[object], mapa: MapaColumnas, numero: int = 0
) -> FilaMatrizCatalogo:
    """Fila del catálogo de matrices → `FilaMatrizCatalogo`, o :class:`ErrorEnFila`."""
    celda_clave = mapa.valor(fila, "clave")
    if esta_vacio(celda_clave):
        raise ErrorEnFila(
            "clave: un concepto sin clave no es identificable (§3.3).", columna="clave"
        )
    try:
        clave = Clave(str(celda_clave))
    except ValueError as exc:
        raise ErrorEnFila(str(exc), columna="clave", valor=celda_clave) from exc

    descripcion = texto_limpio(mapa.valor(fila, "descripcion"))
    if not descripcion:
        raise ErrorEnFila(
            "descripcion: un concepto sin descripción no es identificable (§10.1).",
            columna="descripcion",
        )

    unidad = texto_limpio(mapa.valor(fila, "unidad"))
    if not unidad:
        raise ErrorEnFila("unidad: el concepto no trae unidad.", columna="unidad")

    marca = texto_limpio(mapa.valor(fila, "matriz_desglosable"))
    if marca not in ("", _MARCA_DESGLOSABLE):
        raise ErrorEnFila(
            f"C: se esperaba «+» (matriz desglosable) o vacío, y llegó {marca!r}.",
            columna="matriz_desglosable",
            valor=marca,
        )

    fecha_celda = mapa.valor(fila, "fecha")
    return FilaMatrizCatalogo(
        clave=clave,
        descripcion=descripcion,
        unidad=unidad,
        matriz_desglosable=marca == _MARCA_DESGLOSABLE,
        tipo=texto_limpio(mapa.valor(fila, "tipo")) or None,
        familia=texto_limpio(mapa.valor(fila, "familia")) or None,
        subfamilia=texto_limpio(mapa.valor(fila, "subfamilia")) or None,
        costo_base=_costo(mapa.valor(fila, "costo_base"), campo="costo_base"),
        costo_base_me=_costo(mapa.valor(fila, "costo_base_me"), campo="costo_base_me"),
        costo_unitario=_costo(mapa.valor(fila, "costo_unitario"), campo="costo_unitario"),
        fecha=None if esta_vacio(fecha_celda) else a_fecha(fecha_celda, campo="fecha"),
        fila=numero,
    )
