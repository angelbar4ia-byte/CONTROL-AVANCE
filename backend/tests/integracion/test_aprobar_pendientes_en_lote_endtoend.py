"""Aprobar pendientes en lote por HTTP contra Postgres real (§10.3).

`POST /pendientes/aprobar-lote`: o una lista de `ids` (los marcados en la pantalla) o
«todos los no críticos». Aprobar solo cierra el pendiente, así que el lote no tiene efectos
secundarios; resolver es de una sola vez (lo ya resuelto se omite y no se pisa), todo va en
una transacción y RLS acota a la organización.
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


async def _sembrar(escenario: Escenario, *, no_criticos: int, criticos: int, ya_resueltos: int = 0) -> dict[str, list[str]]:
    """Pendientes abiertos (críticos y no) y algunos ya resueltos, de la organización del escenario."""
    assert DATABASE_URL_ADMIN is not None
    ids: dict[str, list[str]] = {"no_criticos": [], "criticos": [], "resueltos": []}
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as conn:
            for grupo, cantidad, critico, resuelto in (
                ("no_criticos", no_criticos, False, False),
                ("criticos", criticos, True, False),
                ("resueltos", ya_resueltos, False, True),
            ):
                for n in range(cantidad):
                    nuevo = str(uuid.uuid4())
                    ids[grupo].append(nuevo)
                    await conn.execute(
                        text(
                            "insert into pendiente (id, org_id, tipo, entidad, valor_origen, critico, resuelto, resolucion) "
                            "values (:i, :o, 'cpu_nuevo', 'concepto', :v, :c, :r, "
                            "case when :r then cast('{\"accion\": \"rechazado\", \"nota\": \"primera\"}' as jsonb) end)"
                        ),
                        {"i": nuevo, "o": str(escenario.org_id), "v": f"{grupo}-{n}", "c": critico, "r": resuelto},
                    )
    finally:
        await motor.dispose()
    return ids


async def _estado(ids: list[str]) -> dict[str, dict]:
    assert DATABASE_URL_ADMIN is not None
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.connect() as conn:
            filas = await conn.execute(
                text("select id::text, resuelto, resuelto_por::text, resolucion from pendiente where id = any(cast(:ids as uuid[]))"),
                {"ids": ids},
            )
            return {f["id"]: dict(f) for f in filas.mappings()}
    finally:
        await motor.dispose()


async def test_aprobar_los_no_criticos_deja_los_criticos_abiertos(
    escenario: Escenario, cliente_control: httpx.AsyncClient
) -> None:
    ids = await _sembrar(escenario, no_criticos=3, criticos=2, ya_resueltos=1)
    r = await cliente_control.post("/api/v1/pendientes/aprobar-lote", json={"solo_no_criticos": True})
    assert r.status_code == 200, r.text
    assert r.json() == {"aprobados": 3, "omitidos": 0}
    estado = await _estado(ids["no_criticos"] + ids["criticos"] + ids["resueltos"])
    assert all(estado[i]["resuelto"] and estado[i]["resolucion"]["accion"] == "aprobado" for i in ids["no_criticos"])
    assert all(estado[i]["resuelto_por"] == str(escenario.control_id) for i in ids["no_criticos"])
    assert not any(estado[i]["resuelto"] for i in ids["criticos"])
    # lo que ya estaba resuelto no se pisa: sigue «rechazado» con su nota
    assert estado[ids["resueltos"][0]]["resolucion"] == {"accion": "rechazado", "nota": "primera"}


async def test_aprobar_los_marcados_incluso_un_critico_y_repetir_no_pisa(
    escenario: Escenario, cliente_control: httpx.AsyncClient
) -> None:
    ids = await _sembrar(escenario, no_criticos=2, criticos=2)
    marcados = [ids["no_criticos"][0], ids["criticos"][0]]
    r = await cliente_control.post("/api/v1/pendientes/aprobar-lote", json={"ids": marcados, "nota": "revisado en bloque"})
    assert r.json() == {"aprobados": 2, "omitidos": 0}
    estado = await _estado(ids["no_criticos"] + ids["criticos"])
    assert estado[ids["criticos"][0]]["resuelto"] and estado[ids["criticos"][0]]["resolucion"]["nota"] == "revisado en bloque"
    assert not estado[ids["criticos"][1]]["resuelto"] and not estado[ids["no_criticos"][1]]["resuelto"]

    repetido = await cliente_control.post("/api/v1/pendientes/aprobar-lote", json={"ids": [*marcados, str(uuid.uuid4())]})
    assert repetido.json() == {"aprobados": 0, "omitidos": 3}


async def test_pedir_las_dos_formas_o_ninguna_o_vacio_es_422(cliente_control: httpx.AsyncClient) -> None:
    for cuerpo in (
        {"ids": [str(uuid.uuid4())], "solo_no_criticos": True},
        {},
        {"ids": []},
    ):
        r = await cliente_control.post("/api/v1/pendientes/aprobar-lote", json=cuerpo)
        assert r.status_code == 422, (cuerpo, r.text)


async def test_el_residente_no_aprueba_en_lote(
    escenario: Escenario, cliente_residente: httpx.AsyncClient
) -> None:
    ids = await _sembrar(escenario, no_criticos=1, criticos=0)
    r = await cliente_residente.post("/api/v1/pendientes/aprobar-lote", json={"solo_no_criticos": True})
    assert r.status_code == 403, r.text
    assert not (await _estado(ids["no_criticos"]))[ids["no_criticos"][0]]["resuelto"]


async def test_otra_organizacion_no_toca_los_pendientes_ajenos(escenario: Escenario) -> None:
    """Un Control de obra de OTRA organización: el rol alcanza, así que lo que lo frena es RLS."""
    ids = await _sembrar(escenario, no_criticos=2, criticos=0)
    ajeno = ContextoSesion(org_id=uuid.uuid4(), usuario_id=uuid.uuid4(), rol="control_obra")
    async with _cliente(ajeno) as cliente:
        r = await cliente.post("/api/v1/pendientes/aprobar-lote", json={"solo_no_criticos": True})
        assert r.status_code == 200, r.text
        assert r.json() == {"aprobados": 0, "omitidos": 0}
        r = await cliente.post("/api/v1/pendientes/aprobar-lote", json={"ids": ids["no_criticos"]})
        assert r.json() == {"aprobados": 0, "omitidos": 2}
    assert not any(v["resuelto"] for v in (await _estado(ids["no_criticos"])).values())
