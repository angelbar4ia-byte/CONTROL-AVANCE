"""Las partes de una obra y sus plantas (migración 0074; D-571, D-575).

Por HTTP de punta a punta contra Postgres real:

 1. una obra se parte en **etapas**; una actividad marcada como independiente es **una
    parte por sí sola**, y desmarcarla la devuelve a su etapa;
 2. lo que no tiene etapa no queda fuera;
 3. las plantas son 1 o 2: el prototipo las fija y la obra las **hereda al nacer** y puede
    cambiarlas (pasar de una planta a dos);
 4. quién puede qué, y otra organización no ve ni toca nada.
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
async def residente(contexto_residente: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_residente) as c:
        yield c


@pytest.fixture
async def control(contexto_control: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_control) as c:
        yield c


@pytest.fixture
async def ajeno(contexto_ajeno: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_ajeno) as c:
        yield c


@pytest.fixture
async def dos_etapas(escenario: Escenario) -> AsyncIterator[dict[str, uuid.UUID]]:
    """La actividad del escenario en la etapa 1, y una segunda actividad en la etapa 2."""
    engine = create_async_engine(DATABASE_URL_ADMIN)
    nivel, e1, e2, otra = (uuid.uuid4() for _ in range(4))
    org = str(escenario.org_id)
    async with engine.begin() as conn:
        await conn.execute(
            text("insert into nivel (id, org_id, clave, descripcion, orden) values (:i, :o, 'PB', 'Planta baja', 1)"),
            {"i": str(nivel), "o": org},
        )
        for etapa, clave, orden in ((e1, "ECO-1", 1), (e2, "ECO-2", 2)):
            await conn.execute(
                text(
                    "insert into etapa_constructiva (id, org_id, nivel_id, clave, descripcion, orden) "
                    "values (:i, :o, :n, :c, :d, :r)"
                ),
                {"i": str(etapa), "o": org, "n": str(nivel), "c": clave, "d": f"Etapa {orden}", "r": orden},
            )
        await conn.execute(
            text("update actividad set etapa_id = :e where id = :a"),
            {"e": str(e1), "a": str(escenario.actividad_id)},
        )
        await conn.execute(
            text(
                "insert into actividad (id, org_id, obra_id, etapa_id, cant_base, cant_programada) "
                "values (:i, :o, :ob, :e, 100, 100)"
            ),
            {"i": str(otra), "o": org, "ob": str(escenario.obra_id), "e": str(e2)},
        )
    yield {"etapa1": e1, "etapa2": e2, "otra": otra}
    await engine.dispose()


async def _partes(cliente: httpx.AsyncClient, escenario: Escenario) -> dict:
    r = await cliente.get(f"/api/v1/obras/{escenario.obra_id}/partes")
    assert r.status_code == 200, r.text
    return r.json()


async def test_la_obra_se_parte_en_etapas(
    escenario: Escenario, dos_etapas: dict, control: httpx.AsyncClient
) -> None:
    cuerpo = await _partes(control, escenario)
    assert [(p["tipo"], p["n_actividades"]) for p in cuerpo["partes"]] == [
        ("etapa", 1),
        ("etapa", 1),
    ]
    assert cuerpo["partes"][0]["nombre"] == "PB · Etapa 1"
    assert cuerpo["partes"][0]["id"] == str(dos_etapas["etapa1"])


async def test_un_concepto_independiente_es_una_parte_aparte_y_se_puede_devolver(
    escenario: Escenario, dos_etapas: dict, control: httpx.AsyncClient
) -> None:
    url = f"/api/v1/actividades/{dos_etapas['otra']}/parte-independiente"
    assert (await control.put(url, json={"independiente": True})).status_code == 204

    tipos = {p["tipo"]: p for p in (await _partes(control, escenario))["partes"]}
    assert tipos["concepto"]["id"] == str(dos_etapas["otra"])
    assert tipos["concepto"]["actividad_ids"] == [str(dos_etapas["otra"])]
    # La etapa 2 se quedó sin su actividad: ya no es parte.
    assert [p["tipo"] for p in (await _partes(control, escenario))["partes"]].count("etapa") == 1

    assert (await control.put(url, json={"independiente": False})).status_code == 204
    assert [p["tipo"] for p in (await _partes(control, escenario))["partes"]] == ["etapa", "etapa"]


async def test_lo_que_no_tiene_etapa_no_queda_fuera(
    escenario: Escenario, control: httpx.AsyncClient
) -> None:
    [parte] = (await _partes(control, escenario))["partes"]
    assert (parte["tipo"], parte["id"], parte["n_actividades"]) == ("sin_etapa", None, 1)


async def test_las_plantas_del_prototipo_las_hereda_la_obra_al_nacer_y_se_pueden_cambiar(
    escenario: Escenario, control: httpx.AsyncClient
) -> None:
    sin_decir = await control.put(f"/api/v1/prototipos/{escenario.prototipo_id}/plantas", json={"plantas": 2})
    assert sin_decir.status_code == 204, sin_decir.text

    # Una obra que nace después del prototipo con plantas las hereda.
    engine = create_async_engine(DATABASE_URL_ADMIN)
    nueva = uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "insert into obra (id, org_id, cluster_id, prototipo_id, clave) "
                "values (:i, :o, :c, :p, 'OBRA-PLANTAS')"
            ),
            {"i": str(nueva), "o": str(escenario.org_id), "c": str(escenario.cluster_id), "p": str(escenario.prototipo_id)},
        )
    await engine.dispose()

    r = await control.get(f"/api/v1/obras/{nueva}/partes")
    assert (r.json()["plantas"], r.json()["plantas_del_prototipo"]) == (2, 2)

    # Pasar de dos plantas a una es una modificación de la obra, no del prototipo.
    assert (await control.put(f"/api/v1/obras/{nueva}/plantas", json={"plantas": 1})).status_code == 204
    r = await control.get(f"/api/v1/obras/{nueva}/partes")
    assert (r.json()["plantas"], r.json()["plantas_del_prototipo"]) == (1, 2)

    # El prototipo lo dice en su propia respuesta.
    protos = (await control.get("/api/v1/prototipos")).json()
    assert [p["plantas"] for p in protos if p["id"] == str(escenario.prototipo_id)] == [2]


@pytest.mark.parametrize("plantas", [0, 3, -1])
async def test_una_casa_tiene_una_o_dos_plantas(
    escenario: Escenario, control: httpx.AsyncClient, plantas: int
) -> None:
    for ruta in (f"/api/v1/obras/{escenario.obra_id}/plantas", f"/api/v1/prototipos/{escenario.prototipo_id}/plantas"):
        r = await control.put(ruta, json={"plantas": plantas})
        assert r.status_code == 422, r.text


async def test_quien_puede_que(
    escenario: Escenario, dos_etapas: dict, residente: httpx.AsyncClient
) -> None:
    assert (
        await residente.put(
            f"/api/v1/actividades/{dos_etapas['otra']}/parte-independiente", json={"independiente": True}
        )
    ).status_code == 403
    assert (await residente.put(f"/api/v1/obras/{escenario.obra_id}/plantas", json={"plantas": 1})).status_code == 403
    # Leer las partes sí: todos con su alcance.
    assert (await residente.get(f"/api/v1/obras/{escenario.obra_id}/partes")).status_code == 200


async def test_otra_organizacion_no_ve_ni_toca_nada(
    escenario: Escenario, dos_etapas: dict, ajeno: httpx.AsyncClient, contexto_ajeno: ContextoSesion
) -> None:
    assert (await ajeno.get(f"/api/v1/obras/{escenario.obra_id}/partes")).status_code == 404
    control_ajeno = ContextoSesion(org_id=contexto_ajeno.org_id, usuario_id=contexto_ajeno.usuario_id, rol="control_obra")
    async with _cliente(control_ajeno) as c:
        assert (await c.put(f"/api/v1/obras/{escenario.obra_id}/plantas", json={"plantas": 1})).status_code == 404
        assert (await c.put(f"/api/v1/prototipos/{escenario.prototipo_id}/plantas", json={"plantas": 1})).status_code == 404
        assert (
            await c.put(f"/api/v1/actividades/{dos_etapas['otra']}/parte-independiente", json={"independiente": True})
        ).status_code == 404
