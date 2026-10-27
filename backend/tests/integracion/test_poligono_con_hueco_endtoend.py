"""Un polígono con hueco descuenta lo que no se mide (cerebro: descuento de
aberturas) — por HTTP contra Postgres real.

Un muro se cuantifica por su área, pero la ventana y la puerta no son muro. El
trazo lleva el hueco como anillo interior (WKT) y PostGIS hace el descuento:
`ST_Area` resta los huecos y `ST_Perimeter` suma su borde. Lo que se fija aquí es
que el servidor lo cumpla de punta a punta, junto con la escala del plano, y que un
hueco mal puesto se rechace con su motivo en vez de medir cero en silencio.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.api.dependencias import contexto_actual
from obractrl.infrastructure.db.sesion import ContextoSesion
from obractrl.main import crear_app
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario

# Un muro de 10 × 4 con una ventana de 2 × 1.
MURO_CON_VENTANA = "POLYGON((0 0, 10 0, 10 4, 0 4, 0 0), (4 1, 6 1, 6 2, 4 2, 4 1))"
# Y con una ventana y una puerta (1 × 2).
MURO_CON_DOS_HUECOS = (
    "POLYGON((0 0, 10 0, 10 4, 0 4, 0 0), (4 1, 6 1, 6 2, 4 2, 4 1), (8 0.5, 9 0.5, 9 2.5, 8 2.5, 8 0.5))"
)


@pytest.fixture
async def residente(contexto_residente: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    app = crear_app()
    app.dependency_overrides[contexto_actual] = lambda: contexto_residente
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as c:
        yield c


@pytest.fixture(autouse=True)
async def _actividad_con_concepto(escenario: Escenario) -> None:
    engine = create_async_engine(DATABASE_URL_ADMIN)
    concepto = uuid.uuid4()
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "insert into concepto (id, org_id, clave, descripcion) "
                    "values (:id, :org, 'HUE-1', 'Muro con vanos')"
                ),
                {"id": str(concepto), "org": str(escenario.org_id)},
            )
            await conn.execute(
                text(
                    "update actividad set concepto_id = :c, precio_unitario = 10, "
                    "cant_base = 100, cant_programada = 100 where id = :id"
                ),
                {"c": str(concepto), "id": str(escenario.actividad_id)},
            )
    finally:
        await engine.dispose()


async def _plano(cliente: httpx.AsyncClient, escenario: Escenario) -> str:
    r = await cliente.post(
        f"/api/v1/obras/{escenario.obra_id}/planos",
        json={"nombre": "Fachada", "archivo_url": "e2e/fachada.pdf"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _trazo(cliente, escenario, plano_id, wkt, medida):
    return cliente.post(
        f"/api/v1/planos/{plano_id}/trazos",
        json={
            "version_plano": 1,
            "fuente": "pdf",
            "geometria_wkt": wkt,
            "enlaces": [
                {"medida": medida, "factor": "1", "actividad_id": str(escenario.actividad_id)}
            ],
        },
    )


async def test_el_area_descuenta_el_hueco_y_el_perimetro_suma_su_borde(
    escenario: Escenario, residente: httpx.AsyncClient
) -> None:
    plano_id = await _plano(residente, escenario)

    area = await _trazo(residente, escenario, plano_id, MURO_CON_VENTANA, "area")
    assert area.status_code == 201, area.text
    assert Decimal(area.json()["recalculos"][0]["cantidad_total"]) == 38  # 40 − 2

    # Otra medida del mismo trazo: el perímetro recorre el exterior y el hueco.
    plano_2 = await _plano(residente, escenario)
    perimetro = await _trazo(residente, escenario, plano_2, MURO_CON_VENTANA, "perimetro")
    assert perimetro.status_code == 201, perimetro.text
    # 38 (área ya sumada) + 28 (exterior) + 6 (ventana) = 72
    assert Decimal(perimetro.json()["recalculos"][0]["cantidad_total"]) == 72


async def test_varios_huecos_se_descuentan_todos(
    escenario: Escenario, residente: httpx.AsyncClient
) -> None:
    plano_id = await _plano(residente, escenario)
    r = await _trazo(residente, escenario, plano_id, MURO_CON_DOS_HUECOS, "area")
    assert r.status_code == 201, r.text
    assert Decimal(r.json()["recalculos"][0]["cantidad_total"]) == 36  # 40 − 2 − 2


async def test_el_descuento_se_escala_con_el_plano(
    escenario: Escenario, residente: httpx.AsyncClient
) -> None:
    plano_id = await _plano(residente, escenario)
    await _trazo(residente, escenario, plano_id, MURO_CON_VENTANA, "area")

    # 10 unidades de plano son 5 metros: cada unidad vale 0.5 m, el área × 0.25.
    cal = await residente.put(
        f"/api/v1/planos/{plano_id}/escala",
        json={"punto_a": [0, 0], "punto_b": [10, 0], "distancia_m": "5"},
    )
    assert cal.status_code == 200, cal.text
    assert Decimal(cal.json()["recalculos"][0]["cantidad_total"]) == Decimal("9.5")  # 38 × .25


async def test_el_trazo_con_hueco_vuelve_como_geojson_con_dos_anillos(
    escenario: Escenario, residente: httpx.AsyncClient
) -> None:
    plano_id = await _plano(residente, escenario)
    await _trazo(residente, escenario, plano_id, MURO_CON_VENTANA, "area")
    trazos = (await residente.get(f"/api/v1/planos/{plano_id}/trazos")).json()
    geometria = trazos["features"][0]["geometry"]
    assert geometria["type"] == "Polygon"
    assert len(geometria["coordinates"]) == 2  # exterior + hueco


async def test_un_hueco_fuera_del_poligono_se_rechaza_con_su_motivo(
    escenario: Escenario, residente: httpx.AsyncClient
) -> None:
    plano_id = await _plano(residente, escenario)
    fuera = "POLYGON((0 0, 10 0, 10 4, 0 4, 0 0), (20 1, 22 1, 22 2, 20 2, 20 1))"
    r = await _trazo(residente, escenario, plano_id, fuera, "area")
    assert r.status_code == 422, r.text
    assert "inválida" in r.text

    # Nada se guardó: el plano sigue sin trazos.
    trazos = (await residente.get(f"/api/v1/planos/{plano_id}/trazos")).json()
    assert trazos["features"] == []


async def test_dos_huecos_que_se_traslapan_se_rechazan(
    escenario: Escenario, residente: httpx.AsyncClient
) -> None:
    plano_id = await _plano(residente, escenario)
    traslapados = (
        "POLYGON((0 0, 10 0, 10 4, 0 4, 0 0), (2 1, 6 1, 6 3, 2 3, 2 1), (4 1.5, 8 1.5, 8 3.5, 4 3.5, 4 1.5))"
    )
    r = await _trazo(residente, escenario, plano_id, traslapados, "area")
    assert r.status_code == 422, r.text
