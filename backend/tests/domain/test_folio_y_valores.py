"""Folios (§3.2) y value objects (§11.1)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.shared.folio import Folio, interpretar_campo_semana
from obractrl.domain.shared.valores import Avance, Cantidad, Dinero, PrecioUnitario

D = Decimal


class TestFolio:
    """`FOLIO = [E-]WWYY-NNN` (§3.2)."""

    def test_formatea_con_ceros(self) -> None:
        assert str(Folio(semana=5, anio=2026, consecutivo=7)) == "0526-007"

    def test_marca_el_origen_erp(self) -> None:
        assert str(Folio(semana=21, anio=2026, consecutivo=3, es_erp=True)) == "E-2126-003"

    def test_ida_y_vuelta(self) -> None:
        f = Folio(semana=21, anio=2026, consecutivo=3, es_erp=True)
        assert Folio.parsear(str(f)) == f

    def test_el_consecutivo_lo_comparten_erp_y_no_erp(self) -> None:
        """El contador es continuo por semana, sin importar el origen (§3.2)."""
        no_erp = Folio.siguiente(semana=21, anio=2026, ultimo_consecutivo=7)
        erp = Folio.siguiente(semana=21, anio=2026, ultimo_consecutivo=8, es_erp=True)
        assert no_erp.consecutivo == 8
        assert erp.consecutivo == 9

    @pytest.mark.parametrize("semana", [0, 54])
    def test_rechaza_semanas_fuera_de_rango(self, semana: int) -> None:
        with pytest.raises(ValueError):
            Folio(semana=semana, anio=2026, consecutivo=1)


class TestCampoSemanaAmbiguo:
    """Un solo campo puede traer semana, código o folio (§3.2)."""

    def test_folio_completo_manda(self) -> None:
        semana, anio, folio = interpretar_campo_semana("2126-003")
        assert (semana, anio) == (21, 2026)
        assert folio is not None
        assert folio.consecutivo == 3

    def test_codigo_de_semana(self) -> None:
        assert interpretar_campo_semana("S-2126")[:2] == (21, 2026)

    def test_semana_suelta_usa_el_anio_en_curso(self) -> None:
        assert interpretar_campo_semana(21, anio_default=2026)[:2] == (21, 2026)

    def test_folio_erp_conserva_el_origen(self) -> None:
        _, _, folio = interpretar_campo_semana("E-2126-003")
        assert folio is not None and folio.es_erp

    @pytest.mark.parametrize("basura", ["", "   ", "abc", None])
    def test_lo_ininteligible_es_error(self, basura: str | None) -> None:
        with pytest.raises(ValueError):
            interpretar_campo_semana(basura)


class TestDinero:
    def test_redondea_a_centavos(self) -> None:
        assert Dinero("10.005").monto == D("10.01")

    def test_rechaza_float(self) -> None:
        """Los importes van en DECIMAL; un float mete ruido binario (§3.5)."""
        with pytest.raises(TypeError):
            Dinero(10.005)  # type: ignore[arg-type]

    def test_iva_configurable(self) -> None:
        assert Dinero("100").con_iva(D("0.16")).monto == D("116.00")


class TestCantidad:
    def test_no_suma_unidades_distintas(self) -> None:
        with pytest.raises(ValueError, match="distinta unidad"):
            Cantidad("10", "m2") + Cantidad("5", "m3")

    def test_convierte_con_factor(self) -> None:
        c = Cantidad("1", "ton").convertir("kg", 1000)
        assert c.valor == D("1000.000000") and c.unidad == "kg"

    def test_importe(self) -> None:
        assert Cantidad("3", "m2").importe(Dinero("150")).monto == D("450.00")


class TestAvance:
    @pytest.mark.parametrize("pct", ["-0.01", "100.01"])
    def test_acotado_a_0_100(self, pct: str) -> None:
        with pytest.raises(ValueError):
            Avance(pct)

    def test_umbral_casi(self) -> None:
        assert Avance("90").esta_casi_listo
        assert not Avance("89.99").esta_casi_listo


class TestPrecioUnitario:
    def test_el_destajo_no_puede_exceder_el_total(self) -> None:
        with pytest.raises(ValueError, match="porción del total"):
            PrecioUnitario(total=Dinero("100"), destajo=Dinero("150"))

    def test_precio_por_modo(self) -> None:
        """destajo y subcontrato pagan MO; concepto paga el CPU completo (§6)."""
        pu = PrecioUnitario(total=Dinero("500"), destajo=Dinero("120"))
        assert pu.para_modo("destajo") == Dinero("120")
        assert pu.para_modo("subcontrato") == Dinero("120")
        assert pu.para_modo("concepto") == Dinero("500")

    def test_los_materiales_son_el_resto(self) -> None:
        pu = PrecioUnitario(total=Dinero("500"), destajo=Dinero("120"))
        assert pu.materiales == Dinero("380")
