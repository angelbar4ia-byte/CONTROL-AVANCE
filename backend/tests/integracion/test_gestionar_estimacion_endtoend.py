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

from obractrl.adapters.api.casos_uso import obtener_armar_reporte_estimacion
from obractrl.adapters.export.xlsx import estimacion_a_xlsx
from obractrl.adapters.repos.calendario_sql import RepositorioCalendarioSQL
from obractrl.adapters.repos.estimaciones_sql import RepositorioEstimacionesSQL
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL
from obractrl.adapters.repos.usuarios_sql import RepositorioUsuariosSQL
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
from obractrl.application.eventos import BusEnProceso, EstimacionValidada
from obractrl.domain.shared.diccionario import ModoPago, Rol
from obractrl.domain.shared.valores import Dinero
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
    # `monto_total` es un `Dinero` (DECIMAL + MXN, §11.1), no un Decimal
    # suelto: compararlo contra uno crudo siempre da falso.
    assert creada.estimacion.monto_total == Dinero("1200")  # 10 * 120 (destajo)
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


# ---------------------------------------------------------------------------
# §11.3 E.5 — los dos efectos de validar: bloquear el periodo y avisar
# ---------------------------------------------------------------------------


async def _validar(
    ctx: ContextoSesion,
    escenario: Escenario,
    estimacion_id: uuid.UUID,
    *,
    eventos: BusEnProceso | None = None,
) -> dict:
    """Envía y valida en un solo paso: aquí lo que se prueba es el efecto de
    validar, no la transición, que ya cubre `test_flujo_completo_hasta_validada`."""
    async with sesion_con_rls(ctx) as sesion:
        await EnviarEstimacion(
            estimaciones=RepositorioEstimacionesSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
        ).ejecutar(
            ComandoEnviarEstimacion(
                estimacion_id=estimacion_id,
                usuario_id=escenario.supervisor_id,
                rol=Rol.SUPERVISOR,
            )
        )

    async with sesion_con_rls(ctx) as sesion:
        return await ValidarEstimacion(
            estimaciones=RepositorioEstimacionesSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
            eventos=eventos,
        ).ejecutar(
            ComandoValidarEstimacion(
                estimacion_id=estimacion_id,
                usuario_id=escenario.control_id,
                rol=Rol.CONTROL_OBRA,
            )
        )


