"""La ventana de cada actividad sale del CPM, no de la fila (§7.5, §7.6, §8.3).

Esto protege un fallo real que dejó a dos módulos enseñando tablas vacías sobre
obras que sí tenían programa.

`guardar_resultado_cpm` **no persiste** las fechas tempranas y tardías: son
puras y baratas de recalcular, así que `actividad.fecha_inicio` guarda lo que
alguien **capturó a mano** y está vacío en una obra recién programada. Los
insumos programados y la planeación por frente leían esa columna, así que una
obra con 113 actividades calendarizadas por el motor salía entera en
`sin_programar` y ni el material ni las cuadrillas decían nada.

Las tres decisiones que se fijan:

 1. **Sin fecha capturada manda el CPM.** Es el caso normal: el residente corre
    el programa y no toca fechas una por una.
 2. **Una fecha capturada le gana a la calculada.** Fijarla a mano es una
    decisión y el motor no la debe pisar.
 3. **Sin obra concreta no se recalcula.** La ruta se pide obra por obra; en una
    consulta por residente o por supervisor —que barre varias— hacerlo aquí
    multiplicaría el trabajo por el número de obras del alcance.

Sin BD: la ruta crítica se sustituye por un doble, porque lo que se prueba es de
dónde sale la ventana, no el SQL.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from obractrl.application.casos_uso.consultar_insumos_programados import (
    ConsultarInsumosProgramados,
)
from obractrl.domain.insumos.programado import ActividadConVentana

OBRA = uuid.uuid4()
CALCULADO_INICIO = date(2026, 5, 11)
CALCULADO_FIN = date(2026, 5, 21)


@dataclass(frozen=True)
class _ActividadDeRuta:
    actividad_id: str
    inicio_temprano: date
    fin_temprano: date


@dataclass(frozen=True)
class _Ruta:
    actividades: tuple[_ActividadDeRuta, ...]


class _RutaCriticaFalsa:
    """Doble de `ConsultarRutaCritica`: solo cuenta cuántas veces se pide."""

    def __init__(self) -> None:
        self.llamadas: list[uuid.UUID] = []

    async def ejecutar(self, obra_id: uuid.UUID) -> _Ruta:
        self.llamadas.append(obra_id)
        return _Ruta(
            actividades=(
                _ActividadDeRuta("act-1", CALCULADO_INICIO, CALCULADO_FIN),
            )
        )


def _caso(ruta: _RutaCriticaFalsa | None) -> ConsultarInsumosProgramados:
    """El caso de uso con todo en `None` salvo la ruta.

    `con_ventana_del_cpm` no toca ningún otro repositorio; pasarle dobles de los
    nueve solo escondería de qué depende de verdad.
    """
    return ConsultarInsumosProgramados(
        actividades=None,
        conceptos=None,
        insumos=None,
        unidades=None,
        calendario=None,
        obras=None,
        presupuestos=None,
        materiales=None,
        nodos=None,
        ruta=ruta,
    )


def _actividad(
    *, inicio: date | None = None, fin: date | None = None, actividad_id: str = "act-1"
) -> ActividadConVentana:
    return ActividadConVentana(
        actividad_id=actividad_id,
        obra_id=str(OBRA),
        concepto_clave="MURO",
        descripcion="Muro de tabique",
        cantidad=Decimal(10),
        inicio=inicio,
        fin=fin,
    )


@pytest.mark.asyncio
async def test_sin_fecha_capturada_manda_el_cpm() -> None:
    """El caso normal: se corre el programa y nadie captura fecha por fecha.

    Sin esto la actividad sale en `sin_programar` y la obra entera se ve vacía
    aunque su cronograma esté completo.
    """
    resultado = await _caso(_RutaCriticaFalsa()).con_ventana_del_cpm(
        OBRA, [_actividad()]
    )
    assert resultado[0].inicio == CALCULADO_INICIO
    assert resultado[0].fin == CALCULADO_FIN


@pytest.mark.asyncio
async def test_una_fecha_capturada_le_gana_a_la_calculada() -> None:
    """Fijarla a mano es una decisión; el motor no la pisa (§7.6)."""
    a_mano = date(2026, 6, 1)
    resultado = await _caso(_RutaCriticaFalsa()).con_ventana_del_cpm(
        OBRA, [_actividad(inicio=a_mano)]
    )
    assert resultado[0].inicio == a_mano
    # El fin, que nadie capturó, sí lo pone el CPM: se completa lo que falta sin
    # tocar lo que se decidió.
    assert resultado[0].fin == CALCULADO_FIN


@pytest.mark.asyncio
async def test_una_actividad_que_la_ruta_no_conoce_se_queda_como_esta() -> None:
    """Extra-catálogo o fuera del cronograma vigente: no se inventa ventana."""
    resultado = await _caso(_RutaCriticaFalsa()).con_ventana_del_cpm(
        OBRA, [_actividad(actividad_id="act-fantasma")]
    )
    assert resultado[0].inicio is None
    assert resultado[0].fin is None


@pytest.mark.asyncio
async def test_sin_obra_concreta_no_se_pide_la_ruta() -> None:
    """Una consulta por residente barre varias obras.

    La ruta se calcula obra por obra: pedirla aquí multiplicaría el trabajo por
    el número de obras del alcance, y esa consulta ya es la más pesada del
    módulo.
    """
    ruta = _RutaCriticaFalsa()
    resultado = await _caso(ruta).con_ventana_del_cpm(None, [_actividad()])
    assert ruta.llamadas == []
    assert resultado[0].inicio is None


@pytest.mark.asyncio
async def test_sin_ruta_inyectada_no_falla() -> None:
    """El parámetro es opcional: un caso de uso armado a mano sigue corriendo,
    con lo que las actividades traigan capturado."""
    resultado = await _caso(None).con_ventana_del_cpm(OBRA, [_actividad()])
    assert resultado[0].inicio is None
