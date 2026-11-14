"""Insumos permitidos por tipo de elemento, insumos agregados a un elemento y su comparación con el concepto del catálogo
(plan de elementos de muro, fase D; M-25, M-28, M-46, M-55).

Las reglas de familias están en `domain.cuantificacion.insumos_permitidos`; la comparación, en
`domain.cuantificacion.comparacion_con_catalogo`. Aquí se lee la base de insumos, se rechaza el de otra familia con un error
claro, se crean los insumos **provisionales sin precio** (nunca se inventa un precio) y se arma la comparación de cada concepto
del elemento con su composición real del catálogo. Quién escribe (Control de obra y Costos) lo decide la API.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.elementos_parametricos import (
    ElementoParametricoNoEncontrado,
)
from obractrl.application.puertos.repositorios import UnidadDeTrabajo
from obractrl.domain.cuantificacion.comparacion_con_catalogo import (
    comparar_con_concepto,
    expandir_composicion,
)
from obractrl.domain.cuantificacion.elementos_parametricos import (
    ErrorDeElementoParametrico,
    normalizar_parametros,
)
from obractrl.domain.cuantificacion.insumos_permitidos import (
    CLASES_DE_INSUMO,
    SUGERENCIAS_DE_HERRAMIENTA,
    Insumo,
    describir_familias,
    es_permitido,
    familias_de_clase,
    normalizar_insumo_nuevo,
    validar_permitido,
)
from obractrl.domain.cuantificacion.materiales_de_elemento import (
    cantidades_por_insumo,
    claves_de_materiales,
)

__all__ = ["ComandoAgregarInsumos", "ComandoCrearInsumoProvisional", "GestionarInsumosDeElemento"]

_TIPO_EN_LA_BASE = {"material": "material", "trabajo": "mano_obra", "mano_obra": "mano_obra", "herramienta": "herramienta"}
"""Cómo se guarda cada clase en `insumo.tipo` (los destajos y la mano de obra comparten tipo; los equipos y las herramientas, la clase)."""


@dataclass(frozen=True, slots=True)
class ComandoAgregarInsumos:
    elemento_id: UUID
    insumos: Sequence[tuple[UUID, float]]
    autor_id: UUID


@dataclass(frozen=True, slots=True)
class ComandoCrearInsumoProvisional:
    elemento_id: UUID
    clase: str
    clave: str
    descripcion: str
    unidad: str
    autor_id: UUID
    familia: str | None = None
    subfamilia: str | None = None


def _ficha(i: Insumo, insumo_id: UUID | None, tipo: str) -> dict[str, Any]:
    return {
        "id": insumo_id,
        "clave": i.clave,
        "descripcion": i.descripcion,
        "clase": i.clase,
        "familia": i.familia,
        "subfamilia": i.subfamilia,
        "unidad": i.unidad,
        "precio": i.precio if not i.sin_precio else None,
        "sin_precio": i.sin_precio,
        "provisional": i.provisional,
        "permitido": i.clase is not None and es_permitido(tipo, i),
    }


class GestionarInsumosDeElemento:
    def __init__(self, *, elementos: Any, insumos: Any, conceptos: Any, uow: UnidadDeTrabajo) -> None:
        self._elementos = elementos
        self._insumos = insumos
        self._conceptos = conceptos
        self._uow = uow

    async def _elemento(self, elemento_id: UUID) -> dict[str, Any]:
        e = await self._elementos.obtener(elemento_id)
        if e is None:
            raise ElementoParametricoNoEncontrado(f"El elemento {elemento_id} no existe o está fuera de tu alcance.")
        return e  # type: ignore[no-any-return]

    # --- Familias y búsqueda (la ventana de agregar insumos) ----------------------------------------------------

    async def familias(self, tipo: str) -> dict[str, Any]:
        """Las clases de insumo con sus familias y cuáles son las usuales del tipo de elemento (M-55: salen todas; las que no
        son de las usuales llevan la marca)."""
        todos = await self._insumos.todos()
        clases: list[dict[str, Any]] = []
        for clave, info in CLASES_DE_INSUMO.items():
            de_la_clase = [i for _, i in todos if i.clase == clave]
            por_familia: dict[tuple[str, str | None], int] = {}
            for i in de_la_clase:
                k = (i.familia or "Sin familia", i.subfamilia)
                por_familia[k] = por_familia.get(k, 0) + 1
            familias = [
                {
                    "familia": f,
                    "subfamilia": s,
                    "total": n,
                    "usual": es_permitido(tipo, Insumo(clave="-", descripcion="-", clase=clave, familia=f, subfamilia=s)),
                }
                for (f, s), n in sorted(por_familia.items(), key=lambda kv: (kv[0][0].casefold(), (kv[0][1] or "").casefold()))
            ]
            clases.append(
                {
                    "clase": clave,
                    "nombre": info["nombre"],
                    "descripcion": info["descripcion"],
                    "total": len(de_la_clase),
                    "admitidas": describir_familias(tipo, clave),
                    "familias_usuales": [f.texto() for f in familias_de_clase(tipo, clave)] if clave != "herramienta" else [],
                    "familias": familias,
                }
            )
        return {"tipo": tipo, "clases": clases, "sugerencias_de_herramienta": [dict(s) for s in SUGERENCIAS_DE_HERRAMIENTA]}

    async def buscar(
        self, elemento_id: UUID, *, clase: str | None, familia: str | None, q: str | None, limite: int
    ) -> list[dict[str, Any]]:
        """Los insumos de la base filtrados por clase, familia y texto, cada uno con `permitido` para este elemento."""
        elemento = await self._elemento(elemento_id)
        tipo = elemento["tipo"]
        fichas = [_ficha(i, iid, tipo) for iid, i in await self._insumos.todos()]
        if clase:
            fichas = [f for f in fichas if f["clase"] == clase]
        if familia:
            fam = familia.casefold()
            fichas = [f for f in fichas if (f["familia"] or "").casefold() == fam or (f["subfamilia"] or "").casefold() == fam]
        fichas = [f for f in fichas if f["clase"] is not None]
        for t in (q or "").casefold().split():
            fichas = [
                f for f in fichas if t in f"{f['clave']} {f['descripcion']} {f['familia'] or ''} {f['subfamilia'] or ''}".casefold()
            ]
        return fichas[:limite]

    # --- Lo que lleva un elemento --------------------------------------------------------------------------------

    async def del_elemento(self, elemento_id: UUID) -> dict[str, Any]:
        """Los materiales que eligió el elemento y los insumos que se le agregaron, con su ficha de la base."""
        elemento = await self._elemento(elemento_id)
        tipo = elemento["tipo"]
        materiales = dict(elemento.get("materiales") or {})
        pares = claves_de_materiales(materiales)
        por_clave = await self._insumos.por_claves([c for _, c in pares])
        elegidos = []
        for material, clave in pares:
            iid, ins = por_clave.get(clave.upper(), (None, None))
            consumo = dict(materiales.get("cimbra") or {}).get(clave) if material == "cimbra" else None
            elegidos.append(
                {
                    "material": material,
                    "clave": clave,
                    "consumo": consumo,
                    "insumo": _ficha(ins, iid, tipo) if ins is not None else None,
                }
            )
        agregados = []
        filas = await self._insumos.del_elemento(elemento_id)
        for f in filas:
            hallado = await self._insumos.por_id(f["insumo_id"])
            if hallado is None:
                continue
            agregados.append({"id": f["id"], "cantidad": float(f["cantidad"]), "clase": f["clase"], "insumo": _ficha(hallado[1], hallado[0], tipo)})
        return {"elemento_id": elemento_id, "tipo": tipo, "materiales": elegidos, "insumos": agregados}

    async def agregar(self, cmd: ComandoAgregarInsumos) -> int:
        """Agrega insumos al elemento. Todo o nada: si uno es de otra familia se rechaza la petición entera con un error claro.
        Devuelve cuántos se agregaron (los que ya estaban no se repiten)."""
        elemento = await self._elemento(cmd.elemento_id)
        if not cmd.insumos:
            raise ErrorDeElementoParametrico("Marca al menos un insumo.")
        revisados: list[tuple[UUID, Insumo, float]] = []
        for insumo_id, cantidad in cmd.insumos:
            if cantidad < 0:
                raise ErrorDeElementoParametrico("La cantidad de un insumo no puede ser negativa.")
            hallado = await self._insumos.por_id(insumo_id)
            if hallado is None:
                raise ElementoParametricoNoEncontrado(f"El insumo {insumo_id} no existe o está fuera de tu alcance.")
            validar_permitido(elemento["tipo"], hallado[1])
            revisados.append((insumo_id, hallado[1], cantidad))
        nuevos = 0
        async with self._uow:
            for insumo_id, ins, cantidad in revisados:
                if await self._insumos.agregar(
                    elemento_id=cmd.elemento_id, insumo_id=insumo_id, clase=str(ins.clase), cantidad=cantidad, autor_id=cmd.autor_id
                ):
                    nuevos += 1
            await self._uow.commit()
        return nuevos

    async def cambiar_cantidad(self, elemento_id: UUID, insumo_id: UUID, cantidad: float) -> None:
        await self._elemento(elemento_id)
        if cantidad < 0:
            raise ErrorDeElementoParametrico("La cantidad de un insumo no puede ser negativa.")
        async with self._uow:
            if not await self._insumos.cambiar_cantidad(elemento_id, insumo_id, cantidad):
                raise ElementoParametricoNoEncontrado("El elemento no tiene ese insumo.")
            await self._uow.commit()

    async def quitar(self, elemento_id: UUID, insumo_id: UUID) -> None:
        await self._elemento(elemento_id)
        async with self._uow:
            if not await self._insumos.quitar(elemento_id, insumo_id):
                raise ElementoParametricoNoEncontrado("El elemento no tiene ese insumo.")
            await self._uow.commit()

    async def crear_provisional(self, cmd: ComandoCrearInsumoProvisional) -> UUID:
        """Crea un insumo desde la tarjeta del elemento: solo en las familias de su tipo, **provisional y sin precio**."""
        elemento = await self._elemento(cmd.elemento_id)
        nuevo = normalizar_insumo_nuevo(
            elemento["tipo"], clase=cmd.clase, clave=cmd.clave, descripcion=cmd.descripcion, unidad=cmd.unidad,
            familia=cmd.familia, subfamilia=cmd.subfamilia,
        )
        if await self._insumos.por_claves([nuevo.clave]):
            raise ErrorDeElementoParametrico(f"Ya existe un insumo con la clave {nuevo.clave}: elígelo en lugar de crearlo.")
        unidad_id = await self._insumos.unidad_id(nuevo.unidad)
        if unidad_id is None:
            raise ErrorDeElementoParametrico(f"La unidad «{nuevo.unidad}» no existe en el catálogo de unidades.")
        async with self._uow:
            familia_id = await self._insumos.asegurar_familia(nuevo.familia)
            if nuevo.subfamilia and nuevo.subfamilia != nuevo.familia:
                familia_id = await self._insumos.asegurar_familia(nuevo.subfamilia, padre=nuevo.familia)
            nuevo_id: UUID = await self._insumos.crear_provisional(
                tipo=_TIPO_EN_LA_BASE[nuevo.clase], clave=nuevo.clave, descripcion=nuevo.descripcion, unidad_id=unidad_id,
                familia_id=familia_id,
            )
            await self._uow.commit()
        return nuevo_id

    # --- Comparación con el concepto del catálogo ---------------------------------------------------------------

    async def comparacion(self, elemento_id: UUID, *, fila_id: UUID | None = None) -> dict[str, Any]:
        """Para cada concepto del catálogo que paga una parte del elemento: insumo por insumo, lo que lleva el catálogo contra
        lo que calcula el elemento, con la diferencia en % y la marca `=`, `≈`, `≠`. Un concepto nuevo propuesto no tiene
        composición en el catálogo: se muestra solo lo del elemento."""
        elemento = await self._elemento(elemento_id)
        materiales = dict(elemento.get("materiales") or {})
        filas = await self._elementos.conceptos_por_contexto(elemento_id)
        if fila_id is not None:
            filas = [f for f in filas if f["id"] == fila_id]
            if not filas:
                raise ElementoParametricoNoEncontrado(f"El concepto {fila_id} no es de este elemento.")
        parametros = normalizar_parametros(elemento["tipo"], dict(elemento["parametros"] or {}))
        propias = await self._insumos.por_claves([c for _, c in claves_de_materiales(materiales)])
        unidades = {k: (v[1].unidad or "") for k, v in propias.items()}
        bloques: list[dict[str, Any]] = []
        for f in filas:
            toma = {m: bool(v) for m, v in dict(f["toma"] or {}).items()}
            cantidades, avisos = cantidades_por_insumo(
                elemento["tipo"], parametros, materiales, unidad=f["unidad"], toma=toma,
                unidades_de_insumo={k.upper(): u for k, u in unidades.items()},
            )
            composicion = []
            if f["concepto_id"] is not None:
                composicion = expandir_composicion(await self._conceptos.composicion_recursiva(f["concepto_id"]), str(f["clave"]))
            claves = {c.upper() for c in cantidades} | {c.clave.upper() for c in composicion}
            conocidos = await self._insumos.por_claves(sorted(claves))
            descripciones = {k: v[1].descripcion for k, v in conocidos.items()}
            comparado = comparar_con_concepto(
                {k.upper(): v for k, v in cantidades.items()},
                [_con_unidad(c, conocidos) for c in composicion],
                descripciones=descripciones,
            )
            bloques.append(
                {
                    "fila_id": f["id"],
                    "concepto_clave": f["clave"],
                    "concepto_descripcion": f["descripcion"],
                    "unidad": f["unidad"],
                    "estado": f["estado"],
                    "toma": toma,
                    "sin_catalogo": f["concepto_id"] is None,
                    "avisos": avisos,
                    **comparado,
                }
            )
        return {"elemento_id": elemento_id, "umbral_igual_pct": 3.0, "umbral_aproximado_pct": 8.0, "conceptos": bloques}


def _con_unidad(c: Any, conocidos: dict[str, Any]) -> Any:
    hallado = conocidos.get(c.clave.upper())
    return replace(c, clave=c.clave.upper(), descripcion=hallado[1].descripcion if hallado else c.descripcion, unidad=(hallado[1].unidad or "") if hallado else c.unidad)
