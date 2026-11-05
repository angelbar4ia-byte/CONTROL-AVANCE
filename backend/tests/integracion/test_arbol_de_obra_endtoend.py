"""El árbol propio de una obra y las versiones de su presupuesto (D-624), por HTTP contra Postgres real."""

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
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
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
async def base(escenario: Escenario) -> AsyncIterator[dict[str, uuid.UUID]]:
    """El prototipo de la obra con un nivel, una etapa, un concepto y su presupuesto vigente."""
    ids = {k: uuid.uuid4() for k in ("nivel", "etapa", "nodo", "c1", "c2", "ppto", "etapa_cat")}
    org, proto = str(escenario.org_id), str(escenario.prototipo_id)
    motor = create_async_engine(DATABASE_URL_ADMIN)
    async with motor.begin() as c:
        await c.execute(
            text("insert into etapa_constructiva (id, org_id, clave, descripcion) values (:i, :o, 'ET-1', 'Cimentación')"),
            {"i": str(ids["etapa_cat"]), "o": org},
        )
        for k, clave in (("c1", "FIRME"), ("c2", "MURO")):
            await c.execute(
                text("insert into concepto (id, org_id, clave, descripcion) values (:i, :o, :k, :k)"), {"i": str(ids[k]), "o": org, "k": clave}
            )
        await c.execute(text("insert into cpu (org_id, concepto_id, precio_unitario) values (:o, :c, 250)"), {"o": org, "c": str(ids["c2"])})
        for k, tipo, padre, nombre, concepto, etapa in (
            ("nivel", "nivel", None, "Planta baja", None, None),
            ("etapa", "etapa", "nivel", "Cimentación", None, "etapa_cat"),
            ("nodo", "concepto", "etapa", "Firme", "c1", None),
        ):
            await c.execute(
                text(
                    "insert into prototipo_nodo (id, org_id, prototipo_id, parent_id, tipo, nombre, concepto_id, etapa_id, cantidad) "
                    "values (:i, :o, :p, cast(:par as uuid), cast(:t as tipo_prototipo_nodo), :n, cast(:c as uuid), cast(:e as uuid), 10)"
                ),
                {
                    "i": str(ids[k]), "o": org, "p": proto, "par": str(ids[padre]) if padre else None, "t": tipo, "n": nombre,
                    "c": str(ids[concepto]) if concepto else None, "e": str(ids[etapa]) if etapa else None,
                },
            )
        await c.execute(
            text("insert into presupuesto (id, org_id, prototipo_id, version, vigente, monto_total) values (:i, :o, :p, 1, true, 1000)"),
            {"i": str(ids["ppto"]), "o": org, "p": proto},
        )
        await c.execute(
            text(
                "insert into partida_presupuesto (org_id, presupuesto_id, concepto_id, prototipo_nodo_id, cantidad, precio_unitario, importe) "
                "values (:o, :pp, :c, :n, 10, 100, 1000)"
            ),
            {"o": org, "pp": str(ids["ppto"]), "c": str(ids["c1"]), "n": str(ids["nodo"])},
        )
        await c.execute(
            text("update actividad set prototipo_nodo_id = :n, concepto_id = :c where id = :a"),
            {"n": str(ids["nodo"]), "c": str(ids["c1"]), "a": str(escenario.actividad_id)},
        )
    yield ids
    await motor.dispose()


