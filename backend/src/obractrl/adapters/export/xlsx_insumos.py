"""Insumos programados a `.xlsx` (§7.3, §7.5, §11.2).

Es el mismo escritor que `xlsx_avance.py` aplicado a una tabla que crece a lo
ancho: una columna fija por identidad del insumo y **una columna por periodo**.
El archivo se abre en Excel y se manda por correo a un proveedor, así que las
cabeceras van en mayúsculas y sin acentos, como las canónicas de carga (§10.6):
a veces vuelven a entrar al sistema.

**Cero aritmética aquí.** Todas las cifras vienen de
`domain.insumos.programado`; este módulo solo las acomoda en celdas. Si
apareciera una suma en este archivo, sería una segunda definición del mismo
número — y la que se imprime no es la que se ve en pantalla.
"""

from __future__ import annotations

from datetime import date
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.worksheet.worksheet import Worksheet

from obractrl.application.casos_uso.consultar_insumos_programados import (
    InsumosProgramados,
)

__all__ = ["insumos_a_xlsx", "nombre_de_archivo_insumos"]

CONTENT_TYPE_XLSX = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

_FORMATO_CANTIDAD = "#,##0.00"
_FORMATO_MXN = '"$"#,##0.00'

_FIJAS: tuple[tuple[str, int], ...] = (
    ("CLAVE", 16),
    ("DESCRIPCION", 42),
    ("UNIDAD", 10),
    ("TIPO", 14),
    ("DIAS ENTREGA", 14),
)
"""Las columnas de identidad, antes de los periodos. `DIAS ENTREGA` viaja
aunque esté vacío: quien recibe el archivo necesita saber de cuáles insumos
todavía no se ha capturado el plazo."""

_ANCHO_PERIODO = 13
_NEGRITA = Font(bold=True)


def nombre_de_archivo_insumos(generado_en: date) -> str:
    """Nombre sugerido de la descarga.

    Lleva la fecha y no quién lo pidió: dos personas con alcances distintos
    generan archivos distintos, y poner el usuario en el nombre invitaría a
    compartirlos como si fueran el mismo (mismo criterio que el de avance).
    """
    return f"insumos-programados-{generado_en.strftime('%Y-%m-%d')}.xlsx"


def insumos_a_xlsx(
    resultado: InsumosProgramados,
    *,
    con_importe: bool,
    generado_en: date,
) -> bytes:
    """Libro de una hoja: la matriz insumo × periodo, con sus totales.

    `con_importe` es la misma decisión de rol que tomó el borde: el archivo que
    baja un residente no trae dinero, igual que su pantalla.
    """
    libro = Workbook()
    hoja = libro.active
    assert hoja is not None  # noqa: S101 — Workbook() siempre crea una hoja
    hoja.title = "Insumos"

    matriz = resultado.matriz
    hay_surtido = bool(resultado.surtido)

    fila = _escribir_cabecera(hoja, resultado, generado_en=generado_en)
    encabezado = fila + 1
    _escribir_tabla(
        hoja,
        resultado,
        desde=encabezado,
        con_importe=con_importe,
        hay_surtido=hay_surtido,
    )
    _anchos(hoja, n_periodos=len(matriz.periodos))

    # Se congelan el encabezado **y** las columnas de identidad: con veintiséis
    # semanas a la derecha, sin esto se pierde de qué insumo es el número al
    # segundo scroll horizontal.
    hoja.freeze_panes = hoja.cell(row=encabezado + 1, column=len(_FIJAS) + 1)

    memoria = BytesIO()
    libro.save(memoria)
    libro.close()
    return memoria.getvalue()


def _escribir_cabecera(
    hoja: Worksheet, resultado: InsumosProgramados, *, generado_en: date
) -> int:
    """Lo que hace falta para entender el archivo fuera del sistema."""
    hoja.cell(row=1, column=1, value="INSUMOS PROGRAMADOS").font = Font(
        bold=True, size=14
    )
    matriz = resultado.matriz

    datos: tuple[tuple[str, object], ...] = (
        ("INSUMOS", len(matriz.filas)),
        ("PERIODOS", len(matriz.periodos)),
        (
            "RANGO",
            f"{matriz.periodos[0].desde} a {matriz.periodos[-1].hasta}"
            if matriz.periodos
            else "sin periodos",
        ),
        ("GENERADO", generado_en.strftime("%Y-%m-%d")),
        (
            "ALCANCE",
            "Las obras visibles para quien genero el reporte (RLS, §12.4)",
        ),
        (
            "SIN CALENDARIZAR",
            len(matriz.sin_programar),
        ),
        (
            "SIN APU",
            len(matriz.sin_explosion),
        ),
    )

    for desplazamiento, (etiqueta, valor) in enumerate(datos, start=2):
        hoja.cell(row=desplazamiento, column=1, value=etiqueta).font = _NEGRITA
        hoja.cell(row=desplazamiento, column=2, value=valor)

    return 1 + len(datos)


def _escribir_tabla(
    hoja: Worksheet,
    resultado: InsumosProgramados,
    *,
    desde: int,
    con_importe: bool,
    hay_surtido: bool,
) -> None:
    matriz = resultado.matriz

    titulos = [titulo for titulo, _ in _FIJAS]
    titulos += [p.etiqueta.upper() for p in matriz.periodos]
    titulos.append("TOTAL")
    if hay_surtido:
        titulos.append("YA SURTIDO")
    if con_importe:
        titulos.append("IMPORTE")

    for columna, titulo in enumerate(titulos, start=1):
        celda = hoja.cell(row=desde, column=columna, value=titulo)
        celda.font = _NEGRITA
        celda.alignment = Alignment(horizontal="center")

    for desplazamiento, fila in enumerate(matriz.filas, start=1):
        renglon = desde + desplazamiento
        insumo = fila.insumo

        valores: list[object] = [
            insumo.clave,
            insumo.descripcion,
            insumo.unidad or "",
            insumo.tipo,
            insumo.dias_entrega,
        ]
        valores += [float(c) for c in fila.cantidades]
        valores.append(float(fila.total))
        if hay_surtido:
            valores.append(float(resultado.surtido.get(insumo.insumo_id, 0)))
        if con_importe:
            valores.append(None if fila.importe is None else float(fila.importe))

        for columna, valor in enumerate(valores, start=1):
            celda = hoja.cell(row=renglon, column=columna, value=valor)
            if columna > len(_FIJAS):
                celda.number_format = (
                    _FORMATO_MXN
                    if con_importe and columna == len(valores)
                    else _FORMATO_CANTIDAD
                )


def _anchos(hoja: Worksheet, *, n_periodos: int) -> None:
    for columna, (_, ancho) in enumerate(_FIJAS, start=1):
        hoja.column_dimensions[hoja.cell(row=1, column=columna).column_letter].width = (
            ancho
        )
    # Los periodos, el total y las dos columnas opcionales comparten ancho: son
    # todas cifras y alinearlas parejo es lo que hace la tabla legible a lo
    # ancho.
    for indice in range(n_periodos + 3):
        columna = len(_FIJAS) + 1 + indice
        hoja.column_dimensions[hoja.cell(row=1, column=columna).column_letter].width = (
            _ANCHO_PERIODO
        )
