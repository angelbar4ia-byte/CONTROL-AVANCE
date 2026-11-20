"""D8 (Q51 y Q52): el concepto de colado y cimbra por ml de las trabes, contratrabes y nervaduras y su destajo por ml, como propuesta.

Lo que se comprueba: una clave provisional distinta por elemento y solo para los 36 elementos lineales; el concepto toma lo que el elemento gasta por
ml (el mismo cálculo del elemento); el destajo por ml queda SIN importe y la propuesta no trae precios; y no se inventa nada para la zapata ni la
columna (su concepto del catálogo ya paga el colado)."""

from __future__ import annotations

import re

import pytest

from obractrl.domain.cuantificacion.colado_por_ml import (
    CLAVES_PROVISIONALES,
    clave_provisional_de_colado,
    concepto_de_colado,
    concepto_nuevo_de_colado,
)
from obractrl.domain.cuantificacion.conceptos_de_elemento import _CLAVE
from obractrl.domain.cuantificacion.elementos_lineales import (
    TIPO_LINEAL,
    EntradaElementoEstructural,
    calcular_elemento,
    claves_de_elementos_estructurales,
    elemento_estructural,
)

LINEALES = [k for k in claves_de_elementos_estructurales() if elemento_estructural(k)["tipo"] == TIPO_LINEAL]  # type: ignore[index]


def test_los_36_elementos_lineales_tienen_su_clave_provisional_y_ninguna_se_repite() -> None:
    assert len(LINEALES) == 36
    assert set(CLAVES_PROVISIONALES) == set(LINEALES)
    assert len(set(CLAVES_PROVISIONALES.values())) == 36
    for k in CLAVES_PROVISIONALES.values():
        assert k.startswith("EJ-7") and _CLAVE.match(k)


def test_ninguna_clave_provisional_choca_con_un_concepto_o_insumo_que_el_codigo_conoce() -> None:
    usados = {c["clave"] for k in LINEALES for c in elemento_estructural(k)["catalogo"]}  # type: ignore[index]
    assert not usados & set(CLAVES_PROVISIONALES.values())
    # La clave de la armex de K-8 que ya propuso la 3A (D4) tampoco se pisa.
    assert "EJ-780" not in CLAVES_PROVISIONALES.values()


@pytest.mark.parametrize("clave", LINEALES)
def test_el_concepto_toma_lo_que_el_elemento_gasta_por_ml(clave: str) -> None:
    c = concepto_de_colado(clave)
    assert c is not None and c["clave"] == CLAVES_PROVISIONALES[clave] and c["unidad"] == "ml"
    r = calcular_elemento(EntradaElementoEstructural(clave=clave, modo="ml"))
    esperado = {f["clave"]: round(f["por_unidad"], 6) for f in r["insumos"] if f["parte"] in ("concreto", "cimbra")}
    assert c["insumos_por_ml"] == esperado
    assert c["toma"]["concreto"] is True
    assert c["toma"]["cimbra"] is bool(elemento_estructural(clave)["lados"])  # type: ignore[index]
    # El acero sigue pagándose con el auxiliar del catálogo: el concepto nuevo no lo toma.
    assert c["acero"]["clave"] == elemento_estructural(clave)["catalogo"][0]["clave"]  # type: ignore[index]
    assert "acero" not in c["toma"]


def test_la_nervadura_no_lleva_cimbra_porque_el_caseton_la_forma() -> None:
    c = concepto_de_colado("N-1-12x25")
    assert c is not None
    assert c["toma"] == {"concreto": True, "cimbra": False}
    assert c["descripcion"].startswith("Colado de ") and not c["descripcion"].startswith("Colado y cimbra")
    assert set(c["insumos_por_ml"]) == {"CON-00004"}


def test_el_destajo_por_ml_queda_sin_importe_y_la_propuesta_no_trae_precios() -> None:
    for clave in LINEALES:
        p = concepto_nuevo_de_colado(clave)
        assert p is not None
        assert p["clase"] == "concepto_nuevo" and p["elemento_clave"] == clave
        assert p["concepto_clave"] == CLAVES_PROVISIONALES[clave]
        d = p["detalle"]
        assert d["clave_provisional"] is True and d["unidad"] == "ml"
        assert d["destajo_por_ml"] == {
            "clave_provisional": CLAVES_PROVISIONALES[clave] + "-MO", "descripcion": d["destajo_por_ml"]["descripcion"], "unidad": "ml",
            "importe": None, "estado": "por_definir",
        }
        assert re.fullmatch(r"[A-Z0-9.\-_]{2,20}", d["destajo_por_ml"]["clave_provisional"])
        for prohibido in ("precio", "costo", "importe_", "$"):
            assert prohibido not in str({k: v for k, v in d.items() if k != "motivos"}).lower().replace("'importe': none", "")
        assert any("Q52" in m for m in d["motivos"])


def test_la_zapata_y_la_columna_no_tienen_concepto_de_colado_por_ml() -> None:
    for k in ("Z-1", "C-1", "NO-EXISTE"):
        assert clave_provisional_de_colado(k) is None
        assert concepto_de_colado(k) is None
        assert concepto_nuevo_de_colado(k) is None
