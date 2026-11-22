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


def test_el_calculo_suelto_acepta_descansos_propios_y_escalones_de_abanico(cliente: TestClient) -> None:
    cuerpo = {
        "cota_llegada_m": 3.12, "rampas": 2,
        "descansos": [{"posicion": 1, "giro_grados": 180, "largo_m": 1.2, "ancho_m": 2.4, "espesor_m": 0.15}],
        "abanicos": [{"posicion": 1, "escalones": 3, "ancho_interior_m": 0.15, "ancho_exterior_m": 0.75}],
    }
    r = cliente.post(f"{RUTA}/ESC-FORJADA/calcular", json=cuerpo)
    assert r.status_code == 200, r.text
    g = r.json()["geometria"]
    assert (g["peldanos"], g["peldanos_rectos"], g["peldanos_de_abanico"]) == (18, 15, 3) and g["escalones_de_catalogo"] == pytest.approx(20.4)
    assert g["descansos_detalle"][0]["origen"] == "dimensiones" and g["descansos_detalle"][0]["area_m2"] == pytest.approx(2.88)
    assert g["abanicos"][0]["radio_huella_m"] == 0.35 and g["abanicos"][0]["huella_en_la_linea_m"] == pytest.approx(0.325)
    assert {i["parte"] for i in r.json()["insumos"]} == {"rampa", "abanico", "descanso"}
    # Sin ellos, el cálculo es el de siempre.
    base = cliente.post(f"{RUTA}/ESC-FORJADA/calcular", json={"cota_llegada_m": 3.12, "rampas": 2}).json()["geometria"]
    assert base["descansos_detalle"][0]["origen"] == "implicito" and base["abanicos"] == [] and base["escalones_de_catalogo"] == pytest.approx(18.0)


def test_un_descanso_o_un_abanico_que_no_valen_son_422(cliente: TestClient) -> None:
    for mal in (
        {"descansos": [{"posicion": 4}]}, {"descansos": [{"posicion": 1, "giro_grados": 45}]}, {"descansos": [{"posicion": 1, "largo_m": 9}]},
        {"abanicos": [{"posicion": 1, "escalones": 0, "ancho_interior_m": 0.1, "ancho_exterior_m": 0.3}]},
        {"abanicos": [{"posicion": 1, "escalones": 3, "ancho_interior_m": 0.1}]},
    ):
        assert cliente.post(f"{RUTA}/ESC-FORJADA/calcular", json=mal).status_code == 422, mal
    # Valores que el contrato acepta pero el dominio rechaza también son 422, con su motivo.
    r = cliente.post(f"{RUTA}/ESC-FORJADA/calcular", json={"rampas": 2, "descansos": [{"posicion": 2}]})
    assert r.status_code == 422 and "tiene 2 rampas" in r.text
    r = cliente.post(f"{RUTA}/ESC-FORJADA/calcular", json={"abanicos": [{"posicion": 0, "escalones": 3, "ancho_interior_m": 0.4, "ancho_exterior_m": 0.2}]})
    assert r.status_code == 422
    r = cliente.post(f"{RUTA}/ESC-FORJADA/calcular", json={"rampas": 4, "abanicos": [{"posicion": 1, "escalones": 12, "ancho_interior_m": 0.15, "ancho_exterior_m": 0.75}]})
    assert r.status_code == 422 and "no caben" in r.text
