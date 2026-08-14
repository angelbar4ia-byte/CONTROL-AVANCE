"""Repositorio de estimaciones contra Postgres real: agregar conceptos,
actualizar estatus y listar (§7.6, §11.3 E, §12.4).

`test_estimaciones_repo.py` ya cubre `ultimo_consecutivo`, `crear` y
`actividades_estimables`; esto cubre lo que se agregó para el flujo E.2-E.4:
`agregar_conceptos`, `obtener`, `actualizar_estatus` y `listar`.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.repos.estimaciones_sql import (
    EstimacionNoModificada,
    RepositorioEstimacionesSQL,
)
from obractrl.domain.shared.folio import Folio
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario


async def _crear_estimacion(
    repo: RepositorioEstimacionesSQL, escenario: Escenario, *, semana: int = 15
) -> uuid.UUID:
    folio = str(Folio(semana=semana, anio=2026, consecutivo=1))
    return await repo.crear(
        {
            "obra_id": escenario.obra_id,
            "folio": folio,
            "semana": semana,
            "anio": 2026,
            "modo": "destajo",
            "creada_por": escenario.residente_id,
            "monto_total": Decimal("1200"),
        }
    )


async def test_agregar_conceptos_y_obtener(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioEstimacionesSQL(sesion)
        estimacion_id = await _crear_estimacion(repo, escenario)
        await repo.agregar_conceptos(
            estimacion_id,
            [
                {
                    "actividad_id": escenario.actividad_id,
                    "concepto_id": None,
                    "cantidad_validada": Decimal("10"),
                    "precio_unitario": Decimal("120"),
                    "importe": Decimal("1200"),
                }
            ],
        )
        await sesion.commit()

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        fila = (
            await conn.execute(
                text(
                    "select actividad_id, cantidad_validada, importe, fuera_catalogo "
                    "from estimacion_concepto where estimacion_id = :id"
                ),
                {"id": str(estimacion_id)},
            )
        ).first()
    await admin.dispose()

    assert fila is not None
    assert fila.actividad_id == escenario.actividad_id
    assert fila.cantidad_validada == Decimal("10")
    assert fila.importe == Decimal("1200")
    assert fila.fuera_catalogo is True

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioEstimacionesSQL(sesion)
        cabecera = await repo.obtener(estimacion_id)

    assert cabecera is not None
    assert cabecera["estatus"] == "borrador"
    assert cabecera["monto_total"] == Decimal("1200.0000")


async def test_agregar_conceptos_vacio_es_no_op(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioEstimacionesSQL(sesion)
        estimacion_id = await _crear_estimacion(repo, escenario)
        await repo.agregar_conceptos(estimacion_id, [])
        await sesion.commit()


async def test_actualizar_estatus_persiste_validada_por(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioEstimacionesSQL(sesion)
        estimacion_id = await _crear_estimacion(repo, escenario)
        await repo.actualizar_estatus(estimacion_id, estatus="enviada")
        await repo.actualizar_estatus(
            estimacion_id, estatus="validada", validada_por=escenario.control_id
        )
        await sesion.commit()

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        fila = (
            await conn.execute(
                text("select estatus, validada_por from estimacion where id = :id"),
                {"id": str(estimacion_id)},
            )
        ).first()
    await admin.dispose()

    assert fila is not None
    assert fila.estatus == "validada"
    assert fila.validada_por == escenario.control_id


async def test_actualizar_estatus_inexistente_levanta(
    contexto_residente: ContextoSesion,
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioEstimacionesSQL(sesion)
        with pytest.raises(EstimacionNoModificada):
            await repo.actualizar_estatus(uuid.uuid4(), estatus="enviada")


async def test_listar_ordena_por_semana_descendente(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioEstimacionesSQL(sesion)
        await _crear_estimacion(repo, escenario, semana=10)
        await _crear_estimacion(repo, escenario, semana=20)
        await sesion.commit()

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioEstimacionesSQL(sesion)
        estimaciones = await repo.listar(escenario.obra_id)

    assert [e["semana"] for e in estimaciones] == [20, 10]


async def test_listar_no_ve_estimaciones_de_otra_org(
    escenario: Escenario,
    contexto_residente: ContextoSesion,
    contexto_ajeno: ContextoSesion,
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioEstimacionesSQL(sesion)
        await _crear_estimacion(repo, escenario)
        await sesion.commit()

    async with sesion_con_rls(contexto_ajeno) as sesion:
        repo = RepositorioEstimacionesSQL(sesion)
        estimaciones = await repo.listar(escenario.obra_id)

    assert estimaciones == []
