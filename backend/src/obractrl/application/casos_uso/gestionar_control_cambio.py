"""Casos de uso del control de cambio (§11.3, §6).

El residente pide, Control autoriza, y **al autorizar se aplica el efecto**:
subir el techo de una actividad, dar de alta el trabajo nuevo, o cancelar la
que se sustituye. Aplicarlo aquí y no en un paso aparte es lo que evita que una
solicitud quede autorizada y sin efecto —que es peor que rechazada, porque nadie
la vuelve a mirar—.

Mismo par que el cierre de actividad (`SolicitarCierre` / `AutorizarCierre`), a
propósito: es el flujo que la constructora ya conoce.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from obractrl.domain.obras.control_cambio import (
    ErrorDeControlDeCambio,
    LineaDeCambio,
    SolicitudDeCambio,
    TipoControlCambio,
    puede_autorizar,
)
from obractrl.domain.shared.diccionario import EstatusActividad, ModoPago, Rol

__all__ = [
    "ComandoResolverCambio",
    "ComandoSolicitarCambio",
    "ControlDeCambioNoResoluble",
    "ResolverControlDeCambio",
    "SolicitarControlDeCambio",
]


class ControlDeCambioNoResoluble(Exception):
    """La solicitud no existe, está fuera de alcance, o ya se resolvió."""


@dataclass(frozen=True, slots=True)
class ComandoSolicitarCambio:
    obra_id: UUID
    tipo: TipoControlCambio
    motivo: str
    lineas: tuple[LineaDeCambio, ...]
    usuario_id: UUID
    rol: Rol
    nivel_id: UUID | None = None
    etapa_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ComandoResolverCambio:
    control_id: UUID
    usuario_id: UUID
    rol: Rol
    autorizado: bool
    orden_cambio: str | None = None
    """Obligatoria al autorizar: es lo que vuelve válida la autorización, y la
    base lo repite como CHECK (`ck_control_cambio_autorizado_con_oc`)."""
    nota: str | None = None
    descuenta_ejecutado: bool = False
    """Solo en una sustitución. Lo ejecutado de la actividad reemplazada se
    estima por defecto; esto lo descuenta cuando el caso lo pide."""


class SolicitarControlDeCambio:
    """`POST /obras/{id}/controles-cambio` — el residente pide (§11.3)."""

    def __init__(self, *, controles, uow) -> None:
        self._controles = controles
        self._uow = uow

    async def ejecutar(self, cmd: ComandoSolicitarCambio) -> UUID:
        solicitud = SolicitudDeCambio.crear(
            obra_id=str(cmd.obra_id),
            tipo=cmd.tipo,
            motivo=cmd.motivo,
            lineas=cmd.lineas,
            rol=cmd.rol,
            nivel_id=str(cmd.nivel_id) if cmd.nivel_id else None,
            etapa_id=str(cmd.etapa_id) if cmd.etapa_id else None,
        )

        async with self._uow:
            control_id = await self._controles.crear(
                {
                    "obra_id": cmd.obra_id,
                    "tipo": str(solicitud.tipo),
                    "nivel_id": solicitud.nivel_id,
                    "etapa_id": solicitud.etapa_id,
                    "motivo": solicitud.motivo,
                    "solicitado_por": cmd.usuario_id,
                    "lineas": [
                        {
                            "actividad_id": linea.actividad_id,
                            "concepto_id": linea.concepto_id,
                            "descripcion": linea.descripcion,
                            "cantidad": linea.cantidad,
                            "precio_unitario": linea.precio_unitario,
                            "sustituye_a": linea.sustituye_a,
                        }
                        for linea in solicitud.lineas
                    ],
                }
            )
            await self._uow.commit()
        return control_id


class ResolverControlDeCambio:
    """`POST /controles-cambio/{id}/resolver` — Control decide (§11.3).

    Autorizar **aplica el efecto en la misma transacción**. Si se guardara el
    "sí" y el efecto quedara para después, una solicitud autorizada y sin
    aplicar sería invisible: ni sale como pendiente ni cambió nada.
    """

    def __init__(self, *, controles, actividades, uow) -> None:
        self._controles = controles
        self._actividades = actividades
        self._uow = uow

    async def ejecutar(self, cmd: ComandoResolverCambio) -> dict[str, int]:
        if not puede_autorizar(cmd.rol):
            raise ErrorDeControlDeCambio(
                f"Un {cmd.rol.value} no resuelve controles de cambio; lo hacen "
                f"Control de obra y el Super intendente (§4).",
                campo="rol",
            )
        if cmd.autorizado and not (cmd.orden_cambio or "").strip():
            raise ErrorDeControlDeCambio(
                "Autorizar necesita la orden de cambio que lo respalda: sin "
                "ella la autorización no autoriza nada.",
                campo="orden_cambio",
            )

        control = await self._controles.obtener(cmd.control_id)
        if control is None:
            raise ControlDeCambioNoResoluble(
                f"El control de cambio {cmd.control_id} no existe o está fuera "
                f"de tu alcance."
            )

        lineas = await self._controles.lineas_de(cmd.control_id)

        async with self._uow:
            resuelto = await self._controles.resolver(
                cmd.control_id,
                autorizado=cmd.autorizado,
                usuario_id=cmd.usuario_id,
                orden_cambio=cmd.orden_cambio,
                nota=cmd.nota,
                descuenta_ejecutado=cmd.descuenta_ejecutado,
            )
            if not resuelto:
                raise ControlDeCambioNoResoluble(
                    f"El control de cambio {cmd.control_id} ya estaba resuelto."
                )

            efecto = (
                await self._aplicar(control, lineas, cmd)
                if cmd.autorizado
                else {"actividades_afectadas": 0, "actividades_creadas": 0}
            )
            await self._uow.commit()
        return efecto

    async def _aplicar(
        self, control: dict, lineas: list[dict], cmd: ComandoResolverCambio
    ) -> dict[str, int]:
        """Lo que la autorización cambia en la obra, según el tipo."""
        tipo = TipoControlCambio(str(control["tipo"]))
        orden = str(cmd.orden_cambio)
        afectadas = 0
        creadas = 0

        for linea in lineas:
            if tipo is TipoControlCambio.EXTRA_CATALOGO:
                # Sube el techo, no la base: la base es la cantidad del
                # proyecto y subirla borraría la desviación.
                await self._controles.autorizar_cantidad(
                    linea["actividad_id"], linea["cantidad"], orden
                )
                afectadas += 1

            elif tipo in (
                TipoControlCambio.FUERA_CATALOGO,
                TipoControlCambio.ALTA_CATALOGO,
            ):
                await self._crear_actividad(control, linea, orden)
                creadas += 1

            elif tipo is TipoControlCambio.SUSTITUCION:
                # Primero la nueva y luego dar de baja la vieja: si fallara a
                # media transacción, quedarse sin ninguna de las dos es mejor
                # que quedarse sin la que ya se estaba ejecutando.
                await self._crear_actividad(control, linea, orden)
                creadas += 1
                await self._controles.cancelar_actividad(
                    linea["sustituye_a"],
                    descuenta_ejecutado=cmd.descuenta_ejecutado,
                )
                afectadas += 1

        return {"actividades_afectadas": afectadas, "actividades_creadas": creadas}

    async def _crear_actividad(self, control: dict, linea: dict, orden: str) -> None:
        """Da de alta el trabajo autorizado, ubicado donde se pidió.

        Nace con `extra = true` y su orden de cambio, que es lo que la distingue
        de una actividad del prototipo al estimarla y al cerrar la obra.
        """
        await self._actividades.crear_extra(
            {
                "obra_id": control["obra_id"],
                "descripcion": linea.get("descripcion")
                or linea.get("actividad_descripcion")
                or "",
                "orden_cambio": orden,
                "cant_base": linea["cantidad"],
                "modo_pago": str(ModoPago.DESTAJO),
                "precio_unitario": Decimal(0),
                "precio_destajo": linea.get("precio_unitario") or Decimal(0),
                "concepto_id": linea.get("concepto_id"),
                "frente_id": None,
                "nivel_id": control.get("nivel_id"),
                "etapa_id": control.get("etapa_id"),
                "duracion_dias": Decimal(1),
                "estatus": str(EstatusActividad.EXTRA_CATALOGO),
            }
        )
