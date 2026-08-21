"""Export del reporte de avance a `.xlsx` (§11.2 `POST /reportes/{tipo}`).

Spec §11.2 ("Reportes … genera Excel/PDF (job), **por alcance**") · §5.1
("Avance total") · MD/06-reportes.md ("nomenclatura y unidades **del
diccionario**"; "sin lógica de negocio propia").

Módulo aparte de `xlsx.py` y no una función más dentro: los dos comparten
`openpyxl` y poco más. El de estimación dibuja **un documento** —cabecera,
renglones, total, con formato de moneda del §3.5—; este dibuja **una tabla de
cartera**, con una fila por obra y una banda de totales. Meterlos juntos
obligaría a que cada helper privado supiera de cuál de los dos reportes está
hablando.

**Cero aritmética aquí.** Los totales salen de `domain.reportes.avance`; este
módulo escribe celdas. Mismo DoD que el exportador de estimación.
"""

from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from obractrl.domain.reportes.avance import ReporteDeAvance

__all__ = ["CONTENT_TYPE_XLSX", "avance_a_xlsx", "nombre_de_archivo_avance"]

CONTENT_TYPE_XLSX = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

_FORMATO_PCT = '0.00"%"'
"""El porcentaje viaja como número 0-100, no como fracción 0-1: es lo que
guarda `obra.avance_pct` (§6) y convertirlo aquí solo agregaría un lugar donde
equivocarse por un factor de cien."""

_ENCABEZADOS: tuple[tuple[str, int], ...] = (
    ("PROYECTO", 16),
    ("CLUSTER", 16),
    ("OBRA", 16),
    ("RESIDENTE", 24),
    ("ESTATUS", 14),
    ("AVANCE", 12),
    ("ACTIVIDADES", 14),
    ("CONCLUIDAS", 13),
    ("CRITICAS", 11),
    ("BLOQUEADAS", 13),
    ("INCIDENCIAS", 13),
    ("DETIENEN", 11),
    ("CIERRES PEND.", 15),
    ("ATENCION", 11),
)
"""Rótulos en mayúsculas y sin acentos, como las cabeceras canónicas de carga
del §10.6: el archivo se lee fuera del sistema y a veces vuelve a entrar."""

_NEGRITA = Font(bold=True)


def nombre_de_archivo_avance(reporte: ReporteDeAvance) -> str:
    """Nombre sugerido de la descarga.

    Lleva la fecha y no el nombre de quien lo pidió: dos personas con alcances
    distintos generan archivos distintos, y poner el usuario en el nombre
    invitaría a compartirlos como si fueran el mismo.
    """
    return f"avance-{reporte.generado_en.strftime('%Y-%m-%d')}.xlsx"


def avance_a_xlsx(reporte: ReporteDeAvance) -> bytes:
    """Libro de una hoja: totales arriba, una fila por obra debajo."""
    libro = Workbook()
    hoja = libro.active
    assert hoja is not None  # noqa: S101 — Workbook() siempre crea una hoja
    hoja.title = "Avance"

    fila = _escribir_cabecera(hoja, reporte)
    _escribir_tabla(hoja, reporte, desde=fila + 1)
    _anchos(hoja)

    # Congelar bajo el encabezado de la tabla: una cartera del §12.1 son 60-80
    # renglones y sin esto se pierde de qué columna es cada número al tercer
    # scroll.
    hoja.freeze_panes = hoja.cell(row=fila + 2, column=1)

    memoria = BytesIO()
    libro.save(memoria)
    libro.close()
    return memoria.getvalue()


def _escribir_cabecera(hoja: Worksheet, reporte: ReporteDeAvance) -> int:
    """Totales del alcance. Devuelve la última fila escrita."""
    hoja.cell(row=1, column=1, value="AVANCE DE OBRAS").font = Font(bold=True, size=14)

    datos: tuple[tuple[str, object], ...] = (
        ("OBRAS", reporte.total_obras),
        ("ACTIVIDADES", reporte.total_actividades),
        ("CONCLUIDAS", reporte.total_concluidas),
        ("AVANCE POR ACTIVIDADES", float(reporte.avance_por_actividades)),
        # El nombre dice "simple" a propósito: no es un avance ponderado, y el
        # encabezado es donde se lee, no el docstring del dominio.
        ("AVANCE PROMEDIO SIMPLE", float(reporte.avance_promedio_simple)),
        ("REQUIEREN ATENCION", reporte.obras_que_requieren_atencion),
        # Sin zona horaria en el texto: `generado_en` ya es UTC (§3.1).
        ("GENERADO", reporte.generado_en.strftime("%Y-%m-%d %H:%M UTC")),
        (
            "ALCANCE",
            "Las obras visibles para quien generó el reporte (RLS, §12.4)",
        ),
    )

    for desplazamiento, (etiqueta, valor) in enumerate(datos, start=2):
        hoja.cell(row=desplazamiento, column=1, value=etiqueta).font = _NEGRITA
        celda = hoja.cell(row=desplazamiento, column=2, value=valor)
        if etiqueta.startswith("AVANCE"):
            celda.number_format = _FORMATO_PCT

    return 1 + len(datos)


def _escribir_tabla(hoja: Worksheet, reporte: ReporteDeAvance, *, desde: int) -> None:
    for columna, (titulo, _) in enumerate(_ENCABEZADOS, start=1):
        celda = hoja.cell(row=desde, column=columna, value=titulo)
        celda.font = _NEGRITA
        celda.alignment = Alignment(horizontal="center")

    for desplazamiento, obra in enumerate(reporte.obras, start=1):
        fila = desde + desplazamiento
        valores: tuple[object, ...] = (
            obra.proyecto_clave,
            obra.cluster_clave,
            obra.obra_clave,
            obra.residente,
            obra.estatus,
            float(obra.avance_pct),
            obra.actividades,
            obra.concluidas,
            obra.criticas,
            obra.bloqueadas,
            obra.incidencias_abiertas,
            obra.incidencias_detienen,
            obra.cierres_pendientes,
            # "SI"/"" y no TRUE/FALSE: la columna se filtra a ojo en Excel, y
            # una celda vacía se distingue de un vistazo mejor que un FALSE.
            "SI" if obra.requiere_atencion else "",
        )
        for columna, valor in enumerate(valores, start=1):
            celda = hoja.cell(row=fila, column=columna, value=valor)
            if columna == 6:
                celda.number_format = _FORMATO_PCT


def _anchos(hoja: Worksheet) -> None:
    for columna, (_, ancho) in enumerate(_ENCABEZADOS, start=1):
        hoja.column_dimensions[get_column_letter(columna)].width = ancho
