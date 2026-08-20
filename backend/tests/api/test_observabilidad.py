"""Id de petición, logs y sondas de salud (§11.7, §12.2, §12.4).

Lo que se fija aquí es la capacidad de **reconstruir qué pasó**: que el id de
una petición sea el mismo en la cabecera, en el cuerpo del error y en el log,
y que las sondas digan la verdad sin exponer nada ni caerse con lo que
vigilan.

Sin Postgres ni Redis a propósito: `/health/dependencias` tiene que responder
—reportando el problema— justo cuando esas dos no están, que es cuando alguien
la consulta.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from obractrl.infrastructure.config import Config
from obractrl.infrastructure.observabilidad import (
    SIN_PETICION,
    FiltroDeIdDePeticion,
    configurar_logging,
    id_de_peticion,
    iniciar_sentry,
    nuevo_id_de_peticion,
    poner_id_de_peticion,
)
from obractrl.main import crear_app


@pytest.fixture(scope="module")
def app() -> FastAPI:
    aplicacion = crear_app()

    @aplicacion.get("/_prueba/eco-id")
    async def _eco() -> dict[str, str]:
        """Devuelve el id que ve el **endpoint**, no el middleware.

        Es la prueba de que el `ContextVar` sobrevive el salto: con
        `BaseHTTPMiddleware` el endpoint corre en otra tarea y podría no
        verlo.
        """
        return {"visto_por_el_endpoint": id_de_peticion()}

    @aplicacion.get("/_prueba/registra")
    async def _registra() -> dict[str, str]:
        logging.getLogger("obractrl.prueba").info("una línea de bitácora")
        return {"ok": "si"}

    return aplicacion


@pytest.fixture(scope="module")
def cliente(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


class TestIdDePeticion:
    def test_toda_respuesta_lleva_el_id_en_la_cabecera(
        self, cliente: TestClient
    ) -> None:
        assert cliente.get("/health").headers["x-request-id"]

    def test_el_endpoint_ve_el_mismo_id_que_sale_en_la_cabecera(
        self, cliente: TestClient
    ) -> None:
        """El motivo de usar un middleware ASGI puro y no `BaseHTTPMiddleware`."""
        respuesta = cliente.get("/_prueba/eco-id")
        assert (
            respuesta.json()["visto_por_el_endpoint"]
            == respuesta.headers["x-request-id"]
        )

    def test_respeta_el_id_que_trae_el_cliente(self, cliente: TestClient) -> None:
        """Para poder seguir una petición **a través** de los servicios: si el
        front ya trae su id de traza, cortarlo aquí parte el hilo."""
        respuesta = cliente.get(
            "/health", headers={"X-Request-Id": "traza-del-front-123"}
        )
        assert respuesta.headers["x-request-id"] == "traza-del-front-123"

    def test_dos_peticiones_no_comparten_id(self, cliente: TestClient) -> None:
        primera = cliente.get("/health").headers["x-request-id"]
        segunda = cliente.get("/health").headers["x-request-id"]
        assert primera != segunda

    def test_el_problem_json_trae_el_mismo_id_que_la_cabecera(
        self, cliente: TestClient
    ) -> None:
        """Es lo que convierte "me falló" en algo buscable en Render."""
        respuesta = cliente.get("/api/v1/me")
        assert respuesta.json()["request_id"] == respuesta.headers["x-request-id"]

    def test_el_navegador_puede_leer_la_cabecera_entre_origenes(
        self, cliente: TestClient
    ) -> None:
        """Sin `expose_headers`, el front no puede leer el id justo cuando lo
        necesita: en la respuesta de error que va a reportar."""
        respuesta = cliente.get("/health", headers={"Origin": "http://localhost:5173"})
        expuestas = respuesta.headers.get("access-control-expose-headers", "")
        assert "X-Request-Id" in expuestas


class TestSaneadoDelIdEntrante:
    @pytest.mark.parametrize(
        "sucio",
        [
            "malo\ninyectado",          # log forging: renglones falsos
            "con espacios",
            "<script>alert(1)</script>",
            "",
            "   ",
        ],
    )
    def test_un_id_con_caracteres_que_no_sirven_se_reemplaza(
        self, sucio: str
    ) -> None:
        """El id es diagnóstico, no autenticación: una cabecera mal formada no
        puede tumbar la petición, pero tampoco ensuciar la bitácora — un id con
        saltos de línea inyectaría renglones falsos en ella."""
        generado = nuevo_id_de_peticion(sucio)
        assert generado != sucio
        assert len(generado) == 32
        assert generado.isalnum()

    @pytest.mark.parametrize(
        "limpio", ["abc123", "traza-del-front-123", "a_b.c-d", "A1"]
    )
    def test_un_id_razonable_se_respeta(self, limpio: str) -> None:
        assert nuevo_id_de_peticion(limpio) == limpio

    @pytest.mark.parametrize("largo", [200, 5000])
    def test_un_id_desmedido_se_recorta_en_vez_de_descartarse(
        self, largo: int
    ) -> None:
        """Se recorta y no se reemplaza a propósito: el prefijo del id del
        cliente sigue sirviendo para correlacionar, y lo que había que evitar
        —una cabecera de 8 KB repetida en cada línea de log— ya se evitó."""
        generado = nuevo_id_de_peticion("a" * largo)
        assert generado == "a" * 64


class TestLog:
    def test_cada_linea_lleva_el_id_de_su_peticion(
        self, cliente: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """El filtro se aplica a **todo** lo que se registre, no solo a los
        loggers propios: por eso es un `Filter` y no un `LoggerAdapter`."""
        filtro = FiltroDeIdDePeticion()
        with caplog.at_level(logging.INFO):
            caplog.handler.addFilter(filtro)
            try:
                respuesta = cliente.get("/_prueba/registra")
            finally:
                caplog.handler.removeFilter(filtro)

        registro = next(
            r for r in caplog.records if r.name == "obractrl.prueba"
        )
        assert registro.id_peticion == respuesta.headers["x-request-id"]

    def test_fuera_de_una_peticion_el_id_es_un_guion(self) -> None:
        """El worker de jobs y el arranque registran con el mismo formato; el
        campo tiene que existir igual para que el formato no reviente."""
        poner_id_de_peticion(SIN_PETICION)
        registro = logging.LogRecord(
            "x", logging.INFO, "x", 1, "m", None, None
        )
        FiltroDeIdDePeticion().filter(registro)
        assert registro.id_peticion == SIN_PETICION  # type: ignore[attr-defined]

    def test_el_sql_no_se_registra_por_default(self) -> None:
        """`sqlalchemy.engine` en INFO registra cada sentencia **con sus
        parámetros**, y esos parámetros son datos de la organización (§12.4).
        Ni siquiera en debug se enciende solo."""
        configurar_logging(Config(debug=True))  # type: ignore[arg-type]
        assert logging.getLogger("sqlalchemy.engine").level == logging.WARNING

    def test_no_duplica_las_lineas_al_reconfigurar(self) -> None:
        """Se reemplazan los handlers de la raíz en vez de agregar: uvicorn
        instala los suyos y sumarle otro imprime cada línea dos veces."""
        cfg = Config()  # type: ignore[call-arg]
        configurar_logging(cfg)
        configurar_logging(cfg)
        assert len(logging.getLogger().handlers) == 1


class TestSentry:
    def test_sin_dsn_no_arranca_pero_tampoco_falla(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """§12.8: un despliegue al que todavía no le pusieron la variable
        tiene que levantar igual — mismo criterio que Resend sin API key."""
        with caplog.at_level(logging.INFO):
            activo = iniciar_sentry(Config(sentry_dsn=""))  # type: ignore[arg-type]
        assert activo is False
        assert "no configurado" in caplog.text

    def test_con_dsn_arranca_con_los_ajustes_de_la_casa(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`sentry_sdk.init` se intercepta: dejarlo correr de verdad instala un
        cliente global que se queda intentando mandar por red los errores de
        las **demás** pruebas."""
        import sentry_sdk

        recibidos: dict[str, object] = {}
        monkeypatch.setattr(sentry_sdk, "init", lambda **kw: recibidos.update(kw))

        activo = iniciar_sentry(
            Config(  # type: ignore[arg-type]
                sentry_dsn="https://llavesecreta@o1.ingest.sentry.io/42",
                entorno="prod",
            )
        )

        assert activo is True
        assert recibidos["environment"] == "prod"
        # §12.4: nunca correos ni cabeceras de usuarios a un tercero. El
        # default del SDK ya es `False`; se fija explícito para que un cambio
        # de default no lo voltee sin que nadie se entere.
        assert recibidos["send_default_pii"] is False
        # A la escala del §12.1 el valor está en los errores; el muestreo de
        # transacciones es lo que encarece la factura sin que nadie lo mire.
        assert recibidos["traces_sample_rate"] == 0.0

    def test_el_dsn_no_se_registra(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Un DSN de Sentry lleva la llave del proyecto (§12.4)."""
        import sentry_sdk

        monkeypatch.setattr(sentry_sdk, "init", lambda **kw: None)
        with caplog.at_level(logging.INFO):
            iniciar_sentry(
                Config(  # type: ignore[arg-type]
                    sentry_dsn="https://llavesecreta@o1.ingest.sentry.io/42",
                    entorno="dev",
                )
            )
        assert "llavesecreta" not in caplog.text


class TestSondas:
    def test_health_responde_sin_tocar_nada(self, cliente: TestClient) -> None:
        """Es la sonda de liveness de Render: si la base se cae, reiniciar el
        proceso solo agrega un arranque en frío a un incidente que ya existe."""
        cuerpo = cliente.get("/health").json()
        assert cuerpo["estatus"] == "ok"
        assert "postgres" not in cuerpo

    def test_dependencias_reporta_en_vez_de_caerse(self, cliente: TestClient) -> None:
        """Sin Postgres ni Redis —el caso de esta máquina— sigue siendo 200:
        una sonda que se cae junto con lo que vigila no diagnostica nada."""
        respuesta = cliente.get("/health/dependencias")
        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert cuerpo["estatus"] == "degradado"
        assert cuerpo["postgres"] != "ok"
        assert cuerpo["cola"] != "ok"

    def test_reporta_disco_jobs_y_respaldo(self, cliente: TestClient) -> None:
        """El §11.7 pide los cinco, no solo base y cola.

        Los tres nuevos responden aunque la infraestructura no esté: el disco
        no depende de nadie, y los jobs y el respaldo reportan su fallo en vez
        de desaparecer del cuerpo — un campo ausente se lee como "no lo miré".
        """
        cuerpo = cliente.get("/health/dependencias").json()
        for campo in ("jobs", "disco", "ultimo_respaldo"):
            assert campo in cuerpo, f"la sonda ya no reporta {campo}"
            assert cuerpo[campo], f"{campo} vino vacío"
        # El disco no depende de Postgres ni de Redis: siempre tiene respuesta.
        assert "GB libres" in cuerpo["disco"]

    def test_el_disco_y_el_respaldo_no_degradan_el_estatus(
        self, cliente: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`estatus` es el único campo sobre el que alerta un monitor, así que
        significa "la API no puede trabajar". Un disco casi lleno o un respaldo
        que nadie registró hay que atenderlos, pero no son eso — y una sonda que
        grita por todo deja de leerse."""
        import obractrl.main as modulo

        async def _ok() -> str:
            return "ok"

        async def _sin_registro() -> str:
            return "respaldo: sin registro · restauración probada: sin registro"

        monkeypatch.setattr(modulo, "_postgres_responde", _ok)
        monkeypatch.setattr(modulo, "_redis_responde", _ok)
        monkeypatch.setattr(modulo, "_ultimo_respaldo", _sin_registro)
        monkeypatch.setattr(modulo, "_disco_disponible", lambda: "0.2 GB libres · 99% usado")

        cuerpo = cliente.get("/health/dependencias").json()
        assert cuerpo["estatus"] == "ok"
        assert "sin registro" in cuerpo["ultimo_respaldo"]
        assert "99%" in cuerpo["disco"]

    def test_no_expone_la_cadena_de_conexion(self, cliente: TestClient) -> None:
        """El mensaje de asyncpg puede traer el DSN con contraseña; se reporta
        la clase del fallo, que es lo que dice si es red, credencial o esquema."""
        cuerpo = cliente.get("/health/dependencias").json()
        plano = " ".join(str(v) for v in cuerpo.values())
        for filtracion in ("postgresql", "redis://", "@", "password"):
            assert filtracion not in plano
