"""Un concepto que nace desde el cuantificador (entrega 5): alta en el catálogo + renglón en la obra."""

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
async def costos(escenario: Escenario) -> AsyncIterator[httpx.AsyncClient]:
    usuario = uuid.uuid4()
    engine = create_async_engine(DATABASE_URL_ADMIN)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "insert into usuario (id, org_id, nombre, email, rol) "
                "values (:i, :o, 'Costos Test', :e, 'costos')"
            ),
            {"i": str(usuario), "o": str(escenario.org_id), "e": f"cos-{usuario.hex[:8]}@test.mx"},
        )
    await engine.dispose()
    contexto = ContextoSesion(org_id=escenario.org_id, usuario_id=usuario, rol="costos")
    async with _cliente(contexto) as c:
        yield c


@pytest.fixture
async def unidad(escenario: Escenario) -> AsyncIterator[uuid.UUID]:
    engine = create_async_engine(DATABASE_URL_ADMIN)
    unidad_id = uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text("insert into unidad (id, org_id, clave, nombre) values (:i, :o, 'm2', 'Metro cuadrado')"),
            {"i": str(unidad_id), "o": str(escenario.org_id)},
        )
    yield unidad_id
    await engine.dispose()


def _cuerpo(unidad: uuid.UUID, **extra: object) -> dict:
    return {"clave": "nuevo-1", "descripcion": "Firme especial", "unidad_id": str(unidad), **extra}


async def test_nace_en_el_catalogo_y_en_la_obra_sin_cantidad(
    escenario: Escenario, unidad: uuid.UUID, control: httpx.AsyncClient
) -> None:
    r = await control.post(
        f"/api/v1/obras/{escenario.obra_id}/conceptos-nuevos",
        json=_cuerpo(unidad, precio_unitario="120.50"),
    )
    assert r.status_code == 201, r.text
    cuerpo = r.json()
    assert cuerpo["clave"] == "NUEVO-1"

    engine = create_async_engine(DATABASE_URL_ADMIN)
    async with engine.connect() as conn:
        fila = (
            await conn.execute(
                text(
                    "select a.cant_base, a.cant_programada, a.precio_unitario, a.modificacion::text, "
                    "c.unidad_id from actividad a join concepto c on c.id = a.concepto_id "
                    "where a.id = :a"
                ),
                {"a": cuerpo["actividad_id"]},
            )
        ).one()
    await engine.dispose()
    assert (fila[0], fila[1], float(fila[2]), fila[3], fila[4]) == (0, 0, 120.5, "adicional", unidad)


async def test_la_clave_repetida_se_rechaza(
    escenario: Escenario, unidad: uuid.UUID, control: httpx.AsyncClient
) -> None:
    url = f"/api/v1/obras/{escenario.obra_id}/conceptos-nuevos"
    assert (await control.post(url, json=_cuerpo(unidad))).status_code == 201
    r = await control.post(url, json=_cuerpo(unidad, descripcion="Otro"))
    assert r.status_code == 422, r.text


async def test_el_residente_no_da_de_alta_conceptos(
    escenario: Escenario, unidad: uuid.UUID, residente: httpx.AsyncClient
) -> None:
    r = await residente.post(
        f"/api/v1/obras/{escenario.obra_id}/conceptos-nuevos", json=_cuerpo(unidad)
    )
    assert r.status_code == 403, r.text


async def test_obra_ajena_no_existe(unidad: uuid.UUID, control: httpx.AsyncClient) -> None:
    r = await control.post(f"/api/v1/obras/{uuid.uuid4()}/conceptos-nuevos", json=_cuerpo(unidad))
    assert r.status_code == 404, r.text


async def test_costos_da_de_alta_el_concepto_con_su_rol_real(
    escenario: Escenario, unidad: uuid.UUID, costos: httpx.AsyncClient
) -> None:
    """Costos no está en `es_config()`: lo que lo deja escribir es la política de la migración 0090."""
    r = await costos.post(
        f"/api/v1/obras/{escenario.obra_id}/conceptos-nuevos", json=_cuerpo(unidad)
    )
    assert r.status_code == 201, r.text
    # Y lee unidades y etapas para llenar el formulario.
    assert (await costos.get("/api/v1/unidades")).status_code == 200
    assert (await costos.get("/api/v1/etapas")).status_code == 200
    assert (await costos.get("/api/v1/conceptos")).status_code == 200
