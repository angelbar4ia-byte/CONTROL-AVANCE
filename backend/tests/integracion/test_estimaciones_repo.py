"""Repositorio de estimaciones contra Postgres real (§3.2, §7.6, §11.3 E).

`ultimo_consecutivo` es el caso interesante: la tabla no guarda el
consecutivo aparte, solo el folio ya formateado, así que el repo relee con
`Folio.parsear` (dominio) — esta prueba confirma que el contador es
compartido entre ERP y no-ERP, y que un folio corrupto no tumba el conteo.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from obractrl.adapters.repos.estimaciones_sql import RepositorioEstimacionesSQL
from obractrl.domain.shared.folio import Folio
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario


async def _insertar_estimacion(
    admin_engine: AsyncEngine, org_id: uuid.UUID, obra_id: uuid.UUID, folio: str
) -> None:
    async with admin_engine.begin() as conn:
        f = Folio.parsear(folio)
        await conn.execute(
            text(
                "insert into estimacion "
                "(org_id, obra_id, folio, semana, anio, modo) "
                "values (:org, :obra, :folio, :semana, :anio, 'destajo')"
            ),
            {
                "org": str(org_id),
                "obra": str(obra_id),
                "folio": folio,
                "semana": f.semana,
                "anio": f.anio,
            },
        )


async def test_ultimo_consecutivo_comparte_contador_erp_y_no_erp(
    escenario: Escenario,
) -> None:
    admin = create_async_engine(DATABASE_URL_ADMIN)
    await _insertar_estimacion(admin, escenario.org_id, escenario.obra_id, "2126-001")
    await _insertar_estimacion(
        admin, escenario.org_id, escenario.obra_id, "E-2126-002"
    )
    # Folio corrupto: no debe tumbar la lectura del resto.
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "insert into estimacion "
                "(org_id, obra_id, folio, semana, anio, modo) "
                "values (:org, :obra, 'no-es-un-folio', 21, 2026, 'destajo')"
            ),
            {"org": str(escenario.org_id), "obra": str(escenario.obra_id)},
        )
    await admin.dispose()

    ctx = ContextoSesion(
        org_id=escenario.org_id, usuario_id=escenario.residente_id, rol="residente"
    )
    async with sesion_con_rls(ctx) as sesion:
        repo = RepositorioEstimacionesSQL(sesion)
        maximo = await repo.ultimo_consecutivo(semana=21, anio=2026)

    assert maximo == 2  # el E- (ERP) cuenta en el mismo contador


async def test_ultimo_consecutivo_sin_estimaciones_es_cero(
    contexto_residente: ContextoSesion,
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioEstimacionesSQL(sesion)
        assert await repo.ultimo_consecutivo(semana=1, anio=2099) == 0


async def test_crear_inserta_en_borrador(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    folio = str(Folio(semana=15, anio=2026, consecutivo=1))

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioEstimacionesSQL(sesion)
        estimacion_id = await repo.crear(
            {
                "obra_id": escenario.obra_id,
                "folio": folio,
                "semana": 15,
                "anio": 2026,
                "modo": "destajo",
                "creada_por": escenario.residente_id,
            }
        )
        await sesion.commit()

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        fila = (
            await conn.execute(
                text(
                    "select org_id, obra_id, folio, estatus, creada_por "
                    "from estimacion where id = :id"
                ),
                {"id": str(estimacion_id)},
            )
        ).first()
    await admin.dispose()

    assert fila is not None
    assert fila.org_id == escenario.org_id
    assert fila.folio == folio
    assert fila.estatus == "borrador"
    assert fila.creada_por == escenario.residente_id


async def test_actividades_estimables_filtra_por_semana_y_validacion(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        await conn.execute(
            text("select app.generar_calendario(cast(:org as uuid), 'obra'::tipo_semana, 2026::smallint)"),
            {"org": str(escenario.org_id)},
        )
        rango_5 = (
            await conn.execute(
                text(
                    "select fecha_inicio from calendario "
                    "where org_id = :org and tipo = 'obra' and anio = 2026 "
                    "and semana = 5"
                ),
                {"org": str(escenario.org_id)},
            )
        ).scalar_one()

        # Validada, dentro de la semana 5: debe salir en el resultado.
        await conn.execute(
            text(
                """
                insert into solicitud_cierre
                    (org_id, actividad_id, cantidad, estatus,
                     autorizada_por, validada_por, fecha_valida)
                values
                    (:org, :act, 30, 'validada', :res, :res,
                     :fecha_valida)
                """
            ),
            {
                "org": str(escenario.org_id),
                "act": str(escenario.actividad_id),
                "res": str(escenario.residente_id),
                "fecha_valida": rango_5,
            },
        )

        # Otra actividad de la misma obra, con cierre SOLICITADO (no
        # validado): no debe salir.
        otra_actividad = uuid.uuid4()
        await conn.execute(
            text(
                "insert into actividad (id, org_id, obra_id, cant_base) "
                "values (:id, :org, :obra, 10)"
            ),
            {
                "id": str(otra_actividad),
                "org": str(escenario.org_id),
                "obra": str(escenario.obra_id),
            },
        )
        await conn.execute(
            text(
                "insert into solicitud_cierre "
                "(org_id, actividad_id, cantidad, estatus) "
                "values (:org, :act, 5, 'solicitada')"
            ),
            {"org": str(escenario.org_id), "act": str(otra_actividad)},
        )
    await admin.dispose()

    async with sesion_con_rls(contexto_residente) as sesion:
        repo = RepositorioEstimacionesSQL(sesion)
        estimables = await repo.actividades_estimables(
            escenario.obra_id, semana=5, anio=2026
        )
        # Otra semana: no debe encontrar nada.
        vacio = await repo.actividades_estimables(
            escenario.obra_id, semana=6, anio=2026
        )

    assert len(estimables) == 1
    assert estimables[0]["actividad_id"] == escenario.actividad_id
    assert estimables[0]["cantidad_validada"] == Decimal("30")
    assert vacio == []
