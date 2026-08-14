"""Repositorio de incidencias contra Postgres real (§7.8, §12.4).

Igual que `test_cierres_repo.py`: no repite `tests/domain/test_incidencias.py`
(las reglas puras), sino que prueba que el SQL respeta RLS, que
`incidencia_evento` queda enlazada a su incidencia padre (política
`incidencia_evento_scope`) y que el jsonb de `evidencias`/
`bloquea_actividades` va y vuelve sin sorpresas.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.repos.incidencias_sql import (
    IncidenciaNoModificada,
    RepositorioIncidenciasSQL,
)
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario

EVIDENCIAS = ["r2://evidencias/incidencia-1.jpg"]


async def test_crear_y_obtener_respetan_rls(
    escenario: Escenario, contexto_residente: ContextoSesion, contexto_ajeno: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioIncidenciasSQL(sesion)
        incidencia_id = await repo.crear(
            obra_id=escenario.obra_id,
            creada_por=escenario.residente_id,
            tipo="falta_material",
            impacto="detalle",
            titulo="Falta cemento",
            descripcion="No llegó el pedido",
            evidencias=EVIDENCIAS,
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioIncidenciasSQL(sesion)
        fila = await repo.obtener(incidencia_id)

    assert fila is not None
    assert fila["obra_id"] == escenario.obra_id
    assert fila["tipo"] == "falta_material"
    assert fila["impacto"] == "detalle"
    assert fila["titulo"] == "Falta cemento"
    assert fila["evidencias"] == EVIDENCIAS
    assert fila["bloquea_actividades"] == []
    assert fila["estatus"] == "abierta"

    async with sesion_con_rls(contexto_ajeno) as sesion:
        repo = RepositorioIncidenciasSQL(sesion)
        fila_ajena = await repo.obtener(incidencia_id)
    assert fila_ajena is None


async def test_crear_con_impacto_detiene_persiste_bloqueadas(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioIncidenciasSQL(sesion)
        incidencia_id = await repo.crear(
            obra_id=escenario.obra_id,
            creada_por=escenario.residente_id,
            tipo="error_ejecucion",
            impacto="detiene",
            titulo="Falla estructural",
            bloquea_actividades=[str(escenario.actividad_id)],
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioIncidenciasSQL(sesion)
        fila = await repo.obtener(incidencia_id)

    assert fila is not None
    assert fila["bloquea_actividades"] == [str(escenario.actividad_id)]


async def test_actualizar_fija_estatus_y_asignacion(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioIncidenciasSQL(sesion)
        incidencia_id = await repo.crear(
            obra_id=escenario.obra_id,
            creada_por=escenario.residente_id,
            tipo="retrabajo",
            impacto="retraso",
            titulo="Retrabajo de losa",
        )
        await repo.actualizar(
            incidencia_id, estatus="programada", asignada_a=escenario.supervisor_id
        )
        await sesion.commit()

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        fila = (
            await conn.execute(
                text("select estatus, asignada_a from incidencia where id = :id"),
                {"id": str(incidencia_id)},
            )
        ).first()
    await admin.dispose()

    assert fila is not None
    assert fila.estatus == "programada"
    assert fila.asignada_a == escenario.supervisor_id


async def test_actualizar_inexistente_levanta(
    contexto_residente: ContextoSesion,
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioIncidenciasSQL(sesion)
        with pytest.raises(IncidenciaNoModificada):
            await repo.actualizar(uuid.uuid4(), estatus="programada")


async def test_registrar_evento_queda_ligado_a_la_incidencia(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioIncidenciasSQL(sesion)
        incidencia_id = await repo.crear(
            obra_id=escenario.obra_id,
            creada_por=escenario.residente_id,
            tipo="detalle",
            impacto="detalle",
            titulo="Detalle menor",
        )
        await repo.registrar_evento(
            incidencia_id,
            usuario_id=escenario.residente_id,
            accion="comentar",
            estatus_previo="abierta",
            estatus_nuevo="abierta",
            comentario="Se revisó en sitio",
        )
        await sesion.commit()

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        fila = (
            await conn.execute(
                text(
                    "select incidencia_id, accion, comentario "
                    "from incidencia_evento where incidencia_id = :id"
                ),
                {"id": str(incidencia_id)},
            )
        ).first()
    await admin.dispose()

    assert fila is not None
    assert fila.incidencia_id == incidencia_id
    assert fila.accion == "comentar"
    assert fila.comentario == "Se revisó en sitio"


async def test_listar_filtra_por_estatus(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioIncidenciasSQL(sesion)
        await repo.crear(
            obra_id=escenario.obra_id,
            creada_por=escenario.residente_id,
            tipo="cambio_cliente",
            impacto="retraso",
            titulo="Cambio de acabados",
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioIncidenciasSQL(sesion)
        todas = await repo.listar()
        abiertas = await repo.listar(estatus="abierta")
        cerradas = await repo.listar(estatus="cerrada")

    assert len(todas) == 1
    assert len(abiertas) == 1
    assert cerradas == []
