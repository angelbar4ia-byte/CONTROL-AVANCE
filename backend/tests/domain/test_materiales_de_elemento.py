"""Los materiales que elige un elemento: normalización, familias de cada parte, firma y cantidades por insumo (fase D)."""

from __future__ import annotations

import pytest

from obractrl.domain.cuantificacion.clasificacion_de_elementos import firma_de_elemento
from obractrl.domain.cuantificacion.elementos_parametricos import (
    ErrorDeElementoParametrico,
    normalizar_parametros,
    receta,
    toma_por_unidad,
)
from obractrl.domain.cuantificacion.insumos_permitidos import Insumo, InsumoNoPermitido
from obractrl.domain.cuantificacion.materiales_de_elemento import (
    cantidades_por_insumo,
    claves_de_materiales,
    normalizar_materiales,
    validar_materiales,
)


def _mat(clave: str, familia: str, sub: str | None = None, unidad: str = "kg") -> Insumo:
    return Insumo(clave=clave, descripcion=clave, clase="material", familia=familia, subfamilia=sub, unidad=unidad)


BASE = {
    "MEZ-01020": _mat("MEZ-01020", "Mezclas", "Concretos", "m3"),
    "ACE-00001": _mat("ACE-00001", "Aceros", "Consumible"),
    "ACR-00001": _mat("ACR-00001", "Acero De Refuerzo", "Habilitable", "pza"),
    "ACE-00003": _mat("ACE-00003", "Aceros", "Prefabricado"),
    "ACE-00011": _mat("ACE-00011", "Aceros", "Prefabricado", "pza"),
    "ACE-00012": _mat("ACE-00012", "Aceros", "Consumible"),
    "MAD-00001": _mat("MAD-00001", "Cimbra", "Cimbra", "m2"),
    "PET-00004": _mat("PET-00004", "Pétreos", "Piedras", "m3"),
}


def test_normalizar_limpia_y_descarta_lo_vacio() -> None:
    m = normalizar_materiales(
        {"concreto": " mez-01020 ", "alambre": "", "varilla": None, "cimbra": {"mad-00001": 0.12, "ACE-00012": "0.5"}}
    )
    assert m == {"concreto": "MEZ-01020", "cimbra": {"ACE-00012": 0.5, "MAD-00001": 0.12}}
    assert normalizar_materiales(None) == {} and normalizar_materiales({}) == {}


@pytest.mark.parametrize(
    "malo",
    [{"cemento": "X-1"}, {"concreto": "x"}, {"cimbra": [1]}, {"cimbra": {"MAD-00001": 0}}, {"cimbra": {"MAD-00001": "abc"}}, {"cimbra": {"mad-00001": 1, "MAD-00001": 2}}],
)
def test_normalizar_rechaza_lo_que_no_vale(malo: dict) -> None:
    with pytest.raises(ErrorDeElementoParametrico):
        normalizar_materiales(malo)


def test_claves_de_materiales_en_orden_estable() -> None:
    m = normalizar_materiales({"alambre": "ACE-00001", "concreto": "MEZ-01020", "cimbra": {"MAD-00001": 1}})
    assert claves_de_materiales(m) == [("concreto", "MEZ-01020"), ("alambre", "ACE-00001"), ("cimbra", "MAD-00001")]


def _validar(tipo: str, m: dict) -> None:
    limpios = normalizar_materiales(m)
    validar_materiales(tipo, limpios, {c: BASE.get(c) for _, c in claves_de_materiales(limpios)})


def test_cada_parte_se_elige_en_su_familia() -> None:
    _validar("castillo", {"concreto": "MEZ-01020", "alambre": "ACE-00001", "varilla": "ACR-00001", "anillo": "ACE-00003", "armex": "ACE-00011", "cimbra": {"MAD-00001": 0.1, "ACE-00012": 0.2}})
    with pytest.raises(InsumoNoPermitido, match="no sirve de concreto"):
        _validar("castillo", {"concreto": "ACR-00001"})
    with pytest.raises(InsumoNoPermitido, match="no sirve de varilla"):
        _validar("castillo", {"varilla": "ACE-00001"})
    with pytest.raises(InsumoNoPermitido, match="no es de las familias"):
        _validar("castillo", {"alambre": "PET-00004"})


def test_un_insumo_que_no_existe_o_que_no_es_material_se_rechaza() -> None:
    with pytest.raises(ErrorDeElementoParametrico, match="no existe en la base"):
        _validar("lineal", {"concreto": "MEZ-99999"})
    mo = Insumo("CUAD-001", "Cuadrilla", "mano_obra", "Cuadrillas", "Albañilería y Estructura")
    with pytest.raises(InsumoNoPermitido, match="no es un material"):
        validar_materiales("lineal", {"concreto": "CUAD-001"}, {"CUAD-001": mo})


