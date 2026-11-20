"""Los drivers de la obra leídos por los cálculos de los elementos, con sesión y RLS reales (Ola 4, «drivers conectados»).

Cambiar un driver de la obra en el Paramétrico cambia el cálculo del elemento que lo lee; sin `obra_id` el cálculo no cambia; una
obra ajena o inexistente es 404; GET /drivers dice quién usa cada driver.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest

from obractrl.adapters.api.dependencias import contexto_actual
from obractrl.infrastructure.db.sesion import ContextoSesion
from obractrl.main import crear_app
from tests.integracion.conftest import Escenario

K1 = "/api/v1/biblioteca-de-elementos/estructura/EST-02130/calcular"
BASTON = "/api/v1/biblioteca-de-elementos/baston/BA-1/calcular"
TRABE = "/api/v1/biblioteca-de-elementos/estructura-lineal/T-1-15x25/calcular"
SILLAR = "/api/v1/biblioteca-de-elementos/sillar/BAP-01010/calcular"
TABIQUE = "/api/v1/biblioteca-de-elementos/tabique/EST-02010/calcular"


@pytest.fixture
async def control(contexto_control: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    app = crear_app()
    app.dependency_overrides[contexto_actual] = lambda: contexto_control
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as c:
        yield c


def _usados(r: httpx.Response) -> dict[str, dict]:
    assert r.status_code == 200, r.text
    return {u["clave"]: u for u in r.json()["drivers_usados"]}


async def test_cambiar_un_driver_de_la_obra_cambia_el_calculo_del_elemento_y_sin_obra_no(
    control: httpx.AsyncClient, escenario: Escenario
) -> None:
    obra = str(escenario.obra_id)
    antes = await control.post(K1, json={"alto_m": 3.0, "obra_id": obra})
    assert _usados(antes)["traslape_armex_cm"]["fuente"] == "defecto"

    r = await control.put(f"/api/v1/obras/{obra}/drivers/traslape_armex_cm", json={"valor": "30"})
    assert r.status_code == 200, r.text
    r = await control.put(f"/api/v1/obras/{obra}/drivers/altura_estandar", json={"valor": "3.5"})
    assert r.status_code == 200, r.text

    despues = await control.post(K1, json={"obra_id": obra})
    u = _usados(despues)
    assert (u["traslape_armex_cm"]["valor"], u["traslape_armex_cm"]["fuente"]) == (30, "obra")
    assert (u["altura_estandar"]["valor"], despues.json()["alto_m"]) == (3.5, 3.5)
    assert despues.json()["acero"] != antes.json()["acero"]

    # Sin obra: idéntico a antes de tocar nada, aunque la obra tenga sus drivers.
    sin_obra = await control.post(K1, json={"alto_m": 3.0})
    assert sin_obra.json()["acero"] == antes.json()["acero"]
    assert _usados(sin_obra)["traslape_armex_cm"]["fuente"] == "defecto"
    # La petición manda sobre el driver de la obra.
    p = await control.post(K1, json={"alto_m": 3.0, "obra_id": obra, "drivers": {"traslape_armex_cm": 15}})
    assert p.json()["acero"] == antes.json()["acero"] and _usados(p)["traslape_armex_cm"]["fuente"] == "peticion"

    # Un driver global editado llega a la obra que no lo ajusta.
    g = await control.put("/api/v1/drivers/desperdicio_concreto", json={"valor": "8"})
    assert g.status_code == 200, g.text
    t = await control.post(TRABE, json={"obra_id": obra})
    assert (_usados(t)["desperdicio_concreto"]["valor"], _usados(t)["desperdicio_concreto"]["fuente"]) == (8, "global")
    assert t.json()["concreto"]["desperdicio_pct"] == 8
    b = await control.post(BASTON, json={"obra_id": obra, "largo_cm": 800})
    assert _usados(b)["tolerancia_corte_cm"]["fuente"] == "defecto"


async def test_el_desperdicio_de_mamposteria_de_la_obra_mueve_el_sillar_y_no_el_tabique(control: httpx.AsyncClient, escenario: Escenario) -> None:
    """F6: el driver `desperdicio_mamposteria` lo lee el elemento del sillar amarillo (BAP-01010); el tabique de 14 cm no lo lee (M-105)."""
    obra = str(escenario.obra_id)
    antes = await control.post(SILLAR, json={"obra_id": obra})
    assert _usados(antes)["desperdicio_mamposteria"]["fuente"] == "defecto" and antes.json()["parametros"]["desperdicio_de_pieza_pct"] == 5
    tabique_antes = await control.post(TABIQUE, json={"obra_id": obra})
    assert tabique_antes.status_code == 200, tabique_antes.text
    r = await control.put(f"/api/v1/obras/{obra}/drivers/desperdicio_mamposteria", json={"valor": "10"})
    assert r.status_code == 200, r.text
    despues = await control.post(SILLAR, json={"obra_id": obra})
    u = _usados(despues)["desperdicio_mamposteria"]
    assert (u["valor"], u["fuente"]) == (10, "obra")
    assert despues.json()["piezas"]["por_unidad"] > antes.json()["piezas"]["por_unidad"]
    assert despues.json()["mezcla"]["por_unidad"] > antes.json()["mezcla"]["por_unidad"]
    assert (await control.post(TABIQUE, json={"obra_id": obra})).json() == tabique_antes.json()
    # Sin obra el cálculo no cambia, y la petición manda sobre el driver de la obra.
    assert (await control.post(SILLAR, json={})).json()["piezas"] == antes.json()["piezas"]
    p = await control.post(SILLAR, json={"obra_id": obra, "desperdicio_pct": 5})
    assert _usados(p)["desperdicio_mamposteria"]["fuente"] == "peticion" and p.json()["piezas"] == antes.json()["piezas"]


async def test_una_obra_inexistente_o_ajena_es_404_y_el_calculo_sin_obra_no_la_necesita(control: httpx.AsyncClient) -> None:
    r = await control.post(K1, json={"obra_id": str(uuid.uuid4())})
    assert r.status_code == 404, r.text
    assert (await control.post(K1, json={})).status_code == 200


async def test_get_drivers_dice_quien_usa_cada_uno(control: httpx.AsyncClient, escenario: Escenario) -> None:
    filas = {f["clave"]: f for f in (await control.get(f"/api/v1/obras/{escenario.obra_id}/drivers")).json()}
    # El plano y las plantillas ya NO leen la altura estándar: solo los paramétricos de elementos.
    assert {c["id"] for c in filas["altura_estandar"]["lo_usan"]} == {"estructura"}
    assert {c["id"] for c in filas["separacion_castillos"]["lo_usan"]} >= {"plantilla_colocar", "plantilla_vista_previa"}
    assert {c["id"]: c["lectura"] for c in filas["escarpio_minimo"]["lo_usan"]} == {"cimentacion_de_piedra": "constante"}
    # F6: el desperdicio de mampostería lo lee el elemento del sillar amarillo (el tabique de 14 cm no).
    assert {c["id"] for c in filas["desperdicio_mamposteria"]["lo_usan"]} == {"muro_de_sillar"}
    assert filas["desperdicio_mamposteria"]["sin_consumidor"] is None
