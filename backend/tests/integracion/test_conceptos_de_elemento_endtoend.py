"""Los conceptos que paga un elemento por contexto y escalón, por HTTP contra Postgres real (0128; plan de elementos, fase C)."""

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
from tests.integracion.conftest import DATABASE_URL_ADMIN

RUTA = "/api/v1/elementos-parametricos"
ACERO = {"acero": True, "estribos": True, "alambre": True}
COLADO = {"concreto": True, "cimbra": True}


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


async def _catalogo(escenario, *claves: str) -> dict[str, uuid.UUID]:
    """Da de alta conceptos del catálogo (con la descripción real de la clave, abreviada) y devuelve sus ids."""
    ids = {k: uuid.uuid4() for k in claves}
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            for k, i in ids.items():
                await c.execute(
                    text("insert into concepto (id, org_id, clave, descripcion) values (:i, :o, :k, :d)"),
                    {"i": str(i), "o": str(escenario.org_id), "k": k, "d": f"Concepto {k} del catálogo"},
                )
    finally:
        await motor.dispose()
    return ids


async def _castillo(cliente: httpx.AsyncClient, clave: str = "K-1", **parametros: float) -> str:
    r = await cliente.post(RUTA, json={"clave": clave, "nombre": f"Castillo {clave}", "tipo": "castillo", "parametros": parametros})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _alta(cliente: httpx.AsyncClient, elemento: str, **cuerpo: object) -> httpx.Response:
    return await cliente.post(f"{RUTA}/{elemento}/conceptos-por-contexto", json=cuerpo)


async def _lista(cliente: httpx.AsyncClient, elemento: str, **consulta: object) -> dict:
    r = await cliente.get(f"{RUTA}/{elemento}/conceptos-por-contexto", params=consulta)
    assert r.status_code == 200, r.text
    return r.json()


async def test_el_castillo_paga_el_acero_por_escalon_y_el_colado_por_ml(control: httpx.AsyncClient, escenario) -> None:
    """K-1 del catálogo: acero por pieza en cuatro escalones (EST-10013…EST-10011) y colado y cimbra por ml (EST-02110)."""
    ids = await _catalogo(escenario, "EST-10013", "EST-10012", "EST-10010", "EST-10011", "EST-02110")
    k1 = await _castillo(control)  # alto de defecto: 2.60 m
    for clave, hasta in (("EST-10013", 1.0), ("EST-10012", 1.5), ("EST-10010", 4.0), ("EST-10011", 6.0)):
        r = await _alta(control, k1, concepto_id=str(ids[clave]), unidad="pza", toma=ACERO, alto_hasta_m=hasta)
        assert r.status_code == 201, r.text
    assert (await _alta(control, k1, concepto_id=str(ids["EST-02110"]), unidad="ml", toma=COLADO)).status_code == 201

    lista = await _lista(control, k1, nivel=1)
    assert lista["alto_m"] == pytest.approx(2.6)
    assert lista["por_parte"] == {"acero": "EST-10010", "concreto": "EST-02110", "cimbra": "EST-02110"}
    assert lista["avisos"] == []
    por_clave = {c["clave"]: c for c in lista["conceptos"]}
    assert [c["clave"] for c in lista["conceptos"] if c["elegido"]] == ["EST-10010", "EST-02110"] or {
        c["clave"] for c in lista["conceptos"] if c["elegido"]
    } == {"EST-10010", "EST-02110"}
    assert por_clave["EST-10010"]["ranura"] == "acero" and por_clave["EST-10010"]["unidad"] == "pza"
    assert por_clave["EST-10010"]["alto_hasta_m"] == pytest.approx(4.0)
    assert por_clave["EST-02110"]["ranura"] == "colado" and por_clave["EST-02110"]["estado"] == "autorizado"
    assert por_clave["EST-02110"]["descripcion"] == "Concepto EST-02110 del catálogo"

    # Un alto de 5 m cae en el escalón hasta 6.00; uno de 7 m no tiene escalón y avisa.
    assert (await _lista(control, k1, nivel=1, alto_m=5))["por_parte"]["acero"] == "EST-10011"
    sin_escalon = await _lista(control, k1, nivel=1, alto_m=7)
    assert sin_escalon["por_parte"]["acero"] == "EST-10011"
    assert any("no tiene escalón" in a for a in sin_escalon["avisos"])
    # Sin elegir contexto, el castillo de 6.5 m también avisa.
    k2 = await _castillo(control, "K-2", alto=6.5)
    for clave, hasta in (("EST-10010", 4.0), ("EST-10011", 6.0)):
        assert (await _alta(control, k2, concepto_id=str(ids[clave]), unidad="pza", toma=ACERO, alto_hasta_m=hasta)).status_code == 201
    assert any("no tiene escalón" in a for a in (await _lista(control, k2))["avisos"])


