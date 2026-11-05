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


async def test_sin_la_tabla_de_vanos_se_sigue_midiendo(escenario: Escenario, control: httpx.AsyncClient) -> None:
    """Un despliegue del código antes de la migración 0103 no tumba la lectura de trazos (expand → contract)."""
    from obractrl.adapters.repos import cuantificacion_sql as repo

    plano, muro = await _muro(control, escenario, "longitud", "5.2")
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as conn:
            await conn.execute(text("alter table vano rename to vano_oculta"))
        repo._VANOS_DISPONIBLES = False
        r = await control.get(f"/api/v1/planos/{plano}/trazos")
        assert r.status_code == 200, r.text
        assert next(f for f in r.json()["features"] if f["id"] == muro)["properties"]["enlaces"][0]["cantidad"] is not None
    finally:
        async with motor.begin() as conn:
            await conn.execute(text("alter table vano_oculta rename to vano"))
        await motor.dispose()
        repo._VANOS_DISPONIBLES = False


async def test_los_vanos_del_plano_traen_donde_van_y_se_corren_por_el_muro(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano, muro = await _muro(control, escenario, "longitud", "5.2")  # LINESTRING(0 0, 10 0)
    centrada = (await control.post(f"/api/v1/trazos/{muro}/vanos", json=PUERTA)).json()["vano_id"]
    al_final = (await control.post(f"/api/v1/trazos/{muro}/vanos", json={**VENTANA, "posicion_m": "8"})).json()["vano_id"]

    vanos = {v["id"]: v for v in (await control.get(f"/api/v1/planos/{plano}/vanos")).json()}
    # Sin posición va a la mitad del muro (5 m); el muro corre de izquierda a derecha (0°).
    assert vanos[centrada]["x"] == pytest.approx(5.0) and vanos[centrada]["y"] == pytest.approx(0.0)
    assert vanos[centrada]["angulo"] == pytest.approx(0.0, abs=0.01) and vanos[centrada]["ancho_plano"] == pytest.approx(0.9)
    assert vanos[al_final]["x"] == pytest.approx(8.0)

    # Correrlo no cambia lo que mide el muro.
    antes = _total(await control.post(f"/api/v1/trazos/{muro}/vanos", json={**PUERTA, "clave": "P-09", "ancho_m": "0.9"}))
    assert (await control.patch(f"/api/v1/vanos/{centrada}/posicion", json={"posicion_m": "2.5"})).status_code == 204
    despues = (await control.get(f"/api/v1/planos/{plano}/vanos")).json()
    assert next(v for v in despues if v["id"] == centrada)["x"] == pytest.approx(2.5)
    assert antes is not None
    assert (await control.patch(f"/api/v1/vanos/{uuid.uuid4()}/posicion", json={"posicion_m": "1"})).status_code == 404
    assert (await control.patch(f"/api/v1/vanos/{centrada}/posicion", json={"posicion_m": "-1"})).status_code == 422


async def test_el_muro_cuenta_por_caras_y_por_partes_y_el_vano_descuenta_por_las_mismas_caras(
    escenario: Escenario, control: httpx.AsyncClient
) -> None:
    _, trazo = await _muro(control, escenario, "longitud", "5.2")
    ruta = f"/api/v1/trazos/{trazo}/muro"
    cuatro = Decimal("0.0001")

    por_defecto = (await control.get(ruta)).json()
    assert por_defecto["caras"] == 2 and por_defecto["partes"] is None

    # Una sola cara: 10 m × 2.6 m × 1 = 26 m².
    r = await control.put(ruta, json={"altura_m": "2.6", "caras": 1, "cara": "interior"})
    assert r.status_code == 200, r.text
    assert _total(r) == Decimal("26").quantize(cuatro)
    assert (await control.get(ruta)).json()["cara"] == "interior"

    # Altura por partes: lo que no suma (el cerramiento) cuenta para la altura pero no para la cantidad.
    partes = [
        {"nombre": "Muro", "desde_m": "0", "hasta_m": "2.3", "suma": True},
        {"nombre": "Cerramiento", "desde_m": "2.3", "hasta_m": "2.5", "suma": False},
    ]
    r = await control.put(ruta, json={"caras": 2, "partes": partes})
    assert r.status_code == 200, r.text
    assert Decimal((await control.get(ruta)).json()["altura_efectiva_m"]) == Decimal("2.3")
    assert _total(r) == Decimal("46").quantize(cuatro)  # 10 × 2.3 × 2

    # Un vano descuenta por las mismas caras: puerta 0.9 × 2.1 × 2 = 3.78 m².
    v = await control.post(f"/api/v1/trazos/{trazo}/vanos", json=PUERTA)
    assert _total(v) == (Decimal("46") - Decimal("3.78")).quantize(cuatro)

    # Con una cara el vano descuenta una sola vez.
    r = await control.put(ruta, json={"altura_m": "2.6", "caras": 1})
    assert _total(r) == (Decimal("26") - Decimal("1.89")).quantize(cuatro)

    mala = [{"nombre": "X", "desde_m": "2", "hasta_m": "1", "suma": True}]
    assert (await control.put(ruta, json={"caras": 2, "partes": mala})).status_code in (400, 422)
    assert (await control.put(ruta, json={"altura_m": "0.5", "caras": 2})).status_code in (400, 422)
