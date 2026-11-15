"""Costos propone, Control de obra autoriza: versiones del elemento y de sus conceptos, «Confirmar cálculo → actualizar APU» y la
conciliación en las dos direcciones, por HTTP contra Postgres real (migración 0130; plan de elementos de muro, fase I)."""

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
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario

RUTA = "/api/v1/elementos-parametricos"

# (clave, descripción, unidad, familia, subfamilia, costo): datos reales de los catálogos de julio 2026.
INSUMOS = [
    ("ACE-00001", "ALAMBRE RECOCIDO", "kg", "Aceros", "Consumible", 24.68),
    ("ACE-00012", "CLAVO 2 1/2", "kg", "Aceros", "Consumible", 30.68),
    ("MEZ-01020", "CONCRETO H.O. F'C=150", "m3", "Mezclas", "Concretos", 1500.0),
    ("MEZ-01030", "CONCRETO H.O. F'C=200", "m3", "Mezclas", "Concretos", 1650.0),
    ("MAD-00004", "TABLAS", "pza", "Cimbra", None, 198.0),
]


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
async def catalogo(escenario: Escenario) -> dict[str, uuid.UUID]:
    org = str(escenario.org_id)
    ids: dict[str, uuid.UUID] = {}
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            unidades = {}
            for u in ("kg", "pza", "m3", "m2", "ml"):
                unidades[u] = (
                    await c.execute(
                        text("insert into unidad (org_id, clave, nombre, sinonimos) values (:o, :u, :u, '{}') returning id"), {"o": org, "u": u}
                    )
                ).scalar_one()
            familias: dict[tuple[str, str | None], uuid.UUID] = {}
            for _, _, _, fam, sub, _ in INSUMOS:
                if (fam, None) not in familias:
                    familias[(fam, None)] = (
                        await c.execute(text("insert into familia (org_id, clave, nombre) values (:o, :n, :n) returning id"), {"o": org, "n": fam})
                    ).scalar_one()
                if sub and (sub, fam) not in familias:
                    familias[(sub, fam)] = (
                        await c.execute(
                            text("insert into familia (org_id, parent_id, clave, nombre) values (:o, :p, :n, :n) returning id"),
                            {"o": org, "p": str(familias[(fam, None)]), "n": sub},
                        )
                    ).scalar_one()
            for clave, desc, unidad, fam, sub, costo in INSUMOS:
                ids[clave] = (
                    await c.execute(
                        text(
                            "insert into insumo (org_id, tipo, clave, descripcion, unidad_id, familia_id, costo_base) "
                            "values (:o, 'material', :k, :d, :u, :f, :c) returning id"
                        ),
                        {"o": org, "k": clave, "d": desc, "u": str(unidades[unidad]), "f": str(familias[(sub, fam)] if sub else familias[(fam, None)]), "c": costo},
                    )
                ).scalar_one()
    finally:
        await motor.dispose()
    return ids


async def _castillo(cliente: httpx.AsyncClient, clave: str = "K-1", **extra: object) -> httpx.Response:
    return await cliente.post(RUTA, json={"clave": clave, "nombre": f"Castillo {clave}", "tipo": "castillo", **extra})


async def _elemento(cliente: httpx.AsyncClient, clave: str) -> dict:
    return next(x for x in (await cliente.get(RUTA)).json() if x["clave"] == clave)


async def _autorizacion(cliente: httpx.AsyncClient, elemento_id: str) -> dict:
    r = await cliente.get(f"{RUTA}/{elemento_id}/autorizacion")
    assert r.status_code == 200, r.text
    return r.json()


# --- 1. El elemento nuevo --------------------------------------------------------------------------------------


