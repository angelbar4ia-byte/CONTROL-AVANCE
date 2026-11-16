"""Las propuestas de los bastones, por HTTP contra Postgres real (Ola 4, lane 4D).

Usa la tabla de propuestas de la 3A (`propuesta_de_estructura`, 0131) y sus rutas de autorización: Costos o Control de obra proponen,
solo Control de obra autoriza, y el catálogo no se edita."""

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

RUTA = "/api/v1/biblioteca-de-elementos/baston"
PROPUESTAS = "/api/v1/propuestas-de-estructura"


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


SIN_ESCALON = {"largo_cm": 135, "sep_cm": 30}


async def test_costos_propone_el_concepto_nuevo_y_control_de_obra_lo_autoriza(costos: httpx.AsyncClient, control: httpx.AsyncClient) -> None:
    r = await costos.post(f"{RUTA}/BA-1/propuestas/concepto-nuevo", json=SIN_ESCALON)
    assert r.status_code == 201, r.text
    (creada,) = r.json()["creadas"]
    (p,) = (await costos.get(f"{RUTA}/BA-1/propuestas")).json()
    assert p["estado"] == "pendiente" and p["clase"] == "concepto_nuevo" and p["concepto_clave"] == "AUX-B3-135-30" and p["version"] is None
    assert p["propuso_rol"] == "costos"
    assert (await costos.post(f"{PROPUESTAS}/{creada}/autorizar")).status_code == 403
    assert (await control.post(f"{PROPUESTAS}/{creada}/autorizar")).json() == {"version": 1}
    (p,) = (await control.get(f"{RUTA}/BA-1/propuestas")).json()
    assert p["estado"] == "autorizada" and p["version"] == 1


async def test_proponer_dos_veces_no_duplica_y_el_escalon_del_catalogo_no_lleva_concepto_nuevo(costos: httpx.AsyncClient) -> None:
    primera = (await costos.post(f"{RUTA}/BA-1/propuestas/concepto-nuevo", json=SIN_ESCALON)).json()
    segunda = (await costos.post(f"{RUTA}/BA-1/propuestas/concepto-nuevo", json=SIN_ESCALON)).json()
    assert len(primera["creadas"]) == 1 and segunda == {"creadas": [], "omitidas": ["AUX-B3-135-30"]}
    assert (await costos.post(f"{RUTA}/BA-1/propuestas/concepto-nuevo", json={})).status_code == 422
    assert (await costos.post(f"{RUTA}/BA-9/propuestas/concepto-nuevo", json=SIN_ESCALON)).status_code == 404


async def test_confirmar_el_calculo_propone_una_version_con_el_antes_y_el_despues(costos: httpx.AsyncClient, control: httpx.AsyncClient) -> None:
    r = await costos.post(f"{RUTA}/BA-1/propuestas/actualizar-apu", json={})
    assert r.status_code == 201, r.text
    (creada,) = r.json()["creadas"]
    (p,) = (await costos.get(f"{RUTA}/BA-1/propuestas")).json()
    assert p["clase"] == "version_de_concepto" and p["concepto_clave"] == "AUX-02010"
    (cambio,) = p["cambios"]
    assert cambio["insumo"] == "ACR-00001" and cambio["antes"] == 0.432 and cambio["despues"] == pytest.approx(0.5)
    assert (await control.post(f"{PROPUESTAS}/{creada}/autorizar")).json() == {"version": 2}  # el catálogo ya vale como versión 1


async def test_sin_escalon_no_hay_version_que_proponer(costos: httpx.AsyncClient) -> None:
    r = await costos.post(f"{RUTA}/BA-1/propuestas/actualizar-apu", json=SIN_ESCALON)
    assert r.status_code == 201 and r.json() == {"creadas": [], "omitidas": []}


async def test_lo_que_propone_control_de_obra_nace_autorizado_y_el_residente_no_propone(control: httpx.AsyncClient, residente: httpx.AsyncClient) -> None:
    assert (await residente.post(f"{RUTA}/BA-1/propuestas/concepto-nuevo", json=SIN_ESCALON)).status_code == 403
    assert (await control.post(f"{RUTA}/BA-1/propuestas/concepto-nuevo", json=SIN_ESCALON)).status_code == 201
    (p,) = (await control.get(f"{RUTA}/BA-1/propuestas")).json()
    assert p["estado"] == "autorizada" and p["version"] == 1
