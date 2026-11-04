"""Elementos paramétricos del catálogo (`/elementos-parametricos`), por HTTP contra Postgres real."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from obractrl.adapters.api.dependencias import contexto_actual
from obractrl.infrastructure.db.sesion import ContextoSesion
from obractrl.main import crear_app


def _cliente(contexto: ContextoSesion) -> httpx.AsyncClient:
    app = crear_app()
    app.dependency_overrides[contexto_actual] = lambda: contexto
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    )


@pytest.fixture
async def control(contexto_control: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_control) as c:
        yield c


@pytest.fixture
async def residente(contexto_residente: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_residente) as c:
        yield c


async def test_se_define_un_castillo_y_su_receta_sale_del_servidor(control: httpx.AsyncClient) -> None:
    r = await control.post(
        "/api/v1/elementos-parametricos", json={"clave": "k-1", "nombre": "Castillo K-1", "tipo": "castillo"}
    )
    assert r.status_code == 201, r.text
    elemento = r.json()["id"]

    lista = (await control.get("/api/v1/elementos-parametricos")).json()
    k1 = next(e for e in lista if e["id"] == elemento)
    assert k1["clave"] == "K-1" and k1["tipo"] == "castillo"
    assert k1["parametros"]["alto"] == 2.6  # lo que no se dijo toma el valor por defecto
    assert k1["receta"]["concreto"] == pytest.approx(0.0585)

    # Cambiar solo la altura conserva el resto del armado y rehace la receta.
    assert (await control.patch(f"/api/v1/elementos-parametricos/{elemento}", json={"parametros": {"alto": 3.0}})).status_code == 204
    k1 = next(e for e in (await control.get("/api/v1/elementos-parametricos")).json() if e["id"] == elemento)
    assert k1["parametros"]["n_var"] == 4
    assert k1["receta"]["concreto"] == pytest.approx(0.15 * 0.15 * 3.0)

    assert (await control.delete(f"/api/v1/elementos-parametricos/{elemento}")).status_code == 204
    assert (await control.delete(f"/api/v1/elementos-parametricos/{elemento}")).status_code == 404


async def test_validaciones_y_roles(control: httpx.AsyncClient, residente: httpx.AsyncClient) -> None:
    cuerpo = {"clave": "TR-1", "nombre": "Trabe", "tipo": "lineal"}
    assert (await residente.post("/api/v1/elementos-parametricos", json=cuerpo)).status_code == 403
    assert (await control.post("/api/v1/elementos-parametricos", json=cuerpo)).status_code == 201
    assert (await control.post("/api/v1/elementos-parametricos", json={**cuerpo, "clave": "tr-1"})).status_code == 422
    assert (
        await control.post(
            "/api/v1/elementos-parametricos", json={**cuerpo, "clave": "TR-2", "parametros": {"no_sup": 7}}
        )
    ).status_code == 422
    # Lo puede ver cualquiera de la organización.
    assert (await residente.get("/api/v1/elementos-parametricos")).status_code == 200
    tipos = (await residente.get("/api/v1/elementos-parametricos/tipos")).json()
    assert {t["tipo"]: t["unidad"] for t in tipos} == {"castillo": "pza", "lineal": "ml", "zapata": "pza", "losa": "m²"}
