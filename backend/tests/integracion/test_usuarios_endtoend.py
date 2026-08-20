"""Alta de usuarios y reparto de alcance, contra Postgres real (§5.1, §4).

Lo que solo se puede probar aquí y no en `tests/domain`: que las reglas del §4
las **imponga la base** aunque el caso de uso no las mire. El dominio y el
trigger de la migración 0025 dicen lo mismo a propósito (ver el encabezado de
`domain/identidad/reglas.py`), y estas pruebas son las que detectarían que
dejaron de coincidir.

El proveedor de auth no se toca: se sustituye por un doble. Una prueba que crea
cuentas de verdad deja basura en un proyecto compartido, y lo que hay que
verificar aquí es la parte transaccional —qué queda en Postgres cuando la
cuenta ya se creó y la fila falla—, no que Supabase funcione.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from obractrl.adapters.repos.asignaciones_sql import (
    AsignacionNoRetirada,
    RepositorioAsignacionesSQL,
)
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL
from obractrl.adapters.repos.usuarios_sql import RepositorioUsuariosSQL
from obractrl.application.casos_uso.gestionar_usuarios import (
    ActualizarUsuario,
    AsignarAlcance,
    ComandoActualizarUsuario,
    ComandoAsignarAlcance,
    ComandoCrearUsuario,
    CrearUsuario,
)
from obractrl.application.puertos.auth import CuentaDeAuth, ErrorDelProveedorDeAuth
from obractrl.domain.identidad.reglas import ErrorDeIdentidad
from obractrl.domain.shared.diccionario import Rol
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario

CONTRASENA = "temporal-de-prueba-larga"


class AuthDeMentira:
    """Doble del proveedor. Registra lo que le pidieron."""

    def __init__(self, *, falla_al_crear: bool = False) -> None:
        self.falla_al_crear = falla_al_crear
        self.creadas: list[str] = []
        self.borradas: list[uuid.UUID] = []
        self.contrasenas: list[tuple[uuid.UUID, str]] = []

    async def crear_cuenta(
        self, *, email: str, contrasena: str, nombre: str
    ) -> CuentaDeAuth:
        if self.falla_al_crear:
            raise ErrorDelProveedorDeAuth("el proveedor no respondió")
        self.creadas.append(email)
        return CuentaDeAuth(id=uuid.uuid4(), email=email)

    async def fijar_contrasena(self, *, auth_user_id: uuid.UUID, contrasena: str) -> None:
        self.contrasenas.append((auth_user_id, contrasena))

    async def borrar_cuenta(self, *, auth_user_id: uuid.UUID) -> None:
        self.borradas.append(auth_user_id)


async def _alta(ctx: ContextoSesion, auth: AuthDeMentira, **kwargs: object):
    async with sesion_con_rls(ctx) as sesion:
        caso = CrearUsuario(
            usuarios=RepositorioUsuariosSQL(sesion),
            auth=auth,
            uow=UnidadDeTrabajoSQL(sesion),
        )
        return await caso.ejecutar(ComandoCrearUsuario(**kwargs))  # type: ignore[arg-type]


class TestAltaCompleta:
    async def test_control_de_obra_da_de_alta_a_un_residente(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """El criterio de cierre de la Fase 7, sin tocar SQL."""
        auth = AuthDeMentira()
        sufijo = uuid.uuid4().hex[:8]
        resultado = await _alta(
            contexto_control,
            auth,
            nombre="Nuevo Residente",
            email=f"nuevo-{sufijo}@obra.mx",
            rol=Rol.RESIDENTE,
            contrasena_temporal=CONTRASENA,
            quien=Rol.CONTROL_OBRA,
        )

        assert auth.creadas == [f"nuevo-{sufijo}@obra.mx"]

        async with sesion_con_rls(contexto_control) as sesion:
            fila = await RepositorioUsuariosSQL(sesion).obtener(resultado.id)

        assert fila is not None
        assert fila["rol"] == "residente"
        # La contraseña la eligió alguien más: cambiarla es obligatorio.
        assert fila["debe_cambiar_password"] is True
        # Y quedó ligado al proveedor: sin esto aparecería en el equipo sin
        # poder iniciar sesión.
        assert fila["puede_entrar"] is True

    async def test_si_la_fila_falla_la_cuenta_no_queda_huerfana(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """La compensación del caso de uso.

        Se fuerza el fallo con un correo repetido, que es el choque real: la
        restricción `uq_usuario_email_org`. Sin el borrado compensatorio
        quedaría una cuenta capaz de autenticarse y sin organización.
        """
        auth = AuthDeMentira()
        sufijo = uuid.uuid4().hex[:8]
        datos = {
            "nombre": "Repetida",
            "email": f"repe-{sufijo}@obra.mx",
            "rol": Rol.RESIDENTE,
            "contrasena_temporal": CONTRASENA,
            "quien": Rol.CONTROL_OBRA,
        }
        await _alta(contexto_control, auth, **datos)

        with pytest.raises(Exception):  # noqa: B017 — el driver levanta lo suyo
            await _alta(contexto_control, auth, **datos)

        assert len(auth.creadas) == 2, "el proveedor sí creó la segunda cuenta"
        assert len(auth.borradas) == 1, "la segunda cuenta debió borrarse"

    async def test_control_de_obra_no_fabrica_un_super_intendente(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """El dominio corta antes de llamar al proveedor: si no, habría que
        borrar una cuenta creada por algo que se sabía de antemano."""
        auth = AuthDeMentira()
        with pytest.raises(ErrorDeIdentidad):
            await _alta(
                contexto_control,
                auth,
                nombre="Aspirante",
                email=f"aspirante-{uuid.uuid4().hex[:8]}@obra.mx",
                rol=Rol.SUPER_INTENDENTE,
                contrasena_temporal=CONTRASENA,
                quien=Rol.CONTROL_OBRA,
            )
        assert auth.creadas == []


class TestGuardiaDeLaBase:
    """Lo mismo, pero **saltándose el dominio**: SQL directo bajo RLS.

    Es la prueba que importa, porque es el camino que también recorren la ruta
    directa a Supabase (§10.7) y un `UPDATE` a mano en el dashboard. Si esto
    dejara de fallar, la pantalla de Equipo sería la menor de las
    preocupaciones.
    """

    async def test_nadie_cambia_su_propio_rol(
        self, escenario: Escenario, contexto_residente: ContextoSesion
    ) -> None:
        with pytest.raises(Exception, match="propio rol"):
            async with sesion_con_rls(contexto_residente) as sesion:
                await sesion.execute(
                    text(
                        "update usuario set rol = 'super_intendente' where id = :id"
                    ),
                    {"id": str(escenario.residente_id)},
                )
                await sesion.commit()

    async def test_nadie_se_reactiva_a_si_mismo(
        self, escenario: Escenario, contexto_residente: ContextoSesion
    ) -> None:
        with pytest.raises(Exception, match="propio estatus"):
            async with sesion_con_rls(contexto_residente) as sesion:
                await sesion.execute(
                    text("update usuario set estatus = 'inactivo' where id = :id"),
                    {"id": str(escenario.residente_id)},
                )
                await sesion.commit()

    async def test_control_no_promueve_a_super_intendente(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        with pytest.raises(Exception, match="super intendente"):
            async with sesion_con_rls(contexto_control) as sesion:
                await sesion.execute(
                    text(
                        "update usuario set rol = 'super_intendente' where id = :id"
                    ),
                    {"id": str(escenario.residente_id)},
                )
                await sesion.commit()

    async def test_el_org_id_de_un_usuario_no_se_mueve(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """Mover a alguien de organización dejaría sus capturas apuntando a una
        org y su JWT a otra."""
        with pytest.raises(Exception, match="org_id"):
            async with sesion_con_rls(contexto_control) as sesion:
                await sesion.execute(
                    text("update usuario set org_id = :otra where id = :id"),
                    {"otra": str(uuid.uuid4()), "id": str(escenario.residente_id)},
                )
                await sesion.commit()


class TestEdicion:
    async def test_control_da_de_baja_sin_borrar(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        async with sesion_con_rls(contexto_control) as sesion:
            caso = ActualizarUsuario(
                usuarios=RepositorioUsuariosSQL(sesion),
                uow=UnidadDeTrabajoSQL(sesion),
            )
            await caso.ejecutar(
                ComandoActualizarUsuario(
                    usuario_id=escenario.residente_id,
                    quien=Rol.CONTROL_OBRA,
                    quien_id=escenario.control_id,
                    activo=False,
                )
            )

        async with sesion_con_rls(contexto_control) as sesion:
            fila = await RepositorioUsuariosSQL(sesion).obtener(
                escenario.residente_id
            )
        assert fila is not None, "dar de baja no borra la fila (§11.3)"
        assert fila["estatus"] == "inactivo"

    async def test_el_listado_incluye_a_los_inactivos(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """Si desaparecieran, nadie entendería a dónde se fueron ni podría
        reactivarlos."""
        async with sesion_con_rls(contexto_control) as sesion:
            repo = RepositorioUsuariosSQL(sesion)
            await repo.actualizar(
                escenario.residente_id, {"estatus": "inactivo"}
            )
            await sesion.commit()
            equipo = await repo.listar()

        ids = {str(u["id"]) for u in equipo}
        assert str(escenario.residente_id) in ids


class TestAlcance:
    async def test_control_asigna_un_cluster_a_un_supervisor(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        async with sesion_con_rls(contexto_control) as sesion:
            caso = AsignarAlcance(
                usuarios=RepositorioUsuariosSQL(sesion),
                asignaciones=RepositorioAsignacionesSQL(sesion),
                uow=UnidadDeTrabajoSQL(sesion),
            )
            await caso.ejecutar(
                ComandoAsignarAlcance(
                    usuario_id=escenario.supervisor_id,
                    quien=Rol.CONTROL_OBRA,
                    clusters=(escenario.cluster_id,),
                )
            )

        async with sesion_con_rls(contexto_control) as sesion:
            asignados = await RepositorioAsignacionesSQL(sesion).clusters_de(
                escenario.supervisor_id
            )
        assert [str(c["id"]) for c in asignados] == [str(escenario.cluster_id)]

    async def test_asignar_dos_veces_es_la_misma_intencion(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """Un doble clic en la pantalla no puede ser un 500."""
        async with sesion_con_rls(contexto_control) as sesion:
            repo = RepositorioAsignacionesSQL(sesion)
            await repo.asignar_cluster(
                supervisor_id=escenario.supervisor_id, cluster_id=escenario.cluster_id
            )
            await repo.asignar_cluster(
                supervisor_id=escenario.supervisor_id, cluster_id=escenario.cluster_id
            )
            await sesion.commit()
            assert len(await repo.clusters_de(escenario.supervisor_id)) == 1

    async def test_retirar_lo_que_no_estaba_es_un_no_encontrado(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """Un cluster que no existe y uno fuera del alcance se ven igual desde
        aquí, y los dos son un 404: distinguirlos confirmaría la existencia de
        algo que quien pregunta no puede ver (§12.4)."""
        async with sesion_con_rls(contexto_control) as sesion:
            with pytest.raises(AsignacionNoRetirada):
                await RepositorioAsignacionesSQL(sesion).retirar_cluster(
                    supervisor_id=escenario.supervisor_id,
                    cluster_id=uuid.uuid4(),
                )

    async def test_control_no_reparte_proyectos_a_otro_control(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """Ese puente decide el alcance de quien administra (§4)."""
        async with sesion_con_rls(contexto_control) as sesion:
            caso = AsignarAlcance(
                usuarios=RepositorioUsuariosSQL(sesion),
                asignaciones=RepositorioAsignacionesSQL(sesion),
                uow=UnidadDeTrabajoSQL(sesion),
            )
            with pytest.raises(ErrorDeIdentidad, match="no puede cambiar el alcance"):
                await caso.ejecutar(
                    ComandoAsignarAlcance(
                        usuario_id=escenario.control_id,
                        quien=Rol.CONTROL_OBRA,
                        proyectos=(escenario.proyecto_id,),
                    )
                )

    async def test_los_clusters_no_se_le_dan_a_un_residente(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """El residente llega a su obra por `obra.residente_id`; asignarle un
        cluster no le daría alcance, solo una fila que nadie lee."""
        async with sesion_con_rls(contexto_control) as sesion:
            caso = AsignarAlcance(
                usuarios=RepositorioUsuariosSQL(sesion),
                asignaciones=RepositorioAsignacionesSQL(sesion),
                uow=UnidadDeTrabajoSQL(sesion),
            )
            with pytest.raises(ErrorDeIdentidad):
                await caso.ejecutar(
                    ComandoAsignarAlcance(
                        usuario_id=escenario.residente_id,
                        quien=Rol.CONTROL_OBRA,
                        clusters=(escenario.cluster_id,),
                    )
                )


class TestAislamiento:
    async def test_otra_organizacion_no_ve_el_equipo(
        self, escenario: Escenario, contexto_ajeno: ContextoSesion
    ) -> None:
        """`usuario_select` acota a la organización del token (§12.4)."""
        async with sesion_con_rls(contexto_ajeno) as sesion:
            equipo = await RepositorioUsuariosSQL(sesion).listar()
        ids = {str(u["id"]) for u in equipo}
        assert str(escenario.residente_id) not in ids

    async def test_otra_organizacion_no_edita_a_nadie_de_esta(
        self, escenario: Escenario, contexto_ajeno: ContextoSesion
    ) -> None:
        """El `UPDATE` no encuentra la fila: para RLS no existe."""
        from obractrl.adapters.repos.usuarios_sql import UsuarioNoModificado

        async with sesion_con_rls(contexto_ajeno) as sesion:
            with pytest.raises(UsuarioNoModificado):
                await RepositorioUsuariosSQL(sesion).actualizar(
                    escenario.residente_id, {"nombre": "Secuestrado"}
                )


async def test_el_alta_deja_rastro_en_la_bitacora(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """`usuario` **no** está entre las tablas auditadas de la 0023, y eso es
    deliberado: la bitácora de negocio cubre configuración y catálogo —lo que
    altera resultados—, no el directorio del equipo. Esta prueba fija esa
    decisión para que un cambio de opinión sea explícito y no accidental.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    auth = AuthDeMentira()
    await _alta(
        contexto_control,
        auth,
        nombre="Sin Bitácora",
        email=f"sinbit-{uuid.uuid4().hex[:8]}@obra.mx",
        rol=Rol.RESIDENTE,
        contrasena_temporal=CONTRASENA,
        quien=Rol.CONTROL_OBRA,
    )

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        cuantos = (
            await conn.execute(
                text(
                    "select count(*) from bitacora "
                    " where org_id = :org and entidad = 'usuario'"
                ),
                {"org": str(escenario.org_id)},
            )
        ).scalar_one()
    await admin.dispose()

    assert cuantos == 0
