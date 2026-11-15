"""Correcciones propuestas al catálogo como nueva versión del concepto, por HTTP contra Postgres real (migración 0132; Ola 3B).

Costos propone, Control de obra autoriza; el catálogo no se edita; la corrección conocida de EST-02330 (unidad m2 → m) queda como versión
del concepto sin construir el elemento de esa cadena."""

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

RUTA = "/api/v1/correcciones-de-catalogo"
CUERPO = {"concepto_clave": "EST-02330", "campo": "unidad"}


def _cliente(contexto: ContextoSesion) -> httpx.AsyncClient:
    app = crear_app()
    app.dependency_overrides[contexto_actual] = lambda: contexto
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test")


async def _usuario(escenario: Escenario, rol: str, nombre: str) -> uuid.UUID:
    usuario = uuid.uuid4()
    motor = create_async_engine(DATABASE_URL_ADMIN)
    async with motor.begin() as c:
        await c.execute(
            text("insert into usuario (id, org_id, nombre, email, rol) values (:i, :o, :n, :e, :r)"),
            {"i": str(usuario), "o": str(escenario.org_id), "n": nombre, "e": f"{rol}-{usuario.hex[:8]}@t.mx", "r": rol},
        )
    await motor.dispose()
    return usuario


@pytest.fixture
async def control(contexto_control: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_control) as c:
        yield c


@pytest.fixture
async def costos(escenario: Escenario) -> AsyncIterator[httpx.AsyncClient]:
    usuario = await _usuario(escenario, "costos", "Costos")
    async with _cliente(ContextoSesion(org_id=escenario.org_id, usuario_id=usuario, rol="costos")) as c:
        yield c


@pytest.fixture
async def residente(contexto_residente: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_residente) as c:
        yield c


async def test_sin_proponer_la_unidad_es_la_del_catalogo(costos: httpx.AsyncClient) -> None:
    r = await costos.get(RUTA)
    assert r.status_code == 200
    (c,) = r.json()
    assert (c["concepto_clave"], c["estado"], c["valor_catalogo"], c["valor_propuesto"], c["valor_vigente"]) == (
        "EST-02330", "sin_proponer", "m2", "m", "m2",
    )
    assert c["version_vigente"] is None and c["historial"] == []


async def test_costos_propone_control_de_obra_autoriza_y_nace_la_version(costos: httpx.AsyncClient, control: httpx.AsyncClient) -> None:
    r = await costos.post(RUTA, json=CUERPO)
    assert r.status_code == 201, r.text
    propuesta = r.json()
    assert propuesta["estado"] == "pendiente" and propuesta["version"] is None
    # Pendiente: el valor vigente sigue siendo el del catálogo y no se puede proponer otra vez.
    (c,) = (await costos.get(RUTA)).json()
    assert c["estado"] == "pendiente" and c["valor_vigente"] == "m2" and c["pendiente_id"] == propuesta["id"]
    assert (await costos.post(RUTA, json=CUERPO)).status_code == 422
    # Costos no autoriza.
    assert (await costos.post(f"{RUTA}/{propuesta['id']}/autorizar")).status_code == 403
    ok = await control.post(f"{RUTA}/{propuesta['id']}/autorizar")
    assert ok.status_code == 200 and ok.json() == {"version": 1}
    (c,) = (await costos.get(RUTA)).json()
    assert c["estado"] == "autorizada" and c["version_vigente"] == 1 and c["valor_vigente"] == "m"
    assert c["valor_catalogo"] == "m2"  # el catálogo vigente no se edita: la diferencia se sigue mostrando
    (h,) = c["historial"]
    assert h["estado"] == "autorizada" and h["propuso_rol"] == "costos" and h["decidio_rol"] == "control_obra"
    # Ya autorizada: no se vuelve a proponer, y la decidida no se decide otra vez.
    assert (await costos.post(RUTA, json=CUERPO)).status_code == 422
    assert (await control.post(f"{RUTA}/{propuesta['id']}/autorizar")).status_code == 422


async def test_control_de_obra_rechaza_y_se_puede_proponer_de_nuevo(costos: httpx.AsyncClient, control: httpx.AsyncClient) -> None:
    pid = (await costos.post(RUTA, json=CUERPO)).json()["id"]
    assert (await control.post(f"{RUTA}/{pid}/rechazar", json={"motivo": "Falta confirmar con Costos"})).status_code == 204
    (c,) = (await control.get(RUTA)).json()
    assert c["estado"] == "sin_proponer" and c["valor_vigente"] == "m2"
    assert c["historial"][0]["estado"] == "rechazada" and c["historial"][0]["motivo_rechazo"] == "Falta confirmar con Costos"
    otra = await costos.post(RUTA, json=CUERPO)
    assert otra.status_code == 201


async def test_lo_que_propone_control_de_obra_queda_autorizado_al_momento(control: httpx.AsyncClient) -> None:
    r = await control.post(RUTA, json=CUERPO)
    assert r.status_code == 201 and r.json()["estado"] == "autorizada" and r.json()["version"] == 1
    (c,) = (await control.get(RUTA)).json()
    assert c["version_vigente"] == 1 and c["historial"][0]["decidio_rol"] == "control_obra"


async def test_solo_se_proponen_las_correcciones_conocidas_y_por_los_roles_que_proponen(
    costos: httpx.AsyncClient, residente: httpx.AsyncClient
) -> None:
    assert (await costos.post(RUTA, json={"concepto_clave": "EST-02010", "campo": "unidad"})).status_code == 422
    assert (await costos.post(RUTA, json={"concepto_clave": "EST-02330", "campo": "precio"})).status_code == 422
    assert (await residente.post(RUTA, json=CUERPO)).status_code == 403
    assert (await residente.get(RUTA)).status_code == 403
    assert (await costos.post(f"{RUTA}/{uuid.uuid4()}/rechazar", json={})).status_code == 403


async def test_el_catalogo_de_conceptos_no_cambia(costos: httpx.AsyncClient, control: httpx.AsyncClient, escenario: Escenario) -> None:
    """Autorizar la versión no toca `concepto` ni `unidad`: la diferencia se muestra, el catálogo queda como vino."""
    motor = create_async_engine(DATABASE_URL_ADMIN)
    async with motor.connect() as c:
        antes = (await c.execute(text("select count(*) from concepto where org_id = :o"), {"o": str(escenario.org_id)})).scalar_one()
    pid = (await costos.post(RUTA, json=CUERPO)).json()["id"]
    assert (await control.post(f"{RUTA}/{pid}/autorizar")).status_code == 200
    async with motor.connect() as c:
        despues = (await c.execute(text("select count(*) from concepto where org_id = :o"), {"o": str(escenario.org_id)})).scalar_one()
    await motor.dispose()
    assert antes == despues
