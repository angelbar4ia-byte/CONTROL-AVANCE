"""Verifica los datos del catálogo que usa la escalera (Fase 4a) contra los CSV de opus.

No es una prueba de CI (el cerebro no está en el repositorio): se corre a mano cuando cambia el catálogo.

    PYTHONPATH=src python scripts/verificar_escalera_contra_csv.py /ruta/cerebro-erp-construccion/1-mundo/opus

Comprueba que (1) el concepto existente EST-01510 (el del escalón forjado) está en CATALOGO_DE_MATRICES por pza con la descripción que usa el módulo; (2) su composición
(ANALISIS_DE_BASICOS_CONCEPTOS) trae los materiales y los destajos con las cantidades y las líneas que cita el módulo, y no trae otros; (3) los materiales existen en
CATALOGO_DE_MATERIALES con su unidad; (4) los destajos existen en CATALOGO_DE_TRABAJOS con su unidad; (5) la parrilla AUX-06010 trae las cantidades por m² del módulo;
(6) la cimbra MAD-00001 existe en m²; y (7) la clave provisional del descanso (EJ-820) no existe ya en el catálogo y este sigue sin traer un descanso de concreto (la razón de
que el descanso lleve un concepto nuevo). Sale con código 1 si algo no coincide.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from obractrl.domain.cuantificacion.escalera import (
    CIMBRA_DEL_DESCANSO,
    COMPOSICION_DEL_ESCALON,
    CONCEPTO_DE_DESCANSO,
    CONCEPTO_DE_ESCALON,
    DESTAJOS_DEL_ESCALON,
    PARRILLA_POR_M2,
)


def _numero(texto: str) -> float:
    return float(texto.replace("$", "").replace(",", "") or 0)


def _lineas(carpeta: Path, nombre: str) -> list[list[str]]:
    with (carpeta / f"{nombre}.csv").open(encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f))


def _unidad(u: str) -> str:
    u = u.strip().lower().replace("³", "3").replace("²", "2")
    return "pza" if u == "pz" else u  # el catálogo escribe PZ


def main(carpeta: Path) -> int:
    errores: list[str] = []
    clave = CONCEPTO_DE_ESCALON["clave"]
    matrices = {f[1]: f for f in _lineas(carpeta, "CATALOGO_DE_MATRICES") if len(f) > 4}
    fila = matrices.get(clave)
    if fila is None:
        errores.append(f"{clave}: no está en CATALOGO_DE_MATRICES")
    elif not fila[2].startswith(CONCEPTO_DE_ESCALON["descripcion"][:60]) or _unidad(fila[3]) != "pza":
        errores.append(f"{clave}: el módulo dice «{CONCEPTO_DE_ESCALON['descripcion'][:60]}…» por pza y el CSV trae {fila[2:4]}")

    conceptos = _lineas(carpeta, "ANALISIS_DE_BASICOS_CONCEPTOS")
    for hijo, _descripcion, _unidad_del_hijo, cantidad, linea in (*COMPOSICION_DEL_ESCALON, *DESTAJOS_DEL_ESCALON):
        archivo, numero = linea.split(":")
        fila_c = conceptos[int(numero) - 1] if archivo == "ANALISIS_DE_BASICOS_CONCEPTOS" and int(numero) <= len(conceptos) else []
        if len(fila_c) < 5 or fila_c[0] != clave or fila_c[1] != hijo or abs(_numero(fila_c[4]) - cantidad) > 1e-9:
            errores.append(f"{clave} {hijo}: el módulo dice {cantidad} ({linea}), el CSV trae {fila_c[:5]}")
    del_csv = {f[1] for f in conceptos if f and f[0] == clave}
    if del_csv != {c[0] for c in (*COMPOSICION_DEL_ESCALON, *DESTAJOS_DEL_ESCALON)}:
        errores.append(f"{clave}: el CSV trae los insumos {sorted(del_csv)} y el módulo no los repite igual")

    materiales = {f[1]: f for f in _lineas(carpeta, "CATALOGO_DE_MATERIALES") if len(f) > 4}
    for dato in (*COMPOSICION_DEL_ESCALON, *PARRILLA_POR_M2):
        m = materiales.get(dato[0])
        if m is None or m[2].strip() != dato[1] or _unidad(m[4]) != _unidad(dato[2]):
            errores.append(f"{dato[0]}: el módulo dice «{dato[1]}» en {dato[2]} y el CSV trae {m[2:5] if m else 'nada'}")
    cimbra = materiales.get(CIMBRA_DEL_DESCANSO["clave"])
    if cimbra is None or cimbra[2].strip() != CIMBRA_DEL_DESCANSO["descripcion"] or _unidad(cimbra[4]) != "m2":
        errores.append(f"{CIMBRA_DEL_DESCANSO['clave']}: el módulo dice «{CIMBRA_DEL_DESCANSO['descripcion']}» en m² y el CSV trae {cimbra[2:5] if cimbra else 'nada'}")

    trabajos = {f[3]: f for f in _lineas(carpeta, "CATALOGO_DE_TRABAJOS") if len(f) > 7}
    for dato in DESTAJOS_DEL_ESCALON:
        d = trabajos.get(dato[0])
        if d is None or d[4].strip() != dato[1] or _unidad(d[7]) != _unidad(dato[2]):
            errores.append(f"{dato[0]}: el módulo dice «{dato[1]}» por {dato[2]} y el CSV trae {d[4:8] if d else 'nada'}")

    compuestos = _lineas(carpeta, "ANALISIS_DE_BASICOS_COMPUESTOS")
    for hijo, _d, _u, por_m2, linea in PARRILLA_POR_M2:
        _archivo, numero = linea.split(":")
        fila_a = compuestos[int(numero) - 1] if int(numero) <= len(compuestos) else []
        if len(fila_a) < 5 or fila_a[0] != "AUX-06010" or fila_a[1] != hijo or abs(_numero(fila_a[4]) - por_m2) > 1e-9:
            errores.append(f"AUX-06010 {hijo}: el módulo dice {por_m2} por m² ({linea}), el CSV trae {fila_a[:5]}")

    ocupadas = {f[1] for nombre in ("CATALOGO_DE_MATRICES", "CATALOGO_DE_MATERIALES") for f in _lineas(carpeta, nombre) if len(f) > 1} | set(trabajos)
    if CONCEPTO_DE_DESCANSO["clave"] in ocupadas:
        errores.append(f"{CONCEPTO_DE_DESCANSO['clave']}: la clave provisional ya existe en el catálogo")
    for f in _lineas(carpeta, "CATALOGO_DE_MATRICES"):
        texto = " ".join(f[:6]).upper()
        if "DESCANSO" in texto and "HERRER" not in texto and "HER-" not in texto:
            errores.append(f"CATALOGO_DE_MATRICES: ya trae «{texto[:80]}»: el descanso debe usarlo en lugar de proponer un concepto nuevo")

    for m in errores:
        print("DIFERENCIA", m)
    print("Todo coincide." if not errores else f"{len(errores)} diferencias.")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
