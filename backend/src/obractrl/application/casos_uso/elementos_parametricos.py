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
    GEOMETRIA_DEL_TIPO,
    ErrorDeElementoParametrico,
    lados_por_defecto,
    normalizar_parametros,
    receta,
)

__all__ = ["ComandoCrearElementoParametrico", "ElementoParametricoNoEncontrado", "GestionarElementosParametricos"]


_NOMBRE_DE_GEOMETRIA = {"punto": "un punto", "linea": "una línea", "area": "un área"}


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

    async def poner_en_trazo(self, trazo_id: UUID, elemento_id: UUID | None, lados: int | None) -> None:
        """Marca un trazo como un elemento (o le quita la marca). Un punto es una pieza, una línea son metros, un área son m²."""
        geometria = await self._elementos.tipo_de_geometria(trazo_id)
        if geometria is None:
            raise ElementoParametricoNoEncontrado(f"El trazo {trazo_id} no existe o está fuera de tu alcance.")
        if elemento_id is None:
            lados = None
        else:
            elemento = await self._elementos.obtener(elemento_id)
            if elemento is None:
                raise ElementoParametricoNoEncontrado(f"El elemento {elemento_id} no existe o está fuera de tu alcance.")
            esperada = GEOMETRIA_DEL_TIPO[elemento["tipo"]]
            if geometria != esperada:
                raise ErrorDeElementoParametrico(
                    f"{elemento['clave']} se coloca con {_NOMBRE_DE_GEOMETRIA[esperada]}; este trazo es {_NOMBRE_DE_GEOMETRIA[geometria]}."
                )
            if lados is not None:
                disponibles = sorted(int(k) for k in receta(elemento["tipo"], elemento["parametros"] or {})["cimbra_m2"])
                if lados not in disponibles:
                    raise ErrorDeElementoParametrico(f"{elemento['clave']} lleva cimbra de {disponibles} lados, no de {lados}.")
        async with self._uow:
            await self._elementos.poner_en_trazo(trazo_id, elemento_id, lados)
            await self._uow.commit()

    async def totales_del_plano(self, plano_id: UUID) -> dict[str, Any]:
        """Lo que llevan en total los elementos colocados en un plano: la receta de una muestra × lo que aporta cada trazo."""
        elementos = {e["id"]: e for e in await self._elementos.listar()}
        por_elemento: dict[Any, dict[str, Any]] = {}
        trazos = await self._elementos.trazos_del_plano(plano_id)
        for trazo in trazos:
            e = elementos.get(trazo["elemento_parametrico_id"])
            if e is None:
                continue
            p = normalizar_parametros(e["tipo"], dict(e["parametros"] or {}))
            r = receta(e["tipo"], p)
            q = float(trazo["cantidad"])
            lados = trazo["lados_cimbra"] or lados_por_defecto(e["tipo"], p)
            lados_disponibles = r["cimbra_m2"]
            m2_por_muestra = lados_disponibles.get(lados, 0.0)
            t = por_elemento.setdefault(
                e["id"],
                {
                    "elemento_id": e["id"], "clave": e["clave"], "nombre": e["nombre"], "tipo": e["tipo"],
                    "unidad": r["unidad"], "colocados": 0, "cantidad": 0.0, "concreto_m3": 0.0, "acero_kg": 0.0,
                    "estribos_kg": 0.0, "alambre_kg": 0.0, "cimbra_m2": 0.0, "cimbra_por_lados": {},
                },
            )
            t["colocados"] += 1
            t["cantidad"] += q
            t["concreto_m3"] += r["concreto"] * q
            t["acero_kg"] += r["acero_kg"] * q
            t["estribos_kg"] += r["estribos_kg"] * q
            t["alambre_kg"] += r["alambre_kg"] * q
            t["cimbra_m2"] += m2_por_muestra * q
            t["cimbra_por_lados"][lados] = t["cimbra_por_lados"].get(lados, 0.0) + m2_por_muestra * q
        return {
            "totales": sorted(por_elemento.values(), key=lambda x: x["clave"]),
            "trazos": [
                {"trazo_id": t["id"], "elemento_id": t["elemento_parametrico_id"], "lados_cimbra": t["lados_cimbra"]}
                for t in trazos
            ],
        }