async def test_el_elemento_de_control_nace_autorizado_y_el_de_costos_pendiente(control, costos, residente, catalogo) -> None:
    de_control = await _castillo(control, "K-1")
    assert de_control.status_code == 201 and de_control.json()["estado_autorizacion"] == "autorizado"
    k1 = de_control.json()["id"]
    h = await _autorizacion(control, k1)
    assert h["estado"] == "autorizado" and h["version"] == 1
    (v,) = h["versiones"]
    assert (v["clase"], v["estado"], v["version"], v["propuso_rol"], v["decidio_rol"]) == ("elemento", "autorizada", 1, "control_obra", "control_obra")
    assert v["decidido_en"] is not None and v["propuso_id"] == v["decidio_id"]

    de_costos = await _castillo(costos, "K-2", parametros={"alto": 3.0})
    assert de_costos.status_code == 201 and de_costos.json()["estado_autorizacion"] == "pendiente"
    k2 = de_costos.json()["id"]
    e2 = await _elemento(control, "K-2")
    assert (e2["estado_autorizacion"], e2["version_autorizada"]) == ("pendiente", 0)
    assert (await _autorizacion(control, k2))["version"] is None
    # Sigue usable como provisional: Costos puede afinar su propia propuesta sin pedir autorización.
    assert (await costos.patch(f"{RUTA}/{k2}", json={"parametros": {"alto": 3.1}})).status_code == 204
    assert (await residente.post(RUTA, json={"clave": "K-3", "nombre": "x", "tipo": "castillo"})).status_code == 403


async def test_control_autoriza_el_elemento_de_costos_y_nace_la_version_1(control, costos, catalogo) -> None:
    k2 = (await _castillo(costos, "K-2")).json()["id"]
    pendientes = (await control.get("/api/v1/autorizaciones-pendientes")).json()
    assert [(p["tipo"], p["elemento_clave"], p["clase"]) for p in pendientes] == [("elemento_nuevo", "K-2", "elemento")]
    # Costos no autoriza ni lo suyo.
    assert (await costos.post(f"{RUTA}/{k2}/autorizar")).status_code == 403
    r = await control.post(f"{RUTA}/{k2}/autorizar")
    assert r.status_code == 200 and r.json() == {"version": 1}
    h = await _autorizacion(control, k2)
    assert h["estado"] == "autorizado" and h["version"] == 1
    (v,) = h["versiones"]
    assert (v["propuso_rol"], v["decidio_rol"], v["propuso_nombre"], v["decidio_nombre"] is not None) == ("costos", "control_obra", "Costos", True)
    assert (await control.get("/api/v1/autorizaciones-pendientes")).json() == []
    again = await control.post(f"{RUTA}/{k2}/autorizar")
    assert again.status_code == 422 and "ya está autorizado" in again.json()["detail"]


# --- 2. Los cambios --------------------------------------------------------------------------------------------


async def test_costos_propone_el_cambio_y_control_lo_autoriza_con_su_version(control, costos, catalogo) -> None:
    k1 = (await _castillo(control, "K-1", parametros={"alto": 2.5})).json()["id"]
    r = await costos.patch(f"{RUTA}/{k1}", json={"nombre": "Castillo reforzado", "parametros": {"alto": 3.0}})
    assert r.status_code == 202, r.text
    propuesta = r.json()
    assert "Nombre: Castillo K-1 → Castillo reforzado" in propuesta["resumen"] and "Parámetro alto: 2.5 → 3.0" in propuesta["resumen"]
    # Mientras no se autoriza, el elemento sigue como estaba y Costos no tiene otra propuesta encima.
    e = await _elemento(control, "K-1")
    assert e["nombre"] == "Castillo K-1" and e["parametros"]["alto"] == 2.5 and e["revisiones_pendientes"] == 1
    otra = await costos.patch(f"{RUTA}/{k1}", json={"nombre": "Otro nombre"})
    assert otra.status_code == 422 and "propuesta pendiente" in otra.json()["detail"]
    # Un cambio que no se podría guardar ni se propone.
    mala = await costos.patch(f"{RUTA}/{k1}", json={"parametros": {"alto": -1}})
    assert mala.status_code == 422
    assert (await costos.post(f"/api/v1/revisiones-de-elementos/{propuesta['revision_id']}/autorizar")).status_code == 403
    ok = await control.post(f"/api/v1/revisiones-de-elementos/{propuesta['revision_id']}/autorizar")
    assert ok.status_code == 200 and ok.json() == {"version": 2}
    e = await _elemento(control, "K-1")
    assert e["nombre"] == "Castillo reforzado" and e["parametros"]["alto"] == 3.0
    assert (e["version_autorizada"], e["revisiones_pendientes"]) == (2, 0)
    h = await _autorizacion(control, k1)
    v2 = next(v for v in h["versiones"] if v["version"] == 2)
    assert (v2["propuso_rol"], v2["decidio_rol"], v2["estado"]) == ("costos", "control_obra", "autorizada")
    again = await control.post(f"/api/v1/revisiones-de-elementos/{propuesta['revision_id']}/autorizar")
    assert again.status_code == 422 and "ya fue decidida" in again.json()["detail"]


