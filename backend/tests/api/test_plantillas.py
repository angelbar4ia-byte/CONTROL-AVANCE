"""Las plantillas descargables: una por `TipoCarga`, no por archivo (§9.3, §10.6).

`plantilla_de` no toca la base, así que estas pruebas viven aquí y no en
`tests/integracion`: allá el módulo entero se salta cuando no hay Postgres, y
un contrato que solo se comprueba en CI se rompe en local sin que nadie lo vea
—que es exactamente lo que pasó al agregar la especialidad—.

Lo que fijan:

 1. **Conceptos se lee por nombre, no por posición.** CATALOGO_CONCEPTOS *era*
    CPU antes de separarlos: la plantilla no puede volver a dar el layout
    posicional de nueve columnas para un archivo que ahora es
    clave/descripción/unidad por nombre.
 2. **CPU sigue siendo posicional por letra**, con la G en blanco a propósito
    porque el archivo real no la usa.
 3. **El rótulo de cada columna es el que quien la llena tiene que escribir.**
    `plantillas.py` toma el primer alias del campo, así que el orden del `alias`
    es contrato visible, no detalle interno: la columna del oficio rotulada
    "frente" haría que alguien escribiera OBRA —el vocabulario de la etapa— y
    capturara el dato en el eje equivocado.
"""

from __future__ import annotations

from io import BytesIO

from openpyxl import load_workbook

from obractrl.adapters.excel.plantillas import nombre_de_plantilla, plantilla_de
from obractrl.domain.shared.diccionario import TipoCarga


def _encabezados(tipo: TipoCarga) -> list[str | None]:
    libro = load_workbook(BytesIO(plantilla_de(tipo)))
    hoja = libro.active
    assert hoja is not None
    return [celda.value for celda in hoja[1] if celda.value is not None]


def test_plantilla_de_catalogo_de_conceptos_es_por_nombre_no_posicional() -> None:
    """Antes CATALOGO_CONCEPTOS *era* CPU: la plantilla no puede seguir
    dando el layout posicional de 9 columnas para un archivo que ahora es
    clave/descripción/unidad(/clave_unidad) por nombre."""
    assert _encabezados(TipoCarga.CATALOGO_CONCEPTOS) == [
        "clave",
        "descripcion",
        "unidad",
        "clave_unidad",
        # El oficio (§8.3, migración 0047). Rotulado "especialidad" y no
        # "frente", que es como lo trae el archivo del cliente: quien descargue
        # la plantilla y lea "frente" escribiría OBRA o INSTALACIONES —los
        # cuatro de la etapa— en la columna de los quince oficios.
        "especialidad",
    ]


def test_la_plantilla_de_auxiliares_no_pide_oficio() -> None:
    """Un auxiliar es un componente de otro concepto, no algo que se contrate
    por oficio, y su aplicador no recibe el catálogo de especialidades.

    Con la columna en la plantilla, quien la llenara vería su dato leído y
    tirado en silencio — el mismo fallo que tuvieron RFC y CONTACTO."""
    assert "especialidad" not in _encabezados(TipoCarga.CONCEPTOS_AUXILIARES)


def test_la_plantilla_de_contratistas_rotula_los_dos_ejes_en_plural() -> None:
    """Las dos columnas admiten varios valores separados por coma.

    En singular, quien la llene pondría uno solo y perdería el resto de la
    capacidad del contratista, que es lo que después permite proponerlo."""
    encabezados = _encabezados(TipoCarga.CONTRATISTAS)
    assert "frentes" in encabezados
    assert "especialidades" in encabezados


def test_la_plantilla_de_etapas_pide_el_frente() -> None:
    """El otro eje (§8.3, migración 0045): la etapa lleva el frente y el
    concepto el oficio."""
    assert _encabezados(TipoCarga.ETAPAS_CONSTRUCTIVAS) == [
        "clave",
        "descripcion",
        "frente",
    ]


def test_plantilla_de_cpu_sigue_siendo_posicional_por_letra() -> None:
    """§10.6: CPU se lee por letra, no por nombre — la G queda en blanco a
    propósito porque el archivo real no la usa."""
    libro = load_workbook(BytesIO(plantilla_de(TipoCarga.CPU)))
    hoja = libro.active
    assert hoja is not None
    assert [celda.value for celda in hoja[1]] == [
        "CLAVE",
        "CLAVE INSUMO",
        "DESCRIPCION",
        "UNIDAD",
        "CANTIDAD",
        "P.U.",
        None,
        "FAMILIA",
        "TIPO",
    ]


def test_nombre_de_plantilla_distingue_conceptos_de_cpu() -> None:
    assert nombre_de_plantilla(TipoCarga.CATALOGO_CONCEPTOS) == "CABECERAS_CONCEPTOS.xlsx"
    assert nombre_de_plantilla(TipoCarga.CPU) == "CABECERAS_CPU.xlsx"
