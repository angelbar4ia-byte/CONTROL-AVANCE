"""Las hojas «matriz» del cuantificador (migración 0085; cerebro D-565, D-583).

Por HTTP contra Postgres real. El concepto es la matriz madre y un insumo puede ser otra matriz
(nervaduras, trabes, bastones), a cualquier profundidad:

    LOSA ── NERV (0.5 por m²) ── ESTRIBO (3 por ml de NERV)
        └─ TRABE (0.2 por m²)

 1. el árbol de matrices de una actividad trae lo que el catálogo implica para esa actividad;
 2. medir una matriz interna ajusta el importe sin tocar la cantidad de la actividad ni el catálogo;
 3. una matriz medida manda sobre las de adentro; reemplazar su enlace la deja sin medir;
 4. solo se miden las matrices que la receta del concepto contiene; y el enlace de la actividad
    entera no se mezcla con los de sus matrices.
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
async def losa(escenario: Escenario) -> AsyncIterator[dict[str, str]]:
    """Una actividad de LOSA: 10 m² a $1,000, con sus matrices internas."""
    engine = create_async_engine(DATABASE_URL_ADMIN)
    org = str(escenario.org_id)
    ids = {k: str(uuid.uuid4()) for k in ("LOSA", "NERV", "TRABE", "ESTRIBO", "AJENO")}
    async with engine.begin() as conn:
        for clave, pu in (("LOSA", 1000), ("NERV", 200), ("TRABE", 300), ("ESTRIBO", 10), ("AJENO", 5)):
            await conn.execute(
                text("insert into concepto (id, org_id, clave, descripcion) values (:i, :o, :c, :c)"),
                {"i": ids[clave], "o": org, "c": clave},
            )
            await conn.execute(
                text(
                    "insert into cpu (org_id, concepto_id, version, precio_unitario, precio_destajo, vigente) "
                    "values (:o, :c, 1, :p, 0, true)"
                ),
                {"o": org, "c": ids[clave], "p": pu},
            )
        for padre, hijo, cantidad in (("LOSA", "NERV", "0.5"), ("LOSA", "TRABE", "0.2"), ("NERV", "ESTRIBO", "3")):
            await conn.execute(
                text(
                    "insert into explosion (org_id, concepto_id, tipo_hijo, concepto_hijo_id, categoria, cantidad) "
                    "values (:o, :p, 'concepto', :h, 'matriz', :q)"
                ),
                {"o": org, "p": ids[padre], "h": ids[hijo], "q": cantidad},
            )
        await conn.execute(
            text(
                "update actividad set concepto_id = :c, cant_base = 10, cant_programada = 10, "
                "precio_unitario = 1000 where id = :a"
            ),
            {"c": ids["LOSA"], "a": str(escenario.actividad_id)},
        )
    yield ids
    await engine.dispose()


async def _medir(control, escenario, lado: float, *, matriz: str | None = None) -> httpx.Response:
    plano = (
        await control.post(
            f"/api/v1/obras/{escenario.obra_id}/planos",
            json={"nombre": f"P{uuid.uuid4().hex[:6]}", "archivo_url": "r2://p"},
        )
    ).json()
    enlace = {"actividad_id": str(escenario.actividad_id), "medida": "longitud", "factor": "1"}
    if matriz:
        enlace["matriz_concepto_id"] = matriz
    return await control.post(
        f"/api/v1/planos/{plano['id']}/trazos",
        json={
            "version_plano": 1,
            "geometria_wkt": f"LINESTRING(0 0, {lado} 0)",
            "fuente": "pdf",
            "enlaces": [enlace],
        },
    )


async def _matrices(control, escenario) -> dict:
    r = await control.get(f"/api/v1/actividades/{escenario.actividad_id}/matrices")
    assert r.status_code == 200, r.text
    return r.json()


async def test_el_arbol_trae_las_matrices_internas_con_lo_que_el_catalogo_implica(
    escenario: Escenario, losa: dict, control: httpx.AsyncClient
) -> None:
    cuerpo = await _matrices(control, escenario)
    assert (cuerpo["concepto_clave"], float(cuerpo["importe"]), float(cuerpo["importe_ajuste"])) == ("LOSA", 10000.0, 0.0)
    por_clave = {m["clave"]: m for m in cuerpo["matrices"]}
    assert set(por_clave) == {"NERV", "TRABE", "ESTRIBO"}
    # 10 m² × 0.5 = 5 de NERV; 10 × 0.2 = 2 de TRABE; 5 × 3 = 15 de ESTRIBO (dentro de NERV).
    assert {k: float(v["cantidad_catalogo"]) for k, v in por_clave.items()} == {"NERV": 5.0, "TRABE": 2.0, "ESTRIBO": 15.0}
    assert (por_clave["NERV"]["nivel"], por_clave["ESTRIBO"]["nivel"]) == (1, 2)
    assert por_clave["ESTRIBO"]["padre_id"] == losa["NERV"]
    assert all(m["cantidad_medida"] is None for m in cuerpo["matrices"])


async def test_medir_una_matriz_ajusta_el_importe_sin_tocar_la_actividad_ni_el_catalogo(
    escenario: Escenario, losa: dict, control: httpx.AsyncClient
) -> None:
    r = await _medir(control, escenario, 8.0, matriz=losa["NERV"])
    assert r.status_code == 201, r.text
    cuerpo = await _matrices(control, escenario)
    nerv = {m["clave"]: m for m in cuerpo["matrices"]}["NERV"]
    # Se midieron 8 contra 5 que implicaba el catálogo: +3 × $200.
    assert (float(nerv["cantidad_medida"]), float(nerv["diferencia"])) == (8.0, 3.0)
    assert (float(cuerpo["importe_ajuste"]), float(cuerpo["importe_ajustado"]), cuerpo["medidas"]) == (600.0, 10600.0, 1)

    # La actividad entera no cambió, ni su estado de cuantificación mezcla la matriz.
    a = (await control.get(f"/api/v1/obras/{escenario.obra_id}/actividades")).json()[0]
    assert float(a["cant_base"]) == 10.0
    estado = (await control.get(f"/api/v1/obras/{escenario.obra_id}/cuantificacion")).json()
    assert all(n["nodo_id"] != str(escenario.actividad_id) for n in estado)

    # El enlace de la actividad ENTERA no se mezcla con los de sus matrices.
    assert (await _medir(control, escenario, 12.0)).status_code == 201
    estado = (await control.get(f"/api/v1/obras/{escenario.obra_id}/cuantificacion")).json()
    [nodo] = [n for n in estado if n["nodo_id"] == str(escenario.actividad_id)]
    assert float(nodo["cantidad_medida"]) == 12.0
    assert float((await _matrices(control, escenario))["importe_ajuste"]) == 600.0


async def test_una_matriz_medida_manda_sobre_las_de_adentro_y_reemplazarla_la_deja_sin_medir(
    escenario: Escenario, losa: dict, control: httpx.AsyncClient
) -> None:
    # Se mide solo el estribo (de adentro): 20 contra 15 → +5 × $10.
    assert (await _medir(control, escenario, 20.0, matriz=losa["ESTRIBO"])).status_code == 201
    assert float((await _matrices(control, escenario))["importe_ajuste"]) == 50.0

    # Se mide la nervadura: manda sobre el estribo, que ya está dentro de ella.
    assert (await _medir(control, escenario, 8.0, matriz=losa["NERV"])).status_code == 201
    cuerpo = await _matrices(control, escenario)
    assert (float(cuerpo["importe_ajuste"]), cuerpo["medidas"]) == (600.0, 1)

    # Reemplazar (sin sustituto) el enlace de la nervadura la deja sin medir, no «medida en cero».
    plano_id = (await control.get(f"/api/v1/obras/{escenario.obra_id}/planos")).json()
    trazos = []
    for p in plano_id:
        trazos += (await control.get(f"/api/v1/planos/{p['id']}/trazos")).json()["features"]
    enlace = next(
        e["enlace_id"]
        for t in trazos
        for e in t["properties"]["enlaces"]
        if e.get("matriz_concepto_id") == losa["NERV"]
    )
    assert (await control.post(f"/api/v1/enlaces-cuantificacion/{enlace}/reemplazar", json={})).status_code == 200
    cuerpo = await _matrices(control, escenario)
    nerv = {m["clave"]: m for m in cuerpo["matrices"]}["NERV"]
    assert nerv["cantidad_medida"] is None
    assert float(cuerpo["importe_ajuste"]) == 50.0  # vuelve a contar el estribo


async def test_solo_se_miden_las_matrices_de_la_receta(
    escenario: Escenario, losa: dict, control: httpx.AsyncClient
) -> None:
    r = await _medir(control, escenario, 3.0, matriz=losa["AJENO"])
    assert r.status_code == 422, r.text
    assert "matriz interna" in r.text
    r = await control.get(f"/api/v1/actividades/{uuid.uuid4()}/matrices")
    assert r.status_code == 404
