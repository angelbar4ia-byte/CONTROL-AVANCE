"""La escalera como elemento (Fase 4a, migración 0145) por HTTP de punta a punta contra Postgres real.

Las escaleras de una zona de losa (con el concepto EST-01510 del catálogo por escalón de 1.20 m y el concepto nuevo propuesto EJ-820 para el descanso), sus cotas que
salen de las zonas (o se teclean), los peldaños que salen del desnivel, la medición derivada de una línea del plano, la conciliación contra el catálogo vigente sin
tocarlo, el ciclo de la propuesta, los roles (solo Control de obra escribe; todos los que ven el plano leen) y lo que cada espacio escribe en su partida sin doble conteo."""

# ruff: noqa: F811  (las fixtures se importan de otras pruebas y se usan como parámetros)
from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario
from tests.integracion.test_espacios_endtoend import (  # noqa: F401
    _espacio,
    _rama_de_espacio,
)
from tests.integracion.test_matriz_de_losa_endtoend import (  # noqa: F401
    _trazo,
    _zona_con_losas,
    control,
    costos,
    residente,
)
from tests.integracion.test_plantillas_de_prototipo_endtoend import (  # noqa: F401
    _medido,
    arbol,
)

API = "/api/v1"


def _escaleras(zona: str) -> str:
    return f"{API}/zonas-de-losa/{zona}/escaleras"


async def _calculo(c: httpx.AsyncClient, zona: str, **params: Any) -> dict:
    r = await c.get(f"{_escaleras(zona)}/calculo", params=params)
    assert r.status_code == 200, r.text
    return r.json()


async def _calibrar(c: httpx.AsyncClient, plano: str, distancia: str = "4") -> None:
    assert (await c.put(f"{API}/planos/{plano}/escala", json={"punto_a": [0, 0], "punto_b": [4, 0], "distancia_m": distancia})).status_code == 200


async def _zona(c: httpx.AsyncClient, plano: str, nombre: str, **cuerpo: str) -> dict:
    r = await c.post(f"{API}/planos/{plano}/zonas-de-losa", json={"nombre": nombre, "altura_libre_m": "3.00", "espesor_m": "0.12", **cuerpo})
    assert r.status_code == 201, r.text
    return r.json()


async def _vacia(c: httpx.AsyncClient, escenario: Escenario, **cuerpo: str) -> tuple[str, dict]:
    """Un plano con una zona de 3.00 m de altura libre y 12 cm de losa (piso en 0): la escalera sube a 3.12 m."""
    plano = (await c.post(f"{API}/obras/{escenario.obra_id}/planos", json={"nombre": "PB", "archivo_url": "e2e/pb.pdf"})).json()["id"]
    return plano, await _zona(c, plano, "Planta baja", **cuerpo)


# ── Las escaleras de una zona y sus cotas ───────────────────────────────────────────────────────────


async def test_una_escalera_nace_con_los_valores_de_omision_y_el_cambio_conserva_su_espacio(control: httpx.AsyncClient, escenario: Escenario) -> None:
    _, z = await _vacia(control, escenario)
    r = await control.post(_escaleras(z["id"]), json={})
    assert r.status_code == 201, r.text
    nueva = r.json()
    assert (nueva["elemento_clave"], nueva["peldanos"], nueva["contrahuella_max_m"], nueva["huella_m"], nueva["ancho_m"]) == ("ESC-FORJADA", None, 0.18, 0.25, 1.2)
    assert (nueva["espesor_m"], nueva["rampas"], nueva["largo_descanso_m"], nueva["zona_llegada_id"], nueva["trazo_id"], nueva["espacio_id"]) == (0.12, 1, None, None, None, None)
    assert (nueva["cota_arranque_m"], nueva["cota_llegada_m"]) == (None, None)
    espacio = await _espacio(control, escenario.obra_id, "Escalera")
    cambiada = await control.put(f"{API}/escaleras-de-zona/{nueva['id']}", json={"ancho_m": 1.0, "espacio_id": espacio["id"]})
    assert cambiada.status_code == 200, cambiada.text
    assert (cambiada.json()["ancho_m"], cambiada.json()["espacio_id"]) == (1.0, espacio["id"])
    # Sin `espacio_id` conserva su espacio; con `null` se lo quita. Un parámetro que no viene vuelve al de omisión.
    r = await control.put(f"{API}/escaleras-de-zona/{nueva['id']}", json={"rampas": 2})
    assert (r.json()["espacio_id"], r.json()["rampas"], r.json()["ancho_m"]) == (espacio["id"], 2, 1.2)
    assert (await control.put(f"{API}/escaleras-de-zona/{nueva['id']}", json={"espacio_id": None})).json()["espacio_id"] is None
    assert [x["id"] for x in (await control.get(_escaleras(z["id"]))).json()] == [nueva["id"]]
    assert (await control.delete(f"{API}/escaleras-de-zona/{nueva['id']}")).status_code == 204
    assert (await control.get(_escaleras(z["id"]))).json() == []
    assert (await control.delete(f"{API}/escaleras-de-zona/{nueva['id']}")).status_code == 404
    assert (await control.put(f"{API}/escaleras-de-zona/{uuid.uuid4()}", json={})).status_code == 404


