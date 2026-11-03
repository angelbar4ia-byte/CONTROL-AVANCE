"""El WBS (`Ingenieria ERP`) y el `Nivel ERP` se guardan pero no alteran el
árbol ya definido en el cerebro (D-615): con o sin esas dos columnas, el árbol
queda idéntico en padre, orden y conteos."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from obractrl.domain.cargadores.cabeceras import PRESUPUESTO, resolver_encabezados
from obractrl.domain.cargadores.cpu import agrupar_cuadrillas_matriz
from obractrl.domain.cargadores.presupuesto import TipoNodoPresupuesto, construir_arboles

_CSV = Path("/home/user/cerebro-erp-construccion/1-mundo/opus/CATALOGO_DE_PRESUPUESTO.csv")
_ANALISIS = Path("/home/user/cerebro-erp-construccion/1-mundo/opus/ANALISIS_DE_BASICOS_CONCEPTOS.csv")

pytestmark = pytest.mark.skipif(not _CSV.exists(), reason="Archivo real de OPUS no disponible.")


def _arboles(sin_wbs: bool):
    with _CSV.open(newline="", encoding="utf-8-sig") as f:
        todas = list(csv.reader(f))
    encabezados = todas[0]
    filas = [(n, r) for n, r in enumerate(todas[1:], start=2) if any(c.strip() for c in r)]
    if sin_wbs:
        for _, r in filas:
            r[encabezados.index("Nivel ERP")] = ""
            r[encabezados.index("Ingenieria ERP")] = ""
    mapa = resolver_encabezados(encabezados, PRESUPUESTO)
    arboles, errores, pendientes, _ = construir_arboles(filas, mapa)
    assert errores == () and pendientes == ()
    return arboles


def _forma(arboles) -> list:
    resultado = []
    for a in arboles:
        padre_de = {h.fila: p for p, hs in a.hijos.items() for h in hs}
        resultado.append(
            (
                a.clave_prototipo,
                [(n.fila, n.clave, n.tipo.value, padre_de.get(n.fila), n.indice) for n in _todos(a)],
            )
        )
    return resultado


def _todos(a):
    for hijos in a.hijos.values():
        yield from hijos


def test_con_o_sin_wbs_el_arbol_queda_identico_y_el_wbs_se_lee() -> None:
    con = _arboles(sin_wbs=False)
    sin = _arboles(sin_wbs=True)
    assert _forma(con) == _forma(sin)
    nodos = [n for a in con for n in _todos(a)]
    assert sum(1 for n in nodos if n.tipo is TipoNodoPresupuesto.CONCEPTO) == 2445
    assert sum(1 for n in nodos if n.wbs) > 3000  # se lee
    assert all(n.wbs is None and n.nivel_erp is None for a in sin for n in _todos(a))
    assert any(n.nivel_erp is not None for n in nodos)


@pytest.mark.skipif(not _ANALISIS.exists(), reason="Archivo real de OPUS no disponible.")
def test_las_39_cuadrillas_del_analisis_se_agrupan_con_sus_112_lineas() -> None:
    from obractrl.domain.cargadores.cabeceras import CPU_MATRIZ

    with _ANALISIS.open(newline="", encoding="utf-8-sig") as f:
        todas = list(csv.reader(f))
    mapa = resolver_encabezados(todas[0], CPU_MATRIZ)
    filas = [(n, r) for n, r in enumerate(todas[1:], start=2) if any(c.strip() for c in r)]
    claves = {
        r[mapa.indices["clave_padre"]].strip()
        for _, r in filas
        if r[mapa.indices["origen"]].strip() == "ManoDeObra"
    }
    bloques, errores, _ = agrupar_cuadrillas_matriz(
        filas, mapa, descripciones={c: (c, "JOR") for c in claves}
    )
    assert errores == ()
    assert len(bloques) == 39
    assert sum(len(b.componentes) for b in bloques) == 112