async def test_el_cambio_de_control_se_aplica_y_queda_como_version_y_un_rechazo_no_cambia_nada(control, costos, catalogo) -> None:
    k1 = (await _castillo(control, "K-1")).json()["id"]
    assert (await control.patch(f"{RUTA}/{k1}", json={"nombre": "Castillo de Control"})).status_code == 204
    h = await _autorizacion(control, k1)
    assert h["version"] == 2 and h["versiones"][0]["resumen"] == "Nombre: Castillo K-1 → Castillo de Control"
    assert h["versiones"][0]["propuso_rol"] == "control_obra"
    # Un cambio que no cambia nada no crea versión.
    assert (await control.patch(f"{RUTA}/{k1}", json={"nombre": "Castillo de Control"})).status_code == 204
    assert (await _autorizacion(control, k1))["version"] == 2
    propuesta = (await costos.patch(f"{RUTA}/{k1}", json={"nombre": "Otro"})).json()
    r = await control.post(f"/api/v1/revisiones-de-elementos/{propuesta['revision_id']}/rechazar", json={"motivo": "No es el armado que se acordó"})
    assert r.status_code == 204
    assert (await _elemento(control, "K-1"))["nombre"] == "Castillo de Control"
    h = await _autorizacion(control, k1)
    rechazada = next(v for v in h["versiones"] if v["estado"] == "rechazada")
    assert (rechazada["version"], rechazada["motivo"], rechazada["decidio_rol"]) == (None, "No es el armado que se acordó", "control_obra")
    assert h["version"] == 2
    # Tras el rechazo Costos puede volver a proponer.
    assert (await costos.patch(f"{RUTA}/{k1}", json={"nombre": "Otro más"})).status_code == 202


# --- 3. El concepto nuevo -------------------------------------------------------------------------------------


async def test_el_concepto_nuevo_no_cuenta_hasta_que_control_lo_autoriza_y_entra_sin_precio(control, costos, catalogo, escenario) -> None:
    k1 = (await _castillo(control, "K-1", materiales={"concreto": "MEZ-01020"})).json()["id"]
    alta = await costos.post(
        f"{RUTA}/{k1}/conceptos-por-contexto",
        json={"clave_propuesta": "EJ-420", "descripcion": "Castillo de entrepiso", "unidad": "ml", "toma": {"concreto": True}},
    )
    assert alta.status_code == 201, alta.text
    fila = alta.json()["id"]
    (c,) = (await control.get(f"{RUTA}/{k1}/conceptos-por-contexto")).json()["conceptos"]
    assert (c["estado"], c["version"], c["nuevo"]) == ("propuesto", None, True)
    # No existe en el catálogo, así que no cuenta en el presupuesto ni alimenta las tomas.
    assert (await control.get(f"{RUTA}/{k1}/conceptos")).json() == []
    pend = (await control.get("/api/v1/autorizaciones-pendientes")).json()
    assert [(p["tipo"], p["concepto_clave"]) for p in pend if p["tipo"] == "concepto_nuevo"] == [("concepto_nuevo", "EJ-420")]

    assert (await costos.post(f"{RUTA}/{k1}/conceptos-por-contexto/{fila}/autorizar")).status_code == 403
    # Sin APU no hay qué actualizar: primero se autoriza.
    sin = await control.post(f"{RUTA}/{k1}/conceptos-por-contexto/{fila}/apu/confirmar")
    assert sin.status_code == 422 and "concepto nuevo" in sin.json()["detail"]
    r = await control.post(f"{RUTA}/{k1}/conceptos-por-contexto/{fila}/autorizar")
    assert r.status_code == 200 and r.json() == {"version": 1}
    (c,) = (await control.get(f"{RUTA}/{k1}/conceptos-por-contexto")).json()["conceptos"]
    assert (c["estado"], c["version"], c["nuevo"]) == ("autorizado", 1, False)
    # Ahora sí está en el catálogo, sin precio ni versión de CPU: no se inventa ningún precio.
    motor = create_async_engine(DATABASE_URL_ADMIN)
    async with motor.begin() as conn:
        n = (await conn.execute(text("select count(*) from concepto where org_id = :o and clave = 'EJ-420'"), {"o": str(escenario.org_id)})).scalar_one()
        cpus = (await conn.execute(text("select count(*) from cpu where org_id = :o"), {"o": str(escenario.org_id)})).scalar_one()
    await motor.dispose()
    assert (n, cpus) == (1, 0)
    assert len((await control.get(f"{RUTA}/{k1}/conceptos")).json()) == 1
    h = await _autorizacion(control, k1)
    v = next(x for x in h["versiones"] if x["clase"] == "concepto")
    assert (v["concepto_clave"], v["version"], v["decidio_rol"], v["propuso_nombre"] is not None) == ("EJ-420", 1, "control_obra", True)
    assert "sin precio" in v["resumen"]
    again = await control.post(f"{RUTA}/{k1}/conceptos-por-contexto/{fila}/autorizar")
    assert again.status_code == 422 and "ya está autorizado" in again.json()["detail"]


