"""Los conceptos que paga un elemento paramétrico por contexto y por escalón de altura (plan de elementos de muro, fase C).

Lee y escribe `elemento_concepto` (0112, ampliada en la 0128). Las reglas están en
`domain.cuantificacion.conceptos_de_elemento`; aquí se arma la lectura por contexto y se guardan las altas. Quién puede
escribir (Control de obra y Costos) lo decide la API. Un concepto NUEVO queda `propuesto`, sin precio: autorizarlo es de la
fase de roles y versiones.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.elementos_parametricos import (
    ElementoParametricoNoEncontrado,
)
from obractrl.application.puertos.repositorios import UnidadDeTrabajo
from obractrl.domain.cuantificacion.conceptos_de_elemento import (
    ConceptoDeElemento,
    Contexto,
    avisos_de_altura,
    describir_contexto,
    normalizar_clave_propuesta,
    normalizar_descripcion,
    normalizar_toma,
    resolver,
    validar_alta,
    validar_contexto,
)
from obractrl.domain.cuantificacion.elementos_parametricos import (
    ErrorDeElementoParametrico,
    normalizar_parametros,
    toma_por_unidad,
)

__all__ = ["ComandoAgregarConceptoDeElemento", "GestionarConceptosDeElemento"]


@dataclass(frozen=True, slots=True)
class ComandoAgregarConceptoDeElemento:
    elemento_id: UUID
    unidad: str
    toma: dict[str, bool]
    autor_id: UUID
    concepto_id: UUID | None = None
    clave_propuesta: str | None = None
    descripcion: str | None = None
    nivel_min: int | None = None
    nivel_max: int | None = None
    ubicacion: str | None = None
    alto_hasta_m: Decimal | None = None


def _concepto(f: dict[str, Any]) -> ConceptoDeElemento:
    return ConceptoDeElemento(
        id=f["id"],
        clave=f["clave"],
        descripcion=f["descripcion"],
        unidad=f["unidad"],
        toma={m: bool(v) for m, v in dict(f["toma"] or {}).items()},
        contexto=Contexto(f["nivel_min"], f["nivel_max"], f["ubicacion"]),
        alto_hasta_m=Decimal(str(f["alto_hasta_m"])) if f["alto_hasta_m"] is not None else None,
        estado=f["estado"],
        concepto_id=f["concepto_id"],
    )


class GestionarConceptosDeElemento:
    def __init__(self, *, elementos: Any, uow: UnidadDeTrabajo, sincronizador: Any | None = None) -> None:
        self._elementos = elementos
        self._uow = uow
        # Solo el concepto sin contexto ni escalón alimenta las tomas de las matrices (D-639); los demás esperan a la fase del Cuantificador.
        self._sincronizador = sincronizador

    async def _elemento(self, elemento_id: UUID) -> dict[str, Any]:
        e = await self._elementos.obtener(elemento_id)
        if e is None:
            raise ElementoParametricoNoEncontrado(f"El elemento {elemento_id} no existe o está fuera de tu alcance.")
        return e

    @staticmethod
    def _alto_del_elemento(elemento: dict[str, Any]) -> Decimal | None:
        """El alto con que se elige el escalón: el de un castillo; los demás elementos no se escalonan por su alto."""
        if elemento["tipo"] != "castillo":
            return None
        return Decimal(str(normalizar_parametros(elemento["tipo"], dict(elemento["parametros"] or {}))["alto"]))

    async def por_contexto(
        self, elemento_id: UUID, *, nivel: int | None = None, ubicacion: str | None = None, alto_m: Decimal | None = None
    ) -> dict[str, Any]:
        """Los conceptos del elemento. Con un nivel (o una ubicación) dice cuáles aplican y cuál paga cada parte; sin ellos
        los lista todos y avisa de los escalones que no alcanzan el alto del elemento."""
        elemento = await self._elemento(elemento_id)
        filas = await self._elementos.conceptos_por_contexto(elemento_id)
        conceptos = [_concepto(f) for f in filas]
        alto = alto_m if alto_m is not None else self._alto_del_elemento(elemento)
        filtrado = nivel is not None or ubicacion is not None
        elegidos: set[Any] = set()
        por_parte: dict[str, str] = {}
        if filtrado:
            r = resolver(conceptos, nivel=nivel, ubicacion=ubicacion, alto_m=alto)
            avisos = r.avisos
            elegidos = {c.id for c in r.elegidos}
            por_parte = {parte: c.clave for parte, c in r.por_parte.items()}
        else:
            avisos = avisos_de_altura(conceptos, alto) if alto is not None else []
        return {
            "alto_m": alto,
            "nivel": nivel,
            "ubicacion": ubicacion,
            "conceptos": [
                {
                    **f,
                    "contexto": describir_contexto(c.contexto),
                    "elegido": (c.id in elegidos) if filtrado else None,
                }
                for f, c in zip(filas, conceptos, strict=True)
            ],
            "por_parte": por_parte,
            "avisos": avisos,
        }

    async def agregar(self, cmd: ComandoAgregarConceptoDeElemento) -> UUID:
        elemento = await self._elemento(cmd.elemento_id)
        if (cmd.concepto_id is None) == (cmd.clave_propuesta is None):
            raise ErrorDeElementoParametrico("Elige un concepto del catálogo o propón uno nuevo con su clave, no los dos.")
        contexto = validar_contexto(cmd.nivel_min, cmd.nivel_max, cmd.ubicacion)
        toma = normalizar_toma(cmd.toma)
        # Valida la unidad y la cimbra contra la receta antes de guardar.
        toma_por_unidad(elemento["tipo"], dict(elemento["parametros"] or {}), cmd.unidad, toma)
        alto = cmd.alto_hasta_m
        if alto is not None and not (Decimal("0.001") <= alto <= Decimal("99.999")):
            raise ErrorDeElementoParametrico("El «hasta» del escalón es un alto en metros, de 0.001 a 99.999.")
        if cmd.concepto_id is not None:
            clave = await self._elementos.clave_de_concepto(cmd.concepto_id)
            if clave is None:
                raise ElementoParametricoNoEncontrado(f"El concepto {cmd.concepto_id} no existe o está fuera de tu alcance.")
            descripcion = normalizar_descripcion(cmd.descripcion) if cmd.descripcion is not None else None
            estado = "autorizado"
            clave_propuesta = None
        else:
            clave = clave_propuesta = normalizar_clave_propuesta(str(cmd.clave_propuesta))
            if await self._elementos.concepto_con_clave(clave):
                raise ErrorDeElementoParametrico(f"{clave} ya está en el catálogo: enlázalo en lugar de proponerlo como nuevo.")
            descripcion = normalizar_descripcion(cmd.descripcion or "")
            estado = "propuesto"
        nuevo = ConceptoDeElemento(
            id=None, clave=clave, descripcion=descripcion or "", unidad=cmd.unidad, toma=toma, contexto=contexto,
            alto_hasta_m=alto, estado=estado, concepto_id=cmd.concepto_id,
        )
        validar_alta([_concepto(f) for f in await self._elementos.conceptos_por_contexto(cmd.elemento_id)], nuevo)
        async with self._uow:
            fila_id: UUID = await self._elementos.agregar_concepto_por_contexto(
                elemento_id=cmd.elemento_id, concepto_id=cmd.concepto_id, clave_propuesta=clave_propuesta, descripcion=descripcion,
                unidad=cmd.unidad, toma=toma, nivel_min=contexto.nivel_min, nivel_max=contexto.nivel_max,
                ubicacion=contexto.ubicacion, alto_hasta_m=alto, estado=estado, autor_id=cmd.autor_id,
            )
            await self._sincronizar_si_es_general(cmd.elemento_id, nuevo)
            await self._uow.commit()
        return fila_id

    async def cambiar_descripcion(self, elemento_id: UUID, fila_id: UUID, descripcion: str) -> None:
        """Lo único editable de un concepto del elemento: la clave y el «hasta» de un escalón quedan fijos."""
        fila = await self._fila(elemento_id, fila_id)
        nueva = normalizar_descripcion(descripcion)
        async with self._uow:
            await self._elementos.cambiar_descripcion_de_concepto(fila["id"], nueva)
            await self._uow.commit()

    async def quitar(self, elemento_id: UUID, fila_id: UUID) -> None:
        fila = await self._fila(elemento_id, fila_id)
        async with self._uow:
            await self._elementos.quitar_concepto_por_contexto(fila["id"])
            await self._sincronizar_si_es_general(elemento_id, _concepto(fila))
            await self._uow.commit()

    async def _fila(self, elemento_id: UUID, fila_id: UUID) -> dict[str, Any]:
        await self._elemento(elemento_id)
        fila = await self._elementos.concepto_por_contexto(elemento_id, fila_id)
        if fila is None:
            raise ElementoParametricoNoEncontrado(f"El concepto {fila_id} no es de este elemento.")
        return fila  # type: ignore[no-any-return]

    async def _sincronizar_si_es_general(self, elemento_id: UUID, c: ConceptoDeElemento) -> None:
        general = c.concepto_id is not None and c.contexto == Contexto() and c.alto_hasta_m is None
        if general and self._sincronizador is not None:
            await self._sincronizador.de_las_obras_con(elemento_id)
