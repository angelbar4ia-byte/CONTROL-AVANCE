"""Verifica los datos del catálogo que usan los muros de tabique contra los CSV de opus (Ola 3, lane 3C).

No es una prueba de CI (el cerebro no está en el repositorio): se corre a mano cuando cambia el catálogo.

    PYTHONPATH=src python scripts/verificar_tabique_contra_csv.py /ruta/cerebro-erp-construccion/1-mundo/opus

Comprueba que (1) la composición que el módulo guarda de EST-02010, EST-02011, EST-02020 y AUX-04010 es la del CSV (insumo,
cantidad y la línea del CSV que cita), (2) los destajos MOE-02010, MOE-02012 y MOE-02013 existen con su descripción y su costo,
(3) la mezcla MEZ-07010 lleva lo que el módulo dice y (4) las claves de los aparejos nuevos NO existen en ningún CSV. Sale con
código 1 si algo no coincide.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from obractrl.domain.cuantificacion.muro_tabique import (
    _MEZCLA_COMPUESTA,
    ELEMENTOS_DE_TABIQUE,
)


def _numero(texto: str) -> float:
    return float(texto.replace("$", "").replace(",", "") or 0)


def _lineas(carpeta: Path, nombre: str) -> list[list[str]]:
    with (carpeta / f"{nombre}.csv").open(encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f))


def main(carpeta: Path) -> int:
    errores: list[str] = []
    archivos = {n: _lineas(carpeta, n) for n in ("ANALISIS_DE_BASICOS_CONCEPTOS", "ANALISIS_DE_BASICOS_COMPUESTOS", "CATALOGO_DE_TRABAJOS")}
    for e in ELEMENTOS_DE_TABIQUE.values():
        for concepto, filas in e.catalogo:
            for insumo, cantidad, es_mo, costo, linea in filas:
                archivo, numero = linea.split(":")
                fila = archivos[archivo][int(numero) - 1]  # la línea 1 es el encabezado
                if fila[0] != concepto or fila[1] != insumo or abs(_numero(fila[4]) - cantidad) > 1e-9:
                    errores.append(f"{concepto} {insumo}: el módulo dice {cantidad} ({linea}), el CSV trae {fila[:5]}")
                if es_mo and abs(_numero(fila[5]) - float(costo or 0)) > 1e-9:
                    errores.append(f"{concepto} {insumo}: el costo del módulo es {costo} y el CSV trae {fila[5]}")
    for destajo in {c.destajo for e in ELEMENTOS_DE_TABIQUE.values() for c in e.conceptos if c.destajo}:
        clave, descripcion, _ = destajo
        fila = next((f for f in archivos["CATALOGO_DE_TRABAJOS"] if len(f) > 4 and f[3] == clave), None)
        if fila is None or fila[4].strip() != descripcion:
            errores.append(f"{clave}: la descripción del módulo es «{descripcion}» y el CSV trae {fila[4] if fila else 'nada'}")
    for clave, _, _, cantidad, linea in _MEZCLA_COMPUESTA:
        archivo, numero = linea.split(":")
        fila = archivos[archivo][int(numero) - 1]
        if fila[0] != "MEZ-07010" or fila[1] != clave or abs(_numero(fila[4]) - cantidad) > 1e-9:
            errores.append(f"MEZ-07010 {clave}: el módulo dice {cantidad} ({linea}), el CSV trae {fila[:5]}")
    nuevas = [c.clave for e in ELEMENTOS_DE_TABIQUE.values() for c in e.conceptos if c.nuevo]
    for csv_ in sorted(carpeta.glob("*.csv")):
        texto = csv_.read_text(encoding="utf-8-sig")
        errores.extend(f"{k}: la clave provisional ya existe en {csv_.name}" for k in nuevas if k in texto)
    for m in errores:
        print("DIFERENCIA", m)
    print("Todo coincide." if not errores else f"{len(errores)} diferencias.")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
