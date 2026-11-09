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
    CONCEPTOS_AUXILIARES,
    CONCEPTOS_BASE,
    CONTRATISTAS,
    CUADRILLAS,
    ETAPAS_CONSTRUCTIVAS,
    FAMILIAS,
    MANO_DE_OBRA,
    MAPA_CPU,
    MATERIALES,
    NIVELES,
    PRESUPUESTO,
    PROTOTIPOS,
    UNIDADES,
    ErrorDeCabecera,
    indice_de_letra,
    resolver_encabezados,
)
from obractrl.domain.cargadores.claves_automaticas import generar_clave_automatica
from obractrl.domain.cargadores.conceptos_base import validar_concepto_base
from obractrl.domain.cargadores.contratistas import validar_contratista
from obractrl.domain.cargadores.cpu import agrupar_conceptos
from obractrl.domain.cargadores.cuadrillas import agrupar_cuadrillas
from obractrl.domain.cargadores.etapas_constructivas import validar_etapa_constructiva
from obractrl.domain.cargadores.familias import validar_familia
from obractrl.domain.cargadores.homologacion import Homologador
from obractrl.domain.cargadores.mano_de_obra import validar_mano_obra
from obractrl.domain.cargadores.materiales import validar_material
from obractrl.domain.cargadores.niveles import validar_nivel
from obractrl.domain.cargadores.presupuesto import (
    TipoNodoPresupuesto,
    construir_arboles,
    es_etapa_con_componentes_directos,
)
from obractrl.domain.cargadores.prototipos import validar_prototipo
from obractrl.domain.cargadores.reporte import ErrorEnFila, TipoPendiente
from obractrl.domain.cargadores.unidades import validar_unidad
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
    assert material.clave_unidad == "1"  # antes se ignoraba: cae en "CLAVE UNIDAD"
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


def test_concepto_auxiliar_real_captura_clave_unidad_e_ignora_el_costo() -> None:
    """El archivo real de conceptos auxiliares trae las mismas columnas que
    Materiales (CLAVE UNIDAD, UNIDAD, COSTO BASE M.N., COSTO BASE M.E.,
    COSTO UNITARIO, FECHA, FAMILIA) — confirmado con el usuario: el costo
    se ignora aquí (es CPU, no identidad, §8.7), pero `clave_unidad` sí es
    identidad y se captura, igual que en materiales."""
    mapa = resolver_encabezados(
        ["CLAVE", "DESCRIPCIÓN", "CLAVE UNIDAD", "UNIDAD", "COSTO BASE M.N.",
         "COSTO BASE M.E.", "COSTO UNITARIO", "FECHA", "FAMILIA"],
        CONCEPTOS_AUXILIARES,
    )
    auxiliar = validar_concepto_base(
        ["AUX-00001", "Trabe T-3 de 15x25 cm", 8, "m", 72.14, 0, 72.14, None, "Auxiliares"],
        mapa,
        2,
    )
    assert auxiliar.llave == "AUX-00001"
    assert auxiliar.unidad == "m"
    assert auxiliar.clave_unidad == "8"


def test_concepto_base_captura_la_descripcion_corta_sin_chocar_con_la_descripcion() -> None:
    """`DESCRIPCIÓN CORTA` junto a `DESCRIPCIÓN` no rechaza el archivo por ambigüedad y llega como campo propio (0121)."""
    mapa = resolver_encabezados(["Clave", "Descripción", "Descripción corta", "Unidad"], CONCEPTOS_BASE)
    concepto = validar_concepto_base(
        ["EST-10010", "Colocación de acero en cimentación K1, armado completo", "Acero K1", "kg"], mapa, 7
    )
    assert concepto.descripcion == "Colocación de acero en cimentación K1, armado completo"
    assert concepto.descripcion_corta == "Acero K1"
    sin = validar_concepto_base(["EST-02", "Losa", "", "m2"], mapa, 8)
    assert sin.descripcion_corta is None


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


# --- Niveles de construcción (§10.1, `CATALOGO_DE_NIVELES.xlsx`) --------

_MAPA_NIVELES = resolver_encabezados(
    ["TIPO", "CLAVE", "DESCRIPCIÓN", "DESCRIPCIÓN CORTA", "UNIDAD", "CANTIDAD",
     "PRECIO UNITARIO", "TOTAL"],
    NIVELES,
)
"""Cabeceras reales del archivo (`CATALOGO_DE_NIVELES.xlsx`): TIPO,
DESCRIPCIÓN CORTA, UNIDAD, CANTIDAD, PRECIO UNITARIO y TOTAL no tienen
dónde vivir en este catálogo tan simple — se ignoran sin romper (§10.6)."""


