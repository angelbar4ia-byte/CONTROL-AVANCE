"""Repositorio de desviaciones contra Postgres real (MODELO.md §5g, §12.4).

No repite `tests/domain/test_desviacion.py` (las reglas puras del dataclass
y de las nueve causas): prueba que el SQL respeta RLS, que `crear` siempre
nace con `causa = null`, que `capturar_causa` es una escritura aparte e
independiente (regla de captura 1 y 4, MODELO.md §5g) y que las consultas
de patrón agregan lo que dicen agregar.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.repos.desviaciones_sql import (
    DesviacionNoModificada,
    RepositorioDesviacionesSQL,
)
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario


@dataclass(frozen=True, slots=True)
class Catalogos:
    """Un insumo y un concepto mínimos, en la misma org del `escenario`."""

    insumo_id: uuid.UUID
    concepto_id: uuid.UUID


@pytest.fixture
async def catalogos(escenario: Escenario) -> AsyncIterator[Catalogos]:
    """Se limpia sola: cascada desde `organizacion(id) on delete cascade`."""
    engine = create_async_engine(DATABASE_URL_ADMIN)
    insumo = uuid.uuid4()
    concepto = uuid.uuid4()

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "insert into insumo (id, org_id, tipo, clave, descripcion) "
                "values (:id, :org, 'material', 'CEM-01', 'Cemento gris')"
            ),
            {"id": str(insumo), "org": str(escenario.org_id)},
        )
        await conn.execute(
            text(
                "insert into concepto (id, org_id, clave, descripcion) "
                "values (:id, :org, 'EST-001', 'Castillo de concreto')"
            ),
            {"id": str(concepto), "org": str(escenario.org_id)},
        )

    yield Catalogos(insumo_id=insumo, concepto_id=concepto)
    await engine.dispose()


async def test_crear_nace_sin_causa_y_respeta_rls(
    escenario: Escenario,
    catalogos: Catalogos,
    contexto_residente: ContextoSesion,
    contexto_ajeno: ContextoSesion,
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioDesviacionesSQL(sesion)
        desviacion_id = await repo.crear(
            {
                "obra_id": escenario.obra_id,
                "insumo_id": catalogos.insumo_id,
                "tipo": "consumo",
                "monto": Decimal("1500.00"),
                "cantidad_plan": Decimal("10"),
                "cantidad_real": Decimal("13"),
            }
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioDesviacionesSQL(sesion)
        fila = await repo.obtener(desviacion_id)

    assert fila is not None
    assert fila["obra_id"] == escenario.obra_id
    assert fila["tipo_nodo"] == "insumo"
    assert fila["insumo_id"] == catalogos.insumo_id
    assert fila["concepto_id"] is None
    assert fila["tipo"] == "consumo"
    assert fila["monto"] == Decimal("1500.00")
    assert fila["causa"] is None
    assert fila["usuario_id"] is None
    assert fila["causa_capturada_en"] is None
    assert fila["detectada_en"] is not None

    async with sesion_con_rls(contexto_ajeno) as sesion:
        repo = RepositorioDesviacionesSQL(sesion)
        fila_ajena = await repo.obtener(desviacion_id)
    assert fila_ajena is None


async def test_crear_con_concepto(
    escenario: Escenario, catalogos: Catalogos, contexto_residente: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioDesviacionesSQL(sesion)
        desviacion_id = await repo.crear(
            {
                "obra_id": escenario.obra_id,
                "concepto_id": catalogos.concepto_id,
                "tipo": "precio",
                "monto": Decimal("300.00"),
                "precio_plan": Decimal("100.00"),
                "precio_real": Decimal("130.00"),
            }
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioDesviacionesSQL(sesion)
        fila = await repo.obtener(desviacion_id)

    assert fila is not None
    assert fila["tipo_nodo"] == "concepto"
    assert fila["concepto_id"] == catalogos.concepto_id
    assert fila["insumo_id"] is None
    assert fila["tipo"] == "precio"
    assert fila["precio_plan"] == Decimal("100.00")
    assert fila["precio_real"] == Decimal("130.00")


async def test_capturar_causa_es_escritura_independiente(
    escenario: Escenario, catalogos: Catalogos, contexto_residente: ContextoSesion
) -> None:
    """Regla de captura 1 y 4 (MODELO.md §5g): la desviación existe sin
    causa, y la causa llega después, en su propia transacción, sin tocar
    `detectada_en`."""
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioDesviacionesSQL(sesion)
        desviacion_id = await repo.crear(
            {
                "obra_id": escenario.obra_id,
                "insumo_id": catalogos.insumo_id,
                "tipo": "consumo",
                "monto": Decimal("800.00"),
                "cantidad_plan": Decimal("5"),
                "cantidad_real": Decimal("7"),
            }
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioDesviacionesSQL(sesion)
        antes = await repo.obtener(desviacion_id)
    assert antes is not None
    assert antes["causa"] is None
    detectada_en_original = antes["detectada_en"]

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioDesviacionesSQL(sesion)
        await repo.capturar_causa(
            desviacion_id,
            causa="desperdicio_mayor_al_teorico",
            usuario_id=escenario.residente_id,
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioDesviacionesSQL(sesion)
        despues = await repo.obtener(desviacion_id)

    assert despues is not None
    assert despues["causa"] == "desperdicio_mayor_al_teorico"
    assert despues["usuario_id"] == escenario.residente_id
    assert despues["causa_capturada_en"] is not None
    # La captura no reescribe cuándo se detectó.
    assert despues["detectada_en"] == detectada_en_original


async def test_capturar_causa_inexistente_levanta(
    contexto_residente: ContextoSesion,
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioDesviacionesSQL(sesion)
        with pytest.raises(DesviacionNoModificada):
            await repo.capturar_causa(
                uuid.uuid4(), causa="retrabajo", usuario_id=uuid.uuid4()
            )


async def test_patrones_por_insumo_o_concepto_agrega(
    escenario: Escenario, catalogos: Catalogos, contexto_residente: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioDesviacionesSQL(sesion)
        for monto in (Decimal("100.00"), Decimal("200.00")):
            await repo.crear(
                {
                    "obra_id": escenario.obra_id,
                    "insumo_id": catalogos.insumo_id,
                    "tipo": "consumo",
                    "monto": monto,
                    "cantidad_plan": Decimal("1"),
                    "cantidad_real": Decimal("2"),
                }
            )
        await sesion.commit()

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioDesviacionesSQL(sesion)
        patrones = await repo.patrones_por_insumo_o_concepto(
            obra_id=escenario.obra_id
        )

    fila = next(p for p in patrones if p["insumo_id"] == catalogos.insumo_id)
    assert fila["n"] == 2
    assert fila["monto_total"] == Decimal("300.00")
    assert fila["obras_distintas"] == 1


async def test_patrones_por_obra_agrega(
    escenario: Escenario, catalogos: Catalogos, contexto_residente: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioDesviacionesSQL(sesion)
        await repo.crear(
            {
                "obra_id": escenario.obra_id,
                "insumo_id": catalogos.insumo_id,
                "tipo": "consumo",
                "monto": Decimal("50.00"),
                "cantidad_plan": Decimal("1"),
                "cantidad_real": Decimal("2"),
            }
        )
        await repo.crear(
            {
                "obra_id": escenario.obra_id,
                "concepto_id": catalogos.concepto_id,
                "tipo": "precio",
                "monto": Decimal("75.00"),
                "precio_plan": Decimal("10"),
                "precio_real": Decimal("20"),
            }
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioDesviacionesSQL(sesion)
        patrones = await repo.patrones_por_obra(obra_ids=[escenario.obra_id])

    assert len(patrones) == 1
    fila = patrones[0]
    assert fila["obra_id"] == escenario.obra_id
    assert fila["n"] == 2
    assert fila["monto_total"] == Decimal("125.00")
    assert fila["insumos_distintos"] == 1
    assert fila["conceptos_distintos"] == 1
