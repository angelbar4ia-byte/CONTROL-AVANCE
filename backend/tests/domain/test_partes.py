"""La parte de una obra: etapa o concepto independiente (D-575; migración 0074)."""

from __future__ import annotations

from decimal import Decimal

from obractrl.domain.partes.parte import (
    ActividadParaParte,
    TipoDeParte,
    agrupar_en_partes,
)

D = Decimal


def _a(id_: str, etapa: str | None, avance: str = "0", importe: str = "100", **kw):
    return ActividadParaParte(
        id=id_,
        descripcion=f"act {id_}",
        avance_pct=D(avance),
        importe=D(importe),
        etapa_id=etapa,
        etapa_nombre=f"Etapa {etapa}" if etapa else None,
        nivel_clave="PB",
        **kw,
    )


def test_las_actividades_de_una_etapa_son_una_parte() -> None:
    partes = agrupar_en_partes([_a("1", "e1"), _a("2", "e1"), _a("3", "e2")])
    assert [(p.tipo, p.id, p.actividad_ids) for p in partes] == [
        (TipoDeParte.ETAPA, "e1", ["1", "2"]),
        (TipoDeParte.ETAPA, "e2", ["3"]),
    ]
    assert partes[0].nombre == "PB · Etapa e1"


def test_un_concepto_independiente_es_una_parte_aparte_de_su_etapa() -> None:
    partes = agrupar_en_partes([_a("1", "e1"), _a("2", "e1", independiente=True), _a("3", "e1")])
    por_tipo = {p.tipo: p for p in partes}
    assert por_tipo[TipoDeParte.ETAPA].actividad_ids == ["1", "3"]
    assert por_tipo[TipoDeParte.CONCEPTO].actividad_ids == ["2"]
    assert por_tipo[TipoDeParte.CONCEPTO].id == "2"


def test_lo_que_no_tiene_etapa_no_queda_fuera() -> None:
    [parte] = agrupar_en_partes([_a("1", None), _a("2", None)])
    assert parte.tipo is TipoDeParte.SIN_ETAPA
    assert parte.actividad_ids == ["1", "2"]


def test_el_avance_de_la_parte_pesa_por_importe() -> None:
    [parte] = agrupar_en_partes([_a("1", "e1", "100", "300"), _a("2", "e1", "0", "100")])
    assert parte.avance_pct == D("75.00")
    assert parte.importe == D("400")


def test_sin_importes_el_avance_es_el_promedio() -> None:
    [parte] = agrupar_en_partes([_a("1", "e1", "100", "0"), _a("2", "e1", "50", "0")])
    assert parte.avance_pct == D("75.00")


def test_sin_actividades_no_hay_partes() -> None:
    assert agrupar_en_partes([]) == []
