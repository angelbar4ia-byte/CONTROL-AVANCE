"""Cargas del §10.6 de punta a punta: `.xlsx` → pipeline → Postgres real.

Spec §9.2 (pipeline) · §9.3 (reporte por fila) · §10.2 (modos) · §10.3
(bandeja) · §10.5 (valuación y motivos) · §10.6 (cabeceras) · §10.8
(versión y reversa) · §12.11 (Definition of Done).

`tests/domain/test_cargadores.py` prueba las reglas sin disco; esto prueba
que el archivo real las atraviesa: openpyxl lee, el dominio valida, el
aplicador escribe bajo RLS y el lote queda revertible.

Los archivos de ejemplo se **generan aquí** con openpyxl: no se versiona un
binario de prueba, y así el archivo siempre coincide con el contrato que el
§10.6 describe.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import Workbook
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from obractrl.adapters.excel.cargadores import cargador_para
from obractrl.adapters.repos.cargas_sql import RepositorioCargasSQL
from obractrl.adapters.repos.conceptos_sql import RepositorioConceptosSQL
from obractrl.adapters.repos.contratistas_sql import RepositorioContratistasSQL
from obractrl.adapters.repos.familias_sql import RepositorioFamiliasSQL
from obractrl.adapters.repos.insumos_sql import RepositorioInsumosSQL
from obractrl.adapters.repos.materiales_sql import RepositorioMaterialesSQL
from obractrl.adapters.repos.niveles_etapas_sql import RepositorioNivelesEtapasSQL
from obractrl.adapters.repos.obras_sql import RepositorioObrasSQL
from obractrl.adapters.repos.presupuestos_sql import RepositorioPresupuestosSQL
from obractrl.adapters.repos.prototipo_nodo_sql import RepositorioPrototipoNodoSQL
from obractrl.adapters.repos.prototipos_sql import RepositorioPrototiposSQL
from obractrl.adapters.repos.proyectos_sql import RepositorioProyectosSQL
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL
from obractrl.adapters.repos.unidades_sql import RepositorioUnidadesSQL
from obractrl.application.casos_uso.aplicar_carga import (
    AplicadorAlmacen,
    AplicadorCPU,
    AplicadorDeCarga,
    AplicadorMateriales,
    AplicadorPresupuesto,
    AplicadorPrototipos,
)
from obractrl.application.casos_uso.gestionar_carga import (
    ComandoEjecutarCarga,
    EjecutarCarga,
    ResultadoCarga,
    RevertirCarga,
)
from obractrl.domain.cargadores.cabeceras import ErrorDeCabecera
from obractrl.domain.cargadores.reporte import TipoPendiente
from obractrl.domain.proyectos.reglas import ErrorDeProyecto
from obractrl.domain.shared.diccionario import EstatusCarga, ModoCarga, TipoCarga
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario

# --- Construcción de los archivos de ejemplo -----------------------------


def _libro(filas: list[list[object]], *, hoja: str | None = None) -> bytes:
    """Un `.xlsx` en memoria con esas filas. Nada toca el disco."""
    libro = Workbook()
    pagina = libro.active
    assert pagina is not None
    if hoja:
        pagina.title = hoja
    for fila in filas:
        pagina.append(fila)
    memoria = BytesIO()
    libro.save(memoria)
    libro.close()
    return memoria.getvalue()


_CABECERAS_MATERIALES = ["Clave", "Descripción", "Unidad", "Clase", "Costo base", "C/Último", "IVA"]


def _archivo_materiales(filas: list[list[object]]) -> bytes:
    return _libro([_CABECERAS_MATERIALES, *filas])


_CABECERAS_CPU = [
    "CLAVE", "CLAVE INSUMO", "DESCRIPCION", "UNIDAD", "CANTIDAD", "P.U.", "", "FAMILIA", "TIPO",
]


def _fila_cpu(
    clave: str = "",
    insumo: str = "",
    descripcion: str = "",
    unidad: str = "",
    cantidad: object = "",
    pu: object = "",
    tipo: str = "",
) -> list[object]:
    return [clave, insumo, descripcion, unidad, cantidad, pu, "", "", tipo]


def _archivo_cpu(filas: list[list[object]]) -> bytes:
    return _libro([_CABECERAS_CPU, *filas], hoja="EXPORTADOR")


_CABECERAS_ALMACEN = [
    "# Parte", "Parte", "Clase", "Ubicacion", "Lote", "Contratista", "Fecha",
    "Motivo", "Efecto Qty", "Efecto Costo", "C/Último", "C/Promedio",
    "Referencia", "# Almacen", "Almacen", "Usuario",
]


def _archivo_almacen(filas: list[list[object]]) -> bytes:
    return _libro([_CABECERAS_ALMACEN, *filas], hoja="Consulta")


_CABECERAS_PROTOTIPOS = ["Proyecto", "Clave", "Nombre", "M2", "Niveles", "Recamaras"]


def _archivo_prototipos(filas: list[list[object]]) -> bytes:
    return _libro([_CABECERAS_PROTOTIPOS, *filas])


_CABECERAS_PRESUPUESTO = [
    "INDICE", "CLAVE PADRE", "CLAVE HIJO", "DESCRIPCION", "UNIDAD",
    "CANTIDAD", "PRECIO UNITARIO", "IMPORTE", "TIPO",
]


def _archivo_presupuesto(filas: list[list[object]]) -> bytes:
    return _libro([_CABECERAS_PRESUPUESTO, *filas])


def _prototipo_simple(
    clave_prototipo: str, clave_concepto: str, cantidad_alambre: object
) -> list[list[object]]:
    """Árbol mínimo de un prototipo: 1 nivel, 1 etapa, 1 concepto con un
    material — el bloque que casi todos los tests de este cargador reusan,
    variando solo `clave_prototipo`/`clave_concepto`/`cantidad_alambre` para
    forzar coincidencia o conflicto de composición."""
    return [
        [1, None, clave_prototipo, "Prototipo", None, None, None, None, "PROTOTIPO"],
        [1, clave_prototipo, "NIV-1", "Cimentación", None, None, None, None, "NIVEL DE CONSTRUCCION"],
        [1, "NIV-1", "ECO-1", "Estructura", None, None, None, None, "ETAPA DE CONSTRUCCION"],
        # Sin unidad: "M2" no está sembrada en `catalogos` y generaría un
        # pendiente de UNIDAD que no es lo que estos tests ejercitan.
        [1, "ECO-1", clave_concepto, "Losa", None, 1, 0, 0, "CONCEPTO"],
        [1, clave_concepto, "ACE-01", "Alambre", "KG", cantidad_alambre, 20, None, "MATERIAL"],
    ]


# --- Escenario de catálogos ----------------------------------------------


@dataclass(frozen=True, slots=True)
class Catalogos:
    unidad_id: uuid.UUID
    familia_id: uuid.UUID
    motivo_id: uuid.UUID


@pytest.fixture
async def catalogos(escenario: Escenario) -> AsyncIterator[Catalogos]:
    """Unidad, familia y motivo mínimos para que los cruces del §10.3 tengan
    contra qué homologar. Se arma con el rol admin, como el resto de fixtures."""
    engine = create_async_engine(DATABASE_URL_ADMIN)
    unidad, familia, motivo = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "insert into unidad (id, org_id, clave, nombre, sinonimos) "
                "values (:id, :org, 'ton', 'Tonelada', array['TONELADA'])"
            ),
            {"id": str(unidad), "org": str(escenario.org_id)},
        )
        await conn.execute(
            text(
                "insert into familia (id, org_id, clave, nombre, aplica_a, iva_aplica) "
                "values (:id, :org, 'CEM', 'Cementantes', 'material', true)"
            ),
            {"id": str(familia), "org": str(escenario.org_id)},
        )
        await conn.execute(
            text(
                "insert into motivo_almacen (id, org_id, clave, descripcion, signo, bucket) "
                "values (:id, :org, 'SALIDA-PROD', 'Salida para producción', -1, 'salidas')"
            ),
            {"id": str(motivo), "org": str(escenario.org_id)},
        )
    await engine.dispose()

    yield Catalogos(unidad_id=unidad, familia_id=familia, motivo_id=motivo)


def _aplicador(tipo: TipoCarga, sesion: AsyncSession) -> AplicadorDeCarga:
    """Mismo cableado que `adapters/api/casos_uso.py::FabricaDeCargas`."""
    cargas = RepositorioCargasSQL(sesion)
    if tipo is TipoCarga.MATERIALES:
        return AplicadorMateriales(
            insumos=RepositorioInsumosSQL(sesion),
            unidades=RepositorioUnidadesSQL(sesion),
            familias=RepositorioFamiliasSQL(sesion),
            cargas=cargas,
        )
    if tipo is TipoCarga.CATALOGO_CONCEPTOS:
        return AplicadorCPU(
            conceptos=RepositorioConceptosSQL(sesion),
            insumos=RepositorioInsumosSQL(sesion),
            unidades=RepositorioUnidadesSQL(sesion),
            familias=RepositorioFamiliasSQL(sesion),
            cargas=cargas,
        )
    if tipo is TipoCarga.PROTOTIPOS:
        return AplicadorPrototipos(
            prototipos=RepositorioPrototiposSQL(sesion),
            proyectos=RepositorioProyectosSQL(sesion),
        )
    if tipo is TipoCarga.PRESUPUESTO:
        return AplicadorPresupuesto(
            conceptos=RepositorioConceptosSQL(sesion),
            insumos=RepositorioInsumosSQL(sesion),
            unidades=RepositorioUnidadesSQL(sesion),
            prototipos=RepositorioPrototiposSQL(sesion),
            prototipo_nodos=RepositorioPrototipoNodoSQL(sesion),
            niveles_etapas=RepositorioNivelesEtapasSQL(sesion),
            presupuestos=RepositorioPresupuestosSQL(sesion),
            cargas=cargas,
        )
    return AplicadorAlmacen(
        materiales=RepositorioMaterialesSQL(sesion),
        insumos=RepositorioInsumosSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        contratistas=RepositorioContratistasSQL(sesion),
        conceptos=RepositorioConceptosSQL(sesion),
        familias=RepositorioFamiliasSQL(sesion),
        cargas=cargas,
        tasa_iva=Decimal("0.16"),
    )


async def _cargar(
    contexto: ContextoSesion,
    tipo: TipoCarga,
    contenido: bytes,
    *,
    modo: ModoCarga = ModoCarga.ACTUALIZAR,
    dry_run: bool = False,
    nombre: str = "prueba.xlsx",
) -> ResultadoCarga:
    async with sesion_con_rls(contexto) as sesion:
        caso_uso = EjecutarCarga(
            cargas=RepositorioCargasSQL(sesion),
            lector=cargador_para(tipo),
            aplicador=_aplicador(tipo, sesion),
            uow=UnidadDeTrabajoSQL(sesion),
        )
        return await caso_uso.ejecutar(
            ComandoEjecutarCarga(
                tipo=tipo,
                contenido=contenido,
                archivo_nombre=nombre,
                usuario_id=contexto.usuario_id,
                modo=modo,
                dry_run=dry_run,
            )
        )


async def _insumos(contexto: ContextoSesion) -> dict[str, dict]:
    async with sesion_con_rls(contexto) as sesion:
        filas = await RepositorioInsumosSQL(sesion).listar(solo_activos=False)
    return {str(f["clave"]): f for f in filas}


async def _prototipos(contexto: ContextoSesion) -> dict[str, dict]:
    async with sesion_con_rls(contexto) as sesion:
        filas = await RepositorioPrototiposSQL(sesion).listar()
    return {str(f["clave"]): f for f in filas}


async def _conceptos(contexto: ContextoSesion) -> dict[str, dict]:
    async with sesion_con_rls(contexto) as sesion:
        filas = await RepositorioConceptosSQL(sesion).listar(solo_activos=False)
    return {str(f["clave"]): f for f in filas}


async def _nodos_de(contexto: ContextoSesion, prototipo_id: uuid.UUID) -> dict[str, dict]:
    async with sesion_con_rls(contexto) as sesion:
        filas = await RepositorioPrototipoNodoSQL(sesion).por_prototipo(prototipo_id)
    return {str(f["clave"]): f for f in filas if f["clave"]}


# --- Materiales (§10.6 `CABECERAS_MATERIALES.xlsx`) ----------------------


async def test_carga_de_materiales_alimenta_el_catalogo_de_insumos(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """Un material es un `Insumo` con `tipo='material'` (§7.3)."""
    resultado = await _cargar(
        contexto_control,
        TipoCarga.MATERIALES,
        _archivo_materiales(
            [
                ["CEM-01", "Cemento gris", "ton", "CEM", "250.5", "260", "SI"],
                ["ARE-01", "Arena de río", "ton", "CEM", "100", "", "NO"],
            ]
        ),
    )

    assert resultado.estatus is EstatusCarga.APLICADO
    assert resultado.resumen.insertados == 2
    assert resultado.resumen.errores == 0
    assert resultado.version_generada == 1  # §10.8: cada carga es una versión

    catalogo = await _insumos(contexto_control)
    assert catalogo["CEM-01"]["descripcion"] == "Cemento gris"
    assert catalogo["CEM-01"]["costo_base"] == Decimal("250.5000")
    # §10.5: costo_base_actualizado = el costo último más reciente.
    assert catalogo["CEM-01"]["costo_base_actualizado"] == Decimal("260.0000")
    assert catalogo["CEM-01"]["unidad_id"] == catalogos.unidad_id
    assert catalogo["CEM-01"]["familia_id"] == catalogos.familia_id
    assert catalogo["ARE-01"]["iva_aplica"] is False


async def test_el_mismo_archivo_no_se_aplica_dos_veces(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """§10.8/§12.3: "si es idéntico, no crea versión"."""
    contenido = _archivo_materiales([["CEM-01", "Cemento gris", "ton", "CEM", "250", "", "SI"]])
    primera = await _cargar(contexto_control, TipoCarga.MATERIALES, contenido)
    segunda = await _cargar(contexto_control, TipoCarga.MATERIALES, contenido)

    assert primera.reutilizada is False
    assert segunda.reutilizada is True
    assert segunda.carga_id == primera.carga_id
    assert segunda.version_generada == primera.version_generada
    assert len(await _insumos(contexto_control)) == 1


async def test_un_archivo_distinto_sin_cambios_reales_tampoco_versiona(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """El §10.8 compara **contenido**, no bytes: 250 y 250.00 son lo mismo."""
    await _cargar(
        contexto_control,
        TipoCarga.MATERIALES,
        _archivo_materiales([["CEM-01", "Cemento gris", "ton", "CEM", "250", "", "SI"]]),
    )
    segunda = await _cargar(
        contexto_control,
        TipoCarga.MATERIALES,
        # Mismo dato, otro archivo: cambia el hash pero no el catálogo.
        _archivo_materiales([["CEM-01", "Cemento gris", "ton", "CEM", "250.00", "", "SI"]]),
    )

    assert segunda.reutilizada is False
    assert segunda.version_generada is None
    assert segunda.resumen.omitidos == 1


async def test_un_precio_que_cambia_genera_la_version_siguiente(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """El ejemplo del §10.8: v1, luego v2 con el diff de lo que cambió."""
    await _cargar(
        contexto_control,
        TipoCarga.MATERIALES,
        _archivo_materiales([["CEM-01", "Cemento gris", "ton", "CEM", "250", "", "SI"]]),
    )
    segunda = await _cargar(
        contexto_control,
        TipoCarga.MATERIALES,
        _archivo_materiales(
            [
                ["CEM-01", "Cemento gris", "ton", "CEM", "270", "", "SI"],
                ["GRA-01", "Grava", "ton", "CEM", "80", "", "SI"],
            ]
        ),
    )

    assert segunda.version_generada == 2
    assert segunda.resumen.insertados == 1
    assert segunda.resumen.actualizados == 1
    assert segunda.diff["cambios"] == {"CEM-01": ["costo_base"]}
    catalogo = await _insumos(contexto_control)
    assert catalogo["CEM-01"]["costo_base"] == Decimal("270.0000")


async def test_una_fila_mala_se_reporta_y_el_resto_del_archivo_entra(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """§9.3: reporte de errores por fila/columna, sin abortar el archivo."""
    resultado = await _cargar(
        contexto_control,
        TipoCarga.MATERIALES,
        _archivo_materiales(
            [
                ["CEM-01", "Cemento gris", "ton", "CEM", "250", "", "SI"],
                ["", "Sin clave", "ton", "CEM", "10", "", "SI"],
                ["ARE-01", "Arena", "ton", "CEM", "no es número", "", "SI"],
                ["GRA-01", "Grava", "ton", "CEM", "80", "", "SI"],
            ]
        ),
    )

    assert resultado.resumen.insertados == 2
    assert resultado.resumen.errores == 2
    assert {(e.fila, e.columna) for e in resultado.errores} == {(3, "clave"), (4, "costo_base")}
    assert set(await _insumos(contexto_control)) == {"CEM-01", "GRA-01"}


async def test_una_unidad_desconocida_cae_en_la_bandeja_y_no_se_inventa(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """§10.3: el sistema propone, el humano confirma."""
    resultado = await _cargar(
        contexto_control,
        TipoCarga.MATERIALES,
        _archivo_materiales([["CEM-01", "Cemento gris", "sacos", "CEM", "250", "", "SI"]]),
    )

    assert resultado.pendientes == 1
    async with sesion_con_rls(contexto_control) as sesion:
        bandeja = await RepositorioCargasSQL(sesion).listar_pendientes(
            carga_id=resultado.carga_id
        )
    assert bandeja[0]["tipo"] == str(TipoPendiente.UNIDAD)
    assert bandeja[0]["valor_origen"] == "sacos"
    # El material entra igual, pero sin unidad adivinada.
    assert (await _insumos(contexto_control))["CEM-01"]["unidad_id"] is None


async def test_la_vista_previa_cuenta_igual_pero_no_escribe(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """§9.3: el dry-run tiene que dar los mismos números que el commit."""
    contenido = _archivo_materiales(
        [["CEM-01", "Cemento gris", "ton", "CEM", "250", "", "SI"]]
    )
    previa = await _cargar(contexto_control, TipoCarga.MATERIALES, contenido, dry_run=True)

    assert previa.estatus is EstatusCarga.PREVISUALIZADO
    assert previa.resumen.insertados == 1
    assert previa.version_generada is None
    assert await _insumos(contexto_control) == {}

    aplicada = await _cargar(contexto_control, TipoCarga.MATERIALES, contenido)
    assert aplicada.resumen.insertados == previa.resumen.insertados


async def test_reemplazar_da_de_baja_lo_que_el_archivo_ya_no_trae(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """§10.2. La baja es lógica: `explosion` y `salida_almacen` apuntan aquí."""
    await _cargar(
        contexto_control,
        TipoCarga.MATERIALES,
        _archivo_materiales(
            [
                ["CEM-01", "Cemento gris", "ton", "CEM", "250", "", "SI"],
                ["ARE-01", "Arena", "ton", "CEM", "100", "", "SI"],
            ]
        ),
    )
    await _cargar(
        contexto_control,
        TipoCarga.MATERIALES,
        _archivo_materiales([["CEM-01", "Cemento gris", "ton", "CEM", "250", "", "SI"]]),
        modo=ModoCarga.REEMPLAZAR,
    )

    catalogo = await _insumos(contexto_control)
    assert catalogo["CEM-01"]["estatus"] == "activo"
    assert catalogo["ARE-01"]["estatus"] == "inactivo"


async def test_revertir_deja_el_catalogo_como_estaba_antes_del_lote(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """§10.8: se revierte el **lote**, no registro por registro."""
    await _cargar(
        contexto_control,
        TipoCarga.MATERIALES,
        _archivo_materiales([["CEM-01", "Cemento gris", "ton", "CEM", "250", "", "SI"]]),
    )
    segunda = await _cargar(
        contexto_control,
        TipoCarga.MATERIALES,
        _archivo_materiales(
            [
                ["CEM-01", "Cemento gris", "ton", "CEM", "270", "", "SI"],
                ["GRA-01", "Grava", "ton", "CEM", "80", "", "SI"],
            ]
        ),
    )

    async with sesion_con_rls(contexto_control) as sesion:
        reversa = await RevertirCarga(
            cargas=RepositorioCargasSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        ).ejecutar(segunda.carga_id, usuario_id=contexto_control.usuario_id)

    assert reversa["operaciones_revertidas"] == 2
    catalogo = await _insumos(contexto_control)
    assert set(catalogo) == {"CEM-01"}  # la alta del lote se fue
    assert catalogo["CEM-01"]["costo_base"] == Decimal("250.0000")  # el precio volvió


async def test_una_carga_revertida_no_se_revierte_dos_veces(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    from obractrl.application.casos_uso.gestionar_carga import CargaNoRevertible

    resultado = await _cargar(
        contexto_control,
        TipoCarga.MATERIALES,
        _archivo_materiales([["CEM-01", "Cemento gris", "ton", "CEM", "250", "", "SI"]]),
    )
    async with sesion_con_rls(contexto_control) as sesion:
        await RevertirCarga(
            cargas=RepositorioCargasSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        ).ejecutar(resultado.carga_id)

    async with sesion_con_rls(contexto_control) as sesion:
        with pytest.raises(CargaNoRevertible, match="ya se revirtió"):
            await RevertirCarga(
                cargas=RepositorioCargasSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
            ).ejecutar(resultado.carga_id)


async def test_un_archivo_sin_las_cabeceras_del_contrato_se_rechaza_entero(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """§10.6 es el contrato: sin clave no hay nada que validar fila a fila."""
    with pytest.raises(ErrorDeCabecera, match="clave"):
        await _cargar(
            contexto_control,
            TipoCarga.MATERIALES,
            _libro([["Columna A", "Columna B"], ["x", "y"]]),
        )


# --- CPU / Conceptos (§10.6 `CABECERAS_CPU.xlsx`) ------------------------


async def _sembrar_insumos(contexto: ContextoSesion) -> None:
    await _cargar(
        contexto,
        TipoCarga.MATERIALES,
        _archivo_materiales(
            [
                ["MAT-01", "Block de concreto", "ton", "CEM", "20", "", "SI"],
                ["MOA-01", "Albañil", "ton", "CEM", "300", "", "NO"],
            ]
        ),
    )


async def test_carga_de_cpu_crea_concepto_explosion_y_version(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """§10.6 formato plano; §7.3 el CPU **se calcula** de la explosión."""
    await _sembrar_insumos(contexto_control)

    resultado = await _cargar(
        contexto_control,
        TipoCarga.CATALOGO_CONCEPTOS,
        _archivo_cpu(
            [
                _fila_cpu("EST-01", "EST-01", "Muro de block", "ton", tipo="Concepto"),
                _fila_cpu(insumo="MAT-01", descripcion="Block", cantidad="12.5", pu="20", tipo="Material"),
                _fila_cpu(insumo="MOA-01", descripcion="Albañil", cantidad="0.8", pu="300", tipo="Mano de obra"),
            ]
        ),
    )

    assert resultado.resumen.insertados == 1
    assert resultado.resumen.errores == 0

    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioConceptosSQL(sesion)
        concepto = next(c for c in await repo.listar() if str(c["clave"]) == "EST-01")
        versiones = await repo.versiones_cpu(concepto["id"])
        explosion = await repo.explosion_directa(concepto["id"])

    assert len(versiones) == 1
    assert versiones[0]["version"] == 1 and versiones[0]["vigente"] is True
    # 12.5 × 20 = 250 (material) + 0.8 × 300 = 240 (destajo) → 490 total.
    assert versiones[0]["precio_unitario"] == Decimal("490.0000")
    assert versiones[0]["precio_destajo"] == Decimal("240.0000")
    assert len(explosion) == 2
    # §10.6 da una sola columna E: `cantidad` y `rendimiento` reciben lo mismo.
    assert explosion[0]["cantidad"] == explosion[0]["rendimiento"] == Decimal("12.500000")


async def test_un_insumo_desconocido_detiene_el_concepto_y_abre_pendiente_critico(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """Un APU con un hueco publicaría un precio menor al real (§7.3)."""
    await _sembrar_insumos(contexto_control)

    resultado = await _cargar(
        contexto_control,
        TipoCarga.CATALOGO_CONCEPTOS,
        _archivo_cpu(
            [
                _fila_cpu("EST-01", "EST-01", "Muro de block", "ton", tipo="Concepto"),
                _fila_cpu(insumo="MAT-01", cantidad="12.5", pu="20", tipo="Material"),
                _fila_cpu(insumo="NO-EXISTE", cantidad="1", pu="10", tipo="Material"),
            ]
        ),
    )

    assert resultado.resumen.insertados == 0
    assert resultado.pendientes == 1

    async with sesion_con_rls(contexto_control) as sesion:
        bandeja = await RepositorioCargasSQL(sesion).listar_pendientes(
            carga_id=resultado.carga_id
        )
        conceptos = await RepositorioConceptosSQL(sesion).listar()

    assert bandeja[0]["tipo"] == str(TipoPendiente.MAPEO_NO_RECONOCIDO)
    assert bandeja[0]["entidad"] == "insumo"
    assert bandeja[0]["critico"] is True
    assert [c for c in conceptos if str(c["clave"]) == "EST-01"] == []


async def test_recargar_el_cpu_con_otra_receta_publica_version_2_y_se_revierte(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """§10.8: la anterior queda en el historial y el lote se deshace entero."""
    await _sembrar_insumos(contexto_control)
    await _cargar(
        contexto_control,
        TipoCarga.CATALOGO_CONCEPTOS,
        _archivo_cpu(
            [
                _fila_cpu("EST-01", "EST-01", "Muro de block", "ton", tipo="Concepto"),
                _fila_cpu(insumo="MAT-01", cantidad="12.5", pu="20", tipo="Material"),
            ]
        ),
    )
    segunda = await _cargar(
        contexto_control,
        TipoCarga.CATALOGO_CONCEPTOS,
        _archivo_cpu(
            [
                _fila_cpu("EST-01", "EST-01", "Muro de block", "ton", tipo="Concepto"),
                _fila_cpu(insumo="MAT-01", cantidad="14", pu="20", tipo="Material"),
            ]
        ),
    )

    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioConceptosSQL(sesion)
        concepto = next(c for c in await repo.listar() if str(c["clave"]) == "EST-01")
        versiones = await repo.versiones_cpu(concepto["id"])

    assert [v["version"] for v in versiones] == [1, 2]
    assert [v["vigente"] for v in versiones] == [False, True]
    assert versiones[1]["precio_unitario"] == Decimal("280.0000")  # 14 × 20

    async with sesion_con_rls(contexto_control) as sesion:
        await RevertirCarga(
            cargas=RepositorioCargasSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        ).ejecutar(segunda.carga_id)

    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioConceptosSQL(sesion)
        versiones = await repo.versiones_cpu(concepto["id"])
        explosion = await repo.explosion_directa(concepto["id"])

    assert [(v["version"], v["vigente"]) for v in versiones] == [(1, True)]
    assert len(explosion) == 1
    assert explosion[0]["cantidad"] == Decimal("12.500000")


# --- Movimientos de almacén (§10.6 `IMPORTAADOR_ALMACEN.xlsx`) -----------


def _fila_almacen(
    *,
    parte: str = "CEM-01",
    ubicacion: str = "OBRA",
    lote: str = "01",
    motivo: str = "Salida para producción",
    qty: object = "-10",
    costo: object = "-2500",
    ultimo: object = "250",
) -> list[object]:
    return [
        parte, "Cemento gris", "CEM", ubicacion, lote, "Constructora X",
        date(2026, 8, 10), motivo, qty, costo, ultimo, "248",
        "No.Parte:EST-0123 OP-99", "1", "Central", "jperez",
    ]


async def test_carga_de_almacen_registra_movimientos_y_baja_la_valuacion(
    catalogos: Catalogos, escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """§10.5: el signo viene del archivo y `C/Último` es el costo del cruce."""
    await _cargar(
        contexto_control,
        TipoCarga.MATERIALES,
        _archivo_materiales([["CEM-01", "Cemento gris", "ton", "CEM", "200", "", "SI"]]),
    )

    resultado = await _cargar(
        contexto_control, TipoCarga.ALMACEN, _archivo_almacen([_fila_almacen()])
    )

    assert resultado.resumen.insertados == 1
    assert resultado.resumen.errores == 0

    async with sesion_con_rls(contexto_control) as sesion:
        salidas = await RepositorioMaterialesSQL(sesion).listar_salidas(
            obra_id=escenario.obra_id
        )
    assert len(salidas) == 1
    assert salidas[0]["cantidad"] == Decimal("-10.000000")
    assert salidas[0]["costo"] == Decimal("-2500.0000")
    assert salidas[0]["costo_ultimo"] == Decimal("250.0000")
    assert salidas[0]["motivo_id"] == catalogos.motivo_id

    catalogo = await _insumos(contexto_control)
    assert catalogo["CEM-01"]["costo_ultimo"] == Decimal("250.0000")
    assert catalogo["CEM-01"]["costo_base_actualizado"] == Decimal("250.0000")
    assert catalogo["CEM-01"]["origen"] == "almacen"


async def test_el_importe_con_iva_se_calcula_desde_el_costo_sin_iva(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """§10.6: "los costos vienen sin IVA y se agrega 16% según `Clase`"."""
    await _cargar(
        contexto_control,
        TipoCarga.MATERIALES,
        _archivo_materiales([["CEM-01", "Cemento gris", "ton", "CEM", "200", "", ""]]),
    )
    resultado = await _cargar(
        contexto_control, TipoCarga.ALMACEN, _archivo_almacen([_fila_almacen()])
    )

    async with sesion_con_rls(contexto_control) as sesion:
        carga = await RepositorioCargasSQL(sesion).obtener(resultado.carga_id)
    assert carga is not None
    assert carga["resumen"]["importe_con_iva"] == "-2900.0000"
    assert carga["resumen"]["tasa_iva"] == "0.16"


async def test_un_motivo_no_catalogado_va_a_la_bandeja_y_no_se_inventa(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """§10.5: "Motivo no catalogado -> bandeja de pendientes"."""
    await _cargar(
        contexto_control,
        TipoCarga.MATERIALES,
        _archivo_materiales([["CEM-01", "Cemento gris", "ton", "CEM", "200", "", "SI"]]),
    )
    resultado = await _cargar(
        contexto_control,
        TipoCarga.ALMACEN,
        _archivo_almacen([_fila_almacen(motivo="Merma por lluvia")]),
    )

    assert resultado.resumen.insertados == 0
    assert resultado.resumen.omitidos == 1

    async with sesion_con_rls(contexto_control) as sesion:
        bandeja = await RepositorioCargasSQL(sesion).listar_pendientes(
            carga_id=resultado.carga_id
        )
    assert bandeja[0]["tipo"] == str(TipoPendiente.MOTIVO_ALMACEN)
    assert bandeja[0]["valor_origen"] == "Merma por lluvia"
    assert bandeja[0]["critico"] is True


async def test_un_signo_que_contradice_al_motivo_es_error_de_fila(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """Misma regla que la captura manual (`domain.materiales.reglas`, §10.5)."""
    await _cargar(
        contexto_control,
        TipoCarga.MATERIALES,
        _archivo_materiales([["CEM-01", "Cemento gris", "ton", "CEM", "200", "", "SI"]]),
    )
    resultado = await _cargar(
        contexto_control,
        TipoCarga.ALMACEN,
        _archivo_almacen([_fila_almacen(qty="10", costo="2500")]),
    )

    assert resultado.resumen.insertados == 0
    assert resultado.resumen.errores == 1
    assert resultado.errores[0].columna == "cantidad"


async def test_una_obra_que_no_existe_no_carga_el_movimiento(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """§10.3: sin cruce de obra el movimiento va a la bandeja, no a la basura."""
    await _cargar(
        contexto_control,
        TipoCarga.MATERIALES,
        _archivo_materiales([["CEM-01", "Cemento gris", "ton", "CEM", "200", "", "SI"]]),
    )
    resultado = await _cargar(
        contexto_control,
        TipoCarga.ALMACEN,
        _archivo_almacen([_fila_almacen(ubicacion="ENCINO", lote="99")]),
    )

    assert resultado.resumen.insertados == 0
    async with sesion_con_rls(contexto_control) as sesion:
        bandeja = await RepositorioCargasSQL(sesion).listar_pendientes(
            carga_id=resultado.carga_id
        )
    assert bandeja[0]["entidad"] == "obra"
    assert bandeja[0]["valor_origen"] == "ENCINO 99"


async def test_revertir_una_carga_de_almacen_borra_sus_movimientos(
    catalogos: Catalogos, escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """§10.8: el lote se revierte como unidad, valuación incluida."""
    await _cargar(
        contexto_control,
        TipoCarga.MATERIALES,
        _archivo_materiales([["CEM-01", "Cemento gris", "ton", "CEM", "200", "", "SI"]]),
    )
    carga = await _cargar(
        contexto_control, TipoCarga.ALMACEN, _archivo_almacen([_fila_almacen()])
    )

    async with sesion_con_rls(contexto_control) as sesion:
        await RevertirCarga(
            cargas=RepositorioCargasSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        ).ejecutar(carga.carga_id)

    async with sesion_con_rls(contexto_control) as sesion:
        salidas = await RepositorioMaterialesSQL(sesion).listar_salidas(
            obra_id=escenario.obra_id
        )
    assert salidas == []
    catalogo = await _insumos(contexto_control)
    assert catalogo["CEM-01"]["costo_ultimo"] is None
    assert catalogo["CEM-01"]["origen"] == "base"


# --- Prototipos (extensión propia, no está en el §10.6) -------------------
#
# `escenario` ya siembra un proyecto clave `PROY` y un prototipo `CAS-1`
# (§7.2) — se reusan aquí en vez de crear otros, igual que `catalogos` reusa
# lo mínimo para materiales/almacén.


async def test_carga_de_prototipos_alimenta_y_actualiza_el_catalogo(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    resultado = await _cargar(
        contexto_control,
        TipoCarga.PROTOTIPOS,
        _archivo_prototipos(
            [
                ["PROY", "CAS-1", "Casa modelo A editada", "90", "2", "3"],
                ["PROY", "CAS-2", "Casa modelo B", "75", "1", "2"],
            ]
        ),
    )

    assert resultado.estatus is EstatusCarga.APLICADO
    assert resultado.resumen.insertados == 1
    assert resultado.resumen.actualizados == 1
    assert resultado.resumen.errores == 0

    catalogo = await _prototipos(contexto_control)
    assert catalogo["CAS-1"]["nombre"] == "Casa modelo A editada"
    assert catalogo["CAS-1"]["m2"] == Decimal("90.00")
    assert catalogo["CAS-1"]["proyecto_id"] == escenario.proyecto_id  # no se reasigna
    assert catalogo["CAS-2"]["proyecto_id"] == escenario.proyecto_id
    assert catalogo["CAS-2"]["niveles"] == 1


async def test_el_mismo_archivo_de_prototipos_no_se_aplica_dos_veces(
    contexto_control: ContextoSesion,
) -> None:
    contenido = _archivo_prototipos([["PROY", "CAS-2", "Casa modelo B", "", "", ""]])
    primera = await _cargar(contexto_control, TipoCarga.PROTOTIPOS, contenido)
    segunda = await _cargar(contexto_control, TipoCarga.PROTOTIPOS, contenido)

    assert primera.reutilizada is False
    assert segunda.reutilizada is True
    assert len(await _prototipos(contexto_control)) == 2  # CAS-1 (escenario) + CAS-2


async def test_la_vista_previa_de_prototipos_cuenta_igual_pero_no_escribe(
    contexto_control: ContextoSesion,
) -> None:
    """§9.3: el dry-run tiene que dar los mismos números que el commit —

    incluido un error de **dominio** (niveles inválidos), que solo se
    detecta al construir `Prototipo.crear()` y no en la validación de fila.
    """
    contenido = _archivo_prototipos([["PROY", "CAS-9", "Casa sin niveles", "", "0", ""]])
    previa = await _cargar(contexto_control, TipoCarga.PROTOTIPOS, contenido, dry_run=True)

    assert previa.estatus is EstatusCarga.PREVISUALIZADO
    assert previa.resumen.insertados == 0
    assert previa.resumen.errores == 1
    assert "CAS-9" not in await _prototipos(contexto_control)

    aplicada = await _cargar(contexto_control, TipoCarga.PROTOTIPOS, contenido)
    assert aplicada.resumen.insertados == previa.resumen.insertados
    assert aplicada.resumen.errores == previa.resumen.errores
    assert "CAS-9" not in await _prototipos(contexto_control)


async def test_un_proyecto_que_no_existe_es_error_de_fila_y_el_resto_entra(
    contexto_control: ContextoSesion,
) -> None:
    resultado = await _cargar(
        contexto_control,
        TipoCarga.PROTOTIPOS,
        _archivo_prototipos(
            [
                ["NOPE", "CAS-9", "Casa fantasma", "", "", ""],
                ["PROY", "CAS-4", "Casa real", "", "", ""],
            ]
        ),
    )

    assert resultado.resumen.insertados == 1
    assert resultado.resumen.errores == 1
    assert {(e.fila, e.columna) for e in resultado.errores} == {(2, "proyecto_clave")}
    catalogo = await _prototipos(contexto_control)
    assert "CAS-9" not in catalogo
    assert "CAS-4" in catalogo


async def test_prototipos_no_soporta_el_modo_reemplazar(
    contexto_control: ContextoSesion,
) -> None:
    """`prototipo` no tiene `estatus`: no hay baja lógica que ejecutar."""
    with pytest.raises(ErrorDeProyecto, match="Reemplazar"):
        await _cargar(
            contexto_control,
            TipoCarga.PROTOTIPOS,
            _archivo_prototipos([["PROY", "CAS-2", "Casa modelo B", "", "", ""]]),
            modo=ModoCarga.REEMPLAZAR,
        )
    assert "CAS-2" not in await _prototipos(contexto_control)


async def test_revertir_un_lote_de_prototipos_deshace_altas_y_cambios(
    contexto_control: ContextoSesion,
) -> None:
    await _cargar(
        contexto_control,
        TipoCarga.PROTOTIPOS,
        _archivo_prototipos([["PROY", "CAS-5", "Casa modelo E", "", "", ""]]),
    )
    segunda = await _cargar(
        contexto_control,
        TipoCarga.PROTOTIPOS,
        _archivo_prototipos(
            [
                ["PROY", "CAS-5", "Casa modelo E renombrada", "", "", ""],
                ["PROY", "CAS-6", "Casa modelo F", "", "", ""],
            ]
        ),
    )

    async with sesion_con_rls(contexto_control) as sesion:
        reversa = await RevertirCarga(
            cargas=RepositorioCargasSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        ).ejecutar(segunda.carga_id, usuario_id=contexto_control.usuario_id)

    assert reversa["operaciones_revertidas"] == 2
    catalogo = await _prototipos(contexto_control)
    assert "CAS-6" not in catalogo  # la alta del lote se fue
    assert catalogo["CAS-5"]["nombre"] == "Casa modelo E"  # el nombre volvió


# --- Presupuesto jerárquico (extensión propia, no está en el §10.6) -------
#
# `escenario` ya siembra un proyecto clave `PROY` (§7.2) — se reusa aquí
# para dar de alta los prototipos que cada test necesita antes de cargar su
# ingeniería, igual que en producción: primero Prototipos, después el
# desglose. `ACE-01` (el insumo de todos los conceptos de prueba) se carga
# una vez por materiales, no se siembra a mano — es el camino real.


async def _con_insumo_alambre(contexto_control: ContextoSesion) -> None:
    await _cargar(
        contexto_control,
        TipoCarga.MATERIALES,
        _archivo_materiales([["ACE-01", "Alambre recocido", "KG", "CEM", "1", "", "SI"]]),
    )


async def _con_prototipos(contexto_control: ContextoSesion, *claves: str) -> None:
    await _cargar(
        contexto_control,
        TipoCarga.PROTOTIPOS,
        _archivo_prototipos([["PROY", clave, f"Casa {clave}", "", "", ""] for clave in claves]),
    )


async def test_dos_prototipos_comparten_concepto_con_misma_composicion(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """Sin conflicto: el catálogo se publica una vez y las dos partidas
    comparten el mismo precio calculado."""
    await _con_insumo_alambre(contexto_control)
    await _con_prototipos(contexto_control, "CAS-10", "CAS-11")

    resultado = await _cargar(
        contexto_control,
        TipoCarga.PRESUPUESTO,
        _archivo_presupuesto(
            [
                *_prototipo_simple("CAS-10", "EST-01", 5),
                *_prototipo_simple("CAS-11", "EST-01", 5),
            ]
        ),
    )

    assert resultado.estatus is EstatusCarga.APLICADO
    assert resultado.resumen.errores == 0
    assert resultado.pendientes == 0

    conceptos = await _conceptos(contexto_control)
    assert set(conceptos) == {"EST-01"}

    async with sesion_con_rls(contexto_control) as sesion:
        cpu_versiones = await RepositorioConceptosSQL(sesion).versiones_cpu(conceptos["EST-01"]["id"])
    assert len(cpu_versiones) == 1  # solo se publicó una vez

    prototipos = await _prototipos(contexto_control)
    async with sesion_con_rls(contexto_control) as sesion:
        presupuestos = RepositorioPresupuestosSQL(sesion)
        p10 = await presupuestos.vigente_de_prototipo(prototipos["CAS-10"]["id"])
        p11 = await presupuestos.vigente_de_prototipo(prototipos["CAS-11"]["id"])
        partidas10 = await presupuestos.partidas(p10["id"])
        partidas11 = await presupuestos.partidas(p11["id"])

    assert len(partidas10) == 1 and len(partidas11) == 1
    assert partidas10[0]["precio_unitario"] == partidas11[0]["precio_unitario"]


async def test_composicion_distinta_genera_conflicto_y_no_toca_el_catalogo(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    await _con_insumo_alambre(contexto_control)
    await _con_prototipos(contexto_control, "CAS-20", "CAS-21")

    resultado = await _cargar(
        contexto_control,
        TipoCarga.PRESUPUESTO,
        _archivo_presupuesto(
            [
                *_prototipo_simple("CAS-20", "EST-02", 5),
                # Misma clave de concepto, cantidad distinta -> conflicto.
                *_prototipo_simple("CAS-21", "EST-02", 9),
            ]
        ),
    )

    assert resultado.resumen.errores == 0  # el conflicto es pendiente, no error

    async with sesion_con_rls(contexto_control) as sesion:
        bandeja = await RepositorioCargasSQL(sesion).listar_pendientes(carga_id=resultado.carga_id)
    en_conflicto = [b for b in bandeja if b["tipo"] == str(TipoPendiente.CONCEPTO_EN_CONFLICTO)]
    assert len(en_conflicto) == 1
    assert en_conflicto[0]["valor_origen"] == "EST-02"

    conceptos = await _conceptos(contexto_control)
    async with sesion_con_rls(contexto_control) as sesion:
        cpu_versiones = await RepositorioConceptosSQL(sesion).versiones_cpu(conceptos["EST-02"]["id"])
    assert len(cpu_versiones) == 1  # el catálogo se quedó con la composición del primero

    prototipos = await _prototipos(contexto_control)
    async with sesion_con_rls(contexto_control) as sesion:
        presupuestos = RepositorioPresupuestosSQL(sesion)
        p20 = await presupuestos.vigente_de_prototipo(prototipos["CAS-20"]["id"])
        p21 = await presupuestos.vigente_de_prototipo(prototipos["CAS-21"]["id"])
        partida20 = (await presupuestos.partidas(p20["id"]))[0]
        partida21 = (await presupuestos.partidas(p21["id"]))[0]

    # Cada prototipo usa el precio de SU propia composición, no el del
    # catálogo (que se quedó con la del primero).
    assert partida20["precio_unitario"] != partida21["precio_unitario"]


async def test_etapa_sin_concepto_intermedio_crea_concepto_con_su_clave(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    await _con_insumo_alambre(contexto_control)
    await _con_prototipos(contexto_control, "CAS-30")

    filas = [
        [1, None, "CAS-30", "Prototipo", None, None, None, None, "PROTOTIPO"],
        [1, "CAS-30", "NIV-1", "Cimentación", None, None, None, None, "NIVEL DE CONSTRUCCION"],
        [1, "NIV-1", "ECO-99", "Etapa simple", None, None, None, None, "ETAPA DE CONSTRUCCION"],
        [1, "ECO-99", "ACE-01", "Alambre", "KG", 3, 20, None, "MATERIAL"],
    ]
    resultado = await _cargar(contexto_control, TipoCarga.PRESUPUESTO, _archivo_presupuesto(filas))

    assert resultado.resumen.errores == 0
    conceptos = await _conceptos(contexto_control)
    assert "ECO-99" in conceptos


async def test_recargar_el_mismo_prototipo_conserva_los_ids_de_nodo(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    await _con_insumo_alambre(contexto_control)
    await _con_prototipos(contexto_control, "CAS-40")

    await _cargar(
        contexto_control,
        TipoCarga.PRESUPUESTO,
        _archivo_presupuesto(_prototipo_simple("CAS-40", "EST-04", 5)),
    )
    prototipos = await _prototipos(contexto_control)
    nodos_v1 = await _nodos_de(contexto_control, prototipos["CAS-40"]["id"])

    # Recarga con la misma clave de concepto, cantidad distinta (cambia el
    # catálogo, no la identidad del árbol).
    await _cargar(
        contexto_control,
        TipoCarga.PRESUPUESTO,
        _archivo_presupuesto(_prototipo_simple("CAS-40", "EST-04", 7)),
    )
    nodos_v2 = await _nodos_de(contexto_control, prototipos["CAS-40"]["id"])

    assert set(nodos_v1) == set(nodos_v2) == {"NIV-1", "ECO-1", "EST-04"}
    for clave in nodos_v1:
        assert nodos_v1[clave]["id"] == nodos_v2[clave]["id"]


async def test_prototipo_raiz_sin_match_es_error_critico_y_el_resto_sigue(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    await _con_insumo_alambre(contexto_control)
    await _con_prototipos(contexto_control, "CAS-50")

    resultado = await _cargar(
        contexto_control,
        TipoCarga.PRESUPUESTO,
        _archivo_presupuesto(
            [
                *_prototipo_simple("CAS-NOEXISTE", "EST-05", 5),
                *_prototipo_simple("CAS-50", "EST-06", 5),
            ]
        ),
    )

    assert resultado.resumen.errores == 1
    conceptos = await _conceptos(contexto_control)
    assert "EST-06" in conceptos
    assert "EST-05" not in conceptos


async def test_presupuesto_no_soporta_el_modo_reemplazar(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    await _con_insumo_alambre(contexto_control)
    await _con_prototipos(contexto_control, "CAS-60")

    with pytest.raises(ErrorDeProyecto, match="Reemplazar"):
        await _cargar(
            contexto_control,
            TipoCarga.PRESUPUESTO,
            _archivo_presupuesto(_prototipo_simple("CAS-60", "EST-07", 5)),
            modo=ModoCarga.REEMPLAZAR,
        )


async def test_revertir_una_carga_de_presupuesto_deshace_arbol_y_version(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    await _con_insumo_alambre(contexto_control)
    await _con_prototipos(contexto_control, "CAS-70")

    resultado = await _cargar(
        contexto_control,
        TipoCarga.PRESUPUESTO,
        _archivo_presupuesto(_prototipo_simple("CAS-70", "EST-08", 5)),
    )
    prototipos = await _prototipos(contexto_control)
    assert (await _nodos_de(contexto_control, prototipos["CAS-70"]["id"])) != {}

    async with sesion_con_rls(contexto_control) as sesion:
        await RevertirCarga(
            cargas=RepositorioCargasSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        ).ejecutar(resultado.carga_id)

    nodos = await _nodos_de(contexto_control, prototipos["CAS-70"]["id"])
    assert nodos == {}
    conceptos = await _conceptos(contexto_control)
    assert "EST-08" not in conceptos

    async with sesion_con_rls(contexto_control) as sesion:
        vigente = await RepositorioPresupuestosSQL(sesion).vigente_de_prototipo(prototipos["CAS-70"]["id"])
    assert vigente is None
