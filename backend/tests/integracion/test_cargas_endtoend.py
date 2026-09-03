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
from obractrl.adapters.repos.cuadrillas_sql import RepositorioCuadrillasSQL
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
    AplicadorConceptosBase,
    AplicadorCPU,
    AplicadorCuadrillas,
    AplicadorDeCarga,
    AplicadorDePrototipos,
    AplicadorEtapasConstructivas,
    AplicadorFamilias,
    AplicadorManoObra,
    AplicadorMateriales,
    AplicadorNiveles,
    AplicadorPresupuesto,
    AplicadorPrototipos,
    AplicadorUnidades,
)
from obractrl.application.casos_uso.gestionar_carga import (
    CargaConDependientes,
    ComandoEjecutarCarga,
    EjecutarCarga,
    ResultadoCarga,
    RevertirCarga,
    RevertirCargaEnCadena,
)
from obractrl.domain.cargadores.cabeceras import ErrorDeCabecera
from obractrl.domain.cargadores.reporte import TipoPendiente
from obractrl.domain.proyectos.reglas import ErrorDeProyecto
from obractrl.domain.shared.diccionario import (
    EstatusCarga,
    ModoCarga,
    TipoCarga,
    TipoConcepto,
    TipoInsumo,
)
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


_CABECERAS_CONCEPTOS_BASE = ["Clave", "Descripción", "Unidad"]


def _archivo_conceptos_base(filas: list[list[object]]) -> bytes:
    return _libro([_CABECERAS_CONCEPTOS_BASE, *filas])


def _archivo_conceptos_auxiliares(filas: list[list[object]]) -> bytes:
    return _libro([_CABECERAS_CONCEPTOS_BASE, *filas])


_CABECERAS_NIVELES_ETAPAS = [
    "TIPO", "CLAVE", "DESCRIPCIÓN", "DESCRIPCIÓN CORTA", "UNIDAD", "CANTIDAD",
    "PRECIO UNITARIO", "TOTAL",
]
"""Cabeceras reales de `CATALOGO_DE_NIVELES.xlsx`/`CATALOGO_DE_ETAPAS_DE_
CONSTRUCCION.xlsx` — mismo archivo genérico de la herramienta de origen
para ambos catálogos; solo cambia el prefijo de la clave y el valor de TIPO."""


def _fila_nivel_etapa(tipo: str, clave: str, descripcion: str) -> list[object]:
    return [tipo, clave, descripcion, descripcion, None, 1, None, None]


def _archivo_niveles(filas: list[list[object]]) -> bytes:
    return _libro([_CABECERAS_NIVELES_ETAPAS, *filas])


def _archivo_etapas(filas: list[list[object]]) -> bytes:
    return _libro([_CABECERAS_NIVELES_ETAPAS, *filas])


_CABECERAS_UNIDADES = ["CLAVE UNIDAD", "UNIDAD", "SINONIMO"]
"""Cabeceras reales de `CATALOGO_DE_UNIDADES.xlsx`: "CLAVE UNIDAD" es el
consecutivo numérico del sistema de origen (se ignora), "UNIDAD" es la
clave del catálogo (KG/PZ/...) y "SINONIMO" es el nombre descriptivo
completo (Kilogramo/Pieza/...) — confirmado con el usuario."""


def _archivo_unidades(filas: list[list[object]]) -> bytes:
    return _libro([_CABECERAS_UNIDADES, *filas], hoja="Hoja1")


_CABECERAS_FAMILIAS = ["CLAVE", "FAMILIA", "PREFIJO"]
"""Cabeceras reales de `CATALOGO_DE_FAMILIAS.xlsx`: "PREFIJO" (ACA/ADH/...)
no tiene dónde vivir en `familia` hoy — se ignora, mismo criterio que "TIPO"
en niveles/etapas."""


def _archivo_familias(filas: list[list[object]]) -> bytes:
    return _libro([_CABECERAS_FAMILIAS, *filas], hoja="Hoja1")


_CABECERAS_MANO_OBRA = [
    "TIPO", "CLAVE USUARIO", "CLAVE", "DESCTRIPCIÓN", "CLAVE UNIDAD", "UNIDAD",
    "CUADRILLA", "RENDIMIENTO TEORICO", "RENDIMIENTO REAL", "COSTO UNITARIO", "FAMILIA",
]
"""§10.6, archivo real `CABECERAS_MANO_DE_OBRA.xlsx`, hoja `DESTAJOS`.
`DESCTRIPCIÓN` es el typo real del archivo, no del test."""


def _archivo_mano_obra(filas: list[list[object]]) -> bytes:
    return _libro([_CABECERAS_MANO_OBRA, *filas], hoja="DESTAJOS")


def _archivo_subcontratos(filas: list[list[object]]) -> bytes:
    """`catalogo_de_SUBCONTRATOS.xlsx`: mismas cabeceras que mano de obra,
    hoja propia (`SUBCONTRATOS`, no `DESTAJOS`)."""
    return _libro([_CABECERAS_MANO_OBRA, *filas], hoja="SUBCONTRATOS")


_CABECERAS_CUADRILLAS = [
    "Clave cuadrilla", "Clave", "Descripción", "Unidad", "Cantidad", "PU", "IMPORTE",
]
"""§10.6, archivo real `CABECERAS_CUADRILLAS.xlsx`: sin nombre de hoja fijo."""


def _archivo_cuadrillas(filas: list[list[object]]) -> bytes:
    return _libro([_CABECERAS_CUADRILLAS, *filas])


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


