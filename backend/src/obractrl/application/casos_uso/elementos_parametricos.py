"""Elementos paramétricos del catálogo (D-602, D-604): alta, cambio, baja y la receta de cada uno.

Quién los define (Control de obra y Costos) lo decide la API. La receta no se guarda: se calcula al leer con
`domain.cuantificacion.elementos_parametricos`, así un cambio de constantes llega a todos.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.cuantificar import MedicionNoEncontrada
from obractrl.application.casos_uso.tomas_de_elemento import (
    filas_de_toma,
    totales_de_trazos,
)
from obractrl.application.puertos.repositorios import UnidadDeTrabajo
from obractrl.domain.cuantificacion.clasificacion_de_elementos import (
    ElementoDuplicado,
    firma_de_elemento,
    validar_clasificacion,
    validar_posicion,
)
from obractrl.domain.cuantificacion.elementos_parametricos import (
    GEOMETRIA_DEL_TIPO,
    MATERIALES_DE_UN_ELEMENTO,
    ErrorDeElementoParametrico,
    normalizar_parametros,
    receta,
    toma_por_unidad,
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
    categoria: str | None = None
    subcategoria: str | None = None


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
    def __init__(self, *, elementos: Any, uow: UnidadDeTrabajo, sincronizador: Any | None = None) -> None:
        self._elementos = elementos
        self._uow = uow
        # Lo que un concepto toma de un elemento escribe la cantidad medida de su matriz (D-639).
        self._sincronizador = sincronizador

    async def _sincronizar_obras_con(self, elemento_id: UUID | None) -> None:
        if self._sincronizador is not None:
            await self._sincronizador.de_las_obras_con(elemento_id)

    async def sincronizar_obra(self, obra_id: UUID) -> None:
        """Rehace las cantidades que las matrices de la obra toman de los elementos colocados."""
        if self._sincronizador is None:
            return
        async with self._uow:
            await self._sincronizador.de_la_obra(obra_id)
            await self._uow.commit()

    async def listar(self) -> list[dict[str, Any]]:
        return [_con_receta(f) for f in await self._elementos.listar()]

    async def _sin_duplicado(self, firma: str, *, salvo: UUID | None = None) -> None:
        """M-29: un elemento igual a otro no se guarda; se usa el existente."""
        igual = await self._elementos.buscar_duplicado(firma, salvo=salvo)
        if igual is not None:
            raise ElementoDuplicado(igual["clave"], igual["id"])

    async def crear(self, cmd: ComandoCrearElementoParametrico) -> UUID:
        clave = _texto(cmd.clave, "una clave", 20).upper()
        nombre = _texto(cmd.nombre, "un nombre", 80)
        parametros = normalizar_parametros(cmd.tipo, cmd.parametros)
        categoria, subcategoria = validar_clasificacion(cmd.tipo, cmd.categoria, cmd.subcategoria)
        if await self._elementos.clave_en_uso(clave):
            raise ErrorDeElementoParametrico(f"Ya existe un elemento con la clave {clave}.")
        firma = firma_de_elemento(categoria, subcategoria, cmd.tipo, parametros)
        await self._sin_duplicado(firma)
        async with self._uow:
            nuevo: UUID = await self._elementos.crear(
                clave=clave, nombre=nombre, tipo=cmd.tipo, parametros=parametros, autor_id=cmd.autor_id,
                categoria=categoria, subcategoria=subcategoria, firma=firma,
            )
            await self._uow.commit()
        return nuevo

    async def validar_posicion(self, elemento_id: UUID, posicion: str) -> None:
        """La posición en que el muro coloca el elemento debe ser una de las que permite su subcategoría (M-32)."""
        elemento = await self._elemento(elemento_id)
        validar_posicion(elemento["categoria"], elemento["subcategoria"], posicion)

    async def actualizar(
        self,
        elemento_id: UUID,
        *,
        clave: str | None,
        nombre: str | None,
        parametros: dict[str, Any] | None,
        autor_id: UUID | None = None,
        categoria: str | None = None,
        subcategoria: str | None = None,
    ) -> UUID:
        """Cambia un elemento. Devuelve el id de la versión vigente (otro, si hubo que crear una versión nueva)."""
        actual = await self._elementos.obtener(elemento_id)
        if actual is None:
            raise ElementoParametricoNoEncontrado(f"El elemento {elemento_id} no existe o está fuera de tu alcance.")
        nueva_clave = _texto(clave, "una clave", 20).upper() if clave is not None else actual["clave"]
        nuevo_nombre = _texto(nombre, "un nombre", 80) if nombre is not None else actual["nombre"]
        # Los parámetros que no vienen se conservan: se cambia un número sin repetir todo el armado.
        nuevos = normalizar_parametros(actual["tipo"], {**(actual["parametros"] or {}), **(parametros or {})})
        if await self._elementos.clave_en_uso(nueva_clave, salvo=elemento_id):
            raise ErrorDeElementoParametrico(f"Ya existe un elemento con la clave {nueva_clave}.")
        cambia_la_receta = nuevos != normalizar_parametros(actual["tipo"], dict(actual["parametros"] or {}))
        # Cambiar la categoría sin la subcategoría pasa a la primera de la nueva; la subcategoría sola cambia dentro de la actual.
        nueva_categoria, nueva_subcategoria = validar_clasificacion(
            actual["tipo"],
            categoria if categoria is not None else actual["categoria"],
            subcategoria if subcategoria is not None else (actual["subcategoria"] if categoria is None else None),
        )
        cambia_la_clasificacion = (nueva_categoria, nueva_subcategoria) != (actual["categoria"], actual["subcategoria"])
        firma = actual.get("firma")
        if cambia_la_receta or cambia_la_clasificacion:
            # M-29: el elemento cambiado no puede quedar igual a otro. La subcategoría forma parte de la identidad (M-32).
            firma = firma_de_elemento(nueva_categoria, nueva_subcategoria, actual["tipo"], nuevos)
            await self._sin_duplicado(firma, salvo=elemento_id)
        if cambia_la_receta and await self._elementos.obras_congeladas_con(elemento_id):
            # D-639: las obras asignadas conservan la versión con que midieron; el resto pasa a la nueva.
            async with self._uow:
                if autor_id is None:
                    raise ErrorDeElementoParametrico("Falta quién cambia el elemento.")
                nueva = await self._elementos.crear_version(
                    elemento_id, clave=nueva_clave, nombre=nuevo_nombre, parametros=nuevos, autor_id=autor_id,
                    categoria=nueva_categoria, subcategoria=nueva_subcategoria, firma=str(firma),
                )
                await self._sincronizar_obras_con(nueva)
                await self._sincronizar_obras_con(elemento_id)
                await self._uow.commit()
            return nueva
        async with self._uow:
            await self._elementos.actualizar(
                elemento_id, clave=nueva_clave, nombre=nuevo_nombre, parametros=nuevos,
                categoria=nueva_categoria, subcategoria=nueva_subcategoria, firma=firma,
            )
            await self._sincronizar_obras_con(elemento_id)
            await self._uow.commit()
        return elemento_id

    async def eliminar(self, elemento_id: UUID) -> None:
        if await self._elementos.obtener(elemento_id) is None:
            raise ElementoParametricoNoEncontrado(f"El elemento {elemento_id} no existe o está fuera de tu alcance.")
        async with self._uow:
            obras = await self._elementos.obras_con_el_elemento(elemento_id)
            await self._elementos.eliminar(elemento_id)
            if self._sincronizador is not None:
                for obra_id in obras:
                    await self._sincronizador.de_la_obra(obra_id)
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
            obra_id = await self._elementos.obra_del_trazo(trazo_id)
            if self._sincronizador is not None and obra_id is not None:
                await self._sincronizador.de_la_obra(obra_id)
            await self._uow.commit()

    async def _elemento(self, elemento_id: UUID) -> dict[str, Any]:
        e = await self._elementos.obtener(elemento_id)
        if e is None:
            raise ElementoParametricoNoEncontrado(f"El elemento {elemento_id} no existe o está fuera de tu alcance.")
        return e

    @staticmethod
    def _toma_de(fila: dict[str, Any], elemento: dict[str, Any]) -> dict[str, Any]:
        toma = {m: bool(v) for m, v in dict(fila["toma"] or {}).items() if m in MATERIALES_DE_UN_ELEMENTO}
        return {
            "concepto_id": fila["concepto_id"],
            "clave": fila["clave"],
            "descripcion": fila["descripcion"],
            "toma": toma,
            **toma_por_unidad(elemento["tipo"], dict(elemento["parametros"] or {}), fila["unidad"], toma),
        }

    async def conceptos(self, elemento_id: UUID) -> list[dict[str, Any]]:
        """Los conceptos que toman una parte de la receta de este elemento, con lo que toman por unidad del concepto."""
        elemento = await self._elemento(elemento_id)
        return [self._toma_de(f, elemento) for f in await self._elementos.conceptos_de(elemento_id)]

    async def fijar_concepto(
        self, elemento_id: UUID, concepto_id: UUID, *, unidad: str, toma: dict[str, bool], autor_id: UUID
    ) -> None:
        elemento = await self._elemento(elemento_id)
        if not await self._elementos.concepto_existe(concepto_id):
            raise ElementoParametricoNoEncontrado(f"El concepto {concepto_id} no existe o está fuera de tu alcance.")
        limpia = {m: True for m in MATERIALES_DE_UN_ELEMENTO if toma.get(m)}
        if not limpia:
            raise ErrorDeElementoParametrico("El concepto debe tomar al menos un material del elemento.")
        # Valida la unidad y la cimbra contra la receta antes de guardar.
        toma_por_unidad(elemento["tipo"], dict(elemento["parametros"] or {}), unidad, limpia)
        async with self._uow:
            await self._elementos.fijar_concepto(
                elemento_id=elemento_id, concepto_id=concepto_id, unidad=unidad, toma=limpia, autor_id=autor_id
            )
            await self._sincronizar_obras_con(elemento_id)
            await self._uow.commit()

    async def quitar_concepto(self, elemento_id: UUID, concepto_id: UUID) -> None:
        await self._elemento(elemento_id)
        async with self._uow:
            await self._elementos.quitar_concepto(elemento_id=elemento_id, concepto_id=concepto_id)
            await self._sincronizar_obras_con(elemento_id)
            await self._uow.commit()

    async def conceptos_del_plano(self, plano_id: UUID) -> list[dict[str, Any]]:
        """Lo que cada concepto toma, en total, de los elementos colocados en el plano: su cantidad en la unidad del
        concepto y los materiales que toma (D-630)."""
        elementos = {e["id"]: e for e in await self._elementos.listar_todos()}
        totales = {t["elemento_id"]: t for t in (await self.totales_del_plano(plano_id))["totales"]}
        return filas_de_toma(elementos, totales, await self._elementos.de_todos_los_elementos())

    async def totales_del_plano(self, plano_id: UUID) -> dict[str, Any]:
        """Lo que llevan en total los elementos colocados en un plano: la receta de una muestra × lo que aporta cada trazo."""
        elementos = {e["id"]: e for e in await self._elementos.listar_todos()}
        trazos = await self._elementos.trazos_del_plano(plano_id)
        por_elemento = totales_de_trazos(elementos, trazos)
        return {
            "totales": sorted(por_elemento.values(), key=lambda x: x["clave"]),
            "trazos": [
                {"trazo_id": t["id"], "elemento_id": t["elemento_parametrico_id"], "lados_cimbra": t["lados_cimbra"]}
                for t in trazos
            ],
        }
