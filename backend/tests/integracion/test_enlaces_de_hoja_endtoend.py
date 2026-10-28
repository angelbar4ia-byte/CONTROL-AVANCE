"""Enlaces entre hojas (Fase 2, migración 0091): una zona del plano que lleva a otra hoja de la obra."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

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


@pytest.fixture
async def ajeno(contexto_ajeno: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_ajeno) as c:
        yield c


async def _plano(control: httpx.AsyncClient, escenario: Escenario, nombre: str) -> str:
    r = await control.post(
        f"/api/v1/obras/{escenario.obra_id}/planos", json={"nombre": nombre, "archivo_url": f"r2://{nombre}"}
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def _zona(destino: str, **extra: object) -> dict:
    return {"destino_plano_id": destino, "etiqueta": "Ver corte A-A", "x": 10, "y": 20, "ancho": 50, "alto": 30, **extra}


async def test_se_marca_una_zona_se_lista_y_se_quita(escenario: Escenario, control: httpx.AsyncClient) -> None:
    planta = await _plano(control, escenario, f"Planta-{uuid.uuid4().hex[:5]}")
    corte = await _plano(control, escenario, f"Corte-{uuid.uuid4().hex[:5]}")

    r = await control.post(f"/api/v1/planos/{planta}/enlaces", json=_zona(corte))
    assert r.status_code == 201, r.text
    enlace = r.json()["id"]

    lista = (await control.get(f"/api/v1/planos/{planta}/enlaces")).json()
    assert [(e["id"], e["destino_plano_id"], e["etiqueta"]) for e in lista] == [(enlace, corte, "Ver corte A-A")]
    assert lista[0]["destino_nombre"].startswith("Corte-")
    assert (await control.get(f"/api/v1/planos/{corte}/enlaces")).json() == []  # el enlace es de ida

    assert (await control.delete(f"/api/v1/enlaces-de-hoja/{enlace}")).status_code == 204
    assert (await control.get(f"/api/v1/planos/{planta}/enlaces")).json() == []
    assert (await control.delete(f"/api/v1/enlaces-de-hoja/{enlace}")).status_code == 404


async def test_validaciones(escenario: Escenario, control: httpx.AsyncClient) -> None:
    planta = await _plano(control, escenario, f"P-{uuid.uuid4().hex[:5]}")
    otra = await _plano(control, escenario, f"O-{uuid.uuid4().hex[:5]}")
    url = f"/api/v1/planos/{planta}/enlaces"

    assert (await control.post(url, json=_zona(planta))).status_code == 422  # a sí misma
    assert (await control.post(url, json=_zona(otra, etiqueta="  "))).status_code == 422
    assert (await control.post(url, json=_zona(otra, ancho=0))).status_code == 422
    assert (await control.post(url, json=_zona(str(uuid.uuid4())))).status_code == 404  # destino que no existe
    assert (await control.post(f"/api/v1/planos/{uuid.uuid4()}/enlaces", json=_zona(otra))).status_code == 404


async def test_otra_organizacion_no_ve_ni_enlaza(
    escenario: Escenario, control: httpx.AsyncClient, ajeno: httpx.AsyncClient
) -> None:
    a = await _plano(control, escenario, f"A-{uuid.uuid4().hex[:5]}")
    b = await _plano(control, escenario, f"B-{uuid.uuid4().hex[:5]}")
    assert (await control.post(f"/api/v1/planos/{a}/enlaces", json=_zona(b))).status_code == 201
    assert (await ajeno.get(f"/api/v1/planos/{a}/enlaces")).status_code == 404
    assert (await ajeno.post(f"/api/v1/planos/{a}/enlaces", json=_zona(b))).status_code in (403, 404)
