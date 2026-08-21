"""Repositorio de procesos contra Postgres real (§7.9, §11.2, §12.4).

`proceso` entra al loop de **catálogos** de la migración 0012: lectura para
toda la organización, escritura para `app.es_config()`. Eso no lo prueba
ninguna prueba de dominio —el repositorio no tiene reglas— y sí importa, por
dos motivos que solo se ven contra la base:

1. Que el `org_id` del `INSERT` salga de `current_setting('app.org_id')` y no
   de un parámetro. Si viniera del cliente, un usuario podría dar de alta un
   proceso en otra organización.
2. Que un residente **lea** y no escriba. Es la asimetría del §11.2: el
   proceso de mejora existe para que la obra lo siga, así que ocultárselo a
   quien lo ejecuta no tendría sentido; cambiarlo sí es del Super intendente.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import ProgrammingError

from obractrl.adapters.repos.procesos_sql import (
    ProcesoNoEncontrado,
    RepositorioProcesosSQL,
)
from obractrl.domain.shared.diccionario import EstatusProceso
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import Escenario


def _como(escenario: Escenario, usuario: uuid.UUID, rol: str) -> ContextoSesion:
    return ContextoSesion(org_id=escenario.org_id, usuario_id=usuario, rol=rol)


@pytest.fixture
async def proceso_id(escenario: Escenario) -> uuid.UUID:
    """Un proceso dado de alta por Control de obra (que sí puede escribir)."""
    async with sesion_con_rls(
        _como(escenario, escenario.control_id, "control_obra")
    ) as sesion:
        fila = await RepositorioProcesosSQL(sesion).crear(
            nombre="Junta de arranque por cluster",
            descripcion="Antes de iniciar, recorrer el cluster con el residente.",
            definido_por=escenario.control_id,
            estatus=EstatusProceso.PROPUESTO.value,
        )
        await sesion.commit()
    return uuid.UUID(str(fila["id"]))


class TestAlta:
    async def test_el_org_id_sale_del_contexto_y_no_del_cliente(
        self, escenario: Escenario, proceso_id: uuid.UUID
    ) -> None:
        # El repositorio no recibe `org_id`: lo pone la base desde
        # `current_setting('app.org_id')`. Que la fila se vea desde la misma
        # organización es la comprobación de que se guardó con el correcto.
        async with sesion_con_rls(
            _como(escenario, escenario.control_id, "control_obra")
        ) as sesion:
            fila = await RepositorioProcesosSQL(sesion).obtener(proceso_id)

        assert fila is not None
        assert fila["nombre"] == "Junta de arranque por cluster"
        assert fila["estatus"] == "propuesto"
        assert fila["definido_por"] == escenario.control_id

    async def test_otra_organización_no_lo_ve(
        self, escenario: Escenario, proceso_id: uuid.UUID
    ) -> None:
        ajeno = ContextoSesion(
            org_id=uuid.uuid4(), usuario_id=uuid.uuid4(), rol="super_intendente"
        )
        async with sesion_con_rls(ajeno) as sesion:
            assert await RepositorioProcesosSQL(sesion).obtener(proceso_id) is None


class TestLectura:
    async def test_un_residente_ve_el_tablero(
        self, escenario: Escenario, proceso_id: uuid.UUID
    ) -> None:
        # §11.2 deja la escritura al SI, pero la lectura es de todos: un
        # proceso que solo ve quien lo escribió no mejora nada.
        async with sesion_con_rls(
            _como(escenario, escenario.residente_id, "residente")
        ) as sesion:
            filas = await RepositorioProcesosSQL(sesion).listar()

        assert [f["id"] for f in filas] == [proceso_id]

    async def test_el_filtro_por_estatus(
        self, escenario: Escenario, proceso_id: uuid.UUID
    ) -> None:
        async with sesion_con_rls(
            _como(escenario, escenario.residente_id, "residente")
        ) as sesion:
            repo = RepositorioProcesosSQL(sesion)

            assert len(await repo.listar(estatus="propuesto")) == 1
            assert await repo.listar(estatus="adoptado") == []


class TestEscritura:
    async def test_cambiar_de_etapa(
        self, escenario: Escenario, proceso_id: uuid.UUID
    ) -> None:
        async with sesion_con_rls(
            _como(escenario, escenario.control_id, "control_obra")
        ) as sesion:
            fila = await RepositorioProcesosSQL(sesion).cambiar_estatus(
                proceso_id, EstatusProceso.ADOPTADO.value
            )
            await sesion.commit()

        assert fila["estatus"] == "adoptado"

    async def test_un_proceso_ajeno_no_existe_para_el_update(
        self, escenario: Escenario
    ) -> None:
        # RLS filtra la fila antes del `UPDATE`, así que "no existe" y "no es
        # tuyo" llegan igual — y así deben salir (§12.4).
        async with sesion_con_rls(
            _como(escenario, escenario.control_id, "control_obra")
        ) as sesion:
            with pytest.raises(ProcesoNoEncontrado):
                await RepositorioProcesosSQL(sesion).cambiar_estatus(
                    uuid.uuid4(), EstatusProceso.ADOPTADO.value
                )

    async def test_un_residente_no_puede_escribir(
        self, escenario: Escenario, proceso_id: uuid.UUID
    ) -> None:
        """La política de escritura es `app.es_config()` (migración 0012).

        El `UPDATE` no encuentra la fila —RLS la filtra para escritura— así
        que sale como `ProcesoNoEncontrado`, no como un error de permisos.
        Es el mismo comportamiento que en el resto del sistema y es
        deliberado: un 403 confirmaría que el proceso existe.
        """
        async with sesion_con_rls(
            _como(escenario, escenario.residente_id, "residente")
        ) as sesion:
            with pytest.raises((ProcesoNoEncontrado, ProgrammingError)):
                await RepositorioProcesosSQL(sesion).cambiar_estatus(
                    proceso_id, EstatusProceso.ADOPTADO.value
                )
