"""El relleno dinámico de azotea (migración 0147) por HTTP de punta a punta contra Postgres real.

Bajadas pluviales como PUNTOS del plano, la línea de pendiente (trazada o generada), la arenilla de espesor variable con su concepto propuesto EJ-830 y el mortero
de 5 cm con ALB-03014, las guías (líneas de pendiente e hilos de nivel), los roles, lo que no se cuenta dos veces, la zona sin escala y el factor de abundamiento
del compactado."""

# ruff: noqa: F811  (las fixtures se importan de otras pruebas y se usan como parámetros)
from __future__ import annotations

import math
import uuid

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario
from tests.integracion.test_espacios_endtoend import _espacio  # noqa: F401
from tests.integracion.test_matriz_de_losa_endtoend import (  # noqa: F401
    _trazo,
    _zona_con_losas,
    control,
    costos,
    residente,
)
from tests.integracion.test_plantillas_de_prototipo_endtoend import arbol  # noqa: F401
from tests.integracion.test_relleno_endtoend import _calculo, _calibrar, _rellenos

API = "/api/v1"


def _ref(a: float, b: float, pendiente_pct: float, e0: float = 0.05, n: int = 500) -> float:
    """El volumen por fuerza bruta de un rectángulo a × b con la bajada en una esquina (referencia independiente del módulo)."""
    hx, hy = a / n, b / n
    suma = sum(math.hypot((i + 0.5) * hx, (j + 0.5) * hy) for i in range(n) for j in range(n)) * hx * hy
    return a * b * e0 + pendiente_pct / 100 * suma


async def _bajada(c: httpx.AsyncClient, relleno: str, plano: str, wkt: str, **extra: object) -> dict:
    punto = await _trazo(c, plano, wkt)
    r = await c.post(f"{API}/rellenos-de-zona/{relleno}/bajadas", json={"trazo_id": punto, **extra})
    assert r.status_code == 201, r.text
    return r.json()


async def _azotea(c: httpx.AsyncClient, escenario: Escenario, **params: object) -> tuple[str, dict, dict]:
    """Una zona (cuarto de 6 × 4 m y subzona de 2 × 4 m de 20 cm) con un relleno de azotea sin compensación y la escala de 1 m por unidad."""
    plano, z = await _zona_con_losas(c, escenario)
    await _calibrar(c, plano)
    r = await c.post(_rellenos(z["id"]), json={"elemento_clave": "REL-AZOTEA", "compensar_espesores": False, **params})
    assert r.status_code == 201, r.text
    return plano, z, r.json()


async def test_un_relleno_nace_con_los_parametros_dinamicos_por_omision_y_sin_bajadas_se_comporta_como_hoy(control: httpx.AsyncClient, escenario: Escenario) -> None:
    _plano, z, rel = await _azotea(control, escenario)
    assert (rel["pendiente_zona_pct"], rel["espesor_bajada_m"], rel["mortero_espesor_m"], rel["factor_abundamiento"]) == (2.0, 0.05, 0.05, 1.0)
    [r] = (await _calculo(control, z["id"]))["rellenos"]
    assert r["modo"] == "uniforme" and r["dinamico"] is None and r["bajadas"] == []
    assert r["volumen_m3"] == pytest.approx(32 * 0.09) and [c["concepto"]["clave"] for c in r["conceptos"]] == ["ALB-03014"]


