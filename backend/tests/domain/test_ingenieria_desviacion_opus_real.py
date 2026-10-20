"""`domain.ingenieria.desviacion` contra la cimentación real de `ALAMO 18`
(CONOCIMIENTO.md §11.7, §11.9).

Verifica dos cosas a la vez: que el generador funciona sobre datos reales
reconstruidos por la reversión, y que el número que produce confirma —de
forma independiente— lo que ya salió al comparar la etapa completa contra
el prototipo (§11.9: "`EST-01053` da 1.130... coincide con el 1.12 que
salió al comparar la estructura" — "dos caminos independientes llegan al
mismo número").
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from obractrl.domain.cargadores.ingenieria_lote import leer_ingenieria_lote
from obractrl.domain.catalogos.apu import explotar
from obractrl.domain.ingenieria.desviacion import generar_desviaciones_candidatas
from obractrl.domain.ingenieria.reversion import revertir_destajos
from obractrl.domain.shared.diccionario import TipoDesviacion
from tests.domain._opus_real_ingenieria import (
    DIAMANTE_CON_CHIMENEA,
    INGENIERIA_ALAMO_18,
    archivos_disponibles,
    catalogo,
    leer_filas_crudas,
)

pytestmark = pytest.mark.skipif(
    not archivos_disponibles(),
    reason=f"Catálogo/ingenierías reales de ALAMO 18 no disponibles en este entorno: {INGENIERIA_ALAMO_18}",
)

_CIMENTACION = "INGENIERIA_-_ALAMO_18_-_CIM.csv"


def test_est_01053_sale_desviado_1_13_igual_que_la_comparacion_por_etapa() -> None:
    cat = catalogo()
    presupuesto = cat.presupuesto_por_etapa(DIAMANTE_CON_CHIMENEA)
    _, insumos, _, errores, _ = leer_ingenieria_lote(leer_filas_crudas(INGENIERIA_ALAMO_18 / _CIMENTACION))
    assert errores == ()

    resultados, _ = revertir_destajos(insumos, cat.lineas, presupuesto, cat.composiciones)

    conceptos = {c for etapa in presupuesto.values() for c in etapa}
    precio_concepto = {c: explotar(c, composiciones=cat.composiciones).precio.total.monto for c in conceptos}
    concepto_id_de_clave = {c: f"concepto::{c}" for c in conceptos}

    desviaciones, pendientes = generar_desviaciones_candidatas(
        resultados,
        presupuesto,
        precio_concepto,
        obra_id="obra::alamo-18",
        concepto_id_de_clave=concepto_id_de_clave,
        detectada_en=datetime(2026, 10, 16, tzinfo=UTC),
    )

    assert pendientes == ()
    por_concepto = {d.concepto_id: d for d in desviaciones}
    est_01053 = por_concepto["concepto::EST-01053"]

    assert est_01053.tipo is TipoDesviacion.CONSUMO
    assert est_01053.causa is None
    assert est_01053.causa_capturada_por is None
    assert est_01053.obra_id == "obra::alamo-18"
    assert est_01053.cantidad_plan == Decimal(1)
    # 1.1296... redondea a 1.13 — el mismo número que §11.9 cita (1.130) y
    # que §11.5 confirma de forma independiente (1.12 por etapa).
    assert abs(est_01053.cantidad_real - Decimal("1.1296296296")) < Decimal("0.0001")
    assert est_01053.precio_plan is None
    assert est_01053.precio_real is None
    assert est_01053.monto > 0  # gastó de más, no de menos


def test_ningun_concepto_resuelto_sin_desviacion_aparece_en_el_resultado() -> None:
    """Los conceptos donde la reversión confirma el presupuesto (p. ej.
    las zapatas de `MOC-12010`, que cuentan exactas) no generan
    `Desviacion`: la ausencia es el resultado correcto, no un hueco."""
    cat = catalogo()
    presupuesto = cat.presupuesto_por_etapa(DIAMANTE_CON_CHIMENEA)
    _, insumos, _, _, _ = leer_ingenieria_lote(leer_filas_crudas(INGENIERIA_ALAMO_18 / _CIMENTACION))
    resultados, _ = revertir_destajos(insumos, cat.lineas, presupuesto, cat.composiciones)

    conceptos = {c for etapa in presupuesto.values() for c in etapa}
    precio_concepto = {c: explotar(c, composiciones=cat.composiciones).precio.total.monto for c in conceptos}
    concepto_id_de_clave = {c: f"concepto::{c}" for c in conceptos}

    desviaciones, _ = generar_desviaciones_candidatas(
        resultados,
        presupuesto,
        precio_concepto,
        obra_id="obra::alamo-18",
        concepto_id_de_clave=concepto_id_de_clave,
        detectada_en=datetime(2026, 10, 16, tzinfo=UTC),
    )
    claves_con_desviacion = {d.concepto_id for d in desviaciones}
    assert "concepto::EST-01053" in claves_con_desviacion
