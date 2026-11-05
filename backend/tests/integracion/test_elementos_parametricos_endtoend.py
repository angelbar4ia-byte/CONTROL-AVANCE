"""Elementos paramétricos del catálogo (`/elementos-parametricos`), por HTTP contra Postgres real."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest

from obractrl.adapters.api.dependencias import contexto_actual
from obractrl.infrastructure.db.sesion import ContextoSesion
from obractrl.main import crear_app


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


@pytest.fixture
async def residente(contexto_residente: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_residente) as c:
        yield c


async def test_se_define_un_castillo_y_su_receta_sale_del_servidor(control: httpx.AsyncClient) -> None:
    r = await control.post(
        "/api/v1/elementos-parametricos", json={"clave": "k-1", "nombre": "Castillo K-1", "tipo": "castillo"}
    )
    assert r.status_code == 201, r.text
    elemento = r.json()["id"]

    lista = (await control.get("/api/v1/elementos-parametricos")).json()
    k1 = next(e for e in lista if e["id"] == elemento)
    assert k1["clave"] == "K-1" and k1["tipo"] == "castillo"
    assert k1["parametros"]["alto"] == 2.6  # lo que no se dijo toma el valor por defecto
    assert k1["receta"]["concreto"] == pytest.approx(0.0585)

    # Cambiar solo la altura conserva el resto del armado y rehace la receta.
    assert (await control.patch(f"/api/v1/elementos-parametricos/{elemento}", json={"parametros": {"alto": 3.0}})).status_code == 204
    k1 = next(e for e in (await control.get("/api/v1/elementos-parametricos")).json() if e["id"] == elemento)
    assert k1["parametros"]["n_var"] == 4
    assert k1["receta"]["concreto"] == pytest.approx(0.15 * 0.15 * 3.0)

    assert (await control.delete(f"/api/v1/elementos-parametricos/{elemento}")).status_code == 204
    assert (await control.delete(f"/api/v1/elementos-parametricos/{elemento}")).status_code == 404


async def test_validaciones_y_roles(control: httpx.AsyncClient, residente: httpx.AsyncClient) -> None:
    cuerpo = {"clave": "TR-1", "nombre": "Trabe", "tipo": "lineal"}
    assert (await residente.post("/api/v1/elementos-parametricos", json=cuerpo)).status_code == 403
    assert (await control.post("/api/v1/elementos-parametricos", json=cuerpo)).status_code == 201
    assert (await control.post("/api/v1/elementos-parametricos", json={**cuerpo, "clave": "tr-1"})).status_code == 422
    assert (
        await control.post(
            "/api/v1/elementos-parametricos", json={**cuerpo, "clave": "TR-2", "parametros": {"no_sup": 7}}
        )
    ).status_code == 422
    # Lo puede ver cualquiera de la organización.
    assert (await residente.get("/api/v1/elementos-parametricos")).status_code == 200
    tipos = (await residente.get("/api/v1/elementos-parametricos/tipos")).json()
    assert {t["tipo"]: t["unidad"] for t in tipos} == {"castillo": "pza", "lineal": "ml", "zapata": "pza", "losa": "m²"}


async def _plano_con_trazos(cliente: httpx.AsyncClient, escenario) -> tuple[str, dict[str, str]]:
    r = await cliente.post(f"/api/v1/obras/{escenario.obra_id}/planos", json={"nombre": "P", "archivo_url": "e2e/p.pdf"})
    plano = r.json()["id"]
    ids = {}
    for nombre, wkt in (
        ("punto", "POINT(1 1)"),
        ("punto2", "POINT(5 5)"),
        ("linea", "LINESTRING(0 0, 10 0)"),
        ("area", "POLYGON((0 0, 4 0, 4 3, 0 3, 0 0))"),
    ):
        t = await cliente.post(
            f"/api/v1/planos/{plano}/trazos", json={"version_plano": 1, "fuente": "pdf", "geometria_wkt": wkt, "enlaces": []}
        )
        assert t.status_code == 201, t.text
        ids[nombre] = t.json()["trazo_id"]
    return plano, ids


async def test_el_plano_suma_lo_que_llevan_los_elementos_colocados(escenario, control: httpx.AsyncClient) -> None:
    plano, t = await _plano_con_trazos(control, escenario)
    k1 = (await control.post("/api/v1/elementos-parametricos", json={"clave": "K-1", "nombre": "Castillo", "tipo": "castillo"})).json()["id"]
    tr1 = (await control.post("/api/v1/elementos-parametricos", json={"clave": "TR-1", "nombre": "Trabe", "tipo": "lineal"})).json()["id"]
    l1 = (await control.post("/api/v1/elementos-parametricos", json={"clave": "L-1", "nombre": "Losa", "tipo": "losa"})).json()["id"]

    ok = lambda elem, trazo, **extra: control.put(  # noqa: E731
        f"/api/v1/trazos/{trazo}/elemento-parametrico", json={"elemento_id": elem, **extra}
    )
    assert (await ok(k1, t["punto"])).status_code == 204
    assert (await ok(k1, t["punto2"], lados_cimbra=3)).status_code == 204  # junto a un vano
    assert (await ok(tr1, t["linea"])).status_code == 204
    assert (await ok(l1, t["area"])).status_code == 204

    r = (await control.get(f"/api/v1/planos/{plano}/elementos-parametricos")).json()
    por_clave = {x["clave"]: x for x in r["totales"]}
    k = por_clave["K-1"]
    assert (k["colocados"], k["cantidad"]) == (2, 2)
    assert k["concreto_m3"] == pytest.approx(2 * 0.0585)
    # Un castillo aislado lleva 4 lados (1.56 m²); el otro, fijado a 3 junto a un vano (1.17 m²).
    assert k["cimbra_m2"] == pytest.approx(1.56 + 1.17)
    assert k["cimbra_por_lados"] == {"3": pytest.approx(1.17), "4": pytest.approx(1.56)}
    # La trabe: 10 m × (0.2 × 0.4) de concreto; 3 lados = 1.0 m² por metro.
    assert por_clave["TR-1"]["cantidad"] == pytest.approx(10)
    assert por_clave["TR-1"]["concreto_m3"] == pytest.approx(0.8)
    assert por_clave["TR-1"]["cimbra_m2"] == pytest.approx(10.0)
    # La losa: 12 m² × 0.1 m de espesor.
    assert por_clave["L-1"]["cantidad"] == pytest.approx(12)
    assert por_clave["L-1"]["concreto_m3"] == pytest.approx(1.2)
    assert {x["trazo_id"] for x in r["trazos"]} == set(t.values())

    # Quitar la marca la saca de los totales.
    assert (await ok(None, t["punto"])).status_code == 204
    r = (await control.get(f"/api/v1/planos/{plano}/elementos-parametricos")).json()
    assert {x["clave"]: x["colocados"] for x in r["totales"]}["K-1"] == 1


async def test_cada_elemento_se_coloca_con_su_geometria(escenario, control: httpx.AsyncClient, residente: httpx.AsyncClient) -> None:
    _, t = await _plano_con_trazos(control, escenario)
    k1 = (await control.post("/api/v1/elementos-parametricos", json={"clave": "K-1", "nombre": "Castillo", "tipo": "castillo"})).json()["id"]
    poner = lambda cli, elem, trazo, **x: cli.put(  # noqa: E731
        f"/api/v1/trazos/{trazo}/elemento-parametrico", json={"elemento_id": elem, **x}
    )
    assert (await poner(control, k1, t["linea"])).status_code == 422  # un castillo es una pieza: se coloca con un punto
    assert (await poner(control, k1, t["punto"], lados_cimbra=1)).status_code == 422  # el castillo no tiene cimbra de 1 lado
    assert (await poner(control, str(uuid.uuid4()), t["punto"])).status_code == 404
    assert (await poner(control, k1, str(uuid.uuid4()))).status_code == 404
    # El residente traza, así que también puede marcar sus piezas.
    assert (await poner(residente, k1, t["punto"])).status_code == 204


async def test_un_concepto_toma_su_parte_de_la_receta_del_elemento(
    control: httpx.AsyncClient, residente: httpx.AsyncClient, escenario
) -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from tests.integracion.conftest import DATABASE_URL_ADMIN

    elemento = (
        await control.post("/api/v1/elementos-parametricos", json={"clave": "K-9", "nombre": "Castillo K-9", "tipo": "castillo"})
    ).json()["id"]
    habilitado, colado = uuid.uuid4(), uuid.uuid4()
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            for cid, clave in ((habilitado, "HAB-K9"), (colado, "COL-K9")):
                await c.execute(
                    text("insert into concepto (id, org_id, clave, descripcion) values (:i, :o, :k, :k)"),
                    {"i": str(cid), "o": str(escenario.org_id), "k": clave},
                )
    finally:
        await motor.dispose()

    ruta = f"/api/v1/elementos-parametricos/{elemento}/conceptos"
    # El acero, los estribos y el alambre al habilitado; el concreto y la cimbra al colado (en metros).
    assert (await control.put(f"{ruta}/{habilitado}", json={"unidad": "pza", "toma": {"acero": True, "estribos": True, "alambre": True}})).status_code == 204
    assert (await control.put(f"{ruta}/{colado}", json={"unidad": "ml", "toma": {"concreto": True, "cimbra": True}})).status_code == 204

    lista = {c["clave"]: c for c in (await control.get(ruta)).json()}
    receta = next(e for e in (await control.get("/api/v1/elementos-parametricos")).json() if e["id"] == elemento)["receta"]
    assert set(lista["HAB-K9"]["por_unidad"]) == {"acero", "estribos", "alambre"}
    assert lista["HAB-K9"]["por_unidad"]["acero"]["cantidad"] == pytest.approx(receta["acero_kg"])
    # En metros, lo que toma una pieza se divide entre su altura (2.6 m).
    assert lista["COL-K9"]["cantidad_por_muestra"] == pytest.approx(2.6)
    assert lista["COL-K9"]["por_unidad"]["concreto"]["cantidad"] == pytest.approx(receta["concreto"] / 2.6)

    # No toma nada, o una unidad que el elemento no admite: se rechaza. Un residente no define.
    assert (await control.put(f"{ruta}/{colado}", json={"unidad": "ml", "toma": {}})).status_code == 422
    assert (await control.put(f"{ruta}/{colado}", json={"unidad": "m²", "toma": {"concreto": True}})).status_code == 422
    assert (await residente.put(f"{ruta}/{colado}", json={"unidad": "ml", "toma": {"concreto": True}})).status_code == 403

    # Dos castillos en el plano: el concepto en metros suma 2 × 2.6 m y toma el concreto de ambos.
    plano, ids = await _plano_con_trazos(control, escenario)
    for t in (ids["punto"], ids["punto2"]):
        assert (await control.put(f"/api/v1/trazos/{t}/elemento-parametrico", json={"elemento_id": elemento})).status_code == 204
    del_plano = {c["clave"]: c for c in (await control.get(f"/api/v1/planos/{plano}/elementos-parametricos/conceptos")).json()}
    assert del_plano["COL-K9"]["cantidad"] == pytest.approx(5.2)
    assert del_plano["COL-K9"]["materiales"]["concreto"]["cantidad"] == pytest.approx(2 * receta["concreto"])
    assert del_plano["HAB-K9"]["cantidad"] == pytest.approx(2)  # en piezas

    assert (await control.delete(f"{ruta}/{habilitado}")).status_code == 204
    assert [c["clave"] for c in (await control.get(ruta)).json()] == ["COL-K9"]


async def test_la_toma_escribe_la_cantidad_medida_de_la_matriz_y_lo_trazado_manda(
    control: httpx.AsyncClient, escenario
) -> None:
    """D-639: lo que un concepto toma de los elementos colocados es la cantidad medida de su matriz en la actividad."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from tests.integracion.conftest import DATABASE_URL_ADMIN

    org, unidad, madre, hab = str(escenario.org_id), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            await c.execute(text("insert into unidad (id, org_id, clave, nombre) values (:i, :o, 'pza', 'Pieza')"), {"i": str(unidad), "o": org})
            await c.execute(text("insert into concepto (id, org_id, clave, descripcion) values (:i, :o, 'MAD-K9', 'Castillos')"), {"i": str(madre), "o": org})
            await c.execute(
                text("insert into concepto (id, org_id, clave, descripcion, unidad_id) values (:i, :o, 'HAB-K9', 'Habilitado K-9', :u)"),
                {"i": str(hab), "o": org, "u": str(unidad)},
            )
            await c.execute(
                text("insert into explosion (org_id, concepto_id, tipo_hijo, concepto_hijo_id, categoria, cantidad) values (:o, :p, 'concepto', :h, 'matriz', 1)"),
                {"o": org, "p": str(madre), "h": str(hab)},
            )
            await c.execute(
                text("update actividad set concepto_id = :c, cant_base = 10, cant_programada = 10, precio_unitario = 100 where id = :a"),
                {"c": str(madre), "a": str(escenario.actividad_id)},
            )
    finally:
        await motor.dispose()

    elemento = (await control.post("/api/v1/elementos-parametricos", json={"clave": "K-9", "nombre": "Castillo K-9", "tipo": "castillo"})).json()["id"]
    assert (
        await control.put(f"/api/v1/elementos-parametricos/{elemento}/conceptos/{hab}", json={"unidad": "pza", "toma": {"acero": True}})
    ).status_code == 204

    async def matriz() -> dict:
        r = await control.get(f"/api/v1/actividades/{escenario.actividad_id}/matrices")
        assert r.status_code == 200, r.text
        return next(m for m in r.json()["matrices"] if m["concepto_id"] == str(hab))

    assert (await matriz())["cantidad_medida"] is None

    # Dos castillos colocados: la matriz queda medida en 2 piezas, y de dónde viene lo dice.
    plano, ids = await _plano_con_trazos(control, escenario)
    for t in (ids["punto"], ids["punto2"]):
        assert (await control.put(f"/api/v1/trazos/{t}/elemento-parametrico", json={"elemento_id": elemento})).status_code == 204
    m = await matriz()
    assert float(m["cantidad_medida"]) == pytest.approx(2) and m["cantidad_origen"] == "elemento"

    # Quitar la marca de uno baja la cantidad; quitar la toma del concepto deja la matriz sin medir.
    assert (await control.put(f"/api/v1/trazos/{ids['punto2']}/elemento-parametrico", json={"elemento_id": None})).status_code == 204
    assert float((await matriz())["cantidad_medida"]) == pytest.approx(1)
    assert (await control.delete(f"/api/v1/elementos-parametricos/{elemento}/conceptos/{hab}")).status_code == 204
    assert (await matriz())["cantidad_medida"] is None
    assert (
        await control.put(f"/api/v1/elementos-parametricos/{elemento}/conceptos/{hab}", json={"unidad": "pza", "toma": {"acero": True}})
    ).status_code == 204
    assert float((await matriz())["cantidad_medida"]) == pytest.approx(1)

    # Lo trazado directo sobre la matriz manda sobre lo tomado (no hay doble conteo).
    medido = await control.post(
        f"/api/v1/planos/{plano}/trazos",
        json={
            "version_plano": 1,
            "fuente": "pdf",
            "geometria_wkt": "POINT(8 8)",
            "enlaces": [{"medida": "conteo", "factor": "3", "actividad_id": str(escenario.actividad_id), "matriz_concepto_id": str(hab)}],
        },
    )
    assert medido.status_code == 201, medido.text
    m = await matriz()
    assert float(m["cantidad_medida"]) == pytest.approx(3) and m["cantidad_origen"] == "trazos"
    # Rehacer las tomas no pisa lo medido con trazos.
    assert (await control.post(f"/api/v1/obras/{escenario.obra_id}/tomas/sincronizar")).status_code == 204
    assert float((await matriz())["cantidad_medida"]) == pytest.approx(3)


