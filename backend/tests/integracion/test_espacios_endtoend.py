"""La capa «espacio» (migración 0143) por HTTP de punta a punta contra Postgres real.

Los espacios de una obra (recámara 1, baño…), las ramas del árbol del presupuesto que les pertenecen, la asignación de muros y de polígonos y
elementos de losa, el muro compartido entre dos espacios (se reparte y suma una sola vez) y lo que cada partida recibe. Solo Control de obra edita
la estructura; los demás leen. Lo que no tiene espacio (muros, zonas, elementos) se comporta como siempre.
"""

# ruff: noqa: F811  (las fixtures `control`, `residente` y `arbol` se importan de la prueba de plantillas por prototipo y se usan como parámetros)
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.domain.cuantificacion.elementos_lineales import elemento_estructural
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario
from tests.integracion.test_plantillas_de_prototipo_endtoend import (  # noqa: F401  (fixtures y ayudas compartidas)
    PARTES,
    PLANTILLAS,
    _conceptos_de_los_elementos,
    _elementos_de_oro,
    _medido,
    _muro,
    arbol,
    control,
    residente,
)

API = "/api/v1"


async def _espacio(c: httpx.AsyncClient, obra: object, nombre: str, **extra: Any) -> dict:
    r = await c.post(f"{API}/obras/{obra}/espacios", json={"nombre": nombre, **extra})
    assert r.status_code == 201, r.text
    return r.json()


async def _rama_de_espacio(escenario: Escenario, arbol: dict[str, str], nombre: str, concepto: str, unidad: str = "ml") -> dict[str, str]:
    """Una rama «agrupador» del árbol con una partida del concepto y su actividad en planta baja (la partida de ESE espacio, cuando se asigne)."""
    ids = {"rama": str(uuid.uuid4()), "partida": str(uuid.uuid4()), "actividad": str(uuid.uuid4())}
    org, proto, obra = str(escenario.org_id), str(escenario.prototipo_id), str(escenario.obra_id)
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            padre = (await c.execute(text("select id from prototipo_nodo where prototipo_id = :p and tipo = 'etapa'"), {"p": proto})).scalar_one()
            for ident, tipo, padre_id, concepto_id in (
                (ids["rama"], "agrupador", str(padre), None), (ids["partida"], "concepto", ids["rama"], concepto),
            ):
                await c.execute(
                    text(
                        "insert into prototipo_nodo (id, org_id, prototipo_id, parent_id, tipo, nombre, clave, concepto_id, orden) "
                        "values (:i, :o, :p, :pa, cast(:t as tipo_prototipo_nodo), :n, :n, cast(:c as uuid), 0)"
                    ),
                    {"i": ident, "o": org, "p": proto, "pa": padre_id, "t": tipo, "n": nombre, "c": concepto_id},
                )
            await c.execute(
                text(
                    "insert into actividad (id, org_id, obra_id, concepto_id, nivel_id, etapa_id, prototipo_nodo_id, cant_base, cant_programada, precio_unitario) "
                    "select :i, :o, :ob, :c, nivel_id, etapa_id, :pn, 100, 100, 10 from actividad where id = :a"
                ),
                {"i": ids["actividad"], "o": org, "ob": obra, "c": concepto, "pn": ids["partida"], "a": arbol["a_cadena"]},
            )
    finally:
        await motor.dispose()
    return ids


async def _con_la_plantilla_de_cadena(control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, str]) -> str:
    """Un muro de 10 m con la plantilla «muros y cadena»: la cadena toma sus 10 m en el concepto CAD-1."""
    ids = await _elementos_de_oro(control)
    await _conceptos_de_los_elementos(control, arbol, ids)
    plantilla = (
        await control.post(
            PLANTILLAS,
            json={"nombre": "Muros y cadena", "tipo": "con_cadena", "material": "tabique_rojo", "ubicacion": "interior", "partes": PARTES, "elementos": [{"ref": "CE-1"}]},
        )
    ).json()
    muro = await _muro(control, escenario)
    assert (await control.put(f"{API}/trazos/{muro}/muro/plantilla", json={"plantilla_id": plantilla["id"]})).status_code == 200
    return muro


