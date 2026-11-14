"""El endpoint de solo cálculo de la receta del acero (sin base de datos)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from obractrl.adapters.api.v1 import api_v1

RUTA = "/biblioteca-de-elementos/receta-acero/calcular"


@pytest.fixture
def cliente() -> TestClient:
    app = FastAPI()
    app.include_router(api_v1)
    return TestClient(app)


def test_calcula_el_castillo_k2_por_el_endpoint(cliente: TestClient) -> None:
    r = cliente.post(
        RUTA,
        json={
            "forma": "castillo",
            "ancho_cm": 15,
            "peralte_cm": 15,
            "longitud_m": 2.6,
            "lados_cimbra": 2,
            "varillas": [{"clave": "ACR-00001", "numero": 3, "peso_kg_m": 0.56, "cantidad": 4}],
            "anillos": [{"sep_cm": 20, "peso_kg_m": 0.249}],
        },
    )
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["varillas"][0]["kg"] == pytest.approx(8.96)
    assert c["varillas"][0]["corte"]["modulo_m"] == 4.0
    assert c["anillos"]["pza"] == 14
    assert c["drivers"]["max_piezas_corte"] == 3


def test_un_driver_de_la_peticion_cambia_el_resultado(cliente: TestClient) -> None:
    cuerpo = {"forma": "castillo", "ancho_cm": 15, "peralte_cm": 15, "longitud_m": 2.6, "armex": {"clave": "ACE-00011"}}
    base = cliente.post(RUTA, json=cuerpo).json()
    con_driver = cliente.post(RUTA, json={**cuerpo, "drivers": {"puntas_armex_cm": 0}}).json()
    assert base["armex"]["corte"]["modulo_m"] == 4.0
    assert con_driver["armex"]["corte"]["modulo_m"] == 3.0


def test_un_dato_que_no_vale_da_422(cliente: TestClient) -> None:
    r = cliente.post(
        RUTA,
        json={
            "forma": "castillo",
            "ancho_cm": 15,
            "peralte_cm": 15,
            "armex": {"clave": "ACE-00011"},
            "varillas": [{"clave": "ACR-00001", "numero": 3, "cantidad": 4}],
        },
    )
    assert r.status_code == 422


def test_la_ruta_no_la_toma_el_calculo_del_muro_de_piedra(cliente: TestClient) -> None:
    r = cliente.post(
        RUTA, json={"forma": "ml", "ancho_cm": 15, "peralte_cm": 25, "armex": {"clave": "ACE-00020"}}
    )
    assert r.status_code == 200
    assert r.json()["unidad"] == "ml"
