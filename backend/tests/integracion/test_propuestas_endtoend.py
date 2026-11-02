"""Propuestas por revisar (migración 0092): una herramienta automática propone, una persona acepta.

La regla central: **una propuesta nunca cuenta como medida**. Por HTTP contra Postgres real:

 1. proponer no cambia la cantidad medida del concepto;
 2. aceptar crea el enlace y la cantidad sube; el trazo conserva su origen automático;
 3. rechazar borra la propuesta sin haber sumado nada;
 4. la base misma impide un enlace vigente sobre una propuesta pendiente;
 5. la medida debe ir con la geometría, y la actividad ser de la obra del plano.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
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


async def _plano(control: httpx.AsyncClient, escenario: Escenario) -> str:
    r = await control.post(
        f"/api/v1/obras/{escenario.obra_id}/planos", json={"nombre": f"P{uuid.uuid4().hex[:6]}", "archivo_url": "r2://p"}
    )
    return str(r.json()["id"])


async def _cantidad(control: httpx.AsyncClient, escenario: Escenario) -> Decimal:
    nodos = (await control.get(f"/api/v1/obras/{escenario.obra_id}/cuantificacion")).json()
    fila = next((n for n in nodos if n["nodo_id"] == str(escenario.actividad_id)), None)
    return Decimal(str(fila["cantidad_medida"])) if fila else Decimal(0)


def _puntos(n: int) -> list[dict]:
    return [{"wkt": f"POINT({i * 10} 5)", "confianza": "0.9"} for i in range(n)]


async def _proponer(control: httpx.AsyncClient, escenario: Escenario, plano: str, n: int = 3) -> list[str]:
    r = await control.post(
        f"/api/v1/planos/{plano}/propuestas",
        json={
            "actividad_id": str(escenario.actividad_id),
            "medida": "conteo",
            "origen": "conteo_auto",
            "propuestas": _puntos(n),
        },
    )
    assert r.status_code == 201, r.text
    return [str(i) for i in r.json()["trazo_ids"]]


async def test_proponer_no_suma_y_aceptar_si(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano = await _plano(control, escenario)
    antes = await _cantidad(control, escenario)
    ids = await _proponer(control, escenario, plano, 3)
    assert await _cantidad(control, escenario) == antes  # no cuenta como medida

    trazos = (await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"]
    assert {f["id"] for f in trazos} == set(ids)
    assert all(f["properties"]["propuesta"] and f["properties"]["nodo_ids"] == [] for f in trazos)
    assert trazos[0]["properties"]["propuesta_origen"] == "conteo_auto"

    r = await control.post(f"/api/v1/planos/{plano}/propuestas/aceptar", json={"trazo_ids": ids[:2]})
    assert r.status_code == 200, r.text
    assert await _cantidad(control, escenario) == antes + 2  # solo las aceptadas

    despues = {f["id"]: f["properties"] for f in (await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"]}
    assert [despues[i]["propuesta"] for i in ids] == [False, False, True]
    assert despues[ids[0]]["propuesta_origen"] == "conteo_auto"  # se conserva el origen
    assert despues[ids[0]]["nodo_ids"] == [str(escenario.actividad_id)]


async def test_rechazar_borra_sin_haber_sumado(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano = await _plano(control, escenario)
    antes = await _cantidad(control, escenario)
    ids = await _proponer(control, escenario, plano, 2)
    r = await control.post(f"/api/v1/planos/{plano}/propuestas/rechazar", json={"trazo_ids": ids})
    assert r.status_code == 200 and r.json()["rechazadas"] == 2
    assert (await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"] == []
    assert await _cantidad(control, escenario) == antes
    # Lo ya rechazado no es una propuesta pendiente.
    assert (await control.post(f"/api/v1/planos/{plano}/propuestas/rechazar", json={"trazo_ids": ids})).status_code == 422


async def test_la_base_impide_un_enlace_sobre_una_propuesta(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano = await _plano(control, escenario)
    [trazo] = await _proponer(control, escenario, plano, 1)
    engine = create_async_engine(DATABASE_URL_ADMIN)
    try:
        with pytest.raises(DBAPIError, match="no puede sumar cantidad"):
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "insert into enlace_cuantificacion (org_id, trazo_id, tipo_nodo, actividad_id, medida, factor) "
                        "values (:o, :t, 'actividad', :a, 'conteo', 1)"
                    ),
                    {"o": str(escenario.org_id), "t": trazo, "a": str(escenario.actividad_id)},
                )
    finally:
        await engine.dispose()


async def test_validaciones(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano = await _plano(control, escenario)
    url = f"/api/v1/planos/{plano}/propuestas"
    base = {"actividad_id": str(escenario.actividad_id), "medida": "conteo", "origen": "conteo_auto", "propuestas": _puntos(1)}

    assert (await control.post(url, json={**base, "medida": "area"})).status_code == 422  # un punto no da área
    assert (await control.post(url, json={**base, "propuestas": [{"wkt": "POINT(nada)"}]})).status_code == 422  # todo inválido
    assert (await control.post(url, json={**base, "actividad_id": str(uuid.uuid4())})).status_code == 422
    assert (await control.post(f"/api/v1/planos/{uuid.uuid4()}/propuestas", json=base)).status_code == 404
    area = {**base, "medida": "area", "origen": "takeoff", "propuestas": [{"wkt": "POLYGON((0 0,10 0,10 10,0 10,0 0))"}]}
    assert (await control.post(url, json=area)).status_code == 201


async def test_una_geometria_mala_no_pierde_el_lote(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano = await _plano(control, escenario)
    r = await control.post(
        f"/api/v1/planos/{plano}/propuestas",
        json={
            "actividad_id": str(escenario.actividad_id),
            "medida": "area",
            "origen": "takeoff",
            "propuestas": [
                {"wkt": "POLYGON((0 0,10 0,10 10,0 10,0 0))"},
                {"wkt": "POLYGON((0 0,10 10,10 0,0 10,0 0))"},  # corbata: se cruza a sí misma
            ],
        },
    )
    assert r.status_code == 201, r.text
    assert len(r.json()["trazo_ids"]) == 1 and r.json()["descartadas"] == 1