async def test_con_una_bajada_el_relleno_lleva_arenilla_variable_y_mortero_de_5_cm(control: httpx.AsyncClient, escenario: Escenario) -> None:
    plano, z, rel = await _azotea(control, escenario)
    b = await _bajada(control, rel["id"], plano, "POINT(0 -4)", rotulo="BAP-1")
    assert b["rotulo"] == "BAP-1" and b["linea_trazo_id"] is None and b["relleno_id"] == rel["id"]
    [r] = (await _calculo(control, z["id"], conciliar=True))["rellenos"]
    assert r["modo"] == "bajadas" and r["dinamico"]["estado"] == "calculado"
    # Cuarto de 6 × 4 con la bajada en su esquina (0, -4) y la subzona de 2 × 4 a su lado, a 6 m de ella: dos pedazos de la misma zona (sin compensación).
    esperado = _ref(6, 4, 2.0)
    subzona = 8 * 0.05 + 0.02 * sum(
        math.hypot(6 + (i + 0.5) * 2 / 200, (j + 0.5) * 4 / 200) * (2 / 200) * (4 / 200) for i in range(200) for j in range(200)
    )
    assert r["volumen_m3"] == pytest.approx(esperado + subzona, rel=2e-3)
    assert r["area_m2"] == pytest.approx(32.0)
    d = r["dinamico"]
    assert d["error_relativo"] < 1e-3 and d["error_estimado_m3"] >= 0 and d["muestras"] > 5000 and "determinista" in d["metodo"]
    assert d["pendiente_pct"] == 2.0 and d["espesor_en_bajada_m"] == 0.05 and d["mortero_espesor_m"] == 0.05
    assert d["volumen_mortero_m3"] == pytest.approx(32 * 0.05)
    assert d["bajadas"][0]["id"] == b["id"] and d["bajadas"][0]["area_m2"] == pytest.approx(32.0)
    assert (d["bajadas"][0]["x"], d["bajadas"][0]["y"]) == pytest.approx((0.0, -4.0))
    por_clave = {c["concepto"]["clave"]: c for c in r["conceptos"]}
    assert por_clave["ALB-03014"]["cantidad"] == pytest.approx(32.0) and por_clave["ALB-03014"]["unidad"] == "m²"
    assert por_clave["EJ-830"]["cantidad"] == pytest.approx(r["volumen_m3"]) and por_clave["EJ-830"]["unidad"] == "m³"
    assert por_clave["EJ-830"]["concepto"]["estado"] == "propuesto" and por_clave["EJ-830"]["propuesta"] is None  # nadie lo ha propuesto
    # Los insumos son la arenilla y el mortero de 5 cm; el tezontle del relleno sin bajadas se sustituye.
    assert {i["parte"] for i in r["insumos"]} == {"arenilla", "mortero"}
    assert next(i for i in r["insumos"] if i["parte"] == "mortero")["cantidad"] == pytest.approx(1.6)
    # La conciliación contra ALB-03014 muestra lo que difiere sin editar el catálogo.
    assert r["conciliacion"] is not None
    # Los totales de la zona suman lo mismo que el relleno (sin doble conteo).
    c = await _calculo(control, z["id"])
    assert {k["concepto"]["clave"]: k["cantidad"] for k in c["totales"]["conceptos"]}["EJ-830"] == pytest.approx(r["volumen_m3"])


async def test_la_pendiente_la_cambia_el_usuario_y_pendiente_cero_deja_5_cm_parejos(control: httpx.AsyncClient, escenario: Escenario) -> None:
    plano, z, rel = await _azotea(control, escenario)
    await _bajada(control, rel["id"], plano, "POINT(0 -4)")
    r = await control.put(f"{API}/rellenos-de-zona/{rel['id']}", json={"elemento_clave": "REL-AZOTEA", "compensar_espesores": False, "pendiente_zona_pct": 0})
    assert r.status_code == 200 and r.json()["pendiente_zona_pct"] == 0.0
    [calc] = (await _calculo(control, z["id"]))["rellenos"]
    assert calc["volumen_m3"] == pytest.approx(32 * 0.05) and any("0 %" in a for a in calc["advertencias"])
    r = await control.put(f"{API}/rellenos-de-zona/{rel['id']}", json={"elemento_clave": "REL-AZOTEA", "compensar_espesores": False, "pendiente_zona_pct": 1, "espesor_bajada_m": 0.08, "mortero_espesor_m": 0.04})
    assert r.status_code == 200
    [calc] = (await _calculo(control, z["id"]))["rellenos"]
    assert calc["dinamico"]["mortero_espesor_m"] == 0.04 and next(i for i in calc["insumos"] if i["parte"] == "mortero")["cantidad"] == pytest.approx(32 * 0.04)
    assert calc["volumen_m3"] > 32 * 0.08
    for malo in ({"pendiente_zona_pct": 40}, {"espesor_bajada_m": 0.0}, {"mortero_espesor_m": 0.5}):
        assert (await control.put(f"{API}/rellenos-de-zona/{rel['id']}", json={"elemento_clave": "REL-AZOTEA", **malo})).status_code == 422


