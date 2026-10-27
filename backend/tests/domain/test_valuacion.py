"""«Mixto no se guarda, se reporta en porcentaje», y lo medido vuelve al paramétrico (§8.1)."""

from decimal import Decimal

from obractrl.domain.partes.valuacion import FormaDeValuacion, LineaValuada, valuar


def D(x: str) -> Decimal:  # noqa: N802
    return Decimal(x)


def test_una_parte_toda_por_pu_no_es_parametrica() -> None:
    v = valuar([LineaValuada(D("10"), D("100"), estimada=False)])
    assert (v.forma, v.porcentaje_parametrico, v.n_estimadas) == (FormaDeValuacion.PU, D("0.00"), 0)


def test_una_parte_toda_estimada_es_parametrica() -> None:
    v = valuar([LineaValuada(D("10"), D("100"), True), LineaValuada(D("5"), D("200"), True)])
    assert (v.forma, v.porcentaje_parametrico) == (FormaDeValuacion.PARAMETRICO, D("100.00"))


def test_mixto_se_reporta_en_porcentaje_del_importe() -> None:
    # 1,000 estimados y 3,000 por PU: 25 % paramétrico.
    v = valuar([LineaValuada(D("10"), D("100"), True), LineaValuada(D("30"), D("100"), False)])
    assert (v.forma, v.importe, v.importe_parametrico, v.porcentaje_parametrico) == (
        FormaDeValuacion.MIXTO,
        D("4000"),
        D("1000"),
        D("25.00"),
    )
    assert (v.n_estimadas, v.n_total) == (1, 2)


def test_sin_importe_cuenta_los_renglones() -> None:
    v = valuar([LineaValuada(D("0"), D("100"), True), LineaValuada(D("0"), D("100"), False)])
    assert (v.forma, v.porcentaje_parametrico) == (FormaDeValuacion.MIXTO, D("50.00"))
    assert valuar([]).porcentaje_parametrico == D("0.00")


def test_lo_medido_vuelve_al_parametrico_con_su_desviacion() -> None:
    # Estimaba 100 y se midieron 130 a $10: el paramétrico se quedó corto 30 %.
    v = valuar([LineaValuada(D("130"), D("10"), False, cant_estimada=D("100")), LineaValuada(D("5"), D("10"), False)])
    assert (v.estimado_original, v.medido, v.desviacion_pct) == (D("1000"), D("1300"), D("30.00"))
    assert valuar([LineaValuada(D("5"), D("10"), False)]).desviacion_pct is None
