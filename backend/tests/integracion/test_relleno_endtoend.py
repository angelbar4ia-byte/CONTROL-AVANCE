"""El relleno como elemento (Fase 3, migración 0144) por HTTP de punta a punta contra Postgres real.

Los rellenos de una zona de losa (de azotea con el concepto ALB-03014 del catálogo y compactado con el concepto nuevo propuesto EJ-810), su medición derivada
de los polígonos del plano y de la escala, los espesores de losa distintos de las subzonas, la conciliación contra el catálogo vigente sin tocarlo, el ciclo
de la propuesta, los roles (solo Control de obra escribe; todos los que ven el plano leen) y lo que cada espacio escribe en su partida sin doble conteo."""

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
    _zona_de_dos_cuartos,
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


def _rellenos(zona: str) -> str:
    return f"{API}/zonas-de-losa/{zona}/rellenos"


async def _calculo(c: httpx.AsyncClient, zona: str, **params: Any) -> dict:
    r = await c.get(f"{_rellenos(zona)}/calculo", params=params)
    assert r.status_code == 200, r.text
    return r.json()


async def _calibrar(c: httpx.AsyncClient, plano: str, distancia: str = "4") -> None:
    assert (await c.put(f"{API}/planos/{plano}/escala", json={"punto_a": [0, 0], "punto_b": [4, 0], "distancia_m": distancia})).status_code == 200


# ── Los rellenos de una zona y su medición derivada ─────────────────────────────────────────────────


async def test_un_relleno_nace_con_los_valores_de_omision_y_el_cambio_conserva_su_espacio(control: httpx.AsyncClient, escenario: Escenario) -> None:
    _, z = await _zona_con_losas(control, escenario)
    r = await control.post(_rellenos(z["id"]), json={"elemento_clave": "REL-AZOTEA"})
    assert r.status_code == 201, r.text
    nuevo = r.json()
    assert (nuevo["tipo"], nuevo["espesor_m"], nuevo["pendiente_pct"], nuevo["recorrido_m"], nuevo["compensar_espesores"]) == ("azotea", 0.09, 0.0, 0.0, True)
    assert (nuevo["abundamiento_pct"], nuevo["mortero_m3_por_m2"], nuevo["trazo_id"], nuevo["espacio_id"]) == (0.0, 0.0735, None, None)
    espacio = await _espacio(control, escenario.obra_id, "Azotea")
    cambiado = await control.put(f"{API}/rellenos-de-zona/{nuevo['id']}", json={"elemento_clave": "REL-AZOTEA", "espesor_m": 0.12, "espacio_id": espacio["id"]})
    assert cambiado.status_code == 200, cambiado.text
    assert (cambiado.json()["espesor_m"], cambiado.json()["espacio_id"]) == (0.12, espacio["id"])
    # Sin `espacio_id` el relleno conserva su espacio; con `null` se lo quita. Un parámetro que no viene vuelve al de omisión.
    r = await control.put(f"{API}/rellenos-de-zona/{nuevo['id']}", json={"elemento_clave": "REL-AZOTEA", "pendiente_pct": 2, "recorrido_m": 4})
    assert (r.json()["espacio_id"], r.json()["pendiente_pct"], r.json()["espesor_m"]) == (espacio["id"], 2.0, 0.09)
    r = await control.put(f"{API}/rellenos-de-zona/{nuevo['id']}", json={"elemento_clave": "REL-AZOTEA", "espacio_id": None})
    assert r.json()["espacio_id"] is None
    assert [x["id"] for x in (await control.get(_rellenos(z["id"]))).json()] == [nuevo["id"]]
    assert (await control.delete(f"{API}/rellenos-de-zona/{nuevo['id']}")).status_code == 204
    assert (await control.get(_rellenos(z["id"]))).json() == []
    assert (await control.delete(f"{API}/rellenos-de-zona/{nuevo['id']}")).status_code == 404
    assert (await control.put(f"{API}/rellenos-de-zona/{uuid.uuid4()}", json={"elemento_clave": "REL-AZOTEA"})).status_code == 404


