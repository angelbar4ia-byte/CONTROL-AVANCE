"""Los endpoints de la biblioteca de elementos y del cálculo del muro MCT-01010 (sin base de datos)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from obractrl.adapters.api.v1.biblioteca_de_elementos import router


@pytest.fixture
def cliente() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_la_biblioteca_trae_la_categoria_y_la_subcategoria(cliente: TestClient) -> None:
    r = cliente.get("/biblioteca-de-elementos")
    assert r.status_code == 200
    (cat,) = r.json()
    assert cat["nombre"] == "Muros de contención"
    assert cat["subcategorias"][0]["nombre"] == "Mampostería"
    assert cat["subcategorias"][0]["elementos"][0]["clave"] == "MCT-01010"


def test_la_definicion_trae_el_cuadro_y_los_pendientes(cliente: TestClient) -> None:
    r = cliente.get("/biblioteca-de-elementos/MCT-01010")
    assert r.status_code == 200
    cuerpo = r.json()
    assert len(cuerpo["cuadro_1"]) == 11
    assert cuerpo["concepto"]["clave"] == "MCT-01011"
    assert cliente.get("/biblioteca-de-elementos/XX-1").status_code == 404


def test_calcular_devuelve_el_volumen_y_el_dren(cliente: TestClient) -> None:
    r = cliente.post("/biblioteca-de-elementos/MCT-01010/calcular", json={"alto_m": 3.0})
    assert r.status_code == 200
    c = r.json()
    assert c["volumen"]["total_m3_ml"] == pytest.approx(2.91)
    assert c["dren"]["hileras"] == 3
    assert c["dren"]["tubo"]["provisional"] is True


def test_calcular_rechaza_lo_que_no_vale(cliente: TestClient) -> None:
    assert (
        cliente.post(
            "/biblioteca-de-elementos/MCT-01010/calcular", json={"alto_m": 0}
        ).status_code
        == 422
    )
    assert (
        cliente.post(
            "/biblioteca-de-elementos/MCT-01010/calcular",
            json={"alto_m": 3, "lluvia": "media"},
        ).status_code
        == 422
    )
    malo = cliente.post(
        "/biblioteca-de-elementos/MCT-01010/calcular",
        json={"alto_m": 3, "corona_m": 1.0, "base_m": 0.5},
    )
    assert malo.status_code == 422
    assert (
        cliente.post(
            "/biblioteca-de-elementos/CIM-01010/calcular", json={"alto_m": 3}
        ).status_code
        == 404
    )
