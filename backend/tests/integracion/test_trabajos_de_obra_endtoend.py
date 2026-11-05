"""`GET /obras/{id}/trabajos`: los destajos de la receta de cada concepto de la obra, con su cuadrilla.

Contra Postgres real: el SQL (explosión, insumo, cuadrilla y su versión vigente), los derivados
(rendimiento calculado, jornadas por unidad, razón) y el acceso por rol.
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
async def cliente_control(contexto_control: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_control) as cliente:
        yield cliente


@pytest.fixture
async def cliente_residente(contexto_residente: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_residente) as cliente:
        yield cliente


async def _sembrar(escenario: Escenario) -> dict[str, str]:
    """Un concepto con dos líneas de destajo (una con cuadrilla y rendimiento, otra sin nada), una de
    material que no cuenta, y la actividad de la obra apuntando a él."""
    assert DATABASE_URL_ADMIN is not None
    org = str(escenario.org_id)
    ids = {k: str(uuid.uuid4()) for k in ("concepto", "d1", "d2", "mat", "cuad")}
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            async def q(sql: str, **p: object) -> None:
                await c.execute(text(sql), {"org": org, **p})

            await q("insert into concepto (id, org_id, clave, descripcion) values (:i, :org, 'CON-TRB', 'Muro de block')", i=ids["concepto"])
            await q("insert into cuadrilla (id, org_id, clave, nombre, costo_jornada) values (:i, :org, 'CUA-01', 'Cuadrilla de albañilería', 1500)", i=ids["cuad"])
            await q(
                "insert into insumo (id, org_id, tipo, clave, descripcion, costo_base, cuadrilla_id, rendimiento_teorico, origen_rendimiento) "
                "values (:i, :org, 'mano_obra', 'MOA-01', 'Levantado de muro', 100, :cu, 16, 'semilla')",
                i=ids["d1"], cu=ids["cuad"],
            )
            await q("insert into insumo (id, org_id, tipo, clave, descripcion, costo_base) values (:i, :org, 'subcontrato', 'SUB-01', 'Aplanado a destajo', 55)", i=ids["d2"])
            await q("insert into insumo (id, org_id, tipo, clave, descripcion, costo_base) values (:i, :org, 'material', 'MAT-01', 'Block', 12)", i=ids["mat"])
            for orden, (ins, cat, cant) in enumerate(((ids["d1"], "destajo", "1.0"), (ids["d2"], "subcontrato", "2.5"), (ids["mat"], "material", "13"))):
                await q(
                    "insert into explosion (org_id, concepto_id, tipo_hijo, insumo_id, categoria, cantidad, orden) "
                    "values (:org, :c, 'insumo', :ins, cast(:cat as categoria_explosion), cast(:cant as numeric), :o)",
                    c=ids["concepto"], ins=ins, cat=cat, cant=cant, o=orden,
                )
            await q("update actividad set concepto_id = :c, cant_base = 120 where id = :a", c=ids["concepto"], a=str(escenario.actividad_id))
    finally:
        await motor.dispose()
    return ids


async def test_trae_los_destajos_de_la_receta_con_su_cuadrilla_y_lo_derivado(
    escenario: Escenario, cliente_control: httpx.AsyncClient
) -> None:
    ids = await _sembrar(escenario)
    r = await cliente_control.get(f"/api/v1/obras/{escenario.obra_id}/trabajos")
    assert r.status_code == 200, r.text
    filas = {f["clave"]: f for f in r.json()}
    # El material no es un trabajo: solo destajo y subcontrato.
    assert set(filas) == {"MOA-01", "SUB-01"}

    muro = filas["MOA-01"]
    assert muro["concepto_clave"] == "CON-TRB" and Decimal(muro["cantidad_presupuestada"]) == 120
    assert Decimal(muro["factor"]) == 1 and muro["categoria"] == "destajo"
    assert muro["cuadrilla_nombre"] == "Cuadrilla de albañilería" and Decimal(muro["costo_cuadrilla"]) == 1500
    assert Decimal(muro["rendimiento_teorico"]) == 16
    # derivados: 1500 ÷ 100 = 15 de rendimiento calculado; 100 ÷ 1500 jornadas por unidad; razón 16 ÷ 15
    assert Decimal(muro["rendimiento_calculado"]) == 15
    assert abs(Decimal(muro["jornadas_por_unidad"]) - Decimal(100) / Decimal(1500)) < Decimal("0.0001")
    assert abs(Decimal(muro["razon_teorico_calculado"]) - Decimal(16) / Decimal(15)) < Decimal("0.0001")

    sub = filas["SUB-01"]
    assert Decimal(sub["factor"]) == Decimal("2.5") and sub["categoria"] == "subcontrato"
    # sin cuadrilla no hay nada que derivar, y no se inventa
    assert sub["cuadrilla_id"] is None and sub["rendimiento_calculado"] is None
    assert sub["razon_teorico_calculado"] is None
    assert ids["concepto"] == muro["concepto_id"]


async def test_una_obra_sin_conceptos_con_destajos_da_lista_vacia(
    escenario: Escenario, cliente_control: httpx.AsyncClient
) -> None:
    r = await cliente_control.get(f"/api/v1/obras/{escenario.obra_id}/trabajos")
    assert r.status_code == 200 and r.json() == []


async def test_el_costo_de_una_cuadrilla_es_del_catalogo_de_costos_y_el_residente_no_lo_ve(
    escenario: Escenario, cliente_residente: httpx.AsyncClient
) -> None:
    await _sembrar(escenario)
    r = await cliente_residente.get(f"/api/v1/obras/{escenario.obra_id}/trabajos")
    assert r.status_code == 403, r.text


async def test_otra_organizacion_no_ve_los_trabajos_de_esta_obra(escenario: Escenario) -> None:
    await _sembrar(escenario)
    ajeno = ContextoSesion(org_id=uuid.uuid4(), usuario_id=uuid.uuid4(), rol="control_obra")
    async with _cliente(ajeno) as cliente:
        r = await cliente.get(f"/api/v1/obras/{escenario.obra_id}/trabajos")
        assert r.status_code == 200 and r.json() == []


async def test_se_agrega_un_destajo_a_la_receta_de_un_concepto_y_aparece_en_los_trabajos_de_la_obra(
    escenario: Escenario, cliente_control: httpx.AsyncClient, cliente_residente: httpx.AsyncClient
) -> None:
    ids = await _sembrar(escenario)
    concepto = ids["concepto"]
    r = await cliente_control.post(
        f"/api/v1/conceptos/{concepto}/destajos",
        json={"descripcion": "Destajo de aplanado", "precio": "85.5", "factor": "1.2", "cuadrilla_id": ids["cuad"], "rendimiento_teorico": "9"},
    )
    assert r.status_code == 201, r.text
    nuevo = r.json()
    assert nuevo["clave"].startswith("MO-")

    trabajos = (await cliente_control.get(f"/api/v1/obras/{escenario.obra_id}/trabajos")).json()
    t = next(x for x in trabajos if x["insumo_id"] == nuevo["insumo_id"])
    assert Decimal(str(t["precio"])) == Decimal("85.5") and Decimal(str(t["factor"])) == Decimal("1.2")
    assert t["cuadrilla_id"] == ids["cuad"]

    # La clave repetida y el concepto inexistente se rechazan; un residente no cambia el catálogo.
    assert (await cliente_control.post(f"/api/v1/conceptos/{concepto}/destajos", json={"clave": nuevo["clave"], "descripcion": "Otro", "precio": "1"})).status_code == 422
    assert (await cliente_control.post(f"/api/v1/conceptos/{uuid.uuid4()}/destajos", json={"descripcion": "X", "precio": "1"})).status_code == 404
    assert (await cliente_residente.post(f"/api/v1/conceptos/{concepto}/destajos", json={"descripcion": "X", "precio": "1"})).status_code == 403

    # Quitarlo de la receta: el destajo deja de ser un trabajo del concepto.
    assert (await cliente_control.delete(f"/api/v1/conceptos/{concepto}/destajos/{nuevo['insumo_id']}")).status_code == 204
    assert (await cliente_control.delete(f"/api/v1/conceptos/{concepto}/destajos/{nuevo['insumo_id']}")).status_code == 404
    trabajos = (await cliente_control.get(f"/api/v1/obras/{escenario.obra_id}/trabajos")).json()
    assert all(x["insumo_id"] != nuevo["insumo_id"] for x in trabajos)
