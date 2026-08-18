"""Cargador de materiales: validación de fila (§10.6 `CABECERAS_MATERIALES.xlsx`).

Spec §10.6 (contrato del archivo) · §10.1 (campos del catálogo de materiales) ·
§3.3 (la CLAVE manda) · §3.5 (IVA por material, override de la familia) ·
§10.5 (valuación: costo base vs costo de almacén).

Un `Material` es un `Insumo` con ``tipo = 'material'`` (§7.3): este cargador
no crea una entidad nueva, alimenta el catálogo de insumos.

Módulo puro (§12.11): recibe la fila ya leída como celdas y devuelve la
entidad validada o levanta :class:`ErrorEnFila`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from obractrl.domain.cargadores.cabeceras import MapaColumnas
from obractrl.domain.cargadores.reporte import ErrorEnFila
from obractrl.domain.shared.diccionario import TipoInsumo
from obractrl.domain.shared.normalizacion import (
    ValorNoConvertible,
    a_booleano,
    a_decimal,
    esta_vacio,
    texto_limpio,
)
from obractrl.domain.shared.valores import Clave

__all__ = ["FilaMaterial", "validar_material"]


@dataclass(frozen=True, slots=True)
class FilaMaterial:
    """Una fila válida del catálogo de materiales (§10.1, §10.6)."""

    clave: Clave
    descripcion: str
    unidad: str | None = None
    familia: str | None = None
    costo_base: Decimal | None = None
    """``None`` = **la columna no vino** en esta fila.

    Distinguirlo de cero importa: un archivo sin columna de costo no debe
    poner en cero el catálogo entero. Quien aplica la carga trata el ``None``
    como "conserva lo vigente" (§10.2, modo Actualizar).
    """

    costo_ultimo: Decimal | None = None
    costo_promedio: Decimal | None = None
    iva: bool | None = None
    """``None`` = no vino en el archivo. Nótese que en `insumo.iva_aplica`
    ``None`` significa "hereda de la familia" (§3.5): son dos ausencias
    distintas y por eso el aplicador nunca escribe ``None`` encima de un
    override existente."""

    tipo: TipoInsumo = TipoInsumo.MATERIAL

    fila: int = 0
    """Renglón del archivo. Viaja con el registro para que un pendiente pueda
    ligar al origen (§10.3) sin volver a abrir el libro."""

    @property
    def llave(self) -> str:
        """Identidad para dedup y diff: la CLAVE (§3.3, §10.2)."""
        return str(self.clave)


def _decimal_opcional(
    fila: Sequence[object], mapa: MapaColumnas, campo: str
) -> Decimal | None:
    celda = mapa.valor(fila, campo)
    if esta_vacio(celda):
        return None
    try:
        valor = a_decimal(celda, campo=campo)
    except ValorNoConvertible as exc:
        raise ErrorEnFila(str(exc), columna=campo, valor=celda) from exc
    if valor < 0:
        raise ErrorEnFila(
            f"{campo}: un costo de catálogo no puede ser negativo ({valor}).",
            columna=campo,
            valor=celda,
        )
    return valor


def validar_material(
    fila: Sequence[object], mapa: MapaColumnas, numero: int = 0
) -> FilaMaterial:
    """Fila del archivo → `FilaMaterial`, o :class:`ErrorEnFila`.

    La **clave** es obligatoria y se normaliza con `Clave` (§3.3): sin ella no
    hay con qué deduplicar ni contra qué cruzar, y una fila sin clave no se
    "arregla" adivinando por descripción.
    """
    celda_clave = mapa.valor(fila, "clave")
    if esta_vacio(celda_clave):
        raise ErrorEnFila(
            "clave: la fila no trae clave y la clave es única por catálogo (§3.3).",
            columna="clave",
        )
    try:
        clave = Clave(str(celda_clave))
    except ValueError as exc:
        raise ErrorEnFila(str(exc), columna="clave", valor=celda_clave) from exc

    descripcion = texto_limpio(mapa.valor(fila, "descripcion"))
    if not descripcion:
        raise ErrorEnFila(
            "descripcion: es obligatoria (§10.1).",
            columna="descripcion",
            valor=mapa.valor(fila, "descripcion"),
        )

    celda_iva = mapa.valor(fila, "iva")
    iva: bool | None = None
    if not esta_vacio(celda_iva):
        try:
            iva = a_booleano(celda_iva, campo="iva")
        except ValorNoConvertible as exc:
            raise ErrorEnFila(str(exc), columna="iva", valor=celda_iva) from exc

    return FilaMaterial(
        clave=clave,
        descripcion=descripcion,
        unidad=texto_limpio(mapa.valor(fila, "unidad")) or None,
        familia=texto_limpio(mapa.valor(fila, "familia")) or None,
        costo_base=_decimal_opcional(fila, mapa, "costo_base"),
        costo_ultimo=_decimal_opcional(fila, mapa, "costo_ultimo"),
        costo_promedio=_decimal_opcional(fila, mapa, "costo_promedio"),
        iva=iva,
        fila=numero,
    )
