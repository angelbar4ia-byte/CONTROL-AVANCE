"""Caso de uso: reunir los datos de una estimación para exportarla.

Spec §11.2 (`GET /estimaciones/{id}/export` — xlsx, **job**, roles C y SI) ·
§11.3 E.5 · §12.11.

Solo **reúne y arma**: quién dibuja el `.xlsx` es `adapters/export/xlsx.py`
(§MD/06-reportes.md, "vive en `adapters/`; consume el dominio por puertos").
Partirlo así es lo que permite que el job de Arq y una prueba de dominio usen
el mismo reporte sin arrastrar openpyxl a la capa de aplicación.

La obra se pide por su puerto —para el encabezado del archivo— en vez de
join-earla desde el repo de estimaciones: el §11.1 no deja que un contexto lea
las tablas de otro.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from obractrl.application.casos_uso.gestionar_estimacion import EstimacionNoEncontrada
from obractrl.application.puertos.repositorios import (
    RepositorioEstimaciones,
    RepositorioObras,
)
from obractrl.domain.reportes.estimacion import ReporteDeEstimacion

__all__ = ["ArmarReporteDeEstimacion", "EstimacionNoEncontrada"]


class ArmarReporteDeEstimacion:
    """Cabecera + renglones de una estimación, listos para el exportador."""

    def __init__(
        self, *, estimaciones: RepositorioEstimaciones, obras: RepositorioObras
    ) -> None:
        self._estimaciones = estimaciones
        self._obras = obras

    async def ejecutar(self, estimacion_id: UUID) -> ReporteDeEstimacion:
        estimacion = await self._estimaciones.obtener(estimacion_id)
        if estimacion is None:
            raise EstimacionNoEncontrada(
                f"Estimación {estimacion_id} no encontrada en tu alcance."
            )

        obra = await self._obras.obtener(estimacion["obra_id"]) or {}
        conceptos = await self._estimaciones.conceptos_de(estimacion_id)

        return ReporteDeEstimacion.armar(
            estimacion=estimacion,
            obra=obra,
            conceptos=conceptos,
            # El reloj entra por el borde: el dominio no lo consulta (§12.11).
            generado_en=datetime.now(UTC),
        )
