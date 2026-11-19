"""El enlace de ranuras con el árbol de la obra (Ola 4B): especificidad de la capa, partida del árbol y «sin partida no cuenta»."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from obractrl.domain.cuantificacion.enlaces_de_ranura import (
    Capa,
    Contexto,
    EnlaceDeRanura,
    ErrorDeEnlaceDeRanura,
    Partida,
    elegir_enlace,
    partida_en_capa,
    puntaje_de_la_capa,
    ranuras_de_plantilla,
    resolver_ranura,
    validar_que_enlaza,
    validar_ranura,
    validar_ubicacion,
)

PB, ENTREPISO, AZOTEA = uuid4(), uuid4(), uuid4()
ESTRUCTURA, ALBANILERIA = uuid4(), uuid4()
C_ACERO, C_COLADO, C_BARDA, C_TABIQUE = uuid4(), uuid4(), uuid4(), uuid4()


def _enlace(ranura: str, concepto: UUID, clave: str, **capa: object) -> EnlaceDeRanura:
    return EnlaceDeRanura(uuid4(), ranura, Capa(**capa), concepto, clave)  # type: ignore[arg-type]


def _partida(concepto: UUID, nivel: UUID | None, etapa: UUID | None, orden: int = 0) -> Partida:
    return Partida(uuid4(), concepto, nivel, etapa, "p", orden)


def test_una_capa_vacia_aplica_a_todo_con_cero_puntos() -> None:
    assert puntaje_de_la_capa(Capa(), Contexto(PB, ESTRUCTURA, "barda")) == 0


def test_la_ubicacion_pesa_mas_que_la_etapa_y_esta_mas_que_el_nivel() -> None:
    ctx = Contexto(PB, ESTRUCTURA, "barda")
    assert puntaje_de_la_capa(Capa(nivel_id=PB), ctx) == 1
    assert puntaje_de_la_capa(Capa(etapa_id=ESTRUCTURA), ctx) == 2
    assert puntaje_de_la_capa(Capa(ubicacion="barda"), ctx) == 10
    assert puntaje_de_la_capa(Capa(nivel_id=PB, etapa_id=ESTRUCTURA), ctx) == 3


def test_una_capa_que_fija_algo_distinto_o_que_el_contexto_no_trae_no_aplica() -> None:
    assert puntaje_de_la_capa(Capa(nivel_id=ENTREPISO), Contexto(PB, ESTRUCTURA, None)) is None
    assert puntaje_de_la_capa(Capa(ubicacion="pretil"), Contexto(PB, None, "barda")) is None
    assert puntaje_de_la_capa(Capa(etapa_id=ESTRUCTURA), Contexto(PB, None, None)) is None


def test_gana_el_enlace_mas_especifico_como_en_el_mockup() -> None:
    base = _enlace("elemento:K-1:acero", C_ACERO, "A")
    barda = _enlace("elemento:K-1:acero", C_BARDA, "B", ubicacion="barda")
    otra = _enlace("elemento:K-2:acero", C_COLADO, "C", ubicacion="barda")
    enlaces = [base, barda, otra]
    assert elegir_enlace(enlaces, "elemento:K-1:acero", Contexto(PB, ESTRUCTURA, "barda")) is barda
    assert elegir_enlace(enlaces, "elemento:K-1:acero", Contexto(PB, ESTRUCTURA, None)) is base
    assert elegir_enlace(enlaces, "elemento:K-3:acero", Contexto(PB, ESTRUCTURA, None)) is None


def test_la_partida_se_busca_en_el_nivel_y_la_etapa_donde_se_mide() -> None:
    en_pb = _partida(C_TABIQUE, PB, ALBANILERIA)
    en_azotea = _partida(C_TABIQUE, AZOTEA, ALBANILERIA)
    partidas = [en_azotea, en_pb]
    assert partida_en_capa(partidas, C_TABIQUE, Contexto(PB, ALBANILERIA, None)) is en_pb
    assert partida_en_capa(partidas, C_TABIQUE, Contexto(AZOTEA, None, None)) is en_azotea
    assert partida_en_capa(partidas, C_TABIQUE, Contexto(ENTREPISO, None, None)) is None
    assert partida_en_capa(partidas, C_TABIQUE, Contexto(PB, ESTRUCTURA, None)) is None
    assert partida_en_capa(partidas, C_ACERO, Contexto(PB, None, None)) is None


def test_sin_nivel_en_el_contexto_vale_cualquier_partida_la_de_menor_orden() -> None:
    a, b = _partida(C_TABIQUE, AZOTEA, None, orden=5), _partida(C_TABIQUE, PB, None, orden=1)
    assert partida_en_capa([a, b], C_TABIQUE, Contexto()) is b


def test_enlazada_con_su_partida_cuenta() -> None:
    e = _enlace("mamposteria:tabique_rojo", C_TABIQUE, "EST-02010")
    p = _partida(C_TABIQUE, PB, ALBANILERIA)
    r = resolver_ranura([e], [p], "mamposteria:tabique_rojo", Contexto(PB, ALBANILERIA, None))
    assert (r.estado, r.cuenta, r.enlace, r.partida, r.aviso) == ("enlazado", True, e, p, None)


def test_si_falta_la_partida_en_el_arbol_avisa_y_no_cuenta() -> None:
    e = _enlace("mamposteria:tabique_rojo", C_TABIQUE, "EST-02010")
    r = resolver_ranura([e], [_partida(C_TABIQUE, AZOTEA, ALBANILERIA)], "mamposteria:tabique_rojo", Contexto(PB, ALBANILERIA, None))
    assert (r.estado, r.cuenta, r.partida) == ("falta_partida", False, None)
    assert r.aviso is not None and "EST-02010" in r.aviso and "no cuenta" in r.aviso


def test_si_el_arbol_esta_vacio_tampoco_cuenta() -> None:
    e = _enlace("elemento:K-1:acero", C_ACERO, "EST-10010")
    r = resolver_ranura([e], [], "elemento:K-1:acero", Contexto(PB, ESTRUCTURA, None))
    assert r.estado == "falta_partida" and not r.cuenta and not r.por_defecto


def test_una_ranura_de_elemento_sin_enlace_conserva_sus_conceptos_por_defecto() -> None:
    r = resolver_ranura([], [], "elemento:K-1:acero", Contexto(PB, None, None))
    assert (r.estado, r.cuenta, r.por_defecto) == ("sin_enlace", False, True)
    assert r.aviso is not None and "por defecto" in r.aviso


def test_una_ranura_de_plantilla_sin_enlace_no_cuenta_y_no_tiene_por_defecto() -> None:
    r = resolver_ranura([], [], "acabado:gris:exterior", Contexto(PB, None, None))
    assert (r.estado, r.cuenta, r.por_defecto) == ("sin_enlace", False, False)


def test_un_enlace_de_otra_capa_no_rescata_a_la_ranura() -> None:
    e = _enlace("elemento:K-1:acero", C_BARDA, "B", ubicacion="barda")
    r = resolver_ranura([e], [_partida(C_BARDA, PB, None)], "elemento:K-1:acero", Contexto(PB, None, "pretil"))
    assert r.estado == "sin_enlace"


@pytest.mark.parametrize(
    "ranura",
    ["elemento:K-1:acero", "elemento:CE-1:colado", "elemento:EST-02010:completo", "mamposteria:sillar_amarillo", "acabado:gris:exterior"],
)
def test_las_ranuras_con_forma_valida_se_aceptan(ranura: str) -> None:
    assert validar_ranura(f" {ranura} ") == ranura


@pytest.mark.parametrize("ranura", ["", "K-1", "elemento:K-1", "elemento:K-1:todo", "mamposteria:", "acabado:gris", "Mamposteria:x"])
def test_las_ranuras_sin_forma_se_rechazan(ranura: str) -> None:
    with pytest.raises(ErrorDeEnlaceDeRanura):
        validar_ranura(ranura)


def test_la_ubicacion_es_una_de_las_conocidas() -> None:
    assert validar_ubicacion("barda") == "barda" and validar_ubicacion(None) is None and validar_ubicacion("") is None
    with pytest.raises(ErrorDeEnlaceDeRanura):
        validar_ubicacion("azotea")


def test_solo_costos_y_control_de_obra_enlazan() -> None:
    validar_que_enlaza("costos")
    validar_que_enlaza("control_obra")
    with pytest.raises(ErrorDeEnlaceDeRanura):
        validar_que_enlaza("residente")


def test_las_ranuras_de_plantilla_no_inventan_conceptos() -> None:
    ranuras = ranuras_de_plantilla()
    assert [r.ranura for r in ranuras][:4] == ["mamposteria:tabique_rojo", "mamposteria:block_hueco", "mamposteria:sillar_amarillo", "mamposteria:cantera_rosa"]
    assert len(ranuras) == 4 + 6
    # El tabique rojo (EST-02010) y el sillar amarillo de 19 cm (BAP-01010) traen concepto sugerido, verificado en el catálogo; block hueco
    # y cantera rosa no tienen concepto (por capturar, C2/F7); los EJ-* del mockup eran de ejemplo.
    assert {r.ranura: r.sugerido_clave for r in ranuras if r.sugerido_clave} == {
        "mamposteria:tabique_rojo": "EST-02010", "mamposteria:sillar_amarillo": "BAP-01010",
    }
    for r in ranuras:
        validar_ranura(r.ranura)
