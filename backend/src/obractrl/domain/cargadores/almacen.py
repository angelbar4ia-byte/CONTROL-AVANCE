"""Cargador de movimientos de almacén (§10.6 `IMPORTAADOR_ALMACEN.xlsx`).

Spec §10.6 (contrato del archivo, hoja `Consulta`) · §10.5 (motivos con signo,
valuación y C/Último) · §3.5 (IVA) · §3.3 (la CLAVE manda) · §10.3 (bandeja).

Lo que el §10.6 fija y este módulo respeta al pie de la letra:

- **El signo ya viene en el archivo** (`Efecto Qty` / `Efecto Costo`); el
  motivo solo clasifica el bucket de KPI. Aquí no se recalcula ningún signo.
- **Los costos vienen sin IVA** y el 16% se agrega según `Clase` — de ahí
  :func:`importe_con_iva`, que recibe la tasa en vez de clavarla: es
  configurable y se lee de BD (§8.7).
- **El costo del cruce es `C/Último`**; `C/Promedio` solo valida.
- La obra es **`Ubicacion + Lote`**, que es la misma composición
  ``CLUSTER + LOTE`` con que el §10.1 define la clave de obra.

Módulo puro (§12.11).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from obractrl.domain.cargadores.cabeceras import MapaColumnas
from obractrl.domain.cargadores.reporte import ErrorEnFila
from obractrl.domain.shared.normalizacion import (
    ValorNoConvertible,
    a_decimal,
    a_fecha,
    esta_vacio,
    texto_limpio,
)
from obractrl.domain.shared.valores import Clave

__all__ = [
    "FilaMovimiento",
    "clave_de_obra",
    "concepto_de_referencia",
    "importe_con_iva",
    "validar_movimiento",
]

_CUATRO_DEC = Decimal("0.0001")

_CLAVE_EN_REFERENCIA = re.compile(r"\b([A-Z]{2,4}-[A-Z0-9][A-Z0-9._/-]*)")
"""Clave de concepto embebida en la columna `Referencia`.

