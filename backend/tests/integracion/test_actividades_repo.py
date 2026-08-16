"""Repositorio de actividades contra Postgres real (§7.6, §12.4).

No es una repetición de `tests/domain/test_avance.py`: aquí se prueba que el
SQL respeta RLS, que el trigger `app.actividad_recalcular` (BD) llega
exactamente al mismo resultado que `domain.avance.reglas` (Python) —la
premisa de "defensa en profundidad" del comentario en `actividades_sql.py`—,
y que el jsonb de `dependencias`/`evidencias` va y vuelve sin sorpresas.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.repos.actividades_sql import (
    ActividadNoModificada,
    RepositorioActividadesSQL,
)
from obractrl.domain.programacion.cpm import TipoDependencia
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario


async def test_obtener_devuelve_la_actividad_en_tu_alcance(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioActividadesSQL(sesion)
        fila = await repo.obtener(escenario.actividad_id)

    assert fila is not None
    assert fila["id"] == escenario.actividad_id
    assert fila["cant_base"] == Decimal("100")
    assert fila["estatus"] == "programada"
    assert fila["bloqueada"] is False


async def test_obtener_no_ve_actividades_de_otra_org(
    escenario: Escenario, contexto_ajeno: ContextoSesion
) -> None:
    """RLS filtra por org_id: una identidad ajena no ve nada, punto (§12.4)."""
    async with sesion_con_rls(contexto_ajeno) as sesion:
        repo = RepositorioActividadesSQL(sesion)
        fila = await repo.obtener(escenario.actividad_id)

    assert fila is None


async def test_actualizar_avance_persiste_y_el_trigger_coincide(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    """El repo escribe la cantidad programada; `cant_ejecutada` llega por la
    bitácora (D5) y los triggers derivan `avance_pct` y el auto-estatus. Si el
    número no coincide, la corrección de §6 (tope/umbral fijos, no
    configurables) se rompió."""
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioActividadesSQL(sesion)
        await repo.actualizar_avance(
            escenario.actividad_id,
            cant_programada=Decimal("100"),
            estatus="casi",
        )
        await repo.registrar_captura(
            escenario.actividad_id,
            fecha=date.today(),
            delta_ejecutado=Decimal("95"),
            usuario_id=contexto_residente.usuario_id,
            evidencias=[],
        )
        await sesion.commit()

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        fila = (
            await conn.execute(
                text(
                    "select avance_pct, estatus from actividad where id = :id"
                ),
                {"id": str(escenario.actividad_id)},
            )
        ).first()
    await admin.dispose()

    assert fila is not None
    assert fila.avance_pct == Decimal("95.00")
    assert fila.estatus == "casi"


async def test_actualizar_avance_actividad_inexistente_levanta(
    contexto_residente: ContextoSesion,
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioActividadesSQL(sesion)
        with pytest.raises(ActividadNoModificada):
            await repo.actualizar_avance(
                uuid.uuid4(),
                cant_programada=Decimal("1"),
                estatus="concluida",
            )


async def test_registrar_captura_resuelve_org_id_del_contexto(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    """`org_id` sale de `current_setting('app.org_id')`, no de un parámetro:
    si el registro quedó bajo la org correcta, el mecanismo funcionó."""
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioActividadesSQL(sesion)
        registro_id = await repo.registrar_captura(
            escenario.actividad_id,
            fecha=date(2026, 3, 10),
            delta_ejecutado=Decimal("15.5"),
            usuario_id=escenario.residente_id,
            evidencias=["r2://evidencias/foto-1.jpg", "r2://evidencias/foto-2.jpg"],
        )
        await sesion.commit()

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        fila = (
            await conn.execute(
                text(
                    "select org_id, delta_ejecutado, evidencias "
                    "from registro_avance where id = :id"
                ),
                {"id": str(registro_id)},
            )
        ).first()
    await admin.dispose()

    assert fila is not None
    assert fila.org_id == escenario.org_id
    assert fila.delta_ejecutado == Decimal("15.5")
    assert fila.evidencias == [
        "r2://evidencias/foto-1.jpg",
        "r2://evidencias/foto-2.jpg",
    ]


async def test_nodos_cpm_de_obra_parsea_dependencias_jsonb(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    admin = create_async_engine(DATABASE_URL_ADMIN)
    segunda = uuid.uuid4()
    async with admin.begin() as conn:
        await conn.execute(
            text(
                """
                insert into actividad
                    (id, org_id, obra_id, cant_base, cant_programada,
                     cant_ejecutada, duracion_dias, dependencias)
                values
                    (:id, :org, :obra, 10, 10,
                     10, 3, cast(:dependencias as jsonb))
                """
            ),
            {
                "id": str(segunda),
                "org": str(escenario.org_id),
                "obra": str(escenario.obra_id),
                "dependencias": (
                    f'[{{"ref": "{escenario.actividad_id}", "tipo": "FS", '
                    f'"lag_dias": 1}}]'
                ),
            },
        )
        # Solo se puede marcar fecha_termino directo por SQL (no hay caso de
        # uso de cierre todavía); es lo que el repo usa para decidir si
        # fecha_real_termino aplica (avance_pct >= 100).
        await conn.execute(
            text("update actividad set fecha_termino = '2026-03-15' where id = :id"),
            {"id": str(segunda)},
        )
    await admin.dispose()

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioActividadesSQL(sesion)
        nodos = await repo.nodos_cpm_de_obra(escenario.obra_id)

    por_ref = {n.ref: n for n in nodos}
    assert set(por_ref) == {str(escenario.actividad_id), str(segunda)}

    nodo = por_ref[str(segunda)]
    assert nodo.duracion_dias == 3.0
    assert len(nodo.dependencias) == 1
    dep = nodo.dependencias[0]
    assert dep.ref == str(escenario.actividad_id)
    assert dep.tipo == TipoDependencia.FIN_INICIO
    assert dep.lag_dias == 1.0
    # avance_pct=100 -> debe leer fecha_termino como la fecha real (§6)
    assert nodo.fecha_real_termino is not None
    assert nodo.fecha_real_termino.isoformat() == "2026-03-15"

    # La actividad original sigue en 0% -> no tiene fecha real todavía.
    assert por_ref[str(escenario.actividad_id)].fecha_real_termino is None


async def test_marcar_bloqueadas_y_vacio_es_no_op(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioActividadesSQL(sesion)

        # Conjunto vacío: no debe tronar ni tocar nada.
        await repo.marcar_bloqueadas(escenario.obra_id, set(), True)

        await repo.marcar_bloqueadas(
            escenario.obra_id, {str(escenario.actividad_id)}, True
        )
        await sesion.commit()

    # `commit()` cierra la transacción donde vivía el `SET LOCAL app.*`
    # (§12.4): una sesión nueva es lo que haría una petición real de
    # seguimiento, así que la relectura abre su propio `sesion_con_rls`.
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioActividadesSQL(sesion)
        fila = await repo.obtener(escenario.actividad_id)

    assert fila is not None
    assert fila["bloqueada"] is True


async def test_guardar_resultado_cpm_persiste_los_tres_campos(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    resultados = {
        str(escenario.actividad_id): {
            "es_critica": True,
            "holgura": 0.0,
            "desfase": 2.5,
        }
    }
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioActividadesSQL(sesion)

        # Vacío: no debe tronar.
        await repo.guardar_resultado_cpm(escenario.obra_id, {})

        await repo.guardar_resultado_cpm(escenario.obra_id, resultados)
        await sesion.commit()

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        fila = (
            await conn.execute(
                text(
                    "select es_critica, holgura, desfase from actividad where id = :id"
                ),
                {"id": str(escenario.actividad_id)},
            )
        ).first()
    await admin.dispose()

    assert fila is not None
    assert fila.es_critica is True
    assert fila.holgura == Decimal("0.00")
    assert fila.desfase == Decimal("2.50")
