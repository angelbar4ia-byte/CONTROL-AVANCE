"""`RegistrarSalidaAlmacen` de punta a punta: caso de uso + repo + Postgres real.

Spec §7.7 · §10.5 · §12.11 (Definition of Done).

`tests/domain/test_materiales.py` prueba la regla pura del signo; esto prueba
que el caso de uso —cableado igual que en `adapters/api/casos_uso.py`— la
aplica contra la base real: lee el motivo, valida el signo y solo entonces
inserta el movimiento.
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
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL
from obractrl.application.casos_uso.registrar_salida_almacen import (
    ComandoRegistrarSalida,
    MotivoAlmacenNoEncontrado,
    RegistrarSalidaAlmacen,
)
from obractrl.domain.materiales.reglas import ErrorDeMaterial
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario


@dataclass(frozen=True, slots=True)
class Catalogos:
    """Insumo + motivo de salida mínimos (§10.5). Igual que en
    `test_materiales_repo.py`, duplicado a propósito: cada archivo de
    integración arma su propio fixture, sin importar entre sí."""

    insumo_id: uuid.UUID
    motivo_salida_id: uuid.UUID  # signo -1, bucket 'salidas'


@pytest.fixture
async def catalogos(escenario: Escenario) -> AsyncIterator[Catalogos]:
    engine = create_async_engine(DATABASE_URL_ADMIN)
    insumo = uuid.uuid4()
    motivo_salida = uuid.uuid4()

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
    await engine.dispose()

    yield Catalogos(insumo_id=insumo, motivo_salida_id=motivo_salida)


async def test_registra_la_salida_cuando_el_signo_coincide(
    escenario: Escenario, catalogos: Catalogos, contexto_residente: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        caso_uso = RegistrarSalidaAlmacen(
            materiales=RepositorioMaterialesSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        )
        resultado = await caso_uso.ejecutar(
            ComandoRegistrarSalida(
                obra_id=escenario.obra_id,
                insumo_id=catalogos.insumo_id,
                motivo_id=catalogos.motivo_salida_id,  # signo -1
                cantidad=Decimal("-10"),
                costo=Decimal("-2500"),
                fecha=date(2026, 8, 10),
                usuario_id=escenario.residente_id,
            )
        )

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        fila = (
            await conn.execute(
                text("select cantidad, costo, obra_id from salida_almacen where id = :id"),
                {"id": str(resultado.id)},
            )
        ).first()
    await admin.dispose()

    assert fila is not None
    assert fila.cantidad == Decimal("-10")
    assert fila.costo == Decimal("-2500")
    assert fila.obra_id == escenario.obra_id


async def test_signo_inconsistente_no_inserta_nada(
    escenario: Escenario, catalogos: Catalogos, contexto_residente: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        caso_uso = RegistrarSalidaAlmacen(
            materiales=RepositorioMaterialesSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        )
        with pytest.raises(ErrorDeMaterial, match="signo"):
            await caso_uso.ejecutar(
                ComandoRegistrarSalida(
                    obra_id=escenario.obra_id,
                    insumo_id=catalogos.insumo_id,
                    motivo_id=catalogos.motivo_salida_id,  # signo -1
                    cantidad=Decimal("10"),  # positivo: inconsistente
                    costo=Decimal("2500"),
                    fecha=date(2026, 8, 10),
                    usuario_id=escenario.residente_id,
                )
            )

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioMaterialesSQL(sesion)
        assert await repo.listar_salidas(obra_id=escenario.obra_id) == []


async def test_motivo_inexistente_da_no_encontrado(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        caso_uso = RegistrarSalidaAlmacen(
            materiales=RepositorioMaterialesSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        )
        with pytest.raises(MotivoAlmacenNoEncontrado):
            await caso_uso.ejecutar(
                ComandoRegistrarSalida(
                    obra_id=escenario.obra_id,
                    insumo_id=uuid.uuid4(),
                    motivo_id=uuid.uuid4(),
                    cantidad=Decimal("-10"),
                    costo=Decimal("-2500"),
                    fecha=date(2026, 8, 10),
                    usuario_id=escenario.residente_id,
                )
            )