# --- 4. «Confirmar cálculo → actualizar APU» y la conciliación --------------------------------------------------


async def _concepto_con_apu(escenario: Escenario, clave: str, filas: list[tuple[str, str, float]], *, con_cpu: bool) -> uuid.UUID:
    """Un concepto con su APU (insumo, categoría, cantidad). Con CPU, la composición va atada a su versión vigente."""
    org = str(escenario.org_id)
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            cid = (
                await c.execute(
                    text("insert into concepto (org_id, clave, descripcion) values (:o, :k, :d) returning id"),
                    {"o": org, "k": clave, "d": f"Concepto {clave}"},
                )
            ).scalar_one()
            cpu = None
            if con_cpu:
                cpu = (
                    await c.execute(
                        text("insert into cpu (org_id, concepto_id, version, precio_unitario, vigente) values (:o, :c, 1, 100, true) returning id"),
                        {"o": org, "c": str(cid)},
                    )
                ).scalar_one()
            for orden, (insumo, categoria, cantidad) in enumerate(filas):
                await c.execute(
                    text(
                        "insert into explosion (org_id, concepto_id, cpu_id, tipo_hijo, insumo_id, categoria, cantidad, orden) "
                        "values (:o, :c, cast(:p as uuid), 'insumo', (select id from insumo where org_id = :o and clave = :i), "
                        "cast(:g as categoria_explosion), :q, :n)"
                    ),
                    {"o": org, "c": str(cid), "p": str(cpu) if cpu else None, "i": insumo, "g": categoria, "q": cantidad, "n": orden},
                )
    finally:
        await motor.dispose()
    return uuid.UUID(str(cid))


APU = [("MEZ-01020", "material", 0.023625), ("ACE-00001", "material", 0.210987), ("ACE-00012", "material", 0.017021), ("MAD-00004", "material", 0.01)]
MATERIALES = {"concreto": "MEZ-01020", "alambre": "ACE-00001", "cimbra": {"ACE-00012": 0.0175}}


async def _k1_con_concepto(control, escenario, *, con_cpu: bool) -> tuple[str, str, uuid.UUID]:
    est = await _concepto_con_apu(escenario, "EST-02110", APU, con_cpu=con_cpu)
    k1 = (await _castillo(control, "K-1", parametros={"alto": 2.5}, materiales=MATERIALES)).json()["id"]
    alta = await control.post(
        f"{RUTA}/{k1}/conceptos-por-contexto", json={"concepto_id": str(est), "unidad": "ml", "toma": {"concreto": True, "cimbra": True, "alambre": True}}
    )
    assert alta.status_code == 201, alta.text
    return k1, alta.json()["id"], est


