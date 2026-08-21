"""Aviso por Expo Push (§12.2, §11.3 E.5).

Complementa `test_notificaciones.py`, que cubre el correo. Se prueban dos
cosas distintas:

- **`ClienteExpoPush`** (infraestructura), con un transporte falso de `httpx`
  como `test_evidencias_r2.py` prueba la firma sin tocar el bucket. Lo que se
  vigila es la lectura de *tickets*: Expo responde **200** aunque un mensaje
  haya fallado, así que un adaptador que solo mirara el código HTTP reportaría
  éxito sobre teléfonos que nunca recibieron nada.
- **`NotificarEstimacionValidada`** con los dos canales, donde importa que
  ninguno dependa del otro: quien no tiene dispositivo recibe solo el correo,
  y al revés.

Y una que no es cosmética: el push **no lleva el monto**. Aparece en la
pantalla de bloqueo, a la vista de cualquiera que tome el teléfono, y pasa por
servidores de Expo y de Google (§12.4). El correo sí lo lleva: llega a una
bandeja que exige contraseña.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest

from obractrl.application.casos_uso.notificar_estimacion import (
    NotificarEstimacionValidada,
)
from obractrl.application.eventos import EstimacionValidada
from obractrl.application.puertos.notificaciones import Aviso, Correo
from obractrl.infrastructure.config import Config
from obractrl.infrastructure.notificaciones.expo import URL_ENVIO, ClienteExpoPush

TOKEN_A = "ExponentPushToken[aaaaaaaaaaaaaaaaaaaaaa]"
TOKEN_B = "ExponentPushToken[bbbbbbbbbbbbbbbbbbbbbb]"
ACCESS_TOKEN = "expo_llave_que_jamas_debe_salir_en_una_respuesta"

OBRA_ID = uuid.uuid4()
ESTIMACION_ID = uuid.uuid4()
CREADORA = uuid.uuid4()
RESIDENTE = uuid.uuid4()

ESTIMACION = {
    "id": ESTIMACION_ID,
    "obra_id": OBRA_ID,
    "folio": "EST-2026-33-001",
    "semana": 33,
    "anio": 2026,
    "modo": "destajo",
    "estatus": "validada",
    "monto_total": "38855.00",
    "creada_por": CREADORA,
    "validada_por": CREADORA,
}

OBRA = {"id": OBRA_ID, "clave": "OBR-001", "residente_id": RESIDENTE}


def _cliente_falso(manejador: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(manejador))


def _aviso(tokens: tuple[str, ...] = (TOKEN_A,)) -> Aviso:
    return Aviso(tokens=tokens, titulo="Estimación validada", cuerpo="Obra OBR-001")


class TestAdaptador:
    @pytest.mark.asyncio
    async def test_cuenta_los_tickets_aceptados(self) -> None:
        def manejador(_peticion: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": [{"status": "ok"}, {"status": "ok"}]})

        cliente = ClienteExpoPush(Config(), _cliente_falso(manejador))
        assert await cliente.enviar(_aviso((TOKEN_A, TOKEN_B))) == 2

    @pytest.mark.asyncio
    async def test_un_200_con_ticket_en_error_no_es_un_envío_exitoso(self) -> None:
        # Este es el caso que un adaptador ingenuo reporta como éxito.
        def manejador(_peticion: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"status": "ok"},
                        {"status": "error", "details": {"error": "MessageTooBig"}},
                    ]
                },
            )

        cliente = ClienteExpoPush(Config(), _cliente_falso(manejador))
        assert await cliente.enviar(_aviso((TOKEN_A, TOKEN_B))) == 1

    @pytest.mark.asyncio
    async def test_identifica_el_token_muerto_por_su_posición(self) -> None:
        # La respuesta no repite el token: los tickets vienen en el mismo
        # orden que los mensajes, y de ahí sale la asociación. Sin esto no se
        # podría desactivar el dispositivo correcto —o peor, se desactivaría
        # el equivocado—.
        def manejador(_peticion: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"status": "ok"},
                        {"status": "error", "details": {"error": "DeviceNotRegistered"}},
                    ]
                },
            )

        cliente = ClienteExpoPush(Config(), _cliente_falso(manejador))
        resultado = await cliente.enviar_detallado(_aviso((TOKEN_A, TOKEN_B)))

        assert resultado.aceptados == 1
        assert resultado.muertos == (TOKEN_B,)

    @pytest.mark.asyncio
    async def test_sin_dispositivos_no_llama_a_expo(self) -> None:
        llamadas: list[httpx.Request] = []

        def manejador(peticion: httpx.Request) -> httpx.Response:
            llamadas.append(peticion)
            return httpx.Response(200, json={"data": []})

        cliente = ClienteExpoPush(Config(), _cliente_falso(manejador))
        assert await cliente.enviar(_aviso(())) == 0
        assert llamadas == []

    @pytest.mark.asyncio
    async def test_un_5xx_no_levanta(self) -> None:
        # La notificación viaja detrás de un hecho ya commiteado: un proveedor
        # caído no puede deshacer una estimación validada (§11.3 E.5).
        def manejador(_peticion: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="Service Unavailable")

        cliente = ClienteExpoPush(Config(), _cliente_falso(manejador))
        assert await cliente.enviar(_aviso()) == 0

    @pytest.mark.asyncio
    async def test_una_respuesta_inesperada_no_levanta(self) -> None:
        def manejador(_peticion: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="no soy json")

        cliente = ClienteExpoPush(Config(), _cliente_falso(manejador))
        assert await cliente.enviar(_aviso()) == 0

    @pytest.mark.asyncio
    async def test_el_access_token_solo_viaja_en_la_cabecera(self) -> None:
        capturada: dict[str, Any] = {}

        def manejador(peticion: httpx.Request) -> httpx.Response:
            capturada["url"] = str(peticion.url)
            capturada["auth"] = peticion.headers.get("authorization")
            capturada["cuerpo"] = peticion.content.decode()
            return httpx.Response(200, json={"data": [{"status": "ok"}]})

        cfg = Config(expo_access_token=ACCESS_TOKEN)
        await ClienteExpoPush(cfg, _cliente_falso(manejador)).enviar(_aviso())

        assert capturada["url"] == URL_ENVIO
        assert capturada["auth"] == f"Bearer {ACCESS_TOKEN}"
        assert ACCESS_TOKEN not in capturada["cuerpo"]

    @pytest.mark.asyncio
    async def test_sin_access_token_no_manda_authorization(self) -> None:
        # Expo acepta envíos sin token salvo que el proyecto active "enhanced
        # security": mandar `Bearer ` vacío sería peor que no mandarlo.
        capturada: dict[str, Any] = {}

        def manejador(peticion: httpx.Request) -> httpx.Response:
            capturada["auth"] = peticion.headers.get("authorization")
            return httpx.Response(200, json={"data": [{"status": "ok"}]})

        await ClienteExpoPush(Config(expo_access_token=""), _cliente_falso(manejador)).enviar(
            _aviso()
        )
        assert capturada["auth"] is None


# --- Dobles de los puertos, para el caso de uso ----------------------------


class _Estimaciones:
    async def obtener(self, _id: uuid.UUID) -> dict:
        return ESTIMACION


class _Obras:
    async def obtener(self, _id: uuid.UUID) -> dict:
        return OBRA


class _Usuarios:
    def __init__(self, *, correos: dict[uuid.UUID, str], tokens: list[str]) -> None:
        self._correos = correos
        self._tokens = tokens

    async def correos_de(self, usuario_ids: list[uuid.UUID]) -> list[dict]:
        return [
            {"id": uid, "nombre": "quien sea", "email": self._correos[uid]}
            for uid in usuario_ids
            if uid in self._correos
        ]

    async def tokens_push_de(self, _usuario_ids: list[uuid.UUID]) -> list[str]:
        return list(self._tokens)


class _Correo:
    def __init__(self, acepta: bool = True) -> None:
        self.acepta = acepta
        self.enviados: list[Correo] = []

    async def enviar(self, correo: Correo) -> bool:
        self.enviados.append(correo)
        return self.acepta


class _Push:
    def __init__(self, aceptados: int = 1) -> None:
        self.aceptados = aceptados
        self.enviados: list[Aviso] = []

    async def enviar(self, aviso: Aviso) -> int:
        self.enviados.append(aviso)
        return self.aceptados


def _caso_uso(usuarios: _Usuarios, correo: _Correo, push: _Push | None):
    return NotificarEstimacionValidada(
        estimaciones=_Estimaciones(),  # type: ignore[arg-type]
        obras=_Obras(),  # type: ignore[arg-type]
        usuarios=usuarios,  # type: ignore[arg-type]
        correo=correo,  # type: ignore[arg-type]
        push=push,  # type: ignore[arg-type]
    )


def _evento() -> EstimacionValidada:
    return EstimacionValidada(obra_id=OBRA_ID, estimacion_id=ESTIMACION_ID)


class TestLosDosCanales:
    @pytest.mark.asyncio
    async def test_sale_por_correo_y_por_push(self) -> None:
        usuarios = _Usuarios(correos={CREADORA: "a@obractrl.mx"}, tokens=[TOKEN_A])
        correo, push = _Correo(), _Push()

        assert await _caso_uso(usuarios, correo, push).ejecutar(_evento()) is True
        assert len(correo.enviados) == 1
        assert len(push.enviados) == 1

    @pytest.mark.asyncio
    async def test_sin_dispositivos_el_correo_sale_igual(self) -> None:
        usuarios = _Usuarios(correos={CREADORA: "a@obractrl.mx"}, tokens=[])
        correo, push = _Correo(), _Push()

        assert await _caso_uso(usuarios, correo, push).ejecutar(_evento()) is True
        assert len(correo.enviados) == 1
        assert push.enviados == []

    @pytest.mark.asyncio
    async def test_sin_correo_el_push_sale_igual(self) -> None:
        # Es el residente de campo dado de alta sin correo: antes de esto se
        # quedaba sin enterarse de nada.
        usuarios = _Usuarios(correos={}, tokens=[TOKEN_A])
        correo, push = _Correo(), _Push()

        assert await _caso_uso(usuarios, correo, push).ejecutar(_evento()) is True
        assert correo.enviados == []
        assert len(push.enviados) == 1

    @pytest.mark.asyncio
    async def test_si_falla_un_canal_basta_el_otro(self) -> None:
        usuarios = _Usuarios(correos={CREADORA: "a@obractrl.mx"}, tokens=[TOKEN_A])
        correo, push = _Correo(acepta=False), _Push(aceptados=1)

        assert await _caso_uso(usuarios, correo, push).ejecutar(_evento()) is True

    @pytest.mark.asyncio
    async def test_sin_ningún_canal_devuelve_falso(self) -> None:
        usuarios = _Usuarios(correos={}, tokens=[])
        assert await _caso_uso(usuarios, _Correo(), _Push()).ejecutar(_evento()) is False

    @pytest.mark.asyncio
    async def test_el_push_no_lleva_el_monto(self) -> None:
        # Se ve en la pantalla de bloqueo y pasa por Expo y Google (§12.4).
        usuarios = _Usuarios(correos={CREADORA: "a@obractrl.mx"}, tokens=[TOKEN_A])
        push = _Push()
        await _caso_uso(usuarios, _Correo(), push).ejecutar(_evento())

        aviso = push.enviados[0]
        assert "38855" not in aviso.titulo
        assert "38855" not in aviso.cuerpo
        assert "EST-2026-33-001" in aviso.titulo

    @pytest.mark.asyncio
    async def test_sin_push_configurado_ni_se_piden_los_tokens(self) -> None:
        # Un entorno sin Expo sigue notificando por correo (§12.8).
        usuarios = _Usuarios(correos={CREADORA: "a@obractrl.mx"}, tokens=[TOKEN_A])
        correo = _Correo()

        assert await _caso_uso(usuarios, correo, None).ejecutar(_evento()) is True
        assert len(correo.enviados) == 1
