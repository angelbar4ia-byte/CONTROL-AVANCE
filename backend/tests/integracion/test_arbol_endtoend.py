"""Armar el árbol desde el cuantificador (entrega 7): niveles, etapas, partidas y la unidad de un concepto."""

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


@pytest.fixture
async def costos(escenario: Escenario) -> AsyncIterator[httpx.AsyncClient]:
    usuario = uuid.uuid4()
    engine = create_async_engine(DATABASE_URL_ADMIN)
    async with engine.begin() as conn:
        await conn.execute(
            text("insert into usuario (id, org_id, nombre, email, rol) values (:i, :o, 'Costos', :e, 'costos')"),
            {"i": str(usuario), "o": str(escenario.org_id), "e": f"c-{usuario.hex[:8]}@t.mx"},
        )
    await engine.dispose()
    async with _cliente(ContextoSesion(org_id=escenario.org_id, usuario_id=usuario, rol="costos")) as c:
        yield c


@pytest.fixture
async def catalogo(escenario: Escenario) -> AsyncIterator[dict[str, uuid.UUID]]:
    engine = create_async_engine(DATABASE_URL_ADMIN)
    org = str(escenario.org_id)
    ids = {k: uuid.uuid4() for k in ("m2", "ml", "pza", "c1")}
    async with engine.begin() as conn:
        for k, clave in (("m2", "m2"), ("ml", "ml"), ("pza", "pza")):
            await conn.execute(
                text("insert into unidad (id, org_id, clave, nombre) values (:i, :o, :c, :c)"),
                {"i": str(ids[k]), "o": org, "c": clave},
            )
        await conn.execute(
            text(
                "insert into concepto (id, org_id, tipo, clave, descripcion, unidad_id) "
                "values (:i, :o, 'concepto', 'FIRME', 'Firme', :u)"
            ),
            {"i": str(ids["c1"]), "o": org, "u": str(ids["m2"])},
        )
    yield ids
    await engine.dispose()


async def test_se_arma_el_arbol_nivel_etapa_partida_y_se_mueve(
    escenario: Escenario, catalogo: dict, control: httpx.AsyncClient
) -> None:
    n1 = (await control.post("/api/v1/niveles", json={"clave": "pb", "descripcion": "Planta baja"})).json()["id"]
    r = await control.post("/api/v1/etapas", json={"nivel_id": n1, "clave": "cim", "descripcion": "Cimentación"})
    assert r.status_code == 201, r.text
    e1 = r.json()["id"]
    e2 = (await control.post("/api/v1/etapas", json={"nivel_id": n1, "clave": "est", "descripcion": "Estructura"})).json()["id"]

    r = await control.post(
        f"/api/v1/obras/{escenario.obra_id}/partidas", json={"concepto_id": str(catalogo["c1"]), "etapa_id": e1}
    )
    assert r.status_code == 201, r.text
    actividad = r.json()["actividad_id"]
    # La misma partida en la misma etapa no se repite.
    assert (
        await control.post(
            f"/api/v1/obras/{escenario.obra_id}/partidas", json={"concepto_id": str(catalogo["c1"]), "etapa_id": e1}
        )
    ).status_code == 422

    r = await control.put(f"/api/v1/actividades/{actividad}/ubicacion", json={"etapa_id": e2})
    assert r.status_code == 200, r.text
    assert r.json()["etapa_id"] == e2 and r.json()["nivel_id"] == n1


async def test_claves_repetidas_y_validaciones(escenario: Escenario, catalogo: dict, control: httpx.AsyncClient) -> None:
    n = (await control.post("/api/v1/niveles", json={"clave": "n1", "descripcion": "Uno"})).json()["id"]
    assert (await control.post("/api/v1/niveles", json={"clave": "N1", "descripcion": "Otro"})).status_code == 422
    assert (await control.post("/api/v1/etapas", json={"nivel_id": str(uuid.uuid4()), "clave": "x", "descripcion": "x"})).status_code == 422
    assert (await control.post("/api/v1/etapas", json={"nivel_id": n, "clave": "e1", "descripcion": "Uno"})).status_code == 201
    assert (await control.post("/api/v1/etapas", json={"nivel_id": n, "clave": "E1", "descripcion": "Otra"})).status_code == 422
    assert (
        await control.post(f"/api/v1/obras/{uuid.uuid4()}/partidas", json={"concepto_id": str(catalogo["c1"])})
    ).status_code == 404


async def test_cambiar_la_unidad_cambia_el_tipo_y_respeta_lo_ya_medido(
    escenario: Escenario, catalogo: dict, control: httpx.AsyncClient
) -> None:
    url = f"/api/v1/conceptos/{catalogo['c1']}/unidad"
    r = await control.put(url, json={"unidad_id": str(catalogo["pza"])})
    assert r.status_code == 200, r.text
    assert (r.json()["tipo_anterior"], r.json()["tipo_nuevo"]) == ("area", "conteo")

    # Con un trazo de área enlazado, ya no se puede pasar a lineal… ni a conteo.
    await control.put(url, json={"unidad_id": str(catalogo["m2"])})
    engine = create_async_engine(DATABASE_URL_ADMIN)
    async with engine.begin() as conn:
        await conn.execute(
            text("update actividad set concepto_id = :c where id = :a"),
            {"c": str(catalogo["c1"]), "a": str(escenario.actividad_id)},
        )
    await engine.dispose()
    plano = (await control.post(f"/api/v1/obras/{escenario.obra_id}/planos", json={"nombre": "P", "archivo_url": "r2://p"})).json()["id"]
    t = await control.post(
        f"/api/v1/planos/{plano}/trazos",
        json={
            "version_plano": 1,
            "geometria_wkt": "POLYGON((0 0,10 0,10 10,0 10,0 0))",
            "fuente": "pdf",
            "enlaces": [{"actividad_id": str(escenario.actividad_id), "medida": "area", "factor": "1"}],
        },
    )
    assert t.status_code == 201, t.text
    bloqueado = await control.put(url, json={"unidad_id": str(catalogo["pza"])})
    assert bloqueado.status_code == 422, bloqueado.text
    assert "area" in bloqueado.text
    # A una unidad del mismo tipo sí (ml no, pero m2 → m2 es el mismo).
    assert (await control.put(url, json={"unidad_id": str(catalogo["m2"])})).status_code == 200


async def test_costos_arma_el_arbol_con_su_rol_real(escenario: Escenario, catalogo: dict, costos: httpx.AsyncClient) -> None:
    n = await costos.post("/api/v1/niveles", json={"clave": "cs", "descripcion": "De Costos"})
    assert n.status_code == 201, n.text
    e = await costos.post("/api/v1/etapas", json={"nivel_id": n.json()["id"], "clave": "cse", "descripcion": "Etapa"})
    assert e.status_code == 201, e.text
    r = await costos.put(f"/api/v1/conceptos/{catalogo['c1']}/unidad", json={"unidad_id": str(catalogo["ml"])})
    assert r.status_code == 200, r.text


async def test_el_residente_no_arma_el_arbol(escenario: Escenario, catalogo: dict, residente: httpx.AsyncClient) -> None:
    assert (await residente.post("/api/v1/niveles", json={"clave": "r", "descripcion": "r"})).status_code == 403
    assert (
        await residente.put(f"/api/v1/conceptos/{catalogo['c1']}/unidad", json={"unidad_id": str(catalogo["ml"])})
    ).status_code == 403
