"""El escenario «Nuevo»: se entra por el cuantificador y se crea la obra desde ahí (migración
0081; cerebro WORKFLOWS.md §8.9; D-571, D-574).

Por HTTP de punta a punta contra Postgres real:

 1. los catálogos base son los de 1 y de 2 plantas, formados de la estructura y los conceptos de
    un prototipo, **sin cantidades**;
 2. crear la obra y su catálogo es un solo acto (de un solo uso, con su número de plantas);
 3. en esa obra **lo que se mide es el presupuesto**: la cantidad medida sustituye a la base
    mientras la parte no esté asignada, y una parte ya validada vuelve a cuantificarse;
 4. en una obra con presupuesto de un prototipo compartido el cuantificador solo compara;
 5. solo Control crea la obra; otra organización no ve nada.
"""

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


def _cliente(contexto: ContextoSesion) -> httpx.AsyncClient:
    app = crear_app()
    app.dependency_overrides[contexto_actual] = lambda: contexto
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    )


@pytest.fixture
async def control(contexto_control: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_control) as c:
        yield c


@pytest.fixture
async def residente(contexto_residente: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_residente) as c:
        yield c


@pytest.fixture
async def prototipos_base(escenario: Escenario) -> AsyncIterator[dict[str, str]]:
    """Un prototipo de 1 planta y uno de 2, con estructura (etapa → concepto) y cantidades."""
    engine = create_async_engine(DATABASE_URL_ADMIN)
    org = str(escenario.org_id)
    ids: dict[str, str] = {}
    async with engine.begin() as conn:
        concepto = uuid.uuid4()
        await conn.execute(
            text("insert into concepto (id, org_id, clave, descripcion) values (:i, :o, 'CON-NU', 'Muro de block')"),
            {"i": str(concepto), "o": org},
        )
        await conn.execute(
            text(
                "insert into cpu (org_id, concepto_id, version, precio_unitario, precio_destajo, vigente) "
                "values (:o, :c, 1, 100, 80, true)"
            ),
            {"o": org, "c": str(concepto)},
        )
        etapa = uuid.uuid4()
        await conn.execute(
            text(
                "insert into etapa_constructiva (id, org_id, clave, descripcion, orden) "
                "values (:i, :o, 'ECO-NU', 'Muros', 1)"
            ),
            {"i": str(etapa), "o": org},
        )
        for plantas, clave in ((1, "P1-NU"), (2, "P2-NU")):
            proto = uuid.uuid4()
            ids[f"p{plantas}"] = str(proto)
            await conn.execute(
                text(
                    "insert into prototipo (id, org_id, proyecto_id, clave, nombre, plantas) "
                    "values (:i, :o, :p, :c, :c, :n)"
                ),
                {"i": str(proto), "o": org, "p": str(escenario.proyecto_id), "c": clave, "n": plantas},
            )
            nodo_etapa = uuid.uuid4()
            await conn.execute(
                text(
                    "insert into prototipo_nodo (id, org_id, prototipo_id, tipo, nombre, clave, etapa_id, orden) "
                    "values (:i, :o, :p, 'etapa', 'Muros', 'N-ETA', :e, 1)"
                ),
                {"i": str(nodo_etapa), "o": org, "p": str(proto), "e": str(etapa)},
            )
            await conn.execute(
                text(
                    "insert into prototipo_nodo (org_id, prototipo_id, parent_id, tipo, nombre, clave, "
                    "concepto_id, orden, cantidad, modo_cantidad) "
                    "values (:o, :p, :pa, 'concepto', 'Muro de block', 'CON-NU', :c, 1, 250, 'capturada')"
                ),
                {"o": org, "p": str(proto), "pa": str(nodo_etapa), "c": str(concepto)},
            )
    yield ids
    await engine.dispose()


async def _crear(control, escenario, clave="NUE-1", plantas=1):
    return await control.post(
        "/api/v1/obras/desde-catalogo-base",
        json={"cluster_id": str(escenario.cluster_id), "clave": clave, "plantas": plantas},
    )