# ── Los espacios ─────────────────────────────────────────────────────────────────────────────


async def test_control_crea_y_cambia_espacios_los_demas_solo_leen(
    control: httpx.AsyncClient, residente: httpx.AsyncClient, escenario: Escenario
) -> None:
    r1 = await _espacio(control, escenario.obra_id, "Recámara 1", tipo="recamara", area_m2="12.5")
    assert (r1["nombre"], r1["tipo"], Decimal(r1["area_m2"]), r1["muros"], r1["losas"], r1["elementos"], r1["nodos"]) == ("Recámara 1", "recamara", Decimal("12.5"), 0, 0, 0, [])
    bano = await _espacio(control, escenario.obra_id, "Baño")
    assert bano["tipo"] == "otro" and bano["orden"] > r1["orden"]

    lista = (await control.get(f"{API}/obras/{escenario.obra_id}/espacios")).json()
    assert [e["nombre"] for e in lista] == ["Recámara 1", "Baño"]
    # Los demás roles ven la obra y leen; no escriben.
    assert [e["id"] for e in (await residente.get(f"{API}/obras/{escenario.obra_id}/espacios")).json()] == [r1["id"], bano["id"]]
    assert (await residente.post(f"{API}/obras/{escenario.obra_id}/espacios", json={"nombre": "Cocina"})).status_code == 403
    assert (await residente.put(f"{API}/espacios/{r1['id']}", json={"nombre": "X"})).status_code == 403
    assert (await residente.delete(f"{API}/espacios/{r1['id']}")).status_code == 403
    assert (await residente.put(f"{API}/espacios/{r1['id']}/nodos", json={"nodo_ids": []})).status_code == 403

    r = await control.put(f"{API}/espacios/{r1['id']}", json={"nombre": "Recámara principal", "tipo": "recamara", "area_m2": "14"})
    assert r.status_code == 200 and r.json()["nombre"] == "Recámara principal" and Decimal(r.json()["area_m2"]) == 14


async def test_el_nombre_es_unico_en_la_obra_y_los_datos_se_validan(control: httpx.AsyncClient, escenario: Escenario) -> None:
    await _espacio(control, escenario.obra_id, "Cocina")
    r = await control.post(f"{API}/obras/{escenario.obra_id}/espacios", json={"nombre": " COCINA "})
    assert r.status_code == 422 and "Ya hay un espacio" in r.text
    for mal in ({"nombre": " "}, {"nombre": "x" * 61}, {"nombre": "A", "tipo": "sotano"}, {"nombre": "A", "area_m2": "0"}, {"nombre": "A", "area_m2": "-1"}):
        assert (await control.post(f"{API}/obras/{escenario.obra_id}/espacios", json=mal)).status_code == 422
    assert (await control.post(f"{API}/obras/{uuid.uuid4()}/espacios", json={"nombre": "Fantasma"})).status_code == 404
    assert (await control.put(f"{API}/espacios/{uuid.uuid4()}", json={"nombre": "Fantasma"})).status_code == 404
    assert (await control.get(f"{API}/trazos/{uuid.uuid4()}/espacio")).status_code == 404


# ── Muros: asignar, compartir, no contar dos veces ────────────────────────────────────────────


