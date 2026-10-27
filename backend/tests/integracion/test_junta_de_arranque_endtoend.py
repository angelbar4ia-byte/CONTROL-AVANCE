"""La junta de arranque: Control de obra marca la obra `iniciada`
(WORKFLOWS.md §8.1, D-537 `marcar_obra_iniciada`) — por HTTP de punta a punta
contra Postgres real.

`Obra.iniciar` existía en el dominio y nadie lo llamaba: el estatus `iniciada`
era inalcanzable y el cronograma arrancaba el día del alta, no el de la junta.
Lo que se fija aquí es lo que solo se ve cruzando router → caso de uso →
repositorio → trigger de avance → RLS:

 1. Control declara la junta: la obra queda `iniciada` con la fecha de la junta;
 2. esa fecha es el arranque del cronograma: la ruta crítica se recalcula contra
    ella (es lo que dispara las fechas contractuales);
 3. con avance 0 la obra **conserva** `iniciada` (el trigger no la devuelve a
    `pendiente`), y con avance pasa a `en_proceso` como siempre;
 4. solo una obra `pendiente` se inicia; solo Control de obra lo hace; otra
    organización no la ve.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date, timedelta

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
async def supervisor(contexto_supervisor: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_supervisor) as c:
        yield c


@pytest.fixture
async def control(contexto_control: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_control) as c:
        yield c


@pytest.fixture
async def super_intendente(
    contexto_super_intendente: ContextoSesion,
) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_super_intendente) as c:
        yield c


@pytest.fixture
async def ajeno(contexto_ajeno: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_ajeno) as c:
        yield c


def _iniciar(cliente: httpx.AsyncClient, escenario: Escenario, cuerpo: dict | None = None):
    return cliente.post(
        f"/api/v1/obras/{escenario.obra_id}/iniciar",
        json=cuerpo if cuerpo is not None else {},
        headers={"Idempotency-Key": f"junta-{id(cuerpo)}-{date.today()}-{escenario.obra_id}"},
    )


async def _obra(cliente: httpx.AsyncClient, escenario: Escenario) -> dict:
    respuesta = await cliente.get(f"/api/v1/obras/{escenario.obra_id}")
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


async def test_control_declara_la_junta_y_la_obra_queda_iniciada(
    escenario: Escenario, control: httpx.AsyncClient
) -> None:
    assert (await _obra(control, escenario))["estatus"] == "pendiente"

    fecha = date.today() + timedelta(days=14)
    respuesta = await _iniciar(control, escenario, {"fecha": fecha.isoformat()})
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estatus"] == "iniciada"
    assert respuesta.json()["fecha_inicio"] == fecha.isoformat()

    obra = await _obra(control, escenario)
    assert obra["estatus"] == "iniciada"
    assert obra["fecha_inicio"] == fecha.isoformat()


async def test_sin_fecha_la_junta_es_hoy(
    escenario: Escenario, control: httpx.AsyncClient
) -> None:
    respuesta = await _iniciar(control, escenario)
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["fecha_inicio"] == date.today().isoformat()


async def test_la_fecha_de_la_junta_es_el_arranque_del_cronograma(
    escenario: Escenario, control: httpx.AsyncClient
) -> None:
    fecha = date.today() + timedelta(days=30)
    assert (await _iniciar(control, escenario, {"fecha": fecha.isoformat()})).status_code == 200

    ruta = (await control.get(f"/api/v1/obras/{escenario.obra_id}/ruta-critica")).json()
    assert ruta["fecha_inicio"] == fecha.isoformat()
    # Una actividad sin predecesoras ni fechas propias arranca el día de la junta.
    [actividad] = ruta["actividades"]
    assert actividad["inicio_temprano"] == fecha.isoformat()


async def test_con_avance_cero_conserva_iniciada_y_con_avance_pasa_a_en_proceso(
    escenario: Escenario, control: httpx.AsyncClient, residente: httpx.AsyncClient
) -> None:
    assert (await _iniciar(control, escenario)).status_code == 200

    # Capturar 0 no devuelve la obra a `pendiente`: la junta ya se dio.
    cero = await residente.patch(
        f"/api/v1/actividades/{escenario.actividad_id}/avance", json={"cant_ejecutada": "0"}
    )
    assert cero.status_code == 200, cero.text
    assert (await _obra(control, escenario))["estatus"] == "iniciada"

    avance = await residente.patch(
        f"/api/v1/actividades/{escenario.actividad_id}/avance", json={"cant_ejecutada": "40"}
    )
    assert avance.status_code == 200, avance.text
    assert (await _obra(control, escenario))["estatus"] == "en_proceso"


async def test_solo_una_obra_pendiente_se_inicia(
    escenario: Escenario, control: httpx.AsyncClient
) -> None:
    assert (await _iniciar(control, escenario, {"fecha": "2031-03-03"})).status_code == 200

    otra_vez = await control.post(
        f"/api/v1/obras/{escenario.obra_id}/iniciar",
        json={"fecha": "2031-03-10"},
        headers={"Idempotency-Key": "junta-segunda-vez"},
    )
    assert otra_vez.status_code == 409, otra_vez.text
    assert otra_vez.json()["type"].endswith("flujo-de-obra")
    # La junta original no se movió.
    assert (await _obra(control, escenario))["fecha_inicio"] == "2031-03-03"


async def test_la_junta_no_puede_ser_despues_del_fin_de_la_obra(
    escenario: Escenario, control: httpx.AsyncClient
) -> None:
    fin = await control.patch(
        f"/api/v1/obras/{escenario.obra_id}", json={"fecha_fin": "2031-03-01"}
    )
    assert fin.status_code == 200, fin.text

    respuesta = await _iniciar(control, escenario, {"fecha": "2031-04-01"})
    assert respuesta.status_code == 422, respuesta.text
    assert (await _obra(control, escenario))["estatus"] == "pendiente"


async def test_solo_control_de_obra_declara_la_junta(
    escenario: Escenario,
    residente: httpx.AsyncClient,
    supervisor: httpx.AsyncClient,
    super_intendente: httpx.AsyncClient,
    control: httpx.AsyncClient,
) -> None:
    for cliente in (residente, supervisor, super_intendente):
        assert (await _iniciar(cliente, escenario)).status_code == 403
    assert (await _obra(control, escenario))["estatus"] == "pendiente"


async def test_otra_organizacion_no_puede_iniciarla(
    escenario: Escenario, ajeno: httpx.AsyncClient
) -> None:
    # El contexto ajeno es de super intendente: el rol ya lo frena. Se prueba
    # además con el rol correcto en otra organización.
    assert (await _iniciar(ajeno, escenario)).status_code == 403


async def test_control_de_otra_organizacion_recibe_404(
    escenario: Escenario, contexto_ajeno: ContextoSesion
) -> None:
    control_ajeno = ContextoSesion(
        org_id=contexto_ajeno.org_id, usuario_id=contexto_ajeno.usuario_id, rol="control_obra"
    )
    async with _cliente(control_ajeno) as cliente:
        # Sin `Idempotency-Key`: la organización ajena no existe en la base y el
        # registro de la clave toparía con su llave foránea antes de llegar a RLS.
        r = await cliente.post(f"/api/v1/obras/{escenario.obra_id}/iniciar", json={})
        assert r.status_code == 404, r.text
