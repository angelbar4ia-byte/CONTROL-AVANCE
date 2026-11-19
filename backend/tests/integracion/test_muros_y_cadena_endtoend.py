"""Plantilla 2 «muros y cadena», castillo a mano con elección de K y «cambiar de plantilla» sin perder lo medido, por HTTP contra Postgres real.

Con plano estructural el muro lleva solo el muro y las cadenas (plantilla 2) y los castillos reales se siembran uno por uno en el plano, cada
uno de su tipo K del catálogo. Un trazo pasa de la plantilla 1 (muro confinado, que estima los castillos) a la 2 y viceversa sin perder la
medición del muro ni sus vanos; antes de cambiar se dice qué cambia.
"""

# ruff: noqa: F811  (las fixtures `control` y `arbol` se importan de la prueba de plantillas por prototipo y se usan como parámetros)
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario
from tests.integracion.test_plantillas_de_prototipo_endtoend import (  # noqa: F401  (fixtures y ayudas compartidas)
    ELEMENTOS,
    PARTES,
    PLANTILLAS,
    _conceptos_de_los_elementos,
    _elementos_de_oro,
    _medido,
    _muro,
    arbol,
    control,
)


async def _segundo_castillo_con_sus_conceptos(control: httpx.AsyncClient, escenario: Escenario, ids: dict[str, str]) -> dict[str, str]:
    """K-2 se paga con otros conceptos que K-1 (acero ACE-2 y colado COL-2), con una partida y una actividad en planta baja."""
    nuevo = {k: str(uuid.uuid4()) for k in ("acero", "colado", "a_acero", "a_colado")}
    org, proto, obra = str(escenario.org_id), str(escenario.prototipo_id), str(escenario.obra_id)
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            u = {r[0]: r[1] for r in (await c.execute(text("select clave, id from unidad where org_id = :o"), {"o": org})).all()}
            n1 = (await c.execute(text("select id from nivel where org_id = :o and orden = 1"), {"o": org})).scalar_one()
            etapa = (await c.execute(text("select id from etapa_constructiva where org_id = :o"), {"o": org})).scalar_one()
            padre = (
                await c.execute(text("select id from prototipo_nodo where prototipo_id = :p and tipo = 'etapa'"), {"p": proto})
            ).scalar_one()
            for k, clave, unidad in (("acero", "ACE-2", "pza"), ("colado", "COL-2", "ml")):
                await c.execute(
                    text("insert into concepto (id, org_id, clave, descripcion, unidad_id) values (:i, :o, :k, :k, :u)"),
                    {"i": nuevo[k], "o": org, "k": clave, "u": str(u[unidad])},
                )
                await c.execute(
                    text(
                        "insert into prototipo_nodo (id, org_id, prototipo_id, parent_id, tipo, nombre, clave, concepto_id, orden) "
                        "values (gen_random_uuid(), :o, :p, :pa, 'concepto', :k, :k, :c, 0)"
                    ),
                    {"o": org, "p": proto, "pa": str(padre), "k": clave, "c": nuevo[k]},
                )
                await c.execute(
                    text(
                        "insert into actividad (id, org_id, obra_id, concepto_id, nivel_id, etapa_id, cant_base, cant_programada, precio_unitario) "
                        "values (:i, :o, :ob, :c, :n, :e, 100, 100, 10)"
                    ),
                    {"i": nuevo[f"a_{k}"], "o": org, "ob": obra, "c": nuevo[k], "n": str(n1), "e": str(etapa)},
                )
    finally:
        await motor.dispose()
    ruta = f"{ELEMENTOS}/{ids['K-2']}/conceptos-por-contexto"
    for cuerpo in (
        {"concepto_id": nuevo["acero"], "unidad": "pza", "toma": {"acero": True, "estribos": True, "alambre": True}, "alto_hasta_m": "6"},
        {"concepto_id": nuevo["colado"], "unidad": "ml", "toma": {"concreto": True, "cimbra": True}},
    ):
        r = await control.post(ruta, json=cuerpo)
        assert r.status_code == 201, r.text
    return nuevo


