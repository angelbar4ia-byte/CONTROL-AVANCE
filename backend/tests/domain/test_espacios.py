"""La capa «espacio» (0143, D-565/D-566): reparto de un muro compartido sin doble conteo, la capa en el enlace de ranuras, la matriz de la losa por
espacio y en qué partida se mide cada concepto (dominio puro)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from obractrl.domain.cuantificacion.enlaces_de_ranura import (
    Capa,
    Contexto,
    EnlaceDeRanura,
    Partida,
    elegir_enlace,
    partida_en_capa,
    puntaje_de_la_capa,
    resolver_ranura,
)
from obractrl.domain.cuantificacion.espacios import (
    TIPOS_DE_ESPACIO,
    ErrorDeEspacio,
    repartir,
    reparto_de_muro,
    resolver_matriz_por_espacio,
    validar_asignacion_de_muro,
    validar_espacio,
    validar_que_edita,
)
from obractrl.domain.cuantificacion.matriz_de_losa import (
    ElementoDeLosa,
    EntradaMatrizDeLosa,
    LosaDeEntrada,
    calcular_matriz_de_losa,
)

D = Decimal
RECAMARA, BANO, COCHERA = uuid4(), uuid4(), uuid4()
C_LOSA, C_ACERO, C_TABIQUE = uuid4(), uuid4(), uuid4()
NIVEL = uuid4()


def _partida(concepto: UUID, espacio: UUID | None, nombre: str = "p", orden: int = 0) -> Partida:
    return Partida(uuid4(), concepto, NIVEL, None, nombre, orden, espacio)


# ── Quién edita y qué es un espacio ─────────────────────────────────────────────────────────────────────


def test_solo_control_de_obra_edita_los_espacios() -> None:
    validar_que_edita("control_obra")
    for rol in ("costos", "residente", "supervisor", "super_intendente"):
        with pytest.raises(ErrorDeEspacio, match="Solo Control de obra"):
            validar_que_edita(rol)


def test_el_espacio_se_normaliza_y_se_valida() -> None:
    e = validar_espacio(nombre="  Recámara   1 ", tipo="recamara", area_m2="12.345")
    assert e == {"nombre": "Recámara 1", "tipo": "recamara", "area_m2": D("12.35")}
    assert validar_espacio(nombre="Patio", tipo=None, area_m2=None) == {"nombre": "Patio", "tipo": "otro", "area_m2": None}
    for mal in ({"nombre": "  "}, {"nombre": "x" * 61}, {"tipo": "sotano"}, {"area_m2": 0}, {"area_m2": -3}, {"area_m2": 100001}):
        with pytest.raises(ErrorDeEspacio):
            validar_espacio(**{"nombre": "Cocina", "tipo": "cocina", "area_m2": 8, **mal})
    assert "cochera" in TIPOS_DE_ESPACIO and "otro" in TIPOS_DE_ESPACIO


# ── Muro compartido: se traza una vez y se reparte sin contarse dos veces ───────────────────────────────


def test_un_muro_sin_espacio_no_se_reparte() -> None:
    assert reparto_de_muro(None, None, None) == []


def test_un_muro_de_un_solo_espacio_se_lo_lleva_todo() -> None:
    assert reparto_de_muro(RECAMARA, None, None) == [(RECAMARA, D(1))]
    # Si el principal se borró, el otro recibe todo: la cantidad no se pierde.
    assert reparto_de_muro(None, BANO, D("30")) == [(BANO, D(1))]


def test_un_muro_compartido_va_mitad_y_mitad_por_omision() -> None:
    assert reparto_de_muro(RECAMARA, BANO, None) == [(RECAMARA, D("0.5")), (BANO, D("0.5"))]


@pytest.mark.parametrize("pct", ["1", "33.33", "50", "66.67", "99", 12.5])
def test_el_reparto_siempre_suma_exactamente_uno(pct: object) -> None:
    partes = reparto_de_muro(RECAMARA, BANO, pct)  # type: ignore[arg-type]
    assert sum(f for _, f in partes) == D(1)
    assert partes[0][1] == (D(str(pct)) / 100).quantize(D("0.000001"))


@pytest.mark.parametrize("cantidad", ["12.345", "0.001", "100", "7", "1234.567891"])
@pytest.mark.parametrize("pct", ["50", "33.33", "1", "99"])
def test_repartir_una_cantidad_no_pierde_ni_agrega_un_decimal(cantidad: str, pct: str) -> None:
    partes = reparto_de_muro(RECAMARA, BANO, pct)
    repartido = repartir(cantidad, partes)
    assert sum(c for _, c in repartido) == D(cantidad).quantize(D("0.000001"))
    assert [e for e, _ in repartido] == [RECAMARA, BANO]


def test_repartir_pide_fracciones_que_sumen_uno() -> None:
    with pytest.raises(ErrorDeEspacio, match="sumar 1"):
        repartir(10, [(RECAMARA, D("0.4")), (BANO, D("0.4"))])
    assert repartir(10, []) == []


def test_la_asignacion_de_un_muro_se_valida() -> None:
    assert validar_asignacion_de_muro(espacio_id=None, comparte_id=None, reparto_pct=None) == (None, None, None)
    assert validar_asignacion_de_muro(espacio_id=RECAMARA, comparte_id=BANO, reparto_pct="40") == (RECAMARA, BANO, D("40.00"))
    with pytest.raises(ErrorDeEspacio, match="principal"):
        validar_asignacion_de_muro(espacio_id=None, comparte_id=BANO, reparto_pct=None)
    with pytest.raises(ErrorDeEspacio, match="mismo espacio"):
        validar_asignacion_de_muro(espacio_id=BANO, comparte_id=BANO, reparto_pct=None)
    with pytest.raises(ErrorDeEspacio, match="compartido"):
        validar_asignacion_de_muro(espacio_id=BANO, comparte_id=None, reparto_pct=50)
    for pct in (0, 100, -5, 150):
        with pytest.raises(ErrorDeEspacio, match="de más de 0 a menos de 100"):
            validar_asignacion_de_muro(espacio_id=RECAMARA, comparte_id=BANO, reparto_pct=pct)


# ── La capa «espacio» en el enlace de ranuras y en la partida ───────────────────────────────────────────


def test_la_capa_de_espacio_pesa_entre_la_ubicacion_y_la_etapa() -> None:
    ctx = Contexto(NIVEL, uuid4(), "interior", RECAMARA)
    assert puntaje_de_la_capa(Capa(espacio_id=RECAMARA), ctx) == 5
    assert puntaje_de_la_capa(Capa(espacio_id=BANO), ctx) is None
    assert puntaje_de_la_capa(Capa(espacio_id=RECAMARA), Contexto(NIVEL)) is None
    sumas = puntaje_de_la_capa(Capa(nivel_id=NIVEL, etapa_id=ctx.etapa_id), ctx)
    assert sumas == 3 < 5 < 10 == puntaje_de_la_capa(Capa(ubicacion="interior"), ctx)


def test_el_enlace_del_espacio_gana_al_general_y_el_de_otro_espacio_no_aplica() -> None:
    general = EnlaceDeRanura(uuid4(), "mamposteria:tabique_rojo", Capa(), C_TABIQUE, "EST-02010")
    de_recamara = EnlaceDeRanura(uuid4(), "mamposteria:tabique_rojo", Capa(espacio_id=RECAMARA), C_LOSA, "EST-XXXXX")
    assert elegir_enlace([general, de_recamara], "mamposteria:tabique_rojo", Contexto(espacio_id=RECAMARA)) is de_recamara
    assert elegir_enlace([general, de_recamara], "mamposteria:tabique_rojo", Contexto(espacio_id=BANO)) is general
    assert elegir_enlace([general, de_recamara], "mamposteria:tabique_rojo", Contexto()) is general


def test_la_partida_del_espacio_gana_a_la_general_y_la_de_otro_espacio_nunca_cuenta() -> None:
    general, de_recamara, de_bano = _partida(C_TABIQUE, None, "general"), _partida(C_TABIQUE, RECAMARA, "recámara"), _partida(C_TABIQUE, BANO, "baño")
    todas = [general, de_bano, de_recamara]
    assert partida_en_capa(todas, C_TABIQUE, Contexto(espacio_id=RECAMARA)) is de_recamara
    assert partida_en_capa(todas, C_TABIQUE, Contexto(espacio_id=BANO)) is de_bano
    # Un espacio sin partida propia cae en la general; sin espacio, solo la general.
    assert partida_en_capa(todas, C_TABIQUE, Contexto(espacio_id=COCHERA)) is general
    assert partida_en_capa(todas, C_TABIQUE, Contexto()) is general


def test_sin_partida_general_lo_que_no_tiene_espacio_no_cuenta_y_el_aviso_lo_dice() -> None:
    solo_en_recamara = [_partida(C_TABIQUE, RECAMARA)]
    assert partida_en_capa(solo_en_recamara, C_TABIQUE, Contexto()) is None
    assert partida_en_capa(solo_en_recamara, C_TABIQUE, Contexto(espacio_id=BANO)) is None
    enlace = EnlaceDeRanura(uuid4(), "mamposteria:tabique_rojo", Capa(), C_TABIQUE, "EST-02010")
    r_sin = resolver_ranura([enlace], solo_en_recamara, "mamposteria:tabique_rojo", Contexto())
    assert (r_sin.estado, r_sin.cuenta) == ("falta_partida", False)
    assert r_sin.aviso is not None and "asigna lo que se mide a uno de ellos" in r_sin.aviso
    r_otro = resolver_ranura([enlace], solo_en_recamara, "mamposteria:tabique_rojo", Contexto(espacio_id=BANO))
    assert r_otro.aviso is not None and "otros espacios" in r_otro.aviso
    r_ok = resolver_ranura([enlace], solo_en_recamara, "mamposteria:tabique_rojo", Contexto(espacio_id=RECAMARA))
    assert (r_ok.estado, r_ok.cuenta, r_ok.partida) == ("enlazado", True, solo_en_recamara[0])


def test_sin_espacios_en_el_arbol_todo_se_comporta_como_siempre() -> None:
    p = _partida(C_TABIQUE, None)
    assert partida_en_capa([p], C_TABIQUE, Contexto()) is p
    assert partida_en_capa([p], C_TABIQUE, Contexto(NIVEL)) is p
    assert partida_en_capa([p], C_TABIQUE, Contexto(uuid4())) is None


# ── La matriz de la losa por espacio ─────────────────────────────────────────────────────────────────────


def _entrada() -> EntradaMatrizDeLosa:
    return EntradaMatrizDeLosa(
        tipo="maciza", espesor_m=0.12,
        losas=[
            LosaDeEntrada(area_m2=12.0, id="a", espacio_id="recamara"),
            LosaDeEntrada(area_m2=4.5, id="b", espacio_id="bano"),
            LosaDeEntrada(area_m2=6.0, id="c", espacio_id="recamara", espesor_m=0.15),
            LosaDeEntrada(area_m2=3.0, id="d"),
        ],
        elementos=[
            ElementoDeLosa(clave="T-1-15x25", modo="ml", cantidad=5.0, id="t1", espacio_id="recamara"),
            ElementoDeLosa(clave="T-1-15x25", modo="ml", cantidad=2.5, id="t2", espacio_id="bano", pago="propio"),
            ElementoDeLosa(clave="CT1-15x25", modo="ml", cantidad=3.0, id="t3"),
        ],
    )


def test_la_matriz_por_espacio_suma_el_total_de_la_zona_sin_doble_conteo() -> None:
    r = calcular_matriz_de_losa(_entrada())
    grupos = {g["espacio_id"]: g for g in r["por_espacio"]}
    assert set(grupos) == {"recamara", "bano", None}
    assert [g["espacio_id"] for g in r["por_espacio"]] == ["recamara", "bano", None]
    assert grupos["recamara"]["area_m2"] == pytest.approx(18.0)
    assert grupos["bano"]["area_m2"] == pytest.approx(4.5)
    assert sum(g["area_m2"] for g in r["por_espacio"]) == pytest.approx(r["area_m2"])
    for campo in ("longitud_de_elementos_ml", "concreto_m3", "cimbra_m2", "acero_de_elementos_kg"):
        assert sum(g[campo] for g in r["por_espacio"]) == pytest.approx(r["totales"][campo]), campo
    # Cada concepto de la zona, sumado por espacio, es lo que la zona dice.
    por_concepto: dict[tuple[str, str], float] = {}
    for g in r["por_espacio"]:
        for c in g["conceptos"]:
            llave = (c["parte"], c["concepto"]["clave"])
            por_concepto[llave] = por_concepto.get(llave, 0.0) + c["cantidad"]
    total_de_la_zona: dict[tuple[str, str], float] = {}
    for c in r["conceptos"]:
        llave = (c["parte"], c["concepto"]["clave"])
        total_de_la_zona[llave] = total_de_la_zona.get(llave, 0.0) + c["cantidad"]
    assert por_concepto.keys() == total_de_la_zona.keys()
    for llave, cantidad in total_de_la_zona.items():
        assert por_concepto[llave] == pytest.approx(cantidad), llave


def test_cada_poligono_y_cada_elemento_dice_su_espacio() -> None:
    r = calcular_matriz_de_losa(_entrada())
    assert {x["id"]: x["espacio_id"] for x in r["losas"]} == {"a": "recamara", "b": "bano", "c": "recamara", "d": None}
    assert {x["id"]: x["espacio_id"] for x in r["elementos"]} == {"t1": "recamara", "t2": "bano", "t3": None}


def test_sin_espacios_la_matriz_es_un_solo_grupo_y_el_resto_no_cambia() -> None:
    sin = EntradaMatrizDeLosa(tipo="maciza", espesor_m=0.12, losas=[LosaDeEntrada(area_m2=10.0)])
    r = calcular_matriz_de_losa(sin)
    assert [g["espacio_id"] for g in r["por_espacio"]] == [None]
    assert r["por_espacio"][0]["conceptos"] == r["conceptos"]
    assert r["area_m2"] == 10.0
    vacia = calcular_matriz_de_losa(EntradaMatrizDeLosa(tipo="maciza", espesor_m=0.12))
    assert [g["espacio_id"] for g in vacia["por_espacio"]] == [None]


# ── En qué partida se mide cada concepto ─────────────────────────────────────────────────────────────────


def _grupos() -> list[dict[str, object]]:
    def fila(clave: str, cantidad: float, estado: str = "catalogo") -> dict[str, object]:
        return {"parte": "acero", "concepto": {"clave": clave, "estado": estado}, "cantidad": cantidad, "unidad": "ml"}

    return [
        {"espacio_id": str(RECAMARA), "conceptos": [fila("AUX-1", 5.0), fila("AUX-2", 2.0), fila("EJ-800", 18.0, "propuesto"), fila("AUX-3", 0.0), fila("XXX-9", 1.0)]},
        {"espacio_id": str(BANO), "conceptos": [fila("AUX-1", 2.5)]},
        {"espacio_id": None, "conceptos": [fila("AUX-1", 3.0)]},
    ]


def test_cada_concepto_dice_si_cuenta_y_donde() -> None:
    p_recamara, p_bano = _partida(C_ACERO, RECAMARA, "Acero recámara"), _partida(C_ACERO, BANO, "Acero baño")
    r = resolver_matriz_por_espacio(
        _grupos(), partidas=[p_bano, p_recamara], concepto_id_de={"AUX-1": C_ACERO, "AUX-2": uuid4(), "AUX-3": C_ACERO},
        nombres={RECAMARA: "Recámara 1", BANO: "Baño"},
    )
    por = {(g["espacio_id"], c["concepto"]["clave"]): c["resolucion"] for g in r for c in g["conceptos"]}
    assert por[(str(RECAMARA), "AUX-1")]["estado"] == "cuenta"
    assert por[(str(RECAMARA), "AUX-1")]["partida_id"] == p_recamara.id and por[(str(RECAMARA), "AUX-1")]["partida_nombre"] == "Acero recámara"
    assert por[(str(BANO), "AUX-1")]["partida_id"] == p_bano.id
    assert por[(str(RECAMARA), "AUX-2")]["estado"] == "falta_partida" and "no está en el árbol" in por[(str(RECAMARA), "AUX-2")]["aviso"]
    assert por[(str(RECAMARA), "EJ-800")]["estado"] == "propuesto" and not por[(str(RECAMARA), "EJ-800")]["cuenta"]
    assert por[(str(RECAMARA), "AUX-3")]["estado"] == "sin_cantidad"
    assert por[(str(RECAMARA), "XXX-9")]["estado"] == "sin_concepto"
    assert por[(None, "AUX-1")]["estado"] == "sin_espacio" and not por[(None, "AUX-1")]["cuenta"]
    assert [g["espacio_nombre"] for g in r] == ["Recámara 1", "Baño", None]


def test_lo_que_se_escribe_en_las_partidas_suma_lo_de_la_matriz_asignada() -> None:
    p_recamara, p_bano = _partida(C_ACERO, RECAMARA), _partida(C_ACERO, BANO)
    r = resolver_matriz_por_espacio(_grupos(), partidas=[p_recamara, p_bano], concepto_id_de={"AUX-1": C_ACERO})
    escrito = sum(c["cantidad"] for g in r for c in g["conceptos"] if c["resolucion"]["cuenta"])
    asignado_a_un_espacio = 5.0 + 2.5  # lo de «sin espacio» (3.0) no se escribe: no se cuenta en ninguna partida
    assert escrito == pytest.approx(asignado_a_un_espacio)


def test_un_concepto_sin_partida_en_su_espacio_cae_en_la_general() -> None:
    general = _partida(C_ACERO, None, "Acero general")
    r = resolver_matriz_por_espacio(_grupos()[:2], partidas=[general], concepto_id_de={"AUX-1": C_ACERO})
    assert [c["resolucion"]["partida_id"] for g in r for c in g["conceptos"] if c["concepto"]["clave"] == "AUX-1"] == [general.id, general.id]
