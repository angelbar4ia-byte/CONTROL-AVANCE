"""Reporte de estimación: qué renglones lleva y cómo suma (§11.2, §11.3 E).

`domain.reportes.estimacion` es lo que alimenta el `.xlsx` del §11.2
(`GET /estimaciones/{id}/export`). Aquí se fija la parte que **no** puede
vivir en el exportador:

- la suma de los renglones (§11.3 E.2: `cantidad_validada × precio`),
- la verificación de que la cabecera guardada cuadre con esa suma —un
  expediente que no cuadra consigo mismo tiene que decirlo, no esconderlo—,
- y que el reporte **no invente IVA**: el §3.5 lo fija por familia y lo aplica
  a la valuación de materiales (§10.5); la `Estimacion` del §7.6 tiene una
  sola columna de importe.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from obractrl.domain.reportes.estimacion import ReporteDeEstimacion
from obractrl.domain.shared.diccionario import EstatusEstimacion, ModoPago
from obractrl.domain.shared.valores import Dinero

AHORA = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)

CONCEPTOS = [
    {
        "actividad_id": "act-1",
        "clave": "ALB-001",
        "descripcion": "Muro de block 15 cm",
        "unidad": "M2",
        "cantidad_validada": Decimal("120.500000"),
        "precio_unitario": Decimal("310.00"),
        "importe": Decimal("37355.00"),
    },
    {
        "actividad_id": "act-2",
        "clave": None,
        "descripcion": "Detalle no catalogado",
        "unidad": "PZA",
        "cantidad_validada": Decimal("3"),
        "precio_unitario": Decimal("500.00"),
        "importe": Decimal("1500.00"),
        "fuera_catalogo": True,
    },
]

TOTAL = Decimal("38855.00")


def _reporte(
    conceptos: list[dict] | None = None,
    monto_total: Decimal | None = None,
    **cambios: object,
) -> ReporteDeEstimacion:
    filas = CONCEPTOS if conceptos is None else conceptos
    estimacion: dict = {
        "id": "est-1",
        "obra_id": "obra-1",
        "folio": "EST-2026-33-001",
        "semana": 33,
        "anio": 2026,
        "modo": "destajo",
        "estatus": "validada",
        "monto_total": TOTAL if monto_total is None else monto_total,
        "origen_erp": False,
    }
    estimacion.update(cambios)
    return ReporteDeEstimacion.armar(
        estimacion=estimacion,
        obra={"id": "obra-1", "clave": "OBR-001"},
        conceptos=filas,
        generado_en=AHORA,
    )


class TestCabecera:
    def test_conserva_folio_semana_y_modo(self) -> None:
        """§3.2 (folio) y §3.1 (semana/año) son la identidad del documento."""
        reporte = _reporte()
        assert reporte.folio == "EST-2026-33-001"
        assert (reporte.semana, reporte.anio) == (33, 2026)
        assert reporte.modo is ModoPago.DESTAJO
        assert reporte.estatus is EstatusEstimacion.VALIDADA
        assert reporte.obra_clave == "OBR-001"

    def test_una_estimacion_sin_folio_todavia_se_exporta(self) -> None:
        """El folio se asigna al generar (§3.2), pero un borrador importado
        del ERP puede no traerlo y aun así hay que poder verlo."""
        assert _reporte(folio=None).folio is None

    def test_el_reloj_entra_por_el_borde(self) -> None:
        assert _reporte().generado_en == AHORA


class TestSumas:
    def test_suma_los_importes_de_los_renglones(self) -> None:
        assert _reporte().monto_calculado == Dinero(TOTAL)

    def test_cuadra_cuando_la_cabecera_coincide_con_sus_renglones(self) -> None:
        assert _reporte().cuadra is True

    def test_no_cuadra_cuando_la_cabecera_dice_otra_cosa(self) -> None:
        """La verificación es el motivo por el que el reporte suma de nuevo en
        vez de confiar en `estimacion.monto_total`."""
        reporte = _reporte(monto_total=Decimal("40000.00"))
        assert reporte.cuadra is False
        assert reporte.monto_calculado == Dinero(TOTAL)

    def test_una_estimacion_sin_renglones_suma_cero_y_no_revienta(self) -> None:
        reporte = _reporte(conceptos=[], monto_total=Decimal("0"))
        assert reporte.monto_calculado.es_cero
        assert reporte.cuadra is True

    def test_suma_la_cantidad_con_los_seis_decimales_de_la_base(self) -> None:
        """`estimacion_concepto.cantidad_validada` es `numeric(18,6)`."""
        assert _reporte().cantidad_total == Decimal("123.500000")

    def test_no_le_agrega_iva_a_nada(self) -> None:
        """§3.5 fija el IVA por familia sobre materiales (§10.5); la
        `Estimacion` del §7.6 tiene una sola columna de importe. Sumar un IVA
        aquí sería inventar una regla que el spec no escribió."""
        reporte = _reporte()
        assert reporte.monto_calculado.monto == sum(
            Decimal(str(c["importe"])) for c in CONCEPTOS
        )


class TestRenglones:
    def test_marca_el_renglon_fuera_de_catalogo(self) -> None:
        """§11.2 `POST /actividades`: una actividad extra-catálogo no tiene
        CLAVE, y eso no es un dato faltante sino una condición del renglón."""
        fuera = _reporte().conceptos[1]
        assert fuera.fuera_catalogo is True
        assert fuera.clave == ""

    def test_la_descripcion_de_la_actividad_manda_sobre_la_del_catalogo(self) -> None:
        """Una actividad de catálogo puede haber precisado su descripción en
        obra (§7.6); el reporte muestra lo que se ejecutó."""
        reporte = _reporte(
            conceptos=[
                {
                    "actividad_id": "act-1",
                    "clave": "ALB-001",
                    "descripcion": "Muro de block, eje 3",
                    "descripcion_concepto": "Muro de block 15 cm",
                    "unidad": "M2",
                    "cantidad_validada": Decimal("1"),
                    "precio_unitario": Decimal("10"),
                    "importe": Decimal("10"),
                }
            ],
            monto_total=Decimal("10"),
        )
        assert reporte.conceptos[0].descripcion == "Muro de block, eje 3"

    def test_cae_a_la_descripcion_del_catalogo_si_la_actividad_no_trae(self) -> None:
        reporte = _reporte(
            conceptos=[
                {
                    "actividad_id": "act-1",
                    "clave": "ALB-001",
                    "descripcion": None,
                    "descripcion_concepto": "Muro de block 15 cm",
                    "unidad": "M2",
                    "cantidad_validada": Decimal("1"),
                    "precio_unitario": Decimal("10"),
                    "importe": Decimal("10"),
                }
            ],
            monto_total=Decimal("10"),
        )
        assert reporte.conceptos[0].descripcion == "Muro de block 15 cm"

    def test_los_importes_son_dinero_redondeado_a_centavos(self) -> None:
        """§3.5: MXN a dos decimales. El exportador escribe celdas, no
        redondea."""
        reporte = _reporte()
        assert all(isinstance(c.importe, Dinero) for c in reporte.conceptos)
        assert reporte.conceptos[0].precio_unitario.monto == Decimal("310.00")


class TestDatosCanonicos:
    @pytest.mark.parametrize("campo", ["modo", "estatus"])
    def test_un_valor_fuera_del_enum_revienta_en_vez_de_dibujarse(
        self, campo: str
    ) -> None:
        """§8.2: si la base trajera un valor que no es canónico, es un defecto
        de datos y tiene que verse aquí, no en el `.xlsx` del cliente."""
        with pytest.raises(ValueError, match="raro"):
            _reporte(**{campo: "raro"})
