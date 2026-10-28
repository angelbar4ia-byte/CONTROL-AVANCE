"""Casos de uso: propuestas por revisar (Fase 2 y 3, migración 0092).

Una herramienta automática —el conteo por plantilla, el takeoff— encuentra trazos y los **propone**.
Una propuesta es un trazo sin enlaces: **nunca cuenta como medida** hasta que una persona la acepta
(un trigger de la base lo garantiza). Aceptarla crea el enlace al concepto que se propuso y recalcula;
rechazarla la borra. Así se conserva la trazabilidad: lo que sumó, lo revisó alguien.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.cuantificar import (
    ErrorDeCuantificacion,
    PlanoNoEncontrado,
    ResultadoDeRecalculo,
    _avisar_reaperturas,
    _recalcular_nodo,
)
from obractrl.application.puertos.repositorios import UnidadDeTrabajo
from obractrl.domain.cuantificacion.reglas import EnlaceCuantificacion
from obractrl.domain.shared.diccionario import (
    MedidaCuantificacion,
    Rol,
    TipoNodoCuantificacion,
)

__all__ = [
    "AceptarPropuestas",
    "ComandoProponerTrazos",
    "ProponerTrazos",
    "PropuestasAceptadas",
    "PropuestasCreadas",
    "RechazarPropuestas",
]

ORIGENES = frozenset({"conteo_auto", "takeoff"})
MAXIMO_POR_LOTE = 2000

# Qué medidas admite cada geometría: un punto se cuenta, un área da área o perímetro, una línea su longitud.
_MEDIDAS_POR_GEOMETRIA: dict[str, frozenset[str]] = {
    "ST_Point": frozenset({"conteo"}),
    "ST_Polygon": frozenset({"area", "perimetro"}),
    "ST_LineString": frozenset({"longitud"}),
}


@dataclass(frozen=True, slots=True)
class ComandoProponerTrazos:
    plano_id: UUID
    actividad_id: UUID
    medida: str
    origen: str
    geometrias_wkt: tuple[str, ...]
    autor_id: UUID
    rol: Rol
    confianzas: tuple[Decimal, ...] = ()
    """Una por geometría (0 a 1), o vacío."""


@dataclass(frozen=True, slots=True)
class PropuestasCreadas:
    trazo_ids: tuple[UUID, ...]
    descartadas: int = 0
    """Geometrías que no se pudieron medir (inválidas): una herramienta automática las genera de vez en cuando y
    no por eso se pierde todo el lote."""


@dataclass(frozen=True, slots=True)
class PropuestasAceptadas:
    trazo_ids: tuple[UUID, ...]
    recalculos: tuple[ResultadoDeRecalculo, ...] = field(default_factory=tuple)


class ProponerTrazos:
    def __init__(
        self, *, trazos: Any, planos: Any, actividades: Any, uow: UnidadDeTrabajo
    ) -> None:
        self._trazos = trazos
        self._planos = planos
        self._actividades = actividades
        self._uow = uow

    async def ejecutar(self, cmd: ComandoProponerTrazos) -> PropuestasCreadas:
        if cmd.origen not in ORIGENES:
            raise ErrorDeCuantificacion(
                f"Origen de propuesta desconocido: {cmd.origen!r}."
            )
        if not cmd.geometrias_wkt:
            raise ErrorDeCuantificacion("No hay nada que proponer.")
        if len(cmd.geometrias_wkt) > MAXIMO_POR_LOTE:
            raise ErrorDeCuantificacion(
                f"Demasiadas propuestas de una vez (máximo {MAXIMO_POR_LOTE})."
            )
        if cmd.confianzas and len(cmd.confianzas) != len(cmd.geometrias_wkt):
            raise ErrorDeCuantificacion("Una confianza por propuesta, o ninguna.")
        plano = await self._planos.obtener(cmd.plano_id)
        if plano is None:
            raise PlanoNoEncontrado(
                f"El plano {cmd.plano_id} no existe o está fuera de tu alcance."
            )
        actividad = await self._actividades.obtener(cmd.actividad_id)
        if actividad is None or actividad["obra_id"] != plano["obra_id"]:
            raise ErrorDeCuantificacion(
                "La actividad no existe o no es de la obra de este plano."
            )

        validas: list[tuple[str, Decimal | None]] = []
        for i, wkt in enumerate(cmd.geometrias_wkt):
            if await self._trazos.motivo_de_geometria_invalida(wkt) is not None:
                continue  # se descarta y se cuenta: no se pierde el lote por una geometría mala
            tipo = await self._trazos.tipo_de_geometria(wkt)
            if cmd.medida not in _MEDIDAS_POR_GEOMETRIA.get(tipo, frozenset()):
                raise ErrorDeCuantificacion(
                    f"La medida {cmd.medida!r} no va con una geometría {tipo}."
                )
            validas.append((wkt, cmd.confianzas[i] if cmd.confianzas else None))
        if not validas:
            raise ErrorDeCuantificacion(
                "Ninguna de las geometrías propuestas se puede medir."
            )

        async with self._uow:
            ids = [
                await self._trazos.crear_propuesta(
                    plano_id=cmd.plano_id,
                    version_plano=int(plano["version"]),
                    geometria_wkt=wkt,
                    autor_id=cmd.autor_id,
                    origen=cmd.origen,
                    actividad_id=cmd.actividad_id,
                    medida=cmd.medida,
                    confianza=confianza,
                )
                for wkt, confianza in validas
            ]
            await self._uow.commit()
        return PropuestasCreadas(
            trazo_ids=tuple(ids), descartadas=len(cmd.geometrias_wkt) - len(validas)
        )


class AceptarPropuestas:
    """Cada propuesta aceptada se vuelve un trazo con su enlace vigente (factor 1) al concepto propuesto."""

    def __init__(
        self,
        *,
        trazos: Any,
        enlaces: Any,
        actividades: Any,
        prototipo_nodos: Any,
        desviaciones: Any,
        uow: UnidadDeTrabajo,
        eventos: Any = None,
        matrices: Any = None,
    ) -> None:
        self._trazos = trazos
        self._enlaces = enlaces
        self._actividades = actividades
        self._prototipo_nodos = prototipo_nodos
        self._desviaciones = desviaciones
        self._uow = uow
        self._eventos = eventos
        self._matrices = matrices

    async def ejecutar(
        self,
        plano_id: UUID,
        trazo_ids: list[UUID],
        *,
        usuario_id: UUID,
        detectada_en: datetime,
    ) -> PropuestasAceptadas:
        pendientes = await self._trazos.propuestas(plano_id, trazo_ids)
        if not pendientes:
            raise ErrorDeCuantificacion("No hay propuestas pendientes entre esos trazos.")
        async with self._uow:
            nodos: dict[UUID, None] = {}
            for p in pendientes:
                await self._trazos.aceptar_propuesta(p["id"])
                validado = EnlaceCuantificacion(
                    trazo_id=str(p["id"]),
                    actividad_id=str(p["actividad_id"]),
                    prototipo_nodo_id=None,
                    medida=MedidaCuantificacion(str(p["medida"])),
                    factor=Decimal(1),
                    matriz_concepto_id=None,
                )
                await self._enlaces.crear(
                    trazo_id=p["id"],
                    actividad_id=p["actividad_id"],
                    prototipo_nodo_id=None,
                    matriz_concepto_id=None,
                    medida=validado.medida.value,
                    factor=validado.factor,
                )
                nodos[p["actividad_id"]] = None
            recalculos = tuple(
                [
                    await _recalcular_nodo(
                        tipo_nodo=TipoNodoCuantificacion.ACTIVIDAD,
                        actividad_id=actividad_id,
                        prototipo_nodo_id=None,
                        matriz_concepto_id=None,
                        enlaces=self._enlaces,
                        actividades=self._actividades,
                        prototipo_nodos=self._prototipo_nodos,
                        desviaciones=self._desviaciones,
                        detectada_en=detectada_en,
                        matrices=self._matrices,
                    )
                    for actividad_id in nodos
                ]
            )
            await self._uow.commit()
        await _avisar_reaperturas(self._eventos, recalculos, usuario_id)
        return PropuestasAceptadas(
            trazo_ids=tuple(p["id"] for p in pendientes), recalculos=recalculos
        )


class RechazarPropuestas:
    def __init__(self, *, trazos: Any, uow: UnidadDeTrabajo) -> None:
        self._trazos = trazos
        self._uow = uow

    async def ejecutar(self, plano_id: UUID, trazo_ids: list[UUID]) -> int:
        pendientes = await self._trazos.propuestas(plano_id, trazo_ids)
        if not pendientes:
            raise ErrorDeCuantificacion("No hay propuestas pendientes entre esos trazos.")
        async with self._uow:
            for p in pendientes:
                await self._trazos.eliminar(p["id"])
            await self._uow.commit()
        return len(pendientes)
