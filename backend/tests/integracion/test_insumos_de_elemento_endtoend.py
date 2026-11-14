"""Materiales del elemento, insumos permitidos por tipo y comparación con el concepto del catálogo, por HTTP contra Postgres
real (migración 0129; plan de elementos de muro, fase D)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.api.dependencias import contexto_actual
from obractrl.domain.cuantificacion.clasificacion_de_elementos import firma_de_elemento
from obractrl.domain.cuantificacion.elementos_parametricos import normalizar_parametros
from obractrl.infrastructure.db.sesion import ContextoSesion
from obractrl.main import crear_app
from tests.integracion.conftest import DATABASE_URL_ADMIN

RUTA = "/api/v1/elementos-parametricos"

# (clave, descripción, tipo en la base, unidad, familia, subfamilia, costo): datos reales de los catálogos de julio 2026.
INSUMOS = [
    ("ACE-00001", "ALAMBRE RECOCIDO", "material", "kg", "Aceros", "Consumible", 24.68),
    ("ACE-00003", "ANILLO 10X10", "material", "kg", "Aceros", "Prefabricado", 24.01),
    ("ACE-00011", "ARMEX 10X10-4", "material", "pza", "Aceros", "Prefabricado", 140.07),
    ("ACE-00012", "CLAVO 2 1/2", "material", "kg", "Aceros", "Consumible", 30.68),
    ("ACE-00013", "CLAVO 4", "material", "kg", "Aceros", "Consumible", 30.68),
    ("ACR-00001", "VARILLA 3/8", "material", "pza", "Acero De Refuerzo", "Habilitable", 133.01),
    ("MEZ-01020", "CONCRETO H.O. F'C=150", "material", "m3", "Mezclas", "Concretos", 1500.0),
    ("MEZ-01030", "CONCRETO H.O. F'C=200", "material", "m3", "Mezclas", "Concretos", 1650.0),
    ("MEZ-07010", "MORTERO CEMENTO-ARENA 1:4", "material", "m3", "Mezclas", "Morteros", 920.0),
    ("MAD-00001", "CIMBRA 3 MTS", "material", "m2", "Cimbra", None, 95.0),
    ("MAD-00004", "TABLAS", "material", "pza", "Cimbra", None, 198.0),
    ("MAD-00007", "DURMIENTE", "material", "pza", "Maderas", "Ornamental", 750.0),
    ("PET-00004", "PIEDRA BRAZA", "material", "m3", "Pétreos", "Piedras", 400.0),
    ("CUAD-001", "Cuadrilla tareas pesadas", "mano_obra", "jornal", "Cuadrillas", "Albañilería y Estructura", 2068.0),
    ("CUAD-050", "Cuadrilla de carpintería", "mano_obra", "jornal", "Cuadrillas", "Carpintería", 2200.0),
    ("MOE-02020", "MO CASTILLOS K1 (15X15)", "mano_obra", "ml", "Obra Civil", "Castillo", 130.0),
    ("MOE-02050", "MO CADENA", "mano_obra", "ml", "Obra Civil", "Cadena", 100.0),
]


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


@pytest.fixture
async def catalogo(escenario) -> dict[str, uuid.UUID]:
    """Unidades, árbol de familias e insumos del catálogo (como los deja el cargador: la subfamilia cuelga de la familia)."""
    org = str(escenario.org_id)
    ids: dict[str, uuid.UUID] = {}
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            unidades = {}
            for u in ("kg", "pza", "m3", "m2", "ml", "jornal"):
                unidades[u] = (
                    await c.execute(
                        text("insert into unidad (org_id, clave, nombre, sinonimos) values (:o, :u, :u, :s) returning id"),
                        {"o": org, "u": u, "s": ["JOR"] if u == "jornal" else []},
                    )
                ).scalar_one()
            familias: dict[tuple[str, str | None], uuid.UUID] = {}
            for _, _, _, _, fam, sub, _ in INSUMOS:
                if (fam, None) not in familias:
                    familias[(fam, None)] = (
                        await c.execute(
                            text("insert into familia (org_id, clave, nombre) values (:o, :n, :n) returning id"), {"o": org, "n": fam}
                        )
                    ).scalar_one()
                if sub and (sub, fam) not in familias:
                    # Como el cargador: la clave de la subfamilia es su nombre y es única (Concretos cuelga de la primera).
                    existente = (
                        await c.execute(text("select id from familia where org_id = :o and clave = :n"), {"o": org, "n": sub})
                    ).scalar_one_or_none()
                    familias[(sub, fam)] = existente or (
                        await c.execute(
                            text("insert into familia (org_id, parent_id, clave, nombre) values (:o, :p, :n, :n) returning id"),
                            {"o": org, "p": str(familias[(fam, None)]), "n": sub},
                        )
                    ).scalar_one()
            for clave, desc, tipo, unidad, fam, sub, costo in INSUMOS:
                ids[clave] = (
                    await c.execute(
                        text(
                            "insert into insumo (org_id, tipo, clave, descripcion, unidad_id, familia_id, costo_base) "
                            "values (:o, cast(:t as tipo_insumo), :k, :d, :u, :f, :c) returning id"
                        ),
                        {"o": org, "t": tipo, "k": clave, "d": desc, "u": str(unidades[unidad]), "f": str(familias[(sub, fam)] if sub else familias[(fam, None)]), "c": costo},
                    )
                ).scalar_one()
    finally:
        await motor.dispose()
    return ids


async def _castillo(cliente: httpx.AsyncClient, clave: str = "K-1", **extra: object) -> httpx.Response:
    return await cliente.post(RUTA, json={"clave": clave, "nombre": f"Castillo {clave}", "tipo": "castillo", **extra})


MATERIALES = {"concreto": "MEZ-01020", "alambre": "ACE-00001", "varilla": "ACR-00001", "anillo": "ACE-00003", "cimbra": {"MAD-00001": 0.3, "ACE-00012": 0.0175}}


# --- 1. Materiales del elemento ---------------------------------------------------------------------------------


async def test_los_materiales_del_elemento_se_guardan_y_se_leen(control: httpx.AsyncClient, catalogo) -> None:
    r = await _castillo(control, materiales=MATERIALES)
    assert r.status_code == 201, r.text
    e = next(x for x in (await control.get(RUTA)).json() if x["clave"] == "K-1")
    assert e["materiales"] == {"concreto": "MEZ-01020", "alambre": "ACE-00001", "varilla": "ACR-00001", "anillo": "ACE-00003", "armex": None, "cimbra": {"MAD-00001": 0.3, "ACE-00012": 0.0175}}
    # Un elemento sin materiales los trae vacíos (los anteriores a la 0129 quedan así).
    assert (await _castillo(control, "K-2", parametros={"alto": 3.0})).status_code == 201
    k2 = next(x for x in (await control.get(RUTA)).json() if x["clave"] == "K-2")
    assert all(v is None for v in k2["materiales"].values())


async def test_un_material_que_no_existe_o_es_de_otra_familia_se_rechaza(control: httpx.AsyncClient, catalogo) -> None:
    r = await _castillo(control, materiales={"concreto": "MEZ-99999"})
    assert r.status_code == 422 and "no existe en la base" in r.json()["detail"]
    r = await _castillo(control, materiales={"concreto": "PET-00004"})
    assert r.status_code == 422 and "PET-00004" in r.json()["detail"] and "no es de las familias" in r.json()["detail"]
    r = await _castillo(control, materiales={"varilla": "ACE-00001"})
    assert r.status_code == 422 and "no sirve de varilla" in r.json()["detail"]
    r = await _castillo(control, materiales={"alambre": "CUAD-001"})
    assert r.status_code == 422 and "no es un material" in r.json()["detail"]
    assert (await control.get(RUTA)).json() == []


async def test_los_materiales_entran_a_la_firma_anti_duplicados(control: httpx.AsyncClient, catalogo) -> None:
    assert (await _castillo(control, "K-1", materiales={"concreto": "MEZ-01020"})).status_code == 201
    # Mismas medidas y mismo concreto: duplicado.
    dup = await _castillo(control, "K-2", materiales={"concreto": "MEZ-01020"})
    assert dup.status_code == 409 and dup.json()["clave_igual"] == "K-1"
    # Mismas medidas con otro concreto, o sin materiales: son otros elementos.
    assert (await _castillo(control, "K-3", materiales={"concreto": "MEZ-01030"})).status_code == 201
    assert (await _castillo(control, "K-4")).status_code == 201
    # Y el orden de los consumos de cimbra no importa.
    assert (await _castillo(control, "K-5", materiales={"cimbra": {"MAD-00001": 0.3, "ACE-00012": 0.2}})).status_code == 201
    assert (await _castillo(control, "K-6", materiales={"cimbra": {"ACE-00012": 0.2, "MAD-00001": 0.3}})).status_code == 409


async def test_cambiar_los_materiales_actualiza_la_firma_y_respeta_el_duplicado(control: httpx.AsyncClient, catalogo) -> None:
    k1 = (await _castillo(control, "K-1", materiales={"concreto": "MEZ-01020"})).json()["id"]
    k2 = (await _castillo(control, "K-2", materiales={"concreto": "MEZ-01030"})).json()["id"]
    # K-2 pasa al concreto de K-1: sería idéntico.
    r = await control.patch(f"{RUTA}/{k2}", json={"materiales": {"concreto": "MEZ-01020"}})
    assert r.status_code == 409 and r.json()["clave_igual"] == "K-1"
    # Con el alambre de más ya no.
    assert (await control.patch(f"{RUTA}/{k2}", json={"materiales": {"concreto": "MEZ-01020", "alambre": "ACE-00001"}})).status_code == 204
    # Sin `materiales` se conservan; con un objeto vacío se quitan.
    assert (await control.patch(f"{RUTA}/{k2}", json={"nombre": "Otro nombre"})).status_code == 204
    e2 = next(x for x in (await control.get(RUTA)).json() if x["id"] == k2)
    assert e2["materiales"]["alambre"] == "ACE-00001"
    assert (await control.patch(f"{RUTA}/{k1}", json={"materiales": {}})).status_code == 204
    assert next(x for x in (await control.get(RUTA)).json() if x["id"] == k1)["materiales"]["concreto"] is None


async def test_la_firma_de_la_base_con_materiales_es_la_misma_que_la_del_dominio(control: httpx.AsyncClient, catalogo) -> None:
    """`app.firma_elemento` (0129, con materiales) y `firma_de_elemento` arman la misma cadena."""
    assert (await _castillo(control, "K-1", materiales=MATERIALES)).status_code == 201
    assert (await _castillo(control, "K-2", parametros={"alto": 3.0})).status_code == 201
    assert (await control.post(RUTA, json={"clave": "CE-1", "nombre": "Cadena", "tipo": "lineal", "materiales": {"concreto": "MEZ-01030", "cimbra": {"MAD-00004": 0.1234567}}})).status_code == 201
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.connect() as conn:
            filas = (
                await conn.execute(
                    text(
                        "select clave, tipo, categoria, subcategoria, parametros, materiales, firma, "
                        "app.firma_elemento(categoria, subcategoria, tipo, parametros, materiales) as de_la_base, "
                        "app.firma_elemento(categoria, subcategoria, tipo, parametros) as sin_materiales "
                        "from elemento_parametrico where clave in ('K-1','K-2','CE-1')"
                    )
                )
            ).mappings().all()
    finally:
        await motor.dispose()
    assert len(filas) == 3
    for f in filas:
        parametros = normalizar_parametros(f["tipo"], f["parametros"])
        esperada = firma_de_elemento(f["categoria"], f["subcategoria"], f["tipo"], parametros, f["materiales"])
        assert f["firma"] == f["de_la_base"] == esperada, f["clave"]
        # Sin materiales la firma es la de antes de la 0129: los elementos existentes no cambian de firma.
        if not f["materiales"]:
            assert f["firma"] == f["sin_materiales"] == firma_de_elemento(f["categoria"], f["subcategoria"], f["tipo"], parametros)
        else:
            assert f["firma"] != f["sin_materiales"]


async def test_una_version_nueva_conserva_materiales_e_insumos_agregados(control: httpx.AsyncClient, catalogo, escenario) -> None:
    """D-639: al cambiar la receta con una obra asignada nace una versión nueva: lleva los materiales y los insumos de la anterior."""
    from tests.integracion.test_elementos_parametricos_endtoend import _plano_con_trazos

    k1 = (await _castillo(control, "K-1", materiales={"concreto": "MEZ-01020"})).json()["id"]
    assert (await control.post(f"{RUTA}/{k1}/insumos", json={"insumos": [{"insumo_id": str(catalogo["ACE-00011"]), "cantidad": 1}]})).status_code == 201
    _, ids = await _plano_con_trazos(control, escenario)
    assert (await control.put(f"/api/v1/trazos/{ids['punto']}/elemento-parametrico", json={"elemento_id": k1})).status_code in (200, 204)
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            await c.execute(
                text("insert into parte_estado (org_id, obra_id, clave, estado) values (:o, :ob, 'sin_etapa', 'asignada')"),
                {"o": str(escenario.org_id), "ob": str(escenario.obra_id)},
            )
    finally:
        await motor.dispose()
    assert (await control.patch(f"{RUTA}/{k1}", json={"parametros": {"alto": 3.0}})).status_code == 204
    nuevos = [e for e in (await control.get(RUTA)).json() if e["clave"] == "K-1"]
    assert len(nuevos) == 1 and nuevos[0]["version"] == 2 and nuevos[0]["id"] != k1
    assert nuevos[0]["materiales"]["concreto"] == "MEZ-01020"
    insumos = (await control.get(f"{RUTA}/{nuevos[0]['id']}/insumos")).json()["insumos"]
    assert [i["insumo"]["clave"] for i in insumos] == ["ACE-00011"]


# --- 2. Insumos permitidos por tipo ----------------------------------------------------------------------------


async def test_las_familias_de_insumos_marcan_las_usuales_del_tipo(control: httpx.AsyncClient, catalogo) -> None:
    r = await control.get(f"{RUTA}/familias-de-insumos", params={"tipo": "castillo"})
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    clases = {c["clase"]: c for c in cuerpo["clases"]}
    assert list(clases) == ["material", "trabajo", "mano_obra", "herramienta"]
    usuales = {(f["familia"], f["subfamilia"]) for f in clases["material"]["familias"] if f["usual"]}
    fuera = {(f["familia"], f["subfamilia"]) for f in clases["material"]["familias"] if not f["usual"]}
    assert ("Aceros", "Consumible") in usuales and ("Acero De Refuerzo", "Habilitable") in usuales and ("Mezclas", "Concretos") in usuales
    assert ("Cimbra", None) in usuales
    assert ("Pétreos", "Piedras") in fuera and ("Maderas", "Ornamental") in fuera and ("Mezclas", "Morteros") in fuera
    assert "Cimbra" in clases["material"]["admitidas"]
    assert clases["material"]["total"] == 13
    assert clases["mano_obra"]["total"] == 2 and clases["trabajo"]["total"] == 2 and clases["herramienta"]["total"] == 0
    assert {(f["familia"], f["subfamilia"]) for f in clases["mano_obra"]["familias"] if f["usual"]} == {("Cuadrillas", "Albañilería y Estructura")}
    assert {f["subfamilia"] for f in clases["trabajo"]["familias"] if f["usual"]} == {"Castillo"}
    assert [s["clave"] for s in cuerpo["sugerencias_de_herramienta"]] == ["INS-A001"]
    # La cadena admite el destajo de su subfamilia, no el del castillo.
    cadena = (await control.get(f"{RUTA}/familias-de-insumos", params={"tipo": "lineal"})).json()
    trabajo = next(c for c in cadena["clases"] if c["clase"] == "trabajo")
    assert {f["subfamilia"] for f in trabajo["familias"] if f["usual"]} == {"Cadena"}


async def test_buscar_insumos_filtra_por_clase_familia_y_texto_y_marca_los_permitidos(control: httpx.AsyncClient, catalogo) -> None:
    k1 = (await _castillo(control)).json()["id"]
    todos = (await control.get(f"{RUTA}/{k1}/insumos-disponibles", params={"clase": "material"})).json()
    assert len(todos) == 13
    por = {i["clave"]: i for i in todos}
    assert por["ACE-00001"]["permitido"] and por["MAD-00001"]["permitido"] and por["MEZ-01020"]["permitido"]
    assert not por["PET-00004"]["permitido"] and not por["MAD-00007"]["permitido"] and not por["MEZ-07010"]["permitido"]
    assert por["ACE-00001"]["familia"] == "Aceros" and por["ACE-00001"]["subfamilia"] == "Consumible" and por["ACE-00001"]["precio"] == 24.68
    assert {i["clave"] for i in (await control.get(f"{RUTA}/{k1}/insumos-disponibles", params={"familia": "Aceros"})).json()} == {
        "ACE-00001", "ACE-00003", "ACE-00011", "ACE-00012", "ACE-00013"
    }
    assert [i["clave"] for i in (await control.get(f"{RUTA}/{k1}/insumos-disponibles", params={"q": "clavo 4"})).json()] == ["ACE-00013"]
    assert (await control.get(f"{RUTA}/{uuid.uuid4()}/insumos-disponibles")).status_code == 404


async def test_agregar_un_insumo_de_otra_familia_se_rechaza_con_un_error_claro(control: httpx.AsyncClient, catalogo) -> None:
    k1 = (await _castillo(control)).json()["id"]
    r = await control.post(f"{RUTA}/{k1}/insumos", json={"insumos": [{"insumo_id": str(catalogo["PET-00004"]), "cantidad": 2}]})
    assert r.status_code == 422, r.text
    m = r.json()["detail"]
    assert "PET-00004" in m and "Pétreos · Piedras" in m and "castillo" in m and "Aceros" in m and "Cimbra" in m
    # Todo o nada: con uno bueno y uno malo no se agrega ninguno.
    r = await control.post(
        f"{RUTA}/{k1}/insumos",
        json={"insumos": [{"insumo_id": str(catalogo["ACE-00011"])}, {"insumo_id": str(catalogo["MAD-00007"])}]},
    )
    assert r.status_code == 422 and "MAD-00007" in r.json()["detail"]
    assert (await control.get(f"{RUTA}/{k1}/insumos")).json()["insumos"] == []
    # Mano de obra de otra subfamilia y destajo de otro tipo, tampoco.
    assert (await control.post(f"{RUTA}/{k1}/insumos", json={"insumos": [{"insumo_id": str(catalogo["CUAD-050"])}]})).status_code == 422
    r = await control.post(f"{RUTA}/{k1}/insumos", json={"insumos": [{"insumo_id": str(catalogo["MOE-02050"])}]})
    assert r.status_code == 422 and "Castillo" in r.json()["detail"]
    # Un insumo que no existe es 404.
    assert (await control.post(f"{RUTA}/{k1}/insumos", json={"insumos": [{"insumo_id": str(uuid.uuid4())}]})).status_code == 404


async def test_agregar_varios_insumos_permitidos_y_quitarlos(control: httpx.AsyncClient, catalogo) -> None:
    k1 = (await _castillo(control)).json()["id"]
    cuerpo = {
        "insumos": [
            {"insumo_id": str(catalogo[c]), "cantidad": q}
            for c, q in (("ACE-00011", 1), ("MAD-00004", 0.01), ("CUAD-001", 0.05), ("MOE-02020", 1))
        ]
    }
    r = await control.post(f"{RUTA}/{k1}/insumos", json=cuerpo)
    assert r.status_code == 201 and r.json() == {"agregados": 4}
    # No se repiten.
    assert (await control.post(f"{RUTA}/{k1}/insumos", json=cuerpo)).json() == {"agregados": 0}
    lista = (await control.get(f"{RUTA}/{k1}/insumos")).json()
    assert {i["insumo"]["clave"]: (i["clase"], i["cantidad"]) for i in lista["insumos"]} == {
        "ACE-00011": ("material", 1.0), "MAD-00004": ("material", 0.01), "CUAD-001": ("mano_obra", 0.05), "MOE-02020": ("trabajo", 1.0)
    }
    assert all(i["insumo"]["permitido"] for i in lista["insumos"])
    assert (await control.patch(f"{RUTA}/{k1}/insumos/{catalogo['ACE-00011']}", json={"cantidad": 2.5})).status_code == 204
    assert (await control.patch(f"{RUTA}/{k1}/insumos/{catalogo['PET-00004']}", json={"cantidad": 2})).status_code == 404
    assert (await control.delete(f"{RUTA}/{k1}/insumos/{catalogo['MAD-00004']}")).status_code == 204
    assert (await control.delete(f"{RUTA}/{k1}/insumos/{catalogo['MAD-00004']}")).status_code == 404
    lista = (await control.get(f"{RUTA}/{k1}/insumos")).json()
    assert {i["insumo"]["clave"]: i["cantidad"] for i in lista["insumos"]}["ACE-00011"] == 2.5
    assert len(lista["insumos"]) == 3
    # Borrar el elemento se lleva sus insumos agregados.
    assert (await control.delete(f"{RUTA}/{k1}")).status_code == 204


async def test_el_detalle_trae_los_materiales_con_su_ficha(control: httpx.AsyncClient, catalogo) -> None:
    k1 = (await _castillo(control, materiales=MATERIALES)).json()["id"]
    d = (await control.get(f"{RUTA}/{k1}/insumos")).json()
    por = {(m["material"], m["clave"]): m for m in d["materiales"]}
    assert por[("concreto", "MEZ-01020")]["insumo"]["descripcion"] == "CONCRETO H.O. F'C=150"
    assert por[("cimbra", "MAD-00001")]["consumo"] == 0.3
    assert por[("cimbra", "ACE-00012")]["insumo"]["unidad"] == "kg"
    assert d["tipo"] == "castillo"


async def test_la_losa_aun_no_admite_insumos(control: httpx.AsyncClient, catalogo) -> None:
    losa = (await control.post(RUTA, json={"clave": "L-1", "nombre": "Losa", "tipo": "losa"})).json()["id"]
    r = await control.post(f"{RUTA}/{losa}/insumos", json={"insumos": [{"insumo_id": str(catalogo["ACR-00001"])}]})
    assert r.status_code == 422 and "aún no tiene lista" in r.json()["detail"]


async def test_solo_control_de_obra_y_costos_escriben(residente: httpx.AsyncClient, control: httpx.AsyncClient, catalogo) -> None:
    k1 = (await _castillo(control)).json()["id"]
    cuerpo = {"insumos": [{"insumo_id": str(catalogo["ACE-00011"])}]}
    assert (await residente.post(f"{RUTA}/{k1}/insumos", json=cuerpo)).status_code == 403
    assert (await residente.delete(f"{RUTA}/{k1}/insumos/{catalogo['ACE-00011']}")).status_code == 403
    nuevo = {"clase": "herramienta", "clave": "INS-A001", "descripcion": "ANDAMIO", "unidad": "jornal"}
    assert (await residente.post(f"{RUTA}/{k1}/insumos-nuevos", json=nuevo)).status_code == 403
    # Leer sí puede.
    assert (await residente.get(f"{RUTA}/{k1}/insumos")).status_code == 200
    assert (await residente.get(f"{RUTA}/{k1}/comparacion")).status_code == 200


# --- 3. Insumos provisionales ------------------------------------------------------------------------------------


async def test_el_andamio_se_crea_provisional_y_sin_precio_y_se_agrega_al_elemento(control: httpx.AsyncClient, catalogo) -> None:
    k1 = (await _castillo(control)).json()["id"]
    r = await control.post(
        f"{RUTA}/{k1}/insumos-nuevos",
        json={"clase": "herramienta", "clave": "ins-a001", "descripcion": "ANDAMIO (renta por jornada)", "unidad": "JOR", "subfamilia": "Andamios"},
    )
    assert r.status_code == 201, r.text
    nuevo = r.json()["id"]
    # Queda disponible en la búsqueda, de su clase, provisional y sin precio (nunca se inventa uno).
    (a,) = (await control.get(f"{RUTA}/{k1}/insumos-disponibles", params={"clase": "herramienta"})).json()
    assert a["id"] == nuevo and a["clave"] == "INS-A001" and a["provisional"] and a["sin_precio"] and a["precio"] is None
    assert (a["familia"], a["subfamilia"], a["unidad"], a["permitido"]) == ("Herramienta y equipo", "Andamios", "jornal", True)
    assert (await control.post(f"{RUTA}/{k1}/insumos", json={"insumos": [{"insumo_id": nuevo}]})).json() == {"agregados": 1}
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.connect() as conn:
            fila = (await conn.execute(text("select tipo::text, provisional, costo_base from insumo where id = :i"), {"i": nuevo})).one()
    finally:
        await motor.dispose()
    assert tuple(fila) == ("herramienta", True, 0)
    # La clave no se repite.
    r = await control.post(f"{RUTA}/{k1}/insumos-nuevos", json={"clase": "herramienta", "clave": "INS-A001", "descripcion": "x", "unidad": "jornal"})
    assert r.status_code == 422 and "Ya existe un insumo con la clave INS-A001" in r.json()["detail"]
    # Herramienta y equipo es una clase libre: sirve para cualquier tipo de elemento.
    cadena = (await control.post(RUTA, json={"clave": "CE-1", "nombre": "Cadena", "tipo": "lineal"})).json()["id"]
    assert (await control.post(f"{RUTA}/{cadena}/insumos", json={"insumos": [{"insumo_id": nuevo}]})).json() == {"agregados": 1}


async def test_un_insumo_nuevo_solo_se_crea_en_las_familias_del_tipo(control: httpx.AsyncClient, catalogo) -> None:
    k1 = (await _castillo(control)).json()["id"]
    r = await control.post(
        f"{RUTA}/{k1}/insumos-nuevos",
        json={"clase": "material", "clave": "INS-9001", "descripcion": "ANILLO 15X30", "unidad": "kg", "familia": "Aceros", "subfamilia": "Prefabricado"},
    )
    assert r.status_code == 201, r.text
    r = await control.post(
        f"{RUTA}/{k1}/insumos-nuevos",
        json={"clase": "material", "clave": "INS-9002", "descripcion": "PIEDRA", "unidad": "m3", "familia": "Pétreos"},
    )
    assert r.status_code == 422 and "no es de las familias" in r.json()["detail"]
    r = await control.post(f"{RUTA}/{k1}/insumos-nuevos", json={"clase": "material", "clave": "INS-9003", "descripcion": "x", "unidad": "kg"})
    assert r.status_code == 422 and "Elige la familia" in r.json()["detail"]
    r = await control.post(f"{RUTA}/{k1}/insumos-nuevos", json={"clase": "material", "clave": "INS-9004", "descripcion": "x", "unidad": "galón", "familia": "Aceros"})
    assert r.status_code == 422 and "no existe en el catálogo de unidades" in r.json()["detail"]
    # El nuevo ya sale en la búsqueda, provisional y sin precio, y se puede elegir como material del elemento.
    (n,) = (await control.get(f"{RUTA}/{k1}/insumos-disponibles", params={"q": "INS-9001"})).json()
    assert n["provisional"] and n["sin_precio"] and n["permitido"] and n["subfamilia"] == "Prefabricado"
    assert (await control.patch(f"{RUTA}/{k1}", json={"materiales": {"anillo": "INS-9001"}})).status_code == 204


# --- 4. Comparación con el concepto del catálogo --------------------------------------------------------------------


async def _concepto(escenario, clave: str, unidad: str, filas: list[tuple[str, str, str | None, str | None, float]]) -> uuid.UUID:
    """Un concepto con su composición: (tipo_hijo, categoria, insumo, concepto hijo, cantidad)."""
    org = str(escenario.org_id)
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            cid = (
                await c.execute(
                    text("insert into concepto (org_id, clave, descripcion) values (:o, :k, :d) returning id"),
                    {"o": org, "k": clave, "d": f"Concepto {clave} ({unidad})"},
                )
            ).scalar_one()
            for orden, (tipo_hijo, categoria, insumo, hijo, cantidad) in enumerate(filas):
                await c.execute(
                    text(
                        "insert into explosion (org_id, concepto_id, tipo_hijo, insumo_id, concepto_hijo_id, categoria, cantidad, orden) "
                        "values (:o, :c, cast(:t as tipo_hijo_explosion), (select id from insumo where org_id = :o and clave = :i), "
                        "(select id from concepto where org_id = :o and clave = :h), cast(:g as categoria_explosion), :q, :n)"
                    ),
                    {"o": org, "c": str(cid), "t": tipo_hijo, "i": insumo, "h": hijo, "g": categoria, "q": cantidad, "n": orden},
                )
    finally:
        await motor.dispose()
    return uuid.UUID(str(cid))


async def test_la_comparacion_pone_lado_a_lado_el_elemento_y_el_concepto_del_catalogo(control: httpx.AsyncClient, catalogo, escenario) -> None:
    # EST-02110 (ANALISIS_DE_BASICOS_CONCEPTOS): colado y cimbra del castillo por ml; el destajo no se compara.
    est = await _concepto(
        escenario, "EST-02110", "ml",
        [
            ("insumo", "material", "ACE-00001", None, 0.210987),
            ("insumo", "material", "MEZ-01020", None, 0.023625),
            ("insumo", "material", "ACE-00012", None, 0.017021),
            ("insumo", "material", "ACE-00013", None, 0.02),
            ("insumo", "destajo", "MOE-02020", None, 1.0),
            ("insumo", "material", "MAD-00004", None, 0.01),
        ],
    )
    k1 = (
        await _castillo(
            control, parametros={"alto": 2.5},
            materiales={"concreto": "MEZ-01020", "alambre": "ACE-00001", "cimbra": {"ACE-00012": 0.0175, "MAD-00001": 0.3}},
        )
    ).json()["id"]
    alta = await control.post(
        f"{RUTA}/{k1}/conceptos-por-contexto", json={"concepto_id": str(est), "unidad": "ml", "toma": {"concreto": True, "cimbra": True, "alambre": True}}
    )
    assert alta.status_code == 201, alta.text
    r = await control.get(f"{RUTA}/{k1}/comparacion")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert (cuerpo["umbral_igual_pct"], cuerpo["umbral_aproximado_pct"]) == (3.0, 8.0)
    (c,) = cuerpo["conceptos"]
    assert c["concepto_clave"] == "EST-02110" and c["estado"] == "autorizado" and not c["sin_catalogo"] and c["avisos"] == []
    por = {f["clave"]: f for f in c["filas"]}
    # El castillo de 15×15 y 2.5 m, por ml: 0.0225 m³ de concreto contra 0.023625 del catálogo (−4.76 %, ≈).
    assert por["MEZ-01020"]["elemento"] == pytest.approx(0.0225) and por["MEZ-01020"]["catalogo"] == pytest.approx(0.023625)
    assert por["MEZ-01020"]["diferencia_pct"] == pytest.approx(-4.76, abs=0.01) and por["MEZ-01020"]["marca"] == "≈"
    assert por["MEZ-01020"]["descripcion"] == "CONCRETO H.O. F'C=150" and por["MEZ-01020"]["unidad"] == "m3"
    # Clavos: 0.0175 kg por pieza ÷ 2.5 m = 0.007 kg/ml contra 0.017021 (≠); las tablas solo están en el catálogo.
    assert por["ACE-00012"]["elemento"] == pytest.approx(0.007) and por["ACE-00012"]["marca"] == "≠"
    assert por["ACE-00013"]["marca"] == "solo_catalogo" and por["MAD-00004"]["marca"] == "solo_catalogo"
    assert por["MAD-00001"]["marca"] == "solo_elemento" and por["MAD-00001"]["elemento"] == pytest.approx(0.12)
    # El alambre del amarre del elemento por ml, contra los 0.21 kg del catálogo.
    assert por["ACE-00001"]["marca"] == "≠" and por["ACE-00001"]["catalogo"] == pytest.approx(0.210987)
    assert "MOE-02020" not in por
    assert [m["clave"] for m in c["mano_de_obra"]] == ["MOE-02020"]
    assert c["resumen"]["solo_catalogo"] == 2 and c["resumen"]["solo_elemento"] == 1 and c["resumen"]["aproximado"] == 1
    assert not c["coincide"]
    # Filtrar por la fila del concepto da el mismo bloque.
    una = (await control.get(f"{RUTA}/{k1}/comparacion", params={"fila_id": c["fila_id"]})).json()
    assert una["conceptos"][0]["concepto_clave"] == "EST-02110"
    assert (await control.get(f"{RUTA}/{k1}/comparacion", params={"fila_id": str(uuid.uuid4())})).status_code == 404


async def test_la_comparacion_expande_el_auxiliar_hasta_los_insumos(control: httpx.AsyncClient, catalogo, escenario) -> None:
    await _concepto(escenario, "AUX-04010", "m2", [("insumo", "material", "MEZ-07010", None, 0.0447)])
    est = await _concepto(
        escenario, "EST-07010", "pza",
        [("concepto", "auxiliar", None, "AUX-04010", 3.36), ("insumo", "material", "MEZ-01020", None, 0.099225), ("insumo", "destajo", "MOE-02020", None, 1.0)],
    )
    k1 = (await _castillo(control, materiales={"concreto": "MEZ-01020"}, parametros={"largo": 0.15, "ancho": 0.15, "alto": 4.2, "rec": 0.025})).json()["id"]
    assert (await control.post(f"{RUTA}/{k1}/conceptos-por-contexto", json={"concepto_id": str(est), "unidad": "pza", "toma": {"concreto": True}})).status_code == 201
    (c,) = (await control.get(f"{RUTA}/{k1}/comparacion")).json()["conceptos"]
    por = {f["clave"]: f for f in c["filas"]}
    assert por["MEZ-07010"]["catalogo"] == pytest.approx(0.150192) and por["MEZ-07010"]["marca"] == "solo_catalogo"  # el elemento no lleva mezcla
    # 0.15 × 0.15 × 4.2 = 0.0945 m³ contra 0.099225 (el catálogo cuenta 5 % de desperdicio): −4.76 %.
    assert por["MEZ-01020"]["elemento"] == pytest.approx(0.0945) and por["MEZ-01020"]["marca"] == "≈"


async def test_un_concepto_propuesto_no_tiene_con_que_compararse_y_sin_materiales_se_avisa(control: httpx.AsyncClient, catalogo) -> None:
    k1 = (await _castillo(control)).json()["id"]
    r = await control.post(
        f"{RUTA}/{k1}/conceptos-por-contexto",
        json={"clave_propuesta": "EJ-420", "descripcion": "Castillo de entrepiso", "unidad": "ml", "toma": {"concreto": True, "cimbra": True}},
    )
    assert r.status_code == 201, r.text
    (c,) = (await control.get(f"{RUTA}/{k1}/comparacion")).json()["conceptos"]
    assert c["sin_catalogo"] and c["estado"] == "propuesto" and c["filas"] == []
    assert any("concreto" in a for a in c["avisos"]) and any("cimbra" in a for a in c["avisos"])
    # Un elemento sin conceptos no trae bloques.
    vacio = (await _castillo(control, "K-9", parametros={"alto": 3.3})).json()["id"]
    assert (await control.get(f"{RUTA}/{vacio}/comparacion")).json()["conceptos"] == []
    assert (await control.get(f"{RUTA}/{uuid.uuid4()}/comparacion")).status_code == 404
