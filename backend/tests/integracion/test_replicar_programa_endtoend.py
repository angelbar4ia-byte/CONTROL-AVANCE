"""Replicación masiva de un programa base, de punta a punta.

Spec §7.5 (ProgramaBase · ProgramaObra) · §11.2
(`POST /programas-base/{id}/replicar`) · §6 · §12.4.

`test_gestionar_programacion_endtoend.py` cubre la instanciación de **una**
obra; esto cubre lo que el lote agrega encima y que no se puede afirmar con una
sola casa:

* que replicar deja a cada obra exactamente como la habría dejado la
  instanciación individual —cronograma escrito y CPM persistido—;
* que el lote es de **mejor esfuerzo**: la obra que falla no arrastra a las
  demás, y su transacción no deja nada escrito;
* que el resultado reporta obra por obra, con el motivo de las que no;
* y que las precondiciones del **programa** —que exista y sea el vigente— sí
  abortan el lote entero, porque replicar una versión retirada bajaría en
  silencio otra plantilla.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from obractrl.adapters.api.casos_uso import obtener_replicar_programa
from obractrl.adapters.repos.actividades_sql import RepositorioActividadesSQL
from obractrl.adapters.repos.obras_sql import RepositorioObrasSQL
from obractrl.adapters.repos.programas_sql import RepositorioProgramasSQL
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL
from obractrl.application.casos_uso.gestionar_programacion import (
    ComandoInstanciarPrograma,
    ComandoReplicarPrograma,
    ErrorDeProgramacion,
    InstanciarProgramaObra,
    ProgramaBaseNoEncontrado,
)
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario

ARRANQUE = date(2026, 3, 2)  # lunes
CORTE = date(2026, 3, 2)


@dataclass(frozen=True, slots=True)
class Prototipo:
    """Dos nodos del árbol WBS y el programa base que los programa.

    Dos y no tres: aquí lo que se prueba es el reparto, no el motor. A(5) -> B(6)
    basta para que haya una dependencia que traducir y una ruta crítica que
    persistir.
    """

    nodo_a: uuid.UUID
    nodo_b: uuid.UUID
    base_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class ObraDelLote:
    obra_id: uuid.UUID
    clave: str
    act_a: uuid.UUID | None
    act_b: uuid.UUID | None


async def _nodos(escenario: Escenario) -> tuple[uuid.UUID, uuid.UUID]:
    nodos = (uuid.uuid4(), uuid.uuid4())
    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        for nodo, nombre in zip(nodos, ("Cimentación", "Estructura"), strict=True):
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
    await admin.dispose()
    return nodos


async def _prototipo_con_plantilla(
    escenario: Escenario, ctx: ContextoSesion
) -> Prototipo:
    """A(5) -> B(6) como programa base vigente del prototipo del escenario."""
    nodo_a, nodo_b = await _nodos(escenario)

    async with sesion_con_rls(ctx) as sesion:
        repo = RepositorioProgramasSQL(sesion)
        base_id = await repo.crear_base(
            {"prototipo_id": escenario.prototipo_id, "nombre": "Casa tipo"}
        )
        await repo.agregar_items_base(
            base_id,
            [
                {
                    "prototipo_nodo_id": nodo_a,
                    "duracion_dias": Decimal("5"),
                    "orden": 0,
                },
                {
                    "prototipo_nodo_id": nodo_b,
                    "duracion_dias": Decimal("6"),
                    "dependencias": [
                        {"ref": str(nodo_a), "tipo": "FS", "lag_dias": 0}
                    ],
                    "orden": 1,
                },
            ],
        )
        await sesion.commit()

    return Prototipo(nodo_a=nodo_a, nodo_b=nodo_b, base_id=base_id)


async def _obra(
    escenario: Escenario,
    prototipo: Prototipo,
    clave: str,
    *,
    prototipo_id: uuid.UUID | None = None,
    con_actividades: bool = True,
) -> ObraDelLote:
    """Otra casa del cluster, con o sin actividades generadas.

    `con_actividades=False` es la obra que todavía no pasó por el workflow A
    (§11.3 A.2): existe en el sistema pero no hay nada que programarle. Es el
    caso más común de fallo de una casa suelta dentro de un lote sano.
    """
    obra_id = uuid.uuid4()
    actividades = (uuid.uuid4(), uuid.uuid4()) if con_actividades else (None, None)

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                """
                insert into obra
                    (id, org_id, cluster_id, prototipo_id, clave, residente_id,
                     fecha_inicio)
                values
                    (:id, :org, :cluster, :prototipo, :clave, :res, :inicio)
                """
            ),
            {
                "id": str(obra_id),
                "org": str(escenario.org_id),
                "cluster": str(escenario.cluster_id),
                "prototipo": str(prototipo_id or escenario.prototipo_id),
                "clave": clave,
                "res": str(escenario.residente_id),
                "inicio": ARRANQUE,
            },
        )
        if con_actividades:
            nodos = (prototipo.nodo_a, prototipo.nodo_b)
            for orden, (act, nodo) in enumerate(
                zip(actividades, nodos, strict=True)
            ):
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
                        "obra": str(obra_id),
                        "nodo": str(nodo),
                        "descripcion": f"{clave} · {orden}",
                        "orden": orden,
                    },
                )
    await admin.dispose()

    return ObraDelLote(
        obra_id=obra_id, clave=clave, act_a=actividades[0], act_b=actividades[1]
    )


async def _otro_prototipo(escenario: Escenario) -> uuid.UUID:
    """Otro modelo de casa en el mismo proyecto (§7.2)."""
    prototipo_id = uuid.uuid4()
    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "insert into prototipo (id, org_id, proyecto_id, clave, nombre) "
                "values (:id, :org, :proyecto, 'CAS-2', 'Otro prototipo')"
            ),
            {
                "id": str(prototipo_id),
                "org": str(escenario.org_id),
                "proyecto": str(escenario.proyecto_id),
            },
        )
    await admin.dispose()
    return prototipo_id


async def _leer_actividades(ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.connect() as conn:
        filas = (
            await conn.execute(
                text(
                    """
                    select id, obra_id, duracion_dias, dependencias, es_critica,
                           holgura, programa_obra_id
                    from actividad
                    where id = any(cast(:ids as uuid[]))
                    """
                ),
                {"ids": [str(i) for i in ids]},
            )
        ).mappings().all()
    await admin.dispose()
    return {fila["id"]: dict(fila) for fila in filas}


def _instanciar(sesion: AsyncSession) -> InstanciarProgramaObra:
    return InstanciarProgramaObra(
        actividades=RepositorioActividadesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        programas=RepositorioProgramasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def _por_obra(resultado, obra: ObraDelLote):  # noqa: ANN001, ANN201
    """El renglón del parte que corresponde a una obra."""
    return next(r for r in resultado.obras if r.obra_id == obra.obra_id)


async def test_replicar_programa_a_varias_obras_del_prototipo(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """El gesto completo: una plantilla, tres casas, un solo comando.

    Se usa el ensamblado real de `adapters/api/casos_uso.obtener_replicar_programa`
    —no una construcción a mano— para probar también el cableado.
    """
    prototipo = await _prototipo_con_plantilla(escenario, contexto_control)
    casas = [
        await _obra(escenario, prototipo, f"FRESNO 0{n}") for n in (1, 2, 3)
    ]

    async with sesion_con_rls(contexto_control) as sesion:
        resultado = await obtener_replicar_programa(sesion).ejecutar(
            ComandoReplicarPrograma(
                programa_base_id=prototipo.base_id,
                obras=tuple(casa.obra_id for casa in casas),
                fecha_corte=CORTE,
            )
        )

    assert len(resultado.programadas) == 3
    assert resultado.fallidas == ()
    assert resultado.version_base == 1
    assert resultado.prototipo_id == escenario.prototipo_id
    # El orden del parte es el de la petición: quien lee el reporte va bajando
    # por su propia lista de casas.
    assert [r.clave for r in resultado.obras] == [
        "FRESNO 01",
        "FRESNO 02",
        "FRESNO 03",
    ]

    for casa in casas:
        parte = _por_obra(resultado, casa)
        assert parte.version == 1
        assert parte.n_actividades == 2
        assert parte.sin_item == ()
        assert parte.refs_no_resueltas == ()

    # Y cada casa quedó igual que si se hubiera instanciado a mano: las
    # dependencias del programa base traducidas a ids de actividad, y el CPM
    # persistido (§6).
    filas = await _leer_actividades(
        [act for casa in casas for act in (casa.act_a, casa.act_b)]
    )
    for casa in casas:
        assert filas[casa.act_b]["dependencias"] == [
            {"ref": str(casa.act_a), "tipo": "FS", "lag_dias": 0}
        ]
        assert filas[casa.act_a]["duracion_dias"] == Decimal("5.00")
        assert filas[casa.act_a]["es_critica"] is True
        assert filas[casa.act_b]["es_critica"] is True
        assert (
            filas[casa.act_a]["programa_obra_id"]
            == _por_obra(resultado, casa).programa_obra_id
        )


async def test_una_obra_que_falla_no_bloquea_a_las_demas(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """La decisión central del lote (§11.2): mejor esfuerzo, no todo-o-nada.

    La casa de en medio nunca se generó desde su prototipo, así que no tiene
    actividades que programar. Las otras dos tienen que quedar programadas
    igual, y el parte tiene que decir por qué esa no.
    """
    prototipo = await _prototipo_con_plantilla(escenario, contexto_control)
    buena_1 = await _obra(escenario, prototipo, "FRESNO 01")
    mala = await _obra(escenario, prototipo, "FRESNO 02", con_actividades=False)
    buena_2 = await _obra(escenario, prototipo, "FRESNO 03")

    async with sesion_con_rls(contexto_control) as sesion:
        resultado = await obtener_replicar_programa(sesion).ejecutar(
            ComandoReplicarPrograma(
                programa_base_id=prototipo.base_id,
                obras=(buena_1.obra_id, mala.obra_id, buena_2.obra_id),
                fecha_corte=CORTE,
            )
        )

    assert len(resultado.programadas) == 2
    assert [r.clave for r in resultado.fallidas] == ["FRESNO 02"]

    fallida = _por_obra(resultado, mala)
    assert fallida.programada is False
    assert fallida.version is None
    assert fallida.programa_obra_id is None
    # El motivo se lee sin cruzarlo contra nada: nombra el hecho y qué hacer.
    assert "no tiene actividades" in fallida.motivo
    assert "genérala desde su prototipo" in fallida.motivo

    # Las dos buenas quedaron escritas de verdad, no solo reportadas.
    filas = await _leer_actividades([buena_1.act_a, buena_2.act_a])
    assert filas[buena_1.act_a]["duracion_dias"] == Decimal("5.00")
    assert filas[buena_2.act_a]["duracion_dias"] == Decimal("5.00")

    # Y la fallida no dejó basura a medias: ninguna versión de cronograma.
    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioProgramasSQL(sesion)
        assert await repo.programa_vigente(mala.obra_id) is None
        assert await repo.programa_vigente(buena_1.obra_id) is not None
        assert await repo.programa_vigente(buena_2.obra_id) is not None


async def test_una_obra_de_otro_prototipo_se_reporta_y_no_se_toca(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """Dejarla pasar sería peor que rechazarla: `InstanciarProgramaObra`
    resuelve la plantilla por el prototipo de la **obra**, así que se
    programaría con otra y el parte diría "replicada" sobre algo que no lo
    fue."""
    prototipo = await _prototipo_con_plantilla(escenario, contexto_control)
    buena = await _obra(escenario, prototipo, "FRESNO 01")
    ajena = await _obra(
        escenario,
        prototipo,
        "ENCINO 01",
        prototipo_id=await _otro_prototipo(escenario),
    )

    async with sesion_con_rls(contexto_control) as sesion:
        resultado = await obtener_replicar_programa(sesion).ejecutar(
            ComandoReplicarPrograma(
                programa_base_id=prototipo.base_id,
                obras=(buena.obra_id, ajena.obra_id),
                fecha_corte=CORTE,
            )
        )

    parte = _por_obra(resultado, ajena)
    assert parte.programada is False
    assert "otro prototipo" in parte.motivo
    assert len(resultado.programadas) == 1

    async with sesion_con_rls(contexto_control) as sesion:
        assert (
            await RepositorioProgramasSQL(sesion).programa_vigente(ajena.obra_id)
            is None
        )


async def test_una_obra_fuera_de_alcance_no_delata_su_existencia(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """RLS manda también dentro del lote (§12.4): el parte no distingue "no
    existe" de "no la puedes ver", igual que el 404 individual."""
    prototipo = await _prototipo_con_plantilla(escenario, contexto_control)
    buena = await _obra(escenario, prototipo, "FRESNO 01")
    inexistente = uuid.uuid4()

    async with sesion_con_rls(contexto_control) as sesion:
        resultado = await obtener_replicar_programa(sesion).ejecutar(
            ComandoReplicarPrograma(
                programa_base_id=prototipo.base_id,
                obras=(buena.obra_id, inexistente),
                fecha_corte=CORTE,
            )
        )

    parte = next(r for r in resultado.obras if r.obra_id == inexistente)
    assert parte.programada is False
    assert parte.clave is None
    assert "fuera de tu alcance" in parte.motivo
    assert len(resultado.programadas) == 1


