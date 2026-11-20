"""Verifica los datos del catálogo que usa la matriz de la losa (fase 2) contra los CSV de opus.

No es una prueba de CI (el cerebro no está en el repositorio): se corre a mano cuando cambia el catálogo.

    PYTHONPATH=src python scripts/verificar_losa_contra_csv.py /ruta/cerebro-erp-construccion/1-mundo/opus

Comprueba que (1) la parrilla de la losa maciza (AUX-06010) es la del CSV (insumo, cantidad y la línea que cita); (2) el concreto de entrepiso y de
azotea y la cimbra existen con la descripción que usa la matriz; (3) los destajos de losa candidatos existen en CATALOGO_DE_TRABAJOS con la descripción
y por m²; (4) **ninguna clave provisional** de concepto nuevo (EJ-800, EJ-801 y las 36 EJ-7xx de colado por ml) ni la de su destajo existe ya en el
catálogo (matrices, materiales, trabajos); (5) el catálogo **no trae** destajo para trabes, contratrabes ni nervaduras (la razón de que el destajo por ml
quede sin importe); y (6) cada auxiliar con que se paga el acero de un elemento (AUX-xxxxx) es un material del catálogo. Sale con código 1 si algo no coincide.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from obractrl.domain.cuantificacion.colado_por_ml import CLAVES_PROVISIONALES
from obractrl.domain.cuantificacion.elementos_lineales import elemento_estructural
from obractrl.domain.cuantificacion.matriz_de_losa import (
    CONCEPTOS_DE_LOSA,
    CONCRETO_POR_USO,
    DESTAJOS_DE_LOSA_DEL_CATALOGO,
    PARRILLA_DE_MACIZA,
)


def _numero(texto: str) -> float:
    return float(texto.replace("$", "").replace(",", "") or 0)


def _lineas(carpeta: Path, nombre: str) -> list[list[str]]:
    with (carpeta / f"{nombre}.csv").open(encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f))


def main(carpeta: Path) -> int:
    errores: list[str] = []
    compuestos = _lineas(carpeta, "ANALISIS_DE_BASICOS_COMPUESTOS")
    for insumo, _descripcion, _unidad, cantidad, linea in PARRILLA_DE_MACIZA["insumos"]:
        archivo, numero = linea.split(":")
        fila = compuestos[int(numero) - 1]
        if archivo != "ANALISIS_DE_BASICOS_COMPUESTOS" or fila[0] != PARRILLA_DE_MACIZA["clave"] or fila[1] != insumo or abs(_numero(fila[4]) - cantidad) > 1e-9:
            errores.append(f"{PARRILLA_DE_MACIZA['clave']} {insumo}: el módulo dice {cantidad} ({linea}), el CSV trae {fila[:5]}")
    del_csv = {f[1] for f in compuestos if f and f[0] == PARRILLA_DE_MACIZA["clave"]}
    if del_csv != {i[0] for i in PARRILLA_DE_MACIZA["insumos"]}:
        errores.append(f"{PARRILLA_DE_MACIZA['clave']}: el CSV trae los insumos {sorted(del_csv)} y el módulo no los repite igual")

    materiales = {f[1]: f for f in _lineas(carpeta, "CATALOGO_DE_MATERIALES") if len(f) > 4}
    for clave in (*CONCRETO_POR_USO.values(), "MAD-00001", PARRILLA_DE_MACIZA["clave"]):
        if clave not in materiales:
            errores.append(f"{clave}: no está en CATALOGO_DE_MATERIALES")
    if "(LOSAS ENTREPISO)" not in materiales.get(CONCRETO_POR_USO["entrepiso"], ["", "", ""])[2]:
        errores.append(f"{CONCRETO_POR_USO['entrepiso']}: su descripción ya no dice «LOSAS ENTREPISO»")
    if "AZOTEA" not in materiales.get(CONCRETO_POR_USO["azotea"], ["", "", ""])[2]:
        errores.append(f"{CONCRETO_POR_USO['azotea']}: su descripción ya no dice «AZOTEA»")

    trabajos = _lineas(carpeta, "CATALOGO_DE_TRABAJOS")
    por_clave = {f[3]: f for f in trabajos if len(f) > 7}
    for clave, descripcion in DESTAJOS_DE_LOSA_DEL_CATALOGO:
        fila = por_clave.get(clave)
        if fila is None or fila[4].strip() != descripcion or fila[7].strip().upper() != "M2":
            errores.append(f"{clave}: el módulo dice «{descripcion}» por M2 y el CSV trae {fila[4:8] if fila else 'nada'}")
    for f in trabajos:
        if len(f) > 4 and any(p in f[4].upper() for p in ("TRABE", "NERVADURA")):
            errores.append(f"{f[3]}: el catálogo ya trae un destajo de trabe o nervadura ({f[4]!r}): el D8 debe usarlo en lugar de dejar el destajo sin importe")

    ocupadas = {f[1] for nombre in ("CATALOGO_DE_MATRICES", "CATALOGO_DE_MATERIALES") for f in _lineas(carpeta, nombre) if len(f) > 1}
    ocupadas |= set(por_clave)
    provisionales = [c["clave"] for c in CONCEPTOS_DE_LOSA.values()] + list(CLAVES_PROVISIONALES.values())
    provisionales += [f"{c}-MO" for c in provisionales]
    for clave in provisionales:
        if clave in ocupadas:
            errores.append(f"{clave}: la clave provisional ya existe en el catálogo")

    for clave in CLAVES_PROVISIONALES:
        auxiliar = elemento_estructural(clave)["catalogo"][0]["clave"]  # type: ignore[index]
        if auxiliar not in materiales:
            errores.append(f"{clave}: su auxiliar {auxiliar} no está en CATALOGO_DE_MATERIALES")

    for m in errores:
        print("DIFERENCIA", m)
    print("Todo coincide." if not errores else f"{len(errores)} diferencias.")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
