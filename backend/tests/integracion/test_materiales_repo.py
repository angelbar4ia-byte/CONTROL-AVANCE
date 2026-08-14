"""Repositorio de materiales contra Postgres real (§7.7, §10.5, §12.4).

Igual que `test_cierres_repo.py`: no repite `tests/domain/test_materiales.py`
(la regla pura del signo), sino que prueba que el SQL respeta RLS —
`motivo_almacen` por organización, `salida_almacen` por obra— y que
`v_consumo_vs_presupuesto` se lee acotada por `obra_id`, como exige
la vista sin RLS propia (§10.5).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.repos.materiales_sql import RepositorioMaterialesSQL
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario


@dataclass(frozen=True, slots=True)
class Catalogos:
    """Insumo + motivos de almacén mínimos para probar salidas (§10.5)."""

    insumo_id: uuid.UUID
    motivo_salida_id: uuid.UUID  # signo -1, bucket 'salidas'
    motivo_ingreso_id: uuid.UUID  # signo +1, bucket 'ingresos'


@pytest.fixture
async def catalogos(escenario: Escenario) -> AsyncIterator[Catalogos]:
    """Inserta un insumo y dos motivos en la misma org del `escenario`.

    Se limpian solos: cascada de `organizacion(id) on delete cascade` desde
    el fixture `escenario`.
    """
    engine = create_async_engine(DATABASE_URL_ADMIN)
    insumo = uuid.uuid4()
    motivo_salida = uuid.uuid4()
    motivo_ingreso = uuid.uuid4()

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "insert into insumo (id, org_id, tipo, clave, descripcion, costo_base) "
                "values (:id, :org, 'material', 'CEM-01', 'Cemento gris', 250)"
            ),
            {"id": str(insumo), "org": str(escenario.org_id)},
        )
        await conn.execute(
            text(
                "insert into motivo_almacen (id, org_id, clave, descripcion, signo, bucket) "
                "values (:id, :org, 'SALIDA-PROD', 'Salida para producción', -1, 'salidas')"
            ),
            {"id": str(motivo_salida), "org": str(escenario.org_id)},
        )
        await conn.execute(
            text(
                "insert into motivo_almacen (id, org_id, clave, descripcion, signo, bucket) "
                "values (:id, :org, 'RECEPCION', 'Recepción de material', 1, 'ingresos')"
            ),
            {"id": str(motivo_ingreso), "org": str(escenario.org_id)},
        )
    await engine.dispose()

    yield Catalogos(
        insumo_id=insumo, motivo_salida_id=motivo_salida, motivo_ingreso_id=motivo_ingreso
    )


async def test_obtener_motivo_trae_signo_y_bucket(
    catalogos: Catalogos, contexto_residente: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioMaterialesSQL(sesion)
        motivo = await repo.obtener_motivo(catalogos.motivo_salida_id)

    assert motivo is not None
    assert motivo["signo"] == -1
    assert motivo["bucket"] == "salidas"


async def test_obtener_motivo_inexistente_da_none(contexto_residente: ContextoSesion) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioMaterialesSQL(sesion)
        assert await repo.obtener_motivo(uuid.uuid4()) is None


async def test_motivo_no_se_ve_fuera_de_la_organizacion(
    catalogos: Catalogos, contexto_ajeno: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_ajeno) as sesion:
        repo = RepositorioMaterialesSQL(sesion)
        assert await repo.obtener_motivo(catalogos.motivo_salida_id) is None


async def test_crear_y_listar_salidas_respetan_rls(
    escenario: Escenario, catalogos: Catalogos, contexto_residente: ContextoSesion,
    contexto_ajeno: ContextoSesion,
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioMaterialesSQL(sesion)
        salida_id = await repo.crear_salida(
            {
                "obra_id": escenario.obra_id,
                "insumo_id": catalogos.insumo_id,
                "motivo_id": catalogos.motivo_salida_id,
                "usuario_id": escenario.residente_id,
                "fecha": date(2026, 8, 10),
                "cantidad": Decimal("-5"),
                "costo": Decimal("-1250"),
            }
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioMaterialesSQL(sesion)
        todas = await repo.listar_salidas()
        de_la_obra = await repo.listar_salidas(obra_id=escenario.obra_id)
        de_otra_obra = await repo.listar_salidas(obra_id=uuid.uuid4())

    assert len(todas) == 1
    assert todas[0]["id"] == salida_id
    assert todas[0]["cantidad"] == Decimal("-5")
    assert todas[0]["costo"] == Decimal("-1250")
    assert len(de_la_obra) == 1
    assert de_otra_obra == []

    async with sesion_con_rls(contexto_ajeno) as sesion:
        repo = RepositorioMaterialesSQL(sesion)
        assert await repo.listar_salidas() == []


async def test_consumo_vs_presupuesto_filtra_por_obra_y_usa_costo_ultimo(
    escenario: Escenario, catalogos: Catalogos, contexto_residente: ContextoSesion
) -> None:
    """Sin explosión de CPU no hay `cant_teorica`; con una salida registrada,
    la vista sí trae la fila con `cant_real` y `costo_valuacion` desde el
    último costo capturado (§10.5, regla 3: "solo en almacén -> costo
    último")."""
    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "insert into salida_almacen "
                "(org_id, obra_id, insumo_id, motivo_id, usuario_id, fecha, "
                " cantidad, costo, costo_ultimo) "
                "values (:org, :obra, :insumo, :motivo, :usr, '2026-08-10', "
                " -5, -1250, 260)"
            ),
            {
                "org": str(escenario.org_id),
                "obra": str(escenario.obra_id),
                "insumo": str(catalogos.insumo_id),
                "motivo": str(catalogos.motivo_salida_id),
                "usr": str(escenario.residente_id),
            },
        )
    await admin.dispose()

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioMaterialesSQL(sesion)
        filas = await repo.consumo_vs_presupuesto(escenario.obra_id)
        filas_otra_obra = await repo.consumo_vs_presupuesto(uuid.uuid4())

    assert len(filas) == 1
    fila = filas[0]
    assert fila["insumo_id"] == catalogos.insumo_id
    assert fila["cant_teorica"] == Decimal("0")
    assert fila["cant_real"] == Decimal("5")
    assert fila["costo_valuacion"] == Decimal("260.0000")
    assert filas_otra_obra == []
