"""Colocar en el plano lo que trae la plantilla de un muro (Ola 4C): castillos ubicados y estimados, cadenas, altura y posiciones."""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.cuantificacion.colocacion_de_plantilla import (
    ErrorDeColocacion,
    alto_de_castillo,
    colocar_plantilla,
    piezas_de_castillo,
    posiciones_de_castillos,
)

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

from uuid import uuid4  # noqa: E402

from obractrl.domain.cuantificacion.colocacion_de_plantilla import (
    conceptos_de_instancia,  # noqa: E402
)
from obractrl.domain.cuantificacion.conceptos_de_elemento import (  # noqa: E402
    ConceptoDeElemento,
    Contexto,
)
from obractrl.domain.cuantificacion.enlaces_de_ranura import (  # noqa: E402
    Capa,
    EnlaceDeRanura,
    Partida,
)

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
