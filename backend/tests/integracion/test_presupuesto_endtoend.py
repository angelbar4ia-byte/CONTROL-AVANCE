"""Presupuesto y rendimientos contra Postgres real (§5.1, §7.3, §12.4).

Lo que solo se prueba aquí:

· Que `obra → prototipo → presupuesto vigente` resuelva, y que una obra URBA
  —sin prototipo— no lo tenga sin que eso sea un error.
· Que el comparativo incluya **las dos caras que faltan**: lo presupuestado y no
  ejecutado, y lo ejecutado sin presupuestar. Un `left join` habría escondido
  los extras, que son justo los que explican el sobrecosto.
· Que el resumen por obra respete el alcance del rol, porque arranca en `obra`.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.repos.presupuestos_sql import RepositorioPresupuestosSQL
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario


async def _sembrar_presupuesto(escenario: Escenario) -> dict[str, uuid.UUID]:
    """Un presupuesto con dos partidas y una actividad ejecutada.

    · `EXCAV` — presupuestado y ejecutado por encima.
    · `PINT`  — presupuestado y **sin ejecutar**.
    · un extra — ejecutado y **sin presupuestar**.
    """
    ids = {
        "presupuesto": uuid.uuid4(),
        "concepto_excav": uuid.uuid4(),
        "concepto_pint": uuid.uuid4(),
        "actividad_excav": uuid.uuid4(),
        "actividad_extra": uuid.uuid4(),
        "cuadrilla": uuid.uuid4(),
    }
    org = str(escenario.org_id)
    sufijo = uuid.uuid4().hex[:6]

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        for clave, concepto_id in (
            ("EXCAV", ids["concepto_excav"]),
            ("PINT", ids["concepto_pint"]),
        ):
            await conn.execute(
                text(
                    "insert into concepto (id, org_id, clave, descripcion, tipo) "
                    "values (:id, :org, :clave, :desc, 'concepto')"
                ),
                {
                    "id": str(concepto_id),
                    "org": org,
                    "clave": f"{clave}-{sufijo}",
                    "desc": f"Concepto {clave}",
                },
            )

        await conn.execute(
            text(
                "insert into presupuesto (id, org_id, prototipo_id, version, "
                "vigente, monto_total) "
                "values (:id, :org, :proto, 1, true, 150000)"
            ),
            {
                "id": str(ids["presupuesto"]),
                "org": org,
                "proto": str(escenario.prototipo_id),
            },
        )
        await conn.execute(
            text(
                "insert into partida_presupuesto (org_id, presupuesto_id, "
                "concepto_id, cantidad, precio_unitario, importe, orden) values "
                "(:org, :pre, :excav, 100, 1000, 100000, 1), "
                "(:org, :pre, :pint, 50, 1000, 50000, 2)"
            ),
            {
                "org": org,
                "pre": str(ids["presupuesto"]),
                "excav": str(ids["concepto_excav"]),
                "pint": str(ids["concepto_pint"]),
            },
        )

        await conn.execute(
            text(
                "insert into cuadrilla (id, org_id, clave, nombre, rendimiento) "
                "values (:id, :org, :clave, 'Cuadrilla A', 12)"
            ),
            {
                "id": str(ids["cuadrilla"]),
                "org": org,
                "clave": f"CUA-{sufijo}",
            },
        )

        # Ejecutado por encima de lo presupuestado.
        await conn.execute(
            text(
                "insert into actividad (id, org_id, obra_id, concepto_id, "
                "cuadrilla_id, descripcion, cant_base, cant_programada, "
                "modo_pago, precio_unitario) "
                "values (:id, :org, :obra, :concepto, :cuadrilla, 'Excavación', "
                "130, 130, 'concepto', 1000)"
            ),
            {
                "id": str(ids["actividad_excav"]),
                "org": org,
                "obra": str(escenario.obra_id),
                "concepto": str(ids["concepto_excav"]),
                "cuadrilla": str(ids["cuadrilla"]),
            },
        )
        # Un extra: ejecutado y sin presupuestar (§11.2).
        await conn.execute(
            text(
                "insert into actividad (id, org_id, obra_id, descripcion, "
                "cant_base, cant_programada, modo_pago, precio_unitario, "
                "extra, orden_cambio) "
                "values (:id, :org, :obra, 'Demoler muro', 10, 10, 'concepto', "
                "2000, true, 'OC-1')"
            ),
            {
                "id": str(ids["actividad_extra"]),
                "org": org,
                "obra": str(escenario.obra_id),
            },
        )
        # El avance entra por la bitácora, que es su única fuente (D6).
        for actividad, delta in (
            (ids["actividad_excav"], 130),
            (ids["actividad_extra"], 10),
        ):
            await conn.execute(
                text(
                    "insert into registro_avance (org_id, actividad_id, "
                    "delta_ejecutado, usuario_id) "
                    "values (:org, :act, :delta, :usr)"
                ),
                {
                    "org": org,
                    "act": str(actividad),
                    "delta": delta,
                    "usr": str(escenario.residente_id),
                },
            )
    await admin.dispose()
    return ids


class TestPresupuesto:
    async def test_la_obra_llega_a_su_presupuesto_por_el_prototipo(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        ids = await _sembrar_presupuesto(escenario)

        async with sesion_con_rls(contexto_control) as sesion:
            repo = RepositorioPresupuestosSQL(sesion)
            cabecera = await repo.presupuesto_de_obra(escenario.obra_id)
            partidas = await repo.partidas(ids["presupuesto"])

        assert cabecera is not None
        assert str(cabecera["id"]) == str(ids["presupuesto"])
        assert cabecera["monto_total"] == Decimal("150000.0000")
        assert len(partidas) == 2
        # Con la descripción de su concepto: sin ella, la pantalla mostraría
        # uuids.
        assert all(p["concepto_descripcion"] for p in partidas)

    async def test_vigente_de_prototipo_no_necesita_pasar_por_una_obra(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """`GET /prototipos/{id}/presupuesto` (el árbol de Prototipos y
        Programas base, que no tienen una obra a mano) resuelve igual que
        `presupuesto_de_obra`, con `unidad_clave`/`precio_unitario`/
        `importe` por partida — las columnas que la pantalla necesita."""
        ids = await _sembrar_presupuesto(escenario)

        async with sesion_con_rls(contexto_control) as sesion:
            repo = RepositorioPresupuestosSQL(sesion)
            cabecera = await repo.vigente_de_prototipo(escenario.prototipo_id)
            assert cabecera is not None
            partidas = await repo.partidas(uuid.UUID(str(cabecera["id"])))

        assert str(cabecera["id"]) == str(ids["presupuesto"])
        excav = next(p for p in partidas if p["concepto_id"] == ids["concepto_excav"])
        assert excav["cantidad"] == Decimal("100")
        assert excav["precio_unitario"] == Decimal("1000")
        assert excav["importe"] == Decimal("100000")

    async def test_una_obra_sin_presupuesto_devuelve_nada_y_no_revienta(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """El escenario no tiene presupuesto cargado: es el caso normal antes de
        la primera carga de Excel, no un error."""
        async with sesion_con_rls(contexto_control) as sesion:
            assert (
                await RepositorioPresupuestosSQL(sesion).presupuesto_de_obra(
                    escenario.obra_id
                )
                is None
            )

    async def test_el_historial_trae_las_versiones(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        await _sembrar_presupuesto(escenario)
        async with sesion_con_rls(contexto_control) as sesion:
            versiones = await RepositorioPresupuestosSQL(sesion).versiones_de_prototipo(
                escenario.prototipo_id
            )
        assert len(versiones) == 1
        assert versiones[0]["vigente"] is True


class TestRendimientoPorConcepto:
    async def test_incluye_las_dos_caras_que_faltan(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """Un `left join` desde el presupuesto habría escondido el extra, que es
        justo el que explica el sobrecosto."""
        await _sembrar_presupuesto(escenario)

        async with sesion_con_rls(contexto_control) as sesion:
            filas = await RepositorioPresupuestosSQL(sesion).rendimiento_por_concepto(
                escenario.obra_id
            )

        por_clave = {
            (f["concepto_clave"] or "SIN_CONCEPTO").split("-")[0]: f for f in filas
        }

        # Presupuestado 100 000, ejecutado 130 000.
        excav = por_clave["EXCAV"]
        assert excav["importe_presupuestado"] == Decimal("100000.0000")
        assert excav["importe_ejecutado"] == Decimal("130000.0000")

        # Presupuestado y **sin ejecutar**: sigue en la lista.
        pint = por_clave["PINT"]
        assert pint["importe_presupuestado"] == Decimal("50000.0000")
        assert pint["cantidad_ejecutada"] == Decimal(0)

        # Ejecutado **sin presupuestar**: el extra.
        extra = por_clave["SIN_CONCEPTO"]
        assert extra["importe_presupuestado"] == Decimal(0)
        assert extra["importe_ejecutado"] == Decimal("20000.0000")
        assert extra["extra"] is True

    async def test_el_destajo_se_valua_con_su_precio(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """El modo de pago decide qué precio vale (§7.3): valuar un destajo con
        el precio unitario daría un importe que nadie va a pagar."""
        admin = create_async_engine(DATABASE_URL_ADMIN)
        actividad = uuid.uuid4()
        async with admin.begin() as conn:
            await conn.execute(
                text(
                    "insert into actividad (id, org_id, obra_id, descripcion, "
                    "cant_base, cant_programada, modo_pago, precio_unitario, "
                    "precio_destajo) "
                    "values (:id, :org, :obra, 'A destajo', 10, 10, 'destajo', "
                    "9999, 500)"
                ),
                {
                    "id": str(actividad),
                    "org": str(escenario.org_id),
                    "obra": str(escenario.obra_id),
                },
            )
            await conn.execute(
                text(
                    "insert into registro_avance (org_id, actividad_id, "
                    "delta_ejecutado, usuario_id) values (:org, :act, 10, :usr)"
                ),
                {
                    "org": str(escenario.org_id),
                    "act": str(actividad),
                    "usr": str(escenario.residente_id),
                },
            )
        await admin.dispose()

        async with sesion_con_rls(contexto_control) as sesion:
            filas = await RepositorioPresupuestosSQL(sesion).rendimiento_por_concepto(
                escenario.obra_id
            )

        sin_concepto = next(f for f in filas if f["concepto_id"] is None)
        # 10 × 500 del destajo, no 10 × 9999 del unitario.
        assert sin_concepto["importe_ejecutado"] == Decimal("5000.0000")


class TestRendimientoPorCuadrilla:
    async def test_suma_lo_que_produjo_cada_una(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        await _sembrar_presupuesto(escenario)

        async with sesion_con_rls(contexto_control) as sesion:
            filas = await RepositorioPresupuestosSQL(sesion).rendimiento_por_cuadrilla(
                escenario.obra_id
            )

        assert len(filas) == 1
        assert filas[0]["cantidad_ejecutada"] == Decimal("130.000000")
        assert filas[0]["rendimiento_esperado"] == Decimal("12.000000")
        # El extra no tiene cuadrilla: no debe inventarse una fila para él.
        assert filas[0]["actividades"] == 1


class TestResumenPorObra:
    async def test_compara_obra_por_obra(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        await _sembrar_presupuesto(escenario)

        async with sesion_con_rls(contexto_control) as sesion:
            filas = await RepositorioPresupuestosSQL(sesion).resumen_por_obra()

        obra = next(f for f in filas if str(f["obra_id"]) == str(escenario.obra_id))
        assert obra["monto_presupuestado"] == Decimal("150000.0000")
        # 130 000 de excavación + 20 000 del extra.
        assert obra["monto_ejecutado"] == Decimal("150000.0000")
        assert obra["proyecto_clave"]

    async def test_el_alcance_lo_impone_rls(
        self, escenario: Escenario, contexto_ajeno: ContextoSesion
    ) -> None:
        """Arranca en `obra`, que trae su política: no hay `where org_id` a mano
        en la consulta y no debería haberlo."""
        await _sembrar_presupuesto(escenario)

        async with sesion_con_rls(contexto_ajeno) as sesion:
            filas = await RepositorioPresupuestosSQL(sesion).resumen_por_obra()

        assert str(escenario.obra_id) not in {str(f["obra_id"]) for f in filas}

    async def test_el_filtro_por_proyecto_no_amplia_el_alcance(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        async with sesion_con_rls(contexto_control) as sesion:
            filas = await RepositorioPresupuestosSQL(sesion).resumen_por_obra(
                proyecto_id=uuid.uuid4()
            )
        assert filas == []
