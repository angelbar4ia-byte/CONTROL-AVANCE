"""La fachada por bandas de altura (F1): cada m² cae en UNA sola banda, la altura se mide desde el suelo de la cara exterior, los vanos se
descuentan donde caen y solo cuentan las partes que suman con cara exterior."""

from __future__ import annotations

import itertools
from decimal import Decimal

import pytest

from obractrl.domain.cuantificacion.fachada_por_bandas import (
    TIPOS_DE_VANO_QUE_SE_DESCUENTAN,
    ErrorDeFachada,
    FranjaExterior,
    ParteConCaras,
    TramoConCaras,
    VanoEnTramo,
    bandas_de_fachada,
    franjas_exteriores,
    repartir_en_bandas,
    se_descuenta_de_la_fachada,
)

D = Decimal
BANDAS = bandas_de_fachada()


def _neto(franjas: list[FranjaExterior]) -> tuple[Decimal, Decimal, Decimal]:
    r = repartir_en_bandas(franjas, BANDAS)
    return tuple(b.neto_m2 for b in r.bandas)  # type: ignore[return-value]


def test_las_bandas_son_las_de_la_decision_y_no_se_encima_ni_dejan_huecos() -> None:
    assert [(b.clave, b.desde_m, b.hasta_m) for b in BANDAS] == [("baja", 0, D("3.00")), ("media", D("3.00"), D("4.20")), ("resto", D("4.20"), None)]
    assert all(a.hasta_m == b.desde_m for a, b in itertools.pairwise(BANDAS))


@pytest.mark.parametrize(("bajo", "alto"), [("0", "4"), ("4", "3"), ("3", "3"), ("-1", "4")])
def test_los_limites_deben_cumplir_cero_menor_baja_menor_alta(bajo: str, alto: str) -> None:
    with pytest.raises(ErrorDeFachada):
        bandas_de_fachada(D(bajo), D(alto))


def test_cada_metro_cuadrado_cae_en_una_sola_banda_para_cualquier_altura() -> None:
    """La suma de las bandas es el área de la franja, sin importar dónde empiece o termine (propiedad sobre una malla de alturas)."""
    cortes = [D(x) for x in ("0", "0.5", "2.99", "3", "3.01", "4.19", "4.2", "4.21", "6.5", "12")]
    for desde, hasta in itertools.combinations(cortes, 2):
        f = FranjaExterior(largo_m=D("7.3"), desde_m=desde, hasta_m=hasta)
        r = repartir_en_bandas([f], BANDAS)
        assert sum(b.bruto_m2 for b in r.bandas) == D("7.3") * (hasta - desde) == r.bruto_m2, (desde, hasta)


def test_el_reparto_en_los_bordes_de_las_bandas() -> None:
    assert _neto([FranjaExterior(D(10), D(0), D("3.00"))]) == (30, 0, 0)  # justo la banda baja
    assert _neto([FranjaExterior(D(10), D("3.00"), D("4.20"))]) == (0, 12, 0)  # justo la franja +3.00
    assert _neto([FranjaExterior(D(10), D("4.20"), D("5.00"))]) == (0, 0, 8)  # todo en el resto
    assert _neto([FranjaExterior(D(10), D(0), D("5.00"))]) == (30, 12, 8)  # cruza las tres


def test_un_vano_se_descuenta_donde_cae_y_solo_dentro_de_la_franja() -> None:
    vano = (D(2), D("2.5"), D("4.0"))  # 2 m de ancho de 2.50 a 4.00 m de altura
    r = repartir_en_bandas([FranjaExterior(D(10), D(0), D("4.20"), vanos=(vano,))], BANDAS)
    assert [(b.bruto_m2, b.vanos_m2, b.neto_m2) for b in r.bandas] == [(30, D("1.0"), 29), (12, D("2.0"), 10), (0, 0, 0)]
    # Un vano que cae fuera de la franja (el pretil de 3.00 a 4.20 no tiene la ventana de 1.00 a 2.00) no descuenta nada.
    fuera = repartir_en_bandas([FranjaExterior(D(10), D("3.00"), D("4.20"), vanos=((D(2), D("1.0"), D("2.0")),))], BANDAS)
    assert fuera.vanos_m2 == 0 and fuera.neto_m2 == 12


