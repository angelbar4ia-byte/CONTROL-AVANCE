"""El cierre de un frente (migración 0071; D-515/D-522/D-261/D-516) — por HTTP de
punta a punta contra Postgres real.

Un frente es un nivel constructivo. El residente solicita su cierre al 90 % de
avance, el supervisor aprueba y control de obra valida; cerrado el frente, el
residente ya no registra avance ahí, y los demás roles sí. Lo que se fija aquí:

 1. el frente se ve con su avance (ponderado por costo) y avisa cuando llega al 90 %;
 2. solo el residente solicita, solo a partir del 90 %, y una sola vez mientras el
    cierre esté vivo; el rechazado no estorba;
 3. cada paso es de su rol y no se salta ninguno;
 4. cerrado el frente, el residente ya no registra avance ahí: 409 (hoy solo el
    residente captura avance; los demás roles siguen leyendo el frente);
 5. otra organización no ve ni toca nada.
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


@pytest.fixture
async def nivel(escenario: Escenario) -> uuid.UUID:
    """La actividad del escenario cuelga de un nivel (el frente), con costo."""
    engine = create_async_engine(DATABASE_URL_ADMIN)
    nivel_id = uuid.uuid4()
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "insert into nivel (id, org_id, clave, descripcion, orden) "
                    "values (:id, :org, 'CIM', 'Cimentación', 1)"
                ),
                {"id": str(nivel_id), "org": str(escenario.org_id)},
            )
            await conn.execute(
                text(
                    "update actividad set nivel_id = :n, precio_unitario = 10, "
                    "cant_base = 100, cant_programada = 100 where id = :id"
                ),
                {"n": str(nivel_id), "id": str(escenario.actividad_id)},
            )
    finally:
        await engine.dispose()
    return nivel_id


async def _avance(cliente: httpx.AsyncClient, escenario: Escenario, cantidad: str):
    return await cliente.patch(
        f"/api/v1/actividades/{escenario.actividad_id}/avance", json={"cant_ejecutada": cantidad}
    )


async def _frente(cliente: httpx.AsyncClient, escenario: Escenario) -> dict:
    r = await cliente.get(f"/api/v1/obras/{escenario.obra_id}/cierres-frente")
    assert r.status_code == 200, r.text
    [frente] = r.json()
    return frente


def _solicitar(cliente: httpx.AsyncClient, escenario: Escenario, nivel: uuid.UUID, clave: str):
    return cliente.post(
        f"/api/v1/obras/{escenario.obra_id}/cierres-frente",
        json={"nivel_id": str(nivel)},
        headers={"Idempotency-Key": clave},
    )


def _paso(cliente: httpx.AsyncClient, cierre_id: str, accion: str, clave: str, cuerpo=None):
    return cliente.post(
        f"/api/v1/cierres-frente/{cierre_id}/{accion}",
        json=cuerpo or {},
        headers={"Idempotency-Key": clave},
    )


async def test_el_frente_se_ve_con_su_avance_y_avisa_al_llegar_al_90(
    escenario: Escenario, nivel: uuid.UUID, residente: httpx.AsyncClient
) -> None:
    assert (await _avance(residente, escenario, "60")).status_code == 200
    frente = await _frente(residente, escenario)
    assert frente["clave"] == "CIM"
    assert frente["n_actividades"] == 1
    assert Decimal(frente["avance_pct"]) == 60
    assert Decimal(frente["umbral_pct"]) == 90
    assert frente["listo_para_cierre"] is False
    assert frente["cierre_estatus"] is None

    assert (await _avance(residente, escenario, "90")).status_code == 200
    frente = await _frente(residente, escenario)
    assert Decimal(frente["avance_pct"]) == 90
    assert frente["listo_para_cierre"] is True  # avisa, no cierra


async def test_solicitar_exige_al_residente_el_90_y_una_sola_vez(
    escenario: Escenario,
    nivel: uuid.UUID,
    residente: httpx.AsyncClient,
    supervisor: httpx.AsyncClient,
) -> None:
    await _avance(residente, escenario, "80")
    demasiado_pronto = await _solicitar(residente, escenario, nivel, "k1")
    assert demasiado_pronto.status_code == 409, demasiado_pronto.text
    assert "90" in demasiado_pronto.text

    await _avance(residente, escenario, "95")
    # El supervisor no solicita: el rol ya lo frena.
    assert (await _solicitar(supervisor, escenario, nivel, "k2")).status_code == 403

    ok = await _solicitar(residente, escenario, nivel, "k3")
    assert ok.status_code == 201, ok.text
    assert ok.json()["estatus"] == "solicitado"
    assert Decimal(ok.json()["avance_pct"]) == 95  # la constancia de cuánto llevaba

    frente = await _frente(residente, escenario)
    assert frente["cierre_estatus"] == "solicitado"
    assert frente["listo_para_cierre"] is False  # ya se solicitó: deja de avisar

    otra = await _solicitar(residente, escenario, nivel, "k4")
    assert otra.status_code == 409
    assert "ya tiene un cierre" in otra.text


async def test_un_frente_que_no_existe_en_la_obra_es_404(
    escenario: Escenario, nivel: uuid.UUID, residente: httpx.AsyncClient
) -> None:
    await _avance(residente, escenario, "95")
    r = await _solicitar(residente, escenario, uuid.uuid4(), "k1")
    assert r.status_code == 404, r.text


async def test_la_cadena_cada_paso_es_de_su_rol_y_no_se_salta_ninguno(
    escenario: Escenario,
    nivel: uuid.UUID,
    residente: httpx.AsyncClient,
    supervisor: httpx.AsyncClient,
    control: httpx.AsyncClient,
) -> None:
    await _avance(residente, escenario, "95")
    cierre = (await _solicitar(residente, escenario, nivel, "s")).json()["id"]

    # No se valida lo que no se aprobó.
    saltado = await _paso(control, cierre, "validar", "v0")
    assert saltado.status_code == 409, saltado.text

    # Cada paso es de su rol (exigir_rol → 403).
    assert (await _paso(residente, cierre, "aprobar", "a0")).status_code == 403
    assert (await _paso(control, cierre, "aprobar", "a1")).status_code == 403

    aprobado = await _paso(supervisor, cierre, "aprobar", "a2")
    assert aprobado.status_code == 200, aprobado.text
    assert aprobado.json()["estatus"] == "aprobado"
    assert aprobado.json()["aprobado_por"] == str(escenario.supervisor_id)

    assert (await _paso(supervisor, cierre, "validar", "v1")).status_code == 403
    validado = await _paso(control, cierre, "validar", "v2", {"comentario": "Recorrido"})
    assert validado.status_code == 200, validado.text
    assert validado.json()["estatus"] == "validado"
    assert validado.json()["comentarios"] == "Recorrido"

    frente = await _frente(residente, escenario)
    assert frente["cierre_estatus"] == "validado"
    assert frente["validado_en"] is not None


async def test_un_rechazo_pide_motivo_y_no_estorba_una_solicitud_nueva(
    escenario: Escenario,
    nivel: uuid.UUID,
    residente: httpx.AsyncClient,
    supervisor: httpx.AsyncClient,
) -> None:
    await _avance(residente, escenario, "95")
    primero = (await _solicitar(residente, escenario, nivel, "s1")).json()["id"]

    # Un motivo en blanco no es motivo: lo rechaza la regla del cierre.
    assert (await _paso(supervisor, primero, "rechazar", "r0", {"motivo": " "})).status_code == 409
    rechazado = await _paso(supervisor, primero, "rechazar", "r1", {"motivo": "Falta la losa"})
    assert rechazado.status_code == 200, rechazado.text
    assert rechazado.json()["estatus"] == "rechazado"

    # El residente ve por qué, y puede volver a solicitar.
    frente = await _frente(residente, escenario)
    assert frente["cierre_estatus"] == "rechazado"
    assert frente["cierre_comentarios"] == "Falta la losa"
    segundo = await _solicitar(residente, escenario, nivel, "s2")
    assert segundo.status_code == 201, segundo.text
    assert segundo.json()["id"] != primero


async def test_cerrado_el_frente_el_residente_ya_no_registra_avance_pero_el_supervisor_si(
    escenario: Escenario,
    nivel: uuid.UUID,
    residente: httpx.AsyncClient,
    supervisor: httpx.AsyncClient,
    control: httpx.AsyncClient,
) -> None:
    await _avance(residente, escenario, "95")
    cierre = (await _solicitar(residente, escenario, nivel, "s")).json()["id"]

    # Mientras el cierre no se valida, el frente sigue abierto.
    assert (await _avance(residente, escenario, "96")).status_code == 200
    await _paso(supervisor, cierre, "aprobar", "a")
    assert (await _avance(residente, escenario, "97")).status_code == 200

    await _paso(control, cierre, "validar", "v")

    bloqueada = await _avance(residente, escenario, "98")
    assert bloqueada.status_code == 409, bloqueada.text
    assert bloqueada.json()["type"].endswith("frente-cerrado")
    assert "CIM" in bloqueada.json()["detail"]

    # El cierre cierra **al residente**: la lectura del frente sigue abierta para todos.
    assert (await _frente(supervisor, escenario))["cierre_estatus"] == "validado"


async def test_otra_organizacion_no_ve_ni_toca_nada(
    escenario: Escenario,
    nivel: uuid.UUID,
    residente: httpx.AsyncClient,
    supervisor: httpx.AsyncClient,
    ajeno: httpx.AsyncClient,
) -> None:
    await _avance(residente, escenario, "95")
    cierre = (await _solicitar(residente, escenario, nivel, "s")).json()["id"]

    assert (await ajeno.get(f"/api/v1/obras/{escenario.obra_id}/cierres-frente")).status_code == 404
    # Sin Idempotency-Key: la org ajena no existe y el registro de la clave toparía
    # con su llave foránea antes de llegar a RLS. Y el contexto ajeno es de super
    # intendente: el rol ya lo frena antes, así que se prueba con la lectura.
    assert (
        await ajeno.post(f"/api/v1/cierres-frente/{cierre}/rechazar", json={"motivo": "x"})
    ).status_code == 403
