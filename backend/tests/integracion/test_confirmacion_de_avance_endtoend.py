"""Confirmar el avance antes de estimar (migración 0070) — por HTTP de punta a
punta contra Postgres real.

El cerebro separa **registrar** el avance (siempre, sin bloqueo) de **confirmarlo**
(el residente afirma que esa cifra es la real). Confirmar no es un candado, pero lo
estimado por encima de lo confirmado es una alerta (D-535). Lo que se fija aquí:

 1. confirma solo el residente; sin avance no hay nada que confirmar;
 2. la confirmación guarda lo ejecutado **en ese momento**: si luego se captura
    más, queda desactualizada y hay que confirmar de nuevo;
 3. la bitácora de confirmaciones no se reescribe: la vigente es la última;
 4. la estimación lee la alerta contra la última confirmación: sin confirmar,
    por encima, o con respaldo, y la cuenta llega a la cabecera;
 5. una semana ya cerrada por una estimación validada no admite confirmar (D-540);
 6. otra organización no ve ni confirma nada.
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
async def residente(contexto_residente: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_residente) as c:
        yield c


@pytest.fixture
async def supervisor(contexto_supervisor: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_supervisor) as c:
        yield c


@pytest.fixture
async def control(contexto_control: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_control) as c:
        yield c


@pytest.fixture
async def ajeno(contexto_ajeno: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_ajeno) as c:
        yield c


async def _avance(cliente: httpx.AsyncClient, escenario: Escenario, cantidad: str) -> None:
    respuesta = await cliente.patch(
        f"/api/v1/actividades/{escenario.actividad_id}/avance",
        json={"cant_ejecutada": cantidad},
    )
    assert respuesta.status_code == 200, respuesta.text


def _confirmar(cliente: httpx.AsyncClient, escenario: Escenario, **cuerpo):
    return cliente.post(
        f"/api/v1/actividades/{escenario.actividad_id}/avance/confirmar", json=cuerpo
    )


async def _estado(cliente: httpx.AsyncClient, escenario: Escenario) -> dict:
    respuesta = await cliente.get(f"/api/v1/obras/{escenario.obra_id}/avance/confirmaciones")
    assert respuesta.status_code == 200, respuesta.text
    [fila] = respuesta.json()
    return fila


async def test_confirmar_guarda_lo_ejecutado_y_si_cambia_queda_desactualizada(
    escenario: Escenario, residente: httpx.AsyncClient
) -> None:
    await _avance(residente, escenario, "60")
    assert (await _estado(residente, escenario))["estado"] == "sin_confirmar"

    ok = await _confirmar(residente, escenario, momento="antes_de_estimar", nota="Recorrido")
    assert ok.status_code == 201, ok.text
    assert Decimal(ok.json()["cantidad"]) == 60
    estado = await _estado(residente, escenario)
    assert estado["estado"] == "confirmada"
    assert Decimal(estado["cant_confirmada"]) == 60
    assert estado["confirmado_por_nombre"]
    assert estado["momento"] == "antes_de_estimar"

    # Se captura más avance: lo confirmado se queda atrás y hay que confirmar de nuevo.
    await _avance(residente, escenario, "80")
    estado = await _estado(residente, escenario)
    assert estado["estado"] == "desactualizada"
    assert Decimal(estado["cant_confirmada"]) == 60
    assert Decimal(estado["cant_ejecutada"]) == 80

    assert (await _confirmar(residente, escenario, momento="al_terminar")).status_code == 201
    estado = await _estado(residente, escenario)
    assert estado["estado"] == "confirmada"
    assert Decimal(estado["cant_confirmada"]) == 80


async def test_confirma_el_residente_y_sin_avance_no_hay_nada_que_confirmar(
    escenario: Escenario,
    residente: httpx.AsyncClient,
    supervisor: httpx.AsyncClient,
    control: httpx.AsyncClient,
) -> None:
    # Sin avance capturado.
    assert (await _confirmar(residente, escenario)).status_code == 422

    await _avance(residente, escenario, "60")
    for otro in (supervisor, control):
        assert (await _confirmar(otro, escenario)).status_code == 403
    # Un momento fuera del vocabulario ni siquiera entra.
    assert (await _confirmar(residente, escenario, momento="cuando_sea")).status_code == 422
    assert (await _estado(residente, escenario))["estado"] == "sin_confirmar"


async def test_la_estimacion_alerta_lo_estimado_por_encima_de_lo_confirmado(
    escenario: Escenario, residente: httpx.AsyncClient, control: httpx.AsyncClient
) -> None:
    await _avance(residente, escenario, "60")

    estimacion = await _estimacion_con_un_renglon(escenario, cantidad="100")
    detalle = (await control.get(f"/api/v1/estimaciones/{estimacion}")).json()
    [renglon] = detalle["conceptos"]
    # Nadie confirmó: todo lo estimado carece de respaldo.
    assert renglon["alerta"] == "sin_confirmar"
    assert renglon["cantidad_confirmada"] is None
    assert Decimal(renglon["exceso"]) == 100
    assert detalle["n_alertas_de_respaldo"] == 1

    # Se confirma 60 y se estima 100: alerta por 40.
    assert (await _confirmar(residente, escenario)).status_code == 201
    detalle = (await control.get(f"/api/v1/estimaciones/{estimacion}")).json()
    [renglon] = detalle["conceptos"]
    assert renglon["alerta"] == "por_encima"
    assert Decimal(renglon["cantidad_confirmada"]) == 60
    assert Decimal(renglon["exceso"]) == 40

    # La cuenta llega a la cabecera y a la bandeja, que es donde Control la ve.
    lista = (await control.get(f"/api/v1/obras/{escenario.obra_id}/estimaciones")).json()
    assert [e["n_alertas_de_respaldo"] for e in lista] == [1]

    # Se confirma 100 (se capturó y confirmó el avance real): con respaldo, sin alerta.
    await _avance(residente, escenario, "100")
    assert (await _confirmar(residente, escenario)).status_code == 201
    detalle = (await control.get(f"/api/v1/estimaciones/{estimacion}")).json()
    assert detalle["conceptos"][0]["alerta"] is None
    assert detalle["n_alertas_de_respaldo"] == 0


async def test_una_semana_ya_cerrada_no_admite_confirmar(
    escenario: Escenario, residente: httpx.AsyncClient
) -> None:
    await _avance(residente, escenario, "60")
    await _cerrar_la_semana_activa(escenario)
    respuesta = await _confirmar(residente, escenario)
    assert respuesta.status_code == 409, respuesta.text
    assert respuesta.json()["type"].endswith("periodo-bloqueado")


async def test_otra_organizacion_no_ve_ni_confirma(
    escenario: Escenario, residente: httpx.AsyncClient, ajeno: httpx.AsyncClient
) -> None:
    await _avance(residente, escenario, "60")
    assert (await ajeno.get(f"/api/v1/obras/{escenario.obra_id}/avance/confirmaciones")).status_code == 404
    # El contexto ajeno es de super intendente: el rol ya lo frena.
    assert (await _confirmar(ajeno, escenario)).status_code == 403


# --- preparativos con el engine admin (aquí se arma el escenario, no se prueba RLS) ---


async def _estimacion_con_un_renglon(escenario: Escenario, *, cantidad: str) -> uuid.UUID:
    engine = create_async_engine(DATABASE_URL_ADMIN)
    estimacion = uuid.uuid4()
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "insert into estimacion (id, org_id, obra_id, semana, anio, modo, "
                    "estatus, monto_total) values (:id, :org, :obra, 10, 2026, 'destajo', "
                    "'enviada', 1000)"
                ),
                {"id": str(estimacion), "org": str(escenario.org_id), "obra": str(escenario.obra_id)},
            )
            await conn.execute(
                text(
                    "insert into estimacion_concepto (org_id, estimacion_id, actividad_id, "
                    "cantidad_validada, precio_unitario, importe) "
                    "values (:org, :est, :act, :cant, 10, :imp)"
                ),
                {
                    "org": str(escenario.org_id),
                    "est": str(estimacion),
                    "act": str(escenario.actividad_id),
                    "cant": cantidad,
                    "imp": str(Decimal(cantidad) * 10),
                },
            )
    finally:
        await engine.dispose()
    return estimacion


async def _cerrar_la_semana_activa(escenario: Escenario) -> None:
    """Fija el ancla de la semana y la bloquea, como lo hace validar una estimación."""
    engine = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "insert into ancla_semana (org_id, tipo, anio, semana, fijada_por) "
                    "values (:org, 'obra', 2026, 10, :usuario) "
                    "on conflict do nothing"
                ),
                {"org": str(escenario.org_id), "usuario": str(escenario.control_id)},
            )
            await conn.execute(
                text(
                    "insert into periodo_bloqueado (org_id, obra_id, tipo_semana, anio, "
                    "semana, bloqueado_por) values (:org, :obra, 'obra', 2026, 10, :usuario)"
                ),
                {
                    "org": str(escenario.org_id),
                    "obra": str(escenario.obra_id),
                    "usuario": str(escenario.control_id),
                },
            )
    finally:
        await engine.dispose()
