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

from obractrl.application.puertos.repositorios import RegistroNoEncontrado
from obractrl.domain.shared.folio import Folio

__all__ = ["EstimacionNoModificada", "RepositorioEstimacionesSQL"]


class EstimacionNoModificada(RegistroNoEncontrado):
    """El UPDATE no afectó ninguna fila: la estimación ya no existe o salió
    del alcance del usuario (RLS) entre el `obtener()` y la escritura."""


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
        (destajo | concepto | subcontrato), ``creada_por``, ``monto_total``
        (ya calculado por `domain.estimacion.reglas.Estimacion.monto_total`).
        Opcionales: ``tipo_semana`` (default ``"obra"``, §3.1), ``origen_erp``
        (default ``False``, §3.2). ``estatus`` nace ``borrador`` por default
        de la BD.
        """
        fila = await self._sesion.execute(
            text(
                """
                insert into estimacion
                    (org_id, obra_id, folio, semana, anio, tipo_semana, modo,
                     creada_por, origen_erp, monto_total)
                values
                    (cast(current_setting('app.org_id') as uuid),
                     :obra_id, :folio, :semana, :anio, :tipo_semana, :modo,
                     cast(:creada_por as uuid), :origen_erp, :monto_total)
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
                "monto_total": datos.get("monto_total", 0),
            },
        )
        return fila.scalar_one()

    async def agregar_conceptos(
        self, estimacion_id: UUID, conceptos: list[dict[str, Any]]
    ) -> None:
        """Inserta las líneas `EstimacionConcepto` ya calculadas por el
        dominio (§11.3 E.2). Cada dict trae ``actividad_id``, ``concepto_id``
        (o ``None`` si es fuera de catálogo), ``cantidad_validada``,
        ``precio_unitario`` e ``importe``.
        """
        if not conceptos:
            return

        params = [
            {
                "estimacion_id": str(estimacion_id),
                "actividad_id": str(c["actividad_id"]),
                "concepto_id": str(c["concepto_id"]) if c.get("concepto_id") else None,
                "cantidad_validada": c["cantidad_validada"],
                "precio_unitario": c["precio_unitario"],
                "importe": c["importe"],
                "fuera_catalogo": c.get("concepto_id") is None,
            }
            for c in conceptos
        ]

        await self._sesion.execute(
            text(
                """
                insert into estimacion_concepto
                    (org_id, estimacion_id, actividad_id, concepto_id,
                     cantidad_validada, precio_unitario, importe, fuera_catalogo)
                values
                    (cast(current_setting('app.org_id') as uuid),
                     cast(:estimacion_id as uuid), cast(:actividad_id as uuid),
                     cast(:concepto_id as uuid), :cantidad_validada,
                     :precio_unitario, :importe, :fuera_catalogo)
                """
            ),
            params,
        )

    async def obtener(self, estimacion_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select id, obra_id, folio, semana, anio, tipo_semana,
                           modo, estatus, monto_total, origen_erp,
                           creada_por, validada_por
                    from estimacion
                    where id = :id
                    """
                ),
                {"id": str(estimacion_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def actualizar_estatus(
        self,
        estimacion_id: UUID,
        *,
        estatus: str,
        validada_por: UUID | None = None,
    ) -> None:
        resultado = await self._sesion.execute(
            text(
                """
                update estimacion
                   set estatus      = cast(:estatus as estatus_estimacion),
                       validada_por = coalesce(cast(:validada_por as uuid), validada_por)
                 where id = :id
                """
            ),
            {
                "id": str(estimacion_id),
                "estatus": estatus,
                "validada_por": str(validada_por) if validada_por else None,
            },
        )
        if resultado.rowcount == 0:
            raise EstimacionNoModificada(
                f"No se actualizó la estimación {estimacion_id}: ya no existe "
                f"o salió de tu alcance."
            )

    async def listar(self, obra_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select id, obra_id, folio, semana, anio, tipo_semana,
                           modo, estatus, monto_total, origen_erp,
                           creada_por, validada_por
                    from estimacion
                    where obra_id = :obra_id
                    order by anio desc, semana desc
                    """
                ),
                {"obra_id": str(obra_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def conceptos_de(self, estimacion_id: UUID) -> list[dict[str, Any]]:
        """Renglones de la estimación con lo necesario para rotularlos (§11.2
        `GET /estimaciones/{id}/export`).

        Acompaña cada `estimacion_concepto` con la descripción de su actividad
        y con la clave/unidad del concepto de catálogo, igual que
        `actividades_estimables` acompaña la actividad con su precio: el
        renglón de una estimación no se lee sin el concepto que estima. Los
        `left join` son deliberados —una actividad extra-catálogo no tiene
        `concepto_id` (§11.2 `POST /actividades`) y debe salir igual, marcada
        como fuera de catálogo.
        """
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select ec.id, ec.actividad_id, ec.concepto_id,
                           ec.cantidad_validada, ec.precio_unitario,
                           ec.importe, ec.fuera_catalogo,
                           coalesce(a.descripcion, c.descripcion) as descripcion,
                           c.clave, u.clave as unidad
                    from estimacion_concepto ec
                    left join actividad a on a.id = ec.actividad_id
                    left join concepto  c on c.id = ec.concepto_id
                    left join unidad    u on u.id = c.unidad_id
                    where ec.estimacion_id = cast(:id as uuid)
                    order by c.clave nulls last, ec.created_at
                    """
                ),
                {"id": str(estimacion_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    # --- Bloqueo del periodo (§11.3 E.5) ---------------------------------

    async def bloquear_periodo(
        self,
        *,
        obra_id: UUID,
        tipo_semana: str,
        semana: int,
        anio: int,
        estimacion_id: UUID,
        usuario_id: UUID,
    ) -> None:
        """Cierra la semana de la obra al validar (§11.3 E.5).

        `on conflict do nothing` y no un `select` previo: dos modos de pago
        distintos (§6) pueden validarse en la misma semana, y el segundo
        encontraría el periodo ya bloqueado. Eso no es un error —el candado
        ya está puesto— y dejarlo como choque de `uq_periodo_bloqueado`
        abortaría la transacción que acaba de validar la estimación.
        """
        await self._sesion.execute(
            text(
                """
                insert into periodo_bloqueado
                    (org_id, obra_id, tipo_semana, anio, semana,
                     estimacion_id, bloqueado_por)
                values
                    (cast(current_setting('app.org_id') as uuid),
                     cast(:obra_id as uuid),
                     cast(:tipo_semana as tipo_semana),
                     :anio, :semana,
                     cast(:estimacion_id as uuid), cast(:usuario_id as uuid))
                on conflict on constraint uq_periodo_bloqueado do nothing
                """
            ),
            {
                "obra_id": str(obra_id),
                "tipo_semana": tipo_semana,
                "anio": anio,
                "semana": semana,
                "estimacion_id": str(estimacion_id),
                "usuario_id": str(usuario_id),
            },
        )

    async def periodo_bloqueado(
        self, *, obra_id: UUID, tipo_semana: str, semana: int, anio: int
    ) -> bool:
        """¿La semana de esa obra ya está cerrada? (§11.3 E.5)"""
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select 1
                    from periodo_bloqueado
                    where obra_id = cast(:obra_id as uuid)
                      and tipo_semana = cast(:tipo_semana as tipo_semana)
                      and anio = :anio
                      and semana = :semana
                    limit 1
                    """
                ),
                {
                    "obra_id": str(obra_id),
                    "tipo_semana": tipo_semana,
                    "anio": anio,
                    "semana": semana,
                },
            )
        ).first()
        return fila is not None

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
