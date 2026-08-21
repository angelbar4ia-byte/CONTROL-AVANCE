"""Versión mínima del cliente móvil: el 426 y quién no lo recibe (§12.12).

Dos cosas se protegen aquí, y las dos pueden dejar gente afuera:

1. **Que el 426 llegue** a quien de verdad quedó atrás. Sin él, un cliente
   viejo produce errores de contrato sueltos que nadie sabe atribuir a la
   versión.
2. **Que no llegue a nadie más.** La web no manda cabecera de cliente, ni la
   sonda de Render, ni `curl`. Si el middleware bloqueara a quien no se
   identifica, subir la mínima tiraría el sistema entero.

Y un tercero que no se ve hasta que falla: `version_es_menor` tiene que dar
exactamente lo mismo que `comparar()` en `mobile/src/lib/version.ts`. Si el
servidor considerara obsoleto lo que la app cree al día, la app pediría datos,
recibiría 426 y **no** mostraría la pantalla de actualización —quedaría rota
sin explicación—. Por eso los casos de abajo están duplicados en
`mobile/tests/version.test.ts`: son un contrato entre dos lenguajes.

No necesita Postgres: el rechazo ocurre en el borde, antes de tocar la base.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from obractrl.adapters.api.middleware import version_es_menor
from obractrl.infrastructure.config import obtener_config
from obractrl.main import crear_app


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """App real con la mínima fijada en 1.4.0.

    Se parcha el objeto de configuración ya cacheado (`lru_cache`) en vez de
    la variable de entorno: la caché se llenó al importar y cambiar el entorno
    después no la movería.
    """
    cfg = obtener_config()
    monkeypatch.setattr(cfg, "movil_version_minima", "1.4.0", raising=False)
    with TestClient(crear_app(), raise_server_exceptions=False) as c:
        yield c


class TestElBorde:
    def test_un_cliente_viejo_recibe_426(self, cliente: TestClient) -> None:
        respuesta = cliente.get("/health", headers={"X-Cliente-Version": "1.3.9"})
        # `/health` está exenta, así que se usa otra ruta para el caso real.
        assert respuesta.status_code == 200

        respuesta = cliente.get("/api/v1/me", headers={"X-Cliente-Version": "1.3.9"})
        assert respuesta.status_code == 426
        assert respuesta.headers["X-Version-Minima"] == "1.4.0"
        assert respuesta.headers["content-type"].startswith("application/problem+json")

    def test_el_426_dice_qué_versión_hace_falta(self, cliente: TestClient) -> None:
        # Sin este dato la app solo puede decir "actualiza", y el usuario que
        # ya actualizó una vez no sabe si le sirvió.
        cuerpo = cliente.get(
            "/api/v1/me", headers={"X-Cliente-Version": "1.0.0"}
        ).json()
        assert "1.4.0" in cuerpo["detail"]

    def test_un_cliente_al_día_pasa_de_largo(self, cliente: TestClient) -> None:
        # 401 y no 426: llegó al endpoint, que lo rechazó por no traer token.
        # Eso es exactamente lo que se quiere comprobar — que pasó el borde.
        respuesta = cliente.get("/api/v1/me", headers={"X-Cliente-Version": "1.4.0"})
        assert respuesta.status_code == 401

    def test_quien_no_manda_cabecera_no_se_bloquea(self, cliente: TestClient) -> None:
        # La web, `curl` y la sonda de Render caen aquí. La política es
        # "quien se identifica como app vieja, se bloquea", no "quien no se
        # identifica, se bloquea".
        assert cliente.get("/api/v1/me").status_code == 401

    def test_la_ruta_de_versión_nunca_se_bloquea(self, cliente: TestClient) -> None:
        # Es la que le dice al cliente obsoleto qué versión necesita:
        # bloquearla lo dejaría sin forma de saber por qué lo bloquearon.
        respuesta = cliente.get(
            "/api/v1/cliente/version", headers={"X-Cliente-Version": "0.1.0"}
        )
        assert respuesta.status_code == 200
        assert respuesta.json()["minima"] == "1.4.0"

    def test_la_sonda_de_render_nunca_se_bloquea(self, cliente: TestClient) -> None:
        respuesta = cliente.get("/health", headers={"X-Cliente-Version": "0.1.0"})
        assert respuesta.status_code == 200


class TestComparacion:
    """Espejo de `comparar()` en `mobile/src/lib/version.ts`."""

    @pytest.mark.parametrize(
        ("actual", "minima", "esperado"),
        [
            ("1.0.0", "1.0.0", False),
            ("1.0.1", "1.0.0", False),
            ("1.0.0", "1.0.1", True),
            ("1.9.0", "1.10.0", True),
            ("2.0.0", "1.99.99", False),
        ],
    )
    def test_orden(self, actual: str, minima: str, esperado: bool) -> None:
        assert version_es_menor(actual, minima) is esperado

    def test_los_componentes_faltantes_valen_cero(self) -> None:
        # Play muestra "1.2" y la configuración suele escribir "1.2.0".
        assert version_es_menor("1.2", "1.2.0") is False
        assert version_es_menor("1.2", "1.2.1") is True

    def test_una_pre_release_no_es_menor_que_su_release(self) -> None:
        # Si lo fuera, el build que el equipo está probando se bloquearía solo.
        assert version_es_menor("1.4.0-rc.1", "1.4.0") is False

    def test_un_componente_no_numérico_vale_cero_y_no_nan(self) -> None:
        # El default importa: lo que decide si se bloquea el acceso no puede
        # resolverse en "no sé".
        assert version_es_menor("1.x.0", "1.0.0") is False
        assert version_es_menor("1.x.0", "1.1.0") is True


class TestPolitica:
    def test_por_omisión_no_se_bloquea_a_nadie(self) -> None:
        # Un entorno recién levantado no debe dejar fuera a los clientes por
        # olvido de configurar: bloquear tiene que ser una decisión explícita.
        from obractrl.infrastructure.config import Config

        assert Config().movil_version_minima == "0.0.0"
