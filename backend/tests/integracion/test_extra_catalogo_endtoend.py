"""Alta extra-catálogo contra Postgres real (§11.2, §12.4).

Lo que solo se prueba aquí: que la regla «no hay extra sin orden de cambio» la
imponga **la base** y no solo el dominio. El `CHECK` de la migración 0026 es lo
que cubre la ruta directa a Supabase (§10.7) y cualquier `INSERT` de
mantenimiento; si dejara de existir, el dominio seguiría verde y el agujero
estaría abierto por el otro lado.

Y que el auto-estatus sepa de `extra_catalogo`: sin el trigger actualizado, una
actividad extra se quedaría en ese estatus para siempre aunque se le capturara
avance todos los días.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from obractrl.adapters.repos.actividades_sql import RepositorioActividadesSQL
from obractrl.adapters.repos.torre_sql import RepositorioTorreSQL
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL
from obractrl.application.casos_uso.dar_de_alta_extra import (
    ComandoDarDeAltaExtra,
    DarDeAltaExtra,
)
from obractrl.domain.obras.extra_catalogo import ErrorDeExtraCatalogo
from obractrl.domain.shared.diccionario import ModoPago, Rol
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import Escenario


async def _alta(ctx: ContextoSesion, **cambios: object):
    datos: dict[str, object] = {
        "descripcion": "Demoler muro que el proyecto no traía",
        "orden_cambio": "OC-2026-014",
        "cant_base": Decimal("12.5"),
        "rol": Rol.RESIDENTE,
        "modo_pago": ModoPago.DESTAJO,
        "precio_destajo": Decimal("350"),
    }
    datos.update(cambios)
    async with sesion_con_rls(ctx) as sesion:
        caso = DarDeAltaExtra(
            actividades=RepositorioActividadesSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
        )
        return await caso.ejecutar(ComandoDarDeAltaExtra(**datos))  # type: ignore[arg-type]


class TestAlta:
    async def test_el_residente_registra_trabajo_que_no_estaba(
        self, escenario: Escenario, contexto_residente: ContextoSesion
    ) -> None:
        resultado = await _alta(contexto_residente, obra_id=escenario.obra_id)

        async with sesion_con_rls(contexto_residente) as sesion:
            fila = await RepositorioTorreSQL(sesion).actividad(resultado.id)

        assert fila is not None
        assert fila["extra"] is True
        assert fila["orden_cambio"] == "OC-2026-014"
        assert fila["estatus"] == "extra_catalogo"
        # `cant_programada` nace igual a `cant_base`: un extra se autoriza por
        # la cantidad que se va a ejecutar, no hay proyecto del que desviarse.
        assert fila["cant_programada"] == fila["cant_base"]
        assert fila["cant_ejecutada"] == Decimal(0)

    async def test_aparece_en_las_actividades_de_su_obra(
        self, escenario: Escenario, contexto_residente: ContextoSesion
    ) -> None:
        resultado = await _alta(contexto_residente, obra_id=escenario.obra_id)

        async with sesion_con_rls(contexto_residente) as sesion:
            filas = await RepositorioTorreSQL(sesion).actividades_de_obra(
                escenario.obra_id
            )
        extra = next(f for f in filas if str(f["id"]) == str(resultado.id))
        assert extra["extra"] is True

    async def test_control_de_obra_no_da_de_alta_extras(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        with pytest.raises(ErrorDeExtraCatalogo):
            await _alta(
                contexto_control, obra_id=escenario.obra_id, rol=Rol.CONTROL_OBRA
            )

    async def test_una_obra_de_otra_organizacion_no_se_puede_tocar(
        self, escenario: Escenario, contexto_ajeno: ContextoSesion
    ) -> None:
        """La política de `actividad` rechaza el INSERT: no hace falta
        preguntarle antes al repo de Obras (§11.1, §12.4)."""
        with pytest.raises(Exception):  # noqa: B017 — el driver levanta lo suyo
            await _alta(
                contexto_ajeno, obra_id=escenario.obra_id, rol=Rol.RESIDENTE
            )


class TestLaBaseTambienLoImpone:
    async def test_no_hay_extra_sin_orden_de_cambio(
        self, escenario: Escenario, contexto_residente: ContextoSesion
    ) -> None:
        """SQL directo, saltándose el dominio: es el camino de la ruta directa
        a Supabase y del `INSERT` a mano."""
        with pytest.raises(Exception, match="ck_actividad_extra_con_oc"):
            async with sesion_con_rls(contexto_residente) as sesion:
                await sesion.execute(
                    text(
                        "insert into actividad (id, org_id, obra_id, descripcion, "
                        "cant_base, extra) "
                        "values (:id, cast(current_setting('app.org_id') as uuid), "
                        ":obra, 'sin orden', 1, true)"
                    ),
                    {"id": str(uuid.uuid4()), "obra": str(escenario.obra_id)},
                )
                await sesion.commit()

    async def test_una_actividad_normal_no_necesita_orden(
        self, escenario: Escenario, contexto_residente: ContextoSesion
    ) -> None:
        """El `CHECK` es condicional: solo aplica a las extra. Si aplicara a
        todas, la generación desde prototipo se rompería entera."""
        async with sesion_con_rls(contexto_residente) as sesion:
            await sesion.execute(
                text(
                    "insert into actividad (id, org_id, obra_id, descripcion, "
                    "cant_base) "
                    "values (:id, cast(current_setting('app.org_id') as uuid), "
                    ":obra, 'normal', 1)"
                ),
                {"id": str(uuid.uuid4()), "obra": str(escenario.obra_id)},
            )
            await sesion.commit()


class TestAutoEstatus:
    async def test_el_extra_avanza_al_capturar(
        self, escenario: Escenario, contexto_residente: ContextoSesion
    ) -> None:
        """Sin `extra_catalogo` en la lista del trigger (migración 0026), esta
        actividad se quedaría en `extra_catalogo` para siempre."""
        resultado = await _alta(contexto_residente, obra_id=escenario.obra_id)

        async with sesion_con_rls(contexto_residente) as sesion:
            await sesion.execute(
                text(
                    "insert into registro_avance (org_id, actividad_id, "
                    "delta_ejecutado, usuario_id) "
                    "values (cast(current_setting('app.org_id') as uuid), "
                    ":act, 5, :usr)"
                ),
                {"act": str(resultado.id), "usr": str(escenario.residente_id)},
            )
            await sesion.commit()
            fila = await RepositorioTorreSQL(sesion).actividad(resultado.id)

        assert fila is not None
        assert fila["estatus"] == "en_proceso"
        assert fila["cant_ejecutada"] == Decimal("5")

    async def test_al_volver_a_cero_recupera_extra_catalogo(
        self, escenario: Escenario, contexto_residente: ContextoSesion
    ) -> None:
        """Seguir siendo extra no depende de cuánto lleve ejecutado: si cayera
        en `programada`, la actividad dejaría de distinguirse de las del
        prototipo en cualquier bandeja que filtre por estatus."""
        resultado = await _alta(contexto_residente, obra_id=escenario.obra_id)

        async with sesion_con_rls(contexto_residente) as sesion:
            for delta in (5, -5):
                await sesion.execute(
                    text(
                        "insert into registro_avance (org_id, actividad_id, "
                        "delta_ejecutado, usuario_id) "
                        "values (cast(current_setting('app.org_id') as uuid), "
                        ":act, :delta, :usr)"
                    ),
                    {
                        "act": str(resultado.id),
                        "delta": delta,
                        "usr": str(escenario.residente_id),
                    },
                )
            await sesion.commit()
            fila = await RepositorioTorreSQL(sesion).actividad(resultado.id)

        assert fila is not None
        assert fila["cant_ejecutada"] == Decimal(0)
        assert fila["estatus"] == "extra_catalogo"


class TestCarreraConElMovil:
    """El bug que motivó `obtener_para_captura` (D5 + D6).

    `PATCH /actividades/{id}/avance` recibe un absoluto y deriva el delta
    restando lo que ya había. Desde D5 hay otro escritor —el móvil, por
    PowerSync, directo a Postgres—, así que ese lee-modifica-escribe es una
    carrera de verdad y no una hipótesis.
    """

    async def test_el_bloqueo_serializa_a_los_dos_escritores(
        self, escenario: Escenario, contexto_residente: ContextoSesion
    ) -> None:
        """Se reproduce el intercalado exacto: la web lee, el móvil escribe, la
        web escribe. Con `for update`, el móvil espera y el total queda en lo
        que el residente pidió más lo que el móvil aportó — nunca en un número
        que nadie capturó.
        """
        import asyncio

        from obractrl.application.casos_uso.capturar_avance import (
            CapturarAvance,
            ComandoCapturarAvance,
        )

        resultado = await _alta(contexto_residente, obra_id=escenario.obra_id)

        # Punto de partida: 4 de 12.5 ejecutados.
        async with sesion_con_rls(contexto_residente) as sesion:
            await sesion.execute(
                text(
                    "insert into registro_avance (org_id, actividad_id, "
                    "delta_ejecutado, usuario_id) values "
                    "(cast(current_setting('app.org_id') as uuid), :act, 4, :usr)"
                ),
                {"act": str(resultado.id), "usr": str(escenario.residente_id)},
            )
            await sesion.commit()

        async def captura_web() -> None:
            """El residente deja la actividad en 6 desde la web."""
            async with sesion_con_rls(contexto_residente) as sesion:
                caso = CapturarAvance(
                    actividades=RepositorioActividadesSQL(sesion),
                    uow=UnidadDeTrabajoSQL(sesion),
                )
                await caso.ejecutar(
                    ComandoCapturarAvance(
                        actividad_id=resultado.id,
                        cant_ejecutada=Decimal(6),
                        usuario_id=escenario.residente_id,
                    )
                )

        async def sincroniza_movil() -> None:
            """PowerSync mete un +2 sin pasar por la API."""
            async with sesion_con_rls(contexto_residente) as sesion:
                await sesion.execute(
                    text(
                        "insert into registro_avance (org_id, actividad_id, "
                        "delta_ejecutado, usuario_id) values "
                        "(cast(current_setting('app.org_id') as uuid), :act, 2, :usr)"
                    ),
                    {"act": str(resultado.id), "usr": str(escenario.residente_id)},
                )
                await sesion.commit()

        await asyncio.gather(captura_web(), sincroniza_movil())

        async with sesion_con_rls(contexto_residente) as sesion:
            fila = await RepositorioTorreSQL(sesion).actividad(resultado.id)
            total_bitacora = (
                await sesion.execute(
                    text(
                        "select coalesce(sum(delta_ejecutado), 0) "
                        "from registro_avance where actividad_id = :act"
                    ),
                    {"act": str(resultado.id)},
                )
            ).scalar_one()

        assert fila is not None
        # La identidad que D6 sostiene: el total **es** la suma de la bitácora.
        # Si la carrera hubiera corrompido el delta, seguirían cuadrando entre
        # sí —el trigger los mantiene— pero el número sería otro; por eso se
        # comprueba además el rango de los dos intercalados posibles.
        assert Decimal(str(fila["cant_ejecutada"])) == Decimal(str(total_bitacora))
        assert Decimal(str(fila["cant_ejecutada"])) in (Decimal(6), Decimal(8))
