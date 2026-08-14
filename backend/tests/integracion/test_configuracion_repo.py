"""Repositorio de configurables contra Postgres real (§8.7).

El punto central: `valor` es `jsonb` y el dialecto asyncpg lo deserializa
solo —un número JSON llega como `float`/`int` de Python, no como texto—, así
que `decimal()` tiene que pasar por `str()` antes de `Decimal()` para no
arrastrar ruido binario. Esto se verificó empíricamente antes de escribir el
repo; esta prueba es la que lo deja fijo contra una regresión.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.repos.configuracion_sql import RepositorioConfiguracionSQL
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario


async def test_decimal_deserializa_jsonb_sin_ruido_binario(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "insert into configuracion (org_id, clave, valor, ambito) "
                "values (:org, 'iva_tasa', '0.16'::jsonb, 'global')"
            ),
            {"org": str(escenario.org_id)},
        )
    await admin.dispose()

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioConfiguracionSQL(sesion)
        valor = await repo.decimal("iva_tasa", default=Decimal("0.99"))

    assert valor == Decimal("0.16")
    # A propósito: Decimal(float) es justo el error que el repo evita.
    # Si esto empezara a fallar, `RepositorioConfiguracionSQL.decimal()`
    # dejó de pasar por str() antes de construir el Decimal.
    assert valor != Decimal(0.16)  # noqa: RUF032


async def test_decimal_usa_el_default_si_no_hay_fila(
    contexto_residente: ContextoSesion,
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioConfiguracionSQL(sesion)
        valor = await repo.decimal("clave_que_no_existe", default=Decimal("42"))

    assert valor == Decimal("42")


async def test_obtener_respeta_ambito_y_ambito_id(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "insert into configuracion (org_id, clave, valor, ambito) "
                "values (:org, 'umbral_desviacion', '0.05'::jsonb, 'global')"
            ),
            {"org": str(escenario.org_id)},
        )
        await conn.execute(
            text(
                "insert into configuracion "
                "(org_id, clave, valor, ambito, ambito_id) "
                "values (:org, 'umbral_desviacion', '0.10'::jsonb, "
                "'familia', :ambito_id)"
            ),
            {"org": str(escenario.org_id), "ambito_id": str(escenario.proyecto_id)},
        )
    await admin.dispose()

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioConfiguracionSQL(sesion)
        global_ = await repo.obtener("umbral_desviacion")
        especifico = await repo.obtener(
            "umbral_desviacion", ambito="familia", ambito_id=escenario.proyecto_id
        )

    assert global_ == 0.05
    assert especifico == 0.10
