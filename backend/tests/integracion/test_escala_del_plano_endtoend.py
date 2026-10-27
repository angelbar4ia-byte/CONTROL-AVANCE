"""La escala del plano (migración 0069) — por HTTP de punta a punta contra
Postgres real.

Sin escala, lo que mide el cuantificador está en unidades de plano —píxeles del
visor— y compararlo contra la `cant_base` del presupuesto (m², ml) no significa
nada. Lo que se fija aquí es lo que solo se ve cruzando router → caso de uso →
repositorio → PostGIS → RLS:

 1. calibrar con dos puntos y una distancia real fija los metros por unidad;
 2. el **área escala con el cuadrado**, los largos con la escala y el conteo no
    escala: la geometría guardada no se toca, la medida se lee ya escalada;
 3. calibrar recalcula los nodos que los trazos alimentan (lo que la pantalla
    verá como la cantidad nueva);
 4. se puede recalibrar: la última calibración manda;
 5. una calibración inválida se rechaza sin escribir nada;
 6. otra organización no la ve ni la toca.
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


def _cliente(contexto: ContextoSesion) -> httpx.AsyncClient:
    app = crear_app()
    app.dependency_overrides[contexto_actual] = lambda: contexto
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    )


@pytest.fixture
async def residente(contexto_residente: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_residente) as c:
        yield c


@pytest.fixture
async def ajeno(contexto_ajeno: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_ajeno) as c:
        yield c


@pytest.fixture(autouse=True)
async def _actividad_con_concepto(escenario: Escenario) -> None:
    """Le da a la actividad un concepto y un precio: sin eso no hay con qué armar
    la `Desviacion` que levanta una medida apartada de la base."""
    engine = create_async_engine(DATABASE_URL_ADMIN)
    concepto = uuid.uuid4()
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "insert into concepto (id, org_id, clave, descripcion) "
                    "values (:id, :org, 'ESC-1', 'Concepto de escala')"
                ),
                {"id": str(concepto), "org": str(escenario.org_id)},
            )
            await conn.execute(
                text(
                    "update actividad set concepto_id = :c, precio_unitario = 10, "
                    "cant_base = 100, cant_programada = 100 where id = :id"
                ),
                {"c": str(concepto), "id": str(escenario.actividad_id)},
            )
    finally:
        await engine.dispose()


async def _plano(cliente: httpx.AsyncClient, escenario: Escenario) -> str:
    respuesta = await cliente.post(
        f"/api/v1/obras/{escenario.obra_id}/planos",
        json={"nombre": "Planta", "archivo_url": "e2e/planta.pdf"},
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["id"]


async def _trazo(
    cliente: httpx.AsyncClient, escenario: Escenario, plano_id: str, wkt: str, medida: str
) -> dict:
    respuesta = await cliente.post(
        f"/api/v1/planos/{plano_id}/trazos",
        json={
            "version_plano": 1,
            "fuente": "pdf",
            "geometria_wkt": wkt,
            "enlaces": [
                {"medida": medida, "factor": "1", "actividad_id": str(escenario.actividad_id)}
            ],
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


async def _medida(cliente: httpx.AsyncClient, escenario: Escenario) -> Decimal:
    estado = (await cliente.get(f"/api/v1/obras/{escenario.obra_id}/cuantificacion")).json()
    nodo = next(n for n in estado if n["nodo_id"] == str(escenario.actividad_id))
    return Decimal(nodo["cantidad_medida"])


def _calibrar(cliente: httpx.AsyncClient, plano_id: str, metros: str, hasta: list[float] | None = None):
    return cliente.put(
        f"/api/v1/planos/{plano_id}/escala",
        json={"punto_a": [0, 0], "punto_b": hasta or [4, 0], "distancia_m": metros},
    )


async def test_sin_calibrar_la_medida_es_la_del_plano_y_lo_avisa(
    escenario: Escenario, residente: httpx.AsyncClient
) -> None:
    plano_id = await _plano(residente, escenario)
    await _trazo(residente, escenario, plano_id, "POLYGON((0 0, 4 0, 4 3, 0 3, 0 0))", "area")

    assert await _medida(residente, escenario) == 12
    [plano] = (await residente.get(f"/api/v1/obras/{escenario.obra_id}/planos")).json()
    assert plano["escala_m_por_unidad"] is None
    assert plano["escala_referencia"] is None


async def test_el_area_escala_con_el_cuadrado_y_se_recalcula_lo_que_alimenta(
    escenario: Escenario, residente: httpx.AsyncClient
) -> None:
    plano_id = await _plano(residente, escenario)
    await _trazo(residente, escenario, plano_id, "POLYGON((0 0, 4 0, 4 3, 0 3, 0 0))", "area")

    # 4 unidades de plano son 8 metros: cada unidad vale 2 m, el área ×4.
    respuesta = await _calibrar(residente, plano_id, "8")
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert Decimal(cuerpo["escala_m_por_unidad"]) == 2
    [recalculo] = cuerpo["recalculos"]
    assert Decimal(recalculo["cantidad_total"]) == 48

    assert await _medida(residente, escenario) == 48
    [plano] = (await residente.get(f"/api/v1/obras/{escenario.obra_id}/planos")).json()
    assert Decimal(plano["escala_m_por_unidad"]) == 2
    assert plano["escala_referencia"] == {
        "punto_a": [0, 0],
        "punto_b": [4, 0],
        "distancia_m": "8",
    }
    assert plano["escala_calibrada_en"] is not None

    # Los trazos del visor traen la escala, y su geometría sigue siendo la del plano.
    trazos = (await residente.get(f"/api/v1/planos/{plano_id}/trazos")).json()
    assert Decimal(trazos["escala_m_por_unidad"]) == 2
    assert trazos["features"][0]["geometry"]["coordinates"][0][1] == [4.0, 0.0]


async def test_un_largo_escala_lineal_y_un_conteo_no_escala(
    escenario: Escenario, residente: httpx.AsyncClient
) -> None:
    plano_id = await _plano(residente, escenario)
    # 3-4-5: la línea mide 5 unidades de plano.
    await _trazo(residente, escenario, plano_id, "LINESTRING(0 0, 3 4)", "longitud")
    assert await _medida(residente, escenario) == 5

    # 4 unidades son 2 m: cada unidad vale 0.5 m, el largo 5 → 2.5.
    assert (await _calibrar(residente, plano_id, "2")).status_code == 200
    assert await _medida(residente, escenario) == Decimal("2.5")

    # Un punto cuenta una instancia, valga lo que valga la unidad.
    await _trazo(residente, escenario, plano_id, "POINT(1 1)", "conteo")
    assert await _medida(residente, escenario) == Decimal("3.5")


async def test_recalibrar_corrige_y_la_ultima_manda(
    escenario: Escenario, residente: httpx.AsyncClient
) -> None:
    plano_id = await _plano(residente, escenario)
    await _trazo(residente, escenario, plano_id, "POLYGON((0 0, 4 0, 4 3, 0 3, 0 0))", "area")

    assert (await _calibrar(residente, plano_id, "8")).status_code == 200
    assert await _medida(residente, escenario) == 48

    # Se equivocó de cota: 4 unidades son 2 m. El área baja a 12 × 0.25 = 3.
    assert (await _calibrar(residente, plano_id, "2")).status_code == 200
    assert await _medida(residente, escenario) == 3
    [plano] = (await residente.get(f"/api/v1/obras/{escenario.obra_id}/planos")).json()
    assert Decimal(plano["escala_m_por_unidad"]) == Decimal("0.5")


async def test_una_calibracion_invalida_se_rechaza_y_no_escribe(
    escenario: Escenario, residente: httpx.AsyncClient
) -> None:
    plano_id = await _plano(residente, escenario)
    await _trazo(residente, escenario, plano_id, "POLYGON((0 0, 4 0, 4 3, 0 3, 0 0))", "area")

    # Dos puntos iguales, distancia cero y una escala implausible (metros por
    # centímetros): ninguna se acepta.
    assert (await _calibrar(residente, plano_id, "8", hasta=[0, 0])).status_code == 422
    assert (await _calibrar(residente, plano_id, "0")).status_code == 422
    assert (await _calibrar(residente, plano_id, "100000")).status_code == 422

    assert await _medida(residente, escenario) == 12
    [plano] = (await residente.get(f"/api/v1/obras/{escenario.obra_id}/planos")).json()
    assert plano["escala_m_por_unidad"] is None


async def test_otra_organizacion_no_ve_ni_calibra(
    escenario: Escenario, residente: httpx.AsyncClient, ajeno: httpx.AsyncClient
) -> None:
    plano_id = await _plano(residente, escenario)
    assert (await _calibrar(ajeno, plano_id, "8")).status_code == 404
    [plano] = (await residente.get(f"/api/v1/obras/{escenario.obra_id}/planos")).json()
    assert plano["escala_m_por_unidad"] is None