async def test_validar_bloquea_el_periodo_de_esa_obra(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """§11.3 E.5: el candado se escribe dentro de la transacción que valida,
    no en un manejador de evento — el bus descarta los fallos y un periodo sin
    bloquear deja cobrar dos veces la misma semana."""
    semana, anio = await _preparar_calendario_y_cierre_validado(escenario)
    creada = await _generar(contexto_control, escenario, ModoPago.DESTAJO)

    await _validar(contexto_control, escenario, creada.id)

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        fila = (
            await conn.execute(
                text(
                    "select org_id, obra_id, tipo_semana, anio, semana, "
                    "estimacion_id, bloqueado_por from periodo_bloqueado "
                    "where obra_id = :obra"
                ),
                {"obra": str(escenario.obra_id)},
            )
        ).first()
    await admin.dispose()

    assert fila is not None
    assert (fila.anio, fila.semana) == (anio, semana)
    assert fila.tipo_semana == "obra"
    assert fila.org_id == escenario.org_id
    assert fila.estimacion_id == creada.id
    assert fila.bloqueado_por == escenario.control_id


async def test_no_se_puede_volver_a_estimar_una_semana_ya_validada(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """El defecto que la migración 0020 cierra: sin el candado, la misma
    semana se volvía a estimar —y a cobrar—."""
    await _preparar_calendario_y_cierre_validado(escenario)
    creada = await _generar(contexto_control, escenario, ModoPago.DESTAJO)
    await _validar(contexto_control, escenario, creada.id)

    with pytest.raises(ErrorDeEstimacion, match="bloqueado"):
        await _generar(contexto_control, escenario, ModoPago.DESTAJO)


async def test_al_rebotar_por_periodo_cerrado_no_se_gasta_un_folio(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """El candado se consulta **antes** de pedir el consecutivo (§3.2): una
    corrida que va a fallar no puede quemar un folio."""
    await _preparar_calendario_y_cierre_validado(escenario)
    creada = await _generar(contexto_control, escenario, ModoPago.DESTAJO)
    await _validar(contexto_control, escenario, creada.id)

    with pytest.raises(ErrorDeEstimacion):
        await _generar(contexto_control, escenario, ModoPago.DESTAJO)

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        total = (
            await conn.execute(
                text("select count(*) from estimacion where obra_id = :obra"),
                {"obra": str(escenario.obra_id)},
            )
        ).scalar_one()
    await admin.dispose()
    assert total == 1


async def test_validar_publica_el_evento_y_un_manejador_que_truena_no_deshace_nada(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """§11.1: el aviso sale como evento, ya con la estimación commiteada. Un
    Resend caído no puede deshacer la validación."""
    await _preparar_calendario_y_cierre_validado(escenario)
    creada = await _generar(contexto_control, escenario, ModoPago.DESTAJO)

    recibidos: list[EstimacionValidada] = []

    async def _truena(evento: EstimacionValidada) -> None:
        recibidos.append(evento)
        raise RuntimeError("Resend caído")

    bus = BusEnProceso()
    bus.suscribir(EstimacionValidada, _truena)

    validada = await _validar(contexto_control, escenario, creada.id, eventos=bus)

    assert validada["estatus"] == "validada"
    assert [evento.estimacion_id for evento in recibidos] == [creada.id]

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        estatus = (
            await conn.execute(
                text("select estatus from estimacion where id = :id"),
                {"id": str(creada.id)},
            )
        ).scalar_one()
    await admin.dispose()
    assert estatus == "validada"


async def test_una_org_ajena_no_ve_el_periodo_bloqueado(
    escenario: Escenario,
    contexto_control: ContextoSesion,
    contexto_ajeno: ContextoSesion,
) -> None:
    """RLS: `periodo_bloqueado_scope` acota igual que `estimacion`, que es la
    tabla que lo origina (migración 0020, §12.4)."""
    semana, anio = await _preparar_calendario_y_cierre_validado(escenario)
    creada = await _generar(contexto_control, escenario, ModoPago.DESTAJO)
    await _validar(contexto_control, escenario, creada.id)

    async with sesion_con_rls(contexto_ajeno) as sesion:
        visto = await RepositorioEstimacionesSQL(sesion).periodo_bloqueado(
            obra_id=escenario.obra_id,
            tipo_semana="obra",
            semana=semana,
            anio=anio,
        )
    assert visto is False


# ---------------------------------------------------------------------------
# §11.2 `GET /estimaciones/{id}/export` — los renglones que alimentan el xlsx
# ---------------------------------------------------------------------------


async def test_el_reporte_de_estimacion_cuadra_con_lo_guardado(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """El `.xlsx` no recalcula nada: lo que verifica es que la cabecera
    guardada coincida con la suma de sus renglones (§11.3 E.2)."""
    await _preparar_calendario_y_cierre_validado(escenario)
    creada = await _generar(contexto_control, escenario, ModoPago.DESTAJO)

    async with sesion_con_rls(contexto_control) as sesion:
        reporte = await obtener_armar_reporte_estimacion(sesion).ejecutar(creada.id)

    assert reporte.obra_clave == "OBRA 01"
    assert reporte.folio is not None
    assert len(reporte.conceptos) == 1
    assert reporte.monto_total == Dinero("1200")
    assert reporte.cuadra, "la cabecera tiene que coincidir con sus renglones"

    contenido = estimacion_a_xlsx(reporte)
    assert contenido.startswith(b"PK"), "un .xlsx es un zip"


async def test_una_estimacion_fuera_de_alcance_no_se_exporta(
    escenario: Escenario,
    contexto_control: ContextoSesion,
    contexto_ajeno: ContextoSesion,
) -> None:
    """El worker corre con el contexto RLS de quien pidió el reporte: no puede
    exportar lo que ese usuario no vería por HTTP (§12.4)."""
    await _preparar_calendario_y_cierre_validado(escenario)
    creada = await _generar(contexto_control, escenario, ModoPago.DESTAJO)

    with pytest.raises(EstimacionNoEncontrada):
        async with sesion_con_rls(contexto_ajeno) as sesion:
            await obtener_armar_reporte_estimacion(sesion).ejecutar(creada.id)


# ---------------------------------------------------------------------------
# Identidad por su fachada (§11.1) — a quién avisa el evento
# ---------------------------------------------------------------------------


async def test_los_destinatarios_salen_del_puerto_de_identidad(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """§11.1: Notificaciones no consulta `usuario` desde su propio repo."""
    async with sesion_con_rls(contexto_control) as sesion:
        filas = await RepositorioUsuariosSQL(sesion).correos_de(
            [escenario.residente_id, escenario.control_id, uuid.uuid4()]
        )

    correos = {fila["id"]: fila["email"] for fila in filas}
    assert set(correos) == {escenario.residente_id, escenario.control_id}
    assert all(correos.values()), "sin correo no hay a quién avisarle"


async def test_identidad_de_otra_org_simplemente_no_aparece(
    escenario: Escenario, contexto_ajeno: ContextoSesion
) -> None:
    """`usuario_select` da lectura dentro de la organización del token."""
    async with sesion_con_rls(contexto_ajeno) as sesion:
        filas = await RepositorioUsuariosSQL(sesion).correos_de(
            [escenario.residente_id, escenario.control_id]
        )
    assert filas == []


async def test_pedir_cero_destinatarios_no_consulta_nada(
    contexto_control: ContextoSesion,
) -> None:
    async with sesion_con_rls(contexto_control) as sesion:
        assert await RepositorioUsuariosSQL(sesion).correos_de([]) == []
