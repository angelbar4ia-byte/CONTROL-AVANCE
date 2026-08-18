"""Cargador de CPU / Conceptos: formato plano (§10.6 `CABECERAS_CPU.xlsx`).

Spec §10.6 (contrato del archivo, hoja `EXPORTADOR`) · §7.3 (APU: concepto +
explosión) · §3.3 (la CLAVE manda) · §10.3 (bandeja de pendientes) · §10.8
(cada carga es una versión).

El archivo es **plano**: por cada concepto viene una fila **encabezado**
(``TIPO = Concepto``) seguida de sus filas **componente**
(``TIPO = Material | Mano de obra | Subcontrato``). Reconstruir el bloque es
la única regla estructural del cargador y vive aquí, no en el lector: es
gramática del formato, no lectura de celdas (§12.11).

Módulo puro (§12.11).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from obractrl.domain.cargadores.cabeceras import MapaColumnas
from obractrl.domain.cargadores.reporte import (
    ErrorDeFila,
    ErrorEnFila,
    PendientePropuesto,
    TipoPendiente,
)
from obractrl.domain.shared.diccionario import CategoriaExplosion
from obractrl.domain.shared.normalizacion import (
    ValorNoConvertible,
    a_decimal,
    esta_vacio,
    normalizar,
    texto_limpio,
)
from obractrl.domain.shared.valores import Clave

__all__ = [
    "CATEGORIA_POR_TIPO",
    "ComponenteCargado",
    "ConceptoCargado",
    "EncabezadoCargado",
    "agrupar_conceptos",
]

_TIPO_ENCABEZADO = "concepto"
"""Valor de la columna ``TIPO`` que abre un bloque (§10.6: ``TIPO=Concepto``)."""

CATEGORIA_POR_TIPO: dict[str, CategoriaExplosion] = {
    "material": CategoriaExplosion.MATERIAL,
    "mano de obra": CategoriaExplosion.MANO_OBRA,
    "subcontrato": CategoriaExplosion.SUBCONTRATO,
}
"""``TIPO`` del archivo → `explosion.categoria` (§8.2).

