"""Cuántas cuadrillas hacen falta por frente (§8.3, §7.6).

El jefe de obra formuló la pregunta así: *"indicar cuántas cuadrillas necesito
para alcanzar la meta programada por frente"*. La cuenta es una división, y lo
que estas pruebas fijan son las tres decisiones que la rodean:

 1. **Una jornada es una cuadrilla trabajando un día.** 40 jornadas en una
    semana de 5 días hábiles son 8 cuadrillas. Si esa equivalencia cambiara sin
    querer, el número con el que se contrata quedaría mal por un factor.
 2. **No se redondea.** 2.3 cuadrillas significa que dos aprietan y tres
    sobran; redondear aquí escondería esa lectura justo donde se decide.
 3. **Lo que pide cero no desaparece.** Un frente que todavía no arranca sale
    con ceros, no omitido: esconderlo dejaría la tabla con menos renglones cada
    vez que se mueve el rango, sin decir por qué.

Módulo puro: sin BD, sin reloj (§12.11).
"""

from __future__ import annotations

from decimal import Decimal

from obractrl.domain.planeacion.cuadrillas import (
    cuadrillas_necesarias,
    demanda_por_frente,
)


class TestLaDivision:
    def test_una_jornada_es_una_cuadrilla_un_dia(self) -> None:
        # 40 jornadas en una semana de 5 días hábiles: 8 cuadrillas.
        assert cuadrillas_necesarias(
            jornadas=Decimal(40), dias_habiles=5
        ) == Decimal(8)

    def test_no_redondea_hacia_arriba(self) -> None:
        # 2.3 dice que dos aprietan y tres sobran. Redondear a 3 prometería
        # gente de más; a 2, una meta que no se cumple.
        assert cuadrillas_necesarias(
            jornadas=Decimal("11.5"), dias_habiles=5
        ) == Decimal("2.30")

    def test_un_periodo_sin_dias_habiles_no_divide_entre_cero(self) -> None:
        # Pasa en un rango que cae entero en días de descanso: la respuesta es
        # "no hace falta nadie", no una excepción.
        assert cuadrillas_necesarias(jornadas=Decimal(40), dias_habiles=0) == 0

    def test_sin_jornadas_no_hace_falta_nadie(self) -> None:
        assert cuadrillas_necesarias(jornadas=Decimal(0), dias_habiles=5) == 0


class TestDemandaPorFrente:
    _HABILES = (5, 5, 5)

    def test_convierte_cada_periodo_y_saca_el_pico(self) -> None:
        demanda = demanda_por_frente(
            jornadas_por_frente={
                "est": [Decimal(10), Decimal(40), Decimal(20)],
            },
            dias_habiles_por_periodo=self._HABILES,
        )
        fila = demanda[0]
        assert fila.cuadrillas == (Decimal(2), Decimal(8), Decimal(4))
        assert fila.total_jornadas == Decimal(70)
        # El pico es la cifra con la que se contrata: quien te presta dos
        # cuadrillas todo el mes no te resuelve la semana que pide ocho.
        assert fila.pico_cuadrillas == Decimal(8)

    def test_un_frente_sin_carga_sale_con_ceros_y_no_omitido(self) -> None:
        demanda = demanda_por_frente(
            jornadas_por_frente={"aca": [Decimal(0), Decimal(0), Decimal(0)]},
            dias_habiles_por_periodo=self._HABILES,
        )
        assert len(demanda) == 1
        assert demanda[0].pico_cuadrillas == 0

    def test_ordena_por_pico_de_mayor_a_menor(self) -> None:
        # La pregunta es a quién hay que conseguirle más gente.
        demanda = demanda_por_frente(
            jornadas_por_frente={
                "chico": [Decimal(5), Decimal(5), Decimal(5)],
                "grande": [Decimal(50), Decimal(5), Decimal(5)],
            },
            dias_habiles_por_periodo=self._HABILES,
        )
        assert [d.frente_id for d in demanda] == ["grande", "chico"]

    def test_una_lista_corta_se_completa_con_ceros(self) -> None:
        # Menos jornadas que columnas dejaría celdas sin cubrir.
        demanda = demanda_por_frente(
            jornadas_por_frente={"est": [Decimal(10)]},
            dias_habiles_por_periodo=self._HABILES,
        )
        assert demanda[0].jornadas == (Decimal(10), Decimal(0), Decimal(0))

    def test_una_lista_larga_se_recorta_al_rango(self) -> None:
        # Sumar trabajo de fuera del rango consultado inflaría el total.
        demanda = demanda_por_frente(
            jornadas_por_frente={
                "est": [Decimal(10), Decimal(10), Decimal(10), Decimal(999)],
            },
            dias_habiles_por_periodo=self._HABILES,
        )
        assert demanda[0].total_jornadas == Decimal(30)

    def test_un_periodo_de_descanso_no_pide_cuadrillas(self) -> None:
        demanda = demanda_por_frente(
            jornadas_por_frente={"est": [Decimal(10), Decimal(10)]},
            dias_habiles_por_periodo=(5, 0),
        )
        assert demanda[0].cuadrillas == (Decimal(2), Decimal(0))
