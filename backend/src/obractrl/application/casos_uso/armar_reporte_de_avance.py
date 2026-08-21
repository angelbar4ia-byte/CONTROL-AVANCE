"""Caso de uso: reunir el avance de las obras del alcance para exportarlo.

Spec §11.2 ("**Reportes** — `POST /reportes/{tipo}` … por alcance") · §5.1
("Avance total" del Super intendente) · §12.11.

Solo reúne y arma; quién dibuja el `.xlsx` es `adapters/export/xlsx.py`
—mismo reparto que `ArmarReporteDeEstimacion`—, y eso es lo que permite que
el job de Arq y una prueba de dominio usen el mismo reporte sin arrastrar
openpyxl a la capa de aplicación.

**No recibe filtros de alcance y no los quiere.** Los tres opcionales que sí
acepta —proyecto, cluster— son de *foco*, no de permiso: acotan lo que ya se
puede ver. Quién ve qué lo decide RLS con el contexto de la sesión (§12.4).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from obractrl.application.puertos.repositorios import RepositorioTorre
from obractrl.domain.reportes.avance import ReporteDeAvance

__all__ = ["ArmarReporteDeAvance"]


class ArmarReporteDeAvance:
    """El estado de las obras visibles, listo para el exportador."""

    def __init__(self, *, torre: RepositorioTorre) -> None:
        self._torre = torre

    async def ejecutar(
        self,
        *,
        proyecto_id: UUID | None = None,
        cluster_id: UUID | None = None,
    ) -> ReporteDeAvance:
        """Arma el reporte.

        Reusa la misma consulta que alimenta la Torre de control en vez de
        escribir una propia. Es deliberado: si el reporte contara las obras
        detenidas con un criterio distinto al de la pantalla, la junta donde
        se miran los dos números al mismo tiempo terminaría discutiendo cuál
        de los dos está mal.
        """
        filas = await self._torre.estado_de_obras(
            proyecto_id=proyecto_id, cluster_id=cluster_id
        )
        return ReporteDeAvance.armar(
            filas=filas,
            # El reloj entra por el borde: el dominio no lo consulta (§12.11).
            generado_en=datetime.now(UTC),
        )
