"""La losa de cimentación y el muro de cimentación con cotas de desplante (Fase 4b, migración 0146) por HTTP de punta a punta contra Postgres real."""

# ruff: noqa: F811  (las fixtures se importan de otras pruebas y se usan como parámetros)
from __future__ import annotations

import uuid

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
    control,
    costos,
    residente,
)
from tests.integracion.test_plantillas_de_prototipo_endtoend import (  # noqa: F401
    _medido,
    arbol,
)

API = "/api/v1"


def _cimientos(zona: str) -> str:
    return f"{API}/zonas-de-losa/{zona}/cimientos"


async def _calculo(c: httpx.AsyncClient, zona: str) -> dict:
    r = await c.get(f"{_cimientos(zona)}/calculo")
    assert r.status_code == 200, r.text
    return r.json()


async def _calibrar(c: httpx.AsyncClient, plano: str, distancia: str = "4") -> None:
    assert (await c.put(f"{API}/planos/{plano}/escala", json={"punto_a": [0, 0], "punto_b": [4, 0], "distancia_m": distancia})).status_code == 200


async def _zona_de_cimentacion(c: httpx.AsyncClient, escenario: Escenario, **cuerpo: str) -> tuple[str, dict]:
    plano = (await c.post(f"{API}/obras/{escenario.obra_id}/planos", json={"nombre": "Cimentación", "archivo_url": "e2e/cim.pdf"})).json()["id"]
    r = await c.post(
        f"{API}/planos/{plano}/zonas-de-losa",
        json={"nombre": "Cimentación", "altura_libre_m": "0.50", "espesor_m": "0.14", "uso_de_losa": "cimentacion", **cuerpo},
    )
    assert r.status_code == 201, r.text
    return plano, r.json()


# ── La losa de cimentación ──────────────────────────────────────────────────────────────────────────


async def test_la_zona_de_cimentacion_usa_el_concreto_td_200_y_su_concepto_se_propone_con_clave_provisional(
    control: httpx.AsyncClient, costos: httpx.AsyncClient, escenario: Escenario
) -> None:
    plano, z = await _zona_de_cimentacion(control, escenario)
    assert z["uso_de_losa"] == "cimentacion" and z["tipo_de_losa"] == "maciza"
    trazo = await _trazo(control, plano, "POLYGON((0 -10, 10 -10, 10 0, 0 0, 0 -10))")  # 100 m²
    assert (await control.put(f"{API}/trazos/{trazo}/losa", json={"zona_id": z["id"]})).status_code == 200
    m = (await control.get(f"{API}/zonas-de-losa/{z['id']}/matriz")).json()
    assert m["uso"] == "cimentacion" and m["concreto"]["clave"] == "CON-00001" and m["concreto"]["geometrico_m3"] == pytest.approx(14.0)
    assert m["cimbra"]["m2"] == 0 and m["parrilla"]["clave"] == "AUX-00030"
    [losa] = [c for c in m["conceptos"] if c["parte"] == "losa"]
    assert losa["concepto"]["clave"] == "EJ-802" and losa["concepto"]["estado"] == "propuesto"
    primera = await costos.post(f"{API}/zonas-de-losa/{z['id']}/matriz/proponer-conceptos")
    assert primera.status_code == 201 and len(primera.json()["creadas"]) == 1, primera.text
    [p] = [x for x in (await costos.get(f"{API}/biblioteca-de-elementos/losa/LOSA-MACIZA/propuestas")).json() if x["concepto_clave"] == "EJ-802"]
    assert (p["clase"], p["estado"], p["elemento_clave"]) == ("concepto_nuevo", "pendiente", "LOSA-MACIZA")
    # Una zona de entrepiso o de azotea no cambia, y el uso de la base solo admite los tres.
    entrepiso = await control.put(f"{API}/zonas-de-losa/{z['id']}", json={"nombre": "Cimentación", "altura_libre_m": "0.50", "espesor_m": "0.14", "uso_de_losa": "entrepiso"})
    assert entrepiso.json()["uso_de_losa"] == "entrepiso"
    assert (await control.put(f"{API}/zonas-de-losa/{z['id']}", json={"nombre": "Cimentación", "altura_libre_m": "0.50", "espesor_m": "0.14", "uso_de_losa": "sotano"})).status_code == 422
    nervada = await control.put(f"{API}/zonas-de-losa/{z['id']}", json={"nombre": "Cimentación", "altura_libre_m": "0.50", "espesor_m": "0.14", "uso_de_losa": "cimentacion", "tipo_de_losa": "nervada"})
    assert nervada.status_code == 200
    assert (await control.get(f"{API}/zonas-de-losa/{z['id']}/matriz")).status_code == 422  # la cimentación es maciza


# ── Los cimientos con cotas de desplante ────────────────────────────────────────────────────────────