async def _apu_de(escenario: Escenario, concepto: uuid.UUID) -> dict:
    motor = create_async_engine(DATABASE_URL_ADMIN)
    async with motor.begin() as c:
        filas = (
            await c.execute(
                text(
                    "select i.clave, e.cantidad, e.cpu_id, cp.version, cp.vigente from explosion e join insumo i on i.id = e.insumo_id "
                    "left join cpu cp on cp.id = e.cpu_id where e.concepto_id = :c order by i.clave, cp.version nulls first"
                ),
                {"c": str(concepto)},
            )
        ).all()
        cpus = (await c.execute(text("select version, vigente, precio_unitario from cpu where concepto_id = :c order by version"), {"c": str(concepto)})).all()
    await motor.dispose()
    return {"filas": [(f[0], float(f[1]), f[3], f[4]) for f in filas], "cpus": [(v, vig, float(pu)) for v, vig, pu in cpus]}


async def test_el_plan_pone_el_apu_contra_el_calculo_del_elemento(control, costos, residente, catalogo, escenario) -> None:
    k1, fila, _ = await _k1_con_concepto(control, escenario, con_cpu=True)
    r = await control.get(f"{RUTA}/{k1}/conceptos-por-contexto/{fila}/apu")
    assert r.status_code == 200, r.text
    plan = r.json()
    assert plan["manda"] == "apu" and plan["hay_cambios"] and not plan["sin_catalogo"] and plan["propuesta_pendiente"] is None
    por = {f["clave"]: f for f in plan["filas"]}
    assert por["MEZ-01020"]["apu"] == pytest.approx(0.023625) and por["MEZ-01020"]["calculo"] == pytest.approx(0.0225)
    assert (por["MEZ-01020"]["accion"], por["MEZ-01020"]["marca"]) == ("actualizar", "≈")
    assert por["ACE-00012"]["calculo"] == pytest.approx(0.007) and por["ACE-00012"]["accion"] == "actualizar"
    assert por["MAD-00004"]["accion"] == "solo_apu"  # el APU trae las tablas y el elemento no las calcula: manda el APU
    assert plan["pu_vigente"] != plan["pu_con_el_calculo"] and plan["pu_con_el_calculo"] < plan["pu_vigente"]
    assert (await residente.get(f"{RUTA}/{k1}/conceptos-por-contexto/{fila}/apu")).status_code == 403
    assert (await control.get(f"{RUTA}/{k1}/conceptos-por-contexto/{uuid.uuid4()}/apu")).status_code == 404


async def test_costos_propone_actualizar_el_apu_y_control_lo_autoriza_con_version_nueva_del_cpu(control, costos, catalogo, escenario) -> None:
    k1, fila, est = await _k1_con_concepto(control, escenario, con_cpu=True)
    antes = await _apu_de(escenario, est)
    plan = (await control.get(f"{RUTA}/{k1}/conceptos-por-contexto/{fila}/apu")).json()
    r = await costos.post(f"{RUTA}/{k1}/conceptos-por-contexto/{fila}/apu/confirmar")
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["aplicado"] is False and p["version"] is None and "MEZ-01020 0.023625 → 0.0225" in p["resumen"]
    # El APU vigente rige mientras tanto: nada cambió.
    assert await _apu_de(escenario, est) == antes
    again = await costos.post(f"{RUTA}/{k1}/conceptos-por-contexto/{fila}/apu/confirmar")
    assert again.status_code == 422 and "propuesta pendiente" in again.json()["detail"]
    assert (await control.get(f"{RUTA}/{k1}/conceptos-por-contexto/{fila}/apu")).json()["propuesta_pendiente"] == p["revision_id"]
    (c,) = (await control.get(f"{RUTA}/{k1}/conceptos-por-contexto")).json()["conceptos"]
    assert c["con_propuesta"] is True and c["version"] == 1

    ok = await control.post(f"/api/v1/revisiones-de-elementos/{p['revision_id']}/autorizar")
    assert ok.status_code == 200 and ok.json() == {"version": 2}
    despues = await _apu_de(escenario, est)
    # Versión nueva del CPU con su propia composición; la anterior se conserva, retirada, con lo que decía.
    assert [(v, vig) for v, vig, _ in despues["cpus"]] == [(1, False), (2, True)]
    assert despues["cpus"][1][2] == pytest.approx(plan["pu_con_el_calculo"], abs=0.01)
    viejas = {k: q for k, q, v, _ in despues["filas"] if v == 1}
    nuevas = {k: q for k, q, v, _ in despues["filas"] if v == 2}
    assert viejas == {k: q for k, q, _, _ in antes["filas"]}
    assert nuevas["MEZ-01020"] == pytest.approx(0.0225) and nuevas["ACE-00012"] == pytest.approx(0.007)
    assert nuevas["MAD-00004"] == pytest.approx(0.01)  # lo que el elemento no calcula no se toca
    # El APU de ahora es el de la versión 2 y el cálculo ya coincide.
    assert (await control.get(f"{RUTA}/{k1}/conceptos-por-contexto/{fila}/apu")).json()["hay_cambios"] is False
    h = await _autorizacion(control, k1)
    v = next(x for x in h["versiones"] if x["clase"] == "apu")
    assert (v["version"], v["propuso_rol"], v["decidio_rol"], v["concepto_clave"]) == (2, "costos", "control_obra", "EST-02110")
    (c,) = (await control.get(f"{RUTA}/{k1}/conceptos-por-contexto")).json()["conceptos"]
    assert (c["version"], c["con_propuesta"]) == (2, False)
    nada = await control.post(f"{RUTA}/{k1}/conceptos-por-contexto/{fila}/apu/confirmar")
    assert nada.status_code == 422 and "ya coincide" in nada.json()["detail"]


