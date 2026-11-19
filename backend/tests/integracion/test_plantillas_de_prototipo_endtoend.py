"""Plantillas de muro por prototipo (migración 0136) por HTTP contra Postgres real.

El muro confinado lleva VARIOS castillos, cada uno con su regla (cada separación y extremos, solo extremos, por ml, total del prototipo);
hay una variante por prototipo y planta (Oro PB y PA son el ejemplo, con su fila y celda del Excel y «por confirmar») y una global de 1 y de
2 plantas. Las cadenas y los castillos estimados alimentan los conceptos al elegir la plantilla en el muro (no hace falta colocarlos).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

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
PARTES = [{"nombre": "Cuerpo", "desde_m": "0", "hasta_m": "3", "rol": "cuerpo"}]


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


async def _castillo(control: httpx.AsyncClient, clave: str, n: int) -> str:
    # La firma del elemento es única: un largo propio por castillo evita el 409 de «ya existe uno igual».
    r = await control.post(ELEMENTOS, json={"clave": clave, "nombre": f"Castillo {clave}", "tipo": "castillo", "parametros": {"largo": 0.15 + n / 1000}})
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


async def _cadena(control: httpx.AsyncClient, clave: str, n: int) -> str:
    r = await control.post(
        ELEMENTOS,
        json={
            "clave": clave, "nombre": f"Cadena {clave}", "tipo": "lineal", "categoria": "cadenas", "subcategoria": "cerramiento",
            "parametros": {"ancho": 0.15, "alto": 0.2 + n / 1000},
        },
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


async def _elementos_de_oro(control: httpx.AsyncClient) -> dict[str, str]:
    ids = {k: await _castillo(control, k, n) for n, k in enumerate(("K-1", "K-2", "K-3", "K-6", "K-7"))}
    ids["CE-1"] = await _cadena(control, "CE-1", 1)
    ids["CE-2"] = await _cadena(control, "CE-2", 2)
    return ids


async def test_los_prototipos_dicen_que_plantilla_tiene_cada_planta_y_cuales_siguen_vacios(control: httpx.AsyncClient) -> None:
    await _elementos_de_oro(control)
    for planta in ("PB", "PA"):
        c = await control.post(
            PLANTILLAS,
            json={"nombre": f"Oro {planta}", "tipo": "confinado", "material": "tabique_rojo", "ubicacion": "interior", "partes": PARTES, "prototipo": "oro_401", "planta": planta, "elementos": [{"ref": "K-1"}]},
        )
        assert c.status_code == 201, c.text
    r = await control.get("/api/v1/muro-artefacto/prototipos")
    assert r.status_code == 200, r.text
    por_clave = {p["clave"]: p for p in r.json()}
    assert [(p["planta"], p["plantilla_id"] is not None) for p in por_clave["oro_401"]["plantillas"]] == [("PB", True), ("PA", True)]
    assert [(p["planta"], p["plantilla_id"]) for p in por_clave["zafiro_1"]["plantillas"]] == [("PB", None)]  # 1 planta: solo PB
    assert [p["planta"] for p in por_clave["diamante_mas"]["plantillas"]] == ["PB", "PA"]
    assert por_clave["global_2"]["es_global"] is True and [p["planta"] for p in por_clave["global_2"]["plantillas"]] == [None]
    assert por_clave["zafiro_1"]["plantas"] == 1 and por_clave["oro_401"]["plantas"] == 2


async def test_una_plantilla_de_un_prototipo_sin_datos_se_captura_con_su_planta(control: httpx.AsyncClient) -> None:
    await _elementos_de_oro(control)
    cuerpo = {
        "nombre": "Zafiro 1.0 · PB", "tipo": "confinado", "material": "tabique_rojo", "ubicacion": "interior", "partes": PARTES,
        "prototipo": "zafiro_1", "planta": "PB", "por_confirmar": True, "notas": "Captura pendiente.",
        "elementos": [{"ref": "K-1", "regla": "por_ml", "piezas_por_ml": "0.4"}],
    }
    r = await control.post(PLANTILLAS, json=cuerpo)
    assert r.status_code == 201, r.text
    assert (r.json()["prototipo"], r.json()["planta"]) == ("zafiro_1", "PB")
    # Un prototipo de 1 planta no tiene PA; la global no lleva planta; un prototipo sin planta no vale; ni con otro tipo de muro.
    for malo in (
        {"nombre": "Zafiro PA", "planta": "PA"},
        {"nombre": "Global con planta", "prototipo": "global_1", "planta": "PB"},
        {"nombre": "Sin planta", "planta": None},
        {"nombre": "Prototipo inexistente", "prototipo": "platino"},
        {"nombre": "Con cadena", "tipo": "con_cadena", "elementos": []},
        {"nombre": "Planta sin prototipo", "prototipo": None, "planta": "PB"},
    ):
        x = await control.post(PLANTILLAS, json={**cuerpo, **malo})
        assert x.status_code == 422, (malo, x.text)


async def test_las_reglas_de_castillo_se_validan_y_un_muro_con_cadena_solo_admite_separacion_o_extremos(control: httpx.AsyncClient) -> None:
    await _elementos_de_oro(control)
    base = {"nombre": "R", "tipo": "confinado", "material": "tabique_rojo", "ubicacion": "interior", "partes": PARTES}
    ok = await control.post(
        PLANTILLAS,
        json={**base, "elementos": [
            {"ref": "K-1", "regla": "separacion", "sep_m": "2.5"}, {"uid": "K-2", "ref": "K-2", "regla": "extremos"},
            {"ref": "K-3", "regla": "por_ml", "piezas_por_ml": "0.5"}, {"ref": "K-7", "regla": "total", "total_m": "24", "base_m2": "286"},
        ]},
    )
    assert ok.status_code == 201, ok.text
    por_ref = {e["ref"]: e for e in ok.json()["elementos"]}
    assert (por_ref["K-1"]["regla"], por_ref["K-1"]["sep_m"]) == ("separacion", "2.5")
    assert (por_ref["K-2"]["regla"], por_ref["K-2"]["sep_m"]) == ("extremos", None)
    for malo in (
        {"ref": "K-1", "regla": "por_ml"},  # sin piezas por ml
        {"ref": "K-1", "regla": "total", "total_m": "24"},  # sin base
        {"ref": "K-1", "regla": "al_tanteo"},
    ):
        x = await control.post(PLANTILLAS, json={**base, "nombre": "Mala", "elementos": [malo]})
        assert x.status_code == 422, (malo, x.text)
    # Un castillo que se coloca en el plano (con cadena) tiene piezas enteras: ni «por ml» ni «total».
    x = await control.post(PLANTILLAS, json={**base, "nombre": "Con cadena", "tipo": "con_cadena", "elementos": [{"ref": "K-1", "regla": "total", "total_m": "5", "base_m2": "10"}]})
    assert x.status_code == 422 and "por ml" in x.text
    # Sin regla (las plantillas de antes) se normaliza: separación propia, o extremos al colocar y la del driver al estimar.
    legado = await control.post(PLANTILLAS, json={**base, "nombre": "Legado", "elementos": [{"ref": "K-1", "sep_m": "2"}, {"ref": "K-2"}]})
    assert [(e["regla"], e["sep_m"]) for e in legado.json()["elementos"]] == [("separacion", "2"), ("separacion", None)]


# --- Lo que la plantilla coloca y a qué conceptos alimenta ---------------------------------------------------------------------


@pytest.fixture
async def arbol(escenario: Escenario) -> dict[str, str]:
    """Conceptos del catálogo (acero en pza con escalón, colado en ml, cadena en ml), su partida en planta baja y una actividad por concepto."""
    ids = {k: uuid.uuid4() for k in ("m2", "pza", "ml", "muro", "acero", "colado", "cadena", "n1", "etapa", "a_acero", "a_colado", "a_cadena")}
    org, proto, obra = str(escenario.org_id), str(escenario.prototipo_id), str(escenario.obra_id)
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            for k, clave in (("m2", "m2"), ("pza", "pza"), ("ml", "ml")):
                await c.execute(text("insert into unidad (id, org_id, clave, nombre) values (:i, :o, :c, :c)"), {"i": str(ids[k]), "o": org, "c": clave})
            for k, clave, unidad in (("muro", "MUR-1", "m2"), ("acero", "ACE-1", "pza"), ("colado", "COL-1", "ml"), ("cadena", "CAD-1", "ml")):
                await c.execute(
                    text("insert into concepto (id, org_id, clave, descripcion, unidad_id) values (:i, :o, :k, :k, :u)"),
                    {"i": str(ids[k]), "o": org, "k": clave, "u": str(ids[unidad])},
                )
            await c.execute(text("insert into nivel (id, org_id, clave, descripcion, orden) values (:i, :o, 'NIV-1', 'Planta baja', 1)"), {"i": str(ids["n1"]), "o": org})
            await c.execute(text("insert into etapa_constructiva (id, org_id, clave, descripcion, orden) values (:i, :o, 'ECO-1', 'Estructura', 1)"), {"i": str(ids["etapa"]), "o": org})
            await c.execute(
                text("update actividad set concepto_id = :c, nivel_id = :n, etapa_id = :e, precio_unitario = 10, cant_base = 500, cant_programada = 500 where id = :a"),
                {"c": str(ids["muro"]), "n": str(ids["n1"]), "e": str(ids["etapa"]), "a": str(escenario.actividad_id)},
            )

            async def nodo(ident: uuid.UUID, padre: uuid.UUID | None, tipo: str, nombre: str, **kw: uuid.UUID) -> None:
                await c.execute(
                    text(
                        "insert into prototipo_nodo (id, org_id, prototipo_id, parent_id, tipo, nombre, clave, concepto_id, nivel_id, etapa_id, orden) "
                        "values (:i, :o, :p, cast(:pa as uuid), cast(:t as tipo_prototipo_nodo), :n, :n, cast(:c as uuid), cast(:ni as uuid), cast(:et as uuid), 0)"
                    ),
                    {
                        "i": str(ident), "o": org, "p": proto, "pa": str(padre) if padre else None, "t": tipo, "n": nombre,
                        "c": str(kw["concepto"]) if "concepto" in kw else None,
                        "ni": str(kw["nivel"]) if "nivel" in kw else None, "et": str(kw["etapa"]) if "etapa" in kw else None,
                    },
                )

            pb, pb_e = uuid.uuid4(), uuid.uuid4()
            await nodo(pb, None, "nivel", "Planta baja", nivel=ids["n1"])
            await nodo(pb_e, pb, "etapa", "Estructura", etapa=ids["etapa"])
            for nombre in ("acero", "colado", "cadena"):
                await nodo(uuid.uuid4(), pb_e, "concepto", nombre, concepto=ids[nombre])
            for k, concepto in (("a_acero", "acero"), ("a_colado", "colado"), ("a_cadena", "cadena")):
                await c.execute(
                    text(
                        "insert into actividad (id, org_id, obra_id, concepto_id, nivel_id, etapa_id, cant_base, cant_programada, precio_unitario) "
                        "values (:i, :o, :ob, :c, :n, :e, 100, 100, 10)"
                    ),
                    {"i": str(ids[k]), "o": org, "ob": obra, "c": str(ids[concepto]), "n": str(ids["n1"]), "e": str(ids["etapa"])},
                )
    finally:
        await motor.dispose()
    return {k: str(v) for k, v in ids.items()}


async def _conceptos_de_los_elementos(control: httpx.AsyncClient, arbol: dict[str, str], ids: dict[str, str]) -> None:
    ruta = f"{ELEMENTOS}/{ids['K-1']}/conceptos-por-contexto"
    for cuerpo in (
        {"concepto_id": arbol["acero"], "unidad": "pza", "toma": {"acero": True, "estribos": True, "alambre": True}, "alto_hasta_m": "6"},
        {"concepto_id": arbol["colado"], "unidad": "ml", "toma": {"concreto": True, "cimbra": True}},
    ):
        r = await control.post(ruta, json=cuerpo)
        assert r.status_code == 201, r.text
    r = await control.post(
        f"{ELEMENTOS}/{ids['CE-1']}/conceptos-por-contexto",
        json={"concepto_id": arbol["cadena"], "unidad": "ml", "toma": {"concreto": True, "acero": True, "estribos": True, "alambre": True, "cimbra": True}},
    )
    assert r.status_code == 201, r.text


async def _muro(control: httpx.AsyncClient, escenario: Escenario) -> str:
    plano = (await control.post(f"/api/v1/obras/{escenario.obra_id}/planos", json={"nombre": "P", "archivo_url": "e2e/p.pdf"})).json()["id"]
    r = await control.post(
        f"/api/v1/planos/{plano}/trazos",
        json={
            "version_plano": 1, "fuente": "pdf", "geometria_wkt": "LINESTRING(0 0, 10 0)", "grosor_m": "0.15", "alineacion": "centro",
            "enlaces": [{"medida": "longitud", "factor": "1", "actividad_id": str(escenario.actividad_id), "conversion": {"modo": "area", "mide": "eje"}}],
        },
    )
    assert r.status_code == 201, r.text
    return str(r.json()["trazo_id"])


async def _medido(control: httpx.AsyncClient, escenario: Escenario, actividad: str) -> float | None:
    estado = (await control.get(f"/api/v1/obras/{escenario.obra_id}/cuantificacion")).json()
    nodo = next((n for n in estado if n["nodo_id"] == actividad), None)
    return float(nodo["cantidad_medida"]) if nodo and nodo["cantidad_medida"] is not None else None


async def test_elegir_la_plantilla_alimenta_los_conceptos_de_las_cadenas_y_los_castillos_estimados_y_desligarla_los_quita(
    control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, str]
) -> None:
    ids = await _elementos_de_oro(control)
    await _conceptos_de_los_elementos(control, arbol, ids)
    plantilla = (
        await control.post(
            PLANTILLAS,
            json={
                "nombre": "Confinado Oro", "tipo": "confinado", "material": "tabique_rojo", "ubicacion": "interior", "partes": PARTES,
                "elementos": [{"ref": "K-1", "regla": "total", "total_m": "126", "base_m2": "286"}, {"ref": "CE-1"}],
            },
        )
    ).json()
    muro = await _muro(control, escenario)
    assert await _medido(control, escenario, arbol["a_cadena"]) is None  # sin plantilla no hay nada que tomar

    r = await control.put(f"/api/v1/trazos/{muro}/muro/plantilla", json={"plantilla_id": plantilla["id"]})
    assert r.status_code == 200, r.text
    # 10 m × 3.00 m = 30 m²: K-1 lleva 126 × 30 ÷ 286 = 13.217 m de castillo (4.406 piezas de 3.00 m); la cadena, los 10 m del muro.
    assert await _medido(control, escenario, arbol["a_cadena"]) == pytest.approx(10)
    assert await _medido(control, escenario, arbol["a_colado"]) == pytest.approx(13.218, abs=0.01)
    assert await _medido(control, escenario, arbol["a_acero"]) == pytest.approx(4.406, abs=0.01)

    v = (await control.get(f"/api/v1/trazos/{muro}/muro/plantilla/colocacion")).json()
    por_ref = {e["ref"]: e for e in v["elementos"]}
    k, cadena = por_ref["K-1"], por_ref["CE-1"]
    assert (k["regla"], k["modo"], k["piezas"], k["se_coloca"], k["colocados"]) == ("total", "estimado", 5, False, 0)
    assert Decimal(k["piezas_estimadas"]) == Decimal("4.406")
    assert Decimal(k["metros"]) == pytest.approx(Decimal("13.218"), abs=Decimal("0.01"))
    assert "ASIGNACIÓN" not in (k["origen"] or "")  # este K-1 lo capturó el usuario sin celda de origen
    # La cadena ya no solo se reporta: cada concepto que la paga cuenta sus metros.
    assert cadena["clase"] == "cadena" and Decimal(cadena["metros"]) == Decimal(10)
    (c,) = cadena["conceptos"]
    assert (c["clave"], c["unidad"], Decimal(c["cantidad"]), c["cuenta"]) == ("CAD-1", "ml", Decimal(10), True)

    # Desligar la plantilla del muro quita lo que tomaban.
    r = await control.put(f"/api/v1/trazos/{muro}/muro/plantilla", json={"plantilla_id": None})
    assert r.status_code == 200, r.text
    for actividad in ("a_cadena", "a_colado", "a_acero"):
        assert not await _medido(control, escenario, arbol[actividad])


async def test_si_falta_la_partida_de_la_cadena_en_el_arbol_avisa_y_no_cuenta(
    control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, str]
) -> None:
    ids = await _elementos_de_oro(control)
    await _conceptos_de_los_elementos(control, arbol, ids)
    plantilla = (
        await control.post(PLANTILLAS, json={"nombre": "Solo cadena", "tipo": "confinado", "material": "tabique_rojo", "ubicacion": "interior", "partes": PARTES, "elementos": [{"ref": "CE-1"}]})
    ).json()
    muro = await _muro(control, escenario)
    motor = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with motor.begin() as c:
            await c.execute(text("delete from prototipo_nodo where concepto_id = :c"), {"c": arbol["cadena"]})
    finally:
        await motor.dispose()
    assert (await control.put(f"/api/v1/trazos/{muro}/muro/plantilla", json={"plantilla_id": plantilla["id"]})).status_code == 200
    v = (await control.get(f"/api/v1/trazos/{muro}/muro/plantilla/colocacion")).json()
    (c,) = v["elementos"][0]["conceptos"]
    assert (c["clave"], c["cuenta"], c["estado"]) == ("CAD-1", False, "falta_partida")
    assert not await _medido(control, escenario, arbol["a_cadena"])


async def test_editar_en_el_lugar_una_plantilla_por_validar_rehace_lo_que_toman_los_muros_que_la_usan(
    control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, str]
) -> None:
    ids = await _elementos_de_oro(control)
    await _conceptos_de_los_elementos(control, arbol, ids)
    cuerpo: dict[str, Any] = {
        "nombre": "Cadena", "tipo": "confinado", "material": "tabique_rojo", "ubicacion": "interior", "partes": PARTES, "elementos": [{"ref": "CE-1"}],
    }
    plantilla = (await control.post(PLANTILLAS, json=cuerpo)).json()
    muro = await _muro(control, escenario)
    assert (await control.put(f"/api/v1/trazos/{muro}/muro/plantilla", json={"plantilla_id": plantilla["id"]})).status_code == 200
    assert await _medido(control, escenario, arbol["a_cadena"]) == pytest.approx(10)
    # Se le quita la cadena a la plantilla (aún por validar: se edita en el lugar) y el muro deja de tomarla.
    r = await control.put(f"{PLANTILLAS}/{plantilla['id']}", json={**cuerpo, "elementos": []})
    assert r.status_code == 200 and r.json()["version_nueva"] is False, r.text
    assert not await _medido(control, escenario, arbol["a_cadena"])


async def test_la_regla_total_reparte_sobre_el_area_neta_con_los_vanos_ya_colocados_y_sin_vanos_es_el_bruto(
    control: httpx.AsyncClient, escenario: Escenario, arbol: dict[str, str]
) -> None:
    ids = await _elementos_de_oro(control)
    await _conceptos_de_los_elementos(control, arbol, ids)
    plantilla = (
        await control.post(
            PLANTILLAS,
            json={
                "nombre": "Total neto", "tipo": "confinado", "material": "tabique_rojo", "ubicacion": "interior", "partes": PARTES,
                "elementos": [{"ref": "K-1", "regla": "total", "total_m": "126", "base_m2": "286"}],
            },
        )
    ).json()
    muro = await _muro(control, escenario)
    assert (await control.put(f"/api/v1/trazos/{muro}/muro/plantilla", json={"plantilla_id": plantilla["id"]})).status_code == 200
    ruta = f"/api/v1/trazos/{muro}/muro/plantilla/colocacion"
    v = (await control.get(ruta)).json()
    assert (v["area_usada"], Decimal(v["area_bruta_m2"]), Decimal(v["vanos_m2"]), Decimal(v["area_neta_m2"])) == ("bruto", Decimal(30), Decimal(0), Decimal(30))
    assert Decimal(v["elementos"][0]["piezas_estimadas"]) == Decimal("4.406")  # 126 × 30 ÷ 286 ÷ 3.00
    assert await _medido(control, escenario, arbol["a_colado"]) == pytest.approx(13.218, abs=0.01)

    # Una puerta de 1 × 2 m (2 m²) hace neto al muro: 28 m² → 126 × 28 ÷ 286 = 12.336 m = 4.112 piezas; un castillo a mano no descuenta.
    puerta = await control.post(f"/api/v1/trazos/{muro}/vanos", json={"clave": "P-01", "tipo": "puerta", "ancho_m": "1", "alto_m": "2", "posicion_m": "5"})
    assert puerta.status_code == 201, puerta.text
    v = (await control.get(ruta)).json()
    assert (v["area_usada"], Decimal(v["vanos_m2"]), Decimal(v["area_neta_m2"])) == ("neto", Decimal(2), Decimal(28))
    assert Decimal(v["elementos"][0]["piezas_estimadas"]) == Decimal("4.112")
    assert await _medido(control, escenario, arbol["a_colado"]) == pytest.approx(12.336, abs=0.01)  # lo que toman los conceptos también es neto
