"""`CapturarAvance` de punta a punta: caso de uso + repos + Postgres real.

Spec §11.3 workflow B · §6 · §12.11 (Definition of Done).

`tests/domain/test_avance.py` prueba las reglas puras; esto prueba que el
caso de uso —cableado exactamente como en `adapters/api/casos_uso.py`— las
aplica correctamente contra la base real: la actividad queda actualizada, el
`registro_avance` queda escrito, y ambas cosas ocurren en la misma
transacción (si una fallara, ninguna debería quedar).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.repos.actividades_sql import RepositorioActividadesSQL
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL
from obractrl.application.casos_uso.capturar_avance import (
    ActividadNoEncontrada,
    CapturarAvance,
    ComandoCapturarAvance,
)
from obractrl.domain.avance.reglas import ErrorDeCaptura
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario


async def _ejecutar(
    ctx: ContextoSesion, cmd: ComandoCapturarAvance
) -> object:
    async with sesion_con_rls(ctx) as sesion:
        caso_uso = CapturarAvance(
            actividades=RepositorioActividadesSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
        )
        return await caso_uso.ejecutar(cmd)


async def test_captura_valida_deja_todo_consistente(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    resultado = await _ejecutar(
        contexto_residente,
        ComandoCapturarAvance(
            actividad_id=escenario.actividad_id,
            usuario_id=escenario.residente_id,
            cant_ejecutada=Decimal("95"),
            evidencias=("r2://evidencias/a.jpg",),
        ),
    )

    assert resultado.avance.pct == Decimal("95.00")
    assert resultado.estatus.value == "casi"

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        actividad = (
            await conn.execute(
                text(
                    "select cant_ejecutada, avance_pct, estatus "
                    "from actividad where id = :id"
                ),
                {"id": str(escenario.actividad_id)},
            )
        ).first()
        registros = (
            await conn.execute(
                text(
                    "select delta_ejecutado, usuario_id, evidencias "
                    "from registro_avance where actividad_id = :id"
                ),
                {"id": str(escenario.actividad_id)},
            )
        ).all()
    await admin.dispose()

    assert actividad is not None
    assert actividad.cant_ejecutada == Decimal("95")
    assert actividad.avance_pct == Decimal("95.00")
    assert actividad.estatus == "casi"

    assert len(registros) == 1
    assert registros[0].delta_ejecutado == Decimal("95")  # 95 - 0 inicial
    assert registros[0].usuario_id == escenario.residente_id
    assert registros[0].evidencias == ["r2://evidencias/a.jpg"]


async def test_dos_capturas_seguidas_acumulan_el_delta(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    """El delta de la segunda captura es la diferencia contra la primera,
    no el total — así es como PowerSync puede sumar deltas sin conflicto
    (§12.5, comentario en `mobile/src/sync/powersync.ts`)."""
    await _ejecutar(
        contexto_residente,
        ComandoCapturarAvance(
            actividad_id=escenario.actividad_id,
            usuario_id=escenario.residente_id,
            cant_ejecutada=Decimal("30"),
        ),
    )
    await _ejecutar(
        contexto_residente,
        ComandoCapturarAvance(
            actividad_id=escenario.actividad_id,
            usuario_id=escenario.residente_id,
            cant_ejecutada=Decimal("50"),
        ),
    )

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        deltas = (
            await conn.execute(
                text(
                    "select delta_ejecutado from registro_avance "
                    "where actividad_id = :id order by created_at"
                ),
                {"id": str(escenario.actividad_id)},
            )
        ).scalars().all()
    await admin.dispose()

    assert deltas == [Decimal("30"), Decimal("20")]


async def test_sobreprogramar_no_persiste_nada(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    """Si `aplicar_captura` rechaza la regla, no debe quedar ni el UPDATE ni
    el INSERT a medias — la excepción se lanza antes de tocar el repo."""
    with pytest.raises(ErrorDeCaptura):
        await _ejecutar(
            contexto_residente,
            ComandoCapturarAvance(
                actividad_id=escenario.actividad_id,
                usuario_id=escenario.residente_id,
                cant_programada=Decimal("130"),  # > 100 * 1.2
                cant_ejecutada=Decimal("10"),
            ),
        )

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        actividad = (
            await conn.execute(
                text("select cant_ejecutada from actividad where id = :id"),
                {"id": str(escenario.actividad_id)},
            )
        ).first()
        n_registros = (
            await conn.execute(
                text(
                    "select count(*) from registro_avance where actividad_id = :id"
                ),
                {"id": str(escenario.actividad_id)},
            )
        ).scalar_one()
    await admin.dispose()

    assert actividad is not None
    assert actividad.cant_ejecutada == Decimal("0")  # sin tocar
    assert n_registros == 0


async def test_actividad_bloqueada_impide_capturar(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        await conn.execute(
            text("update actividad set bloqueada = true where id = :id"),
            {"id": str(escenario.actividad_id)},
        )
    await admin.dispose()

    from obractrl.application.casos_uso.capturar_avance import ActividadBloqueada

    with pytest.raises(ActividadBloqueada):
        await _ejecutar(
            contexto_residente,
            ComandoCapturarAvance(
                actividad_id=escenario.actividad_id,
                usuario_id=escenario.residente_id,
                cant_ejecutada=Decimal("10"),
            ),
        )


async def test_actividad_fuera_de_alcance_da_no_encontrada(
    contexto_ajeno: ContextoSesion,
) -> None:
    with pytest.raises(ActividadNoEncontrada):
        await _ejecutar(
            contexto_ajeno,
            ComandoCapturarAvance(
                actividad_id=uuid.uuid4(),
                usuario_id=uuid.uuid4(),
                cant_ejecutada=Decimal("10"),
            ),
        )
