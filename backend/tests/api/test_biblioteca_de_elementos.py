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
    cats = {c["clave"]: c for c in r.json()}
    cat, cim = cats["contencion"], cats["muros_cimentacion"]
    assert cim["nombre"] == "Muros de cimentación"
    assert cim["subcategorias"][0]["nombre"] == "Mampostería de piedra"
    assert cim["subcategorias"][0]["elementos"][0]["clave"] == "CIM-01010"
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
            "/biblioteca-de-elementos/XX-1/calcular", json={"alto_m": 3}
        ).status_code
        == 404
    )


def test_la_biblioteca_trae_tambien_la_familia_de_estructura(cliente: TestClient) -> None:
    """Ola 3B: trabes, contratrabes, nervaduras, la zapata Z-1 y la columna C-1 se suman a la biblioteca sin tocar el muro de piedra."""
    cats = {c["clave"]: c for c in cliente.get("/biblioteca-de-elementos").json()}
    assert {"contencion", "trabes", "contratrabes", "nervaduras", "zapatas", "columnas"} <= set(cats)
    assert len(cats["trabes"]["subcategorias"][0]["elementos"]) == 24
    assert cats["trabes"]["subcategorias"][0]["nombre"] == "Trabes de losa (catálogo)"
    # Su definición no es la del muro: vive en /biblioteca-de-elementos/estructura-lineal/{clave}.
    assert cliente.get("/biblioteca-de-elementos/T-1-15x25").status_code == 404


def test_calcular_el_cimiento_devuelve_el_escarpio_y_el_contraste(
    cliente: TestClient,
) -> None:
    r = cliente.post(
        "/biblioteca-de-elementos/CIM-01010/calcular",
        json={"alto_m": 2.0, "dentellon": True},
    )
    assert r.status_code == 200
    c = r.json()
    assert c["seccion"]["base_m"] == pytest.approx(1.73)
    assert c["volumen"]["dentellon_m3_ml"] == pytest.approx(0.21)
    assert c["escarpio"]["cumple"] is True
    assert c["contraste"]["version_propuesta"]["version"] == 2
    assert (
        cliente.get("/biblioteca-de-elementos/CIM-01010").json()["categoria"]["nombre"]
        == "Muros de cimentación"
    )
    malo = cliente.post(
        "/biblioteca-de-elementos/CIM-01010/calcular", json={"alto_m": 2, "caras": 3}
    )
    assert malo.status_code == 422
    sin_base = cliente.post(
        "/biblioteca-de-elementos/CIM-01010/calcular",
        json={"alto_m": 2, "corona_m": 1.0, "base_m": 0.5},
    )
    assert sin_base.status_code == 422


def test_calcular_el_trazo_de_los_dos_muros(cliente: TestClient) -> None:
    for clave, params in (
        ("MCT-01010", {"dentellon": False}),
        ("CIM-01010", {"caras": 2}),
    ):
        r = cliente.post(
            f"/biblioteca-de-elementos/{clave}/calcular-trazo",
            json={
                "longitud_m": 8,
                "altura_inicial_m": 2.0,
                "pendiente_pct": 5,
                "parametros": params,
            },
        )
        assert r.status_code == 200, r.text
        c = r.json()
        assert c["clave"] == clave
        assert c["altura_final_m"] == pytest.approx(2.4)
        assert c["volumen"]["total_m3"] > 0
        assert len(c["perfil"]) == c["rebanadas"]
    assert (
        cliente.post(
            "/biblioteca-de-elementos/XX-1/calcular-trazo",
            json={"longitud_m": 8, "altura_inicial_m": 2.0},
        ).status_code
        == 404
    )
    assert (
        cliente.post(
            "/biblioteca-de-elementos/MCT-01010/calcular-trazo",
            json={
                "longitud_m": 8,
                "altura_inicial_m": 2.0,
                "parametros": {"lluvia": "media"},
            },
        ).status_code
        == 422
    )
