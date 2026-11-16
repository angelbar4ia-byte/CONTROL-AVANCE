"""El Artefacto por HTTP contra Postgres real (migración 0133): plantillas de muro, validación contra la matriz, versiones (Q9),
ubicación por cara, el castillo que depende de la plantilla y la migración de los tipos viejos de muro."""

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

ELEMENTOS = "/api/v1/elementos-parametricos"
PLANTILLAS = "/api/v1/muro-plantillas"
CASTILLO = {"clave": "K-01", "tipo": "castillo", "ancho_m": "0.15", "alto_m": "1", "posicion_m": "3"}
PARTES = [
    {"nombre": "Media altura", "desde_m": "0", "hasta_m": "1.2", "rol": "cuerpo"},
    {"nombre": "Enrase", "desde_m": "1.2", "hasta_m": "2.6", "rol": "enrase"},
]


def _cliente(contexto: ContextoSesion) -> httpx.AsyncClient:
    app = crear_app()
    app.dependency_overrides[contexto_actual] = lambda: contexto
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test")


async def _usuario(escenario: Escenario, rol: str) -> uuid.UUID:
    usuario = uuid.uuid4()
    motor = create_async_engine(DATABASE_URL_ADMIN)
    async with motor.begin() as c:
        await c.execute(
            text("insert into usuario (id, org_id, nombre, email, rol) values (:i, :o, :n, :e, :r)"),
            {"i": str(usuario), "o": str(escenario.org_id), "n": rol, "e": f"{rol}-{usuario.hex[:8]}@t.mx", "r": rol},
        )
    await motor.dispose()
    return usuario


@pytest.fixture
async def control(contexto_control: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_control) as c:
        yield c


@pytest.fixture
async def costos(escenario: Escenario) -> AsyncIterator[httpx.AsyncClient]:
    usuario = await _usuario(escenario, "costos")
    async with _cliente(ContextoSesion(org_id=escenario.org_id, usuario_id=usuario, rol="costos")) as c:
        yield c


@pytest.fixture
async def residente(contexto_residente: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_residente) as c:
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


@pytest.fixture
async def elementos(control: httpx.AsyncClient) -> None:
    """Un castillo, una cadena de cerramiento y una de desplante del catálogo (los crea Control de obra: ya autorizados)."""
    for clave, tipo, parametros, sub in (
        ("K-1", "castillo", None, None),
        ("CE-1", "lineal", {"ancho": 0.15, "alto": 0.2}, "cerramiento"),
        ("CD-1", "lineal", {"ancho": 0.15, "alto": 0.2, "lados": 2}, "desplante"),
        ("T-1", "lineal", {"ancho": 0.15, "alto": 0.3}, "losa"),
    ):
        cuerpo: dict = {"clave": clave, "nombre": f"Elemento {clave}", "tipo": tipo}
        if parametros:
            cuerpo["parametros"] = parametros
        if sub == "losa":
            cuerpo.update(categoria="trabes", subcategoria="losa")
        elif sub:
            cuerpo.update(categoria="cadenas", subcategoria=sub)
        r = await control.post(ELEMENTOS, json=cuerpo)
        assert r.status_code == 201, r.text


def _plantilla(**cambios: object) -> dict:
    base = {
        "nombre": "Muro de fachada", "tipo": "con_cadena", "material": "tabique_rojo", "ubicacion": "fachada_a",
        "partes": PARTES, "elementos": [{"ref": "K-1"}, {"ref": "CE-1"}],
    }
    return {**base, **cambios}


async def _muro(cliente: httpx.AsyncClient, escenario: Escenario) -> tuple[str, str]:
    plano = (await cliente.post(f"/api/v1/obras/{escenario.obra_id}/planos", json={"nombre": "P", "archivo_url": "e2e/p.pdf"})).json()["id"]
    r = await cliente.post(
        f"/api/v1/planos/{plano}/trazos",
        json={
            "version_plano": 1, "fuente": "pdf", "geometria_wkt": "LINESTRING(0 0, 10 0)",
            "enlaces": [{"medida": "longitud", "factor": "5.2", "actividad_id": str(escenario.actividad_id)}],
        },
    )
    assert r.status_code == 201, r.text
    return plano, r.json()["trazo_id"]


