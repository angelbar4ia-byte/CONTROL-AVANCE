"""PDF del expediente técnico (§11.2 `GET /obras/{id}/expediente/pdf`).

Spec §11.2 (Expediente, **job**) · §7.9 (`ExpedienteDoc`, `Evidencia`) ·
§11.3 D (el expediente sostiene el cierre de obra) · §12.2 (WeasyPrint) ·
MD/06-reportes.md.

Dos funciones y la frontera entre ellas es lo importante:

- `expediente_a_html` es **pura**: agregado → texto. Se prueba sin native
  libs, sin BD y sin PDF.
- `expediente_a_pdf` es la que llama a WeasyPrint.

**WeasyPrint se importa dentro de la función, no arriba.** No es una manía de
estilo: WeasyPrint enlaza contra Pango/GObject por `cffi`, y en un entorno sin
esas bibliotecas nativas el `import` revienta —no falla al renderizar, falla al
importar—. Con el import arriba, ese entorno no podría ni **levantar la API**:
`main.py` importa los routers, que importarían esto. Aislado aquí, un
despliegue sin las libs responde 503 en el PDF y sigue sirviendo todo lo
demás, que es el mismo criterio de `AlmacenamientoNoConfigurado` cuando falta
R2 (§12.8).

Las **evidencias no se embeben**. El PDF lista sus claves de R2 (§7.8, §12.2);
descargar cada foto para incrustarla convertiría un reporte en una
transferencia de decenas de MB desde el worker, y la clave es lo que permite
recuperarla con una URL firmada cuando de verdad se necesita.
"""

from __future__ import annotations

from html import escape

from obractrl.domain.reportes.expediente import ExpedienteTecnico

__all__ = [
    "CONTENT_TYPE_PDF",
    "MotorDePdfNoDisponible",
    "expediente_a_html",
    "expediente_a_pdf",
    "nombre_de_archivo_expediente",
]

CONTENT_TYPE_PDF = "application/pdf"


class MotorDePdfNoDisponible(RuntimeError):
    """WeasyPrint no se pudo cargar en este entorno (§12.8).

    Es un fallo **de despliegue**, no del cliente: faltan las bibliotecas
    nativas (Pango/GObject) que WeasyPrint enlaza por `cffi`. Se distingue a
    propósito de un error genérico para que el borde responda un 503 legible
    en vez de un 500 opaco —igual que `AlmacenamientoNoConfigurado` con R2.
    """


_ESTILOS = """
@page { size: Letter; margin: 18mm 14mm; }
body { font-family: "DejaVu Sans", "Helvetica", sans-serif; font-size: 9pt;
       color: #1a1a1a; }
h1 { font-size: 16pt; margin: 0 0 2mm 0; }
h2 { font-size: 11pt; margin: 6mm 0 2mm 0; border-bottom: 1px solid #999;
     padding-bottom: 1mm; }
.meta { color: #555; font-size: 8pt; margin-bottom: 4mm; }
table { width: 100%; border-collapse: collapse; margin-bottom: 3mm; }
th { background: #eee; text-align: left; padding: 1.5mm; font-size: 8pt;
     border-bottom: 1px solid #999; }
td { padding: 1.5mm; border-bottom: 0.4pt solid #ddd; font-size: 8pt;
     vertical-align: top; }
td.num { text-align: right; white-space: nowrap; }
.clave { font-family: "DejaVu Sans Mono", monospace; font-size: 7pt;
         word-break: break-all; }
.resumen td { border: none; padding: 1mm 4mm 1mm 0; }
.resumen .etiqueta { color: #555; }
.resumen .valor { font-weight: bold; }
.vacio { color: #777; font-style: italic; }
"""


def nombre_de_archivo_expediente(expediente: ExpedienteTecnico) -> str:
    obra = expediente.obra_clave.replace(" ", "-") or "obra"
    fecha = expediente.generado_en.strftime("%Y%m%d")
    return f"expediente-{obra}-{fecha}.pdf"


def expediente_a_pdf(expediente: ExpedienteTecnico) -> bytes:
    """Renderiza el expediente. Levanta `MotorDePdfNoDisponible` si no hay motor."""
    try:
        from weasyprint import HTML  # noqa: PLC0415 — ver el encabezado
    except Exception as exc:  # noqa: BLE001 — cffi levanta OSError, no ImportError
        # El detalle va al mensaje pero nunca un secreto: es una ruta de
        # biblioteca del sistema, que es exactamente lo que el operador
        # necesita para instalarla.
        raise MotorDePdfNoDisponible(
            "WeasyPrint no se pudo cargar en este entorno; faltan sus "
            f"bibliotecas nativas (Pango/GObject): {type(exc).__name__}: {exc}"
        ) from exc

    documento = HTML(string=expediente_a_html(expediente))
    return bytes(documento.write_pdf())


