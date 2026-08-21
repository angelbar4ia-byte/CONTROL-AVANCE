"""Programación de punta a punta: casos de uso + repos + Postgres real.

Spec §11.2 ("Programación · CPM") · §7.5 · §6 · §11.3 C.4 · §12.11.

`tests/domain/test_programacion.py` prueba las reglas puras; esto prueba que
los casos de uso —cableados como en `adapters/api/casos_uso.py`— las aplican
contra la base: la instanciación traduce las dependencias del programa base a
ids de actividad y las escribe, el CPM queda persistido en `es_critica` /
`holgura` / `desfase`, recalcular es idempotente, un ciclo aborta sin escribir
nada, y validar un cierre dispara `ActividadCerrada` → recálculo (§11.3 C.4).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from obractrl.adapters.api.casos_uso import (
    obtener_abrir_incidencia,
    obtener_cerrar_incidencia,
    obtener_validar_cierre,
)
from obractrl.adapters.repos.actividades_sql import RepositorioActividadesSQL
from obractrl.adapters.repos.cierres_sql import RepositorioCierresSQL
from obractrl.adapters.repos.incidencias_sql import RepositorioIncidenciasSQL
from obractrl.adapters.repos.obras_sql import RepositorioObrasSQL
from obractrl.adapters.repos.programas_sql import RepositorioProgramasSQL
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL
from obractrl.application.casos_uso.gestionar_cierre import (
    AutorizarCierre,
    ComandoAutorizarCierre,
    ComandoSolicitarCierre,
    ComandoValidarCierre,
    SolicitarCierre,
)
from obractrl.application.casos_uso.gestionar_incidencia import (
    ComandoAbrirIncidencia,
    ComandoCerrarIncidencia,
    ComandoProgramarIncidencia,
    ComandoRegistrarEventoIncidencia,
    ProgramarIncidencia,
    RegistrarEventoIncidencia,
)
from obractrl.application.casos_uso.gestionar_programacion import (
    ActividadNoProgramable,
    ComandoEditarProgramacion,
    ComandoInstanciarPrograma,
    ComandoRecalcularRutaCritica,
    ConsultarRutaCritica,
    EditarProgramacionActividad,
    ErrorDeProgramacion,
    InstanciarProgramaObra,
    RecalcularRutaCritica,
)
from obractrl.domain.programacion.cpm import CicloEnGrafoError, Dependencia
from obractrl.domain.shared.diccionario import (
    EstatusIncidencia,
    ImpactoIncidencia,
    Rol,
    TipoIncidencia,
)
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario

ARRANQUE = date(2026, 3, 2)  # lunes
CORTE = date(2026, 3, 2)


@dataclass(frozen=True, slots=True)
class Cronograma:
    """Tres nodos del prototipo y sus tres actividades, como las deja el
    workflow A: con `prototipo_nodo_id` y las dependencias todavía en el
    lenguaje del prototipo (§11.3 A.2)."""

    nodo_a: uuid.UUID
    nodo_b: uuid.UUID
    nodo_c: uuid.UUID
    act_a: uuid.UUID
    act_b: uuid.UUID
    act_c: uuid.UUID


async def _armar_cronograma(escenario: Escenario) -> Cronograma:
    """Prototipo con tres nodos + obra con tres actividades sin programar."""
    nodos = [uuid.uuid4() for _ in range(3)]
    actividades = [uuid.uuid4() for _ in range(3)]

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        await conn.execute(
            text("update obra set fecha_inicio = :inicio where id = :id"),
            {"inicio": ARRANQUE, "id": str(escenario.obra_id)},
        )
        for nodo, nombre in zip(nodos, ("Cimentación", "Estructura", "Acabados"), strict=True):
            await conn.execute(
                text(
                    "insert into prototipo_nodo "
                    "(id, org_id, prototipo_id, tipo, nombre) "
                    "values (:id, :org, :proto, 'etapa', :nombre)"
                ),
                {
                    "id": str(nodo),
                    "org": str(escenario.org_id),
                    "proto": str(escenario.prototipo_id),
                    "nombre": nombre,
                },
            )
        for orden, (act, nodo) in enumerate(zip(actividades, nodos, strict=True)):
            await conn.execute(
                text(
                    """
                    insert into actividad
                        (id, org_id, obra_id, prototipo_nodo_id, descripcion,
                         cant_base, cant_programada, created_at)
                    values
                        (:id, :org, :obra, :nodo, :descripcion, 100, 100,
                         now() + make_interval(secs => :orden))
                    """
                ),
                {
                    "id": str(act),
                    "org": str(escenario.org_id),
                    "obra": str(escenario.obra_id),
                    "nodo": str(nodo),
                    "descripcion": f"Actividad {orden}",
                    "orden": orden,
                },
            )
    await admin.dispose()

    return Cronograma(
        nodo_a=nodos[0],
        nodo_b=nodos[1],
        nodo_c=nodos[2],
        act_a=actividades[0],
        act_b=actividades[1],
        act_c=actividades[2],
    )


async def _plantilla(
    escenario: Escenario, ctx: ContextoSesion, cronograma: Cronograma
) -> None:
    """A(5) -> B(6); C(2) también cuelga de A. La rama C queda holgada."""
    async with sesion_con_rls(ctx) as sesion:
        repo = RepositorioProgramasSQL(sesion)
        base_id = await repo.crear_base({"prototipo_id": escenario.prototipo_id})
        await repo.agregar_items_base(
            base_id,
            [
                {
                    "prototipo_nodo_id": cronograma.nodo_a,
                    "duracion_dias": Decimal("5"),
                    "orden": 0,
                },
                {
                    "prototipo_nodo_id": cronograma.nodo_b,
                    "duracion_dias": Decimal("6"),
                    "dependencias": [
                        {"ref": str(cronograma.nodo_a), "tipo": "FS", "lag_dias": 0}
                    ],
                    "orden": 1,
                },
                {
                    "prototipo_nodo_id": cronograma.nodo_c,
                    "duracion_dias": Decimal("2"),
                    "dependencias": [
                        {"ref": str(cronograma.nodo_a), "tipo": "FS", "lag_dias": 0}
                    ],
                    "orden": 2,
                },
            ],
        )
        await sesion.commit()


def _instanciar(sesion: AsyncSession) -> InstanciarProgramaObra:
    return InstanciarProgramaObra(
        actividades=RepositorioActividadesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        programas=RepositorioProgramasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def _recalcular(sesion: AsyncSession) -> RecalcularRutaCritica:
    return RecalcularRutaCritica(
        actividades=RepositorioActividadesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        programas=RepositorioProgramasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


async def _leer_actividades(ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        filas = (
            await conn.execute(
                text(
                    """
                    select id, duracion_dias, dependencias, es_critica, holgura,
                           desfase, programa_obra_id, bloqueada
                    from actividad
                    where id = any(cast(:ids as uuid[]))
                    """
                ),
                {"ids": [str(i) for i in ids]},
            )
        ).mappings().all()
    await admin.dispose()
    return {fila["id"]: dict(fila) for fila in filas}


async def test_instanciar_traduce_dependencias_y_persiste_el_cpm(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    cronograma = await _armar_cronograma(escenario)
    await _plantilla(escenario, contexto_control, cronograma)

    async with sesion_con_rls(contexto_control) as sesion:
        resultado = await _instanciar(sesion).ejecutar(
            ComandoInstanciarPrograma(obra_id=escenario.obra_id, fecha_corte=CORTE)
        )

    assert resultado.version == 1
    # La actividad original del fixture no tiene nodo ni plantilla: conserva
    # lo suyo y se reporta como hueco (§7.5).
    assert resultado.n_actividades == 4
    assert str(escenario.actividad_id) in resultado.sin_item
    assert resultado.refs_no_resueltas == ()

    filas = await _leer_actividades(
        [cronograma.act_a, cronograma.act_b, cronograma.act_c]
    )

    # Lo que el workflow A dejó pendiente: los `ref` ya son ids de actividad.
    assert filas[cronograma.act_b]["dependencias"] == [
        {"ref": str(cronograma.act_a), "tipo": "FS", "lag_dias": 0}
    ]
    assert filas[cronograma.act_a]["duracion_dias"] == Decimal("5.00")
    assert filas[cronograma.act_b]["duracion_dias"] == Decimal("6.00")

    # Ruta crítica: A -> B (11 días) gana sobre A -> C (7).
    assert filas[cronograma.act_a]["es_critica"] is True
    assert filas[cronograma.act_b]["es_critica"] is True
    assert filas[cronograma.act_c]["es_critica"] is False
    assert filas[cronograma.act_c]["holgura"] == Decimal("4.00")

    # Cada actividad queda atada a la versión de cronograma que la programó.
    assert filas[cronograma.act_a]["programa_obra_id"] == resultado.programa_obra_id

    fin = {a.actividad_id: a.fin_temprano for a in resultado.ruta.actividades}
    assert fin[cronograma.act_a] == date(2026, 3, 7)
    assert fin[cronograma.act_b] == date(2026, 3, 13)


async def test_recalcular_es_idempotente(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """§6: el recálculo programado y el on-demand se pisan sin conflicto."""
    cronograma = await _armar_cronograma(escenario)
    await _plantilla(escenario, contexto_control, cronograma)

    async with sesion_con_rls(contexto_control) as sesion:
        await _instanciar(sesion).ejecutar(
            ComandoInstanciarPrograma(obra_id=escenario.obra_id, fecha_corte=CORTE)
        )

    ids = [cronograma.act_a, cronograma.act_b, cronograma.act_c]

    async with sesion_con_rls(contexto_control) as sesion:
        primera = await _recalcular(sesion).ejecutar(
            ComandoRecalcularRutaCritica(obra_id=escenario.obra_id, fecha_corte=CORTE)
        )
    tras_una = await _leer_actividades(ids)

    async with sesion_con_rls(contexto_control) as sesion:
        segunda = await _recalcular(sesion).ejecutar(
            ComandoRecalcularRutaCritica(obra_id=escenario.obra_id, fecha_corte=CORTE)
        )
    tras_dos = await _leer_actividades(ids)

    comparable = {
        act: (fila["es_critica"], fila["holgura"], fila["desfase"])
        for act, fila in tras_una.items()
    }
    assert comparable == {
        act: (fila["es_critica"], fila["holgura"], fila["desfase"])
        for act, fila in tras_dos.items()
    }
    assert primera.fin_programado == segunda.fin_programado
    assert [a.holgura for a in primera.actividades] == [
        a.holgura for a in segunda.actividades
    ]

    # Recalcular no versiona el cronograma: eso solo lo hace instanciar (§7.5).
    async with sesion_con_rls(contexto_control) as sesion:
        historial = await RepositorioProgramasSQL(sesion).listar_programas(
            escenario.obra_id
        )
    assert [fila["version"] for fila in historial] == [1]


async def test_un_ciclo_en_la_plantilla_aborta_sin_escribir(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    cronograma = await _armar_cronograma(escenario)

    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioProgramasSQL(sesion)
        base_id = await repo.crear_base({"prototipo_id": escenario.prototipo_id})
        await repo.agregar_items_base(
            base_id,
            [
                {
                    "prototipo_nodo_id": cronograma.nodo_a,
                    "duracion_dias": Decimal("3"),
                    "dependencias": [
                        {"ref": str(cronograma.nodo_b), "tipo": "FS", "lag_dias": 0}
                    ],
                    "orden": 0,
                },
                {
                    "prototipo_nodo_id": cronograma.nodo_b,
                    "duracion_dias": Decimal("3"),
                    "dependencias": [
                        {"ref": str(cronograma.nodo_a), "tipo": "FS", "lag_dias": 0}
                    ],
                    "orden": 1,
                },
            ],
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        with pytest.raises(CicloEnGrafoError) as exc:
            await _instanciar(sesion).ejecutar(
                ComandoInstanciarPrograma(obra_id=escenario.obra_id, fecha_corte=CORTE)
            )

    assert {str(cronograma.act_a), str(cronograma.act_b)} <= set(
        exc.value.involucradas
    )

    # Nada se escribió: ni el cronograma, ni una versión de ProgramaObra.
    filas = await _leer_actividades([cronograma.act_a, cronograma.act_b])
    assert filas[cronograma.act_a]["dependencias"] == []
    assert filas[cronograma.act_a]["duracion_dias"] == Decimal("1.00")

    async with sesion_con_rls(contexto_control) as sesion:
        assert (
            await RepositorioProgramasSQL(sesion).programa_vigente(escenario.obra_id)
            is None
        )


async def test_obra_sin_programa_base_no_se_instancia(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    await _armar_cronograma(escenario)

    async with sesion_con_rls(contexto_control) as sesion:
        with pytest.raises(ErrorDeProgramacion, match="programa base vigente"):
            await _instanciar(sesion).ejecutar(
                ComandoInstanciarPrograma(obra_id=escenario.obra_id)
            )


async def test_patch_programacion_ajusta_y_recalcula(
    escenario: Escenario, contexto_control: ContextoSesion,
    contexto_supervisor: ContextoSesion,
) -> None:
    cronograma = await _armar_cronograma(escenario)
    await _plantilla(escenario, contexto_control, cronograma)

    async with sesion_con_rls(contexto_control) as sesion:
        await _instanciar(sesion).ejecutar(
            ComandoInstanciarPrograma(obra_id=escenario.obra_id, fecha_corte=CORTE)
        )

    # El Supervisor alarga la rama holgada hasta pasar a la crítica (§11.2).
    async with sesion_con_rls(contexto_supervisor) as sesion:
        actualizada = await EditarProgramacionActividad(
            actividades=RepositorioActividadesSQL(sesion),
            obras=RepositorioObrasSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
        ).ejecutar(
            ComandoEditarProgramacion(
                actividad_id=cronograma.act_c, duracion_dias=Decimal("9")
            )
        )

    assert actualizada.duracion_dias == Decimal("9.00")
    assert actualizada.es_critica is True

    filas = await _leer_actividades([cronograma.act_b, cronograma.act_c])
    assert filas[cronograma.act_c]["duracion_dias"] == Decimal("9.00")
    assert filas[cronograma.act_c]["es_critica"] is True
    # Cambiar una duración mueve la holgura de las demás: B ahora sobra 3 días.
    assert filas[cronograma.act_b]["es_critica"] is False
    assert filas[cronograma.act_b]["holgura"] == Decimal("3.00")


async def test_patch_con_dependencia_ciclica_no_escribe(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    cronograma = await _armar_cronograma(escenario)
    await _plantilla(escenario, contexto_control, cronograma)

    async with sesion_con_rls(contexto_control) as sesion:
        await _instanciar(sesion).ejecutar(
            ComandoInstanciarPrograma(obra_id=escenario.obra_id, fecha_corte=CORTE)
        )

    async with sesion_con_rls(contexto_control) as sesion:
        with pytest.raises(CicloEnGrafoError):
            await EditarProgramacionActividad(
                actividades=RepositorioActividadesSQL(sesion),
                obras=RepositorioObrasSQL(sesion),
                uow=UnidadDeTrabajoSQL(sesion),
            ).ejecutar(
                ComandoEditarProgramacion(
                    actividad_id=cronograma.act_a,
                    dependencias=(Dependencia(str(cronograma.act_b)),),
                )
            )

    filas = await _leer_actividades([cronograma.act_a])
    assert filas[cronograma.act_a]["dependencias"] == []


async def test_patch_de_actividad_fuera_de_alcance_da_no_encontrada(
    contexto_ajeno: ContextoSesion,
) -> None:
    async with sesion_con_rls(contexto_ajeno) as sesion:
        with pytest.raises(ActividadNoProgramable):
            await EditarProgramacionActividad(
                actividades=RepositorioActividadesSQL(sesion),
                obras=RepositorioObrasSQL(sesion),
                uow=UnidadDeTrabajoSQL(sesion),
            ).ejecutar(
                ComandoEditarProgramacion(
                    actividad_id=uuid.uuid4(), duracion_dias=Decimal("3")
                )
            )


async def test_consultar_ruta_critica_no_escribe(
    escenario: Escenario,
    contexto_control: ContextoSesion,
    contexto_residente: ContextoSesion,
) -> None:
    """`GET` calcula sin persistir; el Residente ve la de su obra (§11.2, §4)."""
    cronograma = await _armar_cronograma(escenario)
    await _plantilla(escenario, contexto_control, cronograma)

    async with sesion_con_rls(contexto_residente) as sesion:
        ruta = await ConsultarRutaCritica(
            actividades=RepositorioActividadesSQL(sesion),
            obras=RepositorioObrasSQL(sesion),
            programas=RepositorioProgramasSQL(sesion),
        ).ejecutar(escenario.obra_id, fecha_corte=CORTE)

    assert ruta.fecha_inicio == ARRANQUE
    assert len(ruta.actividades) == 4

    # Sin instanciar, cada actividad dura el día por defecto y nada quedó
    # escrito: `es_critica` sigue en su valor inicial.
    filas = await _leer_actividades([cronograma.act_a])
    assert filas[cronograma.act_a]["es_critica"] is False
    assert filas[cronograma.act_a]["holgura"] is None


async def test_validar_cierre_recalcula_la_ruta(
    escenario: Escenario,
    contexto_control: ContextoSesion,
    contexto_residente: ContextoSesion,
    contexto_supervisor: ContextoSesion,
) -> None:
    """§11.3 C.4: el evento `ActividadCerrada` dispara el recálculo de CPM.

    Se usa el ensamblado real de `adapters/api/casos_uso.obtener_validar_cierre`
    —bus incluido— para probar el cableado, no una imitación.
    """
    cronograma = await _armar_cronograma(escenario)
    await _plantilla(escenario, contexto_control, cronograma)

    # Cronograma escrito pero CPM sin calcular: se borra a mano lo que
    # instanciar dejó, para que el único recálculo posible sea el del evento.
    async with sesion_con_rls(contexto_control) as sesion:
        await _instanciar(sesion).ejecutar(
            ComandoInstanciarPrograma(obra_id=escenario.obra_id, fecha_corte=CORTE)
        )

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "update actividad set es_critica = false, holgura = null, "
                "desfase = null where obra_id = :obra"
            ),
            {"obra": str(escenario.obra_id)},
        )
    await admin.dispose()

    async with sesion_con_rls(contexto_residente) as sesion:
        creada = await SolicitarCierre(
            actividades=RepositorioActividadesSQL(sesion),
            cierres=RepositorioCierresSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
        ).ejecutar(
            ComandoSolicitarCierre(
                actividad_id=cronograma.act_a,
                residente_id=escenario.residente_id,
                rol=Rol.RESIDENTE,
                cantidad=Decimal("10"),
                checklist=[{"item": "Nivelación", "ok": True}],
                adjuntos=["r2://evidencias/foto-1.jpg"],
            )
        )

    async with sesion_con_rls(contexto_supervisor) as sesion:
        await AutorizarCierre(
            cierres=RepositorioCierresSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        ).ejecutar(
            ComandoAutorizarCierre(
                cierre_id=creada.id,
                usuario_id=escenario.supervisor_id,
                rol=Rol.SUPERVISOR,
            )
        )

    async with sesion_con_rls(contexto_control) as sesion:
        # El mismo contexto que abrió la sesión: desde la Fase 16 el bus
        # también anuncia el hecho en vivo (§11.2) y el canal reparte por
        # organización, que es lo único que el `ctx` aporta aquí.
        await obtener_validar_cierre(sesion, contexto_control).ejecutar(
            ComandoValidarCierre(
                cierre_id=creada.id,
                usuario_id=escenario.control_id,
                rol=Rol.CONTROL_OBRA,
                comentario="Ok",
            )
        )

    filas = await _leer_actividades(
        [cronograma.act_a, cronograma.act_b, cronograma.act_c]
    )
    assert filas[cronograma.act_a]["es_critica"] is True
    assert filas[cronograma.act_b]["es_critica"] is True
    assert filas[cronograma.act_c]["holgura"] == Decimal("4.00")


async def _llevar_a_cierre_solicitado(
    ctx: ContextoSesion, incidencia_id: uuid.UUID, escenario: Escenario
) -> None:
    """Recorre F.2-F.3 (programar → atender → solicitar cierre) para dejar la
    incidencia lista de cerrar. Es camino ya cubierto por
    `test_gestionar_incidencia_endtoend.py`; aquí solo es preámbulo."""
    async with sesion_con_rls(ctx) as sesion:
        await ProgramarIncidencia(
            incidencias=RepositorioIncidenciasSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
        ).ejecutar(
            ComandoProgramarIncidencia(
                incidencia_id=incidencia_id,
                usuario_id=escenario.supervisor_id,
                rol=Rol.SUPERVISOR,
                asignada_a=escenario.supervisor_id,
            )
        )
        for accion, estatus in (
            ("atender", EstatusIncidencia.EN_ATENCION),
            ("solicitar_cierre", EstatusIncidencia.CIERRE_SOLICITADO),
        ):
            await RegistrarEventoIncidencia(
                incidencias=RepositorioIncidenciasSQL(sesion),
                uow=UnidadDeTrabajoSQL(sesion),
            ).ejecutar(
                ComandoRegistrarEventoIncidencia(
                    incidencia_id=incidencia_id,
                    usuario_id=escenario.supervisor_id,
                    accion=accion,
                    estatus_nuevo=estatus,
                )
            )


async def _borrar_cpm(obra_id: uuid.UUID) -> None:
    """Deja el cronograma escrito pero el CPM sin calcular, para que el único
    recálculo posible sea el que dispare el evento."""
    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "update actividad set es_critica = false, holgura = null, "
                "desfase = null where obra_id = :obra"
            ),
            {"obra": str(obra_id)},
        )
    await admin.dispose()


async def test_incidencia_que_detiene_bloquea_y_recalcula_la_ruta(
    escenario: Escenario,
    contexto_control: ContextoSesion,
    contexto_residente: ContextoSesion,
    contexto_supervisor: ContextoSesion,
) -> None:
    """§11.3 F.5: `impacto=detiene` → bloquea actividades **y** recalcula CPM.

    Igual que `test_validar_cierre_recalcula_la_ruta`, se usa el ensamblado
    real de `adapters/api/casos_uso` —bus incluido— para probar el cableado y
    no una imitación. Las dos mitades se verifican por separado a propósito:
    el bloqueo va dentro de la transacción del caso de uso y el recálculo
    viene después, por el evento (ver `application.eventos.IncidenciaDetiene`).
    """
    cronograma = await _armar_cronograma(escenario)
    await _plantilla(escenario, contexto_control, cronograma)

    async with sesion_con_rls(contexto_control) as sesion:
        await _instanciar(sesion).ejecutar(
            ComandoInstanciarPrograma(obra_id=escenario.obra_id, fecha_corte=CORTE)
        )
    await _borrar_cpm(escenario.obra_id)

    async with sesion_con_rls(contexto_residente) as sesion:
        creada = await obtener_abrir_incidencia(sesion, contexto_residente).ejecutar(
            ComandoAbrirIncidencia(
                obra_id=escenario.obra_id,
                creada_por=escenario.residente_id,
                tipo=TipoIncidencia.FALTA_MATERIAL,
                impacto=ImpactoIncidencia.DETIENE,
                titulo="Sin acero en obra",
                bloquea_actividades=[cronograma.act_a],
            )
        )

    filas = await _leer_actividades([cronograma.act_a, cronograma.act_b, cronograma.act_c])
    assert filas[cronograma.act_a]["bloqueada"] is True
    # Y la ruta quedó replaneada: sin el evento, `holgura` seguiría en null.
    assert filas[cronograma.act_a]["es_critica"] is True
    assert filas[cronograma.act_c]["holgura"] == Decimal("4.00")

    # Cerrar desbloquea y vuelve a replanear (§11.3 F.4-5).
    await _borrar_cpm(escenario.obra_id)
    await _llevar_a_cierre_solicitado(contexto_supervisor, creada.id, escenario)

    async with sesion_con_rls(contexto_supervisor) as sesion:
        await obtener_cerrar_incidencia(sesion, contexto_supervisor).ejecutar(
            ComandoCerrarIncidencia(
                incidencia_id=creada.id,
                usuario_id=escenario.supervisor_id,
                rol=Rol.SUPERVISOR,
                comentario="Llegó el acero",
            )
        )

    filas = await _leer_actividades([cronograma.act_a, cronograma.act_b, cronograma.act_c])
    assert filas[cronograma.act_a]["bloqueada"] is False
    assert filas[cronograma.act_c]["holgura"] == Decimal("4.00")


async def test_incidencia_sin_impacto_detiene_no_recalcula(
    escenario: Escenario,
    contexto_control: ContextoSesion,
    contexto_residente: ContextoSesion,
) -> None:
    """El §11.3 F.5 condiciona el evento a `impacto=detiene`: una incidencia
    de detalle no toca el cronograma de nadie."""
    cronograma = await _armar_cronograma(escenario)
    await _plantilla(escenario, contexto_control, cronograma)

    async with sesion_con_rls(contexto_control) as sesion:
        await _instanciar(sesion).ejecutar(
            ComandoInstanciarPrograma(obra_id=escenario.obra_id, fecha_corte=CORTE)
        )
    await _borrar_cpm(escenario.obra_id)

    async with sesion_con_rls(contexto_residente) as sesion:
        await obtener_abrir_incidencia(sesion, contexto_residente).ejecutar(
            ComandoAbrirIncidencia(
                obra_id=escenario.obra_id,
                creada_por=escenario.residente_id,
                tipo=TipoIncidencia.DETALLE,
                impacto=ImpactoIncidencia.DETALLE,
                titulo="Falta señalización",
            )
        )

    filas = await _leer_actividades([cronograma.act_a, cronograma.act_c])
    assert filas[cronograma.act_a]["bloqueada"] is False
    assert filas[cronograma.act_c]["holgura"] is None