async def test_el_cimiento_toma_su_altura_de_las_cotas_y_su_longitud_de_la_linea_y_sigue_a_la_escala(control: httpx.AsyncClient, escenario: Escenario) -> None:
    plano, z = await _zona_de_cimentacion(control, escenario, cota_piso_m="0")
    linea = await _trazo(control, plano, "LINESTRING(0 0, 10 0)")
    r = await control.post(_cimientos(z["id"]), json={"trazo_id": linea, "cota_desplante_m": -0.8})
    assert r.status_code == 201, r.text
    nuevo = r.json()
    assert (nuevo["elemento_clave"], nuevo["cota_desplante_m"], nuevo["cota_corona_m"], nuevo["caras"], nuevo["dentellon"], nuevo["espacio_id"]) == ("CIM-01010", -0.8, None, 1, False, None)
    c = await _calculo(control, z["id"])
    [e] = c["cimientos"]
    assert c["escala_definida"] is False and e["longitud_m"] == pytest.approx(10.0)
    assert e["origen_de_cotas"] == {"desplante": "explicita", "corona": "zona"}
    assert e["calculo"]["cotas"] == {"desplante_m": -0.8, "corona_m": 0.0, "altura_m": pytest.approx(0.8)}
    assert e["calculo"]["volumen_m3"] == pytest.approx(0.532 * 10) and any("no tiene escala calibrada" in a for a in e["calculo"]["advertencias"])
    assert c["totales"]["conceptos"][0]["concepto"]["clave"] == "MCT-01011" and c["totales"]["volumen_m3"] == pytest.approx(5.32)
    # Medición derivada: al calibrar la escala (2 m por unidad) la línea mide el doble y el cimiento con ella, sin tocar el cimiento.
    await _calibrar(control, plano, "8")
    [e] = (await _calculo(control, z["id"]))["cimientos"]
    assert e["longitud_m"] == pytest.approx(20.0) and e["calculo"]["volumen_m3"] == pytest.approx(0.532 * 20)
    # Cambiar: corona tecleada, dos caras y dentellón; sin `espacio_id` conserva su espacio.
    cambiado = await control.put(f"{API}/cimientos-de-zona/{nuevo['id']}", json={"trazo_id": linea, "cota_desplante_m": -2.5, "cota_corona_m": 0.0, "caras": 2, "dentellon": True})
    assert cambiado.status_code == 200, cambiado.text
    [e] = (await _calculo(control, z["id"]))["cimientos"]
    assert e["origen_de_cotas"]["corona"] == "explicita" and e["calculo"]["dentellon"]["aplica"] is True and e["calculo"]["seccion"]["caras"] == 2
    assert (await control.delete(f"{API}/cimientos-de-zona/{nuevo['id']}")).status_code == 204
    assert (await control.get(_cimientos(z["id"]))).json() == []
    assert (await control.delete(f"{API}/cimientos-de-zona/{nuevo['id']}")).status_code == 404


async def test_el_desplante_puede_salir_de_un_punto_de_nivel_exterior_y_el_cimiento_sigue_al_punto(control: httpx.AsyncClient, escenario: Escenario) -> None:
    plano, z = await _zona_de_cimentacion(control, escenario)
    linea = await _trazo(control, plano, "LINESTRING(0 0, 5 0)")
    punto = await _trazo(control, plano, "POINT(2 2)")
    assert (await control.put(f"{API}/trazos/{punto}/nivel-exterior", json={"cota_m": "-0.60", "rotulo": "Desplante CIM-1"})).status_code == 200
    r = await control.post(_cimientos(z["id"]), json={"trazo_id": linea, "punto_nivel_id": punto})
    assert r.status_code == 201, r.text
    [e] = (await _calculo(control, z["id"]))["cimientos"]
    assert e["origen_de_cotas"]["desplante"] == "punto_de_nivel" and e["calculo"]["cotas"]["desplante_m"] == pytest.approx(-0.60)
    # Si el punto cambia de cota el cimiento cambia solo; la cota tecleada manda sobre el punto.
    assert (await control.put(f"{API}/trazos/{punto}/nivel-exterior", json={"cota_m": "-1.00", "rotulo": "Desplante CIM-1"})).status_code == 200
    [e] = (await _calculo(control, z["id"]))["cimientos"]
    assert e["calculo"]["cotas"]["altura_m"] == pytest.approx(1.0) and e["calculo"]["volumen_m3"] > 0
    cimiento = r.json()
    r = await control.put(f"{API}/cimientos-de-zona/{cimiento['id']}", json={"trazo_id": linea, "punto_nivel_id": punto, "cota_desplante_m": -1.5})
    assert r.status_code == 200
    [e] = (await _calculo(control, z["id"]))["cimientos"]
    assert e["origen_de_cotas"]["desplante"] == "explicita" and e["calculo"]["cotas"]["desplante_m"] == -1.5
    # Un punto que se borra deja el cimiento sin cota y lo dice (si no hay cota tecleada), sin romper el cálculo de la zona.
    r = await control.put(f"{API}/cimientos-de-zona/{cimiento['id']}", json={"trazo_id": linea, "punto_nivel_id": punto})
    assert r.status_code == 200
    assert (await control.delete(f"{API}/trazos/{punto}")).status_code in (200, 204)
    c = await _calculo(control, z["id"])
    [e] = c["cimientos"]
    assert e["calculo"] is None and "ya no existe" in e["error"] and any("no se puede calcular" in a for a in c["advertencias"])
    assert c["totales"]["conceptos"] == [] and c["por_espacio"] == []


