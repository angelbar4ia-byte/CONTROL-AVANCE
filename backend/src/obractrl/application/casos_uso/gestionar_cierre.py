"""Caso de uso: flujo de cierre de actividad (§11.3 workflow C).

Spec §6 · §4 (validar ≠ autorizar) · §12.11 (capa de aplicación).

Cuatro pasos, cuatro comandos, misma forma que `capturar_avance.py`: cada
paso carga el estado actual desde los repos, deja que
`domain.cierres.reglas.SolicitudCierre` decida si la transición es válida —
permisos y estatus incluidos— y solo entonces persiste. Ninguna regla de
negocio vive aquí, solo la secuencia.

`actividad.estatus` es el otro estado que este flujo mueve, fuera del propio
`solicitud_cierre` (§7.6, comentario en `domain.shared.diccionario.EstatusActividad`):
solicitar dejar la actividad en ``pendiente_cierre``, validar la deja en
``concluida``. Rechazar la regresa a lo que el avance ejecutado ya dicta,
recalculado con la misma fórmula del §6 (`resolver_estatus`), no con un valor
fijo — así una actividad rechazada al 95% vuelve a ``casi``, no a
``programada``.

**Evento `ActividadCerrada` (§11.1, §11.3 C.4):** lo publica `ValidarCierre`,
que es el paso que deja la actividad ``concluida`` —el diagrama del §11.3 C
pone el evento después de `validada`, no de `autorizada`. Se publica **fuera**
de la unidad de trabajo, ya commiteado el cierre: quien escucha (el recálculo
de CPM) es otro contexto y no puede revertir un cierre válido si falla (§11.1
"in-process o vía Arq"). El caso de uso no sabe quién escucha; el bus lo
ensambla el borde.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from obractrl.application.casos_uso.capturar_avance import ActividadNoEncontrada
from obractrl.application.eventos import ActividadCerrada, PublicadorEventos
from obractrl.application.puertos.repositorios import (
    RegistroNoEncontrado,
    RepositorioActividades,
    RepositorioCierres,
    UnidadDeTrabajo,
)
from obractrl.domain.avance.reglas import resolver_estatus
from obractrl.domain.cierres.reglas import ErrorDeCierre, SolicitudCierre
from obractrl.domain.shared.diccionario import (
    EstatusActividad,
    EstatusSolicitudCierre,
    Rol,
)
from obractrl.domain.shared.valores import Avance, Dinero, PrecioUnitario

__all__ = [
    "AutorizarCierre",
    "ComandoAutorizarCierre",
    "ComandoRechazarCierre",
    "ComandoSolicitarCierre",
    "ComandoValidarCierre",
    "ErrorDeCierre",
    "RechazarCierre",
    "SolicitarCierre",
    "SolicitudCierreCreada",
    "SolicitudCierreNoEncontrada",
    "ValidarCierre",
]


class SolicitudCierreNoEncontrada(LookupError):
    """La solicitud no existe o está fuera del alcance del usuario (RLS)."""


@dataclass(frozen=True, slots=True)
class ComandoSolicitarCierre:
    actividad_id: UUID
    residente_id: UUID
    rol: Rol
    cantidad: Decimal
    checklist: list[dict]
    adjuntos: list[str]


@dataclass(frozen=True, slots=True)
class ComandoAutorizarCierre:
    cierre_id: UUID
    usuario_id: UUID
    rol: Rol


@dataclass(frozen=True, slots=True)
class ComandoValidarCierre:
    cierre_id: UUID
    usuario_id: UUID
    rol: Rol
    comentario: str | None = None


@dataclass(frozen=True, slots=True)
class ComandoRechazarCierre:
    cierre_id: UUID
    usuario_id: UUID
    rol: Rol
    motivo: str


@dataclass(frozen=True, slots=True)
class SolicitudCierreCreada:
    id: UUID
    solicitud: SolicitudCierre


def _reconstruir(fila: dict) -> SolicitudCierre:
    """Reconstruye la entidad desde lo persistido para aplicarle la siguiente
    transición — no pasa por `SolicitudCierre.solicitar`, eso ya ocurrió."""
    return SolicitudCierre(
        actividad_id=str(fila["actividad_id"]),
        solicitada_por=str(fila["solicitada_por"]),
        cantidad=Decimal(str(fila["cantidad"])),
        monto=Dinero(fila["monto"]),
        checklist=list(fila["checklist"]),
        adjuntos=list(fila["adjuntos"]),
        estatus=EstatusSolicitudCierre(fila["estatus"]),
        autorizada_por=str(fila["autorizada_por"]) if fila["autorizada_por"] else None,
        validada_por=str(fila["validada_por"]) if fila["validada_por"] else None,
        comentarios=fila["comentarios"],
    )


class SolicitarCierre:
    """Residente solicita el cierre de una actividad (§11.3 C.1)."""

    def __init__(
        self,
        *,
        actividades: RepositorioActividades,
        cierres: RepositorioCierres,
        uow: UnidadDeTrabajo,
    ) -> None:
        self._actividades = actividades
        self._cierres = cierres
        self._uow = uow

    async def ejecutar(self, cmd: ComandoSolicitarCierre) -> SolicitudCierreCreada:
        actividad = await self._actividades.obtener(cmd.actividad_id)
        if actividad is None:
            raise ActividadNoEncontrada(
                f"Actividad {cmd.actividad_id} no encontrada en tu alcance."
            )

        precio = PrecioUnitario(
            total=Dinero(actividad["precio_unitario"]),
            destajo=Dinero(actividad["precio_destajo"]),
        )
        precio_aplicable = precio.para_modo(actividad["modo_pago"])

        solicitud = SolicitudCierre.solicitar(
            actividad_id=str(cmd.actividad_id),
            residente_id=str(cmd.residente_id),
            rol=cmd.rol,
            cantidad=cmd.cantidad,
            precio_unitario=precio_aplicable,
            checklist=cmd.checklist,
            adjuntos=cmd.adjuntos,
        )

        async with self._uow:
            cierre_id = await self._cierres.crear(
                actividad_id=cmd.actividad_id,
                solicitada_por=cmd.residente_id,
                cantidad=solicitud.cantidad,
                monto=solicitud.monto.monto,
                checklist=solicitud.checklist,
                adjuntos=solicitud.adjuntos,
            )
            await self._marcar_actividad(cmd.actividad_id, EstatusActividad.PENDIENTE_CIERRE)
            await self._uow.commit()

        return SolicitudCierreCreada(id=cierre_id, solicitud=solicitud)

    async def _marcar_actividad(self, actividad_id: UUID, estatus: EstatusActividad) -> None:
        try:
            await self._actividades.marcar_estatus(actividad_id, estatus.value)
        except RegistroNoEncontrado as exc:
            raise ActividadNoEncontrada(
                f"Actividad {actividad_id} ya no está en tu alcance."
            ) from exc


class AutorizarCierre:
    """Supervisor autoriza: cierra la actividad (§4, §11.3 C.2)."""

    def __init__(
        self, *, cierres: RepositorioCierres, uow: UnidadDeTrabajo
    ) -> None:
        self._cierres = cierres
        self._uow = uow

    async def ejecutar(self, cmd: ComandoAutorizarCierre) -> SolicitudCierre:
        fila = await self._cierres.obtener(cmd.cierre_id)
        if fila is None:
            raise SolicitudCierreNoEncontrada(
                f"Solicitud {cmd.cierre_id} no encontrada en tu alcance."
            )
        solicitud = _reconstruir(fila)
        solicitud.autorizar(usuario_id=str(cmd.usuario_id), rol=cmd.rol)

        async with self._uow:
            try:
                await self._cierres.actualizar(
                    cmd.cierre_id,
                    estatus=solicitud.estatus.value,
                    autorizada_por=cmd.usuario_id,
                )
            except RegistroNoEncontrado as exc:
                raise SolicitudCierreNoEncontrada(
                    f"Solicitud {cmd.cierre_id} ya no está en tu alcance."
                ) from exc
            await self._uow.commit()

        return solicitud


class ValidarCierre:
    """Control de obra valida y comenta: no autoriza (§4, §11.3 C.3).

    Habilita la actividad para estimación al dejarla ``concluida`` y publica
    `ActividadCerrada` (§11.3 C.4). El bus es opcional: sin él el flujo de
    cierre funciona igual, solo que nadie reacciona.
    """

    def __init__(
        self,
        *,
        actividades: RepositorioActividades,
        cierres: RepositorioCierres,
        uow: UnidadDeTrabajo,
        eventos: PublicadorEventos | None = None,
    ) -> None:
        self._actividades = actividades
        self._cierres = cierres
        self._uow = uow
        self._eventos = eventos

    async def ejecutar(self, cmd: ComandoValidarCierre) -> SolicitudCierre:
        fila = await self._cierres.obtener(cmd.cierre_id)
        if fila is None:
            raise SolicitudCierreNoEncontrada(
                f"Solicitud {cmd.cierre_id} no encontrada en tu alcance."
            )
        solicitud = _reconstruir(fila)
        solicitud.validar(usuario_id=str(cmd.usuario_id), rol=cmd.rol, comentario=cmd.comentario)

        actividad_id = UUID(solicitud.actividad_id)
        # Se lee antes del commit y solo si alguien escucha: el evento viaja
        # con la obra a la que pertenece la actividad, y quien lo reciba no
        # puede volver a preguntarle al repo de otro contexto (§11.1).
        obra_id = (
            (await self._actividades.obtener(actividad_id) or {}).get("obra_id")
            if self._eventos is not None
            else None
        )

        async with self._uow:
            try:
                await self._cierres.actualizar(
                    cmd.cierre_id,
                    estatus=solicitud.estatus.value,
                    validada_por=cmd.usuario_id,
                    comentarios=solicitud.comentarios,
                )
                await self._actividades.marcar_estatus(
                    actividad_id, EstatusActividad.CONCLUIDA.value
                )
            except RegistroNoEncontrado as exc:
                raise SolicitudCierreNoEncontrada(
                    f"Solicitud {cmd.cierre_id} ya no está en tu alcance."
                ) from exc
            await self._uow.commit()

        if self._eventos is not None and obra_id is not None:
            await self._eventos.publicar(
                ActividadCerrada(obra_id=obra_id, actividad_id=actividad_id)
            )

        return solicitud


class RechazarCierre:
    """Supervisor o Control de obra rechazan la solicitud (§11.2)."""

    def __init__(
        self,
        *,
        actividades: RepositorioActividades,
        cierres: RepositorioCierres,
        uow: UnidadDeTrabajo,
    ) -> None:
        self._actividades = actividades
        self._cierres = cierres
        self._uow = uow

    async def ejecutar(self, cmd: ComandoRechazarCierre) -> SolicitudCierre:
        fila = await self._cierres.obtener(cmd.cierre_id)
        if fila is None:
            raise SolicitudCierreNoEncontrada(
                f"Solicitud {cmd.cierre_id} no encontrada en tu alcance."
            )
        solicitud = _reconstruir(fila)
        solicitud.rechazar(usuario_id=str(cmd.usuario_id), rol=cmd.rol, motivo=cmd.motivo)

        actividad_id = UUID(solicitud.actividad_id)
        actividad = await self._actividades.obtener(actividad_id)
        # `EstatusActividad.PROGRAMADA` es automático a propósito: fuerza a
        # `resolver_estatus` a recalcular desde el avance real en vez de
        # devolver `pendiente_cierre` sin cambios (§6).
        avance_pct = Decimal(str(actividad["avance_pct"])) if actividad else Decimal(0)
        nuevo_estatus = resolver_estatus(Avance(avance_pct), EstatusActividad.PROGRAMADA)

        async with self._uow:
            try:
                await self._cierres.actualizar(
                    cmd.cierre_id,
                    estatus=solicitud.estatus.value,
                    comentarios=solicitud.comentarios,
                )
                await self._actividades.marcar_estatus(actividad_id, nuevo_estatus.value)
            except RegistroNoEncontrado as exc:
                raise SolicitudCierreNoEncontrada(
                    f"Solicitud {cmd.cierre_id} ya no está en tu alcance."
                ) from exc
            await self._uow.commit()

        return solicitud
