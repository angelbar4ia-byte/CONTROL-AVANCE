"""Ingeniería del lote de punta a punta (`AplicadorIngenieriaLote`,
Fase B del encargo) contra Postgres real.

Spec: cerebro CONOCIMIENTO.md §11 (ingeniería del lote completa) · §11.9
(reversión por destajo) · §11.7 (identificación, P-30) · §13.6 (nueve
causas) · MODELO.md §1/HALLAZGO 12 (modo_cantidad) · §5g (Desviación).

**Camino "conocido"**: reusa el mismo rollout real de `test_cargas_endtoend
.py::test_el_rollout_real_completo_sube_presupuesto_trabajos_y_cpu_matriz`
—los 7 prototipos reales de `ALAMO 18`, su árbol de presupuesto, el
catálogo de trabajos y la matriz de CPU, por el pipeline real— y encima
sube el archivo real de la cimentación (`INGENIERIA_-_ALAMO_18_-_CIM.csv`)
contra una obra cuyo `prototipo_id` ya está asignado.

**Límite real, heredado de `AplicadorCPU` y documentado en el docstring
de `AplicadorIngenieriaLote`**: el catálogo CPU cargado por el rollout
real NUNCA persiste la receta interna de un compuesto (`Origen=Material`/
`ManoDeObra` de la matriz nativa de OPUS se descartan a propósito,
`_agrupar_conceptos_matriz`). Por eso, contra la base real, el destajo
`MOC-12010` —que en el dominio puro (`tests/domain/
test_ingenieria_reversion_opus_real.py`) se resuelve en profundidad contra
el compuesto `ZA1-000001`, clase `COMPUESTO`— aquí cae en `SIN` igual que
`MOS-2079`: nada en la base de este entorno sabe que `ZA1-000001` cita a
`MOC-12010`. Las pruebas de abajo verifican lo que SÍ es alcanzable con el
catálogo real tal como está hoy, y dejan dicho, sin esconderlo, lo que no.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.api.casos_uso import FabricaDeCargas
from obractrl.adapters.repos.cargas_sql import RepositorioCargasSQL
from obractrl.adapters.repos.ingenieria_lote_insumos_sql import (
    RepositorioIngenieriaLoteInsumosSQL,
)
from obractrl.adapters.repos.obras_sql import RepositorioObrasSQL
from obractrl.adapters.repos.prototipo_nodo_sql import RepositorioPrototipoNodoSQL
from obractrl.adapters.repos.prototipos_sql import RepositorioPrototiposSQL
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL
from obractrl.application.casos_uso.aplicar_carga import ContextoIngenieriaIncompleto
from obractrl.application.casos_uso.gestionar_carga import (
    ComandoEjecutarCarga,
    RevertirCarga,
)
from obractrl.domain.cargadores.reporte import TipoPendiente
from obractrl.domain.shared.diccionario import EstatusCarga, TipoCarga
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario
from tests.integracion.test_cargas_endtoend import (
    _CLAVES_PROTOTIPOS_REALES,
    _CPU_MATRIZ_OPUS_CSV,
    _PRESUPUESTO_OPUS_CSV,
    _TRABAJOS_OPUS_CSV,
    _archivo_cpu_matriz_opus_real,
    _archivo_presupuesto,
    _archivo_prototipos,
    _archivo_trabajos_opus_real,
    _cargar,
    _libro,
    _prototipos,
    _repaquetar_csv_como_xlsx,
)

pytestmark = pytest.mark.skipif(
    not (
        _PRESUPUESTO_OPUS_CSV.exists()
        and _CPU_MATRIZ_OPUS_CSV.exists()
        and _TRABAJOS_OPUS_CSV.exists()
    ),
    reason=(
        "Archivos reales del exportador de OPUS no disponibles en este "
        f"entorno: {_PRESUPUESTO_OPUS_CSV}, {_CPU_MATRIZ_OPUS_CSV}, "
        f"{_TRABAJOS_OPUS_CSV}"
    ),
)

_INGENIERIA_ALAMO_18 = _PRESUPUESTO_OPUS_CSV.parent / "ingenieria-alamo-18"
_CIMENTACION_CSV = _INGENIERIA_ALAMO_18 / "INGENIERIA_-_ALAMO_18_-_CIM.csv"
_AJU_GUALDRA_CSV = _INGENIERIA_ALAMO_18 / "INGENIERIA_-_ALAMO_18__-_AJU._GUALDRA_PB.csv"
"""Estructura real `sin_costear` (§11.8): trae NIV-/ECO- y una línea de
insumo sin clave ni precio (GUALDRA 6X12X14)."""
_AJU_PISOS_CSV = _INGENIERIA_ALAMO_18 / "INGENIERIA_-_ALAMO_18__-_AJU_PISOS.csv"
"""Estructura real `suelta` (§11.8): columna 0 siempre vacía, un solo
insumo (`PIS-80475`), sin ninguna etapa en el contenido."""
_PB_CSV = _INGENIERIA_ALAMO_18 / "INGENIERIA_-_ALAMO_18__-_PB.csv"
"""Estructura real `completa`, etapas `ECO-00006`..`ECO-00061` — ninguna
en común con las cinco de `_CIMENTACION_CSV` (`ECO-00001`..`ECO-00005`):
la sube la prueba de consolidación multi-archivo (§11.11)."""

DIAMANTE_CON_CHIMENEA = "CAS-00007"
ZAFIRO_PLUS = "CAS-00006"


async def _rollout_real(contexto_control: ContextoSesion) -> None:
    """Los 7 prototipos reales + su árbol de presupuesto + trabajos + la
    matriz de CPU, por el pipeline real — mismo rollout que
    `test_cargas_endtoend.py::
    test_el_rollout_real_completo_sube_presupuesto_trabajos_y_cpu_matriz`,
    reusado aquí tal cual porque es exactamente el catálogo que
    `AplicadorIngenieriaLote` necesita para tener algo contra qué
    identificar/revertir."""
    await _cargar(
        contexto_control,
        TipoCarga.PROTOTIPOS,
        _archivo_prototipos(
            [
                ["PROY", clave, f"Prototipo {clave}", "", "", ""]
                for clave in _CLAVES_PROTOTIPOS_REALES
            ]
        ),
    )
    resultado_presupuesto = await _cargar(
        contexto_control, TipoCarga.PRESUPUESTO, _repaquetar_csv_como_xlsx(_PRESUPUESTO_OPUS_CSV)
    )
    assert resultado_presupuesto.estatus is EstatusCarga.APLICADO

    resultado_trabajos = await _cargar(
        contexto_control, TipoCarga.TRABAJOS, _archivo_trabajos_opus_real()
    )
    assert resultado_trabajos.estatus is EstatusCarga.APLICADO

    resultado_cpu = await _cargar(
        contexto_control, TipoCarga.CPU, _archivo_cpu_matriz_opus_real()
    )
    assert resultado_cpu.estatus is EstatusCarga.APLICADO


def _archivo_ingenieria_cimentacion() -> bytes:
    """El archivo real, SIN encabezados (ver `domain.cargadores.
    ingenieria_lote`): `_repaquetar_csv_como_xlsx` igual escribe la primera
    fila del `.csv` tal cual la encuentra —aquí ya es la primera fila de
    DATOS, no un título— como la primera fila del `.xlsx` en memoria, así
    que el contenido no cambia, solo el contenedor (openpyxl, §12.11: el
    pipeline de carga solo abre `.xlsx`)."""
    return _repaquetar_csv_como_xlsx(_CIMENTACION_CSV)


async def _asignar_prototipo_a_obra(obra_id: uuid.UUID, prototipo_id: uuid.UUID) -> None:
    engine = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("update obra set prototipo_id = :proto where id = :id"),
                {"proto": str(prototipo_id), "id": str(obra_id)},
            )
    finally:
        await engine.dispose()


async def _cargar_ingenieria(
    contexto: ContextoSesion,
    *,
    obra_id: uuid.UUID,
    camino: str | None = None,
    prototipo_base_id: uuid.UUID | None = None,
    nombre_prototipo_nuevo: str | None = None,
    dry_run: bool = False,
    contenido: bytes | None = None,
    archivo_nombre: str = "INGENIERIA_-_ALAMO_18_-_CIM.csv",
    etapa_externa: str | None = None,
):
    """Sube la ingeniería del lote por el pipeline real —`FabricaDeCargas`,
    la misma fábrica que arma `POST /cargas`—, no por un wiring propio de
    la prueba: es la forma de probar que el router, `ComandoEjecutarCarga`
    y `AplicadorIngenieriaLote` encajan tal como quedaron cableados.

    Sin `contenido`, sube la cimentación real (comportamiento histórico de
    este helper); con él, sube cualquier otro archivo (real o sintético) —
    las pruebas de `suelta`/`con_concepto`/`sin_costear`/consolidación lo
    usan para no duplicar este wiring."""
    async with sesion_con_rls(contexto) as sesion:
        fabrica = FabricaDeCargas(sesion)
        caso_uso = await fabrica.para(TipoCarga.INGENIERIA_LOTE)
        return await caso_uso.ejecutar(
            ComandoEjecutarCarga(
                tipo=TipoCarga.INGENIERIA_LOTE,
                contenido=contenido if contenido is not None else _archivo_ingenieria_cimentacion(),
                archivo_nombre=archivo_nombre,
                usuario_id=contexto.usuario_id,
                obra_id=obra_id,
                camino_ingenieria=camino,
                prototipo_base_id=prototipo_base_id,
                nombre_prototipo_nuevo=nombre_prototipo_nuevo,
                dry_run=dry_run,
                etapa_externa=etapa_externa,
            )
        )


async def _desviaciones_de_obra(obra_id: uuid.UUID) -> list[dict]:
    engine = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with engine.begin() as conn:
            filas = (
                await conn.execute(
                    text(
                        "select d.*, c.clave as concepto_clave from desviacion d "
                        "left join concepto c on c.id = d.concepto_id "
                        "where d.obra_id = :obra"
                    ),
                    {"obra": str(obra_id)},
                )
            ).mappings().all()
    finally:
        await engine.dispose()
    return [dict(f) for f in filas]


class TestCaminoConocidoIdentidadConfirmada:
    """La etiqueta coincide con lo asignado (`CAS-00007`, Diamante con
    chimenea): no se abre alerta de identidad, y lo que la base real SÍ
    puede reconstruir (ver límite documentado arriba) llega a la bandeja y
    a `desviacion`."""

    async def test_aplica_sin_identidad_dudosa_y_persiste_lo_reconstruible(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        await _rollout_real(contexto_control)
        prototipos = await _prototipos(contexto_control)
        diamante = prototipos[DIAMANTE_CON_CHIMENEA]
        await _asignar_prototipo_a_obra(escenario.obra_id, uuid.UUID(str(diamante["id"])))

        resultado = await _cargar_ingenieria(contexto_control, obra_id=escenario.obra_id)

        assert resultado.estatus is EstatusCarga.APLICADO
        assert resultado.resumen.errores == 0

        async with sesion_con_rls(contexto_control) as sesion:
            pendientes = await RepositorioCargasSQL(sesion).listar_pendientes(
                carga_id=resultado.carga_id
            )

        # La etiqueta coincide con lo asignado: nunca se abre la alerta de
        # identidad dudosa (§11.7) — la carga no bloquea ni corrige sola.
        assert not [
            p for p in pendientes if p["tipo"] == str(TipoPendiente.IDENTIDAD_PROTOTIPO_DUDOSA)
        ]

        # Los destajos sin ningún candidato en la base real —directo o en
        # profundidad— caen en DESTAJO_SIN_CANDIDATO. MOS-2079 es el caso
        # que CONOCIMIENTO.md §11.9 documenta y nunca se autocorrige por
        # proximidad: queda como pendiente, no como error. MOC-12010 ya NO
        # está aquí: su único candidato vive en profundidad del compuesto
        # `ZA1-000001`, y el cargador «Análisis de básicos conceptos» ahora
        # persiste la receta interna de los 89 compuestos (matriz dentro de
        # matriz, D-612), así que la reversión lo encuentra.
        sin_candidato = {
            p["valor_origen"]
            for p in pendientes
            if p["tipo"] == str(TipoPendiente.DESTAJO_SIN_CANDIDATO)
        }
        assert "MOS-2079" in sin_candidato
        assert "MOC-12010" not in sin_candidato

        # Lo que SÍ cierra exacto contra el presupuesto real (los cuatro
        # VARIOS de §11.9/D-489) no genera pendiente de ambigüedad.
        assert not [
            p for p in pendientes if p["tipo"] == str(TipoPendiente.DESTAJO_AMBIGUO)
        ]

        desviaciones = await _desviaciones_de_obra(escenario.obra_id)
        assert desviaciones  # algo cerró distinto del presupuesto y se propuso
        assert all(d["causa"] is None for d in desviaciones)
        assert all(d["tipo"] == "consumo" for d in desviaciones)

        # EST-01053 SÍ sale, y con el mismo número que el dominio puro
        # verifica (`test_ingenieria_desviacion_opus_real.py`,
        # 1.1296296...≈1.13): el ganador del desempate de §11.13 (mayor
        # costo observado) es `MOC-01010` —una cita DIRECTA de EST-01053,
        # no la de profundidad vía `ZA1-000001`— así que el límite
        # documentado arriba (receta interna de un compuesto no
        # persistida) no le quita este número a esta prueba en particular;
        # sí le quitaría el que dependiera *solo* de la cita en profundidad.
        por_clave = {d["concepto_clave"]: d for d in desviaciones}
        assert "EST-01053" in por_clave
        est_01053 = por_clave["EST-01053"]
        assert abs(Decimal(str(est_01053["cantidad_real"])) - Decimal("1.1296296296")) < Decimal(
            "0.0001"
        )
        assert Decimal(str(est_01053["cantidad_plan"])) == Decimal(1)
        assert Decimal(str(est_01053["monto"])) > 0

    async def test_dry_run_da_los_mismos_conteos_que_el_commit(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """§9.3: la vista previa tiene que dar los mismos números que el
        commit — aquí, sin tocar `desviacion` ni la bandeja."""
        await _rollout_real(contexto_control)
        prototipos = await _prototipos(contexto_control)
        diamante = prototipos[DIAMANTE_CON_CHIMENEA]
        await _asignar_prototipo_a_obra(escenario.obra_id, uuid.UUID(str(diamante["id"])))

        previa = await _cargar_ingenieria(
            contexto_control, obra_id=escenario.obra_id, dry_run=True
        )
        commit = await _cargar_ingenieria(contexto_control, obra_id=escenario.obra_id)

        assert previa.estatus is EstatusCarga.PREVISUALIZADO
        assert commit.estatus is EstatusCarga.APLICADO
        assert previa.pendientes == commit.pendientes
        assert previa.resumen.insertados == commit.resumen.insertados

        assert await _desviaciones_de_obra(escenario.obra_id)  # solo el commit escribió
        async with sesion_con_rls(contexto_control) as sesion:
            pendientes_previa = await RepositorioCargasSQL(sesion).listar_pendientes(
                carga_id=previa.carga_id
            )
        # La vista previa SÍ registra su bandeja (§10.3 lo hace para
        # cualquier carga, dry_run o no) pero nunca escribió `desviacion`.
        assert len(pendientes_previa) == previa.pendientes


class TestCaminoConocidoIdentidadDudosa:
    """La obra está asignada a un prototipo DISTINTO del que de verdad
    corresponde (Zafiro Plus en vez de Diamante con chimenea, el caso real
    de `ALAMO 18`, §11.5/§11.7): se abre la alerta, pero la carga se
    aplica igual contra el prototipo YA ASIGNADO — nunca se reasigna sola."""

    async def test_abre_identidad_dudosa_pero_aplica_contra_el_asignado(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        await _rollout_real(contexto_control)
        prototipos = await _prototipos(contexto_control)
        zafiro = prototipos[ZAFIRO_PLUS]
        await _asignar_prototipo_a_obra(escenario.obra_id, uuid.UUID(str(zafiro["id"])))

        resultado = await _cargar_ingenieria(contexto_control, obra_id=escenario.obra_id)

        # Nunca se bloquea por duda de identidad (decisión ya tomada: carga
        # igual, con alerta abierta).
        assert resultado.estatus is EstatusCarga.APLICADO

        async with sesion_con_rls(contexto_control) as sesion:
            pendientes = await RepositorioCargasSQL(sesion).listar_pendientes(
                carga_id=resultado.carga_id
            )
        dudosas = [
            p for p in pendientes if p["tipo"] == str(TipoPendiente.IDENTIDAD_PROTOTIPO_DUDOSA)
        ]
        assert len(dudosas) == 1
        propuesta = dudosas[0]["propuesta"]
        assert propuesta["prototipo_asignado"] == ZAFIRO_PLUS
        # Se sugiere SIEMPRE el candidato más cercano, nunca None y nunca
        # el mismo que el asignado dudoso (si lo fuera, no habría duda).
        # No se fija aquí CUÁL es el sugerido: `identificar_prototipo`
        # decide por el costo total explotado de cada candidato (§11.7), y
        # el costo que esta fase explota está incompleto por el mismo
        # límite documentado en el módulo (receta interna de un compuesto
        # no persistida, `AplicadorCPU`) — con esa pieza faltante en los 7
        # candidatos por igual, el más cercano puede no coincidir con el
        # de §11.5 (Diamante con chimenea) aunque la CONCLUSIÓN de fondo
        # —Zafiro Plus no es un match, se detecta y no se autoasigna— sí
        # se sostiene, que es lo que esta prueba verifica.
        assert propuesta["sugerido"] not in (None, ZAFIRO_PLUS)
        assert Decimal(propuesta["razon_global_asignado"]) > Decimal("1.2")

        async with sesion_con_rls(contexto_control) as sesion:
            obra = await RepositorioObrasSQL(sesion).obtener(escenario.obra_id)
        assert str(obra["prototipo_id"]) == str(zafiro["id"])  # nunca se reasignó sola


class TestCaminoDisenoNuevo:
    """No hay datos reales todavía de un lote 'diseño nuevo' (el encargo lo
    dice explícito): valida el MECANISMO —clonar la estructura de un
    prototipo base y reclasificar lo que la reversión resuelve— con un
    fixture sintético pequeño, hecho a mano con las piezas mínimas del
    árbol WBS (nivel -> etapa -> concepto -> material/destajo) y su propia
    matriz de CPU, en vez del catálogo completo de `ALAMO 18`."""

    async def _prototipo_base_sintetico(
        self, contexto_control: ContextoSesion, escenario: Escenario
    ) -> uuid.UUID:
        """Un prototipo con una etapa (`ECO-1`) y un concepto (`EST-1`,
        1 unidad) cuya matriz cita un destajo (`MOC-1`, cantidad 2) —lo
        suficiente para que `revertir_destajos` tenga un `UNICO` que
        resolver al reclasificar."""
        resultado = await _cargar(
            contexto_control,
            TipoCarga.PROTOTIPOS,
            _archivo_prototipos([["PROY", "CAS-SINT", "Prototipo sintético", "", "", ""]]),
        )
        assert resultado.resumen.errores == 0

        # El destajo cuelga directo del CONCEPTO en el mismo árbol de
        # presupuesto (`AplicadorPresupuesto._procesar_concepto` arma el
        # APU desde sus hijos MATERIAL/DESTAJO/SUBCONTRATO y publica su
        # CPU ahí mismo, §7.4) — no hace falta una carga de CPU aparte
        # para este fixture mínimo.
        resultado_presupuesto = await _cargar(
            contexto_control,
            TipoCarga.PRESUPUESTO,
            _archivo_presupuesto(
                [
                    [1, None, "CAS-SINT", "Prototipo", None, None, None, None, "PROTOTIPO"],
                    [1, "CAS-SINT", "NIV-1", "Nivel", None, None, None, None, "NIVEL DE CONSTRUCCION"],
                    [1, "NIV-1", "ECO-1", "Etapa", None, None, None, None, "ETAPA DE CONSTRUCCION"],
                    [1, "ECO-1", "EST-1", "Concepto", "PZA", 1, 0, 0, "CONCEPTO"],
                    [1, "EST-1", "MOC-1", "Destajo", "PZA", 2, 100, 200, "DESTAJO"],
                ]
            ),
        )
        assert resultado_presupuesto.resumen.errores == 0

        prototipos = await _prototipos(contexto_control)
        return uuid.UUID(str(prototipos["CAS-SINT"]["id"]))

    def _archivo_ingenieria_sintetica(self) -> bytes:
        """Un solo bloque `completa`: agrupador `ECO-1`, un insumo destajo
        `MOC-1` con cantidad 6 (3 veces lo que el prototipo base trae por
        unidad: UNICO cierra a `cantidad_real / rendimiento` = 3)."""
        return _libro(
            [
                ["", "", "", "", "", "", ""],
                ["ECO-1", "", "Etapa", "", "", "", ""],
                ["", "MOC-1", "Destajo", "PZA", "6", "100", "600"],
            ]
        )

    async def test_clona_hereda_y_reclasifica_sin_generar_desviacion(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        base_id = await self._prototipo_base_sintetico(contexto_control, escenario)

        async with sesion_con_rls(contexto_control) as sesion:
            fabrica = FabricaDeCargas(sesion)
            caso_uso = await fabrica.para(TipoCarga.INGENIERIA_LOTE)
            resultado = await caso_uso.ejecutar(
                ComandoEjecutarCarga(
                    tipo=TipoCarga.INGENIERIA_LOTE,
                    contenido=self._archivo_ingenieria_sintetica(),
                    archivo_nombre="sintetica.xlsx",
                    usuario_id=contexto_control.usuario_id,
                    obra_id=escenario.obra_id,
                    camino_ingenieria="diseno_nuevo",
                    prototipo_base_id=base_id,
                )
            )

        assert resultado.estatus is EstatusCarga.APLICADO
        assert resultado.resumen.errores == 0

        async with sesion_con_rls(contexto_control) as sesion:
            obra = await RepositorioObrasSQL(sesion).obtener(escenario.obra_id)
        nuevo_prototipo_id = obra["prototipo_id"]
        assert str(nuevo_prototipo_id) != str(base_id)

        async with sesion_con_rls(contexto_control) as sesion:
            nodos = await RepositorioPrototipoNodoSQL(sesion).por_prototipo(nuevo_prototipo_id)
        por_clave = {n["clave"]: n for n in nodos if n["clave"]}

        # El nivel/etapa clonados nunca se tocan: siguen 'heredada'.
        assert por_clave["NIV-1"]["modo_cantidad"] == "heredada"
        assert por_clave["ECO-1"]["modo_cantidad"] == "heredada"
        # El concepto que la reversión resolvió (UNICO, MOC-1 citado una
        # vez por EST-1) se reclasifica con la cantidad reconstruida:
        # 6 (cantidad real del insumo) / 2 (rendimiento por unidad de
        # EST-1) = 3.
        concepto = por_clave["EST-1"]
        assert concepto["modo_cantidad"] == "cargada"
        assert concepto["cantidad"] == Decimal("3")

        # Nunca se audita contra sí mismo: el camino 'diseño_nuevo' no
        # genera ninguna Desviacion.
        assert await _desviaciones_de_obra(escenario.obra_id) == []

        # El prototipo BASE se queda exactamente como estaba.
        async with sesion_con_rls(contexto_control) as sesion:
            nodos_base = await RepositorioPrototipoNodoSQL(sesion).por_prototipo(base_id)
        base_concepto = next(n for n in nodos_base if n["clave"] == "EST-1")
        assert base_concepto["cantidad"] == Decimal("1")
        assert base_concepto["modo_cantidad"] == "capturada"

    async def test_modificar_cambia_la_cantidad_en_el_arbol_propio_y_la_vista_previa_no_escribe(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        base_id = await self._prototipo_base_sintetico(contexto_control, escenario)
        motor = create_async_engine(DATABASE_URL_ADMIN)
        try:
            async with motor.begin() as c:
                await c.execute(text("update obra set prototipo_id = :p where id = :o"), {"p": str(base_id), "o": str(escenario.obra_id)})
        finally:
            await motor.dispose()

        async def cargar(dry_run: bool):
            async with sesion_con_rls(contexto_control) as sesion:
                caso_uso = await FabricaDeCargas(sesion).para(TipoCarga.INGENIERIA_LOTE)
                return await caso_uso.ejecutar(
                    ComandoEjecutarCarga(
                        tipo=TipoCarga.INGENIERIA_LOTE,
                        contenido=self._archivo_ingenieria_sintetica(),
                        archivo_nombre="sintetica.xlsx",
                        usuario_id=contexto_control.usuario_id,
                        obra_id=escenario.obra_id,
                        camino_ingenieria="modificar",
                        dry_run=dry_run,
                    )
                )

        # La vista previa dice qué cambiaría y no toca nada: la obra sigue en el prototipo base.
        previa = await cargar(True)
        assert previa.resumen.errores == 0
        async with sesion_con_rls(contexto_control) as sesion:
            assert (await RepositorioObrasSQL(sesion).obtener(escenario.obra_id))["prototipo_id"] == base_id

        resultado = await cargar(False)
        assert resultado.estatus is EstatusCarga.APLICADO

        async with sesion_con_rls(contexto_control) as sesion:
            propio = (await RepositorioObrasSQL(sesion).obtener(escenario.obra_id))["prototipo_id"]
            assert propio != base_id  # se clonó el árbol propio
            nodos = await RepositorioPrototipoNodoSQL(sesion).por_prototipo(propio)
            base = await RepositorioPrototipoNodoSQL(sesion).por_prototipo(base_id)
        concepto = next(n for n in nodos if n["clave"] == "EST-1")
        assert concepto["cantidad"] == Decimal("3") and concepto["modo_cantidad"] == "cargada"
        # El prototipo compartido no se tocó y el cambio quedó en un borrador del presupuesto de la obra.
        assert next(n for n in base if n["clave"] == "EST-1")["cantidad"] == Decimal("1")
        motor = create_async_engine(DATABASE_URL_ADMIN)
        try:
            async with motor.connect() as c:
                estado = (
                    await c.execute(
                        text("select estado from presupuesto where prototipo_id = :p order by version desc limit 1"), {"p": str(propio)}
                    )
                ).scalar_one()
        finally:
            await motor.dispose()
        assert estado == "borrador"

    async def test_revertir_la_carga_borra_el_prototipo_nuevo_por_cascada(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """Ningún nodo clonado/reclasificado se registra aparte en el
        snapshot (ver docstring de `RepositorioPrototipoNodoSQL.
        clonar_estructura`): revertir el alta del prototipo debe bastar
        para que el árbol completo —y la asignación de la obra— regrese."""
        base_id = await self._prototipo_base_sintetico(contexto_control, escenario)

        async with sesion_con_rls(contexto_control) as sesion:
            obra_antes = await RepositorioObrasSQL(sesion).obtener(escenario.obra_id)
        prototipo_original_id = obra_antes["prototipo_id"]

        async with sesion_con_rls(contexto_control) as sesion:
            fabrica = FabricaDeCargas(sesion)
            caso_uso = await fabrica.para(TipoCarga.INGENIERIA_LOTE)
            resultado = await caso_uso.ejecutar(
                ComandoEjecutarCarga(
                    tipo=TipoCarga.INGENIERIA_LOTE,
                    contenido=self._archivo_ingenieria_sintetica(),
                    archivo_nombre="sintetica.xlsx",
                    usuario_id=contexto_control.usuario_id,
                    obra_id=escenario.obra_id,
                    camino_ingenieria="diseno_nuevo",
                    prototipo_base_id=base_id,
                )
            )

        async with sesion_con_rls(contexto_control) as sesion:
            caso_revertir = RevertirCarga(
                cargas=RepositorioCargasSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
            )
            await caso_revertir.ejecutar(resultado.carga_id, usuario_id=contexto_control.usuario_id)

        async with sesion_con_rls(contexto_control) as sesion:
            obra_despues = await RepositorioObrasSQL(sesion).obtener(escenario.obra_id)
        assert str(obra_despues["prototipo_id"]) == str(prototipo_original_id)

        async with sesion_con_rls(contexto_control) as sesion:
            prototipos = await RepositorioPrototiposSQL(sesion).listar()
        assert "CAS-SINT" in {p["clave"] for p in prototipos}  # el base sigue


class TestEstructuraSinCostear:
    """`sin_costear` (§11.8): mismo flujo que `completa` — ya no levanta
    `EstructuraDeIngenieriaNoSoportada`. El archivo real de `ALAMO 18`
    que la define (`AJU._GUALDRA_PB.csv`) no trae ningún insumo costeado
    (solo la línea sin clave/precio), así que esta prueba verifica lo que
    sí puede verificar con datos reales: la carga se aplica sin error y el
    pendiente `INSUMO_SIN_COSTEAR` —que ya emite el lector puro— llega
    hasta la bandeja de la carga real."""

    async def test_aplica_sin_error_y_el_pendiente_llega_a_la_bandeja(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        await _rollout_real(contexto_control)
        prototipos = await _prototipos(contexto_control)
        diamante = prototipos[DIAMANTE_CON_CHIMENEA]
        await _asignar_prototipo_a_obra(escenario.obra_id, uuid.UUID(str(diamante["id"])))

        resultado = await _cargar_ingenieria(
            contexto_control,
            obra_id=escenario.obra_id,
            contenido=_repaquetar_csv_como_xlsx(_AJU_GUALDRA_CSV),
            archivo_nombre="INGENIERIA_-_ALAMO_18__-_AJU._GUALDRA_PB.csv",
        )

        assert resultado.estatus is EstatusCarga.APLICADO
        assert resultado.resumen.errores == 0
        assert resultado.pendientes == 1

        async with sesion_con_rls(contexto_control) as sesion:
            pendientes = await RepositorioCargasSQL(sesion).listar_pendientes(
                carga_id=resultado.carga_id
            )
        sin_costear = [
            p for p in pendientes if p["tipo"] == str(TipoPendiente.INSUMO_SIN_COSTEAR)
        ]
        assert len(sin_costear) == 1
        assert sin_costear[0]["critico"] is False
        assert sin_costear[0]["propuesta"]["etapa"] == "ECO-00006"


class TestEstructuraSuelta:
    """`suelta` (§11.8): el contenido nunca trae etapa — se exige
    `etapa_externa`, mismo criterio que `obra_id`, nunca se adivina del
    nombre del archivo."""

    async def test_con_etapa_externa_resuelve_igual_que_si_viniera_en_contenido(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        await _rollout_real(contexto_control)
        prototipos = await _prototipos(contexto_control)
        diamante = prototipos[DIAMANTE_CON_CHIMENEA]
        await _asignar_prototipo_a_obra(escenario.obra_id, uuid.UUID(str(diamante["id"])))

        resultado = await _cargar_ingenieria(
            contexto_control,
            obra_id=escenario.obra_id,
            contenido=_repaquetar_csv_como_xlsx(_AJU_PISOS_CSV),
            archivo_nombre="INGENIERIA_-_ALAMO_18__-_AJU_PISOS.csv",
            etapa_externa="ECO-00001",
        )

        assert resultado.estatus is EstatusCarga.APLICADO
        assert resultado.resumen.errores == 0

        # La fila se persistió con la etapa_externa ya sustituida, nunca
        # con la que el contenido no trae (None).
        async with sesion_con_rls(contexto_control) as sesion:
            acumulado = await RepositorioIngenieriaLoteInsumosSQL(sesion).acumulado_por_obra(
                escenario.obra_id
            )
        suelta = [f for f in acumulado if f.clave == "PIS-80475"]
        assert len(suelta) == 1
        assert suelta[0].etapa == "ECO-00001"

    async def test_sin_etapa_externa_levanta_contexto_incompleto(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        await _rollout_real(contexto_control)
        prototipos = await _prototipos(contexto_control)
        diamante = prototipos[DIAMANTE_CON_CHIMENEA]
        await _asignar_prototipo_a_obra(escenario.obra_id, uuid.UUID(str(diamante["id"])))

        with pytest.raises(ContextoIngenieriaIncompleto):
            await _cargar_ingenieria(
                contexto_control,
                obra_id=escenario.obra_id,
                contenido=_repaquetar_csv_como_xlsx(_AJU_PISOS_CSV),
                archivo_nombre="INGENIERIA_-_ALAMO_18__-_AJU_PISOS.csv",
            )


class TestEstructuraConConcepto:
    """`con_concepto` (§11.8): el agrupador YA es el concepto — no hay
    candidatos que buscar, solo dividir la cantidad del insumo entre su
    rendimiento dentro de ESE concepto. Fixture sintético (no el archivo
    real `CEMENTO_EXTRA...csv`, que solo resuelve en profundidad contra un
    compuesto cuya receta interna el catálogo CPU real no persiste —mismo
    límite ya documentado para `MOC-12010`/`ZA1-000001`—; el dominio puro
    SÍ se prueba contra ese archivo real,
    `tests/domain/test_ingenieria_con_concepto_opus_real.py`): un concepto
    con un material citado DIRECTO, para poder verificar de punta a punta
    que la reconstrucción alimenta `Desviacion` igual que un destajo."""

    async def _prototipo_con_concepto(
        self, contexto_control: ContextoSesion, escenario: Escenario
    ) -> None:
        resultado = await _cargar(
            contexto_control,
            TipoCarga.PROTOTIPOS,
            _archivo_prototipos([["PROY", "CAS-CC", "Prototipo con concepto", "", "", ""]]),
        )
        assert resultado.resumen.errores == 0

        resultado_presupuesto = await _cargar(
            contexto_control,
            TipoCarga.PRESUPUESTO,
            _archivo_presupuesto(
                [
                    [1, None, "CAS-CC", "Prototipo", None, None, None, None, "PROTOTIPO"],
                    [1, "CAS-CC", "NIV-1", "Nivel", None, None, None, None, "NIVEL DE CONSTRUCCION"],
                    [1, "NIV-1", "ECO-1", "Etapa", None, None, None, None, "ETAPA DE CONSTRUCCION"],
                    [1, "ECO-1", "ALB-1", "Repellado sintético", None, 1, 0, 0, "CONCEPTO"],
                    [1, "ALB-1", "MAT-1", "Cemento sintético", "BTS", 10, 500, 5000, "MATERIAL"],
                ]
            ),
        )
        assert resultado_presupuesto.resumen.errores == 0

        prototipos = await _prototipos(contexto_control)
        prototipo_id = uuid.UUID(str(prototipos["CAS-CC"]["id"]))
        await _asignar_prototipo_a_obra(escenario.obra_id, prototipo_id)

    @staticmethod
    def _archivo_ingenieria_con_concepto() -> bytes:
        """Un bloque `con_concepto`: agrupador `ALB-1` (no `NIV-`/`ECO-`),
        un insumo `MAT-1` con cantidad 50.

        El rendimiento de `MAT-1` dentro de `ALB-1` lo calcula el CPU real
        a partir del presupuesto (`_prototipo_con_concepto`: concepto con
        cantidad 1, material con cantidad TOTAL 10 para esa cantidad de
        concepto) — 10 / 1 = 10 por unidad. `UNICO` cierra a
        `cantidad_insumo / rendimiento` = 50 / 10 = 5, contra
        `cantidad_plan` = 1 (la cantidad del concepto en el presupuesto):
        una diferencia grande a propósito, para cruzar el piso de monto
        mínimo de `domain.presupuesto.rendimiento.MONTO_IRRELEVANTE`
        ($1,000) y sí generar `Desviacion`."""
        return _libro(
            [
                ["", "", "", "", "", "", ""],
                ["ALB-1", "", "Repellado sintético", "", "", "", ""],
                ["", "MAT-1", "Cemento sintético", "BTS", "50", "500", "25000"],
            ]
        )

    async def test_reconstruye_por_concepto_y_genera_desviacion(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        await self._prototipo_con_concepto(contexto_control, escenario)

        resultado = await _cargar_ingenieria(
            contexto_control,
            obra_id=escenario.obra_id,
            contenido=self._archivo_ingenieria_con_concepto(),
            archivo_nombre="con_concepto_sintetica.xlsx",
        )

        assert resultado.estatus is EstatusCarga.APLICADO
        assert resultado.resumen.errores == 0

        desviaciones = await _desviaciones_de_obra(escenario.obra_id)
        assert len(desviaciones) == 1
        d = desviaciones[0]
        assert d["concepto_clave"] == "ALB-1"
        assert Decimal(str(d["cantidad_real"])) == Decimal("5")
        assert Decimal(str(d["cantidad_plan"])) == Decimal("1")
        assert Decimal(str(d["monto"])) > 0
        assert d["causa"] is None
        assert d["tipo"] == "consumo"


class TestConsolidacionMultiArchivo:
    """§11.11/P-36: "no se consolida al cargar — cada lector agrupa a su
    modo". Dos archivos reales de `ALAMO 18`, etapas distintas
    (cimentación `ECO-00001..5`, planta baja `ECO-00006..61`): el segundo
    tiene que ver el acumulado (insumos de los dos archivos, nunca solo
    los suyos) y nunca debe reabrir/duplicar lo que el primero ya cerró."""

    async def test_el_segundo_archivo_acumula_y_no_duplica_lo_del_primero(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        await _rollout_real(contexto_control)
        prototipos = await _prototipos(contexto_control)
        diamante = prototipos[DIAMANTE_CON_CHIMENEA]
        await _asignar_prototipo_a_obra(escenario.obra_id, uuid.UUID(str(diamante["id"])))

        primero = await _cargar_ingenieria(contexto_control, obra_id=escenario.obra_id)
        assert primero.estatus is EstatusCarga.APLICADO
        assert primero.resumen.errores == 0

        desviaciones_tras_cim = await _desviaciones_de_obra(escenario.obra_id)
        assert desviaciones_tras_cim  # CIM por sí sola ya genera algo (ver TestCaminoConocidoIdentidadConfirmada)
        ids_tras_cim = {d["id"] for d in desviaciones_tras_cim}
        claves_tras_cim = {d["concepto_clave"] for d in desviaciones_tras_cim}

        segundo = await _cargar_ingenieria(
            contexto_control,
            obra_id=escenario.obra_id,
            contenido=_repaquetar_csv_como_xlsx(_PB_CSV),
            archivo_nombre="INGENIERIA_-_ALAMO_18__-_PB.csv",
        )
        assert segundo.estatus is EstatusCarga.APLICADO
        assert segundo.resumen.errores == 0

        # El acumulado de la obra trae las filas de LOS DOS archivos —98
        # de CIM + 345 de PB, verificado contra el archivo real— nunca
        # menos (nada se sustituye) ni más (nada se duplica por archivo).
        async with sesion_con_rls(contexto_control) as sesion:
            acumulado = await RepositorioIngenieriaLoteInsumosSQL(sesion).acumulado_por_obra(
                escenario.obra_id
            )
        assert len(acumulado) == 98 + 345

        desviaciones_tras_pb = await _desviaciones_de_obra(escenario.obra_id)
        ids_tras_pb = {d["id"] for d in desviaciones_tras_pb}
        # Nada de lo que CIM generó se tocó, se borró ni cambió de id.
        assert ids_tras_cim <= ids_tras_pb

        nuevas = [d for d in desviaciones_tras_pb if d["id"] not in ids_tras_cim]
        claves_nuevas = {d["concepto_clave"] for d in nuevas}
        # Ninguna Desviacion nueva (de PB) repite un concepto que CIM ya
        # había resuelto: PB nunca reabre una etapa que no trae.
        assert not (claves_nuevas & claves_tras_cim)