def expediente_a_html(expediente: ExpedienteTecnico) -> str:
    """El expediente como HTML imprimible. Función pura: sin PDF, sin BD."""
    partes = [
        "<style>",
        _ESTILOS,
        "</style>",
        f"<h1>Expediente técnico · {escape(expediente.obra_clave)}</h1>",
        (
            '<p class="meta">Obra '
            f"{escape(expediente.obra_id)} · estatus "
            f"{escape(expediente.obra_estatus or 'n/d')} · avance "
            f"{expediente.avance_pct}% · generado "
            f"{expediente.generado_en.strftime('%Y-%m-%d %H:%M UTC')}</p>"
        ),
        _resumen(expediente),
        _documentos(expediente),
        _cierres(expediente),
        _estimaciones(expediente),
        _evidencias(expediente),
    ]
    return "".join(partes)


def _resumen(expediente: ExpedienteTecnico) -> str:
    filas = (
        ("Documentos", str(len(expediente.documentos))),
        ("Evidencias", str(expediente.n_evidencias)),
        ("Cierres", str(len(expediente.cierres))),
        ("Estimaciones", str(len(expediente.estimaciones))),
        ("Monto cerrado (validado)", f"{expediente.monto_cerrado.monto} MXN"),
        ("Monto estimado (validado)", f"{expediente.monto_estimado.monto} MXN"),
    )
    celdas = "".join(
        f'<tr><td class="etiqueta">{escape(etiqueta)}</td>'
        f'<td class="valor">{escape(valor)}</td></tr>'
        for etiqueta, valor in filas
    )
    return f'<h2>Resumen</h2><table class="resumen">{celdas}</table>'


def _tabla(titulo: str, encabezados: tuple[str, ...], filas: list[str]) -> str:
    if not filas:
        return f'<h2>{escape(titulo)}</h2><p class="vacio">Sin registros.</p>'
    cabecera = "".join(f"<th>{escape(t)}</th>" for t in encabezados)
    return (
        f"<h2>{escape(titulo)}</h2>"
        f"<table><thead><tr>{cabecera}</tr></thead>"
        f"<tbody>{''.join(filas)}</tbody></table>"
    )


def _fecha(valor: object) -> str:
    return valor.strftime("%Y-%m-%d") if hasattr(valor, "strftime") else ""


def _documentos(expediente: ExpedienteTecnico) -> str:
    filas = [
        (
            f"<tr><td>{escape(doc.tipo.value)}</td>"
            f"<td>{escape(doc.nombre)}</td>"
            f'<td class="clave">{escape(doc.clave)}</td>'
            f"<td>{escape(_fecha(doc.fecha))}</td></tr>"
        )
        for doc in expediente.documentos
    ]
    return _tabla("Documentos (§7.9)", ("Tipo", "Nombre", "Clave en R2", "Fecha"), filas)


def _cierres(expediente: ExpedienteTecnico) -> str:
    filas = [
        (
            f"<tr><td>{escape(cierre.estatus.value)}</td>"
            f'<td class="clave">{escape(cierre.actividad_id)}</td>'
            f'<td class="num">{cierre.cantidad}</td>'
            f'<td class="num">{cierre.monto.monto}</td>'
            f"<td>{escape(_fecha(cierre.fecha_valida))}</td></tr>"
        )
        for cierre in expediente.cierres
    ]
    return _tabla(
        "Cierres de actividad (§11.3 C)",
        ("Estatus", "Actividad", "Cantidad", "Monto MXN", "Validado"),
        filas,
    )


def _estimaciones(expediente: ExpedienteTecnico) -> str:
    filas = [
        (
            f"<tr><td>{escape(estimacion.folio or '(sin folio)')}</td>"
            f"<td>{estimacion.semana:02d}/{estimacion.anio}</td>"
            f"<td>{escape(estimacion.modo)}</td>"
            f"<td>{escape(estimacion.estatus.value)}</td>"
            f'<td class="num">{estimacion.monto.monto}</td></tr>'
        )
        for estimacion in expediente.estimaciones
    ]
    return _tabla(
        "Estimaciones (§11.3 E)",
        ("Folio", "Semana", "Modo", "Estatus", "Monto MXN"),
        filas,
    )


def _evidencias(expediente: ExpedienteTecnico) -> str:
    filas = [
        (
            f"<tr><td>{escape(evidencia.origen)}</td>"
            f'<td class="clave">{escape(evidencia.clave)}</td>'
            f"<td>{escape(_fecha(evidencia.fecha))}</td></tr>"
        )
        for evidencia in expediente.evidencias
    ]
    return _tabla("Evidencias (§7.8, §12.2)", ("Origen", "Clave en R2", "Fecha"), filas)