async def test_el_calculo_mide_los_poligonos_de_la_zona_con_la_compensacion_de_la_subzona_y_sigue_a_la_escala(
    control: httpx.AsyncClient, escenario: Escenario
) -> None:
    plano, z = await _zona_con_losas(control, escenario)  # cuarto de 24 m² (12 cm) y subzona de 8 m² (20 cm)
    assert (await control.post(_rellenos(z["id"]), json={"elemento_clave": "REL-AZOTEA"})).status_code == 201
    c = await _calculo(control, z["id"])
    assert c["escala_definida"] is False and c["zona"]["espesor_maximo_m"] == pytest.approx(0.20)
    [r] = c["rellenos"]
    assert r["origen"] == "zona" and r["area_m2"] == pytest.approx(32.0)
    # El cuarto de 12 cm recibe la diferencia contra la subzona de 20 cm; la subzona queda en el espesor mínimo.
    assert [p["espesor_m"] for p in r["poligonos"]] == [pytest.approx(0.17), pytest.approx(0.09)]
    assert r["volumen_m3"] == pytest.approx(24 * 0.17 + 8 * 0.09)
    assert any("no tiene escala calibrada" in a for a in r["advertencias"])
    assert c["totales"]["conceptos"][0]["concepto"]["clave"] == "ALB-03014" and c["totales"]["conceptos"][0]["cantidad"] == pytest.approx(32.0)
    # Medición derivada: al calibrar la escala (2 m por unidad) el área escala con el cuadrado y el cálculo lo sigue sin tocar el relleno.
    await _calibrar(control, plano, "8")
    c = await _calculo(control, z["id"])
    assert c["escala_definida"] is True and c["rellenos"][0]["area_m2"] == pytest.approx(128.0)
    assert c["rellenos"][0]["volumen_m3"] == pytest.approx(4 * (24 * 0.17 + 8 * 0.09))
    assert not any("escala" in a for a in c["rellenos"][0]["advertencias"])


async def test_un_relleno_puede_cubrir_un_solo_poligono_y_su_area_sale_de_ese_poligono(control: httpx.AsyncClient, escenario: Escenario) -> None:
    _plano, z = await _zona_con_losas(control, escenario)
    poligonos = {lo["id"]: lo for lo in (await control.get(f"{API}/zonas-de-losa/{z['id']}/matriz")).json()["losas"]}
    subzona = next(i for i, lo in poligonos.items() if lo["subzona"])
    r = await control.post(_rellenos(z["id"]), json={"elemento_clave": "REL-COMPACTADO", "trazo_id": subzona, "espesor_m": 0.15, "abundamiento_pct": 10})
    assert r.status_code == 201 and r.json()["trazo_id"] == subzona, r.text
    [rel] = (await _calculo(control, z["id"]))["rellenos"]
    assert rel["origen"] == "poligono" and rel["area_m2"] == pytest.approx(8.0) and rel["volumen_m3"] == pytest.approx(8 * 0.15)
    assert rel["volumen_suelto_m3"] == pytest.approx(8 * 0.15 * 1.1) and rel["conceptos"][0]["concepto"]["clave"] == "EJ-810"
    # Si el polígono deja de ser de losa, el relleno ya no cubre nada y lo dice.
    assert (await control.put(f"{API}/trazos/{subzona}/losa", json={"zona_id": None})).status_code == 200
    [rel] = (await _calculo(control, z["id"]))["rellenos"]
    assert rel["area_m2"] == 0 and any("ya no es de la losa" in a for a in rel["advertencias"])