async def test_replicar_sobre_una_obra_ya_programada_crea_version_nueva(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """§7.5: cada bajada versiona. Es lo que la pantalla tiene que advertir
    antes, así que aquí se fija que efectivamente ocurre."""
    prototipo = await _prototipo_con_plantilla(escenario, contexto_control)
    casa = await _obra(escenario, prototipo, "FRESNO 01")

    async with sesion_con_rls(contexto_control) as sesion:
        await _instanciar(sesion).ejecutar(
            ComandoInstanciarPrograma(obra_id=casa.obra_id, fecha_corte=CORTE)
        )

    async with sesion_con_rls(contexto_control) as sesion:
        resultado = await obtener_replicar_programa(sesion).ejecutar(
            ComandoReplicarPrograma(
                programa_base_id=prototipo.base_id,
                obras=(casa.obra_id,),
                fecha_corte=CORTE,
            )
        )

    assert _por_obra(resultado, casa).version == 2

    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioProgramasSQL(sesion)
        historial = await repo.listar_programas(casa.obra_id)
        vigente = await repo.programa_vigente(casa.obra_id)

    assert [fila["version"] for fila in historial] == [2, 1]
    assert vigente["version"] == 2


async def test_una_obra_repetida_en_la_lista_se_programa_una_sola_vez(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """Dos veces la misma casa dejaría dos versiones de cronograma por un solo
    clic (§7.5), y dos renglones para la misma obra en el parte."""
    prototipo = await _prototipo_con_plantilla(escenario, contexto_control)
    casa = await _obra(escenario, prototipo, "FRESNO 01")

    async with sesion_con_rls(contexto_control) as sesion:
        resultado = await obtener_replicar_programa(sesion).ejecutar(
            ComandoReplicarPrograma(
                programa_base_id=prototipo.base_id,
                obras=(casa.obra_id, casa.obra_id),
                fecha_corte=CORTE,
            )
        )

    assert len(resultado.obras) == 1
    assert _por_obra(resultado, casa).version == 1

    async with sesion_con_rls(contexto_control) as sesion:
        historial = await RepositorioProgramasSQL(sesion).listar_programas(
            casa.obra_id
        )
    assert [fila["version"] for fila in historial] == [1]


async def test_replicar_una_version_retirada_aborta_el_lote(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """La única precondición que sí es todo-o-nada, y por qué.

    `instanciar_programa` resuelve la plantilla por `items_base_vigente`, así
    que replicar la v1 después de guardar una v2 bajaría la v2 y el usuario
    creería haber repartido la v1.
    """
    prototipo = await _prototipo_con_plantilla(escenario, contexto_control)
    casa = await _obra(escenario, prototipo, "FRESNO 01")

    # Guardar otra versión retira la anterior (§7.5).
    async with sesion_con_rls(contexto_control) as sesion:
        await RepositorioProgramasSQL(sesion).crear_base(
            {"prototipo_id": escenario.prototipo_id, "nombre": "Casa tipo v2"}
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        with pytest.raises(ErrorDeProgramacion, match="ya no es el vigente"):
            await obtener_replicar_programa(sesion).ejecutar(
                ComandoReplicarPrograma(
                    programa_base_id=prototipo.base_id,
                    obras=(casa.obra_id,),
                    fecha_corte=CORTE,
                )
            )

    async with sesion_con_rls(contexto_control) as sesion:
        assert (
            await RepositorioProgramasSQL(sesion).programa_vigente(casa.obra_id)
            is None
        )


async def test_replicar_un_programa_fuera_de_alcance_da_no_encontrado(
    contexto_ajeno: ContextoSesion,
) -> None:
    async with sesion_con_rls(contexto_ajeno) as sesion:
        with pytest.raises(ProgramaBaseNoEncontrado):
            await obtener_replicar_programa(sesion).ejecutar(
                ComandoReplicarPrograma(
                    programa_base_id=uuid.uuid4(), obras=(uuid.uuid4(),)
                )
            )


async def test_obras_candidatas_traen_su_version_de_cronograma(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """Lo que la pantalla necesita antes de elegir: qué casas hay y cuáles ya
    traen cronograma (§7.5). Son las dos lecturas que compone
    `GET /programas-base/{id}/obras`, cada una por su repositorio (§11.1).
    """
    prototipo = await _prototipo_con_plantilla(escenario, contexto_control)
    programada = await _obra(escenario, prototipo, "FRESNO 01")
    virgen = await _obra(escenario, prototipo, "FRESNO 02")
    ajena = await _obra(
        escenario,
        prototipo,
        "ENCINO 01",
        prototipo_id=await _otro_prototipo(escenario),
    )

    async with sesion_con_rls(contexto_control) as sesion:
        await _instanciar(sesion).ejecutar(
            ComandoInstanciarPrograma(obra_id=programada.obra_id, fecha_corte=CORTE)
        )

    async with sesion_con_rls(contexto_control) as sesion:
        obras = await RepositorioObrasSQL(sesion).listar(
            prototipo_id=escenario.prototipo_id
        )
        vigentes = await RepositorioProgramasSQL(sesion).programas_vigentes(
            [obra["id"] for obra in obras]
        )

    claves = {obra["clave"] for obra in obras}
    # La obra del otro modelo no es candidata de este programa.
    assert ajena.clave not in claves
    assert {"FRESNO 01", "FRESNO 02", "OBRA 01"} == claves

    assert vigentes[str(programada.obra_id)]["version"] == 1
    assert vigentes[str(programada.obra_id)]["fecha_corte"] == CORTE
    # Las que nunca se instanciaron no aparecen: eso es "sin cronograma".
    assert str(virgen.obra_id) not in vigentes


async def test_programas_vigentes_no_devuelve_obras_de_otra_organizacion(
    escenario: Escenario,
    contexto_control: ContextoSesion,
    contexto_ajeno: ContextoSesion,
) -> None:
    """El lote en batch no puede ser una rendija en RLS (§12.4): preguntar por
    un `obra_id` ajeno tiene que dar lo mismo que preguntar por uno que no
    existe."""
    prototipo = await _prototipo_con_plantilla(escenario, contexto_control)
    casa = await _obra(escenario, prototipo, "FRESNO 01")

    async with sesion_con_rls(contexto_control) as sesion:
        await _instanciar(sesion).ejecutar(
            ComandoInstanciarPrograma(obra_id=casa.obra_id, fecha_corte=CORTE)
        )

    async with sesion_con_rls(contexto_ajeno) as sesion:
        vigentes = await RepositorioProgramasSQL(sesion).programas_vigentes(
            [casa.obra_id]
        )
    assert vigentes == {}
