"""Ver las desviaciones de una obra y capturar su causa (cerebro MODELO.md §5g).

El cuantificador escribía desviaciones y nada las mostraba: la regla de captura 4
—«la causa se agrega después, sin penalizar»— no tenía por dónde cumplirse. Por
HTTP de punta a punta contra Postgres real:

 1. la lista trae las desviaciones **con y sin causa**: «sin causa» es un estado
    válido, no un dato faltante;
 2. cada una dice qué causas caben en su factor (`precio` o `consumo`);
 3. capturar la causa la deja con quién y cuándo; también se puede corregir;
 4. una causa del otro factor se rechaza (422) y no escribe nada;
 5. otra organización no ve ni toca nada.
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
async def control(contexto_control: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_control) as c:
        yield c


@pytest.fixture
async def ajeno(contexto_ajeno: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_ajeno) as c:
        yield c


@pytest.fixture
async def desviaciones(escenario: Escenario) -> dict[str, uuid.UUID]:
    """Una de consumo (sobre un concepto) y una de precio (sobre un insumo), las
    dos sin causa — como las deja el cuantificador."""
    engine = create_async_engine(DATABASE_URL_ADMIN)
    insumo, concepto = uuid.uuid4(), uuid.uuid4()
    consumo, precio = uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "insert into insumo (id, org_id, tipo, clave, descripcion) "
                "values (:id, :org, 'material', 'CEM-01', 'Cemento gris')"
            ),
            {"id": str(insumo), "org": str(escenario.org_id)},
        )
        await conn.execute(
            text(
                "insert into concepto (id, org_id, clave, descripcion) "
                "values (:id, :org, 'EST-001', 'Castillo de concreto')"
            ),
            {"id": str(concepto), "org": str(escenario.org_id)},
        )
        await conn.execute(
            text(
                """
                insert into desviacion (id, org_id, obra_id, tipo_nodo, concepto_id,
                                        tipo, monto, cantidad_plan, cantidad_real)
                values (:id, :org, :obra, 'concepto', :nodo, 'consumo', 2000, 100, 120)
                """
            ),
            {
                "id": str(consumo),
                "org": str(escenario.org_id),
                "obra": str(escenario.obra_id),
                "nodo": str(concepto),
            },
        )
        await conn.execute(
            text(
                """
                insert into desviacion (id, org_id, obra_id, tipo_nodo, insumo_id,
                                        tipo, monto, precio_plan, precio_real)
                values (:id, :org, :obra, 'insumo', :nodo, 'precio', 500, 10, 12)
                """
            ),
            {
                "id": str(precio),
                "org": str(escenario.org_id),
                "obra": str(escenario.obra_id),
                "nodo": str(insumo),
            },
        )
    yield {"consumo": consumo, "precio": precio}
    await engine.dispose()


async def _lista(cliente: httpx.AsyncClient, escenario: Escenario) -> dict[str, dict]:
    respuesta = await cliente.get(f"/api/v1/obras/{escenario.obra_id}/desviaciones")
    assert respuesta.status_code == 200, respuesta.text
    return {fila["tipo"]: fila for fila in respuesta.json()}


async def test_la_lista_trae_las_desviaciones_sin_causa_y_dice_que_causas_caben(
    escenario: Escenario, desviaciones: dict, residente: httpx.AsyncClient
) -> None:
    por_tipo = await _lista(residente, escenario)
    assert set(por_tipo) == {"consumo", "precio"}

    consumo = por_tipo["consumo"]
    assert consumo["causa"] is None  # «sin causa» es un estado válido
    assert consumo["tipo_nodo"] == "concepto"
    assert consumo["nodo_clave"] == "EST-001"
    assert Decimal(consumo["monto"]) == 2000
    assert Decimal(consumo["cantidad_plan"]) == 100
    assert Decimal(consumo["cantidad_real"]) == 120
    assert "retrabajo" in consumo["causas_posibles"]
    assert "mercado" not in consumo["causas_posibles"]  # esa es de precio

    precio = por_tipo["precio"]
    assert precio["tipo_nodo"] == "insumo"
    assert precio["nodo_clave"] == "CEM-01"
    assert "mercado" in precio["causas_posibles"]
    assert "retrabajo" not in precio["causas_posibles"]


async def test_capturar_la_causa_deja_quien_y_cuando_y_se_puede_corregir(
    escenario: Escenario, desviaciones: dict, residente: httpx.AsyncClient, control: httpx.AsyncClient
) -> None:
    url = f"/api/v1/desviaciones/{desviaciones['consumo']}/causa"

    ok = await residente.put(url, json={"causa": "retrabajo"})
    assert ok.status_code == 204, ok.text

    consumo = (await _lista(residente, escenario))["consumo"]
    assert consumo["causa"] == "retrabajo"
    assert consumo["causa_capturada_por"] == "Rosa Residente" or consumo["causa_capturada_por"]
    assert consumo["causa_capturada_en"] is not None
    # La otra desviación sigue sin causa: capturar una no toca la otra.
    assert (await _lista(residente, escenario))["precio"]["causa"] is None

    # Corregir: otra persona, otra causa.
    corregida = await control.put(url, json={"causa": "rendimiento_real_distinto"})
    assert corregida.status_code == 204, corregida.text
    assert (await _lista(control, escenario))["consumo"]["causa"] == "rendimiento_real_distinto"


async def test_una_causa_del_otro_factor_se_rechaza_y_no_escribe(
    escenario: Escenario, desviaciones: dict, residente: httpx.AsyncClient
) -> None:
    # `mercado` es una causa de precio; esta fila es de consumo.
    mala = await residente.put(
        f"/api/v1/desviaciones/{desviaciones['consumo']}/causa", json={"causa": "mercado"}
    )
    assert mala.status_code == 422, mala.text
    assert (await _lista(residente, escenario))["consumo"]["causa"] is None

    # Una causa fuera del vocabulario controlado ni siquiera entra.
    fuera = await residente.put(
        f"/api/v1/desviaciones/{desviaciones['consumo']}/causa", json={"causa": "porque_si"}
    )
    assert fuera.status_code == 422


async def test_otra_organizacion_no_ve_ni_toca_nada(
    escenario: Escenario, desviaciones: dict, ajeno: httpx.AsyncClient
) -> None:
    lista = await ajeno.get(f"/api/v1/obras/{escenario.obra_id}/desviaciones")
    assert lista.status_code == 404

    captura = await ajeno.put(
        f"/api/v1/desviaciones/{desviaciones['consumo']}/causa", json={"causa": "retrabajo"}
    )
    assert captura.status_code == 404
