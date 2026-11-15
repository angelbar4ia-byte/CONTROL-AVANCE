"""Costos propone, Control de obra autoriza; las versiones se numeran al autorizar (plan de elementos de muro, fase I)."""

from __future__ import annotations

import pytest

from obractrl.domain.cuantificacion.autorizacion_de_elementos import (
    diferencias,
    estado_de_alta,
    puede_autorizar,
    requiere_autorizacion_el_cambio,
    siguiente_version,
    validar_que_autoriza,
    validar_que_propone,
)
from obractrl.domain.cuantificacion.elementos_parametricos import (
    ErrorDeElementoParametrico,
)


def test_solo_control_de_obra_autoriza() -> None:
    assert puede_autorizar("control_obra")
    for rol in ("costos", "residente", "supervisor", "super_intendente"):
        assert not puede_autorizar(rol)
        with pytest.raises(ErrorDeElementoParametrico, match="Solo Control de obra"):
            validar_que_autoriza(rol)


def test_solo_costos_y_control_proponen() -> None:
    validar_que_propone("costos")
    validar_que_propone("control_obra")
    with pytest.raises(ErrorDeElementoParametrico):
        validar_que_propone("residente")


def test_el_alta_de_control_nace_autorizada_y_la_de_costos_pendiente() -> None:
    assert estado_de_alta("control_obra") == "autorizado"
    assert estado_de_alta("costos") == "pendiente"


def test_un_cambio_pide_autorizacion_solo_si_lo_propone_costos_sobre_un_elemento_autorizado() -> None:
    assert requiere_autorizacion_el_cambio("costos", "autorizado")
    # Sobre un elemento aún provisional, Costos afina su propia propuesta.
    assert not requiere_autorizacion_el_cambio("costos", "pendiente")
    # Los cambios de Control de obra no piden autorización.
    assert not requiere_autorizacion_el_cambio("control_obra", "autorizado")
    assert not requiere_autorizacion_el_cambio("control_obra", "pendiente")


def test_la_version_siguiente_es_una_mas_que_la_mayor_autorizada() -> None:
    assert siguiente_version([]) == 1
    assert siguiente_version([1]) == 2
    assert siguiente_version([1, 3, 2]) == 4


def test_las_diferencias_se_dicen_en_palabras() -> None:
    antes = {"nombre": "K-1", "parametros": {"alto": 3, "ancho": 0.15}, "materiales": {"concreto": "MEZ-01020"}}
    despues = {"nombre": "K-1 reforzado", "parametros": {"alto": 3.5}, "materiales": {"concreto": "MEZ-01030"}}
    assert diferencias(antes, despues) == [
        "Nombre: K-1 → K-1 reforzado",
        "Parámetro alto: 3.0 → 3.5",
        "Material concreto: MEZ-01020 → MEZ-01030",
    ]
    # Lo que no viene en el cambio no cuenta, y lo igual no es diferencia.
    assert diferencias(antes, {"nombre": "K-1"}) == []
    assert diferencias({"parametros": {"alto": 3}}, {"parametros": {"alto": 3.0}}) == []
