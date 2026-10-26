"""El estado por parte: enviar, autorizar, validar, programar, asignar y devolver
(migración 0075; D-571 a D-579).

Por HTTP de punta a punta contra Postgres real:

 1. cada parte arranca `cuantificando` y recorre su camino **a su paso**: una puede estar
    programada mientras otra sigue cuantificándose;
 2. «total o por partes»: una parte, varias o todas; **todo o nada**;
 3. no se salta ningún paso (programar pide autorizada) y cada paso es de su rol;
 4. volver es libre hasta asignar; una parte asignada ya no se devuelve;
 5. cada paso queda en una bitácora que solo se agrega;
 6. la parte que nace de marcar una actividad independiente sigue el paso de la que dejó;
 7. otra organización no ve ni toca nada.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.api.dependencias import contexto_actual
from obractrl.application.puertos.notificaciones import Correo
from obractrl.infrastructure.db.sesion import ContextoSesion
from obractrl.infrastructure.notificaciones.expo import ClienteExpoPush
from obractrl.infrastructure.notificaciones.resend import ClienteResend
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
async def supervisor(contexto_supervisor: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_supervisor) as c:
        yield c


@pytest.fixture
async def control(contexto_control: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_control) as c:
        yield c


@pytest.fixture
async def costos(escenario: Escenario) -> AsyncIterator[httpx.AsyncClient]:
    """Un usuario de Costos: ve todas las obras de la organización, sin privilegios de Control."""
    engine = create_async_engine(DATABASE_URL_ADMIN)
    usuario = uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "insert into usuario (id, org_id, nombre, email, rol) "
                "values (:i, :o, 'Costos Test', :e, 'costos')"
            ),
            {"i": str(usuario), "o": str(escenario.org_id), "e": f"cos-{usuario.hex[:8]}@test.mx"},
        )
    await engine.dispose()
    contexto = ContextoSesion(org_id=escenario.org_id, usuario_id=usuario, rol="costos")
    async with _cliente(contexto) as c:
        yield c


@pytest.fixture
async def buzon(monkeypatch: pytest.MonkeyPatch) -> list[Correo]:
    enviados: list[Correo] = []

    async def capturar(self, correo: Correo) -> bool:  # type: ignore[no-untyped-def]
        enviados.append(correo)
        return True

    async def sin_push(self, aviso) -> int:  # type: ignore[no-untyped-def]
        return 0

    monkeypatch.setattr(ClienteResend, "enviar", capturar)
    monkeypatch.setattr(ClienteExpoPush, "enviar", sin_push)
    return enviados


def _prefijos(correo: Correo) -> list[str]:
    return sorted(a.split("@")[0].split("-")[0] for a in correo.para)


@pytest.fixture
async def partes(escenario: Escenario) -> AsyncIterator[dict[str, str]]:
    """Dos partes: la etapa 1 (la actividad del escenario) y la etapa 2 (otra actividad)."""
    engine = create_async_engine(DATABASE_URL_ADMIN)
    nivel, e1, e2, otra = (uuid.uuid4() for _ in range(4))
    org = str(escenario.org_id)
    async with engine.begin() as conn:
        await conn.execute(
            text("insert into nivel (id, org_id, clave, descripcion, orden) values (:i, :o, 'PB', 'PB', 1)"),
            {"i": str(nivel), "o": org},
        )
        for etapa, clave, orden in ((e1, "ECO-1", 1), (e2, "ECO-2", 2)):
            await conn.execute(
                text(
                    "insert into etapa_constructiva (id, org_id, nivel_id, clave, descripcion, orden) "
                    "values (:i, :o, :n, :c, :c, :r)"
                ),
                {"i": str(etapa), "o": org, "n": str(nivel), "c": clave, "r": orden},
            )
        await conn.execute(
            text("update actividad set etapa_id = :e where id = :a"),
            {"e": str(e1), "a": str(escenario.actividad_id)},
        )
        await conn.execute(
            text(
                "insert into actividad (id, org_id, obra_id, etapa_id, cant_base, cant_programada) "
                "values (:i, :o, :ob, :e, 100, 100)"
            ),
            {"i": str(otra), "o": org, "ob": str(escenario.obra_id), "e": str(e2)},
        )
    yield {"a": f"etapa:{e1}", "b": f"etapa:{e2}", "actividad_b": str(otra)}
    await engine.dispose()


def _paso(cliente, escenario, accion, **cuerpo):
    return cliente.post(
        f"/api/v1/obras/{escenario.obra_id}/partes/transicion", json={"accion": accion, **cuerpo}
    )


async def _estados(cliente, escenario) -> dict[str, str]:
    r = await cliente.get(f"/api/v1/obras/{escenario.obra_id}/partes")
    assert r.status_code == 200, r.text
    return {p["clave"]: p["estado"] for p in r.json()["partes"]}


CAMINO = ["enviar_a_presupuesto", "autorizar", "validar", "enviar_a_programa", "programar", "asignar"]
ESTADOS = [
    "enviada_presupuesto",
    "por_validar",
    "autorizada",
    "enviada_programa",
    "programada",
    "asignada",
]


async def test_cada_parte_recorre_su_camino_a_su_paso(
    escenario: Escenario, partes: dict, control: httpx.AsyncClient
) -> None:
    assert set((await _estados(control, escenario)).values()) == {"cuantificando"}

    for accion, esperado in zip(CAMINO, ESTADOS, strict=True):
        r = await _paso(control, escenario, accion, claves=[partes["a"]])
        assert r.status_code == 200, r.text
        assert r.json()[0]["a"] == esperado

    # La otra parte sigue cuantificándose: el orden es por parte, no por obra.
    estados = await _estados(control, escenario)
    assert estados[partes["a"]] == "asignada"
    assert estados[partes["b"]] == "cuantificando"


async def test_total_o_por_partes_y_todo_o_nada(
    escenario: Escenario, partes: dict, control: httpx.AsyncClient
) -> None:
    assert (await _paso(control, escenario, "enviar_a_presupuesto", claves=[partes["a"]])).status_code == 200

    # «El total» toma solo lo que está en el paso que la acción pide: la otra parte.
    r = await _paso(control, escenario, "enviar_a_presupuesto", todas=True)
    assert r.status_code == 200, r.text
    assert [p["clave"] for p in r.json()] == [partes["b"]]

    # Ahora ya no hay nada que enviar.
    vacio = await _paso(control, escenario, "enviar_a_presupuesto", todas=True)
    assert vacio.status_code == 409, vacio.text

    # Todo o nada: con una parte en otro paso, no se escribe ninguna.
    assert (await _paso(control, escenario, "autorizar", claves=[partes["a"]])).status_code == 200
    mixto = await _paso(control, escenario, "autorizar", claves=[partes["a"], partes["b"]])
    assert mixto.status_code == 409, mixto.text
    estados = await _estados(control, escenario)
    assert (estados[partes["a"]], estados[partes["b"]]) == ("por_validar", "enviada_presupuesto")


async def test_no_se_salta_ningun_paso(
    escenario: Escenario, partes: dict, control: httpx.AsyncClient
) -> None:
    for accion in ("autorizar", "validar", "enviar_a_programa", "programar", "asignar"):
        r = await _paso(control, escenario, accion, claves=[partes["a"]])
        assert r.status_code == 409, (accion, r.text)
        assert r.json()["type"].endswith("regla-de-parte")
    assert (await _estados(control, escenario))[partes["a"]] == "cuantificando"


async def test_cada_paso_es_de_su_rol(
    escenario: Escenario,
    partes: dict,
    residente: httpx.AsyncClient,
    supervisor: httpx.AsyncClient,
    control: httpx.AsyncClient,
) -> None:
    # El residente ni entra a la ruta.
    assert (await _paso(residente, escenario, "enviar_a_presupuesto", claves=[partes["a"]])).status_code == 403
    # El supervisor no manda ni autoriza...
    assert (await _paso(supervisor, escenario, "enviar_a_presupuesto", claves=[partes["a"]])).status_code == 403
    for accion in CAMINO[:5]:
        assert (await _paso(control, escenario, accion, claves=[partes["a"]])).status_code == 200
    # ...pero sí programa lo que ya se mandó a programar.
    assert (await _paso(control, escenario, "devolver", claves=[partes["a"]], a="enviada_programa")).status_code == 200
    ok = await _paso(supervisor, escenario, "programar", claves=[partes["a"]])
    assert ok.status_code == 200, ok.text
    # Y no asigna.
    assert (await _paso(supervisor, escenario, "asignar", claves=[partes["a"]])).status_code == 403


async def test_volver_es_libre_hasta_asignar(
    escenario: Escenario, partes: dict, control: httpx.AsyncClient
) -> None:
    for accion in CAMINO[:3]:
        assert (await _paso(control, escenario, accion, claves=[partes["a"]])).status_code == 200
    # Autorizada: se vuelve a cuantificar, replantear lo hecho.
    r = await _paso(control, escenario, "devolver", claves=[partes["a"]], a="cuantificando", nota="Cambió el plano")
    assert r.status_code == 200, r.text
    assert (await _estados(control, escenario))[partes["a"]] == "cuantificando"
    # Solo hacia atrás, y diciendo a dónde.
    assert (await _paso(control, escenario, "devolver", claves=[partes["a"]], a="autorizada")).status_code == 409
    assert (await _paso(control, escenario, "devolver", claves=[partes["a"]])).status_code == 409

    # Asignada: ya no se devuelve; cambiar es control de cambio.
    for accion in CAMINO:
        assert (await _paso(control, escenario, accion, claves=[partes["a"]])).status_code == 200
    atras = await _paso(control, escenario, "devolver", claves=[partes["a"]], a="cuantificando")
    assert atras.status_code == 409, atras.text
    assert "control de cambio" in atras.json()["detail"]


async def test_la_bitacora_dice_quien_y_cuando_y_la_ven_todos(
    escenario: Escenario, partes: dict, control: httpx.AsyncClient, residente: httpx.AsyncClient
) -> None:
    await _paso(control, escenario, "enviar_a_presupuesto", claves=[partes["a"]], nota="Listo el primer nivel")
    await _paso(control, escenario, "devolver", claves=[partes["a"]], a="cuantificando", nota="Replantear")

    for cliente in (control, residente):
        r = await cliente.get(f"/api/v1/obras/{escenario.obra_id}/partes/bitacora")
        assert r.status_code == 200, r.text
        filas = r.json()
        assert [(f["accion"], f["de"], f["a"]) for f in filas] == [
            ("devolver", "enviada_presupuesto", "cuantificando"),
            ("enviar_a_presupuesto", "cuantificando", "enviada_presupuesto"),
        ]
        assert filas[1]["nota"] == "Listo el primer nivel"
        assert filas[1]["rol"] == "control_obra"
        assert filas[1]["usuario_id"] == str(escenario.control_id)
        assert filas[1]["usuario_nombre"] == "Control Test"


async def test_la_parte_que_nace_de_marcar_una_actividad_sigue_el_paso_de_la_que_dejo(
    escenario: Escenario, partes: dict, control: httpx.AsyncClient
) -> None:
    for accion in CAMINO[:3]:
        assert (await _paso(control, escenario, accion, claves=[partes["b"]])).status_code == 200

    r = await control.put(
        f"/api/v1/actividades/{partes['actividad_b']}/parte-independiente", json={"independiente": True}
    )
    assert r.status_code == 204, r.text
    estados = await _estados(control, escenario)
    assert estados[f"concepto:{partes['actividad_b']}"] == "autorizada"  # no vuelve a cuantificando


async def test_una_parte_que_no_existe_no_se_toca(
    escenario: Escenario, partes: dict, control: httpx.AsyncClient
) -> None:
    r = await _paso(control, escenario, "enviar_a_presupuesto", claves=[f"etapa:{uuid.uuid4()}"])
    assert r.status_code == 404, r.text
    # Sin partes y sin «todas» tampoco hay qué hacer.
    assert (await _paso(control, escenario, "enviar_a_presupuesto")).status_code == 409


async def test_otra_organizacion_no_ve_ni_toca_nada(
    escenario: Escenario, partes: dict, contexto_ajeno: ContextoSesion, control: httpx.AsyncClient
) -> None:
    ajeno = ContextoSesion(org_id=contexto_ajeno.org_id, usuario_id=contexto_ajeno.usuario_id, rol="control_obra")
    async with _cliente(ajeno) as c:
        assert (await c.get(f"/api/v1/obras/{escenario.obra_id}/partes/bitacora")).status_code == 404
        r = await c.post(
            f"/api/v1/obras/{escenario.obra_id}/partes/transicion",
            json={"accion": "enviar_a_presupuesto", "todas": True},
        )
        assert r.status_code == 404, r.text
    assert set((await _estados(control, escenario)).values()) == {"cuantificando"}


async def test_costos_manda_y_autoriza_y_control_valida_al_final(
    escenario: Escenario, partes: dict, costos: httpx.AsyncClient, control: httpx.AsyncClient
) -> None:
    # Costos ve toda la organización: la obra es visible aunque no sea «suya».
    assert set((await _estados(costos, escenario)).values()) == {"cuantificando"}

    assert (await _paso(costos, escenario, "enviar_a_presupuesto", claves=[partes["a"]])).status_code == 200
    assert (await _paso(costos, escenario, "autorizar", claves=[partes["a"]])).status_code == 200
    # Pero no se valida a sí mismo, ni programa, ni asigna, ni devuelve: eso es de Control.
    for accion, cuerpo in (
        ("validar", {}),
        ("enviar_a_programa", {}),
        ("programar", {}),
        ("asignar", {}),
        ("devolver", {"a": "cuantificando"}),
    ):
        r = await _paso(costos, escenario, accion, claves=[partes["a"]], **cuerpo)
        assert r.status_code == 403, (accion, r.text)
    assert (await _estados(control, escenario))[partes["a"]] == "por_validar"

    assert (await _paso(control, escenario, "validar", claves=[partes["a"]])).status_code == 200
    bitacora = (await control.get(f"/api/v1/obras/{escenario.obra_id}/partes/bitacora")).json()
    assert [(f["accion"], f["rol"]) for f in bitacora] == [
        ("validar", "control_obra"),
        ("autorizar", "costos"),
        ("enviar_a_presupuesto", "costos"),
    ]


async def test_se_avisa_a_quien_da_el_siguiente_paso_sin_quien_acaba_de_darlo(
    escenario: Escenario,
    partes: dict,
    costos: httpx.AsyncClient,
    control: httpx.AsyncClient,
    buzon: list[Correo],
) -> None:
    # Costos manda a presupuesto: le toca autorizar a Costos y a Control (no a quien mandó).
    await _paso(costos, escenario, "enviar_a_presupuesto", claves=[partes["a"]])
    [correo] = buzon
    assert correo.etiquetas == {"tipo": "partes_cambiaron_de_estado"}
    assert _prefijos(correo) == ["ctrl"]
    assert "en presupuesto" in correo.texto

    # Costos autoriza: le toca validar a Control.
    await _paso(costos, escenario, "autorizar", claves=[partes["a"]])
    assert _prefijos(buzon[-1]) == ["ctrl"]
    assert "por validar" in buzon[-1].texto

    # Control manda a presupuesto otra parte: le toca autorizar a Costos (y a otro Control, si hubiera).
    antes = len(buzon)
    await _paso(control, escenario, "enviar_a_presupuesto", claves=[partes["b"]])
    assert len(buzon) == antes + 1
    assert _prefijos(buzon[-1]) == ["cos"]

    # Una parte asignada ya no tiene siguiente paso: no se avisa a nadie.
    for accion in ("autorizar", "validar", "enviar_a_programa", "programar", "asignar"):
        await _paso(control, escenario, accion, claves=[partes["b"]])
    assert (await _estados(control, escenario))[partes["b"]] == "asignada"
    despues = len(buzon)
    assert (await control.get(f"/api/v1/obras/{escenario.obra_id}/partes")).status_code == 200
    assert despues == len(buzon)


async def test_devolver_una_parte_con_programa_lo_deja_por_revisar_y_avisa_sin_borrar_nada(
    escenario: Escenario,
    partes: dict,
    control: httpx.AsyncClient,
    buzon: list[Correo],
) -> None:
    for accion in ("enviar_a_presupuesto", "autorizar", "validar", "enviar_a_programa", "programar"):
        await _paso(control, escenario, accion, claves=[partes["a"]])
    por_revisar = lambda cuerpo: {  # noqa: E731
        p["clave"]: p["programa_por_revisar"] for p in cuerpo["partes"]
    }
    ver = await control.get(f"/api/v1/obras/{escenario.obra_id}/partes")
    assert por_revisar(ver.json())[partes["a"]] is False

    buzon.clear()
    r = await _paso(control, escenario, "devolver", claves=[partes["a"]], a="autorizada")
    assert r.status_code == 200, r.text
    ver = await control.get(f"/api/v1/obras/{escenario.obra_id}/partes")
    assert por_revisar(ver.json())[partes["a"]] is True
    # Se avisó a quienes llevan el programa: el residente y el supervisor de la obra (no a quien
    # devolvió), con una etiqueta propia.
    [revisar] = [c for c in buzon if c.etiquetas == {"tipo": "programa_por_revisar"}]
    assert _prefijos(revisar) == ["res", "sup"]
    # Nada se borró: la parte conserva su actividad y solo cambió de paso.
    assert [p["n_actividades"] for p in ver.json()["partes"] if p["clave"] == partes["a"]] == [1]

    # Al volver a programarla la marca se quita.
    for accion in ("enviar_a_programa", "programar"):
        assert (await _paso(control, escenario, accion, claves=[partes["a"]])).status_code == 200
    ver = await control.get(f"/api/v1/obras/{escenario.obra_id}/partes")
    assert por_revisar(ver.json())[partes["a"]] is False


async def test_devolver_una_parte_sin_programa_no_la_marca(
    escenario: Escenario, partes: dict, control: httpx.AsyncClient, buzon: list[Correo]
) -> None:
    for accion in ("enviar_a_presupuesto", "autorizar", "validar"):
        await _paso(control, escenario, accion, claves=[partes["a"]])
    buzon.clear()
    assert (await _paso(control, escenario, "devolver", claves=[partes["a"]], a="cuantificando")).status_code == 200
    ver = await control.get(f"/api/v1/obras/{escenario.obra_id}/partes")
    assert not any(p["programa_por_revisar"] for p in ver.json()["partes"])
    assert not [c for c in buzon if c.etiquetas == {"tipo": "programa_por_revisar"}]


async def _fechar(escenario: Escenario, partes: dict, dias_a: int, dias_b: int) -> None:
    """El programa base necesita la etapa 1 en `dias_a` días y la etapa 2 en `dias_b`."""
    engine = create_async_engine(DATABASE_URL_ADMIN)
    async with engine.begin() as conn:
        for actividad, dias in ((str(escenario.actividad_id), dias_a), (partes["actividad_b"], dias_b)):
            await conn.execute(
                text("update actividad set fecha_inicio = current_date + cast(:d as integer) where id = :a"),
                {"d": dias, "a": actividad},
            )
    await engine.dispose()


async def test_el_presupuesto_debe_ir_por_delante_del_programa_y_avisa_sin_bloquear(
    escenario: Escenario, partes: dict, control: httpx.AsyncClient
) -> None:
    # Etapa 1 la necesita el programa en 10 días (aviso: dentro de 2 semanas); la 2, en 5
    # (importante: dentro de 1 semana).
    await _fechar(escenario, partes, 10, 5)
    r = await control.get(f"/api/v1/obras/{escenario.obra_id}/partes/alertas")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert (cuerpo["aviso_dias"], cuerpo["importante_dias"]) == (14, 7)
    assert {a["clave"]: a["severidad"] for a in cuerpo["alertas"]} == {
        partes["a"]: "aviso",
        partes["b"]: "importante",
    }
    assert cuerpo["alertas"][0]["clave"] == partes["b"]  # lo más urgente, primero

    # Autorizada deja de alertar; avisa pero no bloquea: sin autorizar se sigue pudiendo operar.
    for accion in ("enviar_a_presupuesto", "autorizar", "validar"):
        assert (await _paso(control, escenario, accion, claves=[partes["b"]])).status_code == 200
    r = await control.get(f"/api/v1/obras/{escenario.obra_id}/partes/alertas")
    assert [a["clave"] for a in r.json()["alertas"]] == [partes["a"]]

    # Lejos en el tiempo no alerta.
    await _fechar(escenario, partes, 60, 60)
    r = await control.get(f"/api/v1/obras/{escenario.obra_id}/partes/alertas")
    assert r.json()["alertas"] == []


async def test_los_umbrales_son_globales_y_los_edita_control(
    escenario: Escenario,
    partes: dict,
    control: httpx.AsyncClient,
    residente: httpx.AsyncClient,
    costos: httpx.AsyncClient,
) -> None:
    await _fechar(escenario, partes, 20, 60)
    assert (await control.get("/api/v1/configuracion/desfase-de-partes")).json() == {
        "aviso_dias": 14,
        "importante_dias": 7,
    }
    ya = await control.get(f"/api/v1/obras/{escenario.obra_id}/partes/alertas")
    assert ya.json()["alertas"] == []

    # Solo Control (o la superintendencia) los edita; Costos y el residente los leen.
    for otro in (residente, costos):
        r = await otro.put("/api/v1/configuracion/desfase-de-partes", json={"aviso_dias": 30, "importante_dias": 7})
        assert r.status_code == 403
        assert (await otro.get("/api/v1/configuracion/desfase-de-partes")).status_code == 200

    # El aviso va antes que la alerta importante.
    malo = await control.put("/api/v1/configuracion/desfase-de-partes", json={"aviso_dias": 3, "importante_dias": 7})
    assert malo.status_code == 422

    r = await control.put("/api/v1/configuracion/desfase-de-partes", json={"aviso_dias": 30, "importante_dias": 7})
    assert r.status_code == 200, r.text
    assert r.json() == {"aviso_dias": 30, "importante_dias": 7}
    despues = await control.get(f"/api/v1/obras/{escenario.obra_id}/partes/alertas")
    assert [a["clave"] for a in despues.json()["alertas"]] == [partes["a"]]


async def test_el_arranque_dice_si_todo_esta_validado_sin_impedir_nada(
    escenario: Escenario, partes: dict, control: httpx.AsyncClient
) -> None:
    r = await control.get(f"/api/v1/obras/{escenario.obra_id}/arranque")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["todo_validado"] is False
    assert cuerpo["candado_asignar"] is False
    assert {p["clave"] for p in cuerpo["sin_autorizar"]} == {partes["a"], partes["b"]}

    for clave in (partes["a"], partes["b"]):
        for accion in ("enviar_a_presupuesto", "autorizar", "validar"):
            await _paso(control, escenario, accion, claves=[clave])
    cuerpo = (await control.get(f"/api/v1/obras/{escenario.obra_id}/arranque")).json()
    assert cuerpo["todo_validado"] is True
    assert cuerpo["sin_autorizar"] == []


async def test_el_candado_de_asignar_exige_anotacion_al_validar_y_para_asignar(
    escenario: Escenario,
    partes: dict,
    control: httpx.AsyncClient,
    supervisor: httpx.AsyncClient,
) -> None:
    clave = partes["a"]
    # Lo pone solo Control, por obra.
    assert (
        await supervisor.put(f"/api/v1/obras/{escenario.obra_id}/candado-asignar", json={"activo": True})
    ).status_code == 403
    r = await control.put(f"/api/v1/obras/{escenario.obra_id}/candado-asignar", json={"activo": True})
    assert r.status_code == 204, r.text
    assert (await control.get(f"/api/v1/obras/{escenario.obra_id}/arranque")).json()["candado_asignar"] is True

    for accion in ("enviar_a_presupuesto", "autorizar"):
        await _paso(control, escenario, accion, claves=[clave])
    # Validar sin anotación no pasa; con ella, sí.
    sin = await _paso(control, escenario, "validar", claves=[clave])
    assert sin.status_code == 409 and "anotación" in sin.text
    assert (await _paso(control, escenario, "validar", claves=[clave], nota="Revisado contra el catálogo")).status_code == 200
    for accion in ("enviar_a_programa", "programar"):
        assert (await _paso(control, escenario, accion, claves=[clave])).status_code == 200
    assert (await _paso(control, escenario, "asignar", claves=[clave])).status_code == 200

    # Sin candado, la otra parte se valida y asigna sin anotación.
    await control.put(f"/api/v1/obras/{escenario.obra_id}/candado-asignar", json={"activo": False})
    for accion in ("enviar_a_presupuesto", "autorizar", "validar", "enviar_a_programa", "programar", "asignar"):
        assert (await _paso(control, escenario, accion, claves=[partes["b"]])).status_code == 200


async def test_con_candado_no_se_asigna_lo_validado_sin_anotacion(
    escenario: Escenario, partes: dict, control: httpx.AsyncClient
) -> None:
    clave = partes["a"]
    # Se valida cuando aún no hay candado: sin anotación.
    for accion in ("enviar_a_presupuesto", "autorizar", "validar", "enviar_a_programa", "programar"):
        assert (await _paso(control, escenario, accion, claves=[clave])).status_code == 200
    await control.put(f"/api/v1/obras/{escenario.obra_id}/candado-asignar", json={"activo": True})
    r = await _paso(control, escenario, "asignar", claves=[clave])
    assert r.status_code == 409 and "anotación" in r.text
    assert (await _estados(control, escenario))[clave] == "programada"


async def _cargar_ingenieria(escenario: Escenario, etapa: str, importe: int, revertida: bool = False) -> None:
    """Una carga de ingeniería del lote ya aplicada con una fila de insumo para `etapa`."""
    engine = create_async_engine(DATABASE_URL_ADMIN)
    carga = uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "insert into carga_datos (id, org_id, tipo, estatus, revertida_en) "
                "values (:i, :o, 'ingenieria_lote', 'aplicado', "
                "case when :r then now() end)"
            ),
            {"i": str(carga), "o": str(escenario.org_id), "r": revertida},
        )
        await conn.execute(
            text(
                "insert into ingenieria_lote_insumo "
                "(org_id, obra_id, carga_id, clave, descripcion, cantidad, importe, etapa, fila) "
                "values (:o, :ob, :c, 'INS-1', 'Insumo', 1, :imp, :e, 0)"
            ),
            {"o": str(escenario.org_id), "ob": str(escenario.obra_id), "c": str(carga), "imp": importe, "e": etapa},
        )
    await engine.dispose()


async def test_la_ingenieria_llega_por_partes_y_una_carga_incompleta_solo_avisa(
    escenario: Escenario, partes: dict, control: httpx.AsyncClient
) -> None:
    engine = create_async_engine(DATABASE_URL_ADMIN)
    async with engine.begin() as conn:  # la etapa 2 vale algo: 100 × 10
        await conn.execute(
            text("update actividad set precio_unitario = 10 where id = :a"), {"a": partes["actividad_b"]}
        )
    await engine.dispose()
    ver = lambda: control.get(f"/api/v1/obras/{escenario.obra_id}/partes/carga")  # noqa: E731
    r = await ver()
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["incompletas"] == 2
    assert {p["estado"] for p in cuerpo["partes"]} == {"incompleto"}
    por_clave = {p["clave"]: p for p in cuerpo["partes"]}
    assert por_clave[partes["a"]]["etapa"] == "ECO-1"
    assert por_clave[partes["a"]]["porcentaje_cargado"] in ("0", "0.00", "0.0")

    pres = float(por_clave[partes["b"]]["importe_presupuestado"])
    assert pres > 0
    # Llega la mitad de la etapa 2: sigue incompleta y dice cuánto falta.
    await _cargar_ingenieria(escenario, "ECO-2", int(pres / 2))
    b = {p["clave"]: p for p in (await ver()).json()["partes"]}[partes["b"]]
    assert b["estado"] == "incompleto"
    assert 49 <= float(b["porcentaje_cargado"]) <= 51
    assert float(b["importe_pendiente"]) > 0
    # Llega lo demás: completa. Una carga revertida no cuenta.
    await _cargar_ingenieria(escenario, "ECO-2", int(pres), revertida=True)
    await _cargar_ingenieria(escenario, "ECO-2", int(pres))
    cuerpo = (await ver()).json()
    b = {p["clave"]: p for p in cuerpo["partes"]}[partes["b"]]
    assert (b["estado"], float(b["porcentaje_cargado"])) == ("completo", 100.0)
    assert cuerpo["incompletas"] == 1

    # Una carga incompleta nunca bloquea: la parte incompleta recorre su camino.
    for accion in ("enviar_a_presupuesto", "autorizar", "validar", "enviar_a_programa"):
        assert (await _paso(control, escenario, accion, claves=[partes["a"]])).status_code == 200


async def test_la_carga_de_otra_organizacion_no_se_ve(
    escenario: Escenario, partes: dict, contexto_ajeno: ContextoSesion
) -> None:
    ajeno = ContextoSesion(org_id=contexto_ajeno.org_id, usuario_id=contexto_ajeno.usuario_id, rol="control_obra")
    async with _cliente(ajeno) as c:
        r = await c.get(f"/api/v1/obras/{escenario.obra_id}/partes/carga")
        assert r.status_code == 404
