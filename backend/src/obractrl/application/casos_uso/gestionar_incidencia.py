"""Caso de uso: flujo de incidencias (§11.3 workflow F).

Spec §6 "Incidencias" · §7.8 (control y flujos) · §12.11 (capa de
aplicación).

Cinco pasos, cinco comandos, misma forma que `gestionar_cierre.py`: cada
paso carga el estado actual desde el repo, deja que
`domain.incidencias.reglas.Incidencia` decida si la transición es válida —
permisos y estatus incluidos— y solo entonces persiste. Ninguna regla de
negocio vive aquí, solo la secuencia.

Dos escrituras conviven en cada paso que transiciona: la fila de
`incidencia` (estatus/asignación) y su bitácora en `incidencia_evento`
(§7.8) — ambas dentro de la misma `UnidadDeTrabajo`, igual que
`SolicitarCierre` escribe `solicitud_cierre` y `actividad.estatus` en el
mismo commit.

Si `impacto=detiene` y la incidencia trae `bloquea_actividades`, abrirla
bloquea esas actividades; cerrarla o rechazarla las desbloquea por igual
—reutilizando `RepositorioActividades.marcar_bloqueadas` tal cual, sin
reimplementarlo (§12.11: ningún módulo toca las tablas de otro salvo por su
puerto). El rechazo también desbloquea a propósito: una incidencia
rechazada significa que el bloqueo no era válido, y `rechazada` es terminal
—sin esto, la actividad quedaría bloqueada para siempre sin ninguna vía de
recuperación (ni una incidencia nueva reabre ni desbloquea la anterior).

**Evento `IncidenciaDetiene` (§11.1, §11.3 F.5):** "Si `impacto=detiene` →
evento bloquea actividades + recalcular CPM (desfase)". Los tres pasos que
mueven el bloqueo —abrir, cerrar, rechazar— lo publican **fuera** de la
unidad de trabajo, ya commiteado el cambio, con la misma forma que
`ValidarCierre` publica `ActividadCerrada`: quien escucha (el recálculo de la
ruta crítica) es otro contexto y no puede revertir una incidencia válida si
falla (§11.1 "in-process o vía Arq"). El caso de uso no sabe quién escucha;
el bus lo ensambla el borde (`adapters/api/casos_uso.py`).

Bloquear no viaja en el evento y el recálculo sí: el bus se traga los fallos
del manejador a propósito (ver `BusEnProceso`), así que una actividad que
quedara sin bloquear sería un permiso abierto de más y nadie se enteraría,
mientras que un CPM sin recalcular es dato derivado que `POST
/obras/{id}/ruta-critica/recalcular` repone. Ver el docstring de
`application.eventos.IncidenciaDetiene`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from obractrl.application.eventos import IncidenciaDetiene, PublicadorEventos
from obractrl.application.puertos.repositorios import (
    RegistroNoEncontrado,
    RepositorioActividades,
    RepositorioIncidencias,
    UnidadDeTrabajo,
)
from obractrl.domain.incidencias.reglas import ErrorDeIncidencia, Incidencia
from obractrl.domain.shared.diccionario import (
    EstatusIncidencia,
    ImpactoIncidencia,
    Rol,
    TipoIncidencia,
)

__all__ = [
    "AbrirIncidencia",
    "CerrarIncidencia",
    "ComandoAbrirIncidencia",
    "ComandoCerrarIncidencia",
    "ComandoProgramarIncidencia",
    "ComandoRechazarIncidencia",
    "ComandoRegistrarEventoIncidencia",
    "ErrorDeIncidencia",
    "IncidenciaCreada",
    "IncidenciaNoEncontrada",
    "ProgramarIncidencia",
    "RechazarIncidencia",
    "RegistrarEventoIncidencia",
]


class IncidenciaNoEncontrada(LookupError):
    """La incidencia no existe o está fuera del alcance del usuario (RLS)."""


@dataclass(frozen=True, slots=True)
class ComandoAbrirIncidencia:
    obra_id: UUID
    creada_por: UUID
    tipo: TipoIncidencia
    impacto: ImpactoIncidencia
    titulo: str
    descripcion: str | None = None
    frente_id: UUID | None = None
    evidencias: list[str] = field(default_factory=list)
    bloquea_actividades: list[UUID] = field(default_factory=list)
    fecha_limite: date | None = None


@dataclass(frozen=True, slots=True)
class ComandoProgramarIncidencia:
    incidencia_id: UUID
    usuario_id: UUID
    rol: Rol
    asignada_a: UUID


@dataclass(frozen=True, slots=True)
class ComandoRegistrarEventoIncidencia:
    incidencia_id: UUID
    usuario_id: UUID
    accion: str
    estatus_nuevo: EstatusIncidencia | None = None
    comentario: str | None = None


@dataclass(frozen=True, slots=True)
class ComandoCerrarIncidencia:
    incidencia_id: UUID
    usuario_id: UUID
    rol: Rol
    comentario: str | None = None


@dataclass(frozen=True, slots=True)
class ComandoRechazarIncidencia:
    incidencia_id: UUID
    usuario_id: UUID
    rol: Rol
    motivo: str


@dataclass(frozen=True, slots=True)
class IncidenciaCreada:
    id: UUID
    incidencia: Incidencia


def _reconstruir(fila: dict) -> Incidencia:
    """Reconstruye la entidad desde lo persistido para aplicarle la
    siguiente transición — no pasa por `Incidencia.abrir`, eso ya ocurrió."""
    return Incidencia(
        obra_id=str(fila["obra_id"]),
        creada_por=str(fila["creada_por"]) if fila["creada_por"] else "",
        tipo=TipoIncidencia(fila["tipo"]),
        impacto=ImpactoIncidencia(fila["impacto"]),
        titulo=fila["titulo"],
        descripcion=fila["descripcion"],
        frente_id=str(fila["frente_id"]) if fila["frente_id"] else None,
        evidencias=list(fila["evidencias"]),
        bloquea_actividades=list(fila["bloquea_actividades"]),
        estatus=EstatusIncidencia(fila["estatus"]),
        asignada_a=str(fila["asignada_a"]) if fila["asignada_a"] else None,
        fecha_limite=fila["fecha_limite"],
    )


async def _publicar_detiene(
    eventos: PublicadorEventos | None,
    incidencia: Incidencia,
    *,
    obra_id: UUID,
    incidencia_id: UUID,
    bloquear: bool,
) -> None:
    """Publica `IncidenciaDetiene` si la incidencia movió el bloqueo (§11.3 F.5).

    Se llama **después** del commit, nunca dentro de la `UnidadDeTrabajo`: el
    suscriptor recalcula el CPM en otro contexto y no puede revertir el paso
    del workflow que ya quedó escrito (§11.1). Sin actividades bloqueadas no
    hay nada que replanear, así que no se publica.
    """
    if eventos is None or not incidencia.bloquea_actividades_activo:
        return
    await eventos.publicar(
        IncidenciaDetiene(
            obra_id=obra_id,
            incidencia_id=incidencia_id,
            refs_bloqueadas=tuple(incidencia.bloquea_actividades),
            bloquear=bloquear,
        )
    )


class AbrirIncidencia:
    """Cualquier rol abre una incidencia (§11.3 F.1).

    Con `impacto=detiene` bloquea las actividades listadas y publica
    `IncidenciaDetiene` (§11.3 F.5). El bus es opcional: sin él el flujo
    funciona igual, solo que nadie recalcula la ruta crítica.
    """

    def __init__(
        self,
        *,
        actividades: RepositorioActividades,
        incidencias: RepositorioIncidencias,
        uow: UnidadDeTrabajo,
        eventos: PublicadorEventos | None = None,
    ) -> None:
        self._actividades = actividades
        self._incidencias = incidencias
        self._uow = uow
        self._eventos = eventos

    async def ejecutar(self, cmd: ComandoAbrirIncidencia) -> IncidenciaCreada:
        incidencia = Incidencia.abrir(
            obra_id=str(cmd.obra_id),
            creada_por=str(cmd.creada_por),
            tipo=cmd.tipo,
            impacto=cmd.impacto,
            titulo=cmd.titulo,
            descripcion=cmd.descripcion,
            frente_id=str(cmd.frente_id) if cmd.frente_id else None,
            evidencias=cmd.evidencias,
            bloquea_actividades=[str(ref) for ref in cmd.bloquea_actividades],
            fecha_limite=cmd.fecha_limite,
        )

        async with self._uow:
            incidencia_id = await self._incidencias.crear(
                obra_id=cmd.obra_id,
                creada_por=cmd.creada_por,
                tipo=incidencia.tipo.value,
                impacto=incidencia.impacto.value,
                titulo=incidencia.titulo,
                descripcion=incidencia.descripcion,
                frente_id=cmd.frente_id,
                evidencias=incidencia.evidencias,
                bloquea_actividades=incidencia.bloquea_actividades,
                fecha_limite=incidencia.fecha_limite,
            )
            if incidencia.bloquea_actividades_activo:
                await self._actividades.marcar_bloqueadas(
                    cmd.obra_id, set(incidencia.bloquea_actividades), True
                )
            await self._uow.commit()

        await _publicar_detiene(
            self._eventos,
            incidencia,
            obra_id=cmd.obra_id,
            incidencia_id=incidencia_id,
            bloquear=True,
        )
        return IncidenciaCreada(id=incidencia_id, incidencia=incidencia)


class ProgramarIncidencia:
    """Supervisor o Control programan (asignación) (§11.3 F.2)."""

    def __init__(
        self, *, incidencias: RepositorioIncidencias, uow: UnidadDeTrabajo
    ) -> None:
        self._incidencias = incidencias
        self._uow = uow

    async def ejecutar(self, cmd: ComandoProgramarIncidencia) -> Incidencia:
        fila = await self._incidencias.obtener(cmd.incidencia_id)
        if fila is None:
            raise IncidenciaNoEncontrada(
                f"Incidencia {cmd.incidencia_id} no encontrada en tu alcance."
            )
        incidencia = _reconstruir(fila)
        estatus_previo = incidencia.estatus
        incidencia.programar(rol=cmd.rol, asignada_a=str(cmd.asignada_a))

        async with self._uow:
            try:
                await self._incidencias.actualizar(
                    cmd.incidencia_id,
                    estatus=incidencia.estatus.value,
                    asignada_a=cmd.asignada_a,
                )
                await self._incidencias.registrar_evento(
                    cmd.incidencia_id,
                    usuario_id=cmd.usuario_id,
                    accion="programar",
                    estatus_previo=estatus_previo.value,
                    estatus_nuevo=incidencia.estatus.value,
                )
            except RegistroNoEncontrado as exc:
                raise IncidenciaNoEncontrada(
                    f"Incidencia {cmd.incidencia_id} ya no está en tu alcance."
                ) from exc
            await self._uow.commit()

        return incidencia


class RegistrarEventoIncidencia:
    """Comenta y, opcionalmente, transiciona la incidencia (§11.3 F.3).

    Un mismo endpoint —`POST /incidencias/{id}/eventos`— cubre el evento de
    atención (`en_atencion`) y la solicitud de cierre (`cierre_solicitado`):
    ninguno de los dos tiene una mano única (§11.2 "todos los que
    participan"), así que el dominio no restringe el rol aquí. Sin
    `estatus_nuevo` solo agrega un comentario a la bitácora, sin mover el
    estatus.
    """

    def __init__(
        self, *, incidencias: RepositorioIncidencias, uow: UnidadDeTrabajo
    ) -> None:
        self._incidencias = incidencias
        self._uow = uow

    async def ejecutar(self, cmd: ComandoRegistrarEventoIncidencia) -> Incidencia:
        fila = await self._incidencias.obtener(cmd.incidencia_id)
        if fila is None:
            raise IncidenciaNoEncontrada(
                f"Incidencia {cmd.incidencia_id} no encontrada en tu alcance."
            )
        incidencia = _reconstruir(fila)
        estatus_previo = incidencia.estatus

        if cmd.estatus_nuevo is EstatusIncidencia.EN_ATENCION:
            incidencia.atender()
        elif cmd.estatus_nuevo is EstatusIncidencia.CIERRE_SOLICITADO:
            incidencia.solicitar_cierre()
        elif cmd.estatus_nuevo is not None:
            raise ErrorDeIncidencia(
                f"El evento no puede cambiar el estatus a "
                f"{cmd.estatus_nuevo.value!r}; usa /cerrar o /rechazar para eso."
            )

        async with self._uow:
            try:
                if cmd.estatus_nuevo is not None:
                    await self._incidencias.actualizar(
                        cmd.incidencia_id, estatus=incidencia.estatus.value
                    )
                await self._incidencias.registrar_evento(
                    cmd.incidencia_id,
                    usuario_id=cmd.usuario_id,
                    accion=cmd.accion,
                    estatus_previo=estatus_previo.value,
                    estatus_nuevo=incidencia.estatus.value,
                    comentario=cmd.comentario,
                )
            except RegistroNoEncontrado as exc:
                raise IncidenciaNoEncontrada(
                    f"Incidencia {cmd.incidencia_id} ya no está en tu alcance."
                ) from exc
            await self._uow.commit()

        return incidencia


class CerrarIncidencia:
    """Supervisor o Control cierran la incidencia (§11.3 F.4).

    Si bloqueaba actividades, las desbloquea y publica `IncidenciaDetiene`
    con ``bloquear=False`` para que se replanee la ruta crítica (§11.3 F.5).
    """

    def __init__(
        self,
        *,
        actividades: RepositorioActividades,
        incidencias: RepositorioIncidencias,
        uow: UnidadDeTrabajo,
        eventos: PublicadorEventos | None = None,
    ) -> None:
        self._actividades = actividades
        self._incidencias = incidencias
        self._uow = uow
        self._eventos = eventos

    async def ejecutar(self, cmd: ComandoCerrarIncidencia) -> Incidencia:
        fila = await self._incidencias.obtener(cmd.incidencia_id)
        if fila is None:
            raise IncidenciaNoEncontrada(
                f"Incidencia {cmd.incidencia_id} no encontrada en tu alcance."
            )
        incidencia = _reconstruir(fila)
        estatus_previo = incidencia.estatus
        incidencia.cerrar(rol=cmd.rol)

        async with self._uow:
            try:
                await self._incidencias.actualizar(
                    cmd.incidencia_id, estatus=incidencia.estatus.value
                )
                await self._incidencias.registrar_evento(
                    cmd.incidencia_id,
                    usuario_id=cmd.usuario_id,
                    accion="cerrar",
                    estatus_previo=estatus_previo.value,
                    estatus_nuevo=incidencia.estatus.value,
                    comentario=cmd.comentario,
                )
                if incidencia.bloquea_actividades_activo:
                    await self._actividades.marcar_bloqueadas(
                        UUID(incidencia.obra_id),
                        set(incidencia.bloquea_actividades),
                        False,
                    )
            except RegistroNoEncontrado as exc:
                raise IncidenciaNoEncontrada(
                    f"Incidencia {cmd.incidencia_id} ya no está en tu alcance."
                ) from exc
            await self._uow.commit()

        await _publicar_detiene(
            self._eventos,
            incidencia,
            obra_id=UUID(incidencia.obra_id),
            incidencia_id=cmd.incidencia_id,
            bloquear=False,
        )
        return incidencia


class RechazarIncidencia:
    """Supervisor o Control rechazan la incidencia (§11.2, §6).

    Si bloqueaba actividades, las desbloquea y publica `IncidenciaDetiene`
    con ``bloquear=False`` — igual que al cerrar: una incidencia rechazada no
    debe dejar nada bloqueado sin vía de recuperación, ni la ruta crítica
    midiendo contra un bloqueo que ya no existe.
    """

    def __init__(
        self,
        *,
        actividades: RepositorioActividades,
        incidencias: RepositorioIncidencias,
        uow: UnidadDeTrabajo,
        eventos: PublicadorEventos | None = None,
    ) -> None:
        self._actividades = actividades
        self._incidencias = incidencias
        self._uow = uow
        self._eventos = eventos

    async def ejecutar(self, cmd: ComandoRechazarIncidencia) -> Incidencia:
        fila = await self._incidencias.obtener(cmd.incidencia_id)
        if fila is None:
            raise IncidenciaNoEncontrada(
                f"Incidencia {cmd.incidencia_id} no encontrada en tu alcance."
            )
        incidencia = _reconstruir(fila)
        estatus_previo = incidencia.estatus
        incidencia.rechazar(rol=cmd.rol, motivo=cmd.motivo)

        async with self._uow:
            try:
                await self._incidencias.actualizar(
                    cmd.incidencia_id, estatus=incidencia.estatus.value
                )
                await self._incidencias.registrar_evento(
                    cmd.incidencia_id,
                    usuario_id=cmd.usuario_id,
                    accion="rechazar",
                    estatus_previo=estatus_previo.value,
                    estatus_nuevo=incidencia.estatus.value,
                    comentario=cmd.motivo,
                )
                if incidencia.bloquea_actividades_activo:
                    await self._actividades.marcar_bloqueadas(
                        UUID(incidencia.obra_id),
                        set(incidencia.bloquea_actividades),
                        False,
                    )
            except RegistroNoEncontrado as exc:
                raise IncidenciaNoEncontrada(
                    f"Incidencia {cmd.incidencia_id} ya no está en tu alcance."
                ) from exc
            await self._uow.commit()

        await _publicar_detiene(
            self._eventos,
            incidencia,
            obra_id=UUID(incidencia.obra_id),
            incidencia_id=cmd.incidencia_id,
            bloquear=False,
        )
        return incidencia