def _plantilla_2(**cambios: object) -> dict[str, Any]:
    """«Muros y cadena»: el muro y la cadena, sin castillos (se siembran a mano)."""
    return {
        "nombre": "Muros y cadena", "tipo": "con_cadena", "material": "tabique_rojo", "ubicacion": "interior", "partes": PARTES,
        "elementos": [{"ref": "CE-1"}], **cambios,
    }


def _plantilla_1(**cambios: object) -> dict[str, Any]:
    """Muro confinado: propone los castillos (K-1 por ml) y lleva la misma cadena."""
    return {
        "nombre": "Confinado", "tipo": "confinado", "material": "tabique_rojo", "ubicacion": "interior", "partes": PARTES,
        "elementos": [{"ref": "K-1", "regla": "por_ml", "piezas_por_ml": "0.4"}, {"ref": "CE-1"}], **cambios,
    }


async def _sembrar(control: httpx.AsyncClient, muro: str, clave: str, posicion: str, elemento_ref: str | None = None) -> httpx.Response:
    cuerpo: dict[str, Any] = {"clave": clave, "tipo": "castillo", "ancho_m": "0.15", "alto_m": "1", "posicion_m": posicion}
    if elemento_ref is not None:
        cuerpo["elemento_ref"] = elemento_ref
    return await control.post(f"/api/v1/trazos/{muro}/vanos", json=cuerpo)


async def test_la_plantilla_2_se_crea_sin_castillos_y_cada_castillo_a_mano_elige_su_k_y_alimenta_sus_conceptos(
    control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, str]
) -> None:
    ids = await _elementos_de_oro(control)
    await _conceptos_de_los_elementos(control, arbol, ids)
    k2 = await _segundo_castillo_con_sus_conceptos(control, escenario, ids)
    r = await control.post(PLANTILLAS, json=_plantilla_2())
    assert r.status_code == 201, r.text
    assert [e["ref"] for e in r.json()["elementos"]] == ["CE-1"]  # solo la cadena: el castillo real se siembra en el plano
    muro = await _muro(control, escenario)
    assert (await control.put(f"/api/v1/trazos/{muro}/muro/plantilla", json={"plantilla_id": r.json()["id"]})).status_code == 200

    # Cada castillo elige su K del catálogo (cualquiera, no el primero de la plantilla).
    assert (await _sembrar(control, muro, "K-01", "1", "K-1")).status_code == 201
    assert (await _sembrar(control, muro, "K-02", "5", "K-2")).status_code == 201
    assert (await _sembrar(control, muro, "K-03", "9", "k-2")).status_code == 201  # la clave no distingue mayúsculas
    vanos = (await control.get(f"/api/v1/trazos/{muro}/vanos")).json()
    assert [(v["tipo"], v["elemento_uid"], Decimal(v["alto_m"])) for v in vanos] == [("castillo", "K-1", Decimal(3)), ("castillo", "K-2", Decimal(3)), ("castillo", "K-2", Decimal(3))]
    # Cada uno paga con los conceptos de SU elemento: K-1 con ACE-1/COL-1 y K-2 con ACE-2/COL-2.
    assert await _medido(control, escenario, arbol["a_acero"]) == pytest.approx(1)
    assert await _medido(control, escenario, arbol["a_colado"]) == pytest.approx(3)
    assert await _medido(control, escenario, k2["a_acero"]) == pytest.approx(2)
    assert await _medido(control, escenario, k2["a_colado"]) == pytest.approx(6)
    # La cadena sigue alimentando su concepto (al elegir la plantilla): los 10 m del muro.
    assert await _medido(control, escenario, arbol["a_cadena"]) == pytest.approx(10)

    # Quitar un castillo rehace lo que toma su concepto.
    quitado = next(v for v in vanos if v["clave"] == "K-03")
    assert (await control.delete(f"/api/v1/vanos/{quitado['id']}")).status_code == 200
    assert await _medido(control, escenario, k2["a_acero"]) == pytest.approx(1)


