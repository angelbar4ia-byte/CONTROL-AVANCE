"""Caso de uso: capturar avance de una actividad.

Spec §6 · §11.3 workflow B · §12.11 (capa de aplicación).

Es la referencia de cómo se escribe un caso de uso en este backend:

* Orquesta el **dominio** (`domain.avance.reglas`) a través de **puertos**;
  no importa SQLModel, ni FastAPI, ni la sesión de BD.
* No contiene reglas de negocio propias: las reglas viven en el dominio y
  aquí solo se secuencian.

No depende de `RepositorioConfiguracion`: el tope de sobre-programación y el
umbral de "casi" son fórmulas fijas del §6, no configurables de §8.7 (ver el
comentario en `domain.avance.reglas`). Si en el futuro alguna regla de este
caso de uso sí se vuelve configurable, se resuelve aquí —antes de llamar al
dominio— nunca dentro de `aplicar_captura`.

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
    RegistroNoEncontrado,
    RepositorioActividades,
    UnidadDeTrabajo,
)
from obractrl.domain.avance.reglas import (
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
        uow: UnidadDeTrabajo,
    ) -> None:
        self._actividades = actividades
        self._uow = uow

    async def ejecutar(self, cmd: ComandoCapturarAvance) -> CapturaAvance:
        # Con bloqueo, no con `obtener`: esto es un lee-modifica-escribe y desde
        # D5 hay otro escritor —el móvil, por PowerSync, sin pasar por la API—.
        # Sin el bloqueo, un delta que llegue en medio hace que el total quede
        # en un número que nadie capturó. El razonamiento está entero en
        # `RepositorioActividadesSQL.obtener_para_captura`.
        actividad = await self._actividades.obtener_para_captura(cmd.actividad_id)
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
            cant_perdida=Decimal(str(actividad.get("cant_perdida") or 0)),
            estatus_actual=estatus_actual,
        )

        # El delta sale de lo que el dominio VALIDÓ, no de lo que pidió el
        # cliente: es lo que se persiste, y la bitácora tiene que sumar
        # exactamente el total (D5 — `registro_avance` es la única fuente de
        # `cant_ejecutada`).
        delta = resultado.cant_ejecutada - Decimal(str(actividad["cant_ejecutada"]))

        async with self._uow:
            try:
                await self._actividades.actualizar_avance(
                    cmd.actividad_id,
                    cant_programada=resultado.cant_programada,
                    estatus=resultado.estatus.value,
                )
            except RegistroNoEncontrado as exc:
                # Carrera genuina entre el obtener() de arriba y este UPDATE:
                # la actividad se borró o salió del alcance del usuario justo
                # en medio. Mismo tratamiento que el 404 inicial (§12.4): no
                # se distingue de "no encontrada".
                raise ActividadNoEncontrada(
                    f"Actividad {cmd.actividad_id} ya no está en tu alcance."
                ) from exc

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