async def test_un_elemento_no_cubre_dos_veces_lo_mismo_y_lo_que_no_vale_se_rechaza(control: httpx.AsyncClient, escenario: Escenario) -> None:
    plano, z = await _zona_con_losas(control, escenario)
    poligonos = [lo["id"] for lo in (await control.get(f"{API}/zonas-de-losa/{z['id']}/matriz")).json()["losas"]]
    url = _rellenos(z["id"])
    assert (await control.post(url, json={"elemento_clave": "REL-AZOTEA"})).status_code == 201
    # La zona entera y un polígono del mismo elemento contarían el polígono dos veces; dos de la zona entera, también.
    for mal in ({"elemento_clave": "REL-AZOTEA", "trazo_id": poligonos[0]}, {"elemento_clave": "REL-AZOTEA"}):
        r = await control.post(url, json=mal)
        assert r.status_code == 422 and "dos veces" in r.text, (mal, r.text)
    # Otro elemento sí puede cubrir lo mismo (se paga con otro concepto); dos polígonos distintos del mismo elemento, también.
    assert (await control.post(url, json={"elemento_clave": "REL-COMPACTADO", "trazo_id": poligonos[0]})).status_code == 201
    assert (await control.post(url, json={"elemento_clave": "REL-COMPACTADO", "trazo_id": poligonos[1]})).status_code == 201
    r = await control.post(url, json={"elemento_clave": "REL-COMPACTADO", "trazo_id": poligonos[1]})
    assert r.status_code == 422 and "dos veces" in r.text
    ajeno = await _trazo(control, plano, "POLYGON((20 20, 22 20, 22 22, 20 22, 20 20))")  # un polígono que no es de la losa de la zona
    linea = await _trazo(control, plano, "LINESTRING(0 -2, 6 -2)")
    espesos = [
        ({"elemento_clave": "REL-COMPACTADO", "trazo_id": ajeno}, "no es un polígono de losa"),
        ({"elemento_clave": "REL-COMPACTADO", "trazo_id": linea}, "no es un polígono de losa"),
        ({"elemento_clave": "REL-COMPACTADO", "trazo_id": str(uuid.uuid4())}, ""),
        ({"elemento_clave": "REL-COMPACTADO", "espacio_id": str(uuid.uuid4())}, "espacio no existe"),
        ({"elemento_clave": "REL-COMPACTADO", "mortero_m3_por_m2": 0.07}, "no lleva mortero"),
        ({"elemento_clave": "REL-OTRO"}, ""),
        ({"elemento_clave": "REL-AZOTEA", "espesor_m": -1}, ""),
    ]
    for mal, texto in espesos:
        r = await control.post(url, json=mal)
        assert r.status_code in (404, 422) and texto in r.text, (mal, r.text)
    abund = await control.post(f"{API}/zonas-de-losa/{z['id']}/rellenos", json={"elemento_clave": "REL-AZOTEA", "abundamiento_pct": 5})
    assert abund.status_code == 422
    assert len((await control.get(url)).json()) == 3  # lo que se rechazó no se guardó
    assert (await control.post(f"{API}/zonas-de-losa/{uuid.uuid4()}/rellenos", json={"elemento_clave": "REL-AZOTEA"})).status_code == 404
    assert (await control.get(f"{API}/zonas-de-losa/{uuid.uuid4()}/rellenos/calculo")).status_code == 404


async def test_solo_control_de_obra_escribe_los_rellenos_y_los_demas_roles_leen(
    control: httpx.AsyncClient, costos: httpx.AsyncClient, residente: httpx.AsyncClient, escenario: Escenario
) -> None:
    _, z = await _zona_con_losas(control, escenario)
    nuevo = (await control.post(_rellenos(z["id"]), json={"elemento_clave": "REL-AZOTEA"})).json()
    for otro in (costos, residente):
        assert (await otro.post(_rellenos(z["id"]), json={"elemento_clave": "REL-COMPACTADO"})).status_code == 403
        assert (await otro.put(f"{API}/rellenos-de-zona/{nuevo['id']}", json={"elemento_clave": "REL-AZOTEA", "espesor_m": 0.5})).status_code == 403
        assert (await otro.delete(f"{API}/rellenos-de-zona/{nuevo['id']}")).status_code == 403
        assert [x["id"] for x in (await otro.get(_rellenos(z["id"]))).json()] == [nuevo["id"]]
        assert (await otro.get(f"{_rellenos(z['id'])}/calculo")).status_code == 200
    assert (await control.get(_rellenos(z["id"]))).json()[0]["espesor_m"] == 0.09  # nadie lo cambió


# ── La conciliación contra el catálogo vigente ──────────────────────────────────────────────────────


async def _catalogo_del_relleno(escenario: Escenario) -> str:
    """El concepto ALB-03014 del catálogo con su composición real por m² (tezontle por viaje y mortero), como en ANALISIS_DE_BASICOS_CONCEPTOS."""
    org = str(escenario.org_id)
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            unidades = {}
            for u in ("m2", "m3", "serv"):  # la del árbol (m2) ya puede existir en la organización
                await c.execute(text("insert into unidad (org_id, clave, nombre, sinonimos) values (:o, :u, :u, '{}') on conflict (org_id, clave) do nothing"), {"o": org, "u": u})
                unidades[u] = (await c.execute(text("select id from unidad where org_id = :o and clave = :u"), {"o": org, "u": u})).scalar_one()
            fam = (await c.execute(text("insert into familia (org_id, clave, nombre) values (:o, 'Varios', 'Varios') returning id"), {"o": org})).scalar_one()
            for clave, desc, unidad in (
                ("PET-00069", "TEZONTLE ROJO 7 MTS", "serv"),
                ("CON-00020", "Mortero fc 50 kg/cm2, Normal a 28 días, TMA 05mm Rev 14 cm, bombeado con IMPER 1%", "m3"),
            ):
                await c.execute(
                    text("insert into insumo (org_id, tipo, clave, descripcion, unidad_id, familia_id, costo_base) values (:o, 'material', :k, :d, :u, :f, 10)"),
                    {"o": org, "k": clave, "d": desc, "u": str(unidades[unidad]), "f": str(fam)},
                )
            cid = (
                await c.execute(
                    text("insert into concepto (org_id, clave, descripcion, unidad_id) values (:o, 'ALB-03014', 'Relleno en azotea mezcla antihumedad-arena-arenilla 2:4:10', :u) returning id"),
                    {"o": org, "u": str(unidades["m2"])},
                )
            ).scalar_one()
            for orden, (insumo, cantidad) in enumerate((("PET-00069", 0.012857), ("CON-00020", 0.0735))):
                await c.execute(
                    text(
                        "insert into explosion (org_id, concepto_id, tipo_hijo, insumo_id, categoria, cantidad, orden) "
                        "values (:o, :c, 'insumo', (select id from insumo where org_id = :o and clave = :i), 'material', :q, :n)"
                    ),
                    {"o": org, "c": str(cid), "i": insumo, "q": cantidad, "n": orden},
                )
            return str(cid)
    finally:
        await motor.dispose()


