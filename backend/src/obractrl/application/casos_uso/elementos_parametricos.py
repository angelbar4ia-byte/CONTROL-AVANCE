"""Elementos paramétricos del catálogo (D-602, D-604): alta, cambio, baja y la receta de cada uno.

Quién los define (Control de obra y Costos) lo decide la API. La receta no se guarda: se calcula al leer con
`domain.cuantificacion.elementos_parametricos`, así un cambio de constantes llega a todos.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.cuantificar import MedicionNoEncontrada
from obractrl.application.puertos.repositorios import UnidadDeTrabajo
from obractrl.domain.cuantificacion.elementos_parametricos import (
    ErrorDeElementoParametrico,
    normalizar_parametros,
    receta,
)

__all__ = ["ComandoCrearElementoParametrico", "ElementoParametricoNoEncontrado", "GestionarElementosParametricos"]


class ElementoParametricoNoEncontrado(MedicionNoEncontrada):
    """El elemento no existe o está fuera de tu alcance."""


@dataclass(frozen=True, slots=True)
class ComandoCrearElementoParametrico:
    clave: str
    nombre: str
    tipo: str
    parametros: dict[str, Any]
    autor_id: UUID


def _texto(valor: str, que: str, maximo: int) -> str:
    limpio = " ".join(valor.split())
    if not limpio:
        raise ErrorDeElementoParametrico(f"El elemento necesita {que}.")
    if len(limpio) > maximo:
        raise ErrorDeElementoParametrico(f"{que.capitalize()} no puede pasar de {maximo} caracteres.")
    return limpio


def _con_receta(fila: dict[str, Any]) -> dict[str, Any]:
    parametros = normalizar_parametros(fila["tipo"], dict(fila["parametros"] or {}))
    return {**fila, "parametros": parametros, "receta": receta(fila["tipo"], parametros)}


class GestionarElementosParametricos:
    def __init__(self, *, elementos: Any, uow: UnidadDeTrabajo) -> None:
        self._elementos = elementos
        self._uow = uow

    async def listar(self) -> list[dict[str, Any]]:
        return [_con_receta(f) for f in await self._elementos.listar()]

    async def crear(self, cmd: ComandoCrearElementoParametrico) -> UUID:
        clave = _texto(cmd.clave, "una clave", 20).upper()
        nombre = _texto(cmd.nombre, "un nombre", 80)
        parametros = normalizar_parametros(cmd.tipo, cmd.parametros)
        if await self._elementos.clave_en_uso(clave):
            raise ErrorDeElementoParametrico(f"Ya existe un elemento con la clave {clave}.")
        async with self._uow:
            nuevo: UUID = await self._elementos.crear(
                clave=clave, nombre=nombre, tipo=cmd.tipo, parametros=parametros, autor_id=cmd.autor_id
            )
            await self._uow.commit()
        return nuevo

    async def actualizar(
        self, elemento_id: UUID, *, clave: str | None, nombre: str | None, parametros: dict[str, Any] | None
    ) -> None:
        actual = await self._elementos.obtener(elemento_id)
        if actual is None:
            raise ElementoParametricoNoEncontrado(f"El elemento {elemento_id} no existe o está fuera de tu alcance.")
        nueva_clave = _texto(clave, "una clave", 20).upper() if clave is not None else actual["clave"]
        nuevo_nombre = _texto(nombre, "un nombre", 80) if nombre is not None else actual["nombre"]
        # Los parámetros que no vienen se conservan: se cambia un número sin repetir todo el armado.
        nuevos = normalizar_parametros(actual["tipo"], {**(actual["parametros"] or {}), **(parametros or {})})
        if await self._elementos.clave_en_uso(nueva_clave, salvo=elemento_id):
            raise ErrorDeElementoParametrico(f"Ya existe un elemento con la clave {nueva_clave}.")
        async with self._uow:
            await self._elementos.actualizar(elemento_id, clave=nueva_clave, nombre=nuevo_nombre, parametros=nuevos)
            await self._uow.commit()

    async def eliminar(self, elemento_id: UUID) -> None:
        if await self._elementos.obtener(elemento_id) is None:
            raise ElementoParametricoNoEncontrado(f"El elemento {elemento_id} no existe o está fuera de tu alcance.")
        async with self._uow:
            await self._elementos.eliminar(elemento_id)
            await self._uow.commit()