async def test_las_cotas_salen_de_las_zonas_y_la_escalera_las_sigue_sin_guardar_el_desnivel(control: httpx.AsyncClient, escenario: Escenario) -> None:
    plano, z = await _vacia(control, escenario)
    assert (await control.post(_escaleras(z["id"]), json={})).status_code == 201
    c = await _calculo(control, z["id"])
    assert c["zona"]["cota_piso_m"] == 0 and c["zona"]["cota_de_la_losa_m"] == pytest.approx(3.12)
    [e] = c["escaleras"]
    # Sin zona de llegada la escalera sube a la cara alta de su losa: 3.00 + 0.12 = 3.12 m = 18 peldaños.
    assert e["origen_de_cotas"] == {"arranque": "zona", "llegada": "losa_de_la_zona"} and e["error"] is None
    assert e["calculo"]["cotas"] == {"arranque_m": 0.0, "llegada_m": pytest.approx(3.12), "desnivel_m": pytest.approx(3.12)}
    assert e["calculo"]["geometria"]["peldanos"] == 18 and c["totales"]["peldanos"] == 18
    assert c["totales"]["conceptos"][0]["concepto"]["clave"] == "EST-01510" and c["totales"]["conceptos"][0]["cantidad"] == pytest.approx(18.0)

    # La zona de arriba: su piso (3.12) es la llegada y la altura libre de 1.08 m de la planta alta da los 6 peldaños de Oro.
    arriba = await _zona(control, plano, "Planta alta", cota_piso_m="3.12", altura_libre_m="1.08")
    r = await control.post(_escaleras(arriba["id"]), json={"cota_arranque_m": 3.12, "cota_llegada_m": 4.20})
    assert r.status_code == 201, r.text
    [e2] = (await _calculo(control, arriba["id"]))["escaleras"]
    assert e2["origen_de_cotas"] == {"arranque": "explicita", "llegada": "explicita"} and e2["calculo"]["geometria"]["peldanos"] == 6

    # Una escalera de PB que llega a la zona de arriba: el desnivel sale de las cotas de piso de las dos zonas…
    [propia] = (await control.get(_escaleras(z["id"]))).json()
    r = await control.put(f"{API}/escaleras-de-zona/{propia['id']}", json={"zona_llegada_id": arriba["id"]})
    assert r.status_code == 200 and r.json()["zona_llegada_id"] == arriba["id"], r.text
    [e] = (await _calculo(control, z["id"]))["escaleras"]
    assert e["origen_de_cotas"]["llegada"] == "zona_de_llegada" and e["calculo"]["geometria"]["peldanos"] == 18
    # …y si la zona de arriba cambia de cota, la escalera se recalcula sola: 3.30 m ÷ 0.18 = 18.3 → 19 peldaños.
    cuerpo = {"nombre": "Planta alta", "altura_libre_m": "1.08", "espesor_m": "0.12", "cota_piso_m": "3.30"}
    assert (await control.put(f"{API}/zonas-de-losa/{arriba['id']}", json=cuerpo)).status_code == 200
    [e] = (await _calculo(control, z["id"]))["escaleras"]
    assert e["calculo"]["cotas"]["llegada_m"] == pytest.approx(3.30) and e["calculo"]["geometria"]["peldanos"] == 19
    # Una zona que baja por debajo del arranque deja la escalera sin cálculo y con su motivo, sin romper el cálculo de la zona.
    assert (await control.put(f"{API}/zonas-de-losa/{arriba['id']}", json={**cuerpo, "cota_piso_m": "-0.50"})).status_code == 200
    c = await _calculo(control, z["id"])
    [e] = c["escaleras"]
    assert e["calculo"] is None and "sube" in e["error"] and any("no se puede calcular" in a for a in c["advertencias"])
    assert c["totales"]["conceptos"] == [] and c["por_espacio"] == []
    # Teclear la cota de llegada manda sobre la zona; no se aceptan las dos a la vez.
    r = await control.put(f"{API}/escaleras-de-zona/{propia['id']}", json={"zona_llegada_id": arriba["id"], "cota_llegada_m": 3.0})
    assert r.status_code == 422 and "no las dos" in r.text
    assert (await control.put(f"{API}/escaleras-de-zona/{propia['id']}", json={"cota_llegada_m": 3.6})).status_code == 200
    [e] = (await _calculo(control, z["id"]))["escaleras"]
    assert e["calculo"]["geometria"]["peldanos"] == 20 and e["zona_llegada_id"] is None  # 3.60 ÷ 0.18 = 20


async def test_con_varias_rampas_la_escalera_paga_su_descanso_con_un_concepto_propuesto(control: httpx.AsyncClient, escenario: Escenario) -> None:
    _, z = await _vacia(control, escenario)
    r = await control.post(_escaleras(z["id"]), json={"rampas": 2, "largo_descanso_m": 1.5, "ancho_m": 1.2, "espesor_m": 0.15})
    assert r.status_code == 201, r.text
    [e] = (await _calculo(control, z["id"]))["escaleras"]
    g = e["calculo"]["geometria"]
    assert g["descansos"] == 1 and g["area_de_descanso_m2"] == pytest.approx(1.8) and [x["peldanos"] for x in g["rampas"]] == [9, 9]
    claves = {c["concepto"]["clave"]: c for c in e["calculo"]["conceptos"]}
    assert claves["EST-01510"]["concepto"]["estado"] == "catalogo" and claves["EST-01510"]["propuesta"] is None
    assert claves["EJ-820"]["concepto"]["estado"] == "propuesto" and claves["EJ-820"]["cantidad"] == pytest.approx(1.8)
    # Con espesor de 15 cm el concreto de la rampa y del descanso sale con él.
    de_descanso = {i["clave"]: i["cantidad"] for i in e["calculo"]["insumos"] if i["parte"] == "descanso"}
    assert de_descanso["CON-00004"] == pytest.approx(1.8 * 0.15)


# ── La medición derivada de una línea del plano ─────────────────────────────────────────────────────


async def test_el_recorrido_sale_de_una_linea_del_plano_y_sigue_a_la_escala_sin_guardar_la_huella(control: httpx.AsyncClient, escenario: Escenario) -> None:
    plano, z = await _vacia(control, escenario)
    linea = await _trazo(control, plano, "LINESTRING(0 -1, 4.25 -1)")  # 4.25 unidades de plano
    r = await control.post(_escaleras(z["id"]), json={"trazo_id": linea})
    assert r.status_code == 201 and r.json()["trazo_id"] == linea, r.text
    c = await _calculo(control, z["id"])
    g = c["escaleras"][0]["calculo"]["geometria"]
    # 18 peldaños en una rampa tienen 17 huellas: 4.25 m dan la huella de 25 cm (sin escala calibrada, 1 unidad = 1 m).
    assert c["escala_definida"] is False and g["origen_de_huella"] == "linea" and g["huella_m"] == pytest.approx(0.25)
    assert any("no tiene escala calibrada" in a for a in c["escaleras"][0]["calculo"]["advertencias"])
    # Medición derivada: al calibrar la escala (el doble) la línea mide el doble y la huella con ella; la escalera no se tocó.
    await _calibrar(control, plano, "8")
    c = await _calculo(control, z["id"])
    assert c["escala_definida"] is True and c["escaleras"][0]["calculo"]["geometria"]["huella_m"] == pytest.approx(0.50)
    # Una línea que da una huella que no vale deja la escalera sin cálculo y con su motivo.
    await _calibrar(control, plano, "1")
    c = await _calculo(control, z["id"])
    assert c["escaleras"][0]["calculo"] is None and "huella" in c["escaleras"][0]["error"]
    # Si la línea se borra, la escalera vuelve a la huella tecleada y lo dice.
    assert (await control.delete(f"{API}/trazos/{linea}")).status_code in (200, 204)
    [e] = (await _calculo(control, z["id"]))["escaleras"]
    assert e["trazo_id"] is None and e["calculo"]["geometria"]["origen_de_huella"] == "tecleada"


