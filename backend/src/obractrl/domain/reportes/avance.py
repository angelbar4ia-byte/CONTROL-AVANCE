"""Reporte de avance por alcance: cómo va cada obra que el usuario ve.

Spec §11.2 ("**Reportes** — `POST /reportes/{tipo}` → genera Excel/PDF (job),
**por alcance**") · §5.1 (sidebar del Super intendente: "Avance total") ·
§5.3 · §6 (de dónde sale `avance_pct`) · MD/06-reportes.md ("sin lógica de
negocio propia").

## Qué significa "por alcance"

Que el reporte **no lleva filtro de a quién**. Un residente lo pide y salen
sus obras; un supervisor, las de sus clusters; el Super intendente, todas las
de su organización. No hay un parámetro `usuario_id` ni un `where` que lo
resuelva: lo resuelve RLS, exactamente igual que en la pantalla equivalente
(§12.4). Un reporte que se filtrara a sí mismo sería una segunda frontera que
puede desalinearse de la primera.

## Los dos totales, y el que deliberadamente no está

- **`avance_por_actividades`** — concluidas ÷ totales. Es un conteo, no un
  promedio de porcentajes: no depende de ninguna ponderación y significa
  exactamente lo que dice.
- **`avance_promedio_simple`** — la media aritmética de `obra.avance_pct`.
  Sirve para una cartera de obras comparables (vivienda en serie, §1) y se
  nombra *simple* en el propio campo para que nadie lo lea como otra cosa.

**No hay avance ponderado por dinero.** Sería el número más honesto para una
cartera heterogénea, pero exige decidir contra qué se pondera —presupuesto
aprobado, monto estimado, contrato— y el spec no lo fija. Esa decisión ya
tiene su lugar: el módulo de presupuesto (§5.1, Fase 13). Inventarla aquí
produciría dos "avances" distintos en dos pantallas, que es peor que no tener
el número.

`avance_pct` de cada obra **no se recalcula**: lo deriva la base con la
fórmula del §6 (`app.actividad_recalcular`, migración 0007). Este módulo suma
y cuenta; nada más.

Módulo puro: sin BD, sin openpyxl, sin reloj (§12.11).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

__all__ = ["ObraDelReporte", "ReporteDeAvance"]


def _entero(valor: Any) -> int:
    return int(valor or 0)


def _pct(valor: Any) -> Decimal:
    """Porcentaje con dos decimales, como lo guarda la base (`numeric`)."""
    return Decimal(str(valor or 0)).quantize(Decimal("0.01"))


@dataclass(frozen=True, slots=True)
class ObraDelReporte:
    """Un renglón: una obra visible con sus contadores."""

    obra_id: str
    obra_clave: str
    proyecto_clave: str
    cluster_clave: str
    residente: str
    estatus: str
    avance_pct: Decimal
    actividades: int
    concluidas: int
    criticas: int
    bloqueadas: int
    incidencias_abiertas: int
    incidencias_detienen: int
    cierres_pendientes: int

    @property
    def requiere_atencion(self) -> bool:
        """Algo la detiene o espera a alguien.

        Mismo criterio que el filtro `solo_con_pendientes` de la Torre
        (`adapters/repos/torre_sql.py`): que el reporte y la pantalla marquen
        obras distintas sería la peor forma de discrepar, porque las dos se
        miran en la misma junta.
        """
        return (
            self.bloqueadas > 0
            or self.incidencias_detienen > 0
            or self.incidencias_abiertas > 0
            or self.cierres_pendientes > 0
        )

    @classmethod
    def desde_fila(cls, fila: dict[str, Any]) -> ObraDelReporte:
        return cls(
            obra_id=str(fila["obra_id"]),
            obra_clave=str(fila.get("obra_clave") or ""),
            proyecto_clave=str(fila.get("proyecto_clave") or ""),
            cluster_clave=str(fila.get("cluster_clave") or ""),
            residente=str(fila.get("residente_nombre") or ""),
            estatus=str(fila.get("obra_estatus") or ""),
            avance_pct=_pct(fila.get("avance_pct")),
            actividades=_entero(fila.get("actividades")),
            concluidas=_entero(fila.get("concluidas")),
            criticas=_entero(fila.get("criticas")),
            bloqueadas=_entero(fila.get("bloqueadas")),
            incidencias_abiertas=_entero(fila.get("incidencias_abiertas")),
            incidencias_detienen=_entero(fila.get("incidencias_detienen")),
            cierres_pendientes=_entero(fila.get("cierres_pendientes")),
        )


@dataclass(frozen=True, slots=True)
class ReporteDeAvance:
    """Las obras del alcance con sus contadores, más los totales."""

    obras: tuple[ObraDelReporte, ...]
    generado_en: datetime

    @classmethod
    def armar(
        cls, *, filas: list[dict[str, Any]], generado_en: datetime
    ) -> ReporteDeAvance:
        return cls(
            obras=tuple(ObraDelReporte.desde_fila(fila) for fila in filas),
            generado_en=generado_en,
        )

    @property
    def total_obras(self) -> int:
        return len(self.obras)

    @property
    def total_actividades(self) -> int:
        return sum(obra.actividades for obra in self.obras)

    @property
    def total_concluidas(self) -> int:
        return sum(obra.concluidas for obra in self.obras)

    @property
    def obras_que_requieren_atencion(self) -> int:
        return sum(1 for obra in self.obras if obra.requiere_atencion)

    @property
    def avance_por_actividades(self) -> Decimal:
        """Concluidas ÷ totales, en porcentaje. Con cero actividades es 0.

        El caso de cero no es teórico: una obra recién dada de alta con
        `POST /obras/bulk` todavía no tiene actividades hasta que se genera
        desde el prototipo (§11.3 A), y una cartera nueva las tiene todas así.
        """
        if self.total_actividades == 0:
            return Decimal("0.00")
        pct = Decimal(self.total_concluidas) * 100 / Decimal(self.total_actividades)
        return pct.quantize(Decimal("0.01"))

    @property
    def avance_promedio_simple(self) -> Decimal:
        """Media aritmética de `obra.avance_pct`. Ver el encabezado."""
        if not self.obras:
            return Decimal("0.00")
        total = sum((obra.avance_pct for obra in self.obras), Decimal("0"))
        return (total / Decimal(len(self.obras))).quantize(Decimal("0.01"))
