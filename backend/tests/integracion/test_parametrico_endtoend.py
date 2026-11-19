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
    assert len(d) == 14  # los catorce de la especificación: la fachada por bandas no agrega drivers
    a = d["altura_estandar"]
    assert (a["valor_global"], a["valor_vigente"], a["origen"], a["modo"], a["editado"]) == ("3", "3", "inicial", "ajustable", False)
    assert d["escarpio_minimo"]["modo"] == "fijo" and d["corona_cimiento_cm"]["valor_global"] == "40"


async def test_solo_costos_y_control_de_obra_editan_los_drivers(residente: httpx.AsyncClient, escenario: Escenario) -> None:
    assert (await residente.put("/api/v1/drivers/altura_estandar", json={"valor": "2.8"})).status_code == 403
    assert (await residente.put(f"/api/v1/obras/{escenario.obra_id}/drivers/altura_estandar", json={"valor": "2.8"})).status_code == 403
    assert (await residente.delete(f"/api/v1/obras/{escenario.obra_id}/drivers/altura_estandar")).status_code == 403


async def _autorizar(control: httpx.AsyncClient, r: httpx.Response) -> dict[str, Any]:
    """Costos propone (202): Control de obra autoriza esa propuesta y el cambio se aplica."""
    assert r.status_code == 202, r.text
    a = await control.post(f"/api/v1/drivers-propuestas/{r.json()['propuesta']['id']}/autorizar")
    assert a.status_code == 200, a.text
    return a.json()  # type: ignore[no-any-return]


async def test_global_por_obra_y_mixto(costos: httpx.AsyncClient, control: httpx.AsyncClient, residente: httpx.AsyncClient, escenario: Escenario) -> None:
    obra = f"/api/v1/obras/{escenario.obra_id}/drivers"
    # Costos propone el global (queda pendiente: no cambia nada); Control de obra lo autoriza.
    r = await costos.put("/api/v1/drivers/altura_estandar", json={"valor": "2.8"})
    assert r.status_code == 202, r.text
    assert (r.json()["valor_global"], r.json()["origen"], r.json()["editado"]) == ("3", "inicial", False)
    a = await _autorizar(control, r)
    assert (a["valor_global"], a["origen"], a["editado"]) == ("2.8", "global", True)
    # Control de obra ajusta la obra (nace autorizado, 200): el vigente es el de la obra; el global no cambia.
    r = await control.put(f"{obra}/altura_estandar", json={"valor": "2.6"})
    assert r.status_code == 200, r.text
    a = r.json()
    assert (a["valor_vigente"], a["valor_global"], a["valor_obra"], a["origen"]) == ("2.6", "2.8", "2.6", "obra")
    assert a["propuesta"]["estado"] == "autorizada" and a["propuesta"]["propuso_rol"] == "control_obra"
    # El residente lo ve de la obra y el global sin la obra.
    assert _drivers(await residente.get(obra))["altura_estandar"]["valor_vigente"] == "2.6"
    assert _drivers(await residente.get("/api/v1/drivers"))["altura_estandar"]["valor_vigente"] == "2.8"
    # Fijo: el ajuste de la obra deja de valer (pero queda guardado) y no se pueden crear más.
    a = await _autorizar(control, await costos.put("/api/v1/drivers/altura_estandar", json={"modo": "fijo"}))
    assert a["valor_global"] == "2.8" and a["modo"] == "fijo"
    a = _drivers(await costos.get(obra))["altura_estandar"]
    assert (a["valor_vigente"], a["origen"], a["ajuste_ignorado"], a["valor_obra"]) == ("2.8", "global", True, "2.6")
    assert (await costos.put(f"{obra}/altura_estandar", json={"valor": "2.7"})).status_code == 422
    # De vuelta a ajustable: el ajuste guardado vale otra vez. Quitarlo (se propone y se autoriza) devuelve la obra al global.
    await control.put("/api/v1/drivers/altura_estandar", json={"modo": "ajustable"})
    assert _drivers(await costos.get(obra))["altura_estandar"]["valor_vigente"] == "2.6"
    r = await costos.delete(f"{obra}/altura_estandar")
    assert r.status_code == 202 and r.json()["valor_obra"] == "2.6"  # sigue valiendo hasta que se autorice
    a = await _autorizar(control, r)
    assert (a["valor_vigente"], a["origen"], a["valor_obra"]) == ("2.8", "global", None)


