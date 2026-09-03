"""Unir dos oficios que resultaron ser el mismo (§8.3, §10.3, migración 0047).

El catálogo real del cliente escribe el mismo oficio de dos formas —
`EQUIPAMIENTO` con claves `EQU` y `EQUIPAMIENTOS` con claves `MSA`— y confirmó
que son uno solo. Separados parten el desglose de un frente en dos renglones
que nadie puede contratar por separado.

Lo que estas pruebas fijan es la frontera de "fusionar":

 1. **Se registra el alias** (§10.3). Es lo que hace que la fusión dure: el
    archivo del cliente sigue trayendo los dos nombres, así que sin el mapeo la
    próxima carga recrea el oficio absorbido y la fusión se deshace sola. Es la
    razón de existir de este endpoint frente a un borrado a mano.
 2. **Se dice qué se movió.** Una fusión es difícil de revertir y un 204 mudo
    dejaría a quien la pidió sin saber si tocó tres conceptos o cuatrocientos.
 3. **Un oficio no se fusiona consigo mismo**, y uno que no existe da 404 en vez
    de borrar a medias.
 4. **El rol es el que configura catálogos.** Si aquí fuera más ancho, fusionar
    sería el rodeo para borrar catálogo sin permiso de catálogo.

Sin BD: los repositorios se sustituyen por dobles, porque lo que se prueba es
la decisión, no el SQL.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from obractrl.adapters.api.dependencias import contexto_actual, sesion_rls
from obractrl.domain.shared.diccionario import Rol
from obractrl.infrastructure.db.sesion import ContextoSesion
from obractrl.main import crear_app

ORG = uuid.uuid4()
USUARIO = uuid.uuid4()
DESTINO = uuid.uuid4()
ABSORBIDA = uuid.uuid4()


class _EspecialidadesFalso:
    def __init__(self) -> None:
        self.fusiones: list[tuple[uuid.UUID, uuid.UUID]] = []

    async def listar(self, *, solo_activos: bool = True) -> list[dict[str, Any]]:
        return [
            {"id": DESTINO, "clave": "EQU", "nombre": "EQUIPAMIENTO", "orden": 1},
            {"id": ABSORBIDA, "clave": "MSA", "nombre": "EQUIPAMIENTOS", "orden": 2},
        ]

    async def fusionar(
        self, *, destino: uuid.UUID, absorbida: uuid.UUID
    ) -> dict[str, int]:
        self.fusiones.append((destino, absorbida))
        return {"conceptos": 17, "contratistas": 2}


class _CargasFalso:
    def __init__(self) -> None:
        self.mapeos_registrados: list[dict[str, str]] = []

    async def registrar_mapeo(
        self, *, entidad: str, alias: str, clave_canonica: str
    ) -> None:
        self.mapeos_registrados.append(
            {"entidad": entidad, "alias": alias, "clave_canonica": clave_canonica}
        )


class _SesionFalsa:
    async def commit(self) -> None:  # pragma: no cover - trivial
        return None


@pytest.fixture
def dobles() -> tuple[_EspecialidadesFalso, _CargasFalso]:
    return _EspecialidadesFalso(), _CargasFalso()


@pytest.fixture
def cliente(
    monkeypatch: pytest.MonkeyPatch,
    dobles: tuple[_EspecialidadesFalso, _CargasFalso],
) -> Iterator[TestClient]:
    yield from _cliente_con(monkeypatch, dobles, Rol.CONTROL_OBRA)


def _cliente_con(
    monkeypatch: pytest.MonkeyPatch,
    dobles: tuple[_EspecialidadesFalso, _CargasFalso],
    rol: Rol,
) -> Iterator[TestClient]:
    """La ruta construye sus repositorios con la sesión, así que se sustituyen
    los constructores y la sesión misma: el doble solo necesita `commit`."""
    especialidades, cargas = dobles
    from obractrl.adapters.api.v1 import proyectos

    monkeypatch.setattr(
        proyectos, "RepositorioEspecialidadesSQL", lambda _s: especialidades
    )
    monkeypatch.setattr(proyectos, "RepositorioCargasSQL", lambda _s: cargas)

    app = crear_app()
    app.dependency_overrides[contexto_actual] = lambda: ContextoSesion(
        org_id=ORG, usuario_id=USUARIO, rol=rol.value
    )
    app.dependency_overrides[sesion_rls] = lambda: _SesionFalsa()
    with TestClient(app, raise_server_exceptions=False) as cliente:
        yield cliente


def _fusionar(cliente: TestClient, absorbida: uuid.UUID = ABSORBIDA):
    return cliente.post(
        f"/api/v1/especialidades/{DESTINO}/fusionar",
        json={"absorbida_id": str(absorbida)},
    )


def test_registra_el_alias_para_que_la_fusion_dure(
    cliente: TestClient, dobles: tuple[_EspecialidadesFalso, _CargasFalso]
) -> None:
    """Sin el mapeo, la próxima carga recrea el oficio absorbido.

    El archivo del cliente sigue trayendo los dos nombres. Es la razón por la
    que fusionar es un endpoint y no un borrado a mano.
    """
    _, cargas = dobles
    assert _fusionar(cliente).status_code == 200
    assert cargas.mapeos_registrados == [
        {
            "entidad": "especialidad",
            "alias": "EQUIPAMIENTOS",
            "clave_canonica": "EQU",
        }
    ]


def test_dice_que_se_movio(cliente: TestClient) -> None:
    # Una fusión es difícil de revertir: un 204 mudo dejaría a quien la pidió
    # sin saber si tocó tres conceptos o cuatrocientos.
    cuerpo = _fusionar(cliente).json()
    assert cuerpo["conceptos"] == 17
    assert cuerpo["contratistas"] == 2
    assert cuerpo["alias_registrado"] == "EQUIPAMIENTOS"


def test_un_oficio_no_se_fusiona_consigo_mismo(
    cliente: TestClient, dobles: tuple[_EspecialidadesFalso, _CargasFalso]
) -> None:
    # Se borraría a sí mismo llevándose sus conceptos por delante.
    especialidades, _ = dobles
    assert _fusionar(cliente, DESTINO).status_code == 422
    assert especialidades.fusiones == []


def test_un_oficio_que_no_existe_da_404_y_no_borra_nada(
    cliente: TestClient, dobles: tuple[_EspecialidadesFalso, _CargasFalso]
) -> None:
    especialidades, cargas = dobles
    assert _fusionar(cliente, uuid.uuid4()).status_code == 404
    assert especialidades.fusiones == []
    assert cargas.mapeos_registrados == []


def test_solo_lo_fusiona_quien_configura_catalogos(
    monkeypatch: pytest.MonkeyPatch, dobles: tuple[_EspecialidadesFalso, _CargasFalso]
) -> None:
    """El mismo rol que el resto del catálogo (§4).

    Si aquí fuera más ancho, fusionar sería el rodeo para borrar catálogo sin
    tener permiso de catálogo: la absorbida desaparece y sus conceptos cambian
    de oficio.
    """
    especialidades, _ = dobles
    for rol in (Rol.RESIDENTE, Rol.SUPERVISOR):
        for cliente in _cliente_con(monkeypatch, dobles, rol):
            assert _fusionar(cliente).status_code == 403
    assert especialidades.fusiones == []
