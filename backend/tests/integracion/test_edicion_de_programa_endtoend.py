"""Quién edita qué del programa, y que cada edición deje rastro (migración 0067).

El cerebro reparte la edición en dos permisos (MODELO.md §5b): Control de obra
edita la **estructura** del programa (duraciones, vínculos, tramos, frente) y el
Residente edita las **fechas**, porque es quien sabe cuándo arrancó de verdad una
partida. Y «cada edición se agrega a una bitácora que no se borra»
(erp-programa.md §6). Por HTTP de punta a punta contra Postgres real:

 1. el residente edita fechas y queda en la bitácora con su rol;
 2. el residente no toca la estructura —ni a medias: una petición con fechas **y**
    duración se rechaza entera, no aplica solo las fechas—;
 3. Control de obra y Supervisor editan todo, y la bitácora distingue
    estructura / fechas / mixta;
 4. el Super intendente no edita el programa;
 5. la bitácora solo trae lo que esa persona pidió (no lo que el recálculo
    reescribió solo), la ve quien ve la obra y otra organización no ve nada;
 6. el ancla `inicio_dias` que el PATCH aceptaba ahora sí se escribe.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import text

from obractrl.adapters.api.dependencias import contexto_actual
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
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


async def _editar(cliente: httpx.AsyncClient, escenario: Escenario, cuerpo: dict) -> httpx.Response:
    return await cliente.patch(
        f"/api/v1/actividades/{escenario.actividad_id}/programacion", json=cuerpo
    )


async def _bitacora(cliente: httpx.AsyncClient, escenario: Escenario) -> list[dict]:
    respuesta = await cliente.get(f"/api/v1/obras/{escenario.obra_id}/programa/ediciones")
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


async def _fila(contexto: ContextoSesion, escenario: Escenario) -> dict:
    async with sesion_con_rls(contexto) as sesion:
        fila = (
            await sesion.execute(
                text(
                    "select duracion_dias, fecha_inicio, fecha_termino, inicio_dias "
                    "from actividad where id = :id"
                ),
                {"id": str(escenario.actividad_id)},
            )
        ).mappings().one()
    return dict(fila)


async def test_el_residente_edita_fechas_y_queda_en_la_bitacora(
    escenario: Escenario,
    residente: httpx.AsyncClient,
    control: httpx.AsyncClient,
    contexto_residente: ContextoSesion,
) -> None:
    ok = await _editar(
        residente, escenario, {"fecha_inicio": "2026-03-09", "fecha_termino": "2026-03-13"}
    )
    assert ok.status_code == 200, ok.text

    fila = await _fila(contexto_residente, escenario)
    assert str(fila["fecha_inicio"]) == "2026-03-09"
    assert str(fila["fecha_termino"]) == "2026-03-13"

    [edicion] = await _bitacora(control, escenario)
    assert edicion["rol"] == "residente"
    assert edicion["tipo"] == "fechas"
    assert edicion["usuario_id"] == str(escenario.residente_id)
    assert edicion["actividad_id"] == str(escenario.actividad_id)
    assert edicion["despues"] == {"fecha_inicio": "2026-03-09", "fecha_termino": "2026-03-13"}
    # Solo lo que pidió: ni duración ni dependencias, aunque el CPM las recalculó.
    assert set(edicion["antes"]) == {"fecha_inicio", "fecha_termino"}


async def test_el_residente_no_toca_la_estructura(
    escenario: Escenario,
    residente: httpx.AsyncClient,
    control: httpx.AsyncClient,
    contexto_residente: ContextoSesion,
) -> None:
    antes = await _fila(contexto_residente, escenario)

    for cuerpo in (
        {"duracion_dias": "9"},
        {"dependencias": []},
        {"tramos": []},
        {"inicio_dias": "3"},
    ):
        respuesta = await _editar(residente, escenario, cuerpo)
        assert respuesta.status_code == 403, (cuerpo, respuesta.text)
        assert respuesta.json()["type"].endswith("edicion-de-programa-no-permitida")

    # Fechas y duración juntas: se rechaza entera, no se aplican solo las fechas.
    mixta = await _editar(
        residente, escenario, {"fecha_inicio": "2026-03-09", "duracion_dias": "9"}
    )
    assert mixta.status_code == 403

    assert await _fila(contexto_residente, escenario) == antes
    assert await _bitacora(control, escenario) == []


async def test_control_y_supervisor_editan_todo_y_la_bitacora_distingue_el_tipo(
    escenario: Escenario,
    control: httpx.AsyncClient,
    supervisor: httpx.AsyncClient,
) -> None:
    estructura = await _editar(control, escenario, {"duracion_dias": "6"})
    assert estructura.status_code == 200, estructura.text
    assert Decimal(estructura.json()["duracion_dias"]) == 6

    fechas = await _editar(supervisor, escenario, {"fecha_inicio": "2026-03-09"})
    assert fechas.status_code == 200, fechas.text

    mixta = await _editar(
        control, escenario, {"duracion_dias": "4", "fecha_termino": "2026-03-20"}
    )
    assert mixta.status_code == 200, mixta.text

    bitacora = await _bitacora(control, escenario)
    # Lo más reciente primero.
    assert [(e["rol"], e["tipo"]) for e in bitacora] == [
        ("control_obra", "mixta"),
        ("supervisor", "fechas"),
        ("control_obra", "estructura"),
    ]
    assert Decimal(bitacora[2]["antes"]["duracion_dias"]) == 1
    assert Decimal(bitacora[2]["despues"]["duracion_dias"]) == 6
    assert Decimal(bitacora[0]["antes"]["duracion_dias"]) == 6
    assert Decimal(bitacora[0]["despues"]["duracion_dias"]) == 4


async def test_el_super_intendente_no_edita_el_programa(
    escenario: Escenario, super_intendente: httpx.AsyncClient, control: httpx.AsyncClient
) -> None:
    respuesta = await _editar(super_intendente, escenario, {"fecha_inicio": "2026-03-09"})
    assert respuesta.status_code == 403
    assert await _bitacora(control, escenario) == []


async def test_una_edicion_rechazada_no_deja_rastro(
    escenario: Escenario, control: httpx.AsyncClient
) -> None:
    # Fechas invertidas: el dominio lo rechaza antes de escribir nada.
    invalida = await _editar(
        control, escenario, {"fecha_inicio": "2026-03-20", "fecha_termino": "2026-03-10"}
    )
    assert invalida.status_code == 422
    assert await _bitacora(control, escenario) == []


async def test_otra_organizacion_no_ve_la_bitacora_ni_edita(
    escenario: Escenario, control: httpx.AsyncClient, ajeno: httpx.AsyncClient
) -> None:
    await _editar(control, escenario, {"duracion_dias": "5"})
    assert len(await _bitacora(control, escenario)) == 1

    respuesta = await ajeno.get(f"/api/v1/obras/{escenario.obra_id}/programa/ediciones")
    assert respuesta.status_code == 404


async def test_el_ancla_inicio_dias_ahora_se_escribe(
    escenario: Escenario, control: httpx.AsyncClient, contexto_control: ContextoSesion
) -> None:
    assert (await _fila(contexto_control, escenario))["inicio_dias"] is None

    ok = await _editar(control, escenario, {"inicio_dias": "3"})
    assert ok.status_code == 200, ok.text

    assert Decimal(str((await _fila(contexto_control, escenario))["inicio_dias"])) == 3
