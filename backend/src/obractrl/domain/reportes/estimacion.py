"""Reporte de una estimación semanal: qué renglones lleva y cómo suma.

Spec §11.2 (`GET /estimaciones/{id}/export` — xlsx, job, roles C y SI) ·
§11.3 E · §7.6 (`Estimacion`, `EstimacionConcepto`) · §3.2 (folio) · §3.5
(moneda) · MD/06-reportes.md ("números/IVA/folios conforme al spec").

**Sin IVA, a propósito.** El §3.5 fija el IVA **por familia** y lo aplica a la
valuación de materiales (§10.5); la `Estimacion` del §7.6 tiene una sola
columna de importe (`monto_total`) y sus renglones son `cantidad_validada ×
precio` (§11.3 E.2), sin desglose fiscal. Agregarle un IVA aquí sería
inventar una regla que el spec no escribió, así que el reporte muestra los
mismos importes que la base.

Lo que sí agrega el reporte es una **verificación**: `monto_calculado` vuelve
a sumar los renglones y `cuadra` compara contra la cabecera guardada. Un
expediente que no cuadra consigo mismo es justo lo que un reporte de auditoría
tiene que hacer visible en vez de esconder.

Módulo puro: sin BD, sin openpyxl, sin reloj (§12.11). El `.xlsx` lo dibuja
`adapters/export/xlsx.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from obractrl.domain.shared.diccionario import EstatusEstimacion, ModoPago
from obractrl.domain.shared.valores import Dinero

__all__ = ["ConceptoDelReporte", "ReporteDeEstimacion"]


@dataclass(frozen=True, slots=True)
class ConceptoDelReporte:
    """Un renglón de `EstimacionConcepto` con lo necesario para rotularlo."""

    actividad_id: str
    clave: str
    """CLAVE del concepto (§3.3). Vacía si el renglón es fuera de catálogo."""
    descripcion: str
    unidad: str
    cantidad: Decimal
    precio_unitario: Dinero
    importe: Dinero
    fuera_catalogo: bool = False


@dataclass(frozen=True, slots=True)
class ReporteDeEstimacion:
    """Cabecera + renglones de una estimación, listos para exportar."""

    id: str
    folio: str | None
    obra_id: str
    obra_clave: str
    semana: int
    anio: int
    modo: ModoPago
    estatus: EstatusEstimacion
    monto_total: Dinero
    """Lo que dice la cabecera guardada (`estimacion.monto_total`)."""
    conceptos: tuple[ConceptoDelReporte, ...]
    generado_en: datetime
    origen_erp: bool = False

    @property
    def monto_calculado(self) -> Dinero:
        """Σ de los importes de los renglones (§11.3 E.2)."""
        total = Dinero(0)
        for concepto in self.conceptos:
            total = total + concepto.importe
        return total

    @property
    def cuadra(self) -> bool:
        """¿La cabecera coincide con la suma de sus renglones?"""
        return self.monto_calculado == self.monto_total

    @property
    def cantidad_total(self) -> Decimal:
        return sum((c.cantidad for c in self.conceptos), Decimal(0))

    @classmethod
    def armar(
        cls,
        *,
        estimacion: dict,
        obra: dict,
        conceptos: list[dict],
        generado_en: datetime,
    ) -> ReporteDeEstimacion:
        """Arma el reporte desde las filas crudas de los puertos."""
        return cls(
            id=str(estimacion["id"]),
            folio=str(estimacion["folio"]) if estimacion.get("folio") else None,
            obra_id=str(estimacion["obra_id"]),
            obra_clave=str(obra.get("clave") or ""),
            semana=int(estimacion["semana"]),
            anio=int(estimacion["anio"]),
            modo=ModoPago(str(estimacion["modo"])),
            estatus=EstatusEstimacion(str(estimacion["estatus"])),
            monto_total=Dinero(estimacion.get("monto_total") or 0),
            origen_erp=bool(estimacion.get("origen_erp")),
            generado_en=generado_en,
            conceptos=tuple(_concepto(fila) for fila in conceptos),
        )


def _concepto(fila: dict) -> ConceptoDelReporte:
    return ConceptoDelReporte(
        actividad_id=str(fila["actividad_id"]) if fila.get("actividad_id") else "",
        clave=str(fila.get("clave") or ""),
        # La descripción de la actividad manda sobre la del catálogo: una
        # actividad extra-catálogo (§11.2 `POST /actividades`) solo tiene la
        # suya, y una de catálogo puede haberla precisado en obra (§7.6).
        descripcion=str(fila.get("descripcion") or fila.get("descripcion_concepto") or ""),
        unidad=str(fila.get("unidad") or ""),
        cantidad=Decimal(str(fila.get("cantidad_validada") or 0)),
        precio_unitario=Dinero(fila.get("precio_unitario") or 0),
        importe=Dinero(fila.get("importe") or 0),
        fuera_catalogo=bool(fila.get("fuera_catalogo")),
    )