El §10.6 la describe como ``No.Parte:EST-… + OP``: la clave viene incrustada
en un texto que además trae la orden de producción. El patrón busca la forma
``PREFIJO-…`` que el §10.1 fija para las claves (`EST`, `SUB`, `SER`, `MOA`),
sin exigir un prefijo concreto —los prefijos son semilla editable (§8.7)—.
Que la clave exista es cosa del catálogo, no de esta expresión.
"""


def concepto_de_referencia(referencia: object) -> str | None:
    """Clave de concepto embebida en `Referencia`, o ``None`` (§10.6).

    >>> concepto_de_referencia("No.Parte:EST-0123 OP-99")
    'EST-0123'
    >>> concepto_de_referencia("sin liga")
    """
    texto = texto_limpio(referencia).upper()
    if not texto:
        return None
    hallazgo = _CLAVE_EN_REFERENCIA.search(texto)
    return hallazgo.group(1) if hallazgo else None


def clave_de_obra(ubicacion: object, lote: object) -> Clave:
    """``Ubicacion + Lote`` → clave de obra (§10.6, §10.1 ``CLUSTER + LOTE``).

    `Clave` normaliza a mayúsculas y colapsa espacios, así que ``fresno`` +
    ``12`` y ``FRESNO`` + ``  12 `` dan la misma clave — que es justo lo que
    el §3.3 exige para que el cruce no dependa de cómo se escribió.
    """
    partes = [texto_limpio(ubicacion), texto_limpio(lote)]
    unida = " ".join(p for p in partes if p)
    if not unida:
        raise ErrorEnFila(
            "ubicacion/lote: sin Ubicacion ni Lote no se puede identificar la "
            "obra (§10.6).",
            columna="ubicacion",
        )
    return Clave(unida)


def importe_con_iva(costo: Decimal, *, aplica_iva: bool, tasa: Decimal) -> Decimal:
    """Importe con IVA a partir del costo sin IVA del archivo (§10.6, §3.5).

    La **tasa** llega como parámetro a propósito: el 16% es configurable y se
    lee de BD (§8.7, "nunca se clava un configurable como constante"). El
    signo del costo se conserva —viene del archivo (§10.5)— porque aplicar un
    factor positivo no lo cambia.
    """
    if not aplica_iva:
        return costo.quantize(_CUATRO_DEC, rounding=ROUND_HALF_UP)
    return (costo * (Decimal(1) + tasa)).quantize(_CUATRO_DEC, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class FilaMovimiento:
    """Un movimiento de almacén válido (§7.7 `SalidaAlmacen`, §10.5, §10.6)."""

    clave_insumo: Clave
    clave_obra: Clave
    fecha: date
    motivo: str
    cantidad: Decimal
    """`Efecto Qty` — **ya trae signo** (§10.5)."""

    costo: Decimal = Decimal(0)
    """`Efecto Costo` — ya trae signo y viene **sin IVA** (§10.6)."""

    descripcion: str | None = None
    familia: str | None = None
    """Columna `Clase`: es la que decide familia e IVA (§10.6, §3.5)."""

    contratista: str | None = None
    costo_ultimo: Decimal | None = None
    """`C/Último` — el costo con que se cruza consumo vs presupuesto (§10.5)."""

    costo_promedio: Decimal | None = None
    """`C/Promedio` — solo valida (§10.6); no entra al cruce."""

    clave_concepto: str | None = None
    almacen: str | None = None
    usuario: str | None = None
    fila: int = 0

    @property
    def llave(self) -> str:
        """Identidad de la fila dentro del lote.

        El §10.6 **no** define una clave de renglón para este archivo —es un
        libro de movimientos, no un catálogo—, así que la identidad se compone
        de lo que hace único a un movimiento. Sirve para deduplicar dentro del
        archivo; la idempotencia entre cargas es a nivel de lote, por hash
        (§10.8).
        """
        return "|".join(
            [
                str(self.clave_obra),
                str(self.clave_insumo),
                str(self.fecha),
                self.motivo,
                f"{self.cantidad:f}",
                f"{self.costo:f}",
                self.clave_concepto or "",
                self.almacen or "",
            ]
        )


def _decimal_opcional(celda: object, *, columna: str) -> Decimal | None:
    if esta_vacio(celda):
        return None
    try:
        return a_decimal(celda, campo=columna)
    except ValorNoConvertible as exc:
        raise ErrorEnFila(str(exc), columna=columna, valor=celda) from exc


def validar_movimiento(
    fila: Sequence[object], mapa: MapaColumnas, numero: int = 0
) -> FilaMovimiento:
    """Fila del archivo → `FilaMovimiento`, o :class:`ErrorEnFila`.

    Valida forma, no existencia: si el `# Parte` no está en el catálogo o el
    `Motivo` no está catalogado, eso es una excepción de **cruce** y va a la
    bandeja (§10.3, §10.5), no un error de fila — el caso de uso es quien
    tiene los catálogos para saberlo.
    """
    celda_clave = mapa.valor(fila, "clave")
    if esta_vacio(celda_clave):
        raise ErrorEnFila(
            "clave: sin `# Parte` no hay material con qué cruzar (§10.6, §3.3).",
            columna="clave",
        )
    try:
        clave_insumo = Clave(str(celda_clave))
    except ValueError as exc:
        raise ErrorEnFila(str(exc), columna="clave", valor=celda_clave) from exc

    clave_obra = clave_de_obra(mapa.valor(fila, "ubicacion"), mapa.valor(fila, "lote"))

    celda_fecha = mapa.valor(fila, "fecha")
    try:
        fecha = a_fecha(celda_fecha, campo="fecha")
    except ValorNoConvertible as exc:
        raise ErrorEnFila(str(exc), columna="fecha", valor=celda_fecha) from exc

    motivo = texto_limpio(mapa.valor(fila, "motivo"))
    if not motivo:
        raise ErrorEnFila(
            "motivo: es el que clasifica el bucket de KPI; sin él el movimiento "
            "no es interpretable (§10.5).",
            columna="motivo",
        )

    cantidad = _decimal_opcional(mapa.valor(fila, "cantidad"), columna="cantidad")
    if cantidad is None:
        raise ErrorEnFila(
            "cantidad: `Efecto Qty` es obligatoria (§10.6).", columna="cantidad"
        )
    if cantidad == 0:
        # Misma regla que `domain.materiales.reglas.validar_signo_salida`: no
        # hay movimiento de almacén sin cantidad.
        raise ErrorEnFila(
            "cantidad: un movimiento de almacén no puede tener cantidad cero "
            "(§10.5).",
            columna="cantidad",
            valor=cantidad,
        )

    return FilaMovimiento(
        clave_insumo=clave_insumo,
        clave_obra=clave_obra,
        fecha=fecha,
        motivo=motivo,
        cantidad=cantidad,
        costo=_decimal_opcional(mapa.valor(fila, "costo"), columna="costo") or Decimal(0),
        descripcion=texto_limpio(mapa.valor(fila, "descripcion")) or None,
        familia=texto_limpio(mapa.valor(fila, "familia")) or None,
        contratista=texto_limpio(mapa.valor(fila, "contratista")) or None,
        costo_ultimo=_decimal_opcional(
            mapa.valor(fila, "costo_ultimo"), columna="costo_ultimo"
        ),
        costo_promedio=_decimal_opcional(
            mapa.valor(fila, "costo_promedio"), columna="costo_promedio"
        ),
        clave_concepto=concepto_de_referencia(mapa.valor(fila, "referencia")),
        almacen=texto_limpio(mapa.valor(fila, "almacen")) or None,
        usuario=texto_limpio(mapa.valor(fila, "usuario")) or None,
        fila=numero,
    )
