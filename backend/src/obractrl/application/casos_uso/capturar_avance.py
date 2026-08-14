"""Caso de uso: capturar avance de una actividad.

Spec §6 · §11.3 workflow B · §12.11 (capa de aplicación).

Es la referencia de cómo se escribe un caso de uso en este backend:

* Orquesta el **dominio** (`domain.avance.reglas`) a través de **puertos**;
  no importa SQLModel, ni FastAPI, ni la sesión de BD.
* Lee los configurables de BD antes de aplicar las reglas — el default del
  código es solo fallback (§8.7).
* No contiene reglas de negocio propias: las reglas viven en el dominio y
  aquí solo se secuencian.

La misma entrada sirve para la web (`PATCH /actividades/{id}/avance`) y para
la conciliación offline del móvil, para que ambas rutas apliquen exactamente
las mismas reglas (§11.3 B).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from obractrl.application.puertos.repositorios import (
    RepositorioActividades,
    RepositorioConfiguracion,
    UnidadDeTrabajo,
)
from obractrl.domain.avance.reglas import (
    TOPE_SOBREPROGRAMA,
    UMBRAL_CASI_PCT,
    CapturaAvance,
    ErrorDeCaptura,
    aplicar_captura,
)
from obractrl.domain.shared.diccionario import EstatusActividad

__all__ = ["CapturarAvance", "ComandoCapturarAvance"]


@dataclass(frozen=True, slots=True)
class ComandoCapturarAvance:
    """Entrada del caso de uso."""

    actividad_id: UUID
    usuario_id: UUID
    cant_ejecutada: Decimal
    cant_programada: Decimal | None = None
    fecha: date | None = None
    evidencias: tuple[str, ...] = ()


class ActividadNoEncontrada(LookupError):
    """La actividad no existe o está fuera del alcance del usuario (RLS)."""


class ActividadBloqueada(RuntimeError):
    """Una incidencia con impacto `detiene` frena la actividad (§6)."""


class CapturarAvance:
    """Aplica una captura de avance sobre una actividad."""

    def __init__(
        self,
        *,
        actividades: RepositorioActividades,
        configuracion: RepositorioConfiguracion,
        uow: UnidadDeTrabajo,
    ) -> None:
        self._actividades = actividades
        self._config = configuracion
        self._uow = uow

    async def ejecutar(self, cmd: ComandoCapturarAvance) -> CapturaAvance:
        actividad = await self._actividades.obtener(cmd.actividad_id)
        if actividad is None:
            # RLS ya filtró por alcance: "no existe" y "no la puedes ver" son
            # indistinguibles a propósito, para no filtrar existencia (§12.4).
            raise ActividadNoEncontrada(
                f"Actividad {cmd.actividad_id} no encontrada en tu alcance."
            )

        if actividad.get("bloqueada"):
            raise ActividadBloqueada(
                "La actividad está bloqueada por una incidencia que detiene la "
                "obra. Atiende la incidencia antes de capturar avance (§6)."
            )

        # Los configurables mandan sobre el default del código (§8.7)
        tope = await self._config.decimal("tope_sobreprograma", TOPE_SOBREPROGRAMA)
        umbral = await self._config.decimal("avance_casi_pct", UMBRAL_CASI_PCT)

        cant_base = Decimal(str(actividad["cant_base"]))
        cant_programada = (
            cmd.cant_programada
            if cmd.cant_programada is not None
            else Decimal(str(actividad["cant_programada"]))
        )
        estatus_actual = EstatusActividad(actividad["estatus"])

        resultado = aplicar_captura(
            cant_base=cant_base,
            cant_programada=cant_programada,
            cant_ejecutada=cmd.cant_ejecutada,
            estatus_actual=estatus_actual,
            tope=tope,
            umbral_casi=umbral,
        )

        delta = cmd.cant_ejecutada - Decimal(str(actividad["cant_ejecutada"]))

        async with self._uow:
            await self._actividades.actualizar_avance(
                cmd.actividad_id,
                cant_programada=resultado.cant_programada,
                cant_ejecutada=resultado.cant_ejecutada,
                avance_pct=resultado.avance.pct,
                estatus=resultado.estatus.value,
            )
            await self._actividades.registrar_captura(
                cmd.actividad_id,
                fecha=cmd.fecha or date.today(),
                delta_ejecutado=delta,
                usuario_id=cmd.usuario_id,
                evidencias=list(cmd.evidencias),
            )
            await self._uow.commit()

        return resultado


# Reexportado para que el borde mapee el error a problem+json (§11.2)
# sin tener que importar del dominio.
ErrorDeCaptura = ErrorDeCaptura
