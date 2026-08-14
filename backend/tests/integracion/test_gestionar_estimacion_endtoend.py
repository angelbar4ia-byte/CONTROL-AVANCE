"""Flujo de estimación de punta a punta: casos de uso + repos + Postgres real.

Spec §11.3 workflow E · §3.1 (calendario) · §3.2 (folio) · §12.11 (Definition
of Done).

`tests/domain/test_estimacion.py` prueba las reglas puras; esto prueba que
los tres casos de uso —cableados exactamente como en
`adapters/api/casos_uso.py`— las aplican contra la base real: solo entran las
actividades del `modo` pedido con cierre validado en la semana activa, el
folio sale del contador real y el estatus seguido el flujo hasta bloquear el
periodo.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.repos.calendario_sql import RepositorioCalendarioSQL
from obractrl.adapters.repos.estimaciones_sql import RepositorioEstimacionesSQL
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL
from obractrl.application.casos_uso.gestionar_estimacion import (
    ComandoEnviarEstimacion,
    ComandoGenerarEstimacion,
    ComandoValidarEstimacion,
    EnviarEstimacion,
    ErrorDeEstimacion,
    EstimacionNoEncontrada,
    GenerarEstimacion,
    ValidarEstimacion,
)
from obractrl.domain.shared.diccionario import ModoPago, Rol
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario


async def _preparar_calendario_y_cierre_validado(escenario: Escenario) -> tuple[int, int]:
    """Genera el calendario 2026, ancla la semana activa y deja la actividad
    del escenario con un cierre validado dentro de esa semana."""
    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "select app.generar_calendario(cast(:org as uuid), "
                "'obra'::tipo_semana, 2026::smallint)"
            ),
            {"org": str(escenario.org_id)},
        )
        fila = (
            await conn.execute(
                text(
                    "select semana, anio, fecha_inicio from calendario "
                    "where org_id = :org and tipo = 'obra' and anio = 2026 "
                    "order by semana limit 1"
                ),
                {"org": str(escenario.org_id)},
            )
        ).first()
        semana, anio, fecha_inicio = fila.semana, fila.anio, fila.fecha_inicio

        await conn.execute(
            text(
                "insert into ancla_semana (org_id, tipo, anio, semana) "
                "values (:org, 'obra', :anio, :semana)"
            ),
            {"org": str(escenario.org_id), "anio": anio, "semana": semana},
        )

        await conn.execute(
            text(
                """
                insert into solicitud_cierre
                    (org_id, actividad_id, cantidad, estatus,
                     autorizada_por, validada_por, fecha_valida)
                values
                    (:org, :act, 10, 'validada', :res, :res, :fecha_valida)
                """
            ),
            {
                "org": str(escenario.org_id),
                "act": str(escenario.actividad_id),
                "res": str(escenario.residente_id),
                "fecha_valida": fecha_inicio,
            },
        )
        # precio_destajo > 0 para que el modo destajo produzca un importe no cero.
        await conn.execute(
            text(
                "update actividad set precio_unitario = 500, precio_destajo = 120, "
                "modo_pago = 'destajo' where id = :id"
            ),
            {"id": str(escenario.actividad_id)},
        )
    await admin.dispose()
    return int(semana), int(anio)


async def _generar(ctx: ContextoSesion, escenario: Escenario, modo: ModoPago = ModoPago.DESTAJO):
    async with sesion_con_rls(ctx) as sesion:
        caso_uso = GenerarEstimacion(
            estimaciones=RepositorioEstimacionesSQL(sesion),
            calendario=RepositorioCalendarioSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
        )
        return await caso_uso.ejecutar(
            ComandoGenerarEstimacion(
                obra_id=escenario.obra_id,
                modo=modo,
                usuario_id=escenario.residente_id,
                rol=Rol.RESIDENTE,
            )
        )


async def test_generar_toma_solo_las_actividades_del_modo_pedido(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    semana, anio = await _preparar_calendario_y_cierre_validado(escenario)

    creada = await _generar(contexto_residente, escenario, ModoPago.DESTAJO)

    assert creada.estimacion.semana == semana
    assert creada.estimacion.anio == anio
    assert creada.estimacion.monto_total == Decimal("1200")  # 10 * 120 (destajo)
    assert len(creada.estimacion.conceptos) == 1

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        cabecera = (
            await conn.execute(
                text("select monto_total, folio from estimacion where id = :id"),
                {"id": str(creada.id)},
            )
        ).first()
        conceptos = (
            await conn.execute(
                text(
                    "select count(*) from estimacion_concepto where estimacion_id = :id"
                ),
                {"id": str(creada.id)},
            )
        ).scalar_one()
    await admin.dispose()

    assert cabecera is not None
    assert cabecera.monto_total == Decimal("1200.0000")
    assert cabecera.folio is not None
    assert conceptos == 1


async def test_generar_en_modo_sin_actividades_valida_falla(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    await _preparar_calendario_y_cierre_validado(escenario)  # actividad es modo 'destajo'

    with pytest.raises(ErrorDeEstimacion, match="No hay actividades"):
        await _generar(contexto_residente, escenario, ModoPago.CONCEPTO)


async def test_flujo_completo_hasta_validada(
    escenario: Escenario,
    contexto_residente: ContextoSesion,
    contexto_supervisor: ContextoSesion,
    contexto_control: ContextoSesion,
) -> None:
    await _preparar_calendario_y_cierre_validado(escenario)
    creada = await _generar(contexto_residente, escenario, ModoPago.DESTAJO)

    async with sesion_con_rls(contexto_supervisor) as sesion:
        caso_uso = EnviarEstimacion(
            estimaciones=RepositorioEstimacionesSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        )
        enviada = await caso_uso.ejecutar(
            ComandoEnviarEstimacion(
                estimacion_id=creada.id, usuario_id=escenario.supervisor_id, rol=Rol.SUPERVISOR
            )
        )
    assert enviada["estatus"] == "enviada"

    async with sesion_con_rls(contexto_control) as sesion:
        caso_uso = ValidarEstimacion(
            estimaciones=RepositorioEstimacionesSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        )
        validada = await caso_uso.ejecutar(
            ComandoValidarEstimacion(
                estimacion_id=creada.id, usuario_id=escenario.control_id, rol=Rol.CONTROL_OBRA
            )
        )
    assert validada["estatus"] == "validada"
    assert validada["validada_por"] == escenario.control_id


async def test_enviar_estimacion_inexistente_da_no_encontrada(
    contexto_supervisor: ContextoSesion,
) -> None:
    async with sesion_con_rls(contexto_supervisor) as sesion:
        caso_uso = EnviarEstimacion(
            estimaciones=RepositorioEstimacionesSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        )
        with pytest.raises(EstimacionNoEncontrada):
            await caso_uso.ejecutar(
                ComandoEnviarEstimacion(
                    estimacion_id=uuid.uuid4(), usuario_id=uuid.uuid4(), rol=Rol.SUPERVISOR
                )
            )


async def test_validar_sin_enviar_falla(
    escenario: Escenario, contexto_residente: ContextoSesion, contexto_control: ContextoSesion
) -> None:
    await _preparar_calendario_y_cierre_validado(escenario)
    creada = await _generar(contexto_residente, escenario, ModoPago.DESTAJO)

    async with sesion_con_rls(contexto_control) as sesion:
        caso_uso = ValidarEstimacion(
            estimaciones=RepositorioEstimacionesSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        )
        with pytest.raises(ErrorDeEstimacion, match="No se puede pasar"):
            await caso_uso.ejecutar(
                ComandoValidarEstimacion(
                    estimacion_id=creada.id, usuario_id=escenario.control_id, rol=Rol.CONTROL_OBRA
                )
            )
