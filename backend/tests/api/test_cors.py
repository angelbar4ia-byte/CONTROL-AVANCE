"""CORS: quién puede llamar a esta API desde un navegador (§12.8, §12.4).

## El incidente que las motiva

La web desplegada en Vercel no podía hablar con la API de Render. En el
navegador se veía así:

    Access to fetch at 'https://…onrender.com/api/v1/usuarios' from origin
    'https://…vercel.app' has been blocked by CORS policy: No
    'Access-Control-Allow-Origin' header is present.

El mensaje señala una **cabecera ausente**, que es lo que ve el navegador, y no
la causa: el servidor sí respondió —400, `Disallowed CORS origin`— porque el
origen no estaba en `CORS_ORIGENES` y la lista seguía en su default de
desarrollo. Diagnosticarlo tomó abrir un `curl` con `-X OPTIONS`.

Y tuvo un segundo acto: al fijar `CORS_ORIGENES` en Render, el servicio dejó
de arrancar con `SettingsError: error parsing value for field "cors_origenes"`.
pydantic-settings aplica `json.loads()` a los campos de tipo complejo **antes**
de cualquier validador, así que un valor separado por comas lo tiraba. Ver
`ListaDeTexto` en `infrastructure/config.py`.

Estas pruebas fijan las tres mitades de eso —dos del borde y una de la
configuración:

1. Que un origen permitido reciba `Access-Control-Allow-Origin` y uno no
   permitido no — el comportamiento en sí, que hoy da Starlette y mañana podría
   dar otra cosa si alguien toca el orden de los middlewares.
2. Que `/health` **publique la lista**. Sin eso, el próximo despliegue mal
   configurado vuelve a ser una hora de `curl`.

No necesita Postgres: el preflight se resuelve en el borde.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from obractrl.infrastructure.config import obtener_config
from obractrl.main import crear_app

PERMITIDO = "https://control-avance-chi.vercel.app"
AJENO = "https://sitio-de-otro.example"


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """App real con un origen de producción configurado.

    Se parcha el objeto de configuración ya cacheado (`lru_cache`), como en
    `test_version_de_cliente.py`: la caché se llenó al importar y cambiar la
    variable de entorno después no la movería.
    """
    cfg = obtener_config()
    monkeypatch.setattr(cfg, "cors_origenes", [PERMITIDO], raising=False)
    with TestClient(crear_app(), raise_server_exceptions=False) as c:
        yield c


def _preflight(cliente: TestClient, origen: str):
    return cliente.options(
        "/api/v1/usuarios",
        headers={
            "Origin": origen,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )


class TestPreflight:
    def test_un_origen_configurado_recibe_la_cabecera(self, cliente: TestClient) -> None:
        respuesta = _preflight(cliente, PERMITIDO)

        assert respuesta.status_code == 200
        assert respuesta.headers["access-control-allow-origin"] == PERMITIDO
        # Con credenciales: el front manda `Authorization` en cada llamada.
        assert respuesta.headers["access-control-allow-credentials"] == "true"

    def test_un_origen_ajeno_no_la_recibe(self, cliente: TestClient) -> None:
        respuesta = _preflight(cliente, AJENO)

        assert "access-control-allow-origin" not in respuesta.headers
        # 400 con el motivo en el cuerpo. El navegador **no** lo muestra —dice
        # "falta la cabecera"— y por eso el mismo dato vive en `/health`.
        assert respuesta.status_code == 400

    def test_el_id_de_petición_sale_aunque_CORS_rechace(self, cliente: TestClient) -> None:
        # `MiddlewareDeIdDePeticion` se agrega por fuera de CORS justo para
        # esto (§11.7): un rechazo por origen también es reportable.
        assert "x-request-id" in _preflight(cliente, AJENO).headers

    def test_el_canal_de_avisos_también_pasa_por_CORS(self, cliente: TestClient) -> None:
        # `GET /events` se consume con `fetch` y cabecera `Authorization`
        # (`frontend/src/lib/tiempoReal.ts`), así que dispara preflight igual
        # que cualquier mutación: si se olvida el origen, la web pierde el
        # tiempo real sin ningún error de negocio que lo explique.
        respuesta = cliente.options(
            "/api/v1/events",
            headers={
                "Origin": PERMITIDO,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )

        assert respuesta.headers["access-control-allow-origin"] == PERMITIDO


class TestUn500NoSeDisfrazaDeCORS:
    """La lección del segundo diagnóstico equivocado.

    Con la base de producción sin migrar, `GET /api/v1/usuarios` devolvía 500
    —`column "debe_cambiar_password" does not exist`—. Pero `ServerErrorMiddleware`
    va **por fuera** de `CORSMiddleware`, así que ese 500 salía sin
    `Access-Control-Allow-Origin` y el navegador reportaba, otra vez:

        blocked by CORS policy: No 'Access-Control-Allow-Origin' header

    Un error de esquema disfrazado del error que se acababa de arreglar. Estas
    pruebas fijan que un 500 llegue al navegador **como un 500**.
    """

    @pytest.fixture
    def cliente_que_truena(self, monkeypatch: pytest.MonkeyPatch):
        """La app real con una ruta que falla, montada encima.

        Se monta aquí y no en `main.py` porque es andamio de la prueba: los
        middlewares son de la aplicación y cubren cualquier ruta, incluida
        esta.
        """
        cfg = obtener_config()
        monkeypatch.setattr(cfg, "cors_origenes", [PERMITIDO], raising=False)

        app = crear_app()

        @app.get("/_prueba/truena-con-origen")
        async def _truena() -> dict[str, str]:
            raise RuntimeError("select * from usuario where email = 'ana@obractrl.mx'")

        # `raise_server_exceptions=False` para que el 500 se **responda** en vez
        # de propagarse: lo que se verifica es la respuesta que ve el navegador.
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c

    def test_el_500_lleva_la_cabecera_de_CORS(self, cliente_que_truena: TestClient) -> None:
        respuesta = cliente_que_truena.get(
            "/_prueba/truena-con-origen", headers={"Origin": PERMITIDO}
        )

        assert respuesta.status_code == 500
        # Sin esto el navegador esconde el 500 detrás de un error de CORS y el
        # operador arregla lo que no estaba roto.
        assert respuesta.headers["access-control-allow-origin"] == PERMITIDO

    def test_y_sale_como_problem_json_con_su_request_id(
        self, cliente_que_truena: TestClient
    ) -> None:
        respuesta = cliente_que_truena.get(
            "/_prueba/truena-con-origen", headers={"Origin": PERMITIDO}
        )

        assert respuesta.headers["content-type"].startswith("application/problem+json")
        cuerpo = respuesta.json()
        assert cuerpo["status"] == 500
        assert cuerpo["request_id"]
        # Nombra la clase para poder reportarlo…
        assert "RuntimeError" in cuerpo["detail"]
        # …y no el mensaje, que aquí traía SQL y un correo (§12.4).
        assert "select" not in cuerpo["detail"].lower()
        assert "ana@obractrl.mx" not in cuerpo["detail"]

    def test_el_id_de_petición_también_va_en_la_cabecera(
        self, cliente_que_truena: TestClient
    ) -> None:
        respuesta = cliente_que_truena.get(
            "/_prueba/truena-con-origen", headers={"Origin": PERMITIDO}
        )

        assert respuesta.headers["x-request-id"] == respuesta.json()["request_id"]


class TestSonda:
    def test_health_publica_los_orígenes_permitidos(self, cliente: TestClient) -> None:
        cuerpo = cliente.get("/health").json()

        assert cuerpo["cors_origenes"] == PERMITIDO

    def test_lo_dice_incluso_si_la_lista_está_vacía(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Una lista vacía y "no configurado" se ven igual desde el navegador;
        # la sonda tiene que distinguirlos con palabras.
        cfg = obtener_config()
        monkeypatch.setattr(cfg, "cors_origenes", [], raising=False)

        with TestClient(crear_app()) as c:
            assert c.get("/health").json()["cors_origenes"] == "(ninguno)"


class TestConfiguracion:
    """La variable se lee **desde el entorno**, que es como llega en Render.

    La primera versión de estas pruebas construía `Config(cors_origenes="a,b")`
    —un kwarg— y pasaba en verde mientras el despliegue **no arrancaba**:

        SettingsError: error parsing value for field "cors_origenes"
                       from source "EnvSettingsSource"

    Con un kwarg no hay fuente de entorno, así que el `json.loads()` que
    pydantic-settings aplica a los campos de tipo complejo nunca ocurría y el
    validador corría tranquilo. La prueba comprobaba una ruta que ningún
    servidor recorre.

    Por eso todas las de aquí usan `monkeypatch.setenv` y limpian la caché de
    `obtener_config`: es la única forma de que la prueba pase por donde pasa el
    proceso al arrancar.
    """

    @staticmethod
    def _config_desde_entorno(monkeypatch: pytest.MonkeyPatch, valor: str | None):
        from obractrl.infrastructure.config import Config, obtener_config

        if valor is None:
            monkeypatch.delenv("CORS_ORIGENES", raising=False)
        else:
            monkeypatch.setenv("CORS_ORIGENES", valor)
        obtener_config.cache_clear()
        return Config()

    def test_una_lista_separada_por_comas(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # La forma que documenta OPERACION.md y la que se escribe sin pensar.
        cfg = self._config_desde_entorno(
            monkeypatch, "https://uno.example, https://dos.example"
        )

        assert cfg.cors_origenes == ["https://uno.example", "https://dos.example"]

    def test_un_solo_origen(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # El caso exacto del incidente: un origen, sin comas, sin corchetes.
        cfg = self._config_desde_entorno(monkeypatch, PERMITIDO)

        assert cfg.cors_origenes == [PERMITIDO]

    def test_también_la_forma_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Es la convención de pydantic-settings: quien la conozca la va a usar
        # y no tiene por qué tumbar el arranque.
        cfg = self._config_desde_entorno(
            monkeypatch, '["https://uno.example","https://dos.example"]'
        )

        assert cfg.cors_origenes == ["https://uno.example", "https://dos.example"]

    def test_los_algoritmos_del_JWT_tienen_la_misma_trampa(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # `jwt_algoritmos` es el otro campo de lista de la configuración.
        # Nadie lo fija hoy, y por eso mismo el día que alguien lo haga sería
        # otro arranque caído sin explicación.
        from obractrl.infrastructure.config import Config, obtener_config

        monkeypatch.setenv("JWT_ALGORITMOS", "ES256,RS256")
        obtener_config.cache_clear()

        assert Config().jwt_algoritmos == ["ES256", "RS256"]

    def test_el_default_es_solo_desarrollo(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Y por eso un despliegue que no la fija rechaza a su propio front:
        # exactamente lo que pasó. El default no se cambia a "todo" —eso
        # abriría la API a cualquier sitio—, se documenta en OPERACION.md.
        cfg = self._config_desde_entorno(monkeypatch, None)

        assert cfg.cors_origenes == ["http://localhost:5173"]
