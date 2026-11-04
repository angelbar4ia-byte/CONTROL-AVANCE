"""Caso de uso: armar el árbol de una obra desde el cuantificador (entrega 7).

El árbol es nivel → etapa → partida (la actividad de la obra). Aquí se crean niveles y etapas (catálogo de la
organización), se agregan partidas con un concepto que ya existe, se mueven de etapa y se cambia la unidad de un
concepto. Quién: Control de obra y Costos.

Dos cuidados que son de negocio, no de pantalla:

- **Cambiar la unidad cambia el tipo de medición** (m² → área, ml → lineal, pza → conteo…). Si el concepto ya
  está midiendo con una medida que el tipo nuevo no admite (metros lineales de un concepto que pasa a m²), se
  rechaza: antes hay que quitar o reemplazar esos trazos. El cambio es **del catálogo**: vale para todas las obras.
- Una partida **no se agrega ni se mueve en una parte ya asignada** (eso es control de cambio), y no se mueve una
  que ya tiene avance ejecutado.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.calcular_cpu import ConceptoNoEncontrado
from obractrl.application.casos_uso.cuantificar import ErrorDeCuantificacion
from obractrl.application.casos_uso.generar_obra_desde_prototipo import ObraNoEncontrada
from obractrl.application.casos_uso.gestionar_programacion import ActividadNoProgramable
from obractrl.application.puertos.repositorios import UnidadDeTrabajo
from obractrl.domain.catalogos.reglas import ErrorDeCatalogo
from obractrl.domain.cuantificacion.cambio_de_unidad import cruza_de_tipo
from obractrl.domain.cuantificacion.unidades import medidas_que_caben, tipo_de_unidad
from obractrl.domain.partes.estado import ErrorDeParte, EstadoDeParte

__all__ = ["ArmarArbol", "ComandoAgregarPartida", "UnidadCambiada"]


@dataclass(frozen=True, slots=True)
class ComandoAgregarPartida:
    obra_id: UUID
    concepto_id: UUID
    etapa_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class UnidadCambiada:
    concepto_id: UUID
    unidad_anterior: str | None
    unidad_nueva: str
    tipo_anterior: str | None
    tipo_nuevo: str | None


def _clave(texto: str, que: str) -> str:
    limpia = " ".join(texto.split()).upper()
    if not limpia:
        raise ErrorDeCatalogo(f"El {que} necesita una clave.")
    return limpia


def _parte(etapa_id: UUID | None) -> str:
    return f"etapa:{etapa_id}" if etapa_id else "sin_etapa:-"


class ArmarArbol:
    def __init__(
        self, *, arbol: Any, partes: Any, obras: Any, uow: UnidadDeTrabajo
    ) -> None:
        self._arbol = arbol
        self._partes = partes
        self._obras = obras
        self._uow = uow

    async def crear_nivel(self, *, clave: str, descripcion: str) -> UUID:
        clave = _clave(clave, "nivel")
        if not descripcion.strip():
            raise ErrorDeCatalogo("El nivel necesita una descripción.")
        if await self._arbol.nivel_por_clave(clave) is not None:
            raise ErrorDeCatalogo(f"Ya existe un nivel con la clave {clave}.")
        async with self._uow:
            nivel_id: UUID = await self._arbol.crear_nivel(
                clave=clave, descripcion=" ".join(descripcion.split())
            )
            await self._uow.commit()
        return nivel_id

    async def crear_etapa(self, *, nivel_id: UUID, clave: str, descripcion: str) -> UUID:
        clave = _clave(clave, "etapa")
        if not descripcion.strip():
            raise ErrorDeCatalogo("La etapa necesita una descripción.")
        if not await self._arbol.nivel_existe(nivel_id):
            raise ErrorDeCatalogo("El nivel no existe o está fuera de tu alcance.")
        if await self._arbol.etapa_por_clave(clave) is not None:
            raise ErrorDeCatalogo(f"Ya existe una etapa con la clave {clave}.")
        async with self._uow:
            etapa_id: UUID = await self._arbol.crear_etapa(
                nivel_id=nivel_id, clave=clave, descripcion=" ".join(descripcion.split())
            )
            await self._uow.commit()
        return etapa_id

    async def cambiar_unidad(self, concepto_id: UUID, unidad_id: UUID) -> UnidadCambiada:
        concepto = await self._arbol.concepto(concepto_id)
        if concepto is None:
            raise ConceptoNoEncontrado(
                f"Concepto {concepto_id} no encontrado en tu alcance."
            )
        unidad = await self._arbol.unidad(unidad_id)
        if unidad is None:
            raise ErrorDeCatalogo("La unidad no existe o está fuera de tu alcance.")
        anterior = concepto["unidad_clave"]
        tipo_anterior = tipo_de_unidad(anterior)
        tipo_nuevo = tipo_de_unidad(unidad["clave"])
        if concepto["unidad_id"] != unidad_id and cruza_de_tipo(tipo_anterior, tipo_nuevo) and tipo_nuevo is not None:
            raise ErrorDeCatalogo(
                "Cambiar a una unidad de otro tipo de medición (pieza, longitud, área) pide una equivalencia y crea una "
                "versión del concepto: propón el cambio de unidad."
            )
        if concepto["unidad_id"] != unidad_id:
            caben = medidas_que_caben(tipo_nuevo)
            if caben is not None:
                ajenas = sorted(
                    m
                    for m in await self._arbol.medidas_vigentes_del_concepto(concepto_id)
                    if m not in caben
                )
                if ajenas:
                    raise ErrorDeCuantificacion(
                        f"{concepto['clave']} ya se mide con {', '.join(ajenas)} y la unidad {unidad['clave']} no lo admite: "
                        "quita o reemplaza esos trazos antes de cambiarla."
                    )
            async with self._uow:
                await self._arbol.poner_unidad(concepto_id, unidad_id)
                await self._uow.commit()
        return UnidadCambiada(
            concepto_id, anterior, unidad["clave"], tipo_anterior, tipo_nuevo
        )

    async def agregar_partida(self, cmd: ComandoAgregarPartida) -> dict[str, Any]:
        if await self._obras.obtener(cmd.obra_id) is None:
            raise ObraNoEncontrada(f"Obra {cmd.obra_id} no encontrada en tu alcance.")
        concepto = await self._arbol.concepto(cmd.concepto_id)
        if concepto is None:
            raise ConceptoNoEncontrado(
                f"Concepto {cmd.concepto_id} no encontrado en tu alcance."
            )
        nivel_id: UUID | None = None
        if cmd.etapa_id is not None:
            etapa = await self._arbol.etapa(cmd.etapa_id)
            if etapa is None:
                raise ErrorDeCatalogo("La etapa no existe o está fuera de tu alcance.")
            nivel_id = etapa["nivel_id"]
        if await self._arbol.partida_repetida(cmd.obra_id, cmd.concepto_id, cmd.etapa_id):
            raise ErrorDeCatalogo(f"{concepto['clave']} ya es una partida de esa etapa.")
        clave_parte = _parte(cmd.etapa_id)
        estado = (await self._partes.estados_de_obra(cmd.obra_id)).get(
            clave_parte, EstadoDeParte.CUANTIFICANDO.value
        )
        if estado == EstadoDeParte.ASIGNADA.value:
            raise ErrorDeParte(
                "La parte ya está asignada: agregarle una partida es control de cambio."
            )
        precio, _destajo = await self._arbol.precio_vigente(cmd.concepto_id)
        async with self._uow:
            actividad_id = await self._partes.crear_actividad_nueva(
                {
                    "obra_id": cmd.obra_id,
                    "descripcion": concepto["descripcion"],
                    "cantidad": Decimal(0),
                    "precio_unitario": precio,
                    "concepto_id": cmd.concepto_id,
                    "etapa_id": cmd.etapa_id,
                    "nivel_id": nivel_id,
                    "tipo": "adicional",
                }
            )
            await self._uow.commit()
        return {
            "actividad_id": actividad_id,
            "concepto_id": cmd.concepto_id,
            "clave": concepto["clave"],
            "parte": clave_parte,
        }

    async def mover_partida(
        self, actividad_id: UUID, etapa_id: UUID | None
    ) -> dict[str, Any]:
        actividad = await self._arbol.actividad(actividad_id)
        if actividad is None:
            raise ActividadNoProgramable(
                f"Actividad {actividad_id} no encontrada en tu alcance."
            )
        if actividad["cant_ejecutada"] and Decimal(str(actividad["cant_ejecutada"])) > 0:
            raise ErrorDeParte(
                "La partida ya tiene avance ejecutado: no se mueve de etapa."
            )
        nivel_id: UUID | None = None
        if etapa_id is not None:
            etapa = await self._arbol.etapa(etapa_id)
            if etapa is None:
                raise ErrorDeCatalogo("La etapa no existe o está fuera de tu alcance.")
            nivel_id = etapa["nivel_id"]
        estados = await self._partes.estados_de_obra(actividad["obra_id"])
        for clave in {_parte(actividad["etapa_id"]), _parte(etapa_id)}:
            if estados.get(clave) == EstadoDeParte.ASIGNADA.value:
                raise ErrorDeParte(
                    "Una de las dos partes ya está asignada: moverla es control de cambio."
                )
        async with self._uow:
            await self._arbol.mover_actividad(
                actividad_id, nivel_id=nivel_id, etapa_id=etapa_id
            )
            await self._uow.commit()
        return {"actividad_id": actividad_id, "etapa_id": etapa_id, "nivel_id": nivel_id}

    async def quitar_partida(self, actividad_id: UUID) -> dict[str, Any]:
        """Borra una partida que todavía no se usa: sin avance, sin trazos, sin estimaciones, en una parte sin asignar."""
        actividad = await self._arbol.actividad(actividad_id)
        if actividad is None:
            raise ActividadNoProgramable(
                f"Actividad {actividad_id} no encontrada en tu alcance."
            )
        if actividad["cant_ejecutada"] and Decimal(str(actividad["cant_ejecutada"])) > 0:
            raise ErrorDeParte("La partida ya tiene avance ejecutado: no se quita.")
        estados = await self._partes.estados_de_obra(actividad["obra_id"])
        if estados.get(_parte(actividad["etapa_id"])) == EstadoDeParte.ASIGNADA.value:
            raise ErrorDeParte(
                "La parte ya está asignada: quitarle una partida es control de cambio."
            )
        motivo = await self._arbol.motivo_para_no_quitar(actividad_id)
        if motivo is not None:
            raise ErrorDeParte(motivo)
        async with self._uow:
            await self._arbol.quitar_actividad(actividad_id)
            await self._uow.commit()
        return {"actividad_id": actividad_id}
