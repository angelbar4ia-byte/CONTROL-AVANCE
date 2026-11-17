"""Zonas de losa (migración 0137), por HTTP de punta a punta contra Postgres real.

Dos cuartos contiguos en un mismo plano: el de 3.00 a la izquierda y el de 4.20 a la derecha. Un muro que los cruza se parte en
tramos con su altura; un muro en el límite lleva enrase y cada cara su altura; con losa de un solo lado el otro es exterior. Solo
Control de obra escribe; los demás leen. Lo que ya estaba guardado (un trazo sin zona) no cambia.
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

CUARTO_3 = "POLYGON((0 -4, 6 -4, 6 0, 0 0, 0 -4))"
CUARTO_4 = "POLYGON((6 -4, 12 -4, 12 0, 6 0, 6 -4))"
D = Decimal


def _cliente(contexto: ContextoSesion) -> httpx.AsyncClient:
    app = crear_app()
    app.dependency_overrides[contexto_actual] = lambda: contexto
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test")


@pytest.fixture
async def control(contexto_control: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_control) as c:
        yield c


@pytest.fixture
async def residente(contexto_residente: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_residente) as c:
        yield c


async def _plano(c: httpx.AsyncClient, esc: Escenario) -> str:
    r = await c.post(f"/api/v1/obras/{esc.obra_id}/planos", json={"nombre": "PB", "archivo_url": "e2e/pb.pdf"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _trazo(c: httpx.AsyncClient, plano: str, wkt: str) -> str:
    r = await c.post(f"/api/v1/planos/{plano}/trazos", json={"version_plano": 1, "fuente": "pdf", "geometria_wkt": wkt, "enlaces": []})
    assert r.status_code == 201, r.text
    return r.json()["trazo_id"]


async def _zona(c: httpx.AsyncClient, plano: str, nombre: str, altura: str, espesor: str = "0.12", **extra: str) -> dict:
    r = await c.post(f"/api/v1/planos/{plano}/zonas-de-losa", json={"nombre": nombre, "altura_libre_m": altura, "espesor_m": espesor, **extra})
    assert r.status_code == 201, r.text
    return r.json()


async def _dos_cuartos(c: httpx.AsyncClient, esc: Escenario) -> tuple[str, dict, dict, str, str]:
    plano = await _plano(c, esc)
    z3 = await _zona(c, plano, "Entrepiso 3.00", "3.00", nivel="planta baja")
    z4 = await _zona(c, plano, "Entrepiso 4.20", "4.20", "0.20", nivel="planta baja")
    l3, l4 = await _trazo(c, plano, CUARTO_3), await _trazo(c, plano, CUARTO_4)
    assert (await c.put(f"/api/v1/trazos/{l3}/losa", json={"zona_id": z3["id"]})).status_code == 200
    assert (await c.put(f"/api/v1/trazos/{l4}/losa", json={"zona_id": z4["id"]})).status_code == 200
    return plano, z3, z4, l3, l4


async def test_control_crea_zonas_con_sus_cotas_y_las_lista_con_sus_losas(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano, z3, z4, l3, l4 = await _dos_cuartos(control, escenario)
    assert (z3["cota_piso_m"], z3["altura_libre_m"], z3["espesor_m"]) == ("0.000", "3.000", "0.120")
    assert (D(z3["cota_inferior_m"]), D(z3["cota_superior_m"])) == (D("3.000"), D("3.120"))
    assert D(z4["cota_superior_m"]) == D("4.400")

    lista = (await control.get(f"/api/v1/planos/{plano}/zonas-de-losa")).json()
    assert [z["nombre"] for z in lista["zonas"]] == ["Entrepiso 3.00", "Entrepiso 4.20"]
    assert lista["escala_definida"] is False
    assert [x["trazo_id"] for x in lista["zonas"][0]["losas"]] == [l3]

    # Varias losas por zona y una subzona con espesor estructural propio.
    otra = await _trazo(control, plano, "POLYGON((0 -8, 3 -8, 3 -4, 0 -4, 0 -8))")
    r = await control.put(f"/api/v1/trazos/{otra}/losa", json={"zona_id": z3["id"], "espesor_m": "0.15"})
    assert r.status_code == 200 and D(r.json()["espesor_propio_m"]) == D("0.15")
    losas = (await control.get(f"/api/v1/planos/{plano}/zonas-de-losa")).json()["zonas"][0]["losas"]
    assert sorted((x["trazo_id"], D(x["espesor_m"])) for x in losas) == sorted([(l3, D("0.12")), (otra, D("0.15"))])

    # Las propiedades del trazo en el plano traen el rol.
    feats = (await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"]
    por_id = {f["properties"]["trazo_id"]: f["properties"] for f in feats}
    assert por_id[otra]["losa_zona_id"] == z3["id"] and D(por_id[otra]["losa_espesor_m"]) == D("0.15")
    assert por_id[l4]["losa_espesor_m"] is None


async def test_solo_control_de_obra_escribe_los_demas_leen(escenario: Escenario, control: httpx.AsyncClient, residente: httpx.AsyncClient) -> None:
    plano, z3, _, l3, _ = await _dos_cuartos(control, escenario)
    peticion = {"nombre": "Otra", "altura_libre_m": "3", "espesor_m": "0.1"}
    assert (await residente.post(f"/api/v1/planos/{plano}/zonas-de-losa", json=peticion)).status_code == 403
    assert (await residente.put(f"/api/v1/zonas-de-losa/{z3['id']}", json=peticion)).status_code == 403
    assert (await residente.delete(f"/api/v1/zonas-de-losa/{z3['id']}")).status_code == 403
    assert (await residente.put(f"/api/v1/trazos/{l3}/losa", json={"zona_id": None})).status_code == 403
    assert (await residente.put(f"/api/v1/trazos/{l3}/nivel-exterior", json={"cota_m": "0"})).status_code == 403
    assert (await residente.get(f"/api/v1/planos/{plano}/zonas-de-losa")).status_code == 200
    assert (await residente.get(f"/api/v1/trazos/{l3}/zonas-de-losa")).status_code == 422  # un polígono no es muro: se lee, pero no se resuelve


async def test_validaciones_de_zonas_losas_y_puntos(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano, z3, _, l3, _ = await _dos_cuartos(control, escenario)
    base = {"nombre": "X", "altura_libre_m": "3", "espesor_m": "0.1"}
    for mal in ({"altura_libre_m": "0"}, {"espesor_m": "0"}, {"altura_libre_m": "31"}, {"nombre": " "}, {"cota_piso_m": "500"}):
        assert (await control.post(f"/api/v1/planos/{plano}/zonas-de-losa", json={**base, **mal})).status_code == 422
    # Nombre repetido en el plano (sin importar mayúsculas ni espacios).
    r = await control.post(f"/api/v1/planos/{plano}/zonas-de-losa", json={**base, "nombre": " ENTREPISO 3.00 "})
    assert r.status_code == 422 and "Ya hay una zona" in r.text
    # Un muro (línea) no es losa; un polígono no es un punto de nivel; un punto sí.
    muro = await _trazo(control, plano, "LINESTRING(0 0, 4 0)")
    assert (await control.put(f"/api/v1/trazos/{muro}/losa", json={"zona_id": z3["id"]})).status_code == 422
    assert (await control.put(f"/api/v1/trazos/{l3}/nivel-exterior", json={"cota_m": "0"})).status_code == 422
    punto = await _trazo(control, plano, "POINT(3 3)")
    r = await control.put(f"/api/v1/trazos/{punto}/nivel-exterior", json={"cota_m": "-0.2", "rotulo": " Banqueta "})
    assert r.status_code == 200 and (D(r.json()["cota_m"]), r.json()["rotulo"]) == (D("-0.2"), "Banqueta")
    assert (await control.put(f"/api/v1/trazos/{punto}/nivel-exterior", json={"cota_m": "500"})).status_code == 422
    assert (await control.put(f"/api/v1/trazos/{punto}/losa", json={"zona_id": z3["id"]})).status_code == 422
    # Una zona de otro plano no vale.
    otro_plano = await _plano(control, escenario)
    zajena = await _zona(control, otro_plano, "De otro plano", "3")
    assert (await control.put(f"/api/v1/trazos/{l3}/losa", json={"zona_id": zajena["id"]})).status_code == 422
    assert (await control.put(f"/api/v1/trazos/{l3}/losa", json={"zona_id": str(uuid.uuid4())})).status_code == 404
    assert (await control.put(f"/api/v1/trazos/{uuid.uuid4()}/losa", json={"zona_id": None})).status_code == 404
    assert (await control.put(f"/api/v1/zonas-de-losa/{uuid.uuid4()}", json=base)).status_code == 404
    # Quitar la marca del punto.
    assert (await control.put(f"/api/v1/trazos/{punto}/nivel-exterior", json={"cota_m": None})).json() == {
        "trazo_id": punto, "cota_m": None, "rotulo": None,
    }
    assert (await control.get(f"/api/v1/planos/{plano}/zonas-de-losa")).json()["puntos_de_nivel"] == []


async def test_un_muro_que_cruza_el_limite_se_parte_en_tramos_con_su_altura(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano, *_ = await _dos_cuartos(control, escenario)
    muro = await _trazo(control, plano, "LINESTRING(2 -2, 10 -2)")
    r = (await control.get(f"/api/v1/trazos/{muro}/zonas-de-losa")).json()
    assert r["con_zona"] and r["parte_el_muro"] and r["aplicada"] is False
    assert [(D(t["desde_m"]), D(t["hasta_m"]), D(t["altura_m"]), t["origen_de_altura"]) for t in r["tramos"]] == [
        (D(0), D(4), D(3), "zona"), (D(4), D(8), D("4.2"), "zona"),
    ]
    assert [t["lado_a"]["zona"] for t in r["tramos"]] == ["Entrepiso 3.00", "Entrepiso 4.20"]
    assert D(r["altura_estandar_m"]) == D("3.00")  # el driver de la obra, intacto


async def test_un_muro_en_el_limite_lleva_enrase_y_una_altura_por_cara(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano, *_ = await _dos_cuartos(control, escenario)
    muro = await _trazo(control, plano, "LINESTRING(6 0, 6 -4)")
    t = (await control.get(f"/api/v1/trazos/{muro}/zonas-de-losa")).json()["tramos"][0]
    assert (t["lado_a"]["zona"], t["lado_b"]["zona"]) == ("Entrepiso 3.00", "Entrepiso 4.20")
    assert (D(t["lado_a"]["altura_m"]), D(t["lado_b"]["altura_m"])) == (D(3), D("4.2"))
    assert (D(t["enrase"]["desde_m"]), D(t["enrase"]["hasta_m"])) == (D(3), D("4.2"))
    assert [p["rol"] for p in t["partes"]] == ["cuerpo", "enrase"]
    assert (t["partes"][0]["cara_a"], t["partes"][0]["cara_b"]) == ("interior", "interior")
    assert [s["indice"] for s in t["sugerencias"]] == [1]


async def test_la_losa_de_un_solo_lado_y_el_punto_de_nivel_deciden_la_cara_exterior(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano, *_ = await _dos_cuartos(control, escenario)
    # Muro en el borde sur del cuarto de 3.00 (y = 0), de izquierda a derecha: A (arriba en pantalla) tiene losa, B no.
    muro = await _trazo(control, plano, "LINESTRING(1 0, 5 0)")
    t = (await control.get(f"/api/v1/trazos/{muro}/zonas-de-losa")).json()["tramos"][0]
    assert (t["lado_a"]["cara"], t["lado_b"]["cara"], t["lado_b"]["origen"]) == ("interior", "exterior", "sin_losa")
    punto = await _trazo(control, plano, "POINT(3 2)")
    await control.put(f"/api/v1/trazos/{punto}/nivel-exterior", json={"cota_m": "-0.30", "rotulo": "Banqueta"})
    t = (await control.get(f"/api/v1/trazos/{muro}/zonas-de-losa")).json()["tramos"][0]
    assert (t["lado_b"]["origen"], t["lado_b"]["rotulo_del_punto"], D(t["lado_b"]["altura_m"])) == ("punto_de_nivel", "Banqueta", D("3.3"))


async def test_sin_zona_el_muro_se_comporta_como_siempre_y_nada_guardado_cambia(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano = await _plano(control, escenario)
    muro = await _trazo(control, plano, "LINESTRING(0 0, 5 0)")
    antes = (await control.get(f"/api/v1/planos/{plano}/trazos")).json()
    r = (await control.get(f"/api/v1/trazos/{muro}/zonas-de-losa")).json()
    assert not r["con_zona"] and not r["parte_el_muro"]
    assert (r["tramos"][0]["origen_de_altura"], D(r["tramos"][0]["altura_m"]), r["tramos"][0]["lado_a"]["cara"]) == ("driver", D(3), None)
    # Con zonas dibujadas en otro lado del plano, el muro lejano sigue igual y resolver no escribe nada.
    await _zona(control, plano, "Z", "4.2")
    assert (await control.get(f"/api/v1/planos/{plano}/trazos")).json() == antes


async def test_la_altura_explicita_del_trazo_manda_sobre_la_zona(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano, *_ = await _dos_cuartos(control, escenario)
    muro = await _trazo(control, plano, "LINESTRING(1 -2, 5 -2)")
    r = await control.put(f"/api/v1/trazos/{muro}/muro", json={"altura_m": "2.40", "caras": 2})
    assert r.status_code == 200, r.text
    res = (await control.get(f"/api/v1/trazos/{muro}/zonas-de-losa")).json()
    assert res["altura_explicita_m"] == "2.40" or D(res["altura_explicita_m"]) == D("2.4")
    assert (res["tramos"][0]["origen_de_altura"], D(res["tramos"][0]["altura_m"])) == ("trazo", D("2.4"))
    assert res["tramos"][0]["lado_a"]["cara"] == "interior"  # la zona sigue informando las caras


async def test_borrar_una_zona_suelta_sus_poligonos(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano, z3, _, l3, _ = await _dos_cuartos(control, escenario)
    await control.put(f"/api/v1/trazos/{l3}/losa", json={"zona_id": z3["id"], "espesor_m": "0.15"})
    assert (await control.delete(f"/api/v1/zonas-de-losa/{z3['id']}")).status_code == 204
    feats = (await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"]
    p = next(f["properties"] for f in feats if f["properties"]["trazo_id"] == l3)
    assert p["losa_zona_id"] is None and p["losa_espesor_m"] is None
    assert [z["nombre"] for z in (await control.get(f"/api/v1/planos/{plano}/zonas-de-losa")).json()["zonas"]] == ["Entrepiso 4.20"]


async def test_el_cambio_de_cotas_de_una_zona_se_refleja_en_la_resolucion(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano, z3, *_ = await _dos_cuartos(control, escenario)
    muro = await _trazo(control, plano, "LINESTRING(1 -2, 5 -2)")
    r = await control.put(
        f"/api/v1/zonas-de-losa/{z3['id']}",
        json={"nombre": "Entrepiso 3.00", "altura_libre_m": "2.80", "espesor_m": "0.12", "cota_piso_m": "0.15", "nivel": "planta baja"},
    )
    assert r.status_code == 200 and D(r.json()["cota_inferior_m"]) == D("2.95")
    t = (await control.get(f"/api/v1/trazos/{muro}/zonas-de-losa")).json()["tramos"][0]
    assert D(t["altura_m"]) == D("2.8")
