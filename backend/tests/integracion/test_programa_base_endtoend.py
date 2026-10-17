"""Programa base de prototipo de punta a punta (`AplicadorProgramaBase`,
extensión propia, §7.5) contra Postgres real.

Spec: cerebro `1-mundo/PROGRAMA-CPM.md` y `MODELO.md` §5c (D-442, D-443) ·
`domain.cargadores.programa_base` (el dominio puro, probado sin disco en
`tests/domain/test_programa_base.py`) · `application.casos_uso.
aplicar_carga.AplicadorProgramaBase`.

Reusa el mismo rollout real de `test_cargas_endtoend.py::
test_el_rollout_real_completo_sube_presupuesto_trabajos_y_cpu_matriz` —los 7
prototipos reales, su árbol de presupuesto, trabajos y CPU— y encima sube el
archivo real del programa de Zafiro (`PROGRAMA_ZAFIRO.xlsx`, el mismo que
cerebro carga con `backend/core/programa.py`) contra `CAS-00004`.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.api.casos_uso import FabricaDeCargas
from obractrl.adapters.repos.cargas_sql import RepositorioCargasSQL
from obractrl.adapters.repos.programas_sql import RepositorioProgramasSQL
from obractrl.adapters.repos.prototipo_nodo_sql import RepositorioPrototipoNodoSQL
from obractrl.application.casos_uso.aplicar_carga import (
    ContextoProgramaBaseIncompleto,
    PrototipoDeProgramaNoEncontrado,
)
from obractrl.application.casos_uso.gestionar_carga import ComandoEjecutarCarga
from obractrl.domain.cargadores.reporte import TipoPendiente
from obractrl.domain.programacion.cpm import TipoDependencia
from obractrl.domain.shared.diccionario import EstatusCarga, TipoCarga
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario
from tests.integracion.test_cargas_endtoend import (
    _CLAVES_PROTOTIPOS_REALES,
    _CPU_MATRIZ_OPUS_CSV,
    _PRESUPUESTO_OPUS_CSV,
    _TRABAJOS_OPUS_CSV,
    _archivo_cpu_matriz_opus_real,
    _archivo_prototipos,
    _archivo_trabajos_opus_real,
    _cargar,
    _prototipos,
    _repaquetar_csv_como_xlsx,
)

_PROGRAMA_ZAFIRO_XLSX = Path(
    "/home/user/cerebro-erp-construccion/1-mundo/fuentes/programa/PROGRAMA_ZAFIRO.xlsx"
)
"""El archivo real, repo de referencia de solo lectura — mismo criterio que
`_PRESUPUESTO_OPUS_CSV`: no se versiona aquí, la prueba se salta si la
máquina no lo tiene."""

# Dos condiciones de salto independientes (rollout real + archivo del
# programa): las dos como lista, nunca una segunda asignación a
# `pytestmark` — eso descartaría la primera en silencio, módulo a módulo
# no se suman solos (`pytestmark` es una variable normal de Python).
pytestmark = [
    pytest.mark.skipif(
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
    ),
    pytest.mark.skipif(
        not _PROGRAMA_ZAFIRO_XLSX.exists(),
        reason=f"Archivo real del programa no disponible: {_PROGRAMA_ZAFIRO_XLSX}",
    ),
]

ZAFIRO = "CAS-00004"

# Conteos reales verificados contra el archivo (`PROGRAMA_ZAFIRO.xlsx`, hoja
# `Hoja1`, bloque de `CAS-00004`: filas 2-416) y contra el árbol real de
# `prototipo_nodo` que sube el rollout (`CATALOGO_DE_PRESUPUESTO.csv`):
#   - 317 renglones `Concepto`, de los cuales 315 son partida real (clave,
#     fecha de inicio y días laborables positivos) — los otros 2 son huecos
#     de numeración del exportador (sin clave, sin fecha, 0 días).
#   - De esas 315, 314 cruzan por `ruta` contra el árbol real de
#     `prototipo_nodo`; una sola (fila 327, `ACA-02034`, bajo
#     `NIV-00009/ECO-00051/ACA-00021`) no tiene nodo correspondiente —el
#     archivo del programa y el del presupuesto no describen EXACTAMENTE el
#     mismo árbol ahí— y queda como `MAPEO_NO_RECONOCIDO`, no crítico.
#   - 75 tokens de `Vínculos` en total; 1 autovínculo (fila 335) y 4 ciclos
#     reales (183↔185 y dos cadenas más largas que pasan por un bloque como
#     predecesora, D-442/D-443) se rechazan — quedan 70 dependencias
#     aceptadas, de las cuales 16 son `vinculo_incumplido` (D-442/D-443: las
#     fechas del propio archivo no las cumplen, pero sí se cargan).
_PARTIDAS_DEL_ARCHIVO = 315
_PARTIDAS_INSERTADAS_ESPERADAS = 314  # 315 - 1 sin nodo correspondiente
_VINCULOS_RECHAZADOS_ESPERADOS = 5  # 1 autovínculo + 4 ciclos reales
_VINCULOS_INCUMPLIDOS_ESPERADOS = 16
_PARTIDAS_SIN_NODO_ESPERADAS = 1


async def _rollout_real(contexto_control: ContextoSesion) -> None:
    """Los 7 prototipos reales + su árbol de presupuesto + trabajos + la
    matriz de CPU — mismo rollout que `test_cargas_endtoend.py::
    test_el_rollout_real_completo_sube_presupuesto_trabajos_y_cpu_matriz`."""
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


def _archivo_programa_zafiro() -> bytes:
    return _PROGRAMA_ZAFIRO_XLSX.read_bytes()


async def _cargar_programa_base(
    contexto: ContextoSesion,
    *,
    prototipo_id: uuid.UUID | None,
    dry_run: bool = False,
    contenido: bytes | None = None,
) -> object:
    """Sube el programa base por el pipeline real —`FabricaDeCargas`, la
    misma fábrica que arma `POST /cargas`—, no por un wiring propio de la
    prueba."""
    async with sesion_con_rls(contexto) as sesion:
        fabrica = FabricaDeCargas(sesion)
        caso_uso = await fabrica.para(TipoCarga.PROGRAMA_BASE)
        return await caso_uso.ejecutar(
            ComandoEjecutarCarga(
                tipo=TipoCarga.PROGRAMA_BASE,
                contenido=contenido if contenido is not None else _archivo_programa_zafiro(),
                archivo_nombre="PROGRAMA_ZAFIRO.xlsx",
                usuario_id=contexto.usuario_id,
                dry_run=dry_run,
                prototipo_id=prototipo_id,
            )
        )


async def _items_base_vigente(prototipo_id: uuid.UUID) -> list[dict]:
    engine = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with engine.begin() as conn:
            filas = (
                await conn.execute(
                    text(
                        "select pbi.* from programa_base_item pbi "
                        "join programa_base pb on pb.id = pbi.programa_base_id "
                        "where pb.prototipo_id = :proto and pb.vigente"
                    ),
                    {"proto": str(prototipo_id)},
                )
            ).mappings().all()
    finally:
        await engine.dispose()
    return [dict(f) for f in filas]


class TestProgramaBaseDeZafiro:
    async def test_sube_el_programa_real_de_zafiro_contra_cas_00004(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        await _rollout_real(contexto_control)
        prototipos = await _prototipos(contexto_control)
        zafiro = prototipos[ZAFIRO]
        prototipo_id = uuid.UUID(str(zafiro["id"]))

        resultado = await _cargar_programa_base(contexto_control, prototipo_id=prototipo_id)

        assert resultado.estatus is EstatusCarga.APLICADO
        assert resultado.resumen.errores == 0
        assert resultado.resumen.insertados == _PARTIDAS_INSERTADAS_ESPERADAS

        async with sesion_con_rls(contexto_control) as sesion:
            pendientes = await RepositorioCargasSQL(sesion).listar_pendientes(
                carga_id=resultado.carga_id
            )

        rechazados = [p for p in pendientes if p["tipo"] == str(TipoPendiente.VINCULO_RECHAZADO)]
        incumplidos = [p for p in pendientes if p["tipo"] == str(TipoPendiente.VINCULO_INCUMPLIDO)]
        sin_mapeo = [p for p in pendientes if p["tipo"] == str(TipoPendiente.MAPEO_NO_RECONOCIDO)]
        assert len(rechazados) == _VINCULOS_RECHAZADOS_ESPERADOS
        assert len(incumplidos) == _VINCULOS_INCUMPLIDOS_ESPERADOS
        assert len(sin_mapeo) == _PARTIDAS_SIN_NODO_ESPERADAS
        assert sin_mapeo[0]["valor_origen"] == "ACA-02034"
        assert {r["propuesta"]["motivo"] for r in rechazados} == {
            "autovinculo",
            "cierra_un_ciclo",
        }

        items = await _items_base_vigente(prototipo_id)
        assert len(items) == _PARTIDAS_INSERTADAS_ESPERADAS

        # Los `ref` de las dependencias son ids de `prototipo_nodo`
        # (UUID), nunca números de fila del archivo ni la clave del
        # renglón (§6, `instanciar_programa._resolver` cruza por
        # `prototipo_nodo_id`) — ver el docstring de
        # `domain.cargadores.programa_base`.
        ids_de_item = {str(i["prototipo_nodo_id"]) for i in items}
        algun_vinculo = False
        for item in items:
            for dep in item["dependencias"] or []:
                algun_vinculo = True
                ref = dep["ref"] if isinstance(dep, dict) else dep
                assert isinstance(ref, str)
                uuid.UUID(ref)  # no levanta: es un UUID, no "80" ni "EST-02010"
                assert ref in ids_de_item
                assert (dep["tipo"] if isinstance(dep, dict) else None) in (
                    TipoDependencia.FIN_INICIO,
                    TipoDependencia.INICIO_INICIO,
                    TipoDependencia.FIN_FIN,
                    TipoDependencia.INICIO_FIN,
                )
        assert algun_vinculo

        # Alguna de las 18 claves de concepto que se repiten dentro del
        # propio bloque de Zafiro (confirmado a mano contra el archivo
        # real) resolvió a DOS `programa_base_item` con distinto
        # `prototipo_nodo_id` — nunca a uno solo por ambigüedad de clave.
        async with sesion_con_rls(contexto_control) as sesion:
            nodos = await RepositorioProgramasSQL(sesion).items_base_vigente(prototipo_id)
        assert len(nodos) == len({i["prototipo_nodo_id"] for i in nodos})

    async def test_dry_run_da_los_mismos_conteos_que_el_commit(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        await _rollout_real(contexto_control)
        prototipos = await _prototipos(contexto_control)
        prototipo_id = uuid.UUID(str(prototipos[ZAFIRO]["id"]))

        previa = await _cargar_programa_base(
            contexto_control, prototipo_id=prototipo_id, dry_run=True
        )
        commit = await _cargar_programa_base(contexto_control, prototipo_id=prototipo_id)

        assert previa.estatus is EstatusCarga.PREVISUALIZADO
        assert commit.estatus is EstatusCarga.APLICADO
        assert (
            previa.resumen.insertados
            == commit.resumen.insertados
            == _PARTIDAS_INSERTADAS_ESPERADAS
        )
        assert previa.pendientes == commit.pendientes

        items = await _items_base_vigente(prototipo_id)
        assert len(items) == _PARTIDAS_INSERTADAS_ESPERADAS  # solo el commit escribió

    async def test_sin_prototipo_id_se_rechaza_explicito(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        await _rollout_real(contexto_control)
        with pytest.raises(ContextoProgramaBaseIncompleto):
            await _cargar_programa_base(contexto_control, prototipo_id=None)

    async def test_prototipo_sin_su_bloque_en_el_archivo_se_rechaza(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """El archivo real trae siete prototipos (Zafiro, Rubí, Zafiro
        Plus...); pedir uno que SÍ existe en el catálogo pero cuyo
        `Capítulo` no está en el archivo no inventa nada — se rechaza
        explícito (§3.3)."""
        await _rollout_real(contexto_control)
        await _cargar(
            contexto_control,
            TipoCarga.PROTOTIPOS,
            _archivo_prototipos([["PROY", "CAS-99", "Prototipo inventado", "", "", ""]]),
        )
        prototipos = await _prototipos(contexto_control)
        prototipo_id = uuid.UUID(str(prototipos["CAS-99"]["id"]))

        with pytest.raises(PrototipoDeProgramaNoEncontrado):
            await _cargar_programa_base(contexto_control, prototipo_id=prototipo_id)

    async def test_las_claves_de_concepto_repetidas_no_se_confunden_entre_etapas(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        """`EST-02010` (la misma clave del bug real documentado en
        `test_cargas_endtoend.py::
        test_una_clave_de_concepto_repetida_en_dos_etapas_del_mismo_prototipo_no_se_pisan`)
        también aparece repetida en Zafiro — y en el archivo del programa.
        Cada ocurrencia tiene que resolver a su propio `prototipo_nodo_id`
        por `ruta`, nunca colapsar en una sola."""
        await _rollout_real(contexto_control)
        prototipos = await _prototipos(contexto_control)
        prototipo_id = uuid.UUID(str(prototipos[ZAFIRO]["id"]))

        async with sesion_con_rls(contexto_control) as sesion:
            arbol = await RepositorioPrototipoNodoSQL(sesion).por_prototipo(prototipo_id)
        ocurrencias_est02010 = [n for n in arbol if str(n["clave"]) == "EST-02010"]
        assert len(ocurrencias_est02010) >= 2  # confirmado contra el árbol real de Zafiro

        await _cargar_programa_base(contexto_control, prototipo_id=prototipo_id)

        items = await _items_base_vigente(prototipo_id)
        ids_est02010 = {
            str(i["prototipo_nodo_id"])
            for i in items
            for n in ocurrencias_est02010
            if str(i["prototipo_nodo_id"]) == str(n["id"])
        }
        # Al menos dos ocurrencias distintas de EST-02010 llegaron a tener su
        # propio renglón de programa base — no se pisaron entre sí.
        assert len(ids_est02010) >= 2
