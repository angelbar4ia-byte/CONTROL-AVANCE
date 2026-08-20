"""Flujo de incidencias de punta a punta: casos de uso + repos + Postgres real.

Spec §11.3 workflow F · §6 · §12.11 (Definition of Done).

`tests/domain/test_incidencias.py` prueba las reglas puras; esto prueba que
los cinco casos de uso —cableados exactamente como en
`adapters/api/casos_uso.py`— las aplican contra la base real: la incidencia
queda escrita, su bitácora en `incidencia_evento` registra cada paso, las
actividades se bloquean al abrir (impacto `detiene`) y se desbloquean al
cerrar, y RLS filtra cada paso.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.repos.actividades_sql import RepositorioActividadesSQL
from obractrl.adapters.repos.incidencias_sql import RepositorioIncidenciasSQL
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL
from obractrl.application.casos_uso.gestionar_incidencia import (
    AbrirIncidencia,
    CerrarIncidencia,
    ComandoAbrirIncidencia,
    ComandoCerrarIncidencia,
    ComandoProgramarIncidencia,
    ComandoRechazarIncidencia,
    ComandoRegistrarEventoIncidencia,
    ErrorDeIncidencia,
    IncidenciaNoEncontrada,
    ProgramarIncidencia,
    RechazarIncidencia,
    RegistrarEventoIncidencia,
)
from obractrl.domain.shared.diccionario import (
    EstatusIncidencia,
    ImpactoIncidencia,
    Rol,
    TipoIncidencia,
)
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario


async def _abrir(
    ctx: ContextoSesion,
    escenario: Escenario,
    *,
    impacto: ImpactoIncidencia = ImpactoIncidencia.DETALLE,
    bloquea_actividades: list[uuid.UUID] | None = None,
) -> uuid.UUID:
    async with sesion_con_rls(ctx) as sesion:
        caso_uso = AbrirIncidencia(
            actividades=RepositorioActividadesSQL(sesion),
            incidencias=RepositorioIncidenciasSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
        )
        creada = await caso_uso.ejecutar(
            ComandoAbrirIncidencia(
                obra_id=escenario.obra_id,
                creada_por=escenario.residente_id,
                tipo=TipoIncidencia.FALTA_MATERIAL,
                impacto=impacto,
                titulo="Falta cemento",
                bloquea_actividades=bloquea_actividades or [],
            )
        )
        return creada.id


async def _programar(
    ctx: ContextoSesion, incidencia_id: uuid.UUID, usuario_id: uuid.UUID
) -> None:
    async with sesion_con_rls(ctx) as sesion:
        caso_uso = ProgramarIncidencia(
            incidencias=RepositorioIncidenciasSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        )
        await caso_uso.ejecutar(
            ComandoProgramarIncidencia(
                incidencia_id=incidencia_id,
                usuario_id=usuario_id,
                rol=Rol.SUPERVISOR,
                asignada_a=usuario_id,
            )
        )


async def _atender(
    ctx: ContextoSesion, incidencia_id: uuid.UUID, usuario_id: uuid.UUID
) -> None:
    async with sesion_con_rls(ctx) as sesion:
        caso_uso = RegistrarEventoIncidencia(
            incidencias=RepositorioIncidenciasSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        )
        await caso_uso.ejecutar(
            ComandoRegistrarEventoIncidencia(
                incidencia_id=incidencia_id,
                usuario_id=usuario_id,
                accion="atender",
                estatus_nuevo=EstatusIncidencia.EN_ATENCION,
            )
        )


async def _solicitar_cierre(
    ctx: ContextoSesion, incidencia_id: uuid.UUID, usuario_id: uuid.UUID
) -> None:
    async with sesion_con_rls(ctx) as sesion:
        caso_uso = RegistrarEventoIncidencia(
            incidencias=RepositorioIncidenciasSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        )
        await caso_uso.ejecutar(
            ComandoRegistrarEventoIncidencia(
                incidencia_id=incidencia_id,
                usuario_id=usuario_id,
                accion="solicitar_cierre",
                estatus_nuevo=EstatusIncidencia.CIERRE_SOLICITADO,
                comentario="Listo para cerrar",
            )
        )


async def _cerrar(
    ctx: ContextoSesion, incidencia_id: uuid.UUID, usuario_id: uuid.UUID
) -> None:
    async with sesion_con_rls(ctx) as sesion:
        caso_uso = CerrarIncidencia(
            actividades=RepositorioActividadesSQL(sesion),
            incidencias=RepositorioIncidenciasSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
        )
        await caso_uso.ejecutar(
            ComandoCerrarIncidencia(
                incidencia_id=incidencia_id, usuario_id=usuario_id, rol=Rol.SUPERVISOR
            )
        )


async def test_flujo_completo_deja_la_incidencia_cerrada(
    escenario: Escenario,
    contexto_residente: ContextoSesion,
    contexto_supervisor: ContextoSesion,
) -> None:
    incidencia_id = await _abrir(contexto_residente, escenario)
    await _programar(contexto_supervisor, incidencia_id, escenario.supervisor_id)
    await _atender(contexto_supervisor, incidencia_id, escenario.supervisor_id)
    await _solicitar_cierre(contexto_supervisor, incidencia_id, escenario.supervisor_id)
    await _cerrar(contexto_supervisor, incidencia_id, escenario.supervisor_id)

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        incidencia = (
            await conn.execute(
                text("select estatus, asignada_a from incidencia where id = :id"),
                {"id": str(incidencia_id)},
            )
        ).first()
        eventos = (
            await conn.execute(
                text(
                    "select accion, estatus_previo, estatus_nuevo "
                    # `orden`, no `fecha`: dos eventos del mismo tick comparten `fecha` y
                    # el orden queda a criterio de Postgres. Es lo que hacía
                    # que esta prueba fallara una de cada tantas (migración 0027).
                    "from incidencia_evento where incidencia_id = :id order by orden"
                ),
                {"id": str(incidencia_id)},
            )
        ).all()
    await admin.dispose()

    assert incidencia is not None
    assert incidencia.estatus == "cerrada"
    assert incidencia.asignada_a == escenario.supervisor_id
    assert [e.accion for e in eventos] == ["programar", "atender", "solicitar_cierre", "cerrar"]
    assert eventos[0].estatus_previo == "abierta"
    assert eventos[-1].estatus_nuevo == "cerrada"


async def test_abrir_con_impacto_detiene_bloquea_la_actividad(
    escenario: Escenario, contexto_residente: ContextoSesion, contexto_supervisor: ContextoSesion
) -> None:
    incidencia_id = await _abrir(
        contexto_residente,
        escenario,
        impacto=ImpactoIncidencia.DETIENE,
        bloquea_actividades=[escenario.actividad_id],
    )

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        actividad = (
            await conn.execute(
                text("select bloqueada from actividad where id = :id"),
                {"id": str(escenario.actividad_id)},
            )
        ).first()
    assert actividad.bloqueada is True

    await _programar(contexto_supervisor, incidencia_id, escenario.supervisor_id)
    await _atender(contexto_supervisor, incidencia_id, escenario.supervisor_id)
    await _solicitar_cierre(contexto_supervisor, incidencia_id, escenario.supervisor_id)
    await _cerrar(contexto_supervisor, incidencia_id, escenario.supervisor_id)

    async with admin.connect() as conn:
        actividad = (
            await conn.execute(
                text("select bloqueada from actividad where id = :id"),
                {"id": str(escenario.actividad_id)},
            )
        ).first()
    await admin.dispose()

    assert actividad.bloqueada is False


async def test_rechazar_exige_motivo_y_desbloquea(
    escenario: Escenario, contexto_residente: ContextoSesion, contexto_supervisor: ContextoSesion
) -> None:
    incidencia_id = await _abrir(
        contexto_residente,
        escenario,
        impacto=ImpactoIncidencia.DETIENE,
        bloquea_actividades=[escenario.actividad_id],
    )
    await _programar(contexto_supervisor, incidencia_id, escenario.supervisor_id)
    await _atender(contexto_supervisor, incidencia_id, escenario.supervisor_id)
    await _solicitar_cierre(contexto_supervisor, incidencia_id, escenario.supervisor_id)

    async with sesion_con_rls(contexto_supervisor) as sesion:
        caso_uso = RechazarIncidencia(
            actividades=RepositorioActividadesSQL(sesion),
            incidencias=RepositorioIncidenciasSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
        )
        with pytest.raises(ErrorDeIncidencia, match="motivo"):
            await caso_uso.ejecutar(
                ComandoRechazarIncidencia(
                    incidencia_id=incidencia_id,
                    usuario_id=escenario.supervisor_id,
                    rol=Rol.SUPERVISOR,
                    motivo="   ",
                )
            )
        await caso_uso.ejecutar(
            ComandoRechazarIncidencia(
                incidencia_id=incidencia_id,
                usuario_id=escenario.supervisor_id,
                rol=Rol.SUPERVISOR,
                motivo="Ya no aplica",
            )
        )

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        incidencia = (
            await conn.execute(
                text("select estatus from incidencia where id = :id"),
                {"id": str(incidencia_id)},
            )
        ).first()
        actividad = (
            await conn.execute(
                text("select bloqueada from actividad where id = :id"),
                {"id": str(escenario.actividad_id)},
            )
        ).first()
    await admin.dispose()

    assert incidencia.estatus == "rechazada"
    # Rechazar también desbloquea: sin esto la actividad quedaría bloqueada
    # para siempre, sin vía de recuperación (rechazada es terminal).
    assert actividad.bloqueada is False


async def test_residente_no_programa(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    incidencia_id = await _abrir(contexto_residente, escenario)

    async with sesion_con_rls(contexto_residente) as sesion:
        caso_uso = ProgramarIncidencia(
            incidencias=RepositorioIncidenciasSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        )
        with pytest.raises(ErrorDeIncidencia, match="Solo Supervisor o Control"):
            await caso_uso.ejecutar(
                ComandoProgramarIncidencia(
                    incidencia_id=incidencia_id,
                    usuario_id=escenario.residente_id,
                    rol=Rol.RESIDENTE,
                    asignada_a=escenario.residente_id,
                )
            )


async def test_programar_incidencia_inexistente_da_no_encontrada(
    contexto_supervisor: ContextoSesion,
) -> None:
    with pytest.raises(IncidenciaNoEncontrada):
        await _programar(contexto_supervisor, uuid.uuid4(), uuid.uuid4())


async def test_incidencia_creada_no_es_visible_para_una_org_ajena(
    escenario: Escenario, contexto_residente: ContextoSesion, contexto_ajeno: ContextoSesion
) -> None:
    """RLS: una identidad de otra organización no ve la incidencia (§12.4)."""
    incidencia_id = await _abrir(contexto_residente, escenario)

    async with sesion_con_rls(contexto_ajeno) as sesion:
        repo = RepositorioIncidenciasSQL(sesion)
        fila = await repo.obtener(incidencia_id)
    assert fila is None
