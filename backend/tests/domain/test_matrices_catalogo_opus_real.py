"""`validar_matriz_catalogo` contra el catálogo de matrices del exportador de OPUS.

Decisiones: D-609 (los auxiliares quedan fuera), D-610 (las 11 columnas se
conservan; `C` = `+` es matriz desglosable; costos independientes).
La prueba lee el CSV con el módulo `csv` de la librería estándar, como
`test_trabajos_opus_real`, y se omite si el archivo no está en este entorno.
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import pytest

from obractrl.domain.cargadores.cabeceras import (
    CATALOGO_MATRICES_OPUS,
    resolver_encabezados,
)
from obractrl.domain.cargadores.matrices_catalogo import validar_matriz_catalogo
from obractrl.domain.cargadores.reporte import ErrorEnFila

_MATRICES = Path(
    "/home/user/cerebro-erp-construccion/1-mundo/opus/CATALOGO_DE_MATRICES.csv"
)

pytestmark = pytest.mark.skipif(
    not _MATRICES.exists(),
    reason=f"Archivo real del exportador de OPUS no disponible en este entorno: {_MATRICES}",
)


def _cargar():
    with _MATRICES.open(newline="", encoding="utf-8-sig") as f:
        filas = list(csv.reader(f))
    encabezados, datos = filas[0], filas[1:]
    mapa = resolver_encabezados(encabezados, CATALOGO_MATRICES_OPUS)
    return encabezados, mapa, datos


def test_las_472_filas_validan_y_las_claves_son_unicas() -> None:
    _, mapa, datos = _cargar()
    validadas = [
        validar_matriz_catalogo(fila, mapa, numero=i)
        for i, fila in enumerate(datos, start=2)
    ]
    assert len(validadas) == 472
    assert len({f.llave for f in validadas}) == 472


def test_las_once_columnas_se_conservan_no_se_ignora_ninguna() -> None:
    encabezados, mapa, _ = _cargar()
    assert len(encabezados) == 11
    assert mapa.ignoradas == ()
    campos = set(mapa.indices)
    assert {
        "clave",
        "descripcion",
        "unidad",
        "matriz_desglosable",
        "tipo",
        "familia",
        "subfamilia",
        "costo_base",
        "costo_base_me",
        "costo_unitario",
        "fecha",
    } <= campos


def test_c_con_mas_marca_matriz_desglosable_en_todas_las_filas() -> None:
    _, mapa, datos = _cargar()
    validadas = [
        validar_matriz_catalogo(fila, mapa, numero=i)
        for i, fila in enumerate(datos, start=2)
    ]
    assert all(f.matriz_desglosable for f in validadas)


def test_unidades_se_cargan_tal_cual_incluidas_sal_y_act() -> None:
    _, mapa, datos = _cargar()
    unidades = Counter(validar_matriz_catalogo(fila, mapa).unidad for fila in datos)
    assert unidades == Counter(
        {"pza": 167, "sal": 149, "m2": 61, "m": 47, "act": 44, "ser": 2, "m3": 2}
    )


def test_costos_son_valores_independientes_y_me_es_cero() -> None:
    _, mapa, datos = _cargar()
    validadas = [validar_matriz_catalogo(fila, mapa) for fila in datos]
    assert all(
        f.costo_base == f.costo_unitario for f in validadas
    )  # iguales en las 472 hoy
    assert all(
        f.costo_base_me == 0 for f in validadas
    )  # M.E. en cero, se conserva (D-186)


def test_tipo_es_matriz_y_subfamilia_vacia_hoy() -> None:
    _, mapa, datos = _cargar()
    validadas = [validar_matriz_catalogo(fila, mapa) for fila in datos]
    assert all(f.tipo == "Matriz" for f in validadas)
    assert all(f.subfamilia is None for f in validadas)


def test_marca_c_distinta_de_mas_o_vacia_se_rechaza() -> None:
    _, mapa, datos = _cargar()
    fila = list(datos[0])
    fila[mapa.indices["matriz_desglosable"]] = "x"
    with pytest.raises(ErrorEnFila) as exc:
        validar_matriz_catalogo(fila, mapa)
    assert exc.value.columna == "matriz_desglosable"


def test_concepto_sin_unidad_no_se_acepta() -> None:
    _, mapa, datos = _cargar()
    fila = list(datos[0])
    fila[mapa.indices["unidad"]] = ""
    with pytest.raises(ErrorEnFila) as exc:
        validar_matriz_catalogo(fila, mapa)
    assert exc.value.columna == "unidad"
