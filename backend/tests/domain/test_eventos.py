"""Bus de eventos de dominio (§11.1).

Vive en `application/eventos.py` y no en `domain/`, pero se prueba aquí porque
es puro —sin BD ni framework— igual que el resto de esta carpeta. Lo que se
verifica es el contrato del §11.1: quien publica no sabe quién escucha, y un
manejador que falla **no** puede tumbar al publicador (el cierre ya está
commiteado cuando el evento sale).
"""

from __future__ import annotations

import uuid

import pytest

from obractrl.application.eventos import (
    ActividadCerrada,
    BusEnProceso,
    EstimacionValidada,
    PublicadorEventos,
)


def _evento() -> ActividadCerrada:
    return ActividadCerrada(obra_id=uuid.uuid4(), actividad_id=uuid.uuid4())


async def test_entrega_el_evento_a_sus_suscriptores() -> None:
    bus = BusEnProceso()
    recibidos: list[ActividadCerrada] = []

    async def _manejar(evento: ActividadCerrada) -> None:
        recibidos.append(evento)

    bus.suscribir(ActividadCerrada, _manejar)
    evento = _evento()
    await bus.publicar(evento)

    assert recibidos == [evento]


async def test_no_entrega_eventos_de_otro_tipo() -> None:
    bus = BusEnProceso()
    recibidos: list[object] = []

    async def _manejar(evento: object) -> None:
        recibidos.append(evento)

    bus.suscribir(ActividadCerrada, _manejar)
    await bus.publicar(
        EstimacionValidada(obra_id=uuid.uuid4(), estimacion_id=uuid.uuid4())
    )

    assert recibidos == []


async def test_un_evento_sin_suscriptores_no_revienta() -> None:
    await BusEnProceso().publicar(_evento())


async def test_el_fallo_de_un_manejador_no_sube_al_publicador(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """El publicador ya commiteó lo suyo: un recálculo de CPM que truena no
    puede deshacer un cierre válido (§11.1)."""
    bus = BusEnProceso()
    corridos: list[str] = []

    async def _truena(evento: ActividadCerrada) -> None:
        corridos.append("truena")
        raise RuntimeError("el motor CPM falló")

    async def _sigue(evento: ActividadCerrada) -> None:
        corridos.append("sigue")

    bus.suscribir(ActividadCerrada, _truena)
    bus.suscribir(ActividadCerrada, _sigue)

    await bus.publicar(_evento())

    # El segundo manejador corre igual: un suscriptor caído no ciega al resto.
    assert corridos == ["truena", "sigue"]
    assert "el motor CPM falló" in caplog.text


def test_el_bus_cumple_el_puerto_de_publicacion() -> None:
    assert isinstance(BusEnProceso(), PublicadorEventos)
