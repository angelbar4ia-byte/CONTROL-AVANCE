"""Reglas de los cargadores de datos, sin tocar disco ni base.

Spec §8.6 (sinónimos) · §9.3 (reporte por fila) · §10.2 (modos y dedup) ·
§10.3 (bandeja y homologación) · §10.5 (signo e IVA) · §10.6 (cabeceras) ·
§10.8 (diff y versión).

El dominio de los cargadores es puro (§12.11): estas pruebas le pasan filas
como listas de celdas —lo que el lector entregaría— y verifican qué sale
válido, qué sale como error de fila y qué cae en la bandeja. Ningún `.xlsx`
de por medio; eso lo cubre `tests/integracion/test_cargas_endtoend.py`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from obractrl.domain.cargadores.almacen import (
    clave_de_obra,
    concepto_de_referencia,
    importe_con_iva,
    validar_movimiento,
)
from obractrl.domain.cargadores.cabeceras import (
    ALMACEN,
    CONCEPTOS_BASE,
    CUADRILLAS,
    MANO_DE_OBRA,
    MAPA_CPU,
    MATERIALES,
    PRESUPUESTO,
    PROTOTIPOS,
    ErrorDeCabecera,
    indice_de_letra,
    resolver_encabezados,
)
from obractrl.domain.cargadores.claves_automaticas import generar_clave_automatica
from obractrl.domain.cargadores.conceptos_base import validar_concepto_base
from obractrl.domain.cargadores.cpu import agrupar_conceptos
from obractrl.domain.cargadores.cuadrillas import agrupar_cuadrillas
from obractrl.domain.cargadores.homologacion import Homologador
from obractrl.domain.cargadores.mano_de_obra import validar_mano_obra
from obractrl.domain.cargadores.materiales import validar_material
from obractrl.domain.cargadores.presupuesto import (
    TipoNodoPresupuesto,
    construir_arboles,
    es_etapa_con_componentes_directos,
)
from obractrl.domain.cargadores.prototipos import validar_prototipo
from obractrl.domain.cargadores.reporte import ErrorEnFila, TipoPendiente
from obractrl.domain.cargadores.versionado import diferenciar
from obractrl.domain.shared.diccionario import CategoriaExplosion, ModoCarga, TipoInsumo
from obractrl.domain.shared.normalizacion import (
    ValorNoConvertible,
    a_booleano,
    a_decimal,
    a_fecha,
    canonizar_encabezado,
    similar,
)

# --- Normalización de encabezados y valores (§8.6) -----------------------


@pytest.mark.parametrize(
    ("crudo", "esperado"),
    [
        ("  Descripción ", "descripcion"),
        ("DESCRIPCION", "descripcion"),
        ("P.U.", "precio_unitario"),
        ("Código", "clave"),
        ("# Parte", "clave"),
        ("U", "unidad"),
        ("Vol.", "cantidad"),
        ("Rend.", "rendimiento"),
    ],
)
def test_canoniza_los_alias_del_diccionario(crudo: str, esperado: str) -> None:
    """El §8.6 es el mapa; la normalización solo lo hace comparable."""
    assert canonizar_encabezado(crudo) == esperado


def test_un_encabezado_desconocido_no_se_adivina() -> None:
    """Sin entrada en el §8.6 no hay mapeo: se ignora, no se aproxima."""
    assert canonizar_encabezado("Columna que nadie definió") is None


@pytest.mark.parametrize(
    ("celda", "esperado"),
    [
        ("1,250.50", Decimal("1250.50")),
        ("$ 1,250.50", Decimal("1250.50")),
        ("(1,250.50)", Decimal("-1250.50")),  # paréntesis contable
        (1250, Decimal(1250)),
        (Decimal("0.5"), Decimal("0.5")),
    ],
)
def test_lee_numeros_como_los_exporta_excel(celda: object, esperado: Decimal) -> None:
    assert a_decimal(celda, campo="costo") == esperado


def test_un_texto_que_no_es_numero_es_error_de_valor() -> None:
    with pytest.raises(ValorNoConvertible, match="costo"):
        a_decimal("mil pesos", campo="costo")


def test_la_fecha_ambigua_se_lee_en_formato_mexicano() -> None:
    """``03/04/2026`` es 3 de abril: interpretar mes/día sería inventar."""
    assert a_fecha("03/04/2026", campo="fecha") == date(2026, 4, 3)


def test_la_casilla_de_iva_acepta_las_formas_del_archivo() -> None:
    assert a_booleano("SÍ", campo="iva") is True
    assert a_booleano("X", campo="iva") is True
    assert a_booleano("NO", campo="iva") is False


# --- Cabeceras: el contrato del §10.6 ------------------------------------


def test_las_columnas_del_cpu_van_por_letra() -> None:
    """El §10.6 fija el archivo de CPU por letra: A=0 … I=8."""
    assert indice_de_letra("A") == 0
    assert indice_de_letra("I") == 8
    assert MAPA_CPU.indices == {
        "clave": 0,
        "clave_insumo": 1,
        "descripcion": 2,
        "unidad": 3,
        "cantidad": 4,
        "precio_unitario": 5,
        "familia": 7,
        "tipo": 8,
    }


def test_falta_una_columna_obligatoria_y_el_archivo_se_rechaza() -> None:
    """Sin clave no hay con qué cruzar (§3.3): es error del archivo, no de fila."""
    with pytest.raises(ErrorDeCabecera, match="clave"):
        resolver_encabezados(["Descripción", "Unidad"], MATERIALES)


def test_el_alias_del_archivo_gana_sobre_el_mapa_global() -> None:
    """`Parte` es la descripción en el archivo de almacén (§10.6), aunque el
    §8.6 también mapee `Concepto` a descripción."""
    mapa = resolver_encabezados(
        ["# Parte", "Concepto", "Parte", "Ubicacion", "Lote", "Fecha", "Motivo", "Efecto Qty"],
        ALMACEN,
    )
    assert mapa.indices["descripcion"] == 2
    assert mapa.indices["clave"] == 0
    assert "Concepto" in mapa.ignoradas


def test_dos_columnas_igual_de_fuertes_al_mismo_campo_es_ambiguedad() -> None:
    """Adivinar cuál vale es justo lo que el §3.3 prohíbe."""
    with pytest.raises(ErrorDeCabecera, match="apuntan las dos"):
        resolver_encabezados(["Clave", "Descripción", "Concepto"], MATERIALES)


def test_las_columnas_que_el_contrato_no_nombra_se_ignoran_sin_romper() -> None:
    """El archivo de almacén trae 46 columnas y el §10.6 nombra 16."""
    mapa = resolver_encabezados(
        ["# Parte", "Parte", "Ubicacion", "Lote", "Fecha", "Motivo", "Efecto Qty", "Columna X"],
        ALMACEN,
    )
    assert mapa.ignoradas == ("Columna X",)


# --- Materiales (§10.6 `CABECERAS_MATERIALES.xlsx`) ----------------------

_MAPA_MATERIALES = resolver_encabezados(
    ["Clave", "Descripción", "Unidad", "Clase", "Costo base", "C/Último", "IVA"],
    MATERIALES,
)


def test_una_fila_de_material_completa_queda_validada() -> None:
    material = validar_material(
        ["cem-01", " Cemento  gris ", "ton", "CEM", "250.5", "260", "SI"],
        _MAPA_MATERIALES,
        7,
    )
    assert material.llave == "CEM-01"  # `Clave` normaliza (§3.3)
    assert material.descripcion == "Cemento gris"
    assert material.costo_base == Decimal("250.5")
    assert material.costo_ultimo == Decimal("260")
    assert material.iva is True
    assert material.fila == 7


def test_costo_base_m_n_del_archivo_real_alimenta_costo_base() -> None:
    """El archivo real de producción no dice "Costo base": dice "COSTO BASE
    M.N." (moneda nacional). "COSTO BASE M.E." (moneda extranjera) y "COSTO
    UNITARIO" quedan sin mapear a propósito — dos alias al mismo campo
    canónico son ambigüedad real (§8.6), no un costo de más que capturar."""
    mapa = resolver_encabezados(
        [
            "CLAVE",
            "DESCRIPCIÓN",
            "CLAVE UNIDAD",
            "UNIDAD",
            "COSTO BASE M.N.",
            "COSTO BASE M.E.",
            "COSTO UNITARIO",
            "FECHA",
            "FAMILIA",
        ],
        MATERIALES,
    )
    material = validar_material(
        ["ACE-00001", "ALAMBRE RECOCIDO", 1, "KG", "24.68", "0", "24.68", None, "Aceros"],
        mapa,
        2,
    )
    assert material.costo_base == Decimal("24.68")
    assert material.unidad == "KG"
    assert material.familia == "Aceros"


def test_una_fila_sin_clave_es_error_de_fila_y_no_de_archivo() -> None:
    with pytest.raises(ErrorEnFila) as capturado:
        validar_material(["", "Cemento", "ton", "CEM", "250", "", ""], _MAPA_MATERIALES, 3)
    assert capturado.value.con_fila(3).columna == "clave"


def test_un_costo_negativo_no_entra_al_catalogo() -> None:
    with pytest.raises(ErrorEnFila, match="negativo"):
        validar_material(
            ["CEM-01", "Cemento", "ton", "CEM", "-1", "", ""], _MAPA_MATERIALES, 4
        )


def test_una_columna_ausente_queda_en_none_no_en_cero() -> None:
    """``None`` = "el archivo no lo trae"; cero sería un dato (§10.2)."""
    mapa = resolver_encabezados(["Clave", "Descripción"], MATERIALES)
    material = validar_material(["CEM-01", "Cemento gris"], mapa, 2)
    assert material.costo_base is None
    assert material.iva is None


# --- Catálogo base de conceptos (§8.7 `CABECERAS_CONCEPTOS.xlsx`) --------

_MAPA_CONCEPTOS_BASE = resolver_encabezados(["Clave", "Descripción", "Unidad"], CONCEPTOS_BASE)


def test_una_fila_de_concepto_base_completa_queda_validada() -> None:
    concepto = validar_concepto_base(
        ["EST-01", " Muro de block  hueco ", "m2"], _MAPA_CONCEPTOS_BASE, 5
    )
    assert concepto.llave == "EST-01"  # `Clave` normaliza (§3.3)
    assert concepto.descripcion == "Muro de block hueco"
    assert concepto.unidad == "m2"
    assert concepto.fila == 5


def test_concepto_base_sin_unidad_queda_en_none() -> None:
    concepto = validar_concepto_base(["EST-02", "Losa de azotea", ""], _MAPA_CONCEPTOS_BASE, 6)
    assert concepto.unidad is None


def test_concepto_base_sin_descripcion_es_error_de_fila() -> None:
    """Sin descripción no hay con qué identificar el concepto (§10.1),
    aunque sí traiga clave."""
    with pytest.raises(ErrorEnFila, match="descripcion"):
        validar_concepto_base(["EST-03", "", "m2"], _MAPA_CONCEPTOS_BASE, 7)


def test_concepto_base_sin_clave_no_se_rechaza() -> None:
    """A diferencia de materiales, una clave vacía no es error aquí: el
    usuario pidió que un catálogo base sin clave se numere solo (§8.7). La
    fila queda con ``clave=None`` — quien numera es el aplicador, que sí
    conoce el catálogo vigente (este módulo es puro, §12.11)."""
    concepto = validar_concepto_base(["", "Trabe de cimentación", "ml"], _MAPA_CONCEPTOS_BASE, 8)
    assert concepto.clave is None
    assert concepto.llave == "__sin_clave__8"


def test_dos_conceptos_base_sin_clave_no_se_confunden_en_el_dedup() -> None:
    """`llave` usa el renglón cuando no hay clave: dos filas sin clave son
    dos candidatos a numerar, no "la misma fila repetida" (§10.2)."""
    primero = validar_concepto_base(["", "Trabe A", "ml"], _MAPA_CONCEPTOS_BASE, 8)
    segundo = validar_concepto_base(["", "Trabe B", "ml"], _MAPA_CONCEPTOS_BASE, 9)
    assert primero.llave != segundo.llave


# --- Clave automática (§8.7: catálogo base sin indicador de clave) -------


def test_clave_automatica_empieza_en_00001_sin_precedentes() -> None:
    assert generar_clave_automatica("FAM", []) == "FAM-00001"


def test_clave_automatica_sigue_el_consecutivo_mas_alto() -> None:
    assert (
        generar_clave_automatica("FAM", ["FAM-00001", "FAM-00007", "FAM-00003"]) == "FAM-00008"
    )


def test_clave_automatica_ignora_claves_de_otro_prefijo() -> None:
    """Una clave `CUA-00042` no compite por el consecutivo de `FAM` — son
    catálogos distintos aunque compartan la forma."""
    assert generar_clave_automatica("FAM", ["CUA-00042", "FAM-00001"]) == "FAM-00002"


# --- Similitud de descripciones (§8.7: homologación con alerta) ----------


def test_dos_descripciones_identicas_normalizadas_son_similares() -> None:
    assert similar("Muro de Block", "  muro   de block ") is True


def test_dos_descripciones_claramente_distintas_no_son_similares() -> None:
    assert similar("Muro de block", "Losa de azotea") is False


def test_una_descripcion_con_una_palabra_de_menos_sigue_siendo_similar() -> None:
    assert similar("Muro de block", "Muro block") is True


def test_una_descripcion_abreviada_es_similar_a_la_completa() -> None:
    """Caso real: un renglón de componente de CPU trae "Block" para el
    mismo insumo que el catálogo describe como "Block de concreto" — es
    menos texto, no un insumo distinto que alertar."""
    assert similar("Block", "Block de concreto") is True


# --- Mano de obra / Destajos (§10.6 `CABECERAS_MANO_DE_OBRA.xlsx`) --------

_MAPA_MANO_OBRA = resolver_encabezados(
    [
        "TIPO",
        "CLAVE USUARIO",
        "CLAVE",
        "DESCTRIPCIÓN",
        "CLAVE UNIDAD",
        "UNIDAD",
        "CUADRILLA",
        "RENDIMIENTO TEORICO",
        "RENDIMIENTO REAL",
        "COSTO UNITARIO",
        "FAMILIA",
    ],
    MANO_DE_OBRA,
)


def test_una_fila_de_mano_de_obra_completa_queda_validada() -> None:
    """``DESCTRIPCIÓN`` es el typo real del archivo, no del test (§10.6)."""
    destajo = validar_mano_obra(
        [
            "Individual",
            "US-001",
            "dest-01",
            " Aplanado fino ",
            "UN-01",
            "m2",
            "CUAD-01",
            "12.5",
            None,
            "85.30",
            "Acabados",
        ],
        _MAPA_MANO_OBRA,
        9,
    )
    assert destajo.llave == "DEST-01"
    assert destajo.descripcion == "Aplanado fino"
    assert destajo.unidad == "m2"
    assert destajo.familia == "Acabados"
    assert destajo.cuadrilla == "CUAD-01"
    assert destajo.rendimiento_teorico == Decimal("12.5")
    assert destajo.costo_base == Decimal("85.30")
    assert destajo.tipo == TipoInsumo.MANO_OBRA
    assert destajo.fila == 9


def test_mano_de_obra_con_tipo_subcontrato_queda_marcada_como_tal() -> None:
    """`catalogo_de_SUBCONTRATOS.xlsx` reusa este validador vía
    `functools.partial(validar_mano_obra, tipo=SUBCONTRATO)` (§10.6):
    ``tipo`` no lo trae la fila, lo fija quien llama."""
    subcontrato = validar_mano_obra(
        ["Subcontrato", "US-01", "sub-001", "Instalación eléctrica"],
        resolver_encabezados(["TIPO", "CLAVE USUARIO", "CLAVE", "DESCTRIPCIÓN"], MANO_DE_OBRA),
        1,
        tipo=TipoInsumo.SUBCONTRATO,
    )
    assert subcontrato.tipo == TipoInsumo.SUBCONTRATO


def test_mano_de_obra_sin_rendimiento_queda_en_none_no_en_cero() -> None:
    mapa = resolver_encabezados(["CLAVE", "DESCTRIPCIÓN"], MANO_DE_OBRA)
    destajo = validar_mano_obra(["dest-02", "Pintura"], mapa, 2)
    assert destajo.rendimiento_teorico is None
    assert destajo.cuadrilla is None
    assert destajo.costo_base is None


def test_mano_de_obra_sin_clave_es_error_de_fila() -> None:
    with pytest.raises(ErrorEnFila) as capturado:
        validar_mano_obra(["", "Pintura"], _MAPA_MANO_OBRA, 3)
    assert capturado.value.con_fila(3).columna == "clave"


def test_mano_de_obra_con_rendimiento_negativo_es_error() -> None:
    with pytest.raises(ErrorEnFila, match="negativo"):
        validar_mano_obra(
            [
                None, None, "dest-03", "Pintura", None, "m2", None, "-1", None, None, None,
            ],
            _MAPA_MANO_OBRA,
            4,
        )


# --- Cuadrillas (§10.6 `CABECERAS_CUADRILLAS.xlsx`) -----------------------

_MAPA_CUADRILLAS = resolver_encabezados(
    ["Clave cuadrilla", "Clave", "Descripción", "Unidad", "Cantidad", "PU", "IMPORTE"],
    CUADRILLAS,
)


def test_una_cuadrilla_completa_agrupa_cabecera_e_integrantes() -> None:
    filas = [
        (2, ["CUA0001", "CUA0001", "Cuadrilla (Oficial + Ayudante)", "jor", None, 1584, None]),
        (3, ["CUA0001", "MOOP-0049", "Oficial Albañil", "jor", 1, 840, 840]),
        (4, ["CUA0001", "MOOP-0026", "Ayudante general", "jor", 1, 600, 600]),
        (5, ["CUA0001", "MOOP-0079", "Contratista", "%mo", "0.1", 1440, 144]),
    ]
    bloques, errores, omitidos = agrupar_cuadrillas(filas, _MAPA_CUADRILLAS)
    assert not errores
    assert omitidos == 0
    assert len(bloques) == 1
    bloque = bloques[0]
    assert bloque.llave == "CUA0001"
    assert bloque.encabezado.descripcion == "Cuadrilla (Oficial + Ayudante)"
    assert bloque.encabezado.precio_declarado == Decimal("1584")
    assert len(bloque.componentes) == 3
    assert {str(c.clave_insumo) for c in bloque.componentes} == {
        "MOOP-0049",
        "MOOP-0026",
        "MOOP-0079",
    }


def test_cuadrilla_sin_fila_cabecera_es_error() -> None:
    filas = [
        (2, ["CUA0002", "MOOP-0049", "Oficial Albañil", "jor", 1, 840, 840]),
    ]
    bloques, errores, _omitidos = agrupar_cuadrillas(filas, _MAPA_CUADRILLAS)
    assert not bloques
    assert len(errores) == 1
    assert "cabecera" in errores[0].motivo


def test_cuadrilla_con_dos_cabeceras_es_error() -> None:
    filas = [
        (2, ["CUA0003", "CUA0003", "Primera cabecera", "jor", None, 100, None]),
        (3, ["CUA0003", "CUA0003", "Segunda cabecera", "jor", None, 200, None]),
    ]
    bloques, errores, _omitidos = agrupar_cuadrillas(filas, _MAPA_CUADRILLAS)
    assert not bloques
    assert len(errores) == 2


def test_cuadrilla_agrupa_por_clave_normalizada_no_por_orden() -> None:
    """La agrupación es por `clave_cuadrilla`, no por posición: un integrante
    puede venir antes que su cabecera (§10.6)."""
    filas = [
        (2, ["cua0004", "MOOP-0049", "Oficial Albañil", "jor", 1, 840, 840]),
        (3, ["CUA0004", "CUA0004", "Cuadrilla", "jor", None, 840, None]),
    ]
    bloques, errores, _omitidos = agrupar_cuadrillas(filas, _MAPA_CUADRILLAS)
    assert not errores
    assert len(bloques) == 1
    assert bloques[0].llave == "CUA0004"
    assert len(bloques[0].componentes) == 1


def test_un_integrante_con_cantidad_negativa_no_es_error() -> None:
    """Mismo criterio que un componente de CPU: deducciones/ajustes restan."""
    filas = [
        (2, ["CUA0005", "CUA0005", "Cuadrilla", "jor", None, 500, None]),
        (3, ["CUA0005", "MOOP-0001", "Ajuste", "jor", -1, 500, -500]),
    ]
    bloques, errores, _omitidos = agrupar_cuadrillas(filas, _MAPA_CUADRILLAS)
    assert not errores
    assert bloques[0].componentes[0].cantidad == Decimal("-1")


# --- Prototipos (extensión propia, no está en el §10.6) ------------------

_MAPA_PROTOTIPOS = resolver_encabezados(
    ["Proyecto", "Clave", "Nombre", "M2", "Niveles", "Recamaras"],
    PROTOTIPOS,
)


def test_una_fila_de_prototipo_completa_queda_validada() -> None:
    prototipo = validar_prototipo(
        ["PROY", " cas-01 ", " Casa modelo A ", "85.5", "2", "3"],
        _MAPA_PROTOTIPOS,
        5,
    )
    assert prototipo.proyecto_clave == "PROY"
    assert prototipo.llave == "CAS-01"  # `Clave` normaliza (§3.3)
    assert prototipo.nombre == "Casa modelo A"
    assert prototipo.m2 == Decimal("85.5")
    assert prototipo.niveles == 2
    assert prototipo.recamaras == 3
    assert prototipo.fila == 5


def test_una_fila_sin_proyecto_es_error_de_fila() -> None:
    with pytest.raises(ErrorEnFila) as capturado:
        validar_prototipo(["", "CAS-01", "Casa modelo A", "", "", ""], _MAPA_PROTOTIPOS, 3)
    assert capturado.value.con_fila(3).columna == "proyecto_clave"


def test_una_fila_sin_clave_de_prototipo_es_error_de_fila() -> None:
    with pytest.raises(ErrorEnFila) as capturado:
        validar_prototipo(["PROY", "", "Casa modelo A", "", "", ""], _MAPA_PROTOTIPOS, 4)
    assert capturado.value.con_fila(4).columna == "clave"


def test_una_fila_sin_nombre_de_prototipo_es_error_de_fila() -> None:
    with pytest.raises(ErrorEnFila) as capturado:
        validar_prototipo(["PROY", "CAS-01", "", "", "", ""], _MAPA_PROTOTIPOS, 6)
    assert capturado.value.con_fila(6).columna == "nombre"


def test_prototipo_sin_columnas_opcionales_queda_en_none_no_en_cero() -> None:
    mapa = resolver_encabezados(["Proyecto", "Clave", "Nombre"], PROTOTIPOS)
    prototipo = validar_prototipo(["PROY", "CAS-01", "Casa modelo A"], mapa, 2)
    assert prototipo.m2 is None
    assert prototipo.niveles is None
    assert prototipo.recamaras is None


# --- Presupuesto jerárquico (extensión propia, no está en el §10.6) ------

_MAPA_PRESUPUESTO = resolver_encabezados(
    ["INDICE", "CLAVE PADRE", "CLAVE HIJO", "DESCRIPCION", "UNIDAD",
     "CANTIDAD", "PRECIO UNITARIO", "IMPORTE", "TIPO"],
    PRESUPUESTO,
)


def _fila_presupuesto(
    indice: object = "",
    padre: object = "",
    hijo: str = "",
    descripcion: str = "",
    unidad: object = "",
    cantidad: object = "",
    pu: object = "",
    importe: object = "",
    tipo: str = "",
) -> list[object]:
    return [indice, padre, hijo, descripcion, unidad, cantidad, pu, importe, tipo]


def test_dos_prototipos_con_clave_de_nodo_identica_se_resuelven_independientes() -> None:
    """`NIV-00001` se repite igual en cada prototipo del archivo real: el
    árbol de uno no puede colgar del otro por coincidencia de clave."""
    filas = [
        (2, _fila_presupuesto(1, None, "CAS-1", "Zafiro", tipo="PROTOTIPO")),
        (3, _fila_presupuesto(1, "CAS-1", "NIV-1", "Cimentación", tipo="NIVEL DE CONSTRUCCION")),
        (4, _fila_presupuesto(1, None, "CAS-2", "Otro", tipo="PROTOTIPO")),
        (5, _fila_presupuesto(1, "CAS-2", "NIV-1", "Cimentación", tipo="NIVEL DE CONSTRUCCION")),
    ]
    arboles, errores, pendientes, omitidos = construir_arboles(filas, _MAPA_PRESUPUESTO)

    assert not errores
    assert not pendientes
    assert omitidos == 0
    assert {a.clave_prototipo for a in arboles} == {"CAS-1", "CAS-2"}
    for arbol in arboles:
        hijos = arbol.hijos.get(arbol.clave_prototipo, ())
        assert [h.clave for h in hijos] == ["NIV-1"]


def test_una_fila_con_padre_que_no_aparecio_antes_es_error_de_fila() -> None:
    filas = [
        (2, _fila_presupuesto(1, None, "CAS-1", "Zafiro", tipo="PROTOTIPO")),
        (3, _fila_presupuesto(1, "NIV-FANTASMA", "ECO-1", "Estructura", tipo="ETAPA DE CONSTRUCCION")),
    ]
    _arboles, errores, _pendientes, _omitidos = construir_arboles(filas, _MAPA_PRESUPUESTO)

    assert len(errores) == 1
    assert errores[0].fila == 3
    assert errores[0].columna == "clave_padre"


def test_un_tipo_desconocido_va_a_la_bandeja_y_el_resto_sigue() -> None:
    filas = [
        (2, _fila_presupuesto(1, None, "CAS-1", "Zafiro", tipo="PROTOTIPO")),
        (3, _fila_presupuesto(1, "CAS-1", "NIV-1", "Cimentación", tipo="NIVEL RARO")),
        (4, _fila_presupuesto(2, "CAS-1", "NIV-2", "Planta baja", tipo="NIVEL DE CONSTRUCCION")),
    ]
    arboles, errores, pendientes, _omitidos = construir_arboles(filas, _MAPA_PRESUPUESTO)

    assert len(errores) == 1
    assert errores[0].fila == 3
    assert len(pendientes) == 1
    assert pendientes[0].tipo is TipoPendiente.FILA_NO_PARSEADA
    (arbol,) = arboles
    assert [h.clave for h in arbol.hijos.get("CAS-1", ())] == ["NIV-2"]


def test_prototipo_repetido_en_el_archivo_gana_el_ultimo() -> None:
    filas = [
        (2, _fila_presupuesto(1, None, "CAS-1", "Zafiro v1", tipo="PROTOTIPO")),
        (3, _fila_presupuesto(1, "CAS-1", "NIV-1", "Cimentación", tipo="NIVEL DE CONSTRUCCION")),
        (4, _fila_presupuesto(1, None, "CAS-1", "Zafiro v2", tipo="PROTOTIPO")),
        (5, _fila_presupuesto(1, "CAS-1", "NIV-2", "Planta baja", tipo="NIVEL DE CONSTRUCCION")),
    ]
    arboles, errores, _pendientes, omitidos = construir_arboles(filas, _MAPA_PRESUPUESTO)

    assert not errores
    assert omitidos == 1
    (arbol,) = arboles
    assert arbol.raiz.descripcion == "Zafiro v2"
    assert [h.clave for h in arbol.hijos.get("CAS-1", ())] == ["NIV-2"]


def test_una_etapa_con_hijos_puro_material_actua_como_concepto() -> None:
    filas = [
        (2, _fila_presupuesto(1, None, "CAS-1", "Zafiro", tipo="PROTOTIPO")),
        (3, _fila_presupuesto(1, "CAS-1", "NIV-1", "Cimentación", tipo="NIVEL DE CONSTRUCCION")),
        (4, _fila_presupuesto(1, "NIV-1", "ECO-1", "Planta baja", cantidad=1, tipo="ETAPA DE CONSTRUCCION")),
        (5, _fila_presupuesto(1, "ECO-1", "ELE-1", "Pija", "PZ", 1, "0.5", "0.5", tipo="MATERIAL")),
        (6, _fila_presupuesto(2, "ECO-1", "SUB-1", "Subcontrato", "SERV", 1, "100", "100", tipo="SUBCONTRATO")),
    ]
    arboles, errores, _pendientes, _omitidos = construir_arboles(filas, _MAPA_PRESUPUESTO)
    assert not errores
    (arbol,) = arboles
    etapa = arbol.nodos["ECO-1"]
    assert es_etapa_con_componentes_directos(arbol, etapa) is True


def test_una_etapa_con_un_concepto_hijo_no_actua_como_concepto() -> None:
    filas = [
        (2, _fila_presupuesto(1, None, "CAS-1", "Zafiro", tipo="PROTOTIPO")),
        (3, _fila_presupuesto(1, "CAS-1", "NIV-1", "Cimentación", tipo="NIVEL DE CONSTRUCCION")),
        (4, _fila_presupuesto(1, "NIV-1", "ECO-1", "Planta baja", tipo="ETAPA DE CONSTRUCCION")),
        (5, _fila_presupuesto(1, "ECO-1", "EST-1", "Losa", "M2", 1, "0", "0", tipo="CONCEPTO")),
    ]
    arboles, errores, _pendientes, _omitidos = construir_arboles(filas, _MAPA_PRESUPUESTO)
    assert not errores
    (arbol,) = arboles
    etapa = arbol.nodos["ECO-1"]
    assert es_etapa_con_componentes_directos(arbol, etapa) is False


def test_tipos_de_nodo_normalizan_variantes_con_acentos_y_mayusculas() -> None:
    assert TipoNodoPresupuesto("etapa de construccion") is TipoNodoPresupuesto.ETAPA


# --- CPU / Conceptos (§10.6, formato plano) ------------------------------


def _fila_cpu(
    clave: str = "",
    insumo: str = "",
    descripcion: str = "",
    unidad: str = "",
    cantidad: object = "",
    pu: object = "",
    familia: str = "",
    tipo: str = "",
) -> list[object]:
    """Fila con las columnas en su letra: A B C D E F (G vacía) H I (§10.6)."""
    return [clave, insumo, descripcion, unidad, cantidad, pu, "", familia, tipo]


def test_arma_el_bloque_concepto_mas_componentes() -> None:
    conceptos, errores, pendientes, omitidos = agrupar_conceptos(
        [
            (2, _fila_cpu("EST-01", "EST-01", "Muro de block", "m2", tipo="Concepto")),
            (3, _fila_cpu(insumo="MAT-01", descripcion="Block", cantidad="12.5", pu="20", tipo="Material")),
            (4, _fila_cpu(insumo="MOA-01", descripcion="Albañil", cantidad="0.8", pu="300", tipo="Mano de obra")),
        ],
        MAPA_CPU,
    )
    assert errores == () and pendientes == () and omitidos == 0
    assert len(conceptos) == 1
    bloque = conceptos[0]
    assert bloque.llave == "EST-01"
    assert [str(c.clave_insumo) for c in bloque.componentes] == ["MAT-01", "MOA-01"]
    assert bloque.componentes[0].categoria is CategoriaExplosion.MATERIAL
    assert bloque.componentes[1].categoria is CategoriaExplosion.MANO_OBRA
    assert bloque.componentes[0].cantidad == Decimal("12.5")


def test_un_componente_sin_su_encabezado_es_error_de_fila() -> None:
    conceptos, errores, _, _ = agrupar_conceptos(
        [(2, _fila_cpu(insumo="MAT-01", cantidad="1", tipo="Material"))], MAPA_CPU
    )
    assert conceptos == ()
    assert len(errores) == 1
    assert "sin su fila encabezado" in errores[0].motivo
    assert errores[0].fila == 2


def test_un_componente_con_cantidad_negativa_no_es_error() -> None:
    """Una deducción (material recuperado, ajuste) resta del importe del
    concepto en vez de sumar — no es un dato inválido (§7.3)."""
    conceptos, errores, _, _ = agrupar_conceptos(
        [
            (2, _fila_cpu("EST-01", "EST-01", "Muro de block", "m2", tipo="Concepto")),
            (3, _fila_cpu(insumo="MAT-01", cantidad="-2", tipo="Material")),
        ],
        MAPA_CPU,
    )
    assert not errores
    assert conceptos[0].componentes[0].cantidad == Decimal("-2")


def test_un_tipo_fuera_del_contrato_va_a_la_bandeja() -> None:
    """`explosion.categoria` es invariante del §8.2: no se traduce por parecido."""
    _, errores, pendientes, _ = agrupar_conceptos(
        [
            (2, _fila_cpu("EST-01", "EST-01", "Muro", "m2", tipo="Concepto")),
            (3, _fila_cpu(insumo="X-1", cantidad="1", tipo="Herramienta menor")),
        ],
        MAPA_CPU,
    )
    assert len(errores) == 1
    assert len(pendientes) == 1
    assert pendientes[0].tipo is TipoPendiente.FILA_NO_PARSEADA
    assert pendientes[0].origen_ref == "fila 3"


def test_una_fila_mala_no_tumba_el_resto_del_bloque() -> None:
    """§9.3: el archivo sigue; solo esa fila queda reportada."""
    conceptos, errores, _, _ = agrupar_conceptos(
        [
            (2, _fila_cpu("EST-01", "EST-01", "Muro", "m2", tipo="Concepto")),
            (3, _fila_cpu(insumo="MAT-01", cantidad="no es número", tipo="Material")),
            (4, _fila_cpu(insumo="MAT-02", cantidad="3", tipo="Material")),
        ],
        MAPA_CPU,
    )
    assert len(errores) == 1 and errores[0].fila == 3
    assert [str(c.clave_insumo) for c in conceptos[0].componentes] == ["MAT-02"]


def test_una_clave_repetida_en_el_archivo_deduplica_y_gana_la_ultima() -> None:
    """"Deduplica por clave" del modo Actualizar (§10.2)."""
    conceptos, _, _, omitidos = agrupar_conceptos(
        [
            (2, _fila_cpu("EST-01", "EST-01", "Versión vieja", "m2", tipo="Concepto")),
            (3, _fila_cpu(insumo="MAT-01", cantidad="1", tipo="Material")),
            (4, _fila_cpu("EST-01", "EST-01", "Versión nueva", "m2", tipo="Concepto")),
            (5, _fila_cpu(insumo="MAT-02", cantidad="2", tipo="Material")),
        ],
        MAPA_CPU,
    )
    assert omitidos == 1
    assert len(conceptos) == 1
    assert conceptos[0].encabezado.descripcion == "Versión nueva"


# --- Movimientos de almacén (§10.5, §10.6) -------------------------------

_MAPA_ALMACEN = resolver_encabezados(
    [
        "# Parte", "Parte", "Clase", "Ubicacion", "Lote", "Contratista", "Fecha",
        "Motivo", "Efecto Qty", "Efecto Costo", "C/Último", "C/Promedio",
        "Referencia", "# Almacen", "Almacen", "Usuario",
    ],
    ALMACEN,
)


def _fila_almacen(**cambios: object) -> list[object]:
    fila: dict[str, object] = {
        "# Parte": "CEM-01",
        "Parte": "Cemento gris",
        "Clase": "CEM",
        "Ubicacion": "FRESNO",
        "Lote": "12",
        "Contratista": "Constructora X",
        "Fecha": date(2026, 8, 10),
        "Motivo": "Salida para producción",
        "Efecto Qty": "-10",
        "Efecto Costo": "-2500",
        "C/Último": "250",
        "C/Promedio": "248",
        "Referencia": "No.Parte:EST-0123 OP-99",
        "# Almacen": "1",
        "Almacen": "Central",
        "Usuario": "jperez",
    }
    fila.update(cambios)  # type: ignore[arg-type]
    return list(fila.values())


def test_la_obra_sale_de_ubicacion_mas_lote() -> None:
    """§10.6: obra = `Ubicacion + Lote`; §10.1: clave = `CLUSTER + LOTE`."""
    assert str(clave_de_obra(" fresno ", " 12 ")) == "FRESNO 12"


@pytest.mark.parametrize(
    ("referencia", "esperado"),
    [
        ("No.Parte:EST-0123 OP-99", "EST-0123"),
        ("SUB-77", "SUB-77"),
        ("sin liga alguna", None),
        ("", None),
    ],
)
def test_extrae_la_clave_de_concepto_de_la_referencia(
    referencia: str, esperado: str | None
) -> None:
    assert concepto_de_referencia(referencia) == esperado


def test_un_movimiento_completo_conserva_el_signo_del_archivo() -> None:
    """§10.5: "el signo viene en el archivo"; aquí no se recalcula nada."""
    movimiento = validar_movimiento(_fila_almacen(), _MAPA_ALMACEN, 9)
    assert str(movimiento.clave_insumo) == "CEM-01"
    assert str(movimiento.clave_obra) == "FRESNO 12"
    assert movimiento.cantidad == Decimal("-10")
    assert movimiento.costo == Decimal("-2500")
    assert movimiento.costo_ultimo == Decimal("250")
    assert movimiento.clave_concepto == "EST-0123"
    assert movimiento.fecha == date(2026, 8, 10)
    assert movimiento.fila == 9


def test_un_movimiento_sin_cantidad_no_existe() -> None:
    with pytest.raises(ErrorEnFila, match="cero"):
        validar_movimiento(_fila_almacen(**{"Efecto Qty": "0"}), _MAPA_ALMACEN, 9)


def test_un_movimiento_sin_motivo_no_es_interpretable() -> None:
    """Sin motivo no hay bucket de KPI (§10.5)."""
    with pytest.raises(ErrorEnFila, match="motivo"):
        validar_movimiento(_fila_almacen(**{"Motivo": ""}), _MAPA_ALMACEN, 9)


def test_el_iva_se_agrega_sobre_el_costo_sin_iva_del_archivo() -> None:
    """§10.6: "los costos vienen sin IVA y se agrega 16% según `Clase`"."""
    assert importe_con_iva(
        Decimal("-2500"), aplica_iva=True, tasa=Decimal("0.16")
    ) == Decimal("-2900.0000")
    assert importe_con_iva(
        Decimal("-2500"), aplica_iva=False, tasa=Decimal("0.16")
    ) == Decimal("-2500.0000")


def test_la_tasa_de_iva_es_parametro_y_no_constante() -> None:
    """§8.7: un configurable nunca se clava como constante de cálculo."""
    assert importe_con_iva(
        Decimal("100"), aplica_iva=True, tasa=Decimal("0.08")
    ) == Decimal("108.0000")


# --- Homologación (§10.3) ------------------------------------------------

_CATALOGO = [
    {"clave": "CEM-01", "descripcion": "Cemento gris", "sinonimos": ["CPC30"]},
    {"clave": "ARE-01", "descripcion": "Arena", "sinonimos": []},
    {"clave": "ARE-02", "descripcion": "Arena", "sinonimos": []},
]


def test_la_clave_manda_sobre_todo_lo_demas() -> None:
    homologador = Homologador.desde(_CATALOGO, mapeos={"cem-01": "ARE-01"})
    assert homologador.resolver(" cem-01 ") == "CEM-01"


def test_un_mapeo_confirmado_resuelve_lo_que_la_clave_no() -> None:
    """Lo que el humano resolvió en la bandeja re-alimenta la carga (§10.3)."""
    homologador = Homologador.desde(_CATALOGO, mapeos={"CEMENTO GRIS 50KG": "CEM-01"})
    assert homologador.resolver("cemento gris 50kg") == "CEM-01"


def test_el_sinonimo_del_catalogo_tambien_cruza() -> None:
    assert Homologador.desde(_CATALOGO).resolver("cpc30") == "CEM-01"


def test_una_descripcion_repetida_no_resuelve_a_ninguno() -> None:
    """La descripción solo desempata; si no desempata, es bandeja (§3.3)."""
    assert Homologador.desde(_CATALOGO).resolver("Arena") is None


def test_lo_que_no_cruza_devuelve_none_y_no_una_aproximacion() -> None:
    assert Homologador.desde(_CATALOGO).resolver("Grava de río") is None


# --- Diff y versionado (§10.8) -------------------------------------------

_VIGENTES = {
    "CEM-01": {"descripcion": "Cemento gris", "costo_base": Decimal("250.00")},
    "ARE-01": {"descripcion": "Arena", "costo_base": Decimal("100")},
}


def test_un_archivo_identico_no_genera_version() -> None:
    """§10.8: "si es idéntico, no crea versión"."""
    diff = diferenciar(
        vigentes=_VIGENTES,
        # 250 y 250.00 son el mismo precio: el diff no debe inventar un cambio.
        entrantes={
            "CEM-01": {"descripcion": "Cemento gris", "costo_base": Decimal("250")},
            "ARE-01": {"descripcion": "Arena", "costo_base": Decimal("100.000")},
        },
    )
    assert not diff.hay_cambios
    assert diff.omitidos == 2


def test_actualizar_detecta_altas_y_cambios_con_su_detalle() -> None:
    """El ejemplo del §10.8: precios que cambian + claves nuevas → v2 con diff."""
    diff = diferenciar(
        vigentes=_VIGENTES,
        entrantes={
            "CEM-01": {"descripcion": "Cemento gris", "costo_base": Decimal("270")},
            "ARE-01": {"descripcion": "Arena", "costo_base": Decimal("100")},
            "GRA-01": {"descripcion": "Grava", "costo_base": Decimal("80")},
        },
        modo=ModoCarga.ACTUALIZAR,
    )
    assert [c.clave for c in diff.altas] == ["GRA-01"]
    assert [c.clave for c in diff.cambios] == ["CEM-01"]
    assert diff.cambios[0].campos_cambiados == ("costo_base",)
    assert diff.bajas == ()
    assert diff.hay_cambios


def test_acumular_no_toca_lo_que_ya_existe() -> None:
    """§10.2: "Acumular — solo agrega nuevos, sin tocar lo actual"."""
    diff = diferenciar(
        vigentes=_VIGENTES,
        entrantes={
            "CEM-01": {"descripcion": "Otro nombre", "costo_base": Decimal("999")},
            "GRA-01": {"descripcion": "Grava", "costo_base": Decimal("80")},
        },
        modo=ModoCarga.ACUMULAR,
    )
    assert [c.clave for c in diff.altas] == ["GRA-01"]
    assert diff.cambios == ()
    assert diff.sin_cambio == ("CEM-01",)


def test_reemplazar_da_de_baja_lo_que_el_archivo_ya_no_trae() -> None:
    """§10.2: "Reemplazar — sustituye todo el conjunto"."""
    diff = diferenciar(
        vigentes=_VIGENTES,
        entrantes={"CEM-01": {"descripcion": "Cemento gris", "costo_base": Decimal("250")}},
        modo=ModoCarga.REEMPLAZAR,
    )
    assert [c.clave for c in diff.bajas] == ["ARE-01"]
    assert diff.hay_cambios


def test_el_diff_serializado_dice_que_cambio_de_cada_clave() -> None:
    """§10.8 manda guardar el diff, no solo el conteo."""
    diff = diferenciar(
        vigentes=_VIGENTES,
        entrantes={
            "CEM-01": {"descripcion": "Cemento CPC 30", "costo_base": Decimal("270")}
        },
    )
    assert diff.como_dict()["cambios"] == {"CEM-01": ["costo_base", "descripcion"]}
