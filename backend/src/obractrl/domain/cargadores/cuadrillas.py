"""Cargador de cuadrillas: composición y PU (§10.6 `CABECERAS_CUADRILLAS.xlsx`).

Spec §10.6 (contrato del archivo) · §7.3/§7.6 (cuadrilla) · §3.3 (la CLAVE
manda) · §10.8 (cada carga que cambia la composición es una versión).

El archivo trae, por cuadrilla, una fila **cabecera** (``Clave = Clave
cuadrilla``) seguida de sus filas **integrante** (misma ``Clave cuadrilla``,
``Clave`` = el insumo que la compone). A diferencia de `cpu.py` —que
reconstruye el bloque por orden de filas más una columna ``TIPO``— aquí cada
fila ya trae explícita la llave del bloque (``Clave cuadrilla``), así que
agrupar es un `dict`, no una máquina de estados.

Módulo puro (§12.11).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from obractrl.domain.cargadores.cabeceras import MapaColumnas
from obractrl.domain.cargadores.reporte import ErrorDeFila, ErrorEnFila
from obractrl.domain.shared.normalizacion import (
    ValorNoConvertible,
    a_decimal,
    esta_vacio,
    texto_limpio,
)
from obractrl.domain.shared.valores import Clave

__all__ = [
    "CuadrillaCargada",
    "EncabezadoCuadrillaCargado",
    "IntegranteCargado",
    "agrupar_cuadrillas",
]


@dataclass(frozen=True, slots=True)
class EncabezadoCuadrillaCargado:
    """Fila ``Clave == Clave cuadrilla``: identifica la cuadrilla del bloque."""

    clave: Clave
    descripcion: str
    unidad: str | None = None
    precio_declarado: Decimal | None = None
    """PU de la columna de la fila cabecera. Solo informativo: el PU real
    sale de sumar los integrantes (§10.6), igual que en `EncabezadoCargado`
    de `cpu.py`."""

    fila: int = 0


@dataclass(frozen=True, slots=True)
class IntegranteCargado:
    """Fila integrante: un insumo dentro de la composición de la cuadrilla."""

    clave_insumo: Clave
    descripcion: str
    cantidad: Decimal
    unidad: str | None = None
    costo_unitario: Decimal | None = None
    fila: int = 0


@dataclass(frozen=True, slots=True)
class CuadrillaCargada:
    """Bloque completo: cabecera + sus integrantes."""

    encabezado: EncabezadoCuadrillaCargado
    componentes: tuple[IntegranteCargado, ...] = field(default=())

    @property
    def llave(self) -> str:
        """Identidad para dedup y diff: la CLAVE de la cuadrilla (§3.3)."""
        return str(self.encabezado.clave)


def _clave_de(celda: object, *, columna: str) -> Clave:
    if esta_vacio(celda):
        raise ErrorEnFila(
            f"{columna}: la fila no trae clave y la clave es única por "
            f"catálogo (§3.3).",
            columna=columna,
        )
    try:
        return Clave(str(celda))
    except ValueError as exc:
        raise ErrorEnFila(str(exc), columna=columna, valor=celda) from exc


def _decimal_opcional(celda: object, *, columna: str) -> Decimal | None:
    if esta_vacio(celda):
        return None
    try:
        return a_decimal(celda, campo=columna)
    except ValorNoConvertible as exc:
        raise ErrorEnFila(str(exc), columna=columna, valor=celda) from exc


def _leer_encabezado(
    fila: Sequence[object], mapa: MapaColumnas, numero: int
) -> EncabezadoCuadrillaCargado:
    descripcion = texto_limpio(mapa.valor(fila, "descripcion"))
    if not descripcion:
        raise ErrorEnFila(
            "descripcion: una cuadrilla sin descripción no es identificable (§10.1).",
            columna="descripcion",
        )
    return EncabezadoCuadrillaCargado(
        clave=_clave_de(mapa.valor(fila, "clave"), columna="clave"),
        descripcion=descripcion,
        unidad=texto_limpio(mapa.valor(fila, "unidad")) or None,
        precio_declarado=_decimal_opcional(
            mapa.valor(fila, "precio_unitario"), columna="precio_unitario"
        ),
        fila=numero,
    )


def _leer_integrante(
    fila: Sequence[object], mapa: MapaColumnas, numero: int
) -> IntegranteCargado:
    # Acepta negativos a propósito: mismo criterio que un componente de CPU
    # (§10.6, deducciones/ajustes restan del PU en vez de sumar).
    cantidad = _decimal_opcional(mapa.valor(fila, "cantidad"), columna="cantidad")
    if cantidad is None:
        raise ErrorEnFila(
            "cantidad: obligatoria en una fila integrante (§10.6).",
            columna="cantidad",
        )
    return IntegranteCargado(
        clave_insumo=_clave_de(mapa.valor(fila, "clave"), columna="clave"),
        descripcion=texto_limpio(mapa.valor(fila, "descripcion")),
        cantidad=cantidad,
        unidad=texto_limpio(mapa.valor(fila, "unidad")) or None,
        costo_unitario=_decimal_opcional(
            mapa.valor(fila, "precio_unitario"), columna="precio_unitario"
        ),
        fila=numero,
    )


def _clave_normalizada(celda: object) -> str | None:
    if esta_vacio(celda):
        return None
    try:
        return str(Clave(str(celda)))
    except ValueError:
        return None


def agrupar_cuadrillas(
    filas: Sequence[tuple[int, Sequence[object]]], mapa: MapaColumnas
) -> tuple[tuple[CuadrillaCargada, ...], tuple[ErrorDeFila, ...], int]:
    """Filas planas → bloques cuadrilla+integrantes (§10.6).

    Devuelve ``(cuadrillas, errores, omitidos)``:

    - Se agrupa por ``clave_cuadrilla`` (normalizada, §3.3), no por orden de
      filas: el archivo ya trae la llave del bloque en cada renglón —a
      diferencia de `agrupar_conceptos`, que reconstruye el bloque por
      posición—, así que un integrante puede venir en cualquier posición
      relativa a su cabecera, y agrupar es un `dict`, no una máquina de
      estados. Por construcción cada grupo es único, así que aquí nunca hay
      nada que "gane el último": ``omitidos`` siempre sale en 0 y solo se
      conserva en la firma para que este cargador tenga la misma forma que
      el resto (§9.2).
    - Una fila sin ``clave_cuadrilla`` es un error de fila: sin ella no hay
      a qué bloque pertenece.
    - La fila cuya ``clave`` es igual a su ``clave_cuadrilla`` es la
      cabecera del bloque. Sin ella, o con más de una, el bloque entero es
      un error de fila (no hay PU sin cabecera, y dos cabeceras son
      ambigüedad, no una fusión).
    - Una fila integrante mala no tumba el bloque (§9.3): se reporta y se
      sigue con el resto.
    """
    grupos: dict[str, list[tuple[int, Sequence[object]]]] = {}
    orden_grupos: list[str] = []
    errores: list[ErrorDeFila] = []

    for numero, fila in filas:
        llave = _clave_normalizada(mapa.valor(fila, "clave_cuadrilla"))
        if llave is None:
            errores.append(
                ErrorDeFila(
                    fila=numero,
                    columna="clave_cuadrilla",
                    valor=None,
                    motivo=(
                        "clave_cuadrilla: la fila no dice a qué cuadrilla "
                        "pertenece (§10.6)."
                    ),
                )
            )
            continue
        if llave not in grupos:
            grupos[llave] = []
            orden_grupos.append(llave)
        grupos[llave].append((numero, fila))

    bloques: list[CuadrillaCargada] = []

    for llave_grupo in orden_grupos:
        renglones = grupos[llave_grupo]
        cabeceras = [
            (numero, fila)
            for numero, fila in renglones
            if _clave_normalizada(mapa.valor(fila, "clave")) == llave_grupo
        ]

        if len(cabeceras) != 1:
            for numero, _ in renglones:
                errores.append(
                    ErrorDeFila(
                        fila=numero,
                        columna="clave",
                        valor=llave_grupo,
                        motivo=(
                            f"clave_cuadrilla {llave_grupo!r}: se esperaba "
                            f"exactamente una fila cabecera (Clave = Clave "
                            f"cuadrilla) y se encontraron {len(cabeceras)} (§10.6)."
                        ),
                    )
                )
            continue

        numero_cabecera, fila_cabecera = cabeceras[0]
        try:
            encabezado = _leer_encabezado(fila_cabecera, mapa, numero_cabecera)
        except ErrorEnFila as exc:
            errores.append(exc.con_fila(numero_cabecera))
            continue

        componentes: list[IntegranteCargado] = []
        for numero, fila in renglones:
            if numero == numero_cabecera:
                continue
            try:
                componentes.append(_leer_integrante(fila, mapa, numero))
            except ErrorEnFila as exc:
                errores.append(exc.con_fila(numero))

        bloques.append(CuadrillaCargada(encabezado=encabezado, componentes=tuple(componentes)))

    return tuple(bloques), tuple(errores), 0
