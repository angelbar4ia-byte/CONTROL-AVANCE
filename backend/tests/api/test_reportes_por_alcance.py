"""`POST /reportes/{tipo}`: el catálogo, sus roles y sus parámetros (§11.2).

Lo que se protege aquí es que **el genérico no sea un rodeo**. Las dos rutas
específicas —`GET /estimaciones/{id}/export` y `GET /obras/{id}/expediente/pdf`—
tienen sus guardas desde la Fase 5; si el endpoint nuevo dejara pedir el mismo
trabajo con menos permisos, la guarda vieja se volvería decorativa sin que
ninguna prueba se enterara.

Y el orden de las validaciones: **existe → puedes → está completo**. Al revés,
un 422 por parámetro faltante le confirmaría a alguien sin permiso que ese
reporte existe.

No necesita Postgres ni Redis: la cola se sustituye por un doble que solo
anota lo que se le encoló, que es justo lo que estas pruebas verifican.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient

from obractrl.adapters.api.casos_uso import obtener_cola_de_trabajos
from obractrl.adapters.api.dependencias import contexto_actual
from obractrl.adapters.export.catalogo import CATALOGO
from obractrl.adapters.export.trabajos import (
    EXPEDIENTE_PDF,
    EXPORTAR_ESTIMACION_XLSX,
    INSUMOS_PROGRAMADOS_XLSX,
    REPORTE_DE_AVANCE_XLSX,
)
from obractrl.domain.shared.diccionario import Rol
from obractrl.infrastructure.db.sesion import ContextoSesion
from obractrl.main import crear_app

ORG = uuid.uuid4()
USUARIO = uuid.uuid4()


@dataclass
class _Encolado:
    id: str
    estatus: str


class _ColaFalsa:
    """Doble de `ColaDeTrabajos` que anota en vez de hablar con Redis."""

    def __init__(self) -> None:
        self.encolados: list[tuple[str, dict[str, Any]]] = []

    async def encolar(self, trabajo: str, **argumentos: Any) -> _Encolado:
        self.encolados.append((trabajo, argumentos))
        return _Encolado(id="trabajo-1", estatus="en_cola")


@pytest.fixture
def cola() -> _ColaFalsa:
    return _ColaFalsa()


def _cliente(cola: _ColaFalsa, rol: Rol) -> TestClient:
    app = crear_app()
    app.dependency_overrides[obtener_cola_de_trabajos] = lambda: cola
    app.dependency_overrides[contexto_actual] = lambda: ContextoSesion(
        org_id=ORG, usuario_id=USUARIO, rol=rol.value
    )
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def residente(cola: _ColaFalsa) -> Iterator[TestClient]:
    with _cliente(cola, Rol.RESIDENTE) as c:
        yield c


@pytest.fixture
def control(cola: _ColaFalsa) -> Iterator[TestClient]:
    with _cliente(cola, Rol.CONTROL_OBRA) as c:
        yield c


class TestCatalogo:
    def test_publica_los_tipos_con_lo_que_exigen(self, residente: TestClient) -> None:
        cuerpo = residente.get("/api/v1/reportes/tipos").json()
        por_tipo = {t["tipo"]: t for t in cuerpo}

        assert set(por_tipo) == set(CATALOGO)
        assert por_tipo["estimacion"]["requiere"] == ["estimacion_id"]
        # Vacío = cualquier rol autenticado; el alcance lo pone RLS.
        assert por_tipo["avance"]["roles"] == []
        assert por_tipo["avance"]["formato"] == "xlsx"
        assert por_tipo["expediente"]["formato"] == "pdf"

    def test_los_tipos_no_chocan_con_el_id_de_un_reporte(
        self, residente: TestClient
    ) -> None:
        # `/reportes/tipos` y `/reportes/{reporte_id}` comparten forma: si el
        # orden de declaración se invirtiera, pedir los tipos consultaría el
        # estado de un reporte llamado "tipos".
        assert residente.get("/api/v1/reportes/tipos").status_code == 200


class TestAvance:
    def test_cualquier_rol_lo_pide_y_no_lleva_filtro_de_alcance(
        self, residente: TestClient, cola: _ColaFalsa
    ) -> None:
        respuesta = residente.post("/api/v1/reportes/avance", json={})

        assert respuesta.status_code == 202
        trabajo, argumentos = cola.encolados[0]
        assert trabajo == REPORTE_DE_AVANCE_XLSX
        # El alcance viaja como contexto RLS, no como filtro: son estos tres
        # y ninguno más (`adapters/export/trabajos.py`).
        assert argumentos == {
            "org_id": str(ORG),
            "usuario_id": str(USUARIO),
            "rol": Rol.RESIDENTE.value,
        }

    def test_el_proyecto_es_foco_y_viaja(
        self, residente: TestClient, cola: _ColaFalsa
    ) -> None:
        proyecto = str(uuid.uuid4())
        residente.post("/api/v1/reportes/avance", json={"proyecto_id": proyecto})

        _, argumentos = cola.encolados[0]
        assert argumentos["proyecto_id"] == proyecto

    def test_no_le_pasa_al_worker_lo_que_no_entiende(
        self, residente: TestClient, cola: _ColaFalsa
    ) -> None:
        # `obra_id` es de `expediente`. Mandárselo al job de avance sería un
        # `TypeError` dentro del worker: un reporte `fallido` sin explicación.
        residente.post("/api/v1/reportes/avance", json={"obra_id": str(uuid.uuid4())})

        _, argumentos = cola.encolados[0]
        assert "obra_id" not in argumentos


class TestInsumosProgramados:
    """§7.3, §7.5 — la hoja con la que se compra."""

    _RANGO = {"desde": "2026-09-07", "hasta": "2026-11-30"}

    def test_cualquier_rol_la_pide_y_el_alcance_viaja_como_contexto(
        self, residente: TestClient, cola: _ColaFalsa
    ) -> None:
        # Un residente necesita la hoja de su obra tanto como Control la de
        # todas; quién ve qué lo decide RLS, no la guarda de la ruta.
        respuesta = residente.post(
            "/api/v1/reportes/insumos-programados", json=self._RANGO
        )

        assert respuesta.status_code == 202
        trabajo, argumentos = cola.encolados[0]
        assert trabajo == INSUMOS_PROGRAMADOS_XLSX
        assert argumentos["rol"] == Rol.RESIDENTE.value
        assert argumentos["desde"] == "2026-09-07"

    def test_sin_rango_no_se_encola(self, residente: TestClient) -> None:
        # Sin fechas no hay columnas, y elegirlas por el usuario sería adivinar
        # su horizonte de compra. Se rechaza antes de gastar un viaje al worker.
        respuesta = residente.post("/api/v1/reportes/insumos-programados", json={})
        assert respuesta.status_code == 422

    def test_los_filtros_de_foco_viajan(
        self, control: TestClient, cola: _ColaFalsa
    ) -> None:
        prototipo = str(uuid.uuid4())
        control.post(
            "/api/v1/reportes/insumos-programados",
            json={**self._RANGO, "prototipo_id": prototipo, "n_casas": 40},
        )

        _, argumentos = cola.encolados[0]
        assert argumentos["prototipo_id"] == prototipo
        assert argumentos["n_casas"] == 40

    def test_no_le_pasa_al_worker_lo_que_no_entiende(
        self, residente: TestClient, cola: _ColaFalsa
    ) -> None:
        # `estimacion_id` es de otro reporte; mandárselo sería un `TypeError`
        # dentro del worker y un reporte `fallido` sin explicación.
        residente.post(
            "/api/v1/reportes/insumos-programados",
            json={**self._RANGO, "estimacion_id": str(uuid.uuid4())},
        )

        _, argumentos = cola.encolados[0]
        assert "estimacion_id" not in argumentos


class TestGuardas:
    def test_un_tipo_inexistente_es_404_y_dice_cuáles_hay(
        self, residente: TestClient
    ) -> None:
        respuesta = residente.post("/api/v1/reportes/rendimientos", json={})

        assert respuesta.status_code == 404
        detalle = respuesta.json()["detail"]
        assert "avance" in detalle and "estimacion" in detalle

    def test_el_genérico_respeta_los_roles_de_la_ruta_específica(
        self, residente: TestClient, cola: _ColaFalsa
    ) -> None:
        # `GET /estimaciones/{id}/export` es (C, SI). Si aquí pasara, el
        # genérico sería la puerta de atrás de esa guarda.
        respuesta = residente.post(
            "/api/v1/reportes/estimacion", json={"estimacion_id": str(uuid.uuid4())}
        )

        assert respuesta.status_code == 403
        assert cola.encolados == []

    def test_control_de_obra_sí_puede_pedir_la_estimación(
        self, control: TestClient, cola: _ColaFalsa
    ) -> None:
        estimacion = str(uuid.uuid4())
        respuesta = control.post(
            "/api/v1/reportes/estimacion", json={"estimacion_id": estimacion}
        )

        assert respuesta.status_code == 202
        trabajo, argumentos = cola.encolados[0]
        assert trabajo == EXPORTAR_ESTIMACION_XLSX
        assert argumentos["estimacion_id"] == estimacion

    def test_falta_un_parámetro_obligatorio(self, control: TestClient) -> None:
        respuesta = control.post("/api/v1/reportes/estimacion", json={})

        assert respuesta.status_code == 422
        assert "estimacion_id" in respuesta.json()["detail"]

    def test_primero_el_permiso_y_luego_lo_que_falta(
        self, residente: TestClient
    ) -> None:
        # Sin `estimacion_id` **y** sin permiso: tiene que salir 403, no 422.
        # Un 422 confirmaría que el reporte existe a quien no puede pedirlo.
        respuesta = residente.post("/api/v1/reportes/estimacion", json={})

        assert respuesta.status_code == 403

    def test_el_expediente_no_restringe_rol_pero_sí_exige_la_obra(
        self, residente: TestClient, cola: _ColaFalsa
    ) -> None:
        # §11.2: el expediente es "todos lectura"; el alcance lo acota RLS
        # dentro del worker.
        assert residente.post("/api/v1/reportes/expediente", json={}).status_code == 422

        obra = str(uuid.uuid4())
        respuesta = residente.post("/api/v1/reportes/expediente", json={"obra_id": obra})

        assert respuesta.status_code == 202
        trabajo, argumentos = cola.encolados[0]
        assert trabajo == EXPEDIENTE_PDF
        assert argumentos["obra_id"] == obra
