"""Vanos (puertas, ventanas, pasos) sobre una línea: descuentan lo que mide, contra Postgres real.

Un muro de 10 m sobre un concepto en m² (factor 5.2 = 2.6 m × 2 caras) mide 52 m²; una puerta de 0.9 × 2.1 en un
muro de 2 caras descuenta 0.9 × 2.1 × 2 = 3.78 m². Sobre un concepto en metros (factor 1) solo restan los vanos
que llegan al piso: la puerta sí (0.9 m), la ventana no.
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

MURO = "LINESTRING(0 0, 10 0)"
PUERTA = {"clave": "P-01", "tipo": "puerta", "ancho_m": "0.9", "alto_m": "2.1"}
VENTANA = {"clave": "V-01", "tipo": "ventana", "ancho_m": "1.2", "alto_m": "1.2", "antepecho_m": "0.9"}


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


@pytest.fixture(autouse=True)
async def _actividad_con_concepto(escenario: Escenario) -> None:
    motor = create_async_engine(DATABASE_URL_ADMIN)
    concepto = uuid.uuid4()
    try:
        async with motor.begin() as conn:
            await conn.execute(
                text("insert into concepto (id, org_id, clave, descripcion) values (:id, :org, 'VAN-1', 'Aplanado')"),
                {"id": str(concepto), "org": str(escenario.org_id)},
            )
            await conn.execute(
                text("update actividad set concepto_id = :c, precio_unitario = 10, cant_base = 100, cant_programada = 100 where id = :id"),
                {"c": str(concepto), "id": str(escenario.actividad_id)},
            )
    finally:
        await motor.dispose()


async def _muro(cliente: httpx.AsyncClient, escenario: Escenario, medida: str, factor: str) -> tuple[str, str]:
    r = await cliente.post(f"/api/v1/obras/{escenario.obra_id}/planos", json={"nombre": "P", "archivo_url": "e2e/p.pdf"})
    plano = r.json()["id"]
    r = await cliente.post(
        f"/api/v1/planos/{plano}/trazos",
        json={
            "version_plano": 1,
            "fuente": "pdf",
            "geometria_wkt": MURO,
            "enlaces": [{"medida": medida, "factor": factor, "actividad_id": str(escenario.actividad_id)}],
        },
    )
    assert r.status_code == 201, r.text
    return plano, r.json()["trazo_id"]


def _total(r: httpx.Response) -> Decimal:
    return Decimal(str(r.json()["recalculos"][0]["cantidad_total"])).quantize(Decimal("0.0001"))


async def test_una_puerta_descuenta_ancho_alto_y_caras_en_m2(escenario: Escenario, control: httpx.AsyncClient) -> None:
    _, muro = await _muro(control, escenario, "longitud", "5.2")
    r = await control.post(f"/api/v1/trazos/{muro}/vanos", json=PUERTA)
    assert r.status_code == 201, r.text
    assert _total(r) == (Decimal("52") - Decimal("3.78")).quantize(Decimal("0.0001"))

    # Dos piezas idénticas de la ventana: 1.2 × 1.2 × 2 piezas × 2 caras = 5.76.
    r2 = await control.post(f"/api/v1/trazos/{muro}/vanos", json={**VENTANA, "piezas": 2})
    assert _total(r2) == (Decimal("52") - Decimal("3.78") - Decimal("5.76")).quantize(Decimal("0.0001"))

    vanos = (await control.get(f"/api/v1/trazos/{muro}/vanos")).json()
    assert [v["clave"] for v in vanos] == ["P-01", "V-01"]
    assert [v["llega_al_piso"] for v in vanos] == [True, False]

    # Quitar la puerta devuelve su descuento.
    q = await control.delete(f"/api/v1/vanos/{vanos[0]['id']}")
    assert q.status_code == 200, q.text
    assert _total(q) == (Decimal("52") - Decimal("5.76")).quantize(Decimal("0.0001"))


async def test_en_metros_solo_restan_los_vanos_que_llegan_al_piso(escenario: Escenario, control: httpx.AsyncClient) -> None:
    _, muro = await _muro(control, escenario, "longitud", "1")
    assert _total(await control.post(f"/api/v1/trazos/{muro}/vanos", json=VENTANA)) == Decimal("10.0000")
    assert _total(await control.post(f"/api/v1/trazos/{muro}/vanos", json=PUERTA)) == Decimal("9.1000")


async def test_un_vano_va_en_una_linea_o_en_un_area_y_valida_sus_medidas(escenario: Escenario, control: httpx.AsyncClient) -> None:
    r = await control.post(f"/api/v1/obras/{escenario.obra_id}/planos", json={"nombre": "P", "archivo_url": "e2e/p.pdf"})
    plano = r.json()["id"]
    punto = await control.post(
        f"/api/v1/planos/{plano}/trazos",
        json={"version_plano": 1, "fuente": "pdf", "geometria_wkt": "POINT(1 1)", "enlaces": []},
    )
    assert (await control.post(f"/api/v1/trazos/{punto.json()['trazo_id']}/vanos", json=PUERTA)).status_code == 422
    _, muro = await _muro(control, escenario, "longitud", "5.2")
    assert (await control.post(f"/api/v1/trazos/{muro}/vanos", json={**PUERTA, "ancho_m": "0"})).status_code == 422
    assert (await control.post(f"/api/v1/trazos/{uuid.uuid4()}/vanos", json=PUERTA)).status_code == 404
    assert (await control.delete(f"/api/v1/vanos/{uuid.uuid4()}")).status_code == 404


async def test_sin_la_tabla_de_vanos_se_sigue_midiendo(escenario: Escenario, control: httpx.AsyncClient) -> None:
    """Un despliegue del código antes de la migración 0103 no tumba la lectura de trazos (expand → contract)."""
    from obractrl.adapters.repos import cuantificacion_sql as repo

    plano, muro = await _muro(control, escenario, "longitud", "5.2")
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as conn:
            await conn.execute(text("alter table vano rename to vano_oculta"))
        repo._VANOS_DISPONIBLES = False
        r = await control.get(f"/api/v1/planos/{plano}/trazos")
        assert r.status_code == 200, r.text
        assert next(f for f in r.json()["features"] if f["id"] == muro)["properties"]["enlaces"][0]["cantidad"] is not None
    finally:
        async with motor.begin() as conn:
            await conn.execute(text("alter table vano_oculta rename to vano"))
        await motor.dispose()
        repo._VANOS_DISPONIBLES = False


async def test_los_vanos_del_plano_traen_donde_van_y_se_corren_por_el_muro(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano, muro = await _muro(control, escenario, "longitud", "5.2")  # LINESTRING(0 0, 10 0)
    centrada = (await control.post(f"/api/v1/trazos/{muro}/vanos", json=PUERTA)).json()["vano_id"]
    al_final = (await control.post(f"/api/v1/trazos/{muro}/vanos", json={**VENTANA, "posicion_m": "8"})).json()["vano_id"]

    vanos = {v["id"]: v for v in (await control.get(f"/api/v1/planos/{plano}/vanos")).json()}
    # Sin posición va a la mitad del muro (5 m); el muro corre de izquierda a derecha (0°).
    assert vanos[centrada]["x"] == pytest.approx(5.0) and vanos[centrada]["y"] == pytest.approx(0.0)
    assert vanos[centrada]["angulo"] == pytest.approx(0.0, abs=0.01) and vanos[centrada]["ancho_plano"] == pytest.approx(0.9)
    assert vanos[al_final]["x"] == pytest.approx(8.0)

    # Correrlo no cambia lo que mide el muro.
    antes = _total(await control.post(f"/api/v1/trazos/{muro}/vanos", json={**PUERTA, "clave": "P-09", "ancho_m": "0.9"}))
    assert (await control.patch(f"/api/v1/vanos/{centrada}/posicion", json={"posicion_m": "2.5"})).status_code == 204
    despues = (await control.get(f"/api/v1/planos/{plano}/vanos")).json()
    assert next(v for v in despues if v["id"] == centrada)["x"] == pytest.approx(2.5)
    assert antes is not None
    assert (await control.patch(f"/api/v1/vanos/{uuid.uuid4()}/posicion", json={"posicion_m": "1"})).status_code == 404
    assert (await control.patch(f"/api/v1/vanos/{centrada}/posicion", json={"posicion_m": "-1"})).status_code == 422


async def test_el_muro_cuenta_por_caras_y_por_partes_y_el_vano_descuenta_por_las_mismas_caras(
    escenario: Escenario, control: httpx.AsyncClient
) -> None:
    _, trazo = await _muro(control, escenario, "longitud", "5.2")
    ruta = f"/api/v1/trazos/{trazo}/muro"
    cuatro = Decimal("0.0001")

    por_defecto = (await control.get(ruta)).json()
    assert por_defecto["caras"] == 2 and por_defecto["partes"] is None

    # Una sola cara: 10 m × 2.6 m × 1 = 26 m².
    r = await control.put(ruta, json={"altura_m": "2.6", "caras": 1, "cara": "interior"})
    assert r.status_code == 200, r.text
    assert _total(r) == Decimal("26").quantize(cuatro)
    assert (await control.get(ruta)).json()["cara"] == "interior"

    # Altura por partes: lo que no suma (el cerramiento) cuenta para la altura pero no para la cantidad.
    partes = [
        {"nombre": "Muro", "desde_m": "0", "hasta_m": "2.3", "suma": True},
        {"nombre": "Cerramiento", "desde_m": "2.3", "hasta_m": "2.5", "suma": False},
    ]
    r = await control.put(ruta, json={"caras": 2, "partes": partes})
    assert r.status_code == 200, r.text
    assert Decimal((await control.get(ruta)).json()["altura_efectiva_m"]) == Decimal("2.3")
    assert _total(r) == Decimal("46").quantize(cuatro)  # 10 × 2.3 × 2

    # Un vano descuenta por las mismas caras: puerta 0.9 × 2.1 × 2 = 3.78 m².
    v = await control.post(f"/api/v1/trazos/{trazo}/vanos", json=PUERTA)
    assert _total(v) == (Decimal("46") - Decimal("3.78")).quantize(cuatro)

    # Con una cara el vano descuenta una sola vez.
    r = await control.put(ruta, json={"altura_m": "2.6", "caras": 1})
    assert _total(r) == (Decimal("26") - Decimal("1.89")).quantize(cuatro)

    mala = [{"nombre": "X", "desde_m": "2", "hasta_m": "1", "suma": True}]
    assert (await control.put(ruta, json={"caras": 2, "partes": mala})).status_code in (400, 422)
    assert (await control.put(ruta, json={"altura_m": "0.5", "caras": 2})).status_code in (400, 422)


async def _muro_con(control: httpx.AsyncClient, escenario: Escenario, plano: str, wkt: str, grosor: str | None, factor: str = "1") -> str:
    cuerpo = {
        "version_plano": 1, "fuente": "pdf", "geometria_wkt": wkt,
        "enlaces": [{"medida": "longitud", "factor": factor, "actividad_id": str(escenario.actividad_id)}],
    }
    if grosor:
        cuerpo |= {"grosor_m": grosor, "alineacion": "centro"}
    r = await control.post(f"/api/v1/planos/{plano}/trazos", json=cuerpo)
    assert r.status_code == 201, r.text
    return r.json()["trazo_id"]


async def test_las_uniones_de_muro_recortan_el_largo_y_la_fusion_junta_dos_muros(
    escenario: Escenario, control: httpx.AsyncClient
) -> None:
    plano = (await control.post(f"/api/v1/obras/{escenario.obra_id}/planos", json={"nombre": "P", "archivo_url": "e2e/p.pdf"})).json()["id"]
    # Un muro de 10 m de eje y 0.2 m de grosor, y otro vertical de 0.3 m que cruza su extremo final.
    a = await _muro_con(control, escenario, plano, "LINESTRING(0 0, 10 0)", "0.2")
    b = await _muro_con(control, escenario, plano, "LINESTRING(10 -5, 10 5)", "0.3")
    cuatro = Decimal("0.0001")

    info = (await control.get(f"/api/v1/trazos/{a}/uniones")).json()
    assert info["extremos"] == []
    assert [(c["extremo"], c["trazo_id"]) for c in info["candidatos"]] == [("fin", b)]

    # Conexión: el muro continúa, no cambia lo que mide. Unión a tope: pierde medio grosor del otro (0.15 m).
    r = await control.put(f"/api/v1/trazos/{a}/uniones/fin", json={"op": "conexion", "con_trazo_id": b})
    assert r.status_code == 200, r.text
    assert _total(r) == Decimal("20").quantize(cuatro)  # los dos muros; la conexión no cambia el eje
    # El plano recibe la conexión para dibujar el cuerpo continuo.
    feat = (await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"]
    de_a = next(f for f in feat if f["id"] == a)["properties"]["conexiones"]
    assert de_a == [{"extremo": "fin", "con_trazo_id": b}]
    r = await control.put(f"/api/v1/trazos/{a}/uniones/fin", json={"op": "union", "con_trazo_id": b})
    assert r.status_code == 200, r.text
    total_union = _total(r)
    r = await control.delete(f"/api/v1/trazos/{a}/uniones/fin")
    total_sin = _total(r)
    assert total_sin - total_union == Decimal("0.15").quantize(cuatro)

    # Un muro que no se encuentra con el extremo no se acepta.
    lejos = await _muro_con(control, escenario, plano, "LINESTRING(0 50, 10 50)", "0.2")
    assert (await control.put(f"/api/v1/trazos/{a}/uniones/ini", json={"op": "union", "con_trazo_id": lejos})).status_code == 422

    # Empalme: dos muros que se solapan 2 m (de 8 a 10 m) cuentan ese tramo una sola vez.
    c = await _muro_con(control, escenario, plano, "LINESTRING(8 0, 18 0)", "0.2")
    r = await control.put(f"/api/v1/trazos/{c}/uniones/ini", json={"op": "empalme", "con_trazo_id": a})
    assert r.status_code == 200, r.text
    r2 = await control.delete(f"/api/v1/trazos/{c}/uniones/ini")
    assert _total(r2) - _total(r) == Decimal("2").quantize(cuatro)

    # Fusión: dos muros del mismo grosor que se tocan pasan a ser uno solo.
    d = await _muro_con(control, escenario, plano, "LINESTRING(18 0, 25 0)", "0.2")
    r = await control.post(f"/api/v1/trazos/{c}/fusion", json={"con_trazo_id": d})
    assert r.status_code == 200, r.text
    ids = {f["id"] for f in (await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"]}
    assert c in ids and d not in ids
    # Con distinto grosor no se fusionan.
    assert (await control.post(f"/api/v1/trazos/{a}/fusion", json={"con_trazo_id": b})).status_code == 422


async def test_la_hoja_de_una_puerta_se_guarda_y_no_cambia_lo_que_descuenta(
    escenario: Escenario, control: httpx.AsyncClient
) -> None:
    plano, muro = await _muro(control, escenario, "longitud", "5.2")
    r = await control.post(f"/api/v1/trazos/{muro}/vanos", json=PUERTA)
    antes = _total(r)
    vano = (await control.get(f"/api/v1/trazos/{muro}/vanos")).json()[0]
    assert (vano["bisagra"], vano["lado_hoja"], vano["apertura_grados"]) == (1, 1, 90)  # lo de defecto

    ruta = f"/api/v1/vanos/{vano['id']}/hoja"
    assert (await control.put(ruta, json={"bisagra": -1, "lado_hoja": -1, "apertura_grados": 45})).status_code == 204
    otra = (await control.get(f"/api/v1/trazos/{muro}/vanos")).json()[0]
    assert (otra["bisagra"], otra["lado_hoja"], otra["apertura_grados"]) == (-1, -1, 45)
    en_plano = (await control.get(f"/api/v1/planos/{plano}/vanos")).json()[0]
    assert (en_plano["bisagra"], en_plano["apertura_grados"]) == (-1, 45)

    # Es dibujo: la cantidad del muro no se mueve (otro vano idéntico descuenta lo mismo que el primero).
    otra_puerta = await control.post(f"/api/v1/trazos/{muro}/vanos", json={**PUERTA, "clave": "P-02"})
    assert antes - _total(otra_puerta) == Decimal("3.78").quantize(Decimal("0.0001"))
    # Valores fuera de rango o un vano que no existe se rechazan.
    assert (await control.put(ruta, json={"apertura_grados": 200})).status_code == 422
    assert (await control.put(f"/api/v1/vanos/{uuid.uuid4()}/hoja", json={})).status_code == 404


async def test_un_vano_sobre_un_area_descuenta_de_su_area_y_se_dibuja_en_su_borde(
    escenario: Escenario, control: httpx.AsyncClient
) -> None:
    plano = (await control.post(f"/api/v1/obras/{escenario.obra_id}/planos", json={"nombre": "P", "archivo_url": "e2e/p.pdf"})).json()["id"]
    area = (
        await control.post(
            f"/api/v1/planos/{plano}/trazos",
            json={
                "version_plano": 1, "fuente": "pdf", "geometria_wkt": "POLYGON((0 0, 4 0, 4 3, 0 3, 0 0))",
                "enlaces": [{"medida": "area", "factor": "1", "actividad_id": str(escenario.actividad_id)}],
            },
        )
    ).json()["trazo_id"]
    r = await control.post(f"/api/v1/trazos/{area}/vanos", json={**PUERTA, "posicion_m": 2, "lado_muro": 1})
    assert r.status_code == 201, r.text
    assert _total(r) == (Decimal("12") - Decimal("1.89")).quantize(Decimal("0.0001"))  # 12 m² − 0.9 × 2.1
    en_plano = (await control.get(f"/api/v1/planos/{plano}/vanos")).json()
    assert len(en_plano) == 1 and en_plano[0]["lado_muro"] == 1 and en_plano[0]["trazo_id"] == area
    assert en_plano[0]["y"] == pytest.approx(0)  # a 2 m del inicio, sobre el borde de abajo del área


async def test_el_catalogo_de_versiones_nace_con_las_de_partida_y_se_edita_sin_tocar_los_vanos_puestos(
    escenario: Escenario, control: httpx.AsyncClient, contexto_residente: ContextoSesion
) -> None:
    lista = (await control.get("/api/v1/vanos-version")).json()
    assert {v["clave"] for v in lista} >= {"P-01", "P-02", "P-03", "V-01", "C-01", "A-01", "PS-01"}
    p01 = next(v for v in lista if v["clave"] == "P-01")
    assert (Decimal(str(p01["ancho_m"])), Decimal(str(p01["alto_m"]))) == (Decimal("0.9"), Decimal("2.1"))
    assert [v["clave"] for v in (await control.get("/api/v1/vanos-version", params={"tipo": "ventana"})).json()] == ["V-01", "V-02"]

    # «+ Nueva» copia las medidas de la elegida y toma la clave que sigue.
    r = await control.post("/api/v1/vanos-version", json={"tipo": "puerta", "copiar_de": p01["id"]})
    assert r.status_code == 201, r.text
    nueva = r.json()
    assert nueva["clave"] == "P-04" and Decimal(str(nueva["ancho_m"])) == Decimal("0.9")

    # Editar la versión cambia el catálogo; los vanos ya puestos conservan sus medidas.
    _, muro = await _muro(control, escenario, "longitud", "5.2")
    puesto = await control.post(f"/api/v1/trazos/{muro}/vanos", json={**PUERTA, "clave": "P-04"})
    assert puesto.status_code == 201
    r = await control.patch(f"/api/v1/vanos-version/{nueva['id']}", json={"ancho_m": "1.1", "clave": "p-09"})
    assert r.status_code == 200 and r.json()["clave"] == "P-09" and Decimal(str(r.json()["ancho_m"])) == Decimal("1.1")
    vano = (await control.get(f"/api/v1/trazos/{muro}/vanos")).json()[0]
    assert Decimal(str(vano["ancho_m"])) == Decimal("0.9")
    assert (await control.patch(f"/api/v1/vanos-version/{nueva['id']}", json={"clave": "P-01"})).status_code == 422  # repetida

    # Se puede quitar mientras quede al menos una del tipo; un residente la ve pero no la define.
    assert (await control.delete(f"/api/v1/vanos-version/{nueva['id']}")).status_code == 204
    for v in (await control.get("/api/v1/vanos-version", params={"tipo": "arco"})).json():
        assert (await control.delete(f"/api/v1/vanos-version/{v['id']}")).status_code == 422
    async with _cliente(contexto_residente) as residente:
        assert len((await residente.get("/api/v1/vanos-version")).json()) >= 8
        assert (await residente.post("/api/v1/vanos-version", json={"tipo": "puerta"})).status_code == 403


async def test_cambiar_el_ancho_de_un_vano_recalcula_lo_que_descuenta(escenario: Escenario, control: httpx.AsyncClient) -> None:
    plano, muro = await _muro(control, escenario, "longitud", "5.2")
    vano = (await control.post(f"/api/v1/trazos/{muro}/vanos", json=PUERTA)).json()["vano_id"]

    # Resuelta la posición: sin guardar va a la mitad del muro y el plano lo dice en metros.
    en_plano = next(v for v in (await control.get(f"/api/v1/planos/{plano}/vanos")).json() if v["id"] == vano)
    assert Decimal(str(en_plano["posicion_m"])) == Decimal("5")

    r = await control.patch(f"/api/v1/vanos/{vano}/ancho", json={"ancho_m": "1.0"})
    assert r.status_code == 200, r.text
    assert _total(r) == (Decimal("52") - Decimal("4.2")).quantize(Decimal("0.0001"))
    en_plano = next(v for v in (await control.get(f"/api/v1/planos/{plano}/vanos")).json() if v["id"] == vano)
    assert en_plano["ancho_plano"] == pytest.approx(1.0)
    # La versión sigue al ancho: 1 × 2.1 es la P-02 del catálogo.
    assert r.json()["clave"] == "P-02" and r.json()["version_nueva"] is False
    assert en_plano["clave"] == "P-02"

    # Un ancho que ninguna versión tiene crea la siguiente del tipo.
    r = await control.patch(f"/api/v1/vanos/{vano}/ancho", json={"ancho_m": "1.1"})
    assert r.json()["clave"] == "P-04" and r.json()["version_nueva"] is True
    versiones = (await control.get("/api/v1/vanos-version")).json()
    assert any(v["clave"] == "P-04" and Decimal(str(v["ancho_m"])) == Decimal("1.1") for v in versiones)

    # Las piezas idénticas también recalculan.
    r = await control.patch(f"/api/v1/vanos/{vano}/piezas", json={"piezas": 2})
    assert r.status_code == 200, r.text
    assert _total(r) == (Decimal("52") - Decimal("1.1") * Decimal("2.1") * 2 * 2).quantize(Decimal("0.0001"))
    assert (await control.patch(f"/api/v1/vanos/{vano}/piezas", json={"piezas": 0})).status_code == 422
    assert (await control.patch(f"/api/v1/vanos/{uuid.uuid4()}/piezas", json={"piezas": 1})).status_code == 404

    assert (await control.patch(f"/api/v1/vanos/{uuid.uuid4()}/ancho", json={"ancho_m": "1"})).status_code == 404
    assert (await control.patch(f"/api/v1/vanos/{vano}/ancho", json={"ancho_m": "0"})).status_code == 422


async def test_el_tipo_de_muro_y_su_acabado_se_fijan_se_leen_y_no_cambian_lo_que_mide(
    escenario: Escenario, control: httpx.AsyncClient
) -> None:
    """F-22 (0124): confinado, con cadena, tabique, sillar, pretil o barda, con las capas gris, blanca y pintura en Sí/No por cara.
    Solo clasifica: lo que mide el muro no cambia."""
    plano = (await control.post(f"/api/v1/obras/{escenario.obra_id}/planos", json={"nombre": "P", "archivo_url": "e2e/p.pdf"})).json()["id"]
    muro = await _muro_con(control, escenario, plano, "LINESTRING(0 0, 10 0)", "0.2")
    antes = (await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"][0]["properties"]["enlaces"][0]["cantidad"]

    # Sin clasificar: sin tipo ni acabado.
    vacio = (await control.get(f"/api/v1/trazos/{muro}/muro/clasificacion")).json()
    assert vacio == {"tipo": None, "acabado": None}

    # Se clasifica con el acabado de defecto (todo en Sí) y luego se quita la pintura de la fachada.
    r = await control.put(f"/api/v1/trazos/{muro}/muro/clasificacion", json={"tipo": "confinado"})
    assert r.status_code == 200, r.text
    assert r.json()["acabado"] == {c: dict.fromkeys(("gris", "blanca", "pintura"), True) for c in ("interior", "fachada")}
    r = await control.put(
        f"/api/v1/trazos/{muro}/muro/clasificacion",
        json={"tipo": "tabique", "acabado": {"fachada": {"pintura": False}}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["tipo"] == "tabique"
    assert r.json()["acabado"]["fachada"] == {"gris": True, "blanca": True, "pintura": False}
    assert r.json()["acabado"]["interior"] == {"gris": True, "blanca": True, "pintura": True}

    # El plano trae el tipo y el acabado; lo medido es lo mismo.
    prop = (await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"][0]["properties"]
    assert prop["muro_tipo"] == "tabique"
    assert prop["muro_acabado"]["fachada"]["pintura"] is False
    assert prop["enlaces"][0]["cantidad"] == antes

    # Lo que no vale se rechaza: un tipo desconocido y el revestimiento como capa (es un concepto del catálogo).
    assert (await control.put(f"/api/v1/trazos/{muro}/muro/clasificacion", json={"tipo": "adobe"})).status_code == 422
    malo = await control.put(
        f"/api/v1/trazos/{muro}/muro/clasificacion", json={"tipo": "tabique", "acabado": {"interior": {"revestimiento": True}}}
    )
    assert malo.status_code == 422

    # Se puede cambiar de confinado a con cadena y a tabique, y quitar la clasificación.
    for tipo in ("confinado", "con_cadena", "tabique"):
        assert (await control.put(f"/api/v1/trazos/{muro}/muro/clasificacion", json={"tipo": tipo})).json()["tipo"] == tipo
    quitado = (await control.put(f"/api/v1/trazos/{muro}/muro/clasificacion", json={"tipo": None})).json()
    assert quitado == {"tipo": None, "acabado": None}


async def test_un_revestimiento_se_liga_a_un_muro_y_una_cara_sin_cambiar_lo_que_mide(
    escenario: Escenario, control: httpx.AsyncClient
) -> None:
    """D-645 (0125): el revestimiento es una línea con su concepto (largo × altura en m²) ligada a un muro y a una cara."""
    plano = (await control.post(f"/api/v1/obras/{escenario.obra_id}/planos", json={"nombre": "P", "archivo_url": "e2e/p.pdf"})).json()["id"]
    muro = await _muro_con(control, escenario, plano, "LINESTRING(0 0, 10 0)", "0.2")
    revest = await _muro_con(control, escenario, plano, "LINESTRING(2 0, 6 0)", None)
    otro_plano = (await control.post(f"/api/v1/obras/{escenario.obra_id}/planos", json={"nombre": "Q", "archivo_url": "e2e/q.pdf"})).json()["id"]
    ajeno = await _muro_con(control, escenario, otro_plano, "LINESTRING(0 0, 4 0)", None)

    def medidas(feats: list[dict]) -> dict[str, str]:
        return {f["id"]: f["properties"]["enlaces"][0]["cantidad"] for f in feats}

    antes = medidas((await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"])

    # Se liga a la cara de fachada del muro.
    r = await control.put(f"/api/v1/trazos/{revest}/revestimiento", json={"muro_id": muro, "cara": "fachada"})
    assert r.status_code == 200, r.text
    assert r.json() == {"muro_id": muro, "cara": "fachada"}
    feats = (await control.get(f"/api/v1/planos/{plano}/trazos")).json()["features"]
    prop = next(f for f in feats if f["id"] == revest)["properties"]
    assert prop["revestimiento_de"] == muro and prop["revestimiento_cara"] == "fachada"
    assert next(f for f in feats if f["id"] == muro)["properties"]["revestimiento_de"] is None
    assert medidas(feats) == antes  # lo medido no cambia

    # Lo que no vale: sin cara, a sí mismo, a un muro de otro plano, un revestimiento como muro de otro.
    assert (await control.put(f"/api/v1/trazos/{revest}/revestimiento", json={"muro_id": muro})).status_code == 422
    assert (await control.put(f"/api/v1/trazos/{revest}/revestimiento", json={"muro_id": revest, "cara": "interior"})).status_code == 422
    assert (await control.put(f"/api/v1/trazos/{revest}/revestimiento", json={"muro_id": ajeno, "cara": "interior"})).status_code == 422
    otro = await _muro_con(control, escenario, plano, "LINESTRING(7 0, 9 0)", None)
    assert (await control.put(f"/api/v1/trazos/{otro}/revestimiento", json={"muro_id": revest, "cara": "interior"})).status_code == 422

    # Se deslíga.
    r = await control.put(f"/api/v1/trazos/{revest}/revestimiento", json={"muro_id": None})
    assert r.json() == {"muro_id": None, "cara": None}
