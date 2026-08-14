"""Reglas de captura de avance (§6)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.avance.reglas import (
    ErrorDeCaptura,
    aplicar_captura,
    calcular_avance,
    resolver_estatus,
    validar_ejecucion,
    validar_programacion,
)
from obractrl.domain.shared.diccionario import EstatusActividad
from obractrl.domain.shared.valores import Avance

D = Decimal


class TestTopeDeProgramacion:
    """`cant_programada <= cant_base * 1.2` (§6)."""

    def test_permite_hasta_el_120_por_ciento(self) -> None:
        validar_programacion(D("120"), D("100"))

    def test_permite_el_limite_exacto(self) -> None:
        validar_programacion(D("100") * D("1.2"), D("100"))

    def test_rechaza_arriba_del_tope(self) -> None:
        with pytest.raises(ErrorDeCaptura) as exc:
            validar_programacion(D("120.01"), D("100"))
        assert exc.value.campo == "cant_programada"

    def test_rechaza_negativos(self) -> None:
        with pytest.raises(ErrorDeCaptura):
            validar_programacion(D("-1"), D("100"))

    def test_el_parametro_tope_es_ajustable_para_pruebas(self) -> None:
        """`tope` es parámetro por testabilidad; en producción siempre es 1.2.

        No es un configurable de §8.7 (a diferencia de IVA o el umbral de
        desviación): el §6 lo escribe como fórmula fija, y un CHECK de
        Postgres no puede leer una tabla de configuración, así que la BD no
        podría reflejar un valor distinto sin divergir de la app.
        """
        validar_programacion(D("150"), D("100"), tope=D("1.5"))
        with pytest.raises(ErrorDeCaptura):
            validar_programacion(D("150"), D("100"), tope=D("1.2"))


class TestTopeDeEjecucion:
    """`cant_ejecutada <= cant_programada` (§6)."""

    def test_permite_igual_a_la_programada(self) -> None:
        validar_ejecucion(D("80"), D("80"))

    def test_rechaza_arriba_de_la_programada(self) -> None:
        with pytest.raises(ErrorDeCaptura) as exc:
            validar_ejecucion(D("80.5"), D("80"))
        assert exc.value.campo == "cant_ejecutada"


class TestCalculoDeAvance:
    """`avance_pct = cant_ejecutada / cant_base * 100` (§6)."""

    @pytest.mark.parametrize(
        ("ejecutada", "base", "esperado"),
        [
            ("0", "100", "0.00"),
            ("50", "100", "50.00"),
            ("100", "100", "100.00"),
            ("1", "3", "33.33"),
            ("2", "3", "66.67"),
        ],
    )
    def test_porcentaje(self, ejecutada: str, base: str, esperado: str) -> None:
        assert calcular_avance(D(ejecutada), D(base)).pct == D(esperado)

    def test_base_cero_da_cero_y_no_revienta(self) -> None:
        assert calcular_avance(D("5"), D("0")).pct == D("0.00")

    def test_se_topa_en_cien(self) -> None:
        """Aunque la ejecutada supere la base, el avance no pasa de 100."""
        assert calcular_avance(D("150"), D("100")).pct == D("100.00")


class TestAutoEstatus:
    """`>= 90% -> casi` · `> 0 -> en_proceso` (§6)."""

    @pytest.mark.parametrize(
        ("pct", "esperado"),
        [
            ("0", EstatusActividad.PROGRAMADA),
            ("0.01", EstatusActividad.EN_PROCESO),
            ("89.99", EstatusActividad.EN_PROCESO),
            ("90", EstatusActividad.CASI),
            ("100", EstatusActividad.CASI),
        ],
    )
    def test_umbrales(self, pct: str, esperado: EstatusActividad) -> None:
        estatus = resolver_estatus(Avance(pct), EstatusActividad.PROGRAMADA)
        assert estatus is esperado

    @pytest.mark.parametrize(
        "estatus_de_flujo",
        [
            EstatusActividad.PENDIENTE_CIERRE,
            EstatusActividad.CONCLUIDA,
            EstatusActividad.RETRASADA,
            EstatusActividad.EXTRA_CATALOGO,
        ],
    )
    def test_no_pisa_los_estatus_de_flujo(
        self, estatus_de_flujo: EstatusActividad
    ) -> None:
        """Una actividad con cierre solicitado no vuelve sola a en_proceso."""
        assert resolver_estatus(Avance("50"), estatus_de_flujo) is estatus_de_flujo


class TestCapturaCompleta:
    def test_captura_valida_deriva_todo(self) -> None:
        r = aplicar_captura(
            cant_base=D("100"),
            cant_programada=D("100"),
            cant_ejecutada=D("95"),
        )
        assert r.avance.pct == D("95.00")
        assert r.estatus is EstatusActividad.CASI
        assert r.avance.esta_casi_listo

    def test_encadena_las_dos_validaciones(self) -> None:
        """Programar de más falla antes de mirar la ejecutada."""
        with pytest.raises(ErrorDeCaptura) as exc:
            aplicar_captura(
                cant_base=D("100"),
                cant_programada=D("130"),
                cant_ejecutada=D("10"),
            )
        assert exc.value.campo == "cant_programada"