def test_un_nivel_real_del_archivo_queda_validado() -> None:
    nivel = validar_nivel(
        ["Subcapítulo", "NIV-00001", "CIMENTACION ", "CIMENTACION ", None, 1, None, None],
        _MAPA_NIVELES,
        2,
    )
    assert nivel.llave == "NIV-00001"
    assert nivel.descripcion == "CIMENTACION"
    assert nivel.fila == 2


def test_nivel_sin_clave_no_se_rechaza() -> None:
    """Mismo criterio que el catálogo de conceptos (§8.7): sin clave, la
    fila se numera sola en el aplicador, no se rechaza aquí."""
    nivel = validar_nivel(["Subcapítulo", "", "ACABADOS", "ACABADOS", None, 1, None, None], _MAPA_NIVELES, 6)
    assert nivel.clave is None
    assert nivel.llave == "__sin_clave__6"


def test_nivel_sin_descripcion_es_error_de_fila() -> None:
    with pytest.raises(ErrorEnFila, match="descripcion"):
        validar_nivel(["Subcapítulo", "NIV-00099", "", "", None, 1, None, None], _MAPA_NIVELES, 7)


# --- Etapas de construcción (§10.1, `CATALOGO_DE_ETAPAS_DE_CONSTRUCCION.xlsx`)

_MAPA_ETAPAS = resolver_encabezados(
    ["TIPO", "CLAVE", "DESCRIPCIÓN", "DESCRIPCIÓN CORTA", "UNIDAD", "CANTIDAD",
     "PRECIO UNITARIO", "TOTAL"],
    ETAPAS_CONSTRUCTIVAS,
)


def test_una_etapa_real_del_archivo_queda_validada() -> None:
    etapa = validar_etapa_constructiva(
        ["Nivel 2", "ECO-00001", "ESTRUCTURA CIM", "ESTRUCTURA CIM", None, 1, None, None],
        _MAPA_ETAPAS,
        2,
    )
    assert etapa.llave == "ECO-00001"
    assert etapa.descripcion == "ESTRUCTURA CIM"


def test_etapa_sin_clave_no_se_rechaza() -> None:
    etapa = validar_etapa_constructiva(
        ["Nivel 2", "", "INSTALACIONES GAS PB", "INSTALACIONES GAS PB", None, 1, None, None],
        _MAPA_ETAPAS,
        9,
    )
    assert etapa.clave is None
    assert etapa.llave == "__sin_clave__9"


def test_etapa_sin_descripcion_es_error_de_fila() -> None:
    with pytest.raises(ErrorEnFila, match="descripcion"):
        validar_etapa_constructiva(
            ["Nivel 2", "ECO-00099", "", "", None, 1, None, None], _MAPA_ETAPAS, 10
        )


# --- Unidades (§3.5, `CATALOGO_DE_UNIDADES.xlsx`) -------------------------

_MAPA_UNIDADES = resolver_encabezados(
    ["CLAVE UNIDAD", "UNIDAD", "SINONIMO"],
    UNIDADES,
)
"""Cabeceras reales del archivo: "CLAVE UNIDAD" es un consecutivo numérico
del sistema de origen (sin dónde vivir aquí, se ignora sin romper) —
"UNIDAD" (KG/PZ/...) resuelve a `clave` y "SINONIMO" (Kilogramo/Pieza/...)
a `nombre` vía el alias propio de `cabeceras.UNIDADES`."""


def test_una_unidad_real_del_archivo_queda_validada() -> None:
    unidad = validar_unidad(["1", "KG", "Kilogramo"], _MAPA_UNIDADES, 2)
    assert unidad.llave == "KG"
    assert unidad.nombre == "Kilogramo"
    assert unidad.fila == 2


def test_clave_unidad_numerica_del_sistema_de_origen_se_ignora() -> None:
    """La columna "CLAVE UNIDAD" (1, 2, 3...) no es la `clave` del catálogo
    —esa es "UNIDAD"—: se lee y se descarta sin romper la fila (§10.6)."""
    unidad = validar_unidad(["50", "SAL", "Salida"], _MAPA_UNIDADES, 16)
    assert unidad.llave == "SAL"


def test_unidad_sin_clave_no_se_rechaza() -> None:
    unidad = validar_unidad(["", "", "Actividad"], _MAPA_UNIDADES, 17)
    assert unidad.clave is None
    assert unidad.llave == "__sin_clave__17"


