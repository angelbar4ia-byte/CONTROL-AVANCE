"""Las matrices de un concepto del catálogo (entrega 5b): se ponen, se cambian y se quitan."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.api.dependencias import contexto_actual
from obractrl.infrastructure.db.sesion import ContextoSesion
from obractrl.main import crear_app
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario


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


@pytest.fixture
async def residente(contexto_residente: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_residente) as c:
        yield c


@pytest.fixture
async def catalogo(escenario: Escenario) -> AsyncIterator[dict[str, uuid.UUID]]:
    """Una unidad, un concepto padre ligado a la actividad del escenario y otro suelto."""
    engine = create_async_engine(DATABASE_URL_ADMIN)
    org = str(escenario.org_id)
    unidad, padre, otro = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text("insert into unidad (id, org_id, clave, nombre) values (:i, :o, 'm2', 'Metro cuadrado')"),
            {"i": str(unidad), "o": org},
        )
        for cid, clave in ((padre, "PAD-1"), (otro, "OTR-1")):
            await conn.execute(
                text(
                    "insert into concepto (id, org_id, tipo, clave, descripcion, unidad_id) "
                    "values (:i, :o, 'concepto', :c, :c, :u)"
                ),
                {"i": str(cid), "o": org, "c": clave, "u": str(unidad)},
            )
        await conn.execute(
            text("update actividad set concepto_id = :c where id = :a"),
            {"c": str(padre), "a": str(escenario.actividad_id)},
        )
    yield {"unidad": unidad, "padre": padre, "otro": otro}
    await engine.dispose()


async def _matrices(cliente: httpx.AsyncClient, escenario: Escenario) -> list[dict]:
    r = await cliente.get(f"/api/v1/actividades/{escenario.actividad_id}/matrices")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    return cuerpo["matrices"] if isinstance(cuerpo, dict) else cuerpo


async def test_una_matriz_nueva_nace_y_cuelga_del_concepto(
    escenario: Escenario, catalogo: dict, control: httpx.AsyncClient
) -> None:
    r = await control.post(
        f"/api/v1/conceptos/{catalogo['padre']}/matrices",
        json={
            "cantidad": "0.5",
            "nueva": {"clave": "mat-n1", "descripcion": "Mezcla", "unidad_id": str(catalogo["unidad"])},
        },
    )
    assert r.status_code == 200, r.text
    assert [(m["clave"], float(m["cantidad_catalogo"])) for m in await _matrices(control, escenario)] == [
        ("MAT-N1", 50.0)  # 0.5 por unidad × 100 de la actividad
    ]


async def test_una_existente_se_pone_y_cambiarle_la_cantidad_no_la_duplica(
    escenario: Escenario, catalogo: dict, control: httpx.AsyncClient
) -> None:
    url = f"/api/v1/conceptos/{catalogo['padre']}/matrices"
    for cantidad in ("1", "2.5"):
        r = await control.post(url, json={"cantidad": cantidad, "matriz_id": str(catalogo["otro"])})
        assert r.status_code == 200, r.text
    assert [float(m["cantidad_catalogo"]) for m in await _matrices(control, escenario)] == [250.0]


async def test_un_ciclo_se_rechaza(catalogo: dict, control: httpx.AsyncClient) -> None:
    assert (
        await control.post(
            f"/api/v1/conceptos/{catalogo['padre']}/matrices",
            json={"cantidad": "1", "matriz_id": str(catalogo["otro"])},
        )
    ).status_code == 200
    # Ahora «otro» ya cuelga de «padre»: poner a «padre» bajo «otro» cerraría el ciclo.
    r = await control.post(
        f"/api/v1/conceptos/{catalogo['otro']}/matrices",
        json={"cantidad": "1", "matriz_id": str(catalogo["padre"])},
    )
    assert r.status_code == 422, r.text
    r = await control.post(
        f"/api/v1/conceptos/{catalogo['padre']}/matrices",
        json={"cantidad": "1", "matriz_id": str(catalogo["padre"])},
    )
    assert r.status_code == 422, r.text


async def test_quitar_una_matriz(
    escenario: Escenario, catalogo: dict, control: httpx.AsyncClient
) -> None:
    await control.post(
        f"/api/v1/conceptos/{catalogo['padre']}/matrices",
        json={"cantidad": "1", "matriz_id": str(catalogo["otro"])},
    )
    url = f"/api/v1/conceptos/{catalogo['padre']}/matrices/{catalogo['otro']}"
    assert (await control.delete(url)).status_code == 204
    assert await _matrices(control, escenario) == []
    assert (await control.delete(url)).status_code == 404


async def test_pide_una_cosa_o_la_otra_y_cantidad_positiva(
    catalogo: dict, control: httpx.AsyncClient
) -> None:
    url = f"/api/v1/conceptos/{catalogo['padre']}/matrices"
    assert (await control.post(url, json={"cantidad": "1"})).status_code == 422
    assert (await control.post(url, json={"cantidad": "0", "matriz_id": str(catalogo["otro"])})).status_code == 422


async def test_el_residente_no_cambia_el_catalogo(catalogo: dict, residente: httpx.AsyncClient) -> None:
    r = await residente.post(
        f"/api/v1/conceptos/{catalogo['padre']}/matrices",
        json={"cantidad": "1", "matriz_id": str(catalogo["otro"])},
    )
    assert r.status_code == 403, r.text