async def test_lo_que_no_vale_se_rechaza_y_una_linea_no_sirve_a_dos_escaleras(control: httpx.AsyncClient, escenario: Escenario) -> None:
    plano, z = await _vacia(control, escenario)
    otra_plano = (await control.post(f"{API}/obras/{escenario.obra_id}/planos", json={"nombre": "PA", "archivo_url": "e2e/pa.pdf"})).json()["id"]
    zona_ajena = await _zona(control, otra_plano, "Otra")
    linea = await _trazo(control, plano, "LINESTRING(0 -1, 4.25 -1)")
    segunda = await _trazo(control, plano, "LINESTRING(0 -3, 4.25 -3)")
    url = _escaleras(z["id"])
    assert (await control.post(url, json={"trazo_id": linea})).status_code == 201
    r = await control.post(url, json={"trazo_id": linea})
    assert r.status_code == 422 and "dos veces" in r.text
    poligono = await _trazo(control, plano, "POLYGON((20 20, 22 20, 22 22, 20 22, 20 20))")
    punto = await _trazo(control, plano, "POINT(5 5)")
    ajena = await _trazo(control, otra_plano, "LINESTRING(0 0, 4 0)")
    malos = [
        ({"trazo_id": poligono}, "Solo una línea"),
        ({"trazo_id": punto}, "Solo una línea"),
        ({"trazo_id": ajena}, "otro plano"),
        ({"trazo_id": str(uuid.uuid4())}, ""),
        ({"zona_llegada_id": z["id"]}, "misma de arranque"),
        ({"zona_llegada_id": zona_ajena["id"]}, "otro plano"),
        ({"zona_llegada_id": str(uuid.uuid4())}, "no existe"),
        ({"espacio_id": str(uuid.uuid4())}, "espacio no existe"),
        ({"elemento_clave": "ESC-OTRA"}, ""),
        ({"ancho_m": 0.1}, ""),
        ({"rampas": 9}, ""),
        ({"peldanos": 1}, ""),
        ({"cota_llegada_m": 500}, ""),
    ]
    for mal, texto in malos:
        r = await control.post(url, json=mal)
        assert r.status_code in (404, 422) and texto in r.text, (mal, r.text)
    assert len((await control.get(url)).json()) == 1  # lo que se rechazó no se guardó
    # Cambiar una escalera a la línea de otra se rechaza; dejarle la suya no.
    sin_linea = (await control.post(url, json={})).json()
    assert (await control.put(f"{API}/escaleras-de-zona/{sin_linea['id']}", json={"trazo_id": linea})).status_code == 422
    assert (await control.put(f"{API}/escaleras-de-zona/{sin_linea['id']}", json={"trazo_id": segunda})).status_code == 200
    propia = next(x for x in (await control.get(url)).json() if x["trazo_id"] == linea)
    assert (await control.put(f"{API}/escaleras-de-zona/{propia['id']}", json={"trazo_id": linea, "rampas": 2})).status_code == 200
    assert (await control.post(_escaleras(str(uuid.uuid4())), json={})).status_code == 404
    assert (await control.get(f"{_escaleras(str(uuid.uuid4()))}/calculo")).status_code == 404


async def test_solo_control_de_obra_escribe_las_escaleras_y_los_demas_roles_leen(
    control: httpx.AsyncClient, costos: httpx.AsyncClient, residente: httpx.AsyncClient, escenario: Escenario
) -> None:
    _, z = await _vacia(control, escenario)
    nueva = (await control.post(_escaleras(z["id"]), json={})).json()
    for otro in (costos, residente):
        assert (await otro.post(_escaleras(z["id"]), json={})).status_code == 403
        assert (await otro.put(f"{API}/escaleras-de-zona/{nueva['id']}", json={"ancho_m": 2.0})).status_code == 403
        assert (await otro.delete(f"{API}/escaleras-de-zona/{nueva['id']}")).status_code == 403
        assert [x["id"] for x in (await otro.get(_escaleras(z["id"]))).json()] == [nueva["id"]]
        assert (await otro.get(f"{_escaleras(z['id'])}/calculo")).status_code == 200
    assert (await control.get(_escaleras(z["id"]))).json()[0]["ancho_m"] == 1.2  # nadie lo cambió


# ── La conciliación contra el catálogo vigente ──────────────────────────────────────────────────────


async def _catalogo_de_la_escalera(escenario: Escenario) -> str:
    """El concepto EST-01510 del catálogo con su composición real por escalón (concreto, alambre, mezcla, cimbraplay, tabique y varilla)."""
    org = str(escenario.org_id)
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            unidades = {}
            for u in ("pza", "m3", "kg"):
                await c.execute(text("insert into unidad (org_id, clave, nombre, sinonimos) values (:o, :u, :u, '{}') on conflict (org_id, clave) do nothing"), {"o": org, "u": u})
                unidades[u] = (await c.execute(text("select id from unidad where org_id = :o and clave = :u"), {"o": org, "u": u})).scalar_one()
            fam = (await c.execute(text("insert into familia (org_id, clave, nombre) values (:o, 'Varios', 'Varios') returning id"), {"o": org})).scalar_one()
            composicion = (
                ("CON-00004", "CONCRETO BOMBEADO 250 RAPISO 7 DIAS REVENIMIENTO (LOSAS AZOTEA Y ROOF)", "m3", 0.060583),
                ("ACE-00001", "ALAMBRE RECOCIDO", "kg", 0.44444),
                ("MEZ-07010", "MEZCLA CEMENTO-ARENA 1:4", "m3", 0.0575),
                ("MAD-00003", "CIMBRAPLAY 12 MM", "pza", 0.1633),
                ("PET-00001", "TABIQUE", "pza", 10.0),
                ("ACR-00001", "VARILLA 3/8", "pza", 0.4),
            )
            for clave, desc, unidad, _q in composicion:
                await c.execute(
                    text("insert into insumo (org_id, tipo, clave, descripcion, unidad_id, familia_id, costo_base) values (:o, 'material', :k, :d, :u, :f, 10)"),
                    {"o": org, "k": clave, "d": desc, "u": str(unidades[unidad]), "f": str(fam)},
                )
            cid = (
                await c.execute(
                    text("insert into concepto (org_id, clave, descripcion, unidad_id) values (:o, 'EST-01510', 'Escalera forjada de una rampa de concreto armado', :u) returning id"),
                    {"o": org, "u": str(unidades["pza"])},
                )
            ).scalar_one()
            for orden, (clave, _d, _u, cantidad) in enumerate(composicion):
                await c.execute(
                    text(
                        "insert into explosion (org_id, concepto_id, tipo_hijo, insumo_id, categoria, cantidad, orden) "
                        "values (:o, :c, 'insumo', (select id from insumo where org_id = :o and clave = :i), 'material', :q, :n)"
                    ),
                    {"o": org, "c": str(cid), "i": clave, "q": cantidad, "n": orden},
                )
            return str(cid)
    finally:
        await motor.dispose()


