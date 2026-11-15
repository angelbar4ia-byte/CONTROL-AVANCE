"""Definición y cálculo de trabes, contratrabes, nervaduras, Z-1 y C-1 por HTTP (sin base de datos)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from obractrl.adapters.api.v1.biblioteca_de_elementos import router as router_biblioteca
from obractrl.adapters.api.v1.elementos_estructurales import router


@pytest.fixture
def cliente() -> TestClient:
    app = FastAPI()
    app.include_router(router)  # antes que la biblioteca, como en la API real
    app.include_router(router_biblioteca)
    return TestClient(app)


def test_la_definicion_trae_la_tarjeta(cliente: TestClient) -> None:
    r = cliente.get("/biblioteca-de-elementos/estructura/T-1-15x25")
    assert r.status_code == 200
    d = r.json()
    assert d["nombre"].startswith("Trabe T-1 de 15x25")
    assert d["categoria"]["nombre"] == "Trabes" and d["subcategoria"]["nombre"] == "Trabes de losa (catálogo)"
    assert d["seccion"] == {"ancho_cm": 15.0, "peralte_cm": 25.0, "largo_cm": None}
    assert d["modos"] == ["ml", "pieza"]
    assert d["camino_de_colado_y_cimbra"]["estado"] == "por_registrar"
    assert d["camino_de_colado_y_cimbra"]["borrador"]["clave_propuesta"] is None
    assert cliente.get("/biblioteca-de-elementos/estructura/XX-1").status_code == 404


def test_calcular_por_ml_devuelve_insumos_y_conciliacion(cliente: TestClient) -> None:
    r = cliente.post("/biblioteca-de-elementos/estructura/T-1-15x25/calcular", json={"modo": "ml", "cantidad": 10})
    assert r.status_code == 200
    c = r.json()
    assert c["unidad"] == "ml" and c["mano_de_obra"]["estado"] == "sin_mano_de_obra"
    assert c["concreto"]["m3"] == pytest.approx(0.15 * 0.25 * 1.05)
    assert c["conciliacion"][0]["concepto"]["clave"] == "AUX-00008"
    marcas = {f["clave"]: f["marca"] for f in c["conciliacion"][0]["filas"]}
    assert marcas == {"ACR-00001": "≈", "ACE-00005": "=", "ACE-00001": "="}
    var = next(i for i in c["insumos"] if i["clave"] == "ACR-00001")
    assert var["total"] == pytest.approx(10 * var["por_unidad"]) and var["a_comprar"] == 4.0
    assert c["receta_acero"]["forma"] == "ml"


def test_calcular_por_pieza_con_zonas(cliente: TestClient) -> None:
    r = cliente.post(
        "/biblioteca-de-elementos/estructura/CT1-15x25/calcular",
        json={"modo": "pieza", "largo_m": 5.0, "zonas_de_anillo": [{"len_cm": 50, "sep_cm": 10}, {"sep_cm": 15}]},
    )
    assert r.status_code == 200
    c = r.json()
    assert c["unidad"] == "pza" and c["longitud_m"] == 5.0
    assert len(c["receta_acero"]["anillos"]["zonas"]) == 2


def test_z1_y_c1(cliente: TestClient) -> None:
    z = cliente.post("/biblioteca-de-elementos/estructura/Z-1/calcular", json={"modo": "pieza"}).json()
    assert z["parrilla"]["varillas_por_sentido"] == [5, 5] and z["receta_acero"] is None
    assert {m["clave"] for m in z["conciliacion"][0]["mano_de_obra"]} == {"MOE-05010"}
    c = cliente.post("/biblioteca-de-elementos/estructura/C-1/calcular", json={"modo": "pieza", "alto_m": 4.5}).json()
    assert c["longitud_m"] == 4.5 and len(c["conciliacion"]) == 2


def test_lo_que_no_vale_da_422_o_404(cliente: TestClient) -> None:
    ruta = "/biblioteca-de-elementos/estructura/T-1-15x25/calcular"
    assert cliente.post(ruta, json={"cantidad": 0}).status_code == 422
    assert cliente.post(ruta, json={"modo": "ml", "largo_m": 4}).status_code == 422
    assert cliente.post(ruta, json={"modo": "otro"}).status_code == 422
    assert cliente.post("/biblioteca-de-elementos/estructura/Z-1/calcular", json={"modo": "ml"}).status_code == 422
    assert cliente.post("/biblioteca-de-elementos/estructura/NO/calcular", json={}).status_code == 404
