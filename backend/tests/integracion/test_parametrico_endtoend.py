"""El Paramétrico por HTTP contra Postgres real (migración 0134; Ola 4B): drivers global / por obra / mixto con sus permisos (Q3)
y el enlace de ranuras con el árbol de la obra (si falta la partida, avisa y no cuenta)."""

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


def _cliente(contexto: ContextoSesion) -> httpx.AsyncClient:
    app = crear_app()
    app.dependency_overrides[contexto_actual] = lambda: contexto
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test")


async def _usuario(escenario: Escenario, rol: str, nombre: str) -> uuid.UUID:
    usuario = uuid.uuid4()
    motor = create_async_engine(DATABASE_URL_ADMIN)
    async with motor.begin() as c:
        await c.execute(
            text("insert into usuario (id, org_id, nombre, email, rol) values (:i, :o, :n, :e, :r)"),
            {"i": str(usuario), "o": str(escenario.org_id), "n": nombre, "e": f"{rol}-{usuario.hex[:8]}@t.mx", "r": rol},
        )
    await motor.dispose()
    return usuario


@pytest.fixture
async def control(contexto_control: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_control) as c:
        yield c


@pytest.fixture
async def costos(escenario: Escenario) -> AsyncIterator[httpx.AsyncClient]:
    usuario = await _usuario(escenario, "costos", "Costos")
    async with _cliente(ContextoSesion(org_id=escenario.org_id, usuario_id=usuario, rol="costos")) as c:
        yield c


@pytest.fixture
async def residente(contexto_residente: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_residente) as c:
        yield c


@pytest.fixture
async def arbol(escenario: Escenario) -> dict[str, Any]:
    """El árbol de la obra: Planta baja > Estructura > EST-10010; Planta baja > Albañilería > EST-02010; Azotea > Albañilería > EST-02011.
    Más un concepto del catálogo que NO está en el árbol (EST-10011)."""
    ids = {k: uuid.uuid4() for k in ("pb", "pb_est", "pb_alb", "az", "az_alb", "n_pb", "n_az", "e_est", "e_alb", "c_acero", "c_tabique", "c_azotea", "c_fuera", "u")}
    motor = create_async_engine(DATABASE_URL_ADMIN)
    org, proto = str(escenario.org_id), str(escenario.prototipo_id)
    try:
        async with motor.begin() as c:
            await c.execute(text("insert into unidad (id, org_id, clave, nombre) values (:i, :o, 'm2', 'Metro cuadrado')"), {"i": str(ids["u"]), "o": org})
            for k, clave, desc in (
                ("c_acero", "EST-10010", "Colocación de acero"), ("c_tabique", "EST-02010", "Muro de tabique de 14 cm"),
                ("c_azotea", "EST-02011", "Muro de tabique de 14 cm, 3er nivel"), ("c_fuera", "EST-10011", "Concepto fuera del árbol"),
            ):
                await c.execute(
                    text("insert into concepto (id, org_id, clave, descripcion, unidad_id) values (:i, :o, :k, :d, :u)"),
                    {"i": str(ids[k]), "o": org, "k": clave, "d": desc, "u": str(ids["u"])},
                )
            await c.execute(text("insert into nivel (id, org_id, clave, descripcion, orden) values (:i, :o, 'NIV-1', 'Planta baja', 1), (:j, :o, 'NIV-3', 'Azotea (3er nivel)', 3)"), {"i": str(ids["n_pb"]), "j": str(ids["n_az"]), "o": org})
            await c.execute(text("insert into etapa_constructiva (id, org_id, clave, descripcion, orden) values (:i, :o, 'ECO-1', 'Estructura', 1), (:j, :o, 'ECO-2', 'Albañilería', 2)"), {"i": str(ids["e_est"]), "j": str(ids["e_alb"]), "o": org})

            async def nodo(ident: uuid.UUID, padre: uuid.UUID | None, tipo: str, nombre: str, clave: str, **kw: uuid.UUID) -> None:
                await c.execute(
                    text(
                        "insert into prototipo_nodo (id, org_id, prototipo_id, parent_id, tipo, nombre, clave, concepto_id, nivel_id, etapa_id, orden) "
                        "values (:i, :o, :p, cast(:pa as uuid), cast(:t as tipo_prototipo_nodo), :n, :k, cast(:c as uuid), cast(:ni as uuid), cast(:et as uuid), 0)"
                    ),
                    {
                        "i": str(ident), "o": org, "p": proto, "pa": str(padre) if padre else None, "t": tipo, "n": nombre, "k": clave,
                        "c": str(kw["concepto"]) if "concepto" in kw else None,
                        "ni": str(kw["nivel"]) if "nivel" in kw else None, "et": str(kw["etapa"]) if "etapa" in kw else None,
                    },
                )

            await nodo(ids["pb"], None, "nivel", "Planta baja", "NIV-1", nivel=ids["n_pb"])
            await nodo(ids["pb_est"], ids["pb"], "etapa", "Estructura", "ECO-1", etapa=ids["e_est"])
            await nodo(uuid.uuid4(), ids["pb_est"], "concepto", "EST-10010", "EST-10010", concepto=ids["c_acero"])
            await nodo(ids["pb_alb"], ids["pb"], "etapa", "Albañilería", "ECO-2", etapa=ids["e_alb"])
            await nodo(uuid.uuid4(), ids["pb_alb"], "concepto", "EST-02010", "EST-02010", concepto=ids["c_tabique"])
            await nodo(ids["az"], None, "nivel", "Azotea", "NIV-3", nivel=ids["n_az"])
            await nodo(ids["az_alb"], ids["az"], "etapa", "Albañilería", "ECO-2", etapa=ids["e_alb"])
            await nodo(uuid.uuid4(), ids["az_alb"], "concepto", "EST-02011", "EST-02011", concepto=ids["c_azotea"])
    finally:
        await motor.dispose()
    return {k: str(v) for k, v in ids.items()}


