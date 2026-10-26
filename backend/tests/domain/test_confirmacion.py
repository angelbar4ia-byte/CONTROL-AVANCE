"""Confirmar el avance antes de estimar (migración 0070; cerebro D-533..D-535)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.avance.confirmacion import (
    AlertaDeRespaldo,
    ErrorDeConfirmacion,
    EstadoDeConfirmacion,
    alerta_de_respaldo,
    estado_de_confirmacion,
    exigir_algo_que_confirmar,
    exigir_residente,
)
from obractrl.domain.shared.diccionario import Rol

D = Decimal


class TestQuienConfirma:
    def test_confirma_el_residente(self) -> None:
        exigir_residente(Rol.RESIDENTE)

    @pytest.mark.parametrize("rol", [Rol.SUPERVISOR, Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE])
    def test_los_demas_revisan_pero_no_confirman(self, rol: Rol) -> None:
        with pytest.raises(ErrorDeConfirmacion, match="residente"):
            exigir_residente(rol)

    def test_sin_avance_no_hay_nada_que_confirmar(self) -> None:
        with pytest.raises(ErrorDeConfirmacion, match="nada que confirmar"):
            exigir_algo_que_confirmar(D(0))
        exigir_algo_que_confirmar(D("0.01"))


class TestEstadoDeLaConfirmacion:
    def test_nunca_confirmada(self) -> None:
        assert estado_de_confirmacion(D(60), None) is EstadoDeConfirmacion.SIN_CONFIRMAR

    def test_lo_confirmado_es_lo_ejecutado(self) -> None:
        assert estado_de_confirmacion(D(60), D(60)) is EstadoDeConfirmacion.CONFIRMADA
        assert estado_de_confirmacion(D("60.0"), D("60.000000")) is EstadoDeConfirmacion.CONFIRMADA

    def test_si_el_avance_cambio_despues_hay_que_volver_a_confirmar(self) -> None:
        assert estado_de_confirmacion(D(80), D(60)) is EstadoDeConfirmacion.DESACTUALIZADA
        # También si bajó: una corrección tampoco está confirmada.
        assert estado_de_confirmacion(D(50), D(60)) is EstadoDeConfirmacion.DESACTUALIZADA


class TestAlertaDeRespaldo:
    def test_sin_confirmar_todo_lo_estimado_carece_de_respaldo(self) -> None:
        assert alerta_de_respaldo(D(100), None) == (AlertaDeRespaldo.SIN_CONFIRMAR, D(100))

    def test_estimar_mas_de_lo_confirmado_alerta_y_dice_cuanto(self) -> None:
        assert alerta_de_respaldo(D(100), D(80)) == (AlertaDeRespaldo.POR_ENCIMA, D(20))

    def test_estimar_lo_confirmado_o_menos_no_alerta(self) -> None:
        assert alerta_de_respaldo(D(80), D(80)) is None
        # Bajar la cantidad es justo la salida de la alerta (D-535).
        assert alerta_de_respaldo(D(50), D(80)) is None

    def test_un_renglon_en_cero_no_alerta(self) -> None:
        assert alerta_de_respaldo(D(0), None) is None
