"""Elementos de obra con peso (K1, varilla 3/8): migración 0089.

Un elemento tiene un nombre, el tipo de medición que lo cuenta (por pieza, por metro o por m²) y su
peso en kg por esa unidad. Una medición puede tener un elemento; al asignarla a un concepto en kg o
ton con el peso, el factor del enlace es el del elemento. **Cambiar el peso rehace** las asignaciones
que lo usan —sus enlaces quedan como evidencia y los nuevos llevan el factor al día— y recalcula los
conceptos. Quién lo cambia (Control de obra y Costos) lo decide la API.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from obractrl.application.casos_uso.cuantificar import (
    MedicionNoEncontrada,
    _avisar_reaperturas,
    _recalcular_nodo,
)
from obractrl.application.casos_uso.mediciones import (
    NodoActividad,
    rehacer_factores_por_peso,
)
from obractrl.application.eventos import PublicadorEventos
from obractrl.application.puertos.cuantificacion import (
    RepositorioElementos,
    RepositorioEnlacesCuantificacion,
    RepositorioMatrices,
    RepositorioMediciones,
)
from obractrl.application.puertos.repositorios import (
    RepositorioActividades,
    RepositorioDesviaciones,
    RepositorioPrototipoNodo,
    UnidadDeTrabajo,
)
from obractrl.domain.cuantificacion.medicion import TIPOS_DE_MEDICION
from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion
from obractrl.domain.shared.diccionario import TipoNodoCuantificacion

__all__ = ["ComandoCrearElemento", "GestionarElementos"]


def _nombre(nombre: str) -> str:
    limpio = " ".join(nombre.split())
    if not limpio:
        raise ErrorDeCuantificacion("El elemento necesita un nombre.")
    if len(limpio) > 80:
        raise ErrorDeCuantificacion("El nombre del elemento no puede pasar de 80 caracteres.")
    return limpio


def _peso(peso: Decimal) -> Decimal:
    if peso <= 0:
        raise ErrorDeCuantificacion("El peso debe ser mayor que cero.")
    return peso


@dataclass(frozen=True, slots=True)
class ComandoCrearElemento:
    nombre: str
    tipo: str
    peso_kg: Decimal
    autor_id: UUID


class GestionarElementos:
    def __init__(
        self,
        *,
        elementos: RepositorioElementos,
        mediciones: RepositorioMediciones,
        enlaces: RepositorioEnlacesCuantificacion,
        actividades: RepositorioActividades,
        prototipo_nodos: RepositorioPrototipoNodo,
        desviaciones: RepositorioDesviaciones,
        uow: UnidadDeTrabajo,
        eventos: PublicadorEventos | None = None,
        matrices: RepositorioMatrices | None = None,
    ) -> None:
        self._elementos = elementos
        self._mediciones = mediciones
        self._enlaces = enlaces
        self._actividades = actividades
        self._prototipo_nodos = prototipo_nodos
        self._desviaciones = desviaciones
        self._uow = uow
        self._eventos = eventos
        self._matrices = matrices

    async def listar(self) -> list[dict]:
        return await self._elementos.listar()

    async def crear(self, cmd: ComandoCrearElemento) -> UUID:
        nombre = _nombre(cmd.nombre)
        if cmd.tipo not in TIPOS_DE_MEDICION:
            raise ErrorDeCuantificacion("El tipo de un elemento es área, lineal o conteo.")
        peso = _peso(cmd.peso_kg)
        if await self._elementos.existe_nombre(nombre):
            raise ErrorDeCuantificacion(f"Ya hay un elemento llamado «{nombre}».")
        async with self._uow:
            elemento_id = await self._elementos.crear(nombre=nombre, tipo=cmd.tipo, peso_kg=peso, autor_id=cmd.autor_id)
            await self._uow.commit()
        return elemento_id

    async def actualizar(
        self,
        elemento_id: UUID,
        *,
        nombre: str | None,
        peso_kg: Decimal | None,
        usuario_id: UUID,
        detectada_en: datetime,
    ) -> tuple:
        """Cambia el nombre o el peso. Un peso nuevo rehace las asignaciones por peso y recalcula."""
        elemento = await self._elementos.obtener(elemento_id)
        if elemento is None:
            raise MedicionNoEncontrada(f"El elemento {elemento_id} no existe o está fuera de tu alcance.")
        nuevo_nombre = _nombre(nombre) if nombre is not None else None
        nuevo_peso = _peso(peso_kg) if peso_kg is not None else None
        if nuevo_nombre is not None and await self._elementos.existe_nombre(nuevo_nombre, excepto=elemento_id):
            raise ErrorDeCuantificacion(f"Ya hay un elemento llamado «{nuevo_nombre}».")
        tocados: set[NodoActividad] = set()
        async with self._uow:
            await self._elementos.actualizar(elemento_id, nombre=nuevo_nombre, peso_kg=nuevo_peso)
            if nuevo_peso is not None and nuevo_peso != Decimal(str(elemento["peso_kg"])):
                tocados = await rehacer_factores_por_peso(
                    asignaciones=await self._mediciones.asignaciones_con_peso(elemento_id),
                    peso_kg=nuevo_peso,
                    mediciones=self._mediciones,
                    enlaces=self._enlaces,
                )
            recalculos = tuple(
                [
                    await _recalcular_nodo(
                        tipo_nodo=TipoNodoCuantificacion.ACTIVIDAD,
                        actividad_id=actividad_id,
                        prototipo_nodo_id=None,
                        matriz_concepto_id=matriz_id,
                        enlaces=self._enlaces,
                        actividades=self._actividades,
                        prototipo_nodos=self._prototipo_nodos,
                        desviaciones=self._desviaciones,
                        detectada_en=detectada_en,
                        matrices=self._matrices,
                    )
                    for actividad_id, matriz_id in tocados
                ]
            )
            await self._uow.commit()
        await _avisar_reaperturas(self._eventos, recalculos, usuario_id)
        return recalculos

    async def eliminar(self, elemento_id: UUID) -> None:
        """Se borra solo si ninguna asignación depende de su peso; las mediciones que lo tenían quedan sin elemento."""
        if await self._elementos.obtener(elemento_id) is None:
            raise MedicionNoEncontrada(f"El elemento {elemento_id} no existe o está fuera de tu alcance.")
        uso = await self._elementos.uso(elemento_id)
        if uso["asignaciones_con_peso"] > 0:
            raise ErrorDeCuantificacion(
                "Hay conceptos que reciben cantidad con el peso de este elemento: quita esas asignaciones primero."
            )
        async with self._uow:
            await self._elementos.eliminar(elemento_id)
            await self._uow.commit()
