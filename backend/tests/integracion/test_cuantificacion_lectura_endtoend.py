"""Lecturas del cuantificador por HTTP de punta a punta contra Postgres real
con PostGIS (cerebro MODELO.md §1b, migración 0057).

Sin dobles: la petición cruza router → caso de uso → repositorio SQL → RLS.
Lo que se fija es lo que solo se ve así:

 1. los trazos salen como GeoJSON con la geometría y los enlaces que se
    escribieron, y la `medida_valor` la calcula PostGIS (rectángulo 4×3 → 12),
 2. la cantidad de un nodo es la suma de sus enlaces **vigentes**, y un
    reemplazo la cambia sin borrar el enlace anterior,
 3. un trazo hecho sobre una versión anterior del plano aparece **por revisar**
    y su cantidad no se recalcula sola,
 4. lo que no existe o no se ve es 404, y otra organización no ve nada.
"""

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
from tests.integracion.test_cuantificacion_endtoend import (
    _RECTANGULO_4X3,
    _preparar_actividad_con_concepto,
)


def _cliente(contexto: ContextoSesion) -> httpx.AsyncClient:
    app = crear_app()
    app.dependency_overrides[contexto_actual] = lambda: contexto
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    )


@pytest.fixture
async def cliente_control(contexto_control: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_control) as cliente:
        yield cliente


async def _subir_version_del_plano(plano_id: str, version: int) -> None:
    """Como si el plano se reexportara: engine admin, aquí se prepara el
    fixture, no se prueba aislamiento."""
    engine = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("update plano set version = :v where id = :id"),
                {"v": version, "id": plano_id},
            )
    finally:
        await engine.dispose()


async def _plano_con_dos_trazos(
    cliente: httpx.AsyncClient, escenario: Escenario
) -> tuple[str, str, str]:
    """Un plano con un rectángulo 4×3 (área 12) y un conteo, ambos sobre la
    actividad. Devuelve `(plano_id, enlace_area, enlace_conteo)`."""
    respuesta = await cliente.post(
        f"/api/v1/obras/{escenario.obra_id}/planos",
        json={"nombre": "Planta baja", "archivo_url": "org/planos/pb.pdf", "version": 1},
    )
    assert respuesta.status_code == 201, respuesta.text
    plano_id = respuesta.json()["id"]

    enlaces = []
    for wkt, medida in ((_RECTANGULO_4X3, "area"), ("POINT(1 1)", "conteo")):
        trazo = await cliente.post(
            f"/api/v1/planos/{plano_id}/trazos",
            json={
                "version_plano": 1,
                "fuente": "pdf",
                "geometria_wkt": wkt,
                "enlaces": [
                    {
                        "medida": medida,
                        "factor": "1",
                        "actividad_id": str(escenario.actividad_id),
                    }
                ],
            },
        )
        assert trazo.status_code == 201, trazo.text
        enlaces.append(trazo.json()["enlace_ids"][0])
    return plano_id, enlaces[0], enlaces[1]


async def test_listar_planos_de_una_obra(
    escenario: Escenario, cliente_control: httpx.AsyncClient
) -> None:
    vacio = await cliente_control.get(f"/api/v1/obras/{escenario.obra_id}/planos")
    assert vacio.status_code == 200
    assert vacio.json() == []

    plano_id, _, _ = await _plano_con_dos_trazos(cliente_control, escenario)

    lista = (await cliente_control.get(f"/api/v1/obras/{escenario.obra_id}/planos")).json()
    assert len(lista) == 1
    assert lista[0]["id"] == plano_id
    assert lista[0]["nombre"] == "Planta baja"
    assert lista[0]["n_trazos"] == 2
    assert lista[0]["n_trazos_por_revisar"] == 0


