"""Los conceptos que paga un elemento por contexto y escalón (dominio puro; plan de elementos de muro, fase C)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.cuantificacion.conceptos_de_elemento import (
    ConceptoDeElemento,
    Contexto,
    avisos_de_altura,
    describir_contexto,
    normalizar_clave_propuesta,
    normalizar_toma,
    ranura_de,
    resolver,
    validar_alta,
    validar_contexto,
)
from obractrl.domain.cuantificacion.elementos_parametricos import ErrorDeElementoParametrico

D = Decimal


def _c(clave: str, toma: dict[str, bool], *, nmin: int | None = None, nmax: int | None = None, ubic: str | None = None,
       hasta: str | None = None, unidad: str = "m²", estado: str = "autorizado") -> ConceptoDeElemento:
    return ConceptoDeElemento(
        id=clave + str(nmin) + str(hasta), clave=clave, descripcion=clave, unidad=unidad, toma=toma,
        contexto=Contexto(nmin, nmax, ubic), alto_hasta_m=D(hasta) if hasta else None, estado=estado,
        concepto_id=None if estado == "propuesto" else clave,
    )


def _escalera_k1() -> list[ConceptoDeElemento]:
    """Acero por pieza con los cuatro escalones de K-1 del catálogo y el colado por ml (EST-02110)."""
    acero = {"acero": True, "alambre": True}
    return [
        _c("EST-10013", acero, hasta="1.00", unidad="pza"),
        _c("EST-10012", acero, hasta="1.50", unidad="pza"),
        _c("EST-10010", acero, hasta="4.00", unidad="pza"),
        _c("EST-10011", acero, hasta="6.00", unidad="pza"),
        _c("EST-02110", {"concreto": True, "cimbra": True}, unidad="ml"),
    ]


def test_la_ranura_sale_de_lo_que_toma() -> None:
    assert ranura_de({"acero": True, "estribos": True}) == "acero"
    assert ranura_de({"concreto": True, "cimbra": True}) == "colado"
    assert ranura_de({"acero": True, "cimbra": True}) == "completo"
    assert ranura_de({"acero": False}) is None


def test_una_toma_vacia_se_rechaza() -> None:
    with pytest.raises(ErrorDeElementoParametrico):
        normalizar_toma({"acero": False})
    assert normalizar_toma({"acero": True, "concreto": False, "x": True}) == {"acero": True}


def test_el_mismo_elemento_paga_un_concepto_en_los_niveles_1_y_2_y_otro_desde_el_3() -> None:
    """M-106: EST-02010 en los niveles 1 y 2; EST-02011 del nivel 3 en adelante."""
    toma = {"concreto": True, "cimbra": True, "acero": True}
    cs = [_c("EST-02010", toma, nmin=1, nmax=2), _c("EST-02011", toma, nmin=3)]
    for nivel, esperado in ((1, "EST-02010"), (2, "EST-02010"), (3, "EST-02011"), (5, "EST-02011")):
        r = resolver(cs, nivel=nivel)
        assert {c.clave for c in r.por_parte.values()} == {esperado}, nivel
        assert r.avisos == []


def test_el_acero_elige_el_primer_escalon_que_alcanza_el_alto() -> None:
    cs = _escalera_k1()
    for alto, esperado in (("0.80", "EST-10013"), ("1.00", "EST-10013"), ("1.01", "EST-10012"), ("2.60", "EST-10010"), ("4.00", "EST-10010"), ("5.00", "EST-10011")):
        r = resolver(cs, nivel=1, alto_m=D(alto))
        assert r.por_parte["acero"].clave == esperado, alto
        assert r.por_parte["concreto"].clave == r.por_parte["cimbra"].clave == "EST-02110"
        assert r.avisos == []


def test_un_alto_sin_escalon_avisa_y_usa_el_ultimo() -> None:
    r = resolver(_escalera_k1(), nivel=1, alto_m=D("7.00"))
    assert r.por_parte["acero"].clave == "EST-10011"
    assert any("no tiene escalón" in a and "6" in a for a in r.avisos)
    assert any("no tiene escalón" in a for a in avisos_de_altura(_escalera_k1(), D("6.50")))
    assert avisos_de_altura(_escalera_k1(), D("6.00")) == []


def test_sin_alto_no_se_puede_elegir_el_escalon() -> None:
    r = resolver(_escalera_k1(), nivel=1)
    assert any("no se dio el alto" in a for a in r.avisos)


def test_una_parte_sin_concepto_avisa_que_se_perderia() -> None:
    r = resolver([_c("EST-02110", {"concreto": True, "cimbra": True})], nivel=1, alto_m=D("2.6"))
    assert any(a.startswith("Sin concepto") and "acero" in a for a in r.avisos)


def test_una_parte_tomada_dos_veces_se_rechaza_al_guardar() -> None:
    existentes = [_c("EST-02110", {"concreto": True, "cimbra": True})]
    with pytest.raises(ErrorDeElementoParametrico, match="un solo concepto por contexto"):
        validar_alta(existentes, _c("EJ-411", {"concreto": True}))
    # En otro contexto no choca.
    validar_alta([_c("EST-02010", {"concreto": True}, nmin=1, nmax=2)], _c("EST-02011", {"concreto": True}, nmin=3))
    # Con contexto que se traslapa (uno sin límite), sí.
    with pytest.raises(ErrorDeElementoParametrico):
        validar_alta([_c("EST-02010", {"concreto": True})], _c("EST-02011", {"concreto": True}, nmin=3))


def test_los_escalones_conviven_pero_no_con_el_mismo_alto_ni_con_un_concepto_fijo() -> None:
    cs = _escalera_k1()
    acero = {"acero": True}
    validar_alta(cs, _c("EJ-410", acero, hasta="8.00", unidad="pza"))  # un escalón nuevo más alto
    with pytest.raises(ErrorDeElementoParametrico, match="escalón hasta"):
        validar_alta(cs, _c("EJ-410", acero, hasta="4.00", unidad="pza"))
    with pytest.raises(ErrorDeElementoParametrico, match="misma unidad"):
        validar_alta(cs, _c("EJ-410", acero, hasta="8.00", unidad="ml"))
    with pytest.raises(ErrorDeElementoParametrico, match="un solo concepto por contexto"):
        validar_alta(cs, _c("EJ-410", acero))  # sin escalón junto a una escalera
    with pytest.raises(ErrorDeElementoParametrico):
        validar_alta([_c("EJ-410", acero)], _c("EJ-411", acero, hasta="2.00"))


def test_el_mismo_concepto_no_se_repite_en_el_mismo_contexto_y_escalon() -> None:
    with pytest.raises(ErrorDeElementoParametrico, match="ya está"):
        validar_alta([_c("EST-10010", {"acero": True}, hasta="4.00")], _c("EST-10010", {"cimbra": True}, hasta="4.00"))


def test_el_contexto_se_valida_y_se_describe() -> None:
    assert validar_contexto(None, None, None) == Contexto()
    for malo in ((0, None, None), (3, 2, None), (None, None, "azotea")):
        with pytest.raises(ErrorDeElementoParametrico):
            validar_contexto(*malo)
    assert describir_contexto(Contexto()) == "Todo contexto"
    assert describir_contexto(Contexto(1, 2)) == "niveles 1 a 2"
    assert describir_contexto(Contexto(3, None)) == "nivel 3 en adelante"
    assert describir_contexto(Contexto(None, 2, "barda")) == "hasta el nivel 2, barda"
    assert describir_contexto(Contexto(2, 2)) == "nivel 2"


def test_la_clave_de_un_concepto_nuevo() -> None:
    assert normalizar_clave_propuesta(" ej-410 ") == "EJ-410"
    for mala in ("a", "EJ 410", "-EJ", ""):
        with pytest.raises(ErrorDeElementoParametrico):
            normalizar_clave_propuesta(mala)
