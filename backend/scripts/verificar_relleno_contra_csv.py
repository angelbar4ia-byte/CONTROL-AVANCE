"""Verifica los datos del catálogo que usa el relleno (Fase 3) contra los CSV de opus.

No es una prueba de CI (el cerebro no está en el repositorio): se corre a mano cuando cambia el catálogo.

    PYTHONPATH=src python scripts/verificar_relleno_contra_csv.py /ruta/cerebro-erp-construccion/1-mundo/opus

Comprueba que (1) el concepto existente ALB-03014 (el del relleno de azotea) está en CATALOGO_DE_MATRICES por m² con la descripción que usa el módulo; (2) su
composición (ANALISIS_DE_BASICOS_CONCEPTOS) trae el tezontle PET-00069 (0.012857 viaje), el mortero CON-00020 (0.0735 m³) y el destajo MOA-05012, con las
líneas que cita el módulo; (3) el tezontle se vende por viaje de 7 m³ («7 MTS») y los dos materiales existen en CATALOGO_DE_MATERIALES con su unidad;
(4) el destajo existe en CATALOGO_DE_TRABAJOS por M2; (5) el espesor medio que implica el catálogo es el que usa el módulo (9 cm); y (6) la clave
provisional del compactado (EJ-810) y su destajo no existen ya en el catálogo (matrices, materiales, trabajos), y el catálogo sigue sin traer material de banco,
tepetate ni destajo de compactación (la razón de que el compactado no calcule insumos). Sale con código 1 si algo no coincide.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from obractrl.domain.cuantificacion.relleno import (
    CONCEPTO_AZOTEA,
    CONCEPTOS_DE_RELLENO,
    DESTAJO_AZOTEA,
    ESPESOR_DEL_CATALOGO_M,
    MORTERO_AZOTEA,
    TEZONTLE,
)


def _numero(texto: str) -> float:
    return float(texto.replace("$", "").replace(",", "") or 0)


def _lineas(carpeta: Path, nombre: str) -> list[list[str]]:
    with (carpeta / f"{nombre}.csv").open(encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f))


def main(carpeta: Path) -> int:
    errores: list[str] = []
    matrices = {f[1]: f for f in _lineas(carpeta, "CATALOGO_DE_MATRICES") if len(f) > 4}
    fila = matrices.get(CONCEPTO_AZOTEA["clave"])
    if fila is None:
        errores.append(f"{CONCEPTO_AZOTEA['clave']}: no está en CATALOGO_DE_MATRICES")
    elif not fila[2].startswith(CONCEPTO_AZOTEA["descripcion"]) or fila[3].strip().lower() != "m2":
        errores.append(f"{CONCEPTO_AZOTEA['clave']}: el módulo dice «{CONCEPTO_AZOTEA['descripcion']}» por m² y el CSV trae {fila[2:4]}")

    conceptos = _lineas(carpeta, "ANALISIS_DE_BASICOS_CONCEPTOS")
    esperado = (
        (TEZONTLE["clave"], TEZONTLE["por_m2_del_catalogo"], TEZONTLE["fuente"]),
        (MORTERO_AZOTEA["clave"], MORTERO_AZOTEA["por_m2_del_catalogo"], MORTERO_AZOTEA["fuente"]),
        (DESTAJO_AZOTEA["clave"], 1.0, DESTAJO_AZOTEA["fuente"]),
    )
    for hijo, cantidad, linea in esperado:
        archivo, numero = linea.split(":")
        fila_c = conceptos[int(numero) - 1] if archivo == "ANALISIS_DE_BASICOS_CONCEPTOS" and int(numero) <= len(conceptos) else []
        if len(fila_c) < 5 or fila_c[0] != CONCEPTO_AZOTEA["clave"] or fila_c[1] != hijo or abs(_numero(fila_c[4]) - cantidad) > 1e-9:
            errores.append(f"{CONCEPTO_AZOTEA['clave']} {hijo}: el módulo dice {cantidad} ({linea}), el CSV trae {fila_c[:5]}")
    del_csv = {f[1] for f in conceptos if f and f[0] == CONCEPTO_AZOTEA["clave"]}
    if del_csv != {t[0] for t in esperado}:
        errores.append(f"{CONCEPTO_AZOTEA['clave']}: el CSV trae los insumos {sorted(del_csv)} y el módulo no los repite igual")

    materiales = {f[1]: f for f in _lineas(carpeta, "CATALOGO_DE_MATERIALES") if len(f) > 4}
    for dato in (TEZONTLE, MORTERO_AZOTEA):
        m = materiales.get(dato["clave"])
        if m is None or m[2].strip() != dato["descripcion"] or m[4].strip().upper() != dato["unidad"].upper().replace("³", "3"):
            errores.append(f"{dato['clave']}: el módulo dice «{dato['descripcion']}» en {dato['unidad']} y el CSV trae {m[2:5] if m else 'nada'}")
    if f"{TEZONTLE['m3_por_viaje']:g} MTS" not in materiales.get(TEZONTLE["clave"], ["", "", ""])[2]:
        errores.append(f"{TEZONTLE['clave']}: su descripción ya no dice «{TEZONTLE['m3_por_viaje']:g} MTS» (el viaje de {TEZONTLE['m3_por_viaje']:g} m³)")
    if abs(TEZONTLE["por_m2_del_catalogo"] * TEZONTLE["m3_por_viaje"] - ESPESOR_DEL_CATALOGO_M) > 1e-4:
        errores.append("el espesor medio del catálogo (viajes por m² × m³ por viaje) ya no es el que usa el módulo")

    trabajos = {f[3]: f for f in _lineas(carpeta, "CATALOGO_DE_TRABAJOS") if len(f) > 7}
    d = trabajos.get(DESTAJO_AZOTEA["clave"])
    if d is None or d[4].strip() != DESTAJO_AZOTEA["descripcion"] or d[7].strip().upper() != "M2":
        errores.append(f"{DESTAJO_AZOTEA['clave']}: el módulo dice «{DESTAJO_AZOTEA['descripcion']}» por M2 y el CSV trae {d[4:8] if d else 'nada'}")

    ocupadas = {f[1] for nombre in ("CATALOGO_DE_MATRICES", "CATALOGO_DE_MATERIALES") for f in _lineas(carpeta, nombre) if len(f) > 1} | set(trabajos)
    provisional = CONCEPTOS_DE_RELLENO["compactado"]["clave"]
    for clave in (provisional, f"{provisional}-MO"):
        if clave in ocupadas:
            errores.append(f"{clave}: la clave provisional ya existe en el catálogo")
    for nombre in ("CATALOGO_DE_MATRICES", "CATALOGO_DE_MATERIALES", "CATALOGO_DE_TRABAJOS"):
        for f in _lineas(carpeta, nombre):
            texto = " ".join(f[:6]).upper()
            if any(p in texto for p in ("TEPETATE", "MATERIAL DE BANCO", "COMPACTAC", "RELLENO COMPACTADO")):
                errores.append(f"{nombre}: ya trae «{texto[:80]}»: el relleno compactado debe usarlo en lugar de proponer un concepto sin insumos")

    for m in errores:
        print("DIFERENCIA", m)
    print("Todo coincide." if not errores else f"{len(errores)} diferencias.")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