async def test_la_conciliacion_compara_el_relleno_de_azotea_por_m2_con_alb_03014_sin_tocar_el_catalogo(
    control: httpx.AsyncClient, escenario: Escenario
) -> None:
    _plano, zona, _a, _b = await _zona_de_dos_cuartos(control, escenario)
    await _catalogo_del_relleno(escenario)
    assert (await control.post(_rellenos(zona), json={"elemento_clave": "REL-AZOTEA"})).status_code == 201
    [r] = (await _calculo(control, zona, conciliar="true"))["rellenos"]
    filas = {f["clave"]: f for f in r["conciliacion"]["filas"]}
    assert r["conciliacion"]["concepto"]["clave"] == "ALB-03014" and "por m²" in r["conciliacion"]["nota"]
    # Con el espesor del catálogo (9 cm) el tezontle y el mortero por m² coinciden con la composición vigente.
    assert filas["PET-00069"]["marca"] == "=" and filas["PET-00069"]["catalogo"] == pytest.approx(0.012857)
    assert filas["PET-00069"]["elemento"] == pytest.approx(0.012857, rel=1e-3)
    assert filas["CON-00020"]["marca"] == "=" and r["conciliacion"]["coincide"] is True
    # Con otro espesor la diferencia se muestra (no se corrige el catálogo).
    [rel] = (await control.get(_rellenos(zona))).json()
    assert (await control.put(f"{API}/rellenos-de-zona/{rel['id']}", json={"elemento_clave": "REL-AZOTEA", "espesor_m": 0.15})).status_code == 200
    [r] = (await _calculo(control, zona, conciliar="true"))["rellenos"]
    filas = {f["clave"]: f for f in r["conciliacion"]["filas"]}
    assert filas["PET-00069"]["marca"] == "≠" and filas["PET-00069"]["diferencia_pct"] == pytest.approx(66.67, abs=0.1) and r["conciliacion"]["coincide"] is False
    assert any("difiere" in a for a in r["advertencias"])
    # Sin pedirla, no hay conciliación; el catálogo no cambió.
    assert (await _calculo(control, zona))["rellenos"][0]["conciliacion"] is None
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            assert (await c.execute(text("select count(*) from explosion where concepto_id = (select id from concepto where clave = 'ALB-03014')"))).scalar_one() == 2
    finally:
        await motor.dispose()


# ── La propuesta del concepto nuevo del compactado ──────────────────────────────────────────────────