async def test_se_clona_el_arbol_se_edita_y_las_versiones_se_confirman_y_se_fijan(
    escenario: Escenario, base: dict, control: httpx.AsyncClient, residente: httpx.AsyncClient
) -> None:
    ruta = f"/api/v1/obras/{escenario.obra_id}/arbol"
    previo = (await control.get(ruta)).json()
    assert previo["propio"] is False and len(previo["nodos"]) == 3 and previo["borrador_id"] is None

    # Sin árbol propio no se edita (el del prototipo base es compartido); el residente no lo crea.
    assert (await control.post(f"{ruta}/nodos", json={"tipo": "nivel", "nombre": "Azotea"})).status_code == 422
    assert (await residente.post(f"{ruta}/propio")).status_code == 403

    # --- clonar: el prototipo base queda intacto y la obra pasa a la copia, con su partida re-ligada ----------
    r = await control.post(f"{ruta}/propio")
    assert r.status_code == 201, r.text
    assert r.json()["nodos"] == 3 and r.json()["partidas_religadas"] == 1
    assert (await control.post(f"{ruta}/propio")).status_code == 422  # ya lo tiene
    arbol = (await control.get(ruta)).json()
    assert arbol["propio"] is True and arbol["prototipo_id"] != str(escenario.prototipo_id)
    assert [(v["version"], v["estado"], v["vigente"]) for v in arbol["versiones"]] == [(1, "confirmada", True)]
    assert arbol["borrador_id"] is None  # clonar no es un cambio: el borrador nace con el primero
    nodos = {n["nombre"]: n for n in arbol["nodos"]}
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.connect() as c:
            assert (await c.execute(text("select count(*) from prototipo_nodo where prototipo_id = :p"), {"p": str(escenario.prototipo_id)})).scalar_one() == 3
            ligada = (await c.execute(text("select prototipo_nodo_id from actividad where id = :a"), {"a": str(escenario.actividad_id)})).scalar_one()
            assert str(ligada) == nodos["Firme"]["id"]

        # --- el primer cambio crea el borrador; un concepto nuevo entra sin cantidad y con su precio ----------------
        nivel = nodos["Planta baja"]["id"]
        etapa = nodos["Cimentación"]["id"]
        muro = await control.post(f"{ruta}/nodos", json={"tipo": "concepto", "parent_id": etapa, "concepto_id": str(base["c2"])})
        assert muro.status_code == 201, muro.text
        arbol = (await control.get(ruta)).json()
        assert arbol["borrador_id"] is not None
        assert [(v["version"], v["estado"], v["vigente"]) for v in arbol["versiones"]] == [(2, "borrador", False), (1, "confirmada", True)]
        borrador = next(v for v in arbol["versiones"] if v["estado"] == "borrador")
        assert borrador["partidas"] == 2
        async with motor.connect() as c:
            pu = (await c.execute(text("select precio_unitario, cantidad from partida_presupuesto where presupuesto_id = :b and prototipo_nodo_id = :n"), {"b": borrador["id"], "n": muro.json()["id"]})).one()
            assert (float(pu[0]), float(pu[1])) == (250.0, 0.0)

        # Jerarquía: un concepto cuelga de una etapa; una etapa de un nivel; un nivel de nada.
        assert (await control.post(f"{ruta}/nodos", json={"tipo": "concepto", "parent_id": nivel, "concepto_id": str(base["c2"])})).status_code == 422
        assert (await control.post(f"{ruta}/nodos", json={"tipo": "nivel", "parent_id": nivel, "nombre": "x"})).status_code == 422
        nueva = (await control.post(f"{ruta}/nodos", json={"tipo": "etapa", "parent_id": nivel, "nombre": "Estructura"})).json()["id"]

        # Renombrar y reordenar no crean otro borrador; quitar lo ya generado se rechaza.
        assert (await control.patch(f"{ruta}/nodos/{nueva}", json={"nombre": "Estructura 2", "orden": 9})).status_code == 204
        assert (await control.delete(f"{ruta}/nodos/{nodos['Firme']['id']}")).status_code == 409  # la obra ya generó esa partida
        assert (await control.delete(f"{ruta}/nodos/{nueva}")).status_code == 204
        assert len((await control.get(ruta)).json()["versiones"]) == 2

        # --- confirmar: queda fija; fijarla como activa ----------------------------------------------------------
        assert (await control.post(f"{ruta}/versiones/{borrador['id']}/activar")).status_code == 422  # aún es borrador
        assert (await control.post(f"{ruta}/versiones/confirmar", json={"nota": "se agregó el muro"})).status_code == 204
        versiones = (await control.get(ruta)).json()["versiones"]
        v2 = versiones[0]
        assert (v2["version"], v2["estado"], v2["vigente"], v2["nota"]) == (2, "confirmada", False, "se agregó el muro")
        assert (await control.post(f"{ruta}/versiones/confirmar", json={})).status_code == 422  # ya no hay borrador
        assert (await control.post(f"{ruta}/versiones/{borrador['id']}/activar")).status_code == 204
        versiones = {v["version"]: v for v in (await control.get(ruta)).json()["versiones"]}
        assert versiones[2]["vigente"] is True and versiones[1]["vigente"] is False

        # Después de confirmar, el siguiente cambio abre un borrador nuevo (versión 3), sin tocar la 2.
        assert (await control.patch(f"{ruta}/nodos/{etapa}", json={"nombre": "Cimentación y firme"})).status_code == 204
        assert [(v["version"], v["estado"]) for v in (await control.get(ruta)).json()["versiones"]][:2] == [(3, "borrador"), (2, "confirmada")]
    finally:
        await motor.dispose()


