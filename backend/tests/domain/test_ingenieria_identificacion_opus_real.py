"""`domain.ingenieria.identificacion` contra los datos reales de `ALAMO 18`
(`CONOCIMIENTO.md` §11.5, §11.7, §11.11).

Dos pruebas distintas, porque son dos preguntas distintas (§11.5 vs
§11.11): con una sola ingeniería parcial (la cimentación, 5 de ~41 etapas)
¿el contenido ya apunta al prototipo correcto?; con las once juntas, ¿el
sistema lo identifica sin ambigüedad? Los números de la primera son los
que `CONOCIMIENTO.md` §11.5 cita literal (1.12, 1.03, 1.00, 1.48, 1.00
contra Diamante; 2.08, 1.46, 1.38, 1.70, 2.18 contra Zafiro Plus) —
verificados aquí corriendo el código, no copiados.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.cargadores.ingenieria_lote import leer_ingenieria_lote
from obractrl.domain.ingenieria.consolidacion import consolidar_lote
from obractrl.domain.ingenieria.identificacion import (
    explotar_prototipo_por_etapa,
    identificar_prototipo,
)
from tests.domain._opus_real_ingenieria import (
    DIAMANTE_CON_CHIMENEA,
    INGENIERIA_ALAMO_18,
    ZAFIRO_PLUS,
    archivos_disponibles,
    catalogo,
    leer_filas_crudas,
)

pytestmark = pytest.mark.skipif(
    not archivos_disponibles(),
    reason=f"Catálogo/ingenierías reales de ALAMO 18 no disponibles en este entorno: {INGENIERIA_ALAMO_18}",
)


def _consolidado_de(*nombres: str):
    insumos = []
    for nombre in nombres:
        _, filas_insumo, _, errores, _ = leer_ingenieria_lote(leer_filas_crudas(INGENIERIA_ALAMO_18 / nombre))
        assert errores == ()
        insumos.extend(filas_insumo)
    return consolidar_lote(insumos)


def test_diamante_con_chimenea_es_cas_00007_por_su_total_declarado() -> None:
    cat = catalogo()
    diamante = cat.arboles[DIAMANTE_CON_CHIMENEA]
    assert diamante.raiz.descripcion.upper().startswith("DIAMANTE CON CHIMENEA")
    assert diamante.raiz.importe == Decimal("2829925.98")


def test_las_cinco_etapas_de_la_cimentacion_contra_diamante_y_zafiro_plus() -> None:
    """§11.5: "comparando las cinco etapas contra los siete prototipos...
    tres etapas dan 1.00 o 1.03 contra Diamante. Contra Zafiro Plus
    ninguna se acerca."""
    cat = catalogo()
    consolidado = _consolidado_de("INGENIERIA_-_ALAMO_18_-_CIM.csv")
    assert set(consolidado.total_por_etapa) == {f"ECO-0000{i}" for i in range(1, 6)}

    candidatos = [
        explotar_prototipo_por_etapa(cat.arboles[clave], cat.composiciones)
        for clave in (DIAMANTE_CON_CHIMENEA, ZAFIRO_PLUS)
    ]
    resultado = identificar_prototipo(consolidado.total_por_etapa, candidatos)
    por_clave = {c.clave_prototipo: c for c in resultado.candidatos}

    diamante = por_clave[DIAMANTE_CON_CHIMENEA].razon_por_etapa
    zafiro = por_clave[ZAFIRO_PLUS].razon_por_etapa

    # Estructura, sanitarias, hidráulicas, gas (en ese orden en §11.5):
    esperado_diamante = {
        "ECO-00001": Decimal("1.12"),
        "ECO-00002": Decimal("1.03"),
        "ECO-00003": Decimal("1.00"),
        "ECO-00004": Decimal("1.48"),
        "ECO-00005": Decimal("1.00"),
    }
    for etapa, razon_esperada in esperado_diamante.items():
        assert abs(diamante[etapa] - razon_esperada) < Decimal("0.01"), etapa

    esperado_zafiro = {
        "ECO-00001": Decimal("2.08"),
        "ECO-00002": Decimal("1.46"),
        "ECO-00003": Decimal("1.38"),
        "ECO-00004": Decimal("1.70"),
        "ECO-00005": Decimal("2.18"),
    }
    for etapa, razon_esperada in esperado_zafiro.items():
        assert abs(zafiro[etapa] - razon_esperada) < Decimal("0.01"), etapa

    # Tres etapas (sanitarias, hidráulicas, gas) a menos de 5% de 1.00
    # contra Diamante y ninguna así contra Zafiro Plus.
    cerca_de_uno_diamante = sum(1 for r in diamante.values() if abs(r - 1) < Decimal("0.05"))
    cerca_de_uno_zafiro = sum(1 for r in zafiro.values() if abs(r - 1) < Decimal("0.05"))
    assert cerca_de_uno_diamante == 3
    assert cerca_de_uno_zafiro == 0


def test_identificacion_con_las_once_ingenierias_senala_a_diamante_con_chimenea() -> None:
    """§11.8: "la suma da 92% del presupuesto del Diamante con chimenea".
    Con las once ingenierías juntas, contra los 7 prototipos del
    catálogo, Diamante con chimenea es el único que cae dentro del umbral
    y el más cercano de los siete."""
    cat = catalogo()
    archivos = sorted(INGENIERIA_ALAMO_18.glob("*.csv"))
    consolidado = _consolidado_de(*(a.name for a in archivos))

    candidatos = [
        explotar_prototipo_por_etapa(arbol, cat.composiciones) for arbol in cat.arboles.values()
    ]
    resultado = identificar_prototipo(consolidado.total_por_etapa, candidatos)

    assert resultado.identificado == DIAMANTE_CON_CHIMENEA
    assert resultado.sugerido == DIAMANTE_CON_CHIMENEA
    assert resultado.identidad_dudosa is False

    por_clave = {c.clave_prototipo: c for c in resultado.candidatos}
    assert abs(por_clave[DIAMANTE_CON_CHIMENEA].razon_global - 1) < Decimal("0.2")
    # El resto de los prototipos queda claramente más lejos de 1.00.
    for clave, candidato in por_clave.items():
        if clave != DIAMANTE_CON_CHIMENEA:
            assert candidato.razon_global is not None
            assert candidato.razon_global > por_clave[DIAMANTE_CON_CHIMENEA].razon_global