def test_nunca_sale_un_area_negativa() -> None:
    r = repartir_en_bandas([FranjaExterior(D(1), D(0), D(1), vanos=((D(5), D(0), D(1)),))], BANDAS)
    assert r.neto_m2 == 0 and all(b.neto_m2 >= 0 for b in r.bandas)


def _tramo(partes: list[ParteConCaras], **kw: object) -> TramoConCaras:
    return TramoConCaras(largo_m=D(6), partes=tuple(partes), **kw)  # type: ignore[arg-type]


def test_solo_la_cara_exterior_y_solo_las_partes_que_suman_dan_franjas() -> None:
    partes = [
        ParteConCaras(D(0), D(3), "exterior", "interior"),
        ParteConCaras(D(3), D("4.2"), "exterior", "exterior"),  # pretil: las dos caras
        ParteConCaras(D("4.2"), D(5), "exterior", "exterior", suma=False),  # cerramiento: no se aplana
    ]
    franjas = franjas_exteriores(_tramo(partes))
    assert sorted((f.desde_m, f.hasta_m) for f in franjas) == [(0, 3), (3, D("4.2")), (3, D("4.2"))]
    assert franjas_exteriores(_tramo([ParteConCaras(D(0), D(3), "interior", "interior")])) == []
    assert franjas_exteriores(_tramo([ParteConCaras(D(0), D(3), None, None)])) == []  # sin caras definidas no se adivina


def test_la_altura_se_mide_desde_el_suelo_de_la_cara_exterior() -> None:
    parte = [ParteConCaras(D(0), D(3), "exterior", "interior")]
    # Sin punto de nivel: desde el arranque del muro (su piso).
    assert [(f.desde_m, f.hasta_m) for f in franjas_exteriores(_tramo(parte, base_m=D("0.6")))] == [(0, 3)]
    # Terreno 0.30 por debajo del piso del muro (PB = 0): la cara exterior mide 3.30 m desde su suelo.
    assert [(f.desde_m, f.hasta_m) for f in franjas_exteriores(_tramo(parte, suelo_a_m=D("-0.3")))] == [(0, D("3.3"))]
    # Terreno por arriba del piso: la cara arranca ahí.
    assert [(f.desde_m, f.hasta_m) for f in franjas_exteriores(_tramo(parte, suelo_a_m=D("0.5")))] == [(0, D("2.5"))]
    # El suelo del lado B no cambia la cara A.
    assert [(f.desde_m, f.hasta_m) for f in franjas_exteriores(_tramo(parte, suelo_b_m=D("-1")))] == [(0, 3)]


def test_el_enrase_sobre_una_azotea_cae_en_la_banda_media_aunque_su_parte_empiece_en_cero_del_enrase() -> None:
    """Enrase de 3.00 a 4.20 sobre el arranque del muro: la banda se cuenta desde el suelo, no desde donde empieza la parte."""
    enrase = [ParteConCaras(D(0), D(3), "interior", "interior"), ParteConCaras(D(3), D("4.2"), "interior", "exterior")]
    assert _neto(franjas_exteriores(_tramo(enrase))) == (0, D("7.2"), 0)


def test_una_parte_invertida_o_vacia_se_rechaza() -> None:
    with pytest.raises(ErrorDeFachada):
        franjas_exteriores(_tramo([ParteConCaras(D(3), D(3), "exterior", None)]))


def test_los_vanos_del_tramo_viajan_a_su_franja_con_el_suelo_de_esa_cara() -> None:
    parte = [ParteConCaras(D(0), D(3), "exterior", "interior")]
    vano = VanoEnTramo(ancho_m=D(1), desde_m=D(1), hasta_m=D(2))
    (f,) = franjas_exteriores(_tramo(parte, suelo_a_m=D("-0.5"), vanos=(vano,)))
    assert f.vanos == ((1, D("1.5"), D("2.5")),)


@pytest.mark.parametrize(("tipo", "resta"), [("puerta", True), ("ventana", True), ("castillo", False), ("arco", False), ("paso", False), ("cancel", False), (None, False)])
def test_solo_las_puertas_y_las_ventanas_se_descuentan_de_la_fachada(tipo: str | None, resta: bool) -> None:
    """Decisión del usuario (2026-11-19): los castillos colocados comparten la tabla de vanos pero no son huecos de la fachada."""
    assert se_descuenta_de_la_fachada(tipo) is resta
    assert {"puerta", "ventana"} == TIPOS_DE_VANO_QUE_SE_DESCUENTAN