def _drivers(r: httpx.Response) -> dict[str, dict[str, Any]]:
    assert r.status_code == 200, r.text
    return {d["clave"]: d for d in r.json()}


# --- drivers ------------------------------------------------------------------------------------------------------------


async def test_los_drivers_de_partida_traen_la_altura_de_3_m_y_lo_lee_cualquier_rol(residente: httpx.AsyncClient) -> None:
    d = _drivers(await residente.get("/api/v1/drivers"))
    assert len(d) == 14
    a = d["altura_estandar"]
    assert (a["valor_global"], a["valor_vigente"], a["origen"], a["modo"], a["editado"]) == ("3", "3", "inicial", "ajustable", False)
    assert d["escarpio_minimo"]["modo"] == "fijo" and d["corona_cimiento_cm"]["valor_global"] == "40"


async def test_solo_costos_y_control_de_obra_editan_los_drivers(residente: httpx.AsyncClient, escenario: Escenario) -> None:
    assert (await residente.put("/api/v1/drivers/altura_estandar", json={"valor": "2.8"})).status_code == 403
    assert (await residente.put(f"/api/v1/obras/{escenario.obra_id}/drivers/altura_estandar", json={"valor": "2.8"})).status_code == 403
    assert (await residente.delete(f"/api/v1/obras/{escenario.obra_id}/drivers/altura_estandar")).status_code == 403


