"""Fixtures compartidos de las pruebas de ingeniería del lote contra los
archivos reales de `ALAMO 18` (`1-mundo/opus/`, en el repo adjunto a esta
sesión, no en este). No es un módulo de pruebas — no empieza con
``test_``, pytest no lo recolecta — solo construye, una vez por sesión, lo
que las cuatro pruebas de este paquete necesitan: la matriz completa, los
árboles de los 7 prototipos y el presupuesto por etapa de cada uno.

Mismo criterio que `test_presupuesto_opus_real.py`/`test_cpu_opus_real.py`:
se lee con el `csv` de la librería estándar, nunca con un adaptador de
`adapters/excel`, para seguir ejercitando solo el dominio puro.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

from obractrl.domain.cargadores.cabeceras import (
    CPU_MATRIZ,
    PRESUPUESTO,
    resolver_encabezados,
)
from obractrl.domain.cargadores.presupuesto import construir_arboles
from obractrl.domain.ingenieria.arbol_prototipo import renglones_por_etapa
from obractrl.domain.ingenieria.matriz_completa import (
    construir_composiciones,
    leer_lineas_crudas,
)

OPUS = Path("/home/user/cerebro-erp-construccion/1-mundo/opus")
INGENIERIA_ALAMO_18 = OPUS / "ingenieria-alamo-18"
CATALOGO_PRESUPUESTO = OPUS / "CATALOGO_DE_PRESUPUESTO.csv"
MATRIZ_CONCEPTOS = OPUS / "ANALISIS_DE_BASICOS_CONCEPTOS.csv"

DIAMANTE_CON_CHIMENEA = "CAS-00007"
ZAFIRO_PLUS = "CAS-00006"

ARCHIVOS_REQUERIDOS = (CATALOGO_PRESUPUESTO, MATRIZ_CONCEPTOS)


def archivos_disponibles() -> bool:
    return all(p.exists() for p in ARCHIVOS_REQUERIDOS) and INGENIERIA_ALAMO_18.is_dir()


def leer_tabla(ruta: Path) -> tuple[list[str], list[tuple[int, Sequence[str]]]]:
    """Mismo contrato que `test_presupuesto_opus_real.py::_leer_csv`: la
    primera fila es la cabecera, el resto son ``(numero, fila)`` en base 1
    contando la cabecera como la fila 1."""
    with ruta.open(newline="", encoding="utf-8-sig") as f:
        todas = list(csv.reader(f))
    encabezados = todas[0]
    datos = [
        (numero, fila)
        for numero, fila in enumerate(todas[1:], start=2)
        if any(celda.strip() for celda in fila)
    ]
    return encabezados, datos


def leer_filas_crudas(ruta: Path) -> list[list[str]]:
    """Una ingeniería del lote NO TIENE encabezado (`domain.cargadores.
    ingenieria_lote`): se devuelve el archivo completo, celda por celda,
    sin descartar ninguna fila como "cabecera"."""
    with ruta.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.reader(f))


class CatalogoReal:
    """Lo que las pruebas de identificación/reversión/desviación
    necesitan del catálogo de `ALAMO 18`: la matriz completa (todos los
    orígenes) y el árbol de cada uno de los 7 prototipos."""

    def __init__(self) -> None:
        encabezados, filas = leer_tabla(MATRIZ_CONCEPTOS)
        mapa = resolver_encabezados(encabezados, CPU_MATRIZ)
        self.lineas, self.errores_matriz, self.pendientes_matriz = leer_lineas_crudas(filas, mapa)
        self.composiciones = construir_composiciones(self.lineas)

        encabezados2, filas2 = leer_tabla(CATALOGO_PRESUPUESTO)
        mapa2 = resolver_encabezados(encabezados2, PRESUPUESTO)
        arboles, self.errores_arbol, self.pendientes_arbol, self.omitidos_arbol = construir_arboles(
            filas2, mapa2
        )
        self.arboles = {a.clave_prototipo: a for a in arboles}
        self._presupuesto_por_etapa: dict[str, dict[str, dict[str, Decimal]]] = {}

    def presupuesto_por_etapa(self, clave_prototipo: str) -> dict[str, dict[str, Decimal]]:
        """Cantidad presupuestada de cada concepto, por etapa (`ECO-...`),
        del prototipo ``clave_prototipo`` — memorizado porque varias
        pruebas lo piden del mismo prototipo."""
        if clave_prototipo not in self._presupuesto_por_etapa:
            acumulado: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
            for renglon in renglones_por_etapa(self.arboles[clave_prototipo]):
                if renglon.etapa is not None:
                    acumulado[renglon.etapa][renglon.clave] += renglon.cantidad
            self._presupuesto_por_etapa[clave_prototipo] = {
                etapa: dict(conceptos) for etapa, conceptos in acumulado.items()
            }
        return self._presupuesto_por_etapa[clave_prototipo]


_catalogo: CatalogoReal | None = None


def catalogo() -> CatalogoReal:
    """Singleton de proceso: construir el catálogo completo (3,231 filas
    de presupuesto + 2,568 de matriz) una sola vez por sesión de pruebas."""
    global _catalogo
    if _catalogo is None:
        _catalogo = CatalogoReal()
    return _catalogo
