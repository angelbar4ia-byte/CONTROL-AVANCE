"""Las matrices de un concepto del catálogo (entrega 5b): se ponen, se cambian y se quitan."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

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
async def costos(escenario: Escenario) -> AsyncIterator[httpx.AsyncClient]:
    usuario = uuid.uuid4()
    engine = create_async_engine(DATABASE_URL_ADMIN)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "insert into usuario (id, org_id, nombre, email, rol) "
                "values (:i, :o, 'Costos Test', :e, 'costos')"
            ),
            {"i": str(usuario), "o": str(escenario.org_id), "e": f"cos-{usuario.hex[:8]}@test.mx"},
        )
    await engine.dispose()
    contexto = ContextoSesion(org_id=escenario.org_id, usuario_id=usuario, rol="costos")
    async with _cliente(contexto) as c:
        yield c


@pytest.fixture
async def catalogo(escenario: Escenario) -> AsyncIterator[dict[str, uuid.UUID]]:
    """Una unidad, un concepto padre ligado a la actividad del escenario y otro suelto."""
    engine = create_async_engine(DATABASE_URL_ADMIN)
    org = str(escenario.org_id)
    unidad, padre, otro = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text("insert into unidad (id, org_id, clave, nombre) values (:i, :o, 'm2', 'Metro cuadrado')"),
            {"i": str(unidad), "o": org},
        )
        for cid, clave in ((padre, "PAD-1"), (otro, "OTR-1")):
            await conn.execute(
                text(
                    "insert into concepto (id, org_id, tipo, clave, descripcion, unidad_id) "
                    "values (:i, :o, 'concepto', :c, :c, :u)"
                ),
                {"i": str(cid), "o": org, "c": clave, "u": str(unidad)},
            )
        await conn.execute(
            text("update actividad set concepto_id = :c where id = :a"),
            {"c": str(padre), "a": str(escenario.actividad_id)},
        )
    yield {"unidad": unidad, "padre": padre, "otro": otro}
    await engine.dispose()


async def _matrices(cliente: httpx.AsyncClient, escenario: Escenario) -> list[dict]:
    r = await cliente.get(f"/api/v1/actividades/{escenario.actividad_id}/matrices")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    return cuerpo["matrices"] if isinstance(cuerpo, dict) else cuerpo


async def test_una_matriz_nueva_nace_y_cuelga_del_concepto(
    escenario: Escenario, catalogo: dict, control: httpx.AsyncClient
) -> None:
    r = await control.post(
        f"/api/v1/conceptos/{catalogo['padre']}/matrices",
        json={
            "cantidad": "0.5",
            "nueva": {"clave": "mat-n1", "descripcion": "Mezcla", "unidad_id": str(catalogo["unidad"])},
        },
    )
    assert r.status_code == 200, r.text
    assert [(m["clave"], float(m["cantidad_catalogo"])) for m in await _matrices(control, escenario)] == [
        ("MAT-N1", 50.0)  # 0.5 por unidad × 100 de la actividad
    ]


async def test_una_existente_se_pone_y_cambiarle_la_cantidad_no_la_duplica(
    escenario: Escenario, catalogo: dict, control: httpx.AsyncClient
) -> None:
    url = f"/api/v1/conceptos/{catalogo['padre']}/matrices"
    for cantidad in ("1", "2.5"):
        r = await control.post(url, json={"cantidad": cantidad, "matriz_id": str(catalogo["otro"])})
        assert r.status_code == 200, r.text
    assert [float(m["cantidad_catalogo"]) for m in await _matrices(control, escenario)] == [250.0]


async def test_un_ciclo_se_rechaza(catalogo: dict, control: httpx.AsyncClient) -> None:
    assert (
        await control.post(
            f"/api/v1/conceptos/{catalogo['padre']}/matrices",
            json={"cantidad": "1", "matriz_id": str(catalogo["otro"])},
        )
    ).status_code == 200
    # Ahora «otro» ya cuelga de «padre»: poner a «padre» bajo «otro» cerraría el ciclo.
    r = await control.post(
        f"/api/v1/conceptos/{catalogo['otro']}/matrices",
        json={"cantidad": "1", "matriz_id": str(catalogo["padre"])},
    )
    assert r.status_code == 422, r.text
    r = await control.post(
        f"/api/v1/conceptos/{catalogo['padre']}/matrices",
        json={"cantidad": "1", "matriz_id": str(catalogo["padre"])},
    )
    assert r.status_code == 422, r.text


async def test_quitar_una_matriz(
    escenario: Escenario, catalogo: dict, control: httpx.AsyncClient
) -> None:
    await control.post(
        f"/api/v1/conceptos/{catalogo['padre']}/matrices",
        json={"cantidad": "1", "matriz_id": str(catalogo["otro"])},
    )
    url = f"/api/v1/conceptos/{catalogo['padre']}/matrices/{catalogo['otro']}"
    assert (await control.delete(url)).status_code == 204
    assert await _matrices(control, escenario) == []
    assert (await control.delete(url)).status_code == 404


async def test_pide_una_cosa_o_la_otra_y_cantidad_positiva(
    catalogo: dict, control: httpx.AsyncClient
) -> None:
    url = f"/api/v1/conceptos/{catalogo['padre']}/matrices"
    assert (await control.post(url, json={"cantidad": "1"})).status_code == 422
    assert (await control.post(url, json={"cantidad": "0", "matriz_id": str(catalogo["otro"])})).status_code == 422


async def test_el_residente_no_cambia_el_catalogo(catalogo: dict, residente: httpx.AsyncClient) -> None:
    r = await residente.post(
        f"/api/v1/conceptos/{catalogo['padre']}/matrices",
        json={"cantidad": "1", "matriz_id": str(catalogo["otro"])},
    )
    assert r.status_code == 403, r.text


async def test_costos_pone_y_quita_matrices_con_su_rol_real(
    escenario: Escenario, catalogo: dict, costos: httpx.AsyncClient
) -> None:
    url = f"/api/v1/conceptos/{catalogo['padre']}/matrices"
    r = await costos.post(
        url,
        json={
            "cantidad": "1",
            "nueva": {"clave": "cos-n1", "descripcion": "De Costos", "unidad_id": str(catalogo["unidad"])},
        },
    )
    assert r.status_code == 200, r.text
    assert [m["clave"] for m in await _matrices(costos, escenario)] == ["COS-N1"]
    assert (await costos.delete(f"{url}/{r.json()['matriz_id']}")).status_code == 204
    assert await _matrices(costos, escenario) == []


async def test_el_costo_se_ve_desactualizado_y_se_publica_una_version_nueva(
    escenario: Escenario, catalogo: dict, control: httpx.AsyncClient, costos: httpx.AsyncClient
) -> None:
    """Agregar una matriz con receta propia cambia el costo calculado; Costos publica la versión."""
    engine = create_async_engine(DATABASE_URL_ADMIN)
    org = str(escenario.org_id)
    insumo = uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text("insert into insumo (id, org_id, tipo, clave, descripcion, costo_base) values (:i, :o, 'material', 'INS-1', 'Ins', 10)"),
            {"i": str(insumo), "o": org},
        )
        await conn.execute(
            text(
                "insert into explosion (org_id, concepto_id, tipo_hijo, insumo_id, categoria, cantidad, costo_unitario, importe) "
                "values (:o, :c, 'insumo', :i, 'material', 3, 10, 30)"
            ),
            {"o": org, "c": str(catalogo["otro"]), "i": str(insumo)},
        )
    await engine.dispose()

    url_cpu = f"/api/v1/conceptos/{catalogo['padre']}/cpu"
    primero = await costos.post(url_cpu, json={})
    assert primero.status_code == 201, primero.text
    antes = (await costos.get(url_cpu)).json()
    assert antes["calculado"]["total"] == antes["vigente"]["precio"]["total"]

    # «otro» cuesta 30 por unidad; media unidad suma 15 al padre.
    r = await control.post(
        f"/api/v1/conceptos/{catalogo['padre']}/matrices",
        json={"cantidad": "0.5", "matriz_id": str(catalogo["otro"])},
    )
    assert r.status_code == 200, r.text
    despues = (await costos.get(url_cpu)).json()
    assert float(despues["calculado"]["total"]) == float(antes["calculado"]["total"]) + 15
    assert despues["calculado"]["total"] != despues["vigente"]["precio"]["total"]

    publicada = await costos.post(url_cpu, json={})
    assert publicada.status_code == 201, publicada.text
    assert publicada.json()["version"]["version"] == 2
    final = (await costos.get(url_cpu)).json()
    assert final["calculado"]["total"] == final["vigente"]["precio"]["total"]


async def test_la_cantidad_se_forma_por_piezas_comerciales_castillo_k2(
    escenario: Escenario, catalogo: dict, control: httpx.AsyncClient
) -> None:
    """4 varillas del no. 3 de 12 ml, con 0.5 % de desperdicio: 0.335 varillas por cada ml de castillo."""
    url = f"/api/v1/conceptos/{catalogo['padre']}/matrices"
    r = await control.post(
        url,
        json={"matriz_id": str(catalogo["otro"]), "formula": {"piezas": "4", "largo": "12", "desperdicio_pct": "0.5"}},
    )
    assert r.status_code == 200, r.text
    assert Decimal(str(r.json()["cantidad"])) == Decimal("0.335")
    assert r.json()["formula"] == {"tipo": "piezas_comerciales", "piezas": 4.0, "largo": 12.0, "desperdicio_pct": 0.5}

    # El árbol de la actividad (100 de cantidad base) la usa y la devuelve: 0.335 × 100 = 33.5.
    [matriz] = await _matrices(control, escenario)
    assert float(matriz["cantidad_unitaria"]) == 0.335 and float(matriz["cantidad_catalogo"]) == 33.5
    assert matriz["formula"]["piezas"] == 4.0

    # Cambiarla a mano reemplaza la fórmula.
    r = await control.post(url, json={"matriz_id": str(catalogo["otro"]), "cantidad": "2"})
    assert r.status_code == 200 and r.json()["formula"] is None
    [matriz] = await _matrices(control, escenario)
    assert float(matriz["cantidad_unitaria"]) == 2 and matriz["formula"] is None


async def test_cantidad_y_formula_son_una_o_la_otra(catalogo: dict, control: httpx.AsyncClient) -> None:
    url = f"/api/v1/conceptos/{catalogo['padre']}/matrices"
    formula = {"piezas": "4", "largo": "12"}
    assert (await control.post(url, json={"matriz_id": str(catalogo["otro"])})).status_code == 422
    assert (
        await control.post(url, json={"matriz_id": str(catalogo["otro"]), "cantidad": "1", "formula": formula})
    ).status_code == 422
    assert (
        await control.post(url, json={"matriz_id": str(catalogo["otro"]), "formula": {"piezas": "4", "largo": "0"}})
    ).status_code == 422
    assert (
        await control.post(url, json={"matriz_id": str(catalogo["otro"]), "formula": {**formula, "desperdicio_pct": "150"}})
    ).status_code == 422


async def test_losa_zafiro_una_pieza_con_matrices_de_distintas_unidades(
    escenario: Escenario, catalogo: dict, control: httpx.AsyncClient
) -> None:
    """Losa Zafiro: unidad pieza, cantidad 1; adentro, trabe en ml, malla en m²…, cada una con su tipo de medición."""
    engine = create_async_engine(DATABASE_URL_ADMIN)
    org = str(escenario.org_id)
    ids = {k: uuid.uuid4() for k in ("zafiro", "trabe", "malla")}
    async with engine.begin() as conn:
        for clave in ("ml", "pza"):
            await conn.execute(
                text("insert into unidad (id, org_id, clave, nombre) values (:i, :o, :c, :c)"),
                {"i": str(uuid.uuid4()), "o": org, "c": clave},
            )
        unidades = {
            fila[0]: fila[1]
            for fila in (await conn.execute(text("select clave, id from unidad where org_id = :o"), {"o": org})).all()
        }
        for k, clave, desc, u in (
            ("zafiro", "ZAFIRO", "Losa Zafiro", "pza"),
            ("trabe", "TRABE-ML", "Trabe", "ml"),
            ("malla", "MALLA-M2", "Malla electrosoldada", "m2"),
        ):
            await conn.execute(
                text(
                    "insert into concepto (id, org_id, tipo, clave, descripcion, unidad_id) "
                    "values (:i, :o, 'concepto', :c, :d, :u)"
                ),
                {"i": str(ids[k]), "o": org, "c": clave, "d": desc, "u": str(unidades[u])},
            )
        await conn.execute(
            text("update actividad set concepto_id = :c, cant_base = 1, cant_programada = 1 where id = :a"),
            {"c": str(ids["zafiro"]), "a": str(escenario.actividad_id)},
        )
    await engine.dispose()

    url = f"/api/v1/conceptos/{ids['zafiro']}/matrices"
    assert (await control.post(url, json={"matriz_id": str(ids["trabe"]), "cantidad": "5.5"})).status_code == 200
    assert (await control.post(url, json={"matriz_id": str(ids["malla"]), "cantidad": "1.05"})).status_code == 200

    por_clave = {m["clave"]: m for m in await _matrices(control, escenario)}
    assert (por_clave["TRABE-ML"]["unidad"], float(por_clave["TRABE-ML"]["cantidad_catalogo"])) == ("ml", 5.5)
    assert (por_clave["MALLA-M2"]["unidad"], float(por_clave["MALLA-M2"]["cantidad_catalogo"])) == ("m2", 1.05)
