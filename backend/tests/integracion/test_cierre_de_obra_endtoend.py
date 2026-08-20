"""Cierre de obra final contra Postgres real — workflow D (§11.3 D).

Lo que solo se prueba aquí:

· Que el **estado que decide la entrega** se arme de siete contextos en una
  consulta y salga correcto. Es la parte que un mock daría siempre por buena.
· Que la obra quede **congelada en la misma transacción** que el cierre. Si eso
  se hubiera dejado al bus de eventos —que se traga los fallos a propósito—,
  una obra podría quedar cerrada y seguir admitiendo capturas.
· Que el acta no se pueda firmar dos veces desde dos peticiones.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.repos.cierres_obra_sql import RepositorioCierresDeObraSQL
from obractrl.adapters.repos.obras_sql import RepositorioObrasSQL
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL
from obractrl.application.casos_uso.gestionar_cierre_de_obra import (
    AbrirCierreDeObra,
    ComandoAbrirCierreDeObra,
    ComandoParticipar,
    Participar,
)
from obractrl.application.eventos import BusEnProceso
from obractrl.domain.cierres.obra import ErrorDeCierreDeObra
from obractrl.domain.shared.diccionario import Rol
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario


async def _dejar_obra_lista(escenario: Escenario) -> None:
    """Avance al 100 %, actividad concluida y sin nada esperando.

    Se hace con el rol admin: aquí se prepara el escenario, no se prueba el
    aislamiento —eso lo cubren `database/tests/`—.
    """
    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        await conn.execute(
            text("update obra set avance_pct = 100 where id = :id"),
            {"id": str(escenario.obra_id)},
        )
        await conn.execute(
            text("update actividad set estatus = 'concluida' where obra_id = :obra"),
            {"obra": str(escenario.obra_id)},
        )
    await admin.dispose()


async def _abrir(ctx: ContextoSesion, obra_id: uuid.UUID):
    async with sesion_con_rls(ctx) as sesion:
        caso = AbrirCierreDeObra(
            cierres=RepositorioCierresDeObraSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
        )
        return await caso.ejecutar(
            ComandoAbrirCierreDeObra(
                obra_id=obra_id,
                usuario_id=uuid.UUID(str(ctx.usuario_id)),
                rol=Rol(ctx.rol),
            )
        )


async def _participar(ctx: ContextoSesion, cierre_id: uuid.UUID, **extra: object):
    async with sesion_con_rls(ctx) as sesion:
        caso = Participar(
            cierres=RepositorioCierresDeObraSQL(sesion),
            obras=RepositorioObrasSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
            eventos=BusEnProceso(),
        )
        return await caso.ejecutar(
            ComandoParticipar(
                cierre_id=cierre_id,
                usuario_id=uuid.UUID(str(ctx.usuario_id)),
                rol=Rol(ctx.rol),
                **extra,  # type: ignore[arg-type]
            )
        )


def _contexto(escenario: Escenario, rol: Rol, usuario: uuid.UUID) -> ContextoSesion:
    return ContextoSesion(
        org_id=escenario.org_id, usuario_id=usuario, rol=rol.value
    )


class TestAbrir:
    async def test_el_super_intendente_abre_y_reune_pendientes(
        self, escenario: Escenario
    ) -> None:
        si = _contexto(escenario, Rol.SUPER_INTENDENTE, escenario.control_id)
        resultado = await _abrir(si, escenario.obra_id)

        assert resultado.estatus == "en_proceso"
        # La obra del escenario está a medias: abrir con pendientes es
        # justamente lo que convoca al equipo a resolverlos (§11.3 D.1).
        assert resultado.pendientes
        assert set(resultado.faltan) == set(Rol)

    async def test_control_de_obra_no_abre_el_cierre(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        with pytest.raises(ErrorDeCierreDeObra):
            await _abrir(contexto_control, escenario.obra_id)

    async def test_abrir_dos_veces_devuelve_el_mismo_acta(
        self, escenario: Escenario
    ) -> None:
        """`uq_cierre_obra`: una obra tiene un cierre. Un doble clic no puede
        crear dos actas ni dar un 500."""
        si = _contexto(escenario, Rol.SUPER_INTENDENTE, escenario.control_id)
        primero = await _abrir(si, escenario.obra_id)
        segundo = await _abrir(si, escenario.obra_id)
        assert primero.id == segundo.id


class TestEstadoDeLaObra:
    async def test_junta_los_siete_contextos(self, escenario: Escenario) -> None:
        si = _contexto(escenario, Rol.SUPER_INTENDENTE, escenario.control_id)
        async with sesion_con_rls(si) as sesion:
            estado = await RepositorioCierresDeObraSQL(sesion).estado_de_obra(
                escenario.obra_id
            )

        assert estado is not None
        for clave in (
            "avance_pct",
            "actividades_sin_concluir",
            "cierres_pendientes",
            "estimaciones_sin_validar",
            "incidencias_abiertas",
            "incidencias_detienen",
            "documentos_expediente",
            "evaluaciones_finales",
        ):
            assert clave in estado, f"falta {clave} en el estado de la obra"

    async def test_otra_organizacion_no_ve_el_estado(
        self, escenario: Escenario, contexto_ajeno: ContextoSesion
    ) -> None:
        async with sesion_con_rls(contexto_ajeno) as sesion:
            estado = await RepositorioCierresDeObraSQL(sesion).estado_de_obra(
                escenario.obra_id
            )
        assert estado is None


class TestFirmarElActa:
    async def test_los_cuatro_firman_y_la_obra_queda_entregada(
        self, escenario: Escenario
    ) -> None:
        await _dejar_obra_lista(escenario)

        si = _contexto(escenario, Rol.SUPER_INTENDENTE, escenario.control_id)
        cierre = await _abrir(si, escenario.obra_id)

        await _participar(
            _contexto(escenario, Rol.RESIDENTE, escenario.residente_id), cierre.id
        )
        await _participar(
            _contexto(escenario, Rol.SUPERVISOR, escenario.supervisor_id), cierre.id
        )
        await _participar(
            _contexto(escenario, Rol.CONTROL_OBRA, escenario.control_id), cierre.id
        )
        ultimo = await _participar(si, cierre.id, acta="Entregada sin observaciones")

        assert ultimo.cerro_la_obra is True
        assert ultimo.estatus == "cerrada"

        # Congelada **en la misma transacción**: si esto se hubiera dejado al
        # bus —que se traga los fallos— la obra podría quedar cerrada y seguir
        # admitiendo capturas sobre un acta ya firmada.
        async with sesion_con_rls(si) as sesion:
            obra = await RepositorioObrasSQL(sesion).obtener(escenario.obra_id)
        assert obra is not None
        assert obra["estatus"] == "entregada"

    async def test_no_se_firma_con_trabajo_sin_resolver(
        self, escenario: Escenario
    ) -> None:
        """La obra del escenario va a medias: la cuarta firma tiene que fallar
        **antes** de escribir nada, o quedaría un acta completa sobre una obra
        que no se puede entregar."""
        si = _contexto(escenario, Rol.SUPER_INTENDENTE, escenario.control_id)
        cierre = await _abrir(si, escenario.obra_id)

        await _participar(
            _contexto(escenario, Rol.RESIDENTE, escenario.residente_id), cierre.id
        )
        await _participar(
            _contexto(escenario, Rol.SUPERVISOR, escenario.supervisor_id), cierre.id
        )
        await _participar(
            _contexto(escenario, Rol.CONTROL_OBRA, escenario.control_id), cierre.id
        )

        with pytest.raises(ErrorDeCierreDeObra, match="no se puede entregar"):
            await _participar(si, cierre.id)

        async with sesion_con_rls(si) as sesion:
            repo = RepositorioCierresDeObraSQL(sesion)
            fila = await repo.obtener(cierre.id)
            participaciones = await repo.participaciones(cierre.id)

        assert fila is not None
        assert fila["estatus"] == "en_proceso"
        # Tres, no cuatro: la que falló no se registró.
        assert len(participaciones) == 3

    async def test_un_rol_no_firma_dos_veces(self, escenario: Escenario) -> None:
        si = _contexto(escenario, Rol.SUPER_INTENDENTE, escenario.control_id)
        cierre = await _abrir(si, escenario.obra_id)
        residente = _contexto(escenario, Rol.RESIDENTE, escenario.residente_id)

        await _participar(residente, cierre.id)
        with pytest.raises(ErrorDeCierreDeObra, match="ya registró"):
            await _participar(residente, cierre.id)

    async def test_el_acta_no_se_cierra_dos_veces(self, escenario: Escenario) -> None:
        """El `and estatus = 'en_proceso'` del `UPDATE` es lo que impide que dos
        peticiones simultáneas cierren la misma obra y publiquen el evento dos
        veces."""
        from obractrl.adapters.repos.cierres_obra_sql import CierreDeObraNoModificado

        await _dejar_obra_lista(escenario)
        si = _contexto(escenario, Rol.SUPER_INTENDENTE, escenario.control_id)
        cierre = await _abrir(si, escenario.obra_id)

        async with sesion_con_rls(si) as sesion:
            repo = RepositorioCierresDeObraSQL(sesion)
            await repo.cerrar(cierre.id, fecha=__import__("datetime").date.today(), acta=None)
            await sesion.commit()

            with pytest.raises(CierreDeObraNoModificado):
                await repo.cerrar(
                    cierre.id, fecha=__import__("datetime").date.today(), acta=None
                )

    async def test_la_participacion_guarda_lo_que_dijo_cada_rol(
        self, escenario: Escenario
    ) -> None:
        si = _contexto(escenario, Rol.SUPER_INTENDENTE, escenario.control_id)
        cierre = await _abrir(si, escenario.obra_id)

        await _participar(
            _contexto(escenario, Rol.RESIDENTE, escenario.residente_id),
            cierre.id,
            comentario="Entrego con detalles menores",
            evidencias=("evidencias/foto-1.jpg",),
        )

        async with sesion_con_rls(si) as sesion:
            participaciones = await RepositorioCierresDeObraSQL(sesion).participaciones(
                cierre.id
            )

        assert len(participaciones) == 1
        assert participaciones[0]["comentario"] == "Entrego con detalles menores"
        assert participaciones[0]["evidencias"] == ["evidencias/foto-1.jpg"]
        assert participaciones[0]["usuario_nombre"]


class TestAislamiento:
    async def test_otra_organizacion_no_abre_el_cierre(
        self, escenario: Escenario, contexto_ajeno: ContextoSesion
    ) -> None:
        """`contexto_ajeno` es super intendente de otra org: pasa el permiso de
        rol y lo detiene RLS, que es donde tiene que detenerse.

        La política rechaza el `INSERT` con `insufficient_privilege` — no deja
        que la fila entre y se descubra después—, así que lo que sube es la
        excepción del driver y no un `RegistroNoEncontrado`. Es la falla
        correcta: cuanto antes se detenga, menos hay que deshacer.
        """
        with pytest.raises(Exception, match="pol"):
            await _abrir(contexto_ajeno, escenario.obra_id)

    async def test_la_bandeja_no_muestra_cierres_ajenos(
        self, escenario: Escenario, contexto_ajeno: ContextoSesion
    ) -> None:
        si = _contexto(escenario, Rol.SUPER_INTENDENTE, escenario.control_id)
        cierre = await _abrir(si, escenario.obra_id)

        async with sesion_con_rls(contexto_ajeno) as sesion:
            filas = await RepositorioCierresDeObraSQL(sesion).listar()

        assert str(cierre.id) not in {str(f["id"]) for f in filas}


async def test_el_avance_incompleto_bloquea_aunque_todo_lo_demas_este(
    escenario: Escenario,
) -> None:
    """El caso que más se va a dar en el piloto: la obra está "terminada" para
    todos pero el avance quedó en 99.8 % por un redondeo de captura."""
    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        await conn.execute(
            text("update obra set avance_pct = 99.8 where id = :id"),
            {"id": str(escenario.obra_id)},
        )
        await conn.execute(
            text("update actividad set estatus = 'concluida' where obra_id = :obra"),
            {"obra": str(escenario.obra_id)},
        )
    await admin.dispose()

    si = _contexto(escenario, Rol.SUPER_INTENDENTE, escenario.control_id)
    cierre = await _abrir(si, escenario.obra_id)

    bloqueantes = [p for p in cierre.pendientes if p.bloquea]
    assert [p.clave for p in bloqueantes] == ["avance_incompleto"]
    # El detalle dice el avance real, no un genérico: "falta avance" obligaría
    # a ir a buscar cuánto falta a otra pantalla.
    assert "99.8" in bloqueantes[0].detalle
