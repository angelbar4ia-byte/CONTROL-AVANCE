"""Revisión física de punta a punta: caso de uso + repo + Postgres real.

Spec §7.8 (`RevisionFisica`) · §11.2 ("Revisión física (móvil · Control de
obra)") · §12.4 (RLS) · §12.11 (Definition of Done).

`tests/domain/test_revisiones.py` prueba las reglas puras; esto prueba que el
caso de uso —cableado exactamente como en `adapters/api/casos_uso.py`— las
aplica contra la base real: la revisión queda escrita con sus fotos en jsonb,
el filtro por obra no revienta con `AmbiguousParameterError` cuando llega
vacío, y RLS acota lectura y escritura.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.api.casos_uso import obtener_registrar_revision_fisica
from obractrl.adapters.repos.revisiones_sql import RepositorioRevisionesSQL
from obractrl.application.casos_uso.registrar_revision_fisica import (
    ComandoRegistrarRevision,
    ErrorDeRevision,
)
from obractrl.domain.shared.diccionario import Rol
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario

FECHA = date(2026, 8, 14)


async def _registrar(
    ctx: ContextoSesion,
    escenario: Escenario,
    *,
    usuario_id: uuid.UUID,
    rol: Rol = Rol.CONTROL_OBRA,
    fotos: list[str] | None = None,
    comentario: str | None = None,
    calidad: int | None = None,
    actividad_id: uuid.UUID | None = None,
) -> uuid.UUID:
    async with sesion_con_rls(ctx) as sesion:
        registrada = await obtener_registrar_revision_fisica(sesion).ejecutar(
            ComandoRegistrarRevision(
                obra_id=escenario.obra_id,
                usuario_id=usuario_id,
                rol=rol,
                fecha=FECHA,
                fotos=fotos or [],
                comentario=comentario,
                calidad=calidad,
                actividad_id=actividad_id,
            )
        )
        return registrada.id


async def test_registra_la_revision_con_sus_fotos_y_calidad(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    revision_id = await _registrar(
        contexto_control,
        escenario,
        usuario_id=escenario.control_id,
        fotos=["org/obras/foto-1.jpg", "org/obras/foto-2.jpg"],
        comentario="Acabados con rebaba en el muro norte",
        calidad=3,
        actividad_id=escenario.actividad_id,
    )

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        fila = (
            await conn.execute(
                text(
                    "select obra_id, actividad_id, usuario_id, fecha, fotos, "
                    "comentario, calidad, sync_status "
                    "from revision_fisica where id = :id"
                ),
                {"id": str(revision_id)},
            )
        ).first()
    await admin.dispose()

    assert fila is not None
    assert fila.obra_id == escenario.obra_id
    assert fila.actividad_id == escenario.actividad_id
    assert fila.usuario_id == escenario.control_id
    assert fila.fecha == FECHA
    assert fila.fotos == ["org/obras/foto-1.jpg", "org/obras/foto-2.jpg"]
    assert fila.calidad == 3
    # Lo que llega por HTTP ya está en Postgres; la cola offline del móvil es
    # la que usa los otros valores de `sync_status` (§12.2).
    assert fila.sync_status == "sincronizado"


async def test_una_revision_sin_calidad_ni_fotos_es_valida(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """El §7.8 declara `fotos` y `calidad` opcionales: la visita en sí ya es
    un hecho registrable."""
    revision_id = await _registrar(
        contexto_control, escenario, usuario_id=escenario.control_id
    )

    async with sesion_con_rls(contexto_control) as sesion:
        filas = await RepositorioRevisionesSQL(sesion).listar(
            obra_id=escenario.obra_id
        )

    revision = next(fila for fila in filas if fila["id"] == revision_id)
    assert revision["fotos"] == []
    assert revision["calidad"] is None
    assert revision["comentario"] is None


async def test_solo_control_de_obra_registra(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    """§11.2 pone la `(C)` sobre el alta; el dominio la aplica aunque la
    guarda HTTP faltara."""
    with pytest.raises(ErrorDeRevision, match="Solo Control de obra"):
        await _registrar(
            contexto_residente,
            escenario,
            usuario_id=escenario.residente_id,
            rol=Rol.RESIDENTE,
        )

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        total = (
            await conn.execute(
                text("select count(*) from revision_fisica where obra_id = :obra"),
                {"obra": str(escenario.obra_id)},
            )
        ).scalar_one()
    await admin.dispose()
    assert total == 0


async def test_listar_sin_filtro_no_revienta_por_parametro_ambiguo(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """`obra_id` opcional: el cast del lado `is null` es lo que evita el
    `AmbiguousParameterError` de asyncpg."""
    revision_id = await _registrar(
        contexto_control, escenario, usuario_id=escenario.control_id, calidad=5
    )

    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioRevisionesSQL(sesion)
        sin_filtro = await repo.listar()
        con_filtro = await repo.listar(obra_id=escenario.obra_id)
        de_otra_obra = await repo.listar(obra_id=uuid.uuid4())

    assert revision_id in {fila["id"] for fila in sin_filtro}
    assert [fila["id"] for fila in con_filtro] == [revision_id]
    assert de_otra_obra == []


async def test_una_org_ajena_no_ve_la_revision(
    escenario: Escenario,
    contexto_control: ContextoSesion,
    contexto_ajeno: ContextoSesion,
) -> None:
    """RLS: `revision_fisica_scope` acota por `obra_visible` (§12.4)."""
    await _registrar(contexto_control, escenario, usuario_id=escenario.control_id)

    async with sesion_con_rls(contexto_ajeno) as sesion:
        filas = await RepositorioRevisionesSQL(sesion).listar()
    assert filas == []
