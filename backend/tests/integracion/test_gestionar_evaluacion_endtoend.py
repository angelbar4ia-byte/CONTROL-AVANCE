"""Flujo de evaluación de punta a punta: casos de uso + repos + Postgres real.

Spec §11.3 workflow H · §6 · §12.11 (Definition of Done).

`tests/domain/test_evaluaciones.py` prueba las reglas puras; esto prueba que
los dos casos de uso —cableados igual que en `adapters/api/casos_uso.py`—
las aplican contra la base real: la evaluación queda escrita, el permiso por
nivel se respeta, y RLS filtra cada paso.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.repos.evaluaciones_sql import RepositorioEvaluacionesSQL
from obractrl.adapters.repos.obras_sql import RepositorioObrasSQL
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL
from obractrl.application.casos_uso.gestionar_evaluacion import (
    AgregarRespuestas,
    ComandoAgregarRespuestas,
    ComandoCrearEvaluacion,
    CrearEvaluacion,
    ErrorDeEvaluacion,
    EvaluacionNoEncontrada,
    RespuestaEntrada,
)
from obractrl.domain.shared.diccionario import NivelEvaluacion, Rol, SujetoEvaluacion
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario


@pytest.fixture
async def super_intendente_id(escenario: Escenario) -> uuid.UUID:
    """`Escenario` (conftest común) no trae Super intendente: se agrega aquí,
    solo para este módulo, igual que se arma el resto del escenario base."""
    engine = create_async_engine(DATABASE_URL_ADMIN)
    si_id = uuid.uuid4()
    sufijo = si_id.hex[:8]
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "insert into usuario (id, org_id, nombre, email, rol) "
                "values (:id, :org, 'SI Test', :email, 'super_intendente')"
            ),
            {"id": str(si_id), "org": str(escenario.org_id), "email": f"si-{sufijo}@test.mx"},
        )
    await engine.dispose()
    return si_id


@pytest.fixture
def contexto_super_intendente(
    escenario: Escenario, super_intendente_id: uuid.UUID
) -> ContextoSesion:
    return ContextoSesion(
        org_id=escenario.org_id, usuario_id=super_intendente_id, rol="super_intendente"
    )


@pytest.fixture
async def criterio_id(escenario: Escenario) -> uuid.UUID:
    engine = create_async_engine(DATABASE_URL_ADMIN)
    crit_id = uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "insert into criterio_evaluacion (id, org_id, aplica_a, clave, nombre, peso) "
                "values (:id, :org, 'residente', 'PUNTUALIDAD', 'Puntualidad', 1)"
            ),
            {"id": str(crit_id), "org": str(escenario.org_id)},
        )
    await engine.dispose()
    return crit_id


def _crear_evaluacion_caso_uso(sesion) -> CrearEvaluacion:
    return CrearEvaluacion(
        evaluaciones=RepositorioEvaluacionesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


async def test_residente_se_autoevalua(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        creada = await _crear_evaluacion_caso_uso(sesion).ejecutar(
            ComandoCrearEvaluacion(
                nivel=NivelEvaluacion.AUTO,
                evaluador_id=escenario.residente_id,
                rol=Rol.RESIDENTE,
                sujeto_tipo=SujetoEvaluacion.RESIDENTE,
                sujeto_id=escenario.residente_id,
                periodo="2026-07",
            )
        )
        await sesion.commit()

    assert creada.evaluacion.nivel is NivelEvaluacion.AUTO
    assert creada.evaluacion.sujeto_tipo is SujetoEvaluacion.RESIDENTE


async def test_residente_autoevalua_su_propia_obra(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        creada = await _crear_evaluacion_caso_uso(sesion).ejecutar(
            ComandoCrearEvaluacion(
                nivel=NivelEvaluacion.AUTO,
                evaluador_id=escenario.residente_id,
                rol=Rol.RESIDENTE,
                sujeto_tipo=SujetoEvaluacion.OBRA,
                sujeto_id=escenario.obra_id,
                periodo="2026-07",
            )
        )
        await sesion.commit()

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        fila = (
            await conn.execute(
                text("select sujeto_tipo, obra_id from evaluacion where id = :id"),
                {"id": str(creada.id)},
            )
        ).first()
    await admin.dispose()

    assert fila.sujeto_tipo == "obra"
    assert fila.obra_id == escenario.obra_id


async def test_residente_no_ve_una_obra_ajena_para_autoevaluar(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    """Otra obra en la misma org, con otro residente dueño.

    RLS ya la esconde de este residente (`app.obra_visible`, migración 0011:
    un residente solo ve su propia obra), así que el caso de uso da
    `EvaluacionNoEncontrada` —RLS hace indistinguible "no existe" de "no la
    puedes ver" a propósito (§12.4)— antes de que el dominio llegue a
    comparar `obra_residente_id`.
    """
    engine = create_async_engine(DATABASE_URL_ADMIN)
    otro_residente = uuid.uuid4()
    otra_obra = uuid.uuid4()
    sufijo = otro_residente.hex[:8]
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "insert into usuario (id, org_id, nombre, email, rol) "
                "values (:id, :org, 'Otro Residente', :email, 'residente')"
            ),
            {
                "id": str(otro_residente),
                "org": str(escenario.org_id),
                "email": f"otro-{sufijo}@test.mx",
            },
        )
        await conn.execute(
            text(
                "insert into obra "
                "(id, org_id, cluster_id, prototipo_id, clave, residente_id) "
                "values (:id, :org, :cluster, :prototipo, 'OBRA 02', :res)"
            ),
            {
                "id": str(otra_obra),
                "org": str(escenario.org_id),
                "cluster": str(escenario.cluster_id),
                "prototipo": str(escenario.prototipo_id),
                "res": str(otro_residente),
            },
        )
    await engine.dispose()

    async with sesion_con_rls(contexto_residente) as sesion:
        with pytest.raises(EvaluacionNoEncontrada):
            await _crear_evaluacion_caso_uso(sesion).ejecutar(
                ComandoCrearEvaluacion(
                    nivel=NivelEvaluacion.AUTO,
                    evaluador_id=escenario.residente_id,
                    rol=Rol.RESIDENTE,
                    sujeto_tipo=SujetoEvaluacion.OBRA,
                    sujeto_id=otra_obra,
                    periodo="2026-07",
                )
            )


async def test_control_de_obra_evalua_contratista(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    contratista_id = uuid.uuid4()
    async with sesion_con_rls(contexto_control) as sesion:
        creada = await _crear_evaluacion_caso_uso(sesion).ejecutar(
            ComandoCrearEvaluacion(
                nivel=NivelEvaluacion.CONTROL,
                evaluador_id=escenario.control_id,
                rol=Rol.CONTROL_OBRA,
                sujeto_tipo=SujetoEvaluacion.CONTRATISTA,
                sujeto_id=contratista_id,
                periodo="2026-07",
                obra_id=escenario.obra_id,
            )
        )
        await sesion.commit()

    assert creada.evaluacion.nivel is NivelEvaluacion.CONTROL
    assert creada.evaluacion.sujeto_tipo is SujetoEvaluacion.CONTRATISTA


async def test_residente_no_crea_nivel_control(
    escenario: Escenario, contexto_residente: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        with pytest.raises(ErrorDeEvaluacion, match="Solo Control de obra"):
            await _crear_evaluacion_caso_uso(sesion).ejecutar(
                ComandoCrearEvaluacion(
                    nivel=NivelEvaluacion.CONTROL,
                    evaluador_id=escenario.residente_id,
                    rol=Rol.RESIDENTE,
                    sujeto_tipo=SujetoEvaluacion.OBRA,
                    sujeto_id=escenario.obra_id,
                    periodo="2026-07",
                )
            )


async def test_super_intendente_consolida(
    escenario: Escenario,
    contexto_super_intendente: ContextoSesion,
    super_intendente_id: uuid.UUID,
) -> None:
    async with sesion_con_rls(contexto_super_intendente) as sesion:
        creada = await _crear_evaluacion_caso_uso(sesion).ejecutar(
            ComandoCrearEvaluacion(
                nivel=NivelEvaluacion.FINAL,
                evaluador_id=super_intendente_id,
                rol=Rol.SUPER_INTENDENTE,
                sujeto_tipo=SujetoEvaluacion.RESIDENTE,
                sujeto_id=escenario.residente_id,
                periodo="2026-07",
                obra_id=escenario.obra_id,
            )
        )
        await sesion.commit()

    assert creada.evaluacion.nivel is NivelEvaluacion.FINAL


async def test_control_no_consolida_nivel_final(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_control) as sesion:
        with pytest.raises(ErrorDeEvaluacion, match="Solo el Super intendente"):
            await _crear_evaluacion_caso_uso(sesion).ejecutar(
                ComandoCrearEvaluacion(
                    nivel=NivelEvaluacion.FINAL,
                    evaluador_id=escenario.control_id,
                    rol=Rol.CONTROL_OBRA,
                    sujeto_tipo=SujetoEvaluacion.RESIDENTE,
                    sujeto_id=escenario.residente_id,
                    periodo="2026-07",
                )
            )


async def test_agregar_respuestas_calcula_puntaje(
    escenario: Escenario, contexto_residente: ContextoSesion, criterio_id: uuid.UUID
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        creada = await _crear_evaluacion_caso_uso(sesion).ejecutar(
            ComandoCrearEvaluacion(
                nivel=NivelEvaluacion.AUTO,
                evaluador_id=escenario.residente_id,
                rol=Rol.RESIDENTE,
                sujeto_tipo=SujetoEvaluacion.RESIDENTE,
                sujeto_id=escenario.residente_id,
                periodo="2026-07",
            )
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_residente) as sesion:
        caso_uso = AgregarRespuestas(
            evaluaciones=RepositorioEvaluacionesSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        )
        evaluacion = await caso_uso.ejecutar(
            ComandoAgregarRespuestas(
                evaluacion_id=creada.id,
                usuario_id=escenario.residente_id,
                respuestas=[RespuestaEntrada(criterio_id=criterio_id, valor=Decimal("8"))],
            )
        )
        await sesion.commit()

    assert evaluacion.puntaje == Decimal("8")


async def test_solo_el_evaluador_agrega_respuestas(
    escenario: Escenario, contexto_residente: ContextoSesion, criterio_id: uuid.UUID
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        creada = await _crear_evaluacion_caso_uso(sesion).ejecutar(
            ComandoCrearEvaluacion(
                nivel=NivelEvaluacion.AUTO,
                evaluador_id=escenario.residente_id,
                rol=Rol.RESIDENTE,
                sujeto_tipo=SujetoEvaluacion.RESIDENTE,
                sujeto_id=escenario.residente_id,
                periodo="2026-07",
            )
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_residente) as sesion:
        caso_uso = AgregarRespuestas(
            evaluaciones=RepositorioEvaluacionesSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        )
        with pytest.raises(ErrorDeEvaluacion, match="Solo quien registró"):
            await caso_uso.ejecutar(
                ComandoAgregarRespuestas(
                    evaluacion_id=creada.id,
                    usuario_id=uuid.uuid4(),
                    respuestas=[RespuestaEntrada(criterio_id=criterio_id, valor=Decimal("8"))],
                )
            )


async def test_agregar_respuestas_a_evaluacion_inexistente(
    contexto_residente: ContextoSesion,
) -> None:
    async with sesion_con_rls(contexto_residente) as sesion:
        caso_uso = AgregarRespuestas(
            evaluaciones=RepositorioEvaluacionesSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        )
        with pytest.raises(EvaluacionNoEncontrada):
            await caso_uso.ejecutar(
                ComandoAgregarRespuestas(
                    evaluacion_id=uuid.uuid4(),
                    usuario_id=uuid.uuid4(),
                    respuestas=[
                        RespuestaEntrada(criterio_id=uuid.uuid4(), valor=Decimal("5"))
                    ],
                )
            )
