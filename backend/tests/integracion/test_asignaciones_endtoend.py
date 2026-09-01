"""La cadena de mando, contra Postgres real (§4, §5.1 "Asignaciones").

Spec §4 (roles y alcance) · §5.1 · §12.4 (RLS) · migración 0042.

QUÉ SE PRUEBA AQUÍ Y NO EN OTRO LADO

`tests/domain/test_identidad.py` cubre las reglas puras —quién puede repartir
qué, por rol— y `database/tests/test_rls_asignaciones.sql` cubre las políticas
directamente en SQL. Lo que solo se ve desde aquí es el **encuentro de las
dos**: que el caso de uso y las políticas de la 0042 digan lo mismo, y que
cuando discrepen gane la base.

La diferencia importa porque el dominio contesta la mitad de la pregunta. Puede
decir "un supervisor sí reparte obras entre sus residentes", pero no puede
decir "…siempre que la obra ya le sea visible", porque eso depende de datos.
Esa segunda mitad vive en `app.puede_repartir_obra()` y es la que impide que un
supervisor se amplíe el alcance solo. Si algún día alguien relajara la política
creyendo que el caso de uso ya lo cubre, estas pruebas serían las que fallan.

El escenario del `conftest` ya trae la cadena armada —SI → supervisor →
residente → obra— porque desde la 0042 sin ella nadie ve nada.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.repos.asignaciones_sql import (
    AsignacionNoRetirada,
    RepositorioAsignacionesSQL,
)
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL
from obractrl.adapters.repos.usuarios_sql import RepositorioUsuariosSQL
from obractrl.application.casos_uso.gestionar_usuarios import (
    AsignarAlcance,
    ComandoAsignarAlcance,
)
from obractrl.domain.identidad.reglas import ErrorDeIdentidad
from obractrl.domain.shared.diccionario import Rol
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario


async def _repartir(ctx: ContextoSesion, cmd: ComandoAsignarAlcance) -> None:
    async with sesion_con_rls(ctx) as sesion:
        caso = AsignarAlcance(
            usuarios=RepositorioUsuariosSQL(sesion),
            asignaciones=RepositorioAsignacionesSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
        )
        await caso.ejecutar(cmd)


async def _obras_visibles(ctx: ContextoSesion) -> set[uuid.UUID]:
    """Lo que de verdad importa: qué obras deja ver RLS con esa identidad."""
    async with sesion_con_rls(ctx) as sesion:
        filas = (await sesion.execute(text("select id from obra"))).scalars().all()
    return {uuid.UUID(str(f)) for f in filas}


async def _segunda_obra(escenario: Escenario) -> uuid.UUID:
    """Otra obra en el mismo cluster, SIN residente.

    Se crea con el rol admin porque el punto no es probar el alta sino tener
    una obra que nadie de la cadena vea todavía — la pieza que hace falta para
    comprobar que los mandos intermedios no pueden traérsela.
    """
    obra = uuid.uuid4()
    engine = create_async_engine(DATABASE_URL_ADMIN)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "insert into obra (id, org_id, cluster_id, prototipo_id, clave) "
                "values (:id, :org, :cluster, :prototipo, 'OBRA 02')"
            ),
            {
                "id": str(obra),
                "org": str(escenario.org_id),
                "cluster": str(escenario.cluster_id),
                "prototipo": str(escenario.prototipo_id),
            },
        )
    await engine.dispose()
    return obra


class TestElAlcanceSigueALaGente:
    async def test_mover_un_residente_mueve_su_cartera(
        self,
        escenario: Escenario,
        contexto_control: ContextoSesion,
    ) -> None:
        """Textual del usuario: "al mover un residente, su cartera lo sigue".

        Nadie toca `residente_obra` en esta prueba: se mueve la PERSONA y las
        obras van detrás. Es la diferencia entre el modelo nuevo y el viejo,
        donde había que reasignar cluster por cluster.
        """
        otro = uuid.uuid4()
        engine = create_async_engine(DATABASE_URL_ADMIN)
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "insert into usuario (id, org_id, nombre, email, rol) "
                    "values (:id, :org, 'Sup Dos', :email, 'supervisor')"
                ),
                {
                    "id": str(otro),
                    "org": str(escenario.org_id),
                    "email": f"sup2-{otro.hex[:8]}@test.mx",
                },
            )
        await engine.dispose()

        ctx_otro = ContextoSesion(
            org_id=escenario.org_id, usuario_id=otro, rol="supervisor"
        )
        assert await _obras_visibles(ctx_otro) == set()

        await _repartir(
            contexto_control,
            ComandoAsignarAlcance(
                usuario_id=otro,
                quien=Rol.CONTROL_OBRA,
                gente=(escenario.residente_id,),
            ),
        )

        assert await _obras_visibles(ctx_otro) == {escenario.obra_id}

    async def test_retirar_al_residente_se_lleva_su_cartera(
        self,
        escenario: Escenario,
        contexto_control: ContextoSesion,
        contexto_supervisor: ContextoSesion,
    ) -> None:
        """El alcance no se queda pegado: si se queda, la baja de un supervisor
        no significaría nada."""
        assert await _obras_visibles(contexto_supervisor) == {escenario.obra_id}

        await _repartir(
            contexto_control,
            ComandoAsignarAlcance(
                usuario_id=escenario.supervisor_id,
                quien=Rol.CONTROL_OBRA,
                gente=(escenario.residente_id,),
                retirar=True,
            ),
        )

        assert await _obras_visibles(contexto_supervisor) == set()

    async def test_el_super_intendente_hereda_por_la_cadena(
        self, escenario: Escenario, contexto_super_intendente: ContextoSesion
    ) -> None:
        """Su alcance es el de su gente, y le llega a través del supervisor: el
        SI del escenario nunca tuvo asignado al residente directamente."""
        assert await _obras_visibles(contexto_super_intendente) == {escenario.obra_id}

    async def test_un_super_intendente_sin_gente_no_ve_nada(
        self, escenario: Escenario
    ) -> None:
        """LA INVERSIÓN DE LA 0042, EN UNA SOLA ASERCIÓN.

        Hasta la 0041 este mismo usuario habría visto la organización completa
        solo por tener el rol. Ahora el rol no basta: hace falta que alguien le
        haya asignado gente.
        """
        huerfano = uuid.uuid4()
        engine = create_async_engine(DATABASE_URL_ADMIN)
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "insert into usuario (id, org_id, nombre, email, rol) "
                    "values (:id, :org, 'SI Sin Gente', :email, 'super_intendente')"
                ),
                {
                    "id": str(huerfano),
                    "org": str(escenario.org_id),
                    "email": f"si2-{huerfano.hex[:8]}@test.mx",
                },
            )
        await engine.dispose()

        ctx = ContextoSesion(
            org_id=escenario.org_id, usuario_id=huerfano, rol="super_intendente"
        )
        assert await _obras_visibles(ctx) == set()

    async def test_control_ve_toda_la_organizacion_sin_puente(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """La otra mitad de la inversión: Control ve la obra nueva sin que nadie
        le asigne nada, incluida la que no tiene residente."""
        otra = await _segunda_obra(escenario)
        assert await _obras_visibles(contexto_control) == {escenario.obra_id, otra}


class TestQuienReparteAQuien:
    async def test_el_supervisor_reparte_dentro_de_su_cartera(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """Su trabajo diario: pasarle una obra suya a otro de sus residentes."""
        otro_res = uuid.uuid4()
        engine = create_async_engine(DATABASE_URL_ADMIN)
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "insert into usuario (id, org_id, nombre, email, rol) "
                    "values (:id, :org, 'Res Dos', :email, 'residente')"
                ),
                {
                    "id": str(otro_res),
                    "org": str(escenario.org_id),
                    "email": f"res2-{otro_res.hex[:8]}@test.mx",
                },
            )
        await engine.dispose()

        await _repartir(
            contexto_control,
            ComandoAsignarAlcance(
                usuario_id=escenario.supervisor_id,
                quien=Rol.CONTROL_OBRA,
                gente=(otro_res,),
            ),
        )

        ctx_sup = ContextoSesion(
            org_id=escenario.org_id,
            usuario_id=escenario.supervisor_id,
            rol="supervisor",
        )
        await _repartir(
            ctx_sup,
            ComandoAsignarAlcance(
                usuario_id=otro_res,
                quien=Rol.SUPERVISOR,
                obras=(escenario.obra_id,),
            ),
        )

        async with sesion_con_rls(ctx_sup) as sesion:
            asignadas = await RepositorioAsignacionesSQL(sesion).obras_de(otro_res)
        assert [str(o["id"]) for o in asignadas] == [str(escenario.obra_id)]

    async def test_el_supervisor_no_se_trae_una_obra_que_no_ve(
        self, escenario: Escenario, contexto_supervisor: ContextoSesion
    ) -> None:
        """LA ESCALADA QUE ESTE MODELO TIENE QUE CERRAR.

        El alcance del supervisor ES el de sus residentes. Si pudiera asignarle
        a uno de ellos una obra cualquiera, se ampliaría solo con una fila.

        El caso de uso lo deja pasar a propósito —no puede saber qué obras ve
        alguien— y quien lo rechaza es la política `residente_obra_insert` de
        la 0042. Por eso lo que se espera aquí es un `DBAPIError` y no un
        `ErrorDeIdentidad`: esta prueba verifica que la RED de abajo existe.
        """
        ajena = await _segunda_obra(escenario)
        assert ajena not in await _obras_visibles(contexto_supervisor)

        with pytest.raises(DBAPIError):
            await _repartir(
                contexto_supervisor,
                ComandoAsignarAlcance(
                    usuario_id=escenario.residente_id,
                    quien=Rol.SUPERVISOR,
                    obras=(ajena,),
                ),
            )

        assert ajena not in await _obras_visibles(contexto_supervisor)

    async def test_el_super_intendente_no_amplia_su_propia_gente(
        self, escenario: Escenario, contexto_super_intendente: ContextoSesion
    ) -> None:
        """`superintendente_usuario` decide SU alcance: solo Control la escribe.

        Aquí el corte lo hace el dominio, antes de tocar la base — y la base lo
        volvería a hacer si no.
        """
        with pytest.raises(ErrorDeIdentidad, match="no puede cambiar el alcance"):
            await _repartir(
                contexto_super_intendente,
                ComandoAsignarAlcance(
                    usuario_id=escenario.superintendente_id,
                    quien=Rol.SUPER_INTENDENTE,
                    gente=(escenario.residente_id,),
                ),
            )

    async def test_el_super_intendente_reparte_dentro_de_su_gente(
        self, escenario: Escenario, contexto_super_intendente: ContextoSesion
    ) -> None:
        """Lo que sí puede: mover obras entre residentes que ya alcanza."""
        otro_res = uuid.uuid4()
        engine = create_async_engine(DATABASE_URL_ADMIN)
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "insert into usuario (id, org_id, nombre, email, rol) "
                    "values (:id, :org, 'Res Tres', :email, 'residente')"
                ),
                {
                    "id": str(otro_res),
                    "org": str(escenario.org_id),
                    "email": f"res3-{otro_res.hex[:8]}@test.mx",
                },
            )
            # Cuelga directo del SI, sin supervisor: la forma que el usuario
            # pidió expresamente ("los residentes y supervisores a
            # superintendente").
            await conn.execute(
                text(
                    "insert into superintendente_usuario "
                    "(org_id, superintendente_id, usuario_id) values (:org, :si, :u)"
                ),
                {
                    "org": str(escenario.org_id),
                    "si": str(escenario.superintendente_id),
                    "u": str(otro_res),
                },
            )
        await engine.dispose()

        await _repartir(
            contexto_super_intendente,
            ComandoAsignarAlcance(
                usuario_id=otro_res,
                quien=Rol.SUPER_INTENDENTE,
                obras=(escenario.obra_id,),
            ),
        )

        ctx_res = ContextoSesion(
            org_id=escenario.org_id, usuario_id=otro_res, rol="residente"
        )
        assert await _obras_visibles(ctx_res) == {escenario.obra_id}

    async def test_el_residente_no_se_asigna_obras(
        self, escenario: Escenario, contexto_residente: ContextoSesion
    ) -> None:
        """El fondo de la cadena. Si pudiera, el puente sería decorativo."""
        ajena = await _segunda_obra(escenario)
        with pytest.raises(ErrorDeIdentidad, match="no puede cambiar el alcance"):
            await _repartir(
                contexto_residente,
                ComandoAsignarAlcance(
                    usuario_id=escenario.residente_id,
                    quien=Rol.RESIDENTE,
                    obras=(ajena,),
                ),
            )


class TestElOrganigramaNoAdmiteCualquierPareja:
    async def test_un_supervisor_no_cuelga_de_otro_supervisor(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """Esto la base NO lo comprueba: sus llaves foráneas apuntan a `usuario`
        sin mirar el rol. Es la única regla de esta migración que vive solo en
        el caso de uso, y por eso tiene prueba propia."""
        with pytest.raises(ErrorDeIdentidad, match="no cuelga de un"):
            await _repartir(
                contexto_control,
                ComandoAsignarAlcance(
                    usuario_id=escenario.supervisor_id,
                    quien=Rol.CONTROL_OBRA,
                    gente=(escenario.control_id,),
                ),
            )

    async def test_las_obras_no_se_le_dan_a_un_supervisor(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """Un supervisor llega a las obras por sus residentes; darle una
        directo no le daría alcance, solo una fila que nadie lee."""
        with pytest.raises(ErrorDeIdentidad, match="se asignan a un residente"):
            await _repartir(
                contexto_control,
                ComandoAsignarAlcance(
                    usuario_id=escenario.supervisor_id,
                    quien=Rol.CONTROL_OBRA,
                    obras=(escenario.obra_id,),
                ),
            )

    async def test_de_un_residente_no_cuelga_nadie(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        with pytest.raises(ErrorDeIdentidad, match="no cuelga gente"):
            await _repartir(
                contexto_control,
                ComandoAsignarAlcance(
                    usuario_id=escenario.residente_id,
                    quien=Rol.CONTROL_OBRA,
                    gente=(escenario.supervisor_id,),
                ),
            )


class TestSincroniaConLaColumnaVieja:
    """`obra.residente_id` se conserva como etiqueta de residente principal.

    Todo el código anterior a la 0042 la sigue leyendo —repos, notificaciones,
    reglas de cierre, sync rules— así que las dos representaciones tienen que
    decir lo mismo sin que nadie se acuerde de sincronizarlas. Lo hacen dos
    triggers, y esto es lo que pasaría si alguien los quitara.
    """

    async def test_asignar_por_el_puente_pone_la_etiqueta(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        huerfana = await _segunda_obra(escenario)

        await _repartir(
            contexto_control,
            ComandoAsignarAlcance(
                usuario_id=escenario.residente_id,
                quien=Rol.CONTROL_OBRA,
                obras=(huerfana,),
            ),
        )

        async with sesion_con_rls(contexto_control) as sesion:
            principal = (
                await sesion.execute(
                    text("select residente_id from obra where id = :id"),
                    {"id": str(huerfana)},
                )
            ).scalar_one()
        assert uuid.UUID(str(principal)) == escenario.residente_id

    async def test_retirar_del_puente_limpia_la_etiqueta(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """Dejarla apuntando a quien ya no lleva la obra sería peor que
        dejarla nula: los repos y las notificaciones leen esa columna."""
        await _repartir(
            contexto_control,
            ComandoAsignarAlcance(
                usuario_id=escenario.residente_id,
                quien=Rol.CONTROL_OBRA,
                obras=(escenario.obra_id,),
                retirar=True,
            ),
        )

        async with sesion_con_rls(contexto_control) as sesion:
            principal = (
                await sesion.execute(
                    text("select residente_id from obra where id = :id"),
                    {"id": str(escenario.obra_id)},
                )
            ).scalar_one()
        assert principal is None

    async def test_una_obra_admite_varios_residentes(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """"SON VARIOS RESIDENTES PARA VARIAS OBRAS", textual. El segundo no
        destituye al primero: la etiqueta se queda con quien ya la tenía."""
        segundo = uuid.uuid4()
        engine = create_async_engine(DATABASE_URL_ADMIN)
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "insert into usuario (id, org_id, nombre, email, rol) "
                    "values (:id, :org, 'Res Cuatro', :email, 'residente')"
                ),
                {
                    "id": str(segundo),
                    "org": str(escenario.org_id),
                    "email": f"res4-{segundo.hex[:8]}@test.mx",
                },
            )
        await engine.dispose()

        await _repartir(
            contexto_control,
            ComandoAsignarAlcance(
                usuario_id=segundo,
                quien=Rol.CONTROL_OBRA,
                obras=(escenario.obra_id,),
            ),
        )

        async with sesion_con_rls(contexto_control) as sesion:
            cuantos = (
                await sesion.execute(
                    text(
                        "select count(*) from residente_obra where obra_id = :id"
                    ),
                    {"id": str(escenario.obra_id)},
                )
            ).scalar_one()
            principal = (
                await sesion.execute(
                    text("select residente_id from obra where id = :id"),
                    {"id": str(escenario.obra_id)},
                )
            ).scalar_one()
        assert cuantos == 2
        assert uuid.UUID(str(principal)) == escenario.residente_id

        # Y los dos ven la obra, que es el punto del M2M.
        ctx_segundo = ContextoSesion(
            org_id=escenario.org_id, usuario_id=segundo, rol="residente"
        )
        assert await _obras_visibles(ctx_segundo) == {escenario.obra_id}

    async def test_cambiar_la_columna_mueve_el_puente(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """`update obra set residente_id = B` significa "ahora la lleva B" en
        toda la app. Si el trigger solo agregara a B, el residente anterior
        conservaría el alcance para siempre sin que nadie lo decidiera: una
        concesión silenciosa de permisos."""
        nuevo = uuid.uuid4()
        engine = create_async_engine(DATABASE_URL_ADMIN)
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "insert into usuario (id, org_id, nombre, email, rol) "
                    "values (:id, :org, 'Res Cinco', :email, 'residente')"
                ),
                {
                    "id": str(nuevo),
                    "org": str(escenario.org_id),
                    "email": f"res5-{nuevo.hex[:8]}@test.mx",
                },
            )
        await engine.dispose()

        async with sesion_con_rls(contexto_control) as sesion:
            await sesion.execute(
                text("update obra set residente_id = :res where id = :id"),
                {"res": str(nuevo), "id": str(escenario.obra_id)},
            )
            await sesion.commit()

        ctx_viejo = ContextoSesion(
            org_id=escenario.org_id, usuario_id=escenario.residente_id, rol="residente"
        )
        ctx_nuevo = ContextoSesion(
            org_id=escenario.org_id, usuario_id=nuevo, rol="residente"
        )
        assert await _obras_visibles(ctx_viejo) == set()
        assert await _obras_visibles(ctx_nuevo) == {escenario.obra_id}


class TestConsultaYRetiro:
    async def test_el_alcance_se_consulta_completo(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """Lo que devuelve `GET /usuarios/{id}/alcance` para cada eslabón."""
        async with sesion_con_rls(contexto_control) as sesion:
            repo = RepositorioAsignacionesSQL(sesion)
            gente_si = await repo.gente_de_superintendente(
                escenario.superintendente_id
            )
            residentes = await repo.residentes_de(escenario.supervisor_id)
            obras = await repo.obras_de(escenario.residente_id)

        assert [str(u["id"]) for u in gente_si] == [str(escenario.supervisor_id)]
        assert [str(u["id"]) for u in residentes] == [str(escenario.residente_id)]
        assert [str(o["id"]) for o in obras] == [str(escenario.obra_id)]
        # La obra del escenario llegó por `obra.residente_id`, así que este
        # residente es el principal.
        assert obras[0]["es_principal"] is True

    async def test_retirar_lo_que_no_estaba_es_un_no_encontrado(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """Una asignación inexistente y una fuera de alcance se ven igual desde
        aquí, y las dos son un 404: distinguirlas confirmaría la existencia de
        algo que quien pregunta no puede ver (§12.4)."""
        async with sesion_con_rls(contexto_control) as sesion:
            repo = RepositorioAsignacionesSQL(sesion)
            with pytest.raises(AsignacionNoRetirada):
                await repo.retirar_obra(
                    residente_id=escenario.residente_id, obra_id=uuid.uuid4()
                )
            with pytest.raises(AsignacionNoRetirada):
                await repo.retirar_residente(
                    supervisor_id=escenario.supervisor_id, residente_id=uuid.uuid4()
                )
            with pytest.raises(AsignacionNoRetirada):
                await repo.retirar_persona_de_superintendente(
                    superintendente_id=escenario.superintendente_id,
                    usuario_id=uuid.uuid4(),
                )

    async def test_asignar_dos_veces_es_la_misma_intencion(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """Un doble clic en la pantalla no puede ser un 500."""
        async with sesion_con_rls(contexto_control) as sesion:
            repo = RepositorioAsignacionesSQL(sesion)
            await repo.asignar_residente(
                supervisor_id=escenario.supervisor_id,
                residente_id=escenario.residente_id,
            )
            await repo.asignar_residente(
                supervisor_id=escenario.supervisor_id,
                residente_id=escenario.residente_id,
            )
            await sesion.commit()
            assert len(await repo.residentes_de(escenario.supervisor_id)) == 1


class TestAislamiento:
    async def test_otra_organizacion_no_ve_el_organigrama(
        self, escenario: Escenario, contexto_ajeno: ContextoSesion
    ) -> None:
        async with sesion_con_rls(contexto_ajeno) as sesion:
            repo = RepositorioAsignacionesSQL(sesion)
            assert await repo.residentes_de(escenario.supervisor_id) == []
            assert await repo.obras_de(escenario.residente_id) == []
            assert (
                await repo.gente_de_superintendente(escenario.superintendente_id) == []
            )
