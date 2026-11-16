"""Verifica los escalones de bastón que usa el elemento BA-1 contra los CSV de opus (Ola 4, lane 4D).

No es una prueba de CI (el cerebro no está en el repositorio): se corre a mano cuando cambia el catálogo.

    PYTHONPATH=src python scripts/verificar_baston_contra_csv.py /ruta/cerebro-erp-construccion/1-mundo/opus

Comprueba que (1) cada escalón del módulo existe en CATALOGO_DE_MATERIALES.csv con su largo y separación en la descripción, (2) su
composición (varilla 3/8 y alambre recocido) es la de ANALISIS_DE_BASICOS_CONCEPTOS.csv en la línea que el módulo cita, (3) no hay
en el CSV otro bastón de varilla 3/8 que el módulo no traiga, (4) los insumos de varilla y su peso existen y (5) la clave provisional
de un concepto nuevo no existe en ningún CSV. Sale con código 1 si algo no coincide.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

from obractrl.domain.cuantificacion.baston import (
    CLAVE_ALAMBRE,
    ESCALONES_DE_CATALOGO,
    VARILLAS,
    clave_provisional,
)


def _numero(texto: str) -> float:
    return float(texto.replace("$", "").replace(",", "") or 0)


def _lineas(carpeta: Path, nombre: str) -> list[list[str]]:
    with (carpeta / f"{nombre}.csv").open(encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f))


def main(carpeta: Path) -> int:
    errores: list[str] = []
    mat = _lineas(carpeta, "CATALOGO_DE_MATERIALES")
    ana = _lineas(carpeta, "ANALISIS_DE_BASICOS_CONCEPTOS")
    for clave, largo, sep, varilla, alambre, l_mat, l_var, l_alam in ESCALONES_DE_CATALOGO:
        f = mat[l_mat - 1]
        m = re.match(r'Bastones var 3/8" de ([\d.]+) @(\d+) cm', f[2].strip())
        if f[1] != clave or not m or abs(float(m[1]) - largo) > 1e-9 or int(m[2]) != sep:
            errores.append(f"{clave}: el módulo dice {largo} m @{sep} (línea {l_mat}), el CSV trae {f[1:3]}")
        for linea, insumo, cantidad in ((l_var, "ACR-00001", varilla), (l_alam, CLAVE_ALAMBRE, alambre)):
            g = ana[linea - 1]
            if g[0] != clave or g[1] != insumo or abs(_numero(g[4]) - cantidad) > 1e-9:
                errores.append(f"{clave} {insumo}: el módulo dice {cantidad} (línea {linea}), el CSV trae {g[:5]}")
    claves = {e[0] for e in ESCALONES_DE_CATALOGO}
    for i, f in enumerate(mat, 1):
        if f[1].startswith("AUX-02") and re.search(r'Bastones var 3/8"', f[2]) and f[1] not in claves:
            errores.append(f"{f[1]} (línea {i}): el CSV trae un bastón 3/8 que el módulo no tiene")
    for numero, (clave, nombre) in VARILLAS.items():
        f = next((r for r in mat if r[1] == clave), None)
        if f is None or f[2].strip() != f"VARILLA {nombre}":
            errores.append(f"{clave}: el módulo dice VARILLA {nombre}, el CSV trae {f[2] if f else 'nada'}")
    provisionales = {clave_provisional(n, e[1] * 100, e[2]) for n in VARILLAS for e in ESCALONES_DE_CATALOGO}
    for csv_ in sorted(carpeta.glob("*.csv")):
        texto = csv_.read_text(encoding="utf-8-sig")
        errores.extend(f"{k}: la clave provisional ya existe en {csv_.name}" for k in sorted(provisionales) if k in texto)
    for m in errores:
        print("DIFERENCIA", m)
    print("Todo coincide." if not errores else f"{len(errores)} diferencias.")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
