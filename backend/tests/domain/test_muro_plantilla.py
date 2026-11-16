"""Tipo, ubicación y plantilla de muro (Ola 4A): reglas de ubicación por cara, plantilla normalizada, versiones (Q9) y validación
contra la matriz. Sin base de datos."""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.cuantificacion.muro_plantilla import (
    ConceptoDelElemento,
    ElementoParaValidar,
    ErrorDePlantillaDeMuro,
    InfoDeElemento,
    admite_castillos_ubicados,
    cambia_la_plantilla,
    clase_de_elemento,
    normalizar_plantilla,
    puede_validar,
    requiere_version_nueva,
    validar_contra_matriz,
    validar_que_edita,
    validar_que_valida,
)
from obractrl.domain.cuantificacion.muro_tipo import TIPOS_DE_MURO, tipo_valido
from obractrl.domain.cuantificacion.muro_ubicacion import (
    aplicar_ubicacion,
    caras_de_ubicacion,
    sugerencia_por_losa,
    ubicacion_resultante,
)
from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

K1 = InfoDeElemento("K-1", "Castillo K-1", "castillo", "castillos", "muro")
CE1 = InfoDeElemento("CE-1", "Cadena CE-1", "cadena", "cadenas", "cerramiento")
CD1 = InfoDeElemento("CD-1", "Cadena CD-1", "cadena", "cadenas", "desplante")
MURO = InfoDeElemento("EST-02010", "Muro de tabique de 14 cm", "muro")
INFO = {e.ref: e for e in (K1, CE1, CD1, MURO)}

PARTES = [
    {"nombre": "Media altura", "desde_m": "0", "hasta_m": "1.2", "rol": "cuerpo"},
    {"nombre": "Enrase", "desde_m": "1.2", "hasta_m": "2.6", "rol": "enrase"},
]


def _base(**cambios: object) -> dict:
    return {"nombre": "Fachada", "tipo": "con_cadena", "material": "tabique_rojo", "ubicacion": "fachada_a", "elementos": [{"ref": "K-1"}, {"ref": "CE-1"}], **cambios}


# --- Tipos de muro ------------------------------------------------------------------------------------------------------------


def test_los_tipos_de_muro_son_tres_y_los_viejos_se_explican() -> None:
    assert TIPOS_DE_MURO == ("confinado", "con_cadena", "tabique")
    for viejo in ("pretil", "barda", "sillar"):
        with pytest.raises(ErrorDeCuantificacion, match="ya no es un tipo de muro"):
            tipo_valido(viejo)
    with pytest.raises(ErrorDeCuantificacion):
        tipo_valido("adobe")
    assert tipo_valido(None) is None


# --- Ubicación por cara -------------------------------------------------------------------------------------------------------


def test_la_ubicacion_fija_las_caras_y_el_enrase_interior_sale_exterior() -> None:
    assert caras_de_ubicacion("fachada_a") == ("exterior", "interior")
    assert caras_de_ubicacion("fachada_b") == ("interior", "exterior")
    assert caras_de_ubicacion("pretil") == ("exterior", "exterior")
    assert caras_de_ubicacion("personalizada") is None
    partes = aplicar_ubicacion("interior", PARTES)
    assert [(p["cara_a"], p["cara_b"]) for p in partes] == [("interior", "interior"), ("exterior", "exterior")]


def test_cambiar_la_cara_de_una_parte_vuelve_personalizada_la_ubicacion() -> None:
    partes = aplicar_ubicacion("fachada_a", PARTES)
    assert ubicacion_resultante("fachada_a", partes) == "fachada_a"
    partes[1]["cara_b"] = "exterior"
    assert ubicacion_resultante("fachada_a", partes) == "personalizada"
    # Las partes sin caras (aún no ubicadas) no cuentan.
    assert ubicacion_resultante("fachada_a", PARTES) == "fachada_a"


def test_losa_mas_baja_que_el_muro_solo_sugiere() -> None:
    sugeridas = sugerencia_por_losa(aplicar_ubicacion("interior", PARTES), Decimal("1.2"))
    assert sugeridas == [{"indice": 1, "nombre": "Enrase", "cara_a": "exterior", "cara_b": "exterior"}]
    with pytest.raises(ErrorDeCuantificacion):
        sugerencia_por_losa(PARTES, Decimal(0))


def test_las_partes_y_las_caras_se_validan() -> None:
    with pytest.raises(ErrorDeCuantificacion, match="desde"):
        aplicar_ubicacion("interior", [{"nombre": "x", "desde_m": "2", "hasta_m": "1"}])
    with pytest.raises(ErrorDeCuantificacion, match="cara A"):
        aplicar_ubicacion("interior", [{"nombre": "x", "desde_m": "0", "hasta_m": "1", "cara_a": "afuera"}])
    with pytest.raises(ErrorDeCuantificacion, match="rol"):
        aplicar_ubicacion("interior", [{"nombre": "x", "desde_m": "0", "hasta_m": "1", "rol": "raro"}])