async def test_el_concepto_del_compactado_se_propone_una_vez_y_solo_control_de_obra_lo_autoriza(
    control: httpx.AsyncClient, costos: httpx.AsyncClient, residente: httpx.AsyncClient, escenario: Escenario
) -> None:
    _, z = await _zona_con_losas(control, escenario)
    # Sin un relleno compactado en la zona (y con la azotea, que usa un concepto del catálogo) no hay nada que proponer.
    assert (await control.post(_rellenos(z["id"]), json={"elemento_clave": "REL-AZOTEA"})).status_code == 201
    assert (await costos.post(f"{_rellenos(z['id'])}/propuestas")).json() == {"creadas": [], "omitidas": []}
    assert (await control.post(_rellenos(z["id"]), json={"elemento_clave": "REL-COMPACTADO"})).status_code == 201
    assert (await residente.post(f"{_rellenos(z['id'])}/propuestas")).status_code == 403
    primera = await costos.post(f"{_rellenos(z['id'])}/propuestas")
    assert primera.status_code == 201 and len(primera.json()["creadas"]) == 1
    assert (await costos.post(f"{_rellenos(z['id'])}/propuestas")).json()["omitidas"] == ["EJ-810"]  # idempotente
    assert (await costos.post(f"{API}/biblioteca-de-elementos/relleno/REL-COMPACTADO/propuestas/concepto")).json() == {"creadas": [], "omitidas": ["EJ-810"]}
    c = await _calculo(costos, z["id"])
    compactado = next(r for r in c["rellenos"] if r["tipo"] == "compactado")
    assert compactado["conceptos"][0]["propuesta"]["estado"] == "pendiente"
    azotea = next(r for r in c["rellenos"] if r["tipo"] == "azotea")
    assert azotea["conceptos"][0]["propuesta"] is None  # el concepto del catálogo no se propone

    [p] = (await costos.get(f"{API}/biblioteca-de-elementos/relleno/REL-COMPACTADO/propuestas")).json()
    assert (p["clase"], p["concepto_clave"], p["estado"], p["propuso_rol"], p["elemento_clave"]) == ("concepto_nuevo", "EJ-810", "pendiente", "costos", "REL-COMPACTADO")
    assert any("F7" in x for x in p["motivos"]) and p["destajo_por_definir"] is None
    assert (await costos.post(f"{API}/propuestas-de-estructura/{p['id']}/autorizar")).status_code == 403
    assert (await control.post(f"{API}/propuestas-de-estructura/{p['id']}/autorizar")).json() == {"version": 1}
    c = await _calculo(costos, z["id"])
    assert next(r for r in c["rellenos"] if r["tipo"] == "compactado")["conceptos"][0]["propuesta"]["estado"] == "autorizada"
    # El catálogo no cambia: ningún concepto nuevo se creó en `concepto`.
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as cn:
            assert (await cn.execute(text("select count(*) from concepto where clave = 'EJ-810'"))).scalar_one() == 0
    finally:
        await motor.dispose()
    # El mortero de la azotea usa ALB-03014 del catálogo; su arenilla (relleno con bajadas) propone EJ-830, una sola vez. Una clave que no es de relleno no existe.
    primera_arenilla = await costos.post(f"{API}/biblioteca-de-elementos/relleno/REL-AZOTEA/propuestas/concepto")
    assert primera_arenilla.status_code == 201 and len(primera_arenilla.json()["creadas"]) == 1
    assert (await costos.post(f"{API}/biblioteca-de-elementos/relleno/REL-AZOTEA/propuestas/concepto")).json() == {"creadas": [], "omitidas": ["EJ-830"]}
    for mala in ("LOSA-MACIZA", "REL-OTRO"):
        assert (await costos.post(f"{API}/biblioteca-de-elementos/relleno/{mala}/propuestas/concepto")).status_code == 404
        assert (await costos.get(f"{API}/biblioteca-de-elementos/relleno/{mala}/propuestas")).status_code == 404


# ── La asignación a un espacio y lo que escribe en su partida ───────────────────────────────────────


