"""Cómo cuenta un trazo para su concepto (D-633): la conversión del enlace, por HTTP contra Postgres real.

Un muro de 10 m de eje y 0.15 m de grosor sobre un concepto en m²; un área de 4 × 3 m. La cantidad la calcula la base
(`app.cantidad_conversion`): la vista previa y lo que se guarda al aplicar son la misma cuenta.
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
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test")


@pytest.fixture
async def control(contexto_control: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_control) as c:
        yield c


@pytest.fixture
async def residente(contexto_residente: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_residente) as c:
        yield c


@pytest.fixture(autouse=True)
async def _concepto_en_m2(escenario: Escenario) -> None:
    motor = create_async_engine(DATABASE_URL_ADMIN)
    unidad, concepto = uuid.uuid4(), uuid.uuid4()
    try:
        async with motor.begin() as c:
            await c.execute(text("insert into unidad (id, org_id, clave, nombre) values (:i, :o, 'm2', 'Metro cuadrado')"), {"i": str(unidad), "o": str(escenario.org_id)})
            await c.execute(text("insert into concepto (id, org_id, clave, descripcion, unidad_id) values (:i, :o, 'CNV-1', 'Aplanado', :u)"), {"i": str(concepto), "o": str(escenario.org_id), "u": str(unidad)})
            await c.execute(
                text("update actividad set concepto_id = :c, precio_unitario = 10, cant_base = 100, cant_programada = 100 where id = :id"),
                {"c": str(concepto), "id": str(escenario.actividad_id)},
            )
    finally:
        await motor.dispose()


async def _trazo(control: httpx.AsyncClient, escenario: Escenario, plano: str, wkt: str, medida: str, *, grosor: str | None = None) -> str:
    cuerpo = {
        "version_plano": 1, "fuente": "pdf", "geometria_wkt": wkt,
        "enlaces": [{"medida": medida, "factor": "1", "actividad_id": str(escenario.actividad_id)}],
    }
    if grosor:
        cuerpo |= {"grosor_m": grosor, "alineacion": "centro"}
    r = await control.post(f"/api/v1/planos/{plano}/trazos", json=cuerpo)
    assert r.status_code == 201, r.text
    return r.json()["trazo_id"]


async def _enlace_vigente(control: httpx.AsyncClient, plano: str, trazo: str) -> str:
    f = next(x for x in (await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"] if x["id"] == trazo)
    return next(e["enlace_id"] for e in f["properties"]["enlaces"] if e["vigente"])


async def _plano(control: httpx.AsyncClient, escenario: Escenario) -> str:
    return (await control.post(f"/api/v1/obras/{escenario.obra_id}/planos", json={"nombre": "P", "archivo_url": "e2e/p.pdf"})).json()["id"]


async def test_un_muro_cuenta_por_largo_area_volumen_o_piezas(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano = await _plano(control, escenario)
    muro = await _trazo(control, escenario, plano, "LINESTRING(0 0, 10 0)", "longitud", grosor="0.15")
    enlace = await _enlace_vigente(control, plano, muro)
    ruta = f"/api/v1/enlaces/{enlace}/conversion"

    info = (await control.get(ruta)).json()
    assert info["tipo"] == "muro" and info["unidad_del_concepto"] == "m2"
    assert [m["clave"] for m in info["modos"]] == ["largo", "area", "vol", "pza"]
    assert info["conversion"]["modo"] == "area" and info["es_la_de_hoy"] is False  # el concepto es de m²

    async def calcula(**c: object) -> dict:
        r = await control.post(f"{ruta}/calcular", json=c)
        assert r.status_code == 200, r.text
        return r.json()

    # Largo, y área por eje, una cara o dos (tu captura: 5 m int. + 5 m ext. × 2.6 m, aquí con 10 m).
    assert (await calcula(modo="largo"))["valor"] == pytest.approx(10)
    eje = await calcula(modo="area", mide="eje", alt=2.6)
    assert eje["valor"] == pytest.approx(26) and eje["unidad"] == "m²" and eje["coincide"] is True
    dos = await calcula(modo="area", mide="cara2", alt=2.6)
    assert dos["valor"] == pytest.approx(52) and "m int." in dos["formula"] and "× 2.6 m" in dos["formula"]
    assert (await calcula(modo="area", mide="cara1", alt=2.6))["valor"] == pytest.approx(26)
    # Volumen (largo × altura × grosor) y piezas (⌈largo ÷ separación⌉ + 1).
    assert (await calcula(modo="vol", alt=2.6, gro=0.15))["valor"] == pytest.approx(10 * 2.6 * 0.15)
    pza = await calcula(modo="pza", sep=2.5)
    assert pza["valor"] == 5 and pza["unidad"] == "pza" and pza["coincide"] is False  # ⚠ distinta unidad

    # Altura por partes: lo que no suma cuenta para la altura pero no para la cantidad.
    partes = [{"nombre": "Muro", "desde_m": 0, "hasta_m": 2.3, "suma": True}, {"nombre": "Cerramiento", "desde_m": 2.3, "hasta_m": 2.5, "suma": False}]
    assert (await calcula(modo="area", mide="eje", partes=partes))["valor"] == pytest.approx(23)

    # Un modo que el tipo no admite o una parte al revés se rechazan.
    assert (await control.post(f"{ruta}/calcular", json={"modo": "perim"})).status_code == 422
    assert (await control.post(f"{ruta}/calcular", json={"modo": "area", "partes": [{"desde_m": 2, "hasta_m": 1}]})).status_code == 422


async def test_las_caras_miden_el_largo_real_de_cada_lado_en_una_esquina(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano = await _plano(control, escenario)
    # Un muro en L: 10 m y 10 m. Con grosor 0.2 las caras son 10.1+10.1 o 9.9+9.9 según el lado (esquina en inglete).
    muro = await _trazo(control, escenario, plano, "LINESTRING(0 0, 10 0, 10 10)", "longitud", grosor="0.2")
    ruta = f"/api/v1/enlaces/{await _enlace_vigente(control, plano, muro)}/conversion/calcular"
    der = (await control.post(ruta, json={"modo": "area", "mide": "cara2", "alt": 1.0, "lado": "der"})).json()["componentes"]
    izq = (await control.post(ruta, json={"modo": "area", "mide": "cara2", "alt": 1.0, "lado": "izq"})).json()["componentes"]
    interior, exterior = sorted([der["cara_interior"], der["cara_exterior"]])
    assert interior == pytest.approx(19.8, abs=0.01) and exterior == pytest.approx(20.2, abs=0.01)
    # Cambiar «interior a la izquierda/derecha» intercambia las caras y la suma de las dos no cambia.
    assert izq["cara_interior"] == pytest.approx(der["cara_exterior"], abs=0.001)
    assert izq["base"] == pytest.approx(der["base"], abs=0.001)


async def test_un_area_cuenta_por_area_volumen_piezas_o_perimetro(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano = await _plano(control, escenario)
    area = await _trazo(control, escenario, plano, "POLYGON((0 0, 4 0, 4 3, 0 3, 0 0))", "area")
    ruta = f"/api/v1/enlaces/{await _enlace_vigente(control, plano, area)}/conversion"
    assert [m["clave"] for m in (await control.get(ruta)).json()["modos"]] == ["area", "vol", "pza", "perim"]

    async def calcula(**c: object) -> dict:
        return (await control.post(f"{ruta}/calcular", json=c)).json()

    assert (await calcula(modo="area"))["valor"] == pytest.approx(12)
    assert (await calcula(modo="vol", esp=0.12, desc=0.1))["valor"] == pytest.approx(12 * 0.12 - 0.1)
    assert (await calcula(modo="pza", pw=0.6, ph=0.6, merma=5))["valor"] == 35  # ⌈12 ÷ 0.36 × 1.05⌉
    assert (await calcula(modo="perim", alt=2.6))["valor"] == pytest.approx(14 * 2.6)
    ml = await calcula(modo="perim", alt=0)
    assert ml["valor"] == pytest.approx(14) and ml["unidad"] == "ml"


async def test_aplicar_crea_un_enlace_nuevo_y_el_anterior_queda_como_evidencia(
    escenario: Escenario, control: httpx.AsyncClient, residente: httpx.AsyncClient
) -> None:
    plano = await _plano(control, escenario)
    m1 = await _trazo(control, escenario, plano, "LINESTRING(0 0, 10 0)", "longitud", grosor="0.15")
    m2 = await _trazo(control, escenario, plano, "LINESTRING(0 5, 10 5)", "longitud", grosor="0.15")
    e1 = await _enlace_vigente(control, plano, m1)
    cuerpo = {"conversion": {"modo": "area", "mide": "cara2", "alt": 2.6}, "a_todos": False}
    r = await control.post(f"/api/v1/enlaces/{e1}/conversion", json=cuerpo)
    assert r.status_code == 200, r.text
    assert r.json()["aplicados"] == 1

    f1 = next(x for x in (await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"] if x["id"] == m1)
    enlaces = f1["properties"]["enlaces"]
    assert [e["vigente"] for e in enlaces] == [False, True]  # el anterior queda como evidencia
    assert Decimal(str(enlaces[1]["cantidad"])) == Decimal("52")  # 10 m × 2.6 m × 2 caras
    assert (await control.get(f"/api/v1/enlaces/{enlaces[1]['enlace_id']}/conversion")).json()["es_la_de_hoy"] is True

    # El enlace reemplazado ya no se puede volver a aplicar; con «a todos» entra el otro muro del concepto.
    assert (await control.post(f"/api/v1/enlaces/{e1}/conversion", json=cuerpo)).status_code == 422
    r = await control.post(f"/api/v1/enlaces/{enlaces[1]['enlace_id']}/conversion", json={**cuerpo, "a_todos": True})
    assert r.status_code == 200 and r.json()["aplicados"] == 2
    f2 = next(x for x in (await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"] if x["id"] == m2)
    assert any(e["vigente"] and Decimal(str(e["cantidad"])) == Decimal("52") for e in f2["properties"]["enlaces"])

    # Un vano descuenta por las caras de la conversión: 0.9 × 2.1 × 2 = 3.78 m².
    v = await control.post(f"/api/v1/trazos/{m1}/vanos", json={"clave": "P-01", "tipo": "puerta", "ancho_m": "0.9", "alto_m": "2.1"})
    assert v.status_code == 201
    f1 = next(x for x in (await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"] if x["id"] == m1)
    vigente = next(e for e in f1["properties"]["enlaces"] if e["vigente"])
    assert Decimal(str(vigente["cantidad"])).quantize(Decimal("0.01")) == Decimal("48.22")


async def test_una_forma_y_un_punto_cuentan_por_piezas_area_o_volumen(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano = await _plano(control, escenario)
    # Un castillo de 0.15 × 0.15 m estampado: una forma; y un punto suelto.
    cuerpo = {
        "version_plano": 1, "fuente": "pdf",
        "geometria_wkt": "POLYGON((0 0, 0.15 0, 0.15 0.15, 0 0.15, 0 0))",
        "forma": {"tipo": "cuadrado", "ancho_m": "0.15", "alto_m": "0.15", "rotacion_grados": "0"},
        "enlaces": [{"medida": "conteo", "factor": "1", "actividad_id": str(escenario.actividad_id)}],
    }
    r = await control.post(f"/api/v1/planos/{plano}/trazos", json=cuerpo)
    assert r.status_code == 201, r.text
    forma = r.json()["trazo_id"]
    ruta = f"/api/v1/enlaces/{await _enlace_vigente(control, plano, forma)}/conversion"
    info = (await control.get(ruta)).json()
    assert info["tipo"] == "forma" and [m["clave"] for m in info["modos"]] == ["pza", "area", "vol"]

    async def calcula(**c: object) -> dict:
        return (await control.post(f"{ruta}/calcular", json=c)).json()

    assert (await calcula(modo="pza"))["valor"] == 1
    assert (await calcula(modo="area"))["valor"] == pytest.approx(0.0225)
    vol = await calcula(modo="vol", alt=2.6)
    assert vol["valor"] == pytest.approx(0.0225 * 2.6) and vol["unidad"] == "m³" and "× 2.6 m" in vol["formula"]
    assert (await calcula(modo="area"))["componentes"]["huecos"] == 0

    punto = await _trazo(control, escenario, plano, "POINT(3 3)", "conteo")
    ruta_p = f"/api/v1/enlaces/{await _enlace_vigente(control, plano, punto)}/conversion"
    ip = (await control.get(ruta_p)).json()
    assert ip["tipo"] == "punto" and [m["clave"] for m in ip["modos"]] == ["pza"]
    assert (await control.post(f"{ruta_p}/calcular", json={"modo": "pza"})).json()["valor"] == 1
    assert (await control.post(f"{ruta_p}/calcular", json={"modo": "area"})).status_code == 422