async def test_global_por_obra_y_mixto(costos: httpx.AsyncClient, control: httpx.AsyncClient, residente: httpx.AsyncClient, escenario: Escenario) -> None:
    obra = f"/api/v1/obras/{escenario.obra_id}/drivers"
    # Costos cambia el global.
    r = await costos.put("/api/v1/drivers/altura_estandar", json={"valor": "2.8"})
    assert r.status_code == 200, r.text
    assert (r.json()["valor_global"], r.json()["origen"], r.json()["editado"]) == ("2.8", "global", True)
    # Control de obra ajusta la obra: el vigente es el de la obra; el global no cambia.
    r = await control.put(f"{obra}/altura_estandar", json={"valor": "2.6"})
    assert r.status_code == 200, r.text
    a = r.json()
    assert (a["valor_vigente"], a["valor_global"], a["valor_obra"], a["origen"]) == ("2.6", "2.8", "2.6", "obra")
    # El residente lo ve de la obra y el global sin la obra.
    assert _drivers(await residente.get(obra))["altura_estandar"]["valor_vigente"] == "2.6"
    assert _drivers(await residente.get("/api/v1/drivers"))["altura_estandar"]["valor_vigente"] == "2.8"
    # Fijo: el ajuste de la obra deja de valer (pero queda guardado) y no se pueden crear más.
    r = await costos.put("/api/v1/drivers/altura_estandar", json={"modo": "fijo"})
    assert r.status_code == 200 and r.json()["valor_global"] == "2.8"
    a = _drivers(await costos.get(obra))["altura_estandar"]
    assert (a["valor_vigente"], a["origen"], a["ajuste_ignorado"], a["valor_obra"]) == ("2.8", "global", True, "2.6")
    assert (await costos.put(f"{obra}/altura_estandar", json={"valor": "2.7"})).status_code == 422
    # De vuelta a ajustable: el ajuste guardado vale otra vez. Quitarlo devuelve la obra al global.
    await control.put("/api/v1/drivers/altura_estandar", json={"modo": "ajustable"})
    assert _drivers(await costos.get(obra))["altura_estandar"]["valor_vigente"] == "2.6"
    r = await costos.delete(f"{obra}/altura_estandar")
    assert r.status_code == 200 and (r.json()["valor_vigente"], r.json()["origen"], r.json()["valor_obra"]) == ("2.8", "global", None)


async def test_un_driver_fijo_de_partida_no_se_ajusta_por_obra(costos: httpx.AsyncClient, escenario: Escenario) -> None:
    r = await costos.put(f"/api/v1/obras/{escenario.obra_id}/drivers/escarpio_minimo", json={"valor": "2"})
    assert r.status_code == 422 and "fijo" in r.json()["detail"]


@pytest.mark.parametrize("valor", ["0", "-3", "abc", "31"])
async def test_un_valor_que_no_vale_se_rechaza(costos: httpx.AsyncClient, valor: str) -> None:
    r = await costos.put("/api/v1/drivers/altura_estandar", json={"valor": valor})
    assert r.status_code in (422,), r.text


async def test_un_driver_o_una_obra_que_no_existen_dan_404(costos: httpx.AsyncClient) -> None:
    assert (await costos.put("/api/v1/drivers/no_existe", json={"valor": "1"})).status_code == 404
    assert (await costos.get(f"/api/v1/obras/{uuid.uuid4()}/drivers")).status_code == 404
    assert (await costos.put(f"/api/v1/obras/{uuid.uuid4()}/drivers/altura_estandar", json={"valor": "2"})).status_code == 404


async def test_hay_que_enviar_el_valor_o_el_modo(costos: httpx.AsyncClient) -> None:
    assert (await costos.put("/api/v1/drivers/altura_estandar", json={})).status_code == 422


async def test_el_cambio_de_un_driver_queda_en_la_bitacora(costos: httpx.AsyncClient, escenario: Escenario) -> None:
    await costos.put("/api/v1/drivers/desperdicio_concreto", json={"valor": "7"})
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.connect() as c:
            n = (
                await c.execute(
                    text("select count(*) from bitacora where org_id = :o and entidad = 'driver_valor' and accion = 'insert'"),
                    {"o": str(escenario.org_id)},
                )
            ).scalar_one()
    finally:
        await motor.dispose()
    assert n == 1


# --- la altura estándar (Q1) ------------------------------------------------------------------------------------------


async def test_la_funcion_de_la_base_resuelve_como_el_dominio(costos: httpx.AsyncClient, escenario: Escenario) -> None:
    async def vigente(defecto: str = "3") -> Decimal:
        motor = create_async_engine(DATABASE_URL_ADMIN)
        try:
            async with motor.begin() as c:
                await c.execute(text("select set_config('app.org_id', :o, true)"), {"o": str(escenario.org_id)})
                return Decimal(
                    (
                        await c.execute(
                            text("select app.driver_numerico(:ob, 'altura_estandar', cast(:d as numeric))"), {"ob": str(escenario.obra_id), "d": defecto}
                        )
                    ).scalar_one()
                )
        finally:
            await motor.dispose()

    assert await vigente("3") == Decimal("3")  # sin fila vale el valor de partida
    await costos.put("/api/v1/drivers/altura_estandar", json={"valor": "2.9"})
    assert await vigente() == Decimal("2.9")
    await costos.put(f"/api/v1/obras/{escenario.obra_id}/drivers/altura_estandar", json={"valor": "2.4"})
    assert await vigente() == Decimal("2.4")
    await costos.put("/api/v1/drivers/altura_estandar", json={"modo": "fijo"})
    assert await vigente() == Decimal("2.9")


