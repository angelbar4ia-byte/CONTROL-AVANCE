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


async def test_cambiar_a_otro_tipo_de_medicion_pide_equivalencia_y_no_se_hace_en_el_lugar(
    escenario: Escenario, catalogo: dict, control: httpx.AsyncClient
) -> None:
    """Pasar de m² a pieza o a metros cruza de tipo (D-623): ya no se cambia en el lugar, se propone con equivalencia."""
    url = f"/api/v1/conceptos/{catalogo['c1']}/unidad"
    cruza = await control.put(url, json={"unidad_id": str(catalogo["pza"])})
    assert cruza.status_code == 422, cruza.text
    assert "equivalencia" in cruza.text
    # La misma unidad (o una del mismo tipo) sigue cambiándose directo.
    assert (await control.put(url, json={"unidad_id": str(catalogo["m2"])})).status_code == 200


async def test_costos_arma_el_arbol_con_su_rol_real(escenario: Escenario, catalogo: dict, costos: httpx.AsyncClient) -> None:
    n = await costos.post("/api/v1/niveles", json={"clave": "cs", "descripcion": "De Costos"})
    assert n.status_code == 201, n.text
    e = await costos.post("/api/v1/etapas", json={"nivel_id": n.json()["id"], "clave": "cse", "descripcion": "Etapa"})
    assert e.status_code == 201, e.text
    r = await costos.put(f"/api/v1/conceptos/{catalogo['c1']}/unidad", json={"unidad_id": str(catalogo["m2"])})
    assert r.status_code == 200, r.text


async def test_el_residente_no_arma_el_arbol(escenario: Escenario, catalogo: dict, residente: httpx.AsyncClient) -> None:
    assert (await residente.post("/api/v1/niveles", json={"clave": "r", "descripcion": "r"})).status_code == 403
    assert (
        await residente.put(f"/api/v1/conceptos/{catalogo['c1']}/unidad", json={"unidad_id": str(catalogo["ml"])})
    ).status_code == 403


async def test_quitar_una_partida_sin_uso_y_no_la_que_ya_trabaja(
    escenario: Escenario, catalogo: dict, control: httpx.AsyncClient, residente: httpx.AsyncClient
) -> None:
    r = await control.post(f"/api/v1/obras/{escenario.obra_id}/partidas", json={"concepto_id": str(catalogo["c1"])})
    assert r.status_code == 201, r.text
    actividad = r.json()["actividad_id"]
    # El residente no arma el árbol.
    assert (await residente.delete(f"/api/v1/actividades/{actividad}/partida")).status_code == 403

    # Con avance ejecutado no se quita.
    engine = create_async_engine(DATABASE_URL_ADMIN)
    async with engine.begin() as conn:
        await conn.execute(text("update actividad set cant_ejecutada = 2 where id = :a"), {"a": actividad})
    assert (await control.delete(f"/api/v1/actividades/{actividad}/partida")).status_code == 409
    async with engine.begin() as conn:
        await conn.execute(text("update actividad set cant_ejecutada = 0 where id = :a"), {"a": actividad})
    await engine.dispose()

    assert (await control.delete(f"/api/v1/actividades/{actividad}/partida")).status_code == 204
    assert (await control.delete(f"/api/v1/actividades/{actividad}/partida")).status_code == 404


async def test_renombrar_y_reordenar_niveles_y_etapas(
    escenario: Escenario, catalogo: dict, control: httpx.AsyncClient, residente: httpx.AsyncClient
) -> None:
    a = (await control.post("/api/v1/niveles", json={"clave": "na", "descripcion": "Alfa"})).json()["id"]
    b = (await control.post("/api/v1/niveles", json={"clave": "nb", "descripcion": "Beta"})).json()["id"]
    e = (await control.post("/api/v1/etapas", json={"nivel_id": a, "clave": "ea", "descripcion": "Cim"})).json()["id"]

    # Sin orden, salen por clave; con orden, Beta pasa adelante.
    assert [n["clave"] for n in (await control.get("/api/v1/niveles")).json()] == ["NA", "NB"]
    assert (await control.patch(f"/api/v1/niveles/{b}", json={"orden": 1, "descripcion": "Beta 2"})).status_code == 204
    assert (await control.patch(f"/api/v1/niveles/{a}", json={"orden": 2})).status_code == 204
    lista = (await control.get("/api/v1/niveles")).json()
    assert [n["clave"] for n in lista] == ["NB", "NA"] and lista[0]["descripcion"] == "Beta 2"

    assert (await control.patch(f"/api/v1/etapas/{e}", json={"descripcion": "Cimentación"})).status_code == 204
    assert next(x for x in (await control.get("/api/v1/etapas")).json() if x["id"] == e)["descripcion"] == "Cimentación"

    assert (await control.patch(f"/api/v1/niveles/{uuid.uuid4()}", json={"orden": 1})).status_code == 422
    assert (await control.patch(f"/api/v1/etapas/{e}", json={"descripcion": ""})).status_code == 422
    assert (await residente.patch(f"/api/v1/niveles/{a}", json={"orden": 5})).status_code == 403