async def test_la_conciliacion_compara_la_escalera_por_escalon_con_est_01510_sin_tocar_el_catalogo(control: httpx.AsyncClient, escenario: Escenario) -> None:
    _, z = await _vacia(control, escenario)
    await _catalogo_de_la_escalera(escenario)
    assert (await control.post(_escaleras(z["id"]), json={})).status_code == 201
    [e] = (await _calculo(control, z["id"], conciliar="true"))["escaleras"]
    conc = e["conciliacion"]
    filas = {f["clave"]: f for f in conc["filas"]}
    assert conc["concepto"]["clave"] == "EST-01510" and "por pieza" in conc["nota"] and conc["coincide"] is False
    # Concreto y acero por escalón se calculan y se comparan; lo que el elemento no calcula sale «solo en el catálogo». Nada se corrige.
    por_escalon = e["calculo"]["geometria"]["superficie_de_rampa_m2"] / e["calculo"]["geometria"]["escalones_de_catalogo"]
    assert filas["CON-00004"]["catalogo"] == pytest.approx(0.060583) and filas["CON-00004"]["elemento"] == pytest.approx(por_escalon * 0.12, rel=1e-3)
    assert filas["ACR-00001"]["catalogo"] == pytest.approx(0.4) and filas["ACR-00001"]["elemento"] == pytest.approx(por_escalon * 0.9, rel=1e-3)
    assert filas["ACE-00001"]["marca"] in ("≠", "≈")
    for clave in ("PET-00001", "MEZ-07010", "MAD-00003"):
        assert filas[clave]["marca"] == "solo_catalogo", clave
    # Sin pedirla, no hay conciliación; el catálogo no cambió.
    assert (await _calculo(control, z["id"]))["escaleras"][0]["conciliacion"] is None
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            assert (await c.execute(text("select count(*) from explosion where concepto_id = (select id from concepto where clave = 'EST-01510')"))).scalar_one() == 6
    finally:
        await motor.dispose()
    # Sin el concepto en el catálogo vigente la conciliación lo dice en lugar de fallar.
    async with create_async_engine(DATABASE_URL_ADMIN).begin() as c:
        await c.execute(text("delete from explosion where concepto_id = (select id from concepto where clave = 'EST-01510' and org_id = :o)"), {"o": str(escenario.org_id)})
        await c.execute(text("delete from concepto where clave = 'EST-01510' and org_id = :o"), {"o": str(escenario.org_id)})
    [e] = (await _calculo(control, z["id"], conciliar="true"))["escaleras"]
    assert e["conciliacion"]["filas"] == [] and "no está en el catálogo vigente" in e["conciliacion"]["nota"]


# ── La propuesta del concepto nuevo del descanso ────────────────────────────────────────────────────


async def test_el_concepto_del_descanso_se_propone_una_vez_y_solo_control_de_obra_lo_autoriza(
    control: httpx.AsyncClient, costos: httpx.AsyncClient, residente: httpx.AsyncClient, escenario: Escenario
) -> None:
    _, z = await _vacia(control, escenario)
    # Con una sola rampa no hay descanso y el escalón usa un concepto del catálogo: no hay nada que proponer.
    assert (await control.post(_escaleras(z["id"]), json={})).status_code == 201
    assert (await costos.post(f"{_escaleras(z['id'])}/propuestas")).json() == {"creadas": [], "omitidas": []}
    assert (await control.post(_escaleras(z["id"]), json={"rampas": 2})).status_code == 201
    assert (await residente.post(f"{_escaleras(z['id'])}/propuestas")).status_code == 403
    primera = await costos.post(f"{_escaleras(z['id'])}/propuestas")
    assert primera.status_code == 201 and len(primera.json()["creadas"]) == 1
    assert (await costos.post(f"{_escaleras(z['id'])}/propuestas")).json()["omitidas"] == ["EJ-820"]  # idempotente
    assert (await costos.post(f"{API}/biblioteca-de-elementos/escalera/ESC-FORJADA/propuestas/concepto")).json() == {"creadas": [], "omitidas": ["EJ-820"]}
    c = await _calculo(costos, z["id"])
    con_descanso = next(e for e in c["escaleras"] if e["calculo"]["geometria"]["descansos"] == 1)
    descanso = next(k for k in con_descanso["calculo"]["conceptos"] if k["parte"] == "descanso")
    assert descanso["propuesta"]["estado"] == "pendiente"
    sin_descanso = next(e for e in c["escaleras"] if e["calculo"]["geometria"]["descansos"] == 0)
    assert sin_descanso["calculo"]["conceptos"][0]["propuesta"] is None  # el concepto del catálogo no se propone

    [p] = (await costos.get(f"{API}/biblioteca-de-elementos/escalera/ESC-FORJADA/propuestas")).json()
    assert (p["clase"], p["concepto_clave"], p["estado"], p["propuso_rol"], p["elemento_clave"]) == ("concepto_nuevo", "EJ-820", "pendiente", "costos", "ESC-FORJADA")
    assert any("F7" in x for x in p["motivos"]) and p["destajo_por_definir"] is None
    assert (await costos.post(f"{API}/propuestas-de-estructura/{p['id']}/autorizar")).status_code == 403
    assert (await control.post(f"{API}/propuestas-de-estructura/{p['id']}/autorizar")).json() == {"version": 1}
    c = await _calculo(costos, z["id"])
    descanso = next(k for e in c["escaleras"] if e["calculo"]["geometria"]["descansos"] == 1 for k in e["calculo"]["conceptos"] if k["parte"] == "descanso")
    assert descanso["propuesta"]["estado"] == "autorizada"
    # El catálogo no cambia: ningún concepto nuevo se creó en `concepto`.
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as cn:
            assert (await cn.execute(text("select count(*) from concepto where clave = 'EJ-820'"))).scalar_one() == 0
    finally:
        await motor.dispose()
    assert (await costos.get(f"{API}/biblioteca-de-elementos/escalera/ESC-OTRA/propuestas")).status_code == 404
    assert (await costos.post(f"{API}/biblioteca-de-elementos/escalera/REL-AZOTEA/propuestas/concepto")).status_code == 404


# ── La asignación a un espacio y lo que escribe en su partida ───────────────────────────────────────


