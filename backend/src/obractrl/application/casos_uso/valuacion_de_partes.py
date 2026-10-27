"""Valuación de las partes: por PU, por ensamble o mixta, y el rediseño a paramétrico (cerebro
WORKFLOWS.md §8.1 y §8.9; D-571, D-578, D-579).

*«En presupuesto se autoriza, o se rediseña a paramétrico o mixto»* (escenario 1, paso 5): se valúa
por ensamble, o parte por PU y parte por ensamble. **Mixto no se guarda, se reporta en
porcentaje.** Lo realiza Costos o Control de obra.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.generar_obra_desde_prototipo import ObraNoEncontrada
from obractrl.application.casos_uso.gestionar_ensamble import ExplotarEnsamble
from obractrl.application.casos_uso.gestionar_partes import (
    _REABRE,
    ParteNoEncontrada,
    _avisar_reapertura,
    _partes_de,
    _reabrir_parte,
)
from obractrl.application.eventos import PublicadorEventos
from obractrl.application.puertos.partes import RepositorioPartes
from obractrl.application.puertos.repositorios import RepositorioObras, UnidadDeTrabajo
from obractrl.domain.partes.estado import ErrorDeParte, EstadoDeParte
from obractrl.domain.partes.modificacion import (
    ErrorDeModificacion,
    TipoDeModificacion,
    modificar,
)
from obractrl.domain.partes.valuacion import LineaValuada, valuar
from obractrl.domain.shared.diccionario import Rol

_CIEN = Decimal("100")
_DOS = Decimal("0.01")


def _lineas(filas: list[dict[str, Any]]) -> dict[str, list[LineaValuada]]:
    por_parte: dict[str, list[LineaValuada]] = defaultdict(list)
    for f in filas:
        por_parte[f["clave"]].append(
            LineaValuada(
                cantidad=Decimal(str(f["cant_base"])),
                precio=Decimal(str(f["precio_unitario"] or 0)),
                estimada=f["modo_cantidad"] == "estimada",
                cant_estimada=(
                    Decimal(str(f["cant_estimada"])) if f["cant_estimada"] is not None else None
                ),
            )
        )
    return por_parte


def _dto(v: Any) -> dict[str, Any]:
    return {
        "forma": v.forma.value,
        "importe": v.importe,
        "importe_parametrico": v.importe_parametrico,
        "porcentaje_parametrico": v.porcentaje_parametrico,
        "n_estimadas": v.n_estimadas,
        "n_renglones": v.n_total,
        "estimado_original": v.estimado_original,
        "medido": v.medido,
        "desviacion_pct": v.desviacion_pct,
    }


async def estimadas_por_parte(partes: RepositorioPartes, obra_id: UUID) -> dict[str, int]:
    """Cuántos renglones de cada parte solo tienen cantidad estimada (para avisar, D-579)."""
    por_parte = _lineas(await partes.lineas_de_valuacion(obra_id))
    return {c: sum(1 for x in ls if x.estimada) for c, ls in por_parte.items()}


class ConsultarValuacion:
    """`GET /obras/{id}/partes/valuacion`: cómo se valúa cada parte y la obra."""

    def __init__(self, *, partes: RepositorioPartes, obras: RepositorioObras) -> None:
        self._partes = partes
        self._obras = obras

    async def ejecutar(self, obra_id: UUID) -> dict[str, Any]:
        if await self._obras.obtener(obra_id) is None:
            raise ObraNoEncontrada(f"Obra {obra_id} no encontrada en tu alcance.")
        por_parte = _lineas(await self._partes.lineas_de_valuacion(obra_id))
        nombres = {p.clave: p.nombre for p in await _partes_de(self._partes, obra_id)}
        partes = [
            {"clave": c, "nombre": nombres.get(c, c), **_dto(valuar(ls))}
            for c, ls in por_parte.items()
        ]
        partes.sort(key=lambda p: list(nombres).index(p["clave"]) if p["clave"] in nombres else 10**6)
        return {
            "obra_id": obra_id,
            "obra": _dto(valuar([x for ls in por_parte.values() for x in ls])),
            "partes": partes,
        }


@dataclass(frozen=True, slots=True)
class ComandoRedisenarParte:
    obra_id: UUID
    clave: str
    ensamble_id: UUID
    factor: Decimal
    usuario_id: UUID
    rol: Rol
    aplicar: bool = False


class RedisenarParte:
    """`POST /obras/{id}/partes/rediseno`: la parte se valúa **por ensamble**, total o en parte.

    Se explota el ensamble con su factor y, para cada renglón de la parte cuyo concepto está en el
    ensamble, la cantidad pasa a ser la **estimada** (`modo_cantidad = estimada`). Lo que el
    ensamble no cubre se queda por PU: queda **mixto**, y se reporta en porcentaje. Sin `aplicar`
    solo propone. Si la parte ya estaba validada vuelve a cuantificarse; asignada no se toca.
    """

    def __init__(
        self,
        *,
        partes: RepositorioPartes,
        obras: RepositorioObras,
        explotar: ExplotarEnsamble,
        uow: UnidadDeTrabajo,
        eventos: PublicadorEventos,
    ) -> None:
        self._partes = partes
        self._obras = obras
        self._explotar = explotar
        self._uow = uow
        self._eventos = eventos

    async def ejecutar(self, cmd: ComandoRedisenarParte) -> dict[str, Any]:
        if await self._obras.obtener(cmd.obra_id) is None:
            raise ObraNoEncontrada(f"Obra {cmd.obra_id} no encontrada en tu alcance.")
        if cmd.factor <= 0:
            raise ErrorDeModificacion("El factor del ensamble va por encima de cero.")
        filas = [f for f in await self._partes.lineas_de_valuacion(cmd.obra_id) if f["clave"] == cmd.clave]
        if not filas:
            raise ParteNoEncontrada(f"La obra no tiene la parte {cmd.clave}.")
        estado = (await self._partes.estados_de_obra(cmd.obra_id)).get(
            cmd.clave, EstadoDeParte.CUANTIFICANDO.value
        )
        if cmd.aplicar and estado == EstadoDeParte.ASIGNADA.value:
            raise ErrorDeParte(
                "La parte ya está asignada: lo asignado está congelado y cambiarlo es control de cambio."
            )

        explosion = await self._explotar.ejecutar(cmd.ensamble_id, factor=cmd.factor)
        estimadas: dict[str, Decimal] = defaultdict(Decimal)
        for linea in explosion.lineas:
            if str(linea.tipo_hijo) == "concepto":
                estimadas[linea.referencia] += linea.cantidad
        en_parte = {f["concepto_clave"] for f in filas if f["concepto_clave"]}

        propuestas = []
        for f in filas:
            clave_concepto = f["concepto_clave"]
            if clave_concepto not in estimadas:
                continue
            actual = Decimal(str(f["cant_base"]))
            nueva = estimadas[clave_concepto].quantize(Decimal("0.000001"))
            precio = Decimal(str(f["precio_unitario"] or 0))
            propuestas.append(
                {
                    "actividad_id": f["id"],
                    "concepto_clave": clave_concepto,
                    "descripcion": f["descripcion"],
                    "cantidad_actual": actual,
                    "cantidad_estimada": nueva,
                    "importe_actual": actual * precio,
                    "importe_estimado": nueva * precio,
                    "ya_estimada": f["modo_cantidad"] == "estimada" and actual == nueva,
                }
            )

        revisar = False
        if cmd.aplicar:
            async with self._uow:
                for p in propuestas:
                    delta = p["cantidad_estimada"] - p["cantidad_actual"]
                    if delta != 0:
                        m = modificar(
                            TipoDeModificacion.CAMBIO,
                            cantidad_actual=p["cantidad_actual"],
                            delta=delta,
                        )
                        await self._partes.aplicar_modificacion(
                            p["actividad_id"],
                            tipo=TipoDeModificacion.CAMBIO.value,
                            cantidad=m.cantidad_despues,
                            cant_prototipo=m.cantidad_antes,
                            modo="estimada",
                        )
                        await self._partes.registrar_modificacion(
                            obra_id=cmd.obra_id,
                            actividad_id=p["actividad_id"],
                            tipo=TipoDeModificacion.CAMBIO.value,
                            cantidad_antes=m.cantidad_antes,
                            delta=m.delta,
                            cantidad_despues=m.cantidad_despues,
                            nace_nueva=False,
                            nota=f"Rediseño a paramétrico: {explosion.clave} × {cmd.factor}",
                            usuario_id=cmd.usuario_id,
                            rol=cmd.rol.value,
                        )
                    else:  # misma cantidad: solo cambia de dónde sale
                        await self._partes.aplicar_modificacion(
                            p["actividad_id"],
                            tipo=TipoDeModificacion.CAMBIO.value,
                            cantidad=p["cantidad_estimada"],
                            cant_prototipo=p["cantidad_actual"],
                            modo="estimada",
                        )
                reabierta = bool(propuestas) and EstadoDeParte(estado) in _REABRE
                revisar = False
                if reabierta:
                    revisar = await _reabrir_parte(
                        self._partes, self._eventos, obra_id=cmd.obra_id, clave=cmd.clave,
                        usuario_id=cmd.usuario_id, rol=cmd.rol,
                        motivo=f"Rediseño a paramétrico: {explosion.clave} × {cmd.factor}",
                    )
                await self._uow.commit()
            if reabierta:
                await _avisar_reapertura(
                    self._eventos, obra_id=cmd.obra_id, clave=cmd.clave,
                    usuario_id=cmd.usuario_id, revisar=revisar,
                )

        # Cómo queda la parte (o cómo quedaría) valuada.
        lineas = []
        cambiadas = {p["actividad_id"]: p for p in propuestas}
        for f in filas:
            p = cambiadas.get(f["id"])
            lineas.append(
                LineaValuada(
                    cantidad=p["cantidad_estimada"] if p else Decimal(str(f["cant_base"])),
                    precio=Decimal(str(f["precio_unitario"] or 0)),
                    estimada=True if p else f["modo_cantidad"] == "estimada",
                    cant_estimada=None,
                )
            )
        despues = valuar(lineas)
        return {
            "clave": cmd.clave,
            "ensamble_clave": explosion.clave,
            "factor": cmd.factor,
            "aplicado": cmd.aplicar,
            "propuestas": propuestas,
            "sin_renglon_en_la_parte": sorted(set(estimadas) - en_parte),
            "conservan_pu": len(filas) - len(propuestas),
            "forma_despues": despues.forma.value,
            "porcentaje_parametrico_despues": despues.porcentaje_parametrico,
        }

