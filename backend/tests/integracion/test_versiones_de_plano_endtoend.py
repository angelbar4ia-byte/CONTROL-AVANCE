"""Empalme de versiones del plano (Fase 2): traer un trazo de la versión anterior a la nueva.

Por HTTP contra Postgres real:

 1. el trazo se repite en la versión nueva, corrido, con sus huecos y su enlace;
 2. el enlace del viejo deja de ser vigente y lo medido no se cuenta dos veces;
 3. solo va de una versión anterior a una más nueva, y solo entre versiones del mismo plano.
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

CUADRO = "POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))"
HUECO = "POLYGON((2 2, 4 2, 4 4, 2 4, 2 2))"


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


async def _plano(control: httpx.AsyncClient, escenario: Escenario, nombre: str, version: int) -> str:
    r = await control.post(
        f"/api/v1/obras/{escenario.obra_id}/planos",
        json={"nombre": nombre, "archivo_url": f"r2://{nombre}-{version}", "version": version},
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


async def _cantidad(control: httpx.AsyncClient, escenario: Escenario) -> Decimal:
    nodos = (await control.get(f"/api/v1/obras/{escenario.obra_id}/cuantificacion")).json()
    fila = next((n for n in nodos if n["nodo_id"] == str(escenario.actividad_id)), None)
    return Decimal(str(fila["cantidad_medida"])) if fila else Decimal(0)


async def _trazo_con_hueco(control: httpx.AsyncClient, escenario: Escenario, plano: str, version: int) -> str:
    r = await control.post(
        f"/api/v1/planos/{plano}/trazos",
        json={
            "version_plano": version,
            "geometria_wkt": CUADRO,
            "fuente": "pdf",
            "enlaces": [{"actividad_id": str(escenario.actividad_id), "medida": "area", "factor": "1"}],
        },
    )
    assert r.status_code == 201, r.text
    trazo = str(r.json()["trazo_id"])
    h = await control.post(f"/api/v1/trazos/{trazo}/huecos", json={"geometria_wkt": HUECO})
    assert h.status_code == 201, h.text
    return trazo


async def test_el_trazo_pasa_a_la_version_nueva_sin_contarse_dos_veces(
    escenario: Escenario, control: httpx.AsyncClient
) -> None:
    nombre = f"A-{uuid.uuid4().hex[:5]}"
    v1 = await _plano(control, escenario, nombre, 1)
    v2 = await _plano(control, escenario, nombre, 2)
    trazo = await _trazo_con_hueco(control, escenario, v1, 1)
    assert await _cantidad(control, escenario) == Decimal("96")  # 100 − 4 del hueco

    r = await control.post(
        f"/api/v1/trazos/{trazo}/traer", json={"plano_destino_id": v2, "dx": "5", "dy": "0"}
    )
    assert r.status_code == 201, r.text
    cuerpo = r.json()
    assert cuerpo["huecos"] == 1
    assert len(cuerpo["enlace_ids"]) == 1

    # Lo medido es lo mismo: el enlace del viejo dejó de contar y el nuevo ocupa su lugar.
    assert await _cantidad(control, escenario) == Decimal("96")

    en_v2 = (await control.get(f"/api/v1/planos/{v2}/trazos")).json()["features"]
    assert [f["id"] for f in en_v2] == [cuerpo["trazo_id"]]
    anillo = en_v2[0]["geometry"]["coordinates"][0]  # el exterior; el hueco va en el segundo anillo
    xs = [p[0] for p in anillo]
    assert min(xs) == 5 and max(xs) == 15  # corrido 5 en X
    # El viejo sigue en la versión anterior, como evidencia.
    en_v1 = (await control.get(f"/api/v1/planos/{v1}/trazos")).json()["features"]
    assert [f["id"] for f in en_v1] == [trazo]


async def test_no_se_trae_de_la_nueva_a_la_anterior_ni_entre_planos_distintos(
    escenario: Escenario, control: httpx.AsyncClient
) -> None:
    nombre = f"B-{uuid.uuid4().hex[:5]}"
    v1 = await _plano(control, escenario, nombre, 1)
    v2 = await _plano(control, escenario, nombre, 2)
    otro = await _plano(control, escenario, f"C-{uuid.uuid4().hex[:5]}", 2)
    en_v2 = await _trazo_con_hueco(control, escenario, v2, 2)

    al_reves = await control.post(f"/api/v1/trazos/{en_v2}/traer", json={"plano_destino_id": v1})
    assert al_reves.status_code == 422, al_reves.text
    entre_distintos = await control.post(f"/api/v1/trazos/{en_v2}/traer", json={"plano_destino_id": otro})
    assert entre_distintos.status_code == 422, entre_distintos.text
    assert (await control.post(f"/api/v1/trazos/{uuid.uuid4()}/traer", json={"plano_destino_id": v2})).status_code == 404
