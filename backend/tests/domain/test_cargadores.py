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
    MAPA_CPU,
    MATERIALES,
    ErrorDeCabecera,
    indice_de_letra,
    resolver_encabezados,
)
from obractrl.domain.cargadores.cpu import agrupar_conceptos
from obractrl.domain.cargadores.homologacion import Homologador
from obractrl.domain.cargadores.materiales import validar_material
from obractrl.domain.cargadores.reporte import ErrorEnFila, TipoPendiente
from obractrl.domain.cargadores.versionado import diferenciar
from obractrl.domain.shared.diccionario import CategoriaExplosion, ModoCarga
from obractrl.domain.shared.normalizacion import (
    ValorNoConvertible,
    a_booleano,
    a_decimal,
    a_fecha,
    canonizar_encabezado,
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
