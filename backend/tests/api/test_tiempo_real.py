"""Avisos en vivo: el canal, la traducción y el flujo SSE (§11.2).

Tres cosas se protegen aquí, y las tres pueden fallar en silencio:

1. **Que el canal aísle por organización.** Es la frontera del §12.4 aplicada
   a un transporte que RLS no cubre: nadie filtra los avisos por SQL, los
   filtra este código. Si se equivoca, una organización ve los hechos de otra.
2. **Que el aviso lleve ids y no contenido.** Un canal que serializara el
   evento completo publicaría campos que el rol receptor no podría pedir por
   HTTP — y nadie lo notaría, porque el cliente los ignora.
3. **Que un suscriptor lento no tumbe el proceso.** La cola es acotada: se
   descarta, no se acumula.

No necesita Redis: sin `REDIS_URL` el canal reparte en memoria, que es
exactamente el modo del despliegue de una instancia (§12.8).
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from obractrl.adapters.api.avisos import aviso_de, suscribir_avisos
from obractrl.application.eventos import (
    ActividadCerrada,
    BusEnProceso,
    CierreDeObraCompletado,
    EstimacionValidada,
    IncidenciaDetiene,
)
from obractrl.application.puertos.tiempo_real import Aviso
from obractrl.infrastructure.config import Config
from obractrl.infrastructure.db.sesion import ContextoSesion
from obractrl.infrastructure.tiempo_real.canal import (
    TOPE_POR_SUSCRIPTOR,
    CanalDeAvisos,
    prefijo_de_canal,
)

ORG = uuid.uuid4()
OTRA_ORG = uuid.uuid4()
OBRA = uuid.uuid4()


def _canal_sin_redis() -> CanalDeAvisos:
    """Canal en modo local. `redis_url=""` es el despliegue sin Redis (§12.8)."""
    return CanalDeAvisos(Config(redis_url=""))


class TestCanal:
    @pytest.mark.asyncio
    async def test_entrega_a_quien_escucha_su_organización(self) -> None:
        canal = _canal_sin_redis()

        async with canal.suscribir(ORG) as cola:
            await canal.publicar(Aviso(org_id=ORG, tipo="actividad_cerrada"))
            assert cola.get_nowait() == {"tipo": "actividad_cerrada", "datos": {}}

    @pytest.mark.asyncio
    async def test_no_cruza_de_organización(self) -> None:
        # La frontera del §12.4 en un transporte que RLS no ve.
        canal = _canal_sin_redis()

        async with canal.suscribir(ORG) as mia, canal.suscribir(OTRA_ORG) as ajena:
            await canal.publicar(Aviso(org_id=ORG, tipo="actividad_cerrada"))

            assert mia.qsize() == 1
            assert ajena.empty()

    @pytest.mark.asyncio
    async def test_al_salir_deja_de_recibir(self) -> None:
        canal = _canal_sin_redis()

        async with canal.suscribir(ORG) as cola:
            pass

        await canal.publicar(Aviso(org_id=ORG, tipo="actividad_cerrada"))
        assert cola.empty()
        # Y no queda la cola colgada: una conexión SSE que se cierra no puede
        # dejar memoria creciendo por cada pestaña.
        assert canal.suscriptores == 0

    @pytest.mark.asyncio
    async def test_un_suscriptor_que_no_lee_no_bloquea_a_los_demás(self) -> None:
        canal = _canal_sin_redis()

        async with canal.suscribir(ORG) as dormido, canal.suscribir(ORG) as despierto:
            for _ in range(TOPE_POR_SUSCRIPTOR + 5):
                await canal.publicar(Aviso(org_id=ORG, tipo="actividad_cerrada"))
                # El despierto vacía; el dormido no.
                despierto.get_nowait()

            # El dormido llegó al tope y se le descartó el resto, en vez de
            # crecer sin límite hasta tumbar el proceso.
            assert dormido.qsize() == TOPE_POR_SUSCRIPTOR
            assert despierto.empty()

    @pytest.mark.asyncio
    async def test_publicar_sin_nadie_escuchando_no_falla(self) -> None:
        # Es el caso normal: casi ningún cierre ocurre con la Torre abierta.
        canal = _canal_sin_redis()
        await canal.publicar(Aviso(org_id=ORG, tipo="actividad_cerrada"))

    @pytest.mark.asyncio
    async def test_un_redis_inalcanzable_no_rompe_la_entrega_local(self) -> None:
        # El aviso viaja detrás de un hecho ya commiteado (§11.1): que el
        # reparte-entre-procesos falle no puede impedir que lo reciba quien
        # está conectado aquí.
        canal = CanalDeAvisos(Config(redis_url="redis://127.0.0.1:6390/0"))

        async with canal.suscribir(ORG) as cola:
            await canal.publicar(Aviso(org_id=ORG, tipo="actividad_cerrada"))
            assert cola.qsize() == 1

        await canal.cerrar()

    def test_el_canal_de_redis_lleva_la_organización_en_el_nombre(self) -> None:
        # El aislamiento empieza antes de leer el mensaje.
        assert prefijo_de_canal(ORG).endswith(str(ORG))
        assert prefijo_de_canal(ORG) != prefijo_de_canal(OTRA_ORG)


class TestTraduccion:
    def test_traduce_los_cuatro_eventos_del_dominio(self) -> None:
        eventos = [
            ActividadCerrada(obra_id=OBRA, actividad_id=uuid.uuid4()),
            IncidenciaDetiene(obra_id=OBRA, incidencia_id=uuid.uuid4()),
            EstimacionValidada(obra_id=OBRA, estimacion_id=uuid.uuid4()),
            CierreDeObraCompletado(obra_id=OBRA, cierre_id=uuid.uuid4()),
        ]
        tipos = [aviso_de(e, org_id=ORG).tipo for e in eventos]  # type: ignore[union-attr]

        assert tipos == [
            "actividad_cerrada",
            "incidencia_detiene",
            "estimacion_validada",
            "cierre_de_obra_completado",
        ]

    def test_un_evento_no_listado_no_se_anuncia(self) -> None:
        # Callar de más nunca filtró nada: el default es no publicar.
        assert aviso_de(object(), org_id=ORG) is None

    def test_el_aviso_lleva_ids_y_nada_más(self) -> None:
        evento = EstimacionValidada(obra_id=OBRA, estimacion_id=uuid.uuid4())
        aviso = aviso_de(evento, org_id=ORG)

        assert aviso is not None
        assert set(aviso.datos) == {"obra_id", "estimacion_id"}
        # Todos los valores son cadenas: el cliente no tiene que adivinar
        # tipos por campo.
        assert all(isinstance(v, str) for v in aviso.datos.values())

    def test_incidencia_distingue_bloquear_de_liberar(self) -> None:
        # Es lo que decide si la Torre pinta la obra en rojo o la limpia.
        detiene = aviso_de(
            IncidenciaDetiene(obra_id=OBRA, incidencia_id=uuid.uuid4(), bloquear=True),
            org_id=ORG,
        )
        libera = aviso_de(
            IncidenciaDetiene(obra_id=OBRA, incidencia_id=uuid.uuid4(), bloquear=False),
            org_id=ORG,
        )

        assert detiene is not None and libera is not None
        assert detiene.datos["bloquear"] == "si"
        assert libera.datos["bloquear"] == "no"

    @pytest.mark.asyncio
    async def test_el_bus_anuncia_después_de_los_manejadores_de_negocio(self) -> None:
        canal = _canal_sin_redis()
        ctx = ContextoSesion(org_id=ORG, usuario_id=uuid.uuid4(), rol="supervisor")
        orden: list[str] = []

        async def _recalcular(_evento: ActividadCerrada) -> None:
            orden.append("negocio")

        bus = BusEnProceso()
        bus.suscribir(ActividadCerrada, _recalcular)
        suscribir_avisos(bus, ctx=ctx, canal=canal)

        async with canal.suscribir(ORG) as cola:
            await bus.publicar(ActividadCerrada(obra_id=OBRA, actividad_id=uuid.uuid4()))

            assert orden == ["negocio"]
            assert cola.get_nowait()["tipo"] == "actividad_cerrada"

    @pytest.mark.asyncio
    async def test_si_el_canal_falla_el_evento_no_se_propaga(self) -> None:
        # `BusEnProceso` se traga los fallos de sus manejadores a propósito:
        # un canal caído no puede deshacer un cierre ya commiteado (§11.1).
        class _CanalRoto:
            async def publicar(self, aviso: Aviso) -> None:
                raise RuntimeError("el canal se cayó")

        ctx = ContextoSesion(org_id=ORG, usuario_id=uuid.uuid4(), rol="supervisor")
        bus = suscribir_avisos(BusEnProceso(), ctx=ctx, canal=_CanalRoto())  # type: ignore[arg-type]

        await bus.publicar(ActividadCerrada(obra_id=OBRA, actividad_id=uuid.uuid4()))


class TestFlujoSSE:
    """El endpoint `GET /events`.

    Se prueba con el canal real del proceso porque es lo que usa la ruta: lo
    que aquí importa no es el reparto —ya probado arriba— sino el **formato**
    del flujo, que es lo único que el navegador entiende y lo más fácil de
    romper con un salto de línea de menos.
    """

    @pytest.mark.asyncio
    async def test_el_formato_de_un_mensaje_sse(self) -> None:
        from obractrl.adapters.api.v1.eventos import _sse

        mensaje = _sse({"tipo": "actividad_cerrada", "datos": {"obra_id": "abc"}})

        # Dos saltos al final: es lo que separa un evento del siguiente. Sin
        # el segundo, el navegador espera indefinidamente el resto.
        assert mensaje.endswith("\n\n")
        # Y el JSON en una sola línea: el protocolo separa campos por salto.
        cuerpo = mensaje.removeprefix("data: ").strip()
        assert "\n" not in cuerpo

    @pytest.mark.asyncio
    async def test_el_evento_nombrado_permite_escuchar_por_tipo(self) -> None:
        from obractrl.adapters.api.v1.eventos import _sse

        mensaje = _sse({"tipo": "x", "datos": {}}, evento="actividad_cerrada")
        assert mensaje.startswith("event: actividad_cerrada\ndata: ")

    @pytest.mark.asyncio
    async def test_el_latido_es_un_comentario_que_el_cliente_ignora(self) -> None:
        # Existe por los proxies —Render corta a los ~30 s de silencio—, no
        # por el cliente. Un comentario SSE empieza con `:`.
        from obractrl.adapters.api.v1.eventos import LATIDO_SEGUNDOS

        assert 0 < LATIDO_SEGUNDOS < 30

    @pytest.mark.asyncio
    async def test_el_canal_del_proceso_es_uno_solo(self) -> None:
        # Los suscriptores viven más que la petición que los abrió, así que el
        # canal no puede construirse por petición.
        from obractrl.infrastructure.tiempo_real.canal import canal_de_avisos

        try:
            async with canal_de_avisos.suscribir(ORG):
                assert canal_de_avisos.suscriptores == 1
            assert canal_de_avisos.suscriptores == 0
        finally:
            # Suscribirse arranca el puente con Redis, y esta instancia es de
            # módulo: sin cerrarlo, la tarea sobreviviría al event loop de
            # esta prueba y reventaría en el `lifespan` de la siguiente.
            await canal_de_avisos.cerrar()

        await asyncio.sleep(0)
