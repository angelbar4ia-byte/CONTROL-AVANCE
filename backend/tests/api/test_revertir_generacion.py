"""Deshacer el workflow A: `DELETE /obras/{id}/actividades` (§11.3 A.2).

Generar es la única operación del sistema que escribe cientos de renglones de
un botón, con un parámetro —el modo de pago— que se elige **antes** de ver el
resultado. Equivocarse ahí costaba reiniciar la organización entera, que era lo
único que había.

Lo que estas pruebas fijan es la frontera de "deshacer":

 1. **Sin ejecución encima, se revierte.** Se borra lo que la generación creó
    —actividades y `ProgramaObra`— y nada más: la obra se queda.
 2. **Con ejecución encima, no.** Un avance, una estimación, una revisión o un
    cierre hacen que borrar deje de ser deshacer y pase a perder trabajo. Es un
    409 con el detalle de qué hay, para poder decidir sin abrir la base.
 3. **El rol es el mismo que genera.** Si aquí fuera más ancho, deshacer sería
    el rodeo para saltarse la guarda de la ruta que crea.

Sin BD: el repositorio se sustituye por un doble, porque lo que se prueba es la
decisión, no el SQL.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from obractrl.adapters.api.casos_uso import obtener_revertir_generacion
from obractrl.adapters.api.dependencias import contexto_actual
from obractrl.application.casos_uso.generar_obra_desde_prototipo import (
    RevertirGeneracionDeObra,
)
from obractrl.domain.shared.diccionario import Rol
from obractrl.infrastructure.db.sesion import ContextoSesion
from obractrl.main import crear_app

ORG = uuid.uuid4()
USUARIO = uuid.uuid4()
OBRA = uuid.uuid4()


class _ObrasFalso:
    """Doble de `RepositorioObras` con lo que la reversión consulta."""

    def __init__(self, *, existe: bool = True, rastro: dict[str, int] | None = None):
        self._existe = existe
        self._rastro = rastro or {}
        self.borradas: list[uuid.UUID] = []

    async def obtener(self, obra_id: uuid.UUID) -> dict[str, Any] | None:
        return {"id": str(obra_id)} if self._existe else None

    async def rastro_de_ejecucion(self, obra_id: uuid.UUID) -> dict[str, int]:
        return self._rastro

    async def borrar_generacion(self, obra_id: uuid.UUID) -> int:
        self.borradas.append(obra_id)
        return 157


class _UowFalsa:
    async def __aenter__(self) -> _UowFalsa:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def commit(self) -> None:
        return None


def _cliente(obras: _ObrasFalso, rol: Rol) -> TestClient:
    app = crear_app()
    app.dependency_overrides[obtener_revertir_generacion] = (
        lambda: RevertirGeneracionDeObra(obras=obras, uow=_UowFalsa())
    )
    app.dependency_overrides[contexto_actual] = lambda: ContextoSesion(
        org_id=ORG, usuario_id=USUARIO, rol=rol.value
    )
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def obras() -> _ObrasFalso:
    return _ObrasFalso()


@pytest.fixture
def creador(obras: _ObrasFalso) -> Iterator[TestClient]:
    with _cliente(obras, Rol.CONTROL_OBRA) as c:
        yield c


class TestRevertir:
    def test_sin_ejecucion_encima_se_deshace(
        self, creador: TestClient, obras: _ObrasFalso
    ) -> None:
        respuesta = creador.delete(f"/api/v1/obras/{OBRA}/actividades")

        assert respuesta.status_code == 204
        assert obras.borradas == [OBRA]

    def test_una_obra_fuera_de_alcance_es_404(self) -> None:
        # RLS hace indistinguible "no existe" de "no la puedes ver" (§12.4).
        vacio = _ObrasFalso(existe=False)
        with _cliente(vacio, Rol.CONTROL_OBRA) as c:
            assert c.delete(f"/api/v1/obras/{OBRA}/actividades").status_code == 404

    def test_con_avance_capturado_no_se_deshace(self) -> None:
        conAvance = _ObrasFalso(rastro={"avances": 3})
        with _cliente(conAvance, Rol.CONTROL_OBRA) as c:
            respuesta = c.delete(f"/api/v1/obras/{OBRA}/actividades")

        assert respuesta.status_code == 409
        # El detalle dice QUÉ hay: es lo que permite decidir sin abrir la base.
        assert "3 avances" in respuesta.json()["detail"]
        assert conAvance.borradas == []

    def test_una_estimación_también_frena(self) -> None:
        # No solo el avance: cualquiera de los cuatro rastros cuenta, porque
        # los cuatro cuelgan de la actividad que se iba a borrar.
        conEstimacion = _ObrasFalso(rastro={"estimaciones": 1})
        with _cliente(conEstimacion, Rol.CONTROL_OBRA) as c:
            assert c.delete(f"/api/v1/obras/{OBRA}/actividades").status_code == 409

    def test_el_residente_no_deshace_lo_que_no_genera(self) -> None:
        # Mismo rol que `POST /obras/{id}/generar`: si aquí fuera más ancho,
        # deshacer sería el rodeo para saltarse la guarda de la ruta que crea.
        obras = _ObrasFalso()
        with _cliente(obras, Rol.RESIDENTE) as c:
            assert c.delete(f"/api/v1/obras/{OBRA}/actividades").status_code == 403
        assert obras.borradas == []