async def test_el_mismo_elemento_paga_est_02010_en_los_niveles_1_y_2_y_est_02011_desde_el_3(control: httpx.AsyncClient, escenario) -> None:
    ids = await _catalogo(escenario, "EST-02010", "EST-02011")
    k = await _castillo(control)
    completo = {"acero": True, "concreto": True, "cimbra": True}
    assert (await _alta(control, k, concepto_id=str(ids["EST-02010"]), unidad="ml", toma=completo, nivel_min=1, nivel_max=2)).status_code == 201
    assert (await _alta(control, k, concepto_id=str(ids["EST-02011"]), unidad="ml", toma=completo, nivel_min=3)).status_code == 201
    for nivel, esperado in ((1, "EST-02010"), (2, "EST-02010"), (3, "EST-02011"), (4, "EST-02011")):
        lista = await _lista(control, k, nivel=nivel)
        assert set(lista["por_parte"].values()) == {esperado}, nivel
        assert [c["clave"] for c in lista["conceptos"] if c["elegido"]] == [esperado]
    todos = await _lista(control, k)
    assert [c["contexto"] for c in todos["conceptos"]] == ["niveles 1 a 2", "nivel 3 en adelante"]
    assert all(c["elegido"] is None for c in todos["conceptos"])
    assert {c["ranura"] for c in todos["conceptos"]} == {"completo"}


async def test_una_parte_la_toma_un_solo_concepto_por_contexto(control: httpx.AsyncClient, escenario) -> None:
    ids = await _catalogo(escenario, "EST-02010", "EST-02011", "EST-02110")
    k = await _castillo(control)
    assert (await _alta(control, k, concepto_id=str(ids["EST-02010"]), unidad="ml", toma=COLADO, nivel_min=1, nivel_max=2)).status_code == 201
    # Mismo contexto que se traslapa: rechazado. Contexto distinto: aceptado.
    r = await _alta(control, k, concepto_id=str(ids["EST-02110"]), unidad="ml", toma={"concreto": True})
    assert r.status_code == 422 and "un solo concepto por contexto" in r.json()["detail"], r.text
    assert (await _alta(control, k, concepto_id=str(ids["EST-02011"]), unidad="ml", toma=COLADO, nivel_min=3)).status_code == 201
    # El mismo concepto en el mismo contexto no se repite.
    assert (await _alta(control, k, concepto_id=str(ids["EST-02010"]), unidad="ml", toma={"acero": True}, nivel_min=1, nivel_max=2)).status_code == 422
    # Falta el acero: la lectura avisa que se perdería del presupuesto.
    assert any(a.startswith("Sin concepto") for a in (await _lista(control, k, nivel=1))["avisos"])


async def test_un_concepto_nuevo_queda_propuesto_sin_precio_y_solo_su_descripcion_se_edita(
    control: httpx.AsyncClient, residente: httpx.AsyncClient, escenario
) -> None:
    ids = await _catalogo(escenario, "EST-10010")
    k = await _castillo(control)
    # Propuesto: sin concepto del catálogo, con clave y descripción.
    r = await _alta(control, k, clave_propuesta="ej-410", descripcion="Acero del castillo hasta 8 m", unidad="pza", toma=ACERO, alto_hasta_m=8)
    assert r.status_code == 201, r.text
    fila = r.json()["id"]
    nuevo = next(c for c in (await _lista(control, k))["conceptos"] if c["id"] == fila)
    assert (nuevo["clave"], nuevo["estado"], nuevo["nuevo"], nuevo["concepto_id"]) == ("EJ-410", "propuesto", True, None)
    assert nuevo["alto_hasta_m"] == pytest.approx(8.0) and nuevo["ranura"] == "acero"
    assert "precio" not in nuevo
    # Sin descripción, con una clave que ya está en el catálogo, o con las dos cosas a la vez: se rechaza.
    assert (await _alta(control, k, clave_propuesta="EJ-411", unidad="pza", toma=ACERO, alto_hasta_m=9)).status_code == 422
    assert (await _alta(control, k, clave_propuesta="EST-10010", descripcion="x", unidad="pza", toma=ACERO, alto_hasta_m=9)).status_code == 422
    assert (await _alta(control, k, clave_propuesta="EJ-411", concepto_id=str(ids["EST-10010"]), descripcion="x", unidad="pza", toma=ACERO, alto_hasta_m=9)).status_code == 422
    assert (await _alta(control, k, descripcion="x", unidad="pza", toma=ACERO, alto_hasta_m=9)).status_code == 422
    # Un residente no define; y solo la descripción cambia (clave y «hasta» quedan fijos).
    ruta = f"{RUTA}/{k}/conceptos-por-contexto/{fila}"
    assert (await residente.patch(ruta, json={"descripcion": "otra"})).status_code == 403
    assert (await _alta(residente, k, clave_propuesta="EJ-412", descripcion="x", unidad="pza", toma=ACERO)).status_code == 403
    assert (await control.patch(ruta, json={"descripcion": "  Acero hasta 8 m, armex 10x10-4  "})).status_code == 204
    cambiado = next(c for c in (await _lista(control, k))["conceptos"] if c["id"] == fila)
    assert cambiado["descripcion"] == "Acero hasta 8 m, armex 10x10-4"
    assert (cambiado["clave"], cambiado["alto_hasta_m"], cambiado["estado"]) == ("EJ-410", pytest.approx(8.0), "propuesto")
    assert (await control.patch(ruta, json={"clave": "EJ-999"})).status_code == 422  # la clave no se edita
    assert (await control.patch(f"{RUTA}/{k}/conceptos-por-contexto/{uuid.uuid4()}", json={"descripcion": "x"})).status_code == 404
    # Quitar el escalón mal puesto para corregirlo.
    assert (await control.delete(ruta)).status_code == 204
    assert (await _lista(control, k))["conceptos"] == []


