"""La ficha y el cálculo suelto de la losa por HTTP (fase 2 de las zonas de losa), sin base de datos: no piden sesión ni token."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from obractrl.adapters.api.v1.losas import router

RUTA = "/biblioteca-de-elementos/losa"


@pytest.fixture
def cliente() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_la_ficha_de_la_losa(cliente: TestClient) -> None:
    r = cliente.get(f"{RUTA}/LOSA-MACIZA")
    assert r.status_code == 200
    d = r.json()
    assert d["nombre"] == "Losa maciza" and d["tipo"] == "maciza" and d["categoria"]["clave"] == "losas"
    assert d["concepto"] == {
        "clave": "EJ-800", "descripcion": d["concepto"]["descripcion"], "unidad": "m²", "estado": "propuesto", "provisional": True,
    }
    assert d["parrilla"]["clave"] == "AUX-06010" and len(d["elementos_permitidos"]) == 36
    assert {p["clave"] for p in d["pendientes"]} >= {"Q49", "L1"}
    assert cliente.get(f"{RUTA}/LOSA-NERVADA").json()["parrilla"] is None
    assert cliente.get(f"{RUTA}/T-1-15x25").status_code == 404


def test_calcular_una_losa_maciza_con_trabes(cliente: TestClient) -> None:
    r = cliente.post(
        f"{RUTA}/LOSA-MACIZA/calcular",
        json={
            "espesor_m": 0.12, "uso": "azotea", "losas": [{"area_m2": 125}],
            "elementos": [
                {"clave": "T-1-15x20", "cantidad": 70},
                {"clave": "T-2-12x20", "cantidad": 28, "pago": "propio"},
            ],
        },
    )
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["area_m2"] == 125 and m["concreto"]["clave"] == "CON-00004"
    assert m["concreto"]["con_desperdicio_m3"] == pytest.approx(125 * 0.12 * 1.05)
    assert [(c["parte"], c["concepto"]["clave"], c["cantidad"]) for c in m["conceptos"]] == [
        ("losa", "EJ-800", 125.0), ("acero", "AUX-10106", 70.0), ("acero", "AUX-10205", 28.0), ("colado", "EJ-741", 28.0),
    ]
    assert all(c["propuesta"] is None for c in m["conceptos"])  # el cálculo suelto no consulta propuestas
    assert m["zona"] is None and m["conciliacion"] is None
    assert m["mano_de_obra"]["estado"] == "sin_mano_de_obra"
    claves_de_drivers = {u["clave"] for u in m["drivers_usados"]}
    assert {"desperdicio_concreto", "traslape_varilla_diametros"} <= claves_de_drivers
    assert all(u["fuente"] == "defecto" for u in m["drivers_usados"])  # sin obra: lo de siempre


def test_la_peticion_manda_sobre_el_valor_por_defecto(cliente: TestClient) -> None:
    r = cliente.post(f"{RUTA}/LOSA-MACIZA/calcular", json={"losas": [{"area_m2": 10}], "desperdicio_concreto_pct": 0})
    assert r.json()["concreto"]["con_desperdicio_m3"] == pytest.approx(10 * 0.12)
    usado = next(u for u in r.json()["drivers_usados"] if u["clave"] == "desperdicio_concreto")
    assert (usado["valor"], usado["fuente"]) == (0, "peticion")


def test_un_dato_que_no_vale_es_422_y_una_clave_que_no_existe_404(cliente: TestClient) -> None:
    for elemento in ({"clave": "Z-1"}, {"clave": "XX-9"}, {"clave": "T-1-15x25", "modo": "pieza"}):
        r = cliente.post(f"{RUTA}/LOSA-MACIZA/calcular", json={"losas": [{"area_m2": 10}], "elementos": [elemento]})
        assert r.status_code == 422, (elemento, r.text)
    assert cliente.post(f"{RUTA}/LOSA-MACIZA/calcular", json={"espesor_m": 0}).status_code == 422
    assert cliente.post(f"{RUTA}/LOSA-MACIZA/calcular", json={"uso": "sotano"}).status_code == 422
    assert cliente.post(f"{RUTA}/OTRA/calcular", json={}).status_code == 404
