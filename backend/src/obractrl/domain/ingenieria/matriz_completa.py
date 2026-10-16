"""Lectura cruda de la matriz nativa de OPUS, SIN la restricción de
``Origen = Concepto`` que `domain.cargadores.cpu._agrupar_conceptos_matriz`
aplica a propósito.

Ese cargador existe para el catálogo de Conceptos + CPU (§10.6) y por eso
descarta, a propósito, las líneas ``Origen = Material``/``ManoDeObra`` —
son la matriz INTERNA de un compuesto o de una cuadrilla, "fuera de alcance
de este cargador" (docstring de `cpu.py`). Identificar el prototipo y
revertir por destajo (CONOCIMIENTO.md §11.9, §11.14) necesitan justo esas
líneas: `MOC-12010` (la mano de obra de una zapata) solo aparece en la
matriz del COMPUESTO `ZA1-000001`, nunca en la de un concepto directo
("se estaba buscando en la profundidad equivocada", §11.9). Sin esas
líneas, `domain.catalogos.apu.explotar` no tiene cómo recursar a través
del compuesto — se quedaría en un insumo de precio declarado, igual que le
pasaba al cerebro antes de armar el árbol completo (`armar_arbol`,
`core/importacion_opus.py`, que tampoco filtra por `Origen`).

Por eso este módulo lee la matriz completa (todas las líneas, cualquier
``Origen``) y construye el ``composiciones`` que `apu.explotar` espera,
clasificando cada hijo como insumo o como concepto/compuesto exactamente
como lo hace `core/importacion_opus.py::armar_arbol` del cerebro: un hijo
es "concepto" si ÉL MISMO aparece como padre en alguna línea de la matriz
(tiene su propia composición); si no, es un insumo con el costo que trae
su propia línea.

Módulo puro: sin FastAPI, SQLModel ni RLS (§12.11).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from obractrl.domain.cargadores.cabeceras import MapaColumnas
from obractrl.domain.cargadores.cpu import CATEGORIA_POR_TIPO_MATRIZ
from obractrl.domain.cargadores.reporte import (
    ErrorDeFila,
    ErrorEnFila,
    PendientePropuesto,
    TipoPendiente,
)
from obractrl.domain.catalogos.apu import Componente
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
    "LineaMatrizCruda",
    "construir_composiciones",
    "leer_lineas_crudas",
]

_ORIGEN_CONCEPTO = "concepto"


@dataclass(frozen=True, slots=True)
class LineaMatrizCruda:
    """Un renglón de la matriz nativa de OPUS, de cualquier ``Origen``
    (concepto, compuesto o cuadrilla) — a diferencia de `cpu.
    ComponenteCargado`, que solo existe para las de ``Origen=Concepto``."""

    padre: str
    hijo: str
    descripcion: str
    unidad: str | None
    cantidad: Decimal
    costo: Decimal
    categoria: CategoriaExplosion
    origen: str
    """``Origen`` normalizado (§8.6): ``concepto`` · ``material`` ·
    ``manodeobra`` / ``mano de obra``. No es el ``Tipo`` del hijo
    (`categoria`) — un compuesto `Origen=Material` puede listar un hijo
    `Tipo=Contrato` (`CASO-TRABAJADO.md` §3, `MOC-12010` dentro de
    `ZA1-000001`)."""

    fila: int


def _leer_linea(
    fila: Sequence[object], mapa: MapaColumnas, numero: int
) -> LineaMatrizCruda:
    def celda(campo: str) -> object:
        return mapa.valor(fila, campo)

    padre = celda("clave_padre")
    hijo = celda("clave_insumo")
    if esta_vacio(padre):
        raise ErrorEnFila(
            "clave_padre: la fila no trae clave de padre (§3.3).", columna="clave_padre"
        )
    if esta_vacio(hijo):
        raise ErrorEnFila(
            "clave_insumo: la fila no trae clave de hijo (§3.3).", columna="clave_insumo"
        )
    try:
        cantidad = a_decimal(celda("cantidad"), campo="cantidad")
    except ValorNoConvertible as exc:
        raise ErrorEnFila(str(exc), columna="cantidad", valor=celda("cantidad")) from exc

    crudo_costo = celda("precio_unitario")
    try:
        costo = a_decimal(crudo_costo, campo="costo") if not esta_vacio(crudo_costo) else Decimal(0)
    except ValorNoConvertible as exc:
        raise ErrorEnFila(str(exc), columna="costo", valor=crudo_costo) from exc

    texto_tipo = normalizar(celda("tipo"))
    categoria = CATEGORIA_POR_TIPO_MATRIZ.get(texto_tipo)
    if categoria is None:
        raise ErrorEnFila(
            f"tipo: {texto_limpio(celda('tipo'))!r} no es uno de los valores de la "
            f"matriz nativa de OPUS ({', '.join(sorted(CATEGORIA_POR_TIPO_MATRIZ))}).",
            columna="tipo",
            valor=celda("tipo"),
        )

    return LineaMatrizCruda(
        padre=str(Clave(str(padre))),
        hijo=str(Clave(str(hijo))),
        descripcion=texto_limpio(celda("descripcion")),
        unidad=texto_limpio(celda("unidad")) or None,
        cantidad=cantidad,
        costo=costo,
        categoria=categoria,
        origen=normalizar(celda("origen")),
        fila=numero,
    )


def leer_lineas_crudas(
    filas: Sequence[tuple[int, Sequence[object]]], mapa: MapaColumnas
) -> tuple[tuple[LineaMatrizCruda, ...], tuple[ErrorDeFila, ...], tuple[PendientePropuesto, ...]]:
    """Todas las líneas de la matriz nativa de OPUS, cualquier ``Origen``.

    Una fila mala no tumba el archivo (§9.3): se reporta y se sigue. Un
    ``Tipo`` fuera del vocabulario de `CATEGORIA_POR_TIPO_MATRIZ` va a la
    bandeja como `TipoPendiente.FILA_NO_PARSEADA` — mismo criterio que
    `cpu._agrupar_conceptos_matriz`, solo que aquí ninguna fila se descarta
    por su ``Origen``.
    """
    lineas: list[LineaMatrizCruda] = []
    errores: list[ErrorDeFila] = []
    pendientes: list[PendientePropuesto] = []
    for numero, fila in filas:
        try:
            lineas.append(_leer_linea(fila, mapa, numero))
        except ErrorEnFila as exc:
            if exc.columna == "tipo":
                pendientes.append(
                    PendientePropuesto(
                        tipo=TipoPendiente.FILA_NO_PARSEADA,
                        entidad="matriz_completa",
                        valor_origen=str(exc.valor),
                        propuesta={"opciones": sorted(CATEGORIA_POR_TIPO_MATRIZ)},
                        origen_ref=f"fila {numero}",
                    )
                )
            errores.append(exc.con_fila(numero))
    return tuple(lineas), tuple(errores), tuple(pendientes)


def construir_composiciones(
    lineas: Sequence[LineaMatrizCruda],
) -> dict[str, tuple[Componente, ...]]:
    """``composiciones`` para `domain.catalogos.apu.explotar`: clave de
    padre → sus `Componente`, de TODOS los orígenes (concepto, compuesto,
    cuadrilla) juntos en un solo árbol — igual que `armar_arbol` del
    cerebro (`core/importacion_opus.py`), que tampoco separa por `Origen`.

    Un hijo que también aparece como padre en alguna línea (tiene su
    propia composición) se carga como ``clave_concepto`` — su costo lo
    calcula la explosión, nunca la columna `costo` de esta línea
    (`Componente.__post_init__` ya lo ignora). Un hijo que nunca es padre
    se carga como ``clave_insumo`` con el costo declarado de su propia
    línea.
    """
    padres = {linea.padre for linea in lineas}
    por_padre: dict[str, list[Componente]] = defaultdict(list)
    for orden, linea in enumerate(lineas, start=1):
        if linea.hijo in padres:
            componente = Componente(
                categoria=linea.categoria, cantidad=linea.cantidad, clave_concepto=linea.hijo, orden=orden
            )
        else:
            componente = Componente(
                categoria=linea.categoria,
                cantidad=linea.cantidad,
                clave_insumo=linea.hijo,
                costo_unitario=linea.costo,
                orden=orden,
            )
        por_padre[linea.padre].append(componente)
    return {clave: tuple(componentes) for clave, componentes in por_padre.items()}
