"""Calendario del cronograma: semana laboral o natural (§6, §7.5, 0040).

Dos bloques. El primero prueba el objeto `CalendarioLaboral` solo —el eje de
días hábiles y su inversa—; el segundo, el motor CPM corriendo sobre él, que es
donde la elección se ve.

Las fechas esperadas están escritas a mano con el día de la semana al lado. Es
a propósito: un `assert` contra una expresión que reimplemente el salto de fin
de semana probaría que dos copias del mismo error coinciden.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from obractrl.domain.programacion.calendario import (
    DIAS_DE_LA_SEMANA,
    SEMANA_LABORAL,
    SEMANA_NATURAL,
    CalendarioInvalidoError,
    CalendarioLaboral,
)
from obractrl.domain.programacion.cpm import (
    Dependencia,
    NodoCPM,
    TipoDependencia,
    Tramo,
    calcular_cpm,
)

INICIO = date(2026, 3, 2)  # lunes
DOMINGO = date(2026, 3, 8)

FS = TipoDependencia.FIN_INICIO
SS = TipoDependencia.INICIO_INICIO
FF = TipoDependencia.FIN_FIN
SF = TipoDependencia.INICIO_FIN

L_A_V = CalendarioLaboral.de((1, 2, 3, 4, 5))
"""Lunes a viernes. Se usa en vez de `SEMANA_LABORAL` (lunes a sábado) en la
mayoría de las pruebas porque salta **dos** días seguidos, que es donde un
error de un día en la aritmética se nota."""


def _par(
    tipo: str,
    lag: float,
    *,
    calendario: CalendarioLaboral,
    dur_a: float = 5,
    dur_b: float = 3,
) -> dict:
    """A -> B con una sola relación, como en `test_cpm._par`."""
    nodos = [
        NodoCPM(ref="A", duracion_dias=dur_a),
        NodoCPM(
            ref="B",
            duracion_dias=dur_b,
            dependencias=(Dependencia("A", tipo=tipo, lag_dias=lag),),
        ),
    ]
    return calcular_cpm(nodos, INICIO, fecha_corte=INICIO, calendario=calendario)


class TestConstruccionDelCalendario:
    def test_normaliza_orden_y_repetidos(self) -> None:
        """`de()` es la puerta: lo que llega de la BD o del DTO viene sucio."""
        assert CalendarioLaboral.de([6, 1, 1, 3]).dias_habiles == (1, 3, 6)

    def test_none_es_semana_natural(self) -> None:
        """Una obra sin cronograma instanciado lee `None` de la columna."""
        assert CalendarioLaboral.de(None) == SEMANA_NATURAL

    def test_los_siete_dias_son_la_semana_natural(self) -> None:
        assert SEMANA_NATURAL.es_natural
        assert not SEMANA_LABORAL.es_natural
        assert SEMANA_NATURAL.dias_habiles == DIAS_DE_LA_SEMANA

    def test_el_orden_de_captura_no_cambia_la_identidad(self) -> None:
        """Dos calendarios con los mismos días son el mismo calendario: si no,
        reinstanciar un programa se vería como un cambio de configuración."""
        assert CalendarioLaboral.de([5, 4, 3, 2, 1]) == L_A_V
        assert hash(CalendarioLaboral.de([5, 4, 3, 2, 1])) == hash(L_A_V)

    def test_sin_dias_habiles_no_hay_calendario(self) -> None:
        with pytest.raises(CalendarioInvalidoError):
            CalendarioLaboral.de([])

    @pytest.mark.parametrize("dias", [[0], [8], [-1], [1, 9]])
    def test_solo_existen_los_dias_iso(self, dias: list[int]) -> None:
        with pytest.raises(CalendarioInvalidoError):
            CalendarioLaboral.de(dias)


class TestEjeDeDiasHabiles:
    def test_el_dia_cero_es_el_arranque_si_es_habil(self) -> None:
        assert L_A_V.conversor(INICIO)(0) == INICIO

    def test_salta_el_fin_de_semana(self) -> None:
        """Los cinco primeros índices son la semana; el sexto ya es el lunes."""
        fecha = L_A_V.conversor(INICIO)
        assert [fecha(i) for i in range(7)] == [
            date(2026, 3, 2),  # lunes
            date(2026, 3, 3),
            date(2026, 3, 4),
            date(2026, 3, 5),
            date(2026, 3, 6),  # viernes
            date(2026, 3, 9),  # lunes: sábado y domingo no cuentan
            date(2026, 3, 10),
        ]

    def test_semana_laboral_de_obra_trabaja_el_sabado(self) -> None:
        """Lunes a sábado, que es el default sugerido del giro (§7.5)."""
        fecha = SEMANA_LABORAL.conversor(INICIO)
        assert fecha(5) == date(2026, 3, 7)  # sábado: sí se trabaja
        assert fecha(6) == date(2026, 3, 9)  # lunes: solo se salta el domingo

    def test_arranque_en_dia_no_laborable_corre_al_siguiente_habil(self) -> None:
        """Una obra que arranca en domingo no arranca en domingo.

        Fijar el día 0 en un día que nadie trabaja dejaría a la primera
        actividad empezando y terminando en el mismo día para el Gantt.
        """
        assert L_A_V.primer_habil(DOMINGO) == date(2026, 3, 9)  # lunes
        assert L_A_V.conversor(DOMINGO)(0) == date(2026, 3, 9)

    def test_los_indices_negativos_van_hacia_atras(self) -> None:
        """El backward pass produce inicios tardíos anteriores al arranque
        cuando hay lags negativos, y esa fecha tiene que ser real."""
        fecha = L_A_V.conversor(INICIO)
        assert fecha(-1) == date(2026, 2, 27)  # viernes anterior
        assert fecha(-2) == date(2026, 2, 26)
        assert fecha(-3) == date(2026, 2, 25)

    def test_toda_fecha_convertida_es_un_dia_habil(self) -> None:
        fecha = SEMANA_LABORAL.conversor(INICIO)
        assert all(SEMANA_LABORAL.es_habil(fecha(i)) for i in range(-50, 200))

    def test_dias_entre_cuenta_solo_los_habiles(self) -> None:
        """De viernes a lunes hay un día de trabajo, no tres."""
        assert L_A_V.dias_entre(date(2026, 3, 6), date(2026, 3, 9)) == 1
        assert SEMANA_NATURAL.dias_entre(date(2026, 3, 6), date(2026, 3, 9)) == 3

    def test_dias_entre_tiene_signo(self) -> None:
        assert L_A_V.dias_entre(date(2026, 3, 9), date(2026, 3, 6)) == -1


class TestSemanaNaturalNoMueveNada:
    """El default tiene que ser indistinguible de la aritmética de siempre.

    Los golden de `tests/golden/test_golden_cpm.py` cubren el cronograma
    completo; esto cubre la conversión suelta, incluidos los casos raros que un
    cronograma realista no produce.
    """

    @pytest.mark.parametrize(
        "indice", [0, 1, 5, 100, -1, -7, 2.5, 8.3, -0.5, -3.7, 19.999999999999996]
    )
    def test_es_exactamente_la_suma_de_timedelta(self, indice: float) -> None:
        """Incluye índices fraccionarios: `duracion_dias` es `numeric(8,2)` y
        los lags son float, así que un índice casi entero por acumulación de
        error tiene que partir el día del mismo lado que antes."""
        assert SEMANA_NATURAL.conversor(INICIO)(indice) == INICIO + timedelta(
            days=indice
        )

    def test_dias_entre_es_la_resta_de_fechas(self) -> None:
        for delta in range(-40, 40):
            otra = INICIO + timedelta(days=delta)
            assert SEMANA_NATURAL.dias_entre(INICIO, otra) == delta

    def test_pasar_el_default_explicito_da_lo_mismo_que_omitirlo(self) -> None:
        nodos = [
            NodoCPM(ref="A", duracion_dias=5),
            NodoCPM(ref="B", duracion_dias=3, dependencias=(Dependencia("A"),)),
        ]
        omitido = calcular_cpm(nodos, INICIO, fecha_corte=INICIO)
        explicito = calcular_cpm(
            nodos, INICIO, fecha_corte=INICIO, calendario=SEMANA_NATURAL
        )
        assert omitido == explicito


class TestCPMConSemanaLaboral:
    def test_una_actividad_que_cruza_el_fin_de_semana(self) -> None:
        """7 días de trabajo desde el lunes: se trabaja hasta el martes.

        Con semana natural los mismos 7 días cierran el lunes 9 porque sábado y
        domingo cuentan. La convención de `fin_temprano` no cambia —es el día
        **siguiente** al último trabajado, igual que siempre—, solo qué día es.
        """
        nodos = [NodoCPM(ref="A", duracion_dias=7)]

        laboral = calcular_cpm(nodos, INICIO, fecha_corte=INICIO, calendario=L_A_V)
        assert laboral["A"].inicio_temprano == date(2026, 3, 2)  # lunes
        assert laboral["A"].fin_temprano == date(2026, 3, 11)  # miércoles

        natural = calcular_cpm(nodos, INICIO, fecha_corte=INICIO)
        assert natural["A"].fin_temprano == date(2026, 3, 9)

    def test_duracion_que_cae_justo_en_el_limite_de_la_semana(self) -> None:
        """5 días L-V desde el lunes cierran el lunes siguiente, no el sábado.

        Es el caso frontera: el último día trabajado es el viernes 6 y el
        `fin_temprano` —exclusivo— es el siguiente día **hábil**. Que nunca caiga
        en sábado es lo que deja al Gantt dibujar la barra sin casos especiales.
        """
        r = calcular_cpm(
            [NodoCPM(ref="A", duracion_dias=5)],
            INICIO,
            fecha_corte=INICIO,
            calendario=L_A_V,
        )
        assert r["A"].fin_temprano == date(2026, 3, 9)  # lunes, no sábado 7

    def test_una_actividad_que_arranca_en_dia_no_laborable(self) -> None:
        """La obra arranca en domingo: el cronograma empieza el lunes."""
        r = calcular_cpm(
            [NodoCPM(ref="A", duracion_dias=3)],
            DOMINGO,
            fecha_corte=DOMINGO,
            calendario=L_A_V,
        )
        assert r["A"].inicio_temprano == date(2026, 3, 9)  # lunes
        assert r["A"].fin_temprano == date(2026, 3, 12)

    def test_la_holgura_no_cambia_de_numero_al_cambiar_de_calendario(self) -> None:
        """A(5) -> {B(6), D(2)} -> C: D tiene 4 días de holgura con los dos.

        Es la mitad del diseño que más se presta a confusión: el calendario no
        cambia *cuántos* días de holgura hay —eso es aritmética de índices—,
        cambia *qué es* un día. Lo que sí se mueve son las fechas.
        """
        nodos = [
            NodoCPM(ref="A", duracion_dias=5),
            NodoCPM(ref="B", duracion_dias=6, dependencias=(Dependencia("A"),)),
            NodoCPM(ref="D", duracion_dias=2, dependencias=(Dependencia("A"),)),
            NodoCPM(
                ref="C",
                duracion_dias=2,
                dependencias=(Dependencia("B"), Dependencia("D")),
            ),
        ]
        natural = calcular_cpm(nodos, INICIO, fecha_corte=INICIO)
        laboral = calcular_cpm(nodos, INICIO, fecha_corte=INICIO, calendario=L_A_V)

        assert natural["D"].holgura == laboral["D"].holgura == 4
        assert {r for r, n in laboral.items() if n.es_critica} == {"A", "B", "C"}
        assert natural["C"].fin_temprano == date(2026, 3, 15)
        assert laboral["C"].fin_temprano == date(2026, 3, 19)

    def test_el_desfase_se_cuenta_en_dias_de_trabajo(self) -> None:
        """Misma fecha programada, mismo corte, distinto atraso.

        A dura 4 días desde el lunes, así que cierra el viernes 6 con los dos
        calendarios. Medido el lunes 9, con semana laboral el atraso es **un**
        día de trabajo perdido; con semana natural son tres casillas. El primero
        es el que se puede comparar contra la holgura (§6).
        """
        nodos = [NodoCPM(ref="A", duracion_dias=4)]
        corte = date(2026, 3, 9)  # lunes

        natural = calcular_cpm(nodos, INICIO, fecha_corte=corte)
        laboral = calcular_cpm(nodos, INICIO, fecha_corte=corte, calendario=L_A_V)

        assert natural["A"].fin_temprano == laboral["A"].fin_temprano == date(
            2026, 3, 6
        )
        assert natural["A"].desfase == 3.0
        assert laboral["A"].desfase == 1.0


class TestLasCuatroDependenciasEnDiasHabiles:
    """Los cuatro tipos con lag positivo y negativo, saltando el fin de semana.

    A dura 5 (lunes 2 → índice 5, que es el lunes 9) y B dura 3. El lag se
    cuenta en la misma escala: un `FS` de +2 sobre un fin que cae en lunes lleva
    a B al miércoles 11, no al miércoles de la semana anterior.
    """

    def test_fin_inicio(self) -> None:
        r = _par(FS, 0, calendario=L_A_V)
        assert r["B"].inicio_temprano == date(2026, 3, 9)  # lunes
        assert r["B"].fin_temprano == date(2026, 3, 12)

    def test_fin_inicio_con_lag_positivo(self) -> None:
        r = _par(FS, 2, calendario=L_A_V)
        assert r["B"].inicio_temprano == date(2026, 3, 11)  # índice 7

    def test_fin_inicio_con_lag_negativo(self) -> None:
        """El traslape también son días hábiles: dos días antes del índice 5
        es el jueves 5, no el sábado."""
        r = _par(FS, -2, calendario=L_A_V)
        assert r["B"].inicio_temprano == date(2026, 3, 5)  # jueves, índice 3

    def test_inicio_inicio(self) -> None:
        r = _par(SS, 0, calendario=L_A_V)
        assert r["B"].inicio_temprano == INICIO

    def test_inicio_inicio_con_lag_positivo(self) -> None:
        r = _par(SS, 2, calendario=L_A_V)
        assert r["B"].inicio_temprano == date(2026, 3, 4)  # índice 2

    def test_inicio_inicio_con_lag_negativo_se_clampea_al_arranque(self) -> None:
        """Igual que con semana natural: el día 0 acota por abajo (§6)."""
        r = _par(SS, -2, calendario=L_A_V)
        assert r["B"].inicio_temprano == INICIO

    def test_fin_fin(self) -> None:
        """B no puede cerrar antes que A: cierran el mismo índice 5."""
        r = _par(FF, 0, calendario=L_A_V)
        assert r["B"].inicio_temprano == date(2026, 3, 4)  # índice 2
        assert r["B"].fin_temprano == r["A"].fin_temprano == date(2026, 3, 9)

    def test_fin_fin_con_lag_positivo(self) -> None:
        r = _par(FF, 2, calendario=L_A_V)
        assert r["B"].fin_temprano == date(2026, 3, 11)  # índice 7
        assert r["B"].inicio_temprano == date(2026, 3, 6)  # índice 4

    def test_fin_fin_con_lag_negativo(self) -> None:
        """B cierra dos días de trabajo antes que A: el jueves 5."""
        r = _par(FF, -2, calendario=L_A_V)
        assert r["B"].fin_temprano == date(2026, 3, 5)  # índice 3
        assert r["B"].inicio_temprano == INICIO

    def test_inicio_fin(self) -> None:
        """La provisional que solo se retira cuando arranca la definitiva."""
        r = _par(SF, 5, calendario=L_A_V)
        assert r["B"].fin_temprano == date(2026, 3, 9)  # índice 5
        assert r["B"].inicio_temprano == date(2026, 3, 4)  # índice 2

    def test_inicio_fin_con_lag_negativo_se_clampea(self) -> None:
        r = _par(SF, -2, calendario=L_A_V)
        assert r["B"].inicio_temprano == INICIO


class TestTramosConSemanaLaboral:
    """El muro que para para colar la losa, en días hábiles (§7.6).

    14 días de **trabajo** repartidos en 19 de span: dos tramos de 10 y 4 con
    el segundo arrancando en el día 15. Con semana laboral las tres cifras son
    días hábiles, y por eso el hueco que el Gantt dibuja punteado ocupa más
    casillas de calendario que días tiene.
    """

    def _muro(self) -> NodoCPM:
        return NodoCPM(
            ref="MURO",
            duracion_dias=14,
            tramos=(Tramo(duracion_dias=10), Tramo(duracion_dias=4, offset_dias=15)),
        )

    def test_el_span_manda_sobre_la_duracion(self) -> None:
        """19 días hábiles desde el lunes 2 cierran el viernes 27, no el 21."""
        laboral = calcular_cpm(
            [self._muro()], INICIO, fecha_corte=INICIO, calendario=L_A_V
        )
        assert laboral["MURO"].fin_temprano == date(2026, 3, 27)  # viernes

        natural = calcular_cpm([self._muro()], INICIO, fecha_corte=INICIO)
        assert natural["MURO"].fin_temprano == date(2026, 3, 21)

    def test_la_sucesora_espera_al_span_no_al_trabajo(self) -> None:
        nodos = [
            self._muro(),
            NodoCPM(
                ref="APLANADO",
                duracion_dias=3,
                dependencias=(Dependencia("MURO", tipo=FS),),
            ),
        ]
        r = calcular_cpm(nodos, INICIO, fecha_corte=INICIO, calendario=L_A_V)
        assert r["APLANADO"].inicio_temprano == date(2026, 3, 27)
        assert r["APLANADO"].fin_temprano == date(2026, 4, 1)

    def test_la_pausa_ocupa_mas_calendario_que_dias_habiles_tiene(self) -> None:
        """El punto exacto donde alguien se va a confundir.

        La pausa son 5 días de trabajo —del índice 10 al 15— pero se dibuja
        sobre 7 casillas de calendario porque le cae un fin de semana en medio.
        `offset_dias` cuenta lo primero, no lo segundo.
        """
        fecha = L_A_V.conversor(INICIO)
        cierra_el_primer_tramo = fecha(10)
        arranca_el_segundo = fecha(15)

        assert cierra_el_primer_tramo == date(2026, 3, 16)  # lunes
        assert arranca_el_segundo == date(2026, 3, 23)  # lunes
        assert (arranca_el_segundo - cierra_el_primer_tramo).days == 7
        assert L_A_V.dias_entre(cierra_el_primer_tramo, arranca_el_segundo) == 5
