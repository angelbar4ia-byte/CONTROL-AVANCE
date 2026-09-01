"""Fixtures de integración: corren contra un Postgres real, no mockeado.

Spec §12.11 (Definition of Done: tests de dominio **e integración**).

Requieren dos variables de entorno; ninguna trae un default con
credenciales, ni siquiera de prueba —no se versionan secretos—:

  DATABASE_URL_ADMIN  conexión con privilegios de owner/superusuario, para
      armar y limpiar el escenario de cada prueba. Bypassa RLS a propósito:
      aquí se prepara el fixture, no se prueba el aislamiento —eso ya lo
      cubre `database/tests/test_rls.sql`.
  DATABASE_URL_TEST  conexión como el rol `obractrl_api`
      (`database/migrations/0014`), el mismo que usa el backend en
      producción. Los repos se ejercitan CONTRA este rol, no contra el
      admin: el punto es probar que funcionan bajo RLS, no solo que el SQL
      es sintácticamente válido.

Si faltan, toda la carpeta se salta con un motivo explícito, así
`pytest tests/domain` (sin BD) nunca se ve afectado y un CI sin Postgres
configurado no falla en falso.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.infrastructure.db.sesion import ContextoSesion

DATABASE_URL_ADMIN = os.environ.get("DATABASE_URL_ADMIN")
DATABASE_URL_TEST = os.environ.get("DATABASE_URL_TEST")

collect_ignore_glob: list[str] = []

if not (DATABASE_URL_ADMIN and DATABASE_URL_TEST):
    collect_ignore_glob = ["*"]


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if DATABASE_URL_ADMIN and DATABASE_URL_TEST:
        return
    saltar = pytest.mark.skip(
        reason=(
            "Requiere DATABASE_URL_ADMIN y DATABASE_URL_TEST apuntando a un "
            "Postgres con las migraciones de database/migrations/ aplicadas "
            "(ver backend/tests/integracion/conftest.py)."
        )
    )
    for item in items:
        if "integracion" in str(item.fspath):
            item.add_marker(saltar)


@pytest.fixture(autouse=True)
async def _apuntar_backend_a_bd_de_prueba() -> AsyncIterator[None]:
    """Redirige el engine global del backend a `DATABASE_URL_TEST`, uno
    nuevo por prueba.

    `infrastructure.db.sesion` cachea el engine/sessionmaker a nivel de
    módulo (detrás de `obtener_config()`, con `lru_cache`). Ese engine queda
    atado al *event loop* de asyncio en el que se crea, y con
    `asyncio_mode = "auto"` pytest-asyncio abre un loop nuevo por función de
    prueba — reutilizar el engine cacheado de una prueba anterior revienta
    con "attached to a different loop". Por eso este fixture resetea el
    caché **antes** de cada prueba (fuerza crear un engine fresco, en el
    loop actual) y lo cierra explícito **después**, para no dejar conexiones
    colgando de un loop que ya se cerró.
    """
    if not DATABASE_URL_TEST:
        yield
        return

    os.environ["DATABASE_URL"] = DATABASE_URL_TEST

    from obractrl.infrastructure.config import obtener_config
    from obractrl.infrastructure.db import sesion as sesion_mod

    obtener_config.cache_clear()
    sesion_mod._engine = None
    sesion_mod._sessionmaker = None

    yield

    if sesion_mod._engine is not None:
        await sesion_mod._engine.dispose()
    sesion_mod._engine = None
    sesion_mod._sessionmaker = None


@dataclass(frozen=True, slots=True)
class Escenario:
    """Datos mínimos de una obra con una actividad, listos para probar."""

    org_id: uuid.UUID
    residente_id: uuid.UUID
    supervisor_id: uuid.UUID
    control_id: uuid.UUID
    superintendente_id: uuid.UUID
    proyecto_id: uuid.UUID
    cluster_id: uuid.UUID
    prototipo_id: uuid.UUID
    obra_id: uuid.UUID
    actividad_id: uuid.UUID


@pytest.fixture
async def escenario() -> AsyncIterator[Escenario]:
    """Crea una org con proyecto/cluster/obra/actividad; la borra al terminar.

    Se arma con el rol admin (bypassa RLS a propósito: aquí no se prueba
    aislamiento, se prepara el fixture). Borrar la `organizacion` basta para
    limpiar todo: cada tabla tiene `org_id ... references organizacion(id)
    on delete cascade`.
    """
    engine = create_async_engine(DATABASE_URL_ADMIN)

    org = uuid.uuid4()
    residente = uuid.uuid4()
    supervisor = uuid.uuid4()
    control = uuid.uuid4()
    superintendente = uuid.uuid4()
    proyecto = uuid.uuid4()
    cluster = uuid.uuid4()
    prototipo = uuid.uuid4()
    obra = uuid.uuid4()
    actividad = uuid.uuid4()
    sufijo = org.hex[:8]

    async with engine.begin() as conn:
        await conn.execute(
            text("insert into organizacion (id, nombre, slug) values (:id, 'Test', :slug)"),
            {"id": str(org), "slug": f"test-{sufijo}"},
        )
        await conn.execute(
            text(
                "insert into usuario (id, org_id, nombre, email, rol) "
                "values (:id, :org, 'Residente Test', :email, 'residente')"
            ),
            {"id": str(residente), "org": str(org), "email": f"res-{sufijo}@test.mx"},
        )
        await conn.execute(
            text(
                "insert into usuario (id, org_id, nombre, email, rol) "
                "values (:id, :org, 'Supervisor Test', :email, 'supervisor')"
            ),
            {"id": str(supervisor), "org": str(org), "email": f"sup-{sufijo}@test.mx"},
        )
        await conn.execute(
            text(
                "insert into usuario (id, org_id, nombre, email, rol) "
                "values (:id, :org, 'Control Test', :email, 'control_obra')"
            ),
            {"id": str(control), "org": str(org), "email": f"ctrl-{sufijo}@test.mx"},
        )
        await conn.execute(
            text(
                "insert into usuario (id, org_id, nombre, email, rol) "
                "values (:id, :org, 'Super Intendente Test', :email, 'super_intendente')"
            ),
            {"id": str(superintendente), "org": str(org), "email": f"si-{sufijo}@test.mx"},
        )
        await conn.execute(
            text(
                "insert into proyecto (id, org_id, clave, nombre) "
                "values (:id, :org, 'PROY', 'Proyecto Test')"
            ),
            {"id": str(proyecto), "org": str(org)},
        )
        await conn.execute(
            text(
                "insert into cluster (id, org_id, proyecto_id, clave, nombre) "
                "values (:id, :org, :proyecto, 'CLU', 'Cluster Test')"
            ),
            {"id": str(cluster), "org": str(org), "proyecto": str(proyecto)},
        )
        await conn.execute(
            text(
                "insert into supervisor_cluster (org_id, supervisor_id, cluster_id) "
                "values (:org, :sup, :cluster)"
            ),
            {"org": str(org), "sup": str(supervisor), "cluster": str(cluster)},
        )
        await conn.execute(
            text(
                "insert into control_proyecto (org_id, usuario_id, proyecto_id) "
                "values (:org, :ctrl, :proyecto)"
            ),
            {"org": str(org), "ctrl": str(control), "proyecto": str(proyecto)},
        )
        await conn.execute(
            text(
                "insert into prototipo (id, org_id, proyecto_id, clave, nombre) "
                "values (:id, :org, :proyecto, 'CAS-1', 'Prototipo Test')"
            ),
            {"id": str(prototipo), "org": str(org), "proyecto": str(proyecto)},
        )
        await conn.execute(
            text(
                "insert into obra "
                "(id, org_id, cluster_id, prototipo_id, clave, residente_id) "
                "values (:id, :org, :cluster, :prototipo, 'OBRA 01', :res)"
            ),
            {
                "id": str(obra),
                "org": str(org),
                "cluster": str(cluster),
                "prototipo": str(prototipo),
                "res": str(residente),
            },
        )
        # La cadena de mando de la migración 0042: Super Intendente -> Supervisor
        # -> Residente -> Obra. Sin estas dos filas el supervisor y el super
        # intendente del escenario no verían NADA, porque desde la 0042 su
        # alcance sale de la gente que tienen asignada y no del cluster ni de la
        # organización. `residente_obra` no se siembra: lo llenó el trigger
        # `trg_obra_sincronizar_residente` al insertar la obra de arriba.
        await conn.execute(
            text(
                "insert into supervisor_residente (org_id, supervisor_id, residente_id) "
                "values (:org, :sup, :res)"
            ),
            {"org": str(org), "sup": str(supervisor), "res": str(residente)},
        )
        await conn.execute(
            text(
                "insert into superintendente_usuario "
                "(org_id, superintendente_id, usuario_id) "
                "values (:org, :si, :sup)"
            ),
            {"org": str(org), "si": str(superintendente), "sup": str(supervisor)},
        )
        await conn.execute(
            text(
                "insert into actividad (id, org_id, obra_id, cant_base, cant_programada) "
                "values (:id, :org, :obra, 100, 100)"
            ),
            {"id": str(actividad), "org": str(org), "obra": str(obra)},
        )

    yield Escenario(
        org_id=org,
        residente_id=residente,
        supervisor_id=supervisor,
        control_id=control,
        superintendente_id=superintendente,
        proyecto_id=proyecto,
        cluster_id=cluster,
        prototipo_id=prototipo,
        obra_id=obra,
        actividad_id=actividad,
    )

    async with engine.begin() as conn:
        await conn.execute(
            text("delete from organizacion where id = :id"), {"id": str(org)}
        )
    await engine.dispose()


@pytest.fixture
def contexto_residente(escenario: Escenario) -> ContextoSesion:
    return ContextoSesion(
        org_id=escenario.org_id, usuario_id=escenario.residente_id, rol="residente"
    )


@pytest.fixture
def contexto_supervisor(escenario: Escenario) -> ContextoSesion:
    return ContextoSesion(
        org_id=escenario.org_id, usuario_id=escenario.supervisor_id, rol="supervisor"
    )


@pytest.fixture
def contexto_control(escenario: Escenario) -> ContextoSesion:
    """Control de obra: desde la migración 0042 es el rol de arriba y ve toda
    la organización, y el único que da de alta obras (política `obra_insert`)."""
    return ContextoSesion(
        org_id=escenario.org_id, usuario_id=escenario.control_id, rol="control_obra"
    )


@pytest.fixture
def contexto_super_intendente(escenario: Escenario) -> ContextoSesion:
    """Super intendente con gente asignada.

    Desde la 0042 su alcance ya no es la organización sino su rama del
    organigrama, así que un SI sin `superintendente_usuario` no ve una sola
    obra. El escenario le cuelga el supervisor, que a su vez lleva al
    residente, que lleva la obra."""
    return ContextoSesion(
        org_id=escenario.org_id,
        usuario_id=escenario.superintendente_id,
        rol="super_intendente",
    )


@pytest.fixture
def contexto_ajeno() -> ContextoSesion:
    """Identidad de una organización distinta — para probar que RLS bloquea."""
    return ContextoSesion(
        org_id=uuid.uuid4(), usuario_id=uuid.uuid4(), rol="super_intendente"
    )
