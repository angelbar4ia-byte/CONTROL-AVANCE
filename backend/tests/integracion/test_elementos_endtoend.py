"""Elementos con peso y medición derivada (migración 0089).

Por HTTP contra Postgres real:

 1. un elemento (K1) tiene un peso por pieza; solo Control de obra y Costos lo ponen;
 2. una medición de conteo con ese elemento, asignada a un concepto en kg «con el peso», suma
    conteo × peso; en ton, ese peso ÷ 1000;
 3. cambiar el peso rehace las asignaciones: lo viejo queda como evidencia y la cantidad se actualiza;
 4. el peso solo alimenta conceptos en kg o ton; un conteo normal sigue pidiendo factor entero.
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


async def _concepto_con_unidad(escenario: Escenario, unidad: str) -> None:
    """Le da a la actividad del escenario un concepto con esa unidad (el escenario no trae concepto)."""
    engine = create_async_engine(DATABASE_URL_ADMIN)
    async with engine.begin() as conn:
        unidad_id = (
            await conn.execute(
                text(
                    "insert into unidad (org_id, clave, nombre) values (:org, :clave, :clave) returning id"
                ),
                {"org": str(escenario.org_id), "clave": unidad},
            )
        ).scalar_one()
        concepto_id = (
            await conn.execute(
                text(
                    "insert into concepto (org_id, tipo, clave, descripcion, unidad_id) "
                    "values (:org, 'concepto', :clave, 'Acero de refuerzo', :unidad) returning id"
                ),
                {"org": str(escenario.org_id), "clave": f"ACE-{uuid.uuid4().hex[:5]}", "unidad": str(unidad_id)},
            )
        ).scalar_one()
        await conn.execute(
            text("update actividad set concepto_id = :c where id = :a"),
            {"c": str(concepto_id), "a": str(escenario.actividad_id)},
        )
    await engine.dispose()


async def _plano(control: httpx.AsyncClient, escenario: Escenario) -> str:
    r = await control.post(
        f"/api/v1/obras/{escenario.obra_id}/planos",
        json={"nombre": f"P{uuid.uuid4().hex[:6]}", "archivo_url": "r2://p"},
    )
    return str(r.json()["id"])


async def _castillos(control: httpx.AsyncClient, plano: str, n: int = 3) -> tuple[str, list[str]]:
    r = await control.post(f"/api/v1/planos/{plano}/mediciones", json={"nombre": "Castillos K1", "tipo": "conteo"})
    medicion = str(r.json()["id"])
    trazos = []
    for i in range(n):
        t = await control.post(
            f"/api/v1/planos/{plano}/trazos",
            json={
                "version_plano": 1,
                "geometria_wkt": f"POINT({i * 10} 5)",
                "fuente": "pdf",
                "enlaces": [],
                "medicion_id": medicion,
            },
        )
        assert t.status_code == 201, t.text
        trazos.append(str(t.json()["trazo_id"]))
    return medicion, trazos


async def _elemento(control: httpx.AsyncClient, nombre: str = "K1", tipo: str = "conteo", peso: str = "38") -> str:
    r = await control.post("/api/v1/elementos", json={"nombre": nombre, "tipo": tipo, "peso_kg": peso})
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


async def _cantidad(control, escenario: Escenario) -> Decimal:
    nodos = (await control.get(f"/api/v1/obras/{escenario.obra_id}/cuantificacion")).json()
    fila = next((n for n in nodos if n["nodo_id"] == str(escenario.actividad_id)), None)
    return Decimal(str(fila["cantidad_medida"])) if fila else Decimal(0)


async def test_solo_control_y_costos_ponen_el_peso_y_el_nombre_no_se_repite(
    control: httpx.AsyncClient, residente: httpx.AsyncClient
) -> None:
    k1 = await _elemento(control, "K1")
    body = {"nombre": "K2", "tipo": "conteo", "peso_kg": "40"}
    assert (await residente.post("/api/v1/elementos", json=body)).status_code == 403
    assert (await residente.patch(f"/api/v1/elementos/{k1}", json={"peso_kg": "50"})).status_code == 403
    assert (await residente.delete(f"/api/v1/elementos/{k1}")).status_code == 403
    # El residente sí los ve (es para que sepa qué elemento usa).
    assert any(e["nombre"] == "K1" for e in (await residente.get("/api/v1/elementos")).json())

    assert (await control.post("/api/v1/elementos", json={**body, "nombre": " k1 "})).status_code == 422
    assert (await control.post("/api/v1/elementos", json={**body, "peso_kg": "0"})).status_code == 422
    assert (await control.patch(f"/api/v1/elementos/{k1}", json={"nombre": "k1"})).status_code == 200
    assert (await control.patch(f"/api/v1/elementos/{uuid.uuid4()}", json={"peso_kg": "1"})).status_code == 404


async def test_el_peso_por_cantidad_alimenta_un_concepto_en_kg(
    control: httpx.AsyncClient, escenario: Escenario
) -> None:
    plano = await _plano(control, escenario)
    medicion, _ = await _castillos(control, plano, 3)
    k1 = await _elemento(control, "K1", peso="38")

    async def asignar(usar_peso: bool = True, medida: str = "conteo", factor: str = "1") -> httpx.Response:
        return await control.post(
            f"/api/v1/mediciones/{medicion}/asignaciones",
            json={"actividad_id": str(escenario.actividad_id), "medida": medida, "factor": factor, "usar_peso": usar_peso},
        )

    # Sin elemento en la medición, o con un concepto sin unidad de peso, no hay derivada.
    assert (await asignar()).status_code == 422
    assert (await control.put(f"/api/v1/mediciones/{medicion}/elemento", json={"elemento_id": k1})).status_code == 200
    assert (await asignar()).status_code == 422  # el concepto del escenario no tiene unidad

    await _concepto_con_unidad(escenario, "kg")
    assert (await asignar(medida="area")).status_code == 422  # el peso es por pieza: se asigna con «conteo»
    r = await asignar()
    assert r.status_code == 201, r.text
    asignacion = r.json()["id"]
    assert await _cantidad(control, escenario) == 114  # 3 castillos × 38 kg

    lista = (await control.get(f"/api/v1/planos/{plano}/mediciones")).json()
    m = next(x for x in lista if x["id"] == medicion)
    assert m["elemento"]["nombre"] == "K1" and Decimal(m["elemento"]["peso_kg"]) == 38
    assert m["asignaciones"][0]["usa_peso"] is True and Decimal(m["asignaciones"][0]["factor"]) == 38

    # Cambiar el peso rehace la asignación: lo viejo queda como evidencia y la cantidad se actualiza.
    c = await control.patch(f"/api/v1/elementos/{k1}", json={"peso_kg": "40"})
    assert c.status_code == 200, c.text
    assert await _cantidad(control, escenario) == 120
    trazos = (await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"]
    for f in trazos:
        vigentes = [e for e in f["properties"]["enlaces"] if e["vigente"]]
        viejos = [e for e in f["properties"]["enlaces"] if not e["vigente"]]
        assert len(vigentes) == 1 and Decimal(str(vigentes[0]["factor"])) == 40
        assert len(viejos) == 1 and Decimal(str(viejos[0]["factor"])) == 38
    # Cambiar solo el nombre no toca nada.
    assert (await control.patch(f"/api/v1/elementos/{k1}", json={"nombre": "Castillo K1"})).status_code == 200
    assert await _cantidad(control, escenario) == 120

    # Un trazo que entra después a la medición hereda la derivada.
    nuevo = await control.post(
        f"/api/v1/planos/{plano}/trazos",
        json={"version_plano": 1, "geometria_wkt": "POINT(99 5)", "fuente": "pdf", "enlaces": [], "medicion_id": medicion},
    )
    assert nuevo.status_code == 201
    assert await _cantidad(control, escenario) == 160

    # El elemento no se borra ni se le quita a la medición mientras algo dependa de su peso.
    assert (await control.delete(f"/api/v1/elementos/{k1}")).status_code == 422
    assert (await control.put(f"/api/v1/mediciones/{medicion}/elemento", json={"elemento_id": None})).status_code == 422
    # Quitada la asignación, ya se puede.
    assert (await control.delete(f"/api/v1/asignaciones-de-medicion/{asignacion}")).status_code == 200
    assert await _cantidad(control, escenario) == 0
    assert (await control.put(f"/api/v1/mediciones/{medicion}/elemento", json={"elemento_id": None})).status_code == 200
    assert (await control.delete(f"/api/v1/elementos/{k1}")).status_code == 204


async def test_en_toneladas_el_peso_se_divide_entre_mil(
    control: httpx.AsyncClient, escenario: Escenario
) -> None:
    plano = await _plano(control, escenario)
    medicion, _ = await _castillos(control, plano, 4)
    k1 = await _elemento(control, "K1", peso="38")
    await control.put(f"/api/v1/mediciones/{medicion}/elemento", json={"elemento_id": k1})
    await _concepto_con_unidad(escenario, "ton")
    r = await control.post(
        f"/api/v1/mediciones/{medicion}/asignaciones",
        json={"actividad_id": str(escenario.actividad_id), "medida": "conteo", "usar_peso": True},
    )
    assert r.status_code == 201, r.text
    assert await _cantidad(control, escenario) == Decimal("0.152")  # 4 × 38 kg = 152 kg


async def test_el_elemento_es_del_mismo_tipo_que_la_medicion_y_un_conteo_normal_pide_factor_entero(
    control: httpx.AsyncClient, escenario: Escenario
) -> None:
    plano = await _plano(control, escenario)
    medicion, _ = await _castillos(control, plano, 2)
    varilla = await _elemento(control, "Varilla 3/8", tipo="lineal", peso="0.56")
    assert (await control.put(f"/api/v1/mediciones/{medicion}/elemento", json={"elemento_id": varilla})).status_code == 422
    # Sin usar el peso, el conteo sigue siendo de factor entero.
    r = await control.post(
        f"/api/v1/mediciones/{medicion}/asignaciones",
        json={"actividad_id": str(escenario.actividad_id), "medida": "conteo", "factor": "2.5"},
    )
    assert r.status_code == 422