async def test_la_escalera_de_cada_espacio_se_escribe_en_la_partida_de_ese_espacio_sin_doble_conteo(
    control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, str]
) -> None:
    plano, z = await _vacia(control, escenario)
    await _calibrar(control, plano)
    est = await _catalogo_de_la_escalera(escenario)
    esc1, esc2 = await _espacio(control, escenario.obra_id, "Escalera 1"), await _espacio(control, escenario.obra_id, "Escalera 2")
    de_1, de_2 = await _rama_de_espacio(escenario, arbol, "Escalera 1", est, "pza"), await _rama_de_espacio(escenario, arbol, "Escalera 2", est, "pza")
    for espacio, rama in ((esc1, de_1), (esc2, de_2)):
        assert (await control.put(f"{API}/espacios/{espacio['id']}/nodos", json={"nodo_ids": [rama["rama"]]})).status_code == 200
    a = (await control.post(_escaleras(z["id"]), json={})).json()

    # Sin espacio no se escribe nada (como la losa): el cálculo avisa por qué.
    assert await _medido(control, escenario, de_1["actividad"]) is None and await _medido(control, escenario, de_2["actividad"]) is None
    c = await _calculo(control, z["id"])
    assert [g["espacio_id"] for g in c["por_espacio"]] == [None]
    assert c["por_espacio"][0]["conceptos"][0]["resolucion"]["estado"] == "sin_espacio"

    # Asignada a su espacio, la partida de ese espacio recibe los 18 escalones y nada más.
    assert (await control.put(f"{API}/escaleras-de-zona/{a['id']}", json={"espacio_id": esc1["id"]})).status_code == 200
    assert await _medido(control, escenario, de_1["actividad"]) == pytest.approx(18.0)
    assert await _medido(control, escenario, de_2["actividad"]) is None
    c = await _calculo(control, z["id"])
    [grupo] = c["por_espacio"]
    assert grupo["espacio_nombre"] == "Escalera 1" and grupo["conceptos"][0]["resolucion"]["partida_id"] == de_1["partida"]
    # Una segunda escalera, de 1.20 m más ancha (36 escalones), en el otro espacio: cada partida recibe la suya y la suma es la de la zona.
    b = await control.post(_escaleras(z["id"]), json={"ancho_m": 2.4, "espacio_id": esc2["id"]})
    assert b.status_code == 201, b.text
    assert await _medido(control, escenario, de_1["actividad"]) == pytest.approx(18.0)
    assert await _medido(control, escenario, de_2["actividad"]) == pytest.approx(36.0)
    c = await _calculo(control, z["id"])
    assert sum(g["conceptos"][0]["cantidad"] for g in c["por_espacio"]) == pytest.approx(c["totales"]["conceptos"][0]["cantidad"])
    assert {g["espacio_nombre"] for g in c["por_espacio"]} == {"Escalera 1", "Escalera 2"}
    # Las dos en el mismo espacio se suman en su partida (sin contar dos veces); quitar una la deja con la otra.
    assert (await control.put(f"{API}/escaleras-de-zona/{b.json()['id']}", json={"ancho_m": 2.4, "espacio_id": esc1["id"]})).status_code == 200
    assert await _medido(control, escenario, de_1["actividad"]) == pytest.approx(54.0)
    assert not await _medido(control, escenario, de_2["actividad"])
    assert (await control.delete(f"{API}/escaleras-de-zona/{b.json()['id']}")).status_code == 204
    assert await _medido(control, escenario, de_1["actividad"]) == pytest.approx(18.0)
    # El descanso, mientras su concepto sea una propuesta, informa su cantidad pero no escribe en ninguna partida; los escalones sí.
    assert (await control.put(f"{API}/escaleras-de-zona/{a['id']}", json={"espacio_id": esc1["id"], "rampas": 2})).status_code == 200
    c = await _calculo(control, z["id"])
    estados = {x["concepto"]["clave"]: x["resolucion"]["estado"] for g in c["por_espacio"] for x in g["conceptos"]}
    assert estados == {"EST-01510": "cuenta", "EJ-820": "propuesto"}
    assert await _medido(control, escenario, de_1["actividad"]) == pytest.approx(18.0)


async def test_sin_escala_calibrada_la_escalera_no_escribe_en_ninguna_partida(control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, str]) -> None:
    plano, z = await _vacia(control, escenario)
    est = await _catalogo_de_la_escalera(escenario)
    esc = await _espacio(control, escenario.obra_id, "Escalera")
    de = await _rama_de_espacio(escenario, arbol, "Escalera", est, "pza")
    assert (await control.put(f"{API}/espacios/{esc['id']}/nodos", json={"nodo_ids": [de["rama"]]})).status_code == 200
    assert (await control.post(_escaleras(z["id"]), json={"espacio_id": esc["id"]})).status_code == 201
    assert await _medido(control, escenario, de["actividad"]) is None  # 1 unidad de plano = 1 m solo sirve para mostrar
    await _calibrar(control, plano)
    # Calibrar el plano no rehace las tomas por sí solo (igual que con la losa): se rehacen al pedirlas.
    assert (await control.post(f"{API}/obras/{escenario.obra_id}/tomas/sincronizar")).status_code in (200, 204)
    assert await _medido(control, escenario, de["actividad"]) == pytest.approx(18.0)


async def test_la_escalera_y_la_losa_no_cuentan_lo_mismo_dos_veces(control: httpx.AsyncClient, escenario: Escenario) -> None:
    # La matriz de la losa no se entera de la escalera: se pagan con conceptos distintos y el hueco de la escalera ya se resta del área de la losa.
    _, z = await _zona_con_losas(control, escenario)
    antes = (await control.get(f"{API}/zonas-de-losa/{z['id']}/matriz")).json()
    assert (await control.post(_escaleras(z["id"]), json={"rampas": 2})).status_code == 201
    despues = (await control.get(f"{API}/zonas-de-losa/{z['id']}/matriz")).json()
    assert despues["area_m2"] == pytest.approx(antes["area_m2"]) and despues["conceptos"] == antes["conceptos"]
    assert not {c["concepto"]["clave"] for c in despues["conceptos"]} & {"EST-01510", "EJ-820"}


# ── Descansos propios y escalones de abanico (Fase 4d, migración 0148) ──────────────────────────────


def _descansos(escalera: str) -> str:
    return f"{API}/escaleras-de-zona/{escalera}/descansos"


def _abanicos(escalera: str) -> str:
    return f"{API}/escaleras-de-zona/{escalera}/abanicos"