async def test_un_muro_sin_espacio_sigue_como_siempre_y_con_espacio_cuenta_en_la_partida_de_su_espacio(
    control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, str]
) -> None:
    muro = await _con_la_plantilla_de_cadena(control, escenario, arbol)
    assert await _medido(control, escenario, arbol["a_cadena"]) == pytest.approx(10)  # sin espacios: como hasta hoy

    recamara, bano = await _espacio(control, escenario.obra_id, "Recámara 1"), await _espacio(control, escenario.obra_id, "Baño")
    de_r, de_b = await _rama_de_espacio(escenario, arbol, "Recámara 1", arbol["cadena"]), await _rama_de_espacio(escenario, arbol, "Baño", arbol["cadena"])
    for espacio, rama in ((recamara, de_r), (bano, de_b)):
        r = await control.put(f"{API}/espacios/{espacio['id']}/nodos", json={"nodo_ids": [rama["rama"]]})
        assert r.status_code == 200 and r.json()["nodos"] == [rama["rama"]]
    # Con partidas de espacio en el árbol, un muro SIN espacio sigue contando en la partida general y NO se cuela en las de los espacios.
    assert await _medido(control, escenario, arbol["a_cadena"]) == pytest.approx(10)
    assert await _medido(control, escenario, de_r["actividad"]) is None and await _medido(control, escenario, de_b["actividad"]) is None

    # Asignado a la recámara: sus 10 m cuentan en la partida de la recámara y ya no en la general.
    r = await control.put(f"{API}/trazos/{muro}/espacio", json={"espacio_id": recamara["id"]})
    assert r.status_code == 200, r.text
    assert [(p["espacio_id"], Decimal(p["fraccion"])) for p in r.json()["reparto"]] == [(recamara["id"], Decimal(1))]
    assert await _medido(control, escenario, de_r["actividad"]) == pytest.approx(10)
    assert await _medido(control, escenario, de_b["actividad"]) is None
    assert not await _medido(control, escenario, arbol["a_cadena"])

    # Compartido mitad y mitad: se traza una vez y suma una vez (5 + 5 = 10).
    r = await control.put(f"{API}/trazos/{muro}/espacio", json={"espacio_id": recamara["id"], "espacio_comparte_id": bano["id"]})
    assert r.status_code == 200, r.text
    assert [(p["espacio_id"], Decimal(p["fraccion"])) for p in r.json()["reparto"]] == [(recamara["id"], Decimal("0.5")), (bano["id"], Decimal("0.5"))]
    assert await _medido(control, escenario, de_r["actividad"]) == pytest.approx(5)
    assert await _medido(control, escenario, de_b["actividad"]) == pytest.approx(5)
    assert not await _medido(control, escenario, arbol["a_cadena"])

    # Con otro reparto: 30 % de la recámara y 70 % del baño; la suma sigue siendo el muro.
    r = await control.put(f"{API}/trazos/{muro}/espacio", json={"espacio_id": recamara["id"], "espacio_comparte_id": bano["id"], "reparto_pct": "30"})
    assert r.status_code == 200 and Decimal(r.json()["reparto_pct"]) == Decimal(30)
    assert await _medido(control, escenario, de_r["actividad"]) == pytest.approx(3)
    assert await _medido(control, escenario, de_b["actividad"]) == pytest.approx(7)
    espacios = {e["id"]: e for e in (await control.get(f"{API}/obras/{escenario.obra_id}/espacios")).json()}
    assert espacios[recamara["id"]]["muros"] == 1 and espacios[bano["id"]]["muros"] == 1

    # El plano trae la asignación en las propiedades del trazo.
    plano = (await control.get(f"{API}/obras/{escenario.obra_id}/planos")).json()[0]["id"]
    props = next(f["properties"] for f in (await control.get(f"{API}/planos/{plano}/trazos")).json()["features"] if f["properties"]["trazo_id"] == muro)
    assert (props["espacio_id"], props["espacio_comparte_id"], Decimal(props["espacio_reparto_pct"])) == (recamara["id"], bano["id"], Decimal(30))

    # Quitarle el espacio lo devuelve a la partida general.
    assert (await control.put(f"{API}/trazos/{muro}/espacio", json={})).status_code == 200
    assert await _medido(control, escenario, arbol["a_cadena"]) == pytest.approx(10)
    assert await _medido(control, escenario, de_r["actividad"]) is None