async def test_dos_bajadas_reparten_la_zona_y_cada_una_drena_su_parte_sin_contar_dos_veces(control: httpx.AsyncClient, escenario: Escenario) -> None:
    plano, z, rel = await _azotea(control, escenario)
    una = (await _calculo(control, z["id"]))  # sin bajadas
    assert una["rellenos"][0]["modo"] == "uniforme"
    b1 = await _bajada(control, rel["id"], plano, "POINT(0 -2)", rotulo="BAP-1")
    v1 = (await _calculo(control, z["id"]))["rellenos"][0]["volumen_m3"]
    b2 = await _bajada(control, rel["id"], plano, "POINT(8 -2)", rotulo="BAP-2")
    [r] = (await _calculo(control, z["id"]))["rellenos"]
    assert r["volumen_m3"] < v1
    areas = {b["id"]: b["area_m2"] for b in r["dinamico"]["bajadas"]}
    assert areas[b1["id"]] + areas[b2["id"]] == pytest.approx(32.0)  # la suma de lo que drena cada una es el área: nada se cuenta dos veces
    assert areas[b1["id"]] == pytest.approx(16.0, rel=0.02)
    # Quitar una bajada vuelve a repartir; quitar la última devuelve el relleno al modo de siempre.
    assert (await control.delete(f"{API}/bajadas-de-relleno/{b2['id']}")).status_code == 204
    assert (await _calculo(control, z["id"]))["rellenos"][0]["volumen_m3"] == pytest.approx(v1)
    assert (await control.delete(f"{API}/bajadas-de-relleno/{b1['id']}")).status_code == 204
    [r] = (await _calculo(control, z["id"]))["rellenos"]
    assert r["modo"] == "uniforme" and r["volumen_m3"] == pytest.approx(32 * 0.09)
    assert (await control.delete(f"{API}/bajadas-de-relleno/{b1['id']}")).status_code == 404


async def test_una_linea_de_pendiente_trazada_cambia_el_recorrido_y_una_quitada_vuelve_a_la_generada(control: httpx.AsyncClient, escenario: Escenario) -> None:
    plano, z, rel = await _azotea(control, escenario)
    b = await _bajada(control, rel["id"], plano, "POINT(8 0)")
    recta = (await _calculo(control, z["id"]))["rellenos"][0]
    assert [g["origen"] for g in recta["dinamico"]["guias"] if g["tipo"] == "pendiente"] == ["generada"]
    linea = await _trazo(control, plano, "LINESTRING(0 0, 8 0)")  # dibujada hacia la bajada
    r = await control.put(f"{API}/bajadas-de-relleno/{b['id']}", json={"linea_trazo_id": linea, "rotulo": "BAP-N"})
    assert r.status_code == 200 and r.json()["linea_trazo_id"] == linea and r.json()["rotulo"] == "BAP-N"
    guiada = (await _calculo(control, z["id"]))["rellenos"][0]
    assert guiada["volumen_m3"] > recta["volumen_m3"]
    pendientes = [g for g in guiada["dinamico"]["guias"] if g["tipo"] == "pendiente"]
    assert [g["origen"] for g in pendientes] == ["trazada"] and pendientes[0]["puntos"] == [[0.0, 0.0], [8.0, 0.0]]
    assert guiada["bajadas"][0]["linea_trazo_id"] == linea and guiada["bajadas"][0]["linea"] == [[0.0, 0.0], [8.0, 0.0]]
    # Una línea sirve a una sola bajada.
    otra = await _bajada(control, rel["id"], plano, "POINT(0 -4)")
    r = await control.put(f"{API}/bajadas-de-relleno/{otra['id']}", json={"linea_trazo_id": linea})
    assert r.status_code == 422 and "no sirve a dos" in r.text
    r = await control.put(f"{API}/bajadas-de-relleno/{b['id']}", json={"linea_trazo_id": None, "rotulo": "BAP-N"})
    assert r.json()["linea_trazo_id"] is None