async def test_el_castillo_a_mano_pide_un_castillo_del_catalogo_y_en_la_plantilla_1_no_se_siembra(
    control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, str]
) -> None:
    await _elementos_de_oro(control)
    p2 = (await control.post(PLANTILLAS, json=_plantilla_2())).json()
    p1 = (await control.post(PLANTILLAS, json=_plantilla_1())).json()
    muro = await _muro(control, escenario)
    assert (await control.put(f"/api/v1/trazos/{muro}/muro/plantilla", json={"plantilla_id": p2["id"]})).status_code == 200
    # Sin K elegido y sin castillos en la plantilla: hay que elegir.
    sin = await _sembrar(control, muro, "K-01", "1")
    assert sin.status_code == 422 and "elige el castillo" in sin.text
    # Una cadena o una clave inexistente no es un castillo.
    for malo in ("CE-1", "K-99"):
        x = await _sembrar(control, muro, "K-01", "1", malo)
        assert x.status_code == 422 and "no es un castillo" in x.text, malo
    # El muro confinado estima sus castillos: no se siembran.
    assert (await control.put(f"/api/v1/trazos/{muro}/muro/plantilla", json={"plantilla_id": p1["id"]})).status_code == 200
    x = await _sembrar(control, muro, "K-01", "1", "K-1")
    assert x.status_code == 422 and "confinado" in x.text
    assert (await control.get(f"/api/v1/trazos/{muro}/vanos")).json() == []


async def test_colocar_y_retirar_la_plantilla_no_tocan_el_castillo_sembrado_de_otro_k(
    control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, str]
) -> None:
    ids = await _elementos_de_oro(control)
    await _conceptos_de_los_elementos(control, arbol, ids)
    r = await control.post(PLANTILLAS, json=_plantilla_2(nombre="Con K-1 ubicado", elementos=[{"ref": "K-1"}, {"ref": "CE-1"}]))
    assert r.status_code == 201, r.text
    muro = await _muro(control, escenario)
    assert (await control.put(f"/api/v1/trazos/{muro}/muro/plantilla", json={"plantilla_id": r.json()["id"]})).status_code == 200
    assert (await _sembrar(control, muro, "K-09", "4", "K-2")).status_code == 201  # sembrado a mano con otro K
    ruta = f"/api/v1/trazos/{muro}/muro/plantilla/colocar"
    assert (await control.post(ruta)).json()["colocados"] == 2
    por_uid = lambda vs: sorted(v["elemento_uid"] for v in vs)  # noqa: E731
    assert por_uid((await control.get(f"/api/v1/trazos/{muro}/vanos")).json()) == ["K-1", "K-1", "K-2"]
    assert (await control.post(ruta)).json()["reemplazados"] == 2  # solo reemplaza lo suyo
    assert (await control.delete(ruta)).json() == {"retirados": 2}
    assert por_uid((await control.get(f"/api/v1/trazos/{muro}/vanos")).json()) == ["K-2"]  # el castillo sembrado de K-2 sigue


