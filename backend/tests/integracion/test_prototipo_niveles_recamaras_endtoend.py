"""Niveles (= plantas) y recámaras de un prototipo, editables por HTTP.

`PATCH /prototipos/{id}` toca solo lo que viene; `niveles` se guarda también
como `plantas` (son el mismo dato, 1 o 2). Los prototipos de un catálogo de
presupuesto nacen sin proyecto, niveles ni recámaras (D-614), y esta es la
forma de llenarlos.
"""

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
async def cliente_control(contexto_control: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_control) as cliente:
        yield cliente


@pytest.fixture
async def cliente_residente(contexto_residente: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_residente) as cliente:
        yield cliente


async def _prototipo_sin_proyecto(escenario: Escenario) -> str:
    """Como los deja el catálogo de presupuesto: sin proyecto, niveles ni recámaras."""
    assert DATABASE_URL_ADMIN is not None
    motor = create_async_engine(DATABASE_URL_ADMIN)
    prototipo = str(uuid.uuid4())
    try:
        async with motor.begin() as conn:
            await conn.execute(
                text(
                    "insert into prototipo (id, org_id, clave, nombre, m2) "
                    "values (:i, :o, 'CAS-NR1', 'Zafiro 1.0', 172)"
                ),
                {"i": prototipo, "o": str(escenario.org_id)},
            )
    finally:
        await motor.dispose()
    return prototipo


async def _fila(prototipo: str) -> dict:
    assert DATABASE_URL_ADMIN is not None
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.connect() as conn:
            r = await conn.execute(
                text("select niveles, plantas, recamaras, m2, nombre from prototipo where id = :i"),
                {"i": prototipo},
            )
            return dict(r.mappings().one())
    finally:
        await motor.dispose()


async def test_los_niveles_son_las_plantas_y_se_guardan_juntos(
    escenario: Escenario, cliente_control: httpx.AsyncClient
) -> None:
    prototipo = await _prototipo_sin_proyecto(escenario)
    r = await cliente_control.patch(f"/api/v1/prototipos/{prototipo}", json={"niveles": 2, "recamaras": 3})
    assert r.status_code == 204, r.text
    fila = await _fila(prototipo)
    assert (fila["niveles"], fila["plantas"], fila["recamaras"]) == (2, 2, 3)
    assert (fila["nombre"], int(fila["m2"])) == ("Zafiro 1.0", 172)


async def test_solo_cambia_lo_que_viene(
    escenario: Escenario, cliente_control: httpx.AsyncClient
) -> None:
    prototipo = await _prototipo_sin_proyecto(escenario)
    await cliente_control.patch(f"/api/v1/prototipos/{prototipo}", json={"niveles": 1, "recamaras": 2})
    r = await cliente_control.patch(f"/api/v1/prototipos/{prototipo}", json={"recamaras": 4})
    assert r.status_code == 204, r.text
    fila = await _fila(prototipo)
    assert (fila["niveles"], fila["plantas"], fila["recamaras"]) == (1, 1, 4)


async def test_null_deja_el_dato_sin_decir(
    escenario: Escenario, cliente_control: httpx.AsyncClient
) -> None:
    prototipo = await _prototipo_sin_proyecto(escenario)
    await cliente_control.patch(f"/api/v1/prototipos/{prototipo}", json={"niveles": 2, "recamaras": 3})
    r = await cliente_control.patch(f"/api/v1/prototipos/{prototipo}", json={"niveles": None})
    assert r.status_code == 204, r.text
    fila = await _fila(prototipo)
    assert (fila["niveles"], fila["plantas"], fila["recamaras"]) == (None, None, 3)


@pytest.mark.parametrize("cuerpo", [{"niveles": 3}, {"niveles": 0}, {"recamaras": -1}])
async def test_valores_imposibles_se_rechazan_sin_escribir(
    escenario: Escenario, cliente_control: httpx.AsyncClient, cuerpo: dict
) -> None:
    prototipo = await _prototipo_sin_proyecto(escenario)
    r = await cliente_control.patch(f"/api/v1/prototipos/{prototipo}", json=cuerpo)
    assert r.status_code == 422, r.text
    fila = await _fila(prototipo)
    assert (fila["niveles"], fila["plantas"], fila["recamaras"]) == (None, None, None)


async def test_prototipo_inexistente_es_404(cliente_control: httpx.AsyncClient) -> None:
    r = await cliente_control.patch(f"/api/v1/prototipos/{uuid.uuid4()}", json={"niveles": 1})
    assert r.status_code == 404, r.text


async def test_el_residente_no_edita(
    escenario: Escenario, cliente_residente: httpx.AsyncClient
) -> None:
    prototipo = await _prototipo_sin_proyecto(escenario)
    r = await cliente_residente.patch(f"/api/v1/prototipos/{prototipo}", json={"niveles": 2})
    assert r.status_code == 403, r.text
    assert (await _fila(prototipo))["niveles"] is None
