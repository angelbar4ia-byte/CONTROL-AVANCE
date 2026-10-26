"""Casos de uso: reprogramar lo contratado (migración 0072; cerebro D-533, P-4).

«Las fechas contratadas no se mueven solas.» Quien quiere moverlas **propone** y una
cadena la acepta:

    propone              revisa        valida           realiza
    Residente            Supervisor    Control de obra  Control de obra
    Supervisor           (se salta)    Control de obra  Control de obra

Las transiciones y los permisos de cada paso los decide `domain.programacion.
reprogramacion`; aquí solo se secuencia. El último paso, **realizar**, es el único
camino que mueve la fecha de lo contratado: llama a `EditarProgramacionActividad` con
el id de la reprogramación, y esa llamada marca la reprogramación como `aplicada` **en
la misma transacción** que escribe la fecha (el gancho `en_la_transaccion`). Después
—ya con todo commiteado— publica `ReprogramacionAplicada` para avisar a los demás.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.generar_obra_desde_prototipo import ObraNoEncontrada
from obractrl.application.casos_uso.gestionar_programacion import (
    ActividadNoProgramable,
    ComandoEditarProgramacion,
    EditarProgramacionActividad,
)
from obractrl.application.eventos import PublicadorEventos, ReprogramacionAplicada
from obractrl.application.puertos.repositorios import (
    RegistroNoEncontrado,
    RepositorioActividades,
    RepositorioObras,
    UnidadDeTrabajo,
)
from obractrl.application.puertos.reprogramacion import RepositorioReprogramaciones
from obractrl.domain.programacion.reprogramacion import (
    ErrorDeReprogramacion,
    EstatusReprogramacion,
    Reprogramacion,
    esta_contratada,
)
from obractrl.domain.shared.diccionario import Rol

__all__ = [
    "AplicarReprogramacion",
    "ComandoAplicarReprogramacion",
    "ComandoProponerReprogramacion",
    "ComandoRechazarReprogramacion",
    "ComandoRevisarReprogramacion",
    "ComandoValidarReprogramacion",
    "ConsultarReprogramaciones",
    "ErrorDeReprogramacion",
    "ProponerReprogramacion",
    "RechazarReprogramacion",
    "ReprogramacionNoEncontrada",
    "RevisarReprogramacion",
    "ValidarReprogramacion",
]


class ReprogramacionNoEncontrada(LookupError):
    """La reprogramación no existe o salió del alcance (RLS): indistinguibles a propósito."""


@dataclass(frozen=True, slots=True)
class ComandoProponerReprogramacion:
    actividad_id: UUID
    usuario_id: UUID
    rol: Rol
    motivo: str
    fecha_inicio: date | None = None
    fecha_termino: date | None = None


@dataclass(frozen=True, slots=True)
class ComandoRevisarReprogramacion:
    reprogramacion_id: UUID
    usuario_id: UUID
    rol: Rol


@dataclass(frozen=True, slots=True)
class ComandoValidarReprogramacion:
    reprogramacion_id: UUID
    usuario_id: UUID
    rol: Rol


@dataclass(frozen=True, slots=True)
class ComandoAplicarReprogramacion:
    reprogramacion_id: UUID
    usuario_id: UUID
    rol: Rol


@dataclass(frozen=True, slots=True)
class ComandoRechazarReprogramacion:
    reprogramacion_id: UUID
    usuario_id: UUID
    rol: Rol
    motivo: str


def _reconstruir(fila: dict[str, Any]) -> Reprogramacion:
    def _id(valor: object) -> str | None:
        return str(valor) if valor else None

    return Reprogramacion(
        actividad_id=str(fila["actividad_id"]),
        propuesta_por=str(fila["propuesta_por"]),
        propuesta_rol=Rol(str(fila["propuesta_rol"])),
        motivo=fila["motivo"],
        fecha_inicio=fila["fecha_inicio"],
        fecha_termino=fila["fecha_termino"],
        estatus=EstatusReprogramacion(str(fila["estatus"])),
        revisada_por=_id(fila["revisada_por"]),
        validada_por=_id(fila["validada_por"]),
        aplicada_por=_id(fila["aplicada_por"]),
        rechazada_por=_id(fila["rechazada_por"]),
        motivo_rechazo=fila["motivo_rechazo"],
    )


class ConsultarReprogramaciones:
    """`GET /obras/{id}/reprogramaciones`: la cadena de cada reprogramación de la obra."""

    def __init__(
        self, *, reprogramaciones: RepositorioReprogramaciones, obras: RepositorioObras
    ) -> None:
        self._reprogramaciones = reprogramaciones
        self._obras = obras

    async def ejecutar(self, obra_id: UUID) -> list[dict[str, Any]]:
        if await self._obras.obtener(obra_id) is None:
            raise ObraNoEncontrada(f"Obra {obra_id} no encontrada en tu alcance.")
        return await self._reprogramaciones.de_obra(obra_id)


class ProponerReprogramacion:
    """El residente o el supervisor proponen la fecha nueva de algo contratado."""

    def __init__(
        self,
        *,
        reprogramaciones: RepositorioReprogramaciones,
        actividades: RepositorioActividades,
        uow: UnidadDeTrabajo,
    ) -> None:
        self._reprogramaciones = reprogramaciones
        self._actividades = actividades
        self._uow = uow

    async def ejecutar(self, cmd: ComandoProponerReprogramacion) -> tuple[UUID, Reprogramacion]:
        fila = await self._actividades.programacion_de(cmd.actividad_id)
        if fila is None:
            raise ActividadNoProgramable(
                f"Actividad {cmd.actividad_id} no encontrada en tu alcance."
            )

        reprogramacion = Reprogramacion.proponer(
            actividad_id=str(cmd.actividad_id),
            usuario_id=str(cmd.usuario_id),
            rol=cmd.rol,
            motivo=cmd.motivo,
            contratada=esta_contratada(contratista_id=fila.get("contratista_id")),
            fecha_inicio=cmd.fecha_inicio,
            fecha_termino=cmd.fecha_termino,
            fecha_inicio_actual=fila["fecha_inicio"],
            fecha_termino_actual=fila["fecha_termino"],
        )

        # Una viva por actividad: se avisa con el estado, no con el choque del índice.
        viva = await self._reprogramaciones.viva_de(cmd.actividad_id)
        if viva is not None:
            raise ErrorDeReprogramacion(
                f"Esta actividad ya tiene una reprogramación {viva['estatus']}: resuélvela "
                "o recházala antes de proponer otra."
            )

        async with self._uow:
            reprogramacion_id = await self._reprogramaciones.crear(
                obra_id=fila["obra_id"],
                actividad_id=cmd.actividad_id,
                estatus=reprogramacion.estatus.value,
                fecha_inicio=reprogramacion.fecha_inicio,
                fecha_termino=reprogramacion.fecha_termino,
                fecha_inicio_anterior=fila["fecha_inicio"],
                fecha_termino_anterior=fila["fecha_termino"],
                motivo=reprogramacion.motivo,
                propuesta_por=cmd.usuario_id,
                propuesta_rol=cmd.rol.value,
            )
            await self._uow.commit()
        return reprogramacion_id, reprogramacion


class _PasoDeLaCadena:
    def __init__(
        self, *, reprogramaciones: RepositorioReprogramaciones, uow: UnidadDeTrabajo
    ) -> None:
        self._reprogramaciones = reprogramaciones
        self._uow = uow

    async def _cargar(self, reprogramacion_id: UUID) -> tuple[dict[str, Any], Reprogramacion]:
        fila = await self._reprogramaciones.obtener(reprogramacion_id)
        if fila is None:
            raise ReprogramacionNoEncontrada(
                f"Reprogramación {reprogramacion_id} no encontrada en tu alcance."
            )
        return fila, _reconstruir(fila)

    async def _guardar(
        self, reprogramacion_id: UUID, reprogramacion: Reprogramacion, **autores: Any
    ) -> None:
        async with self._uow:
            await self._actualizar(reprogramacion_id, reprogramacion, **autores)
            await self._uow.commit()

    async def _actualizar(
        self, reprogramacion_id: UUID, reprogramacion: Reprogramacion, **autores: Any
    ) -> None:
        try:
            await self._reprogramaciones.actualizar(
                reprogramacion_id, estatus=reprogramacion.estatus.value, **autores
            )
        except RegistroNoEncontrado as exc:
            raise ReprogramacionNoEncontrada(
                f"Reprogramación {reprogramacion_id} ya no está en tu alcance."
            ) from exc


class RevisarReprogramacion(_PasoDeLaCadena):
    """El supervisor revisa lo que propuso el residente."""

    async def ejecutar(self, cmd: ComandoRevisarReprogramacion) -> Reprogramacion:
        _, reprogramacion = await self._cargar(cmd.reprogramacion_id)
        reprogramacion.revisar(usuario_id=str(cmd.usuario_id), rol=cmd.rol)
        await self._guardar(cmd.reprogramacion_id, reprogramacion, revisada_por=cmd.usuario_id)
        return reprogramacion


class ValidarReprogramacion(_PasoDeLaCadena):
    """Control de obra valida la fecha nueva."""

    async def ejecutar(self, cmd: ComandoValidarReprogramacion) -> Reprogramacion:
        _, reprogramacion = await self._cargar(cmd.reprogramacion_id)
        reprogramacion.validar(usuario_id=str(cmd.usuario_id), rol=cmd.rol)
        await self._guardar(cmd.reprogramacion_id, reprogramacion, validada_por=cmd.usuario_id)
        return reprogramacion


class RechazarReprogramacion(_PasoDeLaCadena):
    """El supervisor (lo que revisa) o control de obra rechazan, con motivo."""

    async def ejecutar(self, cmd: ComandoRechazarReprogramacion) -> Reprogramacion:
        _, reprogramacion = await self._cargar(cmd.reprogramacion_id)
        reprogramacion.rechazar(usuario_id=str(cmd.usuario_id), rol=cmd.rol, motivo=cmd.motivo)
        await self._guardar(
            cmd.reprogramacion_id,
            reprogramacion,
            rechazada_por=cmd.usuario_id,
            motivo_rechazo=reprogramacion.motivo_rechazo,
        )
        return reprogramacion


class AplicarReprogramacion(_PasoDeLaCadena):
    """Control de obra **realiza** la reprogramación: mueve la fecha de lo contratado y
    avisa a los demás.

    La fecha se escribe por `EditarProgramacionActividad`, que recalcula el CPM y deja
    su renglón en la bitácora del programa con el id de esta reprogramación. Que la
    reprogramación quede `aplicada` va en el gancho de esa misma transacción: o se
    mueve y queda aplicada, o no pasa ninguna de las dos.
    """

    def __init__(
        self,
        *,
        reprogramaciones: RepositorioReprogramaciones,
        editar: EditarProgramacionActividad,
        uow: UnidadDeTrabajo,
        eventos: PublicadorEventos,
    ) -> None:
        super().__init__(reprogramaciones=reprogramaciones, uow=uow)
        self._editar = editar
        self._eventos = eventos

    async def ejecutar(self, cmd: ComandoAplicarReprogramacion) -> Reprogramacion:
        fila, reprogramacion = await self._cargar(cmd.reprogramacion_id)
        reprogramacion.aplicar(usuario_id=str(cmd.usuario_id), rol=cmd.rol)

        async def _marcar_aplicada() -> None:
            await self._actualizar(
                cmd.reprogramacion_id, reprogramacion, aplicada_por=cmd.usuario_id
            )

        await self._editar.ejecutar(
            ComandoEditarProgramacion(
                actividad_id=UUID(str(fila["actividad_id"])),
                rol=cmd.rol,
                usuario_id=cmd.usuario_id,
                fecha_inicio=reprogramacion.fecha_inicio,
                fecha_termino=reprogramacion.fecha_termino,
                reprogramacion_id=cmd.reprogramacion_id,
            ),
            en_la_transaccion=_marcar_aplicada,
        )

        await self._eventos.publicar(
            ReprogramacionAplicada(
                obra_id=UUID(str(fila["obra_id"])),
                reprogramacion_id=cmd.reprogramacion_id,
                actividad_id=UUID(str(fila["actividad_id"])),
            )
        )
        return reprogramacion
