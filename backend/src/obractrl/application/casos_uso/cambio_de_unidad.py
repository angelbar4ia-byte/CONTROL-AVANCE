"""Cambiar la unidad de un concepto a otro tipo de medición (D-623).

Dos pasos: se **propone** (con la equivalencia: la del destajo si se encuentra, o la que teclee quien propone) y se
**aprueba** (Control de obra o Costos; lo decide la API). Al aprobar nace una versión del concepto —un concepto nuevo
con la unidad nueva— con las cantidades de su matriz convertidas; los precios de los insumos no cambian.

- Las partidas **asignadas** o con avance se quedan en el concepto original: se bloquean.
- Las demás pasan a la versión nueva; sus trazos se marcan: el enlace viejo queda como evidencia y el nuevo mide con
  lo que cabe en la unidad nueva (un punto no cabe en m²: queda marcado sin enlace nuevo).
- Los nodos que esas partidas alimentan se recalculan.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.calcular_cpu import ConceptoNoEncontrado
from obractrl.application.casos_uso.cuantificar import (
    MedicionNoEncontrada,
    _recalcular_nodo,
)
from obractrl.application.puertos.repositorios import UnidadDeTrabajo
from obractrl.domain.catalogos.reglas import ErrorDeCatalogo
from obractrl.domain.cuantificacion.cambio_de_unidad import (
    TIPOS_CONVERTIBLES,
    cruza_de_tipo,
    divisor_de_cantidades,
    medida_para,
)
from obractrl.domain.cuantificacion.unidades import tipo_de_unidad
from obractrl.domain.partes.estado import ErrorDeParte, EstadoDeParte
from obractrl.domain.shared.diccionario import TipoNodoCuantificacion

__all__ = ["CambioDeUnidad", "CambioNoEncontrado", "ResultadoDelCambio"]


class CambioNoEncontrado(MedicionNoEncontrada):
    """La propuesta de cambio no existe o está fuera de tu alcance."""


@dataclass(frozen=True, slots=True)
class ResultadoDelCambio:
    concepto_nuevo_id: UUID
    clave_nueva: str
    partidas_movidas: int
    partidas_bloqueadas: int
    enlaces_rehechos: int
    enlaces_sin_medida: int


def _parte(etapa_id: UUID | None) -> str:
    return f"etapa:{etapa_id}" if etapa_id else "sin_etapa"


class CambioDeUnidad:
    def __init__(
        self, *, arbol: Any, cambios: Any, partes: Any, enlaces: Any, actividades: Any, prototipo_nodos: Any,
        desviaciones: Any, matrices: Any, uow: UnidadDeTrabajo,
    ) -> None:
        self._arbol = arbol
        self._cambios = cambios
        self._partes = partes
        self._enlaces = enlaces
        self._actividades = actividades
        self._prototipo_nodos = prototipo_nodos
        self._desviaciones = desviaciones
        self._matrices = matrices
        self._uow = uow

    async def proponer(self, concepto_id: UUID, unidad_id: UUID, equivalencia: Decimal | None, autor_id: UUID) -> dict[str, Any]:
        concepto = await self._arbol.concepto(concepto_id)
        if concepto is None:
            raise ConceptoNoEncontrado(f"Concepto {concepto_id} no encontrado en tu alcance.")
        unidad = await self._arbol.unidad(unidad_id)
        if unidad is None:
            raise ErrorDeCatalogo("La unidad no existe o está fuera de tu alcance.")
        anterior = tipo_de_unidad(concepto["unidad_clave"])
        nuevo = tipo_de_unidad(unidad["clave"])
        if concepto["unidad_id"] == unidad_id or not cruza_de_tipo(anterior, nuevo) or nuevo is None:
            raise ErrorDeCatalogo(
                "Ese cambio no cruza de tipo de medición: no pide equivalencia, se cambia la unidad directamente."
            )
        if nuevo not in TIPOS_CONVERTIBLES:
            divisor_de_cantidades(anterior, nuevo, Decimal(1))  # lanza el motivo
        if await self._cambios.pendiente_del_concepto(concepto_id) is not None:
            raise ErrorDeCatalogo("Este concepto ya tiene un cambio de unidad por resolver: apruébalo o recházalo.")
        origen = None
        if equivalencia is None:
            equivalencia = await self._cambios.equivalencia_del_destajo(concepto_id, unidad_id)
            origen = "destajo" if equivalencia is not None else None
        else:
            origen = "tecleada"
        async with self._uow:
            cambio_id = await self._cambios.crear(
                concepto_id=concepto_id, unidad_anterior_id=concepto["unidad_id"], unidad_nueva_id=unidad_id,
                tipo_anterior=anterior, tipo_nuevo=nuevo, equivalencia=equivalencia, origen=origen, autor_id=autor_id,
            )
            await self._uow.commit()
        return await self.ver(cambio_id)

    async def ver(self, cambio_id: UUID) -> dict[str, Any]:
        cambio = await self._cambios.obtener(cambio_id)
        if cambio is None:
            raise CambioNoEncontrado(f"El cambio {cambio_id} no existe o está fuera de tu alcance.")
        partidas = await self._cambios.partidas_del_concepto(cambio["concepto_id"])
        bloqueadas = await self._bloqueadas(partidas)
        return {**cambio, "partidas": len(partidas), "partidas_bloqueadas": len(bloqueadas)}

    async def teclear_equivalencia(self, cambio_id: UUID, equivalencia: Decimal) -> dict[str, Any]:
        cambio = await self._cambios.obtener(cambio_id)
        if cambio is None:
            raise CambioNoEncontrado(f"El cambio {cambio_id} no existe o está fuera de tu alcance.")
        if cambio["estado"] != "propuesto":
            raise ErrorDeCatalogo("Este cambio ya se resolvió.")
        divisor_de_cantidades(cambio["tipo_anterior"], cambio["tipo_nuevo"], equivalencia)  # valida
        async with self._uow:
            await self._cambios.teclear_equivalencia(cambio_id, equivalencia)
            await self._uow.commit()
        return await self.ver(cambio_id)

    async def rechazar(self, cambio_id: UUID, usuario_id: UUID) -> None:
        cambio = await self._cambios.obtener(cambio_id)
        if cambio is None:
            raise CambioNoEncontrado(f"El cambio {cambio_id} no existe o está fuera de tu alcance.")
        if cambio["estado"] != "propuesto":
            raise ErrorDeCatalogo("Este cambio ya se resolvió.")
        async with self._uow:
            await self._cambios.resolver(cambio_id, estado="rechazado", usuario_id=usuario_id, concepto_nuevo_id=None)
            await self._uow.commit()

    async def _bloqueadas(self, partidas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Las partidas que no se tocan: de una parte asignada, o con avance ejecutado."""
        estados: dict[UUID, dict[str, str]] = {}
        bloqueadas = []
        for p in partidas:
            if p["obra_id"] not in estados:
                estados[p["obra_id"]] = await self._partes.estados_de_obra(p["obra_id"])
            asignada = estados[p["obra_id"]].get(_parte(p["etapa_id"])) == EstadoDeParte.ASIGNADA.value
            if asignada or (p["cant_ejecutada"] and Decimal(str(p["cant_ejecutada"])) > 0):
                bloqueadas.append(p)
        return bloqueadas

    async def aprobar(self, cambio_id: UUID, usuario_id: UUID, *, detectada_en: Any) -> ResultadoDelCambio:
        cambio = await self._cambios.obtener(cambio_id)
        if cambio is None:
            raise CambioNoEncontrado(f"El cambio {cambio_id} no existe o está fuera de tu alcance.")
        if cambio["estado"] != "propuesto":
            raise ErrorDeCatalogo("Este cambio ya se resolvió.")
        if cambio["equivalencia"] is None:
            raise ErrorDeCatalogo(
                "Falta la equivalencia: no se encontró en el destajo del concepto. Escríbela (por ejemplo, 48 m² por pieza)."
            )
        divisor = divisor_de_cantidades(cambio["tipo_anterior"], cambio["tipo_nuevo"], Decimal(str(cambio["equivalencia"])))
        partidas = await self._cambios.partidas_del_concepto(cambio["concepto_id"])
        bloqueadas_ids = {p["id"] for p in await self._bloqueadas(partidas)}
        if partidas and len(bloqueadas_ids) == len(partidas):
            raise ErrorDeParte(
                "Todas las partidas de este concepto están asignadas o con avance: no se tocan. Cambiar su unidad es "
                "control de cambio."
            )
        unidad_nueva = await self._arbol.unidad(cambio["unidad_nueva_id"])
        if unidad_nueva is None:
            raise ErrorDeCatalogo("La unidad nueva ya no existe.")
        sufijo = "".join(c for c in unidad_nueva["clave"].upper() if c.isalnum()) or "U"
        movidas = rehechos = sin_medida = 0
        nodos: list[UUID] = []
        async with self._uow:
            nuevo = await self._cambios.clonar_concepto(cambio["concepto_id"], cambio["unidad_nueva_id"], sufijo, divisor)
            for p in partidas:
                if p["id"] in bloqueadas_ids:
                    continue
                await self._cambios.pasar_partida(p["id"], nuevo, divisor)
                movidas += 1
                nodos.append(p["id"])
                for e in await self._cambios.enlaces_a_rehacer(p["id"]):
                    medida = medida_para(cambio["tipo_nuevo"], e["geometria"], e["con_grosor"])
                    if medida is not None and medida == (e["medida"], Decimal(str(e["factor"]))):
                        continue  # ya mide lo que corresponde
                    await self._cambios.retirar_enlace(e["id"])
                    nuevo_enlace = None
                    if medida is not None:
                        nuevo_enlace = await self._cambios.enlazar(
                            trazo_id=e["trazo_id"], actividad_id=p["id"], medida=medida[0], factor=medida[1]
                        )
                        rehechos += 1
                    else:
                        sin_medida += 1
                    await self._cambios.marcar_enlace(
                        cambio_id=cambio_id, trazo_id=e["trazo_id"], viejo=e["id"], nuevo=nuevo_enlace,
                        medida_vieja=e["medida"], medida_nueva=medida[0] if medida else None,
                        nota="Cambio de unidad" if medida else "Cambio de unidad: este trazo no cabe en la unidad nueva",
                    )
            for actividad_id in nodos:
                await _recalcular_nodo(
                    tipo_nodo=TipoNodoCuantificacion.ACTIVIDAD, actividad_id=actividad_id, prototipo_nodo_id=None,
                    matriz_concepto_id=None, enlaces=self._enlaces, actividades=self._actividades,
                    prototipo_nodos=self._prototipo_nodos, desviaciones=self._desviaciones,
                    detectada_en=detectada_en, matrices=self._matrices,
                )
            await self._cambios.resolver(cambio_id, estado="aprobado", usuario_id=usuario_id, concepto_nuevo_id=nuevo)
            clave = (await self._arbol.concepto(nuevo))["clave"]
            await self._uow.commit()
        return ResultadoDelCambio(nuevo, clave, movidas, len(bloqueadas_ids), rehechos, sin_medida)

    async def marcas_del_trazo(self, trazo_id: UUID) -> list[dict[str, Any]]:
        return await self._cambios.marcas_del_trazo(trazo_id)
