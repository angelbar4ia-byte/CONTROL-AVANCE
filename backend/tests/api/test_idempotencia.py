"""`Idempotency-Key`: huella, validación y respuestas (§11.2, §12.3).

Lo que **sí** necesita Postgres —que la clave quede en la misma transacción que
la mutación, y que un reintento no cree un segundo cierre— vive en
`tests/integracion/test_idempotencia_endtoend.py`. Aquí queda lo que se puede
fijar sin base: cómo se calcula la huella que distingue un reintento de una
clave reusada, qué cabeceras se rechazan, y que las tres respuestas salgan en
`problem+json` con el código correcto.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from obractrl.adapters.api.idempotencia import (
    CABECERA,
    LARGO_MAXIMO,
    ClaveDeIdempotenciaInvalida,
    ClaveReusada,
    PeticionYaProcesada,
    _huella,
)
from obractrl.main import crear_app

TIPO_BASE = "https://obractrl.mx/errores/"


def _peticion(metodo: str = "POST", ruta: str = "/api/v1/cierres", cuerpo: bytes = b"{}") -> Request:
    async def _recibir() -> dict[str, object]:
        return {"type": "http.request", "body": cuerpo, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": metodo,
            "path": ruta,
            "raw_path": ruta.encode(),
            "query_string": b"",
            "headers": [],
            "scheme": "http",
            "server": ("testserver", 80),
        },
        _recibir,
    )


class TestHuella:
    async def test_la_misma_peticion_da_la_misma_huella(self) -> None:
        """Es lo que permite decir "esto ya lo mandaste" en vez de ejecutarlo
        otra vez."""
        assert await _huella(_peticion()) == await _huella(_peticion())

    async def test_cambia_con_el_cuerpo(self) -> None:
        """Misma clave con otro cuerpo no es un reintento: es un error del
        cliente, y contestar como si fuera lo mismo daría por hecha una
        operación distinta de la que se pidió."""
        una = await _huella(_peticion(cuerpo=b'{"cantidad": 10}'))
        otra = await _huella(_peticion(cuerpo=b'{"cantidad": 999}'))
        assert una != otra

    async def test_cambia_con_la_ruta(self) -> None:
        assert await _huella(_peticion(ruta="/api/v1/cierres/1/validar")) != await _huella(
            _peticion(ruta="/api/v1/cierres/2/validar")
        )

    async def test_cambia_con_el_metodo(self) -> None:
        assert await _huella(_peticion(metodo="POST")) != await _huella(
            _peticion(metodo="PATCH")
        )

    async def test_los_campos_no_se_pueden_confundir_entre_si(self) -> None:
        """Los tres van separados por un byte nulo: sin separador, `POST` +
        `/ab` y `POS` + `T/ab` producirían la misma huella."""
        una = await _huella(_peticion(metodo="POST", ruta="/ab", cuerpo=b""))
        otra = await _huella(_peticion(metodo="POS", ruta="T/ab", cuerpo=b""))
        assert una != otra

    async def test_es_un_sha256(self) -> None:
        huella = await _huella(_peticion())
        assert len(huella) == 64
        assert all(c in "0123456789abcdef" for c in huella)


# ---------------------------------------------------------------------------
# Las tres respuestas, en problem+json
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def cliente() -> Iterator[TestClient]:
    aplicacion: FastAPI = crear_app()

    @aplicacion.post("/_prueba/ya-procesada")
    async def _ya() -> dict[str, str]:
        raise PeticionYaProcesada("clave-abc")

    @aplicacion.post("/_prueba/reusada")
    async def _reusada() -> dict[str, str]:
        raise ClaveReusada("clave-abc")

    @aplicacion.post("/_prueba/invalida")
    async def _invalida() -> dict[str, str]:
        raise ClaveDeIdempotenciaInvalida("La cabecera viene vacía.")

    with TestClient(aplicacion, raise_server_exceptions=False) as c:
        yield c


class TestRespuestas:
    def test_un_reintento_identico_es_409(self, cliente: TestClient) -> None:
        """409 y no 200: la operación ocurrió **una** vez y esta petición no
        hizo nada. Un 200 fingiría que este intento la ejecutó, y el cliente
        no podría distinguir "se hizo ahora" de "ya estaba hecha" — que es
        justo lo que quiere saber tras un doble clic."""
        respuesta = cliente.post("/_prueba/ya-procesada")
        assert respuesta.status_code == 409
        assert respuesta.headers["content-type"].startswith("application/problem+json")
        cuerpo = respuesta.json()
        assert cuerpo["type"] == f"{TIPO_BASE}peticion-ya-procesada"
        assert cuerpo["clave_idempotencia"] == "clave-abc"

    def test_le_dice_al_cliente_que_consulte_en_vez_de_reintentar(
        self, cliente: TestClient
    ) -> None:
        detalle = cliente.post("/_prueba/ya-procesada").json()["detail"]
        assert "consulta el recurso" in detalle

    def test_una_clave_reusada_para_otra_peticion_es_422(
        self, cliente: TestClient
    ) -> None:
        """422 y no 409: no hay un conflicto de estado que estorbe, el cliente
        mandó mal la petición."""
        respuesta = cliente.post("/_prueba/reusada")
        assert respuesta.status_code == 422
        assert respuesta.json()["type"] == f"{TIPO_BASE}clave-de-idempotencia-reusada"

    def test_una_cabecera_invalida_es_400(self, cliente: TestClient) -> None:
        respuesta = cliente.post("/_prueba/invalida")
        assert respuesta.status_code == 400
        assert (
            respuesta.json()["type"] == f"{TIPO_BASE}clave-de-idempotencia-invalida"
        )

    def test_las_tres_traen_el_id_de_peticion(self, cliente: TestClient) -> None:
        for ruta in ("ya-procesada", "reusada", "invalida"):
            respuesta = cliente.post(f"/_prueba/{ruta}")
            assert respuesta.json()["request_id"] == respuesta.headers["x-request-id"]


class TestContrato:
    def test_las_mutaciones_sensibles_declaran_la_cabecera(self) -> None:
        """Las que mueven dinero o dejan estado irreversible (§11.3 C, E), las
        altas masivas, y las que **cruzan a otro sistema** —el alta de usuario
        y el reseteo de contraseña llaman a la Admin API del proveedor de auth
        (§5.1), y eso no se deshace con un rollback—.

        Que esté en el contrato es lo que hace que Orval le genere el parámetro
        al front. Esta lista es exhaustiva a propósito: agregar una mutación
        sensible sin su cabecera rompe aquí, que es lo que se quiere."""
        spec = crear_app().openapi()
        con_cabecera = {
            f"{metodo.upper()} {ruta}"
            for ruta, ops in spec["paths"].items()
            for metodo, op in ops.items()
            if any(p.get("name") == CABECERA for p in op.get("parameters", []))
        }
        assert con_cabecera == {
            "POST /api/v1/actividades/{actividad_id}/cierre",
            "POST /api/v1/cierres/{cierre_id}/autorizar",
            "POST /api/v1/cierres/{cierre_id}/rechazar",
            "POST /api/v1/cierres-obra/{cierre_id}/participar",
            "POST /api/v1/cierres/{cierre_id}/validar",
            "POST /api/v1/obras/{obra_id}/cierre-obra",
            "PATCH /api/v1/estimaciones/{estimacion_id}",
            "POST /api/v1/estimaciones/{estimacion_id}/validar",
            "POST /api/v1/obras/bulk",
            "POST /api/v1/obras/{obra_id}/estimaciones",
            "POST /api/v1/obras/{obra_id}/generar",
            "POST /api/v1/actividades",
            "POST /api/v1/obras/{obra_id}/salidas",
            "POST /api/v1/usuarios",
            "POST /api/v1/usuarios/{usuario_id}/contrasena",
            # Fase 15: las cuatro de incidencia. No mueven dinero, pero el
            # móvil las captura sin señal y las **reenvía** desde su bandeja
            # de salida (`mobile/src/salida/bandeja.ts`). Sin la cabecera, una
            # respuesta que se pierde en la red se convierte en dos
            # incidencias —y con `impacto=detiene`, en dos bloqueos de las
            # mismas actividades (§11.3 F.5)—.
            "POST /api/v1/incidencias",
            "POST /api/v1/incidencias/{incidencia_id}/eventos",
            "POST /api/v1/incidencias/{incidencia_id}/cerrar",
            "POST /api/v1/incidencias/{incidencia_id}/rechazar",
        }

    def test_es_opcional(self) -> None:
        """Exigirla rompería a los clientes existentes; el §11.2 la pide como
        mecanismo, no como requisito de admisión. Quien la manda, se protege."""
        spec = crear_app().openapi()
        cierre = spec["paths"]["/api/v1/cierres/{cierre_id}/validar"]["post"]
        cabecera = next(
            p for p in cierre["parameters"] if p.get("name") == CABECERA
        )
        assert cabecera["required"] is False

    def test_el_tope_de_largo_deja_pasar_un_uuid(self) -> None:
        """El tope existe porque el valor lo elige el cliente y acaba en un
        índice único — pero no puede estorbar al uso normal."""
        assert LARGO_MAXIMO >= 36
