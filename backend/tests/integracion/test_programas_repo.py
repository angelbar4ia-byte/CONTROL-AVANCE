"""Repositorio de programación contra Postgres real (§7.5, §12.4).

No repite `tests/domain/test_programacion.py`: aquí se prueba que el SQL
respeta RLS —`programa_base` es catálogo (escribe solo Control de obra),
`programa_obra` va por alcance de obra—, que el versionado retira el vigente
anterior sin violar los índices únicos parciales (`uq_programa_base_vigente`,
`uq_programa_obra_vigente`) y que el jsonb de `dependencias` va y vuelve
sin sorpresas.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.repos.programas_sql import (
    ProgramaNoModificado,
    RepositorioProgramasSQL,
)
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario


async def _nodo_prototipo(escenario: Escenario, nombre: str) -> uuid.UUID:
    """Un nodo 'etapa' del árbol WBS: no exige `concepto_id` (§7.4)."""
    nodo = uuid.uuid4()
    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "insert into prototipo_nodo (id, org_id, prototipo_id, tipo, nombre) "
                "values (:id, :org, :proto, 'etapa', :nombre)"
            ),
            {
                "id": str(nodo),
                "org": str(escenario.org_id),
                "proto": str(escenario.prototipo_id),
                "nombre": nombre,
            },
        )
    await admin.dispose()
    return nodo


async def test_crear_base_versiona_y_retira_el_vigente_anterior(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioProgramasSQL(sesion)
        primero = await repo.crear_base(
            {"prototipo_id": escenario.prototipo_id, "nombre": "v1"}
        )
        segundo = await repo.crear_base(
            {"prototipo_id": escenario.prototipo_id, "nombre": "v2"}
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioProgramasSQL(sesion)
        uno = await repo.obtener_base(primero)
        dos = await repo.obtener_base(segundo)
        vigentes = await repo.listar_bases(
            prototipo_id=escenario.prototipo_id, solo_vigentes=True
        )

    assert uno is not None and dos is not None
    assert (uno["version"], uno["vigente"]) == (1, False)
    assert (dos["version"], dos["vigente"]) == (2, True)
    assert [fila["id"] for fila in vigentes] == [segundo]


async def test_items_van_y_vuelven_con_su_jsonb(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    nodo_a = await _nodo_prototipo(escenario, "Cimentación")
    nodo_b = await _nodo_prototipo(escenario, "Estructura")

    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioProgramasSQL(sesion)
        base_id = await repo.crear_base({"prototipo_id": escenario.prototipo_id})
        await repo.agregar_items_base(
            base_id,
            [
                {
                    "prototipo_nodo_id": nodo_a,
                    "duracion_dias": Decimal("5"),
                    "dependencias": [],
                    "orden": 0,
                },
                {
                    "prototipo_nodo_id": nodo_b,
                    "duracion_dias": Decimal("3.5"),
                    "dependencias": [
                        {"ref": str(nodo_a), "tipo": "FS", "lag_dias": 2}
                    ],
                    "orden": 1,
                },
            ],
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        items = await RepositorioProgramasSQL(sesion).listar_items_base(base_id)

    assert [i["orden"] for i in items] == [0, 1]
    assert items[1]["duracion_dias"] == Decimal("3.50")
    assert items[1]["dependencias"] == [
        {"ref": str(nodo_a), "tipo": "FS", "lag_dias": 2}
    ]


async def test_items_base_vigente_solo_trae_los_del_vigente(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    nodo = await _nodo_prototipo(escenario, "Cimentación")

    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioProgramasSQL(sesion)
        vieja = await repo.crear_base({"prototipo_id": escenario.prototipo_id})
        await repo.agregar_items_base(
            vieja,
            [{"prototipo_nodo_id": nodo, "duracion_dias": Decimal("9"), "orden": 0}],
        )
        nueva = await repo.crear_base({"prototipo_id": escenario.prototipo_id})
        await repo.agregar_items_base(
            nueva,
            [{"prototipo_nodo_id": nodo, "duracion_dias": Decimal("4"), "orden": 0}],
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        items = await RepositorioProgramasSQL(sesion).items_base_vigente(
            escenario.prototipo_id
        )

    assert len(items) == 1
    assert items[0]["duracion_dias"] == Decimal("4.00")


async def test_residente_lee_el_catalogo_pero_no_lo_escribe(
    escenario: Escenario,
    contexto_control: ContextoSesion,
    contexto_residente: ContextoSesion,
) -> None:
    """`programa_base` es catálogo: lectura para la org, escritura solo para
    `app.es_config()` (§5.1, migración 0012)."""
    async with sesion_con_rls(contexto_control) as sesion:
        base_id = await RepositorioProgramasSQL(sesion).crear_base(
            {"prototipo_id": escenario.prototipo_id}
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_residente) as sesion:
        assert await RepositorioProgramasSQL(sesion).obtener_base(base_id) is not None

    with pytest.raises(Exception, match=r"(?i)row-level security|política"):
        async with sesion_con_rls(contexto_residente) as sesion:
            await RepositorioProgramasSQL(sesion).crear_base(
                {"prototipo_id": escenario.prototipo_id}
            )
            await sesion.commit()


async def test_una_org_ajena_no_ve_el_programa_base(
    escenario: Escenario,
    contexto_control: ContextoSesion,
    contexto_ajeno: ContextoSesion,
) -> None:
    async with sesion_con_rls(contexto_control) as sesion:
        base_id = await RepositorioProgramasSQL(sesion).crear_base(
            {"prototipo_id": escenario.prototipo_id}
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_ajeno) as sesion:
        assert await RepositorioProgramasSQL(sesion).obtener_base(base_id) is None


async def test_instanciar_versiona_el_programa_de_obra(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioProgramasSQL(sesion)
        uno = await repo.instanciar(escenario.obra_id, fecha_corte=date(2026, 3, 2))
        dos = await repo.instanciar(escenario.obra_id, fecha_corte=date(2026, 3, 9))
        await sesion.commit()

    assert (uno["version"], dos["version"]) == (1, 2)

    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioProgramasSQL(sesion)
        vigente = await repo.programa_vigente(escenario.obra_id)
        historial = await repo.listar_programas(escenario.obra_id)

    assert vigente is not None
    assert vigente["id"] == dos["id"]
    assert vigente["fecha_corte"] == date(2026, 3, 9)
    assert [fila["version"] for fila in historial] == [2, 1]


async def test_fijar_fecha_corte_persiste_y_exige_la_fila(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioProgramasSQL(sesion)
        programa = await repo.instanciar(escenario.obra_id, fecha_corte=None)
        await repo.fijar_fecha_corte(programa["id"], date(2026, 4, 1))
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        vigente = await RepositorioProgramasSQL(sesion).programa_vigente(
            escenario.obra_id
        )

    assert vigente is not None
    assert vigente["fecha_corte"] == date(2026, 4, 1)

    async with sesion_con_rls(contexto_control) as sesion:
        with pytest.raises(ProgramaNoModificado):
            await RepositorioProgramasSQL(sesion).fijar_fecha_corte(
                uuid.uuid4(), date(2026, 4, 1)
            )


async def test_una_org_ajena_no_ve_el_programa_de_obra(
    escenario: Escenario,
    contexto_control: ContextoSesion,
    contexto_ajeno: ContextoSesion,
) -> None:
    async with sesion_con_rls(contexto_control) as sesion:
        await RepositorioProgramasSQL(sesion).instanciar(
            escenario.obra_id, fecha_corte=None
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_ajeno) as sesion:
        repo = RepositorioProgramasSQL(sesion)
        assert await repo.programa_vigente(escenario.obra_id) is None
        assert await repo.listar_programas(escenario.obra_id) == []


# --- Calendario del cronograma (0040) -----------------------------------


async def test_la_plantilla_nace_en_semana_natural(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """Sin elección explícita manda el default de la columna.

    Es lo que garantiza que las plantillas que ya existían no cambiaran de
    comportamiento al aplicar la migración: los siete días hábiles son la
    aritmética de días corridos de siempre.
    """
    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioProgramasSQL(sesion)
        base_id = await repo.crear_base({"prototipo_id": escenario.prototipo_id})
        await sesion.commit()
        base = await repo.obtener_base(base_id)

    assert base is not None
    assert list(base["dias_habiles"]) == [1, 2, 3, 4, 5, 6, 7]


async def test_el_calendario_de_la_plantilla_va_y_vuelve(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """Lunes a sábado, la semana de obra: se guarda y `base_vigente` la lee."""
    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioProgramasSQL(sesion)
        await repo.crear_base(
            {
                "prototipo_id": escenario.prototipo_id,
                "dias_habiles": [1, 2, 3, 4, 5, 6],
            }
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        vigente = await RepositorioProgramasSQL(sesion).base_vigente(
            escenario.prototipo_id
        )

    assert vigente is not None
    assert list(vigente["dias_habiles"]) == [1, 2, 3, 4, 5, 6]


async def test_base_vigente_solo_devuelve_la_version_vigente(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """Cambiar de calendario es publicar una versión nueva de la plantilla.

    La anterior queda con el suyo: es contra ese calendario que se calcularon
    las obras que ya se instanciaron (§7.5, §10.8).
    """
    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioProgramasSQL(sesion)
        await repo.crear_base(
            {"prototipo_id": escenario.prototipo_id, "dias_habiles": [1, 2, 3, 4, 5]}
        )
        await repo.crear_base(
            {
                "prototipo_id": escenario.prototipo_id,
                "dias_habiles": [1, 2, 3, 4, 5, 6],
            }
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        vigente = await RepositorioProgramasSQL(sesion).base_vigente(
            escenario.prototipo_id
        )

    assert vigente is not None
    assert vigente["version"] == 2
    assert list(vigente["dias_habiles"]) == [1, 2, 3, 4, 5, 6]


async def test_instanciar_congela_el_calendario_en_la_version(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """El calendario se guarda por versión de cronograma, como `fecha_corte`.

    Reinstanciar con otra plantilla no debe reescribir contra qué se calculó la
    versión anterior.
    """
    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioProgramasSQL(sesion)
        primera = await repo.instanciar(
            escenario.obra_id, fecha_corte=None, dias_habiles=[1, 2, 3, 4, 5, 6]
        )
        segunda = await repo.instanciar(
            escenario.obra_id, fecha_corte=None, dias_habiles=[1, 2, 3, 4, 5]
        )
        await sesion.commit()

    assert list(primera["dias_habiles"]) == [1, 2, 3, 4, 5, 6]
    assert list(segunda["dias_habiles"]) == [1, 2, 3, 4, 5]

    async with sesion_con_rls(contexto_control) as sesion:
        vigente = await RepositorioProgramasSQL(sesion).programa_vigente(
            escenario.obra_id
        )
    assert vigente is not None
    assert vigente["version"] == 2
    assert list(vigente["dias_habiles"]) == [1, 2, 3, 4, 5]


async def test_el_cronograma_nace_en_semana_natural_sin_calendario(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_control) as sesion:
        programa = await RepositorioProgramasSQL(sesion).instanciar(
            escenario.obra_id, fecha_corte=None
        )
    assert list(programa["dias_habiles"]) == [1, 2, 3, 4, 5, 6, 7]


@pytest.mark.parametrize(
    "dias", [[], [0, 1], [1, 8], [None, 1]], ids=["vacio", "cero", "ocho", "nulo"]
)
async def test_la_base_rechaza_un_calendario_imposible(
    escenario: Escenario, contexto_control: ContextoSesion, dias: list
) -> None:
    """El check de la 0040, que espeja al dominio (§12.11).

    El dominio ya rechaza estos conjuntos con un mensaje legible; el check
    existe para que nadie los meta por SQL directo y deje un cronograma que el
    motor no sabe calcular.
    """
    async with sesion_con_rls(contexto_control) as sesion:
        with pytest.raises(Exception):  # noqa: B017 - la base levanta IntegrityError
            await RepositorioProgramasSQL(sesion).instanciar(
                escenario.obra_id, fecha_corte=None, dias_habiles=dias
            )
