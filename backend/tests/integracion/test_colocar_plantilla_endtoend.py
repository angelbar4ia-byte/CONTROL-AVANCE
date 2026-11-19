"""Colocar en el plano lo que trae la plantilla de un muro (Ola 4C, migración 0135) por HTTP contra Postgres real.

El castillo del plano es una instancia del castillo de la plantilla (`elemento_uid`): sube la altura del muro (el driver, no 2.6 m),
resta de sus m², y alimenta los conceptos que eligen el nivel y el alto (2A) y las ranuras del Paramétrico (4B). Si falta la partida en
el árbol avisa y no cuenta. Un muro sin plantilla conserva la regla vieja del «muro con cadena».
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.api.dependencias import contexto_actual
from obractrl.infrastructure.db.sesion import ContextoSesion
from obractrl.main import crear_app
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario

ELEMENTOS = "/api/v1/elementos-parametricos"
PLANTILLAS = "/api/v1/muro-plantillas"
PARTES = [{"nombre": "Cuerpo", "desde_m": "0", "hasta_m": "3", "rol": "cuerpo"}]


def _cliente(contexto: ContextoSesion) -> httpx.AsyncClient:
    app = crear_app()
    app.dependency_overrides[contexto_actual] = lambda: contexto
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test")


@pytest.fixture
async def control(contexto_control: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_control) as c:
        yield c


@pytest.fixture
async def arbol(escenario: Escenario) -> dict[str, Any]:
    """Conceptos del catálogo (el muro en m², un acero en pza con escalón, un colado en ml por nivel), su partida en el árbol de la obra
    y una actividad por concepto. La actividad del muro está en planta baja."""
    ids = {k: uuid.uuid4() for k in ("m2", "pza", "ml", "muro", "acero", "colado", "colado3", "n1", "n3", "etapa", "a_acero", "a_colado", "a_colado3")}
    org, proto, obra = str(escenario.org_id), str(escenario.prototipo_id), str(escenario.obra_id)
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            for k, clave in (("m2", "m2"), ("pza", "pza"), ("ml", "ml")):
                await c.execute(text("insert into unidad (id, org_id, clave, nombre) values (:i, :o, :c, :c)"), {"i": str(ids[k]), "o": org, "c": clave})
            for k, clave, unidad in (
                ("muro", "MUR-1", "m2"), ("acero", "ACE-1", "pza"), ("colado", "COL-1", "ml"), ("colado3", "COL-3", "ml"),
            ):
                await c.execute(
                    text("insert into concepto (id, org_id, clave, descripcion, unidad_id) values (:i, :o, :k, :k, :u)"),
                    {"i": str(ids[k]), "o": org, "k": clave, "u": str(ids[unidad])},
                )
            await c.execute(
                # F5: con un salto de nivel (no hay orden 2) el número del contexto es explícito, no `orden`.
                text("insert into nivel (id, org_id, clave, descripcion, orden, numero_de_nivel) values (:i, :o, 'NIV-1', 'Planta baja', 1, 1), (:j, :o, 'NIV-3', 'Azotea', 3, 3)"),
                {"i": str(ids["n1"]), "j": str(ids["n3"]), "o": org},
            )
            await c.execute(text("insert into etapa_constructiva (id, org_id, clave, descripcion, orden) values (:i, :o, 'ECO-1', 'Estructura', 1)"), {"i": str(ids["etapa"]), "o": org})
            await c.execute(
                text("update actividad set concepto_id = :c, nivel_id = :n, etapa_id = :e, precio_unitario = 10, cant_base = 500, cant_programada = 500 where id = :a"),
                {"c": str(ids["muro"]), "n": str(ids["n1"]), "e": str(ids["etapa"]), "a": str(escenario.actividad_id)},
            )

            async def nodo(ident: uuid.UUID, padre: uuid.UUID | None, tipo: str, nombre: str, **kw: uuid.UUID) -> None:
                await c.execute(
                    text(
                        "insert into prototipo_nodo (id, org_id, prototipo_id, parent_id, tipo, nombre, clave, concepto_id, nivel_id, etapa_id, orden) "
                        "values (:i, :o, :p, cast(:pa as uuid), cast(:t as tipo_prototipo_nodo), :n, :n, cast(:c as uuid), cast(:ni as uuid), cast(:et as uuid), 0)"
                    ),
                    {
                        "i": str(ident), "o": org, "p": proto, "pa": str(padre) if padre else None, "t": tipo, "n": nombre,
                        "c": str(kw["concepto"]) if "concepto" in kw else None,
                        "ni": str(kw["nivel"]) if "nivel" in kw else None, "et": str(kw["etapa"]) if "etapa" in kw else None,
                    },
                )

            # La planta baja trae el acero y el colado de planta baja; el colado del tercer nivel va en la azotea (o falta, según el caso).
            pb, pb_e = uuid.uuid4(), uuid.uuid4()
            await nodo(pb, None, "nivel", "Planta baja", nivel=ids["n1"])
            await nodo(pb_e, pb, "etapa", "Estructura", etapa=ids["etapa"])
            await nodo(uuid.uuid4(), pb_e, "concepto", "ACE-1", concepto=ids["acero"])
            await nodo(uuid.uuid4(), pb_e, "concepto", "COL-1", concepto=ids["colado"])
            # Una actividad por concepto, para que lo que toman de los elementos aparezca medido.
            for k, concepto in (("a_acero", "acero"), ("a_colado", "colado")):
                await c.execute(
                    text(
                        "insert into actividad (id, org_id, obra_id, concepto_id, nivel_id, etapa_id, cant_base, cant_programada, precio_unitario) "
                        "values (:i, :o, :ob, :c, :n, :e, 100, 100, 10)"
                    ),
                    {"i": str(ids[k]), "o": org, "ob": obra, "c": str(ids[concepto]), "n": str(ids["n1"]), "e": str(ids["etapa"])},
                )
    finally:
        await motor.dispose()
    return {k: str(v) for k, v in ids.items()}


async def _elemento_con_conceptos(control: httpx.AsyncClient, arbol: dict[str, Any]) -> str:
    r = await control.post(ELEMENTOS, json={"clave": "K-1", "nombre": "Castillo K-1", "tipo": "castillo"})
    assert r.status_code == 201, r.text
    elemento = r.json()["id"]
    ruta = f"{ELEMENTOS}/{elemento}/conceptos-por-contexto"
    for cuerpo in (
        {"concepto_id": arbol["acero"], "unidad": "pza", "toma": {"acero": True, "estribos": True, "alambre": True}, "alto_hasta_m": "6"},
        {"concepto_id": arbol["colado"], "unidad": "ml", "toma": {"concreto": True, "cimbra": True}, "nivel_max": 2},
        {"concepto_id": arbol["colado3"], "unidad": "ml", "toma": {"concreto": True, "cimbra": True}, "nivel_min": 3},
    ):
        creado = await control.post(ruta, json=cuerpo)
        assert creado.status_code == 201, creado.text
    return elemento


async def _plantilla(control: httpx.AsyncClient, **cambios: object) -> dict[str, Any]:
    cuerpo = {
        "nombre": "Muro con castillos", "tipo": "con_cadena", "material": "tabique_rojo", "ubicacion": "interior",
        "partes": PARTES, "elementos": [{"ref": "K-1"}],
    } | cambios
    r = await control.post(PLANTILLAS, json=cuerpo)
    assert r.status_code == 201, r.text
    return r.json()


async def _muro(control: httpx.AsyncClient, escenario: Escenario, plantilla: str | None) -> tuple[str, str]:
    plano = (await control.post(f"/api/v1/obras/{escenario.obra_id}/planos", json={"nombre": "P", "archivo_url": "e2e/p.pdf"})).json()["id"]
    r = await control.post(
        f"/api/v1/planos/{plano}/trazos",
        json={
            "version_plano": 1, "fuente": "pdf", "geometria_wkt": "LINESTRING(0 0, 10 0)", "grosor_m": "0.15", "alineacion": "centro",
            # Sin `alt`: nace con la altura base (la de la herramienta, 3.00 m).
            "enlaces": [{"medida": "longitud", "factor": "1", "actividad_id": str(escenario.actividad_id), "conversion": {"modo": "area", "mide": "eje"}}],
        },
    )
    assert r.status_code == 201, r.text
    trazo = r.json()["trazo_id"]
    if plantilla is not None:
        e = await control.put(f"/api/v1/trazos/{trazo}/muro/plantilla", json={"plantilla_id": plantilla})
        assert e.status_code == 200, e.text
    return plano, trazo


async def _medido(control: httpx.AsyncClient, escenario: Escenario, actividad: str | uuid.UUID) -> float | None:
    estado = (await control.get(f"/api/v1/obras/{escenario.obra_id}/cuantificacion")).json()
    nodo = next((n for n in estado if n["nodo_id"] == str(actividad)), None)
    return float(nodo["cantidad_medida"]) if nodo and nodo["cantidad_medida"] is not None else None


async def test_la_plantilla_coloca_sus_castillos_con_la_altura_del_driver_y_alimenta_los_conceptos(
    control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, Any]
) -> None:
    await _elemento_con_conceptos(control, arbol)
    plantilla = await _plantilla(control)
    _, muro = await _muro(control, escenario, plantilla["id"])
    ruta = f"/api/v1/trazos/{muro}/muro/plantilla"

    # Antes de colocar: el reporte dice qué colocaría y qué concepto paga cada parte (sin cambiar nada).
    v = (await control.get(f"{ruta}/colocacion")).json()
    assert (Decimal(v["largo_m"]), Decimal(v["altura_m"]), v["nivel"]) == (Decimal(10), Decimal(3), 1)
    (k,) = v["elementos"]
    assert (k["ref"], k["modo"], k["piezas"], k["colocados"], Decimal(k["alto_m"]), k["se_coloca"]) == ("K-1", "ubicado", 2, 0, Decimal(3), True)
    assert [Decimal(p) for p in k["posiciones_m"]] == [Decimal("0.075"), Decimal("9.925")]
    por_ranura = {c["ranura"]: c for c in k["conceptos"]}
    assert (por_ranura["acero"]["clave"], por_ranura["acero"]["cuenta"], Decimal(por_ranura["acero"]["cantidad"])) == ("ACE-1", True, Decimal(2))
    assert (por_ranura["colado"]["clave"], por_ranura["colado"]["unidad"], Decimal(por_ranura["colado"]["cantidad"])) == ("COL-1", "ml", Decimal(6))
    assert await _medido(control, escenario, arbol["a_acero"]) is None  # aún no hay nada colocado
    antes = await _medido(control, escenario, escenario.actividad_id)
    assert antes == pytest.approx(30)  # por el eje: 10 m × 3.00 m (la de la herramienta, no 2.6)

    r = await control.post(f"{ruta}/colocar")
    assert r.status_code == 200, r.text
    assert (r.json()["colocados"], r.json()["reemplazados"]) == (2, 0)
    vanos = (await control.get(f"/api/v1/trazos/{muro}/vanos")).json()
    assert [(x["tipo"], x["elemento_uid"], Decimal(x["alto_m"]), x["clave"]) for x in vanos] == [("castillo", "K-1", Decimal(3), "K-01"), ("castillo", "K-1", Decimal(3), "K-02")]
    # Resta de los m² del muro lo que ya restaba un castillo (ancho × alto), y alimenta los conceptos de la planta baja.
    assert await _medido(control, escenario, escenario.actividad_id) == pytest.approx(30 - 2 * 0.15 * 3)
    assert await _medido(control, escenario, arbol["a_acero"]) == pytest.approx(2)
    assert await _medido(control, escenario, arbol["a_colado"]) == pytest.approx(6)

    # Idempotente: colocar otra vez reemplaza las instancias, no las duplica.
    r2 = await control.post(f"{ruta}/colocar")
    assert (r2.json()["colocados"], r2.json()["reemplazados"]) == (2, 2)
    assert len((await control.get(f"/api/v1/trazos/{muro}/vanos")).json()) == 2
    assert await _medido(control, escenario, arbol["a_acero"]) == pytest.approx(2)

    # El driver `altura_estandar` cambia después: el plano no lo lee, así que nada se mueve (ni lo colocado ni el muro).
    costos_ruta = f"/api/v1/obras/{escenario.obra_id}/drivers/altura_estandar"
    assert (await control.put(costos_ruta, json={"valor": "2.5"})).status_code == 200
    assert Decimal((await control.get(f"/api/v1/trazos/{muro}/vanos")).json()[0]["alto_m"]) == Decimal(3)
    assert await _medido(control, escenario, arbol["a_colado"]) == pytest.approx(6)

    # Retirar: el muro vuelve a medir lo que medía y los conceptos dejan de tomar.
    assert (await control.delete(f"{ruta}/colocar")).json() == {"retirados": 2}
    assert (await control.get(f"/api/v1/trazos/{muro}/vanos")).json() == []
    assert await _medido(control, escenario, escenario.actividad_id) == pytest.approx(30)
    assert not await _medido(control, escenario, arbol["a_acero"])


async def test_si_falta_la_partida_en_el_arbol_avisa_y_no_cuenta(
    control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, Any]
) -> None:
    await _elemento_con_conceptos(control, arbol)
    plantilla = await _plantilla(control)
    _, muro = await _muro(control, escenario, plantilla["id"])
    # La azotea (3er nivel) no trae el colado COL-3 en el árbol: el contexto lo elige y no hay partida.
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            await c.execute(text("update actividad set nivel_id = :n where id = :a"), {"n": arbol["n3"], "a": str(escenario.actividad_id)})
    finally:
        await motor.dispose()
    v = (await control.get(f"/api/v1/trazos/{muro}/muro/plantilla/colocacion")).json()
    assert v["nivel"] == 3
    colado = next(c for c in v["elementos"][0]["conceptos"] if c["ranura"] == "colado")
    assert (colado["clave"], colado["cuenta"], colado["estado"]) == ("COL-3", False, "falta_partida")
    assert "COL-3" in colado["aviso"] and "no cuenta" in colado["aviso"]
    assert any("COL-3" in a for a in v["avisos"])
    assert (await control.post(f"/api/v1/trazos/{muro}/muro/plantilla/colocar")).status_code == 200
    # El acero sigue contando (su partida está); el colado de la azotea no suma a nada.
    assert await _medido(control, escenario, arbol["a_colado"]) in (None, 0)


async def test_un_castillo_a_mano_en_un_muro_con_plantilla_es_una_instancia_y_sin_plantilla_conserva_la_regla_vieja(
    control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, Any]
) -> None:
    await _elemento_con_conceptos(control, arbol)
    plantilla = await _plantilla(control)
    _, con = await _muro(control, escenario, plantilla["id"])
    r = await control.post(f"/api/v1/trazos/{con}/vanos", json={"clave": "K-01", "tipo": "castillo", "ancho_m": "0.15", "alto_m": "1", "posicion_m": "3"})
    assert r.status_code == 201, r.text
    (v,) = (await control.get(f"/api/v1/trazos/{con}/vanos")).json()
    assert (v["elemento_uid"], Decimal(v["alto_m"])) == ("K-1", Decimal(3))  # sube lo alto del muro (3.00 m de la herramienta), no lo que se mandó
    assert await _medido(control, escenario, arbol["a_acero"]) == pytest.approx(1)

    # Sin plantilla: la regla de siempre (solo un muro «con cadena»), sin elemento.
    _, sin = await _muro(control, escenario, None)
    assert (await control.post(f"/api/v1/trazos/{sin}/muro/plantilla/colocar")).status_code == 422
    assert (await control.post(f"/api/v1/trazos/{sin}/vanos", json={"clave": "K-01", "tipo": "castillo", "ancho_m": "0.15", "alto_m": "1"})).status_code == 422
    assert (await control.put(f"/api/v1/trazos/{sin}/muro/clasificacion", json={"tipo": "con_cadena"})).status_code == 200
    ok = await control.post(f"/api/v1/trazos/{sin}/vanos", json={"clave": "K-01", "tipo": "castillo", "ancho_m": "0.15", "alto_m": "1"})
    assert ok.status_code == 201, ok.text
    (v2,) = (await control.get(f"/api/v1/trazos/{sin}/vanos")).json()
    assert v2["elemento_uid"] is None and Decimal(v2["alto_m"]) == Decimal(3)


async def test_los_castillos_estimados_se_cuentan_pero_no_se_colocan_y_el_castillo_a_mano_no_se_toca(
    control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, Any]
) -> None:
    await _elemento_con_conceptos(control, arbol)
    estimada = await _plantilla(control, nombre="Confinado", tipo="confinado", elementos=[{"ref": "K-1", "sep_m": "2.5"}])
    _, muro = await _muro(control, escenario, estimada["id"])
    v = (await control.get(f"/api/v1/trazos/{muro}/muro/plantilla/colocacion")).json()
    (k,) = v["elementos"]
    assert (k["modo"], k["piezas"], k["se_coloca"], k["posiciones_m"]) == ("estimado", 5, False, [])  # ⌈10 ÷ 2.5⌉ + 1
    assert any("estimados" in a for a in v["avisos"])
    r = await control.post(f"/api/v1/trazos/{muro}/muro/plantilla/colocar")
    assert r.status_code == 422 and "estimados" in r.text


async def test_la_separacion_de_castillos_del_driver_reparte_los_estimados_sin_separacion_propia(
    control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, Any]
) -> None:
    await _elemento_con_conceptos(control, arbol)
    sin_sep = await _plantilla(control, nombre="Confinado sin sep", tipo="confinado", elementos=[{"ref": "K-1"}])
    con_sep = await _plantilla(control, nombre="Confinado con sep", tipo="confinado", elementos=[{"ref": "K-1", "sep_m": "2.5"}])
    ubicada = await _plantilla(control, nombre="Con cadena", tipo="con_cadena", elementos=[{"ref": "K-1"}])
    _, a = await _muro(control, escenario, sin_sep["id"])
    _, b = await _muro(control, escenario, con_sep["id"])
    _, c = await _muro(control, escenario, ubicada["id"])

    async def piezas(trazo: str) -> int:
        (k,) = (await control.get(f"/api/v1/trazos/{trazo}/muro/plantilla/colocacion")).json()["elementos"]
        return int(k["piezas"])

    assert (await piezas(a), await piezas(b), await piezas(c)) == (5, 5, 2)  # 3.00 m de partida: ⌈10 ÷ 3⌉ + 1; el ubicado, en los extremos
    r = await control.put(f"/api/v1/obras/{escenario.obra_id}/drivers/separacion_castillos", json={"valor": "2"})
    assert r.status_code == 200, r.text
    assert (await piezas(a), await piezas(b), await piezas(c)) == (6, 5, 2)  # el driver mueve al que no trae separación; la propia manda
    # Sin plano de por medio, el cambio del driver no toca lo ya colocado (Q1): solo cambia lo que se calcula de ahí en adelante.