Los tres valores son exactamente los que enumera el §10.6
(``TIPO=Material/Mano de obra/Subcontrato``). Un cuarto valor no se traduce
por parecido: es una excepción y va a la bandeja (§10.3), porque
`explosion.categoria` es **invariante** del §8.2 y agregarle un valor es
trabajo de programador (§8.7).
"""


@dataclass(frozen=True, slots=True)
class EncabezadoCargado:
    """Fila ``TIPO=Concepto``: identifica el concepto del bloque (§10.6)."""

    clave: Clave
    descripcion: str
    unidad: str | None = None
    familia: str | None = None
    precio_declarado: Decimal | None = None
    """PU de la columna F en la fila encabezado.

    Solo informativo: el §7.3 dice que el CPU **se calcula** de la explosión,
    y `PublicarVersionCPU` ya trata el precio capturado como la excepción del
    concepto sin desglose.
    """

    fila: int = 0


@dataclass(frozen=True, slots=True)
class ComponenteCargado:
    """Fila componente: un insumo dentro del APU del concepto (§7.3, §10.6).

    ``cantidad`` es la columna E, que el §10.6 define como
    "**rendimiento = CANTIDAD**": una sola columna para las dos cosas.
    """

    clave_insumo: Clave
    descripcion: str
    categoria: CategoriaExplosion
    cantidad: Decimal
    unidad: str | None = None
    precio_unitario: Decimal | None = None
    familia: str | None = None
    fila: int = 0


@dataclass(frozen=True, slots=True)
class ConceptoCargado:
    """Bloque completo: encabezado + sus componentes (§10.6)."""

    encabezado: EncabezadoCargado
    componentes: tuple[ComponenteCargado, ...] = field(default=())

    @property
    def llave(self) -> str:
        """Identidad para dedup y diff: la CLAVE del concepto (§3.3)."""
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


def _leer_encabezado(fila: Sequence[object], mapa: MapaColumnas, numero: int) -> EncabezadoCargado:
    descripcion = texto_limpio(mapa.valor(fila, "descripcion"))
    if not descripcion:
        raise ErrorEnFila(
            "descripcion: un concepto sin descripción no es identificable (§10.1).",
            columna="descripcion",
        )
    return EncabezadoCargado(
        clave=_clave_de(mapa.valor(fila, "clave"), columna="clave"),
        descripcion=descripcion,
        unidad=texto_limpio(mapa.valor(fila, "unidad")) or None,
        familia=texto_limpio(mapa.valor(fila, "familia")) or None,
        precio_declarado=_decimal_opcional(
            mapa.valor(fila, "precio_unitario"), columna="precio_unitario"
        ),
        fila=numero,
    )


def _leer_componente(
    fila: Sequence[object],
    mapa: MapaColumnas,
    numero: int,
    categoria: CategoriaExplosion,
) -> ComponenteCargado:
    cantidad = _decimal_opcional(mapa.valor(fila, "cantidad"), columna="cantidad")
    if cantidad is None:
        raise ErrorEnFila(
            "cantidad: la columna E (rendimiento = CANTIDAD) es obligatoria en "
            "una fila componente (§10.6).",
            columna="cantidad",
        )
    if cantidad < 0:
        raise ErrorEnFila(
            f"cantidad: el rendimiento de un componente no puede ser negativo "
            f"({cantidad}).",
            columna="cantidad",
            valor=cantidad,
        )
    return ComponenteCargado(
        # El §10.6 fija que en la fila componente la clave del insumo es la
        # columna B; los materiales se matchean por ESA clave contra catálogo
        # y almacén.
        clave_insumo=_clave_de(mapa.valor(fila, "clave_insumo"), columna="clave_insumo"),
        descripcion=texto_limpio(mapa.valor(fila, "descripcion")),
        categoria=categoria,
        cantidad=cantidad,
        unidad=texto_limpio(mapa.valor(fila, "unidad")) or None,
        precio_unitario=_decimal_opcional(
            mapa.valor(fila, "precio_unitario"), columna="precio_unitario"
        ),
        familia=texto_limpio(mapa.valor(fila, "familia")) or None,
        fila=numero,
    )


def agrupar_conceptos(
    filas: Sequence[tuple[int, Sequence[object]]], mapa: MapaColumnas
) -> tuple[
    tuple[ConceptoCargado, ...],
    tuple[ErrorDeFila, ...],
    tuple[PendientePropuesto, ...],
    int,
]:
    """Filas planas → bloques concepto+componentes (§10.6).

    Devuelve ``(conceptos, errores, pendientes, omitidos)``:

    - Una fila mala **no** tumba el bloque ni el archivo (§9.3): se reporta y
      se sigue.
    - Un ``TIPO`` fuera del §10.6 va a la bandeja como `fila_no_parseada`
      (§10.3), no se traduce por parecido.
    - Un componente antes de su encabezado es un error de fila: sin concepto
      padre no hay a qué colgarlo.
    - Clave de concepto repetida dentro del archivo: **gana el último bloque**
      y el anterior cuenta como omitido, que es lo que significa "deduplica
      por clave" en el modo Actualizar (§10.2).
    """
    bloques: dict[str, ConceptoCargado] = {}
    errores: list[ErrorDeFila] = []
    pendientes: list[PendientePropuesto] = []
    omitidos = 0

    actual: EncabezadoCargado | None = None
    componentes: list[ComponenteCargado] = []

    def cerrar() -> None:
        nonlocal actual, componentes, omitidos
        if actual is None:
            return
        bloque = ConceptoCargado(encabezado=actual, componentes=tuple(componentes))
        if bloque.llave in bloques:
            omitidos += 1
        bloques[bloque.llave] = bloque
        actual = None
        componentes = []

    for numero, fila in filas:
        crudo_tipo = mapa.valor(fila, "tipo")
        tipo = normalizar(crudo_tipo)

        if not tipo:
            errores.append(
                ErrorDeFila(
                    fila=numero,
                    columna="tipo",
                    valor=None,
                    motivo=(
                        "tipo: la columna I es la que dice si la fila es "
                        "encabezado o componente (§10.6); vacía, la fila no se "
                        "puede clasificar."
                    ),
                )
            )
            continue

        if tipo == _TIPO_ENCABEZADO:
            cerrar()
            try:
                actual = _leer_encabezado(fila, mapa, numero)
            except ErrorEnFila as exc:
                errores.append(exc.con_fila(numero))
                actual = None
            continue

        categoria = CATEGORIA_POR_TIPO.get(tipo)
        if categoria is None:
            errores.append(
                ErrorDeFila(
                    fila=numero,
                    columna="tipo",
                    valor=texto_limpio(crudo_tipo),
                    motivo=(
                        f"tipo: {texto_limpio(crudo_tipo)!r} no es uno de los "
                        f"valores del §10.6 (Concepto, "
                        f"{', '.join(sorted(CATEGORIA_POR_TIPO))})."
                    ),
                )
            )
            pendientes.append(
                PendientePropuesto(
                    tipo=TipoPendiente.FILA_NO_PARSEADA,
                    entidad="explosion",
                    valor_origen=texto_limpio(crudo_tipo),
                    propuesta={"opciones": sorted(CATEGORIA_POR_TIPO)},
                    origen_ref=f"fila {numero}",
                )
            )
            continue

        if actual is None:
            errores.append(
                ErrorDeFila(
                    fila=numero,
                    columna="tipo",
                    valor=texto_limpio(crudo_tipo),
                    motivo=(
                        "Fila componente sin su fila encabezado (TIPO=Concepto) "
                        "previa: no hay concepto al cual colgarla (§10.6)."
                    ),
                )
            )
            continue

        try:
            componentes.append(_leer_componente(fila, mapa, numero, categoria))
        except ErrorEnFila as exc:
            errores.append(exc.con_fila(numero))

    cerrar()
    return tuple(bloques.values()), tuple(errores), tuple(pendientes), omitidos
