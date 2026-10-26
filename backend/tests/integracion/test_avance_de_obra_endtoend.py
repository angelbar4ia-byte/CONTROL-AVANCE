"""Paridad: lo que calcula la base (migración 0064) es lo que dice el dominio.

La regla del avance de la obra se define en `domain.obras.avance` y
`Obra.sincronizar_avance`, y la base la repite en `app.obra_recalcular_avance`
porque el móvil escribe directo a Postgres (decisión D5). Dos implementaciones
de una misma regla se separan tarde o temprano; esta prueba es lo que las
mantiene juntas: arma obras con importes y avances variados, deja que el
trigger calcule, y compara contra el dominio — avance **y** estatus.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.application.casos_uso.generar_obra_desde_prototipo import reconstruir_obra
from obractrl.domain.obras.avance import ActividadParaAvance, avance_de_obra
from obractrl.domain.shared.valores import Avance
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario


@dataclass(frozen=True)
class Caso:
    nombre: str
    # (cant_base, precio_unitario, cant_ejecutada)
    actividades: tuple[tuple[str, str, str], ...]


CASOS = [
    Caso(
        "ponderado: el muro grande en cero y el castillo terminado",
        (("100", "1220", "0"), ("10", "1000", "10")),
    ),
    Caso("todo concluido", (("10", "50", "10"), ("30", "20", "30"))),
    Caso(
        "pesos distintos, avances a medias",
        (("40", "75", "10"), ("25", "310", "25"), ("5", "9", "1")),
    ),
    Caso(
        "sin precios: promedio simple",
        (("10", "0", "10"), ("10", "0", "5"), ("10", "0", "0")),
    ),
    Caso("una sola actividad al 89 %", (("100", "10", "89"),)),
    Caso("una sola actividad al 90 %", (("100", "10", "90"),)),
    Caso(
        "empate de redondeo: 0.005 sube a 0.01 en los dos lados",
        (("1", "1", "0.0001"), ("1", "1", "0")),
    ),
    Caso("sin avance", (("10", "10", "0"), ("20", "10", "0"))),
]


async def _armar(escenario: Escenario, caso: Caso) -> uuid.UUID:
    """Una obra nueva en la organización del escenario con las actividades del
    caso. Engine admin: aquí se prepara el fixture, no se prueba aislamiento."""
    engine = create_async_engine(DATABASE_URL_ADMIN)
    obra_id = uuid.uuid4()
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "insert into obra (id, org_id, cluster_id, prototipo_id, clave, residente_id) "
                    "values (:id, :org, :cluster, :proto, :clave, :res)"
                ),
                {
                    "id": str(obra_id),
                    "org": str(escenario.org_id),
                    "cluster": str(escenario.cluster_id),
                    "proto": str(escenario.prototipo_id),
                    "clave": f"PAR-{obra_id.hex[:6]}",
                    "res": str(escenario.residente_id),
                },
            )
            for base, precio, ejecutada in caso.actividades:
                await conn.execute(
                    text(
                        "insert into actividad "
                        "(org_id, obra_id, cant_base, cant_programada, precio_unitario, cant_ejecutada) "
                        "values (:org, :obra, :base, :base, :precio, :ejecutada)"
                    ),
                    {
                        "org": str(escenario.org_id),
                        "obra": str(obra_id),
                        "base": base,
                        "precio": precio,
                        "ejecutada": ejecutada,
                    },
                )
    finally:
        await engine.dispose()
    return obra_id


async def _leer_obra(obra_id: uuid.UUID) -> dict:
    engine = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with engine.connect() as conn:
            fila = (
                (
                    await conn.execute(
                        text(
                            "select cluster_id, clave, prototipo_id, residente_id, estatus, "
                            "fecha_inicio, fecha_fin, avance_pct, m2, es_urba from obra where id = :id"
                        ),
                        {"id": str(obra_id)},
                    )
                )
                .mappings()
                .one()
            )
            return dict(fila)
    finally:
        await engine.dispose()


@pytest.mark.parametrize("caso", CASOS, ids=[c.nombre for c in CASOS])
async def test_la_base_calcula_lo_que_dice_el_dominio(
    escenario: Escenario, caso: Caso
) -> None:
    obra_id = await _armar(escenario, caso)
    en_base = await _leer_obra(obra_id)

    esperado = avance_de_obra(
        [
            ActividadParaAvance(
                importe=Decimal(base) * Decimal(precio),
                avance=Avance.de_cantidades(Decimal(ejecutada), Decimal(base)),
            )
            for base, precio, ejecutada in caso.actividades
        ]
    )
    assert Decimal(str(en_base["avance_pct"])) == esperado.pct

    # El estatus: la obra nace `pendiente` y el dominio la mueve igual que el
    # trigger (>= 90 por_entregar, > 0 en_proceso, 0 pendiente).
    obra = reconstruir_obra({**en_base, "estatus": "pendiente", "avance_pct": 0})
    obra.sincronizar_avance(esperado)
    assert en_base["estatus"] == obra.estatus.value