async def test_borrar_un_espacio_deja_su_muro_sin_perder_ni_duplicar_la_cantidad(
    control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, str]
) -> None:
    muro = await _con_la_plantilla_de_cadena(control, escenario, arbol)
    recamara, bano = await _espacio(control, escenario.obra_id, "Recámara 1"), await _espacio(control, escenario.obra_id, "Baño")
    de_r, de_b = await _rama_de_espacio(escenario, arbol, "Recámara 1", arbol["cadena"]), await _rama_de_espacio(escenario, arbol, "Baño", arbol["cadena"])
    for espacio, rama in ((recamara, de_r), (bano, de_b)):
        assert (await control.put(f"{API}/espacios/{espacio['id']}/nodos", json={"nodo_ids": [rama["rama"]]})).status_code == 200
    assert (await control.put(f"{API}/trazos/{muro}/espacio", json={"espacio_id": recamara["id"], "espacio_comparte_id": bano["id"]})).status_code == 200
    assert await _medido(control, escenario, de_r["actividad"]) == pytest.approx(5)

    # Se borra el baño: el muro era de los dos y ahora se lo lleva la recámara entero (10); la rama del baño vuelve a ser general y no recibe nada.
    assert (await control.delete(f"{API}/espacios/{bano['id']}")).status_code == 204
    asignacion = (await control.get(f"{API}/trazos/{muro}/espacio")).json()
    assert asignacion["espacio_id"] == recamara["id"] and asignacion["espacio_comparte_id"] is None
    assert [(p["espacio_id"], Decimal(p["fraccion"])) for p in asignacion["reparto"]] == [(recamara["id"], Decimal(1))]
    assert await _medido(control, escenario, de_r["actividad"]) == pytest.approx(10)
    assert not await _medido(control, escenario, de_b["actividad"])
    # Se borra también la recámara: el muro queda sin espacio y vuelve a la partida general.
    assert (await control.delete(f"{API}/espacios/{recamara['id']}")).status_code == 204
    assert (await control.get(f"{API}/trazos/{muro}/espacio")).json()["reparto"] == []
    assert await _medido(control, escenario, arbol["a_cadena"]) == pytest.approx(10)


async def test_una_rama_es_de_un_solo_espacio_y_solo_del_arbol_de_la_obra(
    control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, str]
) -> None:
    recamara, bano = await _espacio(control, escenario.obra_id, "Recámara 1"), await _espacio(control, escenario.obra_id, "Baño")
    rama = await _rama_de_espacio(escenario, arbol, "Compartida", arbol["cadena"])
    assert (await control.put(f"{API}/espacios/{recamara['id']}/nodos", json={"nodo_ids": [rama["rama"], rama["rama"]]})).json()["nodos"] == [rama["rama"]]
    # Pasa del uno al otro: no queda en los dos.
    assert (await control.put(f"{API}/espacios/{bano['id']}/nodos", json={"nodo_ids": [rama["rama"]]})).json()["nodos"] == [rama["rama"]]
    por_id = {e["id"]: e for e in (await control.get(f"{API}/obras/{escenario.obra_id}/espacios")).json()}
    assert por_id[recamara["id"]]["nodos"] == [] and por_id[bano["id"]]["nodos"] == [rama["rama"]]
    r = await control.put(f"{API}/espacios/{bano['id']}/nodos", json={"nodo_ids": [str(uuid.uuid4())]})
    assert r.status_code == 422 and "no es del árbol" in r.text


