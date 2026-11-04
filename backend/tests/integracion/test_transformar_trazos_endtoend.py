"""Mover y girar trazos (`POST /trazos/transformar`), por HTTP contra Postgres real.

Se mueve o se gira el trazo **con sus huecos**; un largo o un área no cambian, así que las cantidades
de los enlaces siguen iguales. Una forma estampada suma el giro a su rotación. Mismo gobierno que
borrar: un trazo propio sin aprobar, o Control de obra y Super intendente cualquiera.
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

# Un muro de 10 × 4 con una ventana de 2 × 1: 40 − 2 = 38 m².
MURO_CON_VENTANA = "POLYGON((0 0, 10 0, 10 4, 0 4, 0 0), (4 1, 6 1, 6 2, 4 2, 4 1))"


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


@pytest.fixture(autouse=True)
async def _actividad_con_concepto(escenario: Escenario) -> None:
    motor = create_async_engine(DATABASE_URL_ADMIN)
    concepto = uuid.uuid4()
    try:
        async with motor.begin() as conn:
            await conn.execute(
                text("insert into concepto (id, org_id, clave, descripcion) values (:id, :org, 'TRF-1', 'Muro')"),
                {"id": str(concepto), "org": str(escenario.org_id)},
            )
            await conn.execute(
                text("update actividad set concepto_id = :c, precio_unitario = 10, cant_base = 100, cant_programada = 100 where id = :id"),
                {"c": str(concepto), "id": str(escenario.actividad_id)},
            )
    finally:
        await motor.dispose()


async def _plano(cliente: httpx.AsyncClient, escenario: Escenario) -> str:
    r = await cliente.post(f"/api/v1/obras/{escenario.obra_id}/planos", json={"nombre": "P", "archivo_url": "e2e/p.pdf"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _trazo(cliente, escenario, plano_id, wkt, medida="area", **extra) -> str:
    r = await cliente.post(
        f"/api/v1/planos/{plano_id}/trazos",
        json={
            "version_plano": 1,
            "fuente": "pdf",
            "geometria_wkt": wkt,
            "enlaces": [{"medida": medida, "factor": "1", "actividad_id": str(escenario.actividad_id)}],
            **extra,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["trazo_id"]


async def _feature(cliente: httpx.AsyncClient, plano_id: str, trazo_id: str) -> dict:
    fs = (await cliente.get(f"/api/v1/planos/{plano_id}/trazos")).json()["features"]
    return next(f for f in fs if f["id"] == trazo_id)


def _anillos(f: dict) -> list[list[tuple[float, float]]]:
    return [[(round(x, 4), round(y, 4)) for x, y in anillo] for anillo in f["geometry"]["coordinates"]]


async def test_mover_corre_el_trazo_y_su_hueco_y_no_cambia_la_cantidad(
    escenario: Escenario, residente: httpx.AsyncClient
) -> None:
    plano = await _plano(residente, escenario)
    id_ = await _trazo(residente, escenario, plano, MURO_CON_VENTANA)
    antes = await _feature(residente, plano, id_)
    cantidad = antes["properties"]["enlaces"][0]["cantidad"]

    r = await residente.post("/api/v1/trazos/transformar", json={"trazo_ids": [id_], "dx": "5", "dy": "3"})
    assert r.status_code == 200, r.text
    assert r.json()["trazos"] == [{"trazo_id": id_, "pivote": None}]  # mover no usa pivote

    despues = await _feature(residente, plano, id_)
    exterior, hueco = _anillos(despues)
    assert exterior == [(5.0, 3.0), (15.0, 3.0), (15.0, 7.0), (5.0, 7.0), (5.0, 3.0)]
    assert hueco == [(9.0, 4.0), (11.0, 4.0), (11.0, 5.0), (9.0, 5.0), (9.0, 4.0)]  # el hueco se fue con él
    assert despues["properties"]["enlaces"][0]["cantidad"] == cantidad  # 38


async def test_girar_noventa_grados_sobre_su_centro_y_deshacerlo_con_el_pivote_devuelto(
    escenario: Escenario, residente: httpx.AsyncClient
) -> None:
    plano = await _plano(residente, escenario)
    id_ = await _trazo(residente, escenario, plano, MURO_CON_VENTANA)
    original = _anillos(await _feature(residente, plano, id_))

    r = await residente.post("/api/v1/trazos/transformar", json={"trazo_ids": [id_], "grados": "90"})
    assert r.status_code == 200, r.text
    pivote = r.json()["trazos"][0]["pivote"]
    assert [Decimal(p) for p in pivote] == [Decimal(5), Decimal(2)]  # el centro de la caja 10 × 4

    girado = await _feature(residente, plano, id_)
    xs = [x for x, _ in _anillos(girado)[0]]
    ys = [y for _, y in _anillos(girado)[0]]
    assert (min(xs), max(xs), min(ys), max(ys)) == (3.0, 7.0, -3.0, 7.0)  # ahora 4 de ancho × 10 de alto
    assert girado["properties"]["enlaces"][0]["cantidad"] == antes_cantidad(girado)  # 38: el área no cambia

    # Deshacer: el giro contrario con el mismo pivote devuelve el trazo a su sitio.
    atras = await residente.post("/api/v1/trazos/transformar", json={"trazo_ids": [id_], "grados": "-90", "pivote": pivote})
    assert atras.status_code == 200, atras.text
    assert _anillos(await _feature(residente, plano, id_)) == original


def antes_cantidad(f: dict) -> str:
    assert Decimal(f["properties"]["enlaces"][0]["cantidad"]) == 38
    return f["properties"]["enlaces"][0]["cantidad"]


async def test_girar_juntos_alrededor_de_un_pivote_comun(
    escenario: Escenario, residente: httpx.AsyncClient
) -> None:
    plano = await _plano(residente, escenario)
    a = await _trazo(residente, escenario, plano, "POLYGON((0 0, 2 0, 2 2, 0 2, 0 0))")
    b = await _trazo(residente, escenario, plano, "POLYGON((4 0, 6 0, 6 2, 4 2, 4 0))")
    r = await residente.post("/api/v1/trazos/transformar", json={"trazo_ids": [a, b], "grados": "180", "pivote": ["3", "1"]})
    assert r.status_code == 200, r.text
    assert all([Decimal(p) for p in t["pivote"]] == [3, 1] for t in r.json()["trazos"])
    # Medio giro alrededor de (3, 1): el de la izquierda queda a la derecha y al revés.
    assert _anillos(await _feature(residente, plano, a))[0][:4] == [(6.0, 2.0), (4.0, 2.0), (4.0, 0.0), (6.0, 0.0)]
    assert _anillos(await _feature(residente, plano, b))[0][:4] == [(2.0, 2.0), (0.0, 2.0), (0.0, 0.0), (2.0, 0.0)]


async def test_una_forma_estampada_suma_el_giro_a_su_rotacion(
    escenario: Escenario, residente: httpx.AsyncClient
) -> None:
    plano = await _plano(residente, escenario)
    id_ = await _trazo(
        residente, escenario, plano, "POLYGON((0 0, 2 0, 2 2, 0 2, 0 0))",
        forma={"tipo": "cuadrado", "ancho_m": "0.15", "alto_m": "0.15", "rotacion_grados": "10", "nombre": "Castillo K1"},
    )
    r = await residente.post("/api/v1/trazos/transformar", json={"trazo_ids": [id_], "grados": "30"})
    assert r.status_code == 200, r.text
    assert Decimal((await _feature(residente, plano, id_))["properties"]["forma"]["rotacion_grados"]) == 40
    # Pasarse de vuelta no rompe el límite de la forma (−360 a 360): 40 + 170 = 210 → −150.
    await residente.post("/api/v1/trazos/transformar", json={"trazo_ids": [id_], "grados": "170"})
    assert Decimal((await _feature(residente, plano, id_))["properties"]["forma"]["rotacion_grados"]) == -150


async def test_un_trazo_aprobado_ya_no_lo_toca_su_autor_pero_si_control(
    escenario: Escenario, residente: httpx.AsyncClient, control: httpx.AsyncClient
) -> None:
    plano = await _plano(residente, escenario)
    id_ = await _trazo(residente, escenario, plano, MURO_CON_VENTANA)
    assert (await control.post(f"/api/v1/trazos/{id_}/aprobar")).status_code == 200
    original = _anillos(await _feature(control, plano, id_))

    r = await residente.post("/api/v1/trazos/transformar", json={"trazo_ids": [id_], "dx": "1"})
    assert r.status_code == 403, r.text
    assert _anillos(await _feature(control, plano, id_)) == original

    assert (await control.post("/api/v1/trazos/transformar", json={"trazo_ids": [id_], "dx": "1"})).status_code == 200


async def test_todo_o_nada_si_uno_de_los_trazos_no_se_puede_tocar(
    escenario: Escenario, residente: httpx.AsyncClient, control: httpx.AsyncClient
) -> None:
    plano = await _plano(residente, escenario)
    libre = await _trazo(residente, escenario, plano, "POLYGON((0 0, 2 0, 2 2, 0 2, 0 0))")
    aprobado = await _trazo(residente, escenario, plano, "POLYGON((4 0, 6 0, 6 2, 4 2, 4 0))")
    await control.post(f"/api/v1/trazos/{aprobado}/aprobar")
    r = await residente.post("/api/v1/trazos/transformar", json={"trazo_ids": [libre, aprobado], "dx": "10"})
    assert r.status_code == 403, r.text
    assert _anillos(await _feature(residente, plano, libre))[0][0] == (0.0, 0.0)  # el libre tampoco se movió


@pytest.mark.parametrize(
    "cuerpo",
    [{"dx": "1", "grados": "30"}, {}, {"dx": "0", "dy": "0", "grados": "0"}, {"grados": "400"}],
)
async def test_pedir_las_dos_cosas_o_ninguna_es_422(
    escenario: Escenario, residente: httpx.AsyncClient, cuerpo: dict
) -> None:
    plano = await _plano(residente, escenario)
    id_ = await _trazo(residente, escenario, plano, MURO_CON_VENTANA)
    r = await residente.post("/api/v1/trazos/transformar", json={"trazo_ids": [id_], **cuerpo})
    assert r.status_code == 422, (cuerpo, r.text)


async def test_un_trazo_inexistente_es_404_y_otra_organizacion_no_lo_ve(
    escenario: Escenario, residente: httpx.AsyncClient
) -> None:
    assert (await residente.post("/api/v1/trazos/transformar", json={"trazo_ids": [str(uuid.uuid4())], "dx": "1"})).status_code == 404
    plano = await _plano(residente, escenario)
    id_ = await _trazo(residente, escenario, plano, MURO_CON_VENTANA)
    ajeno = ContextoSesion(org_id=uuid.uuid4(), usuario_id=uuid.uuid4(), rol="control_obra")
    async with _cliente(ajeno) as c:
        assert (await c.post("/api/v1/trazos/transformar", json={"trazo_ids": [id_], "dx": "1"})).status_code == 404
