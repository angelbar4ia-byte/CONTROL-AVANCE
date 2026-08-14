"""Repositorio de solicitudes de cierre contra Postgres real (§7.8, §12.4).

Igual que `test_actividades_repo.py`: no repite `tests/domain/test_cierres.py`
(las reglas puras), sino que prueba que el SQL respeta RLS y que el jsonb de
`checklist`/`adjuntos` va y vuelve sin sorpresas.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.repos.cierres_sql import (
    RepositorioCierresSQL,
    SolicitudCierreNoModificada,
)
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario

CHECKLIST = [{"item": "Nivelación", "ok": True}]
ADJUNTOS = ["r2://evidencias/foto-1.jpg"]


async def test_crear_y_obtener_respetan_rls(
    escenario: Escenario, contexto_residente: ContextoSesion, contexto_ajeno: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioCierresSQL(sesion)
        cierre_id = await repo.crear(
            actividad_id=escenario.actividad_id,
            solicitada_por=escenario.residente_id,
            cantidad=Decimal("10"),
            monto=Decimal("2500"),
            checklist=CHECKLIST,
            adjuntos=ADJUNTOS,
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioCierresSQL(sesion)
        fila = await repo.obtener(cierre_id)

    assert fila is not None
    assert fila["actividad_id"] == escenario.actividad_id
    assert fila["cantidad"] == Decimal("10")
    assert fila["monto"] == Decimal("2500")
    assert fila["checklist"] == CHECKLIST
    assert fila["adjuntos"] == ADJUNTOS
    assert fila["estatus"] == "solicitada"

    async with sesion_con_rls(contexto_ajeno) as sesion:
        repo = RepositorioCierresSQL(sesion)
        fila_ajena = await repo.obtener(cierre_id)
    assert fila_ajena is None


async def test_actualizar_fija_fecha_autoriza_y_valida(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioCierresSQL(sesion)
        cierre_id = await repo.crear(
            actividad_id=escenario.actividad_id,
            solicitada_por=escenario.residente_id,
            cantidad=Decimal("10"),
            monto=Decimal("2500"),
            checklist=CHECKLIST,
            adjuntos=ADJUNTOS,
        )
        await repo.actualizar(
            cierre_id, estatus="autorizada", autorizada_por=escenario.supervisor_id
        )
        await sesion.commit()

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        fila = (
            await conn.execute(
                text(
                    "select estatus, autorizada_por, fecha_autoriza "
                    "from solicitud_cierre where id = :id"
                ),
                {"id": str(cierre_id)},
            )
        ).first()
    await admin.dispose()

    assert fila is not None
    assert fila.estatus == "autorizada"
    assert fila.autorizada_por == escenario.supervisor_id
    assert fila.fecha_autoriza is not None


async def test_actualizar_inexistente_levanta(
    contexto_residente: ContextoSesion,
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioCierresSQL(sesion)
        with pytest.raises(SolicitudCierreNoModificada):
            await repo.actualizar(uuid.uuid4(), estatus="autorizada")


async def test_listar_filtra_por_estatus(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioCierresSQL(sesion)
        await repo.crear(
            actividad_id=escenario.actividad_id,
            solicitada_por=escenario.residente_id,
            cantidad=Decimal("10"),
            monto=Decimal("2500"),
            checklist=CHECKLIST,
            adjuntos=ADJUNTOS,
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioCierresSQL(sesion)
        todas = await repo.listar()
        solicitadas = await repo.listar(estatus="solicitada")
        validadas = await repo.listar(estatus="validada")

    assert len(todas) == 1
    assert len(solicitadas) == 1
    assert validadas == []
