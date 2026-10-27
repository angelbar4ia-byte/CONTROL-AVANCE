"""Cambios y adicionales sobre el prototipo (D-573, D-574, D-575)."""

from decimal import Decimal

import pytest

from obractrl.domain.partes.modificacion import (
    ErrorDeModificacion,
    TipoDeModificacion,
    modificar,
)

D = Decimal


def test_un_cambio_puede_restar_y_se_elimina_del_presupuesto() -> None:
    m = modificar(TipoDeModificacion.CAMBIO, cantidad_actual=D("100"), delta=D("-30"))
    assert (m.cantidad_antes, m.delta, m.cantidad_despues) == (D("100"), D("-30"), D("70"))
    # Eliminar el concepto es dejarlo en cero.
    assert modificar(TipoDeModificacion.CAMBIO, cantidad_actual=D("100"), delta=D("-100")).cantidad_despues == 0


def test_un_cambio_tambien_puede_sumar() -> None:
    assert modificar(TipoDeModificacion.CAMBIO, cantidad_actual=D("10"), delta=D("5")).cantidad_despues == 15


def test_un_adicional_solo_suma() -> None:
    assert modificar(TipoDeModificacion.ADICIONAL, cantidad_actual=D("0"), delta=D("12")).cantidad_despues == 12
    with pytest.raises(ErrorDeModificacion, match="solo suma"):
        modificar(TipoDeModificacion.ADICIONAL, cantidad_actual=D("10"), delta=D("-1"))


def test_la_cantidad_no_queda_negativa() -> None:
    with pytest.raises(ErrorDeModificacion, match="cero"):
        modificar(TipoDeModificacion.CAMBIO, cantidad_actual=D("10"), delta=D("-11"))


def test_lo_que_no_cambia_nada_no_se_registra() -> None:
    with pytest.raises(ErrorDeModificacion, match="no cambia nada"):
        modificar(TipoDeModificacion.CAMBIO, cantidad_actual=D("10"), delta=D("0"))
