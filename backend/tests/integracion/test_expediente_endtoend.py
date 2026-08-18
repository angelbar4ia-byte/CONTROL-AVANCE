"""Expediente técnico de punta a punta: casos de uso + repos + Postgres real.

Spec §7.9 (`ExpedienteDoc`) · §11.2 ("**Expediente** — `GET/POST
/obras/{id}/expediente` — todos lectura / (C, SI) subida") · §12.4 (RLS) ·
§12.11 (Definition of Done).

`tests/domain/test_expediente.py` prueba las reglas puras y la aritmética del
agregado. Esto prueba lo que solo se ve contra la base:

- el documento queda escrito con su `org_id` tomado de `current_setting`,
- la política `expediente_doc_scope` acota lectura y escritura por obra,
- el filtro por `tipo` no revienta con `AmbiguousParameterError` cuando llega
  vacío (el mismo defecto que ya mordió en obras, clusters y prototipos),
- y sobre todo: `ArmarExpediente` reúne cuatro contextos —Expediente,
  Cierres, Estimación, Incidencias/Revisiones— **cada uno por su repositorio**
  (§11.1) y las sumas salen del dominio, no de un `join` que cruce sus tablas.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.api.casos_uso import (
    obtener_agregar_documento,
    obtener_armar_expediente,
    obtener_consultar_expediente,
)
from obractrl.application.casos_uso.gestionar_expediente import (
    ComandoAgregarDocumento,
    ErrorDeExpediente,
    ObraNoEncontrada,
)
from obractrl.domain.shared.diccionario import Rol, TipoExpedienteDoc
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario


async def _agregar(
    ctx: ContextoSesion,
    escenario: Escenario,
    *,
    usuario_id: uuid.UUID,
    rol: Rol = Rol.CONTROL_OBRA,
    tipo: TipoExpedienteDoc = TipoExpedienteDoc.CONTRATO,
    nombre: str = "Contrato firmado.pdf",
    url: str = "org/obra/expediente/contrato.pdf",
    obra_id: uuid.UUID | None = None,
) -> uuid.UUID:
    async with sesion_con_rls(ctx) as sesion:
        agregado = await obtener_agregar_documento(sesion).ejecutar(
            ComandoAgregarDocumento(
                obra_id=obra_id or escenario.obra_id,
                usuario_id=usuario_id,
                rol=rol,
                tipo=tipo,
                nombre=nombre,
                url=url,
            )
        )
        return agregado.id


class TestAgregarDocumento:
    async def test_escribe_el_documento_con_su_org_del_token(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """El `org_id` no lo manda el cliente: sale de
        `current_setting('app.org_id')` (§12.4)."""
        documento_id = await _agregar(
            contexto_control, escenario, usuario_id=escenario.control_id
        )

        admin = create_async_engine(DATABASE_URL_ADMIN)
        async with admin.connect() as conn:
            fila = (
                await conn.execute(
                    text(
                        "select org_id, obra_id, tipo, nombre, url, subido_por "
                        "from expediente_doc where id = :id"
                    ),
                    {"id": str(documento_id)},
                )
            ).first()
        await admin.dispose()

        assert fila is not None
        assert fila.org_id == escenario.org_id
        assert fila.obra_id == escenario.obra_id
        assert fila.tipo == "contrato"
        assert fila.nombre == "Contrato firmado.pdf"
        assert fila.subido_por == escenario.control_id

    async def test_guarda_la_clave_de_r2_y_no_una_url_firmada(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """§12.2: la firma caduca, la clave no. Lo que persiste es la clave."""
        clave = "org-1/obra-1/expediente/plano-A3.pdf"
        await _agregar(
            contexto_control, escenario, usuario_id=escenario.control_id, url=clave
        )

        async with sesion_con_rls(contexto_control) as sesion:
            filas = await obtener_consultar_expediente(sesion).listar(
                escenario.obra_id
            )
        assert filas[0]["url"] == clave

    async def test_un_residente_no_sube_documentos(
        self, escenario: Escenario, contexto_residente: ContextoSesion
    ) -> None:
        """§11.2 marca `(C, SI)` sobre la subida; el dominio la aplica aunque
        la guarda HTTP faltara."""
        with pytest.raises(ErrorDeExpediente, match="no puede"):
            await _agregar(
                contexto_residente,
                escenario,
                usuario_id=escenario.residente_id,
                rol=Rol.RESIDENTE,
            )

        admin = create_async_engine(DATABASE_URL_ADMIN)
        async with admin.connect() as conn:
            total = (
                await conn.execute(
                    text("select count(*) from expediente_doc where obra_id = :obra"),
                    {"obra": str(escenario.obra_id)},
                )
            ).scalar_one()
        await admin.dispose()
        assert total == 0


class TestListar:
    async def test_filtra_por_tipo_y_sin_filtro_no_revienta(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """El cast del lado `is null` es lo que evita el
        `AmbiguousParameterError` de asyncpg."""
        contrato = await _agregar(
            contexto_control, escenario, usuario_id=escenario.control_id
        )
        plano = await _agregar(
            contexto_control,
            escenario,
            usuario_id=escenario.control_id,
            tipo=TipoExpedienteDoc.PLANO,
            nombre="Planta baja.pdf",
            url="org/obra/expediente/planta.pdf",
        )

        async with sesion_con_rls(contexto_control) as sesion:
            caso_uso = obtener_consultar_expediente(sesion)
            todos = await caso_uso.listar(escenario.obra_id)
            solo_planos = await caso_uso.listar(
                escenario.obra_id, tipo=TipoExpedienteDoc.PLANO
            )
            de_otra_obra = await caso_uso.listar(uuid.uuid4())

        assert {fila["id"] for fila in todos} == {contrato, plano}
        assert [fila["id"] for fila in solo_planos] == [plano]
        assert de_otra_obra == []

    async def test_la_lectura_es_de_todos_los_roles(
        self,
        escenario: Escenario,
        contexto_control: ContextoSesion,
        contexto_residente: ContextoSesion,
    ) -> None:
        """§11.2: "todos lectura". El Residente no sube, pero sí consulta."""
        documento_id = await _agregar(
            contexto_control, escenario, usuario_id=escenario.control_id
        )

        async with sesion_con_rls(contexto_residente) as sesion:
            filas = await obtener_consultar_expediente(sesion).listar(
                escenario.obra_id
            )
        assert [fila["id"] for fila in filas] == [documento_id]

    async def test_una_org_ajena_no_ve_el_expediente(
        self,
        escenario: Escenario,
        contexto_control: ContextoSesion,
        contexto_ajeno: ContextoSesion,
    ) -> None:
        """RLS: `expediente_doc_scope` acota por `obra_visible` (§12.4)."""
        await _agregar(contexto_control, escenario, usuario_id=escenario.control_id)

        async with sesion_con_rls(contexto_ajeno) as sesion:
            filas = await obtener_consultar_expediente(sesion).listar(
                escenario.obra_id
            )
        assert filas == []


class TestArmarExpediente:
    async def test_reune_documentos_cierres_estimaciones_y_evidencias(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """La vista agregada del §11.2, cada parte por su puerto (§11.1)."""
        await _agregar(contexto_control, escenario, usuario_id=escenario.control_id)
        await _sembrar_acervo(escenario)

        async with sesion_con_rls(contexto_control) as sesion:
            expediente = await obtener_armar_expediente(sesion).ejecutar(
                escenario.obra_id
            )

        assert expediente.obra_clave == "OBRA 01"
        assert len(expediente.documentos) == 1
        assert len(expediente.cierres) == 2
        assert len(expediente.estimaciones) == 2
        # Dos fotos de la revisión + una evidencia de la incidencia + un
        # adjunto del cierre validado (§7.8).
        assert expediente.n_evidencias == 4

    async def test_solo_suma_lo_validado(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """§11.3 C.3 y E.4: un cierre `solicitada` o una estimación `borrador`
        todavía pueden cambiar, y el expediente sostiene el cierre de obra."""
        await _sembrar_acervo(escenario)

        async with sesion_con_rls(contexto_control) as sesion:
            expediente = await obtener_armar_expediente(sesion).ejecutar(
                escenario.obra_id
            )

        assert str(expediente.monto_cerrado.monto) == "1000.00"
        assert str(expediente.monto_estimado.monto) == "900.00"

    async def test_una_obra_fuera_del_alcance_es_404_y_no_un_expediente_vacio(
        self, escenario: Escenario, contexto_ajeno: ContextoSesion
    ) -> None:
        """RLS hace indistinguible "no existe" de "no la puedes ver" (§12.4):
        devolver un expediente vacío filtraría que la obra existe."""
        with pytest.raises(ObraNoEncontrada):
            async with sesion_con_rls(contexto_ajeno) as sesion:
                await obtener_armar_expediente(sesion).ejecutar(escenario.obra_id)

    async def test_una_obra_sin_acervo_da_un_expediente_vacio_no_un_error(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        async with sesion_con_rls(contexto_control) as sesion:
            expediente = await obtener_armar_expediente(sesion).ejecutar(
                escenario.obra_id
            )

        assert expediente.documentos == ()
        assert expediente.monto_cerrado.es_cero
        assert expediente.n_evidencias == 0


async def _sembrar_acervo(escenario: Escenario) -> None:
    """Cierres, estimaciones, una revisión y una incidencia de la obra.

    Se siembra con el rol admin —igual que el `escenario`— porque el punto de
    estas pruebas es el **agregado**, no cómo se creó cada pieza: eso ya lo
    cubren `test_gestionar_cierre_endtoend.py`, `test_estimaciones_repo.py`,
    `test_revisiones_endtoend.py` y `test_gestionar_incidencia_endtoend.py`.
    """
    engine = create_async_engine(DATABASE_URL_ADMIN)
    org = str(escenario.org_id)
    obra = str(escenario.obra_id)

    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                -- `ck_cierre_validada` exige autorizada_por y validada_por
                -- para el estatus `validada` (§11.3 C): el escenario los
                -- ocupa con el supervisor y el control de obra.
                insert into solicitud_cierre
                    (org_id, actividad_id, solicitada_por, autorizada_por,
                     validada_por, cantidad, monto, adjuntos, estatus,
                     fecha_autoriza, fecha_valida)
                values
                    (:org, :act, :res, :sup, :ctrl, 10, 1000.00,
                     '["org/obra/cierre-1.jpg"]'::jsonb, 'validada',
                     now(), now()),
                    (:org, :act, :res, null, null, 5, 500.00,
                     '[]'::jsonb, 'solicitada', null, null)
                """
            ),
            {
                "org": org,
                "act": str(escenario.actividad_id),
                "res": str(escenario.residente_id),
                "sup": str(escenario.supervisor_id),
                "ctrl": str(escenario.control_id),
            },
        )
        await conn.execute(
            text(
                """
                insert into estimacion
                    (org_id, obra_id, folio, semana, anio, modo, estatus,
                     monto_total, creada_por)
                values
                    (:org, :obra, 'EST-2026-33-001', 33, 2026, 'destajo',
                     'validada', 900.00, :res),
                    (:org, :obra, null, 34, 2026, 'destajo',
                     'borrador', 400.00, :res)
                """
            ),
            {"org": org, "obra": obra, "res": str(escenario.residente_id)},
        )
        await conn.execute(
            text(
                """
                insert into revision_fisica
                    (org_id, obra_id, usuario_id, fecha, fotos, calidad)
                values
                    (:org, :obra, :ctrl, :fecha,
                     '["org/obra/rev-a.jpg", "org/obra/rev-b.jpg"]'::jsonb, 4)
                """
            ),
            {
                "org": org,
                "obra": obra,
                "ctrl": str(escenario.control_id),
                "fecha": date(2026, 8, 17),
            },
        )
        await conn.execute(
            text(
                """
                insert into incidencia
                    (org_id, obra_id, tipo, titulo, descripcion, creada_por,
                     evidencias)
                values
                    (:org, :obra, 'error_ejecucion', 'Rebaba en muro norte',
                     'Acabado fuera de tolerancia', :ctrl,
                     '["org/obra/inc-1.jpg"]'::jsonb)
                """
            ),
            {"org": org, "obra": obra, "ctrl": str(escenario.control_id)},
        )

    await engine.dispose()
