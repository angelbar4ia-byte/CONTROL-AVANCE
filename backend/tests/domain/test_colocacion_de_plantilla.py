"""Colocar en el plano lo que trae la plantilla de un muro (Ola 4C): castillos ubicados y estimados, cadenas, altura y posiciones."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from obractrl.domain.cuantificacion.colocacion_de_plantilla import (
    ErrorDeColocacion,
    alto_de_castillo,
    colocar_plantilla,
    conceptos_de_instancia,
    piezas_de_castillo,
    posiciones_de_castillos,
    sembrados_por_tipo,
)
from obractrl.domain.cuantificacion.conceptos_de_elemento import (
    ConceptoDeElemento,
    Contexto,
)
from obractrl.domain.cuantificacion.enlaces_de_ranura import Capa, EnlaceDeRanura, Partida

D = Decimal


@pytest.mark.parametrize(
    ("largo", "sep", "esperadas"),
    [
        ("4", None, 2),  # distribución «extremos»
        ("4", "2", 3),  # ⌈4 ÷ 2⌉ + 1
        ("4.1", "2", 4),  # ⌈2.05⌉ + 1
        ("10", "3", 5),  # ⌈3.33⌉ + 1
        ("0.5", "3", 2),  # nunca menos de dos con separación
    ],
)
def test_las_piezas_de_castillo(largo: str, sep: str | None, esperadas: int) -> None:
    assert piezas_de_castillo(D(largo), D(sep) if sep else None) == esperadas


def test_los_datos_que_no_valen_se_rechazan() -> None:
    with pytest.raises(ErrorDeColocacion):
        piezas_de_castillo(D(0), None)
    with pytest.raises(ErrorDeColocacion):
        piezas_de_castillo(D(4), D(0))
    with pytest.raises(ErrorDeColocacion):
        alto_de_castillo(D("0.5"), D("0.45"))


def test_el_alto_sube_lo_alto_del_muro_menos_el_arranque() -> None:
    assert alto_de_castillo(D("3.00")) == D("3.00")
    assert alto_de_castillo(D("3.00"), D("0.30")) == D("2.70")


def test_las_posiciones_van_del_inicio_al_final_y_parejas() -> None:
    assert posiciones_de_castillos(D(4), 2, D("0.15")) == [D("0.075"), D("3.925")]
    assert posiciones_de_castillos(D(4), 3, D("0.20")) == [D("0.100"), D("2.000"), D("3.900")]
    assert posiciones_de_castillos(D(4), 1, D("0.15")) == [D("2.000")]


def test_no_caben_mas_castillos_que_largo() -> None:
    with pytest.raises(ErrorDeColocacion):
        posiciones_de_castillos(D("0.2"), 3, D("0.15"))


PLANTILLA = [
    {"uid": "K-1", "ref": "K-1", "clase": "castillo", "modo": "ubicado", "sep_m": "2", "z_m": "0"},
    {"uid": "CD-1", "ref": "CD-1", "clase": "cadena", "posicion": "cerramiento", "z_m": "2.6"},
    {"uid": "EST-02010", "ref": "EST-02010", "clase": "muro"},
]


def test_una_plantilla_con_castillos_ubicados_los_coloca_y_resta_su_area() -> None:
    c = colocar_plantilla(PLANTILLA, largo_m=D(4), altura_m=D("3.00"), anchos_m={"K-1": D("0.15")})
    k, cadena = c.instancias
    assert (k.piezas, k.alto_m, k.se_coloca) == (3, D("3.00"), True)
    assert k.posiciones_m == (D("0.075"), D("2.000"), D("3.925"))
    assert k.metros == D("9.00")
    assert k.descuento_m2_por_cara == D("0.15") * D("3.00") * 3  # ancho × alto × piezas (por cara)
    assert (cadena.clase, cadena.metros, cadena.se_coloca) == ("cadena", D(4), False)
    assert c.avisos == []  # el muro de tabique no se coloca aquí


def test_un_castillo_estimado_se_cuenta_pero_no_se_coloca_ni_resta() -> None:
    estimado = [{"uid": "K-1", "ref": "K-1", "clase": "castillo", "modo": "estimado", "sep_m": "2.5"}]
    c = colocar_plantilla(estimado, largo_m=D(5), altura_m=D("2.6"), anchos_m={"K-1": D("0.15")})
    (k,) = c.instancias
    assert (k.piezas, k.se_coloca, k.posiciones_m, k.descuento_m2_por_cara) == (3, False, (), D(0))
    assert k.metros == D("2.6") * 3
    assert "estimados" in c.avisos[0]


def test_un_castillo_con_arranque_sube_menos() -> None:
    con_z = [{"uid": "K-1", "ref": "K-1", "clase": "castillo", "modo": "ubicado", "z_m": "0.3"}]
    c = colocar_plantilla(con_z, largo_m=D(4), altura_m=D("3"), anchos_m={"K-1": D("0.15")})
    assert c.instancias[0].alto_m == D("2.7")


def test_sin_ancho_conocido_no_se_coloca() -> None:
    with pytest.raises(ErrorDeColocacion):
        colocar_plantilla(PLANTILLA, largo_m=D(4), altura_m=D(3), anchos_m={})


# --- A qué conceptos alimenta lo colocado -----------------------------------------------------------------------------------



N1, N3, ETAPA = uuid4(), uuid4(), uuid4()
C_ACERO_A, C_ACERO_B, C_COLADO, C_COLADO_N3 = (uuid4() for _ in range(4))


def _c(clave: str, concepto: object, toma: dict[str, bool], *, unidad: str = "pza", hasta: str | None = None, nivel_min: int | None = None, nivel_max: int | None = None, estado: str = "autorizado") -> ConceptoDeElemento:
    return ConceptoDeElemento(
        id=uuid4(), clave=clave, descripcion=clave, unidad=unidad, toma=toma, contexto=Contexto(nivel_min, nivel_max, None),
        alto_hasta_m=D(hasta) if hasta else None, estado=estado, concepto_id=concepto,
    )


CONCEPTOS = [
    _c("EST-11010", C_ACERO_A, {"acero": True, "estribos": True, "alambre": True}, hasta="2.5"),  # escalón: hasta 2.5 m
    _c("EST-11011", C_ACERO_B, {"acero": True, "estribos": True, "alambre": True}, hasta="6"),  # escalón: hasta 6 m
    _c("EST-12010", C_COLADO, {"concreto": True, "cimbra": True}, unidad="ml", nivel_max=2),
    _c("EST-12011", C_COLADO_N3, {"concreto": True, "cimbra": True}, unidad="ml", nivel_min=3),
]


def _partidas(*, falta: tuple[object, ...] = ()) -> list[Partida]:
    todas = [(C_ACERO_A, N1), (C_ACERO_B, N1), (C_COLADO, N1), (C_COLADO_N3, N3)]
    return [Partida(id=uuid4(), concepto_id=c, nivel_id=n, etapa_id=ETAPA, nombre=str(c)) for c, n in todas if c not in falta]  # type: ignore[arg-type]


def _resolver(nivel: int, alto: str, *, partidas: list[Partida], enlaces: list[EnlaceDeRanura] | None = None, nivel_id: object = N1):
    return conceptos_de_instancia(
        CONCEPTOS, ref="K-1", nivel=nivel, ubicacion=None, alto_m=D(alto), piezas=3, enlaces=enlaces or [], partidas=partidas,
        nivel_id=nivel_id, etapa_id=ETAPA, unidades={},  # type: ignore[arg-type]
    )


def test_el_nivel_y_el_alto_eligen_los_conceptos_y_su_cantidad() -> None:
    cs, avisos = _resolver(1, "3.00", partidas=_partidas())
    por = {c.ranura: c for c in cs}
    assert por["acero"].clave == "EST-11011" and por["acero"].cantidad == D(3) and por["acero"].cuenta  # 3 m cae en el escalón de 6 m
    assert por["colado"].clave == "EST-12010" and por["colado"].unidad == "ml" and por["colado"].cantidad == D("9.00")
    assert avisos == []
    cs2, _ = _resolver(1, "2.40", partidas=_partidas())
    assert {c.ranura: c.clave for c in cs2}["acero"] == "EST-11010"  # 2.4 m cabe en el primer escalón


def test_en_el_tercer_nivel_el_colado_es_otro_concepto() -> None:
    cs, _ = _resolver(3, "3.00", partidas=_partidas(), nivel_id=N3)
    assert {c.ranura: c.clave for c in cs}["colado"] == "EST-12011"


def test_si_falta_la_partida_en_el_arbol_avisa_y_no_cuenta() -> None:
    cs, avisos = _resolver(1, "3.00", partidas=_partidas(falta=(C_COLADO,)))
    colado = next(c for c in cs if c.ranura == "colado")
    assert (colado.cuenta, colado.estado) == (False, "falta_partida")
    assert any("EST-12010" in a and "no cuenta" in a for a in avisos)
    assert next(c for c in cs if c.ranura == "acero").cuenta  # lo demás sigue contando


def test_un_concepto_propuesto_no_cuenta() -> None:
    nuevo = _c("EST-NUEVO", None, {"concreto": True, "cimbra": True}, unidad="ml")
    cs, _ = conceptos_de_instancia(
        [nuevo], ref="K-1", nivel=1, ubicacion=None, alto_m=D(3), piezas=2, enlaces=[], partidas=_partidas(),
        nivel_id=N1, etapa_id=ETAPA, unidades={},
    )
    assert [(c.estado, c.cuenta) for c in cs] == [("propuesto", False)]


def test_un_enlace_de_ranura_manda_sobre_el_concepto_del_contexto() -> None:
    otro = uuid4()
    enlace = EnlaceDeRanura(id=uuid4(), ranura="elemento:K-1:colado", capa=Capa(nivel_id=N1), concepto_id=otro, concepto_clave="OTRO-1")
    partidas = [*_partidas(), Partida(id=uuid4(), concepto_id=otro, nivel_id=N1, etapa_id=ETAPA, nombre="otro")]
    cs, _ = conceptos_de_instancia(
        CONCEPTOS, ref="K-1", nivel=1, ubicacion=None, alto_m=D(3), piezas=3, enlaces=[enlace], partidas=partidas,
        nivel_id=N1, etapa_id=ETAPA, unidades={otro: "pza"},
    )
    colado = next(c for c in cs if c.ranura == "colado")
    assert (colado.clave, colado.origen, colado.unidad, colado.cantidad, colado.cuenta) == ("OTRO-1", "ranura", "pza", D(3), True)
    # Si el concepto del enlace no está en el árbol: avisa y no cuenta (4B).
    cs2, avisos = conceptos_de_instancia(
        CONCEPTOS, ref="K-1", nivel=1, ubicacion=None, alto_m=D(3), piezas=3, enlaces=[enlace], partidas=_partidas(),
        nivel_id=N1, etapa_id=ETAPA, unidades={otro: "pza"},
    )
    assert next(c for c in cs2 if c.ranura == "colado").estado == "falta_partida"
    assert any("OTRO-1" in a for a in avisos)


def test_la_separacion_propia_manda_sobre_el_driver_y_sin_ella_el_castillo_estimado_usa_el_driver() -> None:
    anchos = {"K-1": D("0.15")}
    propia = [{"uid": "K-1", "ref": "K-1", "clase": "castillo", "modo": "estimado", "sep_m": "2", "z_m": "0"}]
    sin = [{"uid": "K-1", "ref": "K-1", "clase": "castillo", "modo": "estimado", "z_m": "0"}]

    def piezas(el: list[dict[str, str]], sep: str | None) -> int:
        d = D(sep) if sep else None
        return colocar_plantilla(el, largo_m=D(10), altura_m=D(3), anchos_m=anchos, separacion_m=d).instancias[0].piezas

    assert piezas(propia, "3") == 6  # propia 2 m: ⌈10 ÷ 2⌉ + 1, aunque el driver diga 3 m
    assert piezas(sin, "3") == 5  # la del driver: ⌈10 ÷ 3⌉ + 1
    assert piezas(sin, "2.5") == 5
    assert piezas(sin, "2") == 6
    assert piezas(sin, None) == 2  # sin driver, «extremos» como antes


def test_un_castillo_ubicado_sin_separacion_sigue_en_los_extremos_aunque_haya_driver() -> None:
    sin = [{"uid": "K-1", "ref": "K-1", "clase": "castillo", "modo": "ubicado", "z_m": "0"}]
    c = colocar_plantilla(sin, largo_m=D(10), altura_m=D(3), anchos_m={"K-1": D("0.15")}, separacion_m=D(3))
    assert c.instancias[0].piezas == 2


# --- Varios castillos por plantilla, cada uno con su regla (muro confinado por prototipo) --------------------------------------


def _estimado(uid: str, **regla: str) -> dict[str, object]:
    return {"uid": uid, "ref": uid, "clase": "castillo", "modo": "estimado", **regla}


def test_una_plantilla_confinada_lleva_varios_castillos_cada_uno_con_su_regla() -> None:
    elementos = [
        _estimado("K-1", regla="separacion", sep_m="2.5"),
        _estimado("K-2", regla="extremos"),
        _estimado("K-3", regla="por_ml", piezas_por_ml="0.5"),
        _estimado("K-7", regla="total", total_m="24", base_m2="286"),
        {"uid": "CE-1", "ref": "CE-1", "clase": "cadena", "posicion": "cerramiento"},
    ]
    c = colocar_plantilla(elementos, largo_m=D(10), altura_m=D("3.00"), anchos_m={})
    por_uid = {i.uid: i for i in c.instancias}
    assert (por_uid["K-1"].regla, por_uid["K-1"].piezas_exactas, por_uid["K-1"].piezas) == ("separacion", D(5), 5)  # ⌈10 ÷ 2.5⌉ + 1
    assert (por_uid["K-2"].regla, por_uid["K-2"].piezas_exactas) == ("extremos", D(2))
    assert (por_uid["K-3"].regla, por_uid["K-3"].piezas_exactas, por_uid["K-3"].metros) == ("por_ml", D(5), D(15))  # 10 ml × 0.5 pza/ml
    k7 = por_uid["K-7"]
    # 24 m de castillo sobre 286 m² de muro; este muro mide 10 × 3.00 = 30 m²: 24 × 30 ÷ 286 = 2.517 m = 0.839 piezas de 3.00 m.
    assert (k7.regla, k7.piezas_exactas, k7.piezas) == ("total", D("0.839"), 1)
    assert k7.metros == D("0.839") * D(3)
    assert all(not i.se_coloca and i.posiciones_m == () and i.descuento_m2_por_cara == 0 for i in c.instancias if i.clase == "castillo")
    assert por_uid["CE-1"].metros == D(10)


def test_la_regla_total_usa_el_area_que_se_le_da_y_si_no_el_muro_bruto() -> None:
    k = [_estimado("K-1", regla="total", total_m="126", base_m2="286")]
    bruto = colocar_plantilla(k, largo_m=D(10), altura_m=D(3), anchos_m={}).instancias[0]
    neto = colocar_plantilla(k, largo_m=D(10), altura_m=D(3), anchos_m={}, area_m2=D(26)).instancias[0]
    assert bruto.metros == pytest.approx(D("13.2168"), abs=D("0.01"))
    assert neto.metros == pytest.approx(D("11.4545"), abs=D("0.01"))


def test_los_castillos_sembrados_se_descuentan_de_los_estimados_por_tipo_sin_bajar_de_cero() -> None:
    k = [_estimado("K-1", regla="por_ml", piezas_por_ml="0.4"), _estimado("K-2", regla="por_ml", piezas_por_ml="0.2")]
    c = colocar_plantilla(k, largo_m=D(10), altura_m=D(3), anchos_m={}, sembrados={"K-1": D(3), "K-2": D(5)})
    k1, k2 = c.instancias
    assert (k1.piezas_estimadas, k1.piezas_sembradas, k1.piezas_exactas) == (D(4), D(3), D(1))
    assert (k2.piezas_estimadas, k2.piezas_sembradas, k2.piezas_exactas, k2.piezas) == (D(2), D(2), D(0), 0)  # mínimo 0
    assert k1.metros == D(3) and k2.metros == D(0)
    assert any("estimados 4, sembrados 3, contados 1" in a for a in c.avisos)
    sin = colocar_plantilla(k, largo_m=D(10), altura_m=D(3), anchos_m={}).instancias[0]
    assert (sin.piezas_estimadas, sin.piezas_sembradas, sin.piezas_exactas) == (D(4), D(0), D(4))


def test_sembrados_por_tipo_toma_el_k_de_la_plantilla_o_el_elegido_a_mano() -> None:
    vanos = [
        {"tipo": "castillo", "elemento_uid": "uso-1", "piezas": 2},
        {"tipo": "castillo", "elemento_uid": "k-1", "piezas": 1},
        {"tipo": "puerta", "elemento_uid": None, "piezas": 1},
        {"tipo": "castillo", "elemento_uid": None, "piezas": 1},
    ]
    assert sembrados_por_tipo(vanos, [{"uid": "uso-1", "ref": "K-1"}]) == {"K-1": D(3)}


def test_una_plantilla_anterior_sin_regla_cuenta_como_antes() -> None:
    antes = [
        {"uid": "K-1", "ref": "K-1", "clase": "castillo", "modo": "estimado", "sep_m": "2"},
        {"uid": "K-2", "ref": "K-2", "clase": "castillo", "modo": "estimado"},
        {"uid": "K-3", "ref": "K-3", "clase": "castillo", "modo": "ubicado"},
    ]
    c = colocar_plantilla(antes, largo_m=D(10), altura_m=D(3), anchos_m={"K-3": D("0.15")}, separacion_m=D(5))
    assert [(i.regla, i.piezas) for i in c.instancias] == [("separacion", 6), ("separacion", 3), ("extremos", 2)]


def test_un_castillo_estimado_no_necesita_ancho_y_los_que_no_valen_se_rechazan() -> None:
    colocar_plantilla([_estimado("K-1", regla="extremos")], largo_m=D(4), altura_m=D(3), anchos_m={})
    for malo in (
        {"regla": "por_ml"},
        {"regla": "total", "total_m": "5"},
        {"regla": "al_tanteo"},
    ):
        with pytest.raises(ErrorDeColocacion):
            colocar_plantilla([_estimado("K-1", **malo)], largo_m=D(4), altura_m=D(3), anchos_m={})
    ubicado = {"uid": "K-1", "ref": "K-1", "clase": "castillo", "modo": "ubicado", "regla": "total", "total_m": "5", "base_m2": "10"}
    with pytest.raises(ErrorDeColocacion):
        colocar_plantilla([ubicado], largo_m=D(4), altura_m=D(3), anchos_m={"K-1": D("0.15")})


def test_una_cadena_alimenta_conceptos_en_ml_con_los_metros_del_muro_y_no_en_pza() -> None:
    nivel, etapa, cadena_c, pieza_c = uuid4(), uuid4(), uuid4(), uuid4()
    conceptos = [
        ConceptoDeElemento(
            id=uuid4(), clave="CAD-1", descripcion="", unidad="ml", toma={"concreto": True, "acero": True, "cimbra": True},
            contexto=Contexto(), alto_hasta_m=None, estado="autorizado", concepto_id=cadena_c,
        ),
    ]
    partidas = [Partida(id=uuid4(), concepto_id=cadena_c, nivel_id=nivel, etapa_id=etapa, nombre="CAD-1")]
    ok, _ = conceptos_de_instancia(
        conceptos, ref="CE-1", nivel=1, ubicacion=None, alto_m=None, piezas=1, metros=D("10"), enlaces=[], partidas=partidas,
        nivel_id=nivel, etapa_id=etapa, unidades={},
    )
    (c,) = ok
    assert (c.clave, c.unidad, c.cantidad, c.cuenta, c.estado) == ("CAD-1", "ml", D(10), True, "cuenta")
    en_pza = [ConceptoDeElemento(id=uuid4(), clave="CAD-P", descripcion="", unidad="pza", toma={"concreto": True}, contexto=Contexto(), alto_hasta_m=None, estado="autorizado", concepto_id=pieza_c)]
    malo, _ = conceptos_de_instancia(
        en_pza, ref="CE-1", nivel=1, ubicacion=None, alto_m=None, piezas=1, metros=D("10"), enlaces=[], partidas=[], nivel_id=nivel, etapa_id=etapa, unidades={},
    )
    assert (malo[0].cuenta, malo[0].estado) == (False, "unidad_no_admitida") and "cadena" in (malo[0].aviso or "")