async def test_las_guias_del_plano_traen_las_bajadas_la_linea_de_pendiente_y_los_hilos_en_unidades_del_plano(control: httpx.AsyncClient, escenario: Escenario) -> None:
    plano, z, rel = await _azotea(control, escenario)
    await _bajada(control, rel["id"], plano, "POINT(0 -4)", rotulo="BAP-1")
    g = (await control.get(f"{API}/planos/{plano}/guias-de-relleno")).json()
    assert g["escala_definida"] is True and len(g["bajadas"]) == 1 and g["bajadas"][0]["zona_id"] == z["id"] and g["bajadas"][0]["rotulo"] == "BAP-1"
    assert len([x for x in g["guias"] if x["tipo"] == "pendiente"]) == 1
    hilos = [x for x in g["guias"] if x["tipo"] == "hilo"]
    assert len(hilos) >= 6 and all(x["espesor_m"] > 0.05 for x in hilos) and all(len(x["puntos"]) >= 2 for x in hilos)
    # Con otra escala (2 m por unidad) las coordenadas siguen siendo las del plano: la bajada no se mueve.
    await _calibrar(control, plano, "8")
    g2 = (await control.get(f"{API}/planos/{plano}/guias-de-relleno")).json()
    assert (g2["bajadas"][0]["x"], g2["bajadas"][0]["y"]) == pytest.approx((0.0, -4.0))
    assert max(p[0] for x in g2["guias"] for p in x["puntos"]) <= 8.0 + 1e-9 and min(p[1] for x in g2["guias"] for p in x["puntos"]) >= -4.0 - 1e-9
    # Un plano sin bajadas no trae nada.
    vacio, _ = await _zona_con_losas(control, escenario)
    assert (await control.get(f"{API}/planos/{vacio}/guias-de-relleno")).json()["guias"] == []
    assert (await control.get(f"{API}/planos/{uuid.uuid4()}/guias-de-relleno")).status_code == 404


async def test_sin_escala_calibrada_el_relleno_con_bajadas_no_da_cantidades_ni_guias(control: httpx.AsyncClient, escenario: Escenario) -> None:
    plano, z = await _zona_con_losas(control, escenario)  # sin calibrar
    rel = (await control.post(_rellenos(z["id"]), json={"elemento_clave": "REL-AZOTEA"})).json()
    await _bajada(control, rel["id"], plano, "POINT(0 -4)")
    c = await _calculo(control, z["id"])
    [r] = c["rellenos"]
    assert c["escala_definida"] is False and r["dinamico"]["estado"] == "sin_escala"
    assert r["volumen_m3"] == 0 and r["area_m2"] == 0 and all(k["cantidad"] == 0 for k in r["conceptos"])
    assert any("calibrar" in a for a in r["advertencias"]) and r["dinamico"]["guias"] == []
    g = (await control.get(f"{API}/planos/{plano}/guias-de-relleno")).json()
    assert g["escala_definida"] is False and g["guias"] == []
    # Al calibrar, las cantidades aparecen solas (medición derivada).
    await _calibrar(control, plano)
    [r] = (await _calculo(control, z["id"]))["rellenos"]
    assert r["dinamico"]["estado"] == "calculado" and r["volumen_m3"] > 0


async def test_una_bajada_solo_es_un_punto_del_plano_y_sirve_a_un_solo_relleno(control: httpx.AsyncClient, escenario: Escenario) -> None:
    plano, z, rel = await _azotea(control, escenario)
    url = f"{API}/rellenos-de-zona/{rel['id']}/bajadas"
    punto = await _trazo(control, plano, "POINT(1 -1)")
    linea = await _trazo(control, plano, "LINESTRING(0 0, 4 0)")
    poligono = await _trazo(control, plano, "POLYGON((20 20, 22 20, 22 22, 20 22, 20 20))")
    otro_plano = (await control.post(f"{API}/obras/{escenario.obra_id}/planos", json={"nombre": "Otro", "archivo_url": "e2e/otro.pdf"})).json()["id"]
    ajeno = await _trazo(control, otro_plano, "POINT(1 1)")
    for malo, texto in ((linea, "PUNTO"), (poligono, "PUNTO"), (ajeno, "otro plano")):
        r = await control.post(url, json={"trazo_id": malo})
        assert r.status_code == 422 and texto in r.text, (malo, r.text)
    assert (await control.post(url, json={"trazo_id": str(uuid.uuid4())})).status_code == 404
    assert (await control.post(url, json={"trazo_id": punto, "linea_trazo_id": punto})).status_code == 422  # la «línea» es un punto
    assert (await control.post(url, json={"trazo_id": punto, "rotulo": "x" * 41})).status_code == 422
    assert (await control.post(url, json={"trazo_id": punto})).status_code == 201
    r = await control.post(url, json={"trazo_id": punto})
    assert r.status_code == 422 and "no sirve a dos bajadas" in r.text
    # El compactado no lleva bajadas (no tiene espesor variable).
    compactado = (await control.post(_rellenos(z["id"]), json={"elemento_clave": "REL-COMPACTADO"})).json()
    r = await control.post(f"{API}/rellenos-de-zona/{compactado['id']}/bajadas", json={"trazo_id": await _trazo(control, plano, "POINT(2 -2)")})
    assert r.status_code == 422 and "azotea" in r.text
    assert (await control.post(f"{API}/rellenos-de-zona/{uuid.uuid4()}/bajadas", json={"trazo_id": linea})).status_code == 404
    # Borrar el punto del plano se lleva la bajada.
    assert (await control.delete(f"{API}/trazos/{punto}")).status_code in (200, 204)
    assert (await _calculo(control, z["id"]))["rellenos"][0]["bajadas"] == []


