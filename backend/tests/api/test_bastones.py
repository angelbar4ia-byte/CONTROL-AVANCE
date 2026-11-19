"""Los endpoints de los bastones: ficha y cálculo (sin base de datos)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from obractrl.adapters.api.v1.bastones import router
from obractrl.adapters.api.v1.biblioteca_de_elementos import router as router_biblioteca

RUTA = "/biblioteca-de-elementos/baston"


@pytest.fixture
def cliente() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.include_router(router_biblioteca)
    return TestClient(app)


def test_la_ficha_trae_modulos_escalones_y_pendientes(cliente: TestClient) -> None:
    r = cliente.get(f"{RUTA}/BA-1")
    assert r.status_code == 200
    f = r.json()
    assert f["modulos_de_corte_m"] == [1.0, 1.5, 2.0, 3.0, 4.0, 6.0]
    assert f["parametros_por_defecto"]["puntas_cm"] == 0.0 and len(f["escalones"]) == 28
    assert any(p["clave"] == "Q28" for p in f["pendientes"])
    assert cliente.get(f"{RUTA}/BA-9").status_code == 404


def test_calcula_con_corte_ajustado_y_el_escalon_del_catalogo(cliente: TestClient) -> None:
    r = cliente.post(f"{RUTA}/BA-1/calcular", json={"trazo_m": 10, "largo_cm": 142.86})  # 1.20 m recto + 2 ganchos incluidos
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["ajustado"]["bastones"] == 41 and c["ajustado"]["varillas"] == 6 and c["exacto"]["varillas"] == 6
    assert c["concepto"]["clave"] == "AUX-02010" and c["escalon"] == "exacto" and c["pago"]["modo"] == "pieza"
    assert c["conciliacion"][0]["resumen"]["≠"] == 1


def test_el_gancho_es_un_parametro_explicito_y_sale_en_el_desglose(cliente: TestClient) -> None:
    c = cliente.post(f"{RUTA}/BA-1/calcular", json={"varilla_numero": 4, "gancho_cm": 14, "ganchos": 1}).json()
    assert c["parametros"]["recto_cm"] == pytest.approx(120 - 14) and c["ajustado"]["corte"]["necesario_m"] == pytest.approx(1.2)
    assert c["gancho"]["ganchos"] == 1 and c["gancho"]["longitud_cm"] == 14 and c["ajustado"]["corte"]["gancho_m"] == pytest.approx(0.14)
    c0 = cliente.post(f"{RUTA}/BA-1/calcular", json={"ganchos": 0}).json()
    assert c0["gancho"]["total_por_baston_cm"] == 0 and c0["ajustado"]["corte"]["modulo_m"] == 1.5
    assert cliente.post(f"{RUTA}/BA-1/calcular", json={"ganchos": 3}).status_code == 422
    assert cliente.get(f"{RUTA}/BA-1").json()["parametros_por_defecto"]["ganchos"] == 2


def test_sin_escalon_propone_concepto_nuevo_provisional(cliente: TestClient) -> None:
    c = cliente.post(f"{RUTA}/BA-1/calcular", json={"largo_cm": 135, "sep_cm": 30}).json()
    assert c["escalon"] == "sin_escalon" and c["concepto"]["clave_provisional"] is True and c["conciliacion"] == []


def test_los_datos_que_no_valen_dan_422_y_la_clave_desconocida_404(cliente: TestClient) -> None:
    assert cliente.post(f"{RUTA}/BA-1/calcular", json={"trazo_m": 0}).status_code == 422
    assert cliente.post(f"{RUTA}/BA-1/calcular", json={"varilla_numero": 9}).status_code == 422
    assert cliente.post(f"{RUTA}/BA-9/calcular", json={}).status_code == 404


def test_la_biblioteca_lista_el_baston_y_su_ficha_es_aparte(cliente: TestClient) -> None:
    categorias = {c["clave"]: c for c in cliente.get("/biblioteca-de-elementos").json()}
    assert "aceros" in categorias
    assert cliente.get("/biblioteca-de-elementos/BA-1").status_code == 404