async def test_la_asignacion_de_un_trazo_se_valida(control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, str]) -> None:
    muro = await _muro(control, escenario)
    recamara, bano = await _espacio(control, escenario.obra_id, "Recámara 1"), await _espacio(control, escenario.obra_id, "Baño")
    ruta = f"{API}/trazos/{muro}/espacio"
    for mal, texto in (
        ({"espacio_comparte_id": bano["id"]}, "espacio principal"),
        ({"espacio_id": bano["id"], "espacio_comparte_id": bano["id"]}, "mismo espacio"),
        ({"espacio_id": str(uuid.uuid4())}, "no existe"),
        ({"espacio_id": recamara["id"], "espacio_comparte_id": str(uuid.uuid4())}, "no existe"),
    ):
        r = await control.put(ruta, json=mal)
        assert r.status_code == 422 and texto in r.text, (mal, r.text)
    for pct in ("0", "100", "-4", "130"):
        assert (await control.put(ruta, json={"espacio_id": recamara["id"], "espacio_comparte_id": bano["id"], "reparto_pct": pct})).status_code == 422
    assert (await control.put(ruta, json={"espacio_id": recamara["id"], "reparto_pct": "40"})).status_code == 422  # reparto sin segundo espacio
    assert (await control.put(f"{API}/trazos/{uuid.uuid4()}/espacio", json={"espacio_id": recamara["id"]})).status_code == 404
    # Un polígono (una losa) se asigna a un espacio, pero no se comparte.
    plano = (await control.get(f"{API}/obras/{escenario.obra_id}/planos")).json()[0]["id"]
    poligono = (
        await control.post(
            f"{API}/planos/{plano}/trazos",
            json={"version_plano": 1, "fuente": "pdf", "geometria_wkt": "POLYGON((0 0, 2 0, 2 2, 0 2, 0 0))", "enlaces": []},
        )
    ).json()["trazo_id"]
    assert (await control.put(f"{API}/trazos/{poligono}/espacio", json={"espacio_id": recamara["id"]})).status_code == 200
    r = await control.put(f"{API}/trazos/{poligono}/espacio", json={"espacio_id": recamara["id"], "espacio_comparte_id": bano["id"]})
    assert r.status_code == 422 and "Solo un muro" in r.text


# ── La losa por espacio ──────────────────────────────────────────────────────────────────────


async def _zona_de_dos_cuartos(c: httpx.AsyncClient, escenario: Escenario) -> tuple[str, str, str, str]:
    plano = (await c.post(f"{API}/obras/{escenario.obra_id}/planos", json={"nombre": "PB", "archivo_url": "e2e/pb.pdf"})).json()["id"]
    zona = (await c.post(f"{API}/planos/{plano}/zonas-de-losa", json={"nombre": "Entrepiso", "altura_libre_m": "3.00", "espesor_m": "0.12"})).json()
    poligonos = []
    for wkt in ("POLYGON((0 -4, 3 -4, 3 0, 0 0, 0 -4))", "POLYGON((3 -4, 5 -4, 5 0, 3 0, 3 -4))"):  # 12 m² y 8 m²
        trazo = (await c.post(f"{API}/planos/{plano}/trazos", json={"version_plano": 1, "fuente": "pdf", "geometria_wkt": wkt, "enlaces": []})).json()["trazo_id"]
        assert (await c.put(f"{API}/trazos/{trazo}/losa", json={"zona_id": zona["id"]})).status_code == 200
        poligonos.append(trazo)
    return plano, zona["id"], poligonos[0], poligonos[1]


