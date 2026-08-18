"""Caso de uso: estimación semanal (§11.3 workflow E).

Spec §6 · §3.2 (folio) · §12.11 (capa de aplicación).

Tres pasos, misma forma que `gestionar_cierre.py`: cada uno carga el estado
—o las actividades estimables, en el caso de generar— desde los repos, deja
que `domain.estimacion.reglas` decida si la operación es válida, y persiste.
Ninguna regla de negocio vive aquí, solo la secuencia.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from obractrl.application.eventos import EstimacionValidada, PublicadorEventos
from obractrl.application.puertos.repositorios import (
    RegistroNoEncontrado,
    RepositorioCalendario,
    RepositorioEstimaciones,
    UnidadDeTrabajo,
)
from obractrl.domain.estimacion.reglas import (
    ErrorDeEstimacion,
    Estimacion,
    seleccionar_estimables,
)
from obractrl.domain.shared.diccionario import (
    EstatusEstimacion,
    ModoPago,
    Rol,
    TipoSemana,
)
from obractrl.domain.shared.folio import Folio

__all__ = [
    "ComandoEnviarEstimacion",
    "ComandoGenerarEstimacion",
    "ComandoValidarEstimacion",
    "EnviarEstimacion",
    "ErrorDeEstimacion",
    "EstimacionCreada",
    "EstimacionNoEncontrada",
    "GenerarEstimacion",
    "ValidarEstimacion",
]


class EstimacionNoEncontrada(LookupError):
    """La estimación no existe o está fuera del alcance del usuario (RLS)."""


@dataclass(frozen=True, slots=True)
class ComandoGenerarEstimacion:
    obra_id: UUID
    modo: ModoPago
    usuario_id: UUID
    rol: Rol
    origen_erp: bool = False


@dataclass(frozen=True, slots=True)
class ComandoEnviarEstimacion:
    estimacion_id: UUID
    usuario_id: UUID
    rol: Rol


@dataclass(frozen=True, slots=True)
class ComandoValidarEstimacion:
    estimacion_id: UUID
    usuario_id: UUID
    rol: Rol


@dataclass(frozen=True, slots=True)
class EstimacionCreada:
    id: UUID
    estimacion: Estimacion


def _reconstruir(fila: dict) -> Estimacion:
    """Reconstruye la cabecera para aplicarle la siguiente transición.

    No lleva los conceptos —no hacen falta para enviar/validar, y su
    `monto_total` ya vive en la fila— así que se arma directo con el
    constructor, no con `Estimacion.generar` (esa exige conceptos no vacíos,
    una regla que solo aplica al crear, §11.3 E.1).
    """
    return Estimacion(
        obra_id=str(fila["obra_id"]),
        semana=fila["semana"],
        anio=fila["anio"],
        modo=ModoPago(fila["modo"]),
        conceptos=[],
        creada_por=str(fila["creada_por"]) if fila["creada_por"] else "",
        tipo_semana=TipoSemana(fila["tipo_semana"]),
        folio=Folio.parsear(fila["folio"]) if fila["folio"] else None,
        origen_erp=fila["origen_erp"],
        estatus=EstatusEstimacion(fila["estatus"]),
        validada_por=str(fila["validada_por"]) if fila["validada_por"] else None,
    )


class GenerarEstimacion:
    """Residente o Supervisor generan la estimación de la semana activa
    (§11.3 E.1-2)."""

    def __init__(
        self,
        *,
        estimaciones: RepositorioEstimaciones,
        calendario: RepositorioCalendario,
        uow: UnidadDeTrabajo,
    ) -> None:
        self._estimaciones = estimaciones
        self._calendario = calendario
        self._uow = uow

    async def ejecutar(self, cmd: ComandoGenerarEstimacion) -> EstimacionCreada:
        semana, anio = await self._calendario.semana_activa(TipoSemana.OBRA)
        # El periodo cerrado se consulta **antes** de armar nada: si la semana
        # ya se validó (§11.3 E.5) no hay nada que generar, y así no se gasta
        # un consecutivo de folio (§3.2) en una corrida que va a fallar.
        bloqueado = await self._estimaciones.periodo_bloqueado(
            obra_id=cmd.obra_id,
            tipo_semana=TipoSemana.OBRA.value,
            semana=semana,
            anio=anio,
        )
        filas = await self._estimaciones.actividades_estimables(cmd.obra_id, semana, anio)
        conceptos = seleccionar_estimables(filas, cmd.modo)
        ultimo = await self._estimaciones.ultimo_consecutivo(semana, anio)
        folio = Folio.siguiente(semana, anio, ultimo, es_erp=cmd.origen_erp)

        estimacion = Estimacion.generar(
            obra_id=str(cmd.obra_id),
            semana=semana,
            anio=anio,
            modo=cmd.modo,
            conceptos=conceptos,
            creada_por=str(cmd.usuario_id),
            rol=cmd.rol,
            folio=folio,
            origen_erp=cmd.origen_erp,
            periodo_bloqueado=bloqueado,
        )

        async with self._uow:
            estimacion_id = await self._estimaciones.crear(
                {
                    "obra_id": cmd.obra_id,
                    "folio": str(folio),
                    "semana": semana,
                    "anio": anio,
                    "modo": cmd.modo.value,
                    "creada_por": cmd.usuario_id,
                    "origen_erp": cmd.origen_erp,
                    "monto_total": estimacion.monto_total.monto,
                }
            )
            await self._estimaciones.agregar_conceptos(
                estimacion_id,
                [
                    {
                        "actividad_id": c.actividad_id,
                        "concepto_id": c.concepto_id,
                        "cantidad_validada": c.cantidad_validada,
                        "precio_unitario": c.precio_unitario.monto,
                        "importe": c.importe.monto,
                    }
                    for c in estimacion.conceptos
                ],
            )
            await self._uow.commit()

        return EstimacionCreada(id=estimacion_id, estimacion=estimacion)


class EnviarEstimacion:
    """Residente o Supervisor envían la estimación (§11.3 E.3)."""

    def __init__(
        self, *, estimaciones: RepositorioEstimaciones, uow: UnidadDeTrabajo
    ) -> None:
        self._estimaciones = estimaciones
        self._uow = uow

    async def ejecutar(self, cmd: ComandoEnviarEstimacion) -> dict:
        fila = await self._estimaciones.obtener(cmd.estimacion_id)
        if fila is None:
            raise EstimacionNoEncontrada(
                f"Estimación {cmd.estimacion_id} no encontrada en tu alcance."
            )
        estimacion = _reconstruir(fila)
        estimacion.enviar(rol=cmd.rol)

        async with self._uow:
            try:
                await self._estimaciones.actualizar_estatus(
                    cmd.estimacion_id, estatus=estimacion.estatus.value
                )
            except RegistroNoEncontrado as exc:
                raise EstimacionNoEncontrada(
                    f"Estimación {cmd.estimacion_id} ya no está en tu alcance."
                ) from exc
            await self._uow.commit()

        actualizada = await self._estimaciones.obtener(cmd.estimacion_id)
        assert actualizada is not None  # se acaba de actualizar en esta misma sesión
        return actualizada


class ValidarEstimacion:
    """Control de obra valida: bloquea el periodo y notifica (§11.3 E.4-5).

    Los dos efectos del §11.3 E.5 entran por caminos distintos, a propósito:

    - **Bloquear el periodo** se escribe *dentro* de esta transacción, por el
      puerto de estimaciones. Es un candado, no un derivado: si se perdiera,
      la misma semana se podría volver a estimar y cobrar. Mismo criterio que
      `IncidenciaDetiene` con las actividades bloqueadas (ver su docstring en
      `application/eventos.py`).
    - **Notificar** sale como evento `EstimacionValidada` *después* del
      commit. Es lo que sí se puede perder sin consecuencias, y el bus
      descarta los fallos de sus manejadores (§11.1).
    """

    def __init__(
        self,
        *,
        estimaciones: RepositorioEstimaciones,
        uow: UnidadDeTrabajo,
        eventos: PublicadorEventos | None = None,
    ) -> None:
        self._estimaciones = estimaciones
        self._uow = uow
        self._eventos = eventos

    async def ejecutar(self, cmd: ComandoValidarEstimacion) -> dict:
        fila = await self._estimaciones.obtener(cmd.estimacion_id)
        if fila is None:
            raise EstimacionNoEncontrada(
                f"Estimación {cmd.estimacion_id} no encontrada en tu alcance."
            )
        estimacion = _reconstruir(fila)
        estimacion.validar(usuario_id=str(cmd.usuario_id), rol=cmd.rol)

        async with self._uow:
            try:
                await self._estimaciones.actualizar_estatus(
                    cmd.estimacion_id,
                    estatus=estimacion.estatus.value,
                    validada_por=cmd.usuario_id,
                )
            except RegistroNoEncontrado as exc:
                raise EstimacionNoEncontrada(
                    f"Estimación {cmd.estimacion_id} ya no está en tu alcance."
                ) from exc
            await self._estimaciones.bloquear_periodo(
                obra_id=fila["obra_id"],
                tipo_semana=estimacion.tipo_semana.value,
                semana=estimacion.semana,
                anio=estimacion.anio,
                estimacion_id=cmd.estimacion_id,
                usuario_id=cmd.usuario_id,
            )
            await self._uow.commit()

        if self._eventos is not None:
            await self._eventos.publicar(
                EstimacionValidada(
                    obra_id=UUID(str(fila["obra_id"])),
                    estimacion_id=cmd.estimacion_id,
                )
            )

        actualizada = await self._estimaciones.obtener(cmd.estimacion_id)
        assert actualizada is not None
        return actualizada
