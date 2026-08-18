"""Exportadores de `adapters/export/` (§11.2, §12.2, MD/06-reportes.md).

Viven en `adapters/` pero se prueban aquí —como `test_evidencias_r2.py`—
porque no necesitan ni Postgres ni Redis: reciben un agregado del dominio ya
armado y devuelven bytes o texto.

Lo que se verifica es la frontera que el DoD del agente de Reportes pide:
**el exportador dibuja, no calcula**. Los importes, el total y la verificación
de que la cabecera cuadre salen de `domain/reportes/`; aquí solo se comprueba
que lleguen al archivo sin deformarse y que un entorno sin las bibliotecas
nativas de WeasyPrint falle con un error nombrado (503) en vez de un 500 opaco.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from types import ModuleType

import pytest
from openpyxl import load_workbook

from obractrl.adapters.export.pdf import (
    CONTENT_TYPE_PDF,
    MotorDePdfNoDisponible,
    expediente_a_html,
    expediente_a_pdf,
    nombre_de_archivo_expediente,
)
from obractrl.adapters.export.xlsx import (
    CONTENT_TYPE_XLSX,
    estimacion_a_xlsx,
    nombre_de_archivo_estimacion,
)
from obractrl.domain.reportes.estimacion import ReporteDeEstimacion
from obractrl.domain.reportes.expediente import ExpedienteTecnico

AHORA = datetime(2026, 8, 18, 12, 30, tzinfo=UTC)


def _reporte(monto_total: Decimal = Decimal("37355.00")) -> ReporteDeEstimacion:
    return ReporteDeEstimacion.armar(
        estimacion={
            "id": "est-1",
            "obra_id": "obra-1",
            "folio": "EST-2026/33-001",
            "semana": 33,
            "anio": 2026,
            "modo": "destajo",
            "estatus": "validada",
            "monto_total": monto_total,
        },
        obra={"id": "obra-1", "clave": "OBR 001"},
        conceptos=[
            {
                "actividad_id": "act-1",
                "clave": "ALB-001",
                "descripcion": "Muro de block 15 cm",
                "unidad": "M2",
                "cantidad_validada": Decimal("120.500000"),
                "precio_unitario": Decimal("310.00"),
                "importe": Decimal("37355.00"),
            }
        ],
        generado_en=AHORA,
    )


def _celdas(contenido: bytes) -> list[list[object]]:
    libro = load_workbook(BytesIO(contenido))
    hoja = libro.active
    assert hoja is not None
    return [list(fila) for fila in hoja.iter_rows(values_only=True)]


class TestEstimacionAXlsx:
    def test_produce_un_libro_que_se_puede_volver_a_abrir(self) -> None:
        contenido = estimacion_a_xlsx(_reporte())
        libro = load_workbook(BytesIO(contenido))
        assert libro.sheetnames == ["Estimacion"]

    def test_el_encabezado_lleva_folio_obra_y_semana(self) -> None:
        """§3.2 (folio) y §3.1 (semana/año): el archivo tiene que identificarse
        solo, fuera del sistema."""
        planas = [str(v) for fila in _celdas(estimacion_a_xlsx(_reporte())) for v in fila]
        assert "EST-2026/33-001" in planas
        assert "OBR 001" in planas
        assert "33/2026" in planas

    def test_los_rotulos_van_en_mayusculas_y_sin_acentos(self) -> None:
        """Como las cabeceras canónicas del §10.6: el mismo archivo puede
        volver a entrar por un cargador."""
        filas = _celdas(estimacion_a_xlsx(_reporte()))
        encabezado = next(f for f in filas if f and f[0] == "CLAVE")
        assert encabezado[:6] == [
            "CLAVE",
            "DESCRIPCION",
            "UNIDAD",
            "CANTIDAD",
            "P.U.",
            "IMPORTE",
        ]

    def test_el_renglon_conserva_los_seis_decimales_de_la_cantidad(self) -> None:
        """`cantidad_validada` es `numeric(18,6)`: recortarla falsearía el
        renglón que sostiene el pago."""
        filas = _celdas(estimacion_a_xlsx(_reporte()))
        renglon = next(f for f in filas if f and f[0] == "ALB-001")
        assert Decimal(str(renglon[3])) == Decimal("120.500000")
        assert Decimal(str(renglon[5])) == Decimal("37355.00")

    def test_no_avisa_nada_cuando_la_estimacion_cuadra(self) -> None:
        planas = [str(v) for fila in _celdas(estimacion_a_xlsx(_reporte())) for v in fila]
        assert not any("AVISO" in v for v in planas)

    def test_avisa_en_el_archivo_cuando_la_cabecera_no_cuadra(self) -> None:
        """El `.xlsx` es el soporte del pago (§11.3 E): esconder la diferencia
        sería peor que exponerla."""
        contenido = estimacion_a_xlsx(_reporte(monto_total=Decimal("40000.00")))
        filas = _celdas(contenido)
        aviso = next(
            f for f in filas if f and isinstance(f[0], str) and f[0].startswith("AVISO")
        )
        assert Decimal(str(aviso[5])) == Decimal("37355.00")

    def test_el_nombre_del_archivo_no_trae_diagonales_del_folio(self) -> None:
        """El folio del §3.2 puede llevar `/`, que en un nombre de archivo es
        un separador de ruta."""
        nombre = nombre_de_archivo_estimacion(_reporte())
        assert "/" not in nombre
        assert nombre == "estimacion-EST-2026-33-001-OBR-001.xlsx"

    def test_el_content_type_es_el_de_xlsx(self) -> None:
        assert CONTENT_TYPE_XLSX.endswith("spreadsheetml.sheet")


# ---------------------------------------------------------------------------
# PDF del expediente
# ---------------------------------------------------------------------------


def _expediente(**cambios: object) -> ExpedienteTecnico:
    argumentos: dict[str, object] = {
        "obra": {
            "id": "11111111-1111-1111-1111-111111111111",
            "clave": "OBR 001",
            "estatus": "en_proceso",
            "avance_pct": Decimal("42.5"),
        },
        "generado_en": AHORA,
        "documentos": [
            {
                "id": "doc-1",
                "tipo": "contrato",
                "nombre": "Contrato <firmado> & anexo.pdf",
                "url": "org/obra/contrato.pdf",
                "fecha": AHORA,
            }
        ],
        "cierres": [
            {
                "id": "cie-1",
                "actividad_id": "act-1",
                "estatus": "validada",
                "cantidad": Decimal("10"),
                "monto": Decimal("1000.00"),
                "adjuntos": ["org/obra/cierre-1.jpg"],
                "fecha_valida": AHORA,
            }
        ],
        "estimaciones": [
            {
                "id": "est-1",
                "folio": "EST-2026-33-001",
                "semana": 33,
                "anio": 2026,
                "modo": "destajo",
                "estatus": "validada",
                "monto_total": Decimal("900.00"),
            }
        ],
        "revisiones": [],
        "incidencias": [],
    }
    argumentos.update(cambios)
    return ExpedienteTecnico.armar(**argumentos)  # type: ignore[arg-type]


class TestExpedienteAHtml:
    def test_lleva_las_cuatro_secciones_del_spec(self) -> None:
        html = expediente_a_html(_expediente())
        for titulo in ("Documentos", "Cierres", "Estimaciones", "Evidencias"):
            assert titulo in html

    def test_los_montos_son_los_del_dominio_sin_recalcular(self) -> None:
        expediente = _expediente()
        html = expediente_a_html(expediente)
        assert f"{expediente.monto_cerrado.monto} MXN" in html
        assert f"{expediente.monto_estimado.monto} MXN" in html

    def test_una_seccion_vacia_lo_dice_en_vez_de_desaparecer(self) -> None:
        """Una obra sin documentos y un PDF al que se le perdió la sección se
        leen igual si la tabla simplemente no aparece."""
        html = expediente_a_html(_expediente(documentos=[]))
        assert "Documentos" in html
        assert "Sin registros." in html

    def test_escapa_el_html_de_los_datos(self) -> None:
        """El nombre del documento lo escribe un usuario (§11.2): entra al PDF
        como texto, nunca como marcado."""
        html = expediente_a_html(_expediente())
        assert "&lt;firmado&gt; &amp; anexo" in html
        assert "<firmado>" not in html

    def test_lista_la_clave_de_r2_y_no_incrusta_la_foto(self) -> None:
        """§12.2: la clave es lo que permite recuperar la evidencia con una URL
        firmada; incrustarla convertiría el reporte en decenas de MB."""
        html = expediente_a_html(_expediente())
        assert "org/obra/cierre-1.jpg" in html
        assert "data:image" not in html and "<img" not in html

    def test_el_nombre_del_archivo_lleva_obra_y_fecha(self) -> None:
        assert nombre_de_archivo_expediente(_expediente()) == (
            "expediente-OBR-001-20260818.pdf"
        )


class TestMotorDePdf:
    def test_sin_las_libs_nativas_falla_con_un_error_nombrado(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """§12.8: WeasyPrint enlaza Pango/GObject por `cffi` y en un entorno
        sin ellas revienta **al importar**. El error tiene nombre propio para
        que el borde responda 503 y el resto de la API siga sirviendo."""
        monkeypatch.setitem(sys.modules, "weasyprint", ModuleType("weasyprint"))
        with pytest.raises(MotorDePdfNoDisponible, match="bibliotecas nativas"):
            expediente_a_pdf(_expediente())

    def test_el_error_nombra_la_causa_y_no_un_secreto(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "weasyprint", ModuleType("weasyprint"))
        with pytest.raises(MotorDePdfNoDisponible) as fallo:
            expediente_a_pdf(_expediente())
        assert "Pango/GObject" in str(fallo.value)

    def test_el_html_se_arma_aunque_no_haya_motor(self) -> None:
        """La razón de partir `expediente_a_html` de `expediente_a_pdf`: el
        contenido del reporte se puede probar sin native libs."""
        assert expediente_a_html(_expediente()).startswith("<style>")

    def test_el_content_type_es_el_de_pdf(self) -> None:
        assert CONTENT_TYPE_PDF == "application/pdf"
