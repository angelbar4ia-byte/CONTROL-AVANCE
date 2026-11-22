"""La ficha y el cálculo suelto del relleno por HTTP (Fase 3 de las zonas de losa), sin base de datos: no piden sesión ni token."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from obractrl.adapters.api.v1.rellenos import router

RUTA = "/biblioteca-de-elementos/relleno"


@pytest.fixture
def cliente() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_la_ficha_de_la_azotea_trae_la_arenilla_propuesta_y_los_parametros_dinamicos_por_omision(cliente: TestClient) -> None:
    d = cliente.get(f"{RUTA}/REL-AZOTEA").json()
    assert d["concepto_arenilla"] == {
        "clave": "EJ-830", "descripcion": d["concepto_arenilla"]["descripcion"], "unidad": "m³", "estado": "propuesto", "provisional": True,
    }
    p = d["parametros_por_defecto"]
    assert (p["pendiente_zona_pct"], p["espesor_bajada_m"], p["mortero_espesor_m"], p["factor_abundamiento"]) == (2.0, 0.05, 0.05, 1.0)
    assert {x["clave"] for x in d["pendientes"]} >= {"R8", "R9", "R10", "R11", "R12"}
    assert cliente.get(f"{RUTA}/REL-COMPACTADO").json()["concepto_arenilla"] is None


def test_el_calculo_suelto_del_compactado_mide_el_volumen_por_el_factor_de_abundamiento(cliente: TestClient) -> None:
    d = cliente.post(f"{RUTA}/REL-COMPACTADO/calcular", json={"poligonos": [{"area_m2": 50}], "espesor_m": 0.2, "factor_abundamiento": 1.3}).json()
    assert d["volumen_m3"] == pytest.approx(10.0) and d["conceptos"][0]["cantidad"] == pytest.approx(13.0) and d["parametros"]["abundamiento_pct"] == pytest.approx(30.0)
    assert cliente.post(f"{RUTA}/REL-COMPACTADO/calcular", json={"factor_abundamiento": 0.5}).status_code == 422
    assert cliente.post(f"{RUTA}/REL-AZOTEA/calcular", json={"poligonos": [{"area_m2": 1}], "factor_abundamiento": 1.2}).status_code == 422


def test_la_ficha_del_relleno_de_azotea_se_liga_a_un_concepto_del_catalogo(cliente: TestClient) -> None:
    r = cliente.get(f"{RUTA}/REL-AZOTEA")
    assert r.status_code == 200
    d = r.json()
    assert d["nombre"] == "Relleno de azotea" and d["tipo"] == "azotea" and d["categoria"]["clave"] == "rellenos"
    assert d["concepto"] == {
        "clave": "ALB-03014", "descripcion": d["concepto"]["descripcion"], "unidad": "m²", "estado": "catalogo", "provisional": False,
    }
    assert d["parametros_por_defecto"]["espesor_m"] == 0.09 and d["parametros_por_defecto"]["abundamiento_pct"] == 0.0
    assert d["tezontle"]["clave"] == "PET-00069" and d["mortero"]["por_m2"] == 0.0735
    assert {p["clave"] for p in d["pendientes"]} >= {"R1", "R2", "R3"}


def test_la_ficha_del_compactado_trae_un_concepto_propuesto_de_clave_provisional(cliente: TestClient) -> None:
    d = cliente.get(f"{RUTA}/REL-COMPACTADO").json()
    assert d["concepto"]["clave"] == "EJ-810" and d["concepto"]["estado"] == "propuesto" and d["concepto"]["provisional"] is True
    assert d["tezontle"] is None and d["destajos_candidatos"] == []
    assert cliente.get(f"{RUTA}/LOSA-MACIZA").status_code == 404


def test_el_calculo_suelto_mide_los_poligonos_con_su_subzona(cliente: TestClient) -> None:
    r = cliente.post(
        f"{RUTA}/REL-AZOTEA/calcular",
        json={"poligonos": [{"area_m2": 24, "espacio_id": "rec"}, {"area_m2": 8, "espesor_de_losa_m": 0.2, "espacio_id": "ban"}]},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["area_m2"] == pytest.approx(32.0) and d["volumen_m3"] == pytest.approx(24 * 0.17 + 8 * 0.09)
    assert [p["compensacion_m"] for p in d["poligonos"]] == [pytest.approx(0.08), 0.0]
    assert d["conceptos"][0]["concepto"]["clave"] == "ALB-03014" and d["conceptos"][0]["cantidad"] == pytest.approx(32.0)
    assert {g["espacio_id"] for g in d["por_espacio"]} == {"rec", "ban"} and all(c["resolucion"] is None for g in d["por_espacio"] for c in g["conceptos"])
    assert [i["parte"] for i in d["insumos"]] == ["tezontle", "mortero"]


def test_el_calculo_suelto_acepta_parametros_y_el_compactado_da_el_volumen_suelto(cliente: TestClient) -> None:
    r = cliente.post(
        f"{RUTA}/REL-COMPACTADO/calcular",
        json={"poligonos": [{"area_m2": 50}], "espesor_m": 0.2, "pendiente_pct": 2, "recorrido_m": 4, "abundamiento_pct": 20},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["espesor_medio_m"] == pytest.approx(0.2 + 0.04) and d["volumen_m3"] == pytest.approx(12.0) and d["volumen_suelto_m3"] == pytest.approx(14.4)
    assert d["conceptos"][0]["concepto"]["provisional"] is True and d["conceptos"][0]["unidad"] == "m³"


def test_un_dato_que_no_vale_es_422_y_una_clave_que_no_existe_404(cliente: TestClient) -> None:
    for mal in ({"espesor_m": -1}, {"pendiente_pct": 99}, {"poligonos": [{"area_m2": -3}]}, {"espesor_de_la_zona_m": 0}):
        assert cliente.post(f"{RUTA}/REL-AZOTEA/calcular", json=mal).status_code == 422, mal
    # Un valor que la API acepta pero el dominio rechaza (abundamiento en la azotea) también es 422.
    r = cliente.post(f"{RUTA}/REL-AZOTEA/calcular", json={"poligonos": [{"area_m2": 1}], "abundamiento_pct": 10})
    assert r.status_code == 422 and "abundamiento" in r.text
    assert cliente.post(f"{RUTA}/REL-OTRO/calcular", json={}).status_code == 404
