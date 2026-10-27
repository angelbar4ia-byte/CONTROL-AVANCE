"""Huecos sobre un área, línea con grosor y punto con forma (migración 0086).

Por HTTP contra Postgres real:

 1. un hueco abierto sobre un área ya trazada **resta** de lo que mide y recalcula la
    actividad; el trazo no se modifica y el GeoJSON ya trae el hueco;
 2. un hueco que se sale del área, o sobre algo que no es un área, se rechaza;
 3. una línea con grosor mide largo × grosor (un muro), y el grosor sin alineación o sobre
    otra geometría se rechaza;
 4. un polígono estampado con su forma la guarda y la devuelve.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

import httpx
import pytest

from obractrl.adapters.api.dependencias import contexto_actual
from obractrl.infrastructure.db.sesion import ContextoSesion
from obractrl.main import crear_app
from tests.integracion.conftest import Escenario


def _cliente(contexto: ContextoSesion) -> httpx.AsyncClient:
    app = crear_app()
    app.dependency_overrides[contexto_actual] = lambda: contexto
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    )


@pytest.fixture
async def control(contexto_control: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_control) as c:
        yield c


async def _plano(control: httpx.AsyncClient, escenario: Escenario) -> str:
    r = await control.post(
        f"/api/v1/obras/{escenario.obra_id}/planos",
        json={"nombre": f"P{uuid.uuid4().hex[:6]}", "archivo_url": "r2://p"},
    )
    return str(r.json()["id"])


async def _trazo(control, escenario, plano: str, wkt: str, medida: str, **extra) -> httpx.Response:
    return await control.post(
        f"/api/v1/planos/{plano}/trazos",
        json={
            "version_plano": 1,
            "geometria_wkt": wkt,
            "fuente": "pdf",
            "enlaces": [{"actividad_id": str(escenario.actividad_id), "medida": medida, "factor": "1"}],
            **extra,
        },
    )


async def _features(control, plano: str) -> list[dict]:
    r = await control.get(f"/api/v1/planos/{plano}/trazos")
    assert r.status_code == 200, r.text
    return r.json()["features"]


async def test_un_hueco_resta_del_area_y_recalcula(control, escenario: Escenario) -> None:
    plano = await _plano(control, escenario)
    r = await _trazo(control, escenario, plano, "POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))", "area")
    assert r.status_code == 201, r.text
    trazo_id = r.json()["trazo_id"]
    assert Decimal(r.json()["recalculos"][0]["cantidad_total"]) == 100

    h = await control.post(
        f"/api/v1/trazos/{trazo_id}/huecos",
        json={"geometria_wkt": "POLYGON((2 2, 4 2, 4 4, 2 4, 2 2))"},
    )
    assert h.status_code == 201, h.text
    assert Decimal(h.json()["recalculos"][0]["cantidad_total"]) == 96

    feats = await _features(control, plano)
    assert len(feats) == 1  # el hueco no es un trazo más de la lista
    props = feats[0]["properties"]
    assert props["n_huecos"] == 1
    assert Decimal(props["enlaces"][0]["cantidad"]) == 96
    # El GeoJSON ya trae el hueco como anillo interior.
    assert len(feats[0]["geometry"]["coordinates"]) == 2

    # Un segundo hueco se suma al primero.
    h2 = await control.post(
        f"/api/v1/trazos/{trazo_id}/huecos",
        json={"geometria_wkt": "POLYGON((6 6, 8 6, 8 8, 6 8, 6 6))"},
    )
    assert h2.status_code == 201, h2.text
    assert Decimal(h2.json()["recalculos"][0]["cantidad_total"]) == 92


async def test_un_hueco_que_se_sale_o_sobre_una_linea_se_rechaza(control, escenario: Escenario) -> None:
    plano = await _plano(control, escenario)
    area = (await _trazo(control, escenario, plano, "POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))", "area")).json()
    linea = (await _trazo(control, escenario, plano, "LINESTRING(0 0, 5 0)", "longitud")).json()

    fuera = await control.post(
        f"/api/v1/trazos/{area['trazo_id']}/huecos",
        json={"geometria_wkt": "POLYGON((8 8, 12 8, 12 12, 8 12, 8 8))"},
    )
    assert fuera.status_code == 422, fuera.text
    assert "dentro" in fuera.text

    sobre_linea = await control.post(
        f"/api/v1/trazos/{linea['trazo_id']}/huecos",
        json={"geometria_wkt": "POLYGON((1 1, 2 1, 2 2, 1 2, 1 1))"},
    )
    assert sobre_linea.status_code == 422
    assert "área" in sobre_linea.text

    inexistente = await control.post(
        f"/api/v1/trazos/{uuid.uuid4()}/huecos",
        json={"geometria_wkt": "POLYGON((1 1, 2 1, 2 2, 1 2, 1 1))"},
    )
    assert inexistente.status_code == 404


async def test_una_linea_con_grosor_mide_largo_por_grosor(control, escenario: Escenario) -> None:
    plano = await _plano(control, escenario)
    r = await _trazo(
        control, escenario, plano, "LINESTRING(0 0, 10 0)", "area", grosor_m="0.15", alineacion="izquierda"
    )
    assert r.status_code == 201, r.text
    assert Decimal(r.json()["recalculos"][0]["cantidad_total"]) == Decimal("1.5")

    props = (await _features(control, plano))[0]["properties"]
    assert Decimal(props["grosor_m"]) == Decimal("0.15")
    assert props["alineacion"] == "izquierda"

    # La longitud sigue midiendo el eje.
    plano2 = await _plano(control, escenario)
    r2 = await _trazo(
        control, escenario, plano2, "LINESTRING(0 0, 10 0)", "longitud", grosor_m="0.15", alineacion="centro"
    )
    assert r2.status_code == 201, r2.text


async def test_grosor_sin_alineacion_o_en_un_poligono_se_rechaza(control, escenario: Escenario) -> None:
    plano = await _plano(control, escenario)
    sin_alineacion = await _trazo(control, escenario, plano, "LINESTRING(0 0, 10 0)", "area", grosor_m="0.15")
    assert sin_alineacion.status_code == 422

    en_poligono = await _trazo(
        control,
        escenario,
        plano,
        "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        "area",
        grosor_m="0.15",
        alineacion="centro",
    )
    assert en_poligono.status_code == 422
    assert "línea" in en_poligono.text


async def test_un_punto_con_forma_guarda_la_forma(control, escenario: Escenario) -> None:
    plano = await _plano(control, escenario)
    forma = {"tipo": "cuadrado", "ancho_m": "0.15", "alto_m": "0.15", "nombre": "Castillo"}
    r = await _trazo(
        control, escenario, plano, "POLYGON((1 1, 1.15 1, 1.15 1.15, 1 1.15, 1 1))", "conteo", forma=forma
    )
    assert r.status_code == 201, r.text
    assert Decimal(r.json()["recalculos"][0]["cantidad_total"]) == 1

    props = (await _features(control, plano))[0]["properties"]
    assert props["forma"]["tipo"] == "cuadrado"
    assert props["forma"]["nombre"] == "Castillo"

    en_linea = await _trazo(control, escenario, plano, "LINESTRING(0 0, 1 0)", "longitud", forma=forma)
    assert en_linea.status_code == 422


@pytest.fixture
async def residente(contexto_residente: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_residente) as c:
        yield c


async def test_borrar_un_trazo_recalcula_y_el_ultimo_vuelve_a_sin_medir(control, escenario: Escenario) -> None:
    plano = await _plano(control, escenario)
    a = (await _trazo(control, escenario, plano, "POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))", "area")).json()
    b = (await _trazo(control, escenario, plano, "POLYGON((20 0, 25 0, 25 4, 20 4, 20 0))", "area")).json()
    assert Decimal(b["recalculos"][0]["cantidad_total"]) == 120
    await control.post(
        f"/api/v1/trazos/{a['trazo_id']}/huecos", json={"geometria_wkt": "POLYGON((2 2, 4 2, 4 4, 2 4, 2 2))"}
    )

    # Borrar el primero (con su hueco) deja solo lo del segundo.
    r = await control.delete(f"/api/v1/trazos/{a['trazo_id']}")
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["recalculos"][0]["cantidad_total"]) == 20
    assert len(await _features(control, plano)) == 1

    # Y borrar el último vuelve la cantidad a cero sin levantar una desviación.
    r2 = await control.delete(f"/api/v1/trazos/{b['trazo_id']}")
    assert r2.status_code == 200, r2.text
    assert Decimal(r2.json()["recalculos"][0]["cantidad_total"]) == 0
    assert r2.json()["recalculos"][0]["desviacion_id"] is None
    assert await _features(control, plano) == []

    # Ya no existe.
    assert (await control.delete(f"/api/v1/trazos/{b['trazo_id']}")).status_code == 404


async def test_quien_borra_un_trazo(control, residente, escenario: Escenario) -> None:
    plano = await _plano(control, escenario)
    del_control = (await _trazo(control, escenario, plano, "LINESTRING(0 0, 5 0)", "longitud")).json()
    # El residente traza el suyo sobre el mismo plano.
    mio = await residente.post(
        f"/api/v1/planos/{plano}/trazos",
        json={
            "version_plano": 1,
            "geometria_wkt": "LINESTRING(0 1, 5 1)",
            "fuente": "pdf",
            "enlaces": [{"actividad_id": str(escenario.actividad_id), "medida": "longitud", "factor": "1"}],
        },
    )
    assert mio.status_code == 201, mio.text

    # Lo de Control no es suyo: 403. Lo suyo sin aprobar sí.
    assert (await residente.delete(f"/api/v1/trazos/{del_control['trazo_id']}")).status_code == 403
    assert (await residente.delete(f"/api/v1/trazos/{mio.json()['trazo_id']}")).status_code == 200

    # Control aprueba el suyo; ya aprobado, solo Control o Super intendente lo borran.
    assert (await control.post(f"/api/v1/trazos/{del_control['trazo_id']}/aprobar")).status_code == 200
    assert (await control.delete(f"/api/v1/trazos/{del_control['trazo_id']}")).status_code == 200
