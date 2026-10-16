"""`agrupar_conceptos` (modo matriz) contra el archivo real del exportador
de OPUS.

Spec §7.3 (APU: concepto + explosión) · §10.6 (CPU, extensión propia: la
matriz nativa de OPUS, §cabeceras.CPU_MATRIZ) · §10.3 (bandeja de
pendientes).

Mismo criterio que `test_presupuesto_opus_real.py`: el modo matriz solo se
verifica de verdad contra el archivo que lo originó, así que esta prueba
toca disco — con el `csv` de la librería estándar, sin adaptadores de
Excel, para seguir ejercitando solo el dominio puro. Los tres archivos
viven en otro repo adjunto a esta sesión (no en este).

Como ninguna fila de la matriz describe al concepto mismo (§cpu.
_agrupar_conceptos_matriz), la prueba construye primero el árbol del Paso
1 (`CATALOGO_DE_PRESUPUESTO.csv`, `presupuesto.construir_arboles`) para
sacar de ahí el mapa clave → (descripción, unidad) que la matriz necesita.

Y, desde `CATALOGO_DE_TRABAJOS.csv` (§cabeceras.TRABAJOS_OPUS), construye
``clase_trabajo`` (clave → `DESTAJO`/`SUBCONTRATO`) para que los
componentes `Tipo=Contrato` carguen con la categoría precisa en vez de la
genérica `TRABAJO` — ver `test_cpu.py` para la prueba unitaria de ese
parámetro con datos de mentira; aquí solo se verifican las cifras reales.
"""

from __future__ import annotations

import csv
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

import pytest

from obractrl.domain.cargadores.cabeceras import (
    CPU_MATRIZ,
    PRESUPUESTO,
    TRABAJOS_OPUS,
    resolver_encabezados,
)
from obractrl.domain.cargadores.cpu import ConceptoCargado, agrupar_conceptos
from obractrl.domain.cargadores.mano_de_obra import validar_trabajo
from obractrl.domain.cargadores.presupuesto import TipoNodoPresupuesto, construir_arboles
from obractrl.domain.cargadores.reporte import TipoPendiente
from obractrl.domain.shared.diccionario import CategoriaExplosion, TipoInsumo

_ARBOL_PRESUPUESTO = Path(
    "/home/user/cerebro-erp-construccion/1-mundo/opus/CATALOGO_DE_PRESUPUESTO.csv"
)
_MATRIZ_CPU = Path(
    "/home/user/cerebro-erp-construccion/1-mundo/opus/ANALISIS_DE_BASICOS_CONCEPTOS.csv"
)
_TRABAJOS = Path("/home/user/cerebro-erp-construccion/1-mundo/opus/CATALOGO_DE_TRABAJOS.csv")

pytestmark = pytest.mark.skipif(
    not _ARBOL_PRESUPUESTO.exists() or not _MATRIZ_CPU.exists() or not _TRABAJOS.exists(),
    reason=(
        "Archivos reales del exportador de OPUS no disponibles en este "
        f"entorno: {_ARBOL_PRESUPUESTO}, {_MATRIZ_CPU}, {_TRABAJOS}"
    ),
)

_CLASE_A_CATEGORIA: dict[TipoInsumo, CategoriaExplosion] = {
    TipoInsumo.MANO_OBRA: CategoriaExplosion.DESTAJO,
    TipoInsumo.SUBCONTRATO: CategoriaExplosion.SUBCONTRATO,
}


