"""Cambiar la unidad de un concepto a otro tipo de medición (D-623): propuesta, equivalencia y versión nueva."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

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
async def losa(escenario: Escenario) -> AsyncIterator[dict[str, uuid.UUID]]:
    """Una «Losa» en pieza con 10 de un auxiliar y 48 m² de destajo, ya como partida de la obra."""
    ids = {k: uuid.uuid4() for k in ("pza", "m2", "ml", "losa", "aux", "destajo", "cpu")}
    org = str(escenario.org_id)
    motor = create_async_engine(DATABASE_URL_ADMIN)
    async with motor.begin() as c:
        for k in ("pza", "m2", "ml"):
            await c.execute(
                text("insert into unidad (id, org_id, clave, nombre) values (:i, :o, :c, :c)"),
                {"i": str(ids[k]), "o": org, "c": k},
            )
        for k, clave, unidad in (("losa", "LOSA-1", "pza"), ("aux", "AUX-1", "pza"), ("destajo", "MO-LOSA", "m2")):
            await c.execute(
                text("insert into concepto (id, org_id, clave, descripcion, unidad_id) values (:i, :o, :k, :k, :u)"),
                {"i": str(ids[k]), "o": org, "k": clave, "u": str(ids[unidad])},
            )
        await c.execute(
            text("insert into cpu (id, org_id, concepto_id, precio_unitario, precio_destajo) values (:i, :o, :c, 4800, 4800)"),
            {"i": str(ids["cpu"]), "o": org, "c": str(ids["losa"])},
        )
        for hijo, cat, cant, costo in (("aux", "matriz", 10, 100), ("destajo", "destajo", 48, 80)):
            await c.execute(
                text(
                    "insert into explosion (org_id, concepto_id, cpu_id, tipo_hijo, concepto_hijo_id, categoria, cantidad, costo_unitario, importe) "
                    "values (:o, :c, :cpu, 'concepto', :h, cast(:cat as categoria_explosion), :cant, :costo, :imp)"
                ),
                {"o": org, "c": str(ids["losa"]), "cpu": str(ids["cpu"]), "h": str(ids[hijo]), "cat": cat, "cant": cant, "costo": costo, "imp": cant * costo},
            )
        await c.execute(
            text("update actividad set concepto_id = :c, cant_base = 2, cant_programada = 2, precio_unitario = 4800 where id = :a"),
            {"c": str(ids["losa"]), "a": str(escenario.actividad_id)},
        )
    yield ids
    await motor.dispose()


async def _trazos(cliente: httpx.AsyncClient, escenario: Escenario) -> dict[str, str]:
    plano = (await cliente.post(f"/api/v1/obras/{escenario.obra_id}/planos", json={"nombre": "P", "archivo_url": "e2e/p.pdf"})).json()["id"]
    salida = {}
    for nombre, wkt in (("punto", "POINT(1 1)"), ("area", "POLYGON((0 0, 4 0, 4 3, 0 3, 0 0))")):
        r = await cliente.post(
            f"/api/v1/planos/{plano}/trazos",
            json={
                "version_plano": 1, "fuente": "pdf", "geometria_wkt": wkt,
                "enlaces": [{"medida": "conteo", "factor": "1", "actividad_id": str(escenario.actividad_id)}],
            },
        )
        assert r.status_code == 201, r.text
        salida[nombre] = r.json()["trazo_id"]
    return salida


async def test_de_pieza_a_m2_nace_una_version_con_las_cantidades_entre_48(
    escenario: Escenario, losa: dict, control: httpx.AsyncClient
) -> None:
    trazos = await _trazos(control, escenario)

    # Sin equivalencia, el cambio en el lugar ya no existe: pide proponerlo.
    directo = await control.put(f"/api/v1/conceptos/{losa['losa']}/unidad", json={"unidad_id": str(losa["m2"])})
    assert directo.status_code == 422

    r = await control.post(f"/api/v1/conceptos/{losa['losa']}/cambio-de-unidad", json={"unidad_id": str(losa["m2"])})
    assert r.status_code == 201, r.text
    cambio = r.json()
    assert cambio["origen_equivalencia"] == "destajo" and Decimal(cambio["equivalencia"]) == 48  # los 48 m² del destajo
    assert (cambio["tipo_anterior"], cambio["tipo_nuevo"]) == ("conteo", "area")

    # La puede teclear para corregirla.
    t = await control.put(f"/api/v1/cambios-de-unidad/{cambio['id']}/equivalencia", json={"equivalencia": "40"})
    assert t.json()["origen_equivalencia"] == "tecleada"
    await control.put(f"/api/v1/cambios-de-unidad/{cambio['id']}/equivalencia", json={"equivalencia": "48"})

    a = await control.post(f"/api/v1/cambios-de-unidad/{cambio['id']}/aprobar")
    assert a.status_code == 200, a.text
    res = a.json()
    assert res["clave_nueva"] == "LOSA-1-M2" and res["partidas_movidas"] == 1

    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.connect() as c:
            lineas = (
                await c.execute(
                    text("select cantidad, costo_unitario, importe from explosion where concepto_id = :n order by cantidad"),
                    {"n": res["concepto_nuevo_id"]},
                )
            ).all()
            # 10 ÷ 48 y 48 ÷ 48; el costo unitario de cada insumo no cambia.
            assert [round(float(x[0]), 6) for x in lineas] == [round(10 / 48, 6), 1.0]
            assert [float(x[1]) for x in lineas] == [100.0, 80.0]
            pu = (await c.execute(text("select precio_unitario from cpu where concepto_id = :n"), {"n": res["concepto_nuevo_id"]})).scalar_one()
            assert float(pu) == pytest.approx(4800 / 48)
            act = (await c.execute(text("select concepto_id, cant_base, precio_unitario from actividad where id = :a"), {"a": str(escenario.actividad_id)})).one()
            assert str(act[0]) == res["concepto_nuevo_id"] and float(act[1]) == 96.0 and float(act[2]) == pytest.approx(100.0)
            # El concepto original no se tocó.
            assert (await c.execute(text("select unidad_id from concepto where id = :c"), {"c": str(losa["losa"])})).scalar_one() == losa["pza"]
    finally:
        await motor.dispose()

    # Los trazos: el área mide su área en m²; el punto no cabe en m² y queda marcado sin enlace nuevo.
    area = (await control.get(f"/api/v1/trazos/{trazos['area']}/cambios-de-unidad")).json()
    assert [(m["medida_vieja"], m["medida_nueva"]) for m in area] == [("conteo", "area")]
    punto = (await control.get(f"/api/v1/trazos/{trazos['punto']}/cambios-de-unidad")).json()
    assert [(m["medida_vieja"], m["medida_nueva"], m["enlace_nuevo_id"]) for m in punto] == [("conteo", None, None)]
    assert res["enlaces_rehechos"] == 1 and res["enlaces_sin_medida"] == 1

    # Ya resuelto: no se aprueba dos veces.
    assert (await control.post(f"/api/v1/cambios-de-unidad/{cambio['id']}/aprobar")).status_code == 422


async def test_lo_con_avance_se_bloquea_y_los_roles_se_respetan(
    escenario: Escenario, losa: dict, control: httpx.AsyncClient, residente: httpx.AsyncClient
) -> None:
    ruta = f"/api/v1/conceptos/{losa['losa']}/cambio-de-unidad"
    assert (await residente.post(ruta, json={"unidad_id": str(losa["m2"])})).status_code == 403
    # Una unidad que no cambia (o que no cruza de tipo) no pasa por una propuesta.
    assert (await control.post(f"/api/v1/conceptos/{losa['destajo']}/cambio-de-unidad", json={"unidad_id": str(losa["m2"])})).status_code == 422

    motor = create_async_engine(DATABASE_URL_ADMIN)
    async with motor.begin() as c:
        await c.execute(text("update actividad set cant_ejecutada = 1 where id = :a"), {"a": str(escenario.actividad_id)})
    await motor.dispose()

    cambio = (await control.post(ruta, json={"unidad_id": str(losa["m2"]), "equivalencia": "48"})).json()
    assert cambio["partidas"] == 1 and cambio["partidas_bloqueadas"] == 1 and cambio["origen_equivalencia"] == "tecleada"
    assert (await control.post(ruta, json={"unidad_id": str(losa["m2"])})).status_code == 422  # ya hay uno por resolver
    assert (await control.post(f"/api/v1/cambios-de-unidad/{cambio['id']}/aprobar")).status_code == 409
    assert (await control.post(f"/api/v1/cambios-de-unidad/{cambio['id']}/rechazar")).status_code == 204
    assert (await control.get(f"/api/v1/cambios-de-unidad/{cambio['id']}")).json()["estado"] == "rechazado"
