"""CPU y explosión de punta a punta contra Postgres real (§7.3, §10.8).

Arma un APU con la forma del §7.3 —concepto → auxiliar → insumos— y lo
recorre por los casos de uso reales. Lo que aquí se prueba y no en
`tests/domain/test_apu.py`: que el CTE recursivo de
`composicion_recursiva` trae **todo** el árbol, que sobrevive a un ciclo sin
colgarse, y que publicar una versión deja una sola vigente en la base.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.adapters.repos.conceptos_sql import RepositorioConceptosSQL
from obractrl.adapters.repos.insumos_sql import RepositorioInsumosSQL
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL
from obractrl.application.casos_uso.calcular_cpu import (
    ComandoPublicarVersionCPU,
    ConceptoNoEncontrado,
    ExplotarConcepto,
    ObtenerCPU,
    PublicarVersionCPU,
)
from obractrl.domain.catalogos.apu import CicloEnExplosion
from obractrl.domain.shared.valores import Dinero
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import Escenario


async def _explosion(
    sesion: AsyncSession,
    *,
    concepto_id: UUID,
    categoria: str,
    cantidad: str,
    costo_unitario: str = "0",
    insumo_id: UUID | None = None,
    concepto_hijo_id: UUID | None = None,
    orden: int = 0,
) -> None:
    await sesion.execute(
        text(
            """
            insert into explosion
                (org_id, concepto_id, tipo_hijo, insumo_id, concepto_hijo_id,
                 categoria, cantidad, costo_unitario, orden)
            values (cast(current_setting('app.org_id') as uuid),
                    :concepto_id,
                    cast(:tipo_hijo as tipo_hijo_explosion),
                    cast(:insumo_id as uuid), cast(:concepto_hijo_id as uuid),
                    cast(:categoria as categoria_explosion),
                    cast(:cantidad as numeric), cast(:costo_unitario as numeric),
                    :orden)
            """
        ),
        {
            "concepto_id": str(concepto_id),
            "tipo_hijo": "insumo" if insumo_id else "concepto",
            "insumo_id": str(insumo_id) if insumo_id else None,
            "concepto_hijo_id": str(concepto_hijo_id) if concepto_hijo_id else None,
            "categoria": categoria,
            "cantidad": cantidad,
            "costo_unitario": costo_unitario,
            "orden": orden,
        },
    )


async def _sembrar_apu(sesion: AsyncSession) -> dict[str, UUID]:
    """EST-010 = 10 MAT-BLK + 0.5 AUX-MOR + 1 MOA-ALB (el ejemplo del §7.3)."""
    insumos = RepositorioInsumosSQL(sesion)
    conceptos = RepositorioConceptosSQL(sesion)

    block = await insumos.crear(
        {"tipo": "material", "clave": "MAT-BLK", "descripcion": "Block"}
    )
    cemento = await insumos.crear(
        {
            "tipo": "material",
            "clave": "MAT-CEM",
            "descripcion": "Cemento",
            # Sin PU en la fila del APU, el costo lo pone el catálogo (§10.1).
            "costo_base": Decimal("50.00"),
        }
    )
    albanil = await insumos.crear(
        {"tipo": "mano_obra", "clave": "MOA-ALB", "descripcion": "Albañil"}
    )
    ayudante = await insumos.crear(
        {"tipo": "mano_obra", "clave": "MOA-AYU", "descripcion": "Ayudante"}
    )

    concepto = await conceptos.crear(
        {"tipo": "concepto", "clave": "EST-010", "descripcion": "Muro de block"}
    )
    auxiliar = await conceptos.crear(
        {"tipo": "auxiliar", "clave": "AUX-MOR", "descripcion": "Mortero"}
    )

    await _explosion(
        sesion,
        concepto_id=concepto,
        insumo_id=block,
        categoria="material",
        cantidad="10",
        costo_unitario="20.00",
        orden=1,
    )
    await _explosion(
        sesion,
        concepto_id=concepto,
        concepto_hijo_id=auxiliar,
        categoria="auxiliar",
        cantidad="0.5",
        orden=2,
    )
    await _explosion(
        sesion,
        concepto_id=concepto,
        insumo_id=albanil,
        categoria="mano_obra",
        cantidad="1",
        costo_unitario="100.00",
        orden=3,
    )
    await _explosion(
        sesion,
        concepto_id=auxiliar,
        insumo_id=cemento,
        categoria="material",
        cantidad="4",
        orden=1,  # sin costo_unitario: cae al costo_base del catálogo
    )
    await _explosion(
        sesion,
        concepto_id=auxiliar,
        insumo_id=ayudante,
        categoria="mano_obra",
        cantidad="2",
        costo_unitario="30.00",
        orden=2,
    )
    return {"concepto": concepto, "auxiliar": auxiliar}


async def test_explosion_recorre_el_arbol_completo(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_control) as sesion:
        ids = await _sembrar_apu(sesion)
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        caso_uso = ExplotarConcepto(conceptos=RepositorioConceptosSQL(sesion))
        calculada = await caso_uso.ejecutar(ids["concepto"])

    # El CTE recursivo trae también los nietos, en recorrido padre→hijos.
    assert [(linea.nivel, linea.referencia) for linea in calculada.lineas] == [
        (1, "MAT-BLK"),
        (1, "AUX-MOR"),
        (2, "MAT-CEM"),
        (2, "MOA-AYU"),
        (1, "MOA-ALB"),
    ]
    # El cemento no trae PU en la fila: usa el costo del catálogo (§10.1).
    cemento = next(linea for linea in calculada.lineas if linea.referencia == "MAT-CEM")
    assert cemento.costo_unitario == Decimal("50.0000")
    assert cemento.cantidad == Decimal("2.000000")  # 4 × 0.5


async def test_el_cpu_desglosa_el_destajo_del_auxiliar(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_control) as sesion:
        ids = await _sembrar_apu(sesion)
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        caso_uso = ObtenerCPU(conceptos=RepositorioConceptosSQL(sesion))
        cpu = await caso_uso.ejecutar(ids["concepto"])

    # AUX-MOR = 4×50 + 2×30 = 260 → EST-010 = 200 + 130 + 100 = 430.
    assert cpu.calculado.total == Dinero("430.00")
    # Destajo = 0.5 × 60 (MO dentro del auxiliar) + 100 = 130 (§7.3).
    assert cpu.calculado.destajo == Dinero("130.00")
    assert cpu.vigente is None  # aún no se publica ninguna versión
    assert cpu.historial == ()


async def test_publicar_deja_una_sola_version_vigente(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_control) as sesion:
        ids = await _sembrar_apu(sesion)
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        caso_uso = PublicarVersionCPU(
            conceptos=RepositorioConceptosSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
        )
        primera = await caso_uso.ejecutar(
            ComandoPublicarVersionCPU(concepto_id=ids["concepto"])
        )

    assert primera.version.version == 1
    assert primera.retiradas == ()
    # Se publicó lo calculado de la explosión, no un número capturado.
    assert primera.version.precio.total == Dinero("430.00")

    async with sesion_con_rls(contexto_control) as sesion:
        caso_uso = PublicarVersionCPU(
            conceptos=RepositorioConceptosSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
        )
        segunda = await caso_uso.ejecutar(
            ComandoPublicarVersionCPU(
                concepto_id=ids["concepto"],
                precio_unitario=Decimal("500.00"),
                precio_destajo=Decimal("150.00"),
            )
        )

    assert (segunda.version.version, segunda.retiradas) == (2, (1,))

    async with sesion_con_rls(contexto_control) as sesion:
        cpu = await ObtenerCPU(conceptos=RepositorioConceptosSQL(sesion)).ejecutar(
            ids["concepto"]
        )

    assert cpu.vigente is not None
    assert cpu.vigente.version == 2
    assert cpu.vigente.precio.total == Dinero("500.00")
    # La v1 sigue en el histórico: comparar y restaurar (§10.8).
    assert [v.version for v in cpu.historial] == [1, 2]
    # El calculado de hoy delata que el vigente se capturó a mano.
    assert cpu.calculado.total == Dinero("430.00")


async def test_un_ciclo_indirecto_no_cuelga_al_cte(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """A→B→A pasa el `CHECK` de la base (solo impide el ciclo directo), así
    que el corte por camino del CTE es lo único que evita la recursión
    infinita; el error legible lo pone el dominio."""
    async with sesion_con_rls(contexto_control) as sesion:
        conceptos = RepositorioConceptosSQL(sesion)
        a = await conceptos.crear(
            {"tipo": "concepto", "clave": "EST-A", "descripcion": "A"}
        )
        b = await conceptos.crear(
            {"tipo": "auxiliar", "clave": "AUX-B", "descripcion": "B"}
        )
        await _explosion(
            sesion, concepto_id=a, concepto_hijo_id=b, categoria="auxiliar", cantidad="1"
        )
        await _explosion(
            sesion, concepto_id=b, concepto_hijo_id=a, categoria="auxiliar", cantidad="1"
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        # El CTE termina y devuelve las dos aristas, incluida la que cierra
        # el ciclo: detectarlo es del dominio.
        filas = await RepositorioConceptosSQL(sesion).composicion_recursiva(a)
        assert len(filas) == 2

        caso_uso = ExplotarConcepto(conceptos=RepositorioConceptosSQL(sesion))
        with pytest.raises(CicloEnExplosion) as exc:
            await caso_uso.ejecutar(a)

    assert exc.value.camino == ["EST-A", "AUX-B", "EST-A"]


async def test_un_concepto_de_otra_organizacion_no_existe(
    escenario: Escenario,
    contexto_control: ContextoSesion,
    contexto_ajeno: ContextoSesion,
) -> None:
    """RLS hace indistinguible "no existe" de "no lo puedes ver" (§12.4)."""
    async with sesion_con_rls(contexto_control) as sesion:
        ids = await _sembrar_apu(sesion)
        await sesion.commit()

    async with sesion_con_rls(contexto_ajeno) as sesion:
        caso_uso = ExplotarConcepto(conceptos=RepositorioConceptosSQL(sesion))
        with pytest.raises(ConceptoNoEncontrado):
            await caso_uso.ejecutar(ids["concepto"])
