"""`construir_arboles` contra el archivo real del exportador de OPUS.

Spec §7.4 (árbol WBS del prototipo) · §10.6 (presupuesto jerárquico, alias
`nivel`/`clave` del árbol nativo, §cabeceras.PRESUPUESTO).

Única prueba de este paquete que toca disco: el árbol nativo —`nivel` +
posición, sin `clave_padre`— solo se verifica de verdad contra el archivo
que lo originó; un fixture escrito a mano no prueba nada que el propio
fixture no haya ya decidido. El archivo vive en otro repo adjunto a esta
sesión (no en este), y se lee aquí con el `csv` de la librería estándar
—no con ningún adaptador de `adapters/excel`— para que la prueba siga
ejercitando solo el dominio puro: `construir_arboles` recibe listas de
celdas, igual que cualquier otra prueba de `test_cargadores.py`.

Dos conteos distintos, verificados por separado, porque no son el mismo
número:

- **Por `Tipo` crudo** (`test_el_archivo_trae_las_filas_declaradas_por_tipo`):
  cuántas filas de cada `Tipo` trae el archivo tal cual —7 capítulos, 102
  subcapítulos, 325 `Nivel 2`, 345 `Nivel 3`, 2,452 `Concepto`—, contando
  también los 121 "huecos" del exportador (de un renglón borrado: sin
  clave, sin descripción, sin importe). Es la cuadratura de archivo
  completo, no la del árbol.
- **Árbol reconstruido** (`test_el_arbol_nativo_reproduce_los_conteos_...`):
  318 `Nivel 2`, 238 `Nivel 3`, 2,445 `Concepto` — el `Tipo` crudo menos
  los huecos que `construir_arboles` descarta en silencio. El criterio es
  el de la referencia (`cerebro/backend/core/importacion_opus.py::
  leer_presupuesto`, verificado corriéndola contra este mismo archivo):
  un hueco se descarta salvo que algo con clave real cuelgue debajo de
  él —ninguno de los 121 lo tiene en este archivo—, nunca por traerlo tal
  cual al árbol: un hueco convertido en nodo real sería un concepto
  fantasma en el catálogo compartido (7 casos) o una etapa/agrupador
  fantasma en el árbol WBS (114 casos), ninguno de los dos un dato real.
"""

from __future__ import annotations

import csv
from collections import Counter
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

import pytest

from obractrl.domain.cargadores.cabeceras import PRESUPUESTO, resolver_encabezados
from obractrl.domain.cargadores.presupuesto import (
    ArbolPrototipoCargado,
    TipoNodoPresupuesto,
    construir_arboles,
)

_ARCHIVO_REAL = Path(
    "/home/user/cerebro-erp-construccion/1-mundo/opus/CATALOGO_DE_PRESUPUESTO.csv"
)

pytestmark = pytest.mark.skipif(
    not _ARCHIVO_REAL.exists(),
    reason=f"Archivo real del exportador de OPUS no disponible en este entorno: {_ARCHIVO_REAL}",
)


def _leer_csv(ruta: Path) -> tuple[list[str], list[tuple[int, Sequence[object]]]]:
    """La primera fila no vacía es la cabecera, y el resto son `(numero,
    fila)` en base 1 contando la cabecera como la fila 1 —mismo contrato
    que `adapters.excel.pipeline.leer_filas`— para que un error de fila
    siga señalando al renglón real del archivo."""
    with ruta.open(newline="", encoding="utf-8-sig") as f:
        todas = list(csv.reader(f))
    encabezados = todas[0]
    datos = [
        (numero, fila)
        for numero, fila in enumerate(todas[1:], start=2)
        if any(celda.strip() for celda in fila)
    ]
    return encabezados, datos


def _construir() -> tuple[ArbolPrototipoCargado, ...]:
    encabezados, filas = _leer_csv(_ARCHIVO_REAL)
    mapa = resolver_encabezados(encabezados, PRESUPUESTO)
    # El árbol nativo no trae `clave_padre`: si algún día el archivo real
    # cambiara y la empezara a traer, esto fallaría aquí (no en silencio)
    # y señalaría que la prueba necesita revisarse para ambos formatos.
    assert "clave_padre" not in mapa.indices
    assert "nivel" in mapa.indices

    arboles, errores, pendientes, omitidos = construir_arboles(filas, mapa)
    assert errores == (), [e.motivo for e in errores[:5]]
    assert pendientes == (), [p.tipo for p in pendientes[:5]]
    # Los 121 huecos del exportador (sin clave, sin descripción, sin
    # importe, y sin nada con clave real debajo): mismo criterio que la
    # referencia, que también los descarta los 121/121 para este archivo
    # (`cerebro/backend/core/importacion_opus.py::leer_presupuesto`).
    assert omitidos == 121
    return arboles


