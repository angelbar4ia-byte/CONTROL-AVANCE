"""Flujo de cierre de punta a punta: casos de uso + repos + Postgres real.

Spec §11.3 workflow C · §4 · §12.11 (Definition of Done).

`tests/domain/test_cierres.py` prueba las reglas puras; esto prueba que los
cuatro casos de uso —cableados exactamente como en
`adapters/api/casos_uso.py`— las aplican contra la base real: la solicitud
queda escrita, `actividad.estatus` sigue el flujo (`pendiente_cierre` al
solicitar, `concluida` al validar) y RLS filtra cada paso.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.repos.actividades_sql import RepositorioActividadesSQL
from obractrl.adapters.repos.cierres_sql import RepositorioCierresSQL
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL
from obractrl.application.casos_uso.capturar_avance import ActividadNoEncontrada
from obractrl.application.casos_uso.gestionar_cierre import (
    AutorizarCierre,
    ComandoAutorizarCierre,
    ComandoRechazarCierre,
    ComandoSolicitarCierre,
    ComandoValidarCierre,
    ErrorDeCierre,
    RechazarCierre,
    SolicitarCierre,
    SolicitudCierreNoEncontrada,
    ValidarCierre,
)
from obractrl.domain.shared.diccionario import Rol
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario

CHECKLIST = [{"item": "Nivelación", "ok": True}]
ADJUNTOS = ["r2://evidencias/foto-1.jpg"]


async def _solicitar(ctx: ContextoSesion, escenario: Escenario) -> uuid.UUID:
    async with sesion_con_rls(ctx) as sesion:
        caso_uso = SolicitarCierre(
            actividades=RepositorioActividadesSQL(sesion),
            cierres=RepositorioCierresSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
        )
        creada = await caso_uso.ejecutar(
            ComandoSolicitarCierre(
                actividad_id=escenario.actividad_id,
                residente_id=escenario.residente_id,
                rol=Rol.RESIDENTE,
                cantidad=Decimal("10"),
                checklist=CHECKLIST,
                adjuntos=ADJUNTOS,
            )
        )
        return creada.id


async def _autorizar(ctx: ContextoSesion, cierre_id: uuid.UUID, usuario_id: uuid.UUID) -> None:
    async with sesion_con_rls(ctx) as sesion:
        caso_uso = AutorizarCierre(
            cierres=RepositorioCierresSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        )
        await caso_uso.ejecutar(
            ComandoAutorizarCierre(cierre_id=cierre_id, usuario_id=usuario_id, rol=Rol.SUPERVISOR)
        )


async def _validar(ctx: ContextoSesion, cierre_id: uuid.UUID, usuario_id: uuid.UUID) -> None:
    async with sesion_con_rls(ctx) as sesion:
        caso_uso = ValidarCierre(
            actividades=RepositorioActividadesSQL(sesion),
            cierres=RepositorioCierresSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
        )
        await caso_uso.ejecutar(
            ComandoValidarCierre(
                cierre_id=cierre_id, usuario_id=usuario_id, rol=Rol.CONTROL_OBRA, comentario="Ok"
            )
        )


async def test_flujo_completo_deja_la_actividad_concluida(
    escenario: Escenario,
    contexto_residente: ContextoSesion,
    contexto_supervisor: ContextoSesion,
    contexto_control: ContextoSesion,
) -> None:
    cierre_id = await _solicitar(contexto_residente, escenario)

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        actividad = (
            await conn.execute(
                text("select estatus from actividad where id = :id"),
                {"id": str(escenario.actividad_id)},
            )
        ).first()
    assert actividad.estatus == "pendiente_cierre"

    await _autorizar(contexto_supervisor, cierre_id, escenario.supervisor_id)
    await _validar(contexto_control, cierre_id, escenario.control_id)

    async with admin.connect() as conn:
        actividad = (
            await conn.execute(
                text("select estatus from actividad where id = :id"),
                {"id": str(escenario.actividad_id)},
            )
        ).first()
        cierre = (
            await conn.execute(
                text(
                    "select estatus, autorizada_por, validada_por, fecha_valida "
                    "from solicitud_cierre where id = :id"
                ),
                {"id": str(cierre_id)},
            )
        ).first()
    await admin.dispose()

    assert actividad.estatus == "concluida"
    assert cierre.estatus == "validada"
    assert cierre.autorizada_por == escenario.supervisor_id
    assert cierre.validada_por == escenario.control_id
    assert cierre.fecha_valida is not None


async def test_control_no_puede_autorizar(
    escenario: Escenario, contexto_residente: ContextoSesion, contexto_control: ContextoSesion
) -> None:
    cierre_id = await _solicitar(contexto_residente, escenario)

    with pytest.raises(ErrorDeCierre, match="no autoriza"):
        await _autorizar(contexto_control, cierre_id, escenario.control_id)


async def test_no_se_valida_sin_autorizar(
    escenario: Escenario, contexto_residente: ContextoSesion, contexto_control: ContextoSesion
) -> None:
    cierre_id = await _solicitar(contexto_residente, escenario)

    with pytest.raises(ErrorDeCierre, match="No se puede pasar"):
        await _validar(contexto_control, cierre_id, escenario.control_id)


async def test_rechazar_recalcula_el_estatus_desde_el_avance(
    escenario: Escenario, contexto_residente: ContextoSesion, contexto_supervisor: ContextoSesion
) -> None:
    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "update actividad set cant_ejecutada = 95 where id = :id"
            ),
            {"id": str(escenario.actividad_id)},
        )
    await admin.dispose()

    cierre_id = await _solicitar(contexto_residente, escenario)

    async with sesion_con_rls(contexto_supervisor) as sesion:
        caso_uso = RechazarCierre(
            actividades=RepositorioActividadesSQL(sesion),
            cierres=RepositorioCierresSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
        )
        await caso_uso.ejecutar(
            ComandoRechazarCierre(
                cierre_id=cierre_id,
                usuario_id=escenario.supervisor_id,
                rol=Rol.SUPERVISOR,
                motivo="Checklist incompleto",
            )
        )

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        actividad = (
            await conn.execute(
                text("select estatus from actividad where id = :id"),
                {"id": str(escenario.actividad_id)},
            )
        ).first()
        cierre = (
            await conn.execute(
                text("select estatus, comentarios from solicitud_cierre where id = :id"),
                {"id": str(cierre_id)},
            )
        ).first()
    await admin.dispose()

    # 95% de avance -> el auto-estatus del §6 vuelve a "casi", no a "programada".
    assert actividad.estatus == "casi"
    assert cierre.estatus == "rechazada"
    assert cierre.comentarios == "Checklist incompleto"


async def test_solicitar_actividad_fuera_de_alcance_da_no_encontrada(
    contexto_ajeno: ContextoSesion,
) -> None:
    with pytest.raises(ActividadNoEncontrada):
        await _solicitar(
            contexto_ajeno,
            Escenario(
                org_id=uuid.uuid4(),
                residente_id=uuid.uuid4(),
                supervisor_id=uuid.uuid4(),
                control_id=uuid.uuid4(),
                proyecto_id=uuid.uuid4(),
                cluster_id=uuid.uuid4(),
                prototipo_id=uuid.uuid4(),
                obra_id=uuid.uuid4(),
                actividad_id=uuid.uuid4(),
            ),
        )


async def test_autorizar_cierre_inexistente_da_no_encontrada(
    contexto_supervisor: ContextoSesion,
) -> None:
    with pytest.raises(SolicitudCierreNoEncontrada):
        await _autorizar(contexto_supervisor, uuid.uuid4(), uuid.uuid4())
