"""Reinicio de organización: borrado profundo de punta a punta.

Spec §12.4 (RLS) · §5.1 (Control de obra, "Configuración").

`app.reiniciar_organizacion()` (`database/migrations/
20260814000036_reinicio_de_organizacion.sql`) es `security definer` a
propósito: seis tablas (`control_proyecto`, `evaluacion`, `notificacion`,
`idempotencia`, `dispositivo_push`, `bitacora`) no son escribibles por
`control_obra` bajo su sesión RLS normal. Estas pruebas verifican tanto que
el borrado alcanza esas tablas (el bypass funciona) como que NO borra nada
de otra organización ni de `usuario`/`organizacion`.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.repos.organizacion_sql import RepositorioOrganizacionSQL
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL
from obractrl.application.casos_uso.gestionar_organizacion import ReiniciarOrganizacion
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario


@dataclass(frozen=True, slots=True)
class _OtraOrg:
    org_id: uuid.UUID
    unidad_id: uuid.UUID


@pytest.fixture
async def otra_org() -> AsyncIterator[_OtraOrg]:
    """Una segunda organización, con una fila propia, para probar
    aislamiento: reiniciar la primera no debe tocar esto."""
    engine = create_async_engine(DATABASE_URL_ADMIN)
    org = uuid.uuid4()
    unidad = uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text("insert into organizacion (id, nombre, slug) values (:id, 'Otra', :slug)"),
            {"id": str(org), "slug": f"otra-{org.hex[:8]}"},
        )
        await conn.execute(
            text(
                "insert into unidad (id, org_id, clave, nombre) "
                "values (:id, :org, 'TON', 'Tonelada')"
            ),
            {"id": str(unidad), "org": str(org)},
        )
    yield _OtraOrg(org_id=org, unidad_id=unidad)
    async with engine.begin() as conn:
        await conn.execute(text("delete from organizacion where id = :id"), {"id": str(org)})
    await engine.dispose()


async def _sembrar_datos_variados(escenario: Escenario) -> None:
    """Filas de varias tiers del borrado, más allá de lo que ya trae
    `escenario` (proyecto/cluster/prototipo/obra/actividad): un catálogo con
    FK sin cascada (concepto→unidad/familia), una cadena de cuadrilla
    (cuadrilla_version/integrante→insumo, todas RESTRICT), y dos filas que
    solo se pueden borrar con el bypass de RLS (notificacion/idempotencia
    del RESIDENTE, no de quien va a ejecutar el reinicio)."""
    engine = create_async_engine(DATABASE_URL_ADMIN)
    org = escenario.org_id
    unidad = uuid.uuid4()
    familia = uuid.uuid4()
    concepto = uuid.uuid4()
    insumo = uuid.uuid4()
    cuadrilla = uuid.uuid4()
    cuadrilla_version = uuid.uuid4()

    async with engine.begin() as conn:
        await conn.execute(
            text("insert into unidad (id, org_id, clave, nombre) values (:id, :org, 'M2', 'Metro cuadrado')"),
            {"id": str(unidad), "org": str(org)},
        )
        await conn.execute(
            text(
                "insert into familia (id, org_id, clave, nombre, aplica_a) "
                "values (:id, :org, 'CEM', 'Cemento', 'material')"
            ),
            {"id": str(familia), "org": str(org)},
        )
        await conn.execute(
            text(
                "insert into concepto (id, org_id, tipo, clave, descripcion, unidad_id, familia_id) "
                "values (:id, :org, 'concepto', 'EST-01', 'Muro', :unidad, :familia)"
            ),
            {"id": str(concepto), "org": str(org), "unidad": str(unidad), "familia": str(familia)},
        )
        await conn.execute(
            text(
                "insert into insumo (id, org_id, tipo, clave, descripcion) "
                "values (:id, :org, 'material', 'MAT-01', 'Block')"
            ),
            {"id": str(insumo), "org": str(org)},
        )
        await conn.execute(
            text("insert into cuadrilla (id, org_id, clave, nombre) values (:id, :org, 'CUA-01', 'Cuadrilla 1')"),
            {"id": str(cuadrilla), "org": str(org)},
        )
        await conn.execute(
            text(
                "insert into cuadrilla_version (id, org_id, cuadrilla_id) "
                "values (:id, :org, :cuadrilla)"
            ),
            {"id": str(cuadrilla_version), "org": str(org), "cuadrilla": str(cuadrilla)},
        )
        await conn.execute(
            text(
                "insert into cuadrilla_integrante (id, org_id, cuadrilla_version_id, insumo_id) "
                "values (:id, :org, :version, :insumo)"
            ),
            {"id": str(uuid.uuid4()), "org": str(org), "version": str(cuadrilla_version), "insumo": str(insumo)},
        )
        # Dueño de fila = residente, NO control_obra: sin el bypass de RLS
        # de la función, un reinicio ejecutado por control_obra dejaría
        # estas dos filas intactas (políticas `usuario_id = current_usuario_id()`).
        await conn.execute(
            text(
                "insert into notificacion (id, org_id, usuario_id, tipo) "
                "values (:id, :org, :usuario, 'prueba')"
            ),
            {"id": str(uuid.uuid4()), "org": str(org), "usuario": str(escenario.residente_id)},
        )
        await conn.execute(
            text(
                "insert into idempotencia (id, org_id, usuario_id, clave, metodo, ruta, huella) "
                "values (:id, :org, :usuario, 'clave-1', 'POST', '/x', 'huella')"
            ),
            {"id": str(uuid.uuid4()), "org": str(org), "usuario": str(escenario.residente_id)},
        )
    await engine.dispose()


async def _contar(org_id: uuid.UUID, tabla: str) -> int:
    engine = create_async_engine(DATABASE_URL_ADMIN)
    async with engine.begin() as conn:
        total = (
            await conn.execute(
                text(f"select count(*) from {tabla} where org_id = :org"),  # noqa: S608
                {"org": str(org_id)},
            )
        ).scalar_one()
    await engine.dispose()
    return int(total)


async def _reiniciar(contexto: ContextoSesion) -> dict[str, int]:
    async with sesion_con_rls(contexto) as sesion:
        caso_uso = ReiniciarOrganizacion(
            organizacion=RepositorioOrganizacionSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
        )
        return await caso_uso.ejecutar()


async def test_reiniciar_borra_todo_menos_usuario_y_preserva_otra_org(
    escenario: Escenario,
    contexto_control: ContextoSesion,
    otra_org: _OtraOrg,
) -> None:
    await _sembrar_datos_variados(escenario)

    resumen = await _reiniciar(contexto_control)

    assert resumen.get("proyecto") == 1
    assert resumen.get("actividad") == 1
    assert resumen.get("cuadrilla_integrante") == 1
    # Las dos filas que solo el bypass de RLS alcanza (dueño = residente,
    # no control_obra) — si esto da 0, el reinicio quedó incompleto.
    assert resumen.get("notificacion") == 1
    assert resumen.get("idempotencia") == 1

    for tabla in (
        "proyecto", "cluster", "prototipo", "obra", "actividad",
        "control_proyecto", "supervisor_cluster", "concepto", "unidad",
        "familia", "insumo", "cuadrilla", "cuadrilla_version",
        "cuadrilla_integrante", "notificacion", "idempotencia",
    ):
        assert await _contar(escenario.org_id, tabla) == 0, f"{tabla} no quedó en cero"

    assert await _contar(otra_org.org_id, "unidad") == 1

    engine = create_async_engine(DATABASE_URL_ADMIN)
    async with engine.begin() as conn:
        usuarios = (
            await conn.execute(
                text("select count(*) from usuario where org_id = :org"),
                {"org": str(escenario.org_id)},
            )
        ).scalar_one()
        orgs = (
            await conn.execute(
                text("select count(*) from organizacion where id in (:a, :b)"),
                {"a": str(escenario.org_id), "b": str(otra_org.org_id)},
            )
        ).scalar_one()
    await engine.dispose()
    # residente, supervisor, control y super intendente — ver conftest.escenario.
    # El cuarto lo trajo la migración 0042: sin un super intendente con gente
    # asignada, el escenario no puede ejercitar su alcance.
    assert usuarios == 4
    assert orgs == 2


async def test_reiniciar_no_deja_nada_huerfano_en_ninguna_tabla_con_org_id(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """Cobertura completa (mismo espíritu que la prueba de
    `_REFERENCIAS_EXTERNAS` contra `information_schema` en
    `cargas_sql.py`): esto se rompe solo el día que alguien agregue una
    tabla nueva con `org_id` y se le olvide meterla al arreglo de la
    función — la garantía que hace falta para no dejar basura huérfana."""
    await _sembrar_datos_variados(escenario)
    await _reiniciar(contexto_control)

    engine = create_async_engine(DATABASE_URL_ADMIN)
    async with engine.begin() as conn:
        tablas = (
            await conn.execute(
                text(
                    "select table_name from information_schema.columns "
                    "where table_schema = 'public' and column_name = 'org_id'"
                )
            )
        ).scalars().all()
    huerfanas = []
    for tabla in tablas:
        if tabla == "usuario":
            continue
        if await _contar(escenario.org_id, tabla) > 0:
            huerfanas.append(tabla)
    await engine.dispose()
    assert huerfanas == []


async def test_reiniciar_rechaza_a_quien_no_es_control_de_obra(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    with pytest.raises(DBAPIError, match="Solo Control de obra"):
        await _reiniciar(contexto_residente)