async def test_un_descanso_propio_lleva_sus_medidas_giro_y_espesor_y_las_demas_posiciones_conservan_el_implicito(control: httpx.AsyncClient, escenario: Escenario) -> None:
    _, z = await _vacia(control, escenario)
    e = (await control.post(_escaleras(z["id"]), json={"rampas": 3})).json()
    assert e["descansos"] == [] and e["abanicos"] == []  # sin filas propias: el descanso implícito de siempre
    antes = (await _calculo(control, z["id"]))["escaleras"][0]["calculo"]["geometria"]
    assert antes["descansos"] == 2 and antes["area_de_descanso_m2"] == pytest.approx(2 * 1.44)

    r = await control.put(_descansos(e["id"]), json={"descansos": [{"posicion": 2, "giro_grados": 180, "largo_m": 1.4, "ancho_m": 2.6, "espesor_m": 0.15}]})
    assert r.status_code == 200, r.text
    [d] = r.json()["descansos"]
    assert (d["posicion"], d["giro_grados"], d["largo_m"], d["ancho_m"], d["espesor_m"], d["trazo_id"]) == (2, 180, 1.4, 2.6, 0.15, None)
    assert (await control.get(_escaleras(z["id"]))).json()[0]["id"] == e["id"]
    assert (await control.get(_escaleras(z["id"]))).json()[0]["descansos"][0]["posicion"] == 2
    c = await _calculo(control, z["id"])
    [item] = c["escaleras"]
    assert [x["posicion"] for x in item["descansos"]] == [2]
    g = item["calculo"]["geometria"]
    assert [(x["posicion"], x["origen"]) for x in g["descansos_detalle"]] == [(1, "implicito"), (2, "dimensiones")]
    assert g["area_de_descanso_m2"] == pytest.approx(1.44 + 1.4 * 2.6) and c["totales"]["area_de_descanso_m2"] == pytest.approx(g["area_de_descanso_m2"])
    descanso = next(k for k in item["calculo"]["conceptos"] if k["parte"] == "descanso")
    assert descanso["concepto"]["clave"] == "EJ-820" and descanso["concepto"]["estado"] == "propuesto" and descanso["cantidad"] == pytest.approx(g["area_de_descanso_m2"])

    # Reemplazar deja SOLO los que vienen; vacío vuelve al implícito.
    assert len((await control.put(_descansos(e["id"]), json={"descansos": [{"posicion": 1}, {"posicion": 2, "giro_grados": 0}]})).json()["descansos"]) == 2
    assert (await control.put(_descansos(e["id"]), json={"descansos": []})).json()["descansos"] == []
    despues = (await _calculo(control, z["id"]))["escaleras"][0]["calculo"]["geometria"]
    assert despues["area_de_descanso_m2"] == pytest.approx(antes["area_de_descanso_m2"]) and all(x["origen"] == "implicito" for x in despues["descansos_detalle"])


async def test_un_descanso_mal_puesto_se_rechaza_con_su_motivo_y_no_se_guarda(control: httpx.AsyncClient, escenario: Escenario) -> None:
    _, z = await _vacia(control, escenario)
    e = (await control.post(_escaleras(z["id"]), json={"rampas": 2})).json()
    url = _descansos(e["id"])
    r = await control.put(url, json={"descansos": [{"posicion": 2}]})
    assert r.status_code == 422 and "tiene 2 rampas" in r.text
    r = await control.put(url, json={"descansos": [{"posicion": 1}, {"posicion": 1}]})
    assert r.status_code == 422 and "dos descansos" in r.text
    for mal in ({"posicion": 0}, {"posicion": 1, "giro_grados": 45}, {"posicion": 1, "largo_m": 9}, {"posicion": 1, "espesor_m": 0.9}):
        assert (await control.put(url, json={"descansos": [mal]})).status_code == 422, mal
    assert (await control.put(url, json={"descansos": [{"posicion": 1}, {"posicion": 2}, {"posicion": 3}, {"posicion": 3}]})).status_code == 422
    assert (await control.get(_escaleras(z["id"]))).json()[0]["descansos"] == []  # nada se guardó
    assert (await control.put(_descansos(str(uuid.uuid4())), json={"descansos": []})).status_code == 404
    # Bajar las rampas con un descanso en una posición que ya no existe se rechaza, en vez de dejar la escalera sin cálculo.
    assert (await control.put(url, json={"descansos": [{"posicion": 1}]})).status_code == 200
    r = await control.put(f"{API}/escaleras-de-zona/{e['id']}", json={"rampas": 1})
    assert r.status_code == 422 and "ya no existen" in r.text
    assert (await control.get(_escaleras(z["id"]))).json()[0]["rampas"] == 2


async def test_el_area_de_un_descanso_sale_de_un_poligono_del_plano_con_la_escala_sin_guardarla(control: httpx.AsyncClient, escenario: Escenario) -> None:
    plano, z = await _vacia(control, escenario)
    e = (await control.post(_escaleras(z["id"]), json={"rampas": 2})).json()
    poligono = await _trazo(control, plano, "POLYGON((10 10, 11.2 10, 11.2 12.4, 10 12.4, 10 10))")  # 1.2 × 2.4 = 2.88 unidades²
    r = await control.put(_descansos(e["id"]), json={"descansos": [{"posicion": 1, "giro_grados": 180, "largo_m": 1.0, "ancho_m": 1.0, "trazo_id": poligono}]})
    assert r.status_code == 200 and r.json()["descansos"][0]["trazo_id"] == poligono, r.text
    c = await _calculo(control, z["id"])
    [d] = c["escaleras"][0]["calculo"]["geometria"]["descansos_detalle"]
    # Sin escala se toma 1 unidad = 1 m y el cálculo lo dice; el área del polígono manda sobre largo × ancho.
    assert (d["origen"], d["area_m2"], d["largo_m"]) == ("plano", pytest.approx(2.88), None) and c["escala_definida"] is False
    assert any("sin escala" in a.lower() or "no tiene escala calibrada" in a for a in c["escaleras"][0]["calculo"]["advertencias"])
    # Medición derivada: al calibrar (el doble) el polígono mide cuatro veces; el descanso no se tocó.
    await _calibrar(control, plano, "8")
    [d] = (await _calculo(control, z["id"]))["escaleras"][0]["calculo"]["geometria"]["descansos_detalle"]
    assert d["area_m2"] == pytest.approx(2.88 * 4)
    # Si el polígono se borra, el descanso vuelve a sus dimensiones.
    assert (await control.delete(f"{API}/trazos/{poligono}")).status_code in (200, 204)
    [fila] = (await control.get(_escaleras(z["id"]))).json()[0]["descansos"]
    assert fila["trazo_id"] is None
    [d] = (await _calculo(control, z["id"]))["escaleras"][0]["calculo"]["geometria"]["descansos_detalle"]
    assert d["origen"] == "dimensiones" and d["area_m2"] == pytest.approx(1.0)


