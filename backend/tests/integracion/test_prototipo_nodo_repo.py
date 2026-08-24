"""`RepositorioPrototipoNodoSQL.arbol` contra Postgres real (§7.4).

Mismo caso interesante que `RepositorioObras.arbol_prototipo`
(`test_obras_repo.py`): `orden` solo es comparable entre hermanos, así que
la prueba arma un árbol donde un `ORDER BY orden` plano daría el orden
equivocado, para confirmar que el CTE recursivo de este repo (una copia a
propósito del mismo patrón, no una reexportación — son dos contextos
distintos, §11.1) también hace el recorrido en profundidad
padre-antes-que-hijos.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.repos.prototipo_nodo_sql import RepositorioPrototipoNodoSQL
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario


async def test_arbol_recorre_en_profundidad_padre_antes_que_hijos(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    """Nivel B (orden=2) con Etapa B1 (orden=1) y Nivel A (orden=1) con
    Etapa A1 (orden=1): un `ORDER BY orden` plano mezclaría los dos
    niveles. El resultado correcto es Nivel A, Etapa A1, Nivel B, Etapa B1.
    """
    nivel_a, nivel_b = uuid.uuid4(), uuid.uuid4()
    etapa_a1, etapa_b1 = uuid.uuid4(), uuid.uuid4()

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        for nid, parent, tipo, orden, nombre in [
            (nivel_b, None, "nivel", 2, "Nivel B"),
            (nivel_a, None, "nivel", 1, "Nivel A"),
            (etapa_b1, nivel_b, "etapa", 1, "Etapa B1"),
            (etapa_a1, nivel_a, "etapa", 1, "Etapa A1"),
        ]:
            await conn.execute(
                text(
                    """
                    insert into prototipo_nodo
                        (id, org_id, prototipo_id, parent_id, tipo, nombre, orden)
                    values
                        (:id, :org, :prototipo, :parent, cast(:tipo as tipo_prototipo_nodo),
                         :nombre, :orden)
                    """
                ),
                {
                    "id": str(nid),
                    "org": str(escenario.org_id),
                    "prototipo": str(escenario.prototipo_id),
                    "parent": str(parent) if parent else None,
                    "tipo": tipo,
                    "nombre": nombre,
                    "orden": orden,
                },
            )
    await admin.dispose()

    async with sesion_con_rls(contexto_residente) as sesion:
        nodos = await RepositorioPrototipoNodoSQL(sesion).arbol(escenario.prototipo_id)

    nombres = [n["nombre"] for n in nodos]
    assert nombres == ["Nivel A", "Etapa A1", "Nivel B", "Etapa B1"]

    raiz = next(n for n in nodos if n["nombre"] == "Nivel A")
    assert raiz["parent_id"] is None
    hijo = next(n for n in nodos if n["nombre"] == "Etapa A1")
    assert hijo["parent_id"] == nivel_a


async def test_arbol_de_un_prototipo_sin_ingenieria_cargada_es_vacio(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        nodos = await RepositorioPrototipoNodoSQL(sesion).arbol(escenario.prototipo_id)
    assert nodos == []
