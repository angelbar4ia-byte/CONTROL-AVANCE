"""`domain.ingenieria.reversion` contra la cimentación real de `ALAMO 18`
(`CONOCIMIENTO.md` §11.9, D-489 — "la reversión por destajo, probada").

Traducción fiel de `backend/core/tests/test_reversion_alamo18.py` del
cerebro: mismos 38 destajos, mismo 32/4/1/1, con el refinamiento de D-489
ya incluido desde el principio (nunca el conteo ingenuo de 16/38).
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

import pytest

from obractrl.domain.cargadores.ingenieria_lote import leer_ingenieria_lote
from obractrl.domain.cargadores.reporte import TipoPendiente
from obractrl.domain.ingenieria.reversion import ClaseReversionDestajo, revertir_destajos
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


def _revertir():
    cat = catalogo()
    presupuesto = cat.presupuesto_por_etapa(DIAMANTE_CON_CHIMENEA)
    _, insumos, _, errores, _ = leer_ingenieria_lote(leer_filas_crudas(INGENIERIA_ALAMO_18 / _CIMENTACION))
    assert errores == ()
    return revertir_destajos(insumos, cat.lineas, presupuesto, cat.composiciones)


def test_de_38_destajos_32_tienen_un_candidato_4_varios_1_compuesto_1_sin() -> None:
    resultados, _ = _revertir()
    assert len(resultados) == 38

    por_clase = Counter(r.clase for r in resultados)
    assert por_clase == {
        ClaseReversionDestajo.UNICO: 32,
        ClaseReversionDestajo.VARIOS: 4,
        ClaseReversionDestajo.COMPUESTO: 1,
        ClaseReversionDestajo.SIN: 1,
    }

    compuesto = next(r for r in resultados if r.clase is ClaseReversionDestajo.COMPUESTO)
    assert compuesto.clave == "MOC-12010"
    sin = next(r for r in resultados if r.clase is ClaseReversionDestajo.SIN)
    assert sin.clave == "MOS-2079"


def test_los_cuatro_varios_son_sumas_y_cierran_exacto_contra_el_presupuesto() -> None:
    """§11.9/D-489: "los cuatro ambiguos cierran exacto contra el
    presupuesto del prototipo" — 9+1, 1+1, 3+1, 1+1."""
    resultados, pendientes = _revertir()
    varios = {r.clave: r for r in resultados if r.clase is ClaseReversionDestajo.VARIOS}

    esperado = {
        "MOS-01030": (("ISN-01111", "ISN-01112"), Decimal("10"), {"ISN-01111": Decimal(9), "ISN-01112": Decimal(1)}),
        "MOH-01020": (("IHD-01090", "IHD-01100"), Decimal("2"), {"IHD-01090": Decimal(1), "IHD-01100": Decimal(1)}),
        "MOH-01030": (("IHD-01070", "IHD-01080"), Decimal("4"), {"IHD-01070": Decimal(3), "IHD-01080": Decimal(1)}),
        "MOE-01101": (("IEC-01020", "IEC-01030"), Decimal("2"), {"IEC-01020": Decimal(1), "IEC-01030": Decimal(1)}),
    }
    assert set(varios) == set(esperado)
    for clave, (candidatos, cantidad_real, reparto) in esperado.items():
        r = varios[clave]
        assert tuple(sorted(r.candidatos)) == candidatos
        assert r.cantidad_real == cantidad_real
        assert r.cantidad_presupuestada == cantidad_real
        assert r.reparto == reparto

    # Ninguno de los cuatro generó un pendiente DESTAJO_AMBIGUO: todos
    # cerraron exacto, así que no hay nada que proponer.
    assert all(p.tipo is not TipoPendiente.DESTAJO_AMBIGUO for p in pendientes)


def test_moc_12010_se_resuelve_en_profundidad_contra_est_01053() -> None:
    """§11.9: "`MOC-12010` ... se estaba buscando en la profundidad
    equivocada. Con la búsqueda ampliada a compuestos..." — `ZA1-000001`
    (el compuesto) lo cita, y `EST-01053` (la losa) cita a `ZA1-000001`
    seis veces por unidad: 1 × 6 = 6 zapatas."""
    resultados, _ = _revertir()
    r = next(x for x in resultados if x.clave == "MOC-12010")
    assert r.clase is ClaseReversionDestajo.COMPUESTO
    assert r.candidatos == ("EST-01053",)
    assert r.cantidad_real == Decimal("6")
    assert r.cantidad_presupuestada == Decimal("6")
    assert r.reparto == {"EST-01053": Decimal(1)}


def test_mos_2079_propone_las_dos_lecturas_contra_mos_02020() -> None:
    """§11.9: "`MOS-2079` es el destajo que sobra frente al único que
    falta" — misma descripción, misma cantidad, mismo precio; nunca se
    corrige por proximidad de clave, se reporta sin tocar nada."""
    resultados, pendientes = _revertir()
    sin = next(r for r in resultados if r.clave == "MOS-2079")
    assert sin.descripcion == "MO SALIDA SAN LAVADERO"
    assert sin.cantidad_real == Decimal("1")
    assert sin.precio == Decimal("312.50")
    assert sin.reparto is None

    pendiente = next(p for p in pendientes if p.tipo is TipoPendiente.DESTAJO_SIN_CANDIDATO)
    assert pendiente.valor_origen == "MOS-2079"
    assert pendiente.propuesta["clave_que_falta"] == "MOS-02020"
    assert pendiente.propuesta["coincide_evidencia"] is True
    assert set(pendiente.propuesta["lecturas_propuestas"]) == {
        "errata_de_captura",
        "trabajo_nuevo_no_autorizado",
    }
    assert pendiente.critico is False