async def test_los_trazos_salen_como_geojson_con_su_medida(
    escenario: Escenario, cliente_control: httpx.AsyncClient
) -> None:
    await _preparar_actividad_con_concepto(
        org_id=escenario.org_id,
        actividad_id=escenario.actividad_id,
        precio_unitario=Decimal("10"),
    )
    plano_id, _, _ = await _plano_con_dos_trazos(cliente_control, escenario)

    respuesta = await cliente_control.get(f"/api/v1/planos/{plano_id}/trazos")
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()

    assert cuerpo["type"] == "FeatureCollection"
    assert cuerpo["plano_id"] == plano_id
    assert len(cuerpo["features"]) == 2

    poligono = next(f for f in cuerpo["features"] if f["geometry"]["type"] == "Polygon")
    # Coordenadas de plano, sin `crs` inventado (MODELO.md §1b).
    assert "crs" not in poligono["geometry"]
    assert poligono["geometry"]["coordinates"] == [
        [[0, 0], [4, 0], [4, 3], [0, 3], [0, 0]]
    ]
    propiedades = poligono["properties"]
    assert propiedades["trazo_id"] == poligono["id"]
    assert propiedades["nodo_ids"] == [str(escenario.actividad_id)]
    assert propiedades["por_revisar"] is False

    (enlace,) = propiedades["enlaces"]
    assert enlace["tipo_nodo"] == "actividad"
    assert enlace["nodo_id"] == str(escenario.actividad_id)
    assert Decimal(enlace["medida_valor"]) == Decimal(12)  # ST_Area, calculada por PostGIS
    assert Decimal(enlace["cantidad"]) == Decimal(12)

    punto = next(f for f in cuerpo["features"] if f["geometry"]["type"] == "Point")
    assert Decimal(punto["properties"]["enlaces"][0]["medida_valor"]) == Decimal(1)


async def test_la_cantidad_suma_los_vigentes_y_un_reemplazo_la_cambia(
    escenario: Escenario, cliente_control: httpx.AsyncClient
) -> None:
    await _preparar_actividad_con_concepto(
        org_id=escenario.org_id,
        actividad_id=escenario.actividad_id,
        precio_unitario=Decimal("10"),
    )
    plano_id, _, enlace_conteo = await _plano_con_dos_trazos(cliente_control, escenario)

    estado = (
        await cliente_control.get(f"/api/v1/obras/{escenario.obra_id}/cuantificacion")
    ).json()
    (nodo,) = estado
    assert nodo["tipo_nodo"] == "actividad"
    assert nodo["nodo_id"] == str(escenario.actividad_id)
    assert Decimal(nodo["cant_base"]) == Decimal(100)
    assert Decimal(nodo["cantidad_medida"]) == Decimal(13)  # 12 (área) + 1 (conteo)
    assert Decimal(nodo["diferencia"]) == Decimal(-87)
    assert nodo["enlaces_vigentes"] == 2
    assert nodo["enlaces_reemplazados"] == 0

    # Se reemplaza el conteo por el perímetro del rectángulo (14). El enlace
    # viejo se conserva como evidencia: no se borra ni se suma.
    trazos = (await cliente_control.get(f"/api/v1/planos/{plano_id}/trazos")).json()
    poligono = next(f for f in trazos["features"] if f["geometry"]["type"] == "Polygon")
    reemplazo = await cliente_control.post(
        f"/api/v1/enlaces-cuantificacion/{enlace_conteo}/reemplazar",
        json={"nuevo": {"trazo_id": poligono["id"], "medida": "perimetro", "factor": "1"}},
    )
    assert reemplazo.status_code in (200, 201), reemplazo.text

    (nodo,) = (
        await cliente_control.get(f"/api/v1/obras/{escenario.obra_id}/cuantificacion")
    ).json()
    assert Decimal(nodo["cantidad_medida"]) == Decimal(26)  # 12 (área) + 14 (perímetro)
    assert nodo["enlaces_vigentes"] == 2
    assert nodo["enlaces_reemplazados"] == 1

    # El enlace reemplazado sigue en el trazo, con `vigente = false`, y ya no
    # cuenta en `nodo_ids`.
    punto = next(
        f
        for f in (await cliente_control.get(f"/api/v1/planos/{plano_id}/trazos")).json()["features"]
        if f["geometry"]["type"] == "Point"
    )
    assert [e["vigente"] for e in punto["properties"]["enlaces"]] == [False]
    assert punto["properties"]["nodo_ids"] == []


