"""Casos de uso: el cierre de un frente (migración 0071; D-515/D-522/D-261).

El residente solicita el cierre de un frente —un nivel— al 90 % de avance, el
supervisor lo aprueba y control de obra lo valida. Las transiciones y los permisos
los decide `domain.cierres.frente`; aquí solo se secuencia. Mismo molde que
`gestionar_cierre` (el cierre de actividad).

`ConsultarFrentesDeObra` trae cada frente con su avance y su cierre, y marca los que
están **listos para cierre** (`frente_listo_para_cierre`): una alerta que avisa, no
cierra —el cierre pregunta, no impide—.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.generar_obra_desde_prototipo import ObraNoEncontrada
from obractrl.application.puertos.cierre_frente import RepositorioCierresDeFrente
from obractrl.application.puertos.repositorios import (
    RegistroNoEncontrado,
    RepositorioObras,
    UnidadDeTrabajo,
)
from obractrl.domain.cierres.frente import (
    UMBRAL_CIERRE_DE_FRENTE,
    CierreDeFrente,
    EstatusCierreFrente,
    frente_listo_para_cierre,
)
from obractrl.domain.cierres.reglas import ErrorDeCierre
from obractrl.domain.shared.diccionario import Rol

__all__ = [
    "AprobarCierreDeFrente",
    "CierreDeFrenteNoEncontrado",
    "ComandoAprobarCierreDeFrente",
    "ComandoRechazarCierreDeFrente",
    "ComandoSolicitarCierreDeFrente",
    "ComandoValidarCierreDeFrente",
    "ConsultarFrentesDeObra",
    "ErrorDeCierre",
    "FrenteNoEncontrado",
    "RechazarCierreDeFrente",
    "SolicitarCierreDeFrente",
    "ValidarCierreDeFrente",
]

_VIVOS = (
    EstatusCierreFrente.SOLICITADO.value,
    EstatusCierreFrente.APROBADO.value,
    EstatusCierreFrente.VALIDADO.value,
)


class CierreDeFrenteNoEncontrado(LookupError):
    """El cierre no existe o salió del alcance (RLS): indistinguibles a propósito."""


class FrenteNoEncontrado(LookupError):
    """La obra no tiene actividades en ese nivel (o no se ve)."""


@dataclass(frozen=True, slots=True)
class ComandoSolicitarCierreDeFrente:
    obra_id: UUID
    nivel_id: UUID
    residente_id: UUID
    rol: Rol


@dataclass(frozen=True, slots=True)
class ComandoAprobarCierreDeFrente:
    cierre_id: UUID
    usuario_id: UUID
    rol: Rol


@dataclass(frozen=True, slots=True)
class ComandoValidarCierreDeFrente:
    cierre_id: UUID
    usuario_id: UUID
    rol: Rol
    comentario: str | None = None


@dataclass(frozen=True, slots=True)
class ComandoRechazarCierreDeFrente:
    cierre_id: UUID
    usuario_id: UUID
    rol: Rol
    motivo: str


def _reconstruir(fila: dict) -> CierreDeFrente:
    return CierreDeFrente(
        nivel_id=str(fila["nivel_id"]),
        solicitado_por=str(fila["solicitado_por"]),
        avance_pct=Decimal(str(fila["avance_pct"])),
        estatus=EstatusCierreFrente(str(fila["estatus"])),
        aprobado_por=str(fila["aprobado_por"]) if fila["aprobado_por"] else None,
        validado_por=str(fila["validado_por"]) if fila["validado_por"] else None,
        comentarios=fila["comentarios"],
    )


class ConsultarFrentesDeObra:
    """`GET /obras/{id}/cierres-frente`: cada frente con su avance y su cierre."""

    def __init__(
        self, *, cierres: RepositorioCierresDeFrente, obras: RepositorioObras
    ) -> None:
        self._cierres = cierres
        self._obras = obras

    async def ejecutar(self, obra_id: UUID) -> list[dict[str, Any]]:
        if await self._obras.obtener(obra_id) is None:
            raise ObraNoEncontrada(f"Obra {obra_id} no encontrada en tu alcance.")
        frentes = await self._cierres.frentes_de_obra(obra_id)
        return [
            {
                **f,
                "umbral_pct": UMBRAL_CIERRE_DE_FRENTE,
                "listo_para_cierre": frente_listo_para_cierre(
                    Decimal(str(f["avance_pct"] or 0)),
                    estatus_vivo=f["cierre_estatus"] if f["cierre_estatus"] in _VIVOS else None,
                ),
            }
            for f in frentes
        ]


class SolicitarCierreDeFrente:
    """El residente solicita el cierre de un frente, al 90 %."""

    def __init__(
        self, *, cierres: RepositorioCierresDeFrente, uow: UnidadDeTrabajo
    ) -> None:
        self._cierres = cierres
        self._uow = uow

    async def ejecutar(self, cmd: ComandoSolicitarCierreDeFrente) -> tuple[UUID, CierreDeFrente]:
        avance = await self._cierres.avance_del_frente(cmd.obra_id, cmd.nivel_id)
        if avance is None:
            raise FrenteNoEncontrado(
                f"La obra {cmd.obra_id} no tiene actividades en el frente {cmd.nivel_id}."
            )

        cierre = CierreDeFrente.solicitar(
            nivel_id=str(cmd.nivel_id),
            residente_id=str(cmd.residente_id),
            rol=cmd.rol,
            avance_pct=avance,
        )

        # Un cierre vivo por frente: la validada es definitiva y la rechazada no
        # estorba. Se avisa con el estado, no con el choque del índice único.
        for frente in await self._cierres.frentes_de_obra(cmd.obra_id):
            if str(frente["nivel_id"]) == str(cmd.nivel_id) and frente["cierre_estatus"] in _VIVOS:
                raise ErrorDeCierre(
                    f"El frente ya tiene un cierre {frente['cierre_estatus']}: no cabe otra solicitud."
                )

        async with self._uow:
            cierre_id = await self._cierres.crear(
                obra_id=cmd.obra_id,
                nivel_id=cmd.nivel_id,
                avance_pct=avance,
                solicitado_por=cmd.residente_id,
            )
            await self._uow.commit()
        return cierre_id, cierre


class _PasoDelCierre:
    def __init__(
        self, *, cierres: RepositorioCierresDeFrente, uow: UnidadDeTrabajo
    ) -> None:
        self._cierres = cierres
        self._uow = uow

    async def _cargar(self, cierre_id: UUID) -> CierreDeFrente:
        fila = await self._cierres.obtener(cierre_id)
        if fila is None:
            raise CierreDeFrenteNoEncontrado(
                f"Cierre de frente {cierre_id} no encontrado en tu alcance."
            )
        return _reconstruir(fila)

    async def _guardar(self, cierre_id: UUID, cierre: CierreDeFrente, **autores: Any) -> None:
        async with self._uow:
            try:
                await self._cierres.actualizar(
                    cierre_id,
                    estatus=cierre.estatus.value,
                    comentarios=cierre.comentarios,
                    **autores,
                )
            except RegistroNoEncontrado as exc:
                raise CierreDeFrenteNoEncontrado(
                    f"Cierre de frente {cierre_id} ya no está en tu alcance."
                ) from exc
            await self._uow.commit()


class AprobarCierreDeFrente(_PasoDelCierre):
    """El supervisor aprueba."""

    async def ejecutar(self, cmd: ComandoAprobarCierreDeFrente) -> CierreDeFrente:
        cierre = await self._cargar(cmd.cierre_id)
        cierre.aprobar(usuario_id=str(cmd.usuario_id), rol=cmd.rol)
        await self._guardar(cmd.cierre_id, cierre, aprobado_por=cmd.usuario_id)
        return cierre


class ValidarCierreDeFrente(_PasoDelCierre):
    """Control de obra valida: el frente queda cerrado (al residente)."""

    async def ejecutar(self, cmd: ComandoValidarCierreDeFrente) -> CierreDeFrente:
        cierre = await self._cargar(cmd.cierre_id)
        cierre.validar(usuario_id=str(cmd.usuario_id), rol=cmd.rol, comentario=cmd.comentario)
        await self._guardar(cmd.cierre_id, cierre, validado_por=cmd.usuario_id)
        return cierre


class RechazarCierreDeFrente(_PasoDelCierre):
    """El supervisor o control de obra rechazan, con motivo."""

    async def ejecutar(self, cmd: ComandoRechazarCierreDeFrente) -> CierreDeFrente:
        cierre = await self._cargar(cmd.cierre_id)
        cierre.rechazar(usuario_id=str(cmd.usuario_id), rol=cmd.rol, motivo=cmd.motivo)
        await self._guardar(cmd.cierre_id, cierre)
        return cierre
