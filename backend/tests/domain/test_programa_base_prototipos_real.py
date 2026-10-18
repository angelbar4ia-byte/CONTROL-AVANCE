"""`leer_programa_base`/`resolver_vinculos` contra `PROGRAMAS-PROTOTIPOS.csv`,
el archivo que de verdad trae la red resuelta de los 7 prototipos (§7.5, Paso
4 del rollout: "Se da de alta por la API (no hay cargador) con PROGRAMAS-
PROTOTIPOS.csv y la red mínima").

Por qué este archivo y no `PROGRAMA_ZAFIRO.xlsx` (el que ya prueba
`tests/integracion/test_programa_base_endtoend.py`, solo contra Zafiro):
verificado fila por fila contra los dos archivos reales, `PROGRAMA_ZAFIRO.
xlsx` trae `Vínculos` nativo **solo** en el bloque de Zafiro — los otros seis
prototipos tienen esa columna vacía en el 100% de sus filas, así que ningún
vínculo se podría resolver ahí. `PROGRAMAS-PROTOTIPOS.csv` es el mismo
cronograma con la red ya resuelta para los seis que no la traían (columna
`regla`: "gemelo por clave", "losa por altura", etc. — un vínculo igual de
real, inferido en vez de tecleado en MS Project). Ver el docstring de
`cabeceras.PROGRAMA_BASE`.

Única prueba de este paquete que toca disco, mismo criterio que
`test_presupuesto_opus_real.py`: el archivo vive en el repo de cerebro,
adjunto a esta sesión, no en este."""

from __future__ import annotations

import csv
from collections.abc import Sequence
from pathlib import Path

import pytest

from obractrl.domain.cargadores.cabeceras import PROGRAMA_BASE, resolver_encabezados
from obractrl.domain.cargadores.programa_base import (
    BloqueProgramaCargado,
    leer_programa_base,
    resolver_vinculos,
)

_ARCHIVO_REAL = Path(
    "/home/user/cerebro-erp-construccion/1-mundo/programas/PROGRAMAS-PROTOTIPOS.csv"
)

pytestmark = pytest.mark.skipif(
    not _ARCHIVO_REAL.exists(),
    reason=f"Archivo real PROGRAMAS-PROTOTIPOS.csv no disponible en este entorno: {_ARCHIVO_REAL}",
)

_CLAVES_ESPERADAS = {
    "CAS-00001",
    "CAS-00002",
    "CAS-00003",
    "CAS-00004",
    "CAS-00005",
    "CAS-00006",
    "CAS-00007",
}


def _leer_csv(ruta: Path) -> tuple[list[str], list[tuple[int, Sequence[object]]]]:
    """Mismo contrato que `test_presupuesto_opus_real.py::_leer_csv`: la
    cabecera es la fila 1, y el resto son `(numero, fila)` en base 1 contando
    la cabecera, para que un error de fila señale al renglón real."""
    with ruta.open(newline="", encoding="utf-8-sig") as f:
        todas = list(csv.reader(f))
    encabezados = todas[0]
    datos = [
        (numero, fila)
        for numero, fila in enumerate(todas[1:], start=2)
        if any(celda.strip() for celda in fila)
    ]
    return encabezados, datos


def _construir() -> tuple[BloqueProgramaCargado, ...]:
    encabezados, filas = _leer_csv(_ARCHIVO_REAL)
    mapa = resolver_encabezados(encabezados, PROGRAMA_BASE)
    # Si el archivo real cambiara de ortografía de cabecera otra vez, esto
    # falla aquí (no en silencio) en vez de cargar sin fechas ni vínculos.
    assert "fecha_inicio" in mapa.indices
    assert "fecha_termino" in mapa.indices
    assert "dias_laborables" in mapa.indices
    assert "vinculos" in mapa.indices

    bloques, errores = leer_programa_base(filas, mapa)
    assert errores == (), [e.motivo for e in errores[:5]]
    return bloques


def test_el_archivo_trae_los_siete_prototipos() -> None:
    bloques = _construir()
    assert len(bloques) == 7
    assert {b.clave_prototipo for b in bloques} == _CLAVES_ESPERADAS


def test_los_siete_prototipos_traen_vinculos_resueltos() -> None:
    """A diferencia de `PROGRAMA_ZAFIRO.xlsx` (ver docstring del módulo),
    aquí los 7 bloques producen decenas de dependencias reales, nunca cero
    — es la "red mínima" que el Paso 4 del plan exige para los seis
    prototipos que OPUS nunca programó con vínculos explícitos."""
    bloques = _construir()
    conteos = {
        b.clave_prototipo: len(resolver_vinculos(b).dependencias) for b in bloques
    }
    # Verificado contra el archivo real.
    assert conteos == {
        "CAS-00004": 118,  # Zafiro — el único con vínculos también nativos
        "CAS-00003": 102,
        "CAS-00006": 129,
        "CAS-00002": 85,
        "CAS-00005": 128,
        "CAS-00007": 129,
        "CAS-00001": 131,
    }


def test_cada_bloque_trae_fechas_e_identidad_de_fila() -> None:
    """Las columnas que `PROGRAMA_ZAFIRO.xlsx` no necesita resolver por
    alias (`inicio`/`termino`/`dias_laborables`, sin acento ni espacio) sí
    llegan al dominio con el mismo nombre canónico: toda partida real trae
    su fecha, y es la fecha contra la que se compara el motor de ObraCtrl
    (`test_programa_base_motor_cpm_real.py`)."""
    bloques = _construir()
    for bloque in bloques:
        partidas = bloque.partidas
        assert partidas, bloque.clave_prototipo
        assert all(p.inicio is not None and p.termino is not None for p in partidas)
