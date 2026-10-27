"""Parametrico y mixto, y el escenario «desde cero» (migración 0082; cerebro WORKFLOWS.md §8.1 y
§8.9; D-571, D-578, D-579).

Por HTTP de punta a punta contra Postgres real:

 1. una parte ya cuantificada se **rediseña a paramétrico**: los renglones cuyo concepto está en el
    ensamble pasan a la cantidad estimada y el resto se queda por PU — *mixto no se guarda, se
    reporta en porcentaje*;
 2. sin `aplicar` solo propone; validada vuelve a cuantificarse; asignada no se toca;
 3. **desde cero**: obra sin prototipo de dónde copiar, el ensamble compone las cantidades
    estimadas, se puede programar **avisando**, y medir sustituye a lo estimado sin perderlo;
 4. lo medido vuelve al paramétrico: la desviación entre lo estimado y lo medido se reporta.
"""

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


async def _conceptos(escenario: Escenario) -> dict[str, str]:
    """Dos conceptos con CPU: MURO ($100) y PISO ($50)."""
    engine = create_async_engine(DATABASE_URL_ADMIN)
    org, ids = str(escenario.org_id), {}
    async with engine.begin() as conn:
        for clave, precio in (("EST-MURO", 100), ("EST-PISO", 50)):
            cid = uuid.uuid4()
            ids[clave] = str(cid)
            await conn.execute(
                text("insert into concepto (id, org_id, clave, descripcion) values (:i, :o, :c, :c)"),
                {"i": str(cid), "o": org, "c": clave},
            )
            await conn.execute(
                text(
                    "insert into cpu (org_id, concepto_id, version, precio_unitario, precio_destajo, vigente) "
                    "values (:o, :c, 1, :p, :d, true)"
                ),
                {"o": org, "c": str(cid), "p": precio, "d": precio // 2},
            )
    await engine.dispose()
    return ids


async def _ensamble(control: httpx.AsyncClient, clave: str = "RECAMARA-A") -> str:
    r = await control.post(
        "/api/v1/ensambles",
        json={
            "clave": clave,
            "nombre": "Recámara tipo A",
            "renglones": [{"cantidad": "4", "origen": "manual", "clave_concepto": "EST-MURO"}],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture
async def parte_cuantificada(escenario: Escenario) -> AsyncIterator[dict[str, str]]:
    """Una etapa con dos renglones por PU: 10 muros ($100) y 20 pisos ($50)."""
    ids = await _conceptos(escenario)
    engine = create_async_engine(DATABASE_URL_ADMIN)
    org, etapa = str(escenario.org_id), uuid.uuid4()
    muro, piso = uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text("insert into nivel (id, org_id, clave, descripcion, orden) values (:i, :o, 'PB', 'PB', 1)"),
            {"i": str(uuid.uuid4()), "o": org},
        )
        await conn.execute(
            text("insert into etapa_constructiva (id, org_id, clave, descripcion, orden) values (:i, :o, 'ECO-R', 'Recámara', 1)"),
            {"i": str(etapa), "o": org},
        )
        await conn.execute(text("update actividad set etapa_id = :e where id = :a"), {"e": str(etapa), "a": str(escenario.actividad_id)})
        for aid, concepto, cant, precio in ((muro, "EST-MURO", 10, 100), (piso, "EST-PISO", 20, 50)):
            await conn.execute(
                text(
                    "insert into actividad (id, org_id, obra_id, etapa_id, concepto_id, cant_base, cant_programada, "
                    "precio_unitario, modo_cantidad) values (:i, :o, :ob, :e, :c, :n, :n, :p, 'capturada')"
                ),
                {"i": str(aid), "o": org, "ob": str(escenario.obra_id), "e": str(etapa), "c": ids[concepto], "n": cant, "p": precio},
            )
    yield {"clave": f"etapa:{etapa}", "muro": str(muro), "piso": str(piso), "actividad_base": str(escenario.actividad_id)}
    await engine.dispose()


async def _modo(actividad: str) -> dict:
    engine = create_async_engine(DATABASE_URL_ADMIN)
    async with engine.begin() as conn:
        fila = (
            await conn.execute(
                text("select cant_base, cant_estimada, modo_cantidad::text as modo from actividad where id = :a"),
                {"a": actividad},
            )
        ).mappings().one()
    await engine.dispose()
    return dict(fila)


async def test_redisenar_una_parte_a_parametrico_la_deja_mixta_en_porcentaje(
    escenario: Escenario, parte_cuantificada: dict, control: httpx.AsyncClient
) -> None:
    clave = parte_cuantificada["clave"]
    ensamble = await _ensamble(control)
    antes = (await control.get(f"/api/v1/obras/{escenario.obra_id}/partes/valuacion")).json()
    parte = {p["clave"]: p for p in antes["partes"]}[clave]
    assert (parte["forma"], float(parte["porcentaje_parametrico"])) == ("pu", 0.0)

    # Sin aplicar solo propone: el muro pasa de 10 a 4 × 3 = 12; el piso no está en el ensamble.
    cuerpo = {"clave": clave, "ensamble_id": ensamble, "factor": "3"}
    r = await control.post(f"/api/v1/obras/{escenario.obra_id}/partes/rediseno", json=cuerpo)
    assert r.status_code == 200, r.text
    propuesta = r.json()
    assert propuesta["aplicado"] is False and propuesta["conservan_pu"] == 2  # el piso y el de base
    [p] = propuesta["propuestas"]
    assert (p["concepto_clave"], float(p["cantidad_actual"]), float(p["cantidad_estimada"])) == ("EST-MURO", 10.0, 12.0)
    assert (await _modo(parte_cuantificada["muro"]))["modo"] == "capturada"  # no se tocó

    # Aplicado, queda mixta y se reporta en porcentaje: 1,200 de (1,200 + 1,000) = 54.55 %.
    r = await control.post(f"/api/v1/obras/{escenario.obra_id}/partes/rediseno", json={**cuerpo, "aplicar": True})
    assert r.status_code == 200, r.text
    assert (r.json()["forma_despues"], float(r.json()["porcentaje_parametrico_despues"])) == ("mixto", pytest.approx(54.55, abs=0.5))
    fila = await _modo(parte_cuantificada["muro"])
    assert (float(fila["cant_base"]), fila["modo"]) == (12.0, "estimada")
    val = {p["clave"]: p for p in (await control.get(f"/api/v1/obras/{escenario.obra_id}/partes/valuacion")).json()["partes"]}[clave]
    assert val["forma"] == "mixto" and val["n_estimadas"] == 1
    assert float(val["porcentaje_parametrico"]) == pytest.approx(54.55, abs=0.5)
    # La bitácora de modificaciones cuenta el rediseño.
    bit = (await control.get(f"/api/v1/obras/{escenario.obra_id}/modificaciones")).json()
    assert "Rediseño a paramétrico" in bit[0]["nota"]


async def test_el_rediseno_respeta_los_pasos_de_la_parte_y_los_roles(
    escenario: Escenario, parte_cuantificada: dict, control: httpx.AsyncClient,
    costos: httpx.AsyncClient, residente: httpx.AsyncClient,
) -> None:
    clave = parte_cuantificada["clave"]
    ensamble = await _ensamble(control)
    cuerpo = {"clave": clave, "ensamble_id": ensamble, "factor": "3", "aplicar": True}
    url = f"/api/v1/obras/{escenario.obra_id}/partes/rediseno"
    assert (await residente.post(url, json=cuerpo)).status_code == 403
    assert (await control.post(url, json={**cuerpo, "factor": "0"})).status_code == 422
    assert (await control.post(url, json={**cuerpo, "clave": "etapa:" + str(uuid.uuid4())})).status_code == 404

    # Validada, vuelve a cuantificarse con el rediseño (lo hace Costos, que también puede).
    for accion in ("enviar_a_presupuesto", "autorizar", "validar"):
        r = await control.post(f"/api/v1/obras/{escenario.obra_id}/partes/transicion", json={"accion": accion, "claves": [clave]})
        assert r.status_code == 200, r.text
    assert (await costos.post(url, json=cuerpo)).status_code == 200
    estados = {p["clave"]: p["estado"] for p in (await control.get(f"/api/v1/obras/{escenario.obra_id}/partes")).json()["partes"]}
    assert estados[clave] == "cuantificando"

    # Asignada no se toca; sin aplicar todavía se puede proponer.
    for accion in ("enviar_a_presupuesto", "autorizar", "validar", "enviar_a_programa", "programar", "asignar"):
        r = await control.post(f"/api/v1/obras/{escenario.obra_id}/partes/transicion", json={"accion": accion, "claves": [clave]})
        assert r.status_code == 200, r.text
    assert (await control.post(url, json=cuerpo)).status_code == 409
    assert (await control.post(url, json={**cuerpo, "aplicar": False})).status_code == 200


async def test_desde_cero_el_parametrico_va_primero_y_luego_se_mide(
    escenario: Escenario, control: httpx.AsyncClient
) -> None:
    await _conceptos(escenario)
    ensamble = await _ensamble(control, "ESPACIO-RECAMARA")
    r = await control.post(
        "/api/v1/obras/desde-cero",
        json={"cluster_id": str(escenario.cluster_id), "clave": "CERO-1", "plantas": 1},
    )
    assert r.status_code == 201, r.text
    cero = r.json()

    # Un ensamble por tipo de espacio compone la estructura con cantidades estimadas.
    g = await control.post(
        f"/api/v1/ensambles/{ensamble}/generar",
        json={
            "presupuesto_id": cero["presupuesto_id"],
            "prototipo_id": cero["prototipo_id"],
            "factor": "3",
            "nombre": "Recámara 1",
        },
    )
    assert g.status_code == 200, g.text
    r = await control.post(f"/api/v1/obras/{cero['obra_id']}/generar", json={"modo_pago": "destajo"})
    assert r.status_code in (200, 201), r.text
    [actividad] = (await control.get(f"/api/v1/obras/{cero['obra_id']}/actividades")).json()
    assert float(actividad["cant_base"]) == 12.0  # 4 × 3, estimada
    assert (await _modo(actividad["id"]))["modo"] == "estimada"

    val = (await control.get(f"/api/v1/obras/{cero['obra_id']}/partes/valuacion")).json()
    assert (val["obra"]["forma"], float(val["obra"]["porcentaje_parametrico"])) == ("parametrico", 100.0)

    # Se puede programar y asignar con lo estimado, avisando (D-579).
    clave = (await control.get(f"/api/v1/obras/{cero['obra_id']}/partes")).json()["partes"][0]["clave"]
    avisos = []
    for accion in ("enviar_a_presupuesto", "autorizar", "validar", "enviar_a_programa", "programar"):
        r = await control.post(f"/api/v1/obras/{cero['obra_id']}/partes/transicion", json={"accion": accion, "claves": [clave]})
        assert r.status_code == 200, r.text
        avisos.append(r.json()[0]["aviso"])
    assert avisos[:3] == [None, None, None]  # antes de ir a programa no hay nada que avisar
    assert "estimada" in avisos[3] and "estimada" in avisos[4]

    # Luego se mide, por partes: lo medido sustituye a lo estimado y la parte vuelve a cuantificarse.
    plano = (await control.post(f"/api/v1/obras/{cero['obra_id']}/planos", json={"nombre": "P", "archivo_url": "r2://p"})).json()
    r = await control.post(
        f"/api/v1/planos/{plano['id']}/trazos",
        json={
            "version_plano": 1,
            "geometria_wkt": "POLYGON((0 0, 4 0, 4 4, 0 4, 0 0))",  # 16 m²
            "fuente": "pdf",
            "enlaces": [{"actividad_id": actividad["id"], "medida": "area", "factor": "1"}],
        },
    )
    assert r.status_code == 201, r.text
    fila = await _modo(actividad["id"])
    assert (round(float(fila["cant_base"]), 2), float(fila["cant_estimada"]), fila["modo"]) == (16.0, 12.0, "medida")
    parte = (await control.get(f"/api/v1/obras/{cero['obra_id']}/partes")).json()["partes"][0]
    assert parte["estado"] == "cuantificando"

    # Lo medido vuelve al paramétrico: se quedó corto 33.33 % (12 estimados contra 16 medidos).
    val = (await control.get(f"/api/v1/obras/{cero['obra_id']}/partes/valuacion")).json()
    assert val["obra"]["forma"] == "pu"
    assert float(val["obra"]["desviacion_pct"]) == pytest.approx(33.33, abs=0.01)
    assert Decimal(val["obra"]["estimado_original"]) > 0
