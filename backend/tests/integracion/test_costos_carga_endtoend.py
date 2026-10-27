"""Costos también sube la ingeniería (migración 0083; cerebro D-581).

Por HTTP contra Postgres real: Costos puede subir `ingenieria_lote` —pasa el guardia de rol— y
nada más; el residente sigue sin poder subir. (La lectura del Excel y su aplicación están
cubiertas en `test_ingenieria_lote_endtoend.py`; el alcance de las políticas, en la prueba SQL.)
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
async def costos(escenario: Escenario) -> AsyncIterator[httpx.AsyncClient]:
    engine = create_async_engine(DATABASE_URL_ADMIN)
    usuario = uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "insert into usuario (id, org_id, nombre, email, rol) "
                "values (:i, :o, 'Costos Test', :e, 'costos')"
            ),
            {"i": str(usuario), "o": str(escenario.org_id), "e": f"cos-{usuario.hex[:8]}@test.mx"},
        )
    await engine.dispose()
    async with _cliente(ContextoSesion(org_id=escenario.org_id, usuario_id=usuario, rol="costos")) as c:
        yield c


@pytest.fixture
async def residente(contexto_residente: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_residente) as c:
        yield c


def _archivo() -> dict:
    return {"archivo": ("x.xlsx", b"no es un xlsx", "application/octet-stream")}


async def test_costos_solo_sube_la_ingenieria(
    escenario: Escenario, costos: httpx.AsyncClient, residente: httpx.AsyncClient
) -> None:
    for tipo in ("catalogo_conceptos", "programa_base", "obras"):
        r = await costos.post("/api/v1/cargas", data={"tipo": tipo}, files=_archivo())
        assert r.status_code == 403, (tipo, r.text)
    # Ingeniería: pasa el guardia (el archivo de mentira se rechaza después, por su contenido).
    r = await costos.post(
        "/api/v1/cargas",
        data={"tipo": "ingenieria_lote", "obra_id": str(escenario.obra_id)},
        files=_archivo(),
    )
    assert r.status_code == 422, r.text
    # El residente no sube nada.
    r = await residente.post(
        "/api/v1/cargas",
        data={"tipo": "ingenieria_lote", "obra_id": str(escenario.obra_id)},
        files=_archivo(),
    )
    assert r.status_code == 403, r.text
