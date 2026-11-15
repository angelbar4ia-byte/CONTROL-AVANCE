"""Verifica los datos del catálogo que usan los elementos de estructura contra los CSV de opus (Ola 3, lane 3A).

No es una prueba de CI (el cerebro no está en el repositorio): se corre a mano cuando cambia el catálogo.

    PYTHONPATH=src python scripts/verificar_estructura_contra_csv.py /ruta/cerebro-erp-construccion/1-mundo/opus

Comprueba que (1) cada concepto de colado y de acero que los elementos nombran existe en el catálogo con la unidad que el
elemento supone, (2) los coeficientes `antes` de las correcciones son los que suman los renglones del CSV y (3) los consumos de
cimbra y el concreto de los colados son los del catálogo. Sale con código 1 si algo no coincide.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

from obractrl.domain.cuantificacion.correcciones_de_catalogo import (
    COEFICIENTES_DEL_CATALOGO,
)
from obractrl.domain.cuantificacion.estructura_de_catalogo import (
    ELEMENTOS_DE_ESTRUCTURA,
    claves_de_concepto,
    insumos_del_concepto,
)


def _numero(texto: str) -> float:
    return float(texto.replace("$", "").replace(",", "") or 0)


def main(carpeta: Path) -> int:
    composicion: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    with (carpeta / "ANALISIS_DE_BASICOS_CONCEPTOS.csv").open(encoding="utf-8-sig", newline="") as f:
        for fila in csv.DictReader(f):
            if fila["Tipo"] in ("Material", "Flete"):
                composicion[fila["Clave Padre"]][fila["Clave Hijo"]] += _numero(fila["Cantidad"])
    unidades: dict[str, str] = {}
    with (carpeta / "CATALOGO_DE_MATRICES.csv").open(encoding="utf-8-sig", newline="") as f:
        for fila in csv.reader(f):
            if len(fila) > 3 and fila[1]:
                unidades[fila[1]] = fila[3]
    errores: list[str] = []
    for (concepto, insumo), antes in COEFICIENTES_DEL_CATALOGO.items():
        real = composicion[concepto].get(insumo)
        if real is None or abs(real - antes) > 1e-4:
            errores.append(f"{concepto} {insumo}: el módulo dice {antes}, el CSV suma {real}")
    for e in ELEMENTOS_DE_ESTRUCTURA.values():
        for c in e.conceptos:
            if c.nuevo:
                continue
            for clave in ([x.clave for x in c.escalones] or [c.clave]):
                if clave not in unidades:
                    errores.append(f"{e.clave}: el concepto {clave} no está en CATALOGO_DE_MATRICES.csv")
                elif unidades[clave].lower() != c.unidad:
                    errores.append(f"{e.clave}: {clave} es «{unidades[clave]}» en el catálogo y el elemento supone «{c.unidad}»")
        # El colado: el consumo de cimbra y el concreto del catálogo (el concreto del aparente se corrige a propósito).
        for c in e.conceptos:
            if c.ranura == "colado" and c.clave and not c.nuevo and not e.forro:
                calc = insumos_del_concepto(e, c, 3.0)
                for insumo, q in calc.items():
                    real = composicion[c.clave].get(insumo)
                    if real is None or abs(real - q) > 5e-5 + 0.0 * q:
                        errores.append(f"{c.clave} {insumo}: el elemento calcula {q:.6f}, el catálogo trae {real}")
    for e in ELEMENTOS_DE_ESTRUCTURA.values():
        faltan = [c for c in claves_de_concepto(e) if c not in composicion and c not in unidades and c != "EJ-780"]
        for c in faltan:
            errores.append(f"{e.clave}: {c} no existe en los CSV")
    for m in errores:
        print("DIFERENCIA", m)
    print("Todo coincide." if not errores else f"{len(errores)} diferencias.")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