async def test_solo_control_de_obra_agrega_cambia_y_quita_bajadas_y_los_demas_roles_leen(
    control: httpx.AsyncClient, costos: httpx.AsyncClient, residente: httpx.AsyncClient, escenario: Escenario
) -> None:
    plano, z, rel = await _azotea(control, escenario)
    b = await _bajada(control, rel["id"], plano, "POINT(0 -4)")
    punto = await _trazo(control, plano, "POINT(3 -2)")
    for rol in (costos, residente):
        assert (await rol.post(f"{API}/rellenos-de-zona/{rel['id']}/bajadas", json={"trazo_id": punto})).status_code == 403
        assert (await rol.put(f"{API}/bajadas-de-relleno/{b['id']}", json={"rotulo": "x"})).status_code == 403
        assert (await rol.delete(f"{API}/bajadas-de-relleno/{b['id']}")).status_code == 403
    for rol in (costos, residente):
        assert (await rol.get(f"{API}/planos/{plano}/guias-de-relleno")).json()["bajadas"][0]["id"] == b["id"]
    assert (await costos.get(f"{_rellenos(z['id'])}/calculo")).json()["rellenos"][0]["bajadas"][0]["id"] == b["id"]


async def test_cada_poligono_cae_en_un_espacio_y_la_suma_por_espacio_es_el_total(control: httpx.AsyncClient, escenario: Escenario, arbol) -> None:
    plano, z, rel = await _azotea(control, escenario)
    espacio = await _espacio(control, escenario.obra_id, "Azotea")
    assert (await control.put(f"{API}/rellenos-de-zona/{rel['id']}", json={"elemento_clave": "REL-AZOTEA", "compensar_espesores": False, "espacio_id": espacio["id"]})).status_code == 200
    await _bajada(control, rel["id"], plano, "POINT(0 -4)")
    c = await _calculo(control, z["id"])
    [r] = c["rellenos"]
    grupos = c["por_espacio"]
    assert [g["espacio_id"] for g in grupos] == [espacio["id"]]
    por_grupo = {k["concepto"]["clave"]: k["cantidad"] for k in grupos[0]["conceptos"]}
    assert por_grupo["ALB-03014"] == pytest.approx(r["area_m2"]) and por_grupo["EJ-830"] == pytest.approx(r["volumen_m3"])
    # Un concepto que no está en el catálogo (la arenilla propuesta) no se escribe en ninguna partida.
    resolucion = next(k for k in grupos[0]["conceptos"] if k["concepto"]["clave"] == "EJ-830")["resolucion"]
    assert resolucion["cuenta"] is False