async def test_el_catalogo_del_artefacto_trae_tres_tipos_materiales_y_ubicaciones(control: httpx.AsyncClient) -> None:
    c = (await control.get("/api/v1/muro-artefacto/catalogo")).json()
    assert [t["clave"] for t in c["tipos"]] == ["confinado", "con_cadena", "tabique"]
    assert [t["castillo_modo"] for t in c["tipos"]] == ["estimado", "ubicado", None]
    assert {m["clave"]: m["elemento"] for m in c["materiales"]}["tabique_rojo"] == "EST-02010"
    u = {x["clave"]: x for x in c["ubicaciones"]}
    assert (u["fachada_a"]["cara_a"], u["fachada_a"]["cara_b"]) == ("exterior", "interior")
    assert u["interior"]["enrase_exterior"] is True and u["personalizada"]["cara_a"] is None
    assert set(u) == {"interior", "fachada_a", "fachada_b", "pretil", "barda", "personalizada"}


async def test_la_ubicacion_por_cara_se_calcula_sin_guardar(control: httpx.AsyncClient) -> None:
    r = await control.post("/api/v1/muro-artefacto/ubicacion", json={"ubicacion": "interior", "partes": PARTES, "altura_de_losa_m": "1.2"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ubicacion"] == "interior"
    assert [(p["cara_a"], p["cara_b"]) for p in d["partes"]] == [("interior", "interior"), ("exterior", "exterior")]
    assert d["sugerencias"] == [{"indice": 1, "nombre": "Enrase", "cara_a": "exterior", "cara_b": "exterior"}]
    mala = await control.post("/api/v1/muro-artefacto/ubicacion", json={"ubicacion": "interior", "partes": [{"desde_m": "2", "hasta_m": "1"}]})
    assert mala.status_code == 422


async def test_una_plantilla_nace_por_validar_y_costos_edita_pero_no_valida(
    control: httpx.AsyncClient, costos: httpx.AsyncClient, residente: httpx.AsyncClient, elementos: None
) -> None:
    r = await costos.post(PLANTILLAS, json=_plantilla())
    assert r.status_code == 201, r.text
    p = r.json()
    assert (p["validacion"], p["version"], p["vigente"], p["ubicacion"]) == ("por_validar", 1, True, "fachada_a")
    assert [(e["ref"], e["clase"], e["modo"]) for e in p["elementos"]] == [("K-1", "castillo", "ubicado"), ("CE-1", "cadena", None)]
    assert p["elementos"][1]["posicion"] == "cerramiento"
    assert [(x["cara_a"], x["cara_b"]) for x in p["partes"]] == [("exterior", "interior")] * 2
    # El mismo nombre no se repite; lo que no vale se rechaza.
    assert (await costos.post(PLANTILLAS, json=_plantilla())).status_code == 422
    assert (await costos.post(PLANTILLAS, json=_plantilla(nombre="x", elementos=[{"ref": "T-1"}]))).status_code == 422  # una trabe no va en un muro
    assert (await costos.post(PLANTILLAS, json=_plantilla(nombre="y", tipo="tabique"))).status_code == 422  # sin castillos ni cadenas
    assert (await costos.post(PLANTILLAS, json=_plantilla(nombre="z", tipo="pretil"))).status_code == 422
    assert (await costos.post(PLANTILLAS, json=_plantilla(nombre="w", elementos=[{"ref": "CD-1", "posicion": "remate"}]))).status_code == 422
    # Residente ve, pero no escribe ni valida; Costos no valida.
    assert [x["nombre"] for x in (await residente.get(PLANTILLAS)).json()] == ["Muro de fachada"]
    assert (await residente.post(PLANTILLAS, json=_plantilla(nombre="r"))).status_code == 403
    assert (await costos.post(f"{PLANTILLAS}/{p['id']}/validar", json={"aceptar_alertas": True})).status_code == 403
    assert (await control.get(f"{PLANTILLAS}/{p['id']}")).json()["validacion"] == "por_validar"


async def test_control_de_obra_valida_contra_la_matriz_y_acepta_las_alertas(control: httpx.AsyncClient, elementos: None) -> None:
    p = (await control.post(PLANTILLAS, json=_plantilla())).json()
    rev = (await control.get(f"{PLANTILLAS}/{p['id']}/revision")).json()
    # Los elementos de ejemplo no tienen conceptos: «sin concepto» por cada parte y la mampostería implícita (tabique rojo → EST-02010).
    codigos = {(a["ref"], a["codigo"]) for a in rev["alertas"]}
    assert ("K-1", "sin_concepto") in codigos and ("CE-1", "sin_concepto") in codigos
    assert any(a["ref"] == "EST-02010" for a in rev["alertas"])
    assert rev["bloquea"] is False and rev["validable"] is True
    # Con alertas por revisar hay que aceptarlas expresamente.
    r = await control.post(f"{PLANTILLAS}/{p['id']}/validar", json={})
    assert r.status_code == 422 and "alertas" in r.text
    r = await control.post(f"{PLANTILLAS}/{p['id']}/validar", json={"aceptar_alertas": True})
    assert r.status_code == 200, r.text
    v = r.json()["plantilla"]
    assert v["validacion"] == "validada" and v["validada_por_nombre"] is not None and v["validada_en"] is not None


async def test_cambiar_una_plantilla_validada_crea_version_y_los_trazos_medidos_conservan_la_anterior(
    control: httpx.AsyncClient, costos: httpx.AsyncClient, escenario: Escenario, elementos: None
) -> None:
    """Q9: versión nueva al cambiar una validada; el trazo ya medido sigue apuntando a la versión que eligió."""
    v1 = (await control.post(PLANTILLAS, json=_plantilla())).json()
    # Mientras está por validar se edita en el lugar: sigue siendo la versión 1.
    r = await control.put(f"{PLANTILLAS}/{v1['id']}", json=_plantilla(altura_m="2.8"))
    assert r.status_code == 200 and r.json()["version_nueva"] is False and r.json()["id"] == v1["id"]
    assert (await control.post(f"{PLANTILLAS}/{v1['id']}/validar", json={"aceptar_alertas": True})).status_code == 200

    _, muro = await _muro(control, escenario)
    elegido = await control.put(f"/api/v1/trazos/{muro}/muro/plantilla", json={"plantilla_id": v1["id"]})
    assert elegido.status_code == 200, elegido.text
    assert elegido.json()["plantilla_id"] == v1["id"] and elegido.json()["tipo"] == "con_cadena"
    assert (elegido.json()["material"], elegido.json()["ubicacion"]) == ("tabique_rojo", "fachada_a")

    # Un cambio sin diferencias no crea nada; uno real crea la versión 2 por validar y deja la 1 para los trazos medidos.
    igual = (await costos.put(f"{PLANTILLAS}/{v1['id']}", json=_plantilla(altura_m="2.8"))).json()
    assert igual["version_nueva"] is False and igual["version"] == 1
    r = await costos.put(f"{PLANTILLAS}/{v1['id']}", json=_plantilla(altura_m="3", elementos=[{"ref": "K-1"}]))
    assert r.status_code == 200, r.text
    v2 = r.json()
    assert v2["version_nueva"] is True and v2["version"] == 2 and v2["validacion"] == "por_validar" and v2["raiz_id"] == v1["raiz_id"]
    assert [x["version"] for x in (await control.get(PLANTILLAS)).json()] == [2]  # solo la vigente
    versiones = (await control.get(f"{PLANTILLAS}/{v2['id']}/versiones")).json()
    assert [(x["version"], x["vigente"], x["validacion"], x["trazos"]) for x in versiones] == [(2, True, "por_validar", 0), (1, False, "validada", 1)]
    assert (await control.get(f"/api/v1/trazos/{muro}/muro/clasificacion")).json()["plantilla_id"] == v1["id"]
    # La versión anterior ya no se edita, y una plantilla con trazos no se borra.
    assert (await control.put(f"{PLANTILLAS}/{v1['id']}", json=_plantilla())).status_code == 422
    assert (await control.delete(f"{PLANTILLAS}/{v2['id']}")).status_code == 409
    # Desligar el trazo y escoger la 2.
    assert (await control.put(f"/api/v1/trazos/{muro}/muro/plantilla", json={"plantilla_id": v2["id"]})).json()["plantilla_id"] == v2["id"]


async def test_el_castillo_depende_de_la_plantilla_y_no_del_tipo_con_cadena(
    control: httpx.AsyncClient, escenario: Escenario, elementos: None
) -> None:
    _, muro = await _muro(control, escenario)
    # Sin plantilla se conserva la regla de siempre: solo en un muro «con cadena».
    assert (await control.post(f"/api/v1/trazos/{muro}/vanos", json=CASTILLO)).status_code == 422
    # Una plantilla confinada estima los castillos: no se colocan en el plano.
    confinada = (await control.post(PLANTILLAS, json=_plantilla(nombre="Confinada", tipo="confinado"))).json()
    assert confinada["elementos"][0]["modo"] == "estimado"
    await control.put(f"/api/v1/trazos/{muro}/muro/plantilla", json={"plantilla_id": confinada["id"]})
    r = await control.post(f"/api/v1/trazos/{muro}/vanos", json=CASTILLO)
    assert r.status_code == 422 and "Confinada" in r.text
    # Una con cadena SIN castillo tampoco; con castillo, sí.
    sin_k = (await control.post(PLANTILLAS, json=_plantilla(nombre="Sin castillo", elementos=[{"ref": "CE-1"}]))).json()
    await control.put(f"/api/v1/trazos/{muro}/muro/plantilla", json={"plantilla_id": sin_k["id"]})
    assert (await control.post(f"/api/v1/trazos/{muro}/vanos", json=CASTILLO)).status_code == 422
    con_k = (await control.post(PLANTILLAS, json=_plantilla(nombre="Con castillo"))).json()
    await control.put(f"/api/v1/trazos/{muro}/muro/plantilla", json={"plantilla_id": con_k["id"]})
    r = await control.post(f"/api/v1/trazos/{muro}/vanos", json=CASTILLO)
    assert r.status_code == 201, r.text
    # Con una plantilla con castillos el tipo «con cadena» ya no es lo que decide: cambiar la clasificación a otra cosa desliga la
    # plantilla y vuelve la regla de siempre.
    cambio = (await control.put(f"/api/v1/trazos/{muro}/muro/clasificacion", json={"tipo": "tabique"})).json()
    assert cambio["plantilla_id"] is None
    assert (await control.post(f"/api/v1/trazos/{muro}/vanos", json={**CASTILLO, "clave": "K-02", "posicion_m": "6"})).status_code == 422


async def test_las_partes_con_caras_se_guardan_y_cambiarlas_vuelve_personalizada_la_ubicacion(
    control: httpx.AsyncClient, escenario: Escenario
) -> None:
    _, muro = await _muro(control, escenario)
    await control.put(f"/api/v1/trazos/{muro}/muro/clasificacion", json={"tipo": "con_cadena", "ubicacion": "fachada_a"})
    partes = [
        {"nombre": "Cuerpo", "desde_m": "0", "hasta_m": "2.3", "rol": "cuerpo", "cara_a": "exterior", "cara_b": "interior"},
        {"nombre": "Enrase", "desde_m": "2.3", "hasta_m": "2.6", "rol": "enrase", "cara_a": "exterior", "cara_b": "interior"},
    ]
    r = await control.put(f"/api/v1/trazos/{muro}/muro", json={"caras": 2, "partes": partes})
    assert r.status_code == 200, r.text
    assert (await control.get(f"/api/v1/trazos/{muro}/muro/clasificacion")).json()["ubicacion"] == "fachada_a"
    leido = (await control.get(f"/api/v1/trazos/{muro}/muro")).json()["partes"]
    assert [(p["cara_a"], p["cara_b"], p["rol"]) for p in leido] == [("exterior", "interior", "cuerpo"), ("exterior", "interior", "enrase")]
    # El enrase pasa a exterior en las dos caras: la ubicación pasa a «personalizada».
    partes[1]["cara_b"] = "exterior"
    assert (await control.put(f"/api/v1/trazos/{muro}/muro", json={"caras": 2, "partes": partes})).status_code == 200
    assert (await control.get(f"/api/v1/trazos/{muro}/muro/clasificacion")).json()["ubicacion"] == "personalizada"
    assert (await control.put(f"/api/v1/trazos/{muro}/muro", json={"caras": 2, "partes": [{**partes[0], "cara_a": "afuera"}]})).status_code == 422


async def test_la_migracion_pasa_pretil_barda_y_sillar_a_ubicacion_y_material(escenario: Escenario) -> None:
    """0133: pretil → ubicación pretil + confinado; barda → ubicación barda + confinado; sillar → material sillar_amarillo +
    confinado, marcado «por confirmar». Se prueba con el SQL de la migración sobre filas con los tipos viejos."""
    from pathlib import Path

    sql = next(Path(__file__).resolve().parents[3].joinpath("database/migrations").glob("*000133_*.sql")).read_text()
    cuerpo = sql.split("update trazo set muro_ubicacion = 'pretil'")[1].split("alter table trazo\n  add constraint ck_trazo_muro_tipo")[0]
    cuerpo = "update trazo set muro_ubicacion = 'pretil'" + cuerpo
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            plano = uuid.uuid4()
            await c.execute(
                text("insert into plano (id, org_id, obra_id, nombre, archivo_url) values (:p, :o, :ob, 'M', 'r2://m')"),
                {"p": str(plano), "o": str(escenario.org_id), "ob": str(escenario.obra_id)},
            )
            ids = {}
            for tipo in ("pretil", "barda", "sillar", "confinado"):
                ids[tipo] = uuid.uuid4()
                # El constraint nuevo ya no deja guardar los tipos viejos: se suelta para sembrar el estado de antes de la 0133.
                await c.execute(text("alter table trazo drop constraint if exists ck_trazo_muro_tipo"))
                await c.execute(
                    text(
                        "insert into trazo (id, org_id, plano_id, version_plano, fuente, geometria, muro_tipo) values "
                        "(:i, :o, :p, 1, 'pdf', ST_GeomFromText('LINESTRING(0 0, 1 0)', 0), :t)"
                    ),
                    {"i": str(ids[tipo]), "o": str(escenario.org_id), "p": str(plano), "t": tipo},
                )
            for linea in [x for x in cuerpo.split(";\n") if x.strip().startswith("update trazo")]:
                await c.execute(text(linea))
            filas = {
                tipo: (await c.execute(
                    text("select muro_tipo, muro_ubicacion, muro_material, muro_tipo_por_confirmar from trazo where id = :i"), {"i": str(i)}
                )).one()
                for tipo, i in ids.items()
            }
            assert tuple(filas["pretil"]) == ("confinado", "pretil", None, False)
            assert tuple(filas["barda"]) == ("confinado", "barda", None, False)
            assert tuple(filas["sillar"]) == ("confinado", None, "sillar_amarillo", True)
            assert tuple(filas["confinado"]) == ("confinado", None, None, False)
            await c.rollback()
    finally:
        await motor.dispose()
