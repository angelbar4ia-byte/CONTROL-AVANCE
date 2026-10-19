"""Preview de un ensamble (`ExplotarEnsamble`) contra Postgres real (skill
`erp-parametrico` §4, §6).

Lo que aquí se prueba y no en `tests/domain/test_ensamble.py`: que el caso
de uso resuelve el CPU vigente de cada concepto (capturado, sin APU de por
medio, igual que `GenerarDesdeEnsamble`) y que `factor` escala el preview
exactamente como escala lo que `GenerarDesdeEnsamble` terminaría
escribiendo — las dos comparten la misma resolución de precios a propósito.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.adapters.repos.conceptos_sql import RepositorioConceptosSQL
from obractrl.adapters.repos.ensambles_sql import RepositorioEnsamblesSQL
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL
from obractrl.application.casos_uso.gestionar_ensamble import (
    ComandoExtraerEnsamble,
    EnsambleNoEncontrado,
    ExplotarEnsamble,
    ExtraerEnsamble,
)
from obractrl.domain.catalogos.ensamble import RenglonEnsamble
from obractrl.domain.shared.diccionario import OrigenCantidadEnsamble
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import Escenario


async def _sembrar_ensamble(sesion: AsyncSession) -> None:
    """RECAMARA-A: 4×EST-MURO, CPU capturado 100.00/40.00 (sin APU)."""
    conceptos = RepositorioConceptosSQL(sesion)
    muro = await conceptos.crear(
        {"tipo": "concepto", "clave": "EST-MURO", "descripcion": "Muro de block"}
    )
    await conceptos.publicar_version_cpu(
        muro,
        version=1,
        precio_unitario=Decimal("100.00"),
        precio_destajo=Decimal("40.00"),
        variante=None,
        retirar=[],
    )
    await ExtraerEnsamble(
        ensambles=RepositorioEnsamblesSQL(sesion),
        conceptos=conceptos,
        uow=UnidadDeTrabajoSQL(sesion),
    ).ejecutar(
        ComandoExtraerEnsamble(
            clave="RECAMARA-A",
            nombre="Recámara tipo A",
            renglones=[
                RenglonEnsamble(
                    cantidad=Decimal("4"),
                    origen=OrigenCantidadEnsamble.HEREDADA_CONCEPTO,
                    clave_concepto="EST-MURO",
                )
            ],
        )
    )


async def test_explotar_sin_factor_da_el_costo_de_una_instancia(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_control) as sesion:
        await _sembrar_ensamble(sesion)
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        caso_uso = ExplotarEnsamble(
            ensambles=RepositorioEnsamblesSQL(sesion), conceptos=RepositorioConceptosSQL(sesion)
        )
        calculada = await caso_uso.ejecutar("RECAMARA-A")

    assert calculada.precio.total.monto == Decimal("400.00")  # 4 × 100
    assert calculada.precio.destajo.monto == Decimal("160.00")  # 4 × 40


async def test_el_factor_escala_el_preview_igual_que_generar(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_control) as sesion:
        await _sembrar_ensamble(sesion)
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        caso_uso = ExplotarEnsamble(
            ensambles=RepositorioEnsamblesSQL(sesion), conceptos=RepositorioConceptosSQL(sesion)
        )
        calculada = await caso_uso.ejecutar("RECAMARA-A", factor=Decimal(3))

    assert calculada.precio.total.monto == Decimal("1200.00")  # 3 × 400
    muro = next(linea for linea in calculada.lineas if linea.referencia == "EST-MURO")
    assert muro.cantidad == Decimal("12.000000")  # 4 × 3


async def test_ensamble_inexistente_se_rechaza(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    with pytest.raises(EnsambleNoEncontrado):
        async with sesion_con_rls(contexto_control) as sesion:
            caso_uso = ExplotarEnsamble(
                ensambles=RepositorioEnsamblesSQL(sesion),
                conceptos=RepositorioConceptosSQL(sesion),
            )
            await caso_uso.ejecutar("NO-EXISTE")
