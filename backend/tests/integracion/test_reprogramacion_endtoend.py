"""Reprogramar lo asignado: las fechas no se mueven solas (migración 0072; D-533, P-4).

El cerebro: «las fechas asignadas no se mueven solas: reprogramar **propone** la fecha
nueva y alguien la acepta», con una cadena

    propone              revisa        valida           realiza
    Residente            Supervisor    Control de obra  Control de obra
    Supervisor           (se salta)    Control de obra  Control de obra

y «al aplicarse se notifica el cambio a los demás». Por HTTP de punta a punta contra
Postgres real:

 1. una actividad asignada —su frente tiene contratista en la planeación de la obra, o
    ella lo trae directo— rechaza el `PATCH` directo de fechas (409); lo que no son
    fechas y lo que no está asignado se editan como siempre;
 2. la cadena completa mueve la fecha, deja la reprogramación aplicada con quién hizo
    cada paso y su renglón en la bitácora del programa con el id de la reprogramación;
 3. si propone el supervisor la revisión se salta; cada paso es de su rol y en su orden;
 4. realizar es atómico: si no se puede dejar la reprogramación aplicada, la fecha no se
    mueve;
 5. una sola reprogramación viva por actividad; rechazar la libera y exige motivo;
 6. al aplicarse se avisa por rol, según quien propuso (residente → supervisor y control;
    supervisor → residente y control), y control puede dejar observaciones al residente y
    al supervisor, que no mueven la cadena;
 7. otra organización no ve ni toca nada.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.api.dependencias import contexto_actual
from obractrl.adapters.repos.reprogramaciones_sql import (
    RepositorioReprogramacionesSQL,
    ReprogramacionNoModificada,
)
from obractrl.application.puertos.notificaciones import Correo
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
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
async def super_intendente(
    contexto_super_intendente: ContextoSesion,
) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_super_intendente) as c:
        yield c


@pytest.fixture
async def ajeno(contexto_ajeno: ContextoSesion) -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(contexto_ajeno) as c:
        yield c


@dataclass(frozen=True)
class Trato:
    """El frente de la actividad y el contratista con quien se tiene el trato."""

    frente_id: uuid.UUID
    contratista_id: uuid.UUID


async def _tratar(
    cliente: httpx.AsyncClient,
    escenario: Escenario,
    trato: Trato,
    contratista_id: uuid.UUID | None,
) -> None:
    """Asigna (o quita) el contratista del frente en la obra: el trato de la planeación."""
    r = await cliente.put(
        f"/api/v1/obras/{escenario.obra_id}/planeacion/frentes/{trato.frente_id}",
        json={"contratista_id": str(contratista_id) if contratista_id else None},
    )
    assert r.status_code == 204, r.text


@pytest.fixture
async def asignada(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> AsyncIterator[Trato]:
    """La actividad del escenario con fechas y con el trato de su frente: lo asignado.

    El trato se asigna por el camino real —la planeación del residente—, no tocando la
    columna a mano: es lo que de verdad vuelve «asignada» a una actividad.
    """
    engine = create_async_engine(DATABASE_URL_ADMIN)
    frente, contratista = uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "insert into frente (id, org_id, clave, nombre) "
                "values (:id, :org, 'FR-R', 'Frente de Prueba')"
            ),
            {"id": str(frente), "org": str(escenario.org_id)},
        )
        await conn.execute(
            text(
                "insert into contratista (id, org_id, clave, razon_social) "
                "values (:id, :org, 'CONT-R', 'Contratista de Prueba')"
            ),
            {"id": str(contratista), "org": str(escenario.org_id)},
        )
        await conn.execute(
            text(
                "update actividad set frente_id = :f, fecha_inicio = '2026-03-02', "
                "fecha_termino = '2026-03-13' where id = :id"
            ),
            {"f": str(frente), "id": str(escenario.actividad_id)},
        )
    trato = Trato(frente_id=frente, contratista_id=contratista)
    async with _cliente(contexto_residente) as residente:
        await _tratar(residente, escenario, trato, contratista)
    yield trato
    await engine.dispose()


def _proponer(cliente: httpx.AsyncClient, escenario: Escenario, cuerpo: dict | None = None):
    return cliente.post(
        f"/api/v1/actividades/{escenario.actividad_id}/reprogramaciones",
        json=cuerpo
        or {
            "fecha_inicio": "2026-03-09",
            "fecha_termino": "2026-03-20",
            "motivo": "El contratista no tenía cuadrilla",
        },
    )


def _paso(cliente: httpx.AsyncClient, reprogramacion_id: str, paso: str, cuerpo: dict | None = None):
    return cliente.post(f"/api/v1/reprogramaciones/{reprogramacion_id}/{paso}", json=cuerpo or {})


async def _fechas(contexto: ContextoSesion, escenario: Escenario) -> tuple[str, str]:
    async with sesion_con_rls(contexto) as sesion:
        fila = (
            await sesion.execute(
                text("select fecha_inicio, fecha_termino from actividad where id = :id"),
                {"id": str(escenario.actividad_id)},
            )
        ).mappings().one()
    return str(fila["fecha_inicio"]), str(fila["fecha_termino"])


async def _lista(cliente: httpx.AsyncClient, escenario: Escenario) -> list[dict]:
    respuesta = await cliente.get(f"/api/v1/obras/{escenario.obra_id}/reprogramaciones")
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


async def _cadena_hasta_validada(
    residente: httpx.AsyncClient,
    supervisor: httpx.AsyncClient,
    control: httpx.AsyncClient,
    escenario: Escenario,
) -> str:
    creada = await _proponer(residente, escenario)
    assert creada.status_code == 201, creada.text
    reprogramacion_id = creada.json()["id"]
    assert (await _paso(supervisor, reprogramacion_id, "revisar")).status_code == 200
    assert (await _paso(control, reprogramacion_id, "validar")).status_code == 200
    return reprogramacion_id


# --- 1. P-4: lo asignado no se mueve solo -----------------------------------


async def test_las_fechas_de_lo_asignado_no_se_editan_directo(
    escenario: Escenario,
    asignada: Trato,
    residente: httpx.AsyncClient,
    control: httpx.AsyncClient,
    contexto_residente: ContextoSesion,
) -> None:
    for cliente in (residente, control):
        r = await cliente.patch(
            f"/api/v1/actividades/{escenario.actividad_id}/programacion",
            json={"fecha_inicio": "2026-04-01"},
        )
        assert r.status_code == 409, r.text
        assert r.json()["type"].endswith("fechas-de-lo-asignado")
    assert await _fechas(contexto_residente, escenario) == ("2026-03-02", "2026-03-13")

    # Lo que no son fechas sí se edita: el bloqueo es de las fechas, no de la actividad.
    estructura = await control.patch(
        f"/api/v1/actividades/{escenario.actividad_id}/programacion",
        json={"duracion_dias": "9"},
    )
    assert estructura.status_code == 200, estructura.text


async def test_lo_que_no_esta_asignado_se_edita_libre_y_no_se_reprograma(
    escenario: Escenario, residente: httpx.AsyncClient
) -> None:
    libre = await residente.patch(
        f"/api/v1/actividades/{escenario.actividad_id}/programacion",
        json={"fecha_inicio": "2026-04-01", "fecha_termino": "2026-04-10"},
    )
    assert libre.status_code == 200, libre.text

    # Sin contratista no hay nada que proponer: sus fechas se editan directo.
    r = await _proponer(residente, escenario)
    assert r.status_code == 409, r.text
    assert r.json()["type"].endswith("regla-de-reprogramacion")
    assert "asignad" in r.json()["detail"]


async def test_lo_asignado_es_el_trato_del_frente_en_la_planeacion(
    escenario: Escenario,
    asignada: Trato,
    residente: httpx.AsyncClient,
    control: httpx.AsyncClient,
) -> None:
    fechas = {"fecha_inicio": "2026-04-01", "fecha_termino": "2026-04-10"}
    url = f"/api/v1/actividades/{escenario.actividad_id}/programacion"
    assert (await residente.patch(url, json=fechas)).status_code == 409

    # Se deshace el trato: el frente queda sin contratista y las fechas vuelven a ser libres.
    await _tratar(residente, escenario, asignada, None)
    assert (await _proponer(residente, escenario)).status_code == 409  # nada que reprogramar
    libre = await control.patch(url, json=fechas)
    assert libre.status_code == 200, libre.text

    # Se vuelve a tratar: otra vez asignada.
    await _tratar(residente, escenario, asignada, asignada.contratista_id)
    assert (
        await residente.patch(url, json={"fecha_inicio": "2026-05-01"})
    ).status_code == 409


async def test_el_contratista_que_trae_la_actividad_tambien_la_contrata(
    escenario: Escenario, residente: httpx.AsyncClient
) -> None:
    engine = create_async_engine(DATABASE_URL_ADMIN)
    contratista = uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "insert into contratista (id, org_id, clave, razon_social) "
                "values (:id, :org, 'CONT-D', 'Directo')"
            ),
            {"id": str(contratista), "org": str(escenario.org_id)},
        )
        await conn.execute(
            text("update actividad set contratista_id = :c where id = :id"),
            {"c": str(contratista), "id": str(escenario.actividad_id)},
        )
    await engine.dispose()

    r = await residente.patch(
        f"/api/v1/actividades/{escenario.actividad_id}/programacion",
        json={"fecha_inicio": "2026-04-01"},
    )
    assert r.status_code == 409, r.text
    assert r.json()["type"].endswith("fechas-de-lo-asignado")


# --- 2. La cadena completa ------------------------------------------------------


async def test_la_cadena_completa_mueve_la_fecha_y_deja_el_rastro(
    escenario: Escenario,
    asignada: Trato,
    residente: httpx.AsyncClient,
    supervisor: httpx.AsyncClient,
    control: httpx.AsyncClient,
    contexto_residente: ContextoSesion,
) -> None:
    creada = await _proponer(residente, escenario)
    assert creada.status_code == 201, creada.text
    assert creada.json()["estatus"] == "propuesta"
    reprogramacion_id = creada.json()["id"]
    # Proponer no mueve nada: «las fechas asignadas no se mueven solas».
    assert await _fechas(contexto_residente, escenario) == ("2026-03-02", "2026-03-13")

    revisada = await _paso(supervisor, reprogramacion_id, "revisar")
    assert revisada.status_code == 200, revisada.text
    assert revisada.json()["estatus"] == "revisada"
    assert revisada.json()["revisada_por"] == str(escenario.supervisor_id)

    validada = await _paso(control, reprogramacion_id, "validar")
    assert validada.status_code == 200, validada.text
    assert validada.json()["estatus"] == "validada"
    assert await _fechas(contexto_residente, escenario) == ("2026-03-02", "2026-03-13")

    aplicada = await _paso(control, reprogramacion_id, "aplicar")
    assert aplicada.status_code == 200, aplicada.text
    assert aplicada.json()["estatus"] == "aplicada"
    assert await _fechas(contexto_residente, escenario) == ("2026-03-09", "2026-03-20")

    [fila] = await _lista(control, escenario)
    assert fila["id"] == reprogramacion_id
    assert fila["estatus"] == "aplicada"
    # Lo que había antes: sin el antes, la lista no diría qué se movió.
    assert fila["fecha_inicio_anterior"] == "2026-03-02"
    assert fila["fecha_termino_anterior"] == "2026-03-13"
    assert fila["fecha_inicio"] == "2026-03-09"
    assert fila["contratista"] == "Contratista de Prueba"
    assert fila["motivo"] == "El contratista no tenía cuadrilla"
    # Quién hizo cada paso, y cuándo.
    assert fila["propuesta_por"] == str(escenario.residente_id)
    assert fila["revisada_por"] == str(escenario.supervisor_id)
    assert fila["validada_por"] == str(escenario.control_id)
    assert fila["aplicada_por"] == str(escenario.control_id)
    assert fila["propuesta_por_nombre"] == "Residente Test"
    assert fila["aplicada_en"] is not None

    # La bitácora del programa dice que la fecha se movió por esta reprogramación.
    bitacora = (
        await control.get(f"/api/v1/obras/{escenario.obra_id}/programa/ediciones")
    ).json()
    [edicion] = bitacora
    assert edicion["rol"] == "control_obra"
    assert edicion["tipo"] == "fechas"
    assert edicion["despues"]["reprogramacion_id"] == reprogramacion_id
    assert edicion["antes"] == {"fecha_inicio": "2026-03-02", "fecha_termino": "2026-03-13"}


async def test_se_puede_mover_una_sola_fecha(
    escenario: Escenario,
    asignada: Trato,
    supervisor: httpx.AsyncClient,
    control: httpx.AsyncClient,
    contexto_residente: ContextoSesion,
) -> None:
    creada = await _proponer(
        supervisor, escenario, {"fecha_termino": "2026-03-27", "motivo": "Se alarga el colado"}
    )
    assert creada.status_code == 201, creada.text
    reprogramacion_id = creada.json()["id"]
    assert (await _paso(control, reprogramacion_id, "validar")).status_code == 200
    assert (await _paso(control, reprogramacion_id, "aplicar")).status_code == 200
    assert await _fechas(contexto_residente, escenario) == ("2026-03-02", "2026-03-27")


# --- 3. El salto y los roles ---------------------------------------------------


async def test_si_propone_el_supervisor_la_revision_se_salta(
    escenario: Escenario,
    asignada: Trato,
    supervisor: httpx.AsyncClient,
    control: httpx.AsyncClient,
    contexto_residente: ContextoSesion,
) -> None:
    creada = await _proponer(supervisor, escenario)
    assert creada.status_code == 201, creada.text
    assert creada.json()["estatus"] == "revisada"
    assert creada.json()["revisada_por"] is None  # nadie revisó: el rastro no finge

    reprogramacion_id = creada.json()["id"]
    assert (await _paso(control, reprogramacion_id, "validar")).status_code == 200
    assert (await _paso(control, reprogramacion_id, "aplicar")).status_code == 200
    assert await _fechas(contexto_residente, escenario) == ("2026-03-09", "2026-03-20")


async def test_cada_paso_es_de_su_rol(
    escenario: Escenario,
    asignada: Trato,
    residente: httpx.AsyncClient,
    supervisor: httpx.AsyncClient,
    control: httpx.AsyncClient,
    super_intendente: httpx.AsyncClient,
) -> None:
    # Proponen el residente y el supervisor; control y super intendente no.
    for cliente in (control, super_intendente):
        assert (await _proponer(cliente, escenario)).status_code == 403

    reprogramacion_id = (await _proponer(residente, escenario)).json()["id"]
    # Revisa el supervisor, nadie más.
    for cliente in (residente, control, super_intendente):
        assert (await _paso(cliente, reprogramacion_id, "revisar")).status_code == 403
    assert (await _paso(supervisor, reprogramacion_id, "revisar")).status_code == 200
    # Valida y realiza control de obra, nadie más.
    for paso in ("validar", "aplicar"):
        for cliente in (residente, supervisor, super_intendente):
            assert (await _paso(cliente, reprogramacion_id, paso)).status_code == 403
    # Rechazan el supervisor y control, no el residente.
    for cliente in (residente, super_intendente):
        r = await _paso(cliente, reprogramacion_id, "rechazar", {"motivo": "no"})
        assert r.status_code == 403


async def test_los_pasos_van_en_orden(
    escenario: Escenario,
    asignada: Trato,
    residente: httpx.AsyncClient,
    supervisor: httpx.AsyncClient,
    control: httpx.AsyncClient,
    contexto_residente: ContextoSesion,
) -> None:
    reprogramacion_id = (await _proponer(residente, escenario)).json()["id"]

    # No se valida lo que nadie revisó, ni se realiza lo que no se validó.
    saltar_a_validar = await _paso(control, reprogramacion_id, "validar")
    assert saltar_a_validar.status_code == 409, saltar_a_validar.text
    assert (await _paso(control, reprogramacion_id, "aplicar")).status_code == 409

    assert (await _paso(supervisor, reprogramacion_id, "revisar")).status_code == 200
    assert (await _paso(supervisor, reprogramacion_id, "revisar")).status_code == 409
    saltar_a_aplicar = await _paso(control, reprogramacion_id, "aplicar")
    assert saltar_a_aplicar.status_code == 409, saltar_a_aplicar.text

    # Ninguna de esas negativas movió la fecha.
    assert await _fechas(contexto_residente, escenario) == ("2026-03-02", "2026-03-13")


async def test_lo_aplicado_no_se_aplica_dos_veces(
    escenario: Escenario,
    asignada: Trato,
    residente: httpx.AsyncClient,
    supervisor: httpx.AsyncClient,
    control: httpx.AsyncClient,
) -> None:
    reprogramacion_id = await _cadena_hasta_validada(residente, supervisor, control, escenario)
    assert (await _paso(control, reprogramacion_id, "aplicar")).status_code == 200
    assert (await _paso(control, reprogramacion_id, "aplicar")).status_code == 409
    assert (
        await _paso(control, reprogramacion_id, "rechazar", {"motivo": "tarde"})
    ).status_code == 409


# --- 4. Atomicidad ---------------------------------------------------------------


async def test_realizar_es_atomico_si_no_queda_aplicada_la_fecha_no_se_mueve(
    escenario: Escenario,
    asignada: Trato,
    residente: httpx.AsyncClient,
    supervisor: httpx.AsyncClient,
    control: httpx.AsyncClient,
    contexto_residente: ContextoSesion,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reprogramacion_id = await _cadena_hasta_validada(residente, supervisor, control, escenario)

    original = RepositorioReprogramacionesSQL.actualizar

    async def falla_al_aplicar(self, rid, *, estatus, **resto):  # type: ignore[no-untyped-def]
        if estatus == "aplicada":
            raise ReprogramacionNoModificada("simulada")
        return await original(self, rid, estatus=estatus, **resto)

    monkeypatch.setattr(RepositorioReprogramacionesSQL, "actualizar", falla_al_aplicar)

    r = await _paso(control, reprogramacion_id, "aplicar")
    assert r.status_code == 404, r.text
    # Ni la fecha se movió, ni quedó el renglón de la bitácora, ni cambió el estatus.
    assert await _fechas(contexto_residente, escenario) == ("2026-03-02", "2026-03-13")
    assert (
        await control.get(f"/api/v1/obras/{escenario.obra_id}/programa/ediciones")
    ).json() == []
    assert (await _lista(control, escenario))[0]["estatus"] == "validada"


# --- 5. Una viva por actividad; rechazar -----------------------------------------


async def test_solo_cabe_una_reprogramacion_viva_por_actividad(
    escenario: Escenario, asignada: Trato, residente: httpx.AsyncClient
) -> None:
    assert (await _proponer(residente, escenario)).status_code == 201
    otra = await _proponer(
        residente,
        escenario,
        {"fecha_termino": "2026-03-27", "motivo": "Otra fecha distinta"},
    )
    assert otra.status_code == 409, otra.text
    assert "ya tiene una reprogramación" in otra.json()["detail"]


async def test_rechazar_exige_motivo_y_libera_la_actividad(
    escenario: Escenario,
    asignada: Trato,
    residente: httpx.AsyncClient,
    supervisor: httpx.AsyncClient,
) -> None:
    reprogramacion_id = (await _proponer(residente, escenario)).json()["id"]

    sin_motivo = await _paso(supervisor, reprogramacion_id, "rechazar", {"motivo": ""})
    assert sin_motivo.status_code == 422, sin_motivo.text

    rechazada = await _paso(
        supervisor, reprogramacion_id, "rechazar", {"motivo": "El contrato no lo permite"}
    )
    assert rechazada.status_code == 200, rechazada.text
    assert rechazada.json()["estatus"] == "rechazada"
    assert rechazada.json()["motivo_rechazo"] == "El contrato no lo permite"
    assert rechazada.json()["rechazada_por"] == str(escenario.supervisor_id)

    # Rechazada, ya no estorba: se puede proponer otra.
    assert (await _proponer(residente, escenario)).status_code == 201


@pytest.mark.parametrize(
    "cuerpo, esperado",
    [
        ({"motivo": "algo"}, 409),  # ninguna fecha: el esquema lo deja pasar, el dominio no
        ({"fecha_inicio": "2026-03-02", "fecha_termino": "2026-03-13", "motivo": "x"}, 409),
        ({"fecha_inicio": "2026-03-20", "fecha_termino": "2026-03-10", "motivo": "x"}, 409),
        ({"fecha_inicio": "2026-03-09"}, 422),  # sin motivo: lo corta el esquema
    ],
)
async def test_una_propuesta_sin_nada_que_mover_o_incoherente_se_rechaza(
    escenario: Escenario,
    asignada: Trato,
    residente: httpx.AsyncClient,
    cuerpo: dict,
    esperado: int,
) -> None:
    r = await _proponer(residente, escenario, cuerpo)
    assert r.status_code == esperado, r.text
    assert await _lista(residente, escenario) == []


# --- 6. Se avisa por rol de quien propuso ----------------------------------------


@dataclass
class Buzon:
    """Lo que salió por correo, para ver a quién se le avisó."""

    correos: list[Correo]

    def prefijos(self, indice: int = -1) -> list[str]:
        """Quién recibió ese correo, por el prefijo de su dirección (`res`, `sup`, `ctrl`,
        `ctrl2`, `sup2`): los fixtures dan a cada usuario una dirección `prefijo-sufijo@`."""
        return sorted(a.split("@")[0].split("-")[0] for a in self.correos[indice].para)


@pytest.fixture
async def buzon(monkeypatch: pytest.MonkeyPatch) -> Buzon:
    buzon = Buzon(correos=[])

    async def capturar(self, correo: Correo) -> bool:  # type: ignore[no-untyped-def]
        buzon.correos.append(correo)
        return True

    async def sin_push(self, aviso) -> int:  # type: ignore[no-untyped-def]
        return 0

    monkeypatch.setattr(ClienteResend, "enviar", capturar)
    monkeypatch.setattr(ClienteExpoPush, "enviar", sin_push)
    return buzon


@pytest.fixture
async def equipo_extra(escenario: Escenario) -> AsyncIterator[None]:
    """Otro usuario de control de obra (ve toda la organización) y un supervisor que no
    lleva a este residente: el primero debe enterarse, el segundo no."""
    engine = create_async_engine(DATABASE_URL_ADMIN)
    sufijo = uuid.uuid4().hex[:8]
    async with engine.begin() as conn:
        for nombre, rol, prefijo in (
            ("Otro Control", "control_obra", "ctrl2"),
            ("Supervisor de otra rama", "supervisor", "sup2"),
        ):
            await conn.execute(
                text(
                    "insert into usuario (id, org_id, nombre, email, rol) "
                    "values (:id, :org, :nombre, :email, :rol)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "org": str(escenario.org_id),
                    "nombre": nombre,
                    "email": f"{prefijo}-{sufijo}@test.mx",
                    "rol": rol,
                },
            )
    yield
    await engine.dispose()


async def test_lo_que_propuso_el_residente_se_avisa_al_supervisor_y_a_control(
    escenario: Escenario,
    asignada: Trato,
    equipo_extra: None,
    buzon: Buzon,
    residente: httpx.AsyncClient,
    supervisor: httpx.AsyncClient,
    control: httpx.AsyncClient,
) -> None:
    reprogramacion_id = await _cadena_hasta_validada(residente, supervisor, control, escenario)
    # Hasta validar no se avisa: la fecha todavía no cambia.
    assert buzon.correos == []

    assert (await _paso(control, reprogramacion_id, "aplicar")).status_code == 200
    [correo] = buzon.correos
    assert correo.etiquetas == {"tipo": "reprogramacion_aplicada"}
    assert "2026-03-09" in correo.texto
    assert "El contratista no tenía cuadrilla" in correo.texto
    # El supervisor de la obra y el otro control. No el residente (propuso él), ni quien
    # realizó la acción, ni un supervisor que no lleva esta obra.
    assert buzon.prefijos() == ["ctrl2", "sup"]


async def test_lo_que_propuso_el_supervisor_se_avisa_al_residente_y_a_control(
    escenario: Escenario,
    asignada: Trato,
    equipo_extra: None,
    buzon: Buzon,
    supervisor: httpx.AsyncClient,
    control: httpx.AsyncClient,
) -> None:
    reprogramacion_id = (await _proponer(supervisor, escenario)).json()["id"]
    assert (await _paso(control, reprogramacion_id, "validar")).status_code == 200
    assert (await _paso(control, reprogramacion_id, "aplicar")).status_code == 200

    [correo] = buzon.correos
    # El residente de la obra y el otro control. No el supervisor (propuso él).
    assert buzon.prefijos() == ["ctrl2", "res"]
    assert correo.asunto.startswith("Reprogramación aplicada")


# --- 6b. Observaciones de control -------------------------------------------------


async def _observar(
    cliente: httpx.AsyncClient, reprogramacion_id: str, texto: str = "Ojo con la cuadrilla"
) -> httpx.Response:
    return await _paso(cliente, reprogramacion_id, "observaciones", {"texto": texto})


async def test_control_deja_una_observacion_y_se_avisa_al_residente_y_al_supervisor(
    escenario: Escenario,
    asignada: Trato,
    equipo_extra: None,
    buzon: Buzon,
    residente: httpx.AsyncClient,
    supervisor: httpx.AsyncClient,
    control: httpx.AsyncClient,
) -> None:
    reprogramacion_id = (await _proponer(residente, escenario)).json()["id"]

    creada = await _observar(control, reprogramacion_id, "  Avisa al cliente antes de mover esto  ")
    assert creada.status_code == 201, creada.text
    assert creada.json()["texto"] == "Avisa al cliente antes de mover esto"
    assert creada.json()["rol"] == "control_obra"
    assert creada.json()["usuario_id"] == str(escenario.control_id)
    assert creada.json()["usuario_nombre"] == "Control Test"

    # Se avisó al residente y al supervisor de la obra: no a control ni al supervisor ajeno.
    [correo] = buzon.correos
    assert correo.etiquetas == {"tipo": "reprogramacion_observada"}
    assert "Avisa al cliente antes de mover esto" in correo.texto
    assert buzon.prefijos() == ["res", "sup"]

    # No es un paso de la cadena: el estatus no se movió.
    # Y la ven todos los que ven la reprogramación, con su autor, en orden.
    await _observar(control, reprogramacion_id, "Segunda nota")
    for cliente in (residente, supervisor, control):
        [fila] = await _lista(cliente, escenario)
        assert fila["estatus"] == "propuesta"
        assert [o["texto"] for o in fila["observaciones"]] == [
            "Avisa al cliente antes de mover esto",
            "Segunda nota",
        ]
        assert fila["observaciones"][0]["usuario_nombre"] == "Control Test"


async def test_se_observa_en_cualquier_estatus_tambien_aplicada_o_rechazada(
    escenario: Escenario,
    asignada: Trato,
    residente: httpx.AsyncClient,
    supervisor: httpx.AsyncClient,
    control: httpx.AsyncClient,
) -> None:
    rechazada = (await _proponer(residente, escenario)).json()["id"]
    assert (await _paso(supervisor, rechazada, "rechazar", {"motivo": "no"})).status_code == 200
    assert (await _observar(control, rechazada, "Para la próxima")).status_code == 201

    aplicada = await _cadena_hasta_validada(residente, supervisor, control, escenario)
    assert (await _paso(control, aplicada, "aplicar")).status_code == 200
    assert (await _observar(control, aplicada, "Quedó bien")).status_code == 201

    por_id = {f["id"]: f for f in await _lista(control, escenario)}
    assert por_id[rechazada]["estatus"] == "rechazada"
    assert por_id[aplicada]["estatus"] == "aplicada"
    assert len(por_id[rechazada]["observaciones"]) == 1
    assert len(por_id[aplicada]["observaciones"]) == 1


async def test_solo_control_observa_y_el_texto_no_puede_ir_vacio(
    escenario: Escenario,
    asignada: Trato,
    residente: httpx.AsyncClient,
    supervisor: httpx.AsyncClient,
    super_intendente: httpx.AsyncClient,
    control: httpx.AsyncClient,
) -> None:
    reprogramacion_id = (await _proponer(residente, escenario)).json()["id"]
    for cliente in (residente, supervisor, super_intendente):
        assert (await _observar(cliente, reprogramacion_id)).status_code == 403

    assert (await _observar(control, reprogramacion_id, "")).status_code == 422
    en_blanco = await _observar(control, reprogramacion_id, "   ")
    assert en_blanco.status_code == 409, en_blanco.text
    assert (await _lista(control, escenario))[0]["observaciones"] == []


async def test_una_observacion_de_otra_organizacion_no_existe(
    escenario: Escenario,
    asignada: Trato,
    residente: httpx.AsyncClient,
    contexto_ajeno: ContextoSesion,
) -> None:
    reprogramacion_id = (await _proponer(residente, escenario)).json()["id"]
    control_ajeno = ContextoSesion(
        org_id=contexto_ajeno.org_id, usuario_id=contexto_ajeno.usuario_id, rol="control_obra"
    )
    async with _cliente(control_ajeno) as cliente:
        r = await cliente.post(
            f"/api/v1/reprogramaciones/{reprogramacion_id}/observaciones",
            json={"texto": "intruso"},
        )
        assert r.status_code == 404, r.text


# --- 7. Aislamiento ---------------------------------------------------------------


async def test_otra_organizacion_no_ve_ni_toca_nada(
    escenario: Escenario,
    asignada: Trato,
    residente: httpx.AsyncClient,
    control: httpx.AsyncClient,
    ajeno: httpx.AsyncClient,
    contexto_ajeno: ContextoSesion,
) -> None:
    reprogramacion_id = (await _proponer(residente, escenario)).json()["id"]

    assert (
        await ajeno.get(f"/api/v1/obras/{escenario.obra_id}/reprogramaciones")
    ).status_code == 404
    assert (await _proponer(ajeno, escenario)).status_code in (403, 404)

    # Control de otra organización: el rol cuadra y RLS niega. Sin `Idempotency-Key`: la
    # organización ajena no existe en la base y el registro de la clave toparía con su
    # llave foránea antes de llegar a RLS.
    control_ajeno = ContextoSesion(
        org_id=contexto_ajeno.org_id, usuario_id=contexto_ajeno.usuario_id, rol="control_obra"
    )
    async with _cliente(control_ajeno) as cliente:
        r = await cliente.post(f"/api/v1/reprogramaciones/{reprogramacion_id}/validar", json={})
        assert r.status_code == 404, r.text
        r = await cliente.post(f"/api/v1/reprogramaciones/{reprogramacion_id}/aplicar", json={})
        assert r.status_code == 404, r.text

    assert (await _lista(control, escenario))[0]["estatus"] == "propuesta"
