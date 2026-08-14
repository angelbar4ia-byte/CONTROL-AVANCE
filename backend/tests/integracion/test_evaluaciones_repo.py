"""Repositorio de evaluaciones contra Postgres real (§7.8, §12.4).

Igual que `test_cierres_repo.py`: no repite `tests/domain/test_evaluaciones.py`
(las reglas puras), sino que prueba que el SQL respeta RLS y que el catálogo
de criterios / el puntaje van y vuelven sin sorpresas.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.repos.evaluaciones_sql import (
    EvaluacionNoModificada,
    RepositorioEvaluacionesSQL,
)
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario


@pytest.fixture
async def criterio_id(escenario: Escenario) -> uuid.UUID:
    """Un criterio del catálogo `residente`, peso 2 (§7.8, §8.7 semilla)."""
    engine = create_async_engine(DATABASE_URL_ADMIN)
    crit_id = uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "insert into criterio_evaluacion (id, org_id, aplica_a, clave, nombre, peso) "
                "values (:id, :org, 'residente', 'PUNTUALIDAD', 'Puntualidad', 2)"
            ),
            {"id": str(crit_id), "org": str(escenario.org_id)},
        )
    await engine.dispose()
    return crit_id


async def test_crear_y_obtener_respetan_rls(
    escenario: Escenario, contexto_residente: ContextoSesion, contexto_ajeno: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioEvaluacionesSQL(sesion)
        evaluacion_id = await repo.crear(
            sujeto_tipo="residente",
            sujeto_id=escenario.residente_id,
            evaluador_id=escenario.residente_id,
            nivel="auto",
            periodo="2026-07",
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioEvaluacionesSQL(sesion)
        fila = await repo.obtener(evaluacion_id)

    assert fila is not None
    assert fila["sujeto_tipo"] == "residente"
    assert fila["nivel"] == "auto"
    assert fila["puntaje"] is None

    async with sesion_con_rls(contexto_ajeno) as sesion:
        repo = RepositorioEvaluacionesSQL(sesion)
        fila_ajena = await repo.obtener(evaluacion_id)
    assert fila_ajena is None


async def test_listar_filtra_por_nivel_y_sujeto(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioEvaluacionesSQL(sesion)
        await repo.crear(
            sujeto_tipo="residente",
            sujeto_id=escenario.residente_id,
            evaluador_id=escenario.residente_id,
            nivel="auto",
            periodo="2026-07",
        )
        await repo.crear(
            sujeto_tipo="obra",
            sujeto_id=escenario.obra_id,
            evaluador_id=escenario.residente_id,
            nivel="auto",
            periodo="2026-07",
            obra_id=escenario.obra_id,
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioEvaluacionesSQL(sesion)
        todas = await repo.listar()
        residentes = await repo.listar(sujeto_tipo="residente")
        obras = await repo.listar(sujeto_tipo="obra")
        controles = await repo.listar(nivel="control")

    assert len(todas) == 2
    assert len(residentes) == 1
    assert len(obras) == 1
    assert controles == []


async def test_agregar_respuestas_calcula_puntaje(
    escenario: Escenario,
    contexto_residente: ContextoSesion,
    criterio_id: uuid.UUID,
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioEvaluacionesSQL(sesion)
        evaluacion_id = await repo.crear(
            sujeto_tipo="residente",
            sujeto_id=escenario.residente_id,
            evaluador_id=escenario.residente_id,
            nivel="auto",
            periodo="2026-07",
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioEvaluacionesSQL(sesion)
        pesos = await repo.pesos_de_criterios([criterio_id])
        assert pesos == {criterio_id: Decimal("2")}

        await repo.agregar_respuestas(
            evaluacion_id,
            respuestas=[
                {"criterio_id": criterio_id, "valor": Decimal("9"), "comentario": "Ok"}
            ],
            puntaje=Decimal("9"),
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioEvaluacionesSQL(sesion)
        fila = await repo.obtener(evaluacion_id)
        respuestas = await repo.respuestas_de(evaluacion_id)

    assert fila is not None
    assert fila["puntaje"] == Decimal("9")
    assert len(respuestas) == 1
    assert respuestas[0]["criterio_id"] == criterio_id
    assert respuestas[0]["valor"] == Decimal("9")
    assert respuestas[0]["comentario"] == "Ok"


async def test_actualizar_puntaje_inexistente_levanta(
    contexto_residente: ContextoSesion,
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioEvaluacionesSQL(sesion)
        with pytest.raises(EvaluacionNoModificada):
            await repo.agregar_respuestas(uuid.uuid4(), respuestas=[], puntaje=Decimal("5"))


async def test_listar_criterios_filtra_por_aplica_a(
    contexto_residente: ContextoSesion, criterio_id: uuid.UUID
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioEvaluacionesSQL(sesion)
        residentes = await repo.listar_criterios(aplica_a="residente")
        obras = await repo.listar_criterios(aplica_a="obra")

    assert len(residentes) == 1
    assert residentes[0]["id"] == criterio_id
    assert obras == []
