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

Estas pruebas fijan las dos mitades de eso:

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
    def test_la_variable_acepta_una_lista_separada_por_comas(self) -> None:
        # Es como se escribe en Render: `CORS_ORIGENES=https://a,https://b`.
        from obractrl.infrastructure.config import Config

        cfg = Config(cors_origenes="https://uno.example, https://dos.example")

        assert cfg.cors_origenes == ["https://uno.example", "https://dos.example"]

    def test_el_default_es_solo_desarrollo(self) -> None:
        # Y por eso un despliegue que no la fija rechaza a su propio front:
        # exactamente lo que pasó. El default no se cambia a "todo" —eso
        # abriría la API a cualquier sitio—, se documenta en OPERACION.md.
        from obractrl.infrastructure.config import Config

        assert Config().cors_origenes == ["http://localhost:5173"]
