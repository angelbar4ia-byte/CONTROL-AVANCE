"""Las propuestas de los muros de tabique, los aparejos nuevos y el piso de petatillo, por HTTP contra Postgres real (Ola 3, lane 3C).

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

RUTA = "/api/v1/biblioteca-de-elementos/tabique"
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


async def test_costos_propone_el_concepto_nuevo_y_control_de_obra_lo_autoriza(costos: httpx.AsyncClient, control: httpx.AsyncClient) -> None:
    r = await costos.post(f"{RUTA}/EST-02030/propuestas/concepto-nuevo")
    assert r.status_code == 201, r.text
    (creada,) = r.json()["creadas"]
    (p,) = (await costos.get(f"{RUTA}/EST-02030/propuestas")).json()
    assert p["estado"] == "pendiente" and p["clase"] == "concepto_nuevo" and p["concepto_clave"] == "EST-02030" and p["version"] is None
    assert p["propuso_rol"] == "costos" and p["destajo_por_definir"] is None
    # Costos no autoriza; Control de obra sí, y nace la versión 1.
    assert (await costos.post(f"{PROPUESTAS}/{creada}/autorizar")).status_code == 403
    assert (await control.post(f"{PROPUESTAS}/{creada}/autorizar")).json() == {"version": 1}
    (p,) = (await control.get(f"{RUTA}/EST-02030/propuestas")).json()
    assert p["estado"] == "autorizada" and p["version"] == 1


async def test_proponer_dos_veces_no_duplica_y_el_que_ya_esta_en_el_catalogo_no_lleva_concepto_nuevo(costos: httpx.AsyncClient) -> None:
    primera = (await costos.post(f"{RUTA}/ACA-02090/propuestas/concepto-nuevo")).json()
    segunda = (await costos.post(f"{RUTA}/ACA-02090/propuestas/concepto-nuevo")).json()
    assert len(primera["creadas"]) == 1 and segunda == {"creadas": [], "omitidas": ["ACA-02090"]}
    assert (await costos.post(f"{RUTA}/EST-02010/propuestas/concepto-nuevo")).status_code == 422
    assert (await costos.post(f"{RUTA}/EST-99999/propuestas/concepto-nuevo")).status_code == 404


async def test_confirmar_el_calculo_del_21_propone_una_version_con_el_antes_y_el_despues(costos: httpx.AsyncClient, control: httpx.AsyncClient) -> None:
    r = await costos.post(f"{RUTA}/EST-02020/propuestas/actualizar-apu", json={})
    assert r.status_code == 201, r.text
    (creada,) = r.json()["creadas"]
    (p,) = (await costos.get(f"{RUTA}/EST-02020/propuestas")).json()
    assert p["clase"] == "version_de_concepto" and p["concepto_clave"] == "EST-02020"
    cambios = {c["insumo"]: c for c in p["cambios"]}
    assert cambios["PET-00001"]["antes"] == 86.0 and cambios["PET-00001"]["despues"] == pytest.approx(75.0)
    assert (await control.post(f"{PROPUESTAS}/{creada}/autorizar")).json() == {"version": 2}  # el catálogo ya vale como versión 1


async def test_el_14_cm_coincide_con_el_catalogo_y_no_hay_nada_que_proponer(costos: httpx.AsyncClient) -> None:
    r = await costos.post(f"{RUTA}/EST-02010/propuestas/actualizar-apu", json={})
    assert r.status_code == 201 and r.json() == {"creadas": [], "omitidas": []}


async def test_lo_que_propone_control_de_obra_nace_autorizado_y_el_residente_no_propone(control: httpx.AsyncClient, residente: httpx.AsyncClient) -> None:
    assert (await residente.post(f"{RUTA}/EST-02005/propuestas/concepto-nuevo")).status_code == 403
    assert (await control.post(f"{RUTA}/EST-02005/propuestas/concepto-nuevo")).status_code == 201
    (p,) = (await control.get(f"{RUTA}/EST-02005/propuestas")).json()
    assert p["estado"] == "autorizada" and p["version"] == 1
    # La lista general de pendientes (3A) también trae lo de tabique.
    assert all(x["elemento_clave"] != "EST-02005" for x in (await control.get(f"{PROPUESTAS}/pendientes")).json())


async def test_las_correcciones_de_fabrica_se_proponen_una_vez_y_solo_control_de_obra_autoriza(costos: httpx.AsyncClient, control: httpx.AsyncClient) -> None:
    for clave, concepto in (("EST-02020", "EST-02020"), ("AUX-04010", "AUX-04010")):
        r = await costos.post(f"{RUTA}/{clave}/propuestas/correcciones")
        assert r.status_code == 201 and len(r.json()["creadas"]) == 1, r.text
        assert (await costos.post(f"{RUTA}/{clave}/propuestas/correcciones")).json()["omitidas"] == [concepto]
    (texto,) = (await costos.get(f"{RUTA}/AUX-04010/propuestas")).json()
    assert texto["estado"] == "pendiente" and "1:4" in texto["resumen"] and texto["cambios"] == []
    assert (await control.post(f"{PROPUESTAS}/{texto['id']}/autorizar")).json() == {"version": 2}
    assert (await costos.post(f"{RUTA}/EST-02010/propuestas/correcciones")).json() == {"creadas": [], "omitidas": []}
