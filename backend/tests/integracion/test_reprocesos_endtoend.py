"""Reprocesos: correr dos veces da el mismo resultado (§11.7).

El §11.7 lo pide con esas palabras, y la razón es concreta: los reprocesos del
sistema —recalcular la ruta crítica, reaplicar una carga— se disparan por evento
y por job, y un job **se reintenta**. Si reintentarlo cambiara el resultado, un
fallo transitorio de red se convertiría en datos distintos.

La idempotencia de las cargas ya está probada en `test_cargas_endtoend`
(«el mismo archivo no se aplica dos veces»). Lo que falta aquí es el reproceso
que sí escribe cada vez: el CPM, que recalcula y **pisa** fechas, holguras y
criticidad de todas las actividades de la obra.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.repos.actividades_sql import RepositorioActividadesSQL
from obractrl.adapters.repos.obras_sql import RepositorioObrasSQL
from obractrl.adapters.repos.programas_sql import RepositorioProgramasSQL
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL
from obractrl.application.casos_uso.gestionar_programacion import (
    ComandoRecalcularRutaCritica,
    RecalcularRutaCritica,
)
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario

CAMPOS_DERIVADOS = (
    "es_critica",
    "holgura",
    "desfase",
    # Las **fechas no están** a propósito: el recálculo no las escribe. Las fija
    # la instanciación del programa (§7.5) y el CPM solo deriva criticidad,
    # holgura y desfase sobre ellas (`_a_guardable`). Meterlas aquí haría que
    # esta prueba afirmara algo que el caso de uso nunca prometió.
)


async def _sembrar_cronograma(escenario: Escenario) -> None:
    """Tres actividades encadenadas con duraciones distintas."""
    admin = create_async_engine(DATABASE_URL_ADMIN)
    ids = [uuid.uuid4() for _ in range(3)]
    async with admin.begin() as conn:
        for indice, (actividad_id, duracion) in enumerate(zip(ids, (3, 5, 2), strict=True)):
            dependencias = (
                "[]"
                if indice == 0
                else f'[{{"ref": "{ids[indice - 1]}", "tipo": "FS", "lag_dias": 0}}]'
            )
            await conn.execute(
                text(
                    "insert into actividad (id, org_id, obra_id, descripcion, "
                    "cant_base, cant_programada, duracion_dias, dependencias) "
                    "values (:id, :org, :obra, :desc, 10, 10, :dur, "
                    "cast(:deps as jsonb))"
                ),
                {
                    "id": str(actividad_id),
                    "org": str(escenario.org_id),
                    "obra": str(escenario.obra_id),
                    "desc": f"Etapa {indice + 1}",
                    "dur": duracion,
                    "deps": dependencias,
                },
            )
    await admin.dispose()


async def _derivados(ctx: ContextoSesion, obra_id: uuid.UUID) -> dict:
    """Lo que el CPM escribe, tal como quedó en la base."""
    async with sesion_con_rls(ctx) as sesion:
        filas = await RepositorioActividadesSQL(sesion).programacion_de_obra(obra_id)
    return {
        str(fila["id"]): {
            campo: str(fila.get(campo)) for campo in CAMPOS_DERIVADOS
        }
        for fila in filas
    }


async def _recalcular(ctx: ContextoSesion, obra_id: uuid.UUID) -> None:
    async with sesion_con_rls(ctx) as sesion:
        caso = RecalcularRutaCritica(
            actividades=RepositorioActividadesSQL(sesion),
            obras=RepositorioObrasSQL(sesion),
            programas=RepositorioProgramasSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
        )
        await caso.ejecutar(ComandoRecalcularRutaCritica(obra_id=obra_id))


class TestRecalcularRutaCritica:
    async def test_dos_corridas_dan_el_mismo_resultado(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """El §11.7 con esas palabras: correr 2× = mismo resultado.

        Importa porque el recálculo se dispara por evento y viaja como job, y un
        job se reintenta: si reintentarlo moviera las fechas, un fallo
        transitorio de red se convertiría en un cronograma distinto.
        """
        await _sembrar_cronograma(escenario)

        await _recalcular(contexto_control, escenario.obra_id)
        primera = await _derivados(contexto_control, escenario.obra_id)

        await _recalcular(contexto_control, escenario.obra_id)
        segunda = await _derivados(contexto_control, escenario.obra_id)

        assert primera == segunda
        # Y que de verdad haya calculado algo: comparar dos vacíos también da
        # igual, y eso no probaría nada. Con tres actividades encadenadas, la
        # cadena entera es crítica —no hay caminos alternativos— así que tiene
        # que haber al menos una `es_critica`.
        assert primera, "el escenario debe tener actividades programadas"
        assert any(v["es_critica"] == "True" for v in primera.values())

    async def test_tres_corridas_tampoco_se_desplazan(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """Dos corridas pueden coincidir por casualidad si el cálculo depende de
        algo que solo cambia cada tanto. Tres, no."""
        await _sembrar_cronograma(escenario)

        resultados = []
        for _ in range(3):
            await _recalcular(contexto_control, escenario.obra_id)
            resultados.append(await _derivados(contexto_control, escenario.obra_id))

        assert resultados[0] == resultados[1] == resultados[2]

    async def test_recalcular_una_obra_sin_actividades_no_truena(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """Es el estado normal de una obra recién creada, y el evento
        `ActividadCerrada` puede llegar antes de que haya cronograma."""
        await _recalcular(contexto_control, escenario.obra_id)
        await _recalcular(contexto_control, escenario.obra_id)


class TestCapturaDeAvance:
    async def test_capturar_el_mismo_total_dos_veces_no_lo_duplica(
        self, escenario: Escenario, contexto_residente: ContextoSesion
    ) -> None:
        """`PATCH /actividades/{id}/avance` recibe un **absoluto** (D6).

        Mandarlo dos veces tiene que dejar el mismo total: el segundo delta es
        cero. Si en vez de eso sumara, un reintento de red duplicaría el avance
        —y con él la estimación que se cobra—.
        """
        from obractrl.application.casos_uso.capturar_avance import (
            CapturarAvance,
            ComandoCapturarAvance,
        )

        async def capturar(cantidad: Decimal) -> None:
            async with sesion_con_rls(contexto_residente) as sesion:
                caso = CapturarAvance(
                    actividades=RepositorioActividadesSQL(sesion),
                    uow=UnidadDeTrabajoSQL(sesion),
                )
                await caso.ejecutar(
                    ComandoCapturarAvance(
                        actividad_id=escenario.actividad_id,
                        cant_ejecutada=cantidad,
                        usuario_id=escenario.residente_id,
                    )
                )

        await capturar(Decimal(4))
        await capturar(Decimal(4))

        async with sesion_con_rls(contexto_residente) as sesion:
            fila = await RepositorioActividadesSQL(sesion).obtener(
                escenario.actividad_id
            )
            total_bitacora = (
                await sesion.execute(
                    text(
                        "select coalesce(sum(delta_ejecutado), 0) "
                        "from registro_avance where actividad_id = :act"
                    ),
                    {"act": str(escenario.actividad_id)},
                )
            ).scalar_one()

        assert fila is not None
        assert Decimal(str(fila["cant_ejecutada"])) == Decimal(4)
        # La identidad de D6: el total **es** la suma de la bitácora.
        assert Decimal(str(total_bitacora)) == Decimal(4)
