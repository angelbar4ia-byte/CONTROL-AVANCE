"""Export de estimación a `.xlsx` (§11.2 `GET /estimaciones/{id}/export`).

Spec §11.2 (xlsx, **job**, roles C y SI) · §11.3 E.5 · §3.2 (folio) · §3.5
(moneda MXN) · §12.2 (Pandas + OpenPyXL) · MD/06-reportes.md ("nomenclatura y
unidades **del diccionario**"; "sin lógica de negocio propia").

**Cero aritmética aquí.** Los importes, el total y la verificación de que la
cabecera cuadre con sus renglones salen de `domain.reportes.estimacion`; este
módulo escribe celdas. Si mañana el reporte suma distinto, cambia el dominio y
esto no se toca —que es justamente lo que pide el DoD del agente de Reportes.

Se escribe con `openpyxl` directo y no con Pandas: la hoja lleva encabezado,
formatos de número por columna y una fila de total, cosa que un `to_excel` de
DataFrame no da sin post-procesar el libro de todas formas.
"""

from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from obractrl.domain.reportes.estimacion import ReporteDeEstimacion

__all__ = ["CONTENT_TYPE_XLSX", "estimacion_a_xlsx", "nombre_de_archivo_estimacion"]

CONTENT_TYPE_XLSX = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

_FORMATO_IMPORTE = '#,##0.00 "MXN"'
"""§3.5: moneda única MXN. Se rotula en la celda para que el archivo se
entienda fuera del sistema."""

_FORMATO_CANTIDAD = "#,##0.000000"
"""`estimacion_concepto.cantidad_validada` es `numeric(18,6)`: mostrar menos
decimales de los que guarda la base falsearía el renglón."""

_ENCABEZADOS = (
    ("CLAVE", 18),
    ("DESCRIPCION", 60),
    ("UNIDAD", 10),
    ("CANTIDAD", 16),
    ("P.U.", 16),
    ("IMPORTE", 18),
)
"""Rótulos en mayúsculas y sin acentos, como las cabeceras canónicas de carga
del §10.6: el mismo archivo puede volver a entrar por un cargador."""

_NEGRITA = Font(bold=True)


def nombre_de_archivo_estimacion(reporte: ReporteDeEstimacion) -> str:
    """Nombre sugerido de la descarga: folio del §3.2 y clave de obra."""
    folio = (reporte.folio or f"S{reporte.semana:02d}-{reporte.anio}").replace("/", "-")
    obra = reporte.obra_clave.replace(" ", "-") or "obra"
    return f"estimacion-{folio}-{obra}.xlsx"


def estimacion_a_xlsx(reporte: ReporteDeEstimacion) -> bytes:
    """Libro de una hoja con la cabecera y los renglones de la estimación."""
    libro = Workbook()
    hoja = libro.active
    assert hoja is not None  # noqa: S101 — Workbook() siempre crea una hoja
    hoja.title = "Estimacion"

    fila = _escribir_cabecera(hoja, reporte)
    fila = _escribir_tabla(hoja, reporte, desde=fila + 1)
    _escribir_total(hoja, reporte, fila=fila)
    _anchos(hoja)

    memoria = BytesIO()
    libro.save(memoria)
    libro.close()
    return memoria.getvalue()


def _escribir_cabecera(hoja: Worksheet, reporte: ReporteDeEstimacion) -> int:
    """Datos de identificación. Devuelve la última fila escrita."""
    hoja.cell(row=1, column=1, value="ESTIMACION").font = Font(bold=True, size=14)

    datos: tuple[tuple[str, object], ...] = (
        ("FOLIO", reporte.folio or "(sin folio)"),
        ("OBRA", reporte.obra_clave),
        ("SEMANA", f"{reporte.semana:02d}/{reporte.anio}"),
        ("MODO", reporte.modo.value),
        ("ESTATUS", reporte.estatus.value),
        ("ORIGEN", "ERP" if reporte.origen_erp else "ObraCtrl"),
        # Sin zona horaria en el texto: `generado_en` ya es UTC (§3.1) y el
        # sufijo lo deja explícito para quien reciba el archivo.
        ("GENERADO", reporte.generado_en.strftime("%Y-%m-%d %H:%M UTC")),
    )
    for desplazamiento, (etiqueta, valor) in enumerate(datos, start=2):
        hoja.cell(row=desplazamiento, column=1, value=etiqueta).font = _NEGRITA
        hoja.cell(row=desplazamiento, column=2, value=valor)

    return 1 + len(datos)


def _escribir_tabla(
    hoja: Worksheet, reporte: ReporteDeEstimacion, *, desde: int
) -> int:
    """Encabezados y renglones. Devuelve la fila siguiente a la última."""
    for columna, (titulo, _) in enumerate(_ENCABEZADOS, start=1):
        celda = hoja.cell(row=desde, column=columna, value=titulo)
        celda.font = _NEGRITA
        celda.alignment = Alignment(horizontal="center")

    fila = desde
    for concepto in reporte.conceptos:
        fila += 1
        # Un renglón fuera de catálogo no tiene CLAVE (§11.2 `POST
        # /actividades`): se marca en vez de dejarlo en blanco, que se leería
        # como un dato faltante.
        hoja.cell(
            row=fila,
            column=1,
            value=concepto.clave or ("(fuera de catalogo)" if concepto.fuera_catalogo else ""),
        )
        hoja.cell(row=fila, column=2, value=concepto.descripcion)
        hoja.cell(row=fila, column=3, value=concepto.unidad)
        celda_cantidad = hoja.cell(row=fila, column=4, value=concepto.cantidad)
        celda_cantidad.number_format = _FORMATO_CANTIDAD
        celda_pu = hoja.cell(row=fila, column=5, value=concepto.precio_unitario.monto)
        celda_pu.number_format = _FORMATO_IMPORTE
        celda_importe = hoja.cell(row=fila, column=6, value=concepto.importe.monto)
        celda_importe.number_format = _FORMATO_IMPORTE

    return fila + 1


def _escribir_total(hoja: Worksheet, reporte: ReporteDeEstimacion, *, fila: int) -> None:
    """Total de la cabecera y, si no cuadra, la evidencia de que no cuadra."""
    hoja.cell(row=fila, column=5, value="TOTAL").font = _NEGRITA
    celda = hoja.cell(row=fila, column=6, value=reporte.monto_total.monto)
    celda.font = _NEGRITA
    celda.number_format = _FORMATO_IMPORTE

    if reporte.cuadra:
        return

    # Un expediente que no cuadra consigo mismo tiene que decirlo: el archivo
    # es el soporte del pago (§11.3 E), y esconder la diferencia sería peor
    # que exponerla (`ReporteDeEstimacion.cuadra`).
    aviso = fila + 1
    hoja.cell(
        row=aviso,
        column=1,
        value=(
            "AVISO: la suma de los renglones no coincide con el monto de la "
            "cabecera. Suma de renglones:"
        ),
    ).font = _NEGRITA
    celda_suma = hoja.cell(row=aviso, column=6, value=reporte.monto_calculado.monto)
    celda_suma.number_format = _FORMATO_IMPORTE


def _anchos(hoja: Worksheet) -> None:
    for columna, (_, ancho) in enumerate(_ENCABEZADOS, start=1):
        hoja.column_dimensions[get_column_letter(columna)].width = ancho