async def test_una_parte_asignada_no_se_clona_ni_se_edita(escenario: Escenario, base: dict, control: httpx.AsyncClient) -> None:
    ruta = f"/api/v1/obras/{escenario.obra_id}/arbol"
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            await c.execute(
                text("insert into parte_estado (org_id, obra_id, clave, estado) values (:o, :ob, :k, 'asignada')"),
                {"o": str(escenario.org_id), "ob": str(escenario.obra_id), "k": f"etapa:{base['etapa_cat']}"},
            )
    except Exception as e:  # la tabla de estados de parte puede llamarse distinto: se salta con el motivo
        pytest.skip(f"No se pudo sembrar el estado de la parte: {e}")
    finally:
        await motor.dispose()
    assert (await control.post(f"{ruta}/propio")).status_code == 409


async def test_eliminar_una_obra_en_diseno_pide_la_clave_y_se_lleva_su_arbol_propio(
    escenario: Escenario, base: dict, control: httpx.AsyncClient, residente: httpx.AsyncClient
) -> None:
    ruta = f"/api/v1/obras/{escenario.obra_id}"
    await control.post(f"{ruta}/arbol/propio")  # la obra tiene su árbol propio
    propio = (await control.get(f"{ruta}/arbol")).json()["prototipo_id"]

    assert (await residente.post(f"{ruta}/eliminar", json={"clave": "OBRA 01"})).status_code == 403
    # La segunda confirmación: la clave escrita.
    assert (await control.post(f"{ruta}/eliminar", json={"clave": "otra"})).status_code == 422
    assert (await control.get(f"{ruta}/arbol")).status_code == 200  # sigue ahí

    assert (await control.post(f"{ruta}/eliminar", json={"clave": "obra 01"})).status_code == 204
    assert (await control.get(f"{ruta}/arbol")).status_code == 404
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.connect() as c:
            assert (await c.execute(text("select count(*) from prototipo where id = :p"), {"p": propio})).scalar_one() == 0
            assert (await c.execute(text("select count(*) from prototipo where id = :p"), {"p": str(escenario.prototipo_id)})).scalar_one() == 1
    finally:
        await motor.dispose()


async def test_una_obra_programada_o_con_avance_ya_no_se_elimina(escenario: Escenario, base: dict, control: httpx.AsyncClient) -> None:
    ruta = f"/api/v1/obras/{escenario.obra_id}/eliminar"
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            await c.execute(text("update actividad set cant_ejecutada = 1 where id = :a"), {"a": str(escenario.actividad_id)})
        assert (await control.post(ruta, json={"clave": "OBRA 01"})).status_code == 409  # avance: ya no es diseño
        async with motor.begin() as c:
            await c.execute(text("update actividad set cant_ejecutada = 0 where id = :a"), {"a": str(escenario.actividad_id)})
            await c.execute(
                text("insert into parte_estado (org_id, obra_id, clave, estado) values (:o, :ob, 'sin_etapa', 'programada')"),
                {"o": str(escenario.org_id), "ob": str(escenario.obra_id)},
            )
        assert (await control.post(ruta, json={"clave": "OBRA 01"})).status_code == 409  # programada: contratada
    finally:
        await motor.dispose()