async def test_cambiar_de_la_plantilla_1_a_la_2_y_volver_dice_que_cambia_y_no_pierde_lo_medido(
    control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, str]
) -> None:
    ids = await _elementos_de_oro(control)
    await _conceptos_de_los_elementos(control, arbol, ids)
    p1 = (await control.post(PLANTILLAS, json=_plantilla_1())).json()
    p2 = (await control.post(PLANTILLAS, json=_plantilla_2())).json()
    muro = await _muro(control, escenario)
    ruta = f"/api/v1/trazos/{muro}/muro/plantilla"
    assert (await control.put(ruta, json={"plantilla_id": p1["id"]})).status_code == 200
    # Plantilla 1: K-1 estimado por ml (10 ml × 0.4 = 4 piezas) y la cadena de 10 m alimentan sus conceptos.
    assert await _medido(control, escenario, arbol["a_acero"]) == pytest.approx(4)
    assert await _medido(control, escenario, arbol["a_cadena"]) == pytest.approx(10)
    medida = await _medido(control, escenario, str(escenario.actividad_id))
    assert medida == pytest.approx(30)

    # --- De la 1 a la 2: dice qué cambia y no cambia nada hasta confirmar -------------------------------------------------
    v = (await control.get(f"{ruta}/cambio", params={"hacia": p2["id"]})).json()
    assert (v["de"]["tipo"], v["hacia"]["tipo"]) == ("confinado", "con_cadena")
    assert [(c["campo"], c["de"], c["a"]) for c in v["cambia"]] == [("tipo", "confinado", "con_cadena")]
    efectos = {e["ref"]: e["efecto"] for e in v["efectos"]}
    assert efectos == {"K-1": "deja", "CE-1": "sigue"}
    assert Decimal(next(e for e in v["efectos"] if e["ref"] == "K-1")["piezas"]) == Decimal(4)
    assert any("dejan de contarse" in a for a in v["avisos"]) and any("uno por uno" in a for a in v["avisos"])
    assert any("medición del muro" in c for c in v["conserva"])
    assert (await control.get(f"/api/v1/trazos/{muro}/muro/clasificacion")).json()["plantilla_id"] == p1["id"]  # sin cambiar

    r = await control.post(f"{ruta}/cambio", json={"plantilla_id": p2["id"]})
    assert r.status_code == 200, r.text
    assert (r.json()["antes"]["tipo"], r.json()["despues"]["tipo"], r.json()["retirados"]) == ("confinado", "con_cadena", 0)
    clasificacion = (await control.get(f"/api/v1/trazos/{muro}/muro/clasificacion")).json()
    assert (clasificacion["plantilla_id"], clasificacion["tipo"]) == (p2["id"], "con_cadena")
    # Lo medido sigue: el muro mide lo mismo, la cadena sigue contando y los castillos estimados dejan de contarse.
    assert await _medido(control, escenario, str(escenario.actividad_id)) == pytest.approx(medida)
    assert await _medido(control, escenario, arbol["a_cadena"]) == pytest.approx(10)
    assert not await _medido(control, escenario, arbol["a_acero"])

    # --- Se siembran dos castillos reales; volver a la 1 avisa que se contarían dos veces ---------------------------------
    assert (await _sembrar(control, muro, "K-01", "2", "K-1")).status_code == 201
    assert (await _sembrar(control, muro, "K-02", "7", "K-1")).status_code == 201
    con_castillos = await _medido(control, escenario, str(escenario.actividad_id))
    assert con_castillos == pytest.approx(30 - 2 * 0.15 * 3)
    v2 = (await control.get(f"{ruta}/cambio", params={"hacia": p1["id"]})).json()
    assert v2["castillos_sembrados"] == 2
    assert {e["ref"]: e["efecto"] for e in v2["efectos"]} == {"K-1": "nuevo", "CE-1": "sigue"}
    assert any("dos veces" in a for a in v2["avisos"])
    efecto_k1 = next(e for e in v2["efectos"] if e["ref"] == "K-1")
    assert [Decimal(efecto_k1[k]) for k in ("piezas_estimadas", "piezas_sembradas", "piezas")] == [Decimal(4), Decimal(2), Decimal(2)]
    assert any("estimados 4, sembrados 2, contados 2" in a for a in v2["avisos"]), v2["avisos"]

    # Sin retirar: los castillos sembrados y la medición se conservan (lo medido no se pierde).
    conserva = await control.post(f"{ruta}/cambio", json={"plantilla_id": p1["id"]})
    assert (conserva.json()["retirados"], conserva.json()["conservados"]) == (0, 2)
    assert len((await control.get(f"/api/v1/trazos/{muro}/vanos")).json()) == 2
    assert await _medido(control, escenario, str(escenario.actividad_id)) == pytest.approx(con_castillos)
    # Los sembrados no se cuentan dos veces: K-1 estima 4 piezas, hay 2 sembradas → la plantilla cuenta 2 y el acero de K-1 suma 4 (2 + 2), no 6.
    c = (await control.get(f"{ruta}/colocacion")).json()
    k1 = next(e for e in c["elementos"] if e["ref"] == "K-1")
    assert [Decimal(k1[k]) for k in ("piezas_estimadas", "piezas_sembradas", "piezas_contadas")] == [Decimal(4), Decimal(2), Decimal(2)]
    assert any("estimados 4, sembrados 2, contados 2" in a for a in c["avisos"])
    assert await _medido(control, escenario, arbol["a_acero"]) == pytest.approx(4)
    # Al retirar los sembrados, el muro recupera sus m² y el confinado vuelve a estimar los suyos.
    asi = await control.post(f"{ruta}/cambio", json={"plantilla_id": p2["id"]})
    assert asi.status_code == 200
    retirados = await control.post(f"{ruta}/cambio", json={"plantilla_id": p1["id"], "retirar_castillos": True})
    assert (retirados.json()["retirados"], retirados.json()["conservados"]) == (2, 0)
    assert (await control.get(f"/api/v1/trazos/{muro}/vanos")).json() == []
    assert await _medido(control, escenario, str(escenario.actividad_id)) == pytest.approx(medida)
    assert await _medido(control, escenario, arbol["a_acero"]) == pytest.approx(4)


