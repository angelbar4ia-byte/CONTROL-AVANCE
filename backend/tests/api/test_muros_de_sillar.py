"""Los endpoints del muro de sillar amarillo BAP-01010: ficha, cálculo con el driver de desperdicio y su lugar en la biblioteca (sin base de datos)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from obractrl.adapters.api.v1.biblioteca_de_elementos import router as router_biblioteca
from obractrl.adapters.api.v1.muros_de_sillar import router
from obractrl.adapters.api.v1.muros_de_tabique import router as router_tabique

RUTA = "/biblioteca-de-elementos/sillar"


@pytest.fixture
def cliente() -> TestClient:
    app = FastAPI()
    app.include_router(router_tabique)
    app.include_router(router)
    app.include_router(router_biblioteca)
    return TestClient(app)


def test_la_ficha_trae_la_pieza_el_concepto_del_catalogo_y_los_supuestos(cliente: TestClient) -> None:
    r = cliente.get(f"{RUTA}/BAP-01010")
    assert r.status_code == 200, r.text
    f = r.json()
    assert (f["categoria"]["nombre"], f["subcategoria"]["nombre"]) == ("Muros", "Muros de sillar")
    assert f["pieza"] == {"insumo": "PET-00008", "ancho_cm": 19.0, "alto_cm": 25.0, "largo_cm": 45.0}
    assert [(c["clave"], c["estado"], c["en_catalogo"]) for c in f["conceptos"]] == [("BAP-01010", "catalogo", True)]
    assert f["driver_de_desperdicio"] == "desperdicio_mamposteria" and f["parametros_por_defecto"]["junta_cm"] == 2.0
    assert cliente.get(f"{RUTA}/EST-02010").status_code == 404


def test_calcula_con_el_valor_de_partida_y_dice_de_donde_salio_el_desperdicio(cliente: TestClient) -> None:
    r = cliente.post(f"{RUTA}/BAP-01010/calcular", json={"cantidad": 100})
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["piezas"]["total"] == pytest.approx(827.4231, abs=1e-3) and c["piezas"]["a_comprar"] == 828
    assert c["concepto"]["clave"] == "BAP-01010" and c["mano_de_obra"]["destajo"]["clave"] == "MOE-02016"
    assert [(i["parte"], i["clave"]) for i in c["insumos"]] == [("sillar", "PET-00008"), ("mezcla", "MEZ-07010")]
    assert [(u["clave"], u["valor"], u["fuente"]) for u in c["drivers_usados"]] == [("desperdicio_mamposteria", 5.0, "defecto")]
    assert c["conciliacion"][0]["resumen"]["≠"] == 2
    p = cliente.post(f"{RUTA}/BAP-01010/calcular", json={"desperdicio_pct": 8, "junta_cm": 1}).json()
    assert p["drivers_usados"][0]["fuente"] == "peticion" and p["parametros"]["junta_cm"] == 1


def test_lo_que_no_vale_da_422_y_la_clave_desconocida_404(cliente: TestClient) -> None:
    assert cliente.post(f"{RUTA}/BAP-01010/calcular", json={"cantidad": 0}).status_code == 422
    assert cliente.post(f"{RUTA}/BAP-01010/calcular", json={"junta_cm": 11}).status_code == 422
    assert cliente.post(f"{RUTA}/BAP-01010/calcular", json={"desperdicio_pct": 101}).status_code == 422
    assert cliente.post(f"{RUTA}/EST-99999/calcular", json={}).status_code == 404


def test_la_biblioteca_lista_el_elemento_y_el_tabique_no_lo_confunde(cliente: TestClient) -> None:
    cat = cliente.get("/biblioteca-de-elementos").json()
    muros = next(c for c in cat if c["clave"] == "muros")
    sillar = next(s for s in muros["subcategorias"] if s["clave"] == "sillar")
    assert [e["clave"] for e in sillar["elementos"]] == ["BAP-01010"]
    assert cliente.get("/biblioteca-de-elementos/tabique/BAP-01010").status_code == 404
