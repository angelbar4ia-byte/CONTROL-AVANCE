"""Cómo se mide una desviación (§3.6, §5.1).

La suma la hace SQL. Lo que se fija aquí son las tres decisiones que ninguna
consulta puede tomar: cuándo una desviación importa, qué hacer cuando no hay
contra qué comparar, y que gastar de menos **no** es lo mismo que ahorrar.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.presupuesto.rendimiento import (
    UMBRAL_DESVIACION,
    desviacion_de,
)


def desviacion(presupuestado: str, ejecutado: str, umbral: Decimal | None = None):
    return desviacion_de(
        importe_presupuestado=Decimal(presupuestado),
        importe_ejecutado=Decimal(ejecutado),
        umbral=umbral if umbral is not None else UMBRAL_DESVIACION,
    )


class TestDentroDeRango:
    def test_clavado(self) -> None:
        resultado = desviacion("100000", "100000")
        assert resultado.importe == Decimal(0)
        assert resultado.clasificacion == "dentro_de_rango"
        assert not resultado.relevante

    def test_una_desviacion_pequeña_no_es_noticia(self) -> None:
        # 1 % sobre cien mil: dentro del umbral del §3.6.
        assert desviacion("100000", "101000").clasificacion == "dentro_de_rango"

    def test_un_porcentaje_alto_sobre_un_monto_chico_tampoco(self) -> None:
        """Sin el piso de monto, un concepto de cien pesos con 20 % encabezaría
        la lista y empujaría fuera de vista uno de un millón con 3 %."""
        resultado = desviacion("100", "120")
        assert resultado.porcentaje == Decimal(20)
        assert resultado.clasificacion == "dentro_de_rango"


class TestSobreYBajoCosto:
    def test_gastar_de_mas(self) -> None:
        resultado = desviacion("100000", "130000")
        assert resultado.importe == Decimal(30000)
        assert resultado.porcentaje == Decimal(30)
        assert resultado.clasificacion == "sobre_costo"
        assert resultado.relevante

    def test_gastar_de_menos_se_distingue(self) -> None:
        """No es lo mismo que gastar de más: la pregunta que abre es otra."""
        resultado = desviacion("100000", "70000")
        assert resultado.importe == Decimal(-30000)
        assert resultado.clasificacion == "bajo_costo"

    def test_el_umbral_se_puede_configurar(self) -> None:
        """El §3.6 lo declara configurable por organización; la constante del
        dominio es el default, no una regla fija."""
        assert desviacion("100000", "108000").clasificacion == "sobre_costo"
        assert (
            desviacion("100000", "108000", umbral=Decimal(10)).clasificacion
            == "dentro_de_rango"
        )


class TestCuandoFaltaUnaDeLasDosCaras:
    def test_ejecutado_sin_presupuestar_es_extra(self) -> None:
        """Un extra-catálogo (§11.2). Su desviación no es «infinito por
        ciento»: es que la pregunta del porcentaje no aplica."""
        resultado = desviacion("0", "45000")
        assert resultado.importe == Decimal(45000)
        assert resultado.porcentaje is None
        assert resultado.clasificacion == "sin_presupuesto"
        assert resultado.relevante

    def test_presupuestado_y_sin_ejecutar_no_es_un_ahorro(self) -> None:
        """Es trabajo que no se hizo. Se separa de `bajo_costo` porque la acción
        es otra: ahí se revisa el precio, aquí se pregunta por qué no se hizo."""
        resultado = desviacion("80000", "0")
        assert resultado.clasificacion == "no_ejecutado"
        assert resultado.importe == Decimal(-80000)
        assert resultado.porcentaje == Decimal(-100)
        assert resultado.relevante

    def test_ni_presupuestado_ni_ejecutado_no_dice_nada(self) -> None:
        resultado = desviacion("0", "0")
        assert resultado.clasificacion == "dentro_de_rango"
        assert resultado.porcentaje is None
        assert not resultado.relevante


class TestNoRevienta:
    @pytest.mark.parametrize(
        ("presupuestado", "ejecutado"),
        [("0", "0"), ("0", "1"), ("1", "0"), ("-100", "50")],
    )
    def test_ningun_par_de_importes_lanza(
        self, presupuestado: str, ejecutado: str
    ) -> None:
        """Incluido el presupuesto negativo, que no debería existir pero llega
        de una carga de Excel y no puede tumbar la pantalla."""
        assert desviacion(presupuestado, ejecutado).clasificacion