async def test_control_actualiza_el_apu_al_momento_sobre_la_composicion_viva(control, catalogo, escenario) -> None:
    k1, fila, est = await _k1_con_concepto(control, escenario, con_cpu=False)
    r = await control.post(f"{RUTA}/{k1}/conceptos-por-contexto/{fila}/apu/confirmar")
    assert r.status_code == 200, r.text
    assert r.json()["aplicado"] is True and r.json()["version"] == 2 and r.json()["pu_despues"] < r.json()["pu_antes"]
    despues = await _apu_de(escenario, est)
    por = {k: q for k, q, _, _ in despues["filas"]}
    assert por["MEZ-01020"] == pytest.approx(0.0225) and por["ACE-00012"] == pytest.approx(0.007) and por["MAD-00004"] == pytest.approx(0.01)
    # Sin CPU previo se publica la primera versión con el precio resultante.
    assert [(v, vig) for v, vig, _ in despues["cpus"]] == [(1, True)]
    # La composición viva se cambió en sitio (no hay filas duplicadas).
    assert len(despues["filas"]) == len(APU)


async def test_un_insumo_que_el_apu_no_trae_se_agrega_con_su_costo_de_la_base(control, catalogo, escenario) -> None:
    est = await _concepto_con_apu(escenario, "EST-02110", [("ACE-00001", "material", 0.2)], con_cpu=True)
    k1 = (await _castillo(control, "K-1", parametros={"alto": 2.5}, materiales={"concreto": "MEZ-01030", "alambre": "ACE-00001"})).json()["id"]
    fila = (
        await control.post(f"{RUTA}/{k1}/conceptos-por-contexto", json={"concepto_id": str(est), "unidad": "ml", "toma": {"concreto": True, "alambre": True}})
    ).json()["id"]
    plan = (await control.get(f"{RUTA}/{k1}/conceptos-por-contexto/{fila}/apu")).json()
    assert {f["clave"]: f["accion"] for f in plan["filas"]}["MEZ-01030"] == "agregar"
    assert (await control.post(f"{RUTA}/{k1}/conceptos-por-contexto/{fila}/apu/confirmar")).status_code == 200
    nuevas = {k: q for k, q, v, _ in (await _apu_de(escenario, est))["filas"] if v == 2}
    assert nuevas["MEZ-01030"] == pytest.approx(0.0225)
    assert (await control.get(f"{RUTA}/{k1}/conceptos-por-contexto/{fila}/apu")).json()["hay_cambios"] is False


