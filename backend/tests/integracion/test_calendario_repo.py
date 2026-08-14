"""Repositorio del calendario maestro contra Postgres real (§3.1).

`app.generar_calendario()` (SQL) es quien materializa la tabla; este repo
solo la lee. La prueba de fondo es que ambas semanas —ordinaria y de obra—
resuelven correcto, y que sin calendario/ancla configurados el repo falla
explícito en vez de adivinar (`CalendarioNoConfigurado`).
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.repos.calendario_sql import (
    CalendarioNoConfigurado,
    RepositorioCalendarioSQL,
)
from obractrl.domain.shared.diccionario import TipoSemana
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario


async def test_semana_de_resuelve_ordinaria_y_obra(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        await conn.execute(
            text("select app.generar_calendario(cast(:org as uuid), 'ordinaria'::tipo_semana, 2026::smallint)"),
            {"org": str(escenario.org_id)},
        )
        await conn.execute(
            text("select app.generar_calendario(cast(:org as uuid), 'obra'::tipo_semana, 2026::smallint)"),
            {"org": str(escenario.org_id)},
        )
    await admin.dispose()

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioCalendarioSQL(sesion)
        semana_ord, anio_ord = await repo.semana_de(
            date(2026, 1, 9), TipoSemana.ORDINARIA
        )
        semana_obra, anio_obra = await repo.semana_de(
            date(2026, 1, 9), TipoSemana.OBRA
        )

    # 2026-01-09 es viernes: cae en la semana ordinaria 1 (lun 5 - dom 11) y
    # en la semana de obra 2 (jue 8 - mié 14) — semanas distintas para la
    # misma fecha, justo lo que exige tener dos calendarios separados (§3.1).
    assert (semana_ord, anio_ord) == (1, 2026)
    assert (semana_obra, anio_obra) == (2, 2026)


async def test_rango_de_semana_va_y_viene_con_semana_de(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        await conn.execute(
            text("select app.generar_calendario(cast(:org as uuid), 'obra'::tipo_semana, 2026::smallint)"),
            {"org": str(escenario.org_id)},
        )
    await admin.dispose()

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioCalendarioSQL(sesion)
        inicio, fin = await repo.rango_de_semana(5, 2026, TipoSemana.OBRA)
        semana, anio = await repo.semana_de(inicio, TipoSemana.OBRA)

    assert inicio.weekday() == 3  # jueves (§3.1)
    assert fin.weekday() == 2  # miércoles
    assert (semana, anio) == (5, 2026)


async def test_semana_activa_lee_el_ancla_del_admin(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "insert into ancla_semana (org_id, tipo, anio, semana) "
                "values (:org, 'obra', 2026, 21)"
            ),
            {"org": str(escenario.org_id)},
        )
    await admin.dispose()

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioCalendarioSQL(sesion)
        semana, anio = await repo.semana_activa(TipoSemana.OBRA)

    assert (semana, anio) == (21, 2026)


async def test_sin_calendario_falla_explicito_no_adivina(
    contexto_residente: ContextoSesion,
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioCalendarioSQL(sesion)
        with pytest.raises(CalendarioNoConfigurado):
            await repo.semana_de(date(2099, 1, 1), TipoSemana.OBRA)


async def test_sin_ancla_falla_explicito(
    contexto_residente: ContextoSesion,
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioCalendarioSQL(sesion)
        with pytest.raises(CalendarioNoConfigurado):
            await repo.semana_activa(TipoSemana.OBRA)
