"""Vanos (puertas, ventanas, pasos) sobre una línea: descuentan lo que mide, contra Postgres real.

Un muro de 10 m sobre un concepto en m² (factor 5.2 = 2.6 m × 2 caras) mide 52 m²; una puerta de 0.9 × 2.1 en un
muro de 2 caras descuenta 0.9 × 2.1 × 2 = 3.78 m². Sobre un concepto en metros (factor 1) solo restan los vanos
que llegan al piso: la puerta sí (0.9 m), la ventana no.
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

MURO = "LINESTRING(0 0, 10 0)"
PUERTA = {"clave": "P-01", "tipo": "puerta", "ancho_m": "0.9", "alto_m": "2.1"}
VENTANA = {"clave": "V-01", "tipo": "ventana", "ancho_m": "1.2", "alto_m": "1.2", "antepecho_m": "0.9"}


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


@pytest.fixture(autouse=True)
async def _actividad_con_concepto(escenario: Escenario) -> None:
    motor = create_async_engine(DATABASE_URL_ADMIN)
    concepto = uuid.uuid4()
    try:
        async with motor.begin() as conn:
            await conn.execute(
                text("insert into concepto (id, org_id, clave, descripcion) values (:id, :org, 'VAN-1', 'Aplanado')"),
                {"id": str(concepto), "org": str(escenario.org_id)},
            )
            await conn.execute(
                text("update actividad set concepto_id = :c, precio_unitario = 10, cant_base = 100, cant_programada = 100 where id = :id"),
                {"c": str(concepto), "id": str(escenario.actividad_id)},
            )
    finally:
        await motor.dispose()


async def _muro(cliente: httpx.AsyncClient, escenario: Escenario, medida: str, factor: str) -> tuple[str, str]:
    r = await cliente.post(f"/api/v1/obras/{escenario.obra_id}/planos", json={"nombre": "P", "archivo_url": "e2e/p.pdf"})
    plano = r.json()["id"]
    r = await cliente.post(
        f"/api/v1/planos/{plano}/trazos",
        json={
            "version_plano": 1,
            "fuente": "pdf",
            "geometria_wkt": MURO,
            "enlaces": [{"medida": medida, "factor": factor, "actividad_id": str(escenario.actividad_id)}],
        },
    )
    assert r.status_code == 201, r.text
    return plano, r.json()["trazo_id"]


def _total(r: httpx.Response) -> Decimal:
    return Decimal(str(r.json()["recalculos"][0]["cantidad_total"])).quantize(Decimal("0.0001"))


async def test_una_puerta_descuenta_ancho_alto_y_caras_en_m2(escenario: Escenario, control: httpx.AsyncClient) -> None:
    _, muro = await _muro(control, escenario, "longitud", "5.2")
    r = await control.post(f"/api/v1/trazos/{muro}/vanos", json=PUERTA)
    assert r.status_code == 201, r.text
    assert _total(r) == (Decimal("52") - Decimal("3.78")).quantize(Decimal("0.0001"))

    # Dos piezas idénticas de la ventana: 1.2 × 1.2 × 2 piezas × 2 caras = 5.76.
    r2 = await control.post(f"/api/v1/trazos/{muro}/vanos", json={**VENTANA, "piezas": 2})
    assert _total(r2) == (Decimal("52") - Decimal("3.78") - Decimal("5.76")).quantize(Decimal("0.0001"))

    vanos = (await control.get(f"/api/v1/trazos/{muro}/vanos")).json()
    assert [v["clave"] for v in vanos] == ["P-01", "V-01"]
    assert [v["llega_al_piso"] for v in vanos] == [True, False]

    # Quitar la puerta devuelve su descuento.
    q = await control.delete(f"/api/v1/vanos/{vanos[0]['id']}")
    assert q.status_code == 200, q.text
    assert _total(q) == (Decimal("52") - Decimal("5.76")).quantize(Decimal("0.0001"))


async def test_en_metros_solo_restan_los_vanos_que_llegan_al_piso(escenario: Escenario, control: httpx.AsyncClient) -> None:
    _, muro = await _muro(control, escenario, "longitud", "1")
    assert _total(await control.post(f"/api/v1/trazos/{muro}/vanos", json=VENTANA)) == Decimal("10.0000")
    assert _total(await control.post(f"/api/v1/trazos/{muro}/vanos", json=PUERTA)) == Decimal("9.1000")


async def test_un_vano_solo_va_en_una_linea_y_valida_sus_medidas(escenario: Escenario, control: httpx.AsyncClient) -> None:
    r = await control.post(f"/api/v1/obras/{escenario.obra_id}/planos", json={"nombre": "P", "archivo_url": "e2e/p.pdf"})
    plano = r.json()["id"]
    area = await control.post(
        f"/api/v1/planos/{plano}/trazos",
        json={"version_plano": 1, "fuente": "pdf", "geometria_wkt": "POLYGON((0 0, 4 0, 4 4, 0 4, 0 0))", "enlaces": []},
    )
    assert (await control.post(f"/api/v1/trazos/{area.json()['trazo_id']}/vanos", json=PUERTA)).status_code == 422
    _, muro = await _muro(control, escenario, "longitud", "5.2")
    assert (await control.post(f"/api/v1/trazos/{muro}/vanos", json={**PUERTA, "ancho_m": "0"})).status_code == 422
    assert (await control.post(f"/api/v1/trazos/{uuid.uuid4()}/vanos", json=PUERTA)).status_code == 404
    assert (await control.delete(f"/api/v1/vanos/{uuid.uuid4()}")).status_code == 404
