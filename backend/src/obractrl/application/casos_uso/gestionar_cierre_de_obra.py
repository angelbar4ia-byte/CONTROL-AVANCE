"""Caso de uso: cierre de obra final — workflow D (§11.3 D, §11.2).

Es la culminación del piloto: se cierra la obra con la que se empezó.

## Por qué la obra se congela DENTRO de la transacción y no por evento

El §11.3 D.3 dice «evento `CierreObra` → obra `entregada` (congelada)», y la
tentación es publicarlo por el bus. No se hace, por lo mismo que
`IncidenciaDetiene` documenta para el bloqueo de actividades: **`BusEnProceso`
se traga los fallos de sus manejadores a propósito**, y `entregada` no es un
dato derivado que se pueda recalcular después — es una frontera de permisos.
Una obra que quedara cerrada sin congelar admitiría capturas de avance sobre un
acta ya firmada, y nadie se enteraría.

Así que el `update` viaja en la misma unidad de trabajo que el cierre, por el
puerto `RepositorioObras` (§11.1: por fachada, nunca tocando la tabla de otro
contexto). El evento se publica **después** del commit, para lo que sí es
derivado.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from obractrl.application.eventos import CierreDeObraCompletado, PublicadorEventos
from obractrl.application.puertos.repositorios import (
    RepositorioCierresDeObra,
    RepositorioObras,
    UnidadDeTrabajo,
)
from obractrl.domain.cierres.obra import (
    APORTACION_POR_ROL,
    CierreDeObra,
    ErrorDeCierreDeObra,
    Pendiente,
    evaluar_pendientes,
    puede_abrir_cierre_de_obra,
)
from obractrl.domain.shared.diccionario import EstatusObra, Rol

__all__ = [
    "AbrirCierreDeObra",
    "CierreDeObraNoEncontrado",
    "ComandoAbrirCierreDeObra",
    "ComandoParticipar",
    "ConsultarCierreDeObra",
    "ErrorDeCierreDeObra",
    "Participar",
    "ResultadoDeCierreDeObra",
]


class CierreDeObraNoEncontrado(LookupError):
    """El cierre no existe o está fuera de alcance. Las dos son un 404 (§12.4)."""


@dataclass(frozen=True, slots=True)
class ComandoAbrirCierreDeObra:
    obra_id: UUID
    usuario_id: UUID
    rol: Rol


@dataclass(frozen=True, slots=True)
class ComandoParticipar:
    cierre_id: UUID
    usuario_id: UUID
    rol: Rol
    comentario: str | None = None
    evidencias: tuple[str, ...] = ()
    acta: str | None = None
    """Texto del acta. Solo lo aporta la firma del Super intendente; en los
    demás roles se ignora, porque el acta es del cierre y no de cada parte."""


@dataclass(frozen=True, slots=True)
class ResultadoDeCierreDeObra:
    """Lo que la pantalla necesita después de cualquier paso del workflow."""

    id: UUID
    obra_id: UUID
    estatus: str
    pendientes: tuple[Pendiente, ...]
    participaron: tuple[Rol, ...]
    faltan: tuple[Rol, ...]
    cerro_la_obra: bool = False
    """`True` solo en la participación que completó el acta: es lo que permite
    a la pantalla decir «la obra quedó entregada» en vez de «guardado»."""


def _aportacion(rol: Rol) -> str:
    return APORTACION_POR_ROL.get(rol, "")


class AbrirCierreDeObra:
    """`POST /obras/{id}/cierre-obra` (Super intendente, §11.2)."""

    def __init__(
        self,
        *,
        cierres: RepositorioCierresDeObra,
        uow: UnidadDeTrabajo,
    ) -> None:
        self._cierres = cierres
        self._uow = uow

    async def ejecutar(
        self, cmd: ComandoAbrirCierreDeObra
    ) -> ResultadoDeCierreDeObra:
        if not puede_abrir_cierre_de_obra(cmd.rol):
            raise ErrorDeCierreDeObra(
                f"Un {cmd.rol.value} no abre el cierre de una obra; lo hace el "
                f"super intendente (§11.2)."
            )

        async with self._uow:
            cierre_id = await self._cierres.abrir(
                obra_id=cmd.obra_id, abierto_por=cmd.usuario_id
            )
            await self._uow.commit()

        # Los pendientes se reúnen **después** de abrir (§11.3 D.1): abrir con
        # pendientes está permitido y es el punto — convocar al equipo es lo que
        # hace que se resuelvan. Lo que no se puede es firmar con ellos.
        return await _armar_resultado(self._cierres, cierre_id)


class Participar:
    """`POST /cierres-obra/{id}/participar` (los cuatro roles, §11.3 D.2)."""

    def __init__(
        self,
        *,
        cierres: RepositorioCierresDeObra,
        obras: RepositorioObras,
        uow: UnidadDeTrabajo,
        eventos: PublicadorEventos,
    ) -> None:
        self._cierres = cierres
        self._obras = obras
        self._uow = uow
        self._eventos = eventos

    async def ejecutar(self, cmd: ComandoParticipar) -> ResultadoDeCierreDeObra:
        fila = await self._cierres.obtener(cmd.cierre_id)
        if fila is None:
            raise CierreDeObraNoEncontrado(
                f"El cierre {cmd.cierre_id} no existe o está fuera de tu alcance."
            )

        participaciones = await self._cierres.participaciones(cmd.cierre_id)
        cierre = CierreDeObra(
            obra_id=str(fila["obra_id"]),
            participantes=frozenset(Rol(p["rol"]) for p in participaciones),
            cerrada=fila["estatus"] == "cerrada",
        )

        # El dominio decide si este rol puede participar y si con esto se
        # completa el acta. Levanta si ya participó o si la obra ya se cerró.
        despues = cierre.registrar_participacion(cmd.rol)

        estado = await self._cierres.estado_de_obra(UUID(str(fila["obra_id"])))
        pendientes = evaluar_pendientes(estado or {})

        # Si con esta participación se completa el acta, el cierre tiene que
        # poder cerrarse **antes** de escribir nada: registrar la firma y
        # después descubrir que faltaba resolver dejaría un acta completa sobre
        # una obra que no se puede entregar.
        cierra_ahora = despues.participaron_todos
        if cierra_ahora:
            despues.exigir_que_se_pueda_cerrar(pendientes)

        async with self._uow:
            await self._cierres.participar(
                cierre_obra_id=cmd.cierre_id,
                usuario_id=cmd.usuario_id,
                rol=cmd.rol.value,
                comentario=cmd.comentario,
                evidencias=list(cmd.evidencias),
            )
            if cierra_ahora:
                await self._cierres.cerrar(
                    cmd.cierre_id, fecha=date.today(), acta=cmd.acta
                )
                # Dentro de la transacción, no por evento: ver el encabezado.
                await self._obras.actualizar(
                    UUID(str(fila["obra_id"])),
                    {"estatus": EstatusObra.ENTREGADA.value},
                )
            await self._uow.commit()

        if cierra_ahora:
            # Después del commit, como `ValidarCierre`: el bus se traga los
            # fallos y no puede deshacer una entrega ya firmada.
            await self._eventos.publicar(
                CierreDeObraCompletado(
                    obra_id=UUID(str(fila["obra_id"])), cierre_id=cmd.cierre_id
                )
            )

        resultado = await _armar_resultado(self._cierres, cmd.cierre_id)
        return ResultadoDeCierreDeObra(
            id=resultado.id,
            obra_id=resultado.obra_id,
            estatus=resultado.estatus,
            pendientes=resultado.pendientes,
            participaron=resultado.participaron,
            faltan=resultado.faltan,
            cerro_la_obra=cierra_ahora,
        )


class ConsultarCierreDeObra:
    """Estado del acta y lo que falta (§11.3 D.1)."""

    def __init__(self, *, cierres: RepositorioCierresDeObra) -> None:
        self._cierres = cierres

    async def ejecutar(self, cierre_id: UUID) -> ResultadoDeCierreDeObra:
        return await _armar_resultado(self._cierres, cierre_id)


async def _armar_resultado(
    cierres: RepositorioCierresDeObra, cierre_id: UUID
) -> ResultadoDeCierreDeObra:
    fila = await cierres.obtener(cierre_id)
    if fila is None:
        raise CierreDeObraNoEncontrado(
            f"El cierre {cierre_id} no existe o está fuera de tu alcance."
        )

    participaciones = await cierres.participaciones(cierre_id)
    cierre = CierreDeObra(
        obra_id=str(fila["obra_id"]),
        participantes=frozenset(Rol(p["rol"]) for p in participaciones),
        cerrada=fila["estatus"] == "cerrada",
    )
    estado = await cierres.estado_de_obra(UUID(str(fila["obra_id"])))

    return ResultadoDeCierreDeObra(
        id=cierre_id,
        obra_id=UUID(str(fila["obra_id"])),
        estatus=str(fila["estatus"]),
        pendientes=tuple(evaluar_pendientes(estado or {})),
        participaron=tuple(sorted(cierre.participantes, key=lambda r: r.value)),
        faltan=cierre.faltan_por_participar,
    )
