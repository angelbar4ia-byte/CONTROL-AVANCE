"""`validar_material` contra los dos catálogos reales del exportador de
OPUS que comparten contrato: materiales y fletes.

Spec §3.3 (la CLAVE manda) · §10.1 (campos del catálogo de materiales) ·
§cabeceras.MATERIALES_OPUS / FLETES_OPUS (extensión propia, generación
2025 de OPUS — distinta de `CABECERAS_MATERIALES.xlsx`/`MATERIALES`, que
sigue sirviendo al archivo de la generación anterior sin tocarse).

Mismo criterio que `test_presupuesto_opus_real.py` y
`test_cpu_opus_real.py`: estos dos archivos solo se verifican de verdad
contra los que los originaron, así que la prueba toca disco — con el
``csv`` de la librería estándar, para seguir ejercitando solo el dominio
puro. Los dos viven en otro repo adjunto a esta sesión (no en este).
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from pathlib import Path

import pytest

from obractrl.domain.cargadores.cabeceras import (
    FLETES_OPUS,
    MATERIALES_OPUS,
    resolver_encabezados,
)
from obractrl.domain.cargadores.materiales import validar_material
from obractrl.domain.shared.diccionario import TipoInsumo

_MATERIALES = Path("/home/user/cerebro-erp-construccion/1-mundo/opus/CATALOGO_DE_MATERIALES.csv")
_FLETES = Path("/home/user/cerebro-erp-construccion/1-mundo/opus/CATALOGO_DE_FLETES.csv")

pytestmark = pytest.mark.skipif(
    not _MATERIALES.exists() or not _FLETES.exists(),
    reason=(
        "Archivos reales del exportador de OPUS no disponibles en este "
        f"entorno: {_MATERIALES}, {_FLETES}"
    ),
)


def _leer_csv(ruta: Path) -> tuple[list[str], list[tuple[int, Sequence[object]]]]:
    """Mismo contrato que `test_presupuesto_opus_real._leer_csv`: la
    primera fila es la cabecera, el resto son `(numero, fila)` en base 1
    contando la cabecera como la fila 1."""
    with ruta.open(newline="", encoding="utf-8-sig") as f:
        todas = list(csv.reader(f))
    encabezados = todas[0]
    datos = [
        (numero, fila)
        for numero, fila in enumerate(todas[1:], start=2)
        if any(celda.strip() for celda in fila)
    ]
    return encabezados, datos


def test_los_386_materiales_cargan_sin_error() -> None:
    """386 filas verificadas (sin huecos, sin duplicados de clave). Las
    386 traen clave, descripción y "Costo base M. N." —el que
    `MATERIALES_OPUS.alias` elige como `costo_base`, mismo criterio que
    `MATERIALES` con "COSTO BASE M.N." en el archivo de la generación
    anterior—, así que ninguna fila debería fallar ni quedar sin costo."""
    encabezados, filas = _leer_csv(_MATERIALES)
    mapa = resolver_encabezados(encabezados, MATERIALES_OPUS)

    cargados = [validar_material(fila, mapa, numero) for numero, fila in filas]

    assert len(filas) == 386
    assert len(cargados) == 386
    assert all(m.tipo is TipoInsumo.MATERIAL for m in cargados)
    assert all(m.costo_base is not None for m in cargados)
    assert len({m.llave for m in cargados}) == 386  # sin claves duplicadas

    primero = cargados[0]
    assert str(primero.clave) == "ACE-00001"
    assert primero.descripcion == "ALAMBRE RECOCIDO"
    assert primero.unidad == "KG"
    assert primero.familia == "Aceros"
    assert primero.costo_base == primero.costo_base  # no explota el Decimal


def test_los_9_fletes_cargan_como_mas_materiales() -> None:
    """9 filas verificadas. "Flete" es una categoría de la *explosión* del
    CPU (`CategoriaExplosion.FLETE`, migración 0052), no un tipo de
    insumo distinto —el enum `TipoInsumo` no tiene "flete" y no hace
    falta—, así que las 9 cargan con `tipo=TipoInsumo.MATERIAL`, igual que
    los materiales.

    Ninguna de las 9 claves está hoy en `CATALOGO_DE_MATERIALES.csv`
    (verificado): no hay insumo que migre de un catálogo al otro con la
    misma clave en esta corrida."""
    encabezados, filas = _leer_csv(_FLETES)
    mapa = resolver_encabezados(encabezados, FLETES_OPUS)

    cargados = [validar_material(fila, mapa, numero) for numero, fila in filas]

    assert len(filas) == 9
    assert len(cargados) == 9
    assert all(m.tipo is TipoInsumo.MATERIAL for m in cargados)
    assert all(m.costo_base is not None for m in cargados)

    claves_fletes = {m.llave for m in cargados}

    encabezados_mat, filas_mat = _leer_csv(_MATERIALES)
    mapa_materiales = resolver_encabezados(encabezados_mat, MATERIALES_OPUS)
    claves_materiales = {
        str(validar_material(fila, mapa_materiales, numero).clave)
        for numero, fila in filas_mat
    }
    assert claves_fletes.isdisjoint(claves_materiales)
