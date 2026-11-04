"""Elementos paramétricos del catálogo (`/elementos-parametricos`), por HTTP contra Postgres real."""

from __future__ import annotations

import uuid
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


async def _plano_con_trazos(cliente: httpx.AsyncClient, escenario) -> tuple[str, dict[str, str]]:
    r = await cliente.post(f"/api/v1/obras/{escenario.obra_id}/planos", json={"nombre": "P", "archivo_url": "e2e/p.pdf"})
    plano = r.json()["id"]
    ids = {}
    for nombre, wkt in (
        ("punto", "POINT(1 1)"),
        ("punto2", "POINT(5 5)"),
        ("linea", "LINESTRING(0 0, 10 0)"),
        ("area", "POLYGON((0 0, 4 0, 4 3, 0 3, 0 0))"),
    ):
        t = await cliente.post(
            f"/api/v1/planos/{plano}/trazos", json={"version_plano": 1, "fuente": "pdf", "geometria_wkt": wkt, "enlaces": []}
        )
        assert t.status_code == 201, t.text
        ids[nombre] = t.json()["trazo_id"]
    return plano, ids


async def test_el_plano_suma_lo_que_llevan_los_elementos_colocados(escenario, control: httpx.AsyncClient) -> None:
    plano, t = await _plano_con_trazos(control, escenario)
    k1 = (await control.post("/api/v1/elementos-parametricos", json={"clave": "K-1", "nombre": "Castillo", "tipo": "castillo"})).json()["id"]
    tr1 = (await control.post("/api/v1/elementos-parametricos", json={"clave": "TR-1", "nombre": "Trabe", "tipo": "lineal"})).json()["id"]
    l1 = (await control.post("/api/v1/elementos-parametricos", json={"clave": "L-1", "nombre": "Losa", "tipo": "losa"})).json()["id"]

    ok = lambda elem, trazo, **extra: control.put(  # noqa: E731
        f"/api/v1/trazos/{trazo}/elemento-parametrico", json={"elemento_id": elem, **extra}
    )
    assert (await ok(k1, t["punto"])).status_code == 204
    assert (await ok(k1, t["punto2"], lados_cimbra=3)).status_code == 204  # junto a un vano
    assert (await ok(tr1, t["linea"])).status_code == 204
    assert (await ok(l1, t["area"])).status_code == 204

    r = (await control.get(f"/api/v1/planos/{plano}/elementos-parametricos")).json()
    por_clave = {x["clave"]: x for x in r["totales"]}
    k = por_clave["K-1"]
    assert (k["colocados"], k["cantidad"]) == (2, 2)
    assert k["concreto_m3"] == pytest.approx(2 * 0.0585)
    # Un castillo aislado lleva 4 lados (1.56 m²); el otro, fijado a 3 junto a un vano (1.17 m²).
    assert k["cimbra_m2"] == pytest.approx(1.56 + 1.17)
    assert k["cimbra_por_lados"] == {"3": pytest.approx(1.17), "4": pytest.approx(1.56)}
    # La trabe: 10 m × (0.2 × 0.4) de concreto; 3 lados = 1.0 m² por metro.
    assert por_clave["TR-1"]["cantidad"] == pytest.approx(10)
    assert por_clave["TR-1"]["concreto_m3"] == pytest.approx(0.8)
    assert por_clave["TR-1"]["cimbra_m2"] == pytest.approx(10.0)
    # La losa: 12 m² × 0.1 m de espesor.
    assert por_clave["L-1"]["cantidad"] == pytest.approx(12)
    assert por_clave["L-1"]["concreto_m3"] == pytest.approx(1.2)
    assert {x["trazo_id"] for x in r["trazos"]} == set(t.values())

    # Quitar la marca la saca de los totales.
    assert (await ok(None, t["punto"])).status_code == 204
    r = (await control.get(f"/api/v1/planos/{plano}/elementos-parametricos")).json()
    assert {x["clave"]: x["colocados"] for x in r["totales"]}["K-1"] == 1


async def test_cada_elemento_se_coloca_con_su_geometria(escenario, control: httpx.AsyncClient, residente: httpx.AsyncClient) -> None:
    _, t = await _plano_con_trazos(control, escenario)
    k1 = (await control.post("/api/v1/elementos-parametricos", json={"clave": "K-1", "nombre": "Castillo", "tipo": "castillo"})).json()["id"]
    poner = lambda cli, elem, trazo, **x: cli.put(  # noqa: E731
        f"/api/v1/trazos/{trazo}/elemento-parametrico", json={"elemento_id": elem, **x}
    )
    assert (await poner(control, k1, t["linea"])).status_code == 422  # un castillo es una pieza: se coloca con un punto
    assert (await poner(control, k1, t["punto"], lados_cimbra=1)).status_code == 422  # el castillo no tiene cimbra de 1 lado
    assert (await poner(control, str(uuid.uuid4()), t["punto"])).status_code == 404
    assert (await poner(control, k1, str(uuid.uuid4()))).status_code == 404
    # El residente traza, así que también puede marcar sus piezas.
    assert (await poner(residente, k1, t["punto"])).status_code == 204