async def test_la_matriz_de_la_zona_se_reparte_por_espacio_y_la_suma_es_la_zona(control: httpx.AsyncClient, escenario: Escenario) -> None:
    _plano, zona, p_recamara, p_bano = await _zona_de_dos_cuartos(control, escenario)
    recamara, bano = await _espacio(control, escenario.obra_id, "Recámara 1"), await _espacio(control, escenario.obra_id, "Baño")
    sin = (await control.get(f"{API}/zonas-de-losa/{zona}/matriz")).json()
    assert [g["espacio_id"] for g in sin["por_espacio"]] == [None]  # sin asignar: un solo grupo, como siempre
    assert sin["area_m2"] == pytest.approx(20.0)

    assert (await control.put(f"{API}/trazos/{p_recamara}/espacio", json={"espacio_id": recamara["id"]})).status_code == 200
    assert (await control.put(f"{API}/trazos/{p_bano}/espacio", json={"espacio_id": bano["id"]})).status_code == 200
    e1 = await control.post(f"{API}/zonas-de-losa/{zona}/elementos", json={"elemento_clave": "T-1-15x25", "cantidad": 5, "espacio_id": recamara["id"]})
    assert e1.status_code == 201 and e1.json()["espacio_id"] == recamara["id"], e1.text
    e2 = await control.post(f"{API}/zonas-de-losa/{zona}/elementos", json={"elemento_clave": "T-1-15x25", "cantidad": 2.5, "pago": "propio", "espacio_id": bano["id"]})
    assert e2.status_code == 201, e2.text
    suelto = await control.post(f"{API}/zonas-de-losa/{zona}/elementos", json={"elemento_clave": "CT1-15x25", "cantidad": 3})
    assert suelto.status_code == 201 and suelto.json()["espacio_id"] is None

    m = (await control.get(f"{API}/zonas-de-losa/{zona}/matriz")).json()
    grupos = {g["espacio_id"]: g for g in m["por_espacio"]}
    assert set(grupos) == {recamara["id"], bano["id"], None}
    assert grupos[recamara["id"]]["espacio_nombre"] == "Recámara 1" and grupos[recamara["id"]]["area_m2"] == pytest.approx(12.0)
    assert grupos[bano["id"]]["area_m2"] == pytest.approx(8.0)
    assert grupos[None]["area_m2"] == pytest.approx(0.0)
    assert sum(g["area_m2"] for g in m["por_espacio"]) == pytest.approx(m["area_m2"])
    assert sum(g["longitud_de_elementos_ml"] for g in m["por_espacio"]) == pytest.approx(m["totales"]["longitud_de_elementos_ml"])
    assert sum(g["concreto_m3"] for g in m["por_espacio"]) == pytest.approx(m["totales"]["concreto_m3"])
    assert {x["id"]: x["espacio_id"] for x in m["losas"]} == {p_recamara: recamara["id"], p_bano: bano["id"]}
    # Nada del catálogo ni del árbol todavía: los conceptos avisan por qué no cuentan (propuesto, sin concepto, falta partida, sin espacio).
    estados = {(g["espacio_id"], c["parte"], c["concepto"]["clave"]): c["resolucion"]["estado"] for g in m["por_espacio"] for c in g["conceptos"]}
    assert estados[(recamara["id"], "losa", "EJ-800")] == "propuesto"
    assert estados[(None, "acero", elemento_estructural("CT1-15x25")["catalogo"][0]["clave"])] == "sin_espacio"

    # Cambiar un elemento de espacio y borrarlo.
    r = await control.put(
        f"{API}/elementos-de-losa/{suelto.json()['id']}", json={"elemento_clave": "CT1-15x25", "cantidad": 3, "espacio_id": bano["id"]}
    )
    assert r.status_code == 200 and r.json()["espacio_id"] == bano["id"]
    espacios = {e["id"]: e for e in (await control.get(f"{API}/obras/{escenario.obra_id}/espacios")).json()}
    assert (espacios[recamara["id"]]["losas"], espacios[recamara["id"]]["elementos"]) == (1, 1)
    assert (espacios[bano["id"]]["losas"], espacios[bano["id"]]["elementos"]) == (1, 2)
    # Un espacio que no existe en la obra no vale.
    r = await control.put(f"{API}/elementos-de-losa/{suelto.json()['id']}", json={"elemento_clave": "CT1-15x25", "cantidad": 3, "espacio_id": str(uuid.uuid4())})
    assert r.status_code == 422 and "no existe" in r.text


