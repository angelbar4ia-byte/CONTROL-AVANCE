"""La altura BASE de un muro del plano y Q1: lo ya guardado CONSERVA su altura (desacople del plano del driver `altura_estandar`).

La altura de un muro trazado sale, en este orden: la explícita del trazo (partes o `muro_altura_m`) > la zona de losa > la altura base de
su ARTEFACTO (la `altura_m` de la plantilla de muro que eligió) > la de la HERRAMIENTA de trazo (3.00 m). El driver `altura_estandar`
de Paramétrico NO interviene: cambiarlo (global o por obra) no mueve nada del plano. Lo que ya trae su altura (un muro fijado, una
conversión guardada con `alt`, un vano ya colocado) no se mueve; los trazos viejos sin altura guardada contaban 2.6 m y la
migración 0134 se los fija.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.api.dependencias import contexto_actual
from obractrl.infrastructure.db.sesion import ContextoSesion
from obractrl.main import crear_app
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario

MURO = "LINESTRING(0 0, 10 0)"
CASTILLO = {"clave": "K-01", "tipo": "castillo", "ancho_m": "0.15", "alto_m": "1", "posicion_m": "3"}
MIGRACION = Path(__file__).resolve().parents[3] / "database" / "migrations" / "20260814000134_parametrico_drivers_y_enlaces.sql"


def _cliente(contexto: ContextoSesion) -> httpx.AsyncClient:
    app = crear_app()
    app.dependency_overrides[contexto_actual] = lambda: contexto
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test")


@pytest.fixture
async def control(contexto_control: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_control) as c:
        yield c


@pytest.fixture
async def costos(escenario: Escenario) -> AsyncIterator[httpx.AsyncClient]:
    usuario = uuid.uuid4()
    motor = create_async_engine(DATABASE_URL_ADMIN)
    async with motor.begin() as c:
        await c.execute(
            text("insert into usuario (id, org_id, nombre, email, rol) values (:i, :o, 'Costos', :e, 'costos')"),
            {"i": str(usuario), "o": str(escenario.org_id), "e": f"costos-{usuario.hex[:8]}@t.mx"},
        )
    await motor.dispose()
    async with _cliente(ContextoSesion(org_id=escenario.org_id, usuario_id=usuario, rol="costos")) as c:
        yield c


@pytest.fixture(autouse=True)
async def _concepto_en_m2(escenario: Escenario) -> None:
    motor = create_async_engine(DATABASE_URL_ADMIN)
    unidad, concepto = uuid.uuid4(), uuid.uuid4()
    try:
        async with motor.begin() as c:
            await c.execute(text("insert into unidad (id, org_id, clave, nombre) values (:i, :o, 'm2', 'Metro cuadrado')"), {"i": str(unidad), "o": str(escenario.org_id)})
            await c.execute(text("insert into concepto (id, org_id, clave, descripcion, unidad_id) values (:i, :o, 'ALT-1', 'Aplanado', :u)"), {"i": str(concepto), "o": str(escenario.org_id), "u": str(unidad)})
            await c.execute(
                text("update actividad set concepto_id = :c, precio_unitario = 10, cant_base = 100, cant_programada = 100 where id = :id"),
                {"c": str(concepto), "id": str(escenario.actividad_id)},
            )
    finally:
        await motor.dispose()


async def _muro(control: httpx.AsyncClient, escenario: Escenario, plano: str | None = None) -> tuple[str, str]:
    if plano is None:
        plano = (await control.post(f"/api/v1/obras/{escenario.obra_id}/planos", json={"nombre": "P", "archivo_url": "e2e/p.pdf"})).json()["id"]
    r = await control.post(
        f"/api/v1/planos/{plano}/trazos",
        json={
            "version_plano": 1, "fuente": "pdf", "geometria_wkt": MURO, "grosor_m": "0.15", "alineacion": "centro",
            "enlaces": [{"medida": "longitud", "factor": "1", "actividad_id": str(escenario.actividad_id)}],
        },
    )
    assert r.status_code == 201, r.text
    return plano, r.json()["trazo_id"]


async def _castillo_alto(control: httpx.AsyncClient, trazo: str) -> Decimal:
    await control.put(f"/api/v1/trazos/{trazo}/muro/clasificacion", json={"tipo": "con_cadena"})
    r = await control.post(f"/api/v1/trazos/{trazo}/vanos", json=CASTILLO)
    assert r.status_code == 201, r.text
    (v,) = (await control.get(f"/api/v1/trazos/{trazo}/vanos")).json()
    return Decimal(str(v["alto_m"]))


async def _plantilla(control: httpx.AsyncClient, altura: str | None) -> str:
    r = await control.post(
        "/api/v1/muro-plantillas",
        json={"nombre": f"Base {uuid.uuid4().hex[:6]}", "tipo": "con_cadena", "material": "tabique_rojo", "ubicacion": "interior", "altura_m": altura},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_el_driver_altura_estandar_no_mueve_la_altura_de_un_muro_del_plano(escenario: Escenario, control: httpx.AsyncClient, costos: httpx.AsyncClient) -> None:
    _, muro = await _muro(control, escenario)
    m = (await control.get(f"/api/v1/trazos/{muro}/muro")).json()
    assert m["altura_m"] is None and Decimal(m["altura_efectiva_m"]) == Decimal("3")  # la herramienta: 3.00 m
    # Ni el global ni el ajuste de la obra la tocan; tampoco lo alto de un castillo.
    await costos.put("/api/v1/drivers/altura_estandar", json={"valor": "2.9"})
    await costos.put(f"/api/v1/obras/{escenario.obra_id}/drivers/altura_estandar", json={"valor": "2.5"})
    assert Decimal((await control.get(f"/api/v1/trazos/{muro}/muro")).json()["altura_efectiva_m"]) == Decimal("3")
    assert await _castillo_alto(control, muro) == Decimal("3")


async def test_la_altura_base_del_artefacto_manda_sobre_la_de_la_herramienta(escenario: Escenario, control: httpx.AsyncClient, costos: httpx.AsyncClient) -> None:
    plano, muro = await _muro(control, escenario)
    plantilla = await _plantilla(control, "2.8")
    assert (await control.put(f"/api/v1/trazos/{muro}/muro/plantilla", json={"plantilla_id": plantilla})).status_code == 200
    ruta = f"/api/v1/trazos/{muro}/muro"
    assert Decimal((await control.get(ruta)).json()["altura_efectiva_m"]) == Decimal("2.8")
    # Colocar la plantilla en el plano usa esa misma altura.
    assert Decimal((await control.get(f"/api/v1/trazos/{muro}/muro/plantilla/colocacion")).json()["altura_m"]) == Decimal("2.8")
    # Sin altura en la plantilla vuelve la de la herramienta; el driver sigue sin intervenir.
    _, otro = await _muro(control, escenario, plano)
    sin_altura = await _plantilla(control, None)
    await control.put(f"/api/v1/trazos/{otro}/muro/plantilla", json={"plantilla_id": sin_altura})
    await costos.put(f"/api/v1/obras/{escenario.obra_id}/drivers/altura_estandar", json={"valor": "2.2"})
    assert Decimal((await control.get(f"/api/v1/trazos/{otro}/muro")).json()["altura_efectiva_m"]) == Decimal("3")
    # La explícita del trazo manda sobre la del artefacto.
    await control.put(ruta, json={"altura_m": "2.4", "caras": 2})
    assert Decimal((await control.get(ruta)).json()["altura_efectiva_m"]) == Decimal("2.4")


async def test_un_muro_ya_fijado_conserva_su_altura_aunque_cambie_la_plantilla_o_el_driver(escenario: Escenario, control: httpx.AsyncClient, costos: httpx.AsyncClient) -> None:
    plano, fijado = await _muro(control, escenario)
    ruta = f"/api/v1/trazos/{fijado}/muro"
    # Se fija sin altura: nace con la base del momento (3 m) y la GUARDA.
    r = await control.put(ruta, json={"caras": 2})
    assert r.status_code == 200, r.text
    assert Decimal((await control.get(ruta)).json()["altura_m"]) == Decimal("3")
    # Otro muro se fija con su altura propia.
    _, propio = await _muro(control, escenario, plano)
    await control.put(f"/api/v1/trazos/{propio}/muro", json={"altura_m": "2.6", "caras": 2})
    # Cambia el driver (global y de la obra) y luego la plantilla: ninguno de los dos se mueve.
    await costos.put("/api/v1/drivers/altura_estandar", json={"valor": "3.5"})
    await costos.put(f"/api/v1/obras/{escenario.obra_id}/drivers/altura_estandar", json={"valor": "4"})
    plantilla = await _plantilla(control, "3.3")
    await control.put(f"/api/v1/trazos/{fijado}/muro/plantilla", json={"plantilla_id": plantilla})
    assert Decimal((await control.get(ruta)).json()["altura_efectiva_m"]) == Decimal("3")
    assert Decimal((await control.get(f"/api/v1/trazos/{propio}/muro")).json()["altura_efectiva_m"]) == Decimal("2.6")
    assert await _castillo_alto(control, fijado) == Decimal("3")
    assert await _castillo_alto(control, propio) == Decimal("2.6")


async def test_la_conversion_nueva_propone_la_base_y_la_guardada_sin_altura_cuenta_2_6(escenario: Escenario, control: httpx.AsyncClient, costos: httpx.AsyncClient) -> None:
    plano, muro = await _muro(control, escenario)
    f = next(x for x in (await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"] if x["id"] == muro)
    enlace = next(e["enlace_id"] for e in f["properties"]["enlaces"] if e["vigente"])
    ruta = f"/api/v1/enlaces/{enlace}/conversion"
    # Lo que se propone al abrir el panel: la altura de la herramienta; el driver de la obra no la cambia.
    assert (await control.get(ruta)).json()["conversion"]["alt"] == 3
    r = await costos.put(f"/api/v1/obras/{escenario.obra_id}/drivers/altura_estandar", json={"valor": "2.8"})
    assert r.status_code == 200, r.text
    assert (await control.get(ruta)).json()["conversion"]["alt"] == 3
    # Con plantilla de altura base 2.7, lo que se propone es esa.
    await control.put(f"/api/v1/trazos/{muro}/muro/plantilla", json={"plantilla_id": await _plantilla(control, "2.7")})
    assert (await control.get(ruta)).json()["conversion"]["alt"] == 2.7
    # La cuenta de la base con la altura dicha es esa altura; una conversión guardada antes del driver, sin `alt`, sigue en 2.6.
    con = await control.post(f"{ruta}/calcular", json={"modo": "area", "mide": "eje", "alt": 3})
    assert con.json()["valor"] == pytest.approx(30)
    sin = await control.post(f"{ruta}/calcular", json={"modo": "area", "mide": "eje"})
    assert sin.json()["valor"] == pytest.approx(26)


async def test_la_migracion_fija_2_6_a_las_lineas_viejas_sin_altura(escenario: Escenario, control: httpx.AsyncClient) -> None:
    """Q1: el UPDATE de la 0134 se corre contra un trazo «viejo» (línea sin altura ni partes) y le deja los 2.6 m que ya contaba;
    una línea con su altura, con partes o un área no se tocan."""
    plano, viejo = await _muro(control, escenario)
    _, con_altura = await _muro(control, escenario, plano)
    await control.put(f"/api/v1/trazos/{con_altura}/muro", json={"altura_m": "2.2", "caras": 2})
    sql = re.search(r"update trazo\s+set muro_altura_m = 2\.6.*?;", MIGRACION.read_text(encoding="utf-8"), re.S)
    assert sql is not None
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            await c.execute(text("update trazo set muro_altura_m = null where id = :t"), {"t": viejo})
            await c.execute(text(sql.group(0)))
            alturas = {
                str(f["id"]): f["muro_altura_m"]
                for f in (await c.execute(text("select id, muro_altura_m from trazo where id in (:a, :b)"), {"a": viejo, "b": con_altura})).mappings()
            }
    finally:
        await motor.dispose()
    assert Decimal(alturas[viejo]) == Decimal("2.6") and Decimal(alturas[con_altura]) == Decimal("2.2")
    # Ya con la altura fijada, el driver no lo mueve.
    assert Decimal((await control.get(f"/api/v1/trazos/{viejo}/muro")).json()["altura_efectiva_m"]) == Decimal("2.6")


async def test_un_muro_medido_con_su_conversion_conserva_esa_altura_para_el_castillo(escenario: Escenario, control: httpx.AsyncClient, costos: httpx.AsyncClient) -> None:
    """Q1: la conversión guardada (alt 2.6, la del plano) es la altura con que ya se mide el muro; el castillo y el muro la
    conservan aunque la plantilla diga 3.2 m. Un muro sin conversión con altura sí sigue a su artefacto."""
    plano, medido = await _muro(control, escenario)
    _, nuevo = await _muro(control, escenario, plano)
    f = next(x for x in (await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"] if x["id"] == medido)
    enlace = next(e["enlace_id"] for e in f["properties"]["enlaces"] if e["vigente"])
    r = await control.post(f"/api/v1/enlaces/{enlace}/conversion", json={"conversion": {"modo": "area", "mide": "cara2", "alt": 2.6}, "a_todos": False})
    assert r.status_code == 200, r.text
    plantilla = await _plantilla(control, "3.2")
    for t in (medido, nuevo):
        await control.put(f"/api/v1/trazos/{t}/muro/plantilla", json={"plantilla_id": plantilla})
    await costos.put("/api/v1/drivers/altura_estandar", json={"valor": "2.1"})
    assert Decimal((await control.get(f"/api/v1/trazos/{medido}/muro")).json()["altura_efectiva_m"]) == Decimal("2.6")
    assert Decimal((await control.get(f"/api/v1/trazos/{nuevo}/muro")).json()["altura_efectiva_m"]) == Decimal("3.2")
    assert await _castillo_alto(control, medido) == Decimal("2.6")


async def test_una_conversion_nueva_sin_altura_nace_con_la_base_y_despues_no_se_mueve(escenario: Escenario, control: httpx.AsyncClient, costos: httpx.AsyncClient) -> None:
    """Un trazo que nace con su conversión pero sin `alt` toma la altura de la herramienta (3.00 m; el driver de la obra ya no cuenta) y la
    GUARDA; con `alt` o con partes se respeta lo dicho."""
    await costos.put(f"/api/v1/obras/{escenario.obra_id}/drivers/altura_estandar", json={"valor": "2.5"})
    plano = (await control.post(f"/api/v1/obras/{escenario.obra_id}/planos", json={"nombre": "P", "archivo_url": "e2e/p.pdf"})).json()["id"]

    async def trazar(conversion: dict) -> str:
        r = await control.post(
            f"/api/v1/planos/{plano}/trazos",
            json={
                "version_plano": 1, "fuente": "pdf", "geometria_wkt": MURO,
                "enlaces": [{"medida": "longitud", "factor": "1", "actividad_id": str(escenario.actividad_id), "conversion": conversion}],
            },
        )
        assert r.status_code == 201, r.text
        return r.json()["trazo_id"]

    async def cantidad(trazo: str) -> float:
        f = next(x for x in (await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"] if x["id"] == trazo)
        return float(next(e["cantidad"] for e in f["properties"]["enlaces"] if e["vigente"]))

    sin_alt = await trazar({"modo": "area", "mide": "eje"})  # 10 m × 3.00 m de la herramienta, no los 2.5 m del driver
    con_alt = await trazar({"modo": "area", "mide": "eje", "alt": 2.0})
    con_partes = await trazar({"modo": "area", "mide": "eje", "partes": [{"nombre": "Muro", "desde_m": 0, "hasta_m": 1.5, "suma": True}]})
    assert await cantidad(sin_alt) == pytest.approx(30)
    assert await cantidad(con_alt) == pytest.approx(20)
    assert await cantidad(con_partes) == pytest.approx(15)
    await costos.put(f"/api/v1/obras/{escenario.obra_id}/drivers/altura_estandar", json={"valor": "3.4"})
    assert await cantidad(sin_alt) == pytest.approx(30)
    assert await cantidad(await trazar({"modo": "area", "mide": "eje"})) == pytest.approx(30)


async def test_un_muro_trazado_con_plantilla_nace_con_su_altura_base_y_la_guarda(escenario: Escenario, control: httpx.AsyncClient, costos: httpx.AsyncClient) -> None:
    """El trazo manda `muro_plantilla_id` al nacer: su conversión sin `alt` toma la altura base del artefacto (no la de la herramienta ni el
    driver) y la GUARDA; con `alt` o con partes manda lo dicho; una plantilla sin altura cae a la herramienta; una ajena es 422."""
    plano = (await control.post(f"/api/v1/obras/{escenario.obra_id}/planos", json={"nombre": "P", "archivo_url": "e2e/p.pdf"})).json()["id"]
    plantilla = await _plantilla(control, "2.8")
    sin_altura = await _plantilla(control, None)
    await costos.put(f"/api/v1/obras/{escenario.obra_id}/drivers/altura_estandar", json={"valor": "2.2"})

    async def trazar(conversion: dict, plantilla_id: str | None) -> httpx.Response:
        return await control.post(
            f"/api/v1/planos/{plano}/trazos",
            json={
                "version_plano": 1, "fuente": "pdf", "geometria_wkt": MURO, "muro_plantilla_id": plantilla_id,
                "enlaces": [{"medida": "longitud", "factor": "1", "actividad_id": str(escenario.actividad_id), "conversion": conversion}],
            },
        )

    async def cantidad(trazo: str) -> float:
        f = next(x for x in (await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"] if x["id"] == trazo)
        return float(next(e["cantidad"] for e in f["properties"]["enlaces"] if e["vigente"]))

    base = {"modo": "area", "mide": "eje"}
    con_artefacto = (await trazar(base, plantilla)).json()["trazo_id"]
    assert await cantidad(con_artefacto) == pytest.approx(28)  # 10 m × 2.8 m del artefacto
    assert Decimal((await control.get(f"/api/v1/trazos/{con_artefacto}/muro")).json()["altura_efectiva_m"]) == Decimal("2.8")
    assert await cantidad((await trazar({**base, "alt": 2.0}, plantilla)).json()["trazo_id"]) == pytest.approx(20)
    assert await cantidad((await trazar(base, sin_altura)).json()["trazo_id"]) == pytest.approx(30)
    # Cambiar la altura base de la plantilla después no mueve lo ya guardado (Q1).
    nueva = (await control.put(f"/api/v1/muro-plantillas/{plantilla}", json={"nombre": "Base cambiada", "tipo": "con_cadena", "material": "tabique_rojo", "ubicacion": "interior", "altura_m": "3.6"}))
    assert nueva.status_code in (200, 201), nueva.text
    assert await cantidad(con_artefacto) == pytest.approx(28)
    r = await trazar(base, str(uuid.uuid4()))
    assert r.status_code == 422, r.text