def test_la_firma_sin_materiales_es_la_de_antes() -> None:
    p = normalizar_parametros("lineal", {"ancho": 0.15, "alto": 0.2})
    assert firma_de_elemento("cadenas", "cerramiento", "lineal", p) == firma_de_elemento("cadenas", "cerramiento", "lineal", p, {})
    assert firma_de_elemento("cadenas", "cerramiento", "lineal", p) == firma_de_elemento("cadenas", "cerramiento", "lineal", p, None)


def test_la_firma_distingue_los_materiales_pero_no_su_orden() -> None:
    p = normalizar_parametros("castillo", {})
    sin = firma_de_elemento("castillos", "muro", "castillo", p)
    a = firma_de_elemento("castillos", "muro", "castillo", p, {"concreto": "MEZ-01020", "alambre": "ACE-00001"})
    b = firma_de_elemento("castillos", "muro", "castillo", p, {"alambre": "ACE-00001", "concreto": "MEZ-01020"})
    otro = firma_de_elemento("castillos", "muro", "castillo", p, {"concreto": "MEZ-01030", "alambre": "ACE-00001"})
    assert a == b and len({sin, a, otro}) == 3
    c1 = firma_de_elemento("castillos", "muro", "castillo", p, {"cimbra": {"MAD-00001": 0.1, "ACE-00012": 0.2}})
    c2 = firma_de_elemento("castillos", "muro", "castillo", p, {"cimbra": {"ACE-00012": 0.2, "MAD-00001": 0.1}})
    c3 = firma_de_elemento("castillos", "muro", "castillo", p, {"cimbra": {"MAD-00001": 0.1, "ACE-00012": 0.25}})
    assert c1 == c2 != c3


# --- Cantidades por insumo ------------------------------------------------------------------------------------------


def test_las_cantidades_del_castillo_en_pieza_salen_de_su_receta() -> None:
    p = normalizar_parametros("castillo", {"alto": 2.6})
    r = receta("castillo", p)
    m = normalizar_materiales(
        {"concreto": "MEZ-01020", "alambre": "ACE-00001", "varilla": "ACR-00001", "anillo": "ACE-00003", "cimbra": {"MAD-00001": 0.3}}
    )
    unidades = {"MEZ-01020": "m3", "ACE-00001": "kg", "ACR-00001": "pza", "ACE-00003": "kg", "MAD-00001": "m2"}
    todo = {"concreto": True, "acero": True, "estribos": True, "alambre": True, "cimbra": True}
    q, avisos = cantidades_por_insumo("castillo", p, m, unidad="pza", toma=todo, unidades_de_insumo=unidades)
    assert avisos == []
    assert q["MEZ-01020"] == pytest.approx(r["concreto"])
    assert q["ACE-00001"] == pytest.approx(r["alambre_kg"])
    assert q["ACE-00003"] == pytest.approx(r["estribos_kg"])
    assert q["ACR-00001"] == pytest.approx(r["acero_kg"] / (0.994 * 12))  # varilla #4 en piezas de 12 m
    assert q["MAD-00001"] == pytest.approx(0.3)


def test_un_castillo_contado_en_ml_divide_entre_su_alto() -> None:
    p = normalizar_parametros("castillo", {"alto": 2.5})
    por = toma_por_unidad("castillo", p, "ml", {"concreto": True})["por_unidad"]["concreto"]["cantidad"]
    m = {"concreto": "MEZ-01020", "cimbra": {"MAD-00001": 0.5}}
    q, _ = cantidades_por_insumo("castillo", p, m, unidad="ml", toma={"concreto": True, "cimbra": True}, unidades_de_insumo={})
    assert q["MEZ-01020"] == pytest.approx(por) == pytest.approx(0.15 * 0.15)
    assert q["MAD-00001"] == pytest.approx(0.5 / 2.5)


def test_la_varilla_en_kg_y_el_alambre_de_la_cimbra_se_suman_en_su_clave() -> None:
    p = normalizar_parametros("lineal", {})
    m = {"varilla": "ACE-00002", "alambre": "ACE-00001", "cimbra": {"ACE-00001": 0.01}}
    todo = {"acero": True, "alambre": True, "cimbra": True}
    q, _ = cantidades_por_insumo("lineal", p, m, unidad="ml", toma=todo, unidades_de_insumo={"ACE-00002": "kg"})
    r = receta("lineal", p)
    assert q["ACE-00002"] == pytest.approx(r["acero_kg"])
    assert q["ACE-00001"] == pytest.approx(r["alambre_kg"] + 0.01)


def test_lo_que_no_se_puede_calcular_se_avisa_y_no_se_inventa() -> None:
    p = normalizar_parametros("castillo", {})
    q, avisos = cantidades_por_insumo(
        "castillo", p, {"armex": "ACE-00011"}, unidad="pza",
        toma={"acero": True, "concreto": True, "alambre": True, "estribos": True, "cimbra": True}, unidades_de_insumo={},
    )
    assert q == {}
    assert len(avisos) == 5 and any("armex" in a.lower() for a in avisos) and any("concreto" in a for a in avisos)