async def test_lo_que_paga_la_losa_de_cada_espacio_se_escribe_en_la_partida_de_ese_espacio_y_suma_la_zona(
    control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, str]
) -> None:
    plano, zona, _p_recamara, _p_bano = await _zona_de_dos_cuartos(control, escenario)
    assert (await control.put(f"{API}/planos/{plano}/escala", json={"punto_a": [0, 0], "punto_b": [4, 0], "distancia_m": "4"})).status_code == 200
    aux = elemento_estructural("T-1-15x25")["catalogo"][0]["clave"]  # el auxiliar del catálogo que paga el acero de la trabe, por ml
    concepto = str(uuid.uuid4())
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            unidad = (await c.execute(text("select id from unidad where org_id = :o and clave = 'ml'"), {"o": str(escenario.org_id)})).scalar_one()
            await c.execute(
                text("insert into concepto (id, org_id, clave, descripcion, unidad_id) values (:i, :o, :k, :k, :u)"),
                {"i": concepto, "o": str(escenario.org_id), "k": aux, "u": str(unidad)},
            )
    finally:
        await motor.dispose()
    recamara, bano = await _espacio(control, escenario.obra_id, "Recámara 1"), await _espacio(control, escenario.obra_id, "Baño")
    de_r, de_b = await _rama_de_espacio(escenario, arbol, "Recámara 1", concepto), await _rama_de_espacio(escenario, arbol, "Baño", concepto)
    for espacio, rama in ((recamara, de_r), (bano, de_b)):
        assert (await control.put(f"{API}/espacios/{espacio['id']}/nodos", json={"nodo_ids": [rama["rama"]]})).status_code == 200

    # Sin asignar nada a los espacios, la losa no escribe en ninguna partida (como hasta hoy).
    elementos_nuevos = []
    for ml in (5, 2.5):
        r = await control.post(f"{API}/zonas-de-losa/{zona}/elementos", json={"elemento_clave": "T-1-15x25", "cantidad": ml})
        assert r.status_code == 201, r.text
        elementos_nuevos.append((r.json()["id"], ml))
    assert await _medido(control, escenario, de_r["actividad"]) is None and await _medido(control, escenario, de_b["actividad"]) is None
    # Al asignar cada elemento a su espacio, su acero (ml de trabe) se escribe en la partida de ese espacio.
    for (elemento, ml), espacio in zip(elementos_nuevos, (recamara, bano), strict=True):
        r = await control.put(f"{API}/elementos-de-losa/{elemento}", json={"elemento_clave": "T-1-15x25", "cantidad": ml, "espacio_id": espacio["id"]})
        assert r.status_code == 200, r.text
    assert await _medido(control, escenario, de_r["actividad"]) == pytest.approx(5.0)
    assert await _medido(control, escenario, de_b["actividad"]) == pytest.approx(2.5)

    m = (await control.get(f"{API}/zonas-de-losa/{zona}/matriz")).json()
    cuentan = [(g["espacio_id"], c["resolucion"]["partida_id"], c["cantidad"]) for g in m["por_espacio"] for c in g["conceptos"] if c["resolucion"]["cuenta"]]
    assert sorted(cuentan, key=lambda x: x[2]) == sorted([(recamara["id"], de_r["partida"], 5.0), (bano["id"], de_b["partida"], 2.5)], key=lambda x: x[2])
    assert sum(c for _, _, c in cuentan) == pytest.approx(m["totales"]["longitud_de_elementos_ml"])  # lo escrito suma la zona: sin doble conteo

    # Mover un elemento de espacio mueve su cantidad de una partida a la otra; quitarlo la retira.
    elementos = (await control.get(f"{API}/zonas-de-losa/{zona}/elementos")).json()
    de_cinco = next(e for e in elementos if e["cantidad"] == 5.0)
    r = await control.put(f"{API}/elementos-de-losa/{de_cinco['id']}", json={"elemento_clave": "T-1-15x25", "cantidad": 5, "espacio_id": bano["id"]})
    assert r.status_code == 200
    assert not await _medido(control, escenario, de_r["actividad"])
    assert await _medido(control, escenario, de_b["actividad"]) == pytest.approx(7.5)
    assert (await control.delete(f"{API}/elementos-de-losa/{de_cinco['id']}")).status_code == 204
    assert await _medido(control, escenario, de_b["actividad"]) == pytest.approx(2.5)


