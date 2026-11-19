"""Zonas de losa 1.1 contra Postgres real: un muro NUEVO nace con la altura de su zona; si cruza zonas a lo largo de su recorrido cuenta por
TRAMOS LÓGICOS dentro de un solo trazo (cada vano en el tramo donde cae); en el límite 3.00/4.20 «Aplicar al muro» fija las partes de altura
por cara; sin zona sigue la altura estándar (3.00) y la altura que trae el trazo manda. Nada guardado se recalcula (Q1).

Dos cuartos de 6 × 4 m: el de 3.00 de x 0 a 6 y el de 4.20 de x 6 a 12 (y de -4 a 0).
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

D = Decimal
CONVERSION = {"modo": "area", "mide": "cara2", "cara": "int", "lado": "der"}


def _cliente(contexto: ContextoSesion) -> httpx.AsyncClient:
    app = crear_app()
    app.dependency_overrides[contexto_actual] = lambda: contexto
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test")


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
                text("insert into concepto (id, org_id, clave, descripcion) values (:id, :org, 'ZT-1', 'Aplanado')"),
                {"id": str(concepto), "org": str(escenario.org_id)},
            )
            await conn.execute(
                text("update actividad set concepto_id = :c, precio_unitario = 10, cant_base = 100, cant_programada = 100 where id = :id"),
                {"c": str(concepto), "id": str(escenario.actividad_id)},
            )
    finally:
        await motor.dispose()


async def _dos_cuartos(c: httpx.AsyncClient, esc: Escenario) -> str:
    plano = (await c.post(f"/api/v1/obras/{esc.obra_id}/planos", json={"nombre": "PB", "archivo_url": "e2e/pb.pdf"})).json()["id"]
    for nombre, altura, espesor, wkt in (
        ("Entrepiso 3.00", "3.00", "0.12", "POLYGON((0 -4, 6 -4, 6 0, 0 0, 0 -4))"),
        ("Entrepiso 4.20", "4.20", "0.20", "POLYGON((6 -4, 12 -4, 12 0, 6 0, 6 -4))"),
    ):
        z = await c.post(f"/api/v1/planos/{plano}/zonas-de-losa", json={"nombre": nombre, "altura_libre_m": altura, "espesor_m": espesor})
        losa = await c.post(
            f"/api/v1/planos/{plano}/trazos", json={"version_plano": 1, "fuente": "pdf", "geometria_wkt": wkt, "enlaces": []}
        )
        assert (await c.put(f"/api/v1/trazos/{losa.json()['trazo_id']}/losa", json={"zona_id": z.json()["id"]})).status_code == 200
    return plano


async def _muro(c: httpx.AsyncClient, esc: Escenario, plano: str, wkt: str, conversion: dict | None = None) -> dict:
    r = await c.post(
        f"/api/v1/planos/{plano}/trazos",
        json={
            "version_plano": 1, "fuente": "pdf", "geometria_wkt": wkt, "grosor_m": "0.15", "alineacion": "centro",
            "enlaces": [{"medida": "longitud", "factor": "1", "actividad_id": str(esc.actividad_id), "conversion": conversion or CONVERSION}],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _cant(c: httpx.AsyncClient, plano: str, trazo: str) -> Decimal:
    """Lo que mide ESE trazo (la cantidad del nodo suma todos los trazos de la actividad)."""
    feats = (await c.get(f"/api/v1/planos/{plano}/trazos")).json()["features"]
    f = next(f for f in feats if f["properties"]["trazo_id"] == trazo)
    return sum((D(str(e["cantidad"])) for e in f["properties"]["enlaces"] if e["vigente"]), D(0)).quantize(D("0.0001"))


async def _conversion_vigente(c: httpx.AsyncClient, plano: str, trazo: str) -> dict:
    feats = (await c.get(f"/api/v1/planos/{plano}/trazos")).json()["features"]
    enlace = next(e for f in feats if f["properties"]["trazo_id"] == trazo for e in f["properties"]["enlaces"] if e["vigente"])
    return (await c.get(f"/api/v1/enlaces/{enlace['enlace_id']}/conversion")).json()["conversion"]


async def test_un_muro_nuevo_bajo_una_sola_zona_nace_con_la_altura_de_su_zona(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano = await _dos_cuartos(control, escenario)
    # Un muro de 4 m bajo la losa de 4.20: 4 m × 4.20 × 2 caras. No nace con la altura estándar (3.00).
    r = await _muro(control, escenario, plano, "LINESTRING(7 -2, 11 -2)")
    assert await _cant(control, plano, r["trazo_id"]) == D("33.6000")
    conv = await _conversion_vigente(control, plano, r["trazo_id"])
    assert D(str(conv["alt"])) == D("4.2") and not conv.get("tramos")


async def test_sin_zona_el_muro_nace_con_3_m_y_la_altura_que_trae_manda(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano = await _dos_cuartos(control, escenario)
    lejos = await _muro(control, escenario, plano, "LINESTRING(30 -2, 34 -2)")
    assert await _cant(control, plano, lejos["trazo_id"]) == D("24.0000")  # 4 × 3.00 × 2: la altura estándar de la obra, no 2.60
    explicita = await _muro(control, escenario, plano, "LINESTRING(7 -2, 11 -2)", {**CONVERSION, "alt": 2.5})
    assert await _cant(control, plano, explicita["trazo_id"]) == D("20.0000")  # 4 × 2.50 × 2: la altura del trazo manda sobre la de la zona


async def test_un_muro_que_cruza_cuenta_por_tramos_y_cada_vano_cae_en_su_tramo(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano = await _dos_cuartos(control, escenario)
    r = await _muro(control, escenario, plano, "LINESTRING(2 -2, 10 -2)")
    # (4 m × 3.00 + 4 m × 4.20) × 2 caras = 57.60, en UN solo trazo.
    assert await _cant(control, plano, r["trazo_id"]) == D("57.6000")
    conv = await _conversion_vigente(control, plano, r["trazo_id"])
    assert [(t["desde_m"], t["hasta_m"], t["alt"]) for t in conv["tramos"]] == [(0, 4, 3), (4, 8, 4.2)]
    # Una puerta en el primer tramo (3.00) y otra en el segundo (4.20): cada una descuenta ancho × alto × 2 caras = 3.78.
    for posicion in ("1", "6"):
        v = await control.post(
            f"/api/v1/trazos/{r['trazo_id']}/vanos",
            json={"clave": f"P-{posicion}", "tipo": "puerta", "ancho_m": "0.9", "alto_m": "2.1", "posicion_m": posicion},
        )
        assert v.status_code == 201, v.text
    res = (await control.get(f"/api/v1/trazos/{r['trazo_id']}/zonas-de-losa")).json()
    assert [[v["clave"] for v in tramo] for tramo in res["vanos_por_tramo"]] == [["P-1"], ["P-6"]]
    assert res["parte_el_muro"] is True
    feats = (await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"]
    f = next(f for f in feats if f["properties"]["trazo_id"] == r["trazo_id"])
    assert D(str(f["properties"]["enlaces"][0]["cantidad"])).quantize(D("0.0001")) == D("50.0400")


async def test_aplicar_al_muro_le_da_la_altura_de_su_zona_y_no_toca_otros_trazos(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano = await _dos_cuartos(control, escenario)
    # Un muro con su altura (explícita) en la zona de 4.20 y otro igual: aplicar a uno no mueve al otro.
    a = await _muro(control, escenario, plano, "LINESTRING(7 -1, 11 -1)", {**CONVERSION, "alt": 3.0})
    b = await _muro(control, escenario, plano, "LINESTRING(7 -3, 11 -3)", {**CONVERSION, "alt": 3.0})
    assert await _cant(control, plano, a["trazo_id"]) == await _cant(control, plano, b["trazo_id"]) == D("24.0000")
    # La conversión trae su altura: eso es altura del trazo y la zona solo sugiere; al aplicar, la persona decide por la zona.
    r = await control.post(f"/api/v1/trazos/{a['trazo_id']}/zonas-de-losa/aplicar")
    assert r.status_code == 200, r.text
    assert r.json()["enlaces_aplicados"] == 1
    feats = (await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"]
    cantidades = {
        f["properties"]["trazo_id"]: [D(str(e["cantidad"])) for e in f["properties"]["enlaces"] if e["vigente"]]
        for f in feats
        if f["geometry"]["type"] == "LineString"
    }
    assert cantidades[a["trazo_id"]] == [D("33.6")] and cantidades[b["trazo_id"]] == [D("24")]
    # Un muro fuera de toda zona no tiene qué aplicar.
    lejos = await _muro(control, escenario, plano, "LINESTRING(30 -2, 34 -2)")
    assert (await control.post(f"/api/v1/trazos/{lejos['trazo_id']}/zonas-de-losa/aplicar")).status_code == 422


async def test_en_el_limite_aplicar_fija_las_partes_por_cara_con_el_enrase(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano = await _dos_cuartos(control, escenario)
    # Se traza UNA vez a 4.20 sobre el límite; dibujado hacia arriba, la cara A (izquierda) es la de la losa de 3.00.
    r = await _muro(control, escenario, plano, "LINESTRING(6 0, 6 -4)", {**CONVERSION, "alt": 4.2})
    res = (await control.get(f"/api/v1/trazos/{r['trazo_id']}/zonas-de-losa")).json()
    t = res["tramos"][0]
    assert [p["rol"] for p in t["partes"]] == ["cuerpo", "enrase"]
    assert (t["partes"][1]["cara_a"], t["partes"][1]["cara_b"]) == ("exterior", "interior")
    a = await control.post(f"/api/v1/trazos/{r['trazo_id']}/zonas-de-losa/aplicar")
    assert a.status_code == 200, a.text
    muro = (await control.get(f"/api/v1/trazos/{r['trazo_id']}/muro")).json()
    assert [(p["rol"], D(str(p["desde_m"])), D(str(p["hasta_m"])), p["cara_a"], p["cara_b"]) for p in muro["partes"]] == [
        ("cuerpo", D(0), D(3), "interior", "interior"),
        ("enrase", D(3), D("4.2"), "exterior", "interior"),
    ]
    conv = await _conversion_vigente(control, plano, r["trazo_id"])
    assert [(p["rol"], p.get("cara_a"), p.get("cara_b")) for p in conv["partes"]] == [
        ("cuerpo", "interior", "interior"), ("enrase", "exterior", "interior"),
    ]
    # 4 m × 4.20 × 2 caras: la altura por cara reparte interior y exterior, no cambia la superficie.
    feats = (await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"]
    f = next(f for f in feats if f["properties"]["trazo_id"] == r["trazo_id"])
    assert D(str(f["properties"]["enlaces"][0]["cantidad"])) == D("33.6")
