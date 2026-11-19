"""La fachada por BANDAS de altura contra Postgres real (F1, 2026-11-19): lee los muros reales del plano, sus zonas de losa y sus puntos de
nivel exterior, y reparte los m² de cara exterior en la banda baja (0 a 3.00), la media («+3.00», de 3.00 a 4.20) y el resto. Cada m² cae en una
sola banda. La prueba central es la DESCONEXIÓN que se sospechaba: la fachada sigue al muro real (su largo, su altura, su ubicación, su zona, su
vano) y no a un selector, una cantidad capturada aparte ni el driver `altura_estandar`.

También prueba que un revestimiento nace ligado a su muro en UNA sola transacción (o no nace).

Dos cuartos de 6 × 4 m: el de 3.00 de x 0 a 6 y el de 4.20 de x 6 a 12 (y de -4 a 0). Cara A = izquierda del sentido de dibujo; con Y hacia abajo,
un muro dibujado de izquierda a derecha tiene su cara A hacia arriba en pantalla (y menor).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import httpx
import pytest

from obractrl.adapters.api.dependencias import contexto_actual
from obractrl.infrastructure.db.sesion import ContextoSesion
from obractrl.main import crear_app
from tests.integracion.conftest import Escenario

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


async def _plano(c: httpx.AsyncClient, esc: Escenario, con_zonas: bool = True) -> str:
    plano = (await c.post(f"/api/v1/obras/{esc.obra_id}/planos", json={"nombre": "PB", "archivo_url": "e2e/pb.pdf"})).json()["id"]
    if not con_zonas:
        return str(plano)
    for nombre, altura, espesor, wkt in (
        ("Entrepiso 3.00", "3.00", "0.12", "POLYGON((0 -4, 6 -4, 6 0, 0 0, 0 -4))"),
        ("Entrepiso 4.20", "4.20", "0.20", "POLYGON((6 -4, 12 -4, 12 0, 6 0, 6 -4))"),
    ):
        z = await c.post(f"/api/v1/planos/{plano}/zonas-de-losa", json={"nombre": nombre, "altura_libre_m": altura, "espesor_m": espesor})
        losa = await c.post(f"/api/v1/planos/{plano}/trazos", json={"version_plano": 1, "fuente": "pdf", "geometria_wkt": wkt, "enlaces": []})
        assert (await c.put(f"/api/v1/trazos/{losa.json()['trazo_id']}/losa", json={"zona_id": z.json()["id"]})).status_code == 200
    return str(plano)


async def _muro(c: httpx.AsyncClient, plano: str, wkt: str, ubicacion: str | None = None) -> str:
    r = await c.post(
        f"/api/v1/planos/{plano}/trazos",
        json={"version_plano": 1, "fuente": "pdf", "geometria_wkt": wkt, "grosor_m": "0.15", "alineacion": "centro", "enlaces": []},
    )
    assert r.status_code == 201, r.text
    trazo = str(r.json()["trazo_id"])
    if ubicacion:
        k = await c.put(f"/api/v1/trazos/{trazo}/muro/clasificacion", json={"tipo": "confinado", "ubicacion": ubicacion})
        assert k.status_code == 200, k.text
    return trazo


async def _fachada(c: httpx.AsyncClient, plano: str) -> dict[str, Any]:
    r = await c.get(f"/api/v1/planos/{plano}/fachada-por-bandas")
    assert r.status_code == 200, r.text
    return dict(r.json())


def _bandas(j: dict[str, Any]) -> tuple[Decimal, Decimal, Decimal]:
    por = {b["banda"]: D(b["neto_m2"]) for b in j["bandas"]}
    return por["baja"], por["media"], por["resto"]


def _de_muro(j: dict[str, Any], trazo: str) -> dict[str, Any]:
    return next(m for m in j["muros"] if m["trazo_id"] == trazo)


async def test_un_muro_exterior_de_la_zona_de_3_00_cae_entero_en_la_banda_baja(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano = await _plano(control, escenario)
    muro = await _muro(control, plano, "LINESTRING(0 -4, 6 -4)")  # borde de arriba del cuarto de 3.00: A afuera, B adentro
    j = await _fachada(control, plano)
    assert _bandas(j) == (D("18"), D("0"), D("0"))
    assert (D(j["limite_bajo_m"]), D(j["limite_alto_m"])) == (D("3.00"), D("4.20"))
    m = _de_muro(j, muro)
    assert m["origen_de_caras"] == "zona_de_losa" and D(m["neto_m2"]) == D("18")


async def test_un_muro_exterior_de_la_zona_de_4_20_reparte_en_baja_y_en_la_franja_mas_3_00(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano = await _plano(control, escenario)
    await _muro(control, plano, "LINESTRING(6 -4, 12 -4)")
    j = await _fachada(control, plano)
    assert _bandas(j) == (D("18"), D("7.2"), D("0"))  # 6 m × 3.00, 6 m × 1.20
    assert sum(_bandas(j)) == D(j["neto_m2"]) == D("25.2")  # cada m² cae en una sola banda: 6 m × 4.20


async def test_el_muro_del_limite_aporta_solo_el_enrase_como_fachada_en_la_banda_media(escenario: Escenario, control: httpx.AsyncClient) -> None:
    """Decisión del 2026-11-18: el muro en el límite se traza UNA vez a 4.20; la cara del lado de la losa de 3.00 es exterior de 3.00 a 4.20."""
    plano = await _plano(control, escenario)
    muro = await _muro(control, plano, "LINESTRING(6 -4, 6 0)")
    j = await _fachada(control, plano)
    assert _bandas(j) == (D("0"), D("4.8"), D("0"))  # 4 m × (4.20 - 3.00)
    assert _de_muro(j, muro)["origen_de_caras"] == "zona_de_losa"


async def test_el_punto_de_nivel_exterior_fija_el_suelo_de_la_cara_exterior(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano = await _plano(control, escenario)
    await _muro(control, plano, "LINESTRING(0 -4, 6 -4)")
    punto = (await control.post(f"/api/v1/planos/{plano}/trazos", json={"version_plano": 1, "fuente": "pdf", "geometria_wkt": "POINT(3 -6)", "enlaces": []})).json()["trazo_id"]
    assert (await control.put(f"/api/v1/trazos/{punto}/nivel-exterior", json={"cota_m": "-0.30"})).status_code == 200
    j = await _fachada(control, plano)
    # El terreno está 0.30 m más abajo: la cara exterior mide 3.30 m desde su suelo; los 0.30 m de más caen en la banda media.
    assert _bandas(j) == (D("18"), D("1.8"), D("0"))
    # Con el suelo por ARRIBA del piso (un terreno alto), la cara exterior arranca ahí.
    assert (await control.put(f"/api/v1/trazos/{punto}/nivel-exterior", json={"cota_m": "0.50"})).status_code == 200
    assert _bandas(await _fachada(control, plano)) == (D("15"), D("0"), D("0"))  # de 0.50 a 3.00 m: 2.50 m × 6 m


async def test_sin_zona_la_fachada_sigue_la_ubicacion_la_altura_y_el_largo_del_muro_real(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano = await _plano(control, escenario, con_zonas=False)
    muro = await _muro(control, plano, "LINESTRING(0 10, 5 10)", ubicacion="fachada_a")
    j = await _fachada(control, plano)
    assert _bandas(j) == (D("15"), D("0"), D("0")) and _de_muro(j, muro)["origen_de_caras"] == "ubicacion"  # 3.00 m de la herramienta
    # La altura real del muro manda: 4.50 m → 3.00 + 1.20 + 0.30 por cada metro de largo.
    assert (await control.put(f"/api/v1/trazos/{muro}/muro", json={"altura_m": "4.5", "caras": 2})).status_code == 200
    j = await _fachada(control, plano)
    assert _bandas(j) == (D("15"), D("6"), D("1.5")) and D(j["neto_m2"]) == D("22.5")
    # Su largo: otro muro de 2 m en la misma ubicación suma (3.00 m de la herramienta: todo a la banda baja).
    await _muro(control, plano, "LINESTRING(0 12, 2 12)", ubicacion="fachada_a")
    j = await _fachada(control, plano)
    assert _bandas(j) == (D("21"), D("6"), D("1.5")) and D(j["neto_m2"]) == D("28.5")
    # La cara B exterior (fachada_b) también cuenta; un muro interior no tiene cara exterior: no suma y avisa.
    await _muro(control, plano, "LINESTRING(0 13, 1 13)", ubicacion="fachada_b")
    interior = await _muro(control, plano, "LINESTRING(0 14, 4 14)", ubicacion="interior")
    j = await _fachada(control, plano)
    assert D(j["neto_m2"]) == D("31.5") and [x["trazo_id"] for x in j["muros_sin_cara_exterior"]] == [interior]


async def test_las_partes_de_altura_con_caras_del_muro_mandan_y_lo_que_no_suma_no_se_aplana(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano = await _plano(control, escenario, con_zonas=False)
    muro = await _muro(control, plano, "LINESTRING(0 10, 10 10)")
    partes = [
        {"nombre": "Cuerpo", "desde_m": "0", "hasta_m": "3", "rol": "cuerpo", "cara_a": "exterior", "cara_b": "interior"},
        {"nombre": "Pretil", "desde_m": "3", "hasta_m": "4.2", "rol": "pretil", "cara_a": "exterior", "cara_b": "exterior"},
        {"nombre": "Cerramiento", "desde_m": "4.2", "hasta_m": "5", "suma": False, "cara_a": "exterior", "cara_b": "exterior"},
    ]
    assert (await control.put(f"/api/v1/trazos/{muro}/muro", json={"caras": 2, "partes": partes})).status_code == 200
    j = await _fachada(control, plano)
    # Cara A: 0 a 4.20 (10 m × 4.20); cara B: solo el pretil de 3.00 a 4.20; el cerramiento no suma.
    assert _bandas(j) == (D("30"), D("24"), D("0"))
    assert _de_muro(j, muro)["origen_de_caras"] == "partes_del_muro"


async def test_los_vanos_se_descuentan_en_la_banda_donde_caen(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano = await _plano(control, escenario)
    muro = await _muro(control, plano, "LINESTRING(6 -4, 12 -4)")
    # Una ventana de 2 m de ancho de 2.50 a 4.00 m: 0.50 m de alto en la banda baja y 1.00 m en la media.
    v = await control.post(
        f"/api/v1/trazos/{muro}/vanos",
        json={"clave": "V-1", "tipo": "ventana", "ancho_m": "2", "alto_m": "1.5", "antepecho_m": "2.5", "posicion_m": "3"},
    )
    assert v.status_code == 201, v.text
    j = await _fachada(control, plano)
    assert _bandas(j) == (D("17"), D("5.2"), D("0"))  # 18 - 2×0.5 y 7.2 - 2×1.0
    assert (D(j["bruto_m2"]), D(j["vanos_m2"]), D(j["neto_m2"])) == (D("25.2"), D("3"), D("22.2"))


async def test_los_castillos_colocados_no_se_restan_como_vanos_los_demas_vanos_si(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano = await _plano(control, escenario)
    muro = await _muro(control, plano, "LINESTRING(6 -4, 12 -4)")
    # Los castillos se colocan en un muro «con cadena»; conserva la ubicación para que siga contando su cara exterior.
    assert (await control.put(f"/api/v1/trazos/{muro}/muro/clasificacion", json={"tipo": "con_cadena"})).status_code == 200
    sin_vanos = _bandas(await _fachada(control, plano))
    # Dos castillos colocados en el muro (tipo castillo, 0.15 × 3.00 m) y una puerta de 1 × 2.10 m: solo la puerta resta.
    for clave, pos in (("K-1", "1"), ("K-2", "5")):
        k = await control.post(f"/api/v1/trazos/{muro}/vanos", json={"clave": clave, "tipo": "castillo", "ancho_m": "0.15", "alto_m": "3", "posicion_m": pos})
        assert k.status_code == 201, k.text
    j = await _fachada(control, plano)
    assert _bandas(j) == sin_vanos and D(j["vanos_m2"]) == 0
    p = await control.post(f"/api/v1/trazos/{muro}/vanos", json={"clave": "P-1", "tipo": "puerta", "ancho_m": "1", "alto_m": "2.1", "posicion_m": "3"})
    assert p.status_code == 201, p.text
    j = await _fachada(control, plano)
    assert D(j["vanos_m2"]) == D("2.1") and D(j["neto_m2"]) == D(j["bruto_m2"]) - D("2.1")
    # cancel, arco y paso también son vanos reales y restan (1 × 1 m cada uno).
    for clave, tipo, pos in (("C-1", "cancel", "1"), ("A-1", "arco", "5"), ("PS-1", "paso", "5.5")):
        v = await control.post(f"/api/v1/trazos/{muro}/vanos", json={"clave": clave, "tipo": tipo, "ancho_m": "0.3", "alto_m": "1", "posicion_m": pos})
        assert v.status_code == 201, v.text
    j = await _fachada(control, plano)
    assert D(j["vanos_m2"]) == D("3.0")  # 2.1 de la puerta + 3 × 0.3


async def test_un_muro_sin_caras_definidas_no_se_cuenta_y_avisa(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano = await _plano(control, escenario, con_zonas=False)
    muro = await _muro(control, plano, "LINESTRING(0 10, 4 10)")
    j = await _fachada(control, plano)
    assert j["muros"] == [] and [x["trazo_id"] for x in j["muros_sin_cara_exterior"]] == [muro] and D(j["neto_m2"]) == 0


async def test_la_fachada_ya_no_depende_del_driver_altura_estandar_ni_de_ninguno(escenario: Escenario, control: httpx.AsyncClient, residente: httpx.AsyncClient) -> None:
    """El plano no lee `altura_estandar` (desacople): ni la altura de un muro sin altura propia ni la fachada cambian al cambiarla."""
    plano = await _plano(control, escenario, con_zonas=False)
    await _muro(control, plano, "LINESTRING(0 10, 5 10)", ubicacion="fachada_a")
    antes = await _fachada(control, plano)
    r = await control.put("/api/v1/drivers/altura_estandar", json={"valor": "5"})
    assert r.status_code == 200, r.text  # Control de obra: se aplica
    assert await _fachada(control, plano) == antes
    assert (await _fachada(residente, plano)) == antes  # todos los roles que ven el plano leen


async def test_un_plano_que_no_existe_da_404(control: httpx.AsyncClient) -> None:
    assert (await control.get("/api/v1/planos/00000000-0000-0000-0000-000000000009/fachada-por-bandas")).status_code == 404


# --- creación atómica del revestimiento -----------------------------------------------------------------------------------


async def _n_trazos(c: httpx.AsyncClient, plano: str) -> int:
    return len((await c.get(f"/api/v1/planos/{plano}/trazos")).json()["features"])


async def test_el_revestimiento_nace_ligado_a_su_muro_en_una_sola_llamada(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano = await _plano(control, escenario, con_zonas=False)
    muro = await _muro(control, plano, "LINESTRING(0 10, 5 10)", ubicacion="fachada_a")
    r = await control.post(
        f"/api/v1/planos/{plano}/trazos",
        json={
            "version_plano": 1, "fuente": "pdf", "geometria_wkt": "LINESTRING(0 11, 3 11)", "enlaces": [],
            "revestimiento_muro_id": muro, "revestimiento_cara": "fachada",
        },
    )
    assert r.status_code == 201, r.text
    props = {f["properties"]["trazo_id"]: f["properties"] for f in (await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"]}
    assert (props[r.json()["trazo_id"]]["revestimiento_de"], props[r.json()["trazo_id"]]["revestimiento_cara"]) == (muro, "fachada")
    # Un revestimiento no es un muro: no entra en la fachada ni en la lista de muros sin cara.
    j = await _fachada(control, plano)
    assert [m["trazo_id"] for m in j["muros"]] == [muro] and j["muros_sin_cara_exterior"] == []


async def test_si_el_revestimiento_no_se_puede_ligar_el_trazo_no_nace(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano = await _plano(control, escenario, con_zonas=False)
    otro_plano = await _plano(control, escenario, con_zonas=False)
    muro = await _muro(control, plano, "LINESTRING(0 10, 5 10)")
    ajeno = await _muro(control, otro_plano, "LINESTRING(0 10, 5 10)")
    punto = (await control.post(f"/api/v1/planos/{plano}/trazos", json={"version_plano": 1, "fuente": "pdf", "geometria_wkt": "POINT(1 1)", "enlaces": []})).json()["trazo_id"]
    antes = await _n_trazos(control, plano)
    base = {"version_plano": 1, "fuente": "pdf", "geometria_wkt": "LINESTRING(0 11, 3 11)", "enlaces": []}
    for muro_id, cara, esperado in (
        (ajeno, "fachada", 422),  # otro plano
        (punto, "fachada", 422),  # el «muro» no es una línea
        ("00000000-0000-0000-0000-000000000009", "fachada", 404),  # no existe
    ):
        r = await control.post(f"/api/v1/planos/{plano}/trazos", json={**base, "revestimiento_muro_id": muro_id, "revestimiento_cara": cara})
        assert r.status_code == esperado, (muro_id, r.text)
    # Una cara que no vale, o el muro sin la cara, ni siquiera llega.
    assert (await control.post(f"/api/v1/planos/{plano}/trazos", json={**base, "revestimiento_muro_id": muro, "revestimiento_cara": "techo"})).status_code == 422
    assert (await control.post(f"/api/v1/planos/{plano}/trazos", json={**base, "revestimiento_muro_id": muro})).status_code == 422
    # El revestimiento no es la línea de otro revestimiento ni un punto.
    bueno = await control.post(f"/api/v1/planos/{plano}/trazos", json={**base, "revestimiento_muro_id": muro, "revestimiento_cara": "interior"})
    assert bueno.status_code == 201
    r = await control.post(
        f"/api/v1/planos/{plano}/trazos", json={**base, "revestimiento_muro_id": bueno.json()["trazo_id"], "revestimiento_cara": "fachada"}
    )
    assert r.status_code == 422
    assert await _n_trazos(control, plano) == antes + 1  # solo el bueno: ningún trazo suelto quedó sin ligar