# ── Enlace de ranura con capa de espacio ─────────────────────────────────────────────────────


async def test_el_enlace_de_ranura_acepta_la_capa_de_espacio(control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, str]) -> None:
    recamara, bano = await _espacio(control, escenario.obra_id, "Recámara 1"), await _espacio(control, escenario.obra_id, "Baño")
    ruta = f"{API}/obras/{escenario.obra_id}/enlaces-de-ranura"
    r = await control.put(ruta, json={"ranura": "mamposteria:tabique_rojo", "concepto_clave": "CAD-1"})
    assert r.status_code == 201, r.text
    assert r.json()["capa"]["espacio_id"] is None
    r = await control.put(ruta, json={"ranura": "mamposteria:tabique_rojo", "concepto_clave": "COL-1", "espacio_id": recamara["id"]})
    assert r.status_code == 201 and r.json()["capa"]["espacio_id"] == recamara["id"], r.text
    # La misma capa (ranura + espacio) cambia el concepto en vez de duplicar.
    r = await control.put(ruta, json={"ranura": "mamposteria:tabique_rojo", "concepto_clave": "ACE-1", "espacio_id": recamara["id"]})
    assert r.status_code == 200 and r.json()["concepto_clave"] == "ACE-1"
    listado = (await control.get(ruta)).json()
    assert [e["id"] for e in listado["enlaces"]].__len__() == 2
    assert [e["nombre"] for e in listado["espacios"]] == ["Recámara 1", "Baño"]
    r = await control.put(ruta, json={"ranura": "mamposteria:tabique_rojo", "concepto_clave": "ACE-1", "espacio_id": str(uuid.uuid4())})
    assert r.status_code == 422 and "espacio no existe" in r.text
    # Lo que cuenta depende de dónde se mide: el enlace del espacio solo aplica ahí.
    url = f"{ruta}/resolver"
    en_recamara = (await control.get(url, params={"ranura": "mamposteria:tabique_rojo", "espacio_id": recamara["id"]})).json()
    en_bano = (await control.get(url, params={"ranura": "mamposteria:tabique_rojo", "espacio_id": bano["id"]})).json()
    assert (en_recamara["concepto_clave"], en_bano["concepto_clave"]) == ("ACE-1", "CAD-1")


# ── El árbol propio de la obra ───────────────────────────────────────────────────────────────


async def test_al_crear_el_arbol_propio_las_ramas_del_espacio_siguen_a_sus_nodos_copiados(
    control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, str]
) -> None:
    recamara = await _espacio(control, escenario.obra_id, "Recámara 1")
    rama = await _rama_de_espacio(escenario, arbol, "Recámara 1", arbol["cadena"])
    assert (await control.put(f"{API}/espacios/{recamara['id']}/nodos", json={"nodo_ids": [rama["rama"]]})).status_code == 200
    r = await control.post(f"{API}/obras/{escenario.obra_id}/arbol/propio")
    assert r.status_code == 201, r.text
    nodos = (await control.get(f"{API}/obras/{escenario.obra_id}/arbol")).json()["nodos"]
    (copiada,) = [e for e in (await control.get(f"{API}/obras/{escenario.obra_id}/espacios")).json() if e["id"] == recamara["id"]]
    (nodo,) = copiada["nodos"]
    assert nodo != rama["rama"]  # el nodo del prototipo base ya no es el de la obra: la rama siguió a la copia
    assert next(n for n in nodos if n["id"] == nodo)["nombre"] == "Recámara 1"