# --- enlace de ranuras ----------------------------------------------------------------------------------------------------


async def test_el_listado_trae_las_capas_del_arbol_y_las_ranuras_de_plantilla(costos: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, Any]) -> None:
    r = await costos.get(f"/api/v1/obras/{escenario.obra_id}/enlaces-de-ranura")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["enlaces"] == [] and j["partidas_del_arbol"] == 3
    assert [c["clave"] for c in j["conceptos_del_arbol"]] == ["EST-02010", "EST-02011", "EST-10010"]
    assert {n["clave"] for n in j["niveles"]} == {"NIV-1", "NIV-3"} and {e["clave"] for e in j["etapas"]} == {"ECO-1", "ECO-2"}
    assert j["ranuras_de_plantilla"][0]["ranura"] == "mamposteria:tabique_rojo"
    assert {x["ranura"]: x["sugerido_clave"] for x in j["ranuras_de_plantilla"] if x["sugerido_clave"]} == {
        "mamposteria:tabique_rojo": "EST-02010", "mamposteria:sillar_amarillo": "BAP-01010",  # block hueco y cantera rosa: sin concepto (por capturar)
    }


async def test_enlazar_con_la_partida_en_el_arbol_cuenta(costos: httpx.AsyncClient, residente: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, Any]) -> None:
    ruta = f"/api/v1/obras/{escenario.obra_id}/enlaces-de-ranura"
    r = await costos.put(
        ruta,
        json={"ranura": "mamposteria:tabique_rojo", "concepto_clave": "est-02010", "nivel_id": arbol["n_pb"], "etapa_id": arbol["e_alb"]},
    )
    assert r.status_code == 201, r.text
    e = r.json()
    assert (e["estado"], e["cuenta"], e["concepto_clave"], e["aviso"]) == ("enlazado", True, "EST-02010", None)
    assert e["partida_id"] is not None and e["capa"]["nivel_id"] == arbol["n_pb"]
    # El residente lo ve (de su obra) pero no lo cambia.
    assert len((await residente.get(ruta)).json()["enlaces"]) == 1
    assert (await residente.put(ruta, json={"ranura": "mamposteria:tabique_rojo", "concepto_clave": "EST-02010"})).status_code == 403
    assert (await residente.delete(f"{ruta}/{e['id']}")).status_code == 403


async def test_si_falta_la_partida_en_el_arbol_avisa_y_no_cuenta(costos: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, Any]) -> None:
    ruta = f"/api/v1/obras/{escenario.obra_id}/enlaces-de-ranura"
    # Un concepto del catálogo que el árbol no trae.
    r = await costos.put(ruta, json={"ranura": "elemento:K-1:acero", "concepto_clave": "EST-10011"})
    assert r.status_code == 201
    e = r.json()
    assert (e["estado"], e["cuenta"], e["partida_id"]) == ("falta_partida", False, None)
    assert "EST-10011" in e["aviso"] and "no cuenta" in e["aviso"]
    # El tabique existe en la planta baja, pero esta capa es la azotea: tampoco hay partida ahí.
    r = await costos.put(ruta, json={"ranura": "mamposteria:tabique_rojo", "concepto_clave": "EST-02010", "nivel_id": arbol["n_az"]})
    assert r.json()["estado"] == "falta_partida"
    res = await costos.get(f"{ruta}/resolver", params={"ranura": "elemento:K-1:acero", "nivel_id": arbol["n_pb"]})
    assert res.status_code == 200 and res.json()["estado"] == "falta_partida" and res.json()["cuenta"] is False