# --- Plantilla -------------------------------------------------------------------------------------------------------------------


def test_una_plantilla_con_cadena_coloca_los_castillos_y_la_confinada_los_estima() -> None:
    p = normalizar_plantilla(_base(partes=PARTES), INFO)
    assert p["ubicacion"] == "fachada_a"
    assert [(e["ref"], e["clase"], e["modo"], e["posicion"]) for e in p["elementos"]] == [
        ("K-1", "castillo", "ubicado", None), ("CE-1", "cadena", None, "cerramiento"),
    ]
    assert admite_castillos_ubicados(p["elementos"]) is True
    assert all(x["cara_a"] == "exterior" and x["cara_b"] == "interior" for x in p["partes"])
    c = normalizar_plantilla(_base(tipo="confinado"), INFO)
    assert c["elementos"][0]["modo"] == "estimado" and admite_castillos_ubicados(c["elementos"]) is False


def test_el_tabique_no_lleva_castillos_ni_cadenas_y_el_modo_sale_del_tipo() -> None:
    with pytest.raises(ErrorDePlantillaDeMuro, match="no lleva castillos ni cadenas"):
        normalizar_plantilla(_base(tipo="tabique"), INFO)
    ok = normalizar_plantilla(_base(tipo="tabique", elementos=[{"ref": "EST-02010"}]), INFO)
    assert ok["elementos"][0]["clase"] == "muro"
    with pytest.raises(ErrorDePlantillaDeMuro, match=r"estimados|ubicados"):
        normalizar_plantilla(_base(tipo="confinado", elementos=[{"ref": "K-1", "modo": "ubicado"}]), INFO)


def test_la_posicion_de_una_cadena_respeta_su_subcategoria() -> None:
    ok = normalizar_plantilla(_base(elementos=[{"ref": "CD-1"}]), INFO)
    assert ok["elementos"][0]["posicion"] == "desplante"
    with pytest.raises(ErrorDePlantillaDeMuro, match="desplante"):
        normalizar_plantilla(_base(elementos=[{"ref": "CD-1", "posicion": "remate"}]), INFO)


def test_la_misma_cadena_se_coloca_varias_veces_con_su_propio_uid() -> None:
    p = normalizar_plantilla(_base(elementos=[{"ref": "CE-1"}, {"ref": "CE-1", "posicion": "remate"}]), INFO)
    assert [e["uid"] for e in p["elementos"]] == ["CE-1", "CE-1#2"]
    with pytest.raises(ErrorDePlantillaDeMuro, match="se repite"):
        normalizar_plantilla(_base(elementos=[{"uid": "a", "ref": "K-1"}, {"uid": "a", "ref": "CE-1"}]), INFO)


def test_lo_que_no_vale_se_rechaza() -> None:
    with pytest.raises(ErrorDePlantillaDeMuro, match="no existe en el catálogo"):
        normalizar_plantilla(_base(elementos=[{"ref": "T-3"}]), INFO)
    with pytest.raises(ErrorDePlantillaDeMuro, match="un solo elemento de muro"):
        normalizar_plantilla(_base(tipo="tabique", elementos=[{"ref": "EST-02010"}, {"uid": "b", "ref": "EST-02010"}]), INFO)
    with pytest.raises(ErrorDePlantillaDeMuro, match="nombre"):
        normalizar_plantilla(_base(nombre="  "), INFO)
    with pytest.raises(ErrorDeCuantificacion, match="Material"):
        normalizar_plantilla(_base(material="adobe"), INFO)
    with pytest.raises(ErrorDeCuantificacion, match="Ubicación"):
        normalizar_plantilla(_base(ubicacion="azotea"), INFO)
    with pytest.raises(ErrorDePlantillaDeMuro, match="altura"):
        normalizar_plantilla(_base(altura_m="0"), INFO)


def test_una_cara_distinta_vuelve_personalizada_la_plantilla() -> None:
    partes = [{"nombre": "Cuerpo", "desde_m": "0", "hasta_m": "2.6", "cara_a": "interior", "cara_b": "interior"}]
    assert normalizar_plantilla(_base(partes=partes), INFO)["ubicacion"] == "personalizada"


def test_solo_castillos_y_cadenas_se_colocan_en_un_muro() -> None:
    assert clase_de_elemento("castillos", "muro") == "castillo"
    assert clase_de_elemento("cadenas", "desplante") == "cadena"
    assert clase_de_elemento("dalas", "repison") == "cadena"
    assert clase_de_elemento("trabes", "losa") is None
    assert clase_de_elemento("columnas", "forjada") is None


