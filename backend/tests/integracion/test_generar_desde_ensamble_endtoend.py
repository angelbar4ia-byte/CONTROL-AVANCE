"""Generación de punta a punta contra Postgres real (skill `erp-parametrico`
§6, dirección ensamble → presupuesto).

Lo que aquí se prueba y no en `tests/domain/test_ensamble.py`: que el caso
de uso resuelve el CPU vigente de cada concepto (capturado, sin APU de por
medio), que `factor` escala las cantidades que de verdad se escriben, y
que las cinco clasificaciones de `reconciliar_generacion` corresponden a
lo que el caso de uso aplica solo (NUEVO/ACTUALIZADO) o solo reporta
(DESVINCULADO/CONFLICTO/SOBRA) — nunca arrasando ni respetando en silencio.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from obractrl.adapters.repos.conceptos_sql import RepositorioConceptosSQL
from obractrl.adapters.repos.ensambles_sql import RepositorioEnsamblesSQL
from obractrl.adapters.repos.generacion_ensamble_sql import (
    RepositorioGeneracionDePresupuestoSQL,
)
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL
from obractrl.application.casos_uso.gestionar_ensamble import (
    ComandoExtraerEnsamble,
    ComandoGenerarDesdeEnsamble,
    EnsambleNoCoincideConInstancia,
    EnsambleNoEncontrado,
    ExtraerEnsamble,
    GenerarDesdeEnsamble,
    InstanciaNoEncontrada,
)
from obractrl.domain.catalogos.ensamble import EstadoRenglonGenerado, RenglonEnsamble
from obractrl.domain.shared.diccionario import OrigenCantidadEnsamble
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario


async def _crear_presupuesto(escenario: Escenario) -> uuid.UUID:
    presupuesto_id = uuid.uuid4()
    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "insert into presupuesto (id, org_id, prototipo_id, version, "
                "vigente, monto_total) "
                "values (:id, :org, :proto, 1, true, 0)"
            ),
            {
                "id": str(presupuesto_id),
                "org": str(escenario.org_id),
                "proto": str(escenario.prototipo_id),
            },
        )
    await admin.dispose()
    return presupuesto_id


async def _sembrar_ensamble(
    sesion: AsyncSession, *, clave_concepto: str = "EST-MURO", cantidad: str = "4"
) -> dict[str, uuid.UUID]:
    """RECAMARA-A: 1 renglón (clave_concepto × cantidad), CPU capturado
    100.00/40.00 (sin APU: prueba el camino "precio capturado", §10.1)."""
    conceptos = RepositorioConceptosSQL(sesion)
    muro = await conceptos.crear(
        {"tipo": "concepto", "clave": clave_concepto, "descripcion": "Muro de block"}
    )
    await conceptos.publicar_version_cpu(
        muro,
        version=1,
        precio_unitario=Decimal("100.00"),
        precio_destajo=Decimal("40.00"),
        variante=None,
        retirar=[],
    )

    extraer = ExtraerEnsamble(
        ensambles=RepositorioEnsamblesSQL(sesion),
        conceptos=conceptos,
        uow=UnidadDeTrabajoSQL(sesion),
    )
    creado = await extraer.ejecutar(
        ComandoExtraerEnsamble(
            clave="RECAMARA-A",
            nombre="Recámara tipo A",
            renglones=[
                RenglonEnsamble(
                    cantidad=Decimal(cantidad),
                    origen=OrigenCantidadEnsamble.HEREDADA_CONCEPTO,
                    clave_concepto=clave_concepto,
                )
            ],
        )
    )
    return {"concepto": muro, "ensamble": creado.id}


def _caso_uso(sesion: AsyncSession) -> GenerarDesdeEnsamble:
    return GenerarDesdeEnsamble(
        ensambles=RepositorioEnsamblesSQL(sesion),
        conceptos=RepositorioConceptosSQL(sesion),
        generacion=RepositorioGeneracionDePresupuestoSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


async def test_primera_generacion_crea_instancia_y_partidas_nuevas(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    presupuesto_id = await _crear_presupuesto(escenario)
    async with sesion_con_rls(contexto_control) as sesion:
        ids = await _sembrar_ensamble(sesion)
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        reporte = await _caso_uso(sesion).ejecutar(
            ComandoGenerarDesdeEnsamble(
                presupuesto_id=presupuesto_id,
                prototipo_id=escenario.prototipo_id,
                ensamble_id=ids["ensamble"],
                factor=Decimal(2),
                nombre="Recámara 1",
            )
        )

    assert reporte.nuevos == ("EST-MURO",)
    assert reporte.actualizados == ()
    assert reporte.pendientes == ()

    async with sesion_con_rls(contexto_control) as sesion:
        generacion = RepositorioGeneracionDePresupuestoSQL(sesion)
        instancia = await generacion.obtener_instancia(reporte.prototipo_nodo_id)
        assert instancia is not None
        assert instancia["ensamble_factor"] == Decimal("2")

        filas = await generacion.partidas_de_instancia(
            presupuesto_id=presupuesto_id, instancia_id=reporte.prototipo_nodo_id
        )
    muro = next(f for f in filas if f["concepto_clave"] == "EST-MURO")
    assert muro["cantidad"] == Decimal("8.000000")  # 4 por unidad × factor 2
    assert muro["precio_unitario"] == Decimal("100.0000")
    assert muro["cantidad_generada"] == muro["cantidad"]
    assert muro["precio_unitario_generado"] == muro["precio_unitario"]


async def test_regenerar_sin_tocar_nada_refresca_el_precio_del_catalogo(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    presupuesto_id = await _crear_presupuesto(escenario)
    async with sesion_con_rls(contexto_control) as sesion:
        ids = await _sembrar_ensamble(sesion)
        await sesion.commit()

    cmd = ComandoGenerarDesdeEnsamble(
        presupuesto_id=presupuesto_id,
        prototipo_id=escenario.prototipo_id,
        ensamble_id=ids["ensamble"],
        factor=Decimal(2),
        nombre="Recámara 1",
    )
    async with sesion_con_rls(contexto_control) as sesion:
        primera = await _caso_uso(sesion).ejecutar(cmd)

    # El catálogo sube de precio desde la primera generación.
    async with sesion_con_rls(contexto_control) as sesion:
        await RepositorioConceptosSQL(sesion).publicar_version_cpu(
            ids["concepto"],
            version=2,
            precio_unitario=Decimal("120.00"),
            precio_destajo=Decimal("50.00"),
            variante=None,
            retirar=[1],
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        segunda = await _caso_uso(sesion).ejecutar(
            ComandoGenerarDesdeEnsamble(
                presupuesto_id=presupuesto_id,
                prototipo_id=escenario.prototipo_id,
                ensamble_id=ids["ensamble"],
                factor=Decimal(2),
                nombre="Recámara 1",
                prototipo_nodo_id=primera.prototipo_nodo_id,
            )
        )

    assert segunda.nuevos == ()
    assert segunda.actualizados == ("EST-MURO",)
    assert segunda.pendientes == ()

    async with sesion_con_rls(contexto_control) as sesion:
        filas = await RepositorioGeneracionDePresupuestoSQL(sesion).partidas_de_instancia(
            presupuesto_id=presupuesto_id, instancia_id=primera.prototipo_nodo_id
        )
    muro = next(f for f in filas if f["concepto_clave"] == "EST-MURO")
    assert muro["precio_unitario"] == Decimal("120.0000")
    assert muro["precio_unitario_generado"] == Decimal("120.0000")  # el snapshot avanza


async def test_regenerar_no_pisa_una_partida_editada_a_mano(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    presupuesto_id = await _crear_presupuesto(escenario)
    async with sesion_con_rls(contexto_control) as sesion:
        ids = await _sembrar_ensamble(sesion)
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        primera = await _caso_uso(sesion).ejecutar(
            ComandoGenerarDesdeEnsamble(
                presupuesto_id=presupuesto_id,
                prototipo_id=escenario.prototipo_id,
                ensamble_id=ids["ensamble"],
                factor=Decimal(2),
                nombre="Recámara 1",
            )
        )

    # El usuario agranda el cuarto a mano: 8 → 9. El snapshot generado se queda en 8.
    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "update partida_presupuesto set cantidad = 9, importe = 900 "
                "where presupuesto_id = :pid"
            ),
            {"pid": str(presupuesto_id)},
        )
    await admin.dispose()

    async with sesion_con_rls(contexto_control) as sesion:
        reporte = await _caso_uso(sesion).ejecutar(
            ComandoGenerarDesdeEnsamble(
                presupuesto_id=presupuesto_id,
                prototipo_id=escenario.prototipo_id,
                ensamble_id=ids["ensamble"],
                factor=Decimal(2),
                nombre="Recámara 1",
                prototipo_nodo_id=primera.prototipo_nodo_id,
            )
        )

    assert reporte.nuevos == ()
    assert reporte.actualizados == ()
    assert [p.estado for p in reporte.pendientes] == [EstadoRenglonGenerado.DESVINCULADO]
    pendiente = reporte.pendientes[0]
    assert pendiente.existente is not None and pendiente.existente.actual.cantidad == Decimal(
        "9.000000"
    )
    assert pendiente.receta is not None and pendiente.receta.cantidad == Decimal("8.000000")

    # Nunca se pisó: sigue en 9.
    async with sesion_con_rls(contexto_control) as sesion:
        filas = await RepositorioGeneracionDePresupuestoSQL(sesion).partidas_de_instancia(
            presupuesto_id=presupuesto_id, instancia_id=primera.prototipo_nodo_id
        )
    assert filas[0]["cantidad"] == Decimal("9.000000")


async def test_concepto_que_ya_no_esta_en_la_receta_es_sobra_y_no_se_borra(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    presupuesto_id = await _crear_presupuesto(escenario)
    async with sesion_con_rls(contexto_control) as sesion:
        ids = await _sembrar_ensamble(sesion)
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        primera = await _caso_uso(sesion).ejecutar(
            ComandoGenerarDesdeEnsamble(
                presupuesto_id=presupuesto_id,
                prototipo_id=escenario.prototipo_id,
                ensamble_id=ids["ensamble"],
                factor=Decimal(2),
                nombre="Recámara 1",
            )
        )

    # El ensamble deja de incluir EST-MURO (se quita el renglón directamente).
    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        await conn.execute(
            text("delete from ensamble_renglon where org_id = :org"),
            {"org": str(escenario.org_id)},
        )
    await admin.dispose()

    async with sesion_con_rls(contexto_control) as sesion:
        reporte = await _caso_uso(sesion).ejecutar(
            ComandoGenerarDesdeEnsamble(
                presupuesto_id=presupuesto_id,
                prototipo_id=escenario.prototipo_id,
                ensamble_id=ids["ensamble"],
                factor=Decimal(2),
                nombre="Recámara 1",
                prototipo_nodo_id=primera.prototipo_nodo_id,
            )
        )

    assert [p.estado for p in reporte.pendientes] == [EstadoRenglonGenerado.SOBRA]
    assert reporte.pendientes[0].receta is None

    async with sesion_con_rls(contexto_control) as sesion:
        filas = await RepositorioGeneracionDePresupuestoSQL(sesion).partidas_de_instancia(
            presupuesto_id=presupuesto_id, instancia_id=primera.prototipo_nodo_id
        )
    assert len(filas) == 1  # la partida sigue ahí, no se borró sola


async def test_partida_capturada_sin_generar_es_conflicto(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    presupuesto_id = await _crear_presupuesto(escenario)
    async with sesion_con_rls(contexto_control) as sesion:
        ids = await _sembrar_ensamble(sesion)
        piso = await RepositorioConceptosSQL(sesion).crear(
            {"tipo": "concepto", "clave": "EST-PISO", "descripcion": "Piso"}
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        primera = await _caso_uso(sesion).ejecutar(
            ComandoGenerarDesdeEnsamble(
                presupuesto_id=presupuesto_id,
                prototipo_id=escenario.prototipo_id,
                ensamble_id=ids["ensamble"],
                factor=Decimal(2),
                nombre="Recámara 1",
            )
        )

    # Alguien agrega EST-PISO a mano bajo la misma instancia, y el ensamble
    # también lo empieza a pedir — sin que nunca lo haya generado este ensamble.
    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        nodo_hoja = uuid.uuid4()
        await conn.execute(
            text(
                "insert into prototipo_nodo "
                "(id, org_id, prototipo_id, parent_id, tipo, nombre, concepto_id) "
                "values (:id, :org, :proto, :parent, 'concepto', 'Piso', :concepto)"
            ),
            {
                "id": str(nodo_hoja),
                "org": str(escenario.org_id),
                "proto": str(escenario.prototipo_id),
                "parent": str(primera.prototipo_nodo_id),
                "concepto": str(piso),
            },
        )
        await conn.execute(
            text(
                "insert into partida_presupuesto "
                "(org_id, presupuesto_id, concepto_id, prototipo_nodo_id, "
                " cantidad, precio_unitario, importe) "
                "values (:org, :pre, :concepto, :nodo, 10, 50, 500)"
            ),
            {
                "org": str(escenario.org_id),
                "pre": str(presupuesto_id),
                "concepto": str(piso),
                "nodo": str(nodo_hoja),
            },
        )
        await conn.execute(
            text(
                "insert into ensamble_renglon "
                "(org_id, ensamble_id, concepto_id, cantidad, origen) "
                "select org_id, id, :concepto, 1, 'manual' from ensamble "
                "where clave = 'RECAMARA-A' and org_id = :org"
            ),
            {"concepto": str(piso), "org": str(escenario.org_id)},
        )
    await admin.dispose()

    async with sesion_con_rls(contexto_control) as sesion:
        reporte = await _caso_uso(sesion).ejecutar(
            ComandoGenerarDesdeEnsamble(
                presupuesto_id=presupuesto_id,
                prototipo_id=escenario.prototipo_id,
                ensamble_id=ids["ensamble"],
                factor=Decimal(2),
                nombre="Recámara 1",
                prototipo_nodo_id=primera.prototipo_nodo_id,
            )
        )

    assert ids["concepto"]  # usado arriba, solo para que ruff no lo marque suelto
    conflicto = next(
        p for p in reporte.pendientes if p.estado is EstadoRenglonGenerado.CONFLICTO
    )
    assert conflicto.clave_concepto == "EST-PISO"


async def test_regenerar_con_otro_ensamble_se_rechaza(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    presupuesto_id = await _crear_presupuesto(escenario)
    async with sesion_con_rls(contexto_control) as sesion:
        ids = await _sembrar_ensamble(sesion)

        otro = await RepositorioConceptosSQL(sesion).crear(
            {"tipo": "concepto", "clave": "EST-OTRO", "descripcion": "Otro concepto"}
        )
        creado_b = await ExtraerEnsamble(
            ensambles=RepositorioEnsamblesSQL(sesion),
            conceptos=RepositorioConceptosSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
        ).ejecutar(
            ComandoExtraerEnsamble(
                clave="RECAMARA-B",
                nombre="Recámara tipo B",
                renglones=[
                    RenglonEnsamble(
                        cantidad=Decimal(1),
                        origen=OrigenCantidadEnsamble.MANUAL,
                        clave_concepto="EST-OTRO",
                    )
                ],
            )
        )
        assert otro
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        primera = await _caso_uso(sesion).ejecutar(
            ComandoGenerarDesdeEnsamble(
                presupuesto_id=presupuesto_id,
                prototipo_id=escenario.prototipo_id,
                ensamble_id=ids["ensamble"],
                factor=Decimal(1),
                nombre="Recámara 1",
            )
        )

    with pytest.raises(EnsambleNoCoincideConInstancia):
        async with sesion_con_rls(contexto_control) as sesion:
            await _caso_uso(sesion).ejecutar(
                ComandoGenerarDesdeEnsamble(
                    presupuesto_id=presupuesto_id,
                    prototipo_id=escenario.prototipo_id,
                    ensamble_id=creado_b.id,
                    factor=Decimal(1),
                    nombre="Recámara 1",
                    prototipo_nodo_id=primera.prototipo_nodo_id,
                )
            )


async def test_ensamble_inexistente_se_rechaza(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    presupuesto_id = await _crear_presupuesto(escenario)
    with pytest.raises(EnsambleNoEncontrado):
        async with sesion_con_rls(contexto_control) as sesion:
            await _caso_uso(sesion).ejecutar(
                ComandoGenerarDesdeEnsamble(
                    presupuesto_id=presupuesto_id,
                    prototipo_id=escenario.prototipo_id,
                    ensamble_id=uuid.uuid4(),
                    factor=Decimal(1),
                    nombre="Recámara 1",
                )
            )


async def test_instancia_inexistente_se_rechaza(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    presupuesto_id = await _crear_presupuesto(escenario)
    async with sesion_con_rls(contexto_control) as sesion:
        ids = await _sembrar_ensamble(sesion)
        await sesion.commit()

    with pytest.raises(InstanciaNoEncontrada):
        async with sesion_con_rls(contexto_control) as sesion:
            await _caso_uso(sesion).ejecutar(
                ComandoGenerarDesdeEnsamble(
                    presupuesto_id=presupuesto_id,
                    prototipo_id=escenario.prototipo_id,
                    ensamble_id=ids["ensamble"],
                    factor=Decimal(1),
                    nombre="Recámara 1",
                    prototipo_nodo_id=uuid.uuid4(),
                )
            )