async def test_lo_que_propone_costos_no_cambia_nada_hasta_que_control_de_obra_lo_autoriza(
    costos: httpx.AsyncClient, control: httpx.AsyncClient, residente: httpx.AsyncClient
) -> None:
    r = await costos.put("/api/v1/drivers/desperdicio_concreto", json={"valor": "8"})
    assert r.status_code == 202, r.text
    p = r.json()["propuesta"]
    assert (p["estado"], p["propuso_rol"], p["valor"], p["valor_anterior"], p["decidio_id"], p["decidido_en"]) == ("pendiente", "costos", "8", "5", None, None)
    d = _drivers(await residente.get("/api/v1/drivers"))["desperdicio_concreto"]
    assert d["valor_vigente"] == "5" and [x["id"] for x in d["propuestas_pendientes"]] == [p["id"]]
    # Solo Control de obra decide: ni Costos ni el residente.
    assert (await costos.post(f"/api/v1/drivers-propuestas/{p['id']}/autorizar")).status_code == 403
    assert (await residente.post(f"/api/v1/drivers-propuestas/{p['id']}/rechazar", json={})).status_code == 403
    # Una sola propuesta pendiente por driver.
    assert (await costos.put("/api/v1/drivers/desperdicio_concreto", json={"valor": "9"})).status_code == 422
    a = await control.post(f"/api/v1/drivers-propuestas/{p['id']}/autorizar")
    assert a.status_code == 200 and a.json()["valor_vigente"] == "8" and a.json()["propuestas_pendientes"] == []
    d = a.json()["propuesta"]
    assert (d["estado"], d["decidio_rol"], d["decidio_id"] is not None, d["decidido_en"] is not None) == ("autorizada", "control_obra", True, True)
    # Ya decidida: no se decide otra vez.
    assert (await control.post(f"/api/v1/drivers-propuestas/{p['id']}/autorizar")).status_code == 422
    # La bitácora de quién y cuándo: las más nuevas primero, filtrables.
    hist = (await residente.get("/api/v1/drivers-propuestas", params={"clave": "desperdicio_concreto"})).json()
    assert [(h["estado"], h["propuso_rol"], h["decidio_rol"]) for h in hist] == [("autorizada", "costos", "control_obra")]


async def test_control_de_obra_rechaza_con_motivo_y_el_driver_no_cambia(costos: httpx.AsyncClient, control: httpx.AsyncClient) -> None:
    r = await costos.put("/api/v1/drivers/tolerancia_corte_cm", json={"valor": "20"})
    pid = r.json()["propuesta"]["id"]
    rr = await control.post(f"/api/v1/drivers-propuestas/{pid}/rechazar", json={"motivo": "  Falta confirmar con el estructurista "})
    assert rr.status_code == 200, rr.text
    assert rr.json()["valor_vigente"] == "0" and rr.json()["propuesta"]["estado"] == "rechazada"
    assert rr.json()["propuesta"]["motivo"] == "Falta confirmar con el estructurista"
    # Rechazada, ya se puede proponer otra.
    assert (await costos.put("/api/v1/drivers/tolerancia_corte_cm", json={"valor": "10"})).status_code == 202
    pendientes = (await control.get("/api/v1/drivers-propuestas", params={"estado": "pendiente"})).json()
    assert [(p["clave"], p["valor"]) for p in pendientes] == [("tolerancia_corte_cm", "10")]


async def test_f4_el_escarpio_y_la_corona_siguen_fijos_aunque_los_proponga_control_de_obra(
    costos: httpx.AsyncClient, control: httpx.AsyncClient, escenario: Escenario, residente: httpx.AsyncClient
) -> None:
    d = _drivers(await residente.get("/api/v1/drivers"))
    assert d["escarpio_minimo"]["inmutable"] and d["corona_cimiento_cm"]["inmutable"] and not d["altura_estandar"]["inmutable"]
    for quien in (costos, control):
        for clave in ("escarpio_minimo", "corona_cimiento_cm"):
            for cuerpo in ({"modo": "ajustable"}, {"valor": "2"}, {"valor": "1.5", "modo": "fijo"}):
                r = await quien.put(f"/api/v1/drivers/{clave}", json=cuerpo)
                assert r.status_code == 422 and "no se cambia" in r.json()["detail"], (clave, cuerpo, r.text)
            assert (await quien.put(f"/api/v1/obras/{escenario.obra_id}/drivers/{clave}", json={"valor": "2"})).status_code == 422
    d = _drivers(await residente.get("/api/v1/drivers"))
    assert (d["escarpio_minimo"]["modo"], d["escarpio_minimo"]["valor_vigente"], d["corona_cimiento_cm"]["valor_vigente"]) == ("fijo", "1.5", "40")
    assert (await residente.get("/api/v1/drivers-propuestas")).json() == []


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