async def test_el_relleno_de_cada_espacio_se_escribe_en_la_partida_de_ese_espacio_sin_doble_conteo(
    control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, str]
) -> None:
    plano, zona, p_recamara, p_bano = await _zona_de_dos_cuartos(control, escenario)  # 12 m² y 8 m² de 12 cm
    await _calibrar(control, plano)
    alb = await _catalogo_del_relleno(escenario)
    recamara, bano = await _espacio(control, escenario.obra_id, "Recámara 1"), await _espacio(control, escenario.obra_id, "Baño")
    de_r, de_b = await _rama_de_espacio(escenario, arbol, "Recámara 1", alb, "m2"), await _rama_de_espacio(escenario, arbol, "Baño", alb, "m2")
    for espacio, rama in ((recamara, de_r), (bano, de_b)):
        assert (await control.put(f"{API}/espacios/{espacio['id']}/nodos", json={"nodo_ids": [rama["rama"]]})).status_code == 200
    rel = (await control.post(_rellenos(zona), json={"elemento_clave": "REL-AZOTEA"})).json()

    # Sin espacio no se escribe nada (como la losa): el cálculo avisa por qué.
    assert await _medido(control, escenario, de_r["actividad"]) is None and await _medido(control, escenario, de_b["actividad"]) is None
    c = await _calculo(control, zona)
    assert [g["espacio_id"] for g in c["por_espacio"]] == [None]
    assert c["por_espacio"][0]["conceptos"][0]["resolucion"]["estado"] == "sin_espacio"

    # Cada polígono cae en su espacio: cada partida recibe su área y la suma de lo escrito es la del relleno.
    assert (await control.put(f"{API}/trazos/{p_recamara}/espacio", json={"espacio_id": recamara["id"]})).status_code == 200
    assert (await control.put(f"{API}/trazos/{p_bano}/espacio", json={"espacio_id": bano["id"]})).status_code == 200
    assert await _medido(control, escenario, de_r["actividad"]) == pytest.approx(12.0)
    assert await _medido(control, escenario, de_b["actividad"]) == pytest.approx(8.0)
    c = await _calculo(control, zona)
    cuentan = {g["espacio_id"]: c2["resolucion"] for g in c["por_espacio"] for c2 in g["conceptos"] if c2["resolucion"]["cuenta"]}
    assert {k: v["partida_id"] for k, v in cuentan.items()} == {recamara["id"]: de_r["partida"], bano["id"]: de_b["partida"]}
    assert sum(g["conceptos"][0]["cantidad"] for g in c["por_espacio"]) == pytest.approx(c["totales"]["conceptos"][0]["cantidad"])
    assert {g["espacio_nombre"] for g in c["por_espacio"]} == {"Recámara 1", "Baño"}

    # El espacio del relleno manda sobre el de sus polígonos: todo pasa a la partida del baño, sin quedarse nada en la recámara.
    r = await control.put(f"{API}/rellenos-de-zona/{rel['id']}", json={"elemento_clave": "REL-AZOTEA", "espacio_id": bano["id"]})
    assert r.status_code == 200
    assert not await _medido(control, escenario, de_r["actividad"])
    assert await _medido(control, escenario, de_b["actividad"]) == pytest.approx(20.0)
    # Un relleno solo del polígono de la recámara: el de la zona entera deja de ser válido junto a él, así que se cambia a uno solo.
    assert (await control.delete(f"{API}/rellenos-de-zona/{rel['id']}")).status_code == 204
    assert not await _medido(control, escenario, de_b["actividad"])
    solo = await control.post(_rellenos(zona), json={"elemento_clave": "REL-AZOTEA", "trazo_id": p_recamara})
    assert solo.status_code == 201, solo.text
    assert await _medido(control, escenario, de_r["actividad"]) == pytest.approx(12.0) and not await _medido(control, escenario, de_b["actividad"])
    # El compactado, mientras su concepto sea una propuesta, informa su cantidad pero no escribe en ninguna partida.
    comp = await control.post(_rellenos(zona), json={"elemento_clave": "REL-COMPACTADO", "espacio_id": recamara["id"]})
    assert comp.status_code == 201
    c = await _calculo(control, zona)
    estados = {x["concepto"]["clave"]: x["resolucion"]["estado"] for g in c["por_espacio"] for x in g["conceptos"]}
    assert estados == {"ALB-03014": "cuenta", "EJ-810": "propuesto"}
    assert await _medido(control, escenario, de_r["actividad"]) == pytest.approx(12.0)


async def test_sin_escala_calibrada_el_relleno_no_escribe_en_ninguna_partida(control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, str]) -> None:
    plano, zona, p_recamara, _ = await _zona_de_dos_cuartos(control, escenario)
    alb = await _catalogo_del_relleno(escenario)
    recamara = await _espacio(control, escenario.obra_id, "Recámara 1")
    de_r = await _rama_de_espacio(escenario, arbol, "Recámara 1", alb, "m2")
    assert (await control.put(f"{API}/espacios/{recamara['id']}/nodos", json={"nodo_ids": [de_r["rama"]]})).status_code == 200
    assert (await control.put(f"{API}/trazos/{p_recamara}/espacio", json={"espacio_id": recamara["id"]})).status_code == 200
    assert (await control.post(_rellenos(zona), json={"elemento_clave": "REL-AZOTEA"})).status_code == 201
    assert await _medido(control, escenario, de_r["actividad"]) is None  # 1 unidad de plano = 1 m solo sirve para mostrar
    await _calibrar(control, plano)
    # Calibrar el plano no rehace las tomas por sí solo (igual que con la losa): se rehacen al pedirlas.
    assert (await control.post(f"{API}/obras/{escenario.obra_id}/tomas/sincronizar")).status_code in (200, 204)
    assert await _medido(control, escenario, de_r["actividad"]) == pytest.approx(12.0)
