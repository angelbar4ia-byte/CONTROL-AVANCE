"""`ANALISIS_DE_BASICOS_CONCEPTOS.csv` con las descripciones y unidades del
`CATALOGO_DE_MATRICES.csv` (D-607/D-608), no con el árbol de presupuesto.

Lo que dice el cerebro y esta prueba fija contra los archivos reales:

- Solo `Origen = Concepto` (2,189 filas, 468 padres); compuestos y cuadrillas
  quedan fuera (D-609).
- Las 58 cantidades negativas son ajustes legítimos: se conservan con signo
  (`CATALOGOS.md` §8).
- El mismo insumo puede repetirse en una matriz (dos usos distintos): ninguna
  línea se consolida ni se descarta (`CATALOGOS.md` §8).
- La unidad de la línea viene del catálogo de origen: este archivo no da de
  alta unidades; `'CUB '` (espacio final) se limpia.
"""

from __future__ import annotations

import csv
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

import pytest

from obractrl.domain.cargadores.cabeceras import (
    CATALOGO_MATRICES_OPUS,
    CPU_MATRIZ,
    resolver_encabezados,
)
from obractrl.domain.cargadores.cpu import ConceptoCargado, agrupar_conceptos
from obractrl.domain.cargadores.matrices_catalogo import validar_matriz_catalogo

_OPUS = Path("/home/user/cerebro-erp-construccion/1-mundo/opus")
_MATRICES = _OPUS / "CATALOGO_DE_MATRICES.csv"
_ANALISIS = _OPUS / "ANALISIS_DE_BASICOS_CONCEPTOS.csv"

pytestmark = pytest.mark.skipif(
    not _MATRICES.exists() or not _ANALISIS.exists(),
    reason="Archivos reales del exportador de OPUS no disponibles en este entorno.",
)


def _leer(ruta: Path) -> tuple[list[str], list[tuple[int, Sequence[object]]]]:
    with ruta.open(newline="", encoding="utf-8-sig") as f:
        todas = list(csv.reader(f))
    datos = [
        (n, r) for n, r in enumerate(todas[1:], start=2) if any(c.strip() for c in r)
    ]
    return todas[0], datos


def _agrupar() -> tuple[tuple[ConceptoCargado, ...], tuple, tuple]:
    enc, filas = _leer(_MATRICES)
    mapa = resolver_encabezados(enc, CATALOGO_MATRICES_OPUS)
    descripciones: dict[str, tuple[str, str | None]] = {}
    for n, fila in filas:
        m = validar_matriz_catalogo(fila, mapa, n)
        descripciones[str(m.clave)] = (m.descripcion, m.unidad)
    enc, filas = _leer(_ANALISIS)
    mapa = resolver_encabezados(enc, CPU_MATRIZ)
    bloques, errores, pendientes, _ = agrupar_conceptos(
        filas, mapa, descripciones_concepto=descripciones
    )
    return bloques, errores, pendientes


def test_los_468_padres_de_concepto_cruzan_con_el_catalogo_de_matrices() -> None:
    bloques, errores, _ = _agrupar()
    assert errores == ()
    assert len(bloques) == 468
    assert sum(len(b.componentes) for b in bloques) == 2189


def test_las_58_cantidades_negativas_se_conservan_con_su_signo() -> None:
    bloques, _, _ = _agrupar()
    negativas = [c for b in bloques for c in b.componentes if c.cantidad < 0]
    assert len(negativas) == 58


def test_el_mismo_insumo_repetido_en_un_concepto_no_se_consolida() -> None:
    bloques, _, _ = _agrupar()
    cuentas = Counter(
        (str(b.encabezado.clave), str(c.clave_insumo))
        for b in bloques
        for c in b.componentes
    )
    repetidos = [par for par, n in cuentas.items() if n > 1]
    # 38 pares repetidos en el archivo: 26 son de auxiliares (Origen=Material,
    # fuera de alcance) y 12 de conceptos, que se conservan todos.
    assert len(repetidos) == 12


def test_la_unidad_de_las_lineas_sale_limpia_y_sin_altas_nuevas() -> None:
    bloques, _, _ = _agrupar()
    unidades = {c.unidad for b in bloques for c in b.componentes}
    assert "CUB " not in unidades
    assert None not in unidades
    assert not {"JOR", "(%)mo"} & unidades  # son de las cuadrillas, no de los conceptos


def test_las_recetas_de_los_89_compuestos_se_agrupan_con_matriz_dentro_de_matriz() -> (
    None
):
    from obractrl.domain.cargadores.cpu import agrupar_compuestos

    enc, filas = _leer(_ANALISIS)
    mapa = resolver_encabezados(enc, CPU_MATRIZ)
    bloques, errores, _ = agrupar_compuestos(filas, mapa)
    assert errores == ()
    assert len(bloques) == 89  # 79 AUX + 8 MEZ + ZA1 + ZA2
    assert sum(len(b.componentes) for b in bloques) == 267
    claves = {str(b.encabezado.clave) for b in bloques}
    dentro_de_compuesto = [
        c for b in bloques for c in b.componentes if str(c.clave_insumo) in claves
    ]
    assert len(dentro_de_compuesto) == 12  # compuesto dentro de compuesto
    assert all(b.encabezado.descripcion and b.encabezado.unidad for b in bloques)
