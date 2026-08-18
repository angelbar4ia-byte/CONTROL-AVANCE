"""Todo error de la API sale en `problem+json` (§11.2, RFC 7807).

`main.py` ya traducía las ~40 excepciones de dominio. Lo que se fija aquí es
el resto —lo que **no** nace de una regla— porque es justo lo que se escapaba:

- `HTTPException` de los routers y de Starlette (403 de `exigir_rol`, 409 de
  `/reportes/{id}/descargar`, 404/405 de enrutamiento),
- el 422 de Pydantic,
- y cualquier fallo no previsto.

El motivo no es cosmético: `frontend/src/api/cliente.ts` lee `type`, `title` y
`detail` en **toda** respuesta de error. Una sola que salga con el formato por
defecto de FastAPI obliga a un caso especial en el cliente, y ese caso especial
es donde se pierden los mensajes.

No necesita Postgres: estas rutas fallan en el borde, antes de tocar la base.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from obractrl.main import crear_app

TIPO_BASE = "https://obractrl.mx/errores/"


@pytest.fixture(scope="module")
def app() -> FastAPI:
    """La app real, con dos rutas de prueba montadas encima.

    Se montan aquí y no en `main.py` porque son andamio de la prueba: los
    manejadores de error son de la aplicación, así que cubren cualquier ruta
    —incluidas estas— sin que el código de producción cargue con ellas.
    """
    aplicacion = crear_app()

    @aplicacion.get("/_prueba/suma")
    async def _suma(n: int) -> dict[str, int]:
        return {"n": n}

    @aplicacion.get("/_prueba/truena")
    async def _truena() -> dict[str, str]:
        raise RuntimeError("select * from usuario where email = 'ana@obractrl.mx'")

    @aplicacion.get("/_prueba/conflicto")
    async def _conflicto() -> dict[str, str]:
        raise HTTPException(status_code=409, detail="El reporte no está listo.")

    return aplicacion


@pytest.fixture(scope="module")
def cliente(app: FastAPI) -> Iterator[TestClient]:
    # `raise_server_exceptions=False` para que el 500 se **responda** en vez de
    # propagarse a la prueba: lo que se verifica es la respuesta que ve el
    # cliente, no que la excepción exista.
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _es_problema(respuesta: object, *, status: int, tipo: str) -> dict:
    """Aserción común: content-type, los cuatro campos del RFC y el slug."""
    assert respuesta.status_code == status  # type: ignore[attr-defined]
    assert respuesta.headers["content-type"].startswith(  # type: ignore[attr-defined]
        "application/problem+json"
    )
    cuerpo = respuesta.json()  # type: ignore[attr-defined]
    assert cuerpo["type"] == f"{TIPO_BASE}{tipo}"
    assert cuerpo["status"] == status
    assert cuerpo["title"]
    assert cuerpo["detail"]
    assert cuerpo["instance"].startswith("/")
    return cuerpo


class TestAutenticacion:
    def test_sin_cabecera_es_401_y_no_403(self, cliente: TestClient) -> None:
        """403 significa "te identifiqué y no puedes"; sin token nadie se
        identificó. El front decide con esto entre mandar a login y enseñar
        "no tienes permiso"."""
        cuerpo = _es_problema(
            cliente.get("/api/v1/me"), status=401, tipo="no-autenticado"
        )
        assert "Authorization" in cuerpo["detail"]

    def test_el_401_conserva_el_reto_de_autenticacion(
        self, cliente: TestClient
    ) -> None:
        """RFC 9110 §11.6.1: un 401 sin `WWW-Authenticate` está incompleto. El
        manejador genérico copia las cabeceras de la `HTTPException`."""
        respuesta = cliente.get("/api/v1/me")
        assert respuesta.headers["www-authenticate"] == "Bearer"

    def test_un_token_ilegible_da_el_mismo_401(self, cliente: TestClient) -> None:
        """No se le dice al cliente si falló por no mandarlo o por mandarlo
        mal: no cambia lo que tiene que hacer, y distinguirlo da pistas."""
        _es_problema(
            cliente.get("/api/v1/me", headers={"Authorization": "Bearer basura"}),
            status=401,
            tipo="no-autenticado",
        )


class TestEnrutamiento:
    def test_una_ruta_inexistente_es_problem_json(self, cliente: TestClient) -> None:
        """El 404 lo levanta Starlette antes de llegar a un router; se atrapa
        su `HTTPException`, no la de FastAPI, justamente por esto."""
        _es_problema(cliente.get("/api/v1/no-existe"), status=404, tipo="no-encontrado")

    def test_un_metodo_no_permitido_tambien(self, cliente: TestClient) -> None:
        _es_problema(cliente.post("/health"), status=405, tipo="metodo-no-permitido")

    def test_un_conflicto_del_router_conserva_su_detalle(
        self, cliente: TestClient
    ) -> None:
        """El 409 de `/reportes/{id}/descargar` dice por qué no está listo; esa
        frase es lo que el usuario lee."""
        cuerpo = _es_problema(
            cliente.get("/_prueba/conflicto"), status=409, tipo="conflicto"
        )
        assert cuerpo["detail"] == "El reporte no está listo."


class TestValidacion:
    def test_el_422_de_pydantic_es_problem_json(self, cliente: TestClient) -> None:
        _es_problema(
            cliente.get("/_prueba/suma", params={"n": "no-es-un-numero"}),
            status=422,
            tipo="peticion-invalida",
        )

    def test_conserva_que_campo_fallo_y_por_que(self, cliente: TestClient) -> None:
        """Uniformar el formato no puede costar el detalle por campo: el front
        lo necesita para marcar el input, y perderlo sería cambiar un problema
        por otro."""
        cuerpo = cliente.get("/_prueba/suma", params={"n": "x"}).json()
        assert cuerpo["errores"][0]["campo"] == "n"
        assert cuerpo["errores"][0]["motivo"]
        assert cuerpo["errores"][0]["tipo"]

    def test_un_parametro_faltante_nombra_el_campo(self, cliente: TestClient) -> None:
        cuerpo = cliente.get("/_prueba/suma").json()
        assert [e["campo"] for e in cuerpo["errores"]] == ["n"]
        assert "n" in cuerpo["detail"]


class TestFalloNoPrevisto:
    def test_un_fallo_no_previsto_es_500_en_problem_json(
        self, cliente: TestClient
    ) -> None:
        _es_problema(cliente.get("/_prueba/truena"), status=500, tipo="error-interno")

    def test_no_le_devuelve_al_cliente_el_mensaje_de_la_excepcion(
        self, cliente: TestClient
    ) -> None:
        """§12.4: el mensaje de algo no previsto puede traer SQL, una ruta del
        servidor o el valor de la fila que se estaba procesando."""
        cuerpo = cliente.get("/_prueba/truena").json()
        assert "select" not in cuerpo["detail"].lower()
        assert "ana@obractrl.mx" not in cuerpo["detail"]

    def test_pero_si_nombra_la_clase_para_poder_reportarlo(
        self, cliente: TestClient
    ) -> None:
        """Es lo que permite cruzar el reporte del usuario con el log del
        servidor sin exponer nada."""
        assert "RuntimeError" in cliente.get("/_prueba/truena").json()["detail"]

    def test_la_traza_completa_queda_en_el_log(
        self, cliente: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level("ERROR"):
            cliente.get("/_prueba/truena")
        assert "Fallo no previsto" in caplog.text
        assert "RuntimeError" in caplog.text


class TestLoQueNoSeRompio:
    def test_los_errores_de_dominio_siguen_con_su_propio_tipo(self) -> None:
        """El manejador genérico va **después** en el registro, pero FastAPI
        resuelve por clase, no por orden: un `ErrorDeEstimacion` sigue saliendo
        como `regla-de-estimacion` y no como `error-interno`. Si esto se
        rompiera, el cliente perdería la capacidad de ramificar por regla."""
        from obractrl.domain.estimacion.reglas import ErrorDeEstimacion

        aplicacion = crear_app()

        @aplicacion.get("/_prueba/regla")
        async def _regla() -> dict[str, str]:
            raise ErrorDeEstimacion("El periodo 21/2026 ya está bloqueado.")

        with TestClient(aplicacion, raise_server_exceptions=False) as c:
            cuerpo = _es_problema(
                c.get("/_prueba/regla"), status=409, tipo="regla-de-estimacion"
            )
        assert "bloqueado" in cuerpo["detail"]

    def test_health_sigue_respondiendo_sin_tocar_la_base(
        self, cliente: TestClient
    ) -> None:
        respuesta = cliente.get("/health")
        assert respuesta.status_code == 200
        assert respuesta.json()["estatus"] == "ok"