async def test_una_corona_por_debajo_del_desplante_se_avisa_y_lo_que_no_vale_se_rechaza(control: httpx.AsyncClient, escenario: Escenario) -> None:
    plano, z = await _zona_de_cimentacion(control, escenario)
    otro_plano = (await control.post(f"{API}/obras/{escenario.obra_id}/planos", json={"nombre": "Otro", "archivo_url": "e2e/o.pdf"})).json()["id"]
    linea, segunda = await _trazo(control, plano, "LINESTRING(0 0, 5 0)"), await _trazo(control, plano, "LINESTRING(0 2, 5 2)")
    r = await control.post(_cimientos(z["id"]), json={"trazo_id": linea, "cota_desplante_m": 0.5})  # el piso de la zona (0) queda bajo el desplante
    assert r.status_code == 201
    c = await _calculo(control, z["id"])
    assert "por encima" in c["cimientos"][0]["error"] and c["cimientos"][0]["calculo"] is None
    url = _cimientos(z["id"])
    punto = await _trazo(control, plano, "POINT(1 1)")  # un punto sin cota de nivel
    malos = [
        ({"trazo_id": linea, "cota_desplante_m": -1.0}, "ya mide otro"),
        ({"trazo_id": segunda}, "Falta la cota de desplante"),
        ({"trazo_id": segunda, "punto_nivel_id": punto}, "punto de nivel no existe"),
        ({"trazo_id": segunda, "punto_nivel_id": str(uuid.uuid4())}, "punto de nivel no existe"),
        ({"trazo_id": await _trazo(control, plano, "POLYGON((20 20, 22 20, 22 22, 20 22, 20 20))"), "cota_desplante_m": -1}, "Solo una línea"),
        ({"trazo_id": await _trazo(control, otro_plano, "LINESTRING(0 0, 4 0)"), "cota_desplante_m": -1}, "otro plano"),
        ({"trazo_id": str(uuid.uuid4()), "cota_desplante_m": -1}, ""),
        ({"trazo_id": segunda, "cota_desplante_m": -1, "espacio_id": str(uuid.uuid4())}, "espacio no existe"),
        ({"trazo_id": segunda, "cota_desplante_m": -1, "elemento_clave": "CIM-OTRO"}, ""),
        ({"trazo_id": segunda, "cota_desplante_m": -1, "caras": 3}, ""),
        ({"trazo_id": segunda, "cota_desplante_m": -90}, ""),
    ]
    for mal, texto in malos:
        r = await control.post(url, json=mal)
        assert r.status_code in (404, 422) and texto in r.text, (mal, r.text)
    assert len((await control.get(url)).json()) == 1  # lo que se rechazó no se guardó
    assert (await control.post(_cimientos(str(uuid.uuid4())), json={"trazo_id": linea, "cota_desplante_m": -1})).status_code == 404
    assert (await control.put(f"{API}/cimientos-de-zona/{uuid.uuid4()}", json={"trazo_id": linea, "cota_desplante_m": -1})).status_code == 404


async def test_solo_control_de_obra_escribe_los_cimientos_y_los_demas_roles_leen(
    control: httpx.AsyncClient, costos: httpx.AsyncClient, residente: httpx.AsyncClient, escenario: Escenario
) -> None:
    plano, z = await _zona_de_cimentacion(control, escenario)
    linea = await _trazo(control, plano, "LINESTRING(0 0, 5 0)")
    nuevo = (await control.post(_cimientos(z["id"]), json={"trazo_id": linea, "cota_desplante_m": -0.8})).json()
    for otro in (costos, residente):
        assert (await otro.post(_cimientos(z["id"]), json={"trazo_id": linea, "cota_desplante_m": -1})).status_code == 403
        assert (await otro.put(f"{API}/cimientos-de-zona/{nuevo['id']}", json={"trazo_id": linea, "cota_desplante_m": -9})).status_code == 403
        assert (await otro.delete(f"{API}/cimientos-de-zona/{nuevo['id']}")).status_code == 403
        assert [x["id"] for x in (await otro.get(_cimientos(z["id"]))).json()] == [nuevo["id"]]
        assert (await otro.get(f"{_cimientos(z['id'])}/calculo")).status_code == 200
    assert (await control.get(_cimientos(z["id"]))).json()[0]["cota_desplante_m"] == -0.8  # nadie lo cambió