async def test_cambiar_a_una_plantilla_que_no_existe_o_en_un_trazo_ajeno_es_404(control: httpx.AsyncClient, escenario: Escenario) -> None:
    muro = await _muro(control, escenario)
    ruta = f"/api/v1/trazos/{muro}/muro/plantilla/cambio"
    falsa = str(uuid.uuid4())
    assert (await control.get(ruta, params={"hacia": falsa})).status_code == 404
    assert (await control.post(ruta, json={"plantilla_id": falsa})).status_code == 404
    existente = (await control.post(PLANTILLAS, json={"nombre": "T", "tipo": "tabique", "material": "tabique_rojo", "ubicacion": "interior"})).json()
    assert (await control.get(f"/api/v1/trazos/{uuid.uuid4()}/muro/plantilla/cambio", params={"hacia": existente["id"]})).status_code == 404


async def test_cambiar_de_plantilla_conserva_el_acabado_ya_capturado(control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, str]) -> None:
    await _elementos_de_oro(control)
    # El acabado de cada plantilla es el defecto (todo en Sí); el del muro lo capturó el cliente y no coincide con ninguna.
    p1 = (await control.post(PLANTILLAS, json=_plantilla_1())).json()
    p2 = (await control.post(PLANTILLAS, json=_plantilla_2())).json()
    muro = await _muro(control, escenario)
    ruta = f"/api/v1/trazos/{muro}/muro/plantilla"
    assert (await control.put(ruta, json={"plantilla_id": p1["id"]})).status_code == 200
    propio = {"interior": {"gris": True, "blanca": False, "pintura": False}, "fachada": {"gris": True, "blanca": True, "pintura": False}}
    fijado = await control.put(f"/api/v1/trazos/{muro}/muro/clasificacion", json={"tipo": "confinado", "acabado": propio})
    assert fijado.status_code == 200, fijado.text
    v = (await control.get(f"{ruta}/cambio", params={"hacia": p2["id"]})).json()
    assert v["acabado_se_conserva"] is True
    assert any("acabado ya capturado se conserva" in a for a in v["avisos"]) and any("acabado ya capturado" in c for c in v["conserva"])
    assert (await control.post(f"{ruta}/cambio", json={"plantilla_id": p2["id"]})).status_code == 200
    despues = (await control.get(f"/api/v1/trazos/{muro}/muro/clasificacion")).json()
    assert (despues["tipo"], despues["plantilla_id"]) == ("con_cadena", p2["id"])
    assert despues["acabado"] == propio
    # Y de vuelta: sigue siendo el del cliente.
    assert (await control.post(f"{ruta}/cambio", json={"plantilla_id": p1["id"]})).status_code == 200
    assert (await control.get(f"/api/v1/trazos/{muro}/muro/clasificacion")).json()["acabado"] == propio
