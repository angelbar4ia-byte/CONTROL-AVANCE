"""Mediciones, la capa sombra del cuantificador (migración 0088).

Por HTTP contra Postgres real:

 1. se crean mediciones y submedicion es (del mismo tipo), sin repetir nombre entre hermanas;
 2. un trazo solo entra a una medición de su tipo;
 3. asignar una medición a un concepto enlaza los trazos de ella y de sus submediciones, y un trazo
    que entra después hereda el enlace; la cantidad del concepto es la suma;
 4. sacar un trazo, quitar la asignación o borrar la medición deja las cantidades coherentes;
 5. la misma medida del mismo concepto no se asigna dos veces en una rama.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
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
async def control(contexto_control: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_control) as c:
        yield c


async def _plano(control: httpx.AsyncClient, escenario: Escenario) -> str:
    r = await control.post(
        f"/api/v1/obras/{escenario.obra_id}/planos",
        json={"nombre": f"P{uuid.uuid4().hex[:6]}", "archivo_url": "r2://p"},
    )
    return str(r.json()["id"])


async def _medicion(control, plano: str, nombre: str, tipo: str = "area", parent: str | None = None) -> str:
    r = await control.post(
        f"/api/v1/planos/{plano}/mediciones", json={"nombre": nombre, "tipo": tipo, "parent_id": parent}
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


async def _trazo(control, plano: str, wkt: str, **extra) -> str:
    r = await control.post(
        f"/api/v1/planos/{plano}/trazos",
        json={"version_plano": 1, "geometria_wkt": wkt, "fuente": "pdf", "enlaces": [], **extra},
    )
    assert r.status_code == 201, r.text
    return str(r.json()["trazo_id"])


async def _cantidad(control, escenario: Escenario) -> Decimal:
    nodos = (await control.get(f"/api/v1/obras/{escenario.obra_id}/cuantificacion")).json()
    fila = next((n for n in nodos if n["nodo_id"] == str(escenario.actividad_id)), None)
    return Decimal(str(fila["cantidad_medida"])) if fila else Decimal(0)


async def _asignar(control, medicion: str, escenario: Escenario, medida: str = "area", factor: str = "1"):
    return await control.post(
        f"/api/v1/mediciones/{medicion}/asignaciones",
        json={"actividad_id": str(escenario.actividad_id), "medida": medida, "factor": factor},
    )


CUADRADO_10 = "POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))"
CUADRADO_4 = "POLYGON((20 0, 24 0, 24 4, 20 4, 20 0))"


async def test_las_mediciones_anidan_del_mismo_tipo_y_no_repiten_nombre(
    control: httpx.AsyncClient, escenario: Escenario
) -> None:
    plano = await _plano(control, escenario)
    losa = await _medicion(control, plano, "Losa de cimentación")
    await _medicion(control, plano, "Recámara 1", parent=losa)
    # El mismo nombre en otro lugar sí; entre hermanas no.
    await _medicion(control, plano, "Recámara 1")
    r = await control.post(
        f"/api/v1/planos/{plano}/mediciones", json={"nombre": " recámara   1 ", "tipo": "area", "parent_id": losa}
    )
    assert r.status_code == 422
    # Una submedición es del mismo tipo que su madre.
    r = await control.post(
        f"/api/v1/planos/{plano}/mediciones", json={"nombre": "Muro", "tipo": "lineal", "parent_id": losa}
    )
    assert r.status_code == 422
    assert (await control.post(f"/api/v1/planos/{plano}/mediciones", json={"nombre": "  ", "tipo": "area"})).status_code == 422

    lista = (await control.get(f"/api/v1/planos/{plano}/mediciones")).json()
    assert {m["nombre"] for m in lista} == {"Losa de cimentación", "Recámara 1"}.union({"Recámara 1"})
    assert next(m for m in lista if m["nombre"] == "Recámara 1" and m["parent_id"] == losa)["unidad"] == "m²"


async def test_un_trazo_solo_entra_a_una_medicion_de_su_tipo(
    control: httpx.AsyncClient, escenario: Escenario
) -> None:
    plano = await _plano(control, escenario)
    area = await _medicion(control, plano, "Áreas")
    lineal = await _medicion(control, plano, "Muros", tipo="lineal")
    conteo = await _medicion(control, plano, "Castillos K1", tipo="conteo")

    poligono = await _trazo(control, plano, CUADRADO_10)
    linea = await _trazo(control, plano, "LINESTRING(0 0, 10 0)")
    punto = await _trazo(control, plano, "POINT(5 5)")
    castillo = await _trazo(
        control, plano, CUADRADO_4, forma={"tipo": "cuadrado", "ancho_m": "0.15", "alto_m": "0.15"}
    )

    async def poner(trazo: str, medicion: str | None) -> int:
        return (await control.put(f"/api/v1/trazos/{trazo}/medicion", json={"medicion_id": medicion})).status_code

    assert await poner(poligono, area) == 200
    assert await poner(linea, lineal) == 200
    assert await poner(punto, conteo) == 200
    assert await poner(castillo, conteo) == 200  # una pieza estampada se cuenta
    assert await poner(castillo, area) == 422  # y no es un área
    assert await poner(poligono, lineal) == 422
    assert await poner(linea, area) == 422
    assert await poner(poligono, str(uuid.uuid4())) == 404

    lista = {m["nombre"]: m for m in (await control.get(f"/api/v1/planos/{plano}/mediciones")).json()}
    assert lista["Áreas"]["n_trazos"] == 1 and Decimal(lista["Áreas"]["valor"]) == 100
    assert Decimal(lista["Muros"]["valor"]) == 10
    assert lista["Castillos K1"]["n_trazos"] == 2 and Decimal(lista["Castillos K1"]["valor"]) == 2


async def test_asignar_una_medicion_enlaza_sus_trazos_y_los_de_sus_submediciones(
    control: httpx.AsyncClient, escenario: Escenario
) -> None:
    plano = await _plano(control, escenario)
    losa = await _medicion(control, plano, "Losa")
    r1 = await _medicion(control, plano, "Recámara 1", parent=losa)
    r2 = await _medicion(control, plano, "Recámara 2", parent=losa)
    t1 = await _trazo(control, plano, CUADRADO_10)
    t2 = await _trazo(control, plano, CUADRADO_4)
    assert (await control.put(f"/api/v1/trazos/{t1}/medicion", json={"medicion_id": r1})).status_code == 200
    assert (await control.put(f"/api/v1/trazos/{t2}/medicion", json={"medicion_id": r2})).status_code == 200
    assert await _cantidad(control, escenario) == 0  # una medición suelta no suma a ningún concepto

    # La losa se asigna al concepto: suma lo de sus dos recámaras.
    r = await _asignar(control, losa, escenario)
    assert r.status_code == 201, r.text
    asignacion = r.json()["id"]
    assert r.json()["trazos_enlazados"] == 2
    assert await _cantidad(control, escenario) == 116

    # La misma medida del mismo concepto no se asigna otra vez en la rama (se contaría doble).
    assert (await _asignar(control, r1, escenario)).status_code == 422
    assert (await _asignar(control, losa, escenario)).status_code == 422
    # Otra medida distinta (el perímetro) sí, y no es la misma cantidad.
    assert (await _asignar(control, r1, escenario, medida="perimetro")).status_code == 201
    # Una medida que no es del tipo, no.
    assert (await _asignar(control, r2, escenario, medida="longitud")).status_code == 422

    # Un trazo que entra después hereda los enlaces de su medición y de la que la contiene.
    t3 = await _trazo(control, plano, "POLYGON((30 0, 35 0, 35 2, 30 2, 30 0))", medicion_id=r2)
    assert await _cantidad(control, escenario) == 166  # 116 de área + 40 del perímetro de r1 + 10 del trazo nuevo
    trazos = (await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"]
    nuevo = next(f for f in trazos if f["id"] == t3)
    assert nuevo["properties"]["medicion_id"] == r2
    assert any(e["medida"] == "area" and e["vigente"] for e in nuevo["properties"]["enlaces"])

    # Sacar el trazo de su medición quita los enlaces que le vinieron de ella.
    assert (await control.put(f"/api/v1/trazos/{t3}/medicion", json={"medicion_id": None})).status_code == 200
    trazos = (await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"]
    nuevo = next(f for f in trazos if f["id"] == t3)
    assert nuevo["properties"]["medicion_id"] is None
    assert not any(e["vigente"] for e in nuevo["properties"]["enlaces"])
    assert await _cantidad(control, escenario) == 156

    # Quitar la asignación deja el concepto sin esa cantidad, y la medición ya se puede borrar.
    assert (await control.delete(f"/api/v1/mediciones/{losa}")).status_code == 422  # alimenta un concepto
    q = await control.delete(f"/api/v1/asignaciones-de-medicion/{asignacion}")
    assert q.status_code == 200, q.text
    assert q.json()["trazos_enlazados"] == 2
    assert await _cantidad(control, escenario) == 40  # queda el perímetro de la recámara 1
    assert (await control.delete(f"/api/v1/mediciones/{losa}")).status_code == 422  # todavía tiene recámaras
    for hija in (r1, r2):
        for a in next(m for m in (await control.get(f"/api/v1/planos/{plano}/mediciones")).json() if m["id"] == hija)[
            "asignaciones"
        ]:
            assert (await control.delete(f"/api/v1/asignaciones-de-medicion/{a['id']}")).status_code == 200
        assert (await control.delete(f"/api/v1/mediciones/{hija}")).status_code == 204
    assert await _cantidad(control, escenario) == 0
    assert (await control.delete(f"/api/v1/mediciones/{losa}")).status_code == 204
    # Los trazos de las recámaras borradas quedan sueltos, no desaparecen.
    trazos = (await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"]
    assert {f["id"] for f in trazos} >= {t1, t2}
    assert all(f["properties"]["medicion_id"] is None for f in trazos)


async def test_un_trazo_nuevo_en_una_medicion_de_otro_tipo_se_rechaza_sin_guardarlo(
    control: httpx.AsyncClient, escenario: Escenario
) -> None:
    plano = await _plano(control, escenario)
    lineal = await _medicion(control, plano, "Muros", tipo="lineal")
    r = await control.post(
        f"/api/v1/planos/{plano}/trazos",
        json={"version_plano": 1, "geometria_wkt": CUADRADO_10, "fuente": "pdf", "enlaces": [], "medicion_id": lineal},
    )
    assert r.status_code == 422
    assert (await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"] == []


async def test_renombrar_y_el_nombre_no_se_repite_entre_hermanas(
    control: httpx.AsyncClient, escenario: Escenario
) -> None:
    plano = await _plano(control, escenario)
    a = await _medicion(control, plano, "Cocina")
    await _medicion(control, plano, "Baño")
    assert (await control.patch(f"/api/v1/mediciones/{a}", json={"nombre": "Cocina integral"})).status_code == 204
    assert (await control.patch(f"/api/v1/mediciones/{a}", json={"nombre": "baño"})).status_code == 422
    assert (await control.patch(f"/api/v1/mediciones/{uuid.uuid4()}", json={"nombre": "x"})).status_code == 404