async def test_un_poligono_no_sirve_a_dos_descansos_ni_puede_ser_una_losa_ni_una_linea(control: httpx.AsyncClient, escenario: Escenario) -> None:
    plano, z = await _vacia(control, escenario)
    a = (await control.post(_escaleras(z["id"]), json={"rampas": 2})).json()
    b = (await control.post(_escaleras(z["id"]), json={"rampas": 2})).json()
    libre = await _trazo(control, plano, "POLYGON((10 10, 11.2 10, 11.2 12.4, 10 12.4, 10 10))")
    losa = await _trazo(control, plano, "POLYGON((30 30, 34 30, 34 34, 30 34, 30 30))")
    assert (await control.put(f"{API}/trazos/{losa}/losa", json={"zona_id": z["id"]})).status_code == 200
    linea = await _trazo(control, plano, "LINESTRING(0 -1, 4 -1)")
    otro_plano = (await control.post(f"{API}/obras/{escenario.obra_id}/planos", json={"nombre": "PA", "archivo_url": "e2e/pa.pdf"})).json()["id"]
    ajeno = await _trazo(control, otro_plano, "POLYGON((0 0, 2 0, 2 2, 0 2, 0 0))")
    assert (await control.put(_descansos(a["id"]), json={"descansos": [{"posicion": 1, "trazo_id": libre}]})).status_code == 200
    casos = [
        (b["id"], libre, "ya da el área"),
        (a["id"], losa, "ya es una losa"),
        (a["id"], linea, "Solo un polígono"),
        (a["id"], ajeno, "otro plano"),
        (a["id"], str(uuid.uuid4()), ""),
    ]
    for escalera, trazo, texto in casos[1:]:
        r = await control.put(_descansos(escalera), json={"descansos": [{"posicion": 1, "trazo_id": trazo}]})
        assert r.status_code in (404, 422) and texto in r.text, (trazo, r.text)
    r = await control.put(_descansos(casos[0][0]), json={"descansos": [{"posicion": 1, "trazo_id": libre}]})
    assert r.status_code == 422 and casos[0][2] in r.text
    # La propia escalera puede reafirmar su polígono (no choca consigo misma).
    assert (await control.put(_descansos(a["id"]), json={"descansos": [{"posicion": 1, "trazo_id": libre}]})).status_code == 200
    # La losa de la zona no se enteró de la escalera.
    assert not {c["concepto"]["clave"] for c in (await control.get(f"{API}/zonas-de-losa/{z['id']}/matriz")).json()["conceptos"]} & {"EJ-820", "EST-01510"}


async def test_los_escalones_de_abanico_forman_parte_de_los_peldanos_y_suman_piezas_sin_doble_conteo(control: httpx.AsyncClient, escenario: Escenario) -> None:
    _, z = await _vacia(control, escenario)
    e = (await control.post(_escaleras(z["id"]), json={"rampas": 2})).json()
    r = await control.put(_abanicos(e["id"]), json={"abanicos": [{"posicion": 1, "escalones": 3, "ancho_interior_m": 0.15, "ancho_exterior_m": 0.75}]})
    assert r.status_code == 200, r.text
    [a] = r.json()["abanicos"]
    assert (a["posicion"], a["escalones"], a["ancho_interior_m"], a["ancho_exterior_m"], a["radio_huella_m"]) == (1, 3, 0.15, 0.75, 0.35)  # radio por omisión: 35 cm
    c = await _calculo(control, z["id"])
    [item] = c["escaleras"]
    g = item["calculo"]["geometria"]
    # Los 18 peldaños del desnivel no cambian: 3 de abanico y 15 rectos. Piezas: 15 + 5.4 = 20.4 (y no 18 + 5.4).
    assert (g["peldanos"], g["peldanos_rectos"], g["peldanos_de_abanico"]) == (18, 15, 3) and c["totales"]["peldanos"] == 18 and c["totales"]["peldanos_de_abanico"] == 3
    assert g["escalones_rectos_de_catalogo"] == pytest.approx(15.0) and g["escalones_de_abanico_de_catalogo"] == pytest.approx(5.4)
    assert c["totales"]["escalones_de_catalogo"] == pytest.approx(20.4) and c["totales"]["area_de_abanico_m2"] == pytest.approx(1.62)
    [escalon] = [k for k in item["calculo"]["conceptos"] if k["parte"] == "escalon"]
    assert escalon["cantidad"] == pytest.approx(20.4) and c["totales"]["conceptos"][0]["cantidad"] == pytest.approx(20.4)
    [ab] = g["abanicos"]
    assert ab["huella_en_la_linea_m"] == pytest.approx(0.325) and ab["giro_total_grados"] == pytest.approx(85.94, abs=0.01)
    # Concreto y acero por geometría, una sola vez: la rampa de los 15 rectos y el abanico.
    insumos = item["calculo"]["insumos"]
    concreto = {i["parte"]: i["cantidad"] for i in insumos if i["clave"] == "CON-00004"}
    assert concreto["rampa"] == pytest.approx(g["superficie_de_rampa_m2"] * 0.12) and concreto["abanico"] == pytest.approx(g["superficie_de_abanico_m2"] * 0.12)
    # El radio es editable.
    r = await control.put(_abanicos(e["id"]), json={"abanicos": [{"posicion": 1, "escalones": 3, "ancho_interior_m": 0.15, "ancho_exterior_m": 0.75, "radio_huella_m": 0.40}]})
    assert r.json()["abanicos"][0]["radio_huella_m"] == 0.40
    [ab] = (await _calculo(control, z["id"]))["escaleras"][0]["calculo"]["geometria"]["abanicos"]
    assert ab["huella_en_la_linea_m"] == pytest.approx(0.15 + 0.6 * 0.40 / 1.2)
    # Quitarlos devuelve la escalera recta de siempre.
    assert (await control.put(_abanicos(e["id"]), json={"abanicos": []})).json()["abanicos"] == []
    g = (await _calculo(control, z["id"]))["escaleras"][0]["calculo"]["geometria"]
    assert (g["peldanos_rectos"], g["peldanos_de_abanico"], g["escalones_de_catalogo"]) == (18, 0, pytest.approx(18.0))