async def test_gana_la_capa_mas_especifica_y_resolver_dice_que_cuenta(costos: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, Any]) -> None:
    ruta = f"/api/v1/obras/{escenario.obra_id}/enlaces-de-ranura"
    await costos.put(ruta, json={"ranura": "mamposteria:tabique_rojo", "concepto_clave": "EST-02010"})
    await costos.put(ruta, json={"ranura": "mamposteria:tabique_rojo", "concepto_clave": "EST-02011", "nivel_id": arbol["n_az"]})
    pb = (await costos.get(f"{ruta}/resolver", params={"ranura": "mamposteria:tabique_rojo", "nivel_id": arbol["n_pb"], "etapa_id": arbol["e_alb"]})).json()
    assert (pb["estado"], pb["cuenta"], pb["concepto_clave"]) == ("enlazado", True, "EST-02010")
    az = (await costos.get(f"{ruta}/resolver", params={"ranura": "mamposteria:tabique_rojo", "nivel_id": arbol["n_az"], "etapa_id": arbol["e_alb"]})).json()
    assert (az["estado"], az["cuenta"], az["concepto_clave"]) == ("enlazado", True, "EST-02011")
    # Una ranura sin enlace: la de un elemento conserva sus conceptos por defecto; la de plantilla no cuenta.
    k = (await costos.get(f"{ruta}/resolver", params={"ranura": "elemento:K-2:acero"})).json()
    assert (k["estado"], k["cuenta"], k["por_defecto"]) == ("sin_enlace", False, True)
    a = (await costos.get(f"{ruta}/resolver", params={"ranura": "acabado:gris:exterior"})).json()
    assert (a["estado"], a["por_defecto"]) == ("sin_enlace", False)


async def test_enlazar_dos_veces_la_misma_capa_cambia_el_concepto(costos: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, Any]) -> None:
    ruta = f"/api/v1/obras/{escenario.obra_id}/enlaces-de-ranura"
    primero = await costos.put(ruta, json={"ranura": "elemento:K-1:acero", "concepto_clave": "EST-10011", "ubicacion": "barda"})
    segundo = await costos.put(ruta, json={"ranura": "elemento:K-1:acero", "concepto_clave": "EST-10010", "ubicacion": "barda"})
    assert primero.status_code == 201 and segundo.status_code == 200
    assert segundo.json()["id"] == primero.json()["id"] and segundo.json()["concepto_clave"] == "EST-10010"
    assert len((await costos.get(ruta)).json()["enlaces"]) == 1


async def test_no_se_inventa_un_concepto_ni_una_ranura_ni_una_ubicacion(costos: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, Any]) -> None:
    ruta = f"/api/v1/obras/{escenario.obra_id}/enlaces-de-ranura"
    r = await costos.put(ruta, json={"ranura": "mamposteria:sillar_amarillo", "concepto_clave": "EJ-101"})
    assert r.status_code == 422 and "EJ-101" in r.json()["detail"]
    assert (await costos.put(ruta, json={"ranura": "algo raro", "concepto_clave": "EST-02010"})).status_code == 422
    assert (await costos.put(ruta, json={"ranura": "mamposteria:tabique_rojo", "concepto_clave": "EST-02010", "ubicacion": "azotea"})).status_code == 422
    assert (await costos.put(ruta, json={"ranura": "mamposteria:tabique_rojo", "concepto_clave": "EST-02010", "nivel_id": str(uuid.uuid4())})).status_code == 422
    assert (await costos.get(ruta)).json()["enlaces"] == []


async def test_quitar_un_enlace(control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, Any]) -> None:
    ruta = f"/api/v1/obras/{escenario.obra_id}/enlaces-de-ranura"
    e = (await control.put(ruta, json={"ranura": "mamposteria:tabique_rojo", "concepto_clave": "EST-02010"})).json()
    assert (await control.delete(f"{ruta}/{e['id']}")).status_code == 204
    assert (await control.delete(f"{ruta}/{e['id']}")).status_code == 404
    assert (await control.get(ruta)).json()["enlaces"] == []


async def test_una_obra_ajena_da_404(costos: httpx.AsyncClient) -> None:
    ruta = f"/api/v1/obras/{uuid.uuid4()}/enlaces-de-ranura"
    assert (await costos.get(ruta)).status_code == 404
    assert (await costos.put(ruta, json={"ranura": "mamposteria:tabique_rojo", "concepto_clave": "EST-02010"})).status_code == 404
