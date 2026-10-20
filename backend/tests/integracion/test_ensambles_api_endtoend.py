"""Ensambles por HTTP de punta a punta contra Postgres real (§11.2, §12.4).

A diferencia de `tests/api/*` —que sustituyen los repositorios por dobles
porque prueban la decisión, no el SQL—, aquí no hay dobles: la petición
cruza router → caso de uso → repositorio SQL → RLS. Lo que se fija es lo que
solo se ve de punta a punta:

 1. el contrato (rutas registradas, DTOs, `Decimal` serializado),
 2. el mapeo de errores de dominio a problem+json (404 / 409 / 422),
 3. el RBAC por rol (leer: C y SI; escribir: solo C),
 4. que el reporte de Generación entregue por HTTP lo mismo que el caso de
    uso: lo seguro se escribe, lo demás llega en `pendientes`.

`AsyncClient` sobre `ASGITransport` y no `TestClient`: el engine de pruebas
está atado al event loop de la prueba (ver `conftest._apuntar_backend_a_bd_de_prueba`)
y `TestClient` corre la app en otro hilo con otro loop.
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
from obractrl.adapters.repos.conceptos_sql import RepositorioConceptosSQL
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
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


async def _sembrar_concepto(
    contexto: ContextoSesion, *, clave: str = "EST-MURO"
) -> uuid.UUID:
    """Un concepto con CPU capturado 100.00/40.00 (sin APU, §10.1)."""
    async with sesion_con_rls(contexto) as sesion:
        conceptos = RepositorioConceptosSQL(sesion)
        concepto = await conceptos.crear(
            {"tipo": "concepto", "clave": clave, "descripcion": "Muro de block"}
        )
        await conceptos.publicar_version_cpu(
            concepto,
            version=1,
            precio_unitario=Decimal("100.00"),
            precio_destajo=Decimal("40.00"),
            variante=None,
            retirar=[],
        )
        await sesion.commit()
    return concepto


async def _crear_presupuesto(escenario: Escenario) -> uuid.UUID:
    presupuesto_id = uuid.uuid4()
    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "insert into presupuesto (id, org_id, prototipo_id, version, "
                "vigente, monto_total) values (:id, :org, :proto, 1, true, 0)"
            ),
            {
                "id": str(presupuesto_id),
                "org": str(escenario.org_id),
                "proto": str(escenario.prototipo_id),
            },
        )
    await admin.dispose()
    return presupuesto_id


def _cuerpo_ensamble(clave: str = "RECAMARA-A", **extra: object) -> dict[str, object]:
    return {
        "clave": clave,
        "nombre": "Recámara tipo A",
        "renglones": [
            {
                "cantidad": "4",
                "origen": "heredada_concepto",
                "clave_concepto": "EST-MURO",
            }
        ],
        **extra,
    }


async def test_extraer_y_leer_el_ensamble_por_http(
    escenario: Escenario, contexto_control: ContextoSesion, cliente_control: httpx.AsyncClient
) -> None:
    concepto = await _sembrar_concepto(contexto_control)

    creado = await cliente_control.post(
        "/api/v1/ensambles",
        json=_cuerpo_ensamble(
            divisor_concepto_clave="EST-MURO",
            divisor_nombre="m² de muro",
            cohorte_prototipo_ids=[str(escenario.prototipo_id)],
        ),
    )
    assert creado.status_code == 201, creado.text
    ensamble_id = creado.json()["id"]
    assert creado.json()["renglones"] == 1
    assert creado.json()["cohorte"] == [str(escenario.prototipo_id)]

    listado = await cliente_control.get("/api/v1/ensambles")
    assert [e["clave"] for e in listado.json()] == ["RECAMARA-A"]

    detalle = (await cliente_control.get(f"/api/v1/ensambles/{ensamble_id}")).json()
    assert detalle["divisor_concepto_id"] == str(concepto)
    assert detalle["tasa"] is None  # nunca se ha publicado una tasa (§5.7)

    renglones = (await cliente_control.get(f"/api/v1/ensambles/{ensamble_id}/renglones")).json()
    assert [(r["concepto_clave"], Decimal(r["cantidad"])) for r in renglones] == [
        ("EST-MURO", Decimal("4"))
    ]

    cohorte = (await cliente_control.get(f"/api/v1/ensambles/{ensamble_id}/cohorte")).json()
    assert cohorte == [
        {"prototipo_id": str(escenario.prototipo_id), "prototipo_clave": "CAS-1"}
    ]


async def test_la_explosion_escala_con_el_factor(
    contexto_control: ContextoSesion, cliente_control: httpx.AsyncClient
) -> None:
    await _sembrar_concepto(contexto_control)
    ensamble_id = (
        await cliente_control.post("/api/v1/ensambles", json=_cuerpo_ensamble())
    ).json()["id"]

    una = (await cliente_control.get(f"/api/v1/ensambles/{ensamble_id}/explosion")).json()
    assert Decimal(una["precio"]["total"]) == Decimal("400.00")  # 4 × 100
    assert Decimal(una["precio"]["destajo"]) == Decimal("160.00")  # 4 × 40

    tres = (
        await cliente_control.get(
            f"/api/v1/ensambles/{ensamble_id}/explosion", params={"factor": "3"}
        )
    ).json()
    assert Decimal(tres["precio"]["total"]) == Decimal("1200.00")
    muro = next(linea for linea in tres["lineas"] if linea["referencia"] == "EST-MURO")
    assert Decimal(muro["cantidad"]) == Decimal("12")


async def test_clave_repetida_es_409(
    contexto_control: ContextoSesion, cliente_control: httpx.AsyncClient
) -> None:
    await _sembrar_concepto(contexto_control)
    assert (
        await cliente_control.post("/api/v1/ensambles", json=_cuerpo_ensamble())
    ).status_code == 201

    repetido = await cliente_control.post("/api/v1/ensambles", json=_cuerpo_ensamble())
    assert repetido.status_code == 409
    assert repetido.headers["content-type"].startswith("application/problem+json")
    assert repetido.json()["type"].endswith("clave-de-ensamble-en-uso")


async def test_concepto_inexistente_es_404(
    cliente_control: httpx.AsyncClient,
) -> None:
    respuesta = await cliente_control.post("/api/v1/ensambles", json=_cuerpo_ensamble())
    assert respuesta.status_code == 404
    assert respuesta.json()["type"].endswith("concepto-no-encontrado")


async def test_renglon_que_apunta_a_dos_cosas_es_422(
    contexto_control: ContextoSesion, cliente_control: httpx.AsyncClient
) -> None:
    await _sembrar_concepto(contexto_control)
    cuerpo = _cuerpo_ensamble()
    cuerpo["renglones"] = [
        {
            "cantidad": "1",
            "origen": "manual",
            "clave_concepto": "EST-MURO",
            "clave_sub_ensamble": "OTRO",
        }
    ]
    respuesta = await cliente_control.post("/api/v1/ensambles", json=cuerpo)
    assert respuesta.status_code == 422


async def test_ensamble_inexistente_es_404_en_todas_las_lecturas(
    cliente_control: httpx.AsyncClient,
) -> None:
    desconocido = uuid.uuid4()
    for ruta in ("", "/renglones", "/cohorte", "/instancias", "/explosion"):
        respuesta = await cliente_control.get(f"/api/v1/ensambles/{desconocido}{ruta}")
        assert respuesta.status_code == 404, ruta
        assert respuesta.json()["type"].endswith("ensamble-no-encontrado"), ruta


async def test_generar_y_regenerar_por_http(
    escenario: Escenario, contexto_control: ContextoSesion, cliente_control: httpx.AsyncClient
) -> None:
    await _sembrar_concepto(contexto_control)
    presupuesto_id = await _crear_presupuesto(escenario)
    ensamble_id = (
        await cliente_control.post("/api/v1/ensambles", json=_cuerpo_ensamble())
    ).json()["id"]
    cuerpo = {
        "presupuesto_id": str(presupuesto_id),
        "prototipo_id": str(escenario.prototipo_id),
        "factor": "2",
        "nombre": "Recámara 1",
    }

    primera = await cliente_control.post(f"/api/v1/ensambles/{ensamble_id}/generar", json=cuerpo)
    assert primera.status_code == 200, primera.text
    assert primera.json()["nuevos"] == ["EST-MURO"]
    assert primera.json()["pendientes"] == []
    instancia = primera.json()["prototipo_nodo_id"]

    # El usuario edita la partida a mano: regenerar no la pisa, la reporta.
    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "update partida_presupuesto set cantidad = 9, importe = 900 "
                "where presupuesto_id = :pid"
            ),
            {"pid": str(presupuesto_id)},
        )
    await admin.dispose()

    segunda = await cliente_control.post(
        f"/api/v1/ensambles/{ensamble_id}/generar",
        json={**cuerpo, "prototipo_nodo_id": instancia},
    )
    assert segunda.status_code == 200, segunda.text
    assert segunda.json()["nuevos"] == []
    assert segunda.json()["actualizados"] == []
    [pendiente] = segunda.json()["pendientes"]
    assert pendiente["estado"] == "desvinculado"
    assert Decimal(pendiente["existente"]["actual"]["cantidad"]) == Decimal("9")
    assert Decimal(pendiente["receta"]["cantidad"]) == Decimal("8")


async def test_las_instancias_generadas_se_listan_para_regenerarlas(
    escenario: Escenario, contexto_control: ContextoSesion, cliente_control: httpx.AsyncClient
) -> None:
    await _sembrar_concepto(contexto_control)
    presupuesto_id = await _crear_presupuesto(escenario)
    ensamble_id = (
        await cliente_control.post("/api/v1/ensambles", json=_cuerpo_ensamble())
    ).json()["id"]
    sin_instancias = await cliente_control.get(f"/api/v1/ensambles/{ensamble_id}/instancias")
    assert sin_instancias.status_code == 200
    assert sin_instancias.json() == []

    generada = (
        await cliente_control.post(
            f"/api/v1/ensambles/{ensamble_id}/generar",
            json={
                "presupuesto_id": str(presupuesto_id),
                "prototipo_id": str(escenario.prototipo_id),
                "factor": "2",
                "nombre": "Recámara 1",
            },
        )
    ).json()

    [instancia] = (
        await cliente_control.get(f"/api/v1/ensambles/{ensamble_id}/instancias")
    ).json()
    assert instancia["id"] == generada["prototipo_nodo_id"]
    assert instancia["prototipo_clave"] == "CAS-1"
    assert instancia["nombre"] == "Recámara 1"
    assert Decimal(instancia["factor"]) == Decimal("2")


async def test_regenerar_con_otro_ensamble_es_409(
    escenario: Escenario, contexto_control: ContextoSesion, cliente_control: httpx.AsyncClient
) -> None:
    await _sembrar_concepto(contexto_control)
    presupuesto_id = await _crear_presupuesto(escenario)
    a = (await cliente_control.post("/api/v1/ensambles", json=_cuerpo_ensamble("ENS-A"))).json()
    b = (await cliente_control.post("/api/v1/ensambles", json=_cuerpo_ensamble("ENS-B"))).json()
    cuerpo = {
        "presupuesto_id": str(presupuesto_id),
        "prototipo_id": str(escenario.prototipo_id),
        "factor": "1",
        "nombre": "Recámara 1",
    }
    instancia = (
        await cliente_control.post(f"/api/v1/ensambles/{a['id']}/generar", json=cuerpo)
    ).json()["prototipo_nodo_id"]

    respuesta = await cliente_control.post(
        f"/api/v1/ensambles/{b['id']}/generar",
        json={**cuerpo, "prototipo_nodo_id": instancia},
    )
    assert respuesta.status_code == 409
    assert respuesta.json()["type"].endswith("ensamble-no-coincide-con-instancia")


async def test_instancia_inexistente_es_404(
    escenario: Escenario, contexto_control: ContextoSesion, cliente_control: httpx.AsyncClient
) -> None:
    await _sembrar_concepto(contexto_control)
    presupuesto_id = await _crear_presupuesto(escenario)
    ensamble_id = (
        await cliente_control.post("/api/v1/ensambles", json=_cuerpo_ensamble())
    ).json()["id"]

    respuesta = await cliente_control.post(
        f"/api/v1/ensambles/{ensamble_id}/generar",
        json={
            "presupuesto_id": str(presupuesto_id),
            "prototipo_id": str(escenario.prototipo_id),
            "factor": "1",
            "nombre": "Recámara 1",
            "prototipo_nodo_id": str(uuid.uuid4()),
        },
    )
    assert respuesta.status_code == 404
    assert respuesta.json()["type"].endswith("instancia-no-encontrada")


async def test_super_intendente_lee_pero_no_escribe(
    contexto_control: ContextoSesion, contexto_super_intendente: ContextoSesion
) -> None:
    await _sembrar_concepto(contexto_control)
    async with _cliente(contexto_control) as control:
        ensamble_id = (
            await control.post("/api/v1/ensambles", json=_cuerpo_ensamble())
        ).json()["id"]

    async with _cliente(contexto_super_intendente) as super_intendente:
        assert (await super_intendente.get("/api/v1/ensambles")).status_code == 200
        assert (
            await super_intendente.get(f"/api/v1/ensambles/{ensamble_id}/explosion")
        ).status_code == 200
        assert (
            await super_intendente.post("/api/v1/ensambles", json=_cuerpo_ensamble("OTRA"))
        ).status_code == 403


async def test_el_residente_no_ve_el_catalogo(
    contexto_residente: ContextoSesion,
) -> None:
    async with _cliente(contexto_residente) as residente:
        assert (await residente.get("/api/v1/ensambles")).status_code == 403
        assert (
            await residente.post("/api/v1/ensambles", json=_cuerpo_ensamble())
        ).status_code == 403