def _contar_por_tipo(arboles: tuple[ArbolPrototipoCargado, ...]) -> dict[TipoNodoPresupuesto, int]:
    conteos: dict[TipoNodoPresupuesto, int] = dict.fromkeys(TipoNodoPresupuesto, 0)
    for arbol in arboles:
        conteos[arbol.raiz.tipo] += 1
        for hijos_directos in arbol.hijos.values():
            for nodo in hijos_directos:
                conteos[nodo.tipo] += 1
    return conteos


def test_el_arbol_nativo_reproduce_los_siete_prototipos_del_archivo() -> None:
    arboles = _construir()

    assert len(arboles) == 7
    assert {a.clave_prototipo for a in arboles} == {
        "CAS-00001",
        "CAS-00002",
        "CAS-00003",
        "CAS-00004",
        "CAS-00005",
        "CAS-00006",
        "CAS-00007",
    }


def test_el_archivo_trae_las_filas_declaradas_por_tipo() -> None:
    """Cuadratura de archivo completo, sin pasar por `construir_arboles`:
    cuántas filas de cada `Tipo` trae el CSV tal cual, huecos incluidos
    (107 `Nivel 3`, 7 `Nivel 2` y 7 `Concepto` sin clave/descripción/
    importe) — el archivo los cuenta como filas de ese `Tipo` aunque el
    árbol reconstruido después los descarte (ver el siguiente test). Es la
    prueba de que se leyó el archivo completo, no la del árbol."""
    encabezados, filas = _leer_csv(_ARCHIVO_REAL)
    indice_tipo = encabezados.index(
        next(h for h in encabezados if h.strip().lower() == "tipo")
    )
    conteo = Counter(fila[indice_tipo].strip() for _, fila in filas)

    assert conteo["Capítulo"] == 7
    assert conteo["Subcapítulo"] == 102
    assert conteo["Nivel 2"] == 325
    assert conteo["Nivel 3"] == 345
    assert conteo["Concepto"] == 2452


def test_el_arbol_nativo_reproduce_los_conteos_por_tipo_verificados_del_archivo() -> None:
    """`Tipo` del archivo → `TipoNodoPresupuesto`, contando cada fila una
    sola vez (la raíz de cada árbol + todo lo que cuelga de ella), **tras**
    el descarte de huecos muertos de `construir_arboles` (ver `_construir`,
    `omitidos == 121`):

    - 7 `Capítulo` (uno por prototipo) → `PROTOTIPO`.
    - 102 `Subcapítulo` → `NIVEL`.
    - 318 `Nivel 2` → `ETAPA` (325 crudos − 7 huecos muertos).
    - 238 `Nivel 3` → `AGRUPADOR` (345 crudos − 107 huecos muertos; nuevo,
      migración 0051).
    - 2445 `Concepto` → `CONCEPTO` (2452 crudos − 7 huecos muertos).

    Verificado corriendo la referencia (`cerebro/backend/core/
    importacion_opus.py::leer_presupuesto`) contra este mismo archivo: los
    121 huecos caen 121/121 del lado descartado — ninguno tiene debajo
    algo con clave real que lo salve.
    """
    conteos = _contar_por_tipo(_construir())

    assert conteos[TipoNodoPresupuesto.PROTOTIPO] == 7
    assert conteos[TipoNodoPresupuesto.NIVEL] == 102
    assert conteos[TipoNodoPresupuesto.ETAPA] == 318
    assert conteos[TipoNodoPresupuesto.AGRUPADOR] == 238
    assert conteos[TipoNodoPresupuesto.CONCEPTO] == 2445
    # El archivo no trae ninguno de estos tres tipos (§10.6: viven en otro
    # archivo que esta tarea no toca) — si apareciera uno, sería señal de
    # que el `Tipo`/`_ALIAS_TIPO_RENGLON` resolvió algo distinto a lo
    # esperado, no que el negocio cambió de opinión.
    assert conteos[TipoNodoPresupuesto.MATERIAL] == 0
    assert conteos[TipoNodoPresupuesto.DESTAJO] == 0
    assert conteos[TipoNodoPresupuesto.SUBCONTRATO] == 0
    assert conteos[TipoNodoPresupuesto.CONCEPTO_AUXILIAR] == 0


def test_el_importe_de_cada_capitulo_cuadra_al_centavo_con_sus_hijos_directos() -> None:
    """La suma del `importe` de los hijos **directos** de cada capítulo
    coincide, al centavo, con el `importe` que el archivo trae en la
    propia fila del capítulo — con `Decimal`, nunca con `float` (§3.5)."""
    arboles = _construir()
    assert len(arboles) == 7

    for arbol in arboles:
        hijos_directos = arbol.hijos.get(arbol.raiz.fila, ())
        suma = sum((h.importe or Decimal(0) for h in hijos_directos), Decimal(0))
        assert arbol.raiz.importe is not None
        assert suma == arbol.raiz.importe, (
            f"{arbol.clave_prototipo}: suma de hijos {suma} != total del "
            f"capítulo {arbol.raiz.importe}"
        )
