"""`domain.cargadores.programa_base` — reglas puras de D-442/D-443.

Spec §7.5 (`ProgramaBase`) · cerebro `1-mundo/MODELO.md` §5c (D-442, D-443)
y `1-mundo/PROGRAMA-CPM.md`.

Dos grupos de pruebas:

- Sintéticas, hechas a mano: cada regla de D-442/D-443 por separado
  (autovínculo, formato, predecesora desconocida/sin partidas, bloque como
  predecesora leído "sin la sucesora", ciclo real, vínculo incumplido).
- Contra el archivo real (`PROGRAMA_ZAFIRO.xlsx`, repo de referencia
  adjunto, no versionado aquí): los conteos exactos del bloque de
  `CAS-00004`, la misma prueba de cuadratura que
  `tests/domain/test_presupuesto_opus_real.py` hace para el árbol de
  presupuesto.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from obractrl.domain.cargadores.cabeceras import PROGRAMA_BASE, resolver_encabezados
from obractrl.domain.cargadores.programa_base import (
    TokenVinculo,
    leer_programa_base,
    leer_vinculos,
    resolver_vinculos,
)

_ENCABEZADOS = [
    "Tipo", "Nivel ", "Indice", "Clave", "Descripción", "Vínculos",
    "Fecha de inicio", "Fecha de término", "Días laborables",
]


def _mapa():
    return resolver_encabezados(_ENCABEZADOS, PROGRAMA_BASE)


def _filas_de(tabla: list[list[object]]) -> list[tuple[int, list[object]]]:
    return list(enumerate(tabla, start=2))


# --- `leer_vinculos` -------------------------------------------------------


def test_separa_varios_tokens_y_convierte_horas_a_dias() -> None:
    tokens = leer_vinculos("80SF, 68SS+120.00000")
    assert tokens == (
        TokenVinculo(texto="80SF", fila_predecesora=80, tipo="SF", lag_dias=0.0),
        TokenVinculo(texto="68SS+120.00000", fila_predecesora=68, tipo="SS", lag_dias=15.0),
    )


def test_un_token_mal_escrito_no_tumba_a_los_demas() -> None:
    tokens = leer_vinculos("80SF, no-es-un-token, 68FS")
    assert tokens[0].fila_predecesora == 80
    assert tokens[1] == TokenVinculo(texto="no-es-un-token", fila_predecesora=None)
    assert tokens[2].fila_predecesora == 68


# --- `leer_programa_base`: bloques y `ruta` --------------------------------


def _archivo_dos_prototipos() -> list[list[object]]:
    return [
        ["Capítulo", 0, 1, "CAS-1", "Prototipo 1", None, date(2025, 1, 6), date(2025, 1, 10), 5],
        ["Subcapítulo", 1, 1, "NIV-1", "Nivel 1", None, date(2025, 1, 6), date(2025, 1, 10), 5],
        ["Nivel 2", 2, 1, "ECO-1", "Etapa 1", None, date(2025, 1, 6), date(2025, 1, 7), 2],
        ["Concepto", 3, 1, "EST-1", "Concepto A", None, date(2025, 1, 6), date(2025, 1, 7), 2],
        ["Nivel 2", 2, 2, "ECO-2", "Etapa 2", None, date(2025, 1, 8), date(2025, 1, 10), 3],
        ["Concepto", 3, 1, "EST-1", "Concepto A otra vez", None, date(2025, 1, 8), date(2025, 1, 10), 3],
        ["Capítulo", 0, 2, "CAS-2", "Prototipo 2", None, date(2025, 1, 6), date(2025, 1, 6), 1],
        ["Subcapítulo", 1, 1, "NIV-9", "Nivel 1 de CAS-2", None, date(2025, 1, 6), date(2025, 1, 6), 1],
        ["Concepto", 2, 1, "EST-1", "Concepto A de otro prototipo", None, date(2025, 1, 6), date(2025, 1, 6), 1],
    ]


def test_separa_el_archivo_en_un_bloque_por_capitulo() -> None:
    bloques, errores = leer_programa_base(_filas_de(_archivo_dos_prototipos()), _mapa())
    assert errores == ()
    assert [b.clave_prototipo for b in bloques] == ["CAS-1", "CAS-2"]
    assert len(bloques[0].filas) == 6
    assert len(bloques[1].filas) == 3


def test_la_misma_clave_bajo_dos_padres_distintos_tiene_ruta_distinta() -> None:
    """`EST-1` cuelga de `ECO-1` y de `ECO-2` dentro del MISMO prototipo
    (`CAS-1`) — igual que el bug real de `EST-02010` en Zafiro (ver
    `tests/integracion/test_cargas_endtoend.py::
    test_una_clave_de_concepto_repetida_en_dos_etapas_del_mismo_prototipo_no_se_pisan`).
    `ruta` las distingue; una clave sola no podría."""
    bloques, _ = leer_programa_base(_filas_de(_archivo_dos_prototipos()), _mapa())
    cas1 = bloques[0]
    partidas_est1 = [f for f in cas1.partidas if f.clave == "EST-1"]
    assert len(partidas_est1) == 2
    assert partidas_est1[0].ruta == ("NIV-1", "ECO-1", "EST-1")
    assert partidas_est1[1].ruta == ("NIV-1", "ECO-2", "EST-1")
    assert partidas_est1[0].ruta != partidas_est1[1].ruta

    # La misma clave en el prototipo CAS-2 es una `ruta` completamente
    # distinta — el bloque se reinicia en cada Capítulo.
    cas2 = bloques[1]
    assert cas2.partidas[0].ruta == ("NIV-9", "EST-1")


def test_un_tipo_desconocido_se_reporta_y_el_resto_del_archivo_entra() -> None:
    tabla = _archivo_dos_prototipos()
    tabla[2][0] = "Bloque Raro"  # la fila de ECO-1
    bloques, errores = leer_programa_base(_filas_de(tabla), _mapa())
    assert len(errores) == 1
    assert errores[0].fila == 4  # fila 2 (encabezado) + índice de la lista
    assert errores[0].columna == "tipo"
    # El resto del archivo se sigue leyendo (§9.3): los otros 5 renglones de
    # CAS-1 y los 3 de CAS-2 quedan igual.
    total_filas = sum(len(b.filas) for b in bloques)
    assert total_filas == 8


def test_solo_un_concepto_con_fecha_y_dias_positivos_es_partida() -> None:
    tabla = [
        ["Capítulo", 0, 1, "CAS-1", "Prototipo", None, date(2025, 1, 6), date(2025, 1, 6), 1],
        # Concepto sin fecha: no es partida.
        ["Concepto", 1, 1, "EST-1", "Sin fecha", None, None, None, 0],
        # Concepto con fecha pero 0 días: no es partida (hueco de numeración).
        ["Concepto", 1, 2, "EST-2", "Cero días", None, date(2025, 1, 6), date(2025, 1, 6), 0],
        # Concepto real.
        ["Concepto", 1, 3, "EST-3", "Partida real", None, date(2025, 1, 6), date(2025, 1, 7), 2],
    ]
    bloques, errores = leer_programa_base(_filas_de(tabla), _mapa())
    assert errores == ()
    assert [f.clave for f in bloques[0].partidas] == ["EST-3"]


# --- `resolver_vinculos`: D-442/D-443 --------------------------------------


def _bloque_simple(vinculos_fila3: str = "") -> list[list[object]]:
    """Tres partidas en cadena: fila 2 → fila 3 → fila 4."""
    return [
        ["Capítulo", 0, 1, "CAS-1", "Prototipo", None, date(2025, 1, 6), date(2025, 1, 10), 5],
        ["Concepto", 1, 1, "A", "Partida A", None, date(2025, 1, 6), date(2025, 1, 7), 2],
        ["Concepto", 1, 2, "B", "Partida B", vinculos_fila3, date(2025, 1, 8), date(2025, 1, 9), 2],
        ["Concepto", 1, 3, "C", "Partida C", "4FS", date(2025, 1, 10), date(2025, 1, 10), 1],
    ]


# Números de fila reales de `_bloque_simple` (base 1, contando el
# encabezado): Capítulo=2, A=3, B=4 (el parámetro `vinculos_fila3`, a pesar
# del nombre, cae en la fila 4 — "B, la segunda partida"), C=5.


def test_un_vinculo_bien_formado_se_acepta() -> None:
    bloques, _ = leer_programa_base(_filas_de(_bloque_simple("3FS")), _mapa())
    resuelto = resolver_vinculos(bloques[0])
    assert resuelto.rechazos == ()
    assert len(resuelto.dependencias) == 2  # 3->4 (FS, B depende de A) y 4->5 (FS, C depende de B)
    dep = next(d for d in resuelto.dependencias if d.fila_sucesora == 4)
    assert dep.fila_predecesora == 3
    assert dep.tipo == "FS"
    assert dep.lag_dias == 0.0


def test_un_token_mal_formado_se_rechaza_como_formato() -> None:
    bloques, _ = leer_programa_base(_filas_de(_bloque_simple("no-es-un-token")), _mapa())
    resuelto = resolver_vinculos(bloques[0])
    assert [r.motivo for r in resuelto.rechazos] == ["formato"]


def test_el_autovinculo_se_rechaza() -> None:
    bloques, _ = leer_programa_base(_filas_de(_bloque_simple("4FS")), _mapa())
    resuelto = resolver_vinculos(bloques[0])
    rechazo = next(r for r in resuelto.rechazos if r.fila_sucesora == 4)
    assert rechazo.motivo == "autovinculo"


def test_una_predecesora_que_no_existe_se_rechaza() -> None:
    bloques, _ = leer_programa_base(_filas_de(_bloque_simple("999FS")), _mapa())
    resuelto = resolver_vinculos(bloques[0])
    rechazo = next(r for r in resuelto.rechazos if r.fila_sucesora == 4)
    assert rechazo.motivo == "predecesora_desconocida"


def test_un_vinculo_en_una_fila_que_no_es_partida_se_rechaza_como_sucesora_bloque() -> None:
    tabla = [
        ["Capítulo", 0, 1, "CAS-1", "Prototipo", None, date(2025, 1, 6), date(2025, 1, 10), 5],
        ["Concepto", 1, 1, "A", "Partida A", None, date(2025, 1, 6), date(2025, 1, 7), 2],
        # Nivel 2 con Vínculos (no es partida): se rechaza, nunca se adopta.
        ["Nivel 2", 1, 2, "ECO-1", "Etapa", "2FS", date(2025, 1, 8), date(2025, 1, 9), 2],
    ]
    bloques, _ = leer_programa_base(_filas_de(tabla), _mapa())
    resuelto = resolver_vinculos(bloques[0])
    assert [r.motivo for r in resuelto.rechazos] == ["sucesora_bloque"]


def test_un_bloque_como_predecesora_se_resuelve_a_su_partida_extrema_sin_la_sucesora() -> None:
    """D-442/D-443: el bloque se lee "sin la sucesora". `FS`/`FF` toman la
    partida con el `término` más tardío del bloque; aquí hay dos hijas
    (D y E) y la sucesora (F) también cuelga del mismo bloque — su propio
    término no debe competir."""
    tabla = [
        ["Capítulo", 0, 1, "CAS-1", "Prototipo", None, date(2025, 1, 6), date(2025, 1, 20), 10],
        ["Subcapítulo", 1, 1, "NIV-1", "Bloque", None, date(2025, 1, 6), date(2025, 1, 20), 10],
        ["Concepto", 2, 1, "D", "Hija temprana", None, date(2025, 1, 6), date(2025, 1, 7), 2],
        ["Concepto", 2, 2, "E", "Hija tardía", None, date(2025, 1, 8), date(2025, 1, 10), 3],
        # F depende del BLOQUE (fila 3, NIV-1), no de una partida directa.
        ["Concepto", 2, 3, "F", "Sucesora", "3FS", date(2025, 1, 15), date(2025, 1, 20), 5],
    ]
    bloques, _ = leer_programa_base(_filas_de(tabla), _mapa())
    resuelto = resolver_vinculos(bloques[0])
    assert resuelto.rechazos == ()
    dep = resuelto.dependencias[0]
    assert dep.fila_sucesora == 6  # F
    assert dep.fila_predecesora == 5  # E: término más tardío entre D y E


def test_un_bloque_sin_ninguna_partida_propia_se_rechaza() -> None:
    tabla = [
        ["Capítulo", 0, 1, "CAS-1", "Prototipo", None, date(2025, 1, 6), date(2025, 1, 10), 5],
        ["Subcapítulo", 1, 1, "NIV-1", "Bloque vacío", None, date(2025, 1, 6), date(2025, 1, 6), 0],
        # La única partida bajo NIV-1 es ella misma: "sin la sucesora" no
        # deja ninguna candidata.
        ["Concepto", 2, 1, "A", "Única hija, es la propia sucesora", "3FS", date(2025, 1, 6), date(2025, 1, 7), 1],
    ]
    bloques, _ = leer_programa_base(_filas_de(tabla), _mapa())
    resuelto = resolver_vinculos(bloques[0])
    assert [r.motivo for r in resuelto.rechazos] == ["predecesora_sin_partidas"]


def test_un_ciclo_real_rechaza_el_vinculo_con_holgura_negativa() -> None:
    """Dos partidas que se citan mutuamente (A depende de B con FS, B
    depende de A con SS) forman un ciclo real; D-442/D-443 rechaza el que
    las fechas del propio archivo ya contradicen."""
    tabla = [
        ["Capítulo", 0, 1, "CAS-1", "Prototipo", None, date(2025, 1, 6), date(2025, 1, 20), 10],
        # A (fila 3): 6-ene a 11-ene, depende de B (fila 4) con FS (B debe
        # terminar antes de que A arranque) — pero B termina el 17,
        # DESPUÉS: holgura negativa.
        ["Concepto", 1, 1, "A", "A", "4FS", date(2025, 1, 6), date(2025, 1, 11), 4],
        # B (fila 4): 11-ene a 17-ene, depende de A con SS+0 — consistente
        # (B arranca el mismo día que A, holgura 0).
        ["Concepto", 1, 2, "B", "B", "3SS", date(2025, 1, 11), date(2025, 1, 17), 5],
    ]
    bloques, _ = leer_programa_base(_filas_de(tabla), _mapa())
    resuelto = resolver_vinculos(bloques[0])
    assert len(resuelto.rechazos) == 1
    assert resuelto.rechazos[0].motivo == "cierra_un_ciclo"
    # El que se rechaza es el de A (depende de B, FS) — el que la holgura
    # ya contradecía — no el de B.
    assert resuelto.rechazos[0].fila_sucesora == 3
    assert len(resuelto.dependencias) == 1
    assert resuelto.dependencias[0].fila_sucesora == 4


def test_un_vinculo_incumplido_se_carga_igual_marcado_como_alerta() -> None:
    """Holgura negativa que NO cierra ningún ciclo: D-442/D-443 lo carga
    igual, solo lo marca."""
    tabla = [
        ["Capítulo", 0, 1, "CAS-1", "Prototipo", None, date(2025, 1, 6), date(2025, 1, 20), 10],
        ["Concepto", 1, 1, "A", "A", None, date(2025, 1, 6), date(2025, 1, 11), 4],
        # B (fila 4) depende de A (fila 3) con FS pero arranca el mismo día
        # que A termina, sin esperar un día completo: holgura = -1.
        ["Concepto", 1, 2, "B", "B", "3FS", date(2025, 1, 11), date(2025, 1, 12), 2],
    ]
    bloques, _ = leer_programa_base(_filas_de(tabla), _mapa())
    resuelto = resolver_vinculos(bloques[0])
    assert resuelto.rechazos == ()
    assert len(resuelto.dependencias) == 1
    assert len(resuelto.incumplidos) == 1
    assert resuelto.incumplidos[0].holgura < 0


# --- Contra el archivo real -------------------------------------------------

_ARCHIVO_REAL = Path(
    "/home/user/cerebro-erp-construccion/1-mundo/fuentes/programa/PROGRAMA_ZAFIRO.xlsx"
)


@pytest.mark.skipif(
    not _ARCHIVO_REAL.exists(),
    reason=f"Archivo real del programa no disponible en este entorno: {_ARCHIVO_REAL}",
)
def test_el_archivo_real_de_zafiro_cuadra_contra_los_conteos_verificados() -> None:
    """Mismo criterio que `test_presupuesto_opus_real.py`: un fixture
    escrito a mano no prueba nada que el propio fixture no haya ya
    decidido — esto se verifica contra el archivo real."""
    import openpyxl

    libro = openpyxl.load_workbook(_ARCHIVO_REAL, data_only=True, read_only=True)
    try:
        hoja = libro["Hoja1"]
        filas_crudas = hoja.iter_rows(values_only=True)
        encabezados = next(filas_crudas)
        mapa = resolver_encabezados(encabezados, PROGRAMA_BASE)
        filas = list(enumerate(filas_crudas, start=2))
    finally:
        libro.close()

    bloques, errores = leer_programa_base(filas, mapa)
    assert errores == ()
    assert len(bloques) == 7  # los siete prototipos de Zafiro, apilados

    cas4 = next(b for b in bloques if b.clave_prototipo == "CAS-00004")
    assert len(cas4.partidas) == 315

    resuelto = resolver_vinculos(cas4)
    assert len(resuelto.dependencias) == 70
    assert len(resuelto.rechazos) == 5
    assert {r.motivo for r in resuelto.rechazos} == {"autovinculo", "cierra_un_ciclo"}
    assert sum(1 for r in resuelto.rechazos if r.motivo == "autovinculo") == 1
    assert sum(1 for r in resuelto.rechazos if r.motivo == "cierra_un_ciclo") == 4
    assert len(resuelto.incumplidos) == 16
