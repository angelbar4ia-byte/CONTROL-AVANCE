"""Aviso de `EstimacionValidada` por correo (§11.1, §11.3 E.5, §12.2).

Dos capas y una sola regla que las atraviesa: **una notificación no puede
deshacer una validación**. La estimación ya está commiteada cuando el evento
sale (§11.1), así que ni el caso de uso ni el adaptador de Resend levantan;
ambos devuelven si el aviso salió y dejan el motivo en el log.

- `NotificarEstimacionValidada` (aplicación) se prueba con dobles de los
  puertos: es asíncrono pero puro, sin BD.
- `ClienteResend` (infraestructura) se prueba con un transporte falso de
  `httpx`, como `test_evidencias_r2.py` prueba la firma sin tocar el bucket.
  Lo que se vigila ahí es el §12.4: la API key no sale nunca de la cabecera.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx
import pytest

from obractrl.application.casos_uso.notificar_estimacion import (
    NotificarEstimacionValidada,
)
from obractrl.application.eventos import EstimacionValidada
from obractrl.application.puertos.notificaciones import Correo, EnviadorDeCorreo
from obractrl.infrastructure.config import Config
from obractrl.infrastructure.notificaciones.resend import (
    URL_EMAILS,
    ClienteResend,
    CorreoNoConfigurado,
)

API_KEY = "re_llave_de_prueba_que_jamas_debe_salir_en_una_respuesta"
REMITENTE = "ObraCtrl <avisos@obractrl.mx>"

OBRA_ID = uuid.uuid4()
ESTIMACION_ID = uuid.uuid4()
CREADORA = uuid.uuid4()
VALIDADORA = uuid.uuid4()
RESIDENTE = uuid.uuid4()


# --- Dobles de los puertos -------------------------------------------------


class _Estimaciones:
    def __init__(self, fila: dict | None) -> None:
        self._fila = fila

    async def obtener(self, estimacion_id: uuid.UUID) -> dict | None:
        return self._fila


class _Obras:
    def __init__(self, fila: dict | None) -> None:
        self._fila = fila

    async def obtener(self, obra_id: uuid.UUID) -> dict | None:
        return self._fila


class _Usuarios:
    """Devuelve un correo por id conocido; los demás simplemente no aparecen,
    como dice el puerto."""

    def __init__(self, correos: dict[uuid.UUID, str] | None = None) -> None:
        self.correos = (
            correos
            if correos is not None
            else {
                CREADORA: "residente@obractrl.mx",
                VALIDADORA: "control@obractrl.mx",
                RESIDENTE: "residente@obractrl.mx",
            }
        )
        self.pedidos: list[list[uuid.UUID]] = []

    async def correos_de(self, usuario_ids: list[uuid.UUID]) -> list[dict]:
        self.pedidos.append(list(usuario_ids))
        return [
            {"id": uid, "nombre": "quien sea", "email": self.correos[uid]}
            for uid in usuario_ids
            if uid in self.correos
        ]


class _Correo:
    """`EnviadorDeCorreo` que guarda lo enviado."""

    def __init__(self, acepta: bool = True) -> None:
        self.acepta = acepta
        self.enviados: list[Correo] = []

    async def enviar(self, correo: Correo) -> bool:
        self.enviados.append(correo)
        return self.acepta


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
    "validada_por": VALIDADORA,
}

OBRA = {"id": OBRA_ID, "clave": "OBR-001", "residente_id": RESIDENTE}


def _caso_uso(
    *,
    estimacion: dict | None = ESTIMACION,
    obra: dict | None = OBRA,
    usuarios: _Usuarios | None = None,
    correo: _Correo | None = None,
) -> tuple[NotificarEstimacionValidada, _Usuarios, _Correo]:
    buzon = correo or _Correo()
    identidad = usuarios or _Usuarios()
    caso_uso = NotificarEstimacionValidada(
        estimaciones=_Estimaciones(estimacion),  # type: ignore[arg-type]
        obras=_Obras(obra),  # type: ignore[arg-type]
        usuarios=identidad,  # type: ignore[arg-type]
        correo=buzon,  # type: ignore[arg-type]
    )
    return caso_uso, identidad, buzon


def _evento() -> EstimacionValidada:
    return EstimacionValidada(obra_id=OBRA_ID, estimacion_id=ESTIMACION_ID)


class TestDestinatarios:
    async def test_avisa_a_quien_creo_valido_y_al_residente(self) -> None:
        """§4: son los tres papeles que el workflow E toca."""
        caso_uso, identidad, _ = _caso_uso()
        await caso_uso.ejecutar(_evento())
        assert identidad.pedidos == [[CREADORA, VALIDADORA, RESIDENTE]]

    async def test_no_repite_a_quien_ocupa_dos_papeles(self) -> None:
        """El Residente puede haber creado su propia estimación."""
        estimacion = {**ESTIMACION, "creada_por": RESIDENTE}
        caso_uso, identidad, _ = _caso_uso(estimacion=estimacion)
        await caso_uso.ejecutar(_evento())
        assert identidad.pedidos == [[RESIDENTE, VALIDADORA]]

    async def test_pide_la_identidad_por_su_puerto_y_no_lee_la_tabla(self) -> None:
        """§11.1: `usuario` es del contexto Identidad; Notificaciones la
        consulta por la fachada."""
        caso_uso, identidad, _ = _caso_uso()
        await caso_uso.ejecutar(_evento())
        assert identidad.pedidos, "el caso de uso tiene que pasar por el puerto"

    async def test_una_obra_sin_residente_no_impide_el_aviso(self) -> None:
        caso_uso, _, buzon = _caso_uso(obra={"id": OBRA_ID, "clave": "OBR-001"})
        assert await caso_uso.ejecutar(_evento()) is True
        assert buzon.enviados[0].para


class TestFallaHaciaAdentro:
    async def test_una_estimacion_fuera_de_alcance_no_levanta(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Se validó hace un instante; si ya no se ve, el alcance cambió. No
        hay a quién avisarle, pero tampoco nada que deshacer."""
        caso_uso, _, buzon = _caso_uso(estimacion=None)
        with caplog.at_level(logging.WARNING):
            assert await caso_uso.ejecutar(_evento()) is False
        assert buzon.enviados == []
        assert "ya no está en el alcance" in caplog.text

    async def test_sin_correos_registrados_no_levanta(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caso_uso, _, buzon = _caso_uso(usuarios=_Usuarios(correos={}))
        with caplog.at_level(logging.WARNING):
            assert await caso_uso.ejecutar(_evento()) is False
        assert buzon.enviados == []

    async def test_un_correo_en_blanco_no_cuenta_como_destinatario(self) -> None:
        usuarios = _Usuarios(correos={CREADORA: "   ", VALIDADORA: "", RESIDENTE: ""})
        caso_uso, _, buzon = _caso_uso(usuarios=usuarios)
        assert await caso_uso.ejecutar(_evento()) is False
        assert buzon.enviados == []

    async def test_un_proveedor_que_rechaza_devuelve_false_sin_levantar(self) -> None:
        """§11.3 E.5: la estimación ya está validada y commiteada."""
        caso_uso, _, _ = _caso_uso(correo=_Correo(acepta=False))
        assert await caso_uso.ejecutar(_evento()) is False


class TestContenidoDelAviso:
    async def test_el_asunto_lleva_folio_obra_y_semana(self) -> None:
        caso_uso, _, buzon = _caso_uso()
        await caso_uso.ejecutar(_evento())
        asunto = buzon.enviados[0].asunto
        assert "EST-2026-33-001" in asunto
        assert "OBR-001" in asunto
        assert "33/2026" in asunto

    async def test_una_estimacion_sin_folio_sigue_avisando(self) -> None:
        caso_uso, _, buzon = _caso_uso(estimacion={**ESTIMACION, "folio": None})
        await caso_uso.ejecutar(_evento())
        assert "(sin folio)" in buzon.enviados[0].asunto

    async def test_dice_que_el_periodo_queda_bloqueado(self) -> None:
        """El otro efecto del §11.3 E.5: quien recibe el aviso tiene que saber
        que esa semana ya no se puede volver a estimar."""
        caso_uso, _, buzon = _caso_uso()
        await caso_uso.ejecutar(_evento())
        assert "bloqueado" in buzon.enviados[0].texto

    async def test_la_etiqueta_agrupa_el_envio_y_no_lleva_importes(self) -> None:
        caso_uso, _, buzon = _caso_uso()
        await caso_uso.ejecutar(_evento())
        assert buzon.enviados[0].etiquetas == {"tipo": "estimacion_validada"}


# ---------------------------------------------------------------------------
# El adaptador de Resend (§12.2)
# ---------------------------------------------------------------------------


def _config(**cambios: str) -> Config:
    valores = {"resend_api_key": API_KEY, "resend_remitente": REMITENTE}
    valores.update(cambios)
    return Config(**valores)  # type: ignore[arg-type]


def _cliente_falso(
    manejar: Any, *, capturadas: list[httpx.Request] | None = None
) -> httpx.AsyncClient:
    def _transporte(peticion: httpx.Request) -> httpx.Response:
        if capturadas is not None:
            capturadas.append(peticion)
        return manejar(peticion)

    return httpx.AsyncClient(transport=httpx.MockTransport(_transporte))


def _ok(_peticion: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"id": "res_123"})


