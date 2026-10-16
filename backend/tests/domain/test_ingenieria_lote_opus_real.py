"""`domain.cargadores.ingenieria_lote` contra las once ingenierías reales
de `ALAMO 18` (`CONOCIMIENTO.md` §11.4-§11.9, en el repo adjunto a esta
sesión, no en este).

Cada número de este archivo se verificó corriendo el código contra los
CSV reales (no se copió de `CONOCIMIENTO.md` sin confirmarlo) — incluidas
las dos discrepancias que la investigación previa ya había encontrado:
`CIM_CAMARAS.csv` trae 5 columnas, no 6, y
`AJU._GUALDRA_PB.csv` trae 7, no 5.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.cargadores.ingenieria_lote import (
    TipoEstructuraIngenieria,
    leer_ingenieria_lote,
)
from tests.domain._opus_real_ingenieria import (
    INGENIERIA_ALAMO_18,
    archivos_disponibles,
    leer_filas_crudas,
)

pytestmark = pytest.mark.skipif(
    not archivos_disponibles(),
    reason=f"Ingenierías reales de ALAMO 18 no disponibles en este entorno: {INGENIERIA_ALAMO_18}",
)

# Nombre de archivo -> estructura esperada, verificado contra el ancho de
# columna y el contenido real de cada uno (ver docstring del módulo).
_ESTRUCTURA_ESPERADA = {
    "INGENIERIA_-_ALAMO_18_-_CIM.csv": TipoEstructuraIngenieria.COMPLETA,
    "INGENIERIA_-_ALAMO_18__-_PB.csv": TipoEstructuraIngenieria.COMPLETA,
    "INGENIERIA_-_ALAMO_18__-_PA_AZO_ACA_OBR_EXT_ASA_BAR_PER_PIN_PERGOLAS.csv": TipoEstructuraIngenieria.COMPLETA,
    "INGENIERIA_-_ALAMO_18__-_PISOS.csv": TipoEstructuraIngenieria.COMPLETA,
    "INGENIERIA_-_ALAMO_18__-_AJU_PB.csv": TipoEstructuraIngenieria.SUELTA,
    "INGENIERIA_-_ALAMO_18__-_AJU_PISOS.csv": TipoEstructuraIngenieria.SUELTA,
    "INGENIERIA_-_ALAMO_18__-_CENTRO_DE_CARGA.csv": TipoEstructuraIngenieria.SUELTA,
    "INGENIERIA_-_ALAMO_18__-_AJU_PIEDRA_CERRO_INTERIOR.csv": TipoEstructuraIngenieria.SUELTA,
    "INGENIERIA_-_ALAMO_18__-_CEMENTO_EXTRA_EN_FACHADA_POR_AJUSTE_DEL_NUEVO_RENDIMIENTO.csv": (
        TipoEstructuraIngenieria.CON_CONCEPTO
    ),
    # Discrepancia #1 (ya encontrada): el cerebro documenta esta estructura
    # como "5 columnas, sin clave, sin precio" — el archivo real trae 7
    # columnas, CON agrupador NIV-/ECO-, y una sola línea sin clave/precio.
    "INGENIERIA_-_ALAMO_18__-_AJU._GUALDRA_PB.csv": TipoEstructuraIngenieria.SIN_COSTEAR,
    # Discrepancia #2 (ya encontrada): el cerebro documenta 6 columnas —
    # el archivo real trae 5.
    "INGENIERIA_-_ALAMO_18__CIM_CAMARAS.csv": TipoEstructuraIngenieria.AJENA,
}


def _leer(nombre: str):
    filas = leer_filas_crudas(INGENIERIA_ALAMO_18 / nombre)
    return leer_ingenieria_lote(filas)


@pytest.mark.parametrize("nombre,esperada", sorted(_ESTRUCTURA_ESPERADA.items()))
def test_estructura_de_cada_uno_de_los_once_archivos(nombre: str, esperada: TipoEstructuraIngenieria) -> None:
    assert len(_ESTRUCTURA_ESPERADA) == 11
    estructura, _, _, errores, _ = _leer(nombre)
    assert errores == (), [e.motivo for e in errores[:3]]
    assert estructura is esperada


def test_cim_camaras_tiene_5_columnas_no_6_como_dice_conocimiento() -> None:
    filas = leer_filas_crudas(INGENIERIA_ALAMO_18 / "INGENIERIA_-_ALAMO_18__CIM_CAMARAS.csv")
    assert {len(f) for f in filas} == {5}


def test_aju_gualdra_pb_tiene_7_columnas_no_5_como_dice_conocimiento() -> None:
    filas = leer_filas_crudas(INGENIERIA_ALAMO_18 / "INGENIERIA_-_ALAMO_18__-_AJU._GUALDRA_PB.csv")
    assert {len(f) for f in filas} == {7}
    estructura, insumos, _, _, pendientes = _leer("INGENIERIA_-_ALAMO_18__-_AJU._GUALDRA_PB.csv")
    assert estructura is TipoEstructuraIngenieria.SIN_COSTEAR
    # La única línea del archivo no tiene clave ni precio: no se carga como
    # insumo, y tampoco se pierde en silencio (§11.8).
    assert insumos == ()
    assert len(pendientes) == 1
    assert pendientes[0].valor_origen == "GUALDRA 6X12X14"


def test_particion_en_bloques_155_en_los_cuatro_archivos_grandes() -> None:
    """§11.8: "155 bloques de filas vacías... 151 con un agrupador detrás
    y 4 que cierran el archivo".

    Cada archivo real trae, además de las rachas de blancos ENTRE sus
    bloques de contenido, una racha de apertura (antes del primer bloque)
    y una de cierre (después del último) — verificado contra los 4
    archivos grandes: 159 rachas de blancos en total, 4 de ellas de
    apertura. Las 155 que SÍ son separador (§11.8) se parten en dos
    grupos: la racha que cierra el archivo (1 por archivo, 4 en total:
    nunca sigue nada, así que no participa de `abre_con_agrupador`) y las
    que están ENTRE dos bloques de contenido (`len(bloques) - 1` por
    archivo, 151 en total) — estas últimas, sin una sola excepción, están
    seguidas de un bloque cuya primera fila SÍ es un agrupador.
    """
    grandes = (
        "INGENIERIA_-_ALAMO_18_-_CIM.csv",
        "INGENIERIA_-_ALAMO_18__-_PB.csv",
        "INGENIERIA_-_ALAMO_18__-_PA_AZO_ACA_OBR_EXT_ASA_BAR_PER_PIN_PERGOLAS.csv",
        "INGENIERIA_-_ALAMO_18__-_PISOS.csv",
    )
    total_bloques = 0
    cierran_archivo = 0
    siguen_agrupador = 0
    for nombre in grandes:
        _, _, bloques, _, _ = _leer(nombre)
        total_bloques += len(bloques)
        cierran_archivo += 1  # la racha de cierre, siempre una por archivo
        # El primer bloque del archivo lo abre la racha de APERTURA (fuera
        # del conteo de 155); los demás los abre una racha ENTRE bloques.
        siguen_agrupador += sum(1 for b in bloques[1:] if b.abre_con_agrupador)

    assert total_bloques == 155
    assert siguen_agrupador == 151
    assert cierran_archivo == 4


def test_las_once_ingenierias_suman_1176_filas_390_claves_2604015_74() -> None:
    """Mismo número que `backend/core/tests/test_comparacion_alamo18.py`
    del cerebro (§11.8, la línea base de las once ingenierías)."""
    archivos = sorted(INGENIERIA_ALAMO_18.glob("*.csv"))
    assert len(archivos) == 11

    total_filas = 0
    total_importe = Decimal(0)
    claves: set[str] = set()
    for archivo in archivos:
        _, insumos, _, errores, _ = leer_ingenieria_lote(leer_filas_crudas(archivo))
        assert errores == (), [e.motivo for e in errores[:3]]
        for f in insumos:
            total_filas += 1
            total_importe += f.importe or Decimal(0)
            claves.add(f.clave)

    assert total_filas == 1176
    assert len(claves) == 390
    assert total_importe == Decimal("2604015.74")


def test_es_destajo_reconoce_los_prefijos_mo_de_la_cimentacion() -> None:
    _, insumos, _, _, _ = _leer("INGENIERIA_-_ALAMO_18_-_CIM.csv")
    destajos = {f.clave for f in insumos if f.es_destajo}
    assert len(destajos) == 38
    assert "MOC-12010" in destajos
    assert "MOS-2079" in destajos
    # Un material (no destajo) no debe colarse por parecido de prefijo.
    assert "ACE-00001" not in destajos
