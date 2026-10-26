"""`ESTADO_CARGA`: cuánta ingeniería de una parte ya llegó (MODELO.md §3, D-30)."""

from decimal import Decimal

from obractrl.domain.partes.carga import EstadoDeCarga, estado_de_carga


def test_sin_nada_cargado_esta_incompleta_en_cero() -> None:
    c = estado_de_carga(cargado=Decimal("0"), presupuestado=Decimal("1000"))
    assert (c.estado, c.porcentaje_cargado, c.importe_pendiente) == (
        EstadoDeCarga.INCOMPLETO,
        Decimal("0.00"),
        Decimal("1000"),
    )


def test_a_medias_es_incompleta_y_dice_cuanto_falta() -> None:
    c = estado_de_carga(cargado=Decimal("920"), presupuestado=Decimal("1000"))
    assert c.estado is EstadoDeCarga.INCOMPLETO
    assert c.porcentaje_cargado == Decimal("92.00")
    assert c.importe_pendiente == Decimal("80")


def test_completa_solo_al_cien_por_ciento() -> None:
    assert estado_de_carga(cargado=Decimal("999.99"), presupuestado=Decimal("1000")).estado is EstadoDeCarga.INCOMPLETO
    c = estado_de_carga(cargado=Decimal("1000"), presupuestado=Decimal("1000"))
    assert (c.estado, c.porcentaje_cargado, c.importe_pendiente) == (EstadoDeCarga.COMPLETO, Decimal("100.00"), Decimal("0"))


def test_cargar_de_mas_no_pasa_de_cien() -> None:
    c = estado_de_carga(cargado=Decimal("1500"), presupuestado=Decimal("1000"))
    assert (c.estado, c.porcentaje_cargado, c.importe_pendiente) == (EstadoDeCarga.COMPLETO, Decimal("100.00"), Decimal("0"))


def test_sin_presupuesto_no_hay_contra_que_comparar() -> None:
    assert estado_de_carga(cargado=Decimal("0"), presupuestado=Decimal("0")).estado is EstadoDeCarga.INCOMPLETO
    assert estado_de_carga(cargado=Decimal("50"), presupuestado=Decimal("0")).estado is EstadoDeCarga.COMPLETO