async def test_borrar_el_trazo_de_un_elemento_rehace_lo_que_toma_la_matriz(
    control: httpx.AsyncClient, escenario
) -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from tests.integracion.conftest import DATABASE_URL_ADMIN

    org, unidad, madre, hab = str(escenario.org_id), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            await c.execute(text("insert into unidad (id, org_id, clave, nombre) values (:i, :o, 'pza', 'Pieza')"), {"i": str(unidad), "o": org})
            await c.execute(text("insert into concepto (id, org_id, clave, descripcion) values (:i, :o, 'MAD-B9', 'Castillos')"), {"i": str(madre), "o": org})
            await c.execute(
                text("insert into concepto (id, org_id, clave, descripcion, unidad_id) values (:i, :o, 'HAB-B9', 'Habilitado', :u)"),
                {"i": str(hab), "o": org, "u": str(unidad)},
            )
            await c.execute(
                text("insert into explosion (org_id, concepto_id, tipo_hijo, concepto_hijo_id, categoria, cantidad) values (:o, :p, 'concepto', :h, 'matriz', 1)"),
                {"o": org, "p": str(madre), "h": str(hab)},
            )
            await c.execute(
                text("update actividad set concepto_id = :c, cant_base = 10, cant_programada = 10, precio_unitario = 100 where id = :a"),
                {"c": str(madre), "a": str(escenario.actividad_id)},
            )
    finally:
        await motor.dispose()
    elemento = (await control.post("/api/v1/elementos-parametricos", json={"clave": "K-B", "nombre": "Castillo", "tipo": "castillo"})).json()["id"]
    await control.put(f"/api/v1/elementos-parametricos/{elemento}/conceptos/{hab}", json={"unidad": "pza", "toma": {"acero": True}})
    _plano, ids = await _plano_con_trazos(control, escenario)
    for t in (ids["punto"], ids["punto2"]):
        await control.put(f"/api/v1/trazos/{t}/elemento-parametrico", json={"elemento_id": elemento})

    async def medido() -> object:
        r = await control.get(f"/api/v1/actividades/{escenario.actividad_id}/matrices")
        return next(m for m in r.json()["matrices"] if m["concepto_id"] == str(hab))["cantidad_medida"]

    assert float(await medido()) == pytest.approx(2)  # type: ignore[arg-type]
    assert (await control.delete(f"/api/v1/trazos/{ids['punto']}")).status_code == 200
    assert float(await medido()) == pytest.approx(1)  # type: ignore[arg-type]
