"""Los endpoints de los castillos, aparentes y forjadas: ficha y cálculo (sin base de datos)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from obractrl.adapters.api.v1.biblioteca_de_elementos import router as router_biblioteca
from obractrl.adapters.api.v1.elementos_de_estructura import router

RUTA = "/biblioteca-de-elementos/estructura"


@pytest.fixture
def cliente() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.include_router(router_biblioteca)
    return TestClient(app)


def test_la_ficha_trae_la_clasificacion_los_conceptos_y_los_pendientes(cliente: TestClient) -> None:
    r = cliente.get(f"{RUTA}/EST-02140")
    assert r.status_code == 200
    f = r.json()
    assert f["alias"] == "K-4" and f["categoria"]["clave"] == "castillos" and f["subcategoria"]["nombre"] == "Castillos de muro"
    assert any("en ángulo" in p for p in f["pendientes"])
    assert {c["ranura"] for c in f["conceptos"]} == {"acero", "colado"}
    assert cliente.get(f"{RUTA}/K-99").status_code == 404


def test_la_biblioteca_lista_las_nuevas_categorias_y_la_ficha_del_muro_sigue_aparte(cliente: TestClient) -> None:
    categorias = {c["clave"]: c for c in cliente.get("/biblioteca-de-elementos").json()}
    assert {"castillos", "cadenas", "columnas", "contencion"} <= set(categorias)
    cadenas = {s["clave"]: s for s in categorias["cadenas"]["subcategorias"]}
    assert [e["clave"] for e in cadenas["desplante_aparente"]["elementos"]] == ["BAP-03010"]
    assert [e["clave"] for e in cadenas["cerramiento_aparente"]["elementos"]] == ["BAP-03030"]
    assert cliente.get("/biblioteca-de-elementos/EST-02130").status_code == 404  # su ficha es /estructura/…
    assert cliente.get("/biblioteca-de-elementos/MCT-01010").status_code == 200


def test_calcular_devuelve_la_receta_el_colado_y_los_conceptos(cliente: TestClient) -> None:
    r = cliente.post(f"{RUTA}/EST-02130/calcular", json={"alto_m": 6.0})
    assert r.status_code == 200
    c = r.json()
    assert c["alto_m"] == 6.0 and c["unidad_de_calculo"] == "pza"
    assert c["acero"]["armex"] is None and c["acero"]["varillas"][0]["numero"] == 4
    assert c["colado"]["concreto_m3_ml"] == pytest.approx(0.04725)
    acero = next(x for x in c["conceptos"] if x["ranura"] == "acero")
    assert acero["clave"] == "EST-10031" and acero["insumos"]["ACR-00002"] > 0
    assert c["forro"] is None


def test_sin_alto_usa_la_altura_estandar_y_la_forjada_su_alto_fijo(cliente: TestClient) -> None:
    assert cliente.post(f"{RUTA}/K-1/calcular", json={}).json()["alto_m"] == 3.0
    f = cliente.post(f"{RUTA}/EST-07010/calcular", json={}).json()
    assert f["alto_m"] == 4.2 and f["forro"]["tabique_pza"] == pytest.approx(161.7) and f["lados_cimbra"] == 1


def test_una_forjada_de_otra_altura_avisa_del_concepto_nuevo(cliente: TestClient) -> None:
    f = cliente.post(f"{RUTA}/EST-07010/calcular", json={"alto_m": 3.8}).json()
    assert f["concepto_nuevo_por_altura"]["clave_propuesta"] == "EST-07010-H380"
    assert any("concepto nuevo" in a for a in f["advertencias"])


def test_calcular_rechaza_lo_que_no_vale(cliente: TestClient) -> None:
    assert cliente.post(f"{RUTA}/K-1/calcular", json={"alto_m": 0}).status_code == 422
    assert cliente.post(f"{RUTA}/K-1/calcular", json={"alto_m": 31}).status_code == 422
    assert cliente.post(f"{RUTA}/K-99/calcular", json={}).status_code == 404
    assert cliente.post(f"{RUTA}/K-1/calcular", json={"alto_m": 3, "drivers": {"max_piezas_corte": 0}}).status_code == 422
