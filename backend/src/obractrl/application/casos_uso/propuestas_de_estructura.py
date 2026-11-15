"""Las propuestas de versión de concepto de los castillos, aparentes y forjadas, y su conciliación con el catálogo (Ola 3, 3A).

Costos o Control de obra proponen; solo Control de obra autoriza (y lo que propone Control de obra se registra ya autorizado). Cada
autorización crea la versión siguiente del concepto. Nada toca el catálogo ni pone precios: la conciliación muestra el catálogo
vigente, la versión propuesta y lo que calcula el elemento.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.elementos_parametricos import (
    ElementoParametricoNoEncontrado,
)
from obractrl.application.puertos.repositorios import UnidadDeTrabajo
from obractrl.domain.cuantificacion.autorizacion_de_elementos import (
    estado_de_alta,
    validar_que_autoriza,
    validar_que_propone,
)
from obractrl.domain.cuantificacion.comparacion_con_catalogo import expandir_composicion
from obractrl.domain.cuantificacion.correcciones_de_catalogo import (
    conciliar_con_catalogo,
    correcciones_de,
    numero_de_version,
    propuesta_de_concepto_nuevo,
)
from obractrl.domain.cuantificacion.elementos_parametricos import (
    ErrorDeElementoParametrico,
)
from obractrl.domain.cuantificacion.estructura_de_catalogo import (
    ElementoDeEstructuraNoEncontrado,
    claves_de_concepto,
    elemento_de_estructura,
)

__all__ = ["GestionarPropuestasDeEstructura"]


def _elemento(clave: str) -> Any:
    try:
        return elemento_de_estructura(clave)
    except ElementoDeEstructuraNoEncontrado as e:
        raise ElementoParametricoNoEncontrado(str(e)) from e


class GestionarPropuestasDeEstructura:
    def __init__(self, *, propuestas: Any, conceptos: Any, insumos: Any, uow: UnidadDeTrabajo) -> None:
        self._propuestas = propuestas
        self._conceptos = conceptos
        self._insumos = insumos
        self._uow = uow

    async def listar(self, elemento_clave: str) -> list[dict[str, Any]]:
        _elemento(elemento_clave)
        return list(await self._propuestas.del_elemento(elemento_clave))

    async def pendientes(self) -> list[dict[str, Any]]:
        return list(await self._propuestas.pendientes())

    async def _registrar(self, p: dict[str, Any], *, usuario_id: UUID, rol: str) -> UUID:
        """Costos deja la propuesta pendiente; la de Control de obra nace autorizada con su número de versión."""
        autorizada = estado_de_alta(rol) == "autorizado"
        numero = numero_de_version(p["clase"], await self._propuestas.autorizadas(p["concepto_clave"], p["clase"])) if autorizada else None
        return await self._propuestas.registrar(
            elemento_clave=p["elemento_clave"], concepto_clave=p["concepto_clave"], clase=p["clase"],
            estado="autorizada" if autorizada else "pendiente", version=numero, resumen=p["resumen"], detalle=p["detalle"],
            propuso_id=usuario_id, propuso_rol=rol,
            decidio_id=usuario_id if autorizada else None, decidio_rol=rol if autorizada else None,
        )

    async def proponer_correcciones(self, elemento_clave: str, *, usuario_id: UUID, rol: str) -> dict[str, Any]:
        """Registra las correcciones de fábrica del elemento que aún no están propuestas ni autorizadas (idempotente)."""
        validar_que_propone(rol)
        e = _elemento(elemento_clave)
        creadas: list[UUID] = []
        omitidas: list[str] = []
        async with self._uow:
            for p in correcciones_de(e.clave):
                vigentes = [
                    v for v in await self._propuestas.vigentes_del_concepto(p["concepto_clave"]) if v["clase"] == p["clase"]
                ]
                if vigentes:
                    omitidas.append(p["concepto_clave"])
                    continue
                creadas.append(await self._registrar(p, usuario_id=usuario_id, rol=rol))
            await self._uow.commit()
        return {"creadas": creadas, "omitidas": omitidas}

    async def proponer_concepto_por_altura(self, elemento_clave: str, alto_m: float, *, usuario_id: UUID, rol: str) -> UUID:
        """Q91: la forjada con otra altura que 4.20 m pide un concepto nuevo, pendiente de autorizar y sin precio."""
        validar_que_propone(rol)
        e = _elemento(elemento_clave)
        p = propuesta_de_concepto_nuevo(e, alto_m=alto_m)
        async with self._uow:
            if await self._propuestas.vigentes_del_concepto(p["concepto_clave"]):
                raise ErrorDeElementoParametrico(f"{p['concepto_clave']} ya está propuesto.")
            nuevo = await self._registrar(p, usuario_id=usuario_id, rol=rol)
            await self._uow.commit()
        return nuevo

    async def _pendiente(self, propuesta_id: UUID) -> dict[str, Any]:
        p = await self._propuestas.obtener(propuesta_id)
        if p is None:
            raise ElementoParametricoNoEncontrado(f"La propuesta {propuesta_id} no existe o está fuera de tu alcance.")
        if p["estado"] != "pendiente":
            raise ErrorDeElementoParametrico("Esta propuesta ya fue decidida.")
        return p  # type: ignore[no-any-return]

    async def autorizar(self, propuesta_id: UUID, *, usuario_id: UUID, rol: str) -> int:
        validar_que_autoriza(rol)
        p = await self._pendiente(propuesta_id)
        async with self._uow:
            numero = numero_de_version(p["clase"], await self._propuestas.autorizadas(p["concepto_clave"], p["clase"]))
            await self._propuestas.decidir(propuesta_id, estado="autorizada", version=numero, decidio_id=usuario_id, decidio_rol=rol)
            await self._uow.commit()
        return numero

    async def rechazar(self, propuesta_id: UUID, *, usuario_id: UUID, rol: str, motivo: str | None) -> None:
        validar_que_autoriza(rol)
        await self._pendiente(propuesta_id)
        limpio = " ".join((motivo or "").split())[:300] or None
        async with self._uow:
            await self._propuestas.decidir(
                propuesta_id, estado="rechazada", version=None, decidio_id=usuario_id, decidio_rol=rol, motivo=limpio
            )
            await self._uow.commit()

    async def conciliacion(self, elemento_clave: str) -> dict[str, Any]:
        """El elemento contra la composición real de cada concepto del catálogo (auxiliares expandidos), con las versiones propuestas."""
        e = _elemento(elemento_clave)
        composiciones: dict[str, list[Any]] = {}
        existentes: dict[str, bool] = {}
        for clave in claves_de_concepto(e):
            concepto = await self._conceptos.obtener_por_clave(clave)
            existentes[clave] = concepto is not None
            if concepto is None:
                continue
            filas = await self._conceptos.composicion_recursiva(concepto["id"])
            composiciones[clave] = expandir_composicion(filas, clave)
        claves = {c.clave.upper() for fs in composiciones.values() for c in fs}
        conocidos = await self._insumos.por_claves(sorted(claves | _claves_del_calculo(e)))
        for clave, filas in composiciones.items():
            composiciones[clave] = [
                replace(
                    f,
                    clave=f.clave.upper(),
                    descripcion=conocidos[f.clave.upper()][1].descripcion if f.clave.upper() in conocidos else f.descripcion,
                    unidad=(conocidos[f.clave.upper()][1].unidad or "") if f.clave.upper() in conocidos else f.unidad,
                )
                for f in filas
            ]
        propuestas: list[dict[str, Any]] = []
        for clave in claves_de_concepto(e):
            propuestas.extend(await self._propuestas.vigentes_del_concepto(clave))
        resultado = conciliar_con_catalogo(
            e.clave, composiciones, propuestas=propuestas, descripciones={k: v[1].descripcion for k, v in conocidos.items()}
        )
        for b in resultado["conceptos"]:
            b["en_catalogo"] = bool(existentes.get(b["concepto_clave"]))
        return resultado


def _claves_del_calculo(e: Any) -> set[str]:
    from obractrl.domain.cuantificacion.estructura_de_catalogo import insumos_del_concepto

    salida: set[str] = set()
    for c in e.conceptos:
        salida.update(k.upper() for k in insumos_del_concepto(e, c, e.alto_fijo_m or 3.0))
    return salida