async def test_un_abanico_que_no_cabe_o_esta_mal_puesto_se_rechaza_y_no_se_guarda(control: httpx.AsyncClient, escenario: Escenario) -> None:
    _, z = await _vacia(control, escenario)
    e = (await control.post(_escaleras(z["id"]), json={"rampas": 4})).json()
    url = _abanicos(e["id"])
    base = {"posicion": 1, "escalones": 3, "ancho_interior_m": 0.15, "ancho_exterior_m": 0.75}
    r = await control.put(url, json={"abanicos": [{**base, "escalones": 12}]})  # quedarían 6 peldaños rectos y 4 rampas piden 8
    assert r.status_code == 422 and "no caben" in r.text
    r = await control.put(url, json={"abanicos": [{**base, "posicion": 5}]})
    assert r.status_code == 422
    r = await control.put(url, json={"abanicos": [base, {**base, "escalones": 2}]})
    assert r.status_code == 422 and "misma posición" in r.text
    r = await control.put(url, json={"abanicos": [{**base, "ancho_interior_m": 0.5, "ancho_exterior_m": 0.3}]})
    assert r.status_code == 422
    r = await control.put(url, json={"abanicos": [{**base, "radio_huella_m": 1.5}]})  # pasa del ancho de la escalera (1.20 m)
    assert r.status_code == 422 and "pasa del ancho" in r.text
    r = await control.put(url, json={"abanicos": [{**base, "ancho_interior_m": 0.05, "ancho_exterior_m": 0.15}]})  # 9 cm en la línea de huella
    assert r.status_code == 422 and "línea de huella" in r.text
    assert (await control.get(_escaleras(z["id"]))).json()[0]["abanicos"] == []
    # Con un abanico en la posición 4 (tras la última rampa), bajar las rampas se rechaza.
    assert (await control.put(url, json={"abanicos": [{**base, "posicion": 4}]})).status_code == 200
    r = await control.put(f"{API}/escaleras-de-zona/{e['id']}", json={"rampas": 3})
    assert r.status_code == 422 and "ya no existen" in r.text
    # Subir los peldaños deja sitio a más escalones de abanico.
    assert (await control.put(f"{API}/escaleras-de-zona/{e['id']}", json={"rampas": 4, "peldanos": 40})).status_code == 200
    assert (await control.put(url, json={"abanicos": [{**base, "posicion": 4, "escalones": 12}]})).status_code == 200


async def test_solo_control_de_obra_escribe_descansos_y_abanicos_y_los_demas_los_leen(
    control: httpx.AsyncClient, costos: httpx.AsyncClient, residente: httpx.AsyncClient, escenario: Escenario
) -> None:
    _, z = await _vacia(control, escenario)
    e = (await control.post(_escaleras(z["id"]), json={"rampas": 2})).json()
    assert (await control.put(_descansos(e["id"]), json={"descansos": [{"posicion": 1}]})).status_code == 200
    assert (await control.put(_abanicos(e["id"]), json={"abanicos": [{"posicion": 1, "escalones": 2, "ancho_interior_m": 0.2, "ancho_exterior_m": 0.5}]})).status_code == 200
    for otro in (costos, residente):
        assert (await otro.put(_descansos(e["id"]), json={"descansos": []})).status_code == 403
        assert (await otro.put(_abanicos(e["id"]), json={"abanicos": []})).status_code == 403
        [vista] = (await otro.get(_escaleras(z["id"]))).json()
        assert len(vista["descansos"]) == 1 and len(vista["abanicos"]) == 1
        [item] = (await _calculo(otro, z["id"]))["escaleras"]
        assert len(item["descansos"]) == 1 and len(item["abanicos"]) == 1
    # Nadie cambió nada.
    assert len((await control.get(_escaleras(z["id"]))).json()[0]["descansos"]) == 1


async def test_la_conciliacion_incluye_el_concreto_y_el_acero_de_los_escalones_de_abanico_por_escalon(control: httpx.AsyncClient, escenario: Escenario) -> None:
    _, z = await _vacia(control, escenario)
    await _catalogo_de_la_escalera(escenario)
    e = (await control.post(_escaleras(z["id"]), json={"rampas": 2})).json()
    assert (await control.put(_abanicos(e["id"]), json={"abanicos": [{"posicion": 1, "escalones": 3, "ancho_interior_m": 0.15, "ancho_exterior_m": 0.75}]})).status_code == 200
    [item] = (await _calculo(control, z["id"], conciliar="true"))["escaleras"]
    g = item["calculo"]["geometria"]
    por_escalon = (g["superficie_de_rampa_m2"] + g["superficie_de_abanico_m2"]) / g["escalones_de_catalogo"]
    filas = {f["clave"]: f for f in item["conciliacion"]["filas"]}
    assert filas["CON-00004"]["elemento"] == pytest.approx(por_escalon * 0.12, rel=1e-3) and filas["ACR-00001"]["elemento"] == pytest.approx(por_escalon * 0.9, rel=1e-3)


async def test_los_escalones_de_abanico_se_escriben_en_la_partida_del_espacio_sin_doble_conteo(
    control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, str]
) -> None:
    plano, z = await _vacia(control, escenario)
    await _calibrar(control, plano)
    est = await _catalogo_de_la_escalera(escenario)
    esc = await _espacio(control, escenario.obra_id, "Escalera con abanico")
    de = await _rama_de_espacio(escenario, arbol, "Escalera con abanico", est, "pza")
    assert (await control.put(f"{API}/espacios/{esc['id']}/nodos", json={"nodo_ids": [de["rama"]]})).status_code == 200
    e = (await control.post(_escaleras(z["id"]), json={"rampas": 2, "espacio_id": esc["id"]})).json()
    assert await _medido(control, escenario, de["actividad"]) == pytest.approx(18.0)
    # Al agregar el abanico la partida se rehace con las piezas de los 15 rectos más las del abanico: 20.4, no 18 + 5.4.
    assert (await control.put(_abanicos(e["id"]), json={"abanicos": [{"posicion": 1, "escalones": 3, "ancho_interior_m": 0.15, "ancho_exterior_m": 0.75}]})).status_code == 200
    assert await _medido(control, escenario, de["actividad"]) == pytest.approx(20.4)
    c = await _calculo(control, z["id"])
    assert sum(k["cantidad"] for g in c["por_espacio"] for k in g["conceptos"] if k["concepto"]["clave"] == "EST-01510") == pytest.approx(c["totales"]["conceptos"][0]["cantidad"])
    # Un descanso propio en el mismo espacio informa su cantidad (EJ-820 sigue propuesto: no se escribe en ninguna partida) y no mueve las piezas del escalón.
    assert (await control.put(_descansos(e["id"]), json={"descansos": [{"posicion": 1, "giro_grados": 180}]})).status_code == 200
    c = await _calculo(control, z["id"])
    estados = {x["concepto"]["clave"]: x["resolucion"]["estado"] for g in c["por_espacio"] for x in g["conceptos"]}
    assert estados == {"EST-01510": "cuenta", "EJ-820": "propuesto"} and await _medido(control, escenario, de["actividad"]) == pytest.approx(20.4)
    # Quitar el abanico devuelve la partida a los 18 escalones.
    assert (await control.put(_abanicos(e["id"]), json={"abanicos": []})).status_code == 200
    assert await _medido(control, escenario, de["actividad"]) == pytest.approx(18.0)