async def _catalogo_del_muro(escenario: Escenario) -> str:
    """El concepto MCT-01011 del catálogo (por m³) para que su partida exista en el árbol."""
    org = str(escenario.org_id)
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            await c.execute(text("insert into unidad (org_id, clave, nombre, sinonimos) values (:o, 'm3', 'm3', '{}') on conflict (org_id, clave) do nothing"), {"o": org})
            u = (await c.execute(text("select id from unidad where org_id = :o and clave = 'm3'"), {"o": org})).scalar_one()
            cid = (
                await c.execute(
                    text("insert into concepto (org_id, clave, descripcion, unidad_id) values (:o, 'MCT-01011', 'MURO DE MAMPOSTERÍA DE PIEDRA DE CERRO', :u) returning id"),
                    {"o": org, "u": str(u)},
                )
            ).scalar_one()
            return str(cid)
    finally:
        await motor.dispose()


async def test_el_cimiento_de_cada_espacio_se_escribe_en_la_partida_de_ese_espacio_sin_doble_conteo(
    control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, str]
) -> None:
    plano, z = await _zona_de_cimentacion(control, escenario)
    await _calibrar(control, plano)
    mct = await _catalogo_del_muro(escenario)
    e1, e2 = await _espacio(control, escenario.obra_id, "Cimiento norte"), await _espacio(control, escenario.obra_id, "Cimiento sur")
    de_1, de_2 = await _rama_de_espacio(escenario, arbol, "Cimiento norte", mct, "m3"), await _rama_de_espacio(escenario, arbol, "Cimiento sur", mct, "m3")
    for espacio, rama in ((e1, de_1), (e2, de_2)):
        assert (await control.put(f"{API}/espacios/{espacio['id']}/nodos", json={"nodo_ids": [rama["rama"]]})).status_code == 200
    # 4 unidades = 4 m con la escala calibrada: dos líneas de 4 m y de 8 m.
    norte, sur = await _trazo(control, plano, "LINESTRING(0 0, 4 0)"), await _trazo(control, plano, "LINESTRING(0 2, 8 2)")
    a = (await control.post(_cimientos(z["id"]), json={"trazo_id": norte, "cota_desplante_m": -0.8})).json()
    assert await _medido(control, escenario, de_1["actividad"]) is None  # sin espacio no se escribe
    assert (await _calculo(control, z["id"]))["por_espacio"][0]["conceptos"][0]["resolucion"]["estado"] == "sin_espacio"
    por_metro = 0.532
    assert (await control.put(f"{API}/cimientos-de-zona/{a['id']}", json={"trazo_id": norte, "cota_desplante_m": -0.8, "espacio_id": e1["id"]})).status_code == 200
    assert await _medido(control, escenario, de_1["actividad"]) == pytest.approx(por_metro * 4)
    b = await control.post(_cimientos(z["id"]), json={"trazo_id": sur, "cota_desplante_m": -0.8, "espacio_id": e2["id"]})
    assert b.status_code == 201, b.text
    assert await _medido(control, escenario, de_2["actividad"]) == pytest.approx(por_metro * 8)
    c = await _calculo(control, z["id"])
    assert sum(g["conceptos"][0]["cantidad"] for g in c["por_espacio"]) == pytest.approx(c["totales"]["volumen_m3"]) == pytest.approx(por_metro * 12)
    assert {g["espacio_nombre"] for g in c["por_espacio"]} == {"Cimiento norte", "Cimiento sur"}
    assert (await control.delete(f"{API}/cimientos-de-zona/{b.json()['id']}")).status_code == 204
    assert not await _medido(control, escenario, de_2["actividad"]) and await _medido(control, escenario, de_1["actividad"]) == pytest.approx(por_metro * 4)


async def test_el_cimiento_y_la_losa_no_cuentan_lo_mismo_dos_veces(control: httpx.AsyncClient, escenario: Escenario) -> None:
    plano, z = await _zona_de_cimentacion(control, escenario)
    antes = (await control.get(f"{API}/zonas-de-losa/{z['id']}/matriz")).json()
    linea = await _trazo(control, plano, "LINESTRING(0 0, 5 0)")
    assert (await control.post(_cimientos(z["id"]), json={"trazo_id": linea, "cota_desplante_m": -0.8})).status_code == 201
    despues = (await control.get(f"{API}/zonas-de-losa/{z['id']}/matriz")).json()
    assert despues["conceptos"] == antes["conceptos"] and "MCT-01011" not in {c["concepto"]["clave"] for c in despues["conceptos"]}
