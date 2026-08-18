"""Idempotencia contra Postgres real (§11.2, §12.3, §12.4).

`tests/api/test_idempotencia.py` fija la huella y las respuestas. Lo que solo
se puede probar con base es lo que justifica haber elegido una tabla en vez de
Redis:

**la clave y la mutación quedan en la misma transacción.** Si la mutación se
deshace, la clave se deshace con ella y el reintento vuelve a intentarlo; si se
confirma, la clave queda y el reintento se rechaza. Con un almacén aparte esas
dos cosas no pueden ser una sola.

Y el alcance: la clave la elige el cliente, así que dos usuarios de la misma
organización pueden escoger la misma sin saberlo (§12.4).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.api.idempotencia import (
    ClaveReusada,
    PeticionYaProcesada,
    _registrar,
)
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.api.test_idempotencia import _peticion
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario


async def _cuantas(escenario: Escenario, clave: str) -> int:
    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        total = (
            await conn.execute(
                text(
                    "select count(*) from idempotencia "
                    " where org_id = :org and clave = :clave"
                ),
                {"org": str(escenario.org_id), "clave": clave},
            )
        ).scalar_one()
    await admin.dispose()
    return int(total)


class TestAtomicidad:
    async def test_la_clave_queda_si_la_transaccion_se_confirma(
        self, escenario: Escenario, contexto_residente: ContextoSesion
    ) -> None:
        clave = f"clave-{uuid.uuid4().hex[:8]}"

        async with sesion_con_rls(contexto_residente) as sesion:
            await _registrar(sesion, clave=clave, request=_peticion())
            await sesion.commit()

        assert await _cuantas(escenario, clave) == 1

    async def test_la_clave_se_deshace_con_la_mutacion(
        self, escenario: Escenario, contexto_residente: ContextoSesion
    ) -> None:
        """El motivo de que sea una tabla y no Redis: si el cierre no se
        escribió, la clave tampoco puede quedar registrada — el cliente tiene
        que poder reintentar."""
        clave = f"clave-{uuid.uuid4().hex[:8]}"

        async with sesion_con_rls(contexto_residente) as sesion:
            await _registrar(sesion, clave=clave, request=_peticion())
            await sesion.rollback()

        assert await _cuantas(escenario, clave) == 0

    async def test_tras_el_rollback_el_reintento_vuelve_a_pasar(
        self, escenario: Escenario, contexto_residente: ContextoSesion
    ) -> None:
        """Corolario del anterior: una operación que falló no se queda
        bloqueada por su propia clave."""
        clave = f"clave-{uuid.uuid4().hex[:8]}"

        async with sesion_con_rls(contexto_residente) as sesion:
            await _registrar(sesion, clave=clave, request=_peticion())
            await sesion.rollback()

        async with sesion_con_rls(contexto_residente) as sesion:
            await _registrar(sesion, clave=clave, request=_peticion())
            await sesion.commit()

        assert await _cuantas(escenario, clave) == 1


class TestReintentos:
    async def test_la_misma_peticion_no_se_ejecuta_dos_veces(
        self, escenario: Escenario, contexto_residente: ContextoSesion
    ) -> None:
        clave = f"clave-{uuid.uuid4().hex[:8]}"

        async with sesion_con_rls(contexto_residente) as sesion:
            await _registrar(sesion, clave=clave, request=_peticion())
            await sesion.commit()

        with pytest.raises(PeticionYaProcesada):
            async with sesion_con_rls(contexto_residente) as sesion:
                await _registrar(sesion, clave=clave, request=_peticion())

    async def test_la_misma_clave_con_otro_cuerpo_es_un_error_del_cliente(
        self, escenario: Escenario, contexto_residente: ContextoSesion
    ) -> None:
        """No es un reintento: darle por hecha una operación distinta de la
        que pidió sería peor que rechazarla."""
        clave = f"clave-{uuid.uuid4().hex[:8]}"

        async with sesion_con_rls(contexto_residente) as sesion:
            await _registrar(
                sesion, clave=clave, request=_peticion(cuerpo=b'{"cantidad": 10}')
            )
            await sesion.commit()

        with pytest.raises(ClaveReusada):
            async with sesion_con_rls(contexto_residente) as sesion:
                await _registrar(
                    sesion,
                    clave=clave,
                    request=_peticion(cuerpo=b'{"cantidad": 999}'),
                )

    async def test_la_misma_clave_en_otra_ruta_tambien(
        self, escenario: Escenario, contexto_residente: ContextoSesion
    ) -> None:
        clave = f"clave-{uuid.uuid4().hex[:8]}"

        async with sesion_con_rls(contexto_residente) as sesion:
            await _registrar(
                sesion, clave=clave, request=_peticion(ruta="/api/v1/cierres/1/validar")
            )
            await sesion.commit()

        with pytest.raises(ClaveReusada):
            async with sesion_con_rls(contexto_residente) as sesion:
                await _registrar(
                    sesion,
                    clave=clave,
                    request=_peticion(ruta="/api/v1/cierres/2/validar"),
                )

    async def test_claves_distintas_no_se_estorban(
        self, escenario: Escenario, contexto_residente: ContextoSesion
    ) -> None:
        async with sesion_con_rls(contexto_residente) as sesion:
            await _registrar(sesion, clave="clave-a", request=_peticion())
            await _registrar(sesion, clave="clave-b", request=_peticion())
            await sesion.commit()

        assert await _cuantas(escenario, "clave-a") == 1
        assert await _cuantas(escenario, "clave-b") == 1


class TestAlcance:
    async def test_dos_usuarios_pueden_escoger_la_misma_clave(
        self,
        escenario: Escenario,
        contexto_residente: ContextoSesion,
        contexto_control: ContextoSesion,
    ) -> None:
        """La clave la elige el cliente: si el alcance fuera solo `org_id`, al
        segundo usuario se le rechazaría una operación legítima."""
        clave = "la-misma-clave"

        async with sesion_con_rls(contexto_residente) as sesion:
            await _registrar(sesion, clave=clave, request=_peticion())
            await sesion.commit()

        async with sesion_con_rls(contexto_control) as sesion:
            await _registrar(sesion, clave=clave, request=_peticion())
            await sesion.commit()

        assert await _cuantas(escenario, clave) == 2

    async def test_una_org_ajena_no_ve_las_claves(
        self,
        escenario: Escenario,
        contexto_residente: ContextoSesion,
        contexto_ajeno: ContextoSesion,
    ) -> None:
        """RLS: `idempotencia_scope` acota por org **y** por usuario (§12.4).
        Una clave ajena no sirve para nada y sí dejaría inferir qué hizo otro."""
        clave = f"clave-{uuid.uuid4().hex[:8]}"

        async with sesion_con_rls(contexto_residente) as sesion:
            await _registrar(sesion, clave=clave, request=_peticion())
            await sesion.commit()

        async with sesion_con_rls(contexto_ajeno) as sesion:
            filas = (
                await sesion.execute(text("select count(*) from idempotencia"))
            ).scalar_one()
        assert filas == 0
