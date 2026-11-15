"""Las propuestas de versión de concepto de los castillos, aparentes y forjadas y su conciliación con el catálogo, por HTTP contra
Postgres real (migración 0131; Ola 3, lane 3A). Costos o Control de obra proponen; solo Control de obra autoriza."""

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

RUTA = "/api/v1/biblioteca-de-elementos/estructura"
PROPUESTAS = "/api/v1/propuestas-de-estructura"

# Datos del catálogo de julio 2026 (opus): clave, descripción, unidad.
INSUMOS = [
    ("ACE-00020", "Armex 10x15", "pza"),
    ("ACE-00001", "ALAMBRE RECOCIDO", "kg"),
    ("MEZ-01020", "CONCRETO H.O. F'C=150 KG/CM2", "m3"),
    ("ACE-00012", "CLAVO 2 1/2", "kg"),
    ("ACE-00013", "CLAVO 4", "kg"),
    ("MAD-00004", "TABLAS (se les da 10 pza por lote)", "pza"),
    ("MEZ-07010", "MEZCLA CEMENTO-ARENA 1:4", "m3"),
    ("MAD-00030", "TUINO CHAFLAN", "pza"),
]
EST_10071 = [("ACE-00020", "material", 0.833333), ("ACE-00001", "material", 0.032945)]
BAP_03020 = [
    ("ACE-00001", "material", 0.3), ("ACE-00020", "material", 0.175), ("ACE-00012", "material", 0.025532),
    ("ACE-00013", "material", 0.02), ("MAD-00030", "material", 0.128205), ("MEZ-01020", "material", 0.0525),
    ("MEZ-07010", "material", 0.0021), ("MAD-00004", "material", 0.01),
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


async def _catalogo(escenario: Escenario) -> None:
    """Los insumos y dos conceptos con su APU (EST-10071 y BAP-03020), como están en el catálogo."""
    org = str(escenario.org_id)
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            unidades = {}
            for u in ("kg", "pza", "m3", "m", "m2"):
                unidades[u] = (
                    await c.execute(
                        text("insert into unidad (org_id, clave, nombre, sinonimos) values (:o, :u, :u, '{}') returning id"), {"o": org, "u": u}
                    )
                ).scalar_one()
            fam = (await c.execute(text("insert into familia (org_id, clave, nombre) values (:o, 'Varios', 'Varios') returning id"), {"o": org})).scalar_one()
            for clave, desc, unidad in INSUMOS:
                await c.execute(
                    text(
                        "insert into insumo (org_id, tipo, clave, descripcion, unidad_id, familia_id, costo_base) "
                        "values (:o, 'material', :k, :d, :u, :f, 10)"
                    ),
                    {"o": org, "k": clave, "d": desc, "u": str(unidades[unidad]), "f": str(fam)},
                )
            for clave, filas in (("EST-10071", EST_10071), ("BAP-03020", BAP_03020)):
                cid = (
                    await c.execute(
                        text("insert into concepto (org_id, clave, descripcion) values (:o, :k, :d) returning id"),
                        {"o": org, "k": clave, "d": f"Concepto {clave}"},
                    )
                ).scalar_one()
                for orden, (insumo, categoria, cantidad) in enumerate(filas):
                    await c.execute(
                        text(
                            "insert into explosion (org_id, concepto_id, tipo_hijo, insumo_id, categoria, cantidad, orden) "
                            "values (:o, :c, 'insumo', (select id from insumo where org_id = :o and clave = :i), "
                            "cast(:g as categoria_explosion), :q, :n)"
                        ),
                        {"o": org, "c": str(cid), "i": insumo, "g": categoria, "q": cantidad, "n": orden},
                    )
    finally:
        await motor.dispose()


# --- Conciliación -----------------------------------------------------------------------------------------------------------


async def test_la_conciliacion_compara_con_la_composicion_real_y_marca_lo_que_solo_trae_el_catalogo(control, escenario) -> None:
    await _catalogo(escenario)
    r = await control.get(f"{RUTA}/BAP-03020/conciliacion")
    assert r.status_code == 200, r.text
    (bloque,) = r.json()["conceptos"]
    assert bloque["en_catalogo"] is True and bloque["sin_catalogo"] is False
    filas = {f["clave"]: f for f in bloque["filas"]}
    assert filas["MEZ-01020"]["marca"] == "=" and filas["MEZ-01020"]["catalogo"] == pytest.approx(0.0525)
    assert filas["MEZ-07010"]["marca"] == "solo_catalogo" and "Q82" in filas["MEZ-07010"]["motivo"]
    assert filas["ACE-00020"]["marca"] == "≠"
    assert filas["MEZ-07010"]["descripcion"] == "MEZCLA CEMENTO-ARENA 1:4"


async def test_un_concepto_que_el_catalogo_no_tiene_se_ve_sin_composicion(control, escenario) -> None:
    await _catalogo(escenario)
    r = await control.get(f"{RUTA}/EST-02180/conciliacion")
    bloques = {b["concepto_clave"]: b for b in r.json()["conceptos"]}
    assert bloques["EJ-780"]["nuevo"] is True and bloques["EJ-780"]["en_catalogo"] is False
    assert bloques["EST-10081"]["en_catalogo"] is False and bloques["EST-10081"]["sin_catalogo"] is True
    assert (await control.get(f"{RUTA}/K-99/conciliacion")).status_code == 404


# --- Propuestas -------------------------------------------------------------------------------------------------------------


async def test_costos_propone_las_correcciones_y_control_las_autoriza_con_su_numero_de_version(control, costos, residente, escenario) -> None:
    await _catalogo(escenario)
    assert (await residente.post(f"{RUTA}/EST-02170/propuestas/correcciones")).status_code == 403
    creadas = await costos.post(f"{RUTA}/EST-02170/propuestas/correcciones")
    assert creadas.status_code == 201, creadas.text
    assert len(creadas.json()["creadas"]) == 3  # el armex de EST-10070, 10071 y 10072
    # Es idempotente: lo ya propuesto no se vuelve a proponer.
    otra = await costos.post(f"{RUTA}/EST-02170/propuestas/correcciones")
    assert otra.json()["creadas"] == [] and sorted(otra.json()["omitidas"]) == ["EST-10070", "EST-10071", "EST-10072"]

    p = next(x for x in (await costos.get(f"{RUTA}/EST-02170/propuestas")).json() if x["concepto_clave"] == "EST-10071")
    assert (p["estado"], p["version"], p["clase"], p["concepto_clave"]) == ("pendiente", None, "version_de_concepto", "EST-10071")
    assert p["cambios"] == [{"insumo": "ACE-00020", "unidad": "pza", "antes": 0.833333, "despues": pytest.approx(4 / 3, abs=1e-6)}]
    assert p["propuso_rol"] == "costos" and p["motivos"]

    # La conciliación muestra la versión propuesta junto al catálogo vigente (que no cambió).
    c = await costos.get(f"{RUTA}/EST-02170/conciliacion")
    fila = next(f for b in c.json()["conceptos"] if b["concepto_clave"] == "EST-10071" for f in b["filas"] if f["clave"] == "ACE-00020")
    assert fila["catalogo"] == pytest.approx(0.833333)
    assert fila["propuesta"]["valor"] == pytest.approx(4 / 3, abs=1e-6) and fila["propuesta"]["estado"] == "pendiente"

    pendientes = (await control.get(f"{PROPUESTAS}/pendientes")).json()
    assert sorted(x["concepto_clave"] for x in pendientes) == ["EST-10070", "EST-10071", "EST-10072"]
    assert (await costos.post(f"{PROPUESTAS}/{p['id']}/autorizar")).status_code == 403
    ok = await control.post(f"{PROPUESTAS}/{p['id']}/autorizar")
    assert ok.status_code == 200 and ok.json() == {"version": 2}
    v = next(x for x in (await control.get(f"{RUTA}/EST-02170/propuestas")).json() if x["id"] == p["id"])
    assert (v["estado"], v["version"], v["decidio_rol"]) == ("autorizada", 2, "control_obra")
    assert (await control.post(f"{PROPUESTAS}/{p['id']}/autorizar")).status_code == 422
    # El catálogo no se tocó: el APU del concepto sigue como estaba.
    motor = create_async_engine(DATABASE_URL_ADMIN)
    async with motor.begin() as conn:
        q = (
            await conn.execute(
                text(
                    "select e.cantidad from explosion e join concepto c on c.id = e.concepto_id join insumo i on i.id = e.insumo_id "
                    "where c.org_id = :o and c.clave = 'EST-10071' and i.clave = 'ACE-00020'"
                ),
                {"o": str(escenario.org_id)},
            )
        ).scalar_one()
    await motor.dispose()
    assert float(q) == pytest.approx(0.833333)


async def test_lo_que_propone_control_de_obra_nace_autorizado(control, escenario) -> None:
    r = await control.post(f"{RUTA}/BAP-03010/propuestas/correcciones")
    assert r.status_code == 201
    (p,) = (await control.get(f"{RUTA}/BAP-03010/propuestas")).json()
    assert (p["estado"], p["version"], p["propuso_rol"], p["decidio_rol"]) == ("autorizada", 2, "control_obra", "control_obra")
    assert p["destajo_por_definir"].startswith("MOE-02202")
    assert [(c["insumo"], c["antes"], c["despues"]) for c in p["cambios"]] == [("MEZ-01020", 0.0525, 0.0315)]
    # Con una versión autorizada el concepto ya no se vuelve a proponer, y la siguiente sería la 3.
    assert (await control.post(f"{RUTA}/BAP-03010/propuestas/correcciones")).json()["omitidas"] == ["BAP-03010"]


async def test_un_rechazo_lleva_su_motivo_y_deja_proponer_de_nuevo(control, costos, escenario) -> None:
    await costos.post(f"{RUTA}/EST-02170/propuestas/correcciones")
    p = next(x for x in (await costos.get(f"{RUTA}/EST-02170/propuestas")).json() if x["concepto_clave"] == "EST-10071")
    assert (await costos.post(f"{PROPUESTAS}/{p['id']}/rechazar", json={"motivo": "x"})).status_code == 403
    assert (await control.post(f"{PROPUESTAS}/{p['id']}/rechazar", json={"motivo": "  Falta confirmar  con el estructurista "})).status_code == 204
    r = next(x for x in (await control.get(f"{RUTA}/EST-02170/propuestas")).json() if x["id"] == p["id"])
    assert (r["estado"], r["version"], r["motivo"]) == ("rechazada", None, "Falta confirmar con el estructurista")
    assert (await control.post(f"{PROPUESTAS}/{p['id']}/rechazar", json={})).status_code == 422
    nueva = await costos.post(f"{RUTA}/EST-02170/propuestas/correcciones")
    assert len(nueva.json()["creadas"]) == 1


async def test_el_concepto_nuevo_de_una_forjada_con_otra_altura_nace_pendiente_y_sin_precio(control, costos, escenario) -> None:
    assert (await costos.post(f"{RUTA}/EST-07010/propuestas/concepto-por-altura", json={"alto_m": 4.2})).status_code == 422
    r = await costos.post(f"{RUTA}/EST-07010/propuestas/concepto-por-altura", json={"alto_m": 3.8})
    assert r.status_code == 201, r.text
    assert (await costos.post(f"{RUTA}/EST-07010/propuestas/concepto-por-altura", json={"alto_m": 3.8})).status_code == 422
    (p,) = (await costos.get(f"{RUTA}/EST-07010/propuestas")).json()
    assert (p["concepto_clave"], p["clase"], p["estado"]) == ("EST-07010-H380", "concepto_nuevo", "pendiente")
    assert (await control.post(f"{PROPUESTAS}/{p['id']}/autorizar")).json() == {"version": 1}
    # No crea ningún concepto en el catálogo ni precio alguno: autorizar registra la versión de la propuesta.
    motor = create_async_engine(DATABASE_URL_ADMIN)
    async with motor.begin() as conn:
        n = (await conn.execute(text("select count(*) from concepto where org_id = :o"), {"o": str(escenario.org_id)})).scalar_one()
    await motor.dispose()
    assert n == 0


async def test_las_propuestas_son_de_la_organizacion(control, escenario) -> None:
    await control.post(f"{RUTA}/EST-02170/propuestas/correcciones")
    otra = uuid.uuid4()
    motor = create_async_engine(DATABASE_URL_ADMIN)
    async with motor.begin() as c:
        await c.execute(text("insert into organizacion (id, nombre, slug) values (:i, 'Otra', :s)"), {"i": str(otra), "s": f"otra-{otra.hex[:8]}"})
        u = uuid.uuid4()
        await c.execute(
            text("insert into usuario (id, org_id, nombre, email, rol) values (:i, :o, 'Ctl', :e, 'control_obra')"),
            {"i": str(u), "o": str(otra), "e": f"c-{u.hex[:8]}@o.mx"},
        )
    try:
        async with _cliente(ContextoSesion(org_id=otra, usuario_id=u, rol="control_obra")) as ajeno:
            assert (await ajeno.get(f"{RUTA}/EST-02170/propuestas")).json() == []
            assert (await ajeno.get(f"{PROPUESTAS}/pendientes")).json() == []
    finally:
        async with motor.begin() as c:
            await c.execute(text("delete from organizacion where id = :i"), {"i": str(otra)})
        await motor.dispose()