async def test_el_cambio_de_un_driver_queda_en_la_bitacora(costos: httpx.AsyncClient, control: httpx.AsyncClient, escenario: Escenario) -> None:
    async def renglones(entidad: str, accion: str) -> int:
        motor = create_async_engine(DATABASE_URL_ADMIN)
        try:
            async with motor.connect() as c:
                return int(
                    (
                        await c.execute(
                            text("select count(*) from bitacora where org_id = :o and entidad = :e and accion = :a"),
                            {"o": str(escenario.org_id), "e": entidad, "a": accion},
                        )
                    ).scalar_one()
                )
        finally:
            await motor.dispose()

    r = await costos.put("/api/v1/drivers/desperdicio_concreto", json={"valor": "7"})
    # Pendiente: queda la propuesta en la bitácora y todavía no hay valor de driver escrito.
    assert (await renglones("propuesta_de_driver", "insert"), await renglones("driver_valor", "insert")) == (1, 0)
    await _autorizar(control, r)
    assert (await renglones("propuesta_de_driver", "update"), await renglones("driver_valor", "insert")) == (1, 1)


# --- la altura estándar (Q1) ------------------------------------------------------------------------------------------


async def test_la_funcion_de_la_base_resuelve_como_el_dominio(costos: httpx.AsyncClient, control: httpx.AsyncClient, escenario: Escenario) -> None:
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
    assert await vigente() == Decimal("3")  # pendiente: nada cambió
    for propuesta in (await control.get("/api/v1/drivers-propuestas", params={"estado": "pendiente"})).json():
        assert (await control.post(f"/api/v1/drivers-propuestas/{propuesta['id']}/autorizar")).status_code == 200
    assert await vigente() == Decimal("2.9")
    await control.put(f"/api/v1/obras/{escenario.obra_id}/drivers/altura_estandar", json={"valor": "2.4"})
    assert await vigente() == Decimal("2.4")
    await control.put("/api/v1/drivers/altura_estandar", json={"modo": "fijo"})
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


# --- F5: el nivel del contexto es un campo explícito (0141) -------------------------------------------------------------------


async def test_f5_el_nivel_del_contexto_es_un_campo_explicito_y_no_el_orden(
    costos: httpx.AsyncClient, residente: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, Any]
) -> None:
    """El árbol de la prueba tiene niveles con orden 1 (planta baja) y 3 (azotea): un salto. Sin número explícito la azotea NO es el nivel 3."""
    ruta = f"/api/v1/obras/{escenario.obra_id}/enlaces-de-ranura"

    async def niveles() -> dict[str, tuple[int | None, int | None]]:
        return {n["clave"]: (n["numero_de_nivel"], n["numero_efectivo"]) for n in (await costos.get(ruta)).json()["niveles"]}

    assert await niveles() == {"NIV-1": (None, 1), "NIV-3": (None, None)}  # PB sigue siendo 1; con el salto, la azotea no se adivina
    r = await costos.put(f"/api/v1/niveles/{arbol['n_az']}/numero-de-nivel", json={"numero_de_nivel": 2})
    assert r.status_code == 200, r.text
    assert (r.json()["orden"], r.json()["numero_de_nivel"], r.json()["numero_efectivo"]) == (3, 2, 2)
    assert await niveles() == {"NIV-1": (None, 1), "NIV-3": (2, 2)}
    # Un número explícito gana sobre el orden aunque coincidan o no; quitarlo vuelve a la regla de arriba.
    assert (await costos.put(f"/api/v1/niveles/{arbol['n_pb']}/numero-de-nivel", json={"numero_de_nivel": 1})).status_code == 200
    r = await costos.put(f"/api/v1/niveles/{arbol['n_az']}/numero-de-nivel", json={"numero_de_nivel": None})
    assert r.status_code == 200 and r.json()["numero_efectivo"] is None
    # Lo que no vale, no existe o no es de quien lo pide.
    assert (await costos.put(f"/api/v1/niveles/{arbol['n_az']}/numero-de-nivel", json={"numero_de_nivel": 0})).status_code == 422
    assert (await costos.put(f"/api/v1/niveles/{uuid.uuid4()}/numero-de-nivel", json={"numero_de_nivel": 2})).status_code == 404
    assert (await residente.put(f"/api/v1/niveles/{arbol['n_az']}/numero-de-nivel", json={"numero_de_nivel": 2})).status_code == 403


async def test_f5_la_funcion_de_la_base_no_usa_el_orden_con_saltos(escenario: Escenario, arbol: dict[str, Any]) -> None:
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            await c.execute(text("select set_config('app.org_id', :o, true)"), {"o": str(escenario.org_id)})
            await c.execute(
                text("insert into nivel (org_id, clave, descripcion, orden) values (:o, 'NIV-2', 'Primer nivel', 2)"), {"o": str(escenario.org_id)}
            )
            r = (
                await c.execute(text("select clave, app.numero_de_nivel(id) from nivel where org_id = :o order by orden"), {"o": str(escenario.org_id)})
            ).all()
    finally:
        await motor.dispose()
    assert [(a, b) for a, b in r] == [("NIV-1", 1), ("NIV-2", 2), ("NIV-3", 3)]  # sin salto, el orden es el número
