"""`domain.ingenieria.con_concepto` contra el archivo real
`CEMENTO_EXTRA_EN_FACHADA...csv` de `ALAMO 18` (CONOCIMIENTO.md §11.8,
estructura `CON_CONCEPTO`).

El agrupador `ALB-01212` ("Repellado en muros de fachada...") es el
concepto; su insumo anclado, `ADH-00005` (CEMENTO), no es hijo DIRECTO de
`ALB-01212` en la matriz real —solo lo es del compuesto `MEZ-07010`, que SÍ
cuelga de `ALB-01212`— así que esta prueba verifica, con el catálogo real,
que la reconstrucción SÍ busca en profundidad (no solo en la matriz
directa) y que las otras tres filas del mismo bloque (`ADH-00001`,
`PET-00009`, `PRE-00007` — pegapiso/rodapié/marco, arrastradas al mismo
agrupador por el criterio de "no se reinicia por bloque" pero que en
realidad no pertenecen a la matriz de `ALB-01212`) se reportan como
pendiente en vez de inventarse un rendimiento.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.cargadores.ingenieria_lote import leer_ingenieria_lote
from obractrl.domain.cargadores.reporte import TipoPendiente
from obractrl.domain.ingenieria.con_concepto import reconstruir_con_concepto
from tests.domain._opus_real_ingenieria import (
    INGENIERIA_ALAMO_18,
    archivos_disponibles,
    catalogo,
    leer_filas_crudas,
)

pytestmark = pytest.mark.skipif(
    not archivos_disponibles(),
    reason=f"Catálogo/ingenierías reales de ALAMO 18 no disponibles en este entorno: {INGENIERIA_ALAMO_18}",
)

_CEMENTO_EXTRA = (
    "INGENIERIA_-_ALAMO_18__-_CEMENTO_EXTRA_EN_FACHADA_POR_AJUSTE_DEL_NUEVO_RENDIMIENTO.csv"
)


def _reconstruir():
    cat = catalogo()
    estructura, insumos, _, errores, pendientes_lectura = leer_ingenieria_lote(
        leer_filas_crudas(INGENIERIA_ALAMO_18 / _CEMENTO_EXTRA)
    )
    assert errores == ()
    resultados, pendientes = reconstruir_con_concepto(insumos, cat.composiciones)
    return estructura, insumos, resultados, pendientes, pendientes_lectura


def test_el_archivo_real_se_detecta_con_concepto() -> None:
    estructura, insumos, _, _, _ = _reconstruir()
    from obractrl.domain.cargadores.ingenieria_lote import TipoEstructuraIngenieria

    assert estructura is TipoEstructuraIngenieria.CON_CONCEPTO
    assert len(insumos) == 4
    assert {f.agrupador for f in insumos} == {"ALB-01212"}
    # Ninguna fila trae etapa: CON_CONCEPTO nunca trae ECO-/NIV- (§11.8).
    assert all(f.etapa is None for f in insumos)


def test_cemento_se_reconstruye_en_profundidad_contra_el_compuesto() -> None:
    """`ADH-00005` no es hijo directo de `ALB-01212` —solo del compuesto
    `MEZ-07010`, que sí lo es— así que el rendimiento solo se encuentra
    buscando en profundidad, igual que la clase `COMPUESTO` de la reversión
    por destajo (`apu.explotar`)."""
    _, _, resultados, pendientes, _ = _reconstruir()

    por_clave = {r.clave_insumo: r for r in resultados}
    assert "ADH-00005" in por_clave
    cemento = por_clave["ADH-00005"]
    assert cemento.concepto == "ALB-01212"
    assert cemento.cantidad_insumo == Decimal("18")
    assert cemento.rendimiento == Decimal("0.191100")
    assert cemento.cantidad_real == Decimal("18") / Decimal("0.191100")

    assert all(p.tipo is not TipoPendiente.RENDIMIENTO_NO_ENCONTRADO or p.valor_origen != "ADH-00005" for p in pendientes)


def test_pegapiso_rodapie_y_marco_no_pertenecen_a_la_matriz_y_quedan_pendientes() -> None:
    """Las otras tres filas del bloque (arrastradas al mismo agrupador por
    el criterio de "nunca se reinicia por bloque") no son parte de la
    matriz real de `ALB-01212` — no se inventa un rendimiento, se reportan
    (§3.3)."""
    _, _, resultados, pendientes, _ = _reconstruir()

    resueltas = {r.clave_insumo for r in resultados}
    assert resueltas == {"ADH-00005"}

    sin_rendimiento = {
        p.valor_origen
        for p in pendientes
        if p.tipo is TipoPendiente.RENDIMIENTO_NO_ENCONTRADO
    }
    assert sin_rendimiento == {"ADH-00001", "PET-00009", "PRE-00007"}
    for p in pendientes:
        if p.tipo is TipoPendiente.RENDIMIENTO_NO_ENCONTRADO:
            assert p.propuesta["concepto"] == "ALB-01212"
            assert p.critico is False
