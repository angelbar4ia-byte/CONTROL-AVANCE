"""Repositorio del calendario maestro.

Spec §12.11 (adaptador de persistencia) · §3.1 (semana y año — base
temporal) · §12.4 (RLS).

La tabla `calendario` (materializada por `app.generar_calendario()`,
`database/migrations/0013`) es la **única fuente** de la base temporal: este
repositorio solo la lee, nunca recalcula semana/año en Python. Tener dos
implementaciones de la misma numeración —una en SQL, otra en el adaptador—
es exactamente el tipo de divergencia que ya costó una corrección en
`domain.avance.reglas` (ver el comentario ahí sobre `TOPE_SOBREPROGRAMA`).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.domain.shared.diccionario import TipoSemana

__all__ = ["CalendarioNoConfigurado", "RepositorioCalendarioSQL"]


class CalendarioNoConfigurado(LookupError):
    """No hay fila de `calendario` o `ancla_semana` para lo pedido.

    Pasa si nadie corrió `app.generar_calendario()` para ese año, o si el
    admin no ha fijado el ancla de semana (§3.1) todavía. No se resuelve con
    un default silencioso —adivinar la semana activa rompería la
    trazabilidad de folios y estimaciones (§3.2)— así que el caso de uso
    decide cómo comunicarlo (típicamente, pedir a Control de obra que la
    configure primero).
    """


class RepositorioCalendarioSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def semana_de(self, fecha: date, tipo: TipoSemana) -> tuple[int, int]:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select semana, anio
                    from calendario
                    where tipo = :tipo
                      and fecha_inicio <= :fecha
                      and fecha_fin >= :fecha
                    """
                ),
                {"tipo": tipo.value, "fecha": fecha},
            )
        ).first()
        if fila is None:
            raise CalendarioNoConfigurado(
                f"No hay semana de tipo {tipo.value!r} calculada para "
                f"{fecha.isoformat()}. Genera el calendario de ese año "
                f"(§3.1) antes de operar sobre esta fecha."
            )
        return int(fila.semana), int(fila.anio)

    async def rango_de_semana(
        self, semana: int, anio: int, tipo: TipoSemana
    ) -> tuple[date, date]:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select fecha_inicio, fecha_fin
                    from calendario
                    where tipo = :tipo and anio = :anio and semana = :semana
                    """
                ),
                {"tipo": tipo.value, "anio": anio, "semana": semana},
            )
        ).first()
        if fila is None:
            raise CalendarioNoConfigurado(
                f"No hay calendario tipo {tipo.value!r} para la semana "
                f"{semana} de {anio}. Genera el calendario de ese año (§3.1)."
            )
        return fila.fecha_inicio, fila.fecha_fin

    async def semana_activa(self, tipo: TipoSemana) -> tuple[int, int]:
        """Ancla fijada por el admin en Configuración (§3.1)."""
        fila = (
            await self._sesion.execute(
                text(
                    "select semana, anio from ancla_semana where tipo = :tipo"
                ),
                {"tipo": tipo.value},
            )
        ).first()
        if fila is None:
            raise CalendarioNoConfigurado(
                f"Nadie ha fijado el ancla de semana {tipo.value!r} para "
                f"esta organización. Un admin debe hacerlo en Configuración "
                f"antes de que el sistema pueda numerar semanas (§3.1)."
            )
        return int(fila.semana), int(fila.anio)
