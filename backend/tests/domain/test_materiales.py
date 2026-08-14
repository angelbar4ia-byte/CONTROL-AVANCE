"""Regla de signo del movimiento de almacén (§10.5, §7.7)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.materiales.reglas import (
    ErrorDeMaterial,
    MovimientoAlmacen,
    validar_signo_salida,
)
from obractrl.domain.shared.valores import Dinero

D = Decimal


class TestValidarSignoSalida:
    def test_signo_positivo_coincide_con_motivo_positivo(self) -> None:
        validar_signo_salida(D("10"), 1)  # no debe levantar

    def test_signo_negativo_coincide_con_motivo_negativo(self) -> None:
        validar_signo_salida(D("-10"), -1)

    def test_motivo_negativo_con_cantidad_positiva_levanta(self) -> None:
        """P.ej. "Salida para producción" (signo -) capturada en positivo."""
        with pytest.raises(ErrorDeMaterial, match="signo"):
            validar_signo_salida(D("10"), -1)

    def test_motivo_positivo_con_cantidad_negativa_levanta(self) -> None:
        """P.ej. "Recepción de material" (signo +) capturada en negativo."""
        with pytest.raises(ErrorDeMaterial, match="signo"):
            validar_signo_salida(D("-10"), 1)

    def test_cantidad_cero_es_invalida_con_cualquier_motivo(self) -> None:
        with pytest.raises(ErrorDeMaterial, match="cero"):
            validar_signo_salida(D("0"), 1)
        with pytest.raises(ErrorDeMaterial, match="cero"):
            validar_signo_salida(D("0"), -1)

    def test_motivo_con_signo_fuera_de_invariante_levanta(self) -> None:
        with pytest.raises(ErrorDeMaterial, match="Signo de motivo"):
            validar_signo_salida(D("10"), 2)
        with pytest.raises(ErrorDeMaterial, match="Signo de motivo"):
            validar_signo_salida(D("10"), 0)


class TestMovimientoAlmacen:
    def test_construye_con_datos_consistentes(self) -> None:
        mov = MovimientoAlmacen(cantidad=D("-5"), costo=Dinero("100"), motivo_signo=-1)
        assert mov.cantidad == D("-5")
        assert mov.costo == Dinero("100")
        assert mov.motivo_signo == -1

    def test_signo_inconsistente_no_construye(self) -> None:
        with pytest.raises(ErrorDeMaterial, match="signo"):
            MovimientoAlmacen(cantidad=D("5"), costo=Dinero("100"), motivo_signo=-1)

    def test_cantidad_cero_no_construye(self) -> None:
        with pytest.raises(ErrorDeMaterial, match="cero"):
            MovimientoAlmacen(cantidad=D("0"), costo=Dinero("0"), motivo_signo=1)
