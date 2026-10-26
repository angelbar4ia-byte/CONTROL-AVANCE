"""Lo ejecutado de más se registra y el excedente va a comprobación y validación
(migración 0066) — por HTTP de punta a punta contra Postgres real.

La decisión del usuario: si se puede ejecutar más de lo programado, el excedente
va a comprobación y validación. El cerebro lo respalda: «registrar nunca se
bloquea» (WORKFLOWS.md §8.1). Lo que se fija aquí es lo que solo se ve cruzando
router → caso de uso → repositorio → triggers → RLS:

 1. capturar de más **ya no se rechaza**; el excedente se registra, la bitácora
    sigue sumando el total y el avance sigue topado en 100;
 2. el excedente aparece en la bandeja de Control, con su antigüedad;
 3. una actividad con excedente no se cierra (y por tanto no se estima) hasta que
    se decide;
 4. validar sube el techo, deja un control de cambio ya autorizado con su orden y
    vacía la bandeja; declarar pérdida lo saca de la bandeja sin subir el techo;
 5. solo Control de obra y el Super intendente deciden; otra organización no ve
    nada.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal

import httpx
import pytest

from obractrl.adapters.api.dependencias import contexto_actual
from obractrl.infrastructure.db.sesion import ContextoSesion
from obractrl.main import crear_app
from tests.integracion.conftest import Escenario


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


async def _ejecutar(cliente: httpx.AsyncClient, escenario: Escenario, cantidad: str) -> dict:
    respuesta = await cliente.patch(
        f"/api/v1/actividades/{escenario.actividad_id}/avance",
        json={"cant_ejecutada": cantidad},
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


async def _actividad(cliente: httpx.AsyncClient, escenario: Escenario) -> dict:
    respuesta = await cliente.get(f"/api/v1/actividades/{escenario.actividad_id}")
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


async def test_ejecutar_de_mas_se_registra_y_el_avance_sigue_topado(
    escenario: Escenario, residente: httpx.AsyncClient
) -> None:
    antes = await _ejecutar(residente, escenario, "100")
    assert Decimal(antes["cant_excedente"]) == 0

    # La actividad tiene 100 programados: ejecutar 130 ya no es un 422.
    despues = await _ejecutar(residente, escenario, "130")
    assert Decimal(despues["cant_ejecutada"]) == 130
    assert Decimal(despues["cant_excedente"]) == 30
    assert Decimal(despues["avance_pct"]) == 100  # el excedente no infla el avance

    detalle = await _actividad(residente, escenario)
    assert Decimal(detalle["cant_excedente"]) == 30
    assert detalle["excedente_desde"] == date.today().isoformat()

    # Corregir hacia abajo limpia el excedente y su antigüedad.
    corregido = await _ejecutar(residente, escenario, "100")
    assert Decimal(corregido["cant_excedente"]) == 0
    assert (await _actividad(residente, escenario))["excedente_desde"] is None


async def test_el_excedente_aparece_en_la_bandeja_de_control(
    escenario: Escenario, residente: httpx.AsyncClient, control: httpx.AsyncClient
) -> None:
    assert (await control.get("/api/v1/comprobaciones")).json() == []

    await _ejecutar(residente, escenario, "125")

    bandeja = (await control.get("/api/v1/comprobaciones")).json()
    assert len(bandeja) == 1
    assert bandeja[0]["actividad_id"] == str(escenario.actividad_id)
    assert Decimal(bandeja[0]["cant_excedente"]) == 25
    assert Decimal(bandeja[0]["cant_programada"]) == 100
    assert bandeja[0]["dias"] == 0
    # Lo ve también quien lo originó: la lectura está abierta a quien ve la obra.
    assert len((await residente.get("/api/v1/comprobaciones")).json()) == 1


async def test_con_excedente_pendiente_no_se_puede_cerrar(
    escenario: Escenario, residente: httpx.AsyncClient
) -> None:
    await _ejecutar(residente, escenario, "130")
    cierre = await residente.post(
        f"/api/v1/actividades/{escenario.actividad_id}/cierre",
        json={"cantidad": "130", "checklist": [{"item": "x", "ok": True}], "adjuntos": ["r2://a.jpg"]},
    )
    assert cierre.status_code == 409, cierre.text
    assert "comprobarlos y validarlos" in cierre.json()["detail"]


async def test_validar_sube_el_techo_y_deja_un_control_de_cambio(
    escenario: Escenario, residente: httpx.AsyncClient, control: httpx.AsyncClient
) -> None:
    await _ejecutar(residente, escenario, "130")
    url = f"/api/v1/actividades/{escenario.actividad_id}/excedente/validar"

    # Sin orden de cambio no hay validación: no autoriza nada.
    sin_orden = await control.post(url, json={"nota": "Se midió en obra"})
    assert sin_orden.status_code == 422
    assert sin_orden.json()["campo"] == "orden_cambio"
    sin_nota = await control.post(url, json={"nota": " ", "orden_cambio": "OC-77"})
    assert sin_nota.status_code == 422

    ok = await control.post(url, json={"nota": "Se midió en obra", "orden_cambio": "OC-77"})
    assert ok.status_code == 200, ok.text
    cuerpo = ok.json()
    assert cuerpo["decision"] == "validado"
    assert Decimal(cuerpo["cantidad"]) == 30
    assert cuerpo["control_cambio_id"] is not None

    detalle = await _actividad(control, escenario)
    assert Decimal(detalle["cant_programada"]) == 130  # lo programado sube a lo ejecutado
    assert Decimal(detalle["cant_autorizada"]) == 130  # y el techo firmado también
    assert Decimal(detalle["cant_excedente"]) == 0
    assert detalle["orden_cambio"] == "OC-77"
    assert (await control.get("/api/v1/comprobaciones")).json() == []

    # Quedó como control de cambio ya autorizado, en la bandeja de siempre.
    controles = (await control.get("/api/v1/controles-cambio")).json()
    propio = [c for c in controles if c["id"] == cuerpo["control_cambio_id"]]
    assert len(propio) == 1
    assert propio[0]["estatus"] == "autorizado"
    assert propio[0]["orden_cambio"] == "OC-77"

    historial = (await control.get(f"/api/v1/actividades/{escenario.actividad_id}/excedente")).json()
    assert [h["decision"] for h in historial] == ["validado"]
    assert historial[0]["nota"] == "Se midió en obra"

    # Validado, ya se puede cerrar con lo que se ejecutó.
    cierre = await residente.post(
        f"/api/v1/actividades/{escenario.actividad_id}/cierre",
        json={"cantidad": "130", "checklist": [{"item": "x", "ok": True}], "adjuntos": ["r2://a.jpg"]},
    )
    assert cierre.status_code == 201, cierre.text

    # Una segunda decisión sobre lo mismo no hace nada: ya no hay excedente.
    otra = await control.post(url, json={"nota": "Otra vez", "orden_cambio": "OC-78"})
    assert otra.status_code == 409
    assert otra.json()["type"].endswith("sin-excedente")


async def test_declarar_perdida_saca_el_excedente_sin_subir_el_techo(
    escenario: Escenario, residente: httpx.AsyncClient, control: httpx.AsyncClient
) -> None:
    await _ejecutar(residente, escenario, "130")
    url = f"/api/v1/actividades/{escenario.actividad_id}/excedente/perdida"

    ok = await control.post(url, json={"nota": "Retrabajo del contratista, no se cobra"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["decision"] == "perdida"
    assert ok.json()["control_cambio_id"] is None

    detalle = await _actividad(control, escenario)
    assert Decimal(detalle["cant_programada"]) == 100  # el techo NO sube
    assert Decimal(detalle["cant_ejecutada"]) == 130  # lo ejecutado queda registrado
    assert Decimal(detalle["cant_excedente"]) == 0
    assert (await control.get("/api/v1/comprobaciones")).json() == []

    # No se paga lo perdido: no se puede cerrar por encima de lo programado.
    de_mas = await residente.post(
        f"/api/v1/actividades/{escenario.actividad_id}/cierre",
        json={"cantidad": "130", "checklist": [{"item": "x", "ok": True}], "adjuntos": ["r2://a.jpg"]},
    )
    assert de_mas.status_code == 409
    justo = await residente.post(
        f"/api/v1/actividades/{escenario.actividad_id}/cierre",
        json={"cantidad": "100", "checklist": [{"item": "x", "ok": True}], "adjuntos": ["r2://a.jpg"]},
    )
    assert justo.status_code == 201, justo.text


async def test_si_vuelve_a_crecer_despues_de_la_perdida_solo_lo_nuevo_es_pendiente(
    escenario: Escenario, residente: httpx.AsyncClient, control: httpx.AsyncClient
) -> None:
    await _ejecutar(residente, escenario, "130")
    await control.post(
        f"/api/v1/actividades/{escenario.actividad_id}/excedente/perdida", json={"nota": "x"}
    )
    crecio = await _ejecutar(residente, escenario, "140")
    assert Decimal(crecio["cant_excedente"]) == 10  # los 30 ya decididos no vuelven

    bandeja = (await control.get("/api/v1/comprobaciones")).json()
    assert Decimal(bandeja[0]["cant_excedente"]) == 10


async def test_solo_control_y_super_intendente_deciden(
    escenario: Escenario,
    residente: httpx.AsyncClient,
    contexto_supervisor: ContextoSesion,
    contexto_super_intendente: ContextoSesion,
) -> None:
    await _ejecutar(residente, escenario, "130")
    url = f"/api/v1/actividades/{escenario.actividad_id}/excedente"
    cuerpo = {"nota": "x", "orden_cambio": "OC-1"}

    # Ni quien lo originó ni el supervisor: es de Control.
    assert (await residente.post(f"{url}/validar", json=cuerpo)).status_code == 403
    assert (await residente.post(f"{url}/perdida", json=cuerpo)).status_code == 403
    async with _cliente(contexto_supervisor) as supervisor:
        assert (await supervisor.post(f"{url}/validar", json=cuerpo)).status_code == 403
        # …pero el supervisor sí ve lo que espera decisión en sus obras.
        assert len((await supervisor.get("/api/v1/comprobaciones")).json()) == 1
    async with _cliente(contexto_super_intendente) as super_intendente:
        assert (await super_intendente.post(f"{url}/perdida", json=cuerpo)).status_code == 200


async def test_otra_organizacion_no_ve_ni_decide(
    escenario: Escenario, residente: httpx.AsyncClient
) -> None:
    await _ejecutar(residente, escenario, "130")
    control_ajeno = ContextoSesion(
        org_id=uuid.uuid4(), usuario_id=uuid.uuid4(), rol="control_obra"
    )
    async with _cliente(control_ajeno) as ajeno:
        assert (await ajeno.get("/api/v1/comprobaciones")).json() == []
        r = await ajeno.post(
            f"/api/v1/actividades/{escenario.actividad_id}/excedente/validar",
            json={"nota": "x", "orden_cambio": "OC-1"},
        )
        assert r.status_code == 404
    assert len((await residente.get("/api/v1/comprobaciones")).json()) == 1
