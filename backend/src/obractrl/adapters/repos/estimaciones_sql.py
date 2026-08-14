"""Repositorio de estimaciones.

Spec §12.11 (adaptador de persistencia) · §3.2 (folio) · §7.6 · §11.3
workflow E.

RLS filtra `estimacion` por alcance de rol (política `estimacion_scope`,
`database/migrations/0012`, vía `app.obra_visible(obra_id)`).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.domain.shared.folio import Folio

__all__ = ["RepositorioEstimacionesSQL"]


class RepositorioEstimacionesSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def ultimo_consecutivo(self, semana: int, anio: int) -> int:
        """Último consecutivo de la semana, leyendo el `folio` guardado.

        La tabla no guarda el consecutivo como columna aparte —solo el folio
        ya formateado—, así que se relee con `Folio.parsear` (dominio) en
        vez de reimplementar el parseo `[E-]WWYY-NNN` en SQL: la regla de
        formato se define una sola vez (§3.2). No se filtra por
        `origen_erp`: el contador es compartido entre ERP y no-ERP.
        """
        filas = await self._sesion.execute(
            text(
                """
                select folio
                from estimacion
                where semana = :semana and anio = :anio and folio is not null
                """
            ),
            {"semana": semana, "anio": anio},
        )

        maximo = 0
        for (folio_texto,) in filas:
            try:
                folio = Folio.parsear(folio_texto)
            except ValueError:
                # Un folio que no matchea el formato canónico no debe tumbar
                # el conteo del resto de la semana; solo se ignora.
                continue
            maximo = max(maximo, folio.consecutivo)
        return maximo

    async def crear(self, datos: dict[str, Any]) -> UUID:
        """Crea una estimación en borrador (§6, §11.3 E.1).

        Claves esperadas en ``datos``: ``obra_id``, ``folio`` (str, ya
        formateado por `Folio`), ``semana``, ``anio``, ``modo``
        (destajo | concepto | subcontrato), ``creada_por``. Opcionales:
        ``tipo_semana`` (default ``"obra"``, §3.1), ``origen_erp`` (default
        ``False``, §3.2). ``estatus`` nace ``borrador`` por default de la BD.
        """
        fila = await self._sesion.execute(
            text(
                """
                insert into estimacion
                    (org_id, obra_id, folio, semana, anio, tipo_semana, modo,
                     creada_por, origen_erp)
                values
                    (cast(current_setting('app.org_id') as uuid),
                     :obra_id, :folio, :semana, :anio, :tipo_semana, :modo,
                     cast(:creada_por as uuid), :origen_erp)
                returning id
                """
            ),
            {
                "obra_id": str(datos["obra_id"]),
                "folio": str(datos["folio"]),
                "semana": datos["semana"],
                "anio": datos["anio"],
                "tipo_semana": datos.get("tipo_semana", "obra"),
                "modo": datos["modo"],
                "creada_por": str(datos["creada_por"])
                if datos.get("creada_por")
                else None,
                "origen_erp": datos.get("origen_erp", False),
            },
        )
        return fila.scalar_one()

    async def actividades_estimables(
        self, obra_id: UUID, semana: int, anio: int
    ) -> list[dict[str, Any]]:
        """Actividades con cierre validado en la semana (§11.3 E.2).

        "Validado" = tienen una `solicitud_cierre` en estatus `validada`
        (Control de obra ya la revisó; §4) cuya `fecha_valida` cae dentro del
        rango de esa semana. El rango sale de `calendario` con
        `tipo = 'obra'`: es el default documentado en §3.1 para estimaciones;
        el puerto no recibe `tipo_semana` explícito porque hoy nada lo
        necesita distinto al default.
        """
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select a.id as actividad_id, a.concepto_id,
                           sc.cantidad as cantidad_validada,
                           a.precio_unitario, a.precio_destajo, a.modo_pago
                    from actividad a
                    join solicitud_cierre sc
                      on sc.actividad_id = a.id and sc.estatus = 'validada'
                    join calendario c
                      on c.tipo = 'obra' and c.anio = :anio and c.semana = :semana
                    where a.obra_id = :obra_id
                      and sc.fecha_valida >= c.fecha_inicio
                      and sc.fecha_valida < c.fecha_fin + 1
                    """
                ),
                {"obra_id": str(obra_id), "semana": semana, "anio": anio},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]
