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

from obractrl.domain.avance.confirmacion import AlertaDeRespaldo, alerta_de_respaldo
from obractrl.domain.shared.diccionario import EstatusEstimacion, ModoPago
from obractrl.domain.shared.valores import Dinero

__all__ = ["ConceptoDelReporte", "FrenteDelReporte", "ReporteDeEstimacion"]

SIN_FRENTE = ""
"""Clave con la que se agrupa lo que no tiene frente (§8.3, mismo criterio que
`consultar_planeacion.SIN_FRENTE`). No se descarta: es dinero real que la
estimación reconoce, y esconderlo haría que la suma de los frentes no cuadrara
con el total de la estimación."""


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
    nivel_id: str | None = None
    """El frente (§7.4): el nivel de la actividad que generó este renglón.
    `None` cuando la actividad no tiene nivel capturado — se agrupa bajo
    `SIN_FRENTE`, no se descarta."""
    nivel_clave: str | None = None
    nivel_descripcion: str | None = None
    cantidad_confirmada: Decimal | None = None
    """Lo que el residente confirmó del avance de esta actividad (la última
    confirmación, migración 0070). `None` = nunca se confirmó."""

    @property
    def alerta_de_respaldo(self) -> tuple[AlertaDeRespaldo, Decimal] | None:
        """`pago_sin_respaldo_avance` (MODELO.md §5a): la alerta de lo estimado
        por encima de lo confirmado y cuánto excede. Un renglón sin actividad
        (no hay avance contra qué leerlo) no la lleva."""
        if not self.actividad_id:
            return None
        return alerta_de_respaldo(self.cantidad, self.cantidad_confirmada)


@dataclass(frozen=True, slots=True)
class FrenteDelReporte:
    """Un renglón de la vista «Resumen general»: un frente, cuánto suma y qué
    proporción del total es (§7.4, §11.3 E).

    Es la vista con la que se lee una estimación de un vistazo —cimentación
    73%, estructura 17%— en vez de recorrer renglón por renglón.
    """

    clave: str
    nombre: str
    conceptos: int
    subtotal: Dinero
    porcentaje: Decimal
    """0–100. Redondeado a dos decimales; la suma de todos los frentes puede
    quedar en 99.99 o 100.01 por el redondeo de cada uno — es el mismo costo
    de presentar porcentajes legibles que paga cualquier reporte, y preferible
    a mostrar 17.333333%."""


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

    @property
    def n_alertas_de_respaldo(self) -> int:
        """Renglones estimados por encima de lo confirmado (D-535)."""
        return sum(1 for c in self.conceptos if c.alerta_de_respaldo is not None)

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
        nivel_id=str(fila["nivel_id"]) if fila.get("nivel_id") else None,
        nivel_clave=fila.get("nivel_clave"),
        nivel_descripcion=fila.get("nivel_descripcion"),
        cantidad_confirmada=(
            None
            if fila.get("cantidad_confirmada") is None
            else Decimal(str(fila["cantidad_confirmada"]))
        ),
    )


def por_frente(reporte: ReporteDeEstimacion) -> tuple[FrenteDelReporte, ...]:
    """Agrupa los renglones de una estimación por frente (§7.4, §11.3 E).

    Es la vista «Resumen general»: en vez de recorrer renglón por renglón, se
    lee de un vistazo qué frente pesa más en la semana.

    Se reparte sobre `monto_calculado` —la suma real de los renglones— y no
    sobre `monto_total` de la cabecera: si algún día los dos no cuadran
    (`reporte.cuadra`), los porcentajes tienen que seguir sumando 100% entre
    ellos, no perseguir una cifra que quedó descuadrada.

    Ordenado de mayor a menor subtotal: es la lectura con la que se contrata y
    se revisa —"¿qué frente se llevó la semana?"—, la misma prioridad que
    `domain.planeacion.cuadrillas.demanda_por_frente`.
    """
    grupos: dict[str, list[ConceptoDelReporte]] = {}
    etiquetas: dict[str, tuple[str, str]] = {}
    orden: list[str] = []
    for concepto in reporte.conceptos:
        clave = concepto.nivel_id or SIN_FRENTE
        if clave not in grupos:
            grupos[clave] = []
            orden.append(clave)
            etiquetas[clave] = (
                (concepto.nivel_clave or "—", concepto.nivel_descripcion or "Sin frente")
                if clave != SIN_FRENTE
                else ("—", "Sin frente asignado")
            )
        grupos[clave].append(concepto)

    total = reporte.monto_calculado.monto
    salida = []
    for clave in orden:
        conceptos_del_frente = grupos[clave]
        subtotal = Dinero(sum((c.importe.monto for c in conceptos_del_frente), Decimal(0)))
        nombre_clave, nombre = etiquetas[clave]
        porcentaje = (
            (subtotal.monto * Decimal(100) / total).quantize(Decimal("0.01"))
            if total != 0
            else Decimal(0)
        )
        salida.append(
            FrenteDelReporte(
                clave=nombre_clave,
                nombre=nombre,
                conceptos=len(conceptos_del_frente),
                subtotal=subtotal,
                porcentaje=porcentaje,
            )
        )
    return tuple(sorted(salida, key=lambda f: f.subtotal.monto, reverse=True))
