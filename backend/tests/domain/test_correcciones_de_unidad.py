"""Correcciones propuestas al catálogo como nueva versión del concepto (dominio puro)."""

from __future__ import annotations

import pytest

from obractrl.domain.cuantificacion.correcciones_de_unidad import (
    CORRECCIONES_CONOCIDAS,
    correccion_conocida,
    resumen_de_la_correccion,
    siguiente_version,
    validar_que_autoriza,
    validar_que_propone,
)
from obractrl.domain.cuantificacion.elementos_parametricos import (
    ErrorDeElementoParametrico,
)


def test_la_unica_correccion_conocida_es_la_unidad_de_est_02330() -> None:
    (c,) = CORRECCIONES_CONOCIDAS
    assert (c["concepto_clave"], c["campo"], c["valor_catalogo"], c["valor_propuesto"]) == ("EST-02330", "unidad", "m2", "m")
    assert "Q59" in c["preguntas"] and "CATALOGO_DE_MATRICES:191" in c["fuente"]
    assert "no se construye" in c["nota"]


def test_solo_se_proponen_las_correcciones_conocidas() -> None:
    assert correccion_conocida(" est-02330 ", "unidad")["valor_propuesto"] == "m"
    for clave, campo in (("EST-02010", "unidad"), ("EST-02330", "descripcion")):
        with pytest.raises(ErrorDeElementoParametrico):
            correccion_conocida(clave, campo)


def test_costos_propone_y_solo_control_de_obra_autoriza() -> None:
    validar_que_propone("costos")
    validar_que_propone("control_obra")
    validar_que_autoriza("control_obra")
    for rol in ("costos", "residente", "supervisor"):
        with pytest.raises(ErrorDeElementoParametrico):
            validar_que_autoriza(rol)
    with pytest.raises(ErrorDeElementoParametrico):
        validar_que_propone("residente")


def test_las_versiones_se_numeran_desde_uno() -> None:
    assert siguiente_version([]) == 1
    assert siguiente_version([1, 2]) == 3
    assert "m2 → m" in resumen_de_la_correccion(CORRECCIONES_CONOCIDAS[0])
