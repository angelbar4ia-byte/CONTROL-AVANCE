"""Reporte de avance por alcance (§11.2, §5.1 "Avance total").

Lo que se cuida:

- Que los **dos totales** signifiquen lo que dice su nombre. `avance_por_
  actividades` es un conteo; `avance_promedio_simple` es una media aritmética.
  Confundirlos en una junta cambia decisiones, y los dos números pueden
  diferir muchísimo con obras de distinto tamaño — eso se comprueba abajo con
  un caso a propósito.
- Que `requiere_atencion` marque **lo mismo** que el filtro de la Torre. Que
  el reporte y la pantalla señalaran obras distintas sería la peor forma de
  discrepar: las dos se miran al mismo tiempo.
- Que una cartera recién dada de alta —sin actividades— no divida entre cero.

El exportador se prueba aparte y en superficie: que produzca un `.xlsx` que
`openpyxl` vuelve a abrir con los valores en su lugar. Lo que no se prueba es
el aspecto, que no es verificable así.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from typing import Any

from openpyxl import load_workbook

from obractrl.adapters.export.xlsx_avance import (
    avance_a_xlsx,
    nombre_de_archivo_avance,
)
from obractrl.domain.reportes.avance import ReporteDeAvance

GENERADO = datetime(2026, 8, 20, 15, 30, tzinfo=UTC)


def _fila(**cambios: Any) -> dict[str, Any]:
    """Una fila como la devuelve `RepositorioTorreSQL.estado_de_obras`."""
    base: dict[str, Any] = {
        "obra_id": "11111111-1111-1111-1111-111111111111",
        "obra_clave": "FRESNO 01",
        "proyecto_clave": "MAGNOLIA",
        "cluster_clave": "FRESNO",
        "residente_nombre": "Ana Ruiz",
        "obra_estatus": "en_proceso",
        "avance_pct": Decimal("40.00"),
        "actividades": 10,
        "concluidas": 4,
        "criticas": 2,
        "bloqueadas": 0,
        "incidencias_abiertas": 0,
        "incidencias_detienen": 0,
        "cierres_pendientes": 0,
    }
    return {**base, **cambios}


def _reporte(*filas: dict[str, Any]) -> ReporteDeAvance:
    return ReporteDeAvance.armar(filas=list(filas), generado_en=GENERADO)


class TestTotales:
    def test_cuenta_obras_y_actividades(self) -> None:
        reporte = _reporte(
            _fila(actividades=10, concluidas=4),
            _fila(actividades=30, concluidas=6),
        )

        assert reporte.total_obras == 2
        assert reporte.total_actividades == 40
        assert reporte.total_concluidas == 10

    def test_el_avance_por_actividades_es_un_conteo(self) -> None:
        reporte = _reporte(
            _fila(actividades=10, concluidas=4),
            _fila(actividades=30, concluidas=6),
        )

        # 10 de 40, no el promedio de 40% y 20%.
        assert reporte.avance_por_actividades == Decimal("25.00")

    def test_el_promedio_simple_no_pondera_y_por_eso_difiere(self) -> None:
        # El caso que justifica que los dos números existan y se nombren
        # distinto: una obra chica muy avanzada y una grande apenas empezada.
        reporte = _reporte(
            _fila(actividades=1, concluidas=1, avance_pct=Decimal("100.00")),
            _fila(actividades=99, concluidas=0, avance_pct=Decimal("0.00")),
        )

        assert reporte.avance_promedio_simple == Decimal("50.00")
        assert reporte.avance_por_actividades == Decimal("1.00")

    def test_una_cartera_nueva_no_divide_entre_cero(self) -> None:
        # Obras dadas de alta con `POST /obras/bulk` que todavía no se generan
        # desde su prototipo (§11.3 A).
        reporte = _reporte(_fila(actividades=0, concluidas=0, avance_pct=Decimal("0")))

        assert reporte.avance_por_actividades == Decimal("0.00")
        assert reporte.avance_promedio_simple == Decimal("0.00")

    def test_sin_obras_todo_es_cero(self) -> None:
        vacio = _reporte()

        assert vacio.total_obras == 0
        assert vacio.avance_por_actividades == Decimal("0.00")
        assert vacio.avance_promedio_simple == Decimal("0.00")
        assert vacio.obras_que_requieren_atencion == 0


class TestAtencion:
    def test_una_obra_tranquila_no_se_marca(self) -> None:
        assert _reporte(_fila()).obras[0].requiere_atencion is False

    def test_se_marca_por_cualquiera_de_los_cuatro_motivos(self) -> None:
        # Mismo criterio que `solo_con_pendientes` de la Torre.
        motivos = (
            {"bloqueadas": 1},
            {"incidencias_detienen": 1},
            {"incidencias_abiertas": 1},
            {"cierres_pendientes": 1},
        )
        for motivo in motivos:
            assert _reporte(_fila(**motivo)).obras[0].requiere_atencion is True

    def test_cuenta_obras_y_no_motivos(self) -> None:
        # Una obra con tres problemas es una obra que atender, no tres.
        reporte = _reporte(
            _fila(bloqueadas=2, incidencias_abiertas=1, cierres_pendientes=1),
            _fila(),
        )
        assert reporte.obras_que_requieren_atencion == 1


class TestFilas:
    def test_tolera_los_nulos_de_la_consulta(self) -> None:
        # `residente_nombre` es nulo en una obra sin residente asignado, y los
        # contadores llegan nulos si el `left join lateral` no encontró nada.
        reporte = _reporte(
            _fila(residente_nombre=None, avance_pct=None, actividades=None)
        )
        obra = reporte.obras[0]

        assert obra.residente == ""
        assert obra.avance_pct == Decimal("0.00")
        assert obra.actividades == 0


class TestExportador:
    def test_el_libro_se_vuelve_a_abrir_con_los_datos(self) -> None:
        reporte = _reporte(
            _fila(obra_clave="FRESNO 01", avance_pct=Decimal("40.00")),
            _fila(obra_clave="CEDRO 02", bloqueadas=3),
        )

        hoja = load_workbook(BytesIO(avance_a_xlsx(reporte))).active
        assert hoja is not None
        assert hoja.title == "Avance"

        textos = [
            celda.value
            for fila in hoja.iter_rows()
            for celda in fila
            if isinstance(celda.value, str)
        ]
        assert "FRESNO 01" in textos
        assert "CEDRO 02" in textos
        # La banda de totales nombra el promedio como "simple": es donde se
        # lee, no en el docstring del dominio.
        assert "AVANCE PROMEDIO SIMPLE" in textos

    def test_marca_las_obras_que_requieren_atención(self) -> None:
        reporte = _reporte(_fila(bloqueadas=1), _fila())

        hoja = load_workbook(BytesIO(avance_a_xlsx(reporte))).active
        assert hoja is not None
        marcas = [
            celda.value
            for fila in hoja.iter_rows()
            for celda in fila
            if celda.value == "SI"
        ]
        assert len(marcas) == 1

    def test_el_nombre_del_archivo_lleva_la_fecha_y_no_al_usuario(self) -> None:
        # Dos personas con alcances distintos generan archivos distintos;
        # poner el usuario en el nombre invitaría a compartirlos como si
        # fueran el mismo.
        assert nombre_de_archivo_avance(_reporte()) == "avance-2026-08-20.xlsx"
