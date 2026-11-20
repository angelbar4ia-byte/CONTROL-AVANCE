"""Verifica los datos del catálogo que usa el muro de sillar amarillo BAP-01010 contra los CSV de opus.

No es una prueba de CI (el cerebro no está en el repositorio): se corre a mano cuando cambia el catálogo.

    PYTHONPATH=src python scripts/verificar_sillar_contra_csv.py /ruta/cerebro-erp-construccion/1-mundo/opus

Comprueba que (1) la composición que el módulo guarda de BAP-01010 es la del CSV (insumo, cantidad y la línea que cita), (2) la pieza PET-00008
existe con su descripción y su unidad, (3) el destajo MOE-02016 existe con su descripción y su costo, (4) BAP-01010 es una matriz del catálogo
(CATALOGO_DE_MATRICES) con la descripción que usa el elemento y su unidad, y (5) la pieza mide lo que dice la descripción del concepto
(19x25x45). Sale con código 1 si algo no coincide.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from obractrl.domain.cuantificacion.muro_sillar import (
    _COMPOSICION_DEL_CATALOGO,
    CLAVE_DEL_ELEMENTO,
    CLAVE_PIEZA,
    ELEMENTOS_DE_SILLAR,
)


def _numero(texto: str) -> float:
    return float(texto.replace("$", "").replace(",", "") or 0)


def _lineas(carpeta: Path, nombre: str) -> list[list[str]]:
    with (carpeta / f"{nombre}.csv").open(encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f))


def main(carpeta: Path) -> int:
    errores: list[str] = []
    conceptos = _lineas(carpeta, "ANALISIS_DE_BASICOS_CONCEPTOS")
    for insumo, cantidad, _, costo, linea in _COMPOSICION_DEL_CATALOGO:
        archivo, numero = linea.split(":")
        if archivo != "ANALISIS_DE_BASICOS_CONCEPTOS":
            errores.append(f"{insumo}: la línea citada es de {archivo}, no de la composición del concepto")
            continue
        fila = conceptos[int(numero) - 1]  # la línea 1 es el encabezado
        if fila[0] != CLAVE_DEL_ELEMENTO or fila[1] != insumo or abs(_numero(fila[4]) - cantidad) > 1e-9:
            errores.append(f"{CLAVE_DEL_ELEMENTO} {insumo}: el módulo dice {cantidad} ({linea}), el CSV trae {fila[:5]}")
        if costo is not None and abs(_numero(fila[5]) - costo) > 1e-9:
            errores.append(f"{CLAVE_DEL_ELEMENTO} {insumo}: el costo del módulo es {costo} y el CSV trae {fila[5]}")
    composicion_del_csv = {f[1] for f in conceptos if f and f[0] == CLAVE_DEL_ELEMENTO}
    if composicion_del_csv != {i for i, *_ in _COMPOSICION_DEL_CATALOGO}:
        errores.append(f"{CLAVE_DEL_ELEMENTO}: el CSV trae los insumos {sorted(composicion_del_csv)} y el módulo no los repite igual")

    materiales = _lineas(carpeta, "CATALOGO_DE_MATERIALES")
    pieza = next((f for f in materiales if len(f) > 4 and f[1] == CLAVE_PIEZA), None)
    if pieza is None or pieza[2].strip() != "SILLAR 19X25X45 AMARILLO" or pieza[4].strip() != "PZ":
        errores.append(f"{CLAVE_PIEZA}: el módulo dice «SILLAR 19X25X45 AMARILLO» en PZ y el CSV trae {pieza[:5] if pieza else 'nada'}")

    e = ELEMENTOS_DE_SILLAR[CLAVE_DEL_ELEMENTO]
    medidas = f"{e.espesor_cm:g}x{e.alto_cm:g}x{e.largo_cm:g}"
    if pieza is not None and medidas.upper() not in pieza[2].upper():
        errores.append(f"{CLAVE_PIEZA}: las medidas del módulo ({medidas}) no salen de la descripción {pieza[2]!r}")

    destajo_clave, destajo_descripcion, _ = e.destajo
    trabajos = _lineas(carpeta, "CATALOGO_DE_TRABAJOS")
    fila = next((f for f in trabajos if len(f) > 4 and f[3] == destajo_clave), None)
    if fila is None or fila[4].strip() != destajo_descripcion:
        errores.append(f"{destajo_clave}: la descripción del módulo es «{destajo_descripcion}» y el CSV trae {fila[4] if fila else 'nada'}")

    matrices = _lineas(carpeta, "CATALOGO_DE_MATRICES")
    matriz = next((f for f in matrices if len(f) > 4 and f[1] == CLAVE_DEL_ELEMENTO), None)
    if matriz is None:
        errores.append(f"{CLAVE_DEL_ELEMENTO}: no es una matriz del catálogo (regla F7: el elemento debe tener su concepto)")
    else:
        if not matriz[2].startswith(e.concepto_descripcion):
            errores.append(f"{CLAVE_DEL_ELEMENTO}: la descripción del módulo no abre la del catálogo: {matriz[2]!r}")
        if matriz[3].strip().lower() != "m2":
            errores.append(f"{CLAVE_DEL_ELEMENTO}: la unidad del módulo es m2 y el CSV trae {matriz[3]!r}")

    for m in errores:
        print("DIFERENCIA", m)
    print("Todo coincide." if not errores else f"{len(errores)} diferencias.")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
