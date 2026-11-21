"""La ficha y el cálculo suelto de la escalera por HTTP (Fase 4a), sin base de datos: no piden sesión ni token."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from obractrl.adapters.api.v1.escaleras import router

RUTA = "/biblioteca-de-elementos/escalera"


@pytest.fixture
def cliente() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_la_ficha_liga_la_escalera_a_un_concepto_del_catalogo_y_propone_el_del_descanso(cliente: TestClient) -> None:
    r = cliente.get(f"{RUTA}/ESC-FORJADA")
    assert r.status_code == 200
    d = r.json()
    assert d["nombre"] == "Escalera forjada" and d["categoria"]["clave"] == "escaleras"
    assert (d["concepto"]["clave"], d["concepto"]["unidad"], d["concepto"]["estado"], d["concepto"]["provisional"]) == ("EST-01510", "pza", "catalogo", False)
    assert (d["concepto_del_descanso"]["clave"], d["concepto_del_descanso"]["estado"], d["concepto_del_descanso"]["provisional"]) == ("EJ-820", "propuesto", True)
    assert d["parametros_por_defecto"]["contrahuella_max_m"] == 0.18 and d["parametros_por_defecto"]["peldanos"] is None
    assert [i["clave"] for i in d["composicion_del_escalon"]][:2] == ["CON-00004", "ACE-00001"] and d["largo_base_del_escalon_m"] == 1.2
    assert [x["clave"] for x in d["destajos_candidatos"]] == ["MOE-02311", "MOE-02312"]
    assert cliente.get(f"{RUTA}/REL-AZOTEA").status_code == 404


def test_el_calculo_suelto_saca_los_peldanos_del_desnivel(cliente: TestClient) -> None:
    r = cliente.post(f"{RUTA}/ESC-FORJADA/calcular", json={"cota_arranque_m": 0, "cota_llegada_m": 3.12})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["cotas"]["desnivel_m"] == pytest.approx(3.12) and d["geometria"]["peldanos"] == 18
    assert d["conceptos"][0]["concepto"]["clave"] == "EST-01510" and d["conceptos"][0]["cantidad"] == pytest.approx(18.0)
    assert all(c["resolucion"] is None for g in d["por_espacio"] for c in g["conceptos"])


def test_con_dos_rampas_aparece_el_descanso_y_la_linea_da_la_huella(cliente: TestClient) -> None:
    r = cliente.post(f"{RUTA}/ESC-FORJADA/calcular", json={"cota_llegada_m": 3.12, "rampas": 2, "recorrido_m": 4.0, "espacio_id": "esc"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["geometria"]["huella_m"] == pytest.approx(0.25) and d["geometria"]["origen_de_huella"] == "linea"
    assert [c["concepto"]["clave"] for c in d["conceptos"]] == ["EST-01510", "EJ-820"]
    assert d["por_espacio"][0]["espacio_id"] == "esc" and d["geometria"]["descansos"] == 1


def test_un_dato_que_no_vale_es_422_y_una_clave_que_no_existe_404(cliente: TestClient) -> None:
    for mal in ({"ancho_m": 0.1}, {"rampas": 9}, {"peldanos": 1}, {"cota_arranque_m": 500}):
        assert cliente.post(f"{RUTA}/ESC-FORJADA/calcular", json=mal).status_code == 422, mal
    # Un valor que la API acepta pero el dominio rechaza (la llegada no sube) también es 422.
    r = cliente.post(f"{RUTA}/ESC-FORJADA/calcular", json={"cota_arranque_m": 3, "cota_llegada_m": 2})
    assert r.status_code == 422 and "sube" in r.text
    assert cliente.post(f"{RUTA}/ESC-OTRA/calcular", json={}).status_code == 404
