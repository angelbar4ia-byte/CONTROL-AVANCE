"""Repositorio de obras contra Postgres real (§7.2, §7.4).

El caso interesante es `arbol_prototipo`: `orden` solo es comparable entre
hermanos, así que la prueba arma un árbol donde un `ORDER BY orden` plano
daría el orden equivocado, para confirmar que el CTE recursivo sí hace un
recorrido en profundidad padre-antes-que-hijos.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.repos.obras_sql import RepositorioObrasSQL
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario


async def test_obtener_y_actualizar_avance(
    escenario: Escenario,
    contexto_residente: ContextoSesion,
    contexto_control: ContextoSesion,
) -> None:
    """Lectura y escritura de `obra` tienen alcance distinto (§5.1): el
    Residente lee su propia obra, pero solo Control de obra la actualiza —
    la política `obra_update` exige `app.es_config()`."""
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioObrasSQL(sesion)
        fila = await repo.obtener(escenario.obra_id)
        assert fila is not None
        assert fila["clave"] == "OBRA 01"
        assert fila["avance_pct"] == Decimal("0")

    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioObrasSQL(sesion)
        await repo.actualizar_avance(escenario.obra_id, Decimal("42.50"))
        await sesion.commit()

    # `commit()` cierra la transacción donde vivía el `SET LOCAL app.*`
    # (§12.4): una sesión nueva es lo que haría una petición real de
    # seguimiento, así que la relectura abre su propio `sesion_con_rls`.
    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioObrasSQL(sesion)
        fila = await repo.obtener(escenario.obra_id)

    assert fila is not None
    assert fila["avance_pct"] == Decimal("42.50")


async def test_arbol_prototipo_recorre_en_profundidad(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    """Árbol deliberadamente adverso a un `ORDER BY orden` plano:

        Etapa B (orden=2)
          └─ Concepto B1 (orden=1)
        Etapa A (orden=1)
          └─ Concepto A1 (orden=1)

    `orden` por sí solo (sin jerarquía) pondría "Concepto B1" antes que
    "Etapa A" (1 < 2 en la columna orden de B1 vs... en realidad ambos son
    distintos niveles, así que un ORDER BY orden global mezclaría niveles).
    El resultado correcto es: Etapa A, Concepto A1, Etapa B, Concepto B1.
    """
    etapa_a, etapa_b = uuid.uuid4(), uuid.uuid4()
    concepto_a1, concepto_b1 = uuid.uuid4(), uuid.uuid4()

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        for nid, parent, orden, nombre in [
            (etapa_b, None, 2, "Etapa B"),
            (etapa_a, None, 1, "Etapa A"),
            (concepto_b1, etapa_b, 1, "Concepto B1"),
            (concepto_a1, etapa_a, 1, "Concepto A1"),
        ]:
            await conn.execute(
                text(
                    """
                    insert into prototipo_nodo
                        (id, org_id, prototipo_id, parent_id, tipo, nombre, orden)
                    values
                        (:id, :org, :prototipo, :parent, 'etapa', :nombre, :orden)
                    """
                ),
                {
                    "id": str(nid),
                    "org": str(escenario.org_id),
                    "prototipo": str(escenario.prototipo_id),
                    "parent": str(parent) if parent else None,
                    "nombre": nombre,
                    "orden": orden,
                },
            )
    await admin.dispose()

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioObrasSQL(sesion)
        nodos = await repo.arbol_prototipo(escenario.prototipo_id)

    nombres = [n["nombre"] for n in nodos]
    assert nombres == ["Etapa A", "Concepto A1", "Etapa B", "Concepto B1"]