def test_unidad_sin_nombre_es_error_de_fila() -> None:
    with pytest.raises(ErrorEnFila, match="nombre"):
        validar_unidad(["99", "XX", ""], _MAPA_UNIDADES, 18)


def test_variante_sinomimo_del_archivo_real_tambien_resuelve_a_nombre() -> None:
    """"SINOMIMO" (M/N invertida) es lo que el archivo real trae de verdad
    —confirmado en vivo, no un typo de este módulo—; sin este alias
    "nombre" faltaba y el archivo se rechazaba entero (§10.6)."""
    mapa = resolver_encabezados(["CLAVE UNIDAD", "UNIDAD", "SINOMIMO"], UNIDADES)
    unidad = validar_unidad(["1", "KG", "Kilogramo"], mapa, 2)
    assert unidad.nombre == "Kilogramo"


# --- Familias (§3.5, `CATALOGO_DE_FAMILIAS.xlsx`) --------------------------

_MAPA_FAMILIAS = resolver_encabezados(
    ["CLAVE", "FAMILIA", "PREFIJO"],
    FAMILIAS,
)
"""Cabeceras reales del archivo: "PREFIJO" (ACA/ADH/PET/...) no tiene dónde
vivir en `familia` hoy — se ignora sin romper, mismo criterio que "TIPO" en
niveles/etapas. "FAMILIA" resuelve a `nombre` vía el alias propio de
`cabeceras.FAMILIAS` — sin él resolvería al campo global homónimo (una
referencia ajena en otros archivos), que esta especificación no declara."""


def test_una_familia_real_del_archivo_queda_validada() -> None:
    familia = validar_familia(["FML-00001", "Acabados", "ACA"], _MAPA_FAMILIAS, 2)
    assert familia.llave == "FML-00001"
    assert familia.nombre == "Acabados"
    assert familia.fila == 2


def test_prefijo_de_familia_se_ignora() -> None:
    familia = validar_familia(["FML-00034", "Sanitario", "SAN"], _MAPA_FAMILIAS, 35)
    assert familia.llave == "FML-00034"
    assert familia.nombre == "Sanitario"


def test_familia_sin_clave_no_se_rechaza() -> None:
    familia = validar_familia(["", "Jardinería", "JAR"], _MAPA_FAMILIAS, 36)
    assert familia.clave is None
    assert familia.llave == "__sin_clave__36"


def test_familia_sin_nombre_es_error_de_fila() -> None:
    with pytest.raises(ErrorEnFila, match="nombre"):
        validar_familia(["FML-00099", "", "XXX"], _MAPA_FAMILIAS, 37)


# --- Contratistas (§8.3, §10.6) ------------------------------------------

_MAPA_CONTRATISTAS = resolver_encabezados(
    ["CLAVE", "CONTRATISTA", "RFC", "CONTACTO", "TEL", "CORREO", "FRENTE"],
    CONTRATISTAS,
)
"""Las cabeceras como las escribe una persona: "CONTRATISTA" es la razón
social de ESTA fila —no una referencia a un tercero, como en materiales— y
"TEL"/"CORREO"/"FRENTE" son las abreviaturas que el archivo real usa. Todas
resuelven por el alias propio de `cabeceras.CONTRATISTAS`."""


def test_un_contratista_real_queda_validado() -> None:
    fila = validar_contratista(
        ["CON-001", "Constructora Zafiro SA", "ZAF010101AAA", "Luis",
         "5551234567", "luis@zafiro.mx", "EST, INS"],
        _MAPA_CONTRATISTAS,
        2,
    )
    assert fila.llave == "CON-001"
    assert fila.razon_social == "Constructora Zafiro SA"
    assert [str(f) for f in fila.frentes] == ["EST", "INS"]


def test_los_opcionales_vacios_quedan_nulos_y_no_en_blanco() -> None:
    # Cadena vacía y ausente significan lo mismo —"no lo capturaron"— y
    # guardar `''` haría que la pantalla enseñara un campo lleno de nada.
    fila = validar_contratista(
        ["CON-002", "Instalaciones del Norte", "", "Ana", "", "", "INS"],
        _MAPA_CONTRATISTAS,
        3,
    )
    assert fila.rfc is None
    assert fila.telefono is None
    assert fila.email is None
    assert fila.contacto == "Ana"


def test_el_rfc_no_se_valida_de_formato() -> None:
    # Un contratista real llega con el dato incompleto o con un RFC
    # provisional; rechazar la fila dejaría fuera a quien sí está en la obra.
    fila = validar_contratista(
        ["CON-003", "Herrería López", "no lo tengo", "", "", "", ""],
        _MAPA_CONTRATISTAS,
        4,
    )
    assert fila.rfc == "no lo tengo"