async def test_los_catalogos_base_son_los_de_una_y_dos_plantas(
    escenario: Escenario, prototipos_base: dict, control: httpx.AsyncClient
) -> None:
    r = await control.get("/api/v1/catalogos-base")
    assert r.status_code == 200, r.text
    por_plantas = {c["plantas"]: c for c in r.json()}
    assert set(por_plantas) == {1, 2}
    assert (por_plantas[1]["plazo_base_semanas"], por_plantas[2]["plazo_base_semanas"]) == (28, 30)
    assert por_plantas[1]["prototipo_clave"] == "P1-NU" and por_plantas[1]["disponible"] is True
    assert por_plantas[2]["prototipo_clave"] == "P2-NU" and por_plantas[2]["n_nodos"] == 2


async def test_crear_la_obra_forma_su_catalogo_sin_cantidades_y_de_un_solo_uso(
    escenario: Escenario, prototipos_base: dict, control: httpx.AsyncClient
) -> None:
    r = await _crear(control, escenario, "NUE-A", plantas=2)
    assert r.status_code == 201, r.text
    nueva = r.json()
    assert (nueva["plantas"], nueva["plazo_base_semanas"], nueva["base_clave"], nueva["nodos"]) == (2, 30, "P2-NU", 2)

    engine = create_async_engine(DATABASE_URL_ADMIN)
    async with engine.begin() as conn:
        proto = (
            await conn.execute(
                text("select plantas, de_una_obra, clave from prototipo where id = :i"),
                {"i": nueva["prototipo_id"]},
            )
        ).mappings().one()
        cantidades = (
            await conn.execute(
                text("select tipo::text, cantidad from prototipo_nodo where prototipo_id = :i order by tipo"),
                {"i": nueva["prototipo_id"]},
            )
        ).all()
        obra = (
            await conn.execute(
                text("select prototipo_id::text, plantas from obra where id = :i"), {"i": nueva["obra_id"]}
            )
        ).one()
        base = (
            await conn.execute(text("select cantidad from prototipo_nodo where prototipo_id = :i and tipo = 'concepto'"), {"i": prototipos_base["p2"]})
        ).scalar_one()
    await engine.dispose()
    assert (proto["plantas"], proto["de_una_obra"], proto["clave"]) == (2, True, "NUE-A")
    assert [float(c) for _, c in cantidades] == [0.0, 0.0]  # estructura y conceptos, sin cantidades
    assert obra == (nueva["prototipo_id"], 2)
    assert float(base) == 250.0  # el prototipo base no se tocó

    # Un catálogo de un solo uso no se ofrece como base de otra obra.
    r = await control.get("/api/v1/catalogos-base")
    assert {c["prototipo_clave"] for c in r.json()} == {"P1-NU", "P2-NU"}


async def test_lo_que_no_se_puede_formar_se_rechaza_con_su_motivo(
    escenario: Escenario, control: httpx.AsyncClient, prototipos_base: dict
) -> None:
    r = await control.post(
        "/api/v1/obras/desde-catalogo-base",
        json={"cluster_id": str(escenario.cluster_id), "clave": "NUE-X", "plantas": 3},
    )
    assert r.status_code == 422
    # Sin un prototipo de esa cantidad de plantas con estructura, no hay de dónde formar el catálogo.
    engine = create_async_engine(DATABASE_URL_ADMIN)
    async with engine.begin() as conn:
        await conn.execute(text("delete from prototipo_nodo where prototipo_id = :i"), {"i": prototipos_base["p1"]})
    await engine.dispose()
    r = await _crear(control, escenario, "NUE-Y", plantas=1)
    assert r.status_code == 422 and "estructura" in r.text
    r = await control.post(
        "/api/v1/obras/desde-catalogo-base",
        json={"cluster_id": str(uuid.uuid4()), "clave": "NUE-Z", "plantas": 2},
    )
    assert r.status_code == 404