async def test_un_plano_nuevo_deja_los_trazos_viejos_por_revisar(
    escenario: Escenario, cliente_control: httpx.AsyncClient
) -> None:
    await _preparar_actividad_con_concepto(
        org_id=escenario.org_id,
        actividad_id=escenario.actividad_id,
        precio_unitario=Decimal("10"),
    )
    plano_id, _, _ = await _plano_con_dos_trazos(cliente_control, escenario)
    antes = (
        await cliente_control.get(f"/api/v1/obras/{escenario.obra_id}/cuantificacion")
    ).json()[0]["cantidad_medida"]

    await _subir_version_del_plano(plano_id, 2)

    (plano,) = (await cliente_control.get(f"/api/v1/obras/{escenario.obra_id}/planos")).json()
    assert plano["version"] == 2
    assert plano["n_trazos_por_revisar"] == 2

    trazos = (await cliente_control.get(f"/api/v1/planos/{plano_id}/trazos")).json()
    assert trazos["version_plano"] == 2
    assert all(f["properties"]["por_revisar"] for f in trazos["features"])

    (nodo,) = (
        await cliente_control.get(f"/api/v1/obras/{escenario.obra_id}/cuantificacion")
    ).json()
    assert nodo["trazos_por_revisar"] == 2
    # Marcado para revisión, no recalculado solo (MODELO.md §1b).
    assert nodo["cantidad_medida"] == antes


async def test_lo_que_no_existe_es_404_y_otra_organizacion_no_ve_nada(
    escenario: Escenario, cliente_control: httpx.AsyncClient, contexto_ajeno: ContextoSesion
) -> None:
    plano_id, _, _ = await _plano_con_dos_trazos(cliente_control, escenario)

    inexistente = uuid.uuid4()
    assert (await cliente_control.get(f"/api/v1/obras/{inexistente}/planos")).status_code == 404
    assert (await cliente_control.get(f"/api/v1/obras/{inexistente}/cuantificacion")).status_code == 404
    sin_plano = await cliente_control.get(f"/api/v1/planos/{inexistente}/trazos")
    assert sin_plano.status_code == 404
    assert sin_plano.json()["type"].endswith("plano-no-encontrado")

    # Otra organización: RLS hace indistinguible "no existe" de "no la ves".
    async with _cliente(contexto_ajeno) as ajeno:
        assert (await ajeno.get(f"/api/v1/obras/{escenario.obra_id}/planos")).status_code == 404
        assert (await ajeno.get(f"/api/v1/planos/{plano_id}/trazos")).status_code == 404
        assert (
            await ajeno.get(f"/api/v1/obras/{escenario.obra_id}/cuantificacion")
        ).status_code == 404


async def test_la_lectura_esta_abierta_a_quien_ve_la_obra(
    escenario: Escenario,
    cliente_control: httpx.AsyncClient,
    contexto_residente: ContextoSesion,
    contexto_supervisor: ContextoSesion,
    contexto_super_intendente: ContextoSesion,
) -> None:
    plano_id, _, _ = await _plano_con_dos_trazos(cliente_control, escenario)

    for contexto in (contexto_residente, contexto_supervisor, contexto_super_intendente):
        async with _cliente(contexto) as cliente:
            assert (await cliente.get(f"/api/v1/obras/{escenario.obra_id}/planos")).status_code == 200
            assert (await cliente.get(f"/api/v1/planos/{plano_id}/trazos")).status_code == 200
            assert (
                await cliente.get(f"/api/v1/obras/{escenario.obra_id}/cuantificacion")
            ).status_code == 200