def test_los_frentes_admiten_cualquiera_de_los_separadores() -> None:
    # El archivo lo escribe una persona y ninguna de las cuatro formas es un
    # error.
    for celda in ("EST, INS", "EST; INS", "EST / INS", "EST|INS"):
        fila = validar_contratista(
            ["CON-004", "Varios", "", "", "", "", celda], _MAPA_CONTRATISTAS, 5
        )
        assert [str(f) for f in fila.frentes] == ["EST", "INS"]


def test_un_frente_repetido_no_se_duplica() -> None:
    fila = validar_contratista(
        ["CON-005", "Repetido", "", "", "", "", "INS, INS, EST"],
        _MAPA_CONTRATISTAS,
        6,
    )
    assert [str(f) for f in fila.frentes] == ["INS", "EST"]


def test_sin_razon_social_es_error_de_fila() -> None:
    with pytest.raises(ErrorEnFila, match="razon_social"):
        validar_contratista(
            ["CON-006", "", "", "", "", "", ""], _MAPA_CONTRATISTAS, 7
        )


def test_contratista_sin_clave_no_se_rechaza() -> None:
    # ObraCtrl ya trae claves automáticas (familias/niveles/etapas/unidades,
    # §8.7); un contratista sin clave en el archivo no es la excepción.
    fila = validar_contratista(
        ["", "Varios Chiquitos", "", "", "", "", ""], _MAPA_CONTRATISTAS, 8
    )
    assert fila.clave is None
    assert fila.llave == "__sin_clave__8"


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
    assert destajo.clave_unidad == "UN-01"  # antes se ignoraba: cae en "CLAVE UNIDAD"
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
    wbs: object = "",
) -> list[object]:
    return [indice, padre, hijo, descripcion, unidad, cantidad, pu, importe, tipo, wbs]


_MAPA_PRESUPUESTO_CON_WBS = resolver_encabezados(
    ["INDICE", "CLAVE PADRE", "CLAVE HIJO", "DESCRIPCION", "UNIDAD",
     "CANTIDAD", "PRECIO UNITARIO", "IMPORTE", "TIPO", "WBS"],
    PRESUPUESTO,
)


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
        hijos = arbol.hijos.get(arbol.raiz.fila, ())
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
    assert [h.clave for h in arbol.hijos.get(arbol.raiz.fila, ())] == ["NIV-2"]


# --- WBS opcional del archivo (§7.4, no crítico) --------------------------


def test_wbs_del_archivo_coincide_con_la_esperada_no_genera_pendiente() -> None:
    """El nivel de WBS lo da el TIPO, no la profundidad del árbol: la
    segunda etapa cuelga su material directo (sin concepto de por medio) y
    cae en el nivel 5 igual, con el 4 en 0 — la propia fila ETAPA ya
    reinició los contadores más profundos (§7.4)."""
    filas = [
        (2, _fila_presupuesto(1, None, "CAS-1", "Zafiro", tipo="PROTOTIPO", wbs="1.0.0.0.0")),
        (3, _fila_presupuesto(1, "CAS-1", "NIV-1", "Cimentación", tipo="NIVEL DE CONSTRUCCION", wbs="1.1.0.0.0")),
        (4, _fila_presupuesto(1, "NIV-1", "ECO-1", "Estructura", tipo="ETAPA DE CONSTRUCCION", wbs="1.1.1.0.0")),
        (5, _fila_presupuesto(1, "ECO-1", "EST-1", "Losa", tipo="CONCEPTO", wbs="1.1.1.1.0")),
        (6, _fila_presupuesto(1, "EST-1", "ACE-1", "Alambre", tipo="MATERIAL", wbs="1.1.1.1.1")),
        (7, _fila_presupuesto(2, "NIV-1", "ECO-2", "Instalaciones", tipo="ETAPA DE CONSTRUCCION", wbs="1.1.2.0.0")),
        (8, _fila_presupuesto(1, "ECO-2", "ACE-2", "Cemento", tipo="MATERIAL", wbs="1.1.2.0.1")),
    ]
    _arboles, errores, pendientes, _omitidos = construir_arboles(filas, _MAPA_PRESUPUESTO_CON_WBS)

    assert not errores
    assert not pendientes


