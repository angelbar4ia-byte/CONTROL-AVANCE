"""La matriz de conceptos de la losa (fase 2, migración 0142) por HTTP de punta a punta contra Postgres real.

Una zona con sus polígonos de losa, sus elementos (a mano y medidos de una línea del plano), la escala del plano, los drivers de la obra, la
conciliación contra un concepto del catálogo, los conceptos nuevos propuestos (losa por m² y colado por ml, D8) con su ciclo de autorización, y
los roles: solo Control de obra escribe elementos; Costos o Control de obra proponen; solo Control de obra autoriza; todos los que ven el plano leen."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.api.dependencias import contexto_actual
from obractrl.infrastructure.db.sesion import ContextoSesion
from obractrl.main import crear_app
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario

API = "/api/v1"
CUARTO = "POLYGON((0 -4, 6 -4, 6 0, 0 0, 0 -4))"  # 24 m²
SUBZONA = "POLYGON((6 -4, 8 -4, 8 0, 6 0, 6 -4))"  # 8 m² con espesor propio
TRABE_6M = "LINESTRING(0 -2, 6 -2)"


def _cliente(contexto: ContextoSesion) -> httpx.AsyncClient:
    app = crear_app()
    app.dependency_overrides[contexto_actual] = lambda: contexto
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test")


async def _usuario(escenario: Escenario, rol: str, nombre: str) -> uuid.UUID:
    usuario = uuid.uuid4()
    motor = create_async_engine(DATABASE_URL_ADMIN)
    async with motor.begin() as c:
        await c.execute(
            text("insert into usuario (id, org_id, nombre, email, rol) values (:i, :o, :n, :e, :r)"),
            {"i": str(usuario), "o": str(escenario.org_id), "n": nombre, "e": f"{rol}-{usuario.hex[:8]}@t.mx", "r": rol},
        )
    await motor.dispose()
    return usuario


@pytest.fixture
async def control(contexto_control: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_control) as c:
        yield c


@pytest.fixture
async def costos(escenario: Escenario) -> AsyncIterator[httpx.AsyncClient]:
    usuario = await _usuario(escenario, "costos", "Costos")
    async with _cliente(ContextoSesion(org_id=escenario.org_id, usuario_id=usuario, rol="costos")) as c:
        yield c


@pytest.fixture
async def residente(contexto_residente: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_residente) as c:
        yield c


async def _trazo(c: httpx.AsyncClient, plano: str, wkt: str) -> str:
    r = await c.post(f"{API}/planos/{plano}/trazos", json={"version_plano": 1, "fuente": "pdf", "geometria_wkt": wkt, "enlaces": []})
    assert r.status_code == 201, r.text
    return r.json()["trazo_id"]


async def _zona_con_losas(c: httpx.AsyncClient, esc: Escenario, **zona: str) -> tuple[str, dict]:
    """Un plano con una zona de 3.00 m de altura libre y 12 cm, con su cuarto de 24 m² y una subzona de 8 m² de 20 cm."""
    plano = (await c.post(f"{API}/obras/{esc.obra_id}/planos", json={"nombre": "PB", "archivo_url": "e2e/pb.pdf"})).json()["id"]
    r = await c.post(f"{API}/planos/{plano}/zonas-de-losa", json={"nombre": "Entrepiso 3.00", "altura_libre_m": "3.00", "espesor_m": "0.12", **zona})
    assert r.status_code == 201, r.text
    z = r.json()
    for wkt, extra in ((CUARTO, {}), (SUBZONA, {"espesor_m": "0.20"})):
        trazo = await _trazo(c, plano, wkt)
        assert (await c.put(f"{API}/trazos/{trazo}/losa", json={"zona_id": z["id"], **extra})).status_code == 200
    return plano, z


async def _matriz(c: httpx.AsyncClient, zona: str, **params: str) -> dict:
    r = await c.get(f"{API}/zonas-de-losa/{zona}/matriz", params=params)
    assert r.status_code == 200, r.text
    return r.json()


# ── La zona trae el tipo y el uso de la losa ────────────────────────────────────────────────────────


async def test_la_zona_nace_maciza_de_entrepiso_y_el_tipo_y_el_uso_se_cambian_sin_pisar_lo_demas(control: httpx.AsyncClient, escenario: Escenario) -> None:
    plano, z = await _zona_con_losas(control, escenario)
    assert (z["tipo_de_losa"], z["uso_de_losa"]) == ("maciza", "entrepiso")
    cuerpo = {"nombre": "Entrepiso 3.00", "altura_libre_m": "3.00", "espesor_m": "0.12"}
    r = await control.put(f"{API}/zonas-de-losa/{z['id']}", json={**cuerpo, "tipo_de_losa": "nervada", "uso_de_losa": "azotea"})
    assert (r.json()["tipo_de_losa"], r.json()["uso_de_losa"]) == ("nervada", "azotea")
    # Un PUT que no trae el tipo ni el uso los conserva (lo de la fase 1 sigue funcionando igual).
    r = await control.put(f"{API}/zonas-de-losa/{z['id']}", json={**cuerpo, "nombre": "Azotea 3.00"})
    assert (r.json()["nombre"], r.json()["tipo_de_losa"], r.json()["uso_de_losa"]) == ("Azotea 3.00", "nervada", "azotea")
    assert (await control.put(f"{API}/zonas-de-losa/{z['id']}", json={**cuerpo, "tipo_de_losa": "curva"})).status_code == 422
    zona = next(x for x in (await control.get(f"{API}/planos/{plano}/zonas-de-losa")).json()["zonas"] if x["id"] == z["id"])
    assert (zona["tipo_de_losa"], zona["uso_de_losa"]) == ("nervada", "azotea")


# ── La matriz de una zona ───────────────────────────────────────────────────────────────────────────


async def test_la_matriz_mide_los_poligonos_de_la_zona_y_su_subzona(control: httpx.AsyncClient, escenario: Escenario) -> None:
    plano, z = await _zona_con_losas(control, escenario)
    m = await _matriz(control, z["id"])
    assert m["zona"]["nombre"] == "Entrepiso 3.00" and m["tipo"] == "maciza" and m["escala_definida"] is False
    assert m["area_m2"] == pytest.approx(32.0)
    assert m["concreto"]["geometrico_m3"] == pytest.approx(24 * 0.12 + 8 * 0.20)
    assert m["concreto"]["clave"] == "CON-00003"  # entrepiso
    assert m["cimbra"]["m2"] == pytest.approx(32.0)
    assert [lo["subzona"] for lo in m["losas"]] == [False, True]
    assert any("no tiene escala calibrada" in a for a in m["advertencias"])
    assert m["conceptos"][0]["concepto"]["clave"] == "EJ-800" and m["conceptos"][0]["cantidad"] == pytest.approx(32.0)
    # Con la escala calibrada (2 m por unidad) el área escala con el cuadrado.
    assert (await control.put(f"{API}/planos/{plano}/escala", json={"punto_a": [0, 0], "punto_b": [4, 0], "distancia_m": "8"})).status_code == 200
    m = await _matriz(control, z["id"])
    assert m["escala_definida"] is True and m["area_m2"] == pytest.approx(128.0)
    assert not any("escala" in a for a in m["advertencias"])


async def test_la_zona_nervada_y_de_azotea_cambia_el_concreto_y_la_capa(control: httpx.AsyncClient, escenario: Escenario) -> None:
    _, z = await _zona_con_losas(control, escenario, tipo_de_losa="nervada", uso_de_losa="azotea")
    m = await _matriz(control, z["id"])
    assert m["tipo"] == "nervada" and m["concreto"]["clave"] == "CON-00004" and m["parrilla"] is None
    assert m["concreto"]["geometrico_m3"] == pytest.approx(32 * 0.05)
    assert m["conceptos"][0]["concepto"]["clave"] == "EJ-801"


# ── Los elementos: a mano y medidos de una línea del plano ──────────────────────────────────────────


async def test_los_elementos_se_miden_a_mano_o_de_una_linea_del_plano_y_la_medida_sigue_a_la_escala(
    control: httpx.AsyncClient, escenario: Escenario
) -> None:
    plano, z = await _zona_con_losas(control, escenario)
    linea = await _trazo(control, plano, TRABE_6M)
    a_mano = await control.post(f"{API}/zonas-de-losa/{z['id']}/elementos", json={"elemento_clave": "T-1-15x25", "cantidad": 10.5})
    derivado = await control.post(f"{API}/zonas-de-losa/{z['id']}/elementos", json={"elemento_clave": "T-3-15x25", "trazo_id": linea, "pago": "propio"})
    pieza = await control.post(
        f"{API}/zonas-de-losa/{z['id']}/elementos", json={"elemento_clave": "T-2-12x20", "modo": "pieza", "trazo_id": linea}
    )
    assert (a_mano.status_code, derivado.status_code, pieza.status_code) == (201, 201, 201), (a_mano.text, derivado.text, pieza.text)
    assert (a_mano.json()["origen"], a_mano.json()["cantidad"]) == ("manual", 10.5)
    assert (derivado.json()["origen"], derivado.json()["cantidad"], derivado.json()["longitud_del_trazo_m"]) == ("trazo", 6.0, 6.0)
    assert (pieza.json()["cantidad"], pieza.json()["largo_m"]) == (1.0, 6.0)

    m = await _matriz(control, z["id"])
    assert [e["longitud_ml"] for e in m["elementos"]] == [10.5, 6.0, 6.0]
    assert [c["parte"] for c in m["conceptos"]] == ["losa", "acero", "acero", "colado", "acero"]
    colado = next(c for c in m["conceptos"] if c["parte"] == "colado")
    assert (colado["concepto"]["clave"], colado["cantidad"], colado["elemento_clave"]) == ("EJ-701", 6.0, "T-3-15x25")
    # Medición derivada: al calibrar la escala (2 m por unidad) la línea mide el doble y la matriz lo sigue, sin tocar el elemento.
    assert (await control.put(f"{API}/planos/{plano}/escala", json={"punto_a": [0, 0], "punto_b": [4, 0], "distancia_m": "8"})).status_code == 200
    m = await _matriz(control, z["id"])
    assert [e["longitud_ml"] for e in m["elementos"]] == [10.5, 12.0, 12.0]
    assert next(c for c in m["conceptos"] if c["parte"] == "colado")["cantidad"] == 12.0
    lista = (await control.get(f"{API}/zonas-de-losa/{z['id']}/elementos")).json()
    assert [(e["origen"], e["cantidad"]) for e in lista] == [("manual", 10.5), ("trazo", 12.0), ("trazo", 1.0)]
    assert lista[2]["largo_m"] == 12.0


async def test_un_elemento_se_cambia_y_se_quita_y_lo_que_no_vale_se_rechaza(control: httpx.AsyncClient, escenario: Escenario) -> None:
    plano, z = await _zona_con_losas(control, escenario)
    zona_url = f"{API}/zonas-de-losa/{z['id']}/elementos"
    nuevo = (await control.post(zona_url, json={"elemento_clave": "N-1-12x25", "cantidad": 40})).json()
    cambiado = await control.put(f"{API}/elementos-de-losa/{nuevo['id']}", json={"elemento_clave": "N-2-12x25", "modo": "ml", "cantidad": 55, "pago": "propio"})
    assert cambiado.status_code == 200, cambiado.text
    assert (cambiado.json()["elemento_clave"], cambiado.json()["cantidad"], cambiado.json()["pago"]) == ("N-2-12x25", 55.0, "propio")
    assert (await control.delete(f"{API}/elementos-de-losa/{nuevo['id']}")).status_code == 204
    assert (await control.get(zona_url)).json() == []
    assert (await control.delete(f"{API}/elementos-de-losa/{nuevo['id']}")).status_code == 404
    assert (await control.put(f"{API}/elementos-de-losa/{uuid.uuid4()}", json={"elemento_clave": "T-1-15x25", "cantidad": 1})).status_code == 404
    punto = await _trazo(control, plano, "POINT(1 -1)")
    for mal in (
        {"elemento_clave": "Z-1", "cantidad": 1},  # la zapata no se mide en la losa
        {"elemento_clave": "XX-1", "cantidad": 1},
        {"elemento_clave": "T-1-15x25"},  # sin cantidad ni línea
        {"elemento_clave": "T-1-15x25", "modo": "pieza", "cantidad": 1},  # por pieza sin largo
        {"elemento_clave": "T-1-15x25", "cantidad": 1, "largo_m": 3},  # por ml sin largo de pieza
        {"elemento_clave": "T-1-15x25", "trazo_id": punto},  # un punto no es una línea
        {"elemento_clave": "T-1-15x25", "trazo_id": str(uuid.uuid4())},
    ):
        r = await control.post(zona_url, json=mal)
        assert r.status_code in (404, 422), (mal, r.text)
    assert (await control.get(zona_url)).json() == []
    assert (await control.get(f"{API}/zonas-de-losa/{uuid.uuid4()}/matriz")).status_code == 404


async def test_una_linea_de_otro_plano_no_da_la_medida(control: httpx.AsyncClient, escenario: Escenario) -> None:
    _, z = await _zona_con_losas(control, escenario)
    otro = (await control.post(f"{API}/obras/{escenario.obra_id}/planos", json={"nombre": "PA", "archivo_url": "e2e/pa.pdf"})).json()["id"]
    ajena = await _trazo(control, otro, TRABE_6M)
    r = await control.post(f"{API}/zonas-de-losa/{z['id']}/elementos", json={"elemento_clave": "T-1-15x25", "trazo_id": ajena})
    assert r.status_code == 422 and "otro plano" in r.text


async def test_borrar_la_linea_deja_el_elemento_con_su_ultima_medida_y_borrar_la_zona_se_lleva_sus_elementos(
    control: httpx.AsyncClient, escenario: Escenario
) -> None:
    plano, z = await _zona_con_losas(control, escenario)
    linea = await _trazo(control, plano, TRABE_6M)
    nuevo = (await control.post(f"{API}/zonas-de-losa/{z['id']}/elementos", json={"elemento_clave": "T-1-15x25", "trazo_id": linea})).json()
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            await c.execute(text("delete from trazo where id = :t"), {"t": linea})
        [e] = (await control.get(f"{API}/zonas-de-losa/{z['id']}/elementos")).json()
        assert (e["id"], e["origen"], e["trazo_id"], e["cantidad"]) == (nuevo["id"], "manual", None, 6.0)  # queda la medida con que se guardó
        assert (await control.delete(f"{API}/zonas-de-losa/{z['id']}")).status_code == 204
        async with motor.begin() as c:
            assert (await c.execute(text("select count(*) from losa_elemento where zona_id = :z"), {"z": z["id"]})).scalar_one() == 0
    finally:
        await motor.dispose()


# ── Roles ───────────────────────────────────────────────────────────────────────────────────────────


async def test_todos_leen_la_matriz_pero_solo_control_de_obra_escribe_elementos(
    control: httpx.AsyncClient, costos: httpx.AsyncClient, residente: httpx.AsyncClient, escenario: Escenario
) -> None:
    _, z = await _zona_con_losas(control, escenario)
    url = f"{API}/zonas-de-losa/{z['id']}/elementos"
    assert (await control.post(url, json={"elemento_clave": "T-1-15x25", "cantidad": 3})).status_code == 201
    for cliente in (costos, residente):
        assert (await cliente.get(f"{API}/zonas-de-losa/{z['id']}/matriz")).status_code == 200
        assert len((await cliente.get(url)).json()) == 1
        assert (await cliente.post(url, json={"elemento_clave": "T-1-15x25", "cantidad": 3})).status_code == 403
    [e] = (await control.get(url)).json()
    assert (await costos.put(f"{API}/elementos-de-losa/{e['id']}", json={"elemento_clave": "T-1-15x25", "cantidad": 9})).status_code == 403
    assert (await costos.delete(f"{API}/elementos-de-losa/{e['id']}")).status_code == 403
    assert (await residente.post(f"{API}/zonas-de-losa/{z['id']}/matriz/proponer-conceptos")).status_code == 403


# ── Los conceptos nuevos propuestos: losa por m² y colado por ml (D8) ───────────────────────────────


async def test_costos_propone_los_conceptos_de_la_zona_y_control_de_obra_los_autoriza(
    control: httpx.AsyncClient, costos: httpx.AsyncClient, escenario: Escenario
) -> None:
    _, z = await _zona_con_losas(control, escenario)
    url = f"{API}/zonas-de-losa/{z['id']}"
    await control.post(f"{url}/elementos", json={"elemento_clave": "T-3-15x25", "cantidad": 20, "pago": "propio"})
    await control.post(f"{url}/elementos", json={"elemento_clave": "T-1-15x25", "cantidad": 8})  # en la losa: no lleva concepto de colado
    assert all(c["propuesta"] is None for c in (await _matriz(costos, z["id"]))["conceptos"])

    r = await costos.post(f"{url}/matriz/proponer-conceptos")
    assert r.status_code == 201, r.text
    assert len(r.json()["creadas"]) == 2  # EJ-800 (la losa) y EJ-701 (el colado por ml de T-3-15x25)
    otra = await costos.post(f"{url}/matriz/proponer-conceptos")
    assert otra.json()["creadas"] == [] and sorted(otra.json()["omitidas"]) == ["EJ-701", "EJ-800"]  # idempotente

    m = await _matriz(costos, z["id"])
    proviene = {c["concepto"]["clave"]: c["propuesta"] for c in m["conceptos"] if c["concepto"]["provisional"]}
    assert {k: v["estado"] for k, v in proviene.items()} == {"EJ-800": "pendiente", "EJ-701": "pendiente"}
    assert [c["propuesta"] for c in m["conceptos"] if not c["concepto"]["provisional"]] == [None, None]

    # La propuesta del concepto de la losa trae sus insumos de referencia, sin destajo ni precio; la del colado, el destajo por ml sin importe.
    losa = (await costos.get(f"{API}/biblioteca-de-elementos/losa/LOSA-MACIZA/propuestas")).json()
    [pl] = losa
    assert (pl["clase"], pl["concepto_clave"], pl["estado"], pl["propuso_rol"]) == ("concepto_nuevo", "EJ-800", "pendiente", "costos")
    assert any("F7" in x for x in pl["motivos"]) and pl["destajo_por_definir"] is None
    colado = (await costos.get(f"{API}/biblioteca-de-elementos/estructura/T-3-15x25/propuestas")).json()
    [pc] = colado
    assert pc["concepto_clave"] == "EJ-701" and "EJ-701-MO" in pc["resumen"] and any("Q52" in x for x in pc["motivos"])

    # Costos no autoriza; Control de obra sí, y el estado llega a la matriz.
    assert (await costos.post(f"{API}/propuestas-de-estructura/{pc['id']}/autorizar")).status_code == 403
    assert (await control.post(f"{API}/propuestas-de-estructura/{pc['id']}/autorizar")).json() == {"version": 1}
    m = await _matriz(costos, z["id"])
    estado = {c["concepto"]["clave"]: c["propuesta"]["estado"] for c in m["conceptos"] if c["propuesta"]}
    assert estado == {"EJ-800": "pendiente", "EJ-701": "autorizada"}
    # El catálogo no cambia: ningún concepto nuevo se creó en `concepto`.
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            assert (await c.execute(text("select count(*) from concepto where clave in ('EJ-800', 'EJ-701')"))).scalar_one() == 0
    finally:
        await motor.dispose()


async def test_el_colado_por_ml_de_una_trabe_se_propone_una_vez_y_dos_elementos_no_comparten_clave(
    control: httpx.AsyncClient, costos: httpx.AsyncClient, residente: httpx.AsyncClient, escenario: Escenario
) -> None:
    ruta = f"{API}/biblioteca-de-elementos/estructura/T-1-15x15/propuestas/colado-por-ml"
    assert (await residente.post(ruta)).status_code == 403
    primera = await costos.post(ruta)
    assert primera.status_code == 201 and len(primera.json()["creadas"]) == 1
    assert (await costos.post(ruta)).json() == {"creadas": [], "omitidas": ["EJ-705"]}
    for noes in ("Z-1", "C-1", "XX-1"):
        assert (await costos.post(f"{API}/biblioteca-de-elementos/estructura/{noes}/propuestas/colado-por-ml")).status_code == 404
    # Si otro elemento ya tiene propuesta con esa clave provisional, no se comparte.
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            await c.execute(
                text(
                    "insert into propuesta_de_estructura (org_id, elemento_clave, concepto_clave, clase, estado, resumen) "
                    "values (:o, 'OTRO-1', 'EJ-703', 'concepto_nuevo', 'pendiente', 'ajeno')"
                ),
                {"o": str(escenario.org_id)},
            )
    finally:
        await motor.dispose()
    r = await costos.post(f"{API}/biblioteca-de-elementos/estructura/T-1-15x25/propuestas/colado-por-ml")
    assert r.status_code == 422 and "OTRO-1" in r.text
    # Lo que propone Control de obra nace autorizado.
    c1 = await control.post(f"{API}/biblioteca-de-elementos/estructura/T-2-20x30/propuestas/colado-por-ml")
    assert c1.status_code == 201
    [p] = (await control.get(f"{API}/biblioteca-de-elementos/estructura/T-2-20x30/propuestas")).json()
    assert (p["estado"], p["version"], p["concepto_clave"]) == ("autorizada", 1, "EJ-707")


async def test_el_concepto_de_la_losa_se_propone_desde_la_biblioteca_y_una_clave_que_no_es_de_losa_es_404(
    costos: httpx.AsyncClient, residente: httpx.AsyncClient
) -> None:
    ruta = f"{API}/biblioteca-de-elementos/losa/LOSA-NERVADA/propuestas"
    assert (await residente.post(f"{ruta}/concepto")).status_code == 403
    assert (await costos.post(f"{ruta}/concepto")).status_code == 201
    assert (await costos.post(f"{ruta}/concepto")).json() == {"creadas": [], "omitidas": ["EJ-801"]}
    [p] = (await costos.get(ruta)).json()
    assert p["concepto_clave"] == "EJ-801" and p["elemento_clave"] == "LOSA-NERVADA"
    for mala in ("T-1-15x25", "LOSA-CURVA"):
        assert (await costos.post(f"{API}/biblioteca-de-elementos/losa/{mala}/propuestas/concepto")).status_code == 404
        assert (await costos.get(f"{API}/biblioteca-de-elementos/losa/{mala}/propuestas")).status_code == 404


# ── Los drivers de la obra y la conciliación con el catálogo vigente ────────────────────────────────


async def test_el_desperdicio_de_concreto_de_la_obra_llega_a_la_matriz(control: httpx.AsyncClient, escenario: Escenario) -> None:
    _, z = await _zona_con_losas(control, escenario)
    base = await _matriz(control, z["id"])
    usado = next(u for u in base["drivers_usados"] if u["clave"] == "desperdicio_concreto")
    assert (usado["valor"], usado["fuente"]) == (5.0, "defecto")
    assert (await control.put(f"{API}/obras/{escenario.obra_id}/drivers/desperdicio_concreto", json={"valor": "9"})).status_code in (200, 201, 204)
    con_obra = await _matriz(control, z["id"])
    usado = next(u for u in con_obra["drivers_usados"] if u["clave"] == "desperdicio_concreto")
    assert (usado["valor"], usado["fuente"]) == (9.0, "obra")
    assert con_obra["concreto"]["con_desperdicio_m3"] == pytest.approx(base["concreto"]["geometrico_m3"] * 1.09)


async def _catalogo_de_una_losa(escenario: Escenario) -> None:
    """Un concepto del catálogo con un lote de losa y su APU (como EST-21011 pero chico): 32 m² de losa."""
    org = str(escenario.org_id)
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            unidades = {}
            for u in ("m3", "m2", "pza", "kg"):
                unidades[u] = (
                    await c.execute(text("insert into unidad (org_id, clave, nombre, sinonimos) values (:o, :u, :u, '{}') returning id"), {"o": org, "u": u})
                ).scalar_one()
            fam = (await c.execute(text("insert into familia (org_id, clave, nombre) values (:o, 'Varios', 'Varios') returning id"), {"o": org})).scalar_one()
            for clave, desc, unidad in (
                ("CON-00003", "CONCRETO BOMBEADO 250 28 DIAS 14 REV (LOSAS ENTREPISO)", "m3"),
                ("MAD-00001", "CIMBRA 3 MTS", "m2"),
                ("ACR-00001", "VARILLA 3/8", "pza"),
                ("ACE-00099", "MALLA QUE LA MATRIZ NO CALCULA", "kg"),
            ):
                await c.execute(
                    text(
                        "insert into insumo (org_id, tipo, clave, descripcion, unidad_id, familia_id, costo_base) "
                        "values (:o, 'material', :k, :d, :u, :f, 10)"
                    ),
                    {"o": org, "k": clave, "d": desc, "u": str(unidades[unidad]), "f": str(fam)},
                )
            cid = (
                await c.execute(text("insert into concepto (org_id, clave, descripcion) values (:o, 'EST-LOSA1', 'Losa maciza de 12 cm (32 m2)') returning id"), {"o": org})
            ).scalar_one()
            for orden, (insumo, cantidad) in enumerate((("CON-00003", 4.2), ("MAD-00001", 32.0), ("ACR-00001", 28.8), ("ACE-00099", 5.0))):
                await c.execute(
                    text(
                        "insert into explosion (org_id, concepto_id, tipo_hijo, insumo_id, categoria, cantidad, orden) "
                        "values (:o, :c, 'insumo', (select id from insumo where org_id = :o and clave = :i), 'material', :q, :n)"
                    ),
                    {"o": org, "c": str(cid), "i": insumo, "q": cantidad, "n": orden},
                )
    finally:
        await motor.dispose()


async def test_la_conciliacion_compara_el_total_de_la_zona_con_el_concepto_del_catalogo_sin_tocarlo(
    control: httpx.AsyncClient, escenario: Escenario
) -> None:
    _, z = await _zona_con_losas(control, escenario)
    await _catalogo_de_una_losa(escenario)
    m = await _matriz(control, z["id"], concepto_clave="est-losa1")
    c = m["conciliacion"]
    assert c["concepto"]["clave"] == "EST-LOSA1"
    filas = {f["clave"]: f for f in c["filas"]}
    assert filas["MAD-00001"]["marca"] == "=" and filas["MAD-00001"]["catalogo"] == pytest.approx(32.0)
    assert filas["ACR-00001"]["elemento"] == pytest.approx(28.8) and filas["ACR-00001"]["marca"] == "="  # la parrilla del catálogo (0.9 pza por m²)
    assert filas["CON-00003"]["elemento"] == pytest.approx(m["concreto"]["con_desperdicio_m3"])
    assert filas["CON-00003"]["marca"] in ("≈", "≠")  # 4.2 contra 5.24 m³: el lote del catálogo trae menos concreto y se muestra, no se corrige
    assert filas["ACE-00099"]["marca"] == "solo_catalogo"
    assert c["coincide"] is False and "lote" in c["nota"]
    sin = await control.get(f"{API}/zonas-de-losa/{z['id']}/matriz", params={"concepto_clave": "NO-EXISTE"})
    assert sin.status_code == 422
    assert (await _matriz(control, z["id"]))["conciliacion"] is None
