"""`validar_trabajo`/`clase_de_trabajo` contra el catálogo combinado de
Trabajos del exportador de OPUS.

Spec §3.3 (la CLAVE manda) · §10.2 (multi-archivo: destajos y
subcontratos, antes en dos archivos separados, ahora en uno) ·
§cabeceras.TRABAJOS_OPUS (extensión propia).

Mismo criterio que el resto de `test_*_opus_real.py`: este archivo solo se
verifica de verdad contra el que lo originó, así que la prueba toca disco
con el ``csv`` de la librería estándar —**nunca** `csv.DictReader`, que
con las dos cabeceras "Tipo" duplicadas pisaría una con la otra en
silencio— para seguir ejercitando solo el dominio puro.
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from pathlib import Path

import pytest

from obractrl.domain.cargadores.cabeceras import TRABAJOS_OPUS, resolver_encabezados
from obractrl.domain.cargadores.mano_de_obra import clase_de_trabajo, validar_trabajo
from obractrl.domain.cargadores.reporte import ErrorEnFila
from obractrl.domain.shared.diccionario import TipoInsumo

_TRABAJOS = Path("/home/user/cerebro-erp-construccion/1-mundo/opus/CATALOGO_DE_TRABAJOS.csv")

pytestmark = pytest.mark.skipif(
    not _TRABAJOS.exists(),
    reason=f"Archivo real del exportador de OPUS no disponible en este entorno: {_TRABAJOS}",
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


def test_el_archivo_trae_tipo_dos_veces_y_la_primera_es_la_clase() -> None:
    """Verificación de la trampa misma, por posición y con `csv.reader`
    (no `DictReader`): dos columnas "Tipo" en las posiciones 1 y 13
    (base 0); la primera trae `Destajo`/`Subcontrato` (la clase), la
    última vale "Trabajo" en las 265 filas (la categoría genérica, sin
    aportar nada — igual que "Material" en `MATERIALES_OPUS`)."""
    encabezados, filas = _leer_csv(_TRABAJOS)

    posiciones_tipo = [i for i, c in enumerate(encabezados) if c.strip() == "Tipo"]
    assert posiciones_tipo == [1, 13]

    primera, ultima = posiciones_tipo
    valores_primera = {fila[primera] for _, fila in filas}
    valores_ultima = {fila[ultima] for _, fila in filas}
    assert valores_primera == {"Destajo", "Subcontrato"}
    assert valores_ultima == {"Trabajo"}


def test_las_265_filas_cargan_sin_error() -> None:
    """265 filas verificadas (sin huecos, sin duplicados de clave): 259
    `Destajo` → `TipoInsumo.MANO_OBRA`, 6 `Subcontrato` →
    `TipoInsumo.SUBCONTRATO`. Las 265 suman las 265 claves del catálogo."""
    encabezados, filas = _leer_csv(_TRABAJOS)
    mapa = resolver_encabezados(encabezados, TRABAJOS_OPUS)

    cargados = [validar_trabajo(fila, mapa, numero) for numero, fila in filas]

    assert len(filas) == 265
    assert len(cargados) == 265
    assert len({c.llave for c in cargados}) == 265  # sin claves duplicadas

    destajos = [c for c in cargados if c.tipo is TipoInsumo.MANO_OBRA]
    subcontratos = [c for c in cargados if c.tipo is TipoInsumo.SUBCONTRATO]
    assert len(destajos) == 259
    assert len(subcontratos) == 6
    assert len(destajos) + len(subcontratos) == 265


def test_los_subcontratos_son_las_6_claves_sub() -> None:
    """Las 6 filas `Subcontrato` son exactamente las 6 claves `SUB-*` —
    confirma que `clase_de_trabajo` separa por la columna real, no por el
    prefijo (que el cerebro prohíbe usar como clasificador, §diccionario.
    CategoriaExplosion.TRABAJO)."""
    encabezados, filas = _leer_csv(_TRABAJOS)
    mapa = resolver_encabezados(encabezados, TRABAJOS_OPUS)

    cargados = [validar_trabajo(fila, mapa, numero) for numero, fila in filas]
    claves_subcontrato = {str(c.clave) for c in cargados if c.tipo is TipoInsumo.SUBCONTRATO}

    assert claves_subcontrato == {
        "SUB-00001",
        "SUB-00002",
        "SUB-00003",
        "SUB-00004",
        "SUB-00005",
        "SUB-00006",
    }


def test_clase_de_trabajo_acepta_acarreo_como_tipo_propio() -> None:
    """`Acarreo` es la tercera clase del archivo (§cabeceras.TRABAJOS_OPUS).
    Sin filas en el catálogo real, pero aceptada como su propio tipo
    (`TipoInsumo.ACARREO`, migración 0095): decisión del usuario, no una
    traducción por parecido a flete ni a destajo."""
    encabezados, filas = _leer_csv(_TRABAJOS)
    mapa = resolver_encabezados(encabezados, TRABAJOS_OPUS)
    _, fila_real = filas[0]

    posiciones_tipo = mapa.series["clase"]
    fila_con_acarreo = list(fila_real)
    fila_con_acarreo[posiciones_tipo[0]] = "Acarreo"

    assert clase_de_trabajo(fila_con_acarreo, mapa) == TipoInsumo.ACARREO


def test_clase_de_trabajo_rechaza_un_valor_fuera_del_vocabulario() -> None:
    """Cualquier valor fuera de {Destajo, Subcontrato, Acarreo} se rechaza,
    nunca se traduce por parecido."""
    encabezados, filas = _leer_csv(_TRABAJOS)
    mapa = resolver_encabezados(encabezados, TRABAJOS_OPUS)
    _, fila_real = filas[0]

    posiciones_tipo = mapa.series["clase"]
    fila_con_flete = list(fila_real)
    fila_con_flete[posiciones_tipo[0]] = "Flete"

    with pytest.raises(ErrorEnFila):
        clase_de_trabajo(fila_con_flete, mapa)


def test_clase_de_trabajo_exige_la_categoria_trabajo_explicita() -> None:
    """Segunda confirmación: no basta con que sobre una sola clase —la
    categoría ("Trabajo") también se exige explícita, no solo por
    exclusión. Si la columna de categoría cambiara (aquí, a mano, por
    "Destajo" otra vez) se rechaza con su propio mensaje, en vez de que
    el error genérico de "clase" (dos candidatos) señale al lugar
    equivocado."""
    encabezados, filas = _leer_csv(_TRABAJOS)
    mapa = resolver_encabezados(encabezados, TRABAJOS_OPUS)
    _, fila_real = filas[0]

    posiciones_tipo = mapa.series["clase"]
    fila_sin_categoria = list(fila_real)
    fila_sin_categoria[posiciones_tipo[1]] = "Destajo"

    with pytest.raises(ErrorEnFila, match="literalmente 'Trabajo'"):
        clase_de_trabajo(fila_sin_categoria, mapa)