def test_wbs_del_archivo_distinta_de_la_esperada_avisa_sin_bloquear() -> None:
    """No crítico (§10.3): la fila se arma igual —el árbol la cuelga— solo
    se avisa para que alguien decida si carga o corrige el archivo."""
    filas = [
        (2, _fila_presupuesto(1, None, "CAS-1", "Zafiro", tipo="PROTOTIPO", wbs="1.0.0.0.0")),
        (3, _fila_presupuesto(1, "CAS-1", "NIV-1", "Cimentación", tipo="NIVEL DE CONSTRUCCION", wbs="1.1.0.0.0")),
        (4, _fila_presupuesto(1, "NIV-1", "ECO-1", "Estructura", tipo="ETAPA DE CONSTRUCCION", wbs="1.1..0.0")),
    ]
    arboles, errores, pendientes, _omitidos = construir_arboles(filas, _MAPA_PRESUPUESTO_CON_WBS)

    assert not errores  # no bloquea: sigue siendo un árbol válido
    (arbol,) = arboles
    assert [h.clave for h in arbol.hijos.get(arbol.raiz.fila, ())] == ["NIV-1"]

    assert len(pendientes) == 1
    pendiente = pendientes[0]
    assert pendiente.tipo is TipoPendiente.WBS_INCONSISTENTE
    assert pendiente.valor_origen == "1.1..0.0"
    assert pendiente.propuesta["esperado"] == "1.1.1.0.0"
    assert pendiente.origen_ref == "fila 4"
    assert pendiente.critico is False


def test_sin_columna_wbs_en_el_archivo_no_hay_nada_que_comparar() -> None:
    """Opcional (§7.4): un archivo real que no la trae no genera ni una
    alerta de más — `_MAPA_PRESUPUESTO` (sin "WBS" en la cabecera)."""
    filas = [
        (2, _fila_presupuesto(1, None, "CAS-1", "Zafiro", tipo="PROTOTIPO")),
    ]
    _arboles, errores, pendientes, _omitidos = construir_arboles(filas, _MAPA_PRESUPUESTO)

    assert not errores
    assert not pendientes


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
    assert [h.clave for h in arbol.hijos.get(arbol.raiz.fila, ())] == ["NIV-2"]


def test_una_clave_de_concepto_repetida_en_dos_etapas_del_mismo_prototipo_no_mezcla_hijos() -> None:
    """Bug real: `EST-02010` cuelga de dos etapas distintas del mismo
    prototipo (archivo real, `CAS-00004`), cada una con su propio material.
    Indexar `hijos` por clave del padre las fusionaría en una sola lista —
    debe indexarse por la fila del padre (§construir_arboles)."""
    filas = [
        (2, _fila_presupuesto(1, None, "CAS-1", "Zafiro", tipo="PROTOTIPO")),
        (3, _fila_presupuesto(1, "CAS-1", "NIV-1", "Planta baja", tipo="NIVEL DE CONSTRUCCION")),
        (4, _fila_presupuesto(1, "NIV-1", "ECO-1", "Muros", tipo="ETAPA DE CONSTRUCCION")),
        (5, _fila_presupuesto(1, "ECO-1", "EST-1", "Muro de 14", "M2", 10, "0", "0", tipo="CONCEPTO")),
        (6, _fila_presupuesto(1, "EST-1", "MAT-A", "Block", "PZ", 100, "10", "1000", tipo="MATERIAL")),
        (7, _fila_presupuesto(2, "NIV-1", "ECO-2", "Castillos", tipo="ETAPA DE CONSTRUCCION")),
        (8, _fila_presupuesto(1, "ECO-2", "EST-1", "Muro de 14", "M2", 5, "0", "0", tipo="CONCEPTO")),
        (9, _fila_presupuesto(1, "EST-1", "MAT-B", "Cemento", "KG", 50, "5", "250", tipo="MATERIAL")),
    ]
    arboles, errores, _pendientes, _omitidos = construir_arboles(filas, _MAPA_PRESUPUESTO)

    assert not errores
    (arbol,) = arboles
    hijos_eco1 = [h.clave for h in arbol.hijos.get(4, ())]
    hijos_eco2 = [h.clave for h in arbol.hijos.get(7, ())]
    assert hijos_eco1 == ["EST-1"]
    assert hijos_eco2 == ["EST-1"]

    primer_est1 = arbol.hijos[4][0]
    segundo_est1 = arbol.hijos[7][0]
    assert [h.clave for h in arbol.hijos.get(primer_est1.fila, ())] == ["MAT-A"]
    assert [h.clave for h in arbol.hijos.get(segundo_est1.fila, ())] == ["MAT-B"]


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