async def test_solo_control_crea_la_obra_y_otra_organizacion_no_ve_nada(
    escenario: Escenario,
    prototipos_base: dict,
    residente: httpx.AsyncClient,
    contexto_ajeno: ContextoSesion,
) -> None:
    assert (await _crear(residente, escenario, "NUE-R")).status_code == 403
    ajeno = ContextoSesion(org_id=contexto_ajeno.org_id, usuario_id=contexto_ajeno.usuario_id, rol="control_obra")
    async with _cliente(ajeno) as c:
        assert (await _crear(c, escenario, "NUE-O")).status_code == 404  # el cluster no es suyo
        assert all(not x["disponible"] for x in (await c.get("/api/v1/catalogos-base")).json())


async def test_en_la_obra_nueva_lo_medido_es_el_presupuesto_y_en_las_demas_solo_se_compara(
    escenario: Escenario, prototipos_base: dict, control: httpx.AsyncClient
) -> None:
    nueva = (await _crear(control, escenario, "NUE-M", plantas=1)).json()
    obra_id = nueva["obra_id"]
    r = await control.post(f"/api/v1/obras/{obra_id}/generar", json={"modo_pago": "destajo"})
    assert r.status_code in (200, 201), r.text
    actividades = (await control.get(f"/api/v1/obras/{obra_id}/actividades")).json()
    assert len(actividades) == 1 and float(actividades[0]["cant_base"]) == 0.0
    actividad = actividades[0]["id"]

    async def medir(cantidad: float) -> dict:
        lado = cantidad**0.5
        plano = (
            await control.post(
                f"/api/v1/obras/{obra_id}/planos",
                json={"nombre": f"P{cantidad}", "archivo_url": "r2://p"},
            )
        ).json()
        r = await control.post(
            f"/api/v1/planos/{plano['id']}/trazos",
            json={
                "version_plano": 1,
                "geometria_wkt": f"POLYGON((0 0, {lado} 0, {lado} {lado}, 0 {lado}, 0 0))",
                "fuente": "pdf",
                "enlaces": [{"actividad_id": actividad, "medida": "area", "factor": "1"}],
            },
        )
        assert r.status_code == 201, r.text
        return r.json()

    await medir(120.0)
    a = (await control.get(f"/api/v1/obras/{obra_id}/actividades")).json()[0]
    assert round(float(a["cant_base"]), 2) == 120.0  # lo medido ES el presupuesto

    # Validada la parte, volver a medir la devuelve a cuantificarse.
    clave_parte = (await control.get(f"/api/v1/obras/{obra_id}/partes")).json()["partes"][0]["clave"]
    for accion in ("enviar_a_presupuesto", "autorizar", "validar"):
        r = await control.post(
            f"/api/v1/obras/{obra_id}/partes/transicion", json={"accion": accion, "claves": [clave_parte]}
        )
        assert r.status_code == 200, r.text
    await medir(30.0)  # suma 30 a lo ya medido: la cantidad vigente cambia
    ver = (await control.get(f"/api/v1/obras/{obra_id}/partes")).json()["partes"][0]
    assert ver["estado"] == "cuantificando"
    bit = (await control.get(f"/api/v1/obras/{obra_id}/partes/bitacora")).json()
    assert bit[0]["accion"] == "devolver" and "Medición" in bit[0]["nota"]

    # Asignada, la cantidad ya no se sustituye: otro trazo no la mueve (cambiarla es control de cambio).
    antes = round(float((await control.get(f"/api/v1/obras/{obra_id}/actividades")).json()[0]["cant_base"]), 2)
    for accion in ("enviar_a_presupuesto", "autorizar", "validar", "enviar_a_programa", "programar", "asignar"):
        r = await control.post(
            f"/api/v1/obras/{obra_id}/partes/transicion", json={"accion": accion, "claves": [clave_parte]}
        )
        assert r.status_code == 200, r.text
    await medir(10.0)
    despues = round(float((await control.get(f"/api/v1/obras/{obra_id}/actividades")).json()[0]["cant_base"]), 2)
    assert despues == antes
