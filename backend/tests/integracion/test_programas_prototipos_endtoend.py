"""`scripts/cargar_programas_prototipos.py` de punta a punta contra Postgres
real (§7.5, Paso 4 del plan del rollout) — la pieza que faltaba:
`test_programa_base_endtoend.py` ya prueba el cargador de archivo
(`PROGRAMA_ZAFIRO.xlsx`), pero solo para Zafiro, el único prototipo con
vínculos nativos. Esta prueba sube `PROGRAMAS-PROTOTIPOS.csv` —el archivo
con la red resuelta de los 7— por el camino directo que el plan exige: sin
`TipoCarga`, llamando a `AplicadorProgramaBase.aplicar` tal cual lo hace el
script.

Reusa el mismo rollout real de `test_cargas_endtoend.py::
test_el_rollout_real_completo_sube_presupuesto_trabajos_y_cpu_matriz` para
tener los 7 prototipos y su árbol de presupuesto ya en la base antes de
cargar su programa."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.domain.shared.diccionario import TipoCarga
from obractrl.infrastructure.db.sesion import sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, ContextoSesion, Escenario
from tests.integracion.test_cargas_endtoend import (
    _CLAVES_PROTOTIPOS_REALES,
    _CPU_MATRIZ_OPUS_CSV,
    _PRESUPUESTO_OPUS_CSV,
    _TRABAJOS_OPUS_CSV,
    _archivo_presupuesto_opus_real,
    _archivo_prototipos,
    _cargar,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/, para `scripts`
from scripts.cargar_programas_prototipos import (  # noqa: E402
    cargar_programas_prototipos,
)

_PROGRAMAS_PROTOTIPOS_CSV = Path(
    "/home/user/cerebro-erp-construccion/1-mundo/programas/PROGRAMAS-PROTOTIPOS.csv"
)

pytestmark = pytest.mark.skipif(
    not (
        _PRESUPUESTO_OPUS_CSV.exists()
        and _CPU_MATRIZ_OPUS_CSV.exists()
        and _TRABAJOS_OPUS_CSV.exists()
        and _PROGRAMAS_PROTOTIPOS_CSV.exists()
    ),
    reason="Archivos reales del exportador de OPUS no disponibles en este entorno.",
)


async def _subir_rollout_de_presupuesto(contexto: ContextoSesion) -> None:
    """Los 7 prototipos reales y su árbol de presupuesto — mismo paso 0/1 que
    `test_el_rollout_real_completo_sube_presupuesto_trabajos_y_cpu_matriz`,
    sin trabajos ni CPU (el programa base no los necesita)."""
    await _cargar(
        contexto,
        TipoCarga.PROTOTIPOS,
        _archivo_prototipos(
            [["PROY", clave, f"Prototipo {clave}", "", "", ""] for clave in _CLAVES_PROTOTIPOS_REALES]
        ),
    )
    resultado = await _cargar(contexto, TipoCarga.PRESUPUESTO, _archivo_presupuesto_opus_real())
    assert resultado.resumen.errores == 0


async def _conteo_programa_base_por_prototipo(org_id: uuid.UUID) -> dict[str, int]:
    engine = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with engine.begin() as conn:
            filas = (
                await conn.execute(
                    text(
                        "select pr.clave, count(pbi.id) as n_items "
                        "from programa_base pb "
                        "join prototipo pr on pr.id = pb.prototipo_id "
                        "join programa_base_item pbi on pbi.programa_base_id = pb.id "
                        "where pb.org_id = :org "
                        "group by pr.clave"
                    ),
                    {"org": str(org_id)},
                )
            ).mappings().all()
    finally:
        await engine.dispose()
    return {str(f["clave"]): f["n_items"] for f in filas}


async def test_carga_el_programa_base_de_los_siete_prototipos(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    await _subir_rollout_de_presupuesto(contexto_control)

    async with sesion_con_rls(contexto_control) as sesion:
        cargados = await cargar_programas_prototipos(
            sesion, ruta=_PROGRAMAS_PROTOTIPOS_CSV
        )
        await sesion.commit()

    assert set(cargados) == set(_CLAVES_PROTOTIPOS_REALES)

    conteo = await _conteo_programa_base_por_prototipo(escenario.org_id)
    assert set(conteo) == set(_CLAVES_PROTOTIPOS_REALES)
    # Todas con cientos de items: ninguna cayó en "0 items" por no cruzar
    # ningún `prototipo_nodo` (el archivo del programa y el del presupuesto
    # describen, en lo esencial, el mismo árbol).
    assert all(n > 100 for n in conteo.values()), conteo


async def test_dry_run_no_deja_nada_escrito(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """`dry_run=True` llega hasta `AplicadorProgramaBase.aplicar`, que por
    diseño no llama a `CrearProgramaBase.ejecutar` en ese caso (ver su
    docstring) — nunca se abre la unidad de trabajo que escribe de verdad,
    así que no hay nada que un `rollback()` del lado de afuera tenga que
    deshacer."""
    await _subir_rollout_de_presupuesto(contexto_control)

    async with sesion_con_rls(contexto_control) as sesion:
        cargados = await cargar_programas_prototipos(
            sesion, ruta=_PROGRAMAS_PROTOTIPOS_CSV, dry_run=True
        )

    assert len(cargados) == 7
    conteo = await _conteo_programa_base_por_prototipo(escenario.org_id)
    assert conteo == {}