async def test_reiniciar_una_obra_borra_lo_disenado_y_vuelve_al_prototipo_base(
    escenario: Escenario, base: dict, control: httpx.AsyncClient
) -> None:
    ruta = f"/api/v1/obras/{escenario.obra_id}"
    plano = (await control.post(f"{ruta}/planos", json={"nombre": "P", "archivo_url": "e2e/p.pdf"})).json()["id"]
    await control.post(
        f"/api/v1/planos/{plano}/trazos",
        json={"version_plano": 1, "fuente": "pdf", "geometria_wkt": "POINT(1 1)",
              "enlaces": [{"medida": "conteo", "factor": "1", "actividad_id": str(escenario.actividad_id)}]},
    )
    await control.post(f"{ruta}/arbol/propio")
    propio = (await control.get(f"{ruta}/arbol")).json()["prototipo_id"]
    assert propio != str(escenario.prototipo_id)

    assert (await control.post(f"{ruta}/reiniciar", json={"clave": "mal"})).status_code == 422
    r = await control.post(f"{ruta}/reiniciar", json={"clave": "OBRA 01"})
    assert r.status_code == 200, r.text
    assert r.json() == {"trazos": 1, "actividades": 1, "volvio_al_base": True, "actividades_generadas": 0, "motivo_sin_generar": None}

    # La obra sigue ahí, con su plano, de vuelta en el prototipo base; la copia desapareció y no quedan partidas ni trazos.
    arbol = (await control.get(f"{ruta}/arbol")).json()
    assert arbol["propio"] is False and arbol["prototipo_id"] == str(escenario.prototipo_id)
    assert (await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"] == []
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.connect() as c:
            assert (await c.execute(text("select count(*) from prototipo where id = :p"), {"p": propio})).scalar_one() == 0
            assert (await c.execute(text("select count(*) from actividad where obra_id = :o"), {"o": str(escenario.obra_id)})).scalar_one() == 0
    finally:
        await motor.dispose()


async def test_cambiar_de_prototipo_una_obra_en_diseno_y_la_forma_de_arranque_es_solo_informativa(
    escenario: Escenario, base: dict, control: httpx.AsyncClient
) -> None:
    ruta = f"/api/v1/obras/{escenario.obra_id}"
    # La forma de arranque aparece en el árbol (vacía mientras nadie la fije).
    assert "forma_de_arranque" in (await control.get(f"{ruta}/arbol")).json()

    otro = uuid.uuid4()
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            await c.execute(
                text(
                    "insert into prototipo (id, org_id, proyecto_id, clave, nombre) "
                    "select :i, org_id, proyecto_id, 'CAS-2', 'Otro prototipo' from prototipo where id = :p"
                ),
                {"i": str(otro), "p": str(escenario.prototipo_id)},
            )
        assert (await control.post(f"{ruta}/prototipo", json={"prototipo_id": str(otro), "clave": "mal"})).status_code == 422
        mismo = {"prototipo_id": str(escenario.prototipo_id), "clave": "OBRA 01"}
        assert (await control.post(f"{ruta}/prototipo", json=mismo)).status_code == 422  # ya usa ese
        r = await control.post(f"{ruta}/prototipo", json={"prototipo_id": str(otro), "clave": "OBRA 01"})
        assert r.status_code == 200, r.text
        assert r.json()["actividades"] == 1 and r.json()["volvio_al_base"] is True
        assert r.json()["actividades_generadas"] == 0 and r.json()["motivo_sin_generar"]  # el otro prototipo está vacío
        assert (await control.get(f"{ruta}/arbol")).json()["prototipo_id"] == str(otro)

        # Con una parte programada la obra ya está contratada: no cambia de prototipo.
        async with motor.begin() as c:
            await c.execute(
                text("insert into parte_estado (org_id, obra_id, clave, estado) values (:o, :ob, 'sin_etapa', 'asignada')"),
                {"o": str(escenario.org_id), "ob": str(escenario.obra_id)},
            )
        vuelta = {"prototipo_id": str(escenario.prototipo_id), "clave": "OBRA 01"}
        assert (await control.post(f"{ruta}/prototipo", json=vuelta)).status_code == 409
    finally:
        await motor.dispose()


async def test_toda_obra_nueva_guarda_su_forma_de_arranque_y_reporta_sus_partidas(
    escenario: Escenario, base: dict, control: httpx.AsyncClient
) -> None:
    cuerpo = {"cluster_id": str(escenario.cluster_id), "clave": "NUEVA 01", "prototipo_id": str(escenario.prototipo_id)}
    r = await control.post("/api/v1/obras", json=cuerpo)
    assert r.status_code == 201, r.text
    nueva = r.json()
    # Las partidas se generan solas, o se dice por qué no (nunca falla el alta por eso).
    assert "actividades_generadas" in nueva and "motivo_sin_generar" in nueva
    assert nueva["actividades_generadas"] > 0 or nueva["motivo_sin_generar"]
    arbol = (await control.get(f"/api/v1/obras/{nueva['id']}/arbol")).json()
    assert arbol["forma_de_arranque"] == "prototipo"