async def test_la_conciliacion_va_en_las_dos_direcciones_y_manda_el_apu(control, costos, residente, catalogo, escenario) -> None:
    k1, fila, _ = await _k1_con_concepto(control, escenario, con_cpu=True)
    r = await control.get(f"{RUTA}/{k1}/conceptos-por-contexto/{fila}/conciliacion", params={"cantidad": 100})
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["manda"] == "apu" and c["cantidad"] == 100 and c["tolerancia_pct"] == pytest.approx(3.0)
    por = {f["clave"]: f for f in c["filas"]}
    # Concreto: 100 ml × 0.023625 de APU contra 100 ml × 0.0225 de salida: el estimado difiere de la salida (aviso, no bloqueo).
    mez = por["MEZ-01020"]
    assert mez["estimado"] == pytest.approx(2.3625) and mez["salida"] == pytest.approx(2.25)
    assert mez["sentido"] == "difieren" and mez["avisa"] is True
    assert mez["importe_apu"] == pytest.approx(2.3625 * 1500) and mez["diferencia_importe"] == pytest.approx((2.25 - 2.3625) * 1500)
    # Lo estimado por APU que la salida del elemento no calcula (tablas) y viceversa se listan aparte.
    assert por["MAD-00004"]["sentido"] == "estimado_sin_salida" and por["MAD-00004"]["salida"] is None
    assert c["resumen"]["estimado_sin_salida"] == 1 and c["sin_precio"] is False
    # Tras confirmar el cálculo, las dos direcciones se justifican.
    assert (await control.post(f"{RUTA}/{k1}/conceptos-por-contexto/{fila}/apu/confirmar")).status_code == 200
    c2 = (await control.get(f"{RUTA}/{k1}/conceptos-por-contexto/{fila}/conciliacion", params={"cantidad": 100})).json()
    assert {f["clave"]: f["sentido"] for f in c2["filas"]} == {
        "MEZ-01020": "se_justifican", "ACE-00001": "se_justifican", "ACE-00012": "se_justifican", "MAD-00004": "estimado_sin_salida",
    }
    assert (await control.get(f"{RUTA}/{k1}/conceptos-por-contexto/{fila}/conciliacion", params={"cantidad": 0})).status_code == 422
    assert (await residente.get(f"{RUTA}/{k1}/conceptos-por-contexto/{fila}/conciliacion")).status_code == 403


# --- 5. La versión de la receta (0120) no corta el historial -----------------------------------------------------


async def test_el_historial_sobrevive_a_la_version_nueva_de_la_receta(control, catalogo, escenario) -> None:
    from tests.integracion.test_elementos_parametricos_endtoend import _plano_con_trazos

    est = await _concepto_con_apu(escenario, "EST-02110", APU, con_cpu=True)
    k1 = (await _castillo(control, "K-V", parametros={"alto": 2.5}, materiales=MATERIALES)).json()["id"]
    fila = (await control.post(f"{RUTA}/{k1}/conceptos-por-contexto", json={"concepto_id": str(est), "unidad": "ml", "toma": {"concreto": True}})).json()["id"]
    _plano, ids = await _plano_con_trazos(control, escenario)
    await control.put(f"/api/v1/trazos/{ids['punto']}/elemento-parametrico", json={"elemento_id": k1})
    motor = create_async_engine(DATABASE_URL_ADMIN)
    async with motor.begin() as c:
        await c.execute(
            text("insert into parte_estado (org_id, obra_id, clave, estado) values (:o, :ob, 'sin_etapa', 'asignada')"),
            {"o": str(escenario.org_id), "ob": str(escenario.obra_id)},
        )
    await motor.dispose()
    # Con la obra asignada, cambiar la receta crea otra fila del elemento (D-639): el historial la sigue.
    assert (await control.patch(f"{RUTA}/{k1}", json={"parametros": {"alto": 3.0}})).status_code == 204
    nuevo = await _elemento(control, "K-V")
    assert nuevo["id"] != k1 and nuevo["version"] == 2 and nuevo["version_autorizada"] == 2
    h = await _autorizacion(control, nuevo["id"])
    assert h["version"] == 2 and [v["version"] for v in h["versiones"] if v["clase"] == "elemento"] == [2, 1]
    # El concepto copiado conserva su versión 1 y se puede seguir actualizando su APU.
    (c,) = (await control.get(f"{RUTA}/{nuevo['id']}/conceptos-por-contexto")).json()["conceptos"]
    assert c["version"] == 1 and c["id"] != fila
