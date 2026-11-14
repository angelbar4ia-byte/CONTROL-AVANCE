"""La biblioteca de elementos paramétricos por HTTP contra Postgres real: categoría, subcategoría y firma anti-duplicados."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.api.dependencias import contexto_actual
from obractrl.domain.cuantificacion.clasificacion_de_elementos import firma_de_elemento
from obractrl.domain.cuantificacion.elementos_parametricos import (
    PARAMETROS_POR_TIPO,
    normalizar_parametros,
)
from obractrl.infrastructure.db.sesion import ContextoSesion
from obractrl.main import crear_app
from tests.integracion.conftest import DATABASE_URL_ADMIN

RUTA = "/api/v1/elementos-parametricos"


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


@pytest.fixture
async def residente(contexto_residente: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_residente) as c:
        yield c


def _cadena(clave: str, **extra: object) -> dict[str, object]:
    return {"clave": clave, "nombre": f"Cadena {clave}", "tipo": "lineal", "parametros": {"ancho": 0.15, "alto": 0.2}, **extra}


async def _elemento(cliente: httpx.AsyncClient, clave: str) -> dict:
    return next(e for e in (await cliente.get(RUTA)).json() if e["clave"] == clave)


async def test_un_elemento_sin_clasificar_nace_con_la_de_su_tipo(control: httpx.AsyncClient) -> None:
    k = await control.post(RUTA, json={"clave": "K-1", "nombre": "Castillo", "tipo": "castillo"})
    c = await control.post(RUTA, json=_cadena("CE-1"))
    z = await control.post(RUTA, json={"clave": "Z-1", "nombre": "Zapata", "tipo": "zapata"})
    assert (k.status_code, c.status_code, z.status_code) == (201, 201, 201)
    visto = {e["clave"]: (e["categoria"], e["subcategoria"]) for e in (await control.get(RUTA)).json()}
    assert visto == {"K-1": ("castillos", "muro"), "CE-1": ("cadenas", "cerramiento"), "Z-1": ("zapatas", "aislada")}


async def test_dos_elementos_identicos_se_rechazan_con_la_clave_del_que_ya_existe(control: httpx.AsyncClient) -> None:
    assert (await control.post(RUTA, json=_cadena("CE-1"))).status_code == 201
    r = await control.post(RUTA, json=_cadena("CE-2"))
    assert r.status_code == 409, r.text
    cuerpo = r.json()
    assert cuerpo["clave_igual"] == "CE-1"
    assert "idéntico" in cuerpo["detail"]
    assert [e["clave"] for e in (await control.get(RUTA)).json()] == ["CE-1"]  # el segundo no se guardó
    # Cualquier diferencia en las medidas, el armado o la cimbra lo hace otro elemento.
    for clave, parametros in (
        ("CE-3", {"ancho": 0.15, "alto": 0.25}),
        ("CE-4", {"ancho": 0.15, "alto": 0.2, "n_sup": 2}),
        ("CE-5", {"ancho": 0.15, "alto": 0.2, "lados": 2}),
    ):
        assert (await control.post(RUTA, json=_cadena(clave, parametros=parametros))).status_code == 201, clave


async def test_cerramiento_y_desplante_de_la_misma_geometria_conviven(control: httpx.AsyncClient) -> None:
    ce = await control.post(RUTA, json=_cadena("CE-1", categoria="cadenas", subcategoria="cerramiento"))
    cd = await control.post(RUTA, json=_cadena("CD-1", categoria="cadenas", subcategoria="desplante"))
    assert (ce.status_code, cd.status_code) == (201, 201), (ce.text, cd.text)
    # Un segundo desplante idéntico sí es duplicado; y lo es de CD-1, no de CE-1.
    r = await control.post(RUTA, json=_cadena("CD-2", subcategoria="desplante"))
    assert r.status_code == 409 and r.json()["clave_igual"] == "CD-1"
    assert (await _elemento(control, "CD-1"))["subcategoria"] == "desplante"


async def test_la_clasificacion_tiene_que_existir_y_ser_del_tipo(control: httpx.AsyncClient) -> None:
    for extra in (
        {"categoria": "puentes"},
        {"categoria": "cadenas", "subcategoria": "azotea"},
        {"categoria": "castillos", "subcategoria": "muro"},  # un elemento lineal no es un castillo
    ):
        r = await control.post(RUTA, json=_cadena("X-1", **extra))
        assert r.status_code == 422, (extra, r.text)
    assert (await control.get(RUTA)).json() == []


async def test_reclasificar_cambia_la_identidad_y_no_puede_chocar(control: httpx.AsyncClient) -> None:
    assert (await control.post(RUTA, json=_cadena("CE-1"))).status_code == 201
    cd = (await control.post(RUTA, json=_cadena("CD-1", subcategoria="desplante"))).json()["id"]
    # CD-1 pasaría a ser un CE-1 idéntico: se rechaza y se queda como estaba.
    r = await control.patch(f"{RUTA}/{cd}", json={"subcategoria": "cerramiento"})
    assert r.status_code == 409 and r.json()["clave_igual"] == "CE-1"
    assert (await _elemento(control, "CD-1"))["subcategoria"] == "desplante"
    # Hacia una subcategoría libre sí se puede; la categoría sola toma la primera subcategoría de la nueva.
    assert (await control.patch(f"{RUTA}/{cd}", json={"categoria": "dalas"})).status_code == 204
    assert {k: (await _elemento(control, "CD-1"))[k] for k in ("categoria", "subcategoria")} == {
        "categoria": "dalas",
        "subcategoria": "cerramiento",
    }
    # Reclasificar no es cambiar la receta: no nace una versión nueva.
    assert (await _elemento(control, "CD-1"))["version"] == 1
    assert (await control.patch(f"{RUTA}/{cd}", json={"categoria": "castillos"})).status_code == 422


async def test_cambiar_las_medidas_hasta_igualar_a_otro_elemento_se_rechaza(control: httpx.AsyncClient) -> None:
    assert (await control.post(RUTA, json=_cadena("CE-1"))).status_code == 201
    otro = (await control.post(RUTA, json=_cadena("CE-2", parametros={"ancho": 0.15, "alto": 0.3}))).json()["id"]
    r = await control.patch(f"{RUTA}/{otro}", json={"parametros": {"alto": 0.2}})
    assert r.status_code == 409 and r.json()["clave_igual"] == "CE-1"
    assert (await _elemento(control, "CE-2"))["parametros"]["alto"] == 0.3
    # Renombrar no cambia la identidad: sale sin problema.
    assert (await control.patch(f"{RUTA}/{otro}", json={"nombre": "Otro nombre"})).status_code == 204


async def test_dos_altas_identicas_a_la_vez_dejan_una_sola(control: httpx.AsyncClient) -> None:
    respuestas = await asyncio.gather(*(control.post(RUTA, json=_cadena(f"CE-{n}")) for n in range(1, 6)))
    codigos = sorted(r.status_code for r in respuestas)
    assert codigos == [201, 409, 409, 409, 409], [r.text for r in respuestas]
    assert len((await control.get(RUTA)).json()) == 1


async def test_el_catalogo_de_clasificacion_trae_los_limites_de_posicion(
    control: httpx.AsyncClient, residente: httpx.AsyncClient
) -> None:
    r = await residente.get(f"{RUTA}/clasificacion")
    assert r.status_code == 200
    cats = {c["clave"]: c for c in r.json()}
    cadenas = {s["clave"]: s for s in cats["cadenas"]["subcategorias"]}
    assert cats["cadenas"]["tipo"] == "lineal"
    assert cadenas["desplante"]["posiciones"] == ["desplante"]
    assert cadenas["cerramiento"]["posiciones"] == ["cerramiento", "remate"]
    assert cats["castillos"]["subcategorias"][0]["posiciones"] is None
    assert cats["trabes"]["subcategorias"][0]["en_muro"] is False


async def test_la_firma_de_la_base_es_la_misma_que_la_del_dominio(control: httpx.AsyncClient) -> None:
    """`app.firma_elemento` (migración 0127) y `firma_de_elemento` arman la misma cadena: el índice único y la
    comparación del servidor no se contradicen."""
    for clave, tipo in (("K-1", "castillo"), ("CE-1", "lineal"), ("Z-1", "zapata"), ("L-1", "losa")):
        assert (await control.post(RUTA, json={"clave": clave, "nombre": clave, "tipo": tipo})).status_code == 201
    raros = {"ancho": 0.1234567, "rec": 0.025, "alto": 3.0, "desp": 0.0, "gancho": 0.1}
    assert (await control.post(RUTA, json={"clave": "CE-9", "nombre": "x", "tipo": "lineal", "parametros": raros})).status_code == 201
    engine = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with engine.connect() as conn:
            filas = (
                await conn.execute(
                    text(
                        "select clave, tipo, categoria, subcategoria, parametros, firma, "
                        "app.firma_elemento(categoria, subcategoria, tipo, parametros) as de_la_base "
                        "from elemento_parametrico where clave in ('K-1','CE-1','Z-1','L-1','CE-9')"
                    )
                )
            ).mappings().all()
    finally:
        await engine.dispose()
    assert len(filas) == 5
    for f in filas:
        esperada = firma_de_elemento(f["categoria"], f["subcategoria"], f["tipo"], normalizar_parametros(f["tipo"], f["parametros"]))
        assert f["firma"] == f["de_la_base"] == esperada, f["clave"]
    assert set(PARAMETROS_POR_TIPO) == {"castillo", "lineal", "zapata", "losa"}


async def test_un_elemento_viejo_sin_firma_tambien_se_compara(escenario, control: httpx.AsyncClient) -> None:
    """Los duplicados anteriores a la 0127 quedan sin firma: el servidor los compara con la que calcula la base al vuelo."""
    completos = normalizar_parametros("lineal", {"ancho": 0.15, "alto": 0.2})
    engine = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "insert into elemento_parametrico (org_id, clave, nombre, tipo, parametros, categoria, subcategoria, firma) "
                    "values (:o, 'VIEJO-1', 'Viejo', 'lineal', cast(:p as jsonb), 'cadenas', 'cerramiento', null)"
                ),
                {"o": str(escenario.org_id), "p": json.dumps(completos)},
            )
    finally:
        await engine.dispose()
    r = await control.post(RUTA, json=_cadena("CE-2"))
    assert r.status_code == 409 and r.json()["clave_igual"] == "VIEJO-1", r.text
    # Y editarlo sin cambiar su receta ni su clasificación no lo compara contra nadie: se puede renombrar.
    viejo = (await _elemento(control, "VIEJO-1"))["id"]
    assert (await control.patch(f"{RUTA}/{viejo}", json={"nombre": "Viejo renombrado"})).status_code == 204
