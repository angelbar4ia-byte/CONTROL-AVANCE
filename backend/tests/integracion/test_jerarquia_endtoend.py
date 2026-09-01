"""Programación jerárquica de punta a punta: casos de uso + repos + Postgres.

Spec §7.4 (árbol WBS) · §7.5 · §7.6 · §6 · §11.2 · §12.11.

`tests/domain/test_jerarquia.py` prueba el reparto y el rollup puros; esto
prueba que los casos de uso —cableados como en `adapters/api/casos_uso.py`—
los aplican contra la base: que una ventana capturada en una etapa baje a las
duraciones y fechas de sus conceptos, que la barra resumen que se lee después
reproduzca esa ventana, que el conflicto padre-hijo aborte **sin escribir
nada** hasta que el usuario decida, y que la profundidad de captura sobreviva
al viaje por la columna de la 0041.

El árbol de las pruebas es el del pedido:

    ESTRUCTURA PB  (etapa)
      └ PLANTA BAJA (nivel)
          ├ muro      $122 000
          ├ castillo  $ 10 000
          └ cadena    $ 30 000
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from obractrl.adapters.repos.actividades_sql import RepositorioActividadesSQL
from obractrl.adapters.repos.obras_sql import RepositorioObrasSQL
from obractrl.adapters.repos.programas_sql import RepositorioProgramasSQL
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL
from obractrl.application.casos_uso.gestionar_programacion import (
    ComandoProgramarNodo,
    ConflictoNoResuelto,
    ConsultarArbolPrograma,
    ErrorDeProgramacion,
    NodoNoProgramable,
    ProgramarNodoDelArbol,
)
from obractrl.domain.shared.diccionario import ClaseNodo
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario

ARRANQUE = date(2026, 3, 2)  # lunes

IMPORTES = {
    "muro": (Decimal("317"), Decimal("385")),  # 122 045
    "castillo": (Decimal("40"), Decimal("250")),  # 10 000
    "cadena": (Decimal("120"), Decimal("250")),  # 30 000
}


@dataclass(frozen=True, slots=True)
class Arbol:
    """Etapa → nivel → tres conceptos, con su actividad cada uno."""

    etapa: uuid.UUID
    nivel: uuid.UUID
    conceptos: tuple[uuid.UUID, ...]
    actividades: tuple[uuid.UUID, ...]

    @property
    def muro(self) -> uuid.UUID:
        return self.actividades[0]


async def _armar_arbol(escenario: Escenario) -> Arbol:
    """Prototipo con árbol de dos alturas y obra con tres actividades.

    La actividad del `escenario` base no cuelga de ningún nodo del prototipo,
    así que queda fuera del resumen: es, sin proponérselo, el caso del extra de
    catálogo (§5.1), y comprobar que no ensucia las barras es gratis.
    """
    etapa = uuid.uuid4()
    nivel = uuid.uuid4()
    conceptos = tuple(uuid.uuid4() for _ in range(3))
    actividades = tuple(uuid.uuid4() for _ in range(3))

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        await conn.execute(
            text("update obra set fecha_inicio = :inicio where id = :id"),
            {"inicio": ARRANQUE, "id": str(escenario.obra_id)},
        )
        await conn.execute(
            text(
                "insert into prototipo_nodo "
                "(id, org_id, prototipo_id, tipo, nombre, orden) "
                "values (:id, :org, :proto, 'etapa', 'ESTRUCTURA PB', 0)"
            ),
            {
                "id": str(etapa),
                "org": str(escenario.org_id),
                "proto": str(escenario.prototipo_id),
            },
        )
        await conn.execute(
            text(
                "insert into prototipo_nodo "
                "(id, org_id, prototipo_id, parent_id, tipo, nombre, orden) "
                "values (:id, :org, :proto, :padre, 'nivel', 'PLANTA BAJA', 0)"
            ),
            {
                "id": str(nivel),
                "org": str(escenario.org_id),
                "proto": str(escenario.prototipo_id),
                "padre": str(etapa),
            },
        )

        for orden, (nodo, act, clave) in enumerate(
            zip(conceptos, actividades, IMPORTES, strict=True)
        ):
            concepto_id = uuid.uuid4()
            await conn.execute(
                text(
                    "insert into concepto "
                    "(id, org_id, clave, descripcion, tipo) "
                    "values (:id, :org, :clave, :desc, 'concepto')"
                ),
                {
                    "id": str(concepto_id),
                    "org": str(escenario.org_id),
                    "clave": f"C-{clave}-{orden}",
                    "desc": clave,
                },
            )
            await conn.execute(
                text(
                    """
                    insert into prototipo_nodo
                        (id, org_id, prototipo_id, parent_id, tipo, nombre,
                         concepto_id, orden)
                    values (:id, :org, :proto, :padre, 'concepto', :nombre,
                            :concepto, :orden)
                    """
                ),
                {
                    "id": str(nodo),
                    "org": str(escenario.org_id),
                    "proto": str(escenario.prototipo_id),
                    "padre": str(nivel),
                    "nombre": clave,
                    "concepto": str(concepto_id),
                    "orden": orden,
                },
            )
            cantidad, precio = IMPORTES[clave]
            await conn.execute(
                text(
                    """
                    insert into actividad
                        (id, org_id, obra_id, prototipo_nodo_id, concepto_id,
                         descripcion, cant_base, cant_programada,
                         precio_unitario, created_at)
                    values
                        (:id, :org, :obra, :nodo, :concepto, :desc,
                         :cantidad, :cantidad, :precio,
                         now() + make_interval(secs => :orden))
                    """
                ),
                {
                    "id": str(act),
                    "org": str(escenario.org_id),
                    "obra": str(escenario.obra_id),
                    "nodo": str(nodo),
                    "concepto": str(concepto_id),
                    "desc": clave,
                    "cantidad": cantidad,
                    "precio": precio,
                    "orden": orden,
                },
            )
    await admin.dispose()

    return Arbol(
        etapa=etapa, nivel=nivel, conceptos=conceptos, actividades=actividades
    )


def _consultar(sesion: AsyncSession) -> ConsultarArbolPrograma:
    return ConsultarArbolPrograma(
        actividades=RepositorioActividadesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        programas=RepositorioProgramasSQL(sesion),
    )


def _programar(sesion: AsyncSession) -> ProgramarNodoDelArbol:
    return ProgramarNodoDelArbol(
        actividades=RepositorioActividadesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        programas=RepositorioProgramasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


async def _duraciones(
    ctx: ContextoSesion, obra_id: uuid.UUID
) -> dict[str, tuple[Decimal, date | None, date | None]]:
    async with sesion_con_rls(ctx) as sesion:
        filas = await RepositorioActividadesSQL(sesion).programacion_de_obra(obra_id)
    return {
        str(f["id"]): (
            Decimal(str(f["duracion_dias"])),
            f["fecha_inicio"],
            f["fecha_termino"],
        )
        for f in filas
    }


# --- Lectura: el Gantt jerárquico (§7.4) ---------------------------------


async def test_el_arbol_trae_barras_resumen_de_etapa_y_nivel(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    arbol = await _armar_arbol(escenario)

    async with sesion_con_rls(contexto_control) as sesion:
        resultado = await _consultar(sesion).ejecutar(escenario.obra_id)

    por_nodo = {n.nodo_id: n for n in resultado.nodos}
    assert str(arbol.etapa) in por_nodo
    assert str(arbol.nivel) in por_nodo

    etapa = por_nodo[str(arbol.etapa)]
    assert etapa.tipo is ClaseNodo.ETAPA
    assert etapa.profundidad == 0
    assert set(etapa.actividades) == {str(a) for a in arbol.actividades}
    # La actividad suelta del escenario base no cuelga del árbol: no entra.
    assert str(escenario.actividad_id) not in etapa.actividades


async def test_el_importe_del_resumen_sale_de_cantidad_por_precio(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """§7.3: el peso del reparto y del avance es el importe de la actividad."""
    arbol = await _armar_arbol(escenario)

    async with sesion_con_rls(contexto_control) as sesion:
        resultado = await _consultar(sesion).ejecutar(escenario.obra_id)

    etapa = next(n for n in resultado.nodos if n.nodo_id == str(arbol.etapa))
    esperado = sum(
        cantidad * precio for cantidad, precio in IMPORTES.values()
    )
    assert etapa.importe == esperado


async def test_una_urbanizacion_sin_prototipo_no_tiene_arbol_que_resumir(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """`ck_obra_urba` (0004) sólo deja una obra sin prototipo si es urbanización.

    Ese es el único caso real de este 422: una urbanización no nació de ningún
    árbol WBS, así que no hay nada de qué derivar barras resumen (§7.2, §7.4).
    """
    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "update obra set prototipo_id = null, es_urba = true "
                "where id = :id"
            ),
            {"id": str(escenario.obra_id)},
        )
    await admin.dispose()

    async with sesion_con_rls(contexto_control) as sesion:
        with pytest.raises(ErrorDeProgramacion, match="prototipo"):
            await _consultar(sesion).ejecutar(escenario.obra_id)


# --- Escritura: la ventana gruesa baja al detalle (§7.5) -----------------


async def test_programar_la_etapa_reparte_los_dias_entre_sus_conceptos(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """20 días en `ESTRUCTURA PB` acomodan a los tres uno tras otro."""
    arbol = await _armar_arbol(escenario)

    async with sesion_con_rls(contexto_control) as sesion:
        resultado = await _programar(sesion).ejecutar(
            ComandoProgramarNodo(
                obra_id=escenario.obra_id,
                prototipo_nodo_id=arbol.etapa,
                duracion_dias=Decimal(20),
                fecha_inicio=ARRANQUE,
            )
        )

    assert len(resultado.actividades) == 3
    assert resultado.fecha_inicio == ARRANQUE
    assert resultado.omitidas == ()

    escrito = await _duraciones(contexto_control, escenario.obra_id)
    dias = {str(a): escrito[str(a)][0] for a in arbol.actividades}
    assert sum(dias.values()) == Decimal(20)
    # El muro de $122k se lleva más que la cadena de $30k y que el castillo.
    assert dias[str(arbol.actividades[0])] > dias[str(arbol.actividades[2])]
    assert dias[str(arbol.actividades[2])] > dias[str(arbol.actividades[1])]

    # Uno tras otro, sin huecos: cada uno arranca donde cerró el anterior.
    anterior = None
    for act in arbol.actividades:
        _, inicio, fin = escrito[str(act)]
        assert inicio is not None and fin is not None
        if anterior is not None:
            assert inicio == anterior
        anterior = fin


async def test_lo_repartido_vuelve_a_subir_como_la_misma_ventana(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """Ida y vuelta contra la base: repartir 20 y leer el resumen da 20.

    Es la invariante que hace de las dos direcciones la misma cifra vista desde
    dos lados. Si el reparto perdiera centésimas al pasar por `numeric(8,2)`,
    la barra de la etapa diría 19.98 y parecería un conflicto.
    """
    arbol = await _armar_arbol(escenario)

    async with sesion_con_rls(contexto_control) as sesion:
        await _programar(sesion).ejecutar(
            ComandoProgramarNodo(
                obra_id=escenario.obra_id,
                prototipo_nodo_id=arbol.etapa,
                duracion_dias=Decimal(20),
                fecha_inicio=ARRANQUE,
            )
        )

    async with sesion_con_rls(contexto_control) as sesion:
        resultado = await _consultar(sesion).ejecutar(escenario.obra_id)

    por_nodo = {n.nodo_id: n for n in resultado.nodos}
    for nodo_id in (str(arbol.etapa), str(arbol.nivel)):
        assert por_nodo[nodo_id].duracion_dias == Decimal(20)
        assert por_nodo[nodo_id].fecha_inicio == ARRANQUE


async def test_programar_el_nivel_tambien_reparte(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """Por nivel, por etapa o por concepto: la operación es la misma (§7.4)."""
    arbol = await _armar_arbol(escenario)

    async with sesion_con_rls(contexto_control) as sesion:
        resultado = await _programar(sesion).ejecutar(
            ComandoProgramarNodo(
                obra_id=escenario.obra_id,
                prototipo_nodo_id=arbol.nivel,
                duracion_dias=Decimal(12),
                fecha_inicio=ARRANQUE,
            )
        )

    assert len(resultado.actividades) == 3
    escrito = await _duraciones(contexto_control, escenario.obra_id)
    assert sum(escrito[str(a)][0] for a in arbol.actividades) == Decimal(12)


async def test_programar_un_concepto_le_da_toda_la_ventana(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    arbol = await _armar_arbol(escenario)

    async with sesion_con_rls(contexto_control) as sesion:
        await _programar(sesion).ejecutar(
            ComandoProgramarNodo(
                obra_id=escenario.obra_id,
                prototipo_nodo_id=arbol.conceptos[0],
                duracion_dias=Decimal(16),
                fecha_inicio=ARRANQUE,
            )
        )

    escrito = await _duraciones(contexto_control, escenario.obra_id)
    assert escrito[str(arbol.muro)][0] == Decimal(16)
    # Los otros dos no se tocaron: la ventana era del nodo del muro.
    assert escrito[str(arbol.actividades[1])][0] == Decimal(1)


async def test_no_se_crea_ninguna_actividad_de_resumen(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """La barra de nivel/etapa es derivada; si fuera una fila, duplicaría
    cantidad, avance y costo sobre los de sus hijos (§6, §7.6, §11.3 A.2)."""
    arbol = await _armar_arbol(escenario)

    antes = await _duraciones(contexto_control, escenario.obra_id)
    async with sesion_con_rls(contexto_control) as sesion:
        await _programar(sesion).ejecutar(
            ComandoProgramarNodo(
                obra_id=escenario.obra_id,
                prototipo_nodo_id=arbol.etapa,
                duracion_dias=Decimal(20),
            )
        )
    despues = await _duraciones(contexto_control, escenario.obra_id)

    assert set(antes) == set(despues)


async def test_un_nodo_de_otro_arbol_es_404(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    await _armar_arbol(escenario)

    async with sesion_con_rls(contexto_control) as sesion:
        with pytest.raises(NodoNoProgramable):
            await _programar(sesion).ejecutar(
                ComandoProgramarNodo(
                    obra_id=escenario.obra_id,
                    prototipo_nodo_id=uuid.uuid4(),
                    duracion_dias=Decimal(20),
                )
            )


# --- El conflicto padre-hijo (§7.5) --------------------------------------


async def test_el_conflicto_aborta_sin_escribir_nada(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """Los conceptos ya programados a mano contra una ventana que no cuadra.

    Ni el padre gana en silencio ni el hijo: la operación no escribe y el
    usuario recibe las dos cifras para decidir (§7.5).
    """
    arbol = await _armar_arbol(escenario)

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        for act, dias in zip(arbol.actividades, (10, 8, 5), strict=True):
            await conn.execute(
                text("update actividad set duracion_dias = :d where id = :id"),
                {"d": dias, "id": str(act)},
            )
    await admin.dispose()

    antes = await _duraciones(contexto_control, escenario.obra_id)

    async with sesion_con_rls(contexto_control) as sesion:
        with pytest.raises(ConflictoNoResuelto) as capturado:
            await _programar(sesion).ejecutar(
                ComandoProgramarNodo(
                    obra_id=escenario.obra_id,
                    prototipo_nodo_id=arbol.etapa,
                    duracion_dias=Decimal(20),
                )
            )

    conflicto = capturado.value.conflicto
    assert conflicto.dias_capturados == Decimal(20)
    assert conflicto.dias_derivados == Decimal(23)
    assert set(conflicto.actividades) == {str(a) for a in arbol.actividades}

    assert await _duraciones(contexto_control, escenario.obra_id) == antes


async def test_forzar_es_la_decision_de_conservar_al_padre(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    arbol = await _armar_arbol(escenario)

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        for act, dias in zip(arbol.actividades, (10, 8, 5), strict=True):
            await conn.execute(
                text("update actividad set duracion_dias = :d where id = :id"),
                {"d": dias, "id": str(act)},
            )
    await admin.dispose()

    async with sesion_con_rls(contexto_control) as sesion:
        await _programar(sesion).ejecutar(
            ComandoProgramarNodo(
                obra_id=escenario.obra_id,
                prototipo_nodo_id=arbol.etapa,
                duracion_dias=Decimal(20),
                fecha_inicio=ARRANQUE,
                forzar=True,
            )
        )

    escrito = await _duraciones(contexto_control, escenario.obra_id)
    assert sum(escrito[str(a)][0] for a in arbol.actividades) == Decimal(20)


async def test_el_arbol_marca_el_conflicto_de_la_plantilla_gruesa(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """Un `programa_base_item` sobre un nodo `etapa` es la captura gruesa.

    Siempre fue representable —la columna referencia cualquier nodo del árbol
    (0006)— y hasta ahora nadie la resolvía. Aquí es contra lo que se compara
    el resumen de sus conceptos.
    """
    arbol = await _armar_arbol(escenario)

    admin = create_async_engine(DATABASE_URL_ADMIN)
    async with admin.begin() as conn:
        for act, dias in zip(arbol.actividades, (10, 8, 5), strict=True):
            await conn.execute(
                text(
                    "update actividad set duracion_dias = :d, "
                    "fecha_inicio = null, fecha_termino = null where id = :id"
                ),
                {"d": dias, "id": str(act)},
            )
    await admin.dispose()

    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioProgramasSQL(sesion)
        base_id = await repo.crear_base(
            {
                "prototipo_id": escenario.prototipo_id,
                "profundidad_captura": ClaseNodo.ETAPA.value,
            }
        )
        await repo.agregar_items_base(
            base_id,
            [{"prototipo_nodo_id": arbol.etapa, "duracion_dias": Decimal(20)}],
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        resultado = await _consultar(sesion).ejecutar(escenario.obra_id)

    assert resultado.profundidad_captura is ClaseNodo.ETAPA
    conflictos = {c.nodo_id: c for c in resultado.conflictos}
    assert str(arbol.etapa) in conflictos
    assert conflictos[str(arbol.etapa)].dias_capturados == Decimal(20)


async def test_la_profundidad_de_captura_viaja_por_la_columna(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """0041: la sugerencia se guarda y se lee tal cual, y sin plantilla es
    `concepto` —el comportamiento previo a la migración."""
    await _armar_arbol(escenario)

    async with sesion_con_rls(contexto_control) as sesion:
        resultado = await _consultar(sesion).ejecutar(escenario.obra_id)
    assert resultado.profundidad_captura is ClaseNodo.CONCEPTO

    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioProgramasSQL(sesion)
        base_id = await repo.crear_base(
            {
                "prototipo_id": escenario.prototipo_id,
                "profundidad_captura": ClaseNodo.NIVEL.value,
            }
        )
        await sesion.commit()
        base = await repo.obtener_base(base_id)

    assert str(base["profundidad_captura"]) == "nivel"

    async with sesion_con_rls(contexto_control) as sesion:
        resultado = await _consultar(sesion).ejecutar(escenario.obra_id)
    assert resultado.profundidad_captura is ClaseNodo.NIVEL