async def test_la_arenilla_se_propone_una_vez_y_solo_control_de_obra_la_autoriza_sin_tocar_el_catalogo(
    control: httpx.AsyncClient, costos: httpx.AsyncClient, escenario: Escenario
) -> None:
    plano, z, rel = await _azotea(control, escenario)
    # Sin bajadas no hay arenilla que proponer.
    assert (await costos.post(f"{_rellenos(z['id'])}/propuestas")).json() == {"creadas": [], "omitidas": []}
    await _bajada(control, rel["id"], plano, "POINT(0 -4)")
    primera = await costos.post(f"{_rellenos(z['id'])}/propuestas")
    assert primera.status_code == 201 and len(primera.json()["creadas"]) == 1
    assert (await costos.post(f"{_rellenos(z['id'])}/propuestas")).json()["omitidas"] == ["EJ-830"]  # idempotente
    [r] = (await _calculo(costos, z["id"]))["rellenos"]
    assert next(k for k in r["conceptos"] if k["concepto"]["clave"] == "EJ-830")["propuesta"]["estado"] == "pendiente"
    assert next(k for k in r["conceptos"] if k["concepto"]["clave"] == "ALB-03014")["propuesta"] is None  # el mortero usa el concepto del catálogo
    [p] = (await costos.get(f"{API}/biblioteca-de-elementos/relleno/REL-AZOTEA/propuestas")).json()
    assert (p["clase"], p["concepto_clave"], p["estado"], p["elemento_clave"]) == ("concepto_nuevo", "EJ-830", "pendiente", "REL-AZOTEA")
    assert (await costos.post(f"{API}/propuestas-de-estructura/{p['id']}/autorizar")).status_code == 403
    assert (await control.post(f"{API}/propuestas-de-estructura/{p['id']}/autorizar")).json() == {"version": 1}
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as cn:
            assert (await cn.execute(text("select count(*) from concepto where clave = 'EJ-830'"))).scalar_one() == 0  # nadie creó un concepto en el catálogo
    finally:
        await motor.dispose()
    ficha = (await costos.get(f"{API}/biblioteca-de-elementos/relleno/REL-AZOTEA")).json()
    assert ficha["concepto_arenilla"]["clave"] == "EJ-830" and ficha["parametros_por_defecto"]["pendiente_zona_pct"] == 2.0


async def test_el_compactado_mide_el_volumen_por_el_factor_de_abundamiento_y_el_porcentaje_viejo_sigue_valiendo(control: httpx.AsyncClient, escenario: Escenario) -> None:
    plano, z = await _zona_con_losas(control, escenario)
    await _calibrar(control, plano)
    nuevo = (await control.post(_rellenos(z["id"]), json={"elemento_clave": "REL-COMPACTADO", "espesor_m": 0.2, "factor_abundamiento": 1.25})).json()
    assert nuevo["factor_abundamiento"] == 1.25 and nuevo["abundamiento_pct"] == pytest.approx(25.0)
    [r] = (await _calculo(control, z["id"]))["rellenos"]
    volumen = 24 * (0.2 + 0.08) + 8 * 0.2  # el cuarto de 12 cm recibe 8 cm más que la subzona de 20 cm
    assert r["volumen_m3"] == pytest.approx(volumen)
    [c] = r["conceptos"]
    assert c["concepto"]["clave"] == "EJ-810" and c["cantidad"] == pytest.approx(volumen * 1.25) and c["unidad"] == "m³"  # volumen compactado × factor
    assert r["mano_de_obra"]["destajos_candidatos"] == []  # sin destajo hasta que Costos lo defina
    # El porcentaje viejo sigue valiendo: es (factor − 1) × 100.
    r2 = await control.put(f"{API}/rellenos-de-zona/{nuevo['id']}", json={"elemento_clave": "REL-COMPACTADO", "espesor_m": 0.2, "abundamiento_pct": 10})
    assert r2.json()["factor_abundamiento"] == pytest.approx(1.1)
    # Sin factor vuelve a 1.00; un factor fuera de rango o en la azotea se rechaza.
    r3 = await control.put(f"{API}/rellenos-de-zona/{nuevo['id']}", json={"elemento_clave": "REL-COMPACTADO"})
    assert r3.json()["factor_abundamiento"] == 1.0 and r3.json()["abundamiento_pct"] == 0.0
    assert (await control.put(f"{API}/rellenos-de-zona/{nuevo['id']}", json={"elemento_clave": "REL-COMPACTADO", "factor_abundamiento": 2})).status_code == 422
    assert (await control.post(_rellenos(z["id"]), json={"elemento_clave": "REL-AZOTEA", "factor_abundamiento": 1.2})).status_code == 422
