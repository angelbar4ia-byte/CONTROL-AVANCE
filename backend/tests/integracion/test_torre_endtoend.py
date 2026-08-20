"""La Torre de control contra Postgres real (§5.1, §12.4).

Lo que solo se puede probar aquí: que los contadores se calculen **dentro del
alcance de quien pregunta**. La consulta de la Torre no filtra por `org_id` a
mano —lo impone RLS—, así que si una política cambiara, un supervisor podría
empezar a ver conteos de obras que no son suyas y ninguna prueba de dominio lo
notaría.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.repos.torre_sql import RepositorioTorreSQL
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario


async def _sembrar_pendientes(escenario: Escenario) -> None:
    """Una incidencia abierta que detiene y un cierre esperando autorización."""
    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "insert into incidencia (org_id, obra_id, tipo, impacto, "
                "estatus, titulo) "
                "values (:org, :obra, 'falta_material', 'detiene', 'abierta', "
                "'detiene la obra')"
            ),
            {"org": str(escenario.org_id), "obra": str(escenario.obra_id)},
        )
        # Una rechazada: **no** debe contar. Es el caso que un
        # `estatus <> 'cerrada'` habría sumado como trabajo pendiente.
        await conn.execute(
            text(
                "insert into incidencia (org_id, obra_id, tipo, impacto, "
                "estatus, titulo) "
                "values (:org, :obra, 'detalle', 'detalle', 'rechazada', "
                "'no cuenta')"
            ),
            {"org": str(escenario.org_id), "obra": str(escenario.obra_id)},
        )
        await conn.execute(
            text(
                "insert into solicitud_cierre (org_id, actividad_id, solicitada_por, "
                "cantidad, monto, estatus) "
                "values (:org, :act, :usr, 1, 100, 'solicitada')"
            ),
            {
                "org": str(escenario.org_id),
                "act": str(escenario.actividad_id),
                "usr": str(escenario.residente_id),
            },
        )
        # Una validada: ya no le toca a nadie y no debe contar como pendiente.
        # `ck_cierre_validada` exige que traiga quién autorizó y quién validó
        # (§11.3 C): el esquema no deja fabricar un cierre validado de la nada,
        # y está bien que no deje.
        await conn.execute(
            text(
                "insert into solicitud_cierre (org_id, actividad_id, solicitada_por, "
                "autorizada_por, validada_por, cantidad, monto, estatus) "
                "values (:org, :act, :res, :sup, :ctrl, 1, 100, 'validada')"
            ),
            {
                "org": str(escenario.org_id),
                "act": str(escenario.actividad_id),
                "res": str(escenario.residente_id),
                "sup": str(escenario.supervisor_id),
                "ctrl": str(escenario.control_id),
            },
        )
        await conn.execute(
            text("update actividad set bloqueada = true where id = :id"),
            {"id": str(escenario.actividad_id)},
        )
    await admin.dispose()


class TestEstadoDeObras:
    async def test_cuenta_lo_que_le_toca_a_alguien(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        await _sembrar_pendientes(escenario)

        async with sesion_con_rls(contexto_control) as sesion:
            filas = await RepositorioTorreSQL(sesion).estado_de_obras()

        obra = next(f for f in filas if str(f["obra_id"]) == str(escenario.obra_id))
        # Una abierta de las dos: la rechazada no le toca a nadie.
        assert obra["incidencias_abiertas"] == 1
        assert obra["incidencias_detienen"] == 1
        # Un cierre de los dos: el validado ya se resolvió.
        assert obra["cierres_pendientes"] == 1
        assert obra["bloqueadas"] == 1
        assert obra["actividades"] >= 1

    async def test_trae_el_contexto_para_ubicar_la_obra(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """Clave de proyecto y de cluster: sin ellas, una lista de ochenta obras
        con clave 'FRESNO 01' no dice de qué desarrollo es cada una."""
        async with sesion_con_rls(contexto_control) as sesion:
            filas = await RepositorioTorreSQL(sesion).estado_de_obras()

        obra = next(f for f in filas if str(f["obra_id"]) == str(escenario.obra_id))
        assert obra["proyecto_clave"]
        assert obra["cluster_clave"]
        assert str(obra["proyecto_id"]) == str(escenario.proyecto_id)

    async def test_el_filtro_de_pendientes_deja_lo_que_estorba(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        async with sesion_con_rls(contexto_control) as sesion:
            repo = RepositorioTorreSQL(sesion)
            sin_pendientes = await repo.estado_de_obras(solo_con_pendientes=True)
            assert all(
                f["incidencias_abiertas"] > 0
                or f["cierres_pendientes"] > 0
                or f["bloqueadas"] > 0
                for f in sin_pendientes
            ), "el filtro dejó pasar una obra sin nada pendiente"

    async def test_el_filtro_por_proyecto_no_amplia_el_alcance(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """Pedir un proyecto ajeno devuelve vacío, no las obras de ese proyecto:
        el filtro acota lo visible, nunca lo abre."""
        async with sesion_con_rls(contexto_control) as sesion:
            filas = await RepositorioTorreSQL(sesion).estado_de_obras(
                proyecto_id=uuid.uuid4()
            )
        assert filas == []

    async def test_otra_organizacion_no_ve_nada(
        self, escenario: Escenario, contexto_ajeno: ContextoSesion
    ) -> None:
        async with sesion_con_rls(contexto_ajeno) as sesion:
            filas = await RepositorioTorreSQL(sesion).estado_de_obras()
        claves = {str(f["obra_id"]) for f in filas}
        assert str(escenario.obra_id) not in claves


class TestActividades:
    async def test_lista_las_de_la_obra(
        self, escenario: Escenario, contexto_residente: ContextoSesion
    ) -> None:
        async with sesion_con_rls(contexto_residente) as sesion:
            filas = await RepositorioTorreSQL(sesion).actividades_de_obra(
                escenario.obra_id
            )
        assert any(str(f["id"]) == str(escenario.actividad_id) for f in filas)

    async def test_una_obra_fuera_del_alcance_da_lista_vacia(
        self, escenario: Escenario, contexto_ajeno: ContextoSesion
    ) -> None:
        """No 404: RLS ya la hizo invisible, y distinguir "no existe" de "no la
        ves" hacia afuera sería filtrar su existencia (§12.4)."""
        async with sesion_con_rls(contexto_ajeno) as sesion:
            filas = await RepositorioTorreSQL(sesion).actividades_de_obra(
                escenario.obra_id
            )
        assert filas == []

    async def test_el_detalle_trae_la_obra_a_la_que_pertenece(
        self, escenario: Escenario, contexto_residente: ContextoSesion
    ) -> None:
        async with sesion_con_rls(contexto_residente) as sesion:
            fila = await RepositorioTorreSQL(sesion).actividad(escenario.actividad_id)
        assert fila is not None
        assert fila["obra_clave"]
        assert str(fila["obra_id"]) == str(escenario.obra_id)

    async def test_el_detalle_de_otra_organizacion_no_existe(
        self, escenario: Escenario, contexto_ajeno: ContextoSesion
    ) -> None:
        async with sesion_con_rls(contexto_ajeno) as sesion:
            fila = await RepositorioTorreSQL(sesion).actividad(escenario.actividad_id)
        assert fila is None

    async def test_el_filtro_por_estatus_no_truena_con_el_enum(
        self, escenario: Escenario, contexto_residente: ContextoSesion
    ) -> None:
        """`estatus_actividad` es un enum de Postgres: un valor que no existe
        daría un error de tipo, no una lista vacía."""
        async with sesion_con_rls(contexto_residente) as sesion:
            filas = await RepositorioTorreSQL(sesion).actividades_de_obra(
                escenario.obra_id, estatus="concluida"
            )
        assert isinstance(filas, list)