# --- Versiones y roles -----------------------------------------------------------------------------------------------------------


def test_cambiar_una_plantilla_validada_crea_version_y_la_por_validar_se_edita() -> None:
    assert requiere_version_nueva("validada") is True
    assert requiere_version_nueva("por_validar") is False
    antes = normalizar_plantilla(_base(), INFO)
    assert cambia_la_plantilla(antes, normalizar_plantilla(_base(), INFO)) is False
    assert cambia_la_plantilla(antes, normalizar_plantilla(_base(altura_m="3"), INFO)) is True
    assert cambia_la_plantilla(antes, normalizar_plantilla(_base(elementos=[{"ref": "K-1"}]), INFO)) is True
    # Lo guardado vuelve de la base con números en otra forma y no cuenta como cambio.
    guardado = {**antes, "altura_m": None}
    assert cambia_la_plantilla(guardado, normalizar_plantilla(_base(altura_m=None), INFO)) is False


def test_solo_control_de_obra_valida_y_costos_edita() -> None:
    validar_que_edita("costos")
    validar_que_edita("control_obra")
    validar_que_valida("control_obra")
    for rol in ("costos", "residente", "supervisor", "super_intendente"):
        with pytest.raises(ErrorDePlantillaDeMuro):
            validar_que_valida(rol)
    with pytest.raises(ErrorDePlantillaDeMuro):
        validar_que_edita("residente")


# --- Validación contra la matriz -------------------------------------------------------------------------------------------------


def _elemento(conceptos: list[ConceptoDelElemento], **kw: object) -> ElementoParaValidar:
    partes = {"concreto": frozenset({"MEZ-01020"}), "acero": frozenset({"ACE-00011"}), "cimbra": frozenset()}
    return ElementoParaValidar("K-1", "K-1", "Castillo K-1", "castillo", partes=partes, conceptos=conceptos, **kw)  # type: ignore[arg-type]


def _c(clave: str, toma: set[str], matriz: set[str] | None, **kw: object) -> ConceptoDelElemento:
    return ConceptoDelElemento(clave, frozenset(toma), matriz=frozenset(matriz) if matriz is not None else None, **kw)  # type: ignore[arg-type]


def test_una_plantilla_que_cuadra_no_tiene_alertas() -> None:
    e = _elemento([_c("EST-02110", {"concreto", "acero", "cimbra"}, {"MEZ-01020", "ACE-00011"})])
    assert validar_contra_matriz([e]) == []


def test_parte_sin_concepto_parte_doble_y_parte_fuera_de_la_matriz() -> None:
    sin = validar_contra_matriz([_elemento([_c("EST-02110", {"concreto"}, {"MEZ-01020"})])])
    assert {(a.codigo, a.parte) for a in sin} == {("sin_concepto", "acero"), ("sin_concepto", "cimbra")}
    doble = validar_contra_matriz(
        [_elemento([_c("A", {"concreto", "acero", "cimbra"}, {"MEZ-01020", "ACE-00011"}), _c("B", {"acero"}, {"ACE-00011"})])]
    )
    assert [(a.codigo, a.parte) for a in doble] == [("parte_doble", "acero")]
    fuera = validar_contra_matriz([_elemento([_c("A", {"concreto", "acero", "cimbra"}, {"MEZ-01020"})])])
    assert [(a.codigo, a.parte, a.concepto) for a in fuera] == [("parte_fuera_de_matriz", "acero", "A")]
    assert all(a.nivel == "alerta" for a in (*sin, *doble, *fuera)) and puede_validar([*sin, *doble, *fuera])


def test_escalones_de_altura_distinta_no_son_parte_doble() -> None:
    a = _c("EST-10013", {"acero"}, {"ACE-00011"}, contexto=(None, None, None, Decimal("1.0")))
    b = _c("EST-10012", {"acero"}, {"ACE-00011"}, contexto=(None, None, None, Decimal("1.5")))
    resto = _c("EST-02110", {"concreto", "cimbra"}, {"MEZ-01020"})
    assert validar_contra_matriz([_elemento([a, b, resto])]) == []


def test_concepto_propuesto_provisional_y_sin_conceptos_avisan() -> None:
    propuesto = _c("EJ-1", {"concreto", "acero", "cimbra"}, None, estado="propuesto")
    codigos = {a.codigo for a in validar_contra_matriz([_elemento([propuesto], provisional=True)])}
    assert codigos == {"concepto_propuesto", "elemento_provisional"}
    assert [a.codigo for a in validar_contra_matriz([_elemento([])])] == ["sin_concepto"]
    sin_matriz = _c("X", {"concreto", "acero", "cimbra"}, None, estado="sin_matriz")
    assert [a.codigo for a in validar_contra_matriz([_elemento([sin_matriz])])] == ["concepto_sin_matriz"]
