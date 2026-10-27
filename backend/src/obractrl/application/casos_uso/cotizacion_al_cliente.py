"""Cotización al cliente de lo que la obra modificó (cerebro D-531 a D-533, D-546; B-123).

Control de obra cotiza (hoy es quien lo hace) y registra la respuesta del cliente; el área que
debería registrarla —Proyectos y atención al cliente— no es todavía un rol del sistema. El factor
(0.7) y el precio por m² (17,000) son parámetros editables de `configuracion`; cada cotización
guarda los que valieron al hacerla.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.generar_obra_desde_prototipo import ObraNoEncontrada
from obractrl.application.puertos.partes import RepositorioPartes
from obractrl.application.puertos.repositorios import (
    RepositorioConfiguracion,
    RepositorioObras,
    UnidadDeTrabajo,
)
from obractrl.domain.partes.cotizacion import (
    FACTOR_POR_DEFECTO,
    PRECIO_M2_POR_DEFECTO,
    MetodoDePrecio,
    Modificado,
    cotizar,
)

CLAVE_FACTOR = "cotizacion_factor"
CLAVE_PRECIO_M2 = "cotizacion_precio_m2"


class CotizacionNoEncontrada(LookupError):
    """La cotización no existe o está fuera del alcance."""


@dataclass(frozen=True, slots=True)
class ComandoCotizar:
    obra_id: UUID
    metodo: MetodoDePrecio
    usuario_id: UUID
    m2_ampliacion: Decimal | None = None
    precio_m2: Decimal | None = None
    """Si no se da, el precio por m² configurado."""
    nota: str | None = None


class CotizarLoModificado:
    """`POST /obras/{id}/cotizaciones`."""

    def __init__(
        self,
        *,
        partes: RepositorioPartes,
        obras: RepositorioObras,
        configuracion: RepositorioConfiguracion,
        uow: UnidadDeTrabajo,
    ) -> None:
        self._partes = partes
        self._obras = obras
        self._config = configuracion
        self._uow = uow

    async def ejecutar(self, cmd: ComandoCotizar) -> dict[str, Any]:
        obra = await self._obras.obtener(cmd.obra_id)
        if obra is None:
            raise ObraNoEncontrada(f"Obra {cmd.obra_id} no encontrada en tu alcance.")
        factor = await self._config.decimal(CLAVE_FACTOR, FACTOR_POR_DEFECTO)
        precio_m2 = cmd.precio_m2 or await self._config.decimal(CLAVE_PRECIO_M2, PRECIO_M2_POR_DEFECTO)
        modificados = [
            Modificado(
                actividad_id=str(f["actividad_id"]),
                descripcion=f["descripcion"],
                concepto_clave=f["concepto_clave"],
                delta=Decimal(str(f["delta"])),
                precio_unitario=Decimal(str(f["precio_unitario"] or 0)),
            )
            for f in await self._partes.modificados_netos(cmd.obra_id)
        ]
        c = cotizar(
            modificados,
            metodo=cmd.metodo,
            factor=factor,
            m2_ampliacion=cmd.m2_ampliacion,
            precio_m2=precio_m2 if cmd.metodo is MetodoDePrecio.POR_M2 else None,
        )
        async with self._uow:
            fila = await self._partes.crear_cotizacion(
                obra_id=cmd.obra_id,
                obra_clave=str(obra["clave"]),
                metodo=c.metodo.value,
                factor=c.factor,
                costo_entra=c.costo_entra,
                costo_sale=c.costo_sale,
                m2_ampliacion=cmd.m2_ampliacion,
                precio_m2=precio_m2 if c.precio_por_m2 is not None else None,
                precio_por_diferencia=c.precio_por_diferencia,
                precio_por_m2=c.precio_por_m2,
                precio=c.precio,
                lineas=list(c.lineas),
                nota=cmd.nota,
                usuario_id=cmd.usuario_id,
            )
            await self._uow.commit()
        return _dto(fila)


class ConsultarCotizaciones:
    """`GET /obras/{id}/cotizaciones`."""

    def __init__(self, *, partes: RepositorioPartes, obras: RepositorioObras) -> None:
        self._partes = partes
        self._obras = obras

    async def ejecutar(self, obra_id: UUID) -> list[dict[str, Any]]:
        if await self._obras.obtener(obra_id) is None:
            raise ObraNoEncontrada(f"Obra {obra_id} no encontrada en tu alcance.")
        return [_dto(f) for f in await self._partes.cotizaciones_de_obra(obra_id)]


class ResponderCotizacion:
    """`POST /cotizaciones/{id}/respuesta`: el cliente la aceptó o la rechazó (una sola vez)."""

    def __init__(self, *, partes: RepositorioPartes, uow: UnidadDeTrabajo) -> None:
        self._partes = partes
        self._uow = uow

    async def ejecutar(
        self, cotizacion_id: UUID, *, aceptada: bool, usuario_id: UUID, nota: str | None
    ) -> dict[str, Any]:
        async with self._uow:
            fila = await self._partes.responder_cotizacion(
                cotizacion_id, aceptada=aceptada, usuario_id=usuario_id, nota=nota
            )
            if fila is None:
                raise CotizacionNoEncontrada(f"Cotización {cotizacion_id} no encontrada en tu alcance.")
            await self._uow.commit()
        return _dto(fila)


def _dto(f: dict[str, Any]) -> dict[str, Any]:
    entra = [x for x in f["lineas"] if x["bloque"] == "entra"]
    sale = [x for x in f["lineas"] if x["bloque"] == "sale"]
    coincide = (
        None
        if f["precio_por_m2"] is None
        else abs(Decimal(str(f["precio_por_m2"])) - Decimal(str(f["precio_por_diferencia"]))) < Decimal("1")
    )
    return {**f, "entra": entra, "sale": sale, "por_m2_coincide_con_la_diferencia": coincide}
