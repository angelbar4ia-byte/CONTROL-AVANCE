"""Los endpoints de los muros de tabique, aparejos y piso de petatillo: ficha, cálculo y tabla de revisión (sin base de datos)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from obractrl.adapters.api.v1.biblioteca_de_elementos import router as router_biblioteca
from obractrl.adapters.api.v1.muros_de_tabique import router

RUTA = "/biblioteca-de-elementos/tabique"


@pytest.fixture
def cliente() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.include_router(router_biblioteca)
    return TestClient(app)


def test_la_ficha_trae_aparejo_conceptos_y_pendientes(cliente: TestClient) -> None:
    r = cliente.get(f"{RUTA}/EST-02010")
    assert r.status_code == 200
    f = r.json()
    assert f["categoria"]["nombre"] == "Muros" and f["subcategoria"]["nombre"] == "Muros de tabique"
    assert f["espesor_real_cm"] == pytest.approx(14.0) and f["parametros_por_defecto"]["junta_cm"] == 2.0
    assert [c["clave"] for c in f["conceptos"]] == ["EST-02010", "EST-02011"]
    assert f["conceptos"][1]["nivel_desde"] == 3 and f["conceptos"][0]["destajo"]["clave"] == "MOE-02010"
    assert any(p["clave"] == "Q99" for p in f["pendientes"])
    assert cliente.get(f"{RUTA}/EST-99999").status_code == 404
    piso = cliente.get(f"{RUTA}/ACA-02090").json()
    assert piso["categoria"]["clave"] == "pisos" and piso["parametros_por_defecto"]["cama_cm"] == 0.0


def test_calcula_el_muro_de_14_con_el_concepto_del_nivel(cliente: TestClient) -> None:
    r = cliente.post(f"{RUTA}/EST-02010/calcular", json={"cantidad": 100, "nivel": 3})
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["concepto"]["clave"] == "EST-02011" and c["piezas"]["total"] == pytest.approx(5000.0)
    assert c["piezas"]["a_comprar"] == 5000
    assert c["conciliacion"][0]["resumen"]["="] == 2
    assert c["mano_de_obra"]["destajo"]["clave"] == "MOE-02012"


def test_el_21_muestra_la_diferencia_y_los_aparejos_nuevos_no_tienen_conciliacion(cliente: TestClient) -> None:
    c = cliente.post(f"{RUTA}/EST-02020/calcular", json={}).json()
    assert c["geometria"]["espesor_real_cm"] == pytest.approx(21.0)
    assert c["conciliacion"][0]["coincide"] is False
    nuevo = cliente.post(f"{RUTA}/EST-02040/calcular", json={}).json()
    assert nuevo["conciliacion"] == [] and nuevo["concepto"]["clave_provisional"] is True


def test_los_datos_que_no_valen_dan_422_y_la_clave_desconocida_404(cliente: TestClient) -> None:
    assert cliente.post(f"{RUTA}/EST-02010/calcular", json={"cantidad": 0}).status_code == 422
    assert cliente.post(f"{RUTA}/EST-02050/calcular", json={"tipo_de_sardinel": "otro"}).status_code == 422
    assert cliente.post(f"{RUTA}/EST-02010/calcular", json={"cama_cm": 3}).status_code == 422
    assert cliente.post(f"{RUTA}/EST-99999/calcular", json={}).status_code == 404


def test_la_tabla_de_revision_va_antes_que_la_ficha(cliente: TestClient) -> None:
    r = cliente.get(f"{RUTA}/tabla-de-revision")
    assert r.status_code == 200
    filas = r.json()
    assert len(filas) == 8 and filas[0]["clave"] == "EST-02005" and filas[0]["provisional"] is True


def test_la_biblioteca_lista_muros_y_pisos_y_su_ficha_es_aparte(cliente: TestClient) -> None:
    categorias = {c["clave"]: c for c in cliente.get("/biblioteca-de-elementos").json()}
    assert {"muros", "pisos", "contencion"} <= set(categorias)
    assert cliente.get("/biblioteca-de-elementos/EST-02010").status_code == 404
    assert cliente.get("/biblioteca-de-elementos/MCT-01010").status_code == 200