CORREO = Correo(
    para=("control@obractrl.mx",),
    asunto="Estimación EST-2026-33-001 validada",
    html="<p>hola</p>",
    texto="hola",
    etiquetas={"tipo": "estimacion_validada"},
)


class TestClienteResend:
    async def test_envia_y_devuelve_true_cuando_resend_acepta(self) -> None:
        async with _cliente_falso(_ok) as http:
            assert await ClienteResend(_config(), http).enviar(CORREO) is True

    async def test_arma_el_cuerpo_que_espera_la_api(self) -> None:
        capturadas: list[httpx.Request] = []
        async with _cliente_falso(_ok, capturadas=capturadas) as http:
            await ClienteResend(_config(), http).enviar(CORREO)

        peticion = capturadas[0]
        assert str(peticion.url) == URL_EMAILS
        cuerpo = peticion.read().decode()
        assert '"from"' in cuerpo and REMITENTE in cuerpo
        assert "control@obractrl.mx" in cuerpo
        assert '"tags"' in cuerpo

    async def test_la_llave_solo_viaja_en_la_cabecera(self) -> None:
        """§12.4: ni en el cuerpo, ni en la URL, ni en el log."""
        capturadas: list[httpx.Request] = []
        async with _cliente_falso(_ok, capturadas=capturadas) as http:
            await ClienteResend(_config(), http).enviar(CORREO)

        peticion = capturadas[0]
        assert peticion.headers["Authorization"] == f"Bearer {API_KEY}"
        assert API_KEY not in str(peticion.url)
        assert API_KEY not in peticion.read().decode()

    async def test_no_registra_la_llave_ni_los_destinatarios(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        async with _cliente_falso(_ok) as http:
            with caplog.at_level(logging.INFO):
                await ClienteResend(_config(), http).enviar(CORREO)
        assert API_KEY not in caplog.text
        assert "control@obractrl.mx" not in caplog.text
        assert "res_123" in caplog.text, "el id sí, para rastrearlo en el panel"

    async def test_un_rechazo_de_resend_devuelve_false_y_solo_loguea_el_codigo(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        def _rechaza(_peticion: httpx.Request) -> httpx.Response:
            return httpx.Response(422, json={"message": "dominio no verificado"})

        async with _cliente_falso(_rechaza) as http:
            with caplog.at_level(logging.ERROR):
                assert await ClienteResend(_config(), http).enviar(CORREO) is False
        assert "422" in caplog.text
        assert "dominio no verificado" not in caplog.text

    async def test_una_caida_de_red_no_levanta(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """§11.3 E.5: la estimación ya está validada; el aviso es lo único que
        se puede perder."""

        def _truena(peticion: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("sin red", request=peticion)

        async with _cliente_falso(_truena) as http:
            with caplog.at_level(logging.ERROR):
                assert await ClienteResend(_config(), http).enviar(CORREO) is False
        assert "ConnectError" in caplog.text

    @pytest.mark.parametrize(
        ("cambio", "variable"),
        [
            ({"resend_api_key": ""}, "RESEND_API_KEY"),
            ({"resend_remitente": ""}, "RESEND_REMITENTE"),
        ],
    )
    async def test_sin_configurar_avisa_cual_variable_falta_y_no_levanta(
        self,
        cambio: dict[str, str],
        variable: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """§12.8: un entorno de desarrollo sin Resend no puede hacer fallar la
        validación de una estimación."""
        async with _cliente_falso(_ok) as http:
            with caplog.at_level(logging.WARNING):
                enviado = await ClienteResend(_config(**cambio), http).enviar(CORREO)
        assert enviado is False
        assert variable in caplog.text

    async def test_un_correo_sin_destinatarios_no_sale(self) -> None:
        async with _cliente_falso(_ok) as http:
            vacio = Correo(para=(), asunto="x", html="<p>x</p>")
            assert await ClienteResend(_config(), http).enviar(vacio) is False

    def test_cumple_el_puerto(self) -> None:
        """`EnviadorDeCorreo` es `runtime_checkable`: la comprobación es la que
        haría el ensamblado de `main.py`."""
        assert isinstance(ClienteResend(_config()), EnviadorDeCorreo)

    def test_la_falta_de_configuracion_tiene_nombre_propio(self) -> None:
        """`CorreoNoConfigurado` no llega al borde —`enviar` la atrapa— pero
        existe para que la causa sea nombrable en el log y aquí."""
        assert issubclass(CorreoNoConfigurado, RuntimeError)