def _etapa_colapsada(
    clave_prototipo: str, clave_etapa: str, cantidad_alambre: object
) -> list[list[object]]:
    """Árbol mínimo con una etapa SIN concepto intermedio (`ECO-...` con
    material colgado directo): la otra forma real del archivo, que
    `_clave_catalogo_concepto` aísla por prototipo en el catálogo porque su
    clave se repite igual en cada uno pero la dosificación no."""
    return [
        [1, None, clave_prototipo, "Prototipo", None, None, None, None, "PROTOTIPO"],
        [1, clave_prototipo, "NIV-1", "Cimentación", None, None, None, None, "NIVEL DE CONSTRUCCION"],
        [1, "NIV-1", clave_etapa, "Etapa simple", None, None, None, None, "ETAPA DE CONSTRUCCION"],
        [1, clave_etapa, "ACE-01", "Alambre", "KG", cantidad_alambre, 20, None, "MATERIAL"],
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
    if tipo is TipoCarga.MANO_DE_OBRA:
        return AplicadorManoObra(
            insumos=RepositorioInsumosSQL(sesion),
            unidades=RepositorioUnidadesSQL(sesion),
            familias=RepositorioFamiliasSQL(sesion),
            cuadrillas=RepositorioCuadrillasSQL(sesion),
            cargas=cargas,
        )
    if tipo is TipoCarga.SUBCONTRATOS:
        return AplicadorManoObra(
            insumos=RepositorioInsumosSQL(sesion),
            unidades=RepositorioUnidadesSQL(sesion),
            familias=RepositorioFamiliasSQL(sesion),
            cuadrillas=RepositorioCuadrillasSQL(sesion),
            cargas=cargas,
            tipo=TipoInsumo.SUBCONTRATO,
        )
    if tipo is TipoCarga.CUADRILLAS:
        return AplicadorCuadrillas(
            cuadrillas=RepositorioCuadrillasSQL(sesion),
            insumos=RepositorioInsumosSQL(sesion),
            unidades=RepositorioUnidadesSQL(sesion),
            cargas=cargas,
        )
    if tipo is TipoCarga.CATALOGO_CONCEPTOS:
        return AplicadorConceptosBase(
            conceptos=RepositorioConceptosSQL(sesion),
            unidades=RepositorioUnidadesSQL(sesion),
            cargas=cargas,
        )
    if tipo is TipoCarga.CONCEPTOS_AUXILIARES:
        return AplicadorConceptosBase(
            conceptos=RepositorioConceptosSQL(sesion),
            unidades=RepositorioUnidadesSQL(sesion),
            cargas=cargas,
            tipo=TipoConcepto.AUXILIAR,
            prefijo_clave="AUX",
        )
    if tipo is TipoCarga.NIVELES:
        return AplicadorNiveles(niveles_etapas=RepositorioNivelesEtapasSQL(sesion))
    if tipo is TipoCarga.ETAPAS_CONSTRUCTIVAS:
        return AplicadorEtapasConstructivas(niveles_etapas=RepositorioNivelesEtapasSQL(sesion))
    if tipo is TipoCarga.UNIDADES:
        return AplicadorUnidades(unidades=RepositorioUnidadesSQL(sesion), cargas=cargas)
    if tipo is TipoCarga.FAMILIAS:
        return AplicadorFamilias(familias=RepositorioFamiliasSQL(sesion), cargas=cargas)
    if tipo is TipoCarga.CPU:
        return AplicadorCPU(
            conceptos=RepositorioConceptosSQL(sesion),
            insumos=RepositorioInsumosSQL(sesion),
            unidades=RepositorioUnidadesSQL(sesion),
            familias=RepositorioFamiliasSQL(sesion),
            cargas=cargas,
        )
    if tipo in (TipoCarga.PROTOTIPOS, TipoCarga.PRESUPUESTO):
        return AplicadorDePrototipos(
            plano=AplicadorPrototipos(
                prototipos=RepositorioPrototiposSQL(sesion),
                proyectos=RepositorioProyectosSQL(sesion),
            ),
            ingenieria=AplicadorPresupuesto(
                conceptos=RepositorioConceptosSQL(sesion),
                insumos=RepositorioInsumosSQL(sesion),
                unidades=RepositorioUnidadesSQL(sesion),
                prototipos=RepositorioPrototiposSQL(sesion),
                prototipo_nodos=RepositorioPrototipoNodoSQL(sesion),
                niveles_etapas=RepositorioNivelesEtapasSQL(sesion),
                presupuestos=RepositorioPresupuestosSQL(sesion),
                cargas=cargas,
            ),
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


async def _unidades(contexto: ContextoSesion) -> dict[str, dict]:
    async with sesion_con_rls(contexto) as sesion:
        filas = await RepositorioUnidadesSQL(sesion).listar(solo_activos=False)
    return {str(f["clave"]): f for f in filas}


async def _familias(contexto: ContextoSesion) -> dict[str, dict]:
    async with sesion_con_rls(contexto) as sesion:
        filas = await RepositorioFamiliasSQL(sesion).listar(solo_activos=False)
    return {str(f["clave"]): f for f in filas}


async def _cuadrillas(contexto: ContextoSesion) -> dict[str, dict]:
    async with sesion_con_rls(contexto) as sesion:
        filas = await RepositorioCuadrillasSQL(sesion).listar(solo_activos=False)
    return {str(f["clave"]): f for f in filas}


async def _prototipos(contexto: ContextoSesion) -> dict[str, dict]:
    async with sesion_con_rls(contexto) as sesion:
        filas = await RepositorioPrototiposSQL(sesion).listar()
    return {str(f["clave"]): f for f in filas}


async def _conceptos(contexto: ContextoSesion) -> dict[str, dict]:
    async with sesion_con_rls(contexto) as sesion:
        filas = await RepositorioConceptosSQL(sesion).listar(solo_activos=False)
    return {str(f["clave"]): f for f in filas}


async def _niveles(contexto: ContextoSesion) -> dict[str, dict]:
    async with sesion_con_rls(contexto) as sesion:
        filas = await RepositorioNivelesEtapasSQL(sesion).listar_niveles()
    return {str(f["clave"]): f for f in filas}


async def _etapas(contexto: ContextoSesion) -> dict[str, dict]:
    async with sesion_con_rls(contexto) as sesion:
        filas = await RepositorioNivelesEtapasSQL(sesion).listar_etapas()
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


async def test_una_unidad_desconocida_se_da_de_alta_en_vez_de_bloquear(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """Una unidad nueva no es el mismo riesgo que un concepto o un precio: se
    da de alta con el propio texto del archivo en vez de solo pendiente."""
    resultado = await _cargar(
        contexto_control,
        TipoCarga.MATERIALES,
        _archivo_materiales([["CEM-01", "Cemento gris", "sacos", "CEM", "250", "", "SI"]]),
    )

    assert resultado.pendientes == 0
    assert resultado.resumen.errores == 0

    unidades = await _unidades(contexto_control)
    assert "sacos" in unidades
    assert (await _insumos(contexto_control))["CEM-01"]["unidad_id"] == unidades["sacos"]["id"]


async def test_clave_unidad_del_archivo_se_vuelve_la_clave_del_catalogo(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """El archivo real trae "CLAVE UNIDAD" aparte de "UNIDAD" (§3.3): antes
    se ignoraba y la unidad quedaba con el texto libre como su propia clave.
    Ahora la clave del catálogo es la que trae el archivo, y "UNIDAD" es su
    nombre — no la misma cadena repetida dos veces."""
    resultado = await _cargar(
        contexto_control,
        TipoCarga.MATERIALES,
        _libro(
            [
                ["Clave", "Descripción", "Clave Unidad", "Unidad", "Clase", "Costo base"],
                ["VAR-01", "Varilla 3/8", "TON01", "Tonelada", "ACE", "20"],
            ]
        ),
    )
    assert resultado.resumen.errores == 0

    unidades = await _unidades(contexto_control)
    assert "TON01" in unidades
    assert unidades["TON01"]["nombre"] == "Tonelada"
    assert "Tonelada" not in unidades  # no se dio de alta con el nombre como clave
    assert (await _insumos(contexto_control))["VAR-01"]["unidad_id"] == unidades["TON01"]["id"]


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


async def test_eliminar_una_vista_previa_borra_su_registro(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """Una vista previa nunca escribió nada (§9.3): no hay riesgo en borrar
    su registro del historial."""
    from obractrl.application.casos_uso.gestionar_carga import EliminarCarga

    resultado = await _cargar(
        contexto_control,
        TipoCarga.MATERIALES,
        _archivo_materiales([["CEM-01", "Cemento gris", "ton", "CEM", "250", "", "SI"]]),
        dry_run=True,
    )

    async with sesion_con_rls(contexto_control) as sesion:
        await EliminarCarga(cargas=RepositorioCargasSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)).ejecutar(resultado.carga_id)

    async with sesion_con_rls(contexto_control) as sesion:
        assert await RepositorioCargasSQL(sesion).obtener(resultado.carga_id) is None
    assert await _insumos(contexto_control) == {}  # nunca se aplicó


async def test_no_se_puede_eliminar_una_carga_aplicada_sin_revertir(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """Borrar el snapshot sin deshacer los cambios dejaría el catálogo
    modificado sin ninguna forma de revertirlo."""
    from obractrl.application.casos_uso.gestionar_carga import (
        CargaNoEliminable,
        EliminarCarga,
    )

    resultado = await _cargar(
        contexto_control,
        TipoCarga.MATERIALES,
        _archivo_materiales([["CEM-01", "Cemento gris", "ton", "CEM", "250", "", "SI"]]),
    )

    async with sesion_con_rls(contexto_control) as sesion:
        with pytest.raises(CargaNoEliminable, match="revierte primero"):
            await EliminarCarga(cargas=RepositorioCargasSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)).ejecutar(
                resultado.carga_id
            )
    # Sigue ahí, y el material sigue en el catálogo.
    async with sesion_con_rls(contexto_control) as sesion:
        assert await RepositorioCargasSQL(sesion).obtener(resultado.carga_id) is not None
    assert "CEM-01" in await _insumos(contexto_control)


async def test_eliminar_una_carga_ya_revertida_borra_su_registro(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    from obractrl.application.casos_uso.gestionar_carga import EliminarCarga

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
        await EliminarCarga(cargas=RepositorioCargasSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)).ejecutar(resultado.carga_id)

    async with sesion_con_rls(contexto_control) as sesion:
        assert await RepositorioCargasSQL(sesion).obtener(resultado.carga_id) is None


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


# --- Catálogo base de conceptos (§8.7 `CABECERAS_CONCEPTOS.xlsx`) --------


async def test_carga_de_conceptos_base_crea_sin_tocar_cpu_ni_explosion(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """Identidad únicamente (§8.7): el catálogo de conceptos y CPU son
    cargadores separados — subir el primero no calcula nada del segundo."""
    resultado = await _cargar(
        contexto_control,
        TipoCarga.CATALOGO_CONCEPTOS,
        _archivo_conceptos_base([["EST-01", "Muro de block", "m2"]]),
    )
    assert resultado.resumen.insertados == 1
    assert resultado.resumen.errores == 0

    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioConceptosSQL(sesion)
        concepto = next(c for c in await repo.listar() if str(c["clave"]) == "EST-01")
        assert concepto["descripcion"] == "Muro de block"
        assert len(await repo.explosion_directa(concepto["id"])) == 0
        assert await repo.versiones_cpu(concepto["id"]) == []


async def test_recargar_conceptos_base_actualiza_descripcion_sin_pedir_unidad_de_nuevo(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """§3.4: lo que el archivo no trae, no se toca — una recarga sin columna
    de unidad no debe vaciar la que ya se dio de alta."""
    await _cargar(
        contexto_control,
        TipoCarga.CATALOGO_CONCEPTOS,
        _archivo_conceptos_base([["EST-01", "Muro de block", "m2"]]),
    )
    await _cargar(
        contexto_control,
        TipoCarga.CATALOGO_CONCEPTOS,
        _archivo_conceptos_base([["EST-01", "Muro de block hueco", ""]]),
    )

    conceptos = await _conceptos(contexto_control)
    assert conceptos["EST-01"]["descripcion"] == "Muro de block hueco"
    assert conceptos["EST-01"]["unidad_id"] is not None


async def test_concepto_base_sin_clave_se_numera_solo(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """El usuario pidió que un catálogo base sin indicador de clave se
    numere solo, prefijo del catálogo + consecutivo (§8.7, ej. FAM-00001)."""
    resultado = await _cargar(
        contexto_control,
        TipoCarga.CATALOGO_CONCEPTOS,
        _archivo_conceptos_base([["", "Trabe de cimentación", "ml"]]),
    )
    assert resultado.resumen.insertados == 1

    conceptos = await _conceptos(contexto_control)
    assert "CPT-00001" in conceptos
    assert conceptos["CPT-00001"]["descripcion"] == "Trabe de cimentación"


# --- Conceptos auxiliares (§7.3, mismo contrato que Catálogo de conceptos)


async def test_conceptos_auxiliares_se_dan_de_alta_con_tipo_auxiliar(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    resultado = await _cargar(
        contexto_control,
        TipoCarga.CONCEPTOS_AUXILIARES,
        _archivo_conceptos_auxiliares([["AUX-01", "Cimbra de losa", "m2"]]),
    )
    assert resultado.resumen.insertados == 1

    conceptos = await _conceptos(contexto_control)
    assert conceptos["AUX-01"]["tipo"] == "auxiliar"


async def test_conceptos_auxiliares_con_clave_unidad_real_ignora_costo_y_familia(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """Archivo real (`Catalogo_de_auxiliares.xlsx`): mismas columnas que
    Materiales, costo/familia incluidos. Confirmado con el usuario: se
    ignoran — solo clave/descripción/unidad (con `clave_unidad`) importan
    aquí; el costo es CPU, no identidad (§8.7)."""
    resultado = await _cargar(
        contexto_control,
        TipoCarga.CONCEPTOS_AUXILIARES,
        _libro(
            [
                ["CLAVE", "DESCRIPCIÓN", "CLAVE UNIDAD", "UNIDAD", "COSTO BASE M.N.",
                 "COSTO BASE M.E.", "COSTO UNITARIO", "FECHA", "FAMILIA"],
                ["AUX-00001", "Trabe T-3 de 15x25 cm", 8, "m", 72.14, 0, 72.14, None,
                 "Auxiliares"],
            ]
        ),
    )
    assert resultado.resumen.errores == 0

    conceptos = await _conceptos(contexto_control)
    unidades = await _unidades(contexto_control)
    assert conceptos["AUX-00001"]["tipo"] == "auxiliar"
    assert "8" in unidades
    assert unidades["8"]["nombre"] == "m"
    assert conceptos["AUX-00001"]["unidad_id"] == unidades["8"]["id"]


async def test_conceptos_auxiliares_comparte_clave_con_catalogo_de_conceptos(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """`uq_concepto_clave` es `(org_id, clave)` sin importar el tipo (§7.3):
    un archivo de auxiliares que repite la clave de un concepto normal
    actualiza ESE registro — no lo duplica ni le cambia el tipo, que solo
    se fija al dar de alta (§3.3, la clave manda)."""
    await _cargar(
        contexto_control,
        TipoCarga.CATALOGO_CONCEPTOS,
        _archivo_conceptos_base([["EST-01", "Muro de block", "m2"]]),
    )
    await _cargar(
        contexto_control,
        TipoCarga.CONCEPTOS_AUXILIARES,
        _archivo_conceptos_auxiliares([["EST-01", "Muro de block (renombrado)", "m2"]]),
    )

    conceptos = await _conceptos(contexto_control)
    assert len(conceptos) == 1
    assert conceptos["EST-01"]["tipo"] == "concepto"
    assert conceptos["EST-01"]["descripcion"] == "Muro de block (renombrado)"


# --- Niveles de construcción (§10.1, `CATALOGO_DE_NIVELES.xlsx`) --------


async def test_carga_de_niveles_crea_y_actualiza(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    resultado = await _cargar(
        contexto_control,
        TipoCarga.NIVELES,
        _archivo_niveles([_fila_nivel_etapa("Subcapítulo", "NIV-00001", "CIMENTACION")]),
    )
    assert resultado.resumen.insertados == 1
    assert (await _niveles(contexto_control))["NIV-00001"]["descripcion"] == "CIMENTACION"

    resultado2 = await _cargar(
        contexto_control,
        TipoCarga.NIVELES,
        _archivo_niveles([_fila_nivel_etapa("Subcapítulo", "NIV-00001", "CIMENTACIÓN")]),
    )
    assert resultado2.resumen.actualizados == 1
    assert (await _niveles(contexto_control))["NIV-00001"]["descripcion"] == "CIMENTACIÓN"


async def test_nivel_sin_clave_se_numera_solo(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    await _cargar(
        contexto_control,
        TipoCarga.NIVELES,
        _archivo_niveles([_fila_nivel_etapa("Subcapítulo", "", "PLANTA BAJA")]),
    )
    niveles = await _niveles(contexto_control)
    assert "NIV-00001" in niveles
    assert niveles["NIV-00001"]["descripcion"] == "PLANTA BAJA"


async def test_revertir_carga_de_niveles_deshace_el_alta(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """Ejercita `_ELIMINAR`/`_RESTAURAR["nivel"]` (migración 0037): antes de
    este cargador, `nivel` nunca era dueño de un snapshot revertible."""
    resultado = await _cargar(
        contexto_control,
        TipoCarga.NIVELES,
        _archivo_niveles([_fila_nivel_etapa("Subcapítulo", "NIV-00001", "AZOTEA")]),
    )
    async with sesion_con_rls(contexto_control) as sesion:
        reversa = await RevertirCarga(
            cargas=RepositorioCargasSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        ).ejecutar(resultado.carga_id, usuario_id=contexto_control.usuario_id)
    assert reversa["operaciones_revertidas"] == 1
    assert await _niveles(contexto_control) == {}


# --- Etapas de construcción (§10.1, `CATALOGO_DE_ETAPAS_DE_CONSTRUCCION.xlsx`)


async def test_carga_de_etapas_crea_y_actualiza(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    resultado = await _cargar(
        contexto_control,
        TipoCarga.ETAPAS_CONSTRUCTIVAS,
        _archivo_etapas([_fila_nivel_etapa("Nivel 2", "ECO-00001", "ESTRUCTURA CIM")]),
    )
    assert resultado.resumen.insertados == 1

    resultado2 = await _cargar(
        contexto_control,
        TipoCarga.ETAPAS_CONSTRUCTIVAS,
        _archivo_etapas([_fila_nivel_etapa("Nivel 2", "ECO-00001", "ESTRUCTURA CIMENTACIÓN")]),
    )
    assert resultado2.resumen.actualizados == 1
    etapas = await _etapas(contexto_control)
    assert etapas["ECO-00001"]["descripcion"] == "ESTRUCTURA CIMENTACIÓN"
    # Sin `nivel_id`: el archivo real no trae a qué nivel pertenece (ver
    # `domain.cargadores.etapas_constructivas`).
    assert etapas["ECO-00001"]["nivel_id"] is None


async def test_etapa_sin_clave_se_numera_solo(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    await _cargar(
        contexto_control,
        TipoCarga.ETAPAS_CONSTRUCTIVAS,
        _archivo_etapas([_fila_nivel_etapa("Nivel 2", "", "INSTALACIONES GAS PB")]),
    )
    etapas = await _etapas(contexto_control)
    assert "ECO-00001" in etapas


# --- Unidades (§3.5, `CATALOGO_DE_UNIDADES.xlsx`) -------------------------


async def test_carga_de_unidades_crea_y_actualiza(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    resultado = await _cargar(
        contexto_control,
        TipoCarga.UNIDADES,
        _archivo_unidades([[1, "KG", "Kilogramo"]]),
    )
    assert resultado.resumen.insertados == 1
    assert (await _unidades(contexto_control))["KG"]["nombre"] == "Kilogramo"

    resultado2 = await _cargar(
        contexto_control,
        TipoCarga.UNIDADES,
        _archivo_unidades([[1, "KG", "Kilogramo (kg)"]]),
    )
    assert resultado2.resumen.actualizados == 1
    assert (await _unidades(contexto_control))["KG"]["nombre"] == "Kilogramo (kg)"


async def test_clave_unidad_numerica_del_archivo_no_es_la_clave_del_catalogo(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """"CLAVE UNIDAD" (1, 2, 3...) es un consecutivo del sistema de origen,
    no la clave del catálogo —esa es "UNIDAD"—: dos filas con la misma
    "CLAVE UNIDAD" pero distinta "UNIDAD" son dos unidades distintas."""
    await _cargar(
        contexto_control,
        TipoCarga.UNIDADES,
        _archivo_unidades([[1, "KG", "Kilogramo"], [1, "LTR", "Litro"]]),
    )
    unidades = await _unidades(contexto_control)
    assert {"KG", "LTR"} <= set(unidades)


async def test_unidad_sin_clave_se_numera_solo(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    await _cargar(
        contexto_control,
        TipoCarga.UNIDADES,
        _archivo_unidades([[None, "", "Actividad"]]),
    )
    unidades = await _unidades(contexto_control)
    assert "UNI-00001" in unidades
    assert unidades["UNI-00001"]["nombre"] == "Actividad"


async def test_revertir_carga_de_unidades_deshace_el_alta(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """Ejercita `_ELIMINAR`/`_RESTAURAR["unidad"]`: antes de este cargador,
    `unidad` nunca era dueña de un snapshot revertible (mismo motivo que
    `nivel`/`etapa_constructiva`, migración 0037)."""
    resultado = await _cargar(
        contexto_control,
        TipoCarga.UNIDADES,
        _archivo_unidades([[3, "PZ", "Pieza"]]),
    )
    async with sesion_con_rls(contexto_control) as sesion:
        reversa = await RevertirCarga(
            cargas=RepositorioCargasSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        ).ejecutar(resultado.carga_id, usuario_id=contexto_control.usuario_id)
    assert reversa["operaciones_revertidas"] == 1
    # No `== {}`: la fixture `catalogos` ya sembró su propia unidad ('ton')
    # para que otros tests tengan contra qué homologar — la reversa solo
    # deshace lo que ESTA carga dio de alta.
    assert "PZ" not in await _unidades(contexto_control)


async def test_reemplazar_unidades_da_de_baja_lo_que_el_archivo_ya_no_trae(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """A diferencia de nivel/etapa_constructiva (sin `estatus`, migración
    0005), `unidad` sí tiene baja lógica — modo Reemplazar (§10.2) sí puede
    hacer algo con lo que el archivo ya no trae."""
    await _cargar(
        contexto_control,
        TipoCarga.UNIDADES,
        _archivo_unidades([[1, "KG", "Kilogramo"], [3, "PZ", "Pieza"]]),
    )
    await _cargar(
        contexto_control,
        TipoCarga.UNIDADES,
        _archivo_unidades([[1, "KG", "Kilogramo"]]),
        modo=ModoCarga.REEMPLAZAR,
    )
    unidades = await _unidades(contexto_control)
    assert unidades["KG"]["estatus"] == "activo"
    assert unidades["PZ"]["estatus"] == "inactivo"
    # 'ton' es de la fixture `catalogos`, no de este archivo — Reemplazar
    # también la da de baja: no viene en ninguna de las dos cargas.
    assert unidades["ton"]["estatus"] == "inactivo"


# --- Familias (§3.5, `CATALOGO_DE_FAMILIAS.xlsx`) --------------------------


async def test_carga_de_familias_crea_y_actualiza(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    resultado = await _cargar(
        contexto_control,
        TipoCarga.FAMILIAS,
        _archivo_familias([["FML-00001", "Acabados", "ACA"]]),
    )
    assert resultado.resumen.insertados == 1
    assert (await _familias(contexto_control))["FML-00001"]["nombre"] == "Acabados"

    resultado2 = await _cargar(
        contexto_control,
        TipoCarga.FAMILIAS,
        _archivo_familias([["FML-00001", "Acabados finos", "ACA"]]),
    )
    assert resultado2.resumen.actualizados == 1
    assert (await _familias(contexto_control))["FML-00001"]["nombre"] == "Acabados finos"


async def test_prefijo_de_familia_se_ignora(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """"PREFIJO" (ACA/ADH/...) no tiene dónde vivir en `familia` hoy: se lee
    y se descarta sin romper la fila (§10.6)."""
    await _cargar(
        contexto_control,
        TipoCarga.FAMILIAS,
        _archivo_familias([["FML-00034", "Sanitario", "SAN"]]),
    )
    familias = await _familias(contexto_control)
    assert familias["FML-00034"]["nombre"] == "Sanitario"


async def test_familia_sin_clave_se_numera_solo(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    await _cargar(
        contexto_control,
        TipoCarga.FAMILIAS,
        _archivo_familias([["", "Jardinería", "JAR"]]),
    )
    familias = await _familias(contexto_control)
    assert "FAM-00001" in familias
    assert familias["FAM-00001"]["nombre"] == "Jardinería"


async def test_revertir_carga_de_familias_deshace_el_alta(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """Ejercita `_ELIMINAR`/`_RESTAURAR["familia"]`: antes de este cargador,
    `familia` nunca era dueña de un snapshot revertible."""
    resultado = await _cargar(
        contexto_control,
        TipoCarga.FAMILIAS,
        _archivo_familias([["FML-00009", "Cimentación", "CIM"]]),
    )
    async with sesion_con_rls(contexto_control) as sesion:
        reversa = await RevertirCarga(
            cargas=RepositorioCargasSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        ).ejecutar(resultado.carga_id, usuario_id=contexto_control.usuario_id)
    assert reversa["operaciones_revertidas"] == 1
    # No `== {}`: la fixture `catalogos` ya sembró su propia familia
    # ('CEM') para que otros tests tengan contra qué homologar — la
    # reversa solo deshace lo que ESTA carga dio de alta.
    assert "FML-00009" not in await _familias(contexto_control)


async def test_reemplazar_familias_da_de_baja_lo_que_el_archivo_ya_no_trae(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    await _cargar(
        contexto_control,
        TipoCarga.FAMILIAS,
        _archivo_familias([["FML-00001", "Acabados", "ACA"], ["FML-00009", "Cimentación", "CIM"]]),
    )
    await _cargar(
        contexto_control,
        TipoCarga.FAMILIAS,
        _archivo_familias([["FML-00001", "Acabados", "ACA"]]),
        modo=ModoCarga.REEMPLAZAR,
    )
    familias = await _familias(contexto_control)
    assert familias["FML-00001"]["estatus"] == "activo"
    assert familias["FML-00009"]["estatus"] == "inactivo"
    # 'CEM' es de la fixture `catalogos`, no de este archivo — Reemplazar
    # también la da de baja: no viene en ninguna de las dos cargas.
    assert familias["CEM"]["estatus"] == "inactivo"


# --- Mano de obra / Destajos (§10.6 `CABECERAS_MANO_DE_OBRA.xlsx`) -------


async def test_carga_de_mano_de_obra_alimenta_el_catalogo_de_insumos(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """Un destajo es un `Insumo` con `tipo='mano_obra'` (§7.3). La cuadrilla
    nueva se da de alta sola —mismo criterio que unidad/familia (§8.7)— y
    "asume" el rendimiento teórico que trae el archivo."""
    resultado = await _cargar(
        contexto_control,
        TipoCarga.MANO_DE_OBRA,
        _archivo_mano_obra(
            [
                [
                    # Sin "CLAVE UNIDAD" a propósito: esta fila prueba que
                    # "UNIDAD" solo (texto libre) sigue resolviendo contra el
                    # catálogo ya sembrado (§8.7) cuando el archivo no separa
                    # clave de nombre — ver `test_clave_unidad_...` para el
                    # caso con la columna presente.
                    "Individual", "US-01", "dest-01", "Aplanado fino", "", "ton",
                    "CUAD-01", "12.5", None, "85.30", "CEM",
                ]
            ]
        ),
    )

    assert resultado.estatus is EstatusCarga.APLICADO
    assert resultado.resumen.insertados == 1
    assert resultado.pendientes == 0

    catalogo = await _insumos(contexto_control)
    destajo = catalogo["DEST-01"]
    assert destajo["tipo"] == "mano_obra"
    assert destajo["descripcion"] == "Aplanado fino"
    assert destajo["unidad_id"] == catalogos.unidad_id
    assert destajo["familia_id"] == catalogos.familia_id
    assert destajo["costo_base"] == Decimal("85.3000")
    assert destajo["rendimiento_teorico"] == Decimal("12.500000")

    cuadrillas = await _cuadrillas(contexto_control)
    assert "CUAD-01" in cuadrillas
    assert destajo["cuadrilla_id"] == cuadrillas["CUAD-01"]["id"]
    assert cuadrillas["CUAD-01"]["rendimiento"] == Decimal("12.500000")


# --- Subcontratos (§10.6 `catalogo_de_SUBCONTRATOS.xlsx`) ----------------


async def test_carga_de_subcontratos_alimenta_el_catalogo_de_insumos_como_subcontrato(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """Mismo cargador que mano de obra (`AplicadorManoObra`, `tipo` fijo por
    constructor), pero su propia hoja (`SUBCONTRATOS`, no `DESTAJOS`) y su
    propio `insumo.tipo` — un subcontrato no es mano de obra (§10.1)."""
    resultado = await _cargar(
        contexto_control,
        TipoCarga.SUBCONTRATOS,
        _archivo_subcontratos(
            [
                [
                    "Subcontrato", "US-01", "sub-00001", "Instalación eléctrica",
                    "UN-01", "ton", None, "8", None, "1500.00", "CEM",
                ]
            ]
        ),
    )

    assert resultado.estatus is EstatusCarga.APLICADO
    assert resultado.resumen.insertados == 1
    assert resultado.pendientes == 0

    catalogo = await _insumos(contexto_control)
    subcontrato = catalogo["SUB-00001"]
    assert subcontrato["tipo"] == "subcontrato"
    assert subcontrato["descripcion"] == "Instalación eléctrica"
    assert subcontrato["costo_base"] == Decimal("1500.0000")


async def test_recargar_mano_de_obra_actualiza_el_rendimiento_de_la_cuadrilla(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """"La cuadrilla asume el rendimiento" del destajo que se le asigna: una
    recarga con otro rendimiento lo actualiza, no crea otra cuadrilla."""
    await _cargar(
        contexto_control,
        TipoCarga.MANO_DE_OBRA,
        _archivo_mano_obra(
            [["Individual", "US-01", "dest-01", "Aplanado fino", "UN-01", "ton", "CUAD-01", "10", None, "80", "CEM"]]
        ),
    )
    await _cargar(
        contexto_control,
        TipoCarga.MANO_DE_OBRA,
        _archivo_mano_obra(
            [["Individual", "US-01", "dest-01", "Aplanado fino", "UN-01", "ton", "CUAD-01", "15", None, "80", "CEM"]]
        ),
    )

    cuadrillas = await _cuadrillas(contexto_control)
    assert len(cuadrillas) == 1
    assert cuadrillas["CUAD-01"]["rendimiento"] == Decimal("15.000000")


async def test_revertir_mano_de_obra_deja_el_insumo_sin_cuadrilla_ni_rendimiento(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """§10.8: la reversa del alta borra el insumo entero; no hay nada que
    "dejar en null" porque el registro nunca existió antes de este lote."""
    resultado = await _cargar(
        contexto_control,
        TipoCarga.MANO_DE_OBRA,
        _archivo_mano_obra(
            [["Individual", "US-01", "dest-01", "Aplanado fino", "UN-01", "ton", "CUAD-01", "10", None, "80", "CEM"]]
        ),
    )

    async with sesion_con_rls(contexto_control) as sesion:
        reversa = await RevertirCarga(
            cargas=RepositorioCargasSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        ).ejecutar(resultado.carga_id, usuario_id=contexto_control.usuario_id)

    assert reversa["operaciones_revertidas"] == 1
    assert await _insumos(contexto_control) == {}
    # La cuadrilla es catálogo compartido por organización (§10.6): revertir
    # este lote no se la lleva, igual que `nivel`/`etapa_constructiva`.
    assert "CUAD-01" in await _cuadrillas(contexto_control)


# --- Cuadrillas (§10.6 `CABECERAS_CUADRILLAS.xlsx`) -----------------------

_FILAS_CUADRILLA_V1 = [
    ["CUA0001", "CUA0001", "Cuadrilla (Oficial + Ayudante)", "jor", None, 1584, None],
    ["CUA0001", "MOOP-0049", "Oficial Albañil", "jor", 1, 840, 840],
    ["CUA0001", "MOOP-0026", "Ayudante general", "jor", 1, 600, 600],
    ["CUA0001", "MOOP-0079", "Contratista", "%mo", 0.1, 1440, 144],
]


async def _sembrar_insumos_de_cuadrilla(contexto: ContextoSesion) -> None:
    """Los integrantes de una cuadrilla son insumos ya existentes (§10.6):
    se siembran con una carga de materiales, que alimenta el mismo catálogo
    de insumos que resuelve `AplicadorCuadrillas` (§7.3)."""
    await _cargar(
        contexto,
        TipoCarga.MATERIALES,
        _archivo_materiales(
            [
                ["MOOP-0049", "Oficial Albañil", "jor", "CEM", "840", "", "NO"],
                ["MOOP-0026", "Ayudante general", "jor", "CEM", "600", "", "NO"],
                ["MOOP-0079", "Contratista", "jor", "CEM", "1440", "", "NO"],
            ]
        ),
    )


async def test_carga_de_cuadrillas_publica_version_1_con_su_pu(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """El PU de la cuadrilla (1584) se calcula de sus integrantes, no del PU
    declarado en la fila cabecera (§7.3, mismo criterio que un CPU)."""
    await _sembrar_insumos_de_cuadrilla(contexto_control)

    resultado = await _cargar(
        contexto_control, TipoCarga.CUADRILLAS, _archivo_cuadrillas(_FILAS_CUADRILLA_V1)
    )

    assert resultado.estatus is EstatusCarga.APLICADO
    assert resultado.resumen.insertados == 1
    assert resultado.pendientes == 0

    cuadrilla = (await _cuadrillas(contexto_control))["CUA0001"]
    assert cuadrilla["nombre"] == "Cuadrilla (Oficial + Ayudante)"

    async with sesion_con_rls(contexto_control) as sesion:
        versiones = await RepositorioCuadrillasSQL(sesion).versiones(cuadrilla["id"])
    assert len(versiones) == 1
    assert versiones[0]["version"] == 1
    assert versiones[0]["precio_unitario"] == Decimal("1584.0000")
    assert versiones[0]["vigente"] is True


async def test_un_integrante_inexistente_se_da_de_alta_solo(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """Confirmado con el usuario: el catálogo de personal (`MOOP-...`) nunca
    se carga por ningún otro archivo — un integrante nuevo se da de alta
    solo, mismo criterio que unidad/familia (§8.7), no va a la bandeja."""
    resultado = await _cargar(
        contexto_control,
        TipoCarga.CUADRILLAS,
        _archivo_cuadrillas(
            [
                ["CUA0002", "CUA0002", "Cuadrilla nueva", "jor", None, 500, None],
                ["CUA0002", "MOOP-9999", "Ayudante nuevo", "jor", 1, 500, 500],
            ]
        ),
    )

    assert resultado.estatus is EstatusCarga.APLICADO
    assert resultado.resumen.insertados == 1
    assert resultado.pendientes == 0

    insumo = (await _insumos(contexto_control))["MOOP-9999"]
    assert insumo["tipo"] == "mano_obra"
    assert insumo["descripcion"] == "Ayudante nuevo"

    cuadrilla = (await _cuadrillas(contexto_control))["CUA0002"]
    async with sesion_con_rls(contexto_control) as sesion:
        versiones = await RepositorioCuadrillasSQL(sesion).versiones(cuadrilla["id"])
    assert versiones[0]["precio_unitario"] == Decimal("500.0000")


async def test_recargar_cuadrillas_con_otro_costo_publica_version_2(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    await _sembrar_insumos_de_cuadrilla(contexto_control)
    await _cargar(contexto_control, TipoCarga.CUADRILLAS, _archivo_cuadrillas(_FILAS_CUADRILLA_V1))

    filas_v2 = [
        ["CUA0001", "CUA0001", "Cuadrilla (Oficial + Ayudante)", "jor", None, 1700, None],
        ["CUA0001", "MOOP-0049", "Oficial Albañil", "jor", 1, 900, 900],
        ["CUA0001", "MOOP-0026", "Ayudante general", "jor", 1, 600, 600],
        ["CUA0001", "MOOP-0079", "Contratista", "%mo", 0.1, 1500, 150],
    ]
    segunda = await _cargar(contexto_control, TipoCarga.CUADRILLAS, _archivo_cuadrillas(filas_v2))
    assert segunda.resumen.actualizados == 1

    cuadrilla = (await _cuadrillas(contexto_control))["CUA0001"]
    async with sesion_con_rls(contexto_control) as sesion:
        versiones = await RepositorioCuadrillasSQL(sesion).versiones(cuadrilla["id"])
    assert len(versiones) == 2
    v1, v2 = sorted(versiones, key=lambda v: v["version"])
    assert v1["vigente"] is False
    assert v2["vigente"] is True
    assert v2["precio_unitario"] == Decimal("900") + Decimal("600") + Decimal("150")


async def test_recargar_cuadrillas_con_la_misma_composicion_no_versiona_de_nuevo(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """§10.8: "si es idéntico, no crea versión"."""
    await _sembrar_insumos_de_cuadrilla(contexto_control)
    await _cargar(contexto_control, TipoCarga.CUADRILLAS, _archivo_cuadrillas(_FILAS_CUADRILLA_V1))
    segunda = await _cargar(
        contexto_control, TipoCarga.CUADRILLAS, _archivo_cuadrillas(_FILAS_CUADRILLA_V1)
    )

    assert segunda.resumen.insertados == 0
    assert segunda.resumen.actualizados == 0

    cuadrilla = (await _cuadrillas(contexto_control))["CUA0001"]
    async with sesion_con_rls(contexto_control) as sesion:
        versiones = await RepositorioCuadrillasSQL(sesion).versiones(cuadrilla["id"])
    assert len(versiones) == 1


async def test_revertir_una_recarga_de_cuadrilla_deja_vigente_la_version_anterior(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """§10.8: revertir el lote de la versión 2 la borra y regresa la 1 a vigente."""
    await _sembrar_insumos_de_cuadrilla(contexto_control)
    await _cargar(contexto_control, TipoCarga.CUADRILLAS, _archivo_cuadrillas(_FILAS_CUADRILLA_V1))

    filas_v2 = [
        ["CUA0001", "CUA0001", "Cuadrilla (Oficial + Ayudante)", "jor", None, 2000, None],
        ["CUA0001", "MOOP-0049", "Oficial Albañil", "jor", 1, 1000, 1000],
        ["CUA0001", "MOOP-0026", "Ayudante general", "jor", 1, 800, 800],
        ["CUA0001", "MOOP-0079", "Contratista", "%mo", 0.1, 1800, 180],
    ]
    segunda = await _cargar(contexto_control, TipoCarga.CUADRILLAS, _archivo_cuadrillas(filas_v2))

    async with sesion_con_rls(contexto_control) as sesion:
        reversa = await RevertirCarga(
            cargas=RepositorioCargasSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        ).ejecutar(segunda.carga_id, usuario_id=contexto_control.usuario_id)

    assert reversa["operaciones_revertidas"] > 0
    cuadrilla = (await _cuadrillas(contexto_control))["CUA0001"]
    async with sesion_con_rls(contexto_control) as sesion:
        versiones = await RepositorioCuadrillasSQL(sesion).versiones(cuadrilla["id"])
    assert len(versiones) == 1
    assert versiones[0]["version"] == 1
    assert versiones[0]["vigente"] is True
    assert versiones[0]["precio_unitario"] == Decimal("1584.0000")


async def test_revertir_el_alta_de_una_cuadrilla_nueva_la_borra_completa(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """`AplicadorCuadrillas` registra el insert de `cuadrilla` en el
    snapshot (a diferencia del auto-alta de paso que hace mano de obra, que
    no se registra): sin `cuadrilla` en `_ELIMINAR`, revertir este lote
    tronaba con `TablaNoRevertible` — la cuadrilla es tan suya como un
    `concepto` lo es de su carga de CPU (§10.8)."""
    await _sembrar_insumos_de_cuadrilla(contexto_control)
    primera = await _cargar(
        contexto_control, TipoCarga.CUADRILLAS, _archivo_cuadrillas(_FILAS_CUADRILLA_V1)
    )

    async with sesion_con_rls(contexto_control) as sesion:
        reversa = await RevertirCarga(
            cargas=RepositorioCargasSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        ).ejecutar(primera.carga_id, usuario_id=contexto_control.usuario_id)

    assert reversa["operaciones_revertidas"] > 0
    assert "CUA0001" not in await _cuadrillas(contexto_control)
    # Los integrantes son catálogo compartido (§10.6): la cuadrilla se va,
    # los MOOP- que la sembró la carga de materiales no.
    assert "MOOP-0049" in await _insumos(contexto_control)


async def test_eliminar_version_de_cuadrilla_borra_la_retirada_pero_no_la_vigente(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """Mantenimiento directo del historial (§10.8), sin pasar por una carga:
    una versión retirada se puede borrar; la vigente no."""
    from obractrl.application.puertos.repositorios import (
        RegistroNoEncontrado,
        VersionVigenteNoEliminable,
    )

    await _sembrar_insumos_de_cuadrilla(contexto_control)
    await _cargar(contexto_control, TipoCarga.CUADRILLAS, _archivo_cuadrillas(_FILAS_CUADRILLA_V1))
    filas_v2 = [
        ["CUA0001", "CUA0001", "Cuadrilla (Oficial + Ayudante)", "jor", None, 1700, None],
        ["CUA0001", "MOOP-0049", "Oficial Albañil", "jor", 1, 900, 900],
        ["CUA0001", "MOOP-0026", "Ayudante general", "jor", 1, 600, 600],
        ["CUA0001", "MOOP-0079", "Contratista", "%mo", 0.1, 1500, 150],
    ]
    await _cargar(contexto_control, TipoCarga.CUADRILLAS, _archivo_cuadrillas(filas_v2))

    cuadrilla = (await _cuadrillas(contexto_control))["CUA0001"]
    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioCuadrillasSQL(sesion)
        versiones = await repo.versiones(cuadrilla["id"])
    v1 = next(v for v in versiones if v["version"] == 1)
    v2 = next(v for v in versiones if v["version"] == 2)
    assert v1["vigente"] is False
    assert v2["vigente"] is True

    async with sesion_con_rls(contexto_control) as sesion:
        with pytest.raises(VersionVigenteNoEliminable):
            await RepositorioCuadrillasSQL(sesion).eliminar_version(cuadrilla["id"], v2["id"])

    async with sesion_con_rls(contexto_control) as sesion:
        await RepositorioCuadrillasSQL(sesion).eliminar_version(cuadrilla["id"], v1["id"])
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        restantes = await RepositorioCuadrillasSQL(sesion).versiones(cuadrilla["id"])
    assert [v["version"] for v in restantes] == [2]

    async with sesion_con_rls(contexto_control) as sesion:
        with pytest.raises(RegistroNoEncontrado):
            await RepositorioCuadrillasSQL(sesion).eliminar_version(cuadrilla["id"], v1["id"])


# --- CPU / Conceptos (§10.6 `CABECERAS_CPU.xlsx`) ------------------------


async def _sembrar_insumos(contexto: ContextoSesion) -> ResultadoCarga:
    return await _cargar(
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
        TipoCarga.CPU,
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


async def test_cpu_con_insumo_de_descripcion_distinta_homologa_y_alerta_sin_bloquear(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """Homologación con alerta (§8.7): la clave manda igual (§3.3) —MAT-01
    se resuelve y el concepto entra completo—, pero como la descripción de
    este renglón no se parece a la del catálogo, se abre un pendiente no
    crítico para que alguien lo revise después. No bloquea la carga."""
    await _sembrar_insumos(contexto_control)  # MAT-01 = "Block de concreto"

    resultado = await _cargar(
        contexto_control,
        TipoCarga.CPU,
        _archivo_cpu(
            [
                _fila_cpu("EST-01", "EST-01", "Muro de block", "ton", tipo="Concepto"),
                _fila_cpu(
                    insumo="MAT-01",
                    descripcion="Varilla corrugada",
                    cantidad="12.5",
                    pu="20",
                    tipo="Material",
                ),
            ]
        ),
    )

    assert resultado.estatus is EstatusCarga.APLICADO
    assert resultado.resumen.errores == 0

    async with sesion_con_rls(contexto_control) as sesion:
        bandeja = await RepositorioCargasSQL(sesion).listar_pendientes(
            carga_id=resultado.carga_id
        )
    alertas = [b for b in bandeja if b["tipo"] == "descripcion_distinta"]
    assert len(alertas) == 1
    assert alertas[0]["critico"] is False
    assert alertas[0]["entidad"] == "insumo"
    assert alertas[0]["propuesta"]["clave"] == "MAT-01"


async def test_un_insumo_desconocido_en_el_cpu_se_da_de_alta_solo(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """A diferencia de un concepto, un insumo que no cruza ya no detiene el
    APU (§7.3, §8.7): se da de alta con lo que trae la fila componente
    —clave, descripción, tipo, unidad, costo— y el concepto entra completo.

    El concepto sigue abriendo su propio pendiente informativo de
    "CPU nuevo" (§10.3, ajeno a este cambio: lo abre todo alta de concepto,
    tenga o no un insumo por resolver) — lo que esta prueba verifica es que
    ya **no** hay, además, el pendiente crítico de insumo no reconocido."""
    await _sembrar_insumos(contexto_control)

    resultado = await _cargar(
        contexto_control,
        TipoCarga.CPU,
        _archivo_cpu(
            [
                _fila_cpu("EST-01", "EST-01", "Muro de block", "ton", tipo="Concepto"),
                _fila_cpu(insumo="MAT-01", cantidad="12.5", pu="20", tipo="Material"),
                _fila_cpu(
                    insumo="SUB-01",
                    descripcion="Impermeabilizante",
                    unidad="m2",
                    cantidad="1",
                    pu="500",
                    tipo="Subcontrato",
                ),
            ]
        ),
    )

    assert resultado.estatus is EstatusCarga.APLICADO
    assert resultado.resumen.insertados == 1

    async with sesion_con_rls(contexto_control) as sesion:
        bandeja = await RepositorioCargasSQL(sesion).listar_pendientes(
            carga_id=resultado.carga_id
        )
    assert not [b for b in bandeja if b["entidad"] == "insumo"]

    async with sesion_con_rls(contexto_control) as sesion:
        conceptos = await RepositorioConceptosSQL(sesion).listar()
    assert "EST-01" in {str(c["clave"]) for c in conceptos}

    subcontrato = (await _insumos(contexto_control))["SUB-01"]
    assert subcontrato["tipo"] == "subcontrato"
    assert subcontrato["descripcion"] == "Impermeabilizante"
    assert subcontrato["costo_base"] == Decimal("500.0000")
    # "m2" no estaba sembrada: se dio de alta sola, mismo criterio que la
    # unidad/familia del propio concepto (§8.7).
    assert "m2" in await _unidades(contexto_control)


async def test_recargar_el_cpu_con_otra_receta_publica_version_2_y_se_revierte(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """§10.8: la anterior queda en el historial y el lote se deshace entero."""
    await _sembrar_insumos(contexto_control)
    await _cargar(
        contexto_control,
        TipoCarga.CPU,
        _archivo_cpu(
            [
                _fila_cpu("EST-01", "EST-01", "Muro de block", "ton", tipo="Concepto"),
                _fila_cpu(insumo="MAT-01", cantidad="12.5", pu="20", tipo="Material"),
            ]
        ),
    )
    segunda = await _cargar(
        contexto_control,
        TipoCarga.CPU,
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


async def _cargar_concepto_y_su_recarga(
    contexto_control: ContextoSesion,
) -> tuple[ResultadoCarga, ResultadoCarga]:
    """El alta de EST-01 y una carga posterior que recarga su CPU —la pareja
    que reproduce el conflicto real de reversa fuera de orden (§10.8)."""
    await _sembrar_insumos(contexto_control)

    primera = await _cargar(
        contexto_control,
        TipoCarga.CPU,
        _archivo_cpu(
            [
                _fila_cpu("EST-01", "EST-01", "Muro de block", "ton", tipo="Concepto"),
                _fila_cpu(insumo="MAT-01", cantidad="12.5", pu="20", tipo="Material"),
            ]
        ),
    )
    segunda = await _cargar(
        contexto_control,
        TipoCarga.CPU,
        _archivo_cpu(
            [
                _fila_cpu("EST-01", "EST-01", "Muro de block", "ton", tipo="Concepto"),
                _fila_cpu(insumo="MAT-01", cantidad="14", pu="20", tipo="Material"),
            ]
        ),
    )
    return primera, segunda


async def test_revertir_el_alta_de_un_concepto_con_una_recarga_posterior_bloquea(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """El alta de un concepto no se puede revertir sola mientras una carga
    posterior que recargó su CPU siga aplicada (§10.8): antes se detecta
    (`CargaConDependientes`, 409 claro) y no se llega ni a intentar el
    `IntegrityError` crudo que `ReversaEnConflicto` traduciría."""
    primera, segunda = await _cargar_concepto_y_su_recarga(contexto_control)

    async with sesion_con_rls(contexto_control) as sesion:
        with pytest.raises(CargaConDependientes) as capturado:
            await RevertirCarga(
                cargas=RepositorioCargasSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
            ).ejecutar(primera.carga_id, usuario_id=contexto_control.usuario_id)

    assert [d["id"] for d in capturado.value.dependientes] == [segunda.carga_id]
    # No se tocó nada: el concepto sigue como lo dejó la recarga.
    assert "EST-01" in await _conceptos(contexto_control)


async def test_revertir_en_cadena_deshace_el_alta_y_su_recarga_juntas(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """La salida de `CargaConDependientes` (§10.8): revierte la carga pedida
    y la que depende de ella, de la más nueva a la más vieja, como una sola
    unidad — el concepto vuelve a no existir, las dos cargas quedan
    revertidas."""
    primera, segunda = await _cargar_concepto_y_su_recarga(contexto_control)

    async with sesion_con_rls(contexto_control) as sesion:
        resultado = await RevertirCargaEnCadena(
            cargas=RepositorioCargasSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        ).ejecutar(primera.carga_id, usuario_id=contexto_control.usuario_id)

    assert resultado["cargas_revertidas"] == [segunda.carga_id, primera.carga_id]
    assert resultado["operaciones_revertidas"] > 0
    assert "EST-01" not in await _conceptos(contexto_control)

    async with sesion_con_rls(contexto_control) as sesion:
        cargas = RepositorioCargasSQL(sesion)
        fila_primera = await cargas.obtener(primera.carga_id)
        fila_segunda = await cargas.obtener(segunda.carga_id)
    assert fila_primera is not None and fila_primera["revertida_en"] is not None
    assert fila_segunda is not None and fila_segunda["revertida_en"] is not None


async def test_revertir_materiales_bloqueado_por_insumo_usado_en_un_cpu(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """El insumo y la explosión que lo usa no comparten `(tabla,
    registro_id)` en el snapshot —los liga `explosion.insumo_id`, una FK sin
    cascada, no la misma fila— así que sin `_REFERENCIAS_EXTERNAS`
    `dependientes_de` no veía este caso: revertir materiales con el CPU
    encima seguía aplicado tronaba (o silenciosamente rompía una FK, según
    el orden) en vez de bloquear con un mensaje claro (§10.8)."""
    materiales = await _sembrar_insumos(contexto_control)

    cpu = await _cargar(
        contexto_control,
        TipoCarga.CPU,
        _archivo_cpu(
            [
                _fila_cpu("EST-01", "EST-01", "Muro de block", "ton", tipo="Concepto"),
                _fila_cpu(
                    insumo="MAT-01", descripcion="Block", cantidad="12.5", pu="20",
                    tipo="Material",
                ),
            ]
        ),
    )

    async with sesion_con_rls(contexto_control) as sesion:
        with pytest.raises(CargaConDependientes) as capturado:
            await RevertirCarga(
                cargas=RepositorioCargasSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
            ).ejecutar(materiales.carga_id, usuario_id=contexto_control.usuario_id)

    assert [d["id"] for d in capturado.value.dependientes] == [cpu.carga_id]
    assert "MAT-01" in await _insumos(contexto_control)

    async with sesion_con_rls(contexto_control) as sesion:
        resultado = await RevertirCargaEnCadena(
            cargas=RepositorioCargasSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        ).ejecutar(materiales.carga_id, usuario_id=contexto_control.usuario_id)

    assert resultado["cargas_revertidas"] == [cpu.carga_id, materiales.carga_id]
    assert "MAT-01" not in await _insumos(contexto_control)
    assert "EST-01" not in await _conceptos(contexto_control)


async def test_eliminar_version_de_cpu_borra_la_retirada_pero_no_la_vigente(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """Mismo mantenimiento directo que en cuadrillas (§10.8), para CPU:
    identificado por versión + variante, no por el id interno de la fila
    (el dominio no lo conoce, §3.3)."""
    from obractrl.application.puertos.repositorios import (
        RegistroNoEncontrado,
        VersionVigenteNoEliminable,
    )

    await _cargar_concepto_y_su_recarga(contexto_control)

    async with sesion_con_rls(contexto_control) as sesion:
        concepto = next(c for c in await RepositorioConceptosSQL(sesion).listar() if str(c["clave"]) == "EST-01")

    async with sesion_con_rls(contexto_control) as sesion:
        with pytest.raises(VersionVigenteNoEliminable):
            await RepositorioConceptosSQL(sesion).eliminar_version_cpu(
                concepto["id"], version=2
            )

    async with sesion_con_rls(contexto_control) as sesion:
        await RepositorioConceptosSQL(sesion).eliminar_version_cpu(concepto["id"], version=1)
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        restantes = await RepositorioConceptosSQL(sesion).versiones_cpu(concepto["id"])
    assert [v["version"] for v in restantes] == [2]

    async with sesion_con_rls(contexto_control) as sesion:
        with pytest.raises(RegistroNoEncontrado):
            await RepositorioConceptosSQL(sesion).eliminar_version_cpu(
                concepto["id"], version=1
            )


# --- Integridad de `_REFERENCIAS_EXTERNAS` (§10.8) ------------------------


async def test_referencias_externas_cubre_toda_fk_sin_cascada_hacia_eliminar() -> None:
    """Tripwire de esquema: si una migración agrega una FK sin cascada hacia
    una tabla de `_ELIMINAR` y nadie la registra en `_REFERENCIAS_EXTERNAS`,
    `dependientes_de` deja de verla en silencio — exactamente el bug real
    que dejó materiales, mano de obra y cuadrillas sin poder revertirse con
    un CPU (o una cuadrilla) ya cargado encima (§10.8). Esta prueba falla en
    vez de repetirlo la próxima vez que el esquema cambie."""
    from obractrl.adapters.repos.cargas_sql import _ELIMINAR, _REFERENCIAS_EXTERNAS

    engine = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with engine.connect() as conn:
            filas = (
                await conn.execute(
                    text(
                        """
                        select tc.table_name as tabla_hija, kcu.column_name as columna,
                               ccu.table_name as tabla_padre
                        from information_schema.table_constraints tc
                        join information_schema.key_column_usage kcu
                            on tc.constraint_name = kcu.constraint_name
                        join information_schema.constraint_column_usage ccu
                            on tc.constraint_name = ccu.constraint_name
                        join information_schema.referential_constraints rc
                            on tc.constraint_name = rc.constraint_name
                        where tc.constraint_type = 'FOREIGN KEY'
                          and ccu.table_name = any(cast(:tablas as text[]))
                          and rc.delete_rule in ('NO ACTION', 'RESTRICT')
                        """
                    ),
                    {"tablas": list(_ELIMINAR.keys())},
                )
            ).mappings().all()
    finally:
        await engine.dispose()

    reales = {(f["tabla_hija"], f["columna"], f["tabla_padre"]) for f in filas}
    faltantes = reales - set(_REFERENCIAS_EXTERNAS)
    assert not faltantes, (
        f"FK sin cascada no registradas en _REFERENCIAS_EXTERNAS: {faltantes} "
        f"(cargas_sql.py). Sin esto, dependientes_de() no las ve y revertir "
        f"puede terminar en IntegrityError crudo o en TablaNoRevertible."
    )


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


async def test_dos_prototipos_con_la_misma_clave_de_concepto_cpu_la_comparten(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """Un `CONCEPTO` real (el "Concepto CPU") se reconoce por su propia
    clave de archivo (`EST-01`) en el catálogo compartido —no namespaceada
    por prototipo, a diferencia de `CONCEPTO_AUXILIAR`/etapa colapsada
    (`_clave_catalogo_concepto`)—: dos prototipos que repiten la misma
    clave comparten la MISMA fila de `concepto`/`cpu`. El segundo que la
    trae ya la encuentra publicada y solo la referencia — el cargador de
    prototipos es una guía, no la fuente de verdad de un `CONCEPTO`."""
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
    # Una sola clave nueva → un solo pendiente por autorizar (§10.3): el
    # segundo prototipo referenció, no volvió a dar de alta.
    assert resultado.pendientes == 1

    conceptos = await _conceptos(contexto_control)
    assert "EST-01" in conceptos

    async with sesion_con_rls(contexto_control) as sesion:
        cpu = await RepositorioConceptosSQL(sesion).versiones_cpu(conceptos["EST-01"]["id"])
    # Solo se publicó una vez: el segundo prototipo referenció, no repitió el alta.
    assert len(cpu) == 1

    prototipos = await _prototipos(contexto_control)
    async with sesion_con_rls(contexto_control) as sesion:
        presupuestos = RepositorioPresupuestosSQL(sesion)
        p10 = await presupuestos.vigente_de_prototipo(prototipos["CAS-10"]["id"])
        p11 = await presupuestos.vigente_de_prototipo(prototipos["CAS-11"]["id"])
        partidas10 = await presupuestos.partidas(p10["id"])
        partidas11 = await presupuestos.partidas(p11["id"])

    assert len(partidas10) == 1 and len(partidas11) == 1
    assert partidas10[0]["concepto_id"] == partidas11[0]["concepto_id"] == conceptos["EST-01"]["id"]
    assert partidas10[0]["precio_unitario"] == partidas11[0]["precio_unitario"]


async def test_una_clave_de_concepto_repetida_en_dos_etapas_del_mismo_prototipo_no_se_pisan(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """Bug real reportado con datos de producción (`CAS-00004`, archivo de 7
    prototipos/8014 filas): `EST-02010` cuelga de dos etapas distintas del
    MISMO prototipo. Antes de `uq_prototipo_nodo_posicion` (migración 0038)
    el `upsert` por `(prototipo_id, clave)` hacía que la segunda ocurrencia
    pisara `parent_id` de la primera — la primera "desaparecía" de su etapa
    en el árbol renderizado, que es justo lo que se reportó."""
    await _con_prototipos(contexto_control, "CAS-20")

    resultado = await _cargar(
        contexto_control,
        TipoCarga.PRESUPUESTO,
        _archivo_presupuesto(
            [
                [1, None, "CAS-20", "Prototipo", None, None, None, None, "PROTOTIPO"],
                [1, "CAS-20", "NIV-1", "Planta baja", None, None, None, None, "NIVEL DE CONSTRUCCION"],
                [1, "NIV-1", "ECO-1", "Muros", None, None, None, None, "ETAPA DE CONSTRUCCION"],
                [1, "ECO-1", "EST-1", "Muro de 14", None, 1, 0, 0, "CONCEPTO"],
                [1, "EST-1", "ACE-01", "Alambre", "KG", 10, 20, None, "MATERIAL"],
                [2, "NIV-1", "ECO-2", "Castillos", None, None, None, None, "ETAPA DE CONSTRUCCION"],
                [1, "ECO-2", "EST-1", "Muro de 14", None, 1, 0, 0, "CONCEPTO"],
                [1, "EST-1", "ACE-01", "Alambre", "KG", 20, 20, None, "MATERIAL"],
            ]
        ),
    )

    assert resultado.estatus is EstatusCarga.APLICADO
    assert resultado.resumen.errores == 0

    prototipo_id = (await _prototipos(contexto_control))["CAS-20"]["id"]
    async with sesion_con_rls(contexto_control) as sesion:
        nodos = await RepositorioPrototipoNodoSQL(sesion).por_prototipo(prototipo_id)

    eco1 = next(n for n in nodos if n["clave"] == "ECO-1")
    eco2 = next(n for n in nodos if n["clave"] == "ECO-2")
    por_clave_y_padre = {(n["clave"], n["parent_id"]): n for n in nodos}

    # Las dos ocurrencias de EST-1 existen, cada una bajo su propia etapa —
    # antes del fix, una de estas dos búsquedas fallaba (KeyError): la fila
    # había sido reparentada a la otra etapa por el upsert colisionado.
    est1_bajo_eco1 = por_clave_y_padre[("EST-1", eco1["id"])]
    est1_bajo_eco2 = por_clave_y_padre[("EST-1", eco2["id"])]
    assert est1_bajo_eco1["id"] != est1_bajo_eco2["id"]
    assert sum(1 for n in nodos if n["clave"] == "EST-1") == 2


async def test_un_insumo_desconocido_en_presupuesto_se_da_de_alta_solo(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """Mismo criterio que `AplicadorCPU` (§7.3, §8.7): un material que no
    cruza en el árbol de ingeniería por prototipo se da de alta solo, con
    lo que trae la fila —clave, descripción, unidad, costo—; no hace falta
    sembrarlo antes con una carga de Materiales."""
    await _con_prototipos(contexto_control, "CAS-90")

    resultado = await _cargar(
        contexto_control,
        TipoCarga.PRESUPUESTO,
        _archivo_presupuesto(_prototipo_simple("CAS-90", "EST-90", 5)),
    )

    assert resultado.estatus is EstatusCarga.APLICADO
    assert resultado.resumen.errores == 0
    # No se omite (§10.3): se da de alta igual, pero pendiente de autorizar.
    assert resultado.pendientes == 1

    assert "EST-90" in await _conceptos(contexto_control)

    alambre = (await _insumos(contexto_control))["ACE-01"]
    assert alambre["tipo"] == "material"
    assert alambre["descripcion"] == "Alambre"
    assert alambre["costo_base"] == Decimal("20.0000")
    # "KG" tampoco estaba sembrada: se dio de alta sola (§8.7).
    assert "KG" in await _unidades(contexto_control)


async def test_concepto_ya_publicado_se_referencia_aunque_la_fila_traiga_otra_composicion(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """Un `CONCEPTO` real con CPU vigente no se compara ni disputa (a
    diferencia de `CONCEPTO_AUXILIAR`/etapa colapsada, que sí — ver
    `test_etapa_colapsada_con_cantidades_distintas_no_es_conflicto`): el
    cargador de prototipos es una guía, no la fuente de verdad, así que
    una composición distinta en la fila del segundo prototipo (9 kg vs 5
    kg) simplemente se ignora — nunca genera `CONCEPTO_EN_CONFLICTO`, y su
    partida usa el precio ya vigente del primero."""
    await _con_insumo_alambre(contexto_control)
    await _con_prototipos(contexto_control, "CAS-20", "CAS-21")

    resultado = await _cargar(
        contexto_control,
        TipoCarga.PRESUPUESTO,
        _archivo_presupuesto(
            [
                *_prototipo_simple("CAS-20", "EST-02", 5),
                *_prototipo_simple("CAS-21", "EST-02", 9),
            ]
        ),
    )

    assert resultado.resumen.errores == 0
    # Un solo pendiente CPU_NUEVO (el alta de "EST-02" en el primer
    # prototipo, §10.3) — nunca CONCEPTO_EN_CONFLICTO: la fila del segundo
    # ni se compara.
    assert resultado.pendientes == 1
    async with sesion_con_rls(contexto_control) as sesion:
        bandeja = await RepositorioCargasSQL(sesion).listar_pendientes(carga_id=resultado.carga_id)
    assert not [b for b in bandeja if b["tipo"] == str(TipoPendiente.CONCEPTO_EN_CONFLICTO)]
    assert [b["tipo"] for b in bandeja] == [str(TipoPendiente.CPU_NUEVO)]

    conceptos = await _conceptos(contexto_control)
    async with sesion_con_rls(contexto_control) as sesion:
        cpu = await RepositorioConceptosSQL(sesion).versiones_cpu(conceptos["EST-02"]["id"])
    # Una sola versión: la fila de 9 kg del segundo prototipo no publicó la suya.
    assert len(cpu) == 1
    assert cpu[0]["precio_unitario"] == Decimal("100.0000")  # 5 kg × $20

    prototipos = await _prototipos(contexto_control)
    async with sesion_con_rls(contexto_control) as sesion:
        presupuestos = RepositorioPresupuestosSQL(sesion)
        p20 = await presupuestos.vigente_de_prototipo(prototipos["CAS-20"]["id"])
        p21 = await presupuestos.vigente_de_prototipo(prototipos["CAS-21"]["id"])
        partida20 = (await presupuestos.partidas(p20["id"]))[0]
        partida21 = (await presupuestos.partidas(p21["id"]))[0]

    # Mismo precio para los dos: el segundo referenció el CPU del primero.
    assert partida20["precio_unitario"] == partida21["precio_unitario"] == Decimal("100.0000")


# --- Bandeja: aprobar/rechazar un pendiente (§10.3) -----------------------


async def test_aprobar_un_cpu_nuevo_de_concepto_solo_cierra_el_pendiente(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    from obractrl.application.casos_uso.gestionar_carga import ResolverPendiente

    await _con_insumo_alambre(contexto_control)
    await _con_prototipos(contexto_control, "CAS-94")
    resultado = await _cargar(
        contexto_control,
        TipoCarga.PRESUPUESTO,
        _archivo_presupuesto(_prototipo_simple("CAS-94", "EST-94", 5)),
    )
    async with sesion_con_rls(contexto_control) as sesion:
        bandeja = await RepositorioCargasSQL(sesion).listar_pendientes(carga_id=resultado.carga_id)
    pendiente_id = bandeja[0]["id"]

    async with sesion_con_rls(contexto_control) as sesion:
        fila = await ResolverPendiente(
            cargas=RepositorioCargasSQL(sesion),
            conceptos=RepositorioConceptosSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
        ).ejecutar(pendiente_id, usuario_id=contexto_control.usuario_id, aprobado=True)

    assert fila["resuelto"] is True
    assert fila["resolucion"]["accion"] == "aprobado"
    assert (await _conceptos(contexto_control))["EST-94"]["estatus"] == "activo"


async def test_rechazar_un_cpu_nuevo_de_concepto_lo_da_de_baja(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    from obractrl.application.casos_uso.gestionar_carga import ResolverPendiente

    await _con_insumo_alambre(contexto_control)
    await _con_prototipos(contexto_control, "CAS-95")
    resultado = await _cargar(
        contexto_control,
        TipoCarga.PRESUPUESTO,
        _archivo_presupuesto(_prototipo_simple("CAS-95", "EST-95", 5)),
    )
    async with sesion_con_rls(contexto_control) as sesion:
        bandeja = await RepositorioCargasSQL(sesion).listar_pendientes(carga_id=resultado.carga_id)
    pendiente_id = bandeja[0]["id"]

    async with sesion_con_rls(contexto_control) as sesion:
        fila = await ResolverPendiente(
            cargas=RepositorioCargasSQL(sesion),
            conceptos=RepositorioConceptosSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
        ).ejecutar(pendiente_id, usuario_id=contexto_control.usuario_id, aprobado=False)

    assert fila["resolucion"]["accion"] == "rechazado"
    # Inactivo, no borrado: sigue editable desde el catálogo (§10.3).
    concepto = (await _conceptos(contexto_control))["EST-95"]
    assert concepto["estatus"] == "inactivo"
    assert concepto["descripcion"] == "Losa"


async def test_resolver_un_pendiente_ya_resuelto_no_se_pisa(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    from obractrl.application.casos_uso.gestionar_carga import (
        PendienteNoResoluble,
        ResolverPendiente,
    )

    await _con_insumo_alambre(contexto_control)
    await _con_prototipos(contexto_control, "CAS-96")
    resultado = await _cargar(
        contexto_control,
        TipoCarga.PRESUPUESTO,
        _archivo_presupuesto(_prototipo_simple("CAS-96", "EST-96", 5)),
    )
    async with sesion_con_rls(contexto_control) as sesion:
        bandeja = await RepositorioCargasSQL(sesion).listar_pendientes(carga_id=resultado.carga_id)
    pendiente_id = bandeja[0]["id"]

    async with sesion_con_rls(contexto_control) as sesion:
        resolver = ResolverPendiente(
            cargas=RepositorioCargasSQL(sesion),
            conceptos=RepositorioConceptosSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
        )
        await resolver.ejecutar(pendiente_id, usuario_id=contexto_control.usuario_id, aprobado=True)
        with pytest.raises(PendienteNoResoluble):
            await resolver.ejecutar(
                pendiente_id, usuario_id=contexto_control.usuario_id, aprobado=False
            )
    # La segunda llamada no pisó la primera: sigue aprobado, el concepto activo.
    assert (await _conceptos(contexto_control))["EST-96"]["estatus"] == "activo"


async def test_presupuesto_referencia_el_precio_del_catalogo_de_cpu_sin_recalcularlo(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """El árbol de ingeniería por prototipo reconoce la clave de un
    `CONCEPTO` ya publicado por "Conceptos CPU" (§10.6, `AplicadorCPU`) y
    la usa tal cual: la fila de este archivo (999 kg de alambre) es solo
    una guía —ni se procesa, ni pisa el CPU vigente— porque publicar una
    versión de un `CONCEPTO` real es trabajo exclusivo del cargador
    "Conceptos CPU", este solo referencia."""
    await _sembrar_insumos(contexto_control)
    await _cargar(
        contexto_control,
        TipoCarga.CPU,
        _archivo_cpu(
            [
                _fila_cpu("EST-50", "EST-50", "Muro de block", "ton", tipo="Concepto"),
                _fila_cpu(insumo="MAT-01", cantidad="10", pu="20", tipo="Material"),
            ]
        ),
    )
    concepto_cpu_id = (await _conceptos(contexto_control))["EST-50"]["id"]
    async with sesion_con_rls(contexto_control) as sesion:
        cpu_del_catalogo = await RepositorioConceptosSQL(sesion).versiones_cpu(concepto_cpu_id)
    assert cpu_del_catalogo[0]["precio_unitario"] == Decimal("200.0000")

    await _con_insumo_alambre(contexto_control)
    await _con_prototipos(contexto_control, "CAS-93")

    resultado = await _cargar(
        contexto_control,
        TipoCarga.PRESUPUESTO,
        _archivo_presupuesto(
            [
                [1, None, "CAS-93", "Prototipo", None, None, None, None, "PROTOTIPO"],
                [1, "CAS-93", "NIV-1", "Cimentación", None, None, None, None, "NIVEL DE CONSTRUCCION"],
                [1, "NIV-1", "ECO-1", "Estructura", None, None, None, None, "ETAPA DE CONSTRUCCION"],
                [1, "ECO-1", "EST-50", "Muro de block", None, 1, 0, 0, "CONCEPTO"],
                [1, "EST-50", "ACE-01", "Alambre", "KG", 999, 1, None, "MATERIAL"],
            ]
        ),
    )

    assert resultado.resumen.errores == 0
    assert resultado.pendientes == 0  # se ignora la fila, no se compara

    conceptos = await _conceptos(contexto_control)

    # El catálogo de CPU sigue exactamente igual: ni una versión nueva.
    async with sesion_con_rls(contexto_control) as sesion:
        cpu_despues = await RepositorioConceptosSQL(sesion).versiones_cpu(concepto_cpu_id)
    assert len(cpu_despues) == 1
    assert cpu_despues[0]["precio_unitario"] == Decimal("200.0000")

    # ...y el árbol referencia el MISMO concepto, sin namespacear.
    assert conceptos["EST-50"]["id"] == concepto_cpu_id

    prototipos = await _prototipos(contexto_control)
    async with sesion_con_rls(contexto_control) as sesion:
        presupuestos = RepositorioPresupuestosSQL(sesion)
        version = await presupuestos.vigente_de_prototipo(prototipos["CAS-93"]["id"])
        partida = (await presupuestos.partidas(version["id"]))[0]
    # El precio es el del catálogo de CPU (200), no el de la fila (999×1=999).
    assert partida["concepto_id"] == concepto_cpu_id
    assert partida["precio_unitario"] == Decimal("200.0000")


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
    # Namespaceado por prototipo en el catálogo compartido (ver el siguiente
    # test): la clave de archivo sola no basta como clave de `concepto`.
    assert "ECO-99~CAS-30" in conceptos


async def test_etapa_colapsada_con_cantidades_distintas_no_es_conflicto(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """La etapa sin concepto intermedio (test anterior) es la forma NORMAL
    del archivo real, y su clave se repite igual en cada prototipo — pero
    la cantidad de material que trae cada uno varía a propósito
    (dosificación distinta), no es un desacuerdo que resolver. Antes de
    namespacear por prototipo (`_clave_catalogo_concepto`) esto generaba un
    falso `CONCEPTO_EN_CONFLICTO` en la mayoría de las filas de un archivo
    real."""
    await _con_insumo_alambre(contexto_control)
    await _con_prototipos(contexto_control, "CAS-31", "CAS-32")

    resultado = await _cargar(
        contexto_control,
        TipoCarga.PRESUPUESTO,
        _archivo_presupuesto(
            [
                *_etapa_colapsada("CAS-31", "ECO-99", 5),
                *_etapa_colapsada("CAS-32", "ECO-99", 9),
            ]
        ),
    )

    assert resultado.resumen.errores == 0
    async with sesion_con_rls(contexto_control) as sesion:
        bandeja = await RepositorioCargasSQL(sesion).listar_pendientes(carga_id=resultado.carga_id)
    assert not [b for b in bandeja if b["tipo"] == str(TipoPendiente.CONCEPTO_EN_CONFLICTO)]

    conceptos = await _conceptos(contexto_control)
    assert {"ECO-99~CAS-31", "ECO-99~CAS-32"} <= set(conceptos)
    assert conceptos["ECO-99~CAS-31"]["id"] != conceptos["ECO-99~CAS-32"]["id"]

    prototipos = await _prototipos(contexto_control)
    async with sesion_con_rls(contexto_control) as sesion:
        presupuestos = RepositorioPresupuestosSQL(sesion)
        p31 = await presupuestos.vigente_de_prototipo(prototipos["CAS-31"]["id"])
        p32 = await presupuestos.vigente_de_prototipo(prototipos["CAS-32"]["id"])
        partida31 = (await presupuestos.partidas(p31["id"]))[0]
        partida32 = (await presupuestos.partidas(p32["id"]))[0]

    # Cada prototipo con su propio precio (5 kg vs 9 kg de alambre a 20).
    assert partida31["precio_unitario"] != partida32["precio_unitario"]


async def test_recargar_una_etapa_colapsada_conserva_su_concepto_namespaceado(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """El namespaceo por prototipo (test anterior) no debe volverse un alta
    nueva en cada recarga: debe resolver siempre al MISMO `concepto`."""
    await _con_insumo_alambre(contexto_control)
    await _con_prototipos(contexto_control, "CAS-33")

    await _cargar(
        contexto_control,
        TipoCarga.PRESUPUESTO,
        _archivo_presupuesto(_etapa_colapsada("CAS-33", "ECO-99", 5)),
    )
    id_v1 = (await _conceptos(contexto_control))["ECO-99~CAS-33"]["id"]

    resultado = await _cargar(
        contexto_control,
        TipoCarga.PRESUPUESTO,
        _archivo_presupuesto(_etapa_colapsada("CAS-33", "ECO-99", 7)),
    )

    assert resultado.pendientes == 0  # recarga propia: actualización legítima, no conflicto
    id_v2 = (await _conceptos(contexto_control))["ECO-99~CAS-33"]["id"]
    assert id_v2 == id_v1


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
    assert "EST-08" in await _conceptos(contexto_control)

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


async def test_presupuesto_divide_la_cantidad_del_hijo_entre_la_del_concepto(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """La `CANTIDAD` del árbol es absoluta para ese nodo del prototipo, no
    ya rendimiento por unidad (§7.3, §10.6): con un concepto de 250
    unidades y 500 kg de material a $20, el PU real es (500/250) × 20 =
    $40 — no 500 × 20, que es lo que daría usar la cantidad del hijo tal
    cual (el bug real: ningún test anterior lo veía porque todos usaban
    cantidad=1 en el concepto, y dividir entre 1 es un no-op)."""
    await _con_insumo_alambre(contexto_control)
    await _con_prototipos(contexto_control, "CAS-91")

    resultado = await _cargar(
        contexto_control,
        TipoCarga.PRESUPUESTO,
        _archivo_presupuesto(
            [
                [1, None, "CAS-91", "Prototipo", None, None, None, None, "PROTOTIPO"],
                [1, "CAS-91", "NIV-1", "Cimentación", None, None, None, None, "NIVEL DE CONSTRUCCION"],
                [1, "NIV-1", "ECO-1", "Estructura", None, None, None, None, "ETAPA DE CONSTRUCCION"],
                [1, "ECO-1", "EST-11", "Losa", None, 250, 0, 0, "CONCEPTO"],
                [1, "EST-11", "ACE-01", "Alambre", "KG", 500, 20, None, "MATERIAL"],
            ]
        ),
    )

    assert resultado.estatus is EstatusCarga.APLICADO
    assert resultado.resumen.errores == 0

    conceptos = await _conceptos(contexto_control)
    async with sesion_con_rls(contexto_control) as sesion:
        versiones = await RepositorioConceptosSQL(sesion).versiones_cpu(
            conceptos["EST-11"]["id"]
        )
    assert versiones[0]["precio_unitario"] == Decimal("40.0000")


async def test_presupuesto_suma_conceptos_y_auxiliares_de_la_misma_etapa(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """`CONCEPTO` y `CONCEPTO AUXILIAR` cuelgan igual de una etapa: cada uno
    da de alta su propio `concepto`/`cpu` y su propia partida — el total del
    prototipo es la suma de las dos, "aparecen todos" (§7.3, §7.4)."""
    await _con_insumo_alambre(contexto_control)
    await _con_prototipos(contexto_control, "CAS-92")

    resultado = await _cargar(
        contexto_control,
        TipoCarga.PRESUPUESTO,
        _archivo_presupuesto(
            [
                [1, None, "CAS-92", "Prototipo", None, None, None, None, "PROTOTIPO"],
                [1, "CAS-92", "NIV-1", "Cimentación", None, None, None, None, "NIVEL DE CONSTRUCCION"],
                [1, "NIV-1", "ECO-1", "Estructura", None, None, None, None, "ETAPA DE CONSTRUCCION"],
                [1, "ECO-1", "EST-12", "Losa", None, 10, 0, 0, "CONCEPTO"],
                [1, "EST-12", "ACE-01", "Alambre", "KG", 20, 20, None, "MATERIAL"],
                [1, "ECO-1", "AUX-01", "Cimbra", None, 5, 0, 0, "CONCEPTO AUXILIAR"],
                [1, "AUX-01", "ACE-01", "Alambre", "KG", 15, 20, None, "MATERIAL"],
            ]
        ),
    )

    assert resultado.estatus is EstatusCarga.APLICADO
    assert resultado.resumen.errores == 0

    conceptos = await _conceptos(contexto_control)
    assert {"EST-12", "AUX-01~CAS-92"} <= set(conceptos)
    assert conceptos["AUX-01~CAS-92"]["tipo"] == "auxiliar"

    prototipos = await _prototipos(contexto_control)
    async with sesion_con_rls(contexto_control) as sesion:
        presupuestos = RepositorioPresupuestosSQL(sesion)
        version = await presupuestos.vigente_de_prototipo(prototipos["CAS-92"]["id"])
        partidas = await presupuestos.partidas(version["id"])

    # EST-12: (20/10)×20 = 40 de PU × 10 = 400. AUX-01: (15/5)×20 = 60 de PU × 5 = 300.
    assert {p["concepto_id"] for p in partidas} == {
        conceptos["EST-12"]["id"],
        conceptos["AUX-01~CAS-92"]["id"],
    }
    assert sum(Decimal(str(p["importe"])) for p in partidas) == Decimal("700.0000")
    assert version["monto_total"] == Decimal("700.0000")


# --- Un solo tipo de carga, dos formatos de archivo ----------------------


async def test_el_arbol_de_ingenieria_se_carga_bajo_el_tipo_prototipos(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """El formato lo dice el archivo, no el desplegable.

    Antes había que acertarle al tipo antes de subir: el árbol bajo
    "Prototipos" moría con "faltan las columnas obligatorias
    proyecto_clave, clave, nombre". Ahora los dos formatos entran por el
    mismo tipo y `CargadorPrototipos` reconoce cuál llegó.
    """
    await _con_insumo_alambre(contexto_control)
    await _con_prototipos(contexto_control, "CAS-80")

    resultado = await _cargar(
        contexto_control,
        TipoCarga.PROTOTIPOS,  # el tipo del alta plana, con el archivo del árbol
        _archivo_presupuesto(_prototipo_simple("CAS-80", "EST-09", 5)),
    )

    assert resultado.estatus is EstatusCarga.APLICADO
    assert resultado.resumen.errores == 0
    assert "EST-09" in await _conceptos(contexto_control)

    prototipos = await _prototipos(contexto_control)
    assert set(await _nodos_de(contexto_control, prototipos["CAS-80"]["id"])) == {
        "NIV-1",
        "ECO-1",
        "EST-09",
    }


async def test_el_alta_plana_sigue_funcionando_bajo_el_mismo_tipo(
    catalogos: Catalogos, contexto_control: ContextoSesion
) -> None:
    """La otra mitad de la detección: el archivo plano no se confunde con
    el árbol ni pierde su camino."""
    resultado = await _cargar(
        contexto_control,
        TipoCarga.PROTOTIPOS,
        _archivo_prototipos([["PROY", "CAS-81", "Casa plana", "90", "2", "3"]]),
    )

    assert resultado.resumen.errores == 0
    assert resultado.resumen.insertados == 1
    catalogo = await _prototipos(contexto_control)
    assert catalogo["CAS-81"]["nombre"] == "Casa plana"