async def test_los_conceptos_por_contexto_no_alimentan_las_tomas_y_los_generales_siguen_igual(control: httpx.AsyncClient, escenario) -> None:
    """El camino anterior (`/conceptos`) solo ve el concepto sin contexto ni escalón: lo contextual espera al Cuantificador."""
    ids = await _catalogo(escenario, "HAB-1", "EST-10010")
    k = await _castillo(control)
    legado = f"{RUTA}/{k}/conceptos"
    assert (await control.put(f"{legado}/{ids['HAB-1']}", json={"unidad": "pza", "toma": {"acero": True}})).status_code == 204
    assert (await _alta(control, k, concepto_id=str(ids["EST-10010"]), unidad="pza", toma={"concreto": True}, alto_hasta_m=4)).status_code == 201
    assert [c["clave"] for c in (await control.get(legado)).json()] == ["HAB-1"]
    todos = {c["clave"]: c for c in (await _lista(control, k))["conceptos"]}
    assert set(todos) == {"HAB-1", "EST-10010"}
    assert todos["HAB-1"]["estado"] == "autorizado" and todos["HAB-1"]["contexto"] == "Todo contexto"
    # Quitar el general por el camino anterior no toca el escalonado con el mismo concepto.
    assert (await control.delete(f"{legado}/{ids['EST-10010']}")).status_code == 204
    assert "EST-10010" in {c["clave"] for c in (await _lista(control, k))["conceptos"]}


async def test_validaciones_de_contexto_y_unidad(control: httpx.AsyncClient, escenario) -> None:
    ids = await _catalogo(escenario, "A-1")
    k = await _castillo(control)
    base = {"concepto_id": str(ids["A-1"]), "unidad": "ml", "toma": COLADO}
    assert (await _alta(control, k, **{**base, "nivel_min": 3, "nivel_max": 2})).status_code == 422
    assert (await _alta(control, k, **{**base, "ubicacion": "azotea"})).status_code == 422
    assert (await _alta(control, k, **{**base, "unidad": "m²"})).status_code == 422  # un castillo no se cuenta en m²
    assert (await _alta(control, k, **{**base, "toma": {}})).status_code == 422
    assert (await _alta(control, k, **{**base, "concepto_id": str(uuid.uuid4())})).status_code == 404
    assert (await control.get(f"{RUTA}/{uuid.uuid4()}/conceptos-por-contexto")).status_code == 404
    assert (await _alta(control, k, **base, ubicacion="barda")).status_code == 201


async def test_una_version_nueva_del_elemento_hereda_los_conceptos_por_contexto(control: httpx.AsyncClient, escenario) -> None:
    """D-639: al cambiar la receta con una obra asignada nace la versión 2 y trae los conceptos con su contexto, escalón y estado."""
    from tests.integracion.test_elementos_parametricos_endtoend import _plano_con_trazos

    ids = await _catalogo(escenario, "EST-10010")
    k = await _castillo(control, "K-V")
    assert (await _alta(control, k, concepto_id=str(ids["EST-10010"]), unidad="pza", toma=ACERO, nivel_min=2, alto_hasta_m=4)).status_code == 201
    assert (await _alta(control, k, clave_propuesta="EJ-410", descripcion="Nuevo", unidad="ml", toma=COLADO, nivel_min=2)).status_code == 201
    _, trazos = await _plano_con_trazos(control, escenario)
    assert (await control.put(f"/api/v1/trazos/{trazos['punto']}/elemento-parametrico", json={"elemento_id": k})).status_code == 204
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            await c.execute(
                text("insert into parte_estado (org_id, obra_id, clave, estado) values (:o, :ob, 'sin_etapa', 'asignada')"),
                {"o": str(escenario.org_id), "ob": str(escenario.obra_id)},
            )
    finally:
        await motor.dispose()
    assert (await control.patch(f"{RUTA}/{k}", json={"parametros": {"alto": 3.0}})).status_code == 204
    vigente = next(e for e in (await control.get(RUTA)).json() if e["clave"] == "K-V")
    assert vigente["version"] == 2 and vigente["id"] != k
    heredados = {(c["clave"], c["estado"], c["nivel_min"], c["alto_hasta_m"], c["ranura"]) for c in (await _lista(control, vigente["id"]))["conceptos"]}
    assert heredados == {("EST-10010", "autorizado", 2, 4.0, "acero"), ("EJ-410", "propuesto", 2, None, "colado")}
    assert (await _lista(control, vigente["id"]))["alto_m"] == pytest.approx(3.0)
    assert len((await _lista(control, k))["conceptos"]) == 2  # y la versión anterior conserva los suyos