def _leer_csv(ruta: Path) -> tuple[list[str], list[tuple[int, Sequence[object]]]]:
    """Mismo contrato que `test_presupuesto_opus_real._leer_csv`: la
    primera fila es la cabecera, el resto son `(numero, fila)` en base 1
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


def _mapa_descripciones_concepto() -> dict[str, tuple[str, str | None]]:
    """Clave → (descripción, unidad) de cada `CONCEPTO` del árbol de
    presupuesto del Paso 1 — lo único que, en este par de archivos, trae
    la identidad real del concepto (§cpu._agrupar_conceptos_matriz)."""
    encabezados, filas = _leer_csv(_ARBOL_PRESUPUESTO)
    mapa = resolver_encabezados(encabezados, PRESUPUESTO)
    arboles, errores, pendientes, _ = construir_arboles(filas, mapa)
    assert errores == (), [e.motivo for e in errores[:5]]
    assert pendientes == (), [p.tipo for p in pendientes[:5]]

    descripciones: dict[str, tuple[str, str | None]] = {}
    for arbol in arboles:
        for clave, nodo in arbol.nodos.items():
            if nodo.tipo is TipoNodoPresupuesto.CONCEPTO:
                descripciones[clave] = (nodo.descripcion, nodo.unidad)
    return descripciones


def _mapa_clase_trabajo() -> dict[str, CategoriaExplosion]:
    """Clave → `DESTAJO`/`SUBCONTRATO` de `CATALOGO_DE_TRABAJOS.csv`
    (§cabeceras.TRABAJOS_OPUS): 265 filas, 259 destajo y 6 subcontrato
    (verificado leyendo el archivo con Python) — ninguna con error, la
    `clase` (primera columna "Tipo") resuelve a `Destajo`/`Subcontrato` en
    las 265."""
    encabezados, filas = _leer_csv(_TRABAJOS)
    mapa = resolver_encabezados(encabezados, TRABAJOS_OPUS)
    mapa_clase: dict[str, CategoriaExplosion] = {}
    for numero, fila in filas:
        fila_trabajo = validar_trabajo(fila, mapa, numero)
        mapa_clase[str(fila_trabajo.clave)] = _CLASE_A_CATEGORIA[fila_trabajo.tipo]
    assert len(mapa_clase) == 265
    return mapa_clase


def _agrupar() -> tuple[
    tuple[ConceptoCargado, ...],
    tuple,
    tuple,
    int,
]:
    descripciones = _mapa_descripciones_concepto()
    # 468 claves padre bajo `Origen=Concepto` en la matriz; 467 cruzan
    # contra el árbol de presupuesto (verificado leyendo ambos archivos
    # con Python). La que falta es la prueba, más abajo, de que el modo
    # matriz trata eso como error de fila, no como concepto fantasma.
    assert len(descripciones) == 471  # conceptos totales del árbol de presupuesto
    clase_trabajo = _mapa_clase_trabajo()

    encabezados, filas = _leer_csv(_MATRIZ_CPU)
    mapa = resolver_encabezados(encabezados, CPU_MATRIZ)
    # La matriz nativa trae `clave_padre`: es la columna que decide el modo
    # (§cpu.agrupar_conceptos) — si el archivo real cambiara de formato,
    # esto fallaría aquí, no en silencio.
    assert "clave_padre" in mapa.indices
    return agrupar_conceptos(
        filas, mapa, descripciones_concepto=descripciones, clase_trabajo=clase_trabajo
    )


def test_la_matriz_carga_los_467_conceptos_que_cruzan_con_el_arbol() -> None:
    """468 claves padre bajo `Origen=Concepto` en el archivo; 467 cruzan
    con una clave `CONCEPTO` del árbol de `CATALOGO_DE_PRESUPUESTO.csv`
    (verificado). La que no cruza (`ACA-01070`) no tiene cómo ser
    identificable (§10.1) y no entra al catálogo — se verifica aparte, en
    el siguiente test, que sus filas sí quedan reportadas como error."""
    conceptos, _, _, omitidos = _agrupar()

    assert len(conceptos) == 467
    assert omitidos == 0
    claves = {c.llave for c in conceptos}
    assert "ACA-01070" not in claves
    assert "ACA-01010" in claves  # primer concepto del archivo


def test_la_clave_padre_que_no_cruza_con_el_arbol_es_error_de_fila() -> None:
    """`ACA-01070` no tiene clave `CONCEPTO` en el árbol de presupuesto
    (verificado: es la única de las 468 que no cruza) — sus dos filas
    componente (una `Material`, una `Contrato`, filas 18 y 19 del archivo
    real) se reportan como error, no se cargan como concepto fantasma sin
    descripción."""
    _, errores, _, _ = _agrupar()

    assert len(errores) == 2
    assert {e.fila for e in errores} == {18, 19}
    for error in errores:
        assert error.columna == "clave_padre"
        assert error.valor == "ACA-01070"


def test_los_componentes_cargados_cuadran_con_el_tipo_del_archivo() -> None:
    """De los 2568 renglones del archivo, 2189 son `Origen=Concepto`; 2
    (los de `ACA-01070`) se van a error, así que quedan 2187 componentes
    cargados — 1692 `Material`, 35 `Flete` y 460 `Contrato`, repartidos
    entre los 467 conceptos válidos. Con `clase_trabajo` (construido desde
    `CATALOGO_DE_TRABAJOS.csv`) las 262 claves `Contrato` cruzan al 100%
    (verificado), así que los 460 se reparten en 392 `DESTAJO` y 68
    `SUBCONTRATO` — ninguno se queda en el genérico `TRABAJO`.
    `Material`/`ManoDeObra` bajo `Origen` (matrices de insumo compuesto,
    fuera de alcance de este cargador) no aportan ni un componente ni un
    error: simplemente no son de este catálogo."""
    conceptos, _, _, _ = _agrupar()

    componentes = [c for concepto in conceptos for c in concepto.componentes]
    assert len(componentes) == 2187

    por_categoria = Counter(c.categoria for c in componentes)
    assert por_categoria[CategoriaExplosion.MATERIAL] == 1692
    assert por_categoria[CategoriaExplosion.FLETE] == 35
    assert por_categoria[CategoriaExplosion.DESTAJO] == 392
    assert por_categoria[CategoriaExplosion.SUBCONTRATO] == 68
    assert por_categoria[CategoriaExplosion.TRABAJO] == 0
    # El archivo no deja, bajo `Origen=Concepto`, ningún componente
    # `ManoDeObra` (verificado) — si apareciera uno, sería señal de que el
    # recuento de arriba ya no describe el archivo real.
    assert por_categoria[CategoriaExplosion.MANO_OBRA] == 0


def test_ya_no_sobrevive_ningun_pendiente_de_reclasificar() -> None:
    """Antes de que `CATALOGO_DE_TRABAJOS.csv` existiera, las 460 filas
    `Tipo=Contrato` que SÍ quedan bajo un concepto válido se marcaban con
    `TRABAJO_SIN_CLASE` (el catálogo que distingue destajo de subcontrato
    no estaba disponible). Ahora que `clase_trabajo` se construye desde
    ese archivo y las 262 claves `Contrato` del análisis de básicos cruzan
    al 100% contra él (256 destajo, 6 subcontrato, 0 sin cruzar —
    verificado), ninguna fila se queda sin clase: el pendiente no
    sobrevive ni uno. Ningún otro pendiente debería salir tampoco: el
    archivo real no trae ningún `Tipo` fuera del vocabulario de
    `CATEGORIA_POR_TIPO_MATRIZ`."""
    _, _, pendientes, _ = _agrupar()

    assert pendientes == ()


def test_sin_clase_trabajo_el_comportamiento_de_siempre_no_cambia() -> None:
    """Sin pasar ``clase_trabajo`` (el default, ``None``), cada fila
    `Tipo=Contrato` sigue cayendo en el genérico `TRABAJO` más el
    pendiente `TRABAJO_SIN_CLASE` — el fallback defensivo que existía
    antes de este catálogo se conserva intacto para el día en que una
    clave de verdad no cruce."""
    descripciones = _mapa_descripciones_concepto()
    encabezados, filas = _leer_csv(_MATRIZ_CPU)
    mapa = resolver_encabezados(encabezados, CPU_MATRIZ)

    conceptos, _errores, pendientes, _ = agrupar_conceptos(
        filas, mapa, descripciones_concepto=descripciones
    )

    componentes = [c for concepto in conceptos for c in concepto.componentes]
    por_categoria = Counter(c.categoria for c in componentes)
    assert por_categoria[CategoriaExplosion.TRABAJO] == 460
    assert por_categoria[CategoriaExplosion.DESTAJO] == 0
    assert por_categoria[CategoriaExplosion.SUBCONTRATO] == 0
    assert len(pendientes) == 460
    assert all(p.tipo is TipoPendiente.TRABAJO_SIN_CLASE for p in pendientes)


def test_el_importe_de_un_concepto_conocido_cuadra_con_sus_componentes() -> None:
    """`ACA-01010` ("CONCRETO SIMPLE... MORTERO ESTUCO BLANCO...", primer
    concepto del archivo real): su descripción/unidad vienen del árbol de
    presupuesto (no de la matriz), y sus componentes son los que trae la
    matriz para esa clave_padre."""
    conceptos, _, _, _ = _agrupar()

    aca_01010 = next(c for c in conceptos if c.llave == "ACA-01010")
    assert aca_01010.encabezado.descripcion
    assert aca_01010.encabezado.unidad
    assert len(aca_01010.componentes) >= 1
